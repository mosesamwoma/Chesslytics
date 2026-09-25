# Chess Mistakes Miner

Chess Mistakes Miner reads a collection of your completed chess games, evaluates every move with
Stockfish, and then answers a question a normal game review cannot: **what mistakes do I keep making,
and in what situations?** Stockfish can already tell you that you blundered on move 23. It cannot tell
you that you have now blundered on move 23 in four different games, all of them in the middlegame, all
of them with under thirty seconds on the clock. Turning many engine evaluations into a personal mistake
dataset — and mining that dataset for recurring patterns — is the whole point of this project.

It ships as four things over one engine:

- a **CLI** that goes straight from a PGN file to a terminal report,
- a **REST API** (FastAPI) with a SQLite store of games, moves, mistakes and profiles,
- a **web app** (React + Vite) that charts a single game and turns the whole collection into a profile,
- a **training mode** that turns each stored mistake back into the position it came from and drills you
  on it, scoring your answers against the engine.

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
                      │                      ↘ see / motifs / book   │
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
| `app/chess/book.py` | Polyglot opening book: was this position still theory, and what did theory play |
| `app/mining/mistake_detector.py` | Thresholds, severity bands, categories, per-move mistake records |
| `app/mining/pattern_miner.py` | Aggregate records into counts, and decide what counts as recurring |
| `app/mining/profiler.py` | The profile and its evidence-only observations |
| `app/database/models.py` | `Game`, `Move`, `Mistake`, `PlayerProfile`, `Pattern`, `PuzzleAttempt` |
| `app/services/game_service.py` | Uploads, storage, queries, JSON shapes for games |
| `app/services/analysis_service.py` | The engine pass, the cache, mining, persistence, verification |
| `app/services/training_service.py` | A mistake as a puzzle, the grader, attempts, accuracy stats |
| `app/services/export_service.py` | Mistake records as JSON, CSV or JSONL, for the CLI and the API |
| `app/api/*.py` | `/api/games`, `/api/analysis`, `/api/patterns`, `/api/training` |
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

Opening books are optional and need nothing extra installed — `chess.polyglot` ships inside
python-chess, and it reads the standard Polyglot `.bin` format that every chess GUI can export. Point
`--book` at one and mistakes played while the book still had a move get marked; add `--exclude-book`
to drop them entirely. A missing or unreadable book is reported as such rather than silently
pretended away.

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
| `--workers` | `1`, or `$PARALLEL_WORKERS` | Analyze this many games at once, each in its own engine process |
| `--verify-with` | `$VERIFY_WITH` | A second engine binary; re-check every mistake and mark it agreed or disputed |
| `--book` | `$BOOK_PATH` | Polyglot (`.bin`) opening book; mistakes still in theory are marked |
| `--exclude-book` | — | Drop mistakes played while still in book from every count |
| `--save` | — | Also store games and results in the database |
| `--stockfish` / `--quiet` | — | Binary path / silence progress output |

`--player` matters more than it looks. Without it you get your opponent's blunders mixed in with yours,
which is exactly the data you don't want.

