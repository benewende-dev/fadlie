#!/usr/bin/env python3
"""Dessine `docs/images/lignage.svg` depuis `examples/lineage_graph.json`.

La découverte qui fonde Fadlie tenait dans une phrase : *le lignage ne
distingue pas un jumeau d'un inconnu*. Une phrase se lit et s'oublie ; deux
distributions qui se chevauchent se voient. C'est la même mesure, montrée.

Ne se connecte à rien : tout vient du JSON capturé. Aucun chiffre n'est écrit
dans ce fichier — les pourcentages, les totaux et la phrase du bas sont
calculés. Une figure qui porterait ses nombres en dur finirait par illustrer
une mesure qu'elle ne décrit plus.

    python scripts/dessiner-le-lignage.py

Le SVG est volontairement sans fond : posé sur GitHub en thème sombre comme en
thème clair, il doit rester lisible. Les couleurs sont choisies pour ça, et le
texte prend la couleur courante là où c'est possible.
"""
from __future__ import annotations

import json
import pathlib

RACINE = pathlib.Path(__file__).resolve().parent.parent
SOURCE = RACINE / "examples" / "lineage_graph.json"
CIBLE = RACINE / "docs" / "images" / "lignage.svg"

L, H = 920, 448
MARGE_G, MARGE_D = 58, 24
HAUT, BAS = 116, 136         # place pour le titre et pour la phrase du bas
VERT = "#2e9e6b"             # les homonymes
AMBRE = "#c68a2e"            # les couples au hasard


def cumul(distribution: dict[str, int], seuil: int) -> int:
    return sum(n for d, n in distribution.items() if int(d) <= seuil)


def construire() -> str:
    d = json.loads(SOURCE.read_text("utf-8"))
    h, r = d["same_name_pairs"], d["random_pairs"]
    hd, rd = h["distribution"], r["distribution"]

    portee = sorted({int(k) for k in list(hd) + list(rd)})
    dmin, dmax = portee[0], portee[-1]
    colonnes = list(range(dmin, dmax + 1))

    # Chaque série est ramenée à son propre total : 88 couples d'un côté, 316
    # de l'autre. Comparer des effectifs bruts ferait paraître les homonymes
    # rares alors que c'est l'échantillon qui est plus petit.
    part_h = {c: 100 * hd.get(str(c), 0) / h["pairs"] for c in colonnes}
    part_r = {c: 100 * rd.get(str(c), 0) / r["pairs"] for c in colonnes}
    plafond = max(list(part_h.values()) + list(part_r.values()))

    largeur = (L - MARGE_G - MARGE_D) / len(colonnes)
    barre = largeur * 0.34
    sol = H - BAS
    echelle = (sol - HAUT) / plafond

    def y(p: float) -> float:
        return sol - p * echelle

    morceaux: list[str] = []

    # Les repères horizontaux, sous les barres.
    pas = 10 if plafond > 25 else 5
    graduation = pas
    while graduation <= plafond:
        morceaux.append(
            f'<line class="grille" x1="{MARGE_G}" x2="{L - MARGE_D}" '
            f'y1="{y(graduation):.1f}" y2="{y(graduation):.1f}"/>'
            f'<text class="axe" x="{MARGE_G - 10}" y="{y(graduation) + 4:.1f}" '
            f'text-anchor="end">{graduation}%</text>')
        graduation += pas

    for i, c in enumerate(colonnes):
        x = MARGE_G + i * largeur + largeur / 2
        for part, couleur, decalage in ((part_h, VERT, -barre),
                                        (part_r, AMBRE, 0.0)):
            p = part[c]
            if p <= 0:
                continue
            morceaux.append(
                f'<rect x="{x + decalage + barre * 0.03:.1f}" y="{y(p):.1f}" '
                f'width="{barre * 0.94:.1f}" height="{p * echelle:.1f}" '
                f'rx="2" fill="{couleur}"/>')
        morceaux.append(
            f'<text class="axe" x="{x - barre / 2:.1f}" y="{sol + 20}" '
            f'text-anchor="middle">{c}</text>')

    morceaux.append(
        f'<line class="sol" x1="{MARGE_G}" x2="{L - MARGE_D}" '
        f'y1="{sol}" y2="{sol}"/>')

    # La phrase du bas est la mesure, pas un commentaire : le seuil le plus
    # généreux qui attrape presque tous les jumeaux attrape aussi la majorité
    # des inconnus. C'est ce qui rend la distance inutilisable comme verdict.
    seuil = max(colonnes)
    for c in colonnes:
        if cumul(hd, c) >= 0.95 * h["pairs"]:
            seuil = c
            break
    pris_h, pris_r = cumul(hd, seuil), cumul(rd, seuil)

    lignes_bas = [
        f'Set the threshold at {seuil}: it catches {pris_h} of the '
        f'{h["pairs"]} same-name pairs &#8212; and {pris_r} of the '
        f'{r["pairs"]} pairs picked at random '
        f'({100 * pris_r / r["pairs"]:.0f}%).',
        'There is no cut that keeps the twins and drops the strangers. '
        'Structure proposes; a model decides.',
    ]
    for i, ligne in enumerate(lignes_bas):
        morceaux.append(
            f'<text class="{"pied" if i else "pied fort"}" x="{MARGE_G}" '
            f'y="{H - 42 + i * 19}">{ligne}</text>')

    plein = d["full_graph"]
    sous_titre = (
        f'{plein["nodes"]} nodes, {plein["edges"]} edges, '
        f'{plein["components"]} component, {d["isolated_datasets"]} isolated '
        f'datasets &#8212; every pair of datasets is connected, both kinds.')

    legende = (
        f'<g transform="translate({L - MARGE_D - 300},{HAUT - 34})">'
        f'<rect width="11" height="11" rx="2" fill="{VERT}"/>'
        f'<text class="leg" x="17" y="10">same name '
        f'({h["pairs"]} pairs)</text>'
        f'<rect x="150" width="11" height="11" rx="2" fill="{AMBRE}"/>'
        f'<text class="leg" x="167" y="10">picked at random '
        f'({r["pairs"]})</text></g>')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {L} {H}"
     width="{L}" height="{H}" role="img"
     aria-label="Lineage distance between same-name dataset pairs and pairs
     picked at random. The two distributions overlap: no threshold separates
     them.">
