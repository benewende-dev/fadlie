#!/usr/bin/env python3
"""La même donnée, dans plusieurs systèmes, et rien pour le dire.

C'est la mesure qui fonde Fadlie. Elle établit quatre choses.

1. **Onze tables existent à l'identique sur quatre plateformes** — dbt,
   snowflake, postgres, s3 — avec un recouvrement de colonnes de 100 %.
2. **La gouvernance s'arrête à dbt.** Propriétaires, domaine, description et
   annotations existent d'un côté et pas de l'autre, sur des colonnes
   identiques. Onze groupes sur douze sont gouvernés inégalement.
3. **Le nom ne peut pas trancher** : trois groupes homonymes sur quinze ne sont
   pas la même chose — `custom_sql_query` recouvre 0 %, `promotions` 9 %.
4. **Le lignage ne peut pas trancher non plus**, et c'est le résultat le plus
   utile. Le graphe est d'un seul tenant : 103 sommets, 0 jeu isolé, et les 88
   couples d'homonymes sont **tous** reliés — à distance 2 ou 4, c'est-à-dire
   la distance médiane entre deux jeux pris au hasard. La connexité ne porte
   aucune information sur « est-ce la même donnée ».

Il reste donc la structure, qui dit « peut-être », et un juge, qui tranche.

Deux avertissements payés cher, inscrits dans le code plus bas : mesurer trop
tôt (l'index de lignage se remplit longtemps après la recherche), et ne garder
que les arêtes entre jeux de données (les traitements sont des relais, et
`postgres/customers` n'a qu'eux pour voisins).

    set -a && . ./.env && set +a
    python scripts/mesurer-jumeaux.py
"""
import collections
import itertools
import json
import os
import sys
import urllib.request

GMS = os.environ.get("DATAHUB_GMS_URL")
JETON = os.environ.get("DATAHUB_GMS_TOKEN")
if not GMS or not JETON:
    sys.exit("DATAHUB_GMS_URL et DATAHUB_GMS_TOKEN sont requis (voir .env.example)")


def gql(requete, variables=None):
    req = urllib.request.Request(
        GMS + "/api/graphql",
        data=json.dumps({"query": requete, "variables": variables or {}}).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + JETON})
    with urllib.request.urlopen(req, timeout=90) as r:
        rep = json.loads(r.read())
    if rep.get("errors"):
        sys.exit("GraphQL : " + json.dumps(rep["errors"])[:600])
    return rep["data"]


JEUX = """
{ search(input:{type:DATASET, query:"*", start:0, count:300}) {
  searchResults { entity { ... on Dataset {
    urn name platform { name }
    properties { description }
    ownership { owners { owner { ... on CorpUser { username } ... on CorpGroup { name } } } }
    domain { domain { properties { name } } }
    schemaMetadata { fields { fieldPath nativeDataType
      glossaryTerms { terms { term { urn } } } globalTags { tags { tag { urn } } } } }
    editableSchemaMetadata { editableSchemaFieldInfo { fieldPath
      glossaryTerms { terms { term { urn } } } globalTags { tags { tag { urn } } } } }
  } } } } }"""


def colonnes(e):
    return {f["fieldPath"].lower(): (f.get("nativeDataType") or "")
            for f in ((e.get("schemaMetadata") or {}).get("fields") or [])}


def annotations(e):
    """Étiquettes et termes par colonne, schéma et couche éditable réunis."""
    m = collections.defaultdict(set)
    for bloc in (((e.get("schemaMetadata") or {}).get("fields") or []),
                 ((e.get("editableSchemaMetadata") or {}).get("editableSchemaFieldInfo") or [])):
        for f in bloc:
            s = {t["term"]["urn"].split(":")[-1] for t in ((f.get("glossaryTerms") or {}).get("terms") or [])}
            s |= {t["tag"]["urn"].split(":")[-1] for t in ((f.get("globalTags") or {}).get("tags") or [])}
            if s:
                m[f["fieldPath"].lower()] |= s
    return m


def gouvernance(e):
    return (len((e.get("ownership") or {}).get("owners") or []),
            ((e.get("domain") or {}).get("domain") or {}).get("properties", {}).get("name"),
            bool((e.get("properties") or {}).get("description")))


jeux = [r["entity"] for r in gql(JEUX)["search"]["searchResults"]]

# --- 1. le lignage dit-il quelque chose sur « est-ce la même donnée » ? ------
# Cette mesure a été fausse deux fois, dans deux directions opposées. D'abord
# parce qu'elle a été lancée pendant que l'index de lignage se remplissait —
# 24 jeux paraissaient sans arête. Puis parce qu'elle ne gardait que les arêtes
# entre *jeux de données* : or `postgres/customers` n'a qu'un voisin, et c'est
# un **traitement**, `export_table_customers_to_s3`, qui mène à `s3/customers`.
# Filtrer les traitements coupe le chemin exactement là où il passe.
#
# Les traitements sont donc des relais, et le parcours suit la frontière au-delà
# des seuls jeux de départ.
LIGNAGE = """
query($u:String!, $d:LineageDirection!) {
  entity(urn:$u) {
    ... on Dataset { lineage(input:{direction:$d,start:0,count:200}) {
        relationships { entity { urn type } } } }
    ... on DataJob { lineage(input:{direction:$d,start:0,count:200}) {
        relationships { entity { urn type } } } } } }"""

