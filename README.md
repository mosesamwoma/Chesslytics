# Chess Mistakes Miner

Chess Mistakes Miner reads a collection of your completed chess games, evaluates every move with
Stockfish, and then answers a question a normal game review cannot: **what mistakes do I keep making,
and in what situations?** Stockfish can already tell you that you blundered on move 23. It cannot tell
you that you have now blundered on move 23 in four different games, all of them in the middlegame, all
of them with under thirty seconds on the clock. Turning many engine evaluations into a personal mistake
dataset — and mining that dataset for recurring patterns — is the whole point of this project.

It ships as three things over one engine:

- a **CLI** that goes straight from a PGN file to a terminal report,
- a **REST API** (FastAPI) with a SQLite store of games, moves, mistakes and profiles,
- a **web app** (React + Vite) that charts a single game and turns the whole collection into a profile.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
sudo dnf install stockfish                     # Fedora; apt/brew on other systems

python -m app.main --pgn data/sample_games.pgn --limit-time 0.05
```

## Architecture

```
                      ┌──────────────────────────────────────────────┐
   PGN file ─────────▶│ app/chess/                                   │
   (CLI, upload)      │   pgn_parser → engine → evaluator → features │
                      │                      ↘ see / motifs         │
                      └───────────────────┬──────────────────────────┘
                                          │ per-move evaluations (JSON cache)
                                          ▼
                      ┌──────────────────────────────────────────────┐
                      │ app/mining/                                  │
                      │   mistake_detector → pattern_miner → profiler│
                      └───────────────────┬──────────────────────────┘
                                          │ mistakes, patterns, profile
                                          ▼
       ┌──────────────────────┬───────────────────────┬───────────────────────┐
       │ app/database/        │ app/api/              │ app/main.py           │
       │  SQLAlchemy + SQLite │  FastAPI routers      │  CLI + report         │
       └──────────────────────┴───────────┬───────────┴───────────────────────┘
                                          │ JSON over /api
                                          ▼
                                  frontend/  (React + Vite)
```

The split matters. Engine analysis is slow and is cached; mining is instant and can be re-run with
different thresholds for free. The database makes results queryable; the frontend makes them visible.

```
app/
  chess/          PGN parsing, Stockfish access, evaluation, board facts
  mining/         mistake records, pattern aggregation, profiling
  database/       engine/session plumbing and ORM models
  services/       the operations the API and the CLI both call
  api/            thin FastAPI routers — request in, service call, response out
  main.py         FastAPI app, plus the CLI entry point
