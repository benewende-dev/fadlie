#!/usr/bin/env python3
"""Capture le graphe de lignage dans `examples/lineage_graph.json`.

Le README affirme que **le lignage ne distingue pas un jumeau d'un inconnu**.
C'est la mesure qui fonde tout le reste, et elle n'était lisible que dans une
phrase. Ce fichier l'expose, et `dessiner-le-lignage.py` la dessine — sans
réseau, depuis ce JSON. Une image qui exigerait un compte DataHub pour être
regénérée ne serait vérifiable par personne.

    set -a && . ./.env && set +a
    python scripts/capturer-lignage.py

**Deux graphes, et il faut les distinguer**, sinon on publie un chiffre en
croyant en publier un autre.

*Le graphe complet* compte tout ce que le lignage relie, y compris les
graphiques et tableaux de bord. Ils ne mènent nulle part : on ne peut pas les
traverser, donc **aucun plus court chemin entre deux jeux ne passe par eux**.
Ce sont eux qui font les 103 sommets et 161 arêtes annoncés par le README et
par `mesurer-jumeaux.py`.

*Le graphe traversable* ne garde que les jeux et les traitements — c'est le
graphe sur lequel une distance veut dire quelque chose, et le seul que Fadlie
consulte (`Catalogue.graphe_lignage`). Il est plus petit. **Toutes les
distances sont les mêmes dans les deux**, ce que ce script vérifie plutôt que
de l'affirmer.

Deux pièges payés cher, hérités de `mesurer-jumeaux.py`. Mesurer trop tôt :
l'index de lignage se remplit longtemps après la recherche, et une mesure
prématurée rend un chiffre plausible et faux. Et ne traverser que les jeux :
les traitements sont des relais, `postgres/customers` n'a qu'eux pour voisins,
les retirer fabrique des îlots qui n'existent pas.
"""
from __future__ import annotations

import collections
import itertools
import json
import os
import pathlib
import statistics
import sys
import urllib.request

RACINE = pathlib.Path(__file__).resolve().parent.parent
CIBLE = RACINE / "examples" / "lineage_graph.json"

GMS = os.environ.get("DATAHUB_GMS_URL")
JETON = os.environ.get("DATAHUB_GMS_TOKEN")
if not GMS or not JETON:
    sys.exit("DATAHUB_GMS_URL et DATAHUB_GMS_TOKEN sont requis (voir .env.example)")

TRAVERSABLES = ("DATASET", "DATA_JOB")

# Un couple sur sept, comme `mesurer-jumeaux.py`. Déterministe : le chiffre
# publié doit se retrouver, et un échantillon tiré au sort ne se retrouve pas.
PAS = 7


def gql(requete: str, variables: dict | None = None) -> dict:
    req = urllib.request.Request(
        GMS + "/api/graphql",
        data=json.dumps({"query": requete,
                         "variables": variables or {}}).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + JETON})
    with urllib.request.urlopen(req, timeout=90) as r:
        rep = json.loads(r.read())
    if rep.get("errors"):
        sys.exit("GraphQL : " + json.dumps(rep["errors"])[:600])
    return rep["data"]


JEUX = """
{ search(input:{type:DATASET, query:"*", start:0, count:300}) {
  searchResults { entity { ... on Dataset {
    urn name platform { name } } } } } }"""

LIGNAGE = """
query($u:String!, $d:LineageDirection!) {
  entity(urn:$u) {
    ... on Dataset { lineage(input:{direction:$d,start:0,count:200}) {
        relationships { entity { urn type } } } }
    ... on DataJob { lineage(input:{direction:$d,start:0,count:200}) {
        relationships { entity { urn type } } } } } }"""


def distances(graphe: dict[str, set[str]], depart: str) -> dict[str, int]:
    vus = {depart: 0}
    file = collections.deque([depart])
    while file:
        u = file.popleft()
        for v in graphe.get(u, ()):
            if v not in vus:
                vus[v] = vus[u] + 1
                file.append(v)
    return vus


def profil(couples: list[tuple[str, str]],
           tous: dict[str, dict[str, int]]) -> dict:
    mesures = [tous[a].get(b) for a, b in couples]
    atteints = [m for m in mesures if m is not None]
    return {
        "pairs": len(couples),
        "connected": len(atteints),
        "unreachable": len(mesures) - len(atteints),
        "median_distance": statistics.median(atteints) if atteints else None,
        "distribution": dict(sorted(collections.Counter(atteints).items())),
    }


