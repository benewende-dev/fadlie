"""Ce qu'un jumeau a et que l'autre n'a pas.

Une fois qu'un juge a confirmé que deux jeux portent la même donnée, comparer
leur gouvernance est mécanique. Ce qui ne l'est pas, ce sont deux règles.

**Fadlie ne rédige jamais, il recopie.** Aucune valeur écrite dans le catalogue
n'est produite par un modèle : chacune vient d'un jeu identifié, qui la portait
déjà. La provenance est donc intrinsèque et vérifiable — on peut toujours ouvrir
la source et constater. Une description inventée par une machine, elle, est
indiscernable d'une description écrite par l'équipe qui connaît la donnée ; six
mois plus tard, plus personne ne sait laquelle est laquelle. (Naaba a payé ça :
une fusion réécrivait le contenu sans la source, et la provenance affirmait le
contraire de la vérité. Une provenance fausse est pire qu'une provenance
absente : elle se vérifie, et elle ment.)

**Un désaccord n'est pas un écart.** Si deux jumeaux portent des domaines
différents, il n'y a rien à propager : quelqu'un a décidé, ou quelqu'un s'est
trompé, et dans les deux cas ce n'est pas à un agent de choisir. Le désaccord est
signalé tel quel.
"""
from __future__ import annotations

import collections
import dataclasses
from typing import Iterable

from .catalogue import Jeu

# Ce qui se propage, et sous quel nom lisible.
GENRES = {
    "owner": "propriétaire",
    "domain": "domaine",
    "description": "description",
    "column_tag": "étiquette de colonne",
    "column_term": "terme de colonne",
    "column_description": "description de colonne",
}


@dataclasses.dataclass(frozen=True)
class Ecart:
    """Une valeur qui manque ici, et le jeu nommé qui la porte déjà."""

    cible: str            # urn du jeu à compléter
    source: str           # urn du jumeau d'où vient la valeur — jamais vide
    genre: str            # une clé de GENRES
    valeur: str           # ce qui s'écrit : un urn pour owner/domain/tag/term
    colonne: str | None = None
    libelle: str | None = None   # ce qui se lit, quand `valeur` est un urn

    def __post_init__(self) -> None:
        if self.genre not in GENRES:
            raise ValueError(f"genre inconnu : {self.genre!r}")
        if not self.source:
            raise ValueError("un écart sans source ne doit pas exister : "
                             "Fadlie recopie, il ne rédige pas")

    def resume(self, nom=lambda urn: urn) -> str:
        ou = f".{self.colonne}" if self.colonne else ""
        return (f"{nom(self.cible)}{ou} — {GENRES[self.genre]} manquant : "
                f"{self.libelle or self.valeur}  (depuis {nom(self.source)})")


@dataclasses.dataclass(frozen=True)
class Desaccord:
    """Deux jumeaux affirment des choses différentes. On ne tranche pas."""

    genre: str
    colonne: str | None
    valeurs: tuple[tuple[str, str], ...]   # (urn, valeur)

    def resume(self, nom=lambda urn: urn) -> str:
        ou = f".{self.colonne}" if self.colonne else ""
        details = " / ".join(f"{nom(u)}: {v}" for u, v in self.valeurs)
        return f"désaccord sur {GENRES[self.genre]}{ou} — {details}"


def _valeurs_uniques(porteurs: list[tuple[str, str]]) -> set[str]:
    return {v for _, v in porteurs}


def _propager_valeur_simple(groupe: list[Jeu], genre: str,
                            lire) -> tuple[list[Ecart], list[Desaccord]]:
    """Un attribut à valeur unique : domaine, description.

    Propagé seulement si tous ceux qui l'ont sont d'accord. Sinon, désaccord.
    """
    porteurs = [(j.urn, lire(j)) for j in groupe if lire(j)]
    if not porteurs:
        return [], []
    valeurs = _valeurs_uniques(porteurs)
    if len(valeurs) > 1:
        return [], [Desaccord(genre=genre, colonne=None, valeurs=tuple(sorted(porteurs)))]
    # Source déterministe : le même appel doit produire le même plan, sinon deux
    # exécutions ne se comparent pas.
    source, valeur = sorted(porteurs)[0]
    manquants = [j for j in groupe if not lire(j)]
    return ([Ecart(cible=j.urn, source=source, genre=genre, valeur=valeur)
             for j in manquants], [])


