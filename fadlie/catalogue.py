"""Ce que Fadlie sait lire et écrire dans DataHub.

Une seule porte vers GMS, pour que les pièges vérifiés y soient réglés une fois :

- l'authentification est obligatoire (le quickstart la livre désactivée) ;
- `removeTerm` prend un `TermAssociationInput`, pas le `RemoveTermInput` que la
  symétrie laisse croire ;
- une écriture de colonne passe par `subResource` + `subResourceType`, pas par
  un urn de champ ;
- une erreur GraphQL n'est pas une exception HTTP : la réponse est un 200 avec
  un tableau `errors`. Qui ne le lit pas croit avoir écrit.
"""
from __future__ import annotations

import dataclasses
import json
import re
import urllib.error
import urllib.request
from typing import Any, Iterable

from .config import Config


def cle_colonne(nom: str) -> str:
    """La forme sous laquelle deux colonnes se comparent d'un système à l'autre.

    Deux normalisations, chacune mesurée sur le vrai catalogue :

    - **la casse** : les 18 colonnes marquées de `dbt/order_details` se
      retrouvent une pour une dans `powerbi/ORDER_DETAILS`, à la seule casse
      près. Les distinguer inventerait un écart de 100 %.
    - **les séparateurs** : `tableau/Top Product Category` porte
      `Category Name` là où la requête qui l'alimente porte `CATEGORY_NAME`. Un
      espace au lieu d'un tiret bas faisait tomber le recouvrement de 80 % à
      50 %, sous le seuil — le couple disparaissait sans que rien ne le signale.

    On ne va pas plus loin : rapprocher `cust_email` et `email` demanderait de
    deviner, et deviner est le travail du juge, pas celui d'une clé.
    """
    return re.sub(r"[^a-z0-9]+", "_", nom.lower()).strip("_")


class CatalogueError(RuntimeError):
    """DataHub a refusé, ou n'a pas répondu ce qu'on attendait."""


@dataclasses.dataclass(frozen=True)
class Colonne:
    nom: str
    type_natif: str
    description: str | None
    etiquettes: frozenset[str]
    termes: frozenset[str]

    @property
    def annotee(self) -> bool:
        return bool(self.etiquettes or self.termes)


@dataclasses.dataclass(frozen=True)
class Jeu:
    """Un jeu de données, réduit à ce qui sert à juger et à comparer."""

    urn: str
    nom: str
    plateforme: str
    description: str | None
    domaine: str | None
    proprietaires: tuple[str, ...]
    etiquettes: frozenset[str]
    termes: frozenset[str]
    colonnes: tuple[Colonne, ...]
    lignage_amont: int = 0
    lignage_aval: int = 0

    @property
    def noms_colonnes(self) -> frozenset[str]:
        """Les colonnes sous une forme comparable d'un système à l'autre."""
        return frozenset(cle_colonne(c.nom) for c in self.colonnes)

    @property
    def isole(self) -> bool:
        return self.lignage_amont == 0 and self.lignage_aval == 0

    def colonne(self, nom: str) -> Colonne | None:
        """La colonne, désignée par n'importe laquelle de ses écritures.

        Rend l'objet portant le **nom réel** du jeu : c'est celui-là qu'il faudra
        donner à DataHub pour écrire, pas la clé normalisée — une écriture sur un
        chemin de champ qui n'existe pas ne lève rien et ne fait rien.
        """
        cible = cle_colonne(nom)
        return next((c for c in self.colonnes if cle_colonne(c.nom) == cible), None)


