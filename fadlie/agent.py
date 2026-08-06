"""L'enchaînement : lire, présélectionner, juger, comparer.

Trois couches, et chacune existe parce qu'une mesure a montré que la précédente
ne suffit pas :

    catalogue   →  67 jeux, leur schéma, leur gouvernance, leur lignage
    candidats   →  la structure dit « peut-être » (2 211 couples → ~96)
    juge        →  un modèle tranche (le nom se trompe 3 fois sur 15)
    écart       →  ce qu'un jumeau a et que l'autre n'a pas

Un détail qui n'en est pas un : les couples confirmés sont **réunis en groupes**.
`customers` existe sur quatre plateformes, ce qui fait six couples ; les traiter
séparément produirait six rapports au lieu d'un, et propagerait deux fois la
même valeur. On fait donc l'union des couples confirmés avant de comparer.
"""
from __future__ import annotations

import collections
import dataclasses
import logging

from .candidats import Candidat, preselectionner
from .catalogue import Catalogue, Jeu
from .config import Config
from .ecart import Desaccord, Ecart, comparer
from .juge import Juge, Verdict

journal = logging.getLogger("fadlie")


@dataclasses.dataclass(frozen=True)
class Groupe:
    """Des jeux que le juge a reconnus comme portant la même donnée."""

    jeux: tuple[Jeu, ...]
    verdicts: tuple[tuple[str, str, Verdict], ...]  # (urn, urn, verdict)

    @property
    def nom(self) -> str:
        """Tous les noms distincts du groupe, pas un choisi parmi eux.

        Une première version prenait `jeux[0].nom`, c'est-à-dire le premier par
        urn : le groupe « Promotions ≟ Custom SQL Query » s'affichait
        « Custom SQL Query », et le rapport donnait l'impression d'avoir confondu
        des requêtes sans rapport. Le résultat était juste, l'étiquette mentait.

        La correction suivante départageait par une règle qui nommait
        « Custom SQL Query » dans le code — une donnée de ce catalogue-ci glissée
        dans la bibliothèque. Il n'y a pas de bon départage : un groupe qui porte
        deux noms **porte deux noms**, et c'est précisément ce qu'un lecteur doit
        voir.
        """
        vus: list[str] = []
        for j in self.jeux:
            if j.nom not in vus:
                vus.append(j.nom)
        return " / ".join(vus)

    @property
    def plateformes(self) -> tuple[str, ...]:
        return tuple(j.plateforme for j in self.jeux)


@dataclasses.dataclass(frozen=True)
class Rapport:
    groupes: tuple[Groupe, ...]
    ecarts: tuple[Ecart, ...]
    desaccords: tuple[Desaccord, ...]
    couples_examines: int
    couples_confirmes: int

    @property
    def jeux_a_completer(self) -> int:
        return len({e.cible for e in self.ecarts})


class _Union:
    """Union-find, juste assez pour réunir les couples confirmés."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def trouver(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def unir(self, a: str, b: str) -> None:
        ra, rb = self.trouver(a), self.trouver(b)
        if ra != rb:
            self.parent[rb] = ra


class Agent:
    def __init__(self, config: Config, catalogue: Catalogue | None = None,
                 juge: Juge | None = None) -> None:
        self.config = config
        self.catalogue = catalogue or Catalogue(config)
        self.juge = juge or Juge(config)

    def analyser(self, avec_lignage: bool = False) -> Rapport:
        """Le rapport complet. `avec_lignage` construit le graphe, lent et
        facultatif : mesuré, la distance de lignage ne dit rien sur « est-ce la
        même donnée ». On ne la calcule que si quelqu'un veut la lire.
        """
        # La sonde d'abord, toujours. Sans elle, un juge muet rendrait un rapport
        # vide — c'est-à-dire un catalogue en règle — et personne ne vérifie une
        # bonne nouvelle.
        self.juge.sonder()

        jeux = self.catalogue.jeux()
        par_urn = {j.urn: j for j in jeux}
        graphe = self.catalogue.graphe_lignage(jeux) if avec_lignage else None
        candidats = preselectionner(jeux, self.config.recouvrement_minimum, graphe)
        journal.info("%d jeux, %d couples présélectionnés", len(jeux), len(candidats))

        union = _Union()
        confirmes: list[tuple[Candidat, Verdict]] = []
        for candidat in candidats:
            verdict = self.juge.meme_donnee(candidat)
            if verdict.identiques:
                union.unir(candidat.gauche.urn, candidat.droite.urn)
                confirmes.append((candidat, verdict))

        # Regrouper, puis comparer une seule fois par groupe.
        membres: dict[str, list[str]] = {}
        for urn in {u for c, _ in confirmes for u in (c.gauche.urn, c.droite.urn)}:
            membres.setdefault(union.trouver(urn), []).append(urn)

        groupes: list[Groupe] = []
        tous_ecarts: list[Ecart] = []
        tous_desaccords: list[Desaccord] = []
        for racine, urns in sorted(membres.items()):
            jeux_du_groupe = sorted((par_urn[u] for u in urns), key=lambda j: j.urn)
            verdicts = tuple(
                (c.gauche.urn, c.droite.urn, v) for c, v in confirmes
                if union.trouver(c.gauche.urn) == racine
            )
            groupes.append(Groupe(jeux=tuple(jeux_du_groupe), verdicts=verdicts))
            ecarts, desaccords = comparer(jeux_du_groupe)
            tous_ecarts += ecarts
            tous_desaccords += desaccords

        return Rapport(
            groupes=tuple(groupes),
            ecarts=tuple(tous_ecarts),
            desaccords=tuple(tous_desaccords),
            couples_examines=len(candidats),
            couples_confirmes=len(confirmes),
        )