def comparer(groupe: Iterable[Jeu]) -> tuple[list[Ecart], list[Desaccord]]:
    """Les écarts de gouvernance dans un groupe de jumeaux **déjà confirmés**.

    Cette fonction ne juge rien : elle suppose que le groupe qu'on lui donne
    porte bien la même donnée. C'est au juge de l'avoir dit.
    """
    groupe = sorted(groupe, key=lambda j: j.urn)
    if len(groupe) < 2:
        return [], []

    ecarts: list[Ecart] = []
    desaccords: list[Desaccord] = []

    # --- domaine et description : une seule valeur, ou rien ------------------
    # Le domaine se compare et s'écrit par son urn ; son nom ne sert qu'à être lu.
    # Deux domaines peuvent porter le même nom, et `setDomain` refuse un nom.
    e, d = _propager_valeur_simple(groupe, "domain", lambda j: j.domaine_urn)
    libelles = {j.domaine_urn: j.domaine for j in groupe if j.domaine_urn}
    ecarts += [dataclasses.replace(x, libelle=libelles.get(x.valeur)) for x in e]
    desaccords += [
        Desaccord(genre=dd.genre, colonne=dd.colonne,
                  valeurs=tuple((u, libelles.get(v) or v) for u, v in dd.valeurs))
        for dd in d
    ]
    e, d = _propager_valeur_simple(groupe, "description", lambda j: j.description)
    ecarts += e
    desaccords += d

    # --- propriétaires : un ensemble, pas une valeur -------------------------
    # Plusieurs propriétaires ne se contredisent pas ; on complète chacun avec ce
    # que les autres portent, sans jamais en retirer.
    origine_proprietaire: dict[str, str] = {}
    for j in groupe:
        for p in j.proprietaires:
            origine_proprietaire.setdefault(p, j.urn)
    for j in groupe:
        for p, source in sorted(origine_proprietaire.items()):
            if p not in j.proprietaires:
                ecarts.append(Ecart(cible=j.urn, source=source,
                                    genre="owner", valeur=p))

    # --- les colonnes communes ----------------------------------------------
    communes = set.intersection(*[set(j.noms_colonnes) for j in groupe])
    for colonne in sorted(communes):
        cellules = {j.urn: j.colonne(colonne) for j in groupe}

        for genre, attribut in (("column_tag", "etiquettes"), ("column_term", "termes")):
            origine: dict[str, str] = {}
            for j in groupe:
                for valeur in sorted(getattr(cellules[j.urn], attribut)):
                    origine.setdefault(valeur, j.urn)
            for j in groupe:
                portees = getattr(cellules[j.urn], attribut)
                for valeur, source in sorted(origine.items()):
                    if valeur not in portees:
                        ecarts.append(Ecart(cible=j.urn, source=source, genre=genre,
                                            valeur=valeur, colonne=cellules[j.urn].nom))

        # La description de colonne, elle, est une valeur unique : même règle que
        # le domaine, désaccord compris.
        porteurs = [(j.urn, cellules[j.urn].description)
                    for j in groupe if cellules[j.urn].description]
        if not porteurs:
            continue
        if len(_valeurs_uniques(porteurs)) > 1:
            desaccords.append(Desaccord(genre="column_description", colonne=colonne,
                                        valeurs=tuple(sorted(porteurs))))
            continue
        source, valeur = sorted(porteurs)[0]
        for j in groupe:
            if not cellules[j.urn].description:
                ecarts.append(Ecart(cible=j.urn, source=source,
                                    genre="column_description", valeur=valeur,
                                    colonne=cellules[j.urn].nom))

    return ecarts, desaccords


def par_cible(ecarts: Iterable[Ecart]) -> dict[str, list[Ecart]]:
    """Regroupe pour un rapport lisible : un jeu, tout ce qui lui manque."""
    groupes: dict[str, list[Ecart]] = collections.defaultdict(list)
    for e in ecarts:
        groupes[e.cible].append(e)
    return dict(groupes)
