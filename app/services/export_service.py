from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Optional

from app.chess.motifs import summarise

FORMATS = ("json", "csv", "jsonl")

MISTAKE_COLUMNS = [
    "game_id",
    "game_key",
    "move_number",
    "ply",
    "color",
    "player",
    "opponent",
    "played_move",
    "best_move",
    "eval_before",
    "eval_after",
    "loss",
    "loss_cp",
    "winpct_before",
    "winpct_after",
    "severity",
    "category",
    "category_basis",
    "phase",
    "opening",
    "in_time_pressure",
    "time_remaining",
    "game_decided",
    "motifs_allowed",
    "hung_piece",
    "hung_piece_square",
    "hung_piece_see",
    "fen",
    "played_uci",
    "best_move_uci",
    "in_book",
    "book_move",
    "agreed",
    "verified_loss",
    "verified_by",
]


def format_for(path: str) -> str:
    suffix = Path(path).suffix.lower().lstrip(".")
    if suffix == "jsonl":
        return "jsonl"
    if suffix == "csv":
        return "csv"
    return "json"


def mistake_row(record: dict) -> dict:
    facts = record.get("facts") or {}
    hung = facts.get("hung_piece") or {}
    return {
        "game_id": record.get("game_id"),
        "game_key": record.get("game_key"),
        "move_number": record.get("move_number"),
        "ply": record.get("ply"),
        "color": record.get("color"),
        "player": record.get("player"),
        "opponent": record.get("opponent"),
        "played_move": record.get("played_move"),
        "best_move": record.get("best_move"),
        "eval_before": record.get("eval_before"),
        "eval_after": record.get("eval_after"),
        "loss": record.get("loss"),
        "loss_cp": record.get("loss_cp"),
        "winpct_before": record.get("winpct_before"),
        "winpct_after": record.get("winpct_after"),
        "severity": record.get("severity"),
        "category": record.get("category"),
        "category_basis": record.get("category_basis"),
        "phase": record.get("phase"),
        "opening": record.get("opening"),
        "in_time_pressure": record.get("in_time_pressure"),
        "time_remaining": record.get("time_remaining"),
        "game_decided": record.get("game_decided"),
        "motifs_allowed": "; ".join(summarise(facts.get("motifs_allowed") or [])),
        "hung_piece": hung.get("name"),
        "hung_piece_square": hung.get("square"),
        "hung_piece_see": hung.get("see_pawns"),
        "fen": record.get("fen"),
        "played_uci": record.get("played_uci"),
        "best_move_uci": record.get("best_move_uci"),
        "in_book": record.get("in_book"),
        "book_move": record.get("book_move"),
        "agreed": record.get("agreed"),
        "verified_loss": record.get("verified_loss"),
        "verified_by": record.get("verified_by"),
    }


def mistake_rows(report: dict) -> list[dict]:
    return [mistake_row(record) for record in (report.get("mistakes") or [])]


def write_csv(report: dict, path: Path) -> int:
    rows = mistake_rows(report)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MISTAKE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def write_jsonl(report: dict, path: Path) -> int:
    rows = mistake_rows(report)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str) + "\n")
    return len(rows)


def write_json(report: dict, path: Path) -> int:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, default=str)
    return len(report.get("mistakes") or [])


WRITERS = {"json": write_json, "csv": write_csv, "jsonl": write_jsonl}


def write_report(report: dict, path: str, fmt: Optional[str] = None) -> tuple[str, int]:
    chosen = (fmt or format_for(path)).lower()
    if chosen not in WRITERS:
        raise ValueError(f"unknown export format {chosen!r}; expected one of {', '.join(FORMATS)}")
    target = Path(path).expanduser()
    if target.parent != Path(""):
        target.parent.mkdir(parents=True, exist_ok=True)
    count = WRITERS[chosen](report, target)
    return chosen, count


def render(report: dict, fmt: str) -> str:
    chosen = fmt.lower()
    if chosen == "csv":
        from io import StringIO

        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=MISTAKE_COLUMNS)
        writer.writeheader()
        writer.writerows(mistake_rows(report))
        return buffer.getvalue()
    if chosen == "jsonl":
        return "".join(
            json.dumps(row, default=str) + "\n" for row in mistake_rows(report)
        )
    if chosen == "json":
        return json.dumps(report, indent=2, default=str)
    raise ValueError(f"unknown export format {chosen!r}; expected one of {', '.join(FORMATS)}")


def content_type(fmt: str) -> str:
    return {
        "csv": "text/csv",
        "jsonl": "application/x-ndjson",
        "json": "application/json",
    }[fmt.lower()]


def extension(fmt: str) -> str:
    return {"csv": "csv", "jsonl": "jsonl", "json": "json"}[fmt.lower()]
