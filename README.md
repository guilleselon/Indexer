# Indexer — Web3 Event Indexer (MVP)

A Web3 event indexer built from scratch to learn how data pipelines work on Ethereum. It indexes Uniswap V3 swaps from three high-volume pools, stores raw logs as the source of truth, and exposes the processed data through a REST API. It also includes a lightweight gas monitor.

> **⚠️ This is an MVP, not a production product.**
>
> It works. It has been tested against Ethereum mainnet with real data, and it handles edge cases like chain reorganizations, rate limits, and reprocessing.
>
> But it was built as a learning project, not a product. If you find it useful, **use the parts that work to build something better** rather than deploying this as-is. See [What I would do differently](#what-i-would-do-differently) for the honest list of gaps.

---

## Table of contents

- [What it does](#what-it-does)
- [What it does not do](#what-it-does-not-do)
- [Architecture](#architecture)
- [Key design decisions](#key-design-decisions)
- [Tech stack](#tech-stack)
- [Setup](#setup)
- [Usage](#usage)
- [API endpoints](#api-endpoints)
- [Gas monitor](#gas-monitor)
- [What I would do differently](#what-i-would-do-differently)
- [Why I built this](#why-i-built-this)

---

## What it does

- **Indexes Uniswap V3 swaps** from 3 pools on Ethereum mainnet:
  - USDC/WETH 0.05%
  - WBTC/WETH 0.3%
  - USDC/USDT 0.01%
- **Stores raw logs** from `eth_getLogs` as an immutable source of truth.
- **Processes events** into a normalized domain table (`uniswap_v3_swaps`) with decoded prices.
- **Handles chain reorganizations** by detecting hash mismatches and rolling back affected blocks.
- **Supports resumable backfill** — process historical ranges without blocking the live tail.
- **Reprocesses** raw logs into domain tables without touching the RPC (useful when a handler is fixed or extended).
- **Exposes a REST API** (FastAPI) with Swagger docs at `/docs`.
- **Monitors gas** in real time using `eth_feeHistory`, with an in-memory store and cost estimates per operation.
- **Ships with an operational dashboard** (FastHTML) — not included in this repo by default, but the pattern is documented.

---

## What it does not do

This is important. An honest list:

- **It only indexes Uniswap V3 swaps.** No other events (`Mint`, `Burn`, `Collect`), no other protocols, no other chains.
- **It runs on SQLite.** Fine for a single writer, not for production concurrency. Postgres would be needed for real workloads.
- **There are no tests.** It has been verified manually with smoke tests and real data, but there is no `pytest` suite.
- **No authentication on the API.** It's designed for `localhost`, not for the public internet.
- **No Docker or deployment config.** No `Dockerfile`, no `docker-compose.yml`, no cloud setup.
- **Gas history is in memory only.** It's lost on restart and rebuilt with one `eth_feeHistory` call.
- **No Alembic migrations.** Schema changes require deleting `indexer.db` and re-running `db-init`.

If you need any of the above, build it. The architecture is designed to make that possible without rewriting the core.

---

## Architecture
┌──────────────────────────────────────────────────────────────┐
│ Core (generic) │
│ │
│ RPCClient → Decoder → Ingester → Repositories → DB │
│ │ │ │
│ │ └── reorg detection │
│ │ └── checkpoint per adapter │
│ └── ABI-driven event decoding │
└──────────────────────────────────────────────────────────────┘
▲
│ implements
┌──────────────────────────────────────────────────────────────┐
│ Adapters (plug-in) │
│ │
│ BaseAdapter → UniswapV3Adapter (swaps + volume + prices) │
│ → EchoAdapter (fixture for testing) │
└──────────────────────────────────────────────────────────────┘
│
▼
┌──────────────────────────────────────────────────────────────┐
│ API layer (FastAPI) │
│ │
│ /status /blocks /raw-logs /uniswap/* /gas/* /health │
└──────────────────────────────────────────────────────────────┘
│
▼
┌──────────────────────────────────────────────────────────────┐
│ Gas module (isolated) │
│ │
│ eth_feeHistory → GasStore (in memory) → /gas/current │
└──────────────────────────────────────────────────────────────┘

text

**Adding a new adapter** requires:
1. A new folder under `indexer/adapters/` with `models.py`, `handlers.py`, `adapter.py`, `abi.py`.
2. Two lines in `indexer/adapters/registry.py`.

No changes to the core, the ingester, the decoder, or the API. This is what the architecture is designed for.

---

## Key design decisions

These are the choices that made the project work, and the ones I would keep in any successor.

### 1. Raw logs are the source of truth

Every log returned by `eth_getLogs` is stored in `raw_logs` exactly as it came. It is never modified. Domain tables (`uniswap_v3_swaps`) are derived from it.

**Why it matters:** if the handler has a bug, or a new field is needed, or the price formula was wrong, you fix the handler and run:

```bash
python run.py reprocess --adapter uniswap_v3 --from-block X --to-block Y --clean
No RPC calls. No re-downloading. No wasted Infura quota. The raw_logs table is the safety net.

2. Idempotency by (block_number, log_index)
Every domain table has a UniqueConstraint on (chain_id, block_number, log_index). Reprocessing the same block twice does not duplicate rows.

3. Reorg detection and rollback
Before each ingest iteration, the ingester compares stored block hashes with current RPC hashes. If they diverge, it rolls back the affected range and re-indexes it. Reorgs are not an edge case — they happen, and ignoring them corrupts the data.

4. Checkpoints per adapter
Each adapter (and each mode: tail, backfill, backward) has its own row in the checkpoints table. This allows the tail to keep running while a backfill fills a historical gap, without them stepping on each other.

5. Batch RPC calls with retries
blocks_batch sends up to 10 eth_getBlockByNumber calls in one JSON-RPC batch. If Infura returns -32005 (rate limit) for some items, only those items are retried with exponential backoff. This makes backfill viable on free-tier RPC.

6. Gas module is completely isolated
The gas monitor uses eth_feeHistory (one call returns 1024 blocks of base fees and priority fees). It stores snapshots in memory (a deque of 2048 items), not in SQLite.

Why: it can run in the same process as the API without touching the DB. It doesn't block the tail. It's lost on restart but rebuilt in one call.

Tech stack
Layer	Choice	Why
RPC client	web3.py + httpx for batching	Stable, well-documented
Database	SQLite with WAL mode	Zero setup, single-writer for this workload
ORM	SQLAlchemy 2.0	Typed models, create_all for MVP
API	FastAPI	Auto-generated OpenAPI docs
Config	pydantic-settings	Typed, validated .env
CLI	typer	Subcommands with help
Retries	tenacity	Exponential backoff
Gas	eth_feeHistory	One call, 1024 blocks
Dashboard	FastHTML + Tailwind + HTMX	Server-rendered, no build step
Setup
Requirements
Python 3.11+

An Ethereum RPC endpoint (Infura free tier is enough for the tail; Alchemy is recommended for backfill)

Installation
bash
git clone <this-repo>
cd indexer
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
Configuration
Copy the example environment file and fill in your RPC URL:

bash
cp .env.example .env
Edit .env:

env
RPC_URL=https://mainnet.infura.io/v3/YOUR_KEY
CHAIN_ID=1
START_BLOCK=17000000
CONFIRMATIONS=12
MAX_BLOCK_RANGE=2000
LOG_LEVEL=INFO
Then create the database:

bash
python run.py db-init
This creates indexer.db with all tables: 4 core tables (blocks, raw_logs, checkpoints, reorg_events) plus the adapter-specific table (uniswap_v3_swaps).

Usage
All commands are run from the project root. The CLI entry point is run.py.

Check the connection
bash
python run.py rpc-check
Index in real time
bash
python run.py run --adapter uniswap_v3 --tail
This processes new blocks as they are confirmed. Leave it running in a terminal (or in tmux).

If your checkpoint is far behind the head (e.g., the indexer was off for days), you have two options:

bash
# Option A: skip the backlog and index from now
python run.py run --adapter uniswap_v3 --tail --skip-backlog

# Option B: leave it running — it will catch up slowly
python run.py run --adapter uniswap_v3 --tail
Fill historical gaps
bash
# Automatic: scans DB backwards, fills holes, stops at contract creation
python run.py backfill --adapter uniswap_v3

# Manual range
python run.py backfill --adapter uniswap_v3 --from-block 25000000 --to-block 25001000
Reprocess domain tables from raw logs
bash
python run.py reprocess --adapter uniswap_v3 --from-block 25000000 --to-block 25001000
No RPC calls. Useful after fixing a handler.

Start the API
bash
python run.py serve
Swagger UI: http://127.0.0.1:8000/docs

Health: http://127.0.0.1:8000/health

The API also starts the gas collector in the background.

API endpoints
Core (generic)
Method	Path	Description
GET	/health	Liveness probe
GET	/ready	Readiness probe (checks DB)
GET	/status	Checkpoints, lag, recent reorgs
GET	/blocks?from=X&to=Y&limit=N&offset=N	Processed blocks
GET	/raw-logs?address=X&topic0=Y&from=X&to=Y	Raw logs
Uniswap V3
Method	Path	Description
GET	/uniswap/pools	Configured pools
GET	/uniswap/swaps?pool=X&from_block=Y&to_block=Z	Swaps with filters
GET	/uniswap/pools/{address}/stats	Aggregated stats per pool
GET	/uniswap/pools/{address}/volume?window=24h	Volume in a time window
GET	/uniswap/pools/{address}/price-history?interval=hour	Time series of price
Gas
Method	Path	Description
GET	/gas/current	Current gas prices (slow/standard/fast) + cost estimates
GET	/gas/history?blocks=1800	Time series of base fees
GET	/gas/status	Collector state
The /gas/current endpoint returns cost estimates in ETH and, if the indexer has any WETH/USDC swaps, also in USD. It uses the indexer's own data as the price source, so it does not depend on external APIs.

Gas monitor
The gas module is completely isolated from the event indexer. It lives in indexer/gas/ and:

Uses eth_feeHistory(block_count=1024, ...) — one call returns ~3.4 hours of history.

Keeps snapshots in a thread-safe deque(maxlen=2048) — about 160 KB of RAM.

Never touches the SQLite database.

Never blocks the tail or the backfill.

Rebuilds its history on startup with a single RPC call.

This is why it can run in the same process as the API without causing write contention.

What I would do differently
An honest list of what I would change before turning this into a real product:

1. Add tests
There is no pytest suite. It should have unit tests for compute_prices, reorg.detect, reprocess, and integration tests with a mocked RPC. Without tests, every change is verified manually.

2. Migrate to PostgreSQL
SQLite with WAL is fine for a single writer, but:

Tail + backfill cannot run concurrently (one writer at a time).

Aggregations (AVG, GROUP BY over millions of rows) are slow.

No uint256 arithmetic in SQL — currently done in Python.

PostgreSQL fixes all three. The change is one variable in .env plus installing psycopg. The code does not change.

3. Add Alembic migrations
Currently, changing a schema requires deleting indexer.db. Alembic would let you evolve the schema without data loss.

4. Add authentication to the API
The API is designed for localhost. It has no auth, no rate limiting, no CORS. Before exposing it publicly, add:

API key or JWT auth.

Rate limiting per IP.

CORS configured for specific origins.

5. Move the gas store to Redis (or keep it in memory with better eviction)
The in-memory store is lost on restart. For a real product, Redis with a TTL gives you persistence without the SQLite write contention.

6. Add a proper dashboard
The current dashboard (FastHTML) is a working MVP but it reads from the DB and the API with no caching and no auth. For a real product, a proper frontend (React, SvelteKit) with a dedicated read replica would be better.

7. Add more adapters
The architecture is designed for this. Adding an adapter for Aave, Seaport, or another DEX requires ~5 files and 2 lines in the registry. The Uniswap V3 adapter is the reference implementation.

8. Fix the --skip-backlog behavior
Currently --skip-backlog requires --tail to be passed. It should work independently. This is a small bug in the CLI.

9. Externalize ABI files
Currently ABIs are inline Python dicts. Moving them to .json files in each adapter's folder would make it easier to add events without touching code.

10. Deploy it
The current project has no Dockerfile, no docker-compose.yml, and no cloud config. A real deployment would need:

Docker image.

PostgreSQL instance.

Environment variables via secrets.

A reverse proxy (Caddy, Nginx) for TLS and caching.

Healthchecks and auto-restart.

Why I built this
I wanted to understand how The Graph, Ponder, and similar tools work from the inside. Not just use them, but build the pipeline:

How do you ingest blocks without missing any or duplicating them?

How do you handle a reorg without corrupting your data?

How do you reprocess a range without re-hitting the RPC?

How do you extend an indexer to a new protocol without rewriting the core?

Building it from scratch answered those questions. The result is a working MVP with real data from Ethereum mainnet, a clean adapter contract, and a gas module that demonstrates a different ingestion pattern (eth_feeHistory vs eth_getLogs).

This is not a product. It is a learning exercise that happens to work. If you find it useful, take the design decisions (raw logs, adapter contract, per-adapter checkpoints) and build something better on top of them.

License
MIT. Do whatever you want with it.