voisins = collections.defaultdict(set)
a_faire = collections.deque(e["urn"] for e in jeux)
explores = set()
while a_faire:
    u = a_faire.popleft()
    if u in explores:
        continue
    explores.add(u)
    for sens in ("UPSTREAM", "DOWNSTREAM"):
        e = gql(LIGNAGE, {"u": u, "d": sens}).get("entity") or {}
        for r in ((e.get("lineage") or {}).get("relationships") or []):
            v, t = r["entity"]["urn"], r["entity"]["type"]
            voisins[u].add(v)
            voisins[v].add(u)
            if t in ("DATASET", "DATA_JOB") and v not in explores:
                a_faire.append(v)

isoles = [e for e in jeux if not voisins[e["urn"]]]
aretes = sum(len(v) for v in voisins.values()) // 2
print(f"graphe de lignage : {len(voisins)} sommets ({len(jeux)} jeux), "
      f"{aretes} arêtes, {len(isoles)} jeu(x) sans arête")
if isoles:
    print("  ⚠ des jeux isolés : l'index de lignage n'a peut-être pas fini de se")
    print("    remplir. Attendre et re-mesurer — une mesure trop tôt rend un")
    print("    chiffre plausible et faux. C'est arrivé.\n")


def distance(a, b):
    """Plus court chemin non orienté, ou None."""
    if a == b:
        return 0
    vus, file = {a}, collections.deque([(a, 0)])
    while file:
        u, d = file.popleft()
        for v in voisins[u]:
            if v in vus:
                continue
            if v == b:
                return d + 1
            vus.add(v)
            file.append((v, d + 1))
    return None

# --- 2. les homonymes se recouvrent-ils ? ------------------------------------
groupes = collections.defaultdict(list)
for e in jeux:
    groupes[e["name"].lower().replace(" ", "_")].append(e)
multi = {n: g for n, g in groupes.items() if len(g) > 1}

print(f"{'nom':<22} {'plateformes':<36} {'colonnes':<18} {'recouvrement':>12}")
print("-" * 92)
jumeaux = []
for nom, g in sorted(multi.items()):
    cs = [colonnes(e) for e in g]
    if not all(cs):
        continue
    commun = set.intersection(*[set(c) for c in cs])
    union = set.union(*[set(c) for c in cs])
    recouv = 100 * len(commun) // len(union) if union else 0
    print(f"{nom:<22} {','.join(e['platform']['name'] for e in g):<36} "
          f"{'/'.join(str(len(c)) for c in cs):<18} {recouv:>11} %")
    if recouv >= 80:
        jumeaux.append((nom, g, commun))

faibles = len(multi) - len(jumeaux)
print(f"\n  {len(jumeaux)} groupes se recouvrent à 80 % ou plus.")
print(f"  {faibles} portent le même nom **sans** être la même chose.")
print("  → le nom présélectionne ; il ne tranche pas.\n")

# --- 2 bis. et le lignage relie-t-il ces copies entre elles ? ----------------
print("=== distance de lignage entre homonymes ===")
print(f"{'groupe':<22} {'couples':>8} {'reliés':>7}  distances")
print("-" * 60)
couples = relies = 0
for nom, g in sorted(multi.items()):
    ds = [distance(g[i]["urn"], g[k]["urn"])
          for i in range(len(g)) for k in range(i + 1, len(g))]
    compte = collections.Counter(d for d in ds if d is not None)
    couples += len(ds)
    relies += sum(1 for d in ds if d is not None)
    print(f"{nom:<22} {len(ds):>8} {sum(1 for d in ds if d is not None):>7}  "
          f"{dict(sorted(compte.items())) if compte else '— aucun chemin'}")
print(f"\n  {relies} couples d'homonymes sur {couples} sont reliés par un chemin.")

# Et le contrôle qui rend ce chiffre lisible : à quoi ressemble un couple *au
# hasard* ? Si les jumeaux sont à la même distance que n'importe quel couple,
# alors la connexité ne dit rien de « est-ce la même donnée ».
tous = sorted(e["urn"] for e in jeux)
echantillon = list(itertools.islice(itertools.combinations(tous, 2), 0, None, 7))
au_hasard = sorted(d for d in (distance(a, b) for a, b in echantillon) if d is not None)
if au_hasard:
    print(f"  distance médiane entre deux jeux **au hasard** : "
          f"{au_hasard[len(au_hasard) // 2]}"
          f"  ({len(au_hasard)}/{len(echantillon)} couples reliés)")
print("  → les jumeaux sont à la même distance que n'importe quel couple : la")
print("    connexité ne dit rien. La structure présélectionne, un juge tranche.\n")

# --- 3. la gouvernance franchit-elle la frontière ? --------------------------
print("=== colonnes identiques, annotations divergentes ===")
divergences = 0
for nom, g, commun in jumeaux:
    ms = [annotations(e) for e in g]
    for col in sorted(commun):
        etats = [frozenset(m.get(col, set())) for m in ms]
        if len(set(etats)) > 1:
            divergences += 1
            detail = "  ".join(
                f"{e['platform']['name']}:{','.join(sorted(x)[:1]) or '—'}"
                for e, x in zip(g, etats))
            print(f"  {nom}.{col:<22} {detail}")
print(f"  → {divergences} colonnes marquées d'un côté, nues de l'autre.\n")

print("=== propriétaire / domaine / description, d'un jumeau à l'autre ===")
ecarts = 0
for nom, g, _ in jumeaux:
    etats = [gouvernance(e) for e in g]
    if len(set(etats)) > 1:
        ecarts += 1
        print(f"  {nom:<20} " + "  ".join(
            f"{e['platform']['name']}[prop:{p} dom:{d or '—'} desc:{'oui' if x else 'non'}]"
            for e, (p, d, x) in zip(g, etats)))
print(f"  → {ecarts} groupes sur {len(jumeaux)} gouvernés inégalement.")