def main() -> None:
    jeux = [r["entity"] for r
            in gql(JEUX)["search"]["searchResults"] if r["entity"]]
    urns = [j["urn"] for j in jeux]
    print(f"{len(jeux)} jeux lus")

    complet: dict[str, set[str]] = collections.defaultdict(set)
    traversable: dict[str, set[str]] = {u: set() for u in urns}
    types: dict[str, str] = {u: "DATASET" for u in urns}

    a_faire = collections.deque(urns)
    explores: set[str] = set()
    while a_faire:
        u = a_faire.popleft()
        if u in explores:
            continue
        explores.add(u)
        for sens in ("UPSTREAM", "DOWNSTREAM"):
            e = gql(LIGNAGE, {"u": u, "d": sens}).get("entity") or {}
            for r in ((e.get("lineage") or {}).get("relationships") or []):
                v, t = r["entity"]["urn"], r["entity"]["type"]
                types.setdefault(v, t)
                complet[u].add(v)
                complet[v].add(u)
                if t in TRAVERSABLES:
                    traversable.setdefault(u, set()).add(v)
                    traversable.setdefault(v, set()).add(u)
                    if v not in explores:
                        a_faire.append(v)

    def taille(g: dict[str, set[str]]) -> tuple[int, int]:
        return len(g), sum(len(v) for v in g.values()) // 2

    n_complet, a_complet = taille(complet)
    n_trav, a_trav = taille(traversable)

    # Les distances, sur chacun des deux graphes. On les compare : si elles
    # diffèrent, la phrase « aucun chemin ne passe par un graphique » est
    # fausse et il faut le savoir avant de la publier.
    d_trav = {u: distances(traversable, u) for u in urns}
    d_complet = {u: distances(complet, u) for u in urns}
    ecarts = sum(1 for a in urns for b in urns
                 if d_trav[a].get(b) != d_complet[a].get(b))
    if ecarts:
        sys.exit(f"REFUS : {ecarts} distances diffèrent entre les deux graphes. "
                 "L'affirmation « les feuilles ne portent aucun chemin » ne "
                 "tient pas sur ce catalogue.")

    restants, composantes = set(complet), []
    while restants:
        vu = distances(complet, next(iter(restants)))
        composantes.append(len(vu))
        restants -= set(vu)
    composantes.sort(reverse=True)

    # Le groupement du README : le nom nu, sans retrait de suffixe. C'est lui
    # qui donne les 88 couples annoncés ; une autre normalisation en donnerait
    # un autre nombre, tout aussi juste et impossible à rapprocher du texte.
    par_nom: dict[str, list[str]] = {}
    for j in jeux:
        par_nom.setdefault(j["name"].lower().replace(" ", "_"), []).append(j["urn"])
    homonymes = [(a, b) for g in par_nom.values() if len(g) > 1
                 for a, b in itertools.combinations(sorted(g), 2)]
    echantillon = list(itertools.islice(
        itertools.combinations(sorted(urns), 2), 0, None, PAS))

    feuilles = collections.Counter(
        t for u, t in types.items() if t not in TRAVERSABLES)

    donnees = {
        "full_graph": {
            "nodes": n_complet, "edges": a_complet,
            "components": len(composantes),
            "largest_component": composantes[0],
            "leaf_entity_types": dict(feuilles.most_common()),
            "note": "Everything lineage connects, charts and dashboards "
                    "included. They cannot be traversed, so no shortest path "
                    "between two datasets passes through one.",
        },
        "traversable_graph": {
            "nodes": n_trav, "edges": a_trav,
            "note": "Datasets and data jobs only — the graph Fadlie reads. "
                    "Every distance below is identical in both graphs, "
                    "which this capture checks rather than assumes.",
        },
        "datasets": len(urns),
        "isolated_datasets": sum(1 for u in urns if not complet.get(u)),
        "same_name_pairs": profil(homonymes, d_trav),
        "random_pairs": profil(echantillon, d_trav),
        "random_pairs_note": f"every {PAS}th pair of the "
                             f"{len(urns) * (len(urns) - 1) // 2} possible, "
                             "not a draw — a published number has to be "
                             "reproducible",
        "graph": {u: sorted(v) for u, v in sorted(traversable.items())},
        "node_types": {u: types[u] for u in sorted(traversable)},
        "dataset_labels": {j["urn"]: f"{j['platform']['name']}/{j['name']}"
                           for j in jeux},
        "same_name_urns": [list(c) for c in homonymes],
    }

    CIBLE.write_text(json.dumps(donnees, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")

    h, r = donnees["same_name_pairs"], donnees["random_pairs"]
    print(f"  graphe complet         {n_complet} sommets, {a_complet} arêtes, "
          f"{len(composantes)} composante(s)")
    print(f"  graphe traversable     {n_trav} sommets, {a_trav} arêtes")
    print(f"  distances identiques   oui, sur les {len(urns) ** 2} couples")
    print(f"  jeux isolés            {donnees['isolated_datasets']}")
    print(f"  homonymes              {h['pairs']} couples, médiane "
          f"{h['median_distance']}, {h['distribution']}")
    print(f"  au hasard              {r['pairs']} couples, médiane "
          f"{r['median_distance']}, {r['distribution']}")
    print(f"  → {CIBLE.relative_to(RACINE)}")


if __name__ == "__main__":
    main()
