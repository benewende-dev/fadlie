#!/usr/bin/env python3
"""Le juge se trompe-t-il ? Sur des couples tirés du vrai catalogue.

Aucun couple inventé : chacun existe dans `showcase-ecommerce`, et sa réponse
attendue se justifie en une phrase, écrite à côté. Les couples faciles ne
prouvent rien — ceux-ci sont choisis pour être difficiles dans les deux sens :

- des copies que la structure ne suffit pas à reconnaître (casse différente,
  nombre de colonnes différent) ;
- des jeux qui se ressemblent beaucoup sans être la même donnée (tables de
  référence de même forme, homonymes sans colonnes communes, agrégats calculés
  à partir d'une table plutôt que copiés d'elle).

    set -a && . ./.env && set +a
    python scripts/mesurer-le-juge.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from fadlie.candidats import Candidat, recouvrement  # noqa: E402
from fadlie.catalogue import Catalogue  # noqa: E402
from fadlie.config import Config  # noqa: E402
from fadlie.juge import Juge, JugeError  # noqa: E402

# (plateforme, nom, plateforme, nom, même donnée ?, pourquoi)
EPREUVE = [
    # --- des copies -----------------------------------------------------------
    ("dbt", "customers", "postgres", "customers", True,
     "22 colonnes identiques, même entité, deux systèmes"),
    ("postgres", "addresses", "s3", "addresses", True,
     "export S3 de la table postgres — le traitement existe dans le lignage"),
    ("dbt", "order_details", "snowflake", "ORDER_DETAILS_REPLICA", True,
     "réplique déclarée ; seul le nom porte le suffixe"),
    ("dbt", "order_details", "powerbi", "ORDER_DETAILS", True,
     "même table, casse différente et deux colonnes de plus côté powerbi"),

    # --- des ressemblances trompeuses ----------------------------------------
    ("dbt", "countries", "dbt", "regions", False,
     "deux tables de référence à quatre colonnes, entités différentes"),
    ("dbt", "warehouses", "dbt", "product_categories", False,
     "même forme, un entrepôt n'est pas une catégorie de produit"),
    ("postgres", "products", "postgres", "product_information", False,
     "noms voisins, 12 colonnes contre 5, granularités différentes"),
    ("dbt", "promotions", "tableau", "promotions", False,
     "homonymes ; recouvrement de colonnes mesuré à 9 %"),
    ("dbt", "order_details", "powerbi", "Customer Analytics Measures", False,
     "des mesures calculées en aval, pas une copie de la table"),
    ("dbt", "orders", "dbt", "order_items", False,
     "une commande et ses lignes : reliées, pas identiques"),
]


def trouver(jeux, plateforme, nom):
    cible = nom.lower()
    for j in jeux:
        if j.plateforme == plateforme and j.nom.lower() == cible:
            return j
    return None


def main() -> int:
    config = Config.depuis_environnement()
    print(f"juge : {config.modele_juge} en {config.region}\n")

    jeux = Catalogue(config).jeux()
    juge = Juge(config)

    # Avant tout verdict : le juge répond-il ? Un juge muet rendrait « aucune
    # copie », c'est-à-dire un catalogue en règle. La panne se déguiserait en
    # bonne nouvelle.
    try:
        juge.sonder()
        print("sonde : le juge répond.\n")
    except JugeError as e:
        print(f"sonde : ÉCHEC — {e}")
        return 2

    justes = total = 0
    erreurs = []
    for pg, ng, pd_, nd, attendu, pourquoi in EPREUVE:
        g, d = trouver(jeux, pg, ng), trouver(jeux, pd_, nd)
        if g is None or d is None:
            print(f"  ⚠ introuvable : {pg}/{ng} ou {pd_}/{nd} — couple ignoré")
            continue
        candidat = Candidat(
            gauche=g, droite=d,
            recouvrement=recouvrement(g, d),
            meme_nom=g.nom.lower() == d.nom.lower(),
            colonnes_communes=tuple(sorted(g.noms_colonnes & d.noms_colonnes)),
            colonnes_propres_gauche=tuple(sorted(g.noms_colonnes - d.noms_colonnes)),
            colonnes_propres_droite=tuple(sorted(d.noms_colonnes - g.noms_colonnes)),
        )
        verdict = juge.meme_donnee(candidat)
        total += 1
        bon = verdict.identiques == attendu
        justes += bon
        marque = "✓" if bon else "✗"
        print(f"  {marque} {pg}/{ng} ≟ {pd_}/{nd}")
        print(f"      attendu {'même' if attendu else 'distinct':<8} "
              f"— {pourquoi}")
        print(f"      rendu   {'même' if verdict.identiques else 'distinct':<8} "
              f"({verdict.confiance}, recouvrement {candidat.recouvrement:.0%}) "
              f": {verdict.raison}")
        if not bon:
            erreurs.append((f"{pg}/{ng} ≟ {pd_}/{nd}", verdict.raison))

    print(f"\n{justes}/{total} couples correctement tranchés")
    if erreurs:
        print("\nles erreurs, à regarder avant de se fier au juge :")
        for couple, raison in erreurs:
            print(f"  {couple} — le juge dit : {raison}")
    return 0 if justes == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
