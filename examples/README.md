# Example output

These are **real responses from the deployed agent**, captured on 6 August 2026
against the live DataHub instance. Nothing here was written by hand or trimmed
for effect. They exist so you can judge the quality of what Fadlie produces
without installing an MCP client or running anything.

Reproduce them:

```bash
set -a && . ./.env && set +a
FADLIE_MCP_URL=https://…/mcp python scripts/capturer-exemples.py
```

The script only reads. `apply_governance` is called as a dry run, and the
capture refuses to save unless the response confirms that nothing was written.

| File | Call |
|---|---|
| [`catalog_summary.json`](catalog_summary.json) | `catalog_summary()` |
| [`find_duplicate_datasets.json`](find_duplicate_datasets.json) | `find_duplicate_datasets()` |
| [`governance_gaps.json`](governance_gaps.json) | `governance_gaps(dataset="order_details")` |
| [`governance_gaps_all.json`](governance_gaps_all.json) | `governance_gaps()` — every gap, unfiltered |
| [`apply_governance_dry_run.json`](apply_governance_dry_run.json) | `apply_governance(dataset="order_details")` |

One more file is not a tool call.
[`lineage_graph.json`](lineage_graph.json) holds the lineage measurement the
whole design rests on — the graph, and the distance between every same-name
pair and every pair picked at random. `scripts/capturer-lignage.py` writes it
against DataHub; `scripts/dessiner-le-lignage.py` turns it into the figure in
the README without touching the network.

`governance_gaps_all.json` is also what the browsable page is built from —
`python scripts/faire-la-page.py` turns these files into a single HTML page and
connects to nothing while doing it.

## What to look at

**Every gap names its source.** In `governance_gaps.json`, each entry carries
`copied_from` and `copied_from_urn` — the dataset the value would be taken
from — alongside the `value` itself. Those fields are not decoration: the
`Ecart` type refuses to be constructed without a source. No value in this file
was produced by a model.

**The judge's reasons are in `find_duplicate_datasets.json`,** one per pair,
under `verdicts`. Read a few. They are the model's own words about why two
datasets hold the same data, and they are why a name match or a lineage path was
not enough. Note also that a reason is a comment, not a verified fact — the
judge sometimes justifies a correct verdict with a wrong detail, which is
exactly why Fadlie never writes a reason into the catalog.

**`apply_governance` did nothing,** and says so: `"applied": 0`, and a summary
that reads *"56 gaps simulated, nothing was written"*. Writing the catalog takes
a second argument.

**The single disagreement is at the end of `governance_gaps.json`.**
`snowflake/ORDER_DETAILS` sits in one domain while its twins sit in another.
Fadlie reports it and does not choose. Someone decided, or someone erred, and
neither is an agent's call.

## Why the numbers move

`analysis_age_seconds` tells you how old the served report was. A stale report is
returned immediately while a fresh one is computed in the background — a request
that waited for a full analysis would exceed the platform's 120-second limit.

The counts move a little between runs: the judge confirms 83, 85 or 84 pairs out
of the same 97 examined. The structural findings never move. Numbers quoted
anywhere in this repository are read off the run that produced them, never
copied from an earlier one.

And the live instance has drifted from the datapack on purpose: Fadlie has
already levelled `customers`, `orders` and `products`. Reload the datapack into
a fresh DataHub and the original state comes back exactly.
