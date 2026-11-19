# pgvector issue draft (NOT SENT)

Nothing in this file has been posted. Posting needs the author's approval (docs/MONTH_PLAN.md,
Rules). The text is written to be pasted as is, so everything under "Issue text" has to be
true; the status of each statement is listed in "What is verified" below.

## What is verified, and what is not

| Statement | Status |
|---|---|
| The plan and cost numbers in the table | Measured with EXPLAIN on the 500K x 1024 build of E17 (PostgreSQL 17.11, pgvector 0.8.6). Source: `data-manifests/e17_full_a5bb141.json`, result `task_0011_7014453` |
| The condition in `hnswcostestimate` | Read from `src/hnsw.c` at tag v0.8.6 (quoted below) |
| The formula predicts the ef at which the index cost drops | Computed for all 20 builds: matches in 20 of 20 (`analysis/predict_hnsw_cost_threshold.py`, `results/derived/e17_cost_threshold_check.json`) |
| 9 of 360 (N, dimension, ef) cells choose a sequential scan, all at 768 and 1024 dimensions | E17 analysis |
| The reproducer script reproduces the plans | **NOT RUN.** It has not been executed anywhere. The cost model uses page counts, which do not depend on the vector values, so random vectors should give the same plans, but that is an inference and has to be checked before posting |
| That the behavior is a bug and not intended | **Unknown.** The text asks the maintainers. It proposes no patch |
| Other PostgreSQL or pgvector versions | **Not tested.** Only 17.11 and 0.8.6 |
| The 218x slowdown of the scan plan | Measured once, in the E1 default-planner run (500K x 1024, ef=256: 888 ms against 4.1 ms, recall 0.9999), on a different build with the same page counts; not measured in the other eight affected cells |

## Issue text

**Title:** Planner can pick a sequential scan over the HNSW index for some `hnsw.ef_search` values when vectors are stored out of line (TOAST)

**Environment:** PostgreSQL 17.11 (Debian), pgvector 0.8.6, default planner settings
(`random_page_cost` 4, `seq_page_cost` 1, `cpu_tuple_cost` 0.01, `parallel_setup_cost` 1000,
`parallel_tuple_cost` 0.1, `max_parallel_workers_per_gather` 2), table `items(id bigint primary key,
embedding vector(1024))` with 500,000 rows, `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64)`. Query: `SELECT id FROM items ORDER BY embedding <=> $1 LIMIT 10`
(custom plan).

**What happens:** For `hnsw.ef_search` = 256 the planner chooses a parallel sequential scan
(`Limit / Gather Merge / Sort / Seq Scan`) instead of the index. The query returns correct results (it is
an exact scan, so recall was 0.9999 over 1,677 queries), but it took 888 ms per query against 4.1 ms with the
index forced (`enable_seqscan = off`), with no warning. The latency was measured in an earlier run on a
different build of the same table (same page counts); the plans and costs below come from the build
whose sizes are given. The neighboring values use the index:

| `hnsw.ef_search` | plan chosen | total cost, index plan | total cost, scan plan |
|---:|---|---:|---:|
| 192 | Index Scan | 10,515.5 | 11,819.4 |
| 224 | Index Scan | 11,932.1 | 11,819.4 |
| 256 | **Seq Scan** | 13,323.0 | 11,819.4 |
| 320 | Index Scan | 3,782.3 | 11,819.4 |

The cost of the index plan is not monotone in `ef_search`: it rises until 256 and then falls by a
factor of 3.5 at 320. The scan plan costs the same at every `ef_search`. The table has 3,712 heap
pages, 333,334 TOAST pages and 498,862 index pages (1024-dimensional float4 vectors are stored out of
line, so the heap holds pointers).

**Where it comes from (our reading of the code, please correct us):** in `hnswcostestimate`
(`src/hnsw.c`, v0.8.6) the startup cost is lowered only under this condition:

```c
startupPages = costs.numIndexPages * ratio;
if (startupPages > path->indexinfo->rel->pages && ratio < 0.5)
{
    /* Change all page cost from random to sequential */
    ...
}
```

