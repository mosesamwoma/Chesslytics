from __future__ import annotations

import chess
import pytest
from fastapi.testclient import TestClient

from app.database import database
from app.services import analysis_service
from fake_engine import FakeChessEngine, ScriptedEngine
from helpers import fen_after

UPLOAD_PGN = """[Event "API Test"]
[White "Alice"]
[Black "Bob"]
[Result "*"]

1. e4 e5 *
"""

PNG_BYTES = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("ANALYSIS_DIR", str(tmp_path / "analysis"))
    monkeypatch.setenv("ANALYSIS_CACHE", str(tmp_path / "analysis" / "eval_cache.json"))

    database.reset_engine()
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    database.reset_engine()


@pytest.fixture
def engine(monkeypatch):
    scripted = ScriptedEngine(
        script={
            chess.STARTING_FEN: {"cp": 300, "best": "d2d4"},
            fen_after("e4"): {"cp": 300},
        }
    )
    monkeypatch.setattr(
        analysis_service, "ChessEngine", lambda path, limit: FakeChessEngine(path, limit, scripted)
    )
    monkeypatch.setattr(analysis_service, "find_stockfish", lambda explicit=None: "/fake/stockfish")
    return scripted


def upload(client, text=UPLOAD_PGN, filename="games.pgn"):
    return client.post(
        "/api/games/upload",
        files={"file": (filename, text.encode("utf-8"), "application/x-chess-pgn")},
    )


def test_the_api_starts_empty(client):
    assert client.get("/api/health").json()["status"] == "ok"

    listing = client.get("/api/games").json()
    assert listing["total"] == 0
    assert listing["games"] == []


def test_uploading_stores_games_and_skips_duplicates(client):
    first = upload(client)
    assert first.status_code == 200

    body = first.json()
    assert body["parsed"] == 1
    assert body["stored"] == 1
    assert body["skipped"] == 0
    assert body["games"][0]["white"] == "Alice"
    assert body["games"][0]["move_count"] == 0

    again = upload(client).json()
    assert again["stored"] == 0
    assert again["skipped"] == 1

    assert client.get("/api/games").json()["total"] == 1


def test_uploading_something_that_is_not_a_pgn_is_rejected(client):
    response = upload(client, text="not a pgn", filename="picture.png")

    assert response.status_code == 400
    assert "pgn" in response.json()["detail"]


def test_an_empty_upload_is_rejected(client):
    response = upload(client, text="", filename="empty.pgn")

    assert response.status_code == 400
    assert client.get("/api/games").json()["total"] == 0


def test_a_game_can_be_read_and_deleted(client):
    upload(client)

    detail = client.get("/api/games/1").json()
    assert detail["white"] == "Alice"
    assert detail["moves"] == []
    assert "mistakes" not in detail

    assert client.get("/api/games/999").status_code == 404
    assert client.delete("/api/games/1").json() == {"deleted": 1}
    assert client.delete("/api/games/1").status_code == 404
    assert client.get("/api/games").json()["total"] == 0


def test_analysis_without_stored_games_is_rejected(client):
    response = client.post("/api/analysis/run", json={})

    assert response.status_code == 400


def test_a_missing_engine_is_reported_as_unavailable(client, monkeypatch):
    upload(client)

    def missing(explicit=None):
        raise FileNotFoundError("no stockfish binary found")

    monkeypatch.setattr(analysis_service, "find_stockfish", missing)
    response = client.post("/api/analysis/run", json={})

    assert response.status_code == 503
    assert "stockfish" in response.json()["detail"]


