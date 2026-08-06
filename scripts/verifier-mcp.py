#!/usr/bin/env python3
"""Le serveur, éprouvé par un vrai client MCP.

Pas des `curl` : un client qui parle le protocole, comme celui d'un juge. Ce qui
est vérifié va au-delà de « ça répond » — ce sont les garanties qu'on affirme :

- le jeton est exigé, et un jeton faux est refusé ;
- **aucun outil ne prend d'identité en argument** (rien dans le langage ne
  l'empêche, donc un contrôle le tient) ;
- une écriture à blanc n'écrit rien — vérifié en relisant le catalogue, pas en
  croyant la réponse de l'outil ;
- une panne ne raconte pas l'infrastructure au client.

    set -a && . ./.env && set +a
    python scripts/verifier-mcp.py                     # local, lève son serveur
    FADLIE_MCP_URL=https://…/mcp python scripts/verifier-mcp.py --distant
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, ".")

from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import (  # noqa: E402
    create_mcp_http_client, streamable_http_client,
)

VERTS = 0
ROUGES: list[str] = []


def controle(nom: str, condition: bool, detail: str = "") -> None:
    global VERTS
    if condition:
        VERTS += 1
        print(f"  ✓ {nom}")
    else:
        ROUGES.append(f"{nom} — {detail}" if detail else nom)
        print(f"  ✗ {nom}{(' — ' + detail) if detail else ''}")


def http(url: str, jeton: str | None = None, corps: bytes | None = None) -> int:
    entetes = {"Accept": "application/json, text/event-stream",
               "Content-Type": "application/json"}
    if jeton:
        entetes["Authorization"] = "Bearer " + jeton
    req = urllib.request.Request(url, data=corps, headers=entetes,
                                 method="POST" if corps is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return 0


async def eprouver(url: str, jeton: str) -> None:
    import httpx2

    # Le jeton voyage dans le client HTTP, pas dans un paramètre du transport :
    # c'est la même chose qu'un client de juge ferait. Le délai est large parce
    # que la première analyse invoque le juge une centaine de fois.
    client = create_mcp_http_client(
        headers={"Authorization": "Bearer " + jeton},
        timeout=httpx2.Timeout(600.0, connect=20.0),
    )
    async with streamable_http_client(url, http_client=client) as flux:
        lire, ecrire = flux[0], flux[1]
        async with ClientSession(lire, ecrire) as session:
            await session.initialize()
            controle("le client MCP s'initialise", True)

            outils = (await session.list_tools()).tools
            noms = sorted(o.name for o in outils)
            controle("les quatre outils sont là", noms == [
                "apply_governance", "catalog_summary", "find_duplicate_datasets",
                "governance_gaps"], str(noms))

            # L'invariant d'identité. Rien dans le langage n'empêche d'ajouter un
            # paramètre `user` ou `token` à un outil ; ce contrôle, si.
            interdits = {"user", "user_id", "token", "api_key", "actor",
                         "identity", "auth", "authorization", "tenant"}
            fautifs = [
                f"{o.name}.{p}"
                for o in outils
                for p in (o.input_schema or {}).get("properties", {})
                if p.lower() in interdits
            ]
            controle("aucun outil ne prend une identité en argument",
                     not fautifs, ", ".join(fautifs))

            def contenu(resultat):
                return json.loads(resultat.content[0].text)

            print("\n  (la première analyse invoque le juge ~100 fois, patience)")
            debut = time.time()
            resume = contenu(await session.call_tool("catalog_summary", {}))
            print(f"  analyse en {time.time() - debut:.0f} s")

            controle("catalog_summary rend des couples examinés",
                     resume.get("pairs_examined", 0) > 0, str(resume))
            controle("des couples sont confirmés",
                     resume.get("pairs_confirmed_same_data", 0) > 0)
            controle("des groupes de jumeaux sont trouvés",
                     resume.get("duplicate_groups", 0) >= 10, str(resume.get("duplicate_groups")))
            controle("des écarts de gouvernance sont trouvés",
                     resume.get("governance_gaps", 0) > 100, str(resume.get("governance_gaps")))
            controle("les confirmés ne dépassent pas les examinés",
                     resume["pairs_confirmed_same_data"] <= resume["pairs_examined"])

            groupes = contenu(await session.call_tool("find_duplicate_datasets", {}))["groups"]
            controle("chaque groupe a au moins deux jeux",
                     all(len(g["datasets"]) >= 2 for g in groupes))
            controle("chaque groupe porte les verdicts du juge",
                     all(g["verdicts"] for g in groupes))
            controle("chaque verdict porte une raison",
                     all(v["reason"] for g in groupes for v in g["verdicts"]))
            multi = [g for g in groupes if len(set(g["platforms"])) >= 3]
            controle("au moins un groupe traverse trois plateformes",
                     bool(multi), f"{len(multi)} groupes")

            ecarts = contenu(await session.call_tool("governance_gaps", {"limit": 200}))
            controle("governance_gaps rend des écarts", ecarts["total"] > 0)
            # La règle qui distingue Fadlie d'un générateur de texte.
            controle("chaque écart nomme le jeu d'où vient la valeur",
                     all(e["copied_from"] and e["copied_from_urn"] for e in ecarts["gaps"]),
                     "un écart sans provenance")
            controle("aucun écart ne se copie sur lui-même",
                     all(e["copied_from_urn"] != e["dataset_urn"] for e in ecarts["gaps"]))
            controle("le filtre par jeu réduit bien",
                     contenu(await session.call_tool(
                         "governance_gaps", {"dataset": "customers"}))["total"] < ecarts["total"])

            # L'écriture à blanc. On ne croit pas la réponse de l'outil : on
            # relit le catalogue et on compare.
            avant = contenu(await session.call_tool("catalog_summary", {}))["governance_gaps"]
            blanc = contenu(await session.call_tool("apply_governance", {}))
            controle("apply_governance est à blanc par défaut", blanc["dry_run"] is True)
            controle("à blanc, rien n'est appliqué", blanc["applied"] == 0)
            controle("à blanc, le compte annoncé est non nul", blanc["would_apply"] > 0)
            apres = contenu(await session.call_tool("catalog_summary", {}))["governance_gaps"]
            controle("le catalogue n'a pas bougé après une écriture à blanc",
                     avant == apres, f"{avant} → {apres}")

            # Une panne ne doit pas raconter l'infrastructure.
            try:
                mauvais = await session.call_tool("governance_gaps", {"limit": "beaucoup"})
                texte = str(mauvais.content[0].text if mauvais.content else mauvais)
            except Exception as e:  # noqa: BLE001
                texte = str(e)
            fuites = [m for m in ("63.186.160.88", "8080", "Bearer", "amazonaws",
                                  "Traceback", "urllib") if m in texte]
            controle("une erreur ne montre ni hôte, ni port, ni jeton",
                     not fuites, f"fuite : {fuites} dans {texte[:120]}")


def main() -> int:
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument("--distant", action="store_true",
                           help="éprouve FADLIE_MCP_URL au lieu d'un serveur local")
    args = analyseur.parse_args()

    jeton = os.environ.get("FADLIE_API_TOKEN", "").strip()
    if not jeton:
        print("FADLIE_API_TOKEN est requise", file=sys.stderr)
        return 2

    serveur = None
    if args.distant:
        url = os.environ.get("FADLIE_MCP_URL", "").strip()
        if not url:
            print("FADLIE_MCP_URL est requise avec --distant", file=sys.stderr)
            return 2
        racine = url.rsplit("/mcp", 1)[0]
    else:
        port = 8766
        url, racine = f"http://127.0.0.1:{port}/mcp", f"http://127.0.0.1:{port}"
        serveur = subprocess.Popen(
            [sys.executable, "-m", "fadlie", "serve", "--port", str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(30):
            time.sleep(1)
            if http(racine + "/health") == 200:
                break

    print(f"éprouve {url}\n")
    try:
        controle("/health répond sans jeton", http(racine + "/health") == 200)
        controle("/mcp refuse sans jeton", http(url, corps=b"{}") == 401)
        controle("/mcp refuse un jeton faux", http(url, "faux-jeton", b"{}") == 401)
        asyncio.run(eprouver(url, jeton))
    finally:
        if serveur:
            serveur.terminate()
            serveur.wait(timeout=10)

    print(f"\n{VERTS} contrôles verts, {len(ROUGES)} rouges")
    for r in ROUGES:
        print(f"  ✗ {r}")
    return 0 if not ROUGES else 1


if __name__ == "__main__":
    raise SystemExit(main())
