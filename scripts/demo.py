#!/usr/bin/env python3
"""La démonstration, contre le serveur déployé — rien n'est joué d'avance.

Chaque ligne affichée vient d'un appel MCP réel. Le script est écrit pour être
filmé : il avance à un rythme lisible, montre la question avant la réponse, et
ne triche sur aucun chiffre. Si le serveur répond autre chose, la démonstration
le montre.

    FADLIE_MCP_URL=https://…/mcp FADLIE_API_TOKEN=… python scripts/demo.py
    …  --vite            sans les pauses
    …  --repetition      ne grave rien : la scène d'écriture reste à blanc
    …  --jeu order_items  un autre groupe de jumeaux que `customers`

`--repetition` existe parce que la démonstration est destructrice par nature :
une fois `apply_governance` passé pour de vrai, les écarts du groupe visé
n'existent plus et la scène suivante n'a plus rien à montrer. On répète à blanc,
on tourne une seule fois — et `--jeu` permet de refaire une prise ailleurs
plutôt que d'attendre que le catalogue se re-dégrade, ce qu'il ne fera pas.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, ".")

from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import (  # noqa: E402
    create_mcp_http_client, streamable_http_client,
)

GRIS, BLANC, VERT, JAUNE, ROUGE, FIN = (
    "\033[90m", "\033[97m", "\033[92m", "\033[93m", "\033[91m", "\033[0m")

PAUSE = 1.0


def souffler(facteur: float = 1.0) -> None:
    time.sleep(PAUSE * facteur)


def titre(texte: str) -> None:
    print(f"\n{BLANC}── {texte} {'─' * max(0, 66 - len(texte))}{FIN}")
    souffler(0.6)


def dire(texte: str, couleur: str = "") -> None:
    print(f"{couleur}{texte}{FIN}")


_LETTRES = {2: "two", 3: "three", 4: "four", 5: "five",
            6: "six", 7: "seven", 8: "eight"}


def _en_lettres(n: int) -> str:
    """« four » plutôt que « 4 » : c'est un titre, pas une mesure."""
    return _LETTRES.get(n, str(n))


def appel(nom: str, arguments: dict | None = None) -> None:
    args = json.dumps(arguments) if arguments else ""
    dire(f"{GRIS}▸ {nom}({args}){FIN}")
    souffler(0.5)


