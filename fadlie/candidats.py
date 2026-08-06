"""Présélection : quels couples de jeux méritent qu'on les juge.

Cette couche ne décide rien. Elle réduit 67 jeux — 2 211 couples — à une poignée
que le juge examinera, et elle rassemble pour lui les preuves : recouvrement des
colonnes, noms, types, isolement dans le lignage.

Pourquoi elle ne décide pas, mesuré sur le vrai graphe : trois groupes homonymes
sur quinze **ne sont pas la même chose**. `custom_sql_query` réunit quatre jeux
tableau du même nom dont les colonnes ne se recouvrent pas du tout ;
`promotions` recouvre 9 %. Le nom présélectionne, il ne tranche pas.

Et inversement, un fort recouvrement ne suffit pas non plus : quatre tables de
référence à quatre colonnes (`countries`, `regions`, `warehouses`,
`product_categories`) se ressemblent structurellement sans être la même donnée.
C'est exactement le genre de couple qu'on soumet à un juge.

Et le lignage ne tranche pas non plus — c'est le résultat le plus utile de tous.
Le graphe de lignage du catalogue est **une seule composante** : 103 sommets,
tout jeu atteint tout autre, distance médiane 4. Les copies d'une même table
sont à distance 2 ou 4, exactement comme deux jeux pris au hasard. La connexité
ne porte donc aucune information sur « est-ce la même donnée ». On la reporte
comme une pièce du dossier, jamais comme un verdict.

Il reste donc, pour décider : la structure, qui dit « peut-être », et un juge.
"""
from __future__ import annotations

import collections
import dataclasses
import itertools
import re

from .catalogue import Jeu

# Suffixes qui marquent une copie plutôt qu'une autre donnée. Retirés seulement
# pour comparer les noms — jamais pour désigner un jeu.
_SUFFIXES = ("_replica", "_copy", "_bak", "_backup", "_raw", "_staging", "_stg",
             "_tmp", "_v2", "_new", "_old")


def normaliser(nom: str) -> str:
    n = re.sub(r"[^a-z0-9]+", "_", nom.lower()).strip("_")
    for s in _SUFFIXES:
        if n.endswith(s):
            n = n[: -len(s)]
            break
    return n


def recouvrement(a: Jeu, b: Jeu) -> float:
    """Jaccard sur les noms de colonnes, casse ignorée.

    Casse ignorée parce que c'est mesuré : les 18 colonnes marquées de
    `dbt/order_details` se retrouvent une pour une dans `powerbi/ORDER_DETAILS`,
    à la seule casse près. Les distinguer inventerait un écart.
    """
    x, y = a.noms_colonnes, b.noms_colonnes
    if not x or not y:
        return 0.0
    return len(x & y) / len(x | y)


def distances_depuis(graphe: dict[str, set[str]]):
    """Rend une fonction (a, b) → longueur du plus court chemin, ou None.

    Un parcours en largeur par appel suffit : la présélection ne garde qu'une
    poignée de couples, et mémoriser des composantes entières coûterait plus que
    ça ne rapporte.
    """
    def distance(a: str, b: str) -> int | None:
        if a == b:
            return 0
        vus, file = {a}, collections.deque([(a, 0)])
        while file:
            u, d = file.popleft()
            for v in graphe.get(u, ()):
                if v in vus:
                    continue
                if v == b:
                    return d + 1
                vus.add(v)
                file.append((v, d + 1))
        return None

    return distance


@dataclasses.dataclass(frozen=True)
class Candidat:
    """Un couple à juger, avec de quoi le juger."""

    gauche: Jeu
    droite: Jeu
    recouvrement: float
    meme_nom: bool
    colonnes_communes: tuple[str, ...]
    colonnes_propres_gauche: tuple[str, ...]
    colonnes_propres_droite: tuple[str, ...]
    # Longueur du plus court chemin de lignage, traitements compris. Mesuré :
    # dans ce catalogue, *toutes* les copies sont reliées (88 couples sur 88),
    # à distance 2 ou 4 — soit la même chose qu'un couple au hasard. À reporter,
    # pas à interpréter. None = aucun chemin ; non renseigné sans graphe.
    distance_lignage: int | None = None
    distance_connue: bool = False

    @property
    def sans_lien(self) -> bool:
        """Aucun chemin de lignage entre ces deux-là, traitements compris.

        Rare, et à ne surtout pas lire à l'envers : dans le catalogue mesuré,
        **aucun** couple de copies n'est dans ce cas — le graphe est d'un seul
        tenant. Un couple relié n'est donc pas un couple identique, et cette
        propriété ne sert qu'à signaler l'exception, pas à trier.
        """
        return self.distance_connue and self.distance_lignage is None

    def resume(self) -> str:
        """Une ligne, pour un journal ou une réponse d'outil."""
        if not self.distance_connue:
            lien = ""
        elif self.distance_lignage is None:
            lien = ", aucun chemin de lignage"
        else:
            lien = f", reliés à distance {self.distance_lignage}"
        return (f"{self.gauche.plateforme}/{self.gauche.nom} ≟ "
                f"{self.droite.plateforme}/{self.droite.nom} — "
                f"recouvrement {self.recouvrement:.0%}"
                f"{', même nom' if self.meme_nom else ''}{lien}")


def preselectionner(jeux: list[Jeu], seuil: float = 0.6,
                    graphe: dict[str, set[str]] | None = None) -> list[Candidat]:
    """Les couples dont la structure dit « peut-être ».

    Un couple est retenu si les colonnes se recouvrent assez, **ou** si les noms
    normalisés coïncident. Les deux critères ratent séparément : le nom rate les
    copies renommées, le recouvrement rate les jeux dont le schéma a divergé.
    Retenir large ici est peu coûteux — c'est le juge qui paye, et il ne voit
    qu'une poignée de couples.

    `graphe` est facultatif : sans lui la présélection fonctionne, mais elle ne
    peut pas dire si le lignage relie déjà le couple. On ne devine pas — le
    champ reste marqué « non connu ».
    """
    distance = distances_depuis(graphe) if graphe is not None else None
    retenus: list[Candidat] = []
    for a, b in itertools.combinations(jeux, 2):
        if a.urn == b.urn:
            continue
        r = recouvrement(a, b)
        meme_nom = normaliser(a.nom) == normaliser(b.nom)
        if r < seuil and not meme_nom:
            continue
        communes = sorted(a.noms_colonnes & b.noms_colonnes)
        retenus.append(Candidat(
            gauche=a,
            droite=b,
            recouvrement=r,
            meme_nom=meme_nom,
            colonnes_communes=tuple(communes),
            colonnes_propres_gauche=tuple(sorted(a.noms_colonnes - b.noms_colonnes)),
            colonnes_propres_droite=tuple(sorted(b.noms_colonnes - a.noms_colonnes)),
            distance_lignage=distance(a.urn, b.urn) if distance else None,
            distance_connue=distance is not None,
        ))

    # Les couples que le lignage ne relie pas d'abord, puis les plus
    # ressemblants : en tête, ce que le graphe ne pouvait pas trouver seul.
    retenus.sort(key=lambda c: (not c.sans_lien, -c.recouvrement))
    return retenus