`--workers` is opt-in and defaults to 1, so nothing about a normal run changes. See
[Parallel analysis](#parallel-analysis) for what it actually buys you on real hardware — on a
two-core laptop it is close to break-even, and the measured speed-ups are there.

`--verify-with` answers a different worry: a single engine's verdict at depth 12 carries real noise,
so a mistake only one engine sees is worth flagging before you go and study it. It costs one engine
call per mistake, against the two per move the analysis itself spends, and the verdicts are cached
separately from the evaluation cache, so re-running it is free.

```bash
python -m app.main --workers 4                          # four games at a time
python -m app.main --verify-with /usr/bin/stockfish     # second opinion on every mistake
python -m app.main --book data/book.bin --exclude-book  # ignore mistakes that were still theory
```

### Exports

`--output` writes the mistake records, not the whole report, in the format the extension implies:
`.csv` gives one flat row per mistake with a fixed 35-column header (`motifs_allowed`, the hung
piece's square and SEE value, the played and best moves in UCI, the opening-book columns and the
verification columns among them), `.jsonl` gives the same rows as newline-delimited objects, and
`.json` gives the entire report including patterns, profile and observations. `--output-format`
overrides the extension when the name is something else.

The last seven columns are the V4 additions: `fen`, `played_uci` and `best_move_uci` (raw moves, so a
row can be replayed without re-parsing SAN), `in_book` and `book_move`, and `agreed` with
`verified_loss` and `verified_by`. When no verifier ran, `agreed`, `verified_loss` and `verified_by`
are empty rather than `false` — "not checked" and "checked and disagreed" are different things.

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

With `--workers`, `--verify-with` and `--book`, three more lines and two more sections appear, and the
largest-loss block gains a note when the second engine disagrees:

```
Engine: Stockfish 18  |  search: depth 12  |  workers: 4
...
Largest single evaluation loss
------------------------------
  Game 42, move 27 (white)
  Played: Qe2
  Best:   Bxh7+
  Book:   Nf6
  Loss:   3.10 pawns (+0.80 -> -2.30)
  Note:   Stockfish 17 did not score this as a loss (it measured 0.40 pawns)

Engine agreement
----------------
  Verified with Stockfish 17 (depth 12)
  Agreed: 121 of 142 mistakes (85.2%)
  Disputed: 21

Opening book
------------
  Book: data/book.bin
  A book move existed in 2140 of 6842 positions examined
  Mistakes played while still in book: 46
  Book ran out at a median of move 9 (83 games reached it)
```

A disputed mistake is not necessarily a mistake you should ignore — at depth 12 the two engines are
disagreeing inside the noise floor the thresholds section describes. It is a flag that says "go and
look at this one yourself" rather than "this is wrong".

## Web app

Backend and frontend run separately in development:

```bash
uvicorn app.main:app --reload            # http://127.0.0.1:8000
cd frontend && npm install && npm run dev  # http://127.0.0.1:5173
```

Vite proxies `/api` to the backend, so no CORS setup is needed in development. Five pages:

- **Dashboard** — totals, mistake types, phases, severity, openings with the most mistakes.
- **Games** — upload a PGN, analyze everything stored, page through games, delete.
- **Game analysis** — win-probability chart for the whole game, a board you can step through
  move by move, and the mistake cards for that game.
- **Training** — the stored mistakes as puzzles: play your move on the board and get it graded.
- **Chess DNA** — the profile: time-pressure share, tactical weaknesses, phase and severity
  breakdowns, openings you lose ground in, and the evidence-only observations.

### Training

Training shows you the position *before* one of your mistakes with you to move, and grades whatever
you play. The solution is not in the payload the board renders from — the answer comes from the
server only after you have committed to a move, or when you ask to see it.

A move is **correct** when it is the stored best move, or it delivers mate, or it gives up no more
than `PUZZLE_TOLERANCE` (default 5.0) percentage points of winning chance against the best move.
Win chance rather than raw centipawns, for the same reason the thresholds section gives: dropping two
pawns at +0.5 throws the game, the same two pawns at +9.0 changes nothing. Grading costs one engine
call per attempt, and only when it has to: an answer that matches the stored best move is graded
`"stored"` with no engine call at all, an engine-graded answer reports `graded_by: "engine"`, and if
the engine will not start the grader falls back to plain exact match and reports
`graded_by: "exact_match"` — so a missing engine degrades the drill rather than breaking it.

Every attempt is stored in `puzzle_attempts`, and the page's accuracy panel reads back from it:
attempts, solves and accuracy overall and per category, plus whichever category you are worst at.
That is the point of the page — the drill results are another dataset about you, and the weakest
category is a better answer to "what should I study" than the raw mistake count.

The board is click-source-then-target, with keyboard `←`/`→` to move between puzzles. When two legal
moves share a from and to square (promotion), you are asked which piece. Filters narrow to a
category, a severity or puzzles you have not seen; by default the least-attempted puzzles come first,
so a session surfaces new material before repeats. A mistake with no stored position is skipped
rather than guessed at, since the FEN is what the whole drill depends on.

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
| `GET` | `/api/training/puzzles` | Mistakes as puzzles, solution withheld (`category`, `severity`, `player`, `unseen_only`, `limit`, `offset`) |
| `GET` | `/api/training/puzzles/{id}` | One puzzle, with its legal moves and your attempt history |
| `POST` | `/api/training/puzzles/{id}/attempt` | Grade a move, store the attempt, return the verdict |
| `GET` | `/api/training/puzzles/{id}/solution` | Explicit reveal: best move, the basis, what you played |
| `GET` | `/api/training/attempts` | Recent attempts (`player`, `limit`) |
| `GET` | `/api/training/stats` | Attempts, solves and accuracy, overall and per category |

Interactive docs are at `/docs` while the server runs. `/api/analysis/run` and `/api/analysis/export`
also accept `workers`, `verify_with`, `book` and `exclude_book`, so the web app can drive everything
the CLI can.

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
| `VERIFY_CACHE` | `<ANALYSIS_DIR>/verify_cache.json` | Where second-engine verdicts are cached |
| `PARALLEL_WORKERS` | `1` | Default for `--workers` |
| `VERIFY_WITH` | — | Default for `--verify-with` |
| `BOOK_PATH` | — | Default for `--book` |
| `PUZZLE_TOLERANCE` | `5.0` | Winning-chance points a training answer may give up and still count |
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

**The opening book is consulted at mining time, never during analysis.** `in_book` and `book_move` are
threshold-like: they depend on which book file you point at, and the cache key deliberately excludes
everything threshold-like. Writing them into cached move records would mean a new book invalidates
the cache — the one thing the design promises it never does. So the book is opened once per mining
run and queried from each record's `fen_before`, which is a memory-mapped lookup costing microseconds.
Swapping books re-reports from the existing cache with zero engine cost, exactly like changing
`--min-loss`.

**Re-mining without a verifier clears the verification columns.** `persist_analysis` deletes and
re-inserts the mistake rows for every game it re-mines, so `--verify-with` results do not survive a
later run that omits it. That is deliberate — a stale "agreed" badge next to a freshly mined loss
would be a claim nothing had checked. The columns null out and the CSV leaves them empty, which is how
"not checked" stays distinguishable from "checked and disagreed".

**`--workers` is a process pool with one engine per worker, and the engine is closed inside the task
that opened it.** Two things force this shape. First, launching Stockfish costs about 800 ms on this
machine against roughly 20 ms for a depth-10 search, so opening an engine per *game* made parallel
analysis slower than sequential; slicing the games into one contiguous run per worker pays that cost
once per worker instead of once per game. Second — and this is the one that will bite anyone who
refactors it — python-chess runs each engine's asyncio loop in a **non-daemon** thread. A worker
process that still holds an engine at interpreter exit can never finish shutting down, and the pool
hangs in `join()` forever with no error. Holding the engine in a pool initializer, which looks like
the natural way to amortise the launch cost, produces exactly that hang. So `_analyze_slice` opens its
engine, analyses its games, and closes it in a `finally`.

**Every slice clears the engine's hash before each game.** Stockfish is stateful across searches:
its transposition table carries over, so the same position at the same depth returns a different
evaluation depending on what was searched before it (measured: 38 cp from a fresh engine, 49 cp after
a warm-up, and 38/39/46/44 across four orderings). `Clear Hash` resets the table, the history and the
pawn cache, and reproduces a virgin engine exactly — 38 == 38 after warm-up. Without it, results would
depend on how the games happened to be sliced, and re-running with a different `--workers` would
change the numbers.

**An engine cannot be closed across a process boundary, and a queue cannot be passed as a task
argument.** The progress queue is created from the `spawn` context and passed to the pool through
`initargs`, because a `multiprocessing.Queue` may only be shared by inheritance. It is drained with
`get_nowait()` on the parent's `wait()` timeout rather than by blocking on it, so a worker that dies
without finishing cannot wedge the parent.

**Parallel output is deterministic, but it is not identical to sequential output — and the sequential
path is the one that moves.** This is the least obvious thing in the codebase, so here is the whole
finding.

The sequential path reuses one engine across every game, so Stockfish's transposition table carries
from one game into the next. Positions recur between games (openings especially), so later games are
searched with knowledge of earlier ones. Isolating that on a 12-game collection at depth 8, evaluating
the same 33 distinct positions twice with the same binary and the same limit:

| | Positions differing | Worst gap |
| --- | --- | --- |
| One engine across games vs. `Clear Hash` before each game | **30 of 33** | 71 cp |

Those 71-centipawn swings land right on the reporting threshold, so the *count* of mistakes changes
with it: the same collection, the same depth, the same binary gives **9 mistakes sequentially and 12
with the pool**. Nothing is broken — both are honest outputs of the engine — but it means the shipped
sequential path's verdict on a move depends on which other games are in the PGN and what order they
are in. Add one game to your collection and a mistake in a different game can appear or vanish.

The pool does not have that property: fresh engine per slice plus `Clear Hash` before each game makes
each game's evaluation depend only on that game. What is guaranteed and was measured: the pool is
exactly equivalent to a fresh engine per game (0 differing evaluations in 148 plies), the result does
not depend on the worker count, and repeated runs are bit-identical to each other.

The default is left exactly as it was, so an existing cache and an existing report keep meaning what
they meant. If you want history-independent numbers, the pool is the path that gives them.

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

## Parallel analysis

`--workers N` slices the games that missed the cache into N contiguous runs, weighted by game length
(longest first, into the least-loaded bin), and gives each worker one slice. Each worker starts one
Stockfish process pinned to `Threads=1` — the stock engine otherwise uses every core by itself, so
naive fan-out oversubscribes the CPU and makes things worse.

The cost model is fixed-per-worker plus per-move, and the fixed part dominates on small collections:

| Cost | Measured |
| --- | --- |
| Process spawn + Stockfish NNUE load + `isready` | ~800 ms per engine |
| One depth-10 search of a middlegame position | ~19–41 ms |
| One depth-13 search | ~183 ms |

So a worker costs about the same as 40 depth-10 searches before it evaluates anything. On the
2-physical-core, 4-thread laptop this was developed on, with 12 games and a fair slice each way:

| Search | Sequential | 4 workers | Speed-up |
| --- | --- | --- | --- |
| depth 10 (41 ms/move) | 19.6 s | 26.5 s | **0.74×** |
| depth 13 (183 ms/move) | 71.4 s | 65.5 s | **1.09×** |

That is the honest picture: **on a two-core machine, `--workers` is close to break-even and can be a
loss.** Parallelism here is not free throughput, it is a trade — you spend cores you do not have on
process startup and memory (each Stockfish instance holds its own NNUE network), and you win only once
the per-move search time is large enough to bury that. It pays off on collections that are long rather
than numerous, at high depth, on machines with real cores to spare, and it is worth one measurement on
your own machine before you leave it on. The default is 1 because the default should not be a
gamble.

Speed is not the only thing `--workers` changes. Each worker gets a fresh engine and clears its hash
before every game, so the pool's verdicts depend only on the game being analysed — while the
sequential default carries engine state from game to game. The two paths therefore disagree on a small
number of positions near the reporting threshold, and the mistake count with them (9 against 12 on the
sample collection at depth 8). The mechanism is measured and the reasoning is in
[the invariants](#invariants-worth-knowing). If you want numbers that do not move when you add an
unrelated game to your PGN, the pool is the path that gives you that.

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
  `--workers` helps less than it sounds like it should — see
  [Parallel analysis](#parallel-analysis) for the measured numbers.
- **The sequential path's verdicts depend on the rest of your collection.** Stockfish carries its
  transposition table from one game to the next, and adding or reordering games shifts evaluations by
  up to 71 cp — enough to move a mistake across the 1.0-pawn line. This is inherited behaviour, not
  something the parallel work introduced, and it is left alone so existing caches keep meaning what
  they meant. `--workers 2` and up analyse each game in isolation and do not have it. The measurement
  is in [the invariants](#invariants-worth-knowing).
- **One engine's verdict is not gospel, and the second opinion is bounded by the same noise.** A
  mistake is a comparison of two independent searches, and at depth 12 that comparison carries
  ±0.2–0.4 pawns, so `--verify-with` is comparing one noisy estimate against another. It is a
  triage flag, not a correction. On the machine this was developed on only one engine binary was
  installed, so verification was exercised by pointing both sides at the same binary at different
  search depths — that proves the plumbing and that the verdicts are genuinely computed, but not
  cross-engine agreement. Run it with two different engines before trusting the colours on it.
- **The opening book is only as good as the book.** Coverage is disclosed in the report ("a book move
  existed in X of Y positions") for the same reason clock coverage is: a `--exclude-book` run against
  a thin or short book quietly means something different from one against a deep book, and a mistake
  at move 3 is marked as theory because some book happened to contain it, not because it is good.
  `in_book` means "a book had a move here", never "this move was fine".
- **Engine evaluations are an analytical signal, not an explanation of the position.**

## Development

There are no comments in the source. The rules that would normally be comments — perspective
normalisation, the parent-node clock, the mate-in-zero sign loss, the cache key, the decided-position
rule, why the book is mined rather than analysed, why the pool closes its engine inside the task, why
each slice clears the hash — are in the sections above. If you change one of those behaviours, change
the paragraph that explains it in the same commit, or the code becomes folklore.

## Roadmap

- **V1** — PGN in, Stockfish evaluation, evaluation-loss detection, mistake records, pattern mining,
  terminal report, REST API, database, web dashboard, profile.
- **V2** — Static exchange evaluation for accurate hanging-piece detection; tactical motif
  recognition (mates, forks, pins, skewers); richer exports (JSON, CSV, JSONL, over the CLI and the API).
- **V3 (this)** — Training mode: stored mistakes become puzzles you play a move against, graded by
  the engine on winning chance, with every attempt persisted and accuracy reported per category.
- **V4 (this)** — Multi-engine verification of every mistake (`agreed` / `disputed`); opt-in parallel
  analysis over a process pool; Polyglot opening-book awareness, including `--exclude-book`.
- **V5** — Optional ML/LLM layer for explanation and clustering, once there is a dataset worth using.
  The engine stays the source of objective evaluation.

## Privacy

Your PGNs are personal data. `data/games.pgn` is gitignored by default — keep it that way unless you are
happy for your games to be public. Everything runs locally; nothing is uploaded anywhere.

## License

MIT
