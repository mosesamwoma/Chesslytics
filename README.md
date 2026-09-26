# Chess Mistakes Miner

**Stop reviewing games one at a time. Start finding the mistake you keep making.**

Chess Mistakes Miner ingests your PGN games, evaluates every move with Stockfish, and mines
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
- **Multi-engine verification** — re-check every flagged mistake with a second engine
  binary and mark it `agreed` / `disputed`, so you know which findings to trust.
- **Parallel analysis** — an opt-in process pool for analyzing large collections faster,
  with measured (not assumed) speed-up numbers documented below.
- **Opening-book awareness** — Polyglot `.bin` support to mark or exclude mistakes that
  were technically still "in theory."
- **Training mode** — every stored mistake becomes a puzzle: play a move against the
  position, get graded on winning-chance loss, and track accuracy per category over time.
- **Four interfaces, one engine** — CLI, REST API, SQLite-backed persistence, and a
  React/Vite dashboard, all built on the same analysis core.
- **Exports** — JSON, CSV, or JSONL, from both the CLI and the API, for anyone who wants
  to do their own analysis downstream.

## Quick Start

```bash
git clone https://github.com/mosesamwoma/chess-mistakes-miner.git
cd chess-mistakes-miner

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# install Stockfish for your platform, see below
which stockfish   # confirm the path, then set it in .env

cp .env.example .env

python -m app.main --pgn data/sample_games.pgn --limit-time 0.05
```

## Installation

Requires **Python 3.11+** and a **Stockfish** binary.

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

Five pages: **Dashboard** (aggregate stats), **Games** (upload/manage), **Game Analysis**
(win-probability chart + step-through board), **Training** (puzzle drills), **Chess DNA**
(your mistake profile).

For a single-server deployment, build the frontend (`npm run build`) and point
`FRONTEND_DIST` at `frontend/dist` — FastAPI will serve it directly, no separate dev server
needed.

### Docker

```bash
docker compose up --build
```

Backend on `:8000`, frontend on `:8080` via nginx. `./data` is mounted so the database,
uploads, and cache survive rebuilds.

### Training Mode

Every stored mistake becomes a puzzle: you're shown the position before the mistake, you
play a move, and it's graded against the engine on **winning-chance loss**, not raw
centipawns (dropping 2 pawns at +0.5 loses the game; the same 2 pawns at +9.0 changes
nothing). A move matching the stored best move is graded instantly with zero engine calls;
anything else costs one engine call. Every attempt persists, and accuracy is tracked
per category so "what should I study" has a real answer.

### REST API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/games/upload` | Upload a PGN (deduplicated by fingerprint) |
| `GET` / `DELETE` | `/api/games/{id}` | Fetch or remove one game |
| `POST` | `/api/analysis/run` | Analyze stored games (`workers`, `verify_with`, `book`, thresholds) |
| `POST` | `/api/analysis/export` | Download mistakes as json/csv/jsonl |
| `GET` | `/api/patterns/overview` | Aggregate stats across everything stored |
| `GET` | `/api/patterns/profile` | Latest player profile |
| `GET` | `/api/training/puzzles` | Puzzles from stored mistakes (solution withheld) |
| `POST` | `/api/training/puzzles/{id}/attempt` | Grade a move, persist the attempt |
| `GET` | `/api/training/stats` | Attempts, solves, and accuracy per category |

Full interactive docs at `/docs` while the server is running.

## Configuration

Copy `.env.example` to `.env`. Every variable has a safe default — nothing is required to
run the sample data.

| Variable | Default | Meaning |
| --- | --- | --- |
| `STOCKFISH_PATH` | auto-detected | Stockfish binary path |
| `STOCKFISH_DEPTH` / `STOCKFISH_TIME` | `12` / — | Default search limit |
| `DATABASE_URL` | `sqlite:///./data/chess_mistakes.db` | SQLAlchemy URL |
| `UPLOAD_DIR` / `ANALYSIS_DIR` | `data/uploads` / `data/analysis` | Storage locations |
| `ANALYSIS_CACHE` / `VERIFY_CACHE` | derived from `ANALYSIS_DIR` | Explicit cache paths |
| `PARALLEL_WORKERS` | `1` | Default for `--workers` |
| `VERIFY_WITH` | — | Default for `--verify-with` |
| `BOOK_PATH` | — | Default for `--book` |
| `PUZZLE_TOLERANCE` | `5.0` | Win% a training answer may give up and still count as correct |
| `CORS_ORIGINS` | `localhost:5173` | Allowed browser origins |
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

## Privacy

Your PGNs are personal data. `data/games.pgn` is gitignored by default — keep it that way
unless you're fine with your games being public. Everything runs locally; nothing is
uploaded anywhere.