_JEUX = """
query($debut:Int!, $nombre:Int!) {
  search(input:{type:DATASET, query:"*", start:$debut, count:$nombre}) {
    total
    searchResults { entity { ... on Dataset {
      urn
      name
      platform { name }
      properties { description }
      domain { domain { properties { name } } }
      ownership { owners { owner {
        ... on CorpUser { urn username }
        ... on CorpGroup { urn name } } } }
      globalTags { tags { tag { urn } } }
      glossaryTerms { terms { term { urn } } }
      schemaMetadata { fields {
        fieldPath nativeDataType description
        globalTags { tags { tag { urn } } }
        glossaryTerms { terms { term { urn } } } } }
      editableSchemaMetadata { editableSchemaFieldInfo {
        fieldPath description
        globalTags { tags { tag { urn } } }
        glossaryTerms { terms { term { urn } } } } }
      amont: lineage(input:{direction:UPSTREAM, start:0, count:1}) { total }
      aval:  lineage(input:{direction:DOWNSTREAM, start:0, count:1}) { total }
    } } } } }"""


def _urns(bloc: dict | None, cle: str, sous_cle: str) -> frozenset[str]:
    if not bloc:
        return frozenset()
    return frozenset(x[sous_cle]["urn"] for x in (bloc.get(cle) or []))