<style>
  text{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,
       sans-serif;fill:#16181d}}
  .titre{{font-size:21px;font-weight:650;letter-spacing:-.3px}}
  .sous{{font-size:13.5px;fill:#5b6270}}
  .axe{{font-size:11.5px;fill:#5b6270}}
  .leg{{font-size:12.5px;fill:#5b6270}}
  .pied{{font-size:13px;fill:#5b6270}}
  .pied.fort{{fill:#16181d}}
  .grille{{stroke:#e3e6ea;stroke-width:1}}
  .sol{{stroke:#b9bfc8;stroke-width:1}}
  @media (prefers-color-scheme:dark){{
    text{{fill:#e6e9ef}} .sous,.axe,.leg,.pied{{fill:#98a1b0}}
    .pied.fort{{fill:#e6e9ef}}
    .grille{{stroke:#242a33}} .sol{{stroke:#3a424e}}
  }}
</style>
<text class="titre" x="{MARGE_G}" y="38">Lineage cannot tell a twin from a
stranger</text>
<text class="sous" x="{MARGE_G}" y="60">{sous_titre}</text>
<text class="axe" x="{MARGE_G}" y="{HAUT - 24}">share of pairs at each lineage
distance</text>
{legende}
{chr(10).join(morceaux)}
<text class="axe" x="{L - MARGE_D}" y="{H - BAS + 42}" text-anchor="end">shortest
path, in hops</text>
</svg>
"""


def main() -> None:
    CIBLE.parent.mkdir(parents=True, exist_ok=True)
    svg = construire()
    CIBLE.write_text(svg, encoding="utf-8")
    print(f"{CIBLE.relative_to(RACINE)} — {len(svg.encode()) / 1024:.1f} Ko")


if __name__ == "__main__":
    main()
