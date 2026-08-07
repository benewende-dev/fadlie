#!/usr/bin/env python3
"""Capture de vraies sorties de l'agent déployé, pour `examples/`.

Un juge qui n'installe pas de client MCP, et qui n'a pas le jeton sous la main,
doit quand même pouvoir juger la **qualité de ce que Fadlie produit**. Ces
fichiers sont là pour ça : ce ne sont pas des exemples écrits à la main, ce sont
les réponses réelles du service, telles quelles.

**Rien ici n'écrit dans le catalogue.** Les trois premiers outils lisent ;
`apply_governance` est appelé à blanc, et le script vérifie que la réponse le
confirme avant d'enregistrer. Un exemple qui aurait consommé un groupe de la
démonstration serait payé deux fois : une fois par le catalogue, une fois par le
juge qui ne verrait plus rien à voir.

    set -a && . ./.env && set +a
    FADLIE_MCP_URL=https://…/mcp python scripts/capturer-exemples.py
"""
from __future__ import annotations

import asyncio
import datetime
import json
import os
import pathlib
import sys

sys.path.insert(0, ".")

from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import (  # noqa: E402
    create_mcp_http_client, streamable_http_client,
)

RACINE = pathlib.Path(__file__).resolve().parent.parent
EXEMPLES = RACINE / "examples"

# Le jeu visé pour l'exemple d'écarts. `order_details` est le cas le plus parlant
# du catalogue : quatre jumeaux, dix-sept colonnes sensibles, et le seul
# désaccord de domaine que Fadlie refuse de trancher.
JEU = "order_details"


def extraire(resultat) -> dict:
    """Le contenu structuré d'un appel d'outil."""
    if resultat.structured_content is not None:
        return resultat.structured_content
    return json.loads(resultat.content[0].text)


def ecrire(nom: str, appel: str, donnees: dict) -> pathlib.Path:
    cible = EXEMPLES / nom
    cible.write_text(json.dumps(donnees, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    lignes = len(cible.read_text(encoding="utf-8").splitlines())
    print(f"  ✓ {nom:34} {appel:52} {lignes} lignes")
    return cible


async def capturer(url: str, jeton: str) -> None:
    import httpx2

    client = create_mcp_http_client(
        headers={"Authorization": "Bearer " + jeton},
        timeout=httpx2.Timeout(600.0, connect=20.0),
    )
    EXEMPLES.mkdir(exist_ok=True)

    async with streamable_http_client(url, http_client=client) as flux:
        async with ClientSession(flux[0], flux[1]) as session:
            await session.initialize()

            resume = extraire(await session.call_tool("catalog_summary", {}))
            ecrire("catalog_summary.json", "catalog_summary()", resume)

            groupes = extraire(await session.call_tool("find_duplicate_datasets", {}))
            ecrire("find_duplicate_datasets.json",
                   "find_duplicate_datasets()", groupes)

            ecarts = extraire(await session.call_tool(
                "governance_gaps", {"dataset": JEU, "limit": 50}))
            ecrire("governance_gaps.json",
                   f'governance_gaps(dataset="{JEU}")', ecarts)

            blanc = extraire(await session.call_tool(
                "apply_governance", {"dataset": JEU}))
            # Le contrôle qui rend ce script sûr à relancer : si la réponse ne
            # dit pas que rien n'a été écrit, on n'enregistre pas et on le dit.
            if blanc.get("applied", -1) != 0 or blanc.get("dry_run") is not True:
                raise SystemExit(
                    "REFUS : apply_governance n'a pas répondu en écriture à "
                    f"blanc — {json.dumps(blanc, ensure_ascii=False)}")
            ecrire("apply_governance_dry_run.json",
                   f'apply_governance(dataset="{JEU}")', blanc)


def main() -> None:
    url = os.environ.get("FADLIE_MCP_URL", "").strip()
    jeton = os.environ.get("FADLIE_API_TOKEN", "").strip()
    if not url or not jeton:
        raise SystemExit("FADLIE_MCP_URL et FADLIE_API_TOKEN sont nécessaires.")

    print(f"capture contre {url}\n")
    asyncio.run(capturer(url, jeton))
    print(f"\n{datetime.date.today().isoformat()} — examples/ à jour")


if __name__ == "__main__":
    main()
