#!/usr/bin/env python3
"""Reproduit chaque chiffre affirmé dans CLAUDE.md et dans le README.

Un chiffre qu'on ne peut pas refaire tourner est une opinion. Ce script est la
preuve : il interroge le vrai graphe et réaffiche les mesures qui fondent la
conception de Fadlie.

    set -a && . ./.env && set +a
    python scripts/mesurer-catalogue.py
"""
import collections
import json
import os
import sys
import urllib.parse
import urllib.request

GMS = os.environ.get("DATAHUB_GMS_URL")
JETON = os.environ.get("DATAHUB_GMS_TOKEN")
if not GMS or not JETON:
    sys.exit("DATAHUB_GMS_URL et DATAHUB_GMS_TOKEN sont requis (voir .env.example)")

# Les noms de colonnes qui *ressemblent* à de la donnée personnelle. Cette liste
# n'est pas la règle de Fadlie — c'est le repère grossier qui sert à mesurer
# l'écart entre ce que le catalogue déclare et ce qu'il contient. La distinguer
# du verdict est tout le sujet : voir docs/appariement.md.
SOUPCON = ("email", "phone", "address", "first_name", "last_name", "zipcode",
           "customer_id", "cust_", "billing", "shipping", "town", "city")


def gql(requete, variables=None):
    corps = json.dumps({"query": requete, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        GMS + "/api/graphql", data=corps,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + JETON})
    with urllib.request.urlopen(req, timeout=90) as r:
        rep = json.loads(r.read())
    if rep.get("errors"):
        sys.exit("GraphQL : " + json.dumps(rep["errors"])[:600])
    return rep["data"]


def aspect(urn, nom):
    """Un aspect brut, par l'API OpenAPI : le lignage fin n'est pas en GraphQL."""
    u = f"{GMS}/openapi/v2/entity/dataset/{urllib.parse.quote(urn, safe='')}/{nom}"
    req = urllib.request.Request(u, headers={"Authorization": "Bearer " + JETON})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception:
        return {}


JEUX = """
{ search(input:{type:DATASET, query:"*", start:0, count:300}) {
    total
    searchResults { entity { ... on Dataset {
      urn name platform { name }
      properties { description }
      domain { domain { properties { name } } }
      ownership { owners { owner { ... on CorpUser { username } ... on CorpGroup { name } } } }
      globalTags { tags { tag { urn } } }
      schemaMetadata { fields { fieldPath description
        globalTags { tags { tag { urn } } }
        glossaryTerms { terms { term { urn } } } } }
      editableSchemaMetadata { editableSchemaFieldInfo { fieldPath description
        globalTags { tags { tag { urn } } }
        glossaryTerms { terms { term { urn } } } } }
    } } } } }"""


def marquages(jeu):
    """Étiquettes et termes portés par un jeu, au jeu comme à la colonne."""
    au_jeu = {t["tag"]["urn"].split(":")[-1]
              for t in ((jeu.get("globalTags") or {}).get("tags") or [])}
    par_champ = collections.defaultdict(set)
    for bloc in (((jeu.get("schemaMetadata") or {}).get("fields") or []),
                 ((jeu.get("editableSchemaMetadata") or {}).get("editableSchemaFieldInfo") or [])):
        for f in bloc:
            m = {t["tag"]["urn"].split(":")[-1]
                 for t in ((f.get("globalTags") or {}).get("tags") or [])}
            m |= {t["term"]["urn"].split(":")[-1]
                  for t in ((f.get("glossaryTerms") or {}).get("terms") or [])}
            if m:
                par_champ[f["fieldPath"]] |= m
    return au_jeu, par_champ


def colonnes(jeu):
    return [f["fieldPath"] for f in ((jeu.get("schemaMetadata") or {}).get("fields") or [])]


def sensibles(noms):
    return [c for c in noms if any(s in c.lower() for s in SOUPCON)]


d = gql(JEUX)
jeux = [r["entity"] for r in d["search"]["searchResults"]]
n = len(jeux)
print(f"jeux de données : {d['search']['total']}\n")

# --- 1. l'étendue -------------------------------------------------------------
plateformes = collections.Counter(j["platform"]["name"] for j in jeux)
print("— plateformes —")
for p, c in plateformes.most_common():
    print(f"  {p:<12} {c}")