`rel->pages` is the number of pages of the main table, which does not include the TOAST relation.
For out-of-line vectors it is small (3,712 here), so the correction applies from a modest
`ef_search` upward (between 256 and 320 for this table), and below that the index is charged at
random page cost for every page it is expected to visit. In a band of `ef_search` just below the
threshold the index plan then costs more than a sequential scan of the small heap, which the
planner estimates without the TOAST pages it would have to read. Applying the formula in
`hnswcostestimate` to the page counts above predicts the `ef_search` at which the index cost falls
(320) and, for 20 combinations of 100K to 1M rows and 128 to 1024 dimensions, predicts it correctly
in all 20.

**How often:** We recorded the default plan for 5 table sizes (100K to 1M rows) x 4 dimensions
(128, 384, 768, 1024) x 18 values of `ef_search` (16 to 1000), 360 combinations. 9 choose a sequential
scan. All 9 are at 768 or 1024 dimensions (9 of 180); none at 128 or 384 dimensions, where the vectors
are not stored out of line. The affected values form narrow bands that move with the table size, for
example only `ef_search` = 256 at 500K rows and only 512 at 1M rows, both at 1024 dimensions.

**Questions:** Is this the intended behavior of the estimate? Should the comparison with the heap
size account for the TOAST pages? We have not tried a patch. We can share the plan grid and the
script that produced it.

**Workaround we used:** `SET enable_seqscan = off` for the benchmark session, with the plan checked
per `ef_search`.

## Reproducer (NOT RUN)

Self-contained; needs `psycopg`, `numpy` and `pgvector` (Python) and a PostgreSQL with the extension.
Fill in the connection string. The table is created as `items` and dropped first, so use an empty
database.

```python
import numpy as np, psycopg
from pgvector.psycopg import register_vector

N, D, M, EFC = 500_000, 1024, 16, 64
EFS = [128, 160, 192, 224, 256, 320, 384]

with psycopg.connect("dbname=postgres", autocommit=True) as conn:
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    conn.execute("DROP TABLE IF EXISTS items")
    conn.execute(f"CREATE TABLE items (id bigint PRIMARY KEY, embedding vector({D}))")
    rng = np.random.default_rng(0)
    with conn.cursor() as cur, cur.copy("COPY items (id, embedding) FROM STDIN WITH (FORMAT BINARY)") as cp:
        cp.set_types(["int8", "vector"])
        for start in range(0, N, 10_000):
            block = rng.standard_normal((min(10_000, N - start), D)).astype(np.float32)
            block /= np.linalg.norm(block, axis=1, keepdims=True)
            for i, row in enumerate(block):
                cp.write_row((start + i, row))
    conn.execute(f"CREATE INDEX ON items USING hnsw (embedding vector_cosine_ops) WITH (m={M}, ef_construction={EFC})")
    conn.execute("ANALYZE items")
    print(conn.execute("SELECT relpages FROM pg_class WHERE relname = 'items'").fetchone())
    query = "[" + ",".join(f"{x:.7g}" for x in rng.standard_normal(D)) + "]"
    conn.execute("PREPARE bq(vector) AS SELECT id FROM items ORDER BY embedding <=> $1 LIMIT 10")
    conn.execute("SET plan_cache_mode = force_custom_plan")
    for ef in EFS:
        conn.execute(f"SET hnsw.ef_search = {ef}")
        plan = conn.execute(f"EXPLAIN (FORMAT JSON) EXECUTE bq('{query}')").fetchone()[0][0]["Plan"]
        print(ef, plan["Node Type"], plan["Total Cost"])
```

Expected, if it reproduces: a sequential scan at one of the listed `ef_search` values and an index
scan at its neighbors, with the cost of the index plan rising and then dropping. The exact
`ef_search` depends on the page counts, which depend on `N`, `D`, `m` and the PostgreSQL build.
A random unit vector as the query may plan differently from a real embedding; the cost model does
not look at the query value, so this should not matter, and that is also unchecked.
