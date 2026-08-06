#!/usr/bin/env python3
"""La même donnée, dans plusieurs systèmes, sans une arête pour le dire.

C'est la mesure qui fonde Fadlie. Elle établit trois choses :

1. Onze tables existent à l'identique sur quatre plateformes — recouvrement de
   colonnes de 100 %.
2. Aucun lignage ne les relie. Les douze tables postgres et les douze tables s3
   n'ont **aucune** arête, dans aucun sens. Donc aucune propagation le long du
   lignage ne les atteindra jamais.
3. La gouvernance s'arrête à la frontière : propriétaires, domaine, description
   et étiquettes existent d'un côté et pas de l'autre, sur des colonnes
   identiques.

Et elle établit aussi pourquoi un simple appariement par nom ne suffit pas :
quatre groupes portent le même nom avec un recouvrement de colonnes quasi nul.

    set -a && . ./.env && set +a
    ./scripts/tunnel.sh && python scripts/mesurer-jumeaux.py
"""
import collections
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

# --- 1. qui n'a aucun lignage ? ----------------------------------------------
sans_lignage = []
for e in jeux:
    n = 0
    for sens in ("UPSTREAM", "DOWNSTREAM"):
        n += gql("""query($urn:String!,$d:LineageDirection!){ dataset(urn:$urn){
            lineage(input:{direction:$d,start:0,count:1}){ total } } }""",
                 {"urn": e["urn"], "d": sens})["dataset"]["lineage"]["total"]
    if n == 0:
        sans_lignage.append(e)

par_plateforme = collections.Counter(e["platform"]["name"] for e in sans_lignage)
print(f"jeux sans aucun lignage : {len(sans_lignage)} / {len(jeux)}")
for p, c in par_plateforme.most_common():
    print(f"  {p:<12} {c}")
print("  → aucune propagation le long du lignage ne peut les atteindre.\n")

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