# --- 2. ce qui manque ---------------------------------------------------------
sans_desc = sum(1 for j in jeux if not (j.get("properties") or {}).get("description"))
sans_prop = sum(1 for j in jeux if not (j.get("ownership") or {}).get("owners"))
sans_dom = sum(1 for j in jeux if not (j.get("domain") or {}).get("domain"))
champs = sum(len(colonnes(j)) for j in jeux)
decrits = sum(1 for j in jeux
              for f in ((j.get("schemaMetadata") or {}).get("fields") or [])
              if f.get("description"))
print(f"\n— ce qui manque, sur {n} jeux —")
print(f"  sans description   {sans_desc:>3}  ({100 * sans_desc // n} %)")
print(f"  sans propriétaire  {sans_prop:>3}  ({100 * sans_prop // n} %)")
print(f"  sans domaine       {sans_dom:>3}  ({100 * sans_dom // n} %)")
print(f"  colonnes décrites  {decrits}/{champs}  ({100 * decrits // champs} %)")

# --- 3. l'angle mort ----------------------------------------------------------
# La mesure qui fonde le projet : ce que le catalogue *déclare* personnel, face à
# ce qu'il *contient* de personnel.
porteurs = []
for j in jeux:
    au_jeu, par_champ = marquages(j)
    c = sum(1 for x in au_jeu if "PII" in x) + \
        sum(1 for s in par_champ.values() for x in s if "PII" in x)
    if c:
        porteurs.append((j["platform"]["name"], j["name"], c))

exposes = [j for j in jeux if sensibles(colonnes(j))]
print(f"\n— l'angle mort —")
print(f"  jeux déclarés personnels (étiquette PII_Data) : {len(porteurs)} / {n}")
for p, nom, c in porteurs:
    print(f"      {p:<10} {nom:<40} {c} marquage(s)")
print(f"  jeux contenant des colonnes qui en ont l'air   : {len(exposes)} / {n}")
print(f"  écart                                          : {len(exposes) - len(porteurs)}")

# --- 4. le lignage est-il fin ? ----------------------------------------------
# Décisif : sans lignage à la colonne, aucune propagation mécanique n'est
# possible. Tout le reste de Fadlie découle de cette absence.
avec_fin = 0
for j in jeux:
    a = aspect(j["urn"], "upstreamLineage")
    if (((a or {}).get("upstreamLineage") or {}).get("value") or {}).get("fineGrainedLineages"):
        avec_fin += 1
print(f"\n— lignage —")
print(f"  jeux portant du lignage à la colonne : {avec_fin} / {n}")
if avec_fin == 0:
    print("  → aucune propagation mécanique possible : le lignage présélectionne,")
    print("    l'appariement et le verdict sont à construire.")

# --- 5. la descendance d'un jeu marqué ---------------------------------------
depart = next((j for j in jeux
               if j["name"].lower() == "order_details" and j["platform"]["name"] == "snowflake"), None)
if depart:
    aval = gql("""
      query($urn:String!) { dataset(urn:$urn) {
        lineage(input:{direction:DOWNSTREAM, start:0, count:100}) {
          total
          relationships { entity { urn type ... on Dataset {
            name platform { name }
            globalTags { tags { tag { urn } } }
            schemaMetadata { fields { fieldPath globalTags { tags { tag { urn } } }
              glossaryTerms { terms { term { urn } } } } }
            editableSchemaMetadata { editableSchemaFieldInfo { fieldPath
              globalTags { tags { tag { urn } } }
              glossaryTerms { terms { term { urn } } } } }
          } } } } } }""", {"urn": depart["urn"]})["dataset"]["lineage"]
    print(f"\n— en aval de {depart['platform']['name']}/{depart['name']} : {aval['total']} —")
    for rel in aval["relationships"]:
        e = rel["entity"]
        if e["type"] != "DATASET":
            continue
        au_jeu, par_champ = marquages(e)
        cols = colonnes(e)
        sens = sensibles(cols)
        non_dites = [c for c in sens if c not in par_champ]
        declare = any("PII" in x for x in au_jeu) or \
            any("PII" in x for s in par_champ.values() for x in s)
        drapeau = "  ⚠" if non_dites and not declare else "   "
        print(f"{drapeau} {e['platform']['name']:<10} {e['name']:<38} "
              f"{len(cols):>3} col.  {len(sens):>2} sensibles  "
              f"{'déclaré' if declare else 'rien'}")
        if non_dites and not declare:
            print(f"        non déclarées : {', '.join(non_dites[:8])}"
                  f"{' …' if len(non_dites) > 8 else ''}")