async def jouer(url: str, jeton: str, repetition: bool = False,
                jeu: str = "customers") -> int:
    import httpx2

    client = create_mcp_http_client(
        headers={"Authorization": "Bearer " + jeton},
        timeout=httpx2.Timeout(600.0, connect=20.0),
    )
    async with streamable_http_client(url, http_client=client) as flux:
        async with ClientSession(flux[0], flux[1]) as session:
            await session.initialize()

            def contenu(r):
                return json.loads(r.content[0].text)

            # --- 1. l'état du catalogue --------------------------------------
            titre("What the catalog looks like")
            appel("catalog_summary")
            resume = contenu(await session.call_tool("catalog_summary", {}))
            dire(f"  {resume['pairs_examined']} pairs examined, "
                 f"{resume['pairs_confirmed_same_data']} hold the same data")
            dire(f"  {resume['duplicate_groups']} groups of copies across platforms")
            dire(f"  {ROUGE}{resume['governance_gaps']} governance gaps "
                 f"on {resume['datasets_with_gaps']} datasets{FIN}")
            dire(f"  {resume['disagreements']} disagreement the agent refused to settle")
            souffler(2.5)

            # --- 2. les copies -----------------------------------------------
            appel("find_duplicate_datasets")
            groupes = contenu(await session.call_tool("find_duplicate_datasets", {}))["groups"]
            clients = next((g for g in groupes
                            if any(jeu in d.lower() for d in g["datasets"])), groupes[0])
            # Le titre se lit après le résultat, pas avant : c'est le serveur qui
            # dit combien de systèmes portent la table, pas le script.
            titre(f"The same table, {_en_lettres(len(clients['datasets']))} systems")
            for d in clients["datasets"]:
                dire(f"  {d}")
            souffler(1.2)
            verdict = clients["verdicts"][0]
            dire(f"\n{GRIS}  the judge, on {verdict['a']} vs {verdict['b']}:{FIN}")
            dire(f'  "{verdict["reason"]}" ({verdict["confidence"]} confidence)')
            dire(f"{GRIS}  no lineage edge says these are the same table.{FIN}")
            souffler(2.5)

            # --- 3. la gouvernance qui s'arrête -------------------------------
            titre("Where the governance stopped")
            appel("governance_gaps", {"dataset": jeu})
            ecarts = contenu(await session.call_tool(
                "governance_gaps", {"dataset": jeu, "limit": 200}))
            dire(f"  {ecarts['total']} gaps on the {jeu} copies alone\n")
            # Un écart par genre, et par colonne distincte : cinq fois « missing
            # owner » ne montre pas ce que fait l'agent, ça montre qu'il boucle.
            vus, varies = set(), []
            for e in ecarts["gaps"]:
                cle = (e["kind"], e["column"])
                if cle in vus:
                    continue
                vus.add(cle)
                varies.append(e)
                if len(varies) == 5:
                    break
            for e in varies:
                colonne = f".{e['column']}" if e["column"] else ""
                dire(f"  {e['dataset']}{colonne}")
                dire(f"    {JAUNE}missing {e['kind']}{FIN}  "
                     f"{GRIS}copied from {e['copied_from']}{FIN}")
            souffler(1.0)
            dire(f"\n{GRIS}  every value names the dataset it comes from."
                 f" nothing here was written by a model.{FIN}")
            souffler(2.5)

            # --- 4. la réparation, à blanc puis pour de vrai ------------------
            titre("Fixing it")
            appel("apply_governance", {"dataset": jeu})
            blanc = contenu(await session.call_tool(
                "apply_governance", {"dataset": jeu}))
            dire(f"  dry run: {blanc['would_apply']} values would be written, "
                 f"{blanc['applied']} written")
            dire(f"{GRIS}  dry run is the default. writing takes a second argument.{FIN}")
            souffler(2.0)

            if repetition:
                dire(f"{GRIS}  [répétition : l'écriture réelle est sautée]{FIN}")
                souffler(1.0)
                vrai = None
            else:
                appel("apply_governance", {"dataset": jeu, "dry_run": False})
                debut = time.time()
                vrai = contenu(await session.call_tool(
                    "apply_governance", {"dataset": jeu, "dry_run": False}))
                dire(f"  {VERT}{vrai['applied']} values written to DataHub{FIN}"
                     f"  {GRIS}({time.time() - debut:.0f}s){FIN}")
                if vrai["failed"]:
                    dire(f"  {ROUGE}{vrai['failed']} failed{FIN} — "
                         f"{vrai['failures'][0]['reason'][:70]}")
                souffler(1.5)

            appel("governance_gaps", {"dataset": jeu})
            reste = contenu(await session.call_tool(
                "governance_gaps", {"dataset": jeu, "limit": 1}))
            # La légende suit le résultat du serveur, elle ne le précède pas.
            # Piège vécu au tournage de Naaba : un commentaire écrit d'avance
            # démentait la ligne juste au-dessus, et il a fallu refaire la prise.
            if reste["total"] < ecarts["total"]:
                dire(f"  gaps on {jeu} now: {VERT}{reste['total']}{FIN}"
                     f"  {GRIS}(was {ecarts['total']}){FIN}")
            else:
                dire(f"  gaps on {jeu}: {reste['total']}"
                     f"  {GRIS}(unchanged — nothing was written){FIN}")
            souffler(2.0)

            titre("What it will not do")
            for d in reste["disagreements"][:2]:
                dire(f"  {JAUNE}{d['kind']}{FIN} — " + " / ".join(
                    f"{v['dataset']}: {v['value']}" for v in d["values"]))
            dire(f"{GRIS}  someone decided, or someone erred."
                 f" that is not an agent's call.{FIN}")
            souffler(2.0)
    return 0


def main() -> int:
    global PAUSE
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument("--vite", action="store_true", help="sans les pauses")
    analyseur.add_argument("--repetition", action="store_true",
                           help="ne grave rien : la scène d'écriture reste à blanc")
    # La scène d'écriture est destructrice : une fois un groupe réparé, il n'a
    # plus rien à montrer. Pouvoir en viser un autre, c'est pouvoir refaire une
    # prise sans attendre que le catalogue se re-dégrade — ce qu'il ne fera pas.
    analyseur.add_argument("--jeu", default="customers",
                           help="le groupe de jumeaux à montrer (défaut : customers)")
    args = analyseur.parse_args()
    if args.vite:
        PAUSE = 0.0

    url = os.environ.get("FADLIE_MCP_URL", "").strip()
    jeton = os.environ.get("FADLIE_API_TOKEN", "").strip()
    if not url or not jeton:
        print("FADLIE_MCP_URL et FADLIE_API_TOKEN sont requises", file=sys.stderr)
        return 2
    return asyncio.run(jouer(url, jeton, repetition=args.repetition, jeu=args.jeu))


if __name__ == "__main__":
    raise SystemExit(main())
