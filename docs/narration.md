# La narration, mot à mot

Le texte exact à donner à la voix de synthèse. [`docs/video.md`](video.md) dit
*quoi filmer* ; ce fichier dit *quoi dire*, et rien d'autre — pour qu'on puisse
le copier segment par segment sans avoir à décider quoi que ce soit au moment de
générer l'audio.

**En anglais**, parce que la vidéo est un livrable public et que le jury est
celui de DataHub. Même règle que le README et la licence.

## Le budget

Six segments, 356 mots. À cent cinquante mots par minute — le débit d'une voix
de synthèse lue confortablement — ça fait **2 min 22 de parole** pour une vidéo
de moins de trois minutes. Le reste, ce sont les silences pendant lesquels le
terminal travaille.

| segment | plan | mots | parole |
|---|---|---|---|
| 1 | 0:00 – 0:20 | 52 | ~21 s |
| 2 | 0:20 – 0:45 | 61 | ~24 s |
| 3 | 0:45 – 1:15 | 68 | ~27 s |
| 4 | 1:15 – 1:55 | 76 | ~30 s |
| 5 | 1:55 – 2:30 | 61 | ~24 s |
| 6 | 2:30 – 2:55 | 38 | ~15 s |

**Enregistrer les six séparément.** Un segment à refaire coûte alors vingt
secondes, pas trois minutes — et les silences entre segments se règlent au
montage, ce qui est exactement ce qu'on veut pour caler la voix sur un terminal
qui ne répond jamais deux fois à la même vitesse.

## Ce qui se prononce mal

Une voix de synthèse lit les nombres de façon imprévisible selon le moteur. Ils
sont donc **écrits en toutes lettres** ci-dessous. Ne pas les « corriger » en
repassant aux chiffres.

`MCP` s'écrit `M C P` pour que la voix épelle au lieu de tenter un mot. `dbt`
s'écrit `d b t`. Si le moteur massacre un nom de plateforme, l'écrire
phonétiquement **dans l'entrée du moteur uniquement** — jamais dans le dépôt.

---

## 1 — 0:00 – 0:20 · le problème

**À l'écran** : les quatre tables `customers`, et ce que chacune porte.

> The same customer table lives in four systems: d b t, Snowflake, Postgres, and
> S three. Twenty-two columns each, identical. One of them has three owners, a
> domain, and a description. The other three have none. Ask that catalog who
> owns customer data, and it will answer — with the confidence of something that
> has looked.

## 2 — 0:20 – 0:45 · pourquoi le lignage ne répond pas

**À l'écran** : les deux distances, en gros, en même temps.

> The obvious fix is lineage, so we measured it. The graph is a single connected
> component: a hundred and three nodes, a hundred and sixty-one edges, no
> isolated dataset. Every same-name pair is connected, at distance two or four.
> The median distance between two datasets picked at random is also four. Twins
> are indistinguishable from strangers.

## 3 — 0:45 – 1:15 · les noms mentent aussi

**À l'écran** : les quatre `Custom SQL Query`, puis le tableau des couches.

> Names are no better. Four Tableau datasets are all called Custom S Q L Query,
> and they share zero percent of their columns. So structure only shortlists —
> column overlap cuts two thousand two hundred and eleven pairs down to
> ninety-seven. Then a model on Amazon Bedrock decides, one pair at a time.
> Against sixteen hard pairs drawn from the real catalog: sixteen correct.

## 4 — 1:15 – 1:55 · l'agent déployé

**À l'écran** : `demo.py`, sections 1 à 3.

Deux analyses complètes et indépendantes ont rendu les mêmes nombres le 6 août
2026, donc ceux ci-dessous devraient tenir. **Enregistrer quand même ce segment
en dernier**, une fois la capture faite, et lire ce qui est réellement à
l'écran : c'est vingt secondes contre le seul défaut qu'un jury remarque à coup
sûr. Voir `video.md`.

> This is the deployed agent, answering over M C P. Ninety-seven pairs examined.
> Eighty-three hold the same data. Eighteen groups of copies, across platforms.
> Five hundred and eighty governance gaps, on forty-eight datasets.
>
> Here are the four customer tables, and the judge's own reason for calling two
> of them the same thing. A hundred and two gaps on those four copies alone —
> and every one of them names the dataset its value would be copied from.

## 5 — 1:55 – 2:30 · les deux règles

**À l'écran** : la scène « Fixing it », le passage de cent deux à zéro.

> Two rules shape all of this. Fadlie copies; it never writes. No value it
> proposes was produced by a model. A generated description is indistinguishable
> from one written by the team that knows the data, and six months later nobody
> can tell which is which.
>
> And writing is a dry run by default. Touching the catalog takes a second
> argument.

## 6 — 2:30 – 2:55 · ce qu'il refuse de faire

**À l'écran** : le désaccord sur `order_details`, puis l'erreur du juge.

> Snowflake's order details sits in one domain. Its three twins sit in another.
> Fadlie reports that, and does not choose. Someone decided, or someone erred,
> and neither is an agent's call.
>
> And when the judge cannot reach the model, it raises. It never reports a clean
> catalog. Nobody audits good news.
