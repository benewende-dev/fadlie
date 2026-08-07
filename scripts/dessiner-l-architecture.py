#!/usr/bin/env python3
"""Dessine `docs/images/architecture.svg`.

Il manquait au dépôt la seule image qu'un juge cherche avant de lire : *par où
passe une requête, et qui décide quoi*. Le README l'explique en trois sections ;
un schéma le dit en un regard.

Ne se connecte à rien. Les effectifs — jeux lus, couples possibles, couples
examinés, groupes, écarts — sont **comptés depuis `examples/*.json`**, pas
écrits dans le gabarit. Un schéma qui porte ses nombres en dur devient faux sans
prévenir, et un schéma faux est pire qu'un schéma absent : il se lit vite et on
le croit.

    python scripts/dessiner-l-architecture.py
"""
from __future__ import annotations

import html
import json
import pathlib

RACINE = pathlib.Path(__file__).resolve().parent.parent
EXEMPLES = RACINE / "examples"
CIBLE = RACINE / "docs" / "images" / "architecture.svg"

L, H = 1000, 566
BLEU = "#3f6ea8"      # ce qui vient du dehors
VERT = "#2e9e6b"      # ce qui lit
AMBRE = "#c68a2e"     # ce qui décide
ROUGE = "#b3564e"     # ce qui écrit


def e(x: object) -> str:
    return html.escape(str(x))


def boite(x: float, y: float, w: float, h: float, titre: str,
          lignes: list[str], couleur: str, sourdine: bool = False) -> str:
    """Une boîte, son titre, et ses lignes de détail."""
    morceaux = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" '
        f'class="{"boite douce" if sourdine else "boite"}" '
        f'stroke="{couleur}"/>',
        f'<text class="bt" x="{x + 14}" y="{y + 24}" fill="{couleur}">'
        f'{titre}</text>',
    ]
    for i, ligne in enumerate(lignes):
        morceaux.append(
            f'<text class="bl" x="{x + 14}" y="{y + 44 + i * 17}">{ligne}</text>')
    return "".join(morceaux)


def fleche(x1: float, y1: float, x2: float, y2: float, couleur: str,
           pointe: str) -> str:
    """Une flèche nue.

    Les étiquettes le long des flèches ont été retirées : entre le cadre du
    service et les boîtes du dehors il ne reste que quarante pixels, et un mot
    posé là chevauchait la boîte qu'il désignait. Les boîtes disent déjà ce que
    l'étiquette répétait.
    """
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{couleur}" '
            f'stroke-width="1.6" marker-end="url(#{pointe})"/>')


