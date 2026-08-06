"""La ligne de commande : `python -m fadlie <commande>`.

    check     lit la configuration, ne se connecte à rien
    serve     lève le serveur MCP
    report    l'analyse complète, affichée
"""
from __future__ import annotations

import argparse
import collections
import logging
import sys

from .config import Config, ConfigError


def commande_check() -> int:
    try:
        config = Config.depuis_environnement()
    except ConfigError as e:
        print(f"configuration incomplète : {e}", file=sys.stderr)
        return 1
    for cle, valeur in config.resume().items():
        print(f"  {cle:<22} {valeur}")
    import os

    jeton = os.environ.get("FADLIE_API_TOKEN", "")
    print(f"  {'fadlie_api_token':<22} "
          f"{'…' + jeton[-4:] if jeton else '— absent, le serveur ne démarrera pas'}")
    return 0


def commande_report() -> int:
    from .agent import Agent
    from .ecart import GENRES

    config = Config.depuis_environnement()
    rapport = Agent(config).analyser()
    noms = {j.urn: f"{j.plateforme}/{j.nom}" for g in rapport.groupes for j in g.jeux}
    nom = lambda urn: noms.get(urn, urn)  # noqa: E731

    print(f"couples examinés {rapport.couples_examines}, "
          f"confirmés {rapport.couples_confirmes}")
    print(f"groupes de jumeaux : {len(rapport.groupes)}\n")
    for g in sorted(rapport.groupes, key=lambda x: x.nom):
        print(f"  {g.nom:<46} {', '.join(g.plateformes)}")
    print(f"\nécarts : {len(rapport.ecarts)} sur {rapport.jeux_a_completer} jeux")
    for genre, n in collections.Counter(e.genre for e in rapport.ecarts).most_common():
        print(f"  {GENRES[genre]:<24} {n}")
    if rapport.desaccords:
        print("\ndésaccords — Fadlie ne tranche pas :")
        for d in rapport.desaccords:
            print("  " + d.resume(nom))
    return 0


def commande_serve(port: int, hote: str) -> int:
    import uvicorn

    from .serveur import application

    uvicorn.run(application(), host=hote, port=port, log_level="info")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    analyseur = argparse.ArgumentParser(prog="fadlie")
    sous = analyseur.add_subparsers(dest="commande", required=True)
    sous.add_parser("check", help="lit la configuration, ne se connecte à rien")
    sous.add_parser("report", help="l'analyse complète, affichée")
    servir = sous.add_parser("serve", help="lève le serveur MCP")
    servir.add_argument("--port", type=int, default=8000)
    servir.add_argument("--host", default="127.0.0.1")

    args = analyseur.parse_args(argv)
    try:
        if args.commande == "check":
            return commande_check()
        if args.commande == "report":
            return commande_report()
        return commande_serve(args.port, args.host)
    except ConfigError as e:
        print(f"configuration : {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
