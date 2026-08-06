# La narration, mot à mot

**Faite, le 6 août 2026 : 2 min 40, 1080p, voix Liam, sous-titres anglais.**
Ce qui suit est le texte exact qui a été prononcé — pas un brouillon.

**En anglais**, parce que la vidéo est un livrable public et que le jury est
celui de DataHub. Même règle que le README et la licence.

## Ce qui a été tourné, et sur quel groupe

Le plan principal devait être `customers`. Il ne l'est pas : `customers` avait
déjà été réparé par Fadlie lui-même au cours des essais, donc il n'avait plus
d'écart à montrer. La démonstration a été tournée sur **`products`** — même
forme exacte : quatre plateformes, trois jumeaux nus face à `dbt/products`, et
cinquante-trois écarts qui viennent tous de lui.

C'est pour ça que `scripts/demo.py` prend `--jeu` : une prise réelle consomme
son groupe, et il faut pouvoir en viser un autre sans attendre que le catalogue
se re-dégrade — ce qu'il ne fera jamais.

## Ce qui se prononce mal

Les nombres sont **écrits en toutes lettres** : un moteur de synthèse les
prononce autrement de façon imprévisible. Ne pas les « corriger » en repassant
aux chiffres. `MCP` s'écrit `M C P`, `dbt` s'écrit `d b t`, `SQL` s'écrit
`S Q L` — sinon la voix tente des mots. Les sous-titres, eux, refont le chemin
inverse : ils affichent `420` là où la voix dit *four hundred and twenty*.

## Les six segments, et leur durée mesurée

| segment | plan | mots | audio |
|---|---|---|---|
| s1 | 0:00 – 0:22 | 61 | 22.2 s |
| s2 | 0:22 – 0:47 | 58 | 24.4 s |
| s3 | 0:47 – 1:14 | 61 | 27.2 s |
| s4 | 1:14 – 1:50 | 87 | 35.7 s |
| s5 | 1:50 – 2:18 | 73 | 27.8 s |
| s6 | 2:18 – 2:40 | 52 | 23.0 s |

**Total : 160.3 s.** Enregistrés séparément — un segment à refaire coûte vingt secondes, pas trois minutes. C'est ce qui a permis de reprendre le segment 1 quand il a fallu passer de `orders` à `products` : la voix disait encore « order table » et « two owners » alors que l'image montrait `products` et trois propriétaires. **Les sous-titres l'ont attrapé, pas l'oreille.**

---

## s1 — 0:00 – 0:22 · le problème

**À l'écran** : les quatre tables `products` et ce que chacune porte.

> The same product table lives in four systems: d b t, Postgres, S three, and Snowflake. Identical columns, all four of them. One has three owners, a domain, a description, and twelve annotated columns. The other three have none of it. Ask this catalog who owns product data, and it will answer — with the confidence of something that has looked.

## s2 — 0:22 – 0:47 · pourquoi le lignage ne répond pas

**À l'écran** : une composante, cent trois nœuds, et les deux distances égales.

> Following lineage was the obvious answer, so it was measured. The graph is a single connected component: a hundred and three nodes, a hundred and sixty-one edges, not one isolated dataset. Every same-name pair is connected, at distance two or four. The median distance between two datasets picked at random is also four. Twins are indistinguishable from strangers.

## s3 — 0:47 – 1:14 · les noms mentent aussi

**À l'écran** : les quatre `Custom SQL Query`, les couches, le seize sur seize.

> Names are no better. Four Tableau datasets are all called Custom S Q L Query, and they share zero percent of their columns. So structure only shortlists: column overlap cuts two thousand two hundred and eleven pairs down to ninety-seven. Then a model on Amazon Bedrock decides, one pair at a time. Sixteen hard pairs from the real catalog: sixteen correct.

## s4 — 1:14 – 1:50 · l'agent déployé, en direct

**À l'écran** : `scripts/demo.py --jeu products`, révélé section par section.

> This is the deployed agent, answering over M C P. Ninety-seven pairs examined, eighty-five hold the same data, in eighteen groups across platforms. Four hundred and twenty governance gaps, on forty-three datasets. Here are the four product tables, and the judge's own reason for calling two of them the same. Fifty-three gaps on those copies alone, each naming where its value comes from. Dry run: fifty-three would be written, nothing written. Then the second argument — fifty-three values written to DataHub, in eleven seconds. Gaps now: zero.

## s5 — 1:50 – 2:18 · les deux règles

**À l'écran** : un écart avec sa source, et le passage à blanc / pour de vrai.

> Two rules shape all of this. Fadlie copies; it never writes. No value it proposes was produced by a model. Each one comes from a twin that already carried it, and names it. A description written by a machine is indistinguishable from one written by the team that knows the data — six months later, nobody can tell. And writing is a dry run by default. Touching the catalog takes a second argument.

## s6 — 2:18 – 2:40 · ce qu'il refuse de faire

**À l'écran** : le désaccord sur `order_details`, puis le juge qui lève.

> Snowflake's order details sits in one domain. Its three twins sit in another. Fadlie reports that, and does not choose. Someone decided, or someone erred, and neither is an agent's call. And when the judge cannot reach the model, it raises. It never reports a clean catalog, because nobody audits good news.
