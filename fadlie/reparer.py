"""Appliquer les écarts, ou faire semblant.

Trois règles, chacune payée par une panne vécue ailleurs.

**À blanc par défaut.** `pour_de_vrai=False` est le défaut du code, pas seulement
celui de l'interface : un appel qui oublie le paramètre ne doit rien écrire.

**On ne recopie que ce qu'on a lu.** Un `Ecart` porte toujours la source ; il n'y
a donc rien à inventer ici, seulement à transporter.

**Un échec partiel se dit.** Écrire 580 valeurs, c'est 580 occasions d'échouer.
Rendre « appliqué » parce que la boucle est allée au bout serait le genre de
mensonge qu'on ne découvre qu'en ouvrant le catalogue. Chaque échec est retenu
avec sa cible, et le compte final distingue posé, échoué, simulé.
"""
from __future__ import annotations

import dataclasses
import logging

from .catalogue import Catalogue, CatalogueError
from .ecart import Ecart

journal = logging.getLogger("fadlie")


@dataclasses.dataclass(frozen=True)
class Resultat:
    poses: int
    simules: int
    echecs: tuple[tuple[Ecart, str], ...]

    @property
    def total(self) -> int:
        return self.poses + self.simules + len(self.echecs)

    def resume(self) -> str:
        """Pour la sortie de travail — `python -m fadlie report`."""
        if self.simules:
            return f"{self.simules} écarts simulés, rien n'a été écrit"
        if self.echecs:
            return (f"{self.poses} écarts posés, {len(self.echecs)} en échec "
                    f"— le catalogue est partiellement à jour")
        return f"{self.poses} écarts posés"

    def summary(self) -> str:
        """Pour les réponses d'outil MCP, qui sont une surface publique.

        Même règle que les désaccords : une réponse d'outil se lit par
        n'importe qui, donc elle est en anglais. `resume()` reste français, il
        ne sort que dans la ligne de commande de travail.
        """
        if self.simules:
            return f"{self.simules} gaps simulated, nothing was written"
        if self.echecs:
            return (f"{self.poses} gaps written, {len(self.echecs)} failed "
                    f"— the catalog is partially updated")
        return f"{self.poses} gaps written"


def _appliquer_un(catalogue: Catalogue, e: Ecart) -> None:
    if e.genre == "owner":
        catalogue.poser_proprietaires(e.cible, [e.valeur])
    elif e.genre == "description":
        catalogue.poser_description(e.cible, e.valeur)
    elif e.genre == "column_description":
        catalogue.poser_description(e.cible, e.valeur, colonne=e.colonne)
    elif e.genre == "column_tag":
        catalogue.poser_etiquettes(e.cible, [e.valeur], colonne=e.colonne)
    elif e.genre == "column_term":
        catalogue.poser_termes(e.cible, [e.valeur], colonne=e.colonne)
    elif e.genre == "domain":
        catalogue.poser_domaine(e.cible, e.valeur)
    else:  # pragma: no cover — `Ecart` refuse déjà les genres inconnus
        raise CatalogueError(f"genre non applicable : {e.genre}")


def appliquer(catalogue: Catalogue, ecarts: list[Ecart],
              pour_de_vrai: bool = False) -> Resultat:
    """Pose les écarts dans DataHub, ou compte ce qui serait posé."""
    if not pour_de_vrai:
        journal.info("à blanc : %d écarts simulés", len(ecarts))
        return Resultat(poses=0, simules=len(ecarts), echecs=())

    poses = 0
    echecs: list[tuple[Ecart, str]] = []
    for e in ecarts:
        try:
            _appliquer_un(catalogue, e)
            poses += 1
        except CatalogueError as erreur:
            # On continue : un domaine impossible à poser ne doit pas empêcher
            # les 579 autres écarts d'être réparés.
            journal.warning("écart refusé sur %s : %s", e.cible, erreur)
            echecs.append((e, str(erreur)))
    return Resultat(poses=poses, simules=0, echecs=tuple(echecs))