def test_analysis_persists_what_it_found(client, engine):
    upload(client)
    response = client.post("/api/analysis/run", json={"player": "Alice", "depth": 12})

    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "Fake Engine 1"
    assert body["limit"] == {"type": "depth", "value": 12.0}
    assert body["counts"]["games_analyzed"] == 1
    assert body["persistence"]["moves"] == 2
    assert body["persistence"]["mistakes"] == 1

    assert len(body["mistakes"]) == 1
    mistake = body["mistakes"][0]
    assert mistake["player"] == "Alice"
    assert mistake["color"] == "white"
    assert mistake["played_move"] == "e4"
    assert mistake["best_move"] == "d2d4"
    assert mistake["severity"] == "blunder"
    assert mistake["loss"] == 6.0
    assert mistake["category_basis"]

    stored = client.get("/api/analysis/mistakes").json()["mistakes"]
    assert len(stored) == 1
    assert stored[0]["category"] == "opening"

    filtered = client.get("/api/analysis/mistakes", params={"severity": "mistake"}).json()
    assert filtered["mistakes"] == []


def test_the_stored_game_carries_its_move_sequence(client, engine):
    upload(client)
    client.post("/api/analysis/run", json={})

    detail = client.get("/api/analysis/games/1").json()
    assert detail["analyzed"] is True
    assert detail["analyzed_depth"] == 12
    assert detail["move_count"] == 2

    moves = sorted(detail["moves"], key=lambda move: move["ply"])
    assert [move["san"] for move in moves] == ["e4", "e5"]
    assert moves[0]["winpct_before"] > 50.0
    assert moves[0]["winpct_after"] < 50.0
    assert moves[0]["loss_cp"] == 600
    assert moves[0]["uci"] == "e2e4"
    assert moves[1]["error"] is None


def test_the_overview_aggregates_what_was_stored(client, engine):
    upload(client)
    client.post("/api/analysis/run", json={"player": "Alice"})

    overview = client.get("/api/patterns/overview").json()
    assert overview["games"] == 1
    assert overview["games_analyzed"] == 1
    assert overview["mistakes"] == 1
    assert overview["average_loss"] == 6.0
    assert overview["by_category"] == [{"key": "opening", "count": 1}]
    assert overview["by_color"] == [{"key": "white", "count": 1}]

    profiles = client.get("/api/patterns/profiles").json()
    assert len(profiles["profiles"]) == 1

    profile = client.get("/api/patterns/profile").json()
    assert profile["mistake_count"] == 1
    assert profile["player"] == "Alice"
    assert profile["profile"]["average_loss"] == 6.0

    patterns = client.get("/api/patterns").json()["patterns"]
    assert {row["kind"] for row in patterns} >= {"category", "severity", "phase"}


def test_a_second_run_reuses_the_cache_without_the_engine(client, engine):
    upload(client)
    first = client.post("/api/analysis/run", json={}).json()
    calls = engine.call_count
    assert calls == 4
    assert first["counts"]["games_analyzed"] == 1
    assert first["persistence"]["mistakes"] == 2

    second = client.post("/api/analysis/run", json={}).json()

    assert second["counts"]["games_reused"] == 1
    assert second["counts"]["games_analyzed"] == 0
    assert engine.call_count == calls
    assert second["persistence"]["mistakes"] == first["persistence"]["mistakes"]


def test_the_cache_can_be_inspected_and_cleared(client, engine):
    upload(client)
    client.post("/api/analysis/run", json={})

    info = client.get("/api/analysis/cache").json()
    assert info["games"] == 1
    assert info["moves"] == 2
    assert info["meta"]["engine"] == "Fake Engine 1"

    assert client.delete("/api/analysis/cache").json()["cleared"]
    assert client.get("/api/analysis/cache").json()["games"] == 0


def test_upload_and_analyze_in_a_single_request(client, engine):
    response = client.post(
        "/api/analysis/upload",
        files={"file": ("games.pgn", UPLOAD_PGN.encode("utf-8"), "application/x-chess-pgn")},
        data={"player": "Alice", "depth": "12", "min_loss": "1.0"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["uploaded"].endswith("games.pgn")
    assert body["parsed"] == 1
    assert body["persistence"]["games"] == 1
    assert len(body["mistakes"]) == 1
    assert client.get("/api/games").json()["total"] == 1


def test_a_binary_upload_is_reported_as_unreadable(client):
    response = client.post(
        "/api/games/upload",
        files={"file": ("games.pgn", PNG_BYTES, "application/octet-stream")},
    )

    assert response.status_code == 200
    assert response.json()["parsed"] == 0
