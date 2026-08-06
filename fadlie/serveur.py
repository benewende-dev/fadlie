"""Le serveur MCP : quatre outils, un jeton, aucune panne bavarde.

Trois principes repris de Naaba, où ils ont été payés.

**L'autorisation vient du transport, jamais des arguments.** Aucun outil ne prend
de jeton ni d'identité : c'est l'en-tête `Authorization` qui décide, avant que le
moindre outil ne soit appelé. Un test l'impose, parce que rien dans le langage ne
l'empêche.

**Une panne ne raconte pas la base au client.** Le SDK enveloppe toute exception
dans `ToolError(f"Error executing tool {nom}: {e}")` et transmet ce texte tel
quel. Vérifié sur Naaba : une erreur de connexion y mettait l'hôte, le port et
l'utilisateur de la base. Tout outil passe donc par `_executer`, qui journalise
le détail et rend une phrase neutre. Les erreurs qui disent *quoi corriger*
passent, elles.

**Rien n'est écrit sans qu'on l'ait demandé deux fois.** `apply_governance` est
à blanc par défaut, et le défaut est dans le code.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from mcp.server.mcpserver import MCPServer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .agent import Agent, Rapport
from .catalogue import CatalogueError
from .config import Config, ConfigError
from .ecart import Ecart
from .juge import JugeError
from .reparer import appliquer

journal = logging.getLogger("fadlie")

# Une analyse complète coûte une centaine d'invocations du juge. La garder
# quelques minutes rend les outils utilisables ; la garder plus longtemps
# ferait mentir `apply_governance` sur l'état réel du catalogue.
DUREE_CACHE = int(os.environ.get("FADLIE_CACHE_SECONDS", "300"))


class _Analyse:
    """Le dernier rapport, et un verrou pour ne pas le calculer en double."""

    def __init__(self, agent: Agent) -> None:
        self.agent = agent
        self._verrou = threading.Lock()
        self._rapport: Rapport | None = None
        self._date: float = 0.0

    def rapport(self, forcer: bool = False) -> Rapport:
        with self._verrou:
            frais = self._rapport is not None and time.time() - self._date < DUREE_CACHE
            if forcer or not frais:
                self._rapport = self.agent.analyser()
                self._date = time.time()
            return self._rapport

    @property
    def age(self) -> int:
        return int(time.time() - self._date) if self._rapport else -1

    def prechauffer(self) -> None:
        """Calcule le premier rapport à part, pendant que le serveur écoute.

        Mesuré : une analyse complète prend **238 secondes** — 67 jeux lus, 97
        couples soumis au juge. Sans préchauffage, le premier appel d'outil les
        attend, et quatre minutes de silence se lisent comme une panne. Le
        démarrage n'est pas bloqué pour autant : `/health` doit répondre tout de
        suite, sinon App Runner déclare le service mort et le remplace en boucle.
        """

        def travailler():
            try:
                self.rapport()
                journal.info("préchauffage terminé")
            except Exception:  # noqa: BLE001 — un échec ici ne doit pas tuer le serveur
                journal.exception("préchauffage impossible ; le premier appel réessaiera")

        threading.Thread(target=travailler, name="fadlie-prechauffage",
                         daemon=True).start()


def _executer(nom: str, faire):
    """Journalise le détail, ne rend au client que ce qui l'aide.

    `CatalogueError`, `JugeError` et `ConfigError` disent quoi corriger : elles
    passent. Tout le reste est un défaut de Fadlie, et son texte peut contenir
    n'importe quoi — un hôte, un port, un jeton mal placé.
    """
    try:
        return faire()
    except (CatalogueError, JugeError, ConfigError) as e:
        journal.warning("%s : %s", nom, e)
        raise
    except Exception:
        journal.exception("%s a échoué", nom)
        raise RuntimeError(
            f"{nom} n'a pas abouti. Le détail est dans le journal du serveur."
        ) from None


def _nommer(rapport: Rapport):
    noms = {j.urn: f"{j.plateforme}/{j.nom}" for g in rapport.groupes for j in g.jeux}
    return lambda urn: noms.get(urn, urn)


def _desaccord_en_dict(d, nom) -> dict[str, Any]:
    """Un désaccord, en données plutôt qu'en phrase.

    `Desaccord.resume()` est en français : c'est une aide de travail, et les
    réponses d'outil sont une surface publique. Rendre la structure évite d'avoir
    à traduire de la prose, et laisse l'appelant la formuler comme il veut.
    """
    return {
        "kind": d.genre,
        "column": d.colonne,
        "values": [{"dataset": nom(u), "dataset_urn": u, "value": v}
                   for u, v in d.valeurs],
        "resolution": "left to a human: Fadlie reports the conflict, it does not pick",
    }


def _ecart_en_dict(e: Ecart, nom) -> dict[str, Any]:
    return {
        "dataset": nom(e.cible),
        "dataset_urn": e.cible,
        "column": e.colonne,
        "kind": e.genre,
        "value": e.libelle or e.valeur,
        # La provenance n'est pas décorative : c'est ce qui distingue une valeur
        # recopiée d'une valeur inventée. Elle accompagne toujours la valeur.
        "copied_from": nom(e.source),
        "copied_from_urn": e.source,
    }


class Authentification(BaseHTTPMiddleware):
    """Le jeton, avant tout le reste."""

    def __init__(self, app, jeton: str) -> None:
        super().__init__(app)
        self.jeton = jeton

    async def dispatch(self, requete, suivant):
        if requete.url.path == "/health":
            return await suivant(requete)
        entete = requete.headers.get("authorization", "")
        presente = entete[7:] if entete.lower().startswith("bearer ") else ""
        # Comparaison à temps constant : la longueur du jeton ne doit pas fuir.
        import hmac

        if not presente or not hmac.compare_digest(presente, self.jeton):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await suivant(requete)


def construire(config: Config | None = None, agent: Agent | None = None,
               prechauffer: bool = False) -> MCPServer:
    config = config or Config.depuis_environnement()
    analyse = _Analyse(agent or Agent(config))
    if prechauffer:
        analyse.prechauffer()

    serveur = MCPServer(
        name="fadlie",
        title="Fadlie — governance that travels with the data",
        version="0.1.0",
        instructions=(
            "Fadlie finds datasets that hold the same data across different "
            "systems, and the governance that stopped at one of them. It never "
            "writes a value it did not read from an identified twin."
        ),
    )

    @serveur.tool(
        description="Counts for the whole catalog: datasets, duplicate groups, "
                    "governance gaps, and disagreements the agent refused to settle."
    )
    def catalog_summary() -> dict[str, Any]:
        def faire():
            r = analyse.rapport()
            return {
                "pairs_examined": r.couples_examines,
                "pairs_confirmed_same_data": r.couples_confirmes,
                "duplicate_groups": len(r.groupes),
                "governance_gaps": len(r.ecarts),
                "datasets_with_gaps": r.jeux_a_completer,
                "disagreements": len(r.desaccords),
                "analysis_age_seconds": analyse.age,
            }

        return _executer("catalog_summary", faire)

    @serveur.tool(
        description="Groups of datasets that hold the same data, across platforms. "
                    "Each group carries the judge's verdict for every pair."
    )
    def find_duplicate_datasets() -> dict[str, Any]:
        def faire():
            r = analyse.rapport()
            nom = _nommer(r)
            return {"groups": [
                {
                    "name": g.nom,
                    "platforms": list(g.plateformes),
                    "datasets": [nom(j.urn) for j in g.jeux],
                    "urns": [j.urn for j in g.jeux],
                    "verdicts": [
                        {"a": nom(a), "b": nom(b),
                         "confidence": v.confiance, "reason": v.raison}
                        for a, b, v in g.verdicts
                    ],
                }
                for g in r.groupes
            ]}

        return _executer("find_duplicate_datasets", faire)

    @serveur.tool(
        description="Governance a dataset is missing that one of its twins already "
                    "carries — owners, domain, descriptions, column tags and terms. "
                    "Every entry names the dataset the value was copied from. "
                    "Optionally filter by a dataset name or urn fragment."
    )
    def governance_gaps(dataset: str | None = None, limit: int = 50) -> dict[str, Any]:
        def faire():
            r = analyse.rapport()
            nom = _nommer(r)
            ecarts = list(r.ecarts)
            if dataset:
                aiguille = dataset.lower()
                ecarts = [e for e in ecarts
                          if aiguille in e.cible.lower() or aiguille in nom(e.cible).lower()]
            return {
                "total": len(ecarts),
                "returned": min(limit, len(ecarts)),
                "gaps": [_ecart_en_dict(e, nom) for e in ecarts[:limit]],
                "disagreements": [_desaccord_en_dict(d, nom) for d in r.desaccords],
            }

        return _executer("governance_gaps", faire)

    @serveur.tool(
        description="Write the missing governance into DataHub. Dry run by default: "
                    "call with dry_run=false to actually write. Only ever copies "
                    "values read from an identified twin — nothing is generated."
    )
    def apply_governance(dataset: str | None = None,
                         dry_run: bool = True) -> dict[str, Any]:
        def faire():
            r = analyse.rapport()
            nom = _nommer(r)
            ecarts = list(r.ecarts)
            if dataset:
                aiguille = dataset.lower()
                ecarts = [e for e in ecarts
                          if aiguille in e.cible.lower() or aiguille in nom(e.cible).lower()]
            resultat = appliquer(analyse.agent.catalogue, ecarts, pour_de_vrai=not dry_run)
            if not dry_run:
                # Le catalogue a changé : le rapport en cache décrit un état qui
                # n'existe plus. Le garder ferait proposer deux fois les mêmes
                # écritures, et compter deux fois le même travail.
                analyse.rapport(forcer=True)
            return {
                "dry_run": dry_run,
                "applied": resultat.poses,
                "would_apply": resultat.simules,
                "failed": len(resultat.echecs),
                "failures": [{"dataset": nom(e.cible), "reason": raison}
                             for e, raison in resultat.echecs[:10]],
                "summary": resultat.resume(),
            }

        return _executer("apply_governance", faire)

    # App Runner sonde une URL sans en-tête : elle doit répondre sans jeton, et
    # ne rien dire du catalogue. Sinon le service est déclaré mort et remplacé
    # en boucle — l'échec ressemble alors à un problème d'image.
    @serveur.custom_route("/health", methods=["GET"])
    async def sante(_requete):
        return JSONResponse({"status": "ok", "service": "fadlie"})

    return serveur


def application(config: Config | None = None):
    """L'application HTTP, jeton compris."""
    config = config or Config.depuis_environnement()
    jeton = os.environ.get("FADLIE_API_TOKEN", "").strip()
    if not jeton:
        # Pas de repli. Un serveur qui démarre sans jeton parce que la variable
        # manquait est un serveur ouvert, et personne ne s'en aperçoit avant
        # qu'il soit trop tard.
        raise ConfigError(
            "FADLIE_API_TOKEN n'est pas renseignée. Le serveur ne démarre pas "
            "sans jeton : il serait ouvert à tous."
        )
    if len(jeton) < 24:
        raise ConfigError("FADLIE_API_TOKEN doit faire au moins 24 caractères.")

    serveur = construire(config, prechauffer=True)
    # `host` ne choisit pas l'adresse d'écoute — elle vient d'uvicorn. Elle ne
    # décide que de la protection anti-DNS-rebinding, et seulement pour
    # 127.0.0.1. Piège mesuré sur Naaba : « 0.0.0.0 » la laissait désactivée en
    # donnant à lire l'inverse.
    app = serveur.streamable_http_app(json_response=True)
    app.add_middleware(Authentification, jeton=jeton)
    return app
