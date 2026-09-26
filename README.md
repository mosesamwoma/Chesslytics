# Chess Mistakes Miner

Reads your PGN games, evaluates every move with Stockfish, and mines the results for
**recurring** mistakes — not "you blundered on move 23" but "you blunder like this in the
middlegame, under time pressure, four games running."

Ships as: a **CLI**, a **REST API** (FastAPI + SQLite), a **web app** (React/Vite), and a
**training mode** that turns stored mistakes back into puzzles you play against the engine.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
sudo apt install stockfish        # Debian/Ubuntu puts it at /usr/games/stockfish — check with `which stockfish`
cp .env.example .env              # edit STOCKFISH_PATH if needed

python -m app.main --pgn data/sample_games.pgn --limit-time 0.05
```

## Features (roadmap)

- **V1** — PGN → Stockfish eval → mistake detection → pattern mining → CLI/API/DB/dashboard
- **V2** — Static exchange evaluation (accurate hanging-piece detection), tactical motifs
  (mates/forks/pins/skewers), JSON/CSV/JSONL exports
- **V3** — Training mode: puzzles from your own mistakes, engine-graded, attempts persisted,
  per-category accuracy
- **V4** — Multi-engine verification (`agreed`/`disputed`), opt-in parallel analysis
  (`--workers`), Polyglot opening-book awareness (`--book`, `--exclude-book`)

## CLI

```bash
python -m app.main --pgn games.pgn --player Alice --limit-time 0.1
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--pgn` | `data/games.pgn` | PGN file to read |
| `--depth` / `--limit-time` | `12` / — | Search depth, or seconds per move (overrides depth) |
| `--min-loss` | `1.0` | Minimum pawn loss to report (don't set below ~1.0 at depth 12 — engine noise) |
| `--player` / `--color` | — / `both` | Only this player's / this color's moves |
| `--workers` | `1` | Parallel engine processes — mostly a wash below ~4 physical cores |
| `--verify-with` | — | Second engine binary; flags mistakes the two engines disagree on |
| `--book` / `--exclude-book` | — | Polyglot `.bin`; mark or drop moves still in theory |
| `--output` / `--output-format` | — | Write mistakes to `.json`/`.csv`/`.jsonl` |
| `--save` | — | Persist games + results to the database |

## Web app

```bash
uvicorn app.main:app --reload             # http://127.0.0.1:8000
cd frontend && npm install && npm run dev # http://127.0.0.1:5173
```

Pages: Dashboard, Games, Game Analysis (board + eval chart), Training, Chess DNA (profile).

## API (highlights)

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/games/upload` | Upload a PGN (deduplicated by fingerprint) |
| `POST` | `/api/analysis/run` | Analyze stored games — accepts `workers`, `verify_with`, `book` |
| `POST` | `/api/analysis/export` | Download mistakes as json/csv/jsonl |
| `GET` | `/api/training/puzzles` | Puzzles from stored mistakes (solution withheld) |
| `POST` | `/api/training/puzzles/{id}/attempt` | Grade a move, store the attempt |
| `GET` | `/api/patterns/overview` | Aggregate stats across everything stored |

Full interactive docs at `/docs` while the server runs.

## Configuration

Copy `.env.example` to `.env`. Nothing is required — every variable has a safe default. The
one worth double-checking is `STOCKFISH_PATH`: if set, it's used as-is and the app will error
rather than fall back to searching `PATH`, so make sure it actually points at your binary
(`which stockfish`).

| Variable | Default | Meaning |
| --- | --- | --- |
| `STOCKFISH_PATH` | auto-detected | Stockfish binary path |
| `STOCKFISH_DEPTH` / `STOCKFISH_TIME` | `12` / — | Default search limit |
| `DATABASE_URL` | `sqlite:///./data/chess_mistakes.db` | SQLAlchemy URL |
| `UPLOAD_DIR` / `ANALYSIS_DIR` | `data/uploads` / `data/analysis` | Storage locations |
| `ANALYSIS_CACHE` / `VERIFY_CACHE` | `<ANALYSIS_DIR>/eval_cache.json` / `verify_cache.json` | Cache overrides |
| `PARALLEL_WORKERS` | `1` | Default for `--workers` |
| `VERIFY_WITH` | — | Default for `--verify-with` |
| `BOOK_PATH` | — | Default for `--book` |
| `PUZZLE_TOLERANCE` | `5.0` | Win% a training answer may give up and still count correct |
| `CORS_ORIGINS` | localhost:5173 | Allowed origins |
| `FRONTEND_DIST` | `frontend/dist` | Built SPA mounted at `/` when present |

## Known limitations

- SEE and motif detection are heuristics, not a tactics solver — a few plies deep, not a full search.
- `--min-loss` below ~1.0 at depth 12 mixes real mistakes with engine noise; raise `--depth` first.
- Time-pressure stats need clock annotations in the PGN (Chess.com has them; many sources don't).
- Sequential analysis carries Stockfish's transposition table across games in the same run, so
  results can shift slightly if you add/reorder games in the PGN. `--workers 2+` isolates each
  game and doesn't have this property — use it if you want numbers that never move.
- `--verify-with` is a second noisy opinion, not a ground truth — treat "disputed" as "check
  this one yourself," not "this is wrong."
- Opening-book coverage is only as good as the book you point at.

## Privacy

Your PGNs are personal data. `data/games.pgn` is gitignored by default. Everything runs locally.
