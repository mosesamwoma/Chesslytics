# Chesslytics

**Stop reviewing games one at a time. Start finding the mistake you keep making.**

Chesslytics ingests your PGN games, evaluates every move with Stockfish, and mines
the results for **recurring** weaknesses — not "you blundered on move 23," but "you hang
pieces in the middlegame under time pressure, four games running." Stockfish tells you what
happened in one game. This tool tells you what keeps happening across all of them.

---

## Why this exists

Engine review tools are great at telling you *that* a move lost 2.3 pawns. They're bad at
telling you *why you keep doing it*. This project treats every evaluated move as a data
point, stores it, and mines the collection for patterns: which categories of mistake recur,
in which phase of the game, under what clock pressure, against which openings. The engine
stays the source of objective truth; the mining layer is what turns raw evaluations into
something you can actually study.

## Features

- **Deep move evaluation** — every move scored by Stockfish, evaluations normalized to the
  mover's perspective, with mate scores handled correctly rather than approximated.
- **Static exchange evaluation (SEE)** — hanging-piece detection based on the actual outcome
  of a full capture sequence, not "attacked by something cheaper."
- **Tactical motif recognition** — mates, forks, pins, and skewers are detected on the
  resulting position, independent of whether the move's notation makes them obvious.
- **Mistake mining** — configurable severity bands (inaccuracy/mistake/blunder), phase
  detection, time-pressure flags, and a fixed-priority category system so nothing is
  double-counted.
- **Pattern & profile mining** — recurring categories, weak openings, tactical
  weaknesses, and evidence-only observations (no invented psychology).
- **AI coaching commentary** — a Groq-backed Coach turns your mined patterns and worst
  mistakes into a plain-English summary, a focus drill for the week, and a short set of
  topic breakdowns, grounded strictly in the evidence already mined (no invented reasons).
- **Multi-engine verification** — re-check every flagged mistake with a second engine
  binary and mark it `agreed` / `disputed`, so you know which findings to trust.
- **Parallel analysis** — an opt-in process pool for analyzing large collections faster,
  with measured (not assumed) speed-up numbers documented below.
- **Opening-book awareness** — Polyglot `.bin` support to mark or exclude mistakes that
  were technically still "in theory."
- **Training mode** — every stored mistake becomes a puzzle: play a move against the
  position, get graded on winning-chance loss, and track accuracy per category over time.
- **Four interfaces, one engine** — CLI, REST API, Postgres-backed persistence, and a
  React/Vite dashboard, all built on the same analysis core.
- **Exports** — JSON, CSV, or JSONL, from both the CLI and the API, for anyone who wants
  to do their own analysis downstream.

## Quick Start

```bash
git clone https://github.com/mosesamwoma/Chesslytics.git
cd Chesslytics

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# install Stockfish for your platform, see below
which stockfish   # confirm the path, then set it in .env

# install Postgres (or run `docker compose up postgres` to use the bundled one)

cp .env.example .env
# set POSTGRES_* to match your Postgres instance, and GROQ_API_KEY if you want
# the Coach feature — everything else works without it

python -m app.main --pgn data/sample_games.pgn --limit-time 0.05
```

## Installation

Requires **Python 3.11+**, a **Stockfish** binary, and a **Postgres** database.

