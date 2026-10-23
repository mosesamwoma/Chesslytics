from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
import chess.pgn

from app import settings
from app.chess.pgn_parser import parse_pgn

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{2,40}$")
SOURCES = ("chesscom", "lichess")
CHESSCOM_ARCHIVE_PREFIX = "https://api.chess.com/pub/player/"
USER_AGENT = "Chesslytics/1.0 (game import)"
TIMEOUT_SECONDS = 25


class ImportFailed(ValueError):
    pass


class InvalidUsername(ValueError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def clean_username(value: str) -> str:
    name = (value or "").strip()
    if not USERNAME_PATTERN.match(name):
        raise InvalidUsername("that does not look like a valid username")
    return name


def fetch(url: str, accept: str, site: str) -> str:
    limit = settings.max_upload_bytes()
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": accept}
    )
    try:
        with _opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ImportFailed(f"{site} has no player with that username") from exc
        if exc.code == 429:
            raise ImportFailed(f"{site} is rate limiting requests; try again in a minute") from exc
        raise ImportFailed(f"{site} answered with an error ({exc.code})") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ImportFailed(f"could not reach {site}; try again later") from exc
    if len(raw) > limit:
        raise ImportFailed(f"{site} returned more data than the {limit // (1024 * 1024)} MB limit")
    return raw.decode("utf-8", errors="replace")


def chesscom_text(username: str, months: int) -> str:
    name = username.lower()
    listing = fetch(
        f"{CHESSCOM_ARCHIVE_PREFIX}{name}/games/archives", "application/json", "Chess.com"
    )
    try:
        archives = json.loads(listing).get("archives") or []
    except (ValueError, AttributeError) as exc:
        raise ImportFailed("Chess.com sent an answer that could not be read") from exc
    urls = [
        item
        for item in archives
        if isinstance(item, str) and item.startswith(CHESSCOM_ARCHIVE_PREFIX)
    ]
    if not urls:
        raise ImportFailed("Chess.com has no games for that player")
    chunks: list[str] = []
    size = 0
    budget = settings.max_upload_bytes()
    for url in reversed(urls[-months:]):
        text = fetch(f"{url}/pgn", "application/x-chess-pgn", "Chess.com")
        size += len(text)
        chunks.append(text)
        if size >= budget:
            break
    return "\n\n".join(chunks)


def lichess_text(username: str, max_games: int) -> str:
    url = (
        f"https://lichess.org/api/games/user/{username}"
        f"?max={max_games}&clocks=true&opening=true&evals=false"
    )
    return fetch(url, "application/x-chess-pgn", "Lichess")


def download(
    source: str, username: str, max_games: int, months: int
) -> tuple[list[chess.pgn.Game], list[str]]:
    if source not in SOURCES:
        raise ImportFailed("unknown source")
    name = clean_username(username)
    if source == "chesscom":
        text = chesscom_text(name, max(1, min(months, settings.import_months())))
    else:
        text = lichess_text(name, max_games)
    games, errors = parse_pgn(text)
    if not games:
        raise ImportFailed("no games were found for that player")
    games.sort(key=lambda game: game.headers.get("UTCDate", game.headers.get("Date", "")), reverse=True)
    return games[:max_games], errors


def source_label(source: str, username: str) -> str:
    site = "chess.com" if source == "chesscom" else "lichess"
    return f"{site}: {username}"[:200]

