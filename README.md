# Chesslytics

**Stop reviewing games one at a time. Start finding the mistake you keep making.**

[Live application](https://chesslytics.onrender.com/)

Chesslytics ingests PGN games, evaluates every move with Stockfish, and mines the results for
**recurring** weaknesses: not "you blundered on move 23" but "you hang pieces in the middlegame
under time pressure, four games running." It is a multi-user web application: every person has
their own account and their own private library, and administrators manage accounts without ever
seeing anyone's games.

## Features

- **Move evaluation** with Stockfish, normalised to the mover's perspective, with correct mate handling.
- **Static exchange evaluation** for hanging-piece detection and **tactical motif** detection (mates, forks, pins, skewers).
- **Mistake mining**: severity bands, game phase, time-pressure flags, opening-book awareness and a fixed-priority category system.
- **Patterns, Chess DNA and Coach**: recurring categories, weak openings, evidence-only observations and optional AI coaching through Gemini.
- **Training mode**: every stored mistake becomes a puzzle, graded on winning-chance loss. Spaced repetition brings puzzles you got wrong back at growing intervals. Progress survives re-analysis.
- **Progress and openings**: weekly charts of average loss and mistakes per 100 moves, and a per-opening report with win rate, average loss and the move where you most often go wrong.
- **Background analysis**: uploads return immediately; analysis runs in a bounded worker pool with live progress and cancel.
- **Accounts and administration**: registration, sign-in, password change, optional email confirmation and password reset by email, one-time reset links created by an administrator, account deletion, and an admin console.
- **Backup and restore**: download everything you own as one JSON file and restore it later.
- **Operations**: request IDs, optional JSON logs, an analysis history page with retry, and optional Sentry error tracking.
- **Exports** in JSON, CSV and JSONL, plus a CLI for batch work.

## Security model

| Area | What is enforced |
| --- | --- |
| Passwords | scrypt (N=32768, r=8, p=1), per-user random salt, constant-time comparison, transparent upgrade of old hashes. Minimum 10 characters, common passwords and passwords containing the username are rejected. |
| Sessions | Signed token in an `HttpOnly`, `SameSite=Lax` cookie (`Secure` automatically over HTTPS). No token is ever visible to JavaScript. Changing a password, disabling an account or changing a role ends that account's other sessions immediately. |
| Brute force | Per-account lockout (8 failures, 15 minutes) stored in the database, plus a per-IP failure throttle. Unknown usernames take the same time as wrong passwords. |
| CSRF | Every state-changing API call must carry the `X-CSRF-Protection` header, which browsers cannot add cross-site without CORS approval. |
| Data isolation | Every table holding user data carries a `user_id`; every query is scoped to the signed-in user. Other people's IDs return `404`. Administrators cannot read other users' games through any route. |
| Abuse limits | Upload size, games per upload, games per user, plies per game, analysis depth and seconds, one active analysis per user, global queue size, per-user rate limits on uploads, puzzle attempts and Coach requests. |
| Engine safety | Clients cannot choose engine, book or verifier paths. These were previously accepted by the API and allowed running arbitrary programs on the server. |
| Transport and browser | Strict `Content-Security-Policy`, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, HSTS over HTTPS, `no-store` on API responses, request body size limit, optional `ALLOWED_HOSTS`. |
| Output | CSV exports neutralise spreadsheet formula injection. Server errors never leak internals. API docs are disabled unless `ENABLE_DOCS=true`. |
| Audit | Registrations, sign-ins, lockouts, password changes and every administrator action are recorded and shown in the admin console. |

Fail-closed by design: the application never runs without authentication. If no administrator is
configured it still starts, logs a warning, and users can register, but nobody can administer.

## Quick start (local)

Requirements: Python 3.12, Node 26 with npm 12 or newer, Stockfish (`apt install stockfish`, `brew install stockfish`
or the official download). On Debian and Ubuntu the binary is `/usr/games/stockfish`; leave
`STOCKFISH_PATH` empty and it is found automatically.

```bash
python -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --upgrade -r requirements.txt
cp .env.example .env
```

Edit `.env`: set `SECRET_KEY` (32 or more random characters), `ADMIN_USERNAME` and
`ADMIN_PASSWORD` (10 or more characters, must not contain the username). Without a database
setting the app uses a local SQLite file. Generate a secret with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Build the frontend once, then start the server:

```bash
cd frontend && npm ci && npm run build && cd ..
uvicorn app.main:app --port 8000
```

Open http://127.0.0.1:8000 and sign in as the administrator. For frontend development run
`npm run dev` in `frontend/`; the dev server proxies `/api` to port 8000.

### Updating dependencies

Python uses `pip`'s explicit `--upgrade` option:

```bash
python -m pip install --upgrade pip
python -m pip install --upgrade -r requirements.txt
```

For npm, `npm ci` is intentionally used for normal builds because it installs the exact
versions recorded in `frontend/package-lock.json`. npm does not use pip's `--upgrade` flag:
use `npm update` to refresh dependencies within the ranges declared in `frontend/package.json`,
then commit the updated lockfile. To update npm itself:

```bash
npm install --global npm@latest
cd frontend
npm update
npm run build
```

The Docker build uses Node 26 and npm 12, installs npm before installing the frontend
dependencies, and uses the lockfile for the production build.

## Deploy on a VPS (Docker, PostgreSQL, automatic HTTPS)

1. Point a DNS `A` record for your domain at the server and open ports 80 and 443.
2. Create `.env` next to `docker-compose.yml`:

```dotenv
POSTGRES_USER=chesslytics
POSTGRES_PASSWORD=<long random string>
POSTGRES_DB=chesslytics_db
SECRET_KEY=<48 random characters>
ADMIN_USERNAME=<your admin name>
ADMIN_PASSWORD=<10+ characters>
SITE_ADDRESS=chesslytics.example.com
ALLOWED_HOSTS=chesslytics.example.com
```

3. Run `docker compose up -d --build`.

Caddy obtains and renews the TLS certificate automatically. PostgreSQL sits on an internal
network with no published port, and the application container is only reachable through Caddy.
The compose file refuses to start until you set a real database password, secret and admin
credentials. Use a long random `POSTGRES_PASSWORD`; short numeric passwords are guessable.

The compose file sets `TRUSTED_PROXY_HOPS=1` so the real client address (as seen by Caddy) is used for
rate limiting. Run a single application process (the default) because the rate limiter and
job queue live in process memory.

Back up the `postgres-data` volume, for example with
`docker compose exec postgres pg_dump -U chesslytics chesslytics_db > backup.sql`.

## Deploy on Render with Neon

1. In Neon, copy the connection string (it ends with `?sslmode=require`).
2. In Render, create a Blueprint from this repository (`render.yaml`).
3. Set the environment variables below. Use the Neon string for `DATABASE_URL`.

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Neon connection string |
| `ADMIN_USERNAME` | your admin name |
| `ADMIN_PASSWORD` | 10 or more characters, not containing the username |
| `SECRET_KEY` | generated automatically by the blueprint |
| `TRUSTED_PROXY_HOPS` | `1` (set by the blueprint; see the note below) |
| `PUBLIC_URL` | optional: your Render address, for example `https://chesslytics.onrender.com` |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | optional: a mail server, to enable password reset by email |
| `SENTRY_DSN` | optional: a Sentry project address |

The blueprint asks for each optional value; leave the ones you do not need empty.

Check in the admin console's activity log that sign-in events show real client addresses. If
every event shows the same address, increase `TRUSTED_PROXY_HOPS` by one.

The free Render plan has very little CPU, and its disk is wiped on every restart, so keep
`MAX_CONCURRENT_JOBS=1` and use a lower `STOCKFISH_DEPTH` there. Move to a paid plan or a VPS for
real traffic. When you move to a VPS, point `POSTGRES_*` at the new database and restore a dump
of the Neon database; no code changes are needed.

### Upgrading an existing single-user installation

Start the new version with `ADMIN_USERNAME` and `ADMIN_PASSWORD` set (the old `AUTH_USERNAME`
and `AUTH_PASSWORD` are still read as fallbacks). On first start the application:

1. adds the new tables and `user_id` columns,
2. replaces the global-unique game fingerprint index with a per-user one,
3. creates the administrator,
4. assigns every existing game, mistake, profile and coach report to that administrator.

Nothing is deleted, and starting again changes nothing. If `ADMIN_PASSWORD` is too weak the
application logs the reason, creates no administrator and leaves your data untouched until you
fix it. Old sessions are invalidated, so everyone signs in again once.

## Administration

Sign in as an administrator and open **Admin**. You can search users, disable or enable them,
promote or demote them, reset a password, unlock a locked account, delete an account together
with all its data, and review the activity log. You cannot disable, demote or delete yourself, and
the last administrator cannot be removed.

Without a web session (for example, if you forgot the administrator password), use the command line
on the server:

```bash
python -m app.manage list-users
python -m app.manage create-user alice
python -m app.manage create-user ops --admin
python -m app.manage reset-password alice
python -m app.manage set-role alice --admin
```

On platforms without a shell, set `ADMIN_PASSWORD` to a new value together with
`ADMIN_RESET_PASSWORD=true`, deploy once, then remove `ADMIN_RESET_PASSWORD`.

To close sign-ups set `ALLOW_REGISTRATION=false`; create accounts yourself with `app.manage`.
Sign-up is also limited to 5 accounts per hour per address.

**Forgotten passwords.** An administrator can open **Admin**, choose **Reset link** next to a user
and send them the one-time link (it works once and expires after one hour; the administrator never
sees or sets the password). If you configure email (see below), users with a confirmed address can
also reset their own password from the sign-in page. Administrators cannot reset their own password
from the Admin page; they use **Account**, or `python -m app.manage reset-password`.

**Email (optional).** Set `PUBLIC_URL` and the `SMTP_*` variables. Users add an address on the
**Account** page, receive a confirmation link, and only a confirmed address can be used for
password reset. Each confirmed address belongs to one account. Without these settings the email
features are hidden and everything else works.

## Using the application

- **Games**: upload a `.pgn` file. It is stored, then analysed in the background. You can leave the page and come back; progress resumes.
- **Analyses**: every analysis you started, with status, duration and settings. Cancel one that is running, or run a finished one again.
- **Dashboard**: aggregate views of your mistakes plus **Your progress**, two weekly charts (average loss per move, mistakes per 100 moves). Lower is better. Weeks start on Monday and use the game date, falling back to the upload date.
- **Patterns**: recurring patterns, and an **Openings** table with games, win rate, average loss and the move number where mistakes cluster. Win rates need your username to be entered when you analyse.
- **Chess DNA**: your mistake profile.
- **Training**: replay the position before each mistake and get graded by the engine. **Practice** modes: smart review (due first, then new), due for review, new puzzles, every puzzle. A right answer moves a puzzle up one of five boxes (reviewed again after 1, 3, 7, 14 and 30 days); a wrong answer sends it back to the start (15 minutes).
- **Coach**: optional AI summary of your profile (needs `GEMINI_API_KEY`; limited per user per day).
- **Account**: change your password, manage your email address, download a backup or restore one, export mistakes, delete your account.

**Backup and restore.** The backup is one JSON file with your games, every mistake, your puzzle
attempts and your latest profile. Restoring only adds games you do not already have, never
overwrites anything, checks every field, and respects the library size limit. Move-by-move data is
not included (it can be rebuilt): after a restore, run an analysis on the Games page and your
puzzle history is kept.

Re-analysing a single game updates that game's moves and mistakes but leaves your Chess DNA
profile alone. Uploading or choosing **Analyze stored games** builds a new profile from the games
that were analysed in that run.

## Command line

```bash
python -m app.main --pgn games.pgn --player Alice --limit-time 0.1
python -m app.main --pgn games.pgn --save --user alice
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--pgn` | `data/games.pgn` | PGN file to analyse |
| `--depth` / `--limit-time` | `STOCKFISH_DEPTH` (else `12`) / none | Search depth, or seconds per move |
| `--min-loss` | `1.0` | Minimum pawn loss to report |
| `--player` / `--color` | none / `both` | Restrict to one player or colour |
| `--time-pressure` | `30` | Seconds below which a move counts as time-pressured |
| `--workers` | `1` | Parallel engine processes |
| `--verify-with` | none | Second engine binary for an agree / disputed check |
| `--book` / `--exclude-book` | none | Polyglot `.bin`; mark or drop moves still in theory |
| `--output` / `--output-format` | none | Write `.json`, `.csv` or `.jsonl` |
| `--save` with `--user` | none | Store results in the database for an existing account |
| `--no-cache` / `--rebuild-cache` | none | Bypass or rebuild the local evaluation cache |

The command line is a trusted, local tool, so engine, book and verifier paths are allowed here.
The web API ignores them.

## REST API

All routes except `/api/health` and `/api/auth/status|register|login|logout` require a session
cookie. Every `POST`, `PATCH` and `DELETE` needs the `X-CSRF-Protection: 1` header.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness probe |
| `GET` | `/api/auth/status` | Registration availability and password rules |
| `POST` | `/api/auth/register`, `/login`, `/logout` | Account creation and sessions |
| `GET` / `DELETE` | `/api/auth/me` | Current user / delete own account |
| `POST` | `/api/auth/password` | Change password |
| `POST` | `/api/auth/forgot`, `/reset`, `/verify-email` | Password reset and email confirmation (public, rate limited; need email configured) |
| `PUT` / `DELETE` / `POST` | `/api/account/email`, `/api/account/email/resend` | Manage your email address |
| `GET` / `POST` | `/api/account/backup`, `/api/account/backup/restore` | Download or restore a backup |
| `POST` | `/api/games/upload` | Store games without analysing |
| `GET` / `DELETE` | `/api/games`, `/api/games/{id}` | Library |
| `POST` | `/api/analysis/upload` | Store games and start an analysis job |
| `POST` | `/api/analysis/run` | Analyse stored games (optional `game_ids`, `update_profile`) |
| `GET` | `/api/analysis/jobs`, `/jobs/{id}` | Job history (`limit`, `offset`) and status |
| `POST` | `/api/analysis/jobs/{id}/cancel`, `/retry` | Cancel a job, or run a finished one again |
| `GET` | `/api/analysis/mistakes`, `/games/{id}`, `/export` | Results and exports |
| `GET` | `/api/patterns/overview`, `/api/patterns/profile`, `/api/patterns/profiles`, `/api/patterns` | Aggregates |
| `GET` | `/api/patterns/progress`, `/api/patterns/openings` | Weekly progress and per-opening report |
| `GET` / `POST` | `/api/training/puzzles...` (`practice=queue\|due\|new\|all`), `/stats`, `/attempts` | Training |
| `GET` | `/api/coach` | AI coaching report |
| `GET` / `PATCH` / `POST` / `DELETE` | `/api/admin/stats`, `/users`, `/users/{id}/reset-link`, `/audit` | Administrators only |

Interactive API docs are off by default; set `ENABLE_DOCS=true` to expose `/docs`.

## Configuration reference

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | none | Full database URL (Neon or any Postgres). Tried first. |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT` | none | Used when `DATABASE_URL` is empty, or as a fallback if it cannot connect, as long as `POSTGRES_USER` is set. With neither, a local SQLite file is used. |
| `SECRET_KEY` | random per start | Signing key, 32 or more characters. Without it every restart signs everyone out. |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | none | Administrator created on first start. |
| `ADMIN_RESET_PASSWORD` | `false` | One-off reset of the administrator password from `ADMIN_PASSWORD`. |
| `ALLOW_REGISTRATION` | `true` | Allow public sign-up. |
| `SESSION_HOURS` | `24` | Session lifetime. |
| `ALLOWED_HOSTS` | any | Comma-separated host names the server answers to. |
| `CORS_ORIGINS` | none | Only needed if the frontend is served from another origin. |
| `TRUSTED_PROXY_HOPS` | `0` | Number of reverse proxies in front of the app. `0` when exposed directly. Set to `1` behind Caddy or Render (the compose file and blueprint already do). A wrong value either lets clients spoof their address or makes everyone share one address. |
| `COOKIE_SECURE` | auto | Force the `Secure` cookie flag. |
| `ENABLE_DOCS` | `false` | Expose `/docs` and `/openapi.json`. |
| `STOCKFISH_PATH` | auto-detect | Engine binary. |
| `STOCKFISH_DEPTH`, `STOCKFISH_TIME` | `12`, none | Default search limit (time overrides depth). |
| `MAX_UPLOAD_MB` | `8` | Upload size cap. |
| `MAX_GAMES_PER_UPLOAD` | `300` | Games per file. |
| `MAX_GAMES_PER_USER` | `1500` | Library size for non-admin users. |
| `MAX_PLIES_PER_GAME` | `600` | Longer games are skipped. |
| `MAX_ANALYSIS_DEPTH`, `MAX_ANALYSIS_SECONDS` | `18`, `2` | Caps on what a user may request. |
| `MAX_CONCURRENT_JOBS` | `2` | Analyses running at once (each uses one engine process). |
| `MAX_QUEUED_JOBS` | `40` | Waiting analyses before new ones are refused. |
| `MAX_CONCURRENT_GRADING` | `2` | Simultaneous training gradings. |
| `COACH_DAILY_LIMIT` | `10` | Coach reports per user per day. |
| `MAX_BACKUP_MB` | `32` | Largest backup file a user may restore. |
| `PUBLIC_URL` | none | Address people use in the browser, no trailing slash. Needed for links in emails. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | none, `587`, `starttls` | Mail server. `SMTP_SECURITY` is `starttls`, `ssl` or `none`. Email features turn on when `PUBLIC_URL`, `SMTP_HOST` and `SMTP_FROM` are all set. |
| `LOG_FORMAT` | `text` | `json` for log services. Every response carries an `X-Request-ID`, and every log line includes it. |
| `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE` | none, `production`, `0` | Optional error tracking. Cookies, passwords, request bodies and query strings are never sent. |
| `PROFILES_KEPT_PER_USER`, `JOB_RETENTION_DAYS` | `5`, `14` | History kept. |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_RECYCLE` | `5`, `5`, `300` | Connection pool tuning. |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | none, `gemini-2.5-flash` | Enables Coach. |
| `PUZZLE_TOLERANCE` | `5.0` | Win-percentage a training answer may lose and still count as correct. |
| `PARALLEL_WORKERS`, `VERIFY_WITH`, `BOOK_PATH`, `ANALYSIS_DIR` | see `.env.example` | Command-line defaults. |
| `SITE_ADDRESS` | `:80` | Caddy address (compose only), e.g. your domain. |
| `LOG_LEVEL` | `INFO` | Logging level. |

## Known limitations

- Rate limits and the job queue are in process memory, so run one application process. Account lockout is stored in the database and is shared.
- Analysis jobs interrupted by a restart are marked failed (queued ones are resumed).
- Heuristic tactics detection (SEE, motifs) is not a full tactics solver.
- Time-pressure statistics need clock annotations in the PGN (Chess.com exports have them).
- The analysis cache file is used by the command line only. The web app stores every result in the database, so redeploys never force a re-analysis and no disk is needed.
- Backups do not contain move-by-move data; run an analysis after restoring to rebuild it.
- Coach output is only as good as the evidence behind it, and it sends your profile summary (not raw games) to Gemini when enabled.

## Privacy

Your games are private to your account. Everything runs on your own server except Coach, which
sends the mined profile summary to Gemini only when `GEMINI_API_KEY` is set. Deleting your account
removes your games, analysis, training history and Coach reports.