class Catalogue:
    """La connexion à DataHub. Sans état, sinon la configuration."""

    def __init__(self, config: Config, ouvrir=urllib.request.urlopen) -> None:
        self.config = config
        self._ouvrir = ouvrir  # injectable : les tests ne touchent pas le réseau

    # --- transport ------------------------------------------------------------
    def _gql(self, requete: str, variables: dict | None = None) -> dict:
        corps = json.dumps({"query": requete, "variables": variables or {}}).encode()
        req = urllib.request.Request(
            self.config.gms_url + "/api/graphql",
            data=corps,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.config.gms_token,
            },
        )
        try:
            with self._ouvrir(req, timeout=90) as r:
                brut = r.read()
        except urllib.error.HTTPError as e:
            # 401 mérite sa propre phrase : c'est l'erreur qu'on rencontrera, et
            # « HTTP Error 401 » n'aide personne à la corriger.
            if e.code == 401:
                raise CatalogueError(
                    "DataHub refuse le jeton (401). Vérifier DATAHUB_GMS_TOKEN — "
                    "un jeton émis avant un changement de clé de signature est invalide."
                ) from e
            raise CatalogueError(f"DataHub a répondu {e.code} sur /api/graphql") from e
        except OSError as e:
            raise CatalogueError(f"DataHub injoignable à {self.config.gms_url} : {e}") from e

        reponse = json.loads(brut)
        # Une erreur GraphQL arrive dans un 200. Sans ce contrôle, une mutation
        # refusée passe pour un succès et l'agent affirme avoir réparé.
        if reponse.get("errors"):
            messages = "; ".join(e.get("message", "?") for e in reponse["errors"])
            raise CatalogueError(f"DataHub : {messages}")
        if "data" not in reponse:
            raise CatalogueError(f"réponse inattendue de DataHub : {brut[:200]!r}")
        return reponse["data"]

    # --- lecture --------------------------------------------------------------
    def jeux(self, plafond: int = 1000) -> list[Jeu]:
        """Tous les jeux, avec ce qu'il faut pour les comparer."""
        tout: list[Jeu] = []
        debut, page = 0, 100
        while debut < plafond:
            d = self._gql(_JEUX, {"debut": debut, "nombre": min(page, plafond - debut)})
            resultats = d["search"]["searchResults"]
            tout.extend(self._vers_jeu(r["entity"]) for r in resultats)
            debut += len(resultats)
            if not resultats or debut >= d["search"]["total"]:
                break
        return tout

    @staticmethod
    def _vers_jeu(e: dict) -> Jeu:
        # Les annotations vivent à deux endroits : le schéma tel qu'ingéré, et la
        # couche « editable » que l'interface écrit. Les deux comptent, et les
        # ignorer d'un côté fait voir des écarts qui n'existent pas.
        par_champ: dict[str, dict[str, Any]] = {}
        for f in ((e.get("schemaMetadata") or {}).get("fields") or []):
            par_champ[f["fieldPath"]] = {
                "type": f.get("nativeDataType") or "",
                "description": f.get("description"),
                "etiquettes": set(_urns(f.get("globalTags"), "tags", "tag")),
                "termes": set(_urns(f.get("glossaryTerms"), "terms", "term")),
            }
        for f in ((e.get("editableSchemaMetadata") or {}).get("editableSchemaFieldInfo") or []):
            ligne = par_champ.setdefault(
                f["fieldPath"],
                {"type": "", "description": None, "etiquettes": set(), "termes": set()},
            )
            ligne["description"] = ligne["description"] or f.get("description")
            ligne["etiquettes"] |= set(_urns(f.get("globalTags"), "tags", "tag"))
            ligne["termes"] |= set(_urns(f.get("glossaryTerms"), "terms", "term"))

        proprietaires = tuple(
            o["owner"].get("urn", "")
            for o in ((e.get("ownership") or {}).get("owners") or [])
        )
        domaine = (((e.get("domain") or {}).get("domain") or {})
                   .get("properties") or {}).get("name")

        return Jeu(
            urn=e["urn"],
            nom=e["name"],
            plateforme=e["platform"]["name"],
            description=(e.get("properties") or {}).get("description"),
            domaine=domaine,
            proprietaires=proprietaires,
            etiquettes=_urns(e.get("globalTags"), "tags", "tag"),
            termes=_urns(e.get("glossaryTerms"), "terms", "term"),
            colonnes=tuple(
                Colonne(
                    nom=nom,
                    type_natif=v["type"],
                    description=v["description"],
                    etiquettes=frozenset(v["etiquettes"]),
                    termes=frozenset(v["termes"]),
                )
                for nom, v in par_champ.items()
            ),
            lignage_amont=((e.get("amont") or {}).get("total") or 0),
            lignage_aval=((e.get("aval") or {}).get("total") or 0),
        )

    # `entity(urn:)` plutôt que `dataset(urn:)` : le chemin passe par des
    # traitements autant que par des jeux, et il faut pouvoir interroger les deux
    # avec la même requête.
    _VOISINS = """
      query($urn:String!, $sens:LineageDirection!) {
        entity(urn:$urn) {
          ... on Dataset { lineage(input:{direction:$sens, start:0, count:200}) {
              relationships { entity { urn type } } } }
          ... on DataJob { lineage(input:{direction:$sens, start:0, count:200}) {
              relationships { entity { urn type } } } } } }"""

    # Un traitement relie deux jeux sans être un jeu. Filtrer sur `DATASET`
    # coupait le chemin exactement là où il passe : `postgres/customers` n'a
    # qu'un voisin, le DataJob `export_table_customers_to_s3`, qui mène à
    # `s3/customers`. Cette erreur a fabriqué des îlots qui n'existent pas.
    _RELAIS = ("DATASET", "DATA_JOB")

    def voisins_lignage(self, urn: str) -> set[str]:
        """Les entités directement reliées, dans les deux sens.

        Le sens ne nous intéresse pas : on cherche si deux copies communiquent,
        pas laquelle nourrit l'autre.
        """
        trouves: set[str] = set()
        for sens in ("UPSTREAM", "DOWNSTREAM"):
            e = self._gql(self._VOISINS, {"urn": urn, "sens": sens}).get("entity") or {}
            for r in ((e.get("lineage") or {}).get("relationships") or []):
                if r["entity"]["type"] in self._RELAIS:
                    trouves.add(r["entity"]["urn"])
        return trouves

    def graphe_lignage(self, jeux: Iterable[Jeu]) -> dict[str, set[str]]:
        """Le graphe de lignage entier, non orienté, traitements compris.

        Mesuré, et c'est le résultat qui fonde Fadlie : **ce graphe est une seule
        composante**. 103 sommets, tout jeu atteint tout autre, distance médiane
        4 — et les copies d'une même table sont à 2 ou 4, c'est-à-dire
        indiscernables d'un couple pris au hasard.

        Autrement dit la connexité ne dit **rien** sur « est-ce la même donnée ».
        On construit quand même le graphe, parce qu'une distance courte reste une
        pièce à verser au dossier ; mais elle ne décide pas, et il ne faut jamais
        la lire comme un verdict.
        """
        graphe: dict[str, set[str]] = {j.urn: set() for j in jeux}
        a_faire = list(graphe)
        vus: set[str] = set()
        while a_faire:
            urn = a_faire.pop()
            if urn in vus:
                continue
            vus.add(urn)
            for voisin in self.voisins_lignage(urn):
                graphe.setdefault(urn, set()).add(voisin)
                graphe.setdefault(voisin, set()).add(urn)
                if voisin not in vus:
                    a_faire.append(voisin)
        return graphe

    # --- écriture -------------------------------------------------------------
    # Chaque écriture est nommée par ce qu'elle répare, pas par la mutation
    # qu'elle appelle : l'appelant raisonne en gouvernance, pas en GraphQL.

    def poser_etiquettes(self, urn: str, etiquettes: Iterable[str],
                         colonne: str | None = None) -> None:
        variables: dict[str, Any] = {"i": {"tagUrns": list(etiquettes), "resourceUrn": urn}}
        if colonne:
            variables["i"]["subResource"] = colonne
            variables["i"]["subResourceType"] = "DATASET_FIELD"
        self._gql("mutation($i:AddTagsInput!){ addTags(input:$i) }", variables)

    def poser_termes(self, urn: str, termes: Iterable[str],
                     colonne: str | None = None) -> None:
        variables: dict[str, Any] = {"i": {"termUrns": list(termes), "resourceUrn": urn}}
        if colonne:
            variables["i"]["subResource"] = colonne
            variables["i"]["subResourceType"] = "DATASET_FIELD"
        self._gql("mutation($i:AddTermsInput!){ addTerms(input:$i) }", variables)

    def poser_proprietaires(self, urn: str, proprietaires: Iterable[str],
                            type_de_role: str = "TECHNICAL_OWNER") -> None:
        owners = [
            {
                "ownerUrn": p,
                "ownerEntityType": "CORP_GROUP" if ":corpGroup:" in p else "CORP_USER",
                "type": type_de_role,
            }
            for p in proprietaires
        ]
        if not owners:
            return
        self._gql(
            "mutation($i:AddOwnersInput!){ addOwners(input:$i) }",
            {"i": {"owners": owners, "resourceUrn": urn}},
        )

    def poser_description(self, urn: str, description: str,
                          colonne: str | None = None) -> None:
        entree: dict[str, Any] = {"description": description, "resourceUrn": urn}
        if colonne:
            entree["subResource"] = colonne
            entree["subResourceType"] = "DATASET_FIELD"
        self._gql(
            "mutation($i:DescriptionUpdateInput!){ updateDescription(input:$i) }",
            {"i": entree},
        )

    def retirer_etiquette(self, urn: str, etiquette: str,
                          colonne: str | None = None) -> None:
        entree: dict[str, Any] = {"tagUrn": etiquette, "resourceUrn": urn}
        if colonne:
            entree["subResource"] = colonne
            entree["subResourceType"] = "DATASET_FIELD"
        self._gql("mutation($i:TagAssociationInput!){ removeTag(input:$i) }", {"i": entree})

    def retirer_terme(self, urn: str, terme: str, colonne: str | None = None) -> None:
        # `TermAssociationInput`, et non `RemoveTermInput` : la symétrie avec
        # `addTerms` est trompeuse, et le message d'erreur est un « Unknown type »
        # qui n'oriente vers rien.
        entree: dict[str, Any] = {"termUrn": terme, "resourceUrn": urn}
        if colonne:
            entree["subResource"] = colonne
            entree["subResourceType"] = "DATASET_FIELD"
        self._gql("mutation($i:TermAssociationInput!){ removeTerm(input:$i) }", {"i": entree})