| Platform | Command |
| --- | --- |
| Debian / Ubuntu | `sudo apt install stockfish` (installs to `/usr/games/stockfish`) |
| Fedora | `sudo dnf install stockfish` |
| macOS | `brew install stockfish` |
| Windows | Download from [stockfishchess.org](https://stockfishchess.org/download/) |

The app resolves the binary in this order: `--stockfish` CLI flag → `STOCKFISH_PATH` in
`.env` → `PATH`. If `STOCKFISH_PATH` is set but wrong, it fails with a clear error rather
than silently falling back — run `which stockfish` and confirm before setting it.

Opening books are optional and need no extra install; standard Polyglot `.bin` files
(exportable from most chess GUIs) work out of the box via `--book`.

### Setting up Postgres (Linux)

Install the server and client:

```bash
sudo apt update && sudo apt install -y postgresql
sudo systemctl enable --now postgresql
```

Create the role and database used by `.env` (match the values below to whatever you put
in `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`):

```bash
sudo -u postgres psql -c "CREATE USER \"you-name\" WITH PASSWORD '1234';"
sudo -u postgres psql -c "CREATE DATABASE chesslytics_db OWNER \"you-name\";"
```

Confirm it's reachable before starting the app:

```bash
psql -h 127.0.0.1 -U you-name -d chesslytics_db -c "\dt"
```

An empty table list is fine — the app creates its tables on first run. If that command
fails to connect, check that `sudo systemctl status postgresql` shows it running and that
`POSTGRES_PORT` (`5432` by default) isn't already in use.

Prefer not to install Postgres at all? `docker compose up postgres` creates the same
role/database automatically from the `POSTGRES_*` values in `.env` — skip straight to
[Docker](#docker) below.

Point `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` / `POSTGRES_HOST` /
`POSTGRES_PORT` in `.env` at whichever of the above you used. Leaving `POSTGRES_HOST` as
`auto` resolves to the `postgres` docker-compose service when it's reachable, and falls
back to `localhost` otherwise — useful when running the API outside Docker against a
locally exposed Postgres port. Setting `DATABASE_URL` directly always overrides the
individual `POSTGRES_*` variables.

### Getting a Groq API key (optional, enables Coach)

1. Sign up or log in at [console.groq.com](https://console.groq.com).
2. Open [console.groq.com/keys](https://console.groq.com/keys) → **Create API Key** →
   copy it.
3. Paste it into `GROQ_API_KEY` in `.env`.

`GROQ_MODEL` defaults to `llama-3.3-70b-versatile`. Other current options (see
[console.groq.com/docs/models](https://console.groq.com/docs/models) for the live list):
`llama-3.1-8b-instant` (faster, cheaper, lower quality), `openai/gpt-oss-120b` and
`openai/gpt-oss-20b` (OpenAI's open-weight models, hosted on Groq). Leaving
`GROQ_API_KEY` blank disables `/api/coach` only — every other feature works without it.

## Usage

### CLI

```bash
python -m app.main --pgn games.pgn --player Alice --limit-time 0.1
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--pgn` | `data/games.pgn` | PGN file to analyze |
| `--depth` / `--limit-time` | `12` / — | Search depth, or seconds per move (overrides depth) |
| `--min-loss` | `1.0` | Minimum pawn loss to report — don't go much below 1.0 at depth 12 (engine noise) |
| `--player` / `--color` | — / `both` | Restrict to one player or color |
| `--time-pressure` | `30` | Seconds below which a move is flagged as time-pressured |
| `--workers` | `1` | Parallel engine processes; see [Known Limitations](#known-limitations) |
| `--verify-with` | — | Second engine binary; flags mistakes the two engines disagree on |
| `--book` / `--exclude-book` | — | Polyglot `.bin`; mark, or drop, moves still in theory |
| `--output` / `--output-format` | — | Write results to `.json` / `.csv` / `.jsonl` |
| `--save` | — | Persist games and results to the database |
| `--no-cache` / `--rebuild-cache` | — | Bypass or rebuild the evaluation cache |

`--player` matters more than it looks — without it, your opponents' blunders are mixed in
with yours.

### Web App

Run the backend and frontend in two terminals:

```bash
uvicorn app.main:app --reload              # http://127.0.0.1:8000
cd frontend && npm install && npm run dev  # http://127.0.0.1:5173
```

Six pages: **Dashboard** (aggregate stats), **Games** (upload/manage), **Game Analysis**
(win-probability chart + step-through board), **Training** (puzzle drills), **Chess DNA**
(your mistake profile), and **Coach** (AI coaching commentary generated from your profile,
with a Regenerate button).

For a single-server deployment, build the frontend (`npm run build`) and point
`FRONTEND_DIST` at `frontend/dist` — FastAPI will serve it directly, no separate dev server
needed.

### Docker

```bash
docker compose up --build
```

Backend on `:8000`, frontend on `:8080` via nginx, Postgres on its default port with data
persisted in a named volume. `./data` is mounted so uploads and the evaluation cache
survive rebuilds. The backend waits for Postgres to report healthy before starting.

### Training Mode

Every stored mistake becomes a puzzle: you're shown the position before the mistake, you
play a move, and it's graded against the engine on **winning-chance loss**, not raw
centipawns (dropping 2 pawns at +0.5 loses the game; the same 2 pawns at +9.0 changes
nothing). A move matching the stored best move is graded instantly with zero engine calls;
anything else costs one engine call. Every attempt persists, and accuracy is tracked
per category so "what should I study" has a real answer.

### Coach

`GET /api/coach` builds a JSON snapshot of your latest profile — recurring categories,
tactical weaknesses, phase and opening breakdowns, time-pressure share, and your worst
individual mistakes — and sends it to Groq, which returns a short coaching summary, one
concrete focus drill, and a handful of topic sections. The result is cached per profile so
repeat visits don't re-call the model; pass `?refresh=true` (or press Regenerate in the UI)
to force a new pass. Requires `GROQ_API_KEY`; without it the endpoint returns a clear 503
rather than failing silently, and every other feature keeps working normally.

### REST API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/games/upload` | Upload a PGN (deduplicated by fingerprint) |
| `GET` / `DELETE` | `/api/games/{id}` | Fetch or remove one game |
| `POST` | `/api/analysis/run` | Analyze stored games (`workers`, `verify_with`, `book`, thresholds) |
| `POST` | `/api/analysis/export` | Download mistakes as json/csv/jsonl |
| `GET` | `/api/patterns/overview` | Aggregate stats across everything stored |
| `GET` | `/api/patterns/profile` | Latest player profile |
| `GET` | `/api/coach` | AI coaching commentary for the latest profile (`player`, `refresh`) |
| `GET` | `/api/training/puzzles` | Puzzles from stored mistakes (solution withheld) |
| `POST` | `/api/training/puzzles/{id}/attempt` | Grade a move, persist the attempt |
| `GET` | `/api/training/stats` | Attempts, solves, and accuracy per category |

Full interactive docs at `/docs` while the server is running.

## Configuration

Copy `.env.example` to `.env`. Everything except the Postgres connection has a safe
default — nothing else is required to run the sample data.

| Variable | Default | Meaning |
| --- | --- | --- |
| `STOCKFISH_PATH` | auto-detected | Stockfish binary path |
| `STOCKFISH_DEPTH` / `STOCKFISH_TIME` | `12` / — | Default search limit |
| `POSTGRES_USER` | `you-name` | Postgres role used to connect |
| `POSTGRES_PASSWORD` | `1234` | Password for `POSTGRES_USER` |
| `POSTGRES_DB` | `chesslytics_db` | Database name |
| `POSTGRES_HOST` | `auto` | `auto` tries the `postgres` docker-compose host, then falls back to `localhost` |
| `POSTGRES_PORT` | `5432` | Postgres port |
| `DATABASE_URL` | — | Full SQLAlchemy URL; overrides every `POSTGRES_*` variable above when set |
| `GROQ_API_KEY` | — | Enables `/api/coach`; leave blank to disable it |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq chat model used for coaching commentary |
| `UPLOAD_DIR` / `ANALYSIS_DIR` | `data/uploads` / `data/analysis` | Storage locations |
| `ANALYSIS_CACHE` / `VERIFY_CACHE` | derived from `ANALYSIS_DIR` | Explicit cache paths |
| `PARALLEL_WORKERS` | `1` | Default for `--workers` |
| `VERIFY_WITH` | — | Default for `--verify-with` |
| `BOOK_PATH` | — | Default for `--book` |
| `PUZZLE_TOLERANCE` | `5.0` | Win% a training answer may give up and still count as correct |
| `CORS_ORIGINS` | `http://127.0.0.1:5173` | Allowed browser origins (comma-separated for more than one) |
| `FRONTEND_DIST` | `frontend/dist` | Built SPA served at `/` when present |

## Known Limitations

- SEE and motif detection are heuristics, not a full tactics solver — a few plies deep, not
  a search engine in miniature.
- `--min-loss` below ~1.0 pawn at depth 12 mixes real mistakes with engine search noise;
  raise `--depth` before lowering the threshold.
- Time-pressure stats require clock annotations in the PGN (present on Chess.com exports,
  often absent elsewhere).
- Sequential analysis carries Stockfish's transposition table across games in the same run,
  so results can shift slightly if games are added or reordered. `--workers 2+` isolates
  each game and avoids this.
- `--verify-with` is a second noisy opinion, not ground truth — treat `disputed` as "check
  this one yourself," not "this is wrong."
- Opening-book coverage is only as good as the book you point it at; `in_book` means "a book
  had a move here," not "this move was good."
- Coach commentary is only as good as the evidence behind it — a thin profile (few games,
  few mistakes) produces thin, generic-sounding sections. It's a summary layer over the
  mined data, not a substitute for it.

## Privacy

Your PGNs are personal data. `data/games.pgn` is gitignored by default — keep it that way
unless you're fine with your games being public. Everything runs locally except the Coach
feature, which sends the mined pattern/profile summary (not raw PGNs or board positions) to
Groq's API when `GROQ_API_KEY` is set. Leave it blank to keep Chesslytics fully local.