def construire() -> str:
    resume = json.loads((EXEMPLES / "catalog_summary.json").read_text("utf-8"))
    lignage = json.loads((EXEMPLES / "lineage_graph.json").read_text("utf-8"))
    tous = json.loads((EXEMPLES / "governance_gaps_all.json").read_text("utf-8"))

    n = lignage["datasets"]
    possibles = n * (n - 1) // 2
    examines = resume["pairs_examined"]
    confirmes = resume["pairs_confirmed_same_data"]
    groupes = resume["duplicate_groups"]
    ecarts = tous["total"]

    corps = []

    # --- l'appelant ---------------------------------------------------------
    corps.append(boite(
        20, 150, 178, 96, "MCP client",
        ["Claude, or any MCP host.", "Holds a bearer token.",
         "Never sends a user id."], BLEU))

    # --- le service ---------------------------------------------------------
    corps.append(
        '<rect x="240" y="96" width="440" height="424" rx="12" class="cadre"/>'
        '<text class="cadre-t" x="256" y="120">AWS App Runner &#183; '
        'eu-central-1 &#183; image from Amazon ECR</text>')

    corps.append(boite(
        258, 134, 404, 54, "Authorization: Bearer &#8212; middleware",
        ["Checked before any tool runs. No tool takes an identity."],
        BLEU, sourdine=True))

    corps.append(boite(
        258, 200, 404, 76, "Four MCP tools",
        ["catalog_summary &#183; find_duplicate_datasets",
         "governance_gaps &#183; apply_governance"], BLEU, sourdine=True))

    corps.append(boite(
        258, 288, 404, 46, "Cached report, refreshed in the background",
        ["App Runner cuts at 120 s; a full analysis takes about 240."],
        BLEU, sourdine=True))

    corps.append(boite(
        258, 346, 404, 158, "The agent &#8212; four layers",
        [f"catalogue &#8212; reads {n} datasets, schemas, lineage",
         f"candidats &#8212; {possibles:,} pairs &#8594; {examines}".replace(",", "&#8239;"),
         f"juge &#8212; a model decides: {confirmes} confirmed, "
         f"{groupes} groups",
         f"ecart &#8594; reparer &#8212; {ecarts} gaps, each naming a source"],
        AMBRE, sourdine=True))

    # --- le dehors ----------------------------------------------------------
    corps.append(boite(
        726, 150, 254, 100, "DataHub Core v1.7.0",
        ["on Amazon EC2, contest datapack",
         "GraphQL + OpenAPI v3",
         "read &#8212; and written back"], VERT))

    corps.append(boite(
        726, 300, 254, 84, "Amazon Bedrock",
        ["Amazon Nova Micro, temperature 0",
         "the only layer that decides"], AMBRE))

    corps.append(boite(
        726, 424, 254, 72, "AWS Secrets Manager",
        ["the DataHub token, never in the",
         "image and never in the repo"], BLEU, sourdine=True))

    # --- les flèches --------------------------------------------------------
    corps.append(fleche(200, 190, 236, 190, BLEU, "pointe-bleue"))
    corps.append(fleche(664, 372, 722, 214, VERT, "pointe-verte"))
    corps.append(fleche(664, 402, 722, 340, AMBRE, "pointe-ambre"))
    corps.append('<text class="et" x="218" y="182" text-anchor="middle">'
                 'HTTPS</text>')

    # --- les trois règles ---------------------------------------------------
    # Trois colonnes de 327 px : le texte de la deuxième mordait sur la
    # troisième. Raccourci plutôt que rétréci — une règle illisible ne règle
    # rien.
    regles = [
        ("Identity comes from the transport.",
         "No tool takes a user or a token."),
        ("It copies; it never writes.",
         "Every value names where it came from."),
        ("Writing takes a second argument.",
         "A dry run by default, in the code."),
    ]
    for i, (fort, doux) in enumerate(regles):
        x = 20 + i * 327
        corps.append(
            f'<text class="regle" x="{x}" y="{H - 34}">{fort}</text>'
            f'<text class="regle douce" x="{x}" y="{H - 16}">{doux}</text>')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {L} {H}"
     width="{L}" height="{H}" role="img"
     aria-label="Fadlie's architecture: an MCP client calls a server on AWS App
     Runner, which reads DataHub Core on EC2, asks Amazon Nova Micro on Bedrock
     to decide which datasets hold the same data, and writes the missing
     governance back.">
<defs>
  <marker id="pointe-bleue" viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="{BLEU}"/></marker>
  <marker id="pointe-verte" viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="{VERT}"/></marker>
  <marker id="pointe-ambre" viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="{AMBRE}"/></marker>
</defs>
<style>
  text{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,
       sans-serif;fill:#16181d}}
  .titre{{font-size:21px;font-weight:650;letter-spacing:-.3px}}
  .sous{{font-size:13.5px;fill:#5b6270}}
  .boite{{fill:#fff;stroke-width:1.6}}
  .boite.douce{{fill:#f7f8fa;stroke-width:1;stroke-opacity:.55}}
  .cadre{{fill:none;stroke:#c8ced7;stroke-width:1.4;stroke-dasharray:5 4}}
  .cadre-t{{font-size:12px;fill:#5b6270;letter-spacing:.02em}}
  .bt{{font-size:13.5px;font-weight:640}}
  .bl{{font-size:12px;fill:#5b6270}}
  .et{{font-size:11px;fill:#8a93a1}}
  .regle{{font-size:12.5px;font-weight:640}}
  .regle.douce{{font-weight:400;fill:#5b6270}}
  @media (prefers-color-scheme:dark){{
    text{{fill:#e6e9ef}} .sous,.bl,.cadre-t,.et,.regle.douce{{fill:#98a1b0}}
    .boite{{fill:#0e1116}} .boite.douce{{fill:#161b22}}
    .cadre{{stroke:#3a424e}}
  }}
</style>
<text class="titre" x="20" y="40">Structure proposes. A model decides. Nothing
is invented.</text>
<text class="sous" x="20" y="62">Every value Fadlie writes into DataHub was read
from a dataset it names &#8212; and it will not write at all unless asked
twice.</text>
{"".join(corps)}
</svg>
"""


def main() -> None:
    CIBLE.parent.mkdir(parents=True, exist_ok=True)
    svg = construire()
    CIBLE.write_text(svg, encoding="utf-8")
    print(f"{CIBLE.relative_to(RACINE)} — {len(svg.encode()) / 1024:.1f} Ko")


if __name__ == "__main__":
    main()
