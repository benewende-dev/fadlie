# Fadlie

**The same data lives in four systems. Your catalog knows every path between
them. Only one copy is governed.**

Fadlie is an MCP agent for [DataHub](https://datahub.com). It finds datasets
that hold the same data across different platforms, then finds the governance —
owners, domain, descriptions, PII tags, glossary terms — that stopped at one of
them. It can level the difference, and it never writes a value it did not read
from a dataset it names.

Built for **Build with DataHub: The Agent Hackathon**, on the contest's own
`showcase-ecommerce` dataset. Every number below is produced by a script in this
repository, against a live DataHub instance.

![Fadlie reading the catalog, listing the governance that stopped at one copy of
`products`, and levelling it — every value naming the dataset it came
from](docs/images/demo.gif)

*Sixteen seconds of a real run against the deployed agent: 97 pairs examined, 18
groups of copies, 53 gaps on the `products` copies alone — then zero. The full
video, two minutes and forty seconds, is at
<https://youtu.be/YXff0HNRAwU>.*

**Every finding, browsable, nothing to install:
<https://benewende-dev.github.io/fadlie/>** — each gap with the dataset its
value would be copied from, the judge's reason for every pair, and the one
conflict Fadlie refuses to settle. That page is generated from
[`examples/`](examples/) by a script that connects to nothing.

---

## What the measurements found

Run `python scripts/mesurer-jumeaux.py` to reproduce all of this.

**The lineage graph tells you nothing about whether two datasets hold the same
data.** The graph is a single component: 103 nodes, 161 edges, no isolated
dataset. All 88 same-name pairs are connected — and so is every one of the 316
pairs picked at random. Connectivity carries no information whatsoever.

Distance carries almost none. Set the threshold at 4 hops and you catch 86 of
the 88 same-name pairs, along with 199 of the 316 strangers. There is no cut
that keeps the twins and drops the rest.

![Lineage distance for same-name pairs and for pairs picked at random: two
distributions that overlap, with no threshold separating
them](docs/images/lignage.svg)

`python scripts/capturer-lignage.py` writes the numbers behind that figure to
[`examples/lineage_graph.json`](examples/lineage_graph.json), and
`scripts/dessiner-le-lignage.py` draws it from that file without touching the
network. The capture also checks something the figure depends on: charts and
dashboards hang off the graph as leaves that cannot be traversed, so dropping
them leaves 90 nodes and 123 edges and **not one distance changes** — verified
across all 4 489 pairs rather than assumed.

**Names tell you almost as little.** Three of fifteen same-name groups are not
the same thing: four Tableau datasets called `Custom SQL Query` share 0 % of
their columns; `promotions` shares 9 %.

**And the governance does not travel.** Eleven tables exist identically on dbt,
Snowflake, Postgres and S3 — 100 % column overlap, `customers` has the same 22
columns in all four. On the datapack as it ships, `dbt/customers` has three
owners, a domain and a description; its three twins have none, none and none.
Twelve identical columns are annotated on one side and bare on the other, and
`customers.customer_id` carries the `PII_Data` tag on Postgres alone.

Ask that catalog where the personal data is, and it answers with two datasets,
with the confidence of something that has looked.

> **The live demo no longer matches that paragraph, and that is the point.**
> Fadlie has since levelled three of the eighteen groups on the running
> instance — `customers`, `orders`, `products` — writing 102, 60 and 53 values
> that it read from their twins. The run captured in [`examples/`](examples/)
> counts 373 gaps left on 46 datasets, so there is plenty still to try. That
> total moves a little between runs — the judge confirms 83, 84 or 85 of the
> same 97 pairs — while the structural findings do not move at all. Reload the
> datapack into a fresh DataHub and the numbers above come back exactly.

## How it decides

Structure suggests. A model decides. Nothing is invented.

![An MCP client calls the Fadlie server on AWS App Runner; the server reads
DataHub Core on EC2, asks Amazon Nova Micro on Bedrock which datasets hold the
same data, and writes the missing governance back — a dry run unless asked
twice](docs/images/architecture.svg)

| Layer | What it does | Why it cannot be the last word |
|---|---|---|
| `catalogue` | reads schemas, governance, lineage | — |
| `candidats` | 2 211 pairs → 97 | names and column overlap are wrong 1 time in 5 |
| `juge` | Amazon Nova Micro, temperature 0 | it decides; it never guesses on its own |
| `ecart` | what one twin has and another lacks | — |

`python scripts/mesurer-le-juge.py` puts the judge against **16 pairs drawn from
the real catalog**, chosen to be hard in both directions: replicas that differ
in case and column count, reference tables of identical shape, aggregates
computed *from* a table rather than copied from it, and the four homonymous
Tableau queries that share only measure names. **16 out of 16.** Ten runs of the
same pair give the same verdict ten times.

## Two rules that shape everything

**Fadlie copies; it never writes.** No value put into the catalog is produced by
a model. Each one comes from a dataset that already carried it, and every
proposal names its source — `Ecart` refuses to exist without one. A description
generated by a machine is indistinguishable from a description written by the
team that knows the data; six months later nobody can tell which is which.

**A disagreement is not a gap.** `snowflake/ORDER_DETAILS` sits in *Ecommerce
Operations* while its four twins sit in *Data Platform Team*. Fadlie reports it
and does not choose. Someone decided, or someone erred, and neither is an
agent's call.

## A failure must not look like good news

The judge raises rather than returns "different". If it could silently fail,
Fadlie would report *no duplicates found* — a catalog in good order. Nobody
audits good news. So the server probes the model before its first verdict, and
both real failure modes are verified: a bare model id (Frankfurt requires the
regional inference profile) and credentials without Bedrock access.

## The tools

| Tool | What it returns |
|---|---|
| `catalog_summary` | pairs examined, groups found, gaps, disagreements |
| `find_duplicate_datasets` | the groups, with the judge's verdict for each pair |
| `governance_gaps` | every gap, each naming the dataset it would be copied from |
| `apply_governance` | writes them. **Dry run by default** |

No tool takes a user, a token, or an identity — authorisation comes from the
`Authorization` header, and a check enforces it because nothing in the language
does.

## Running it

```bash
cp .env.example .env && $EDITOR .env
set -a && . ./.env && set +a

python -m pytest tests/          # 77 tests, no network, no bill
python -m fadlie check           # reads config, connects to nothing
python -m fadlie report          # the full analysis, printed
python -m fadlie serve           # the MCP server, locally

python scripts/mesurer-jumeaux.py    # every number in this README
python scripts/mesurer-le-juge.py    # the judge against 16 hard pairs
python scripts/verifier-mcp.py       # 24 checks through a real MCP client
```

## What it runs on

- **DataHub Core** v1.7.0 on EC2, loaded with the contest's `showcase-ecommerce`
  datapack — 67 datasets across Snowflake, dbt, Postgres, S3, Tableau, PowerBI
  and Looker.
- **Amazon Bedrock**, Amazon Nova Micro as the judge, in `eu-central-1`.
- **AWS App Runner** for the MCP server, over HTTPS.

## Licence

Apache License 2.0 — see [LICENSE](LICENSE).