frontend/         React SPA (services / hooks / components / pages)
data/             uploads, analysis cache, SQLite database, sample PGN
```

| Module | Responsibility |
| --- | --- |
| `app/chess/pgn_parser.py` | Read PGN text or files, fingerprint games, flatten headers, read clocks |
| `app/chess/engine.py` | Find the Stockfish binary, wrap UCI, describe a search limit |
| `app/chess/evaluator.py` | Evaluate before/after each move, normalise perspective, build move records |
| `app/chess/features.py` | Board facts: material, phase, hanging pieces, king safety, move flags |
| `app/chess/pieces.py` | Piece names and values — the tables `features`, `see` and `motifs` all share |
| `app/chess/see.py` | Static exchange evaluation: what a capture actually wins |
| `app/chess/motifs.py` | Tactical motifs: mates, forks, pins and skewers a position offers |
| `app/mining/mistake_detector.py` | Thresholds, severity bands, categories, per-move mistake records |
| `app/mining/pattern_miner.py` | Aggregate records into counts, and decide what counts as recurring |
| `app/mining/profiler.py` | The profile and its evidence-only observations |
| `app/database/models.py` | `Game`, `Move`, `Mistake`, `PlayerProfile`, `Pattern` |
| `app/services/game_service.py` | Uploads, storage, queries, JSON shapes for games |
| `app/services/analysis_service.py` | The engine pass, the cache, mining, persistence |
| `app/services/export_service.py` | Mistake records as JSON, CSV or JSONL, for the CLI and the API |
| `app/api/*.py` | `/api/games`, `/api/analysis`, `/api/patterns` |
| `app/main.py` | FastAPI app (lifespan, CORS, static frontend) and the CLI |

## Installation

Requires **Python 3.11+** and **Stockfish**.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Stockfish is an executable engine, not a Python package:

```bash
sudo dnf install stockfish         # Fedora
sudo apt install stockfish         # Debian / Ubuntu
brew install stockfish             # macOS
```

The tool finds Stockfish on `PATH`, then at `/usr/bin`, `/usr/local/bin` and `/usr/games`, then via
`STOCKFISH_PATH` in `.env`, then via `--stockfish`. If it cannot be found you get an actionable error
rather than a traceback.

## Getting your games

Chess.com → **Games** → select the games you want → **Share & Export** → **Download PGN**.

Save the file as `data/games.pgn` (the CLI default), or upload it in the web app. More games make the
patterns more meaningful: two to five is enough to check the pipeline works, fifty is enough to start
seeing yourself, a few hundred is where this gets genuinely interesting. A synthetic
`data/sample_games.pgn` ships with the project so you can try it immediately.

## CLI

```bash
python -m app.main --pgn data/sample_games.pgn --player Alice
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--pgn` | `data/games.pgn` | PGN file to read |
| `--depth` | `12` | Engine search depth per position |
| `--limit-time` | — | Seconds per position; overrides `--depth`, much faster on big collections |
| `--min-loss` | `1.0` | Minimum loss in pawns to report |
| `--player` | — | Only report this player's mistakes (matched against PGN headers) |
| `--color` | `both` | Restrict to `white` or `black` |
| `--time-pressure` | `30` | Seconds below which a move counts as time-pressured |
| `--cache` | `$ANALYSIS_CACHE`, else `<ANALYSIS_DIR>/eval_cache.json` | Where the evaluation cache lives |
| `--output` | — | Write the mistake records to a file; the format follows the extension |
| `--output-format` | from the extension | Force `json`, `csv` or `jsonl` regardless of the filename |
| `--no-cache` / `--rebuild-cache` | — | Ignore, or discard and rebuild, the cache |
| `--include-decided` | — | Also count mistakes made in already-decided positions |
| `--save` | — | Also store games and results in the database |
| `--stockfish` / `--quiet` | — | Binary path / silence progress output |

`--player` matters more than it looks. Without it you get your opponent's blunders mixed in with yours,
which is exactly the data you don't want.

### Exports

`--output` writes the mistake records, not the whole report, in the format the extension implies:
`.csv` gives one flat row per mistake with a fixed 28-column header (`motifs_allowed` and the hung
piece's square and SEE value among them), `.jsonl` gives the same rows as newline-delimited objects,
and `.json` gives the entire report including patterns, profile and observations. `--output-format`
overrides the extension when the name is something else.

```bash
python -m app.main --output mistakes.csv            # spreadsheet-ready
python -m app.main --output report.jsonl            # one object per line, for jq or a loader
python -m app.main --output out.dat --output-format csv
```

The same three formats are available over HTTP from `POST /api/analysis/export`.

### Example output

```
Chess Mistakes Miner
====================

Engine: Stockfish 18  |  search: depth 12
Games analyzed: 87
Moves evaluated: 6842
Mistakes found: 142 (loss >= 1.0 pawns)

Recurring patterns
------------------
1. Time-pressure mistakes          31  (18 games)
2. Missed captures                 27  (21 games)
3. Hanging pieces                  22  (17 games)
4. Opening mistakes                19  (15 games)

Most common mistake phase: middlegame
By severity: blunder 38, mistake 61, inaccuracy 43

Tactics handed to the opponent
------------------------------
  Pin allowed                18  (14 games)
  Fork allowed               11  (9 games)
  Mate allowed                6  (5 games)

Largest single evaluation loss
------------------------------
  Game 42, move 27 (white)
  Played: Qe2
  Best:   Bxh7+
  Loss:   3.10 pawns (+0.80 -> -2.30)
  Why:    this move left the queen on e2 en prise, worth 3 pawns by static exchange

Profile
-------
  Average loss per mistake: 1.84 pawns
  Time pressure: 31 mistakes (22%) below 30.0s
  Tactical weaknesses: Missed captures 27, Hanging pieces 22

Observations
------------
  - 31 mistakes (22%) were played with under 30s remaining. Clock annotations were
    present in 87 of 87 games, so this describes only those.
```

## Web app

Backend and frontend run separately in development:

```bash
uvicorn app.main:app --reload            # http://127.0.0.1:8000
cd frontend && npm install && npm run dev  # http://127.0.0.1:5173
```

Vite proxies `/api` to the backend, so no CORS setup is needed in development. Four pages:

- **Dashboard** — totals, mistake types, phases, severity, openings with the most mistakes.
- **Games** — upload a PGN, analyze everything stored, page through games, delete.
- **Game analysis** — win-probability chart for the whole game, a board you can step through
  move by move, and the mistake cards for that game.
- **Chess DNA** — the profile: time-pressure share, tactical weaknesses, phase and severity
  breakdowns, openings you lose ground in, and the evidence-only observations.

### Docker

```bash
docker compose up --build
```

Backend on `http://localhost:8000`, frontend on `http://localhost:8080` with nginx proxying `/api`.
The image installs Stockfish from the distribution packages; `./data` is mounted at `/data`, so the
database, uploads and cache survive rebuilds.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness |
| `POST` | `/api/games/upload` | Upload a PGN; deduplicates by fingerprint |
| `GET` | `/api/games` | List stored games (`limit`, `offset`) |
| `GET`/`DELETE` | `/api/games/{id}` | One game with its stored moves / delete it |
| `POST` | `/api/analysis/run` | Analyze stored games (JSON body: player, color, depth, thresholds…) |
| `POST` | `/api/analysis/upload` | Upload and analyze in one request |
| `POST` | `/api/analysis/export` | Download the mistakes as `json`, `csv` or `jsonl` (same body as `/run`) |
| `GET`/`DELETE` | `/api/analysis/cache` | Cache contents / clear it |
| `GET` | `/api/analysis/mistakes` | Stored mistakes (`game_id`, `category`, `severity`, `player`) |
| `GET` | `/api/analysis/games/{id}` | One analyzed game with its moves and mistakes |
| `GET` | `/api/patterns/overview` | SQL aggregates over everything stored |
| `GET` | `/api/patterns/profiles` | Stored profiles |
| `GET` | `/api/patterns/profile` | Latest profile (optionally `?player=`) |
| `GET` | `/api/patterns` | Patterns of a profile (`kind`, `recurring_only`) |

Interactive docs are at `/docs` while the server runs.

## Configuration

Copy `.env.example` to `.env`; nothing there is required.

| Variable | Default | Meaning |
| --- | --- | --- |
| `STOCKFISH_PATH` | auto-detected | Path to the Stockfish binary |
| `STOCKFISH_DEPTH` | `12` | Default search depth |
| `STOCKFISH_TIME` | — | Seconds per position; overrides the depth |
| `DATABASE_URL` | `sqlite:///./data/chess_mistakes.db` | SQLAlchemy URL |
| `UPLOAD_DIR` | `data/uploads` | Where uploaded PGNs are kept |
| `ANALYSIS_DIR` | `data/analysis` | Where the evaluation cache is kept |
| `ANALYSIS_CACHE` | `<ANALYSIS_DIR>/eval_cache.json` | Explicit cache path |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated allowed origins |
| `FRONTEND_DIST` | `frontend/dist` | Built SPA mounted at `/` when it exists |

No secrets are needed, and `.env` is gitignored.

## Invariants worth knowing

These are the non-obvious rules the code depends on. They are the reason a few lines look unusual.

**Engine scores are normalised to the mover.** Stockfish reports relative to the side to move; every
record stores the evaluation from the perspective of the player who made the move, via
`PovScore.pov(color)`. Mate scores keep their sign and are mapped to `±10000` centipawns, so a missed
mate registers as the blunder it is instead of a fabricated "100 pawn" loss.

**Flipping perspective in win% is exactly `100 - value`.** `win_percent(cp)` is a logistic, so
`win_percent(-cp) == 100 - win_percent(cp)`. The chart relies on this rather than re-deriving
probabilities.

**A finished position is never sent to the engine.** A checkmated position evaluates to `Mate(0)`, and
negating that gives `Mate(-0) == Mate(0)` — the sign of the mate is lost. So checkmate is scored
directly, other game-overs (stalemate, insufficient material) are scored as a draw, and the engine is
only asked about positions the game continued from.

**The thinking clock is the parent node's clock.** Chess.com writes `{[%clk 0:09:58]}` and python-chess
attaches the comment to the node *after* the move, so that value is the time left once the move was
played. The time the player had while deciding is therefore the parent node's clock. The first move has
no parent and is recorded as `null`, never as zero.

**The cache key is engine name plus search limit — never thresholds.** `--min-loss`, `--player`,
`--color` and every severity band are applied when mining, not when analyzing, so changing them re-reports
from the existing cache with zero engine cost. Only a new engine, a new search limit or a new PGN
invalidates anything.

**A position is "decided" only when both sides of the move agree.** It is decided when the mover was
already winning before *and* after (≥ 90% win chance), or already lost before *and* after (≤ 10%). A
move that collapses a winning position is not decided — that is precisely the mistake worth counting.
Decided positions are excluded by default, and the report always says how many were excluded.

**A hanging piece is a static exchange, not a price comparison.** The older test — "is this attacked
by something cheaper than it is worth" — calls a defended queen attacked by a knight a loss, and misses
a queen attacked by a rook behind a pawn. The detector now runs a full static exchange over the square
and reports the piece only when the exchange actually wins material. Both sides are free to stop
capturing at any point, which is what makes it a real exchange rather than a count of attackers.

**A hanging piece is only reported when a legal capture exists.** The whole thing stays gated on the
opponent actually having a legal capture onto that square — which is what suppresses pinned attackers.

**Attribution is a delta, not a state.** "This move left a piece loose" compares the loose pieces
before the move with those after it, and reports only the difference. Asking whether *anything* is
hanging would blame a move for a piece that was already lost, and would flag every position in a lost
game regardless of what was played.

**Asking what a side could do requires giving them the move.** The before-the-move facts are computed
on a copy of the board with a null move pushed, because a position evaluated with the wrong side to
move answers a different question. That flip is illegal in check and in finished positions, so it is
guarded and returns nothing there rather than raising.

**Motifs describe what the position offered, not what was played.** `motifs_before` is what the mover
could have done; `motifs_allowed` is what the position offers the opponent afterwards. The second is
what the report calls "tactics handed to the opponent", and it is derived from the board, not from the
played move's SAN — a move that walks into a fork is described as doing so even when the fork is not
apparent from the notation.

## Thresholds, and what they are worth

| Severity | Evaluation loss | Interpretation |
| --- | --- | --- |
| Normal | < 0.50 | No significant engine drop |
| Inaccuracy | 0.50 – 0.99 | Noticeable loss |
| Mistake | 1.00 – 1.99 | Serious loss |
| Blunder | 2.00+ | Very large loss |

These are a practical starting point, not chess law, and the numbers have a real noise floor.
Detecting a mistake means comparing two *independent* engine searches of two *different* positions, and
at depth 12 that difference carries roughly ±0.2–0.4 pawns of noise in a complex middlegame. **Losses
below about 1.0 at depth 12 are not trustworthy** — which is why the default `--min-loss` sits at 1.0
rather than at the inaccuracy line. Raise `--depth` before you lower `--min-loss`.

The tool also records **winning chances** alongside centipawns, because centipawn loss on its own is
misleading: dropping two pawns at +0.5 throws the game, and the same two-pawn drop at +9.0 changes
nothing at all.

## Board facts vs. interpretation

Every record keeps two things apart:

- **`facts`** — what is observable. Was the move a capture? A check? Did it leave a piece loose? What
  tactics does the resulting position offer the opponent, and what did the static exchange say the
  loose piece was worth? What did the clock say?
- **`category`** — a *heuristic* label, always accompanied by a `category_basis` string explaining the
  board facts behind it. Each `motifs_allowed` entry likewise carries its own `detail` line, so a
  reader sees the fork itself rather than having to trust the word.

The report states frequencies and conditions ("31 mistakes were played with under 30 seconds
remaining"). It does not claim to know why you played them, because the data cannot support that claim.
The stricter version of that rule: the observations must not contain motive words.

## Known limitations

- **Static exchange evaluation is exact within its rules, and its rules are not chess.** SEE assumes
  both sides keep capturing on one square, values pieces by a fixed table, and knows nothing about
  check, mate, or a defender that is pinned. It is a large improvement on counting attackers, and it is
  still a hint rather than a verdict.
- **Categories are heuristics.** A move can satisfy several tests at once; exactly one category is
  assigned, by a fixed priority order (allowed mate → missed mate → newly hanging piece → piece still
  hanging → missed capture → time pressure → phase), so counts never double-count a single mistake.
  The tactics a move hands over are reported separately and *can* outnumber the mistakes, because one
  move can hand over more than one.
- **Motif detection is a shallow search, not a tactic solver.** A fork is a piece attacking two things
  at once; a pin is a line through a more valuable piece. Neither looks more than a few plies ahead, so
  a combination that wins material over three moves is not recognised as one.
- **Phase is approximate.** "Opening / middlegame / endgame" is decided by remaining material and move
  number. Chess has no crisp definition of these, so treat them as grouping labels.
- **Time pressure needs clock data.** Chess.com includes it; many other PGN sources do not. The report
  always discloses how many games actually carried clock annotations.
- **A pattern needs repetition.** A category seen once is listed but never called a pattern; the miner
  requires at least two independent games.
- **Analysis is the bottleneck.** 500 games × ~80 moves means ~80,000 engine calls. At depth 12 that is
  roughly 40–130 minutes. The cache means you pay it once; `--limit-time` is the faster trade-off.
- **Engine evaluations are an analytical signal, not an explanation of the position.**

## Development

There are no comments in the source. The rules that would normally be comments — perspective
normalisation, the parent-node clock, the mate-in-zero sign loss, the cache key, the decided-position
rule — are in the sections above.

## Roadmap

- **V1** — PGN in, Stockfish evaluation, evaluation-loss detection, mistake records, pattern mining,
  terminal report, REST API, database, web dashboard, profile.
- **V2 (this)** — Static exchange evaluation for accurate hanging-piece detection; tactical motif
  recognition (mates, forks, pins, skewers); richer exports (JSON, CSV, JSONL, over the CLI and the API).
- **V3** — Training mode: replay your own mistakes as puzzles instead of just listing them.
- **V4** — Multi-engine and parallel analysis; opening-book awareness.
- **V5** — Optional ML/LLM layer for explanation and clustering, once there is a dataset worth using.
  The engine stays the source of objective evaluation.

## Privacy

Your PGNs are personal data. `data/games.pgn` is gitignored by default — keep it that way unless you are
happy for your games to be public. Everything runs locally; nothing is uploaded anywhere.

## License

MIT
