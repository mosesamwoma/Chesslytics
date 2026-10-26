from __future__ import annotations

from typing import Iterable, Optional

import chess

from app.chess.lines import classify_line

LICHESS_TO_OURS = {
    "fork": "fork",
    "pin": "pin",
    "skewer": "skewer",
    "discoveredAttack": "discovered_attack",
    "trappedPiece": "trapped_piece",
    "backRankMate": "back_rank",
    "mate": "mate",
    "mateIn1": "mate",
    "mateIn2": "mate",
    "mateIn3": "mate",
    "mateIn4": "mate",
    "mateIn5": "mate",
    "sacrifice": "sacrifice",
    "intermezzo": "zwischenzug",
    "deflection": "deflection",
    "interference": "interference",
    "promotion": "promotion",
    "advancedPawn": "passed_pawn",
}
EVALUATED = (
    "mate",
    "back_rank",
    "fork",
    "pin",
    "skewer",
    "discovered_attack",
    "trapped_piece",
    "sacrifice",
    "zwischenzug",
    "deflection",
    "interference",
    "promotion",
)


def predict(fen: str, moves: list[str]) -> Optional[set[str]]:
    try:
        board = chess.Board(fen)
        parsed = [chess.Move.from_uci(item) for item in moves]
    except ValueError:
        return None
    if len(parsed) < 2 or parsed[0] not in board.legal_moves:
        return None
    board.push(parsed[0])
    return set(classify_line(board, parsed[1:])["themes"])


def actual(themes: str) -> set[str]:
    return {LICHESS_TO_OURS[item] for item in themes.split() if item in LICHESS_TO_OURS}


def evaluate(rows: Iterable[dict], limit: int = 5000) -> dict:
    counts = {theme: {"tp": 0, "fp": 0, "fn": 0} for theme in EVALUATED}
    used = skipped = 0
    for row in rows:
        if used >= limit:
            break
        predicted = predict(row.get("FEN", ""), (row.get("Moves") or "").split())
        if predicted is None:
            skipped += 1
            continue
        truth = actual(row.get("Themes") or "")
        used += 1
        for theme in EVALUATED:
            if theme in predicted and theme in truth:
                counts[theme]["tp"] += 1
            elif theme in predicted:
                counts[theme]["fp"] += 1
            elif theme in truth:
                counts[theme]["fn"] += 1
    report = []
    for theme in EVALUATED:
        tp, fp, fn = counts[theme]["tp"], counts[theme]["fp"], counts[theme]["fn"]
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and precision + recall
            else None
        )
        report.append(
            {
                "theme": theme,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": precision,
                "recall": recall,
                "f1": f1,
            }
        )
    return {"puzzles": used, "skipped": skipped, "themes": report}


def format_report(report: dict) -> str:
    def cell(value: Optional[float]) -> str:
        return "   n/a" if value is None else f"{value * 100:5.1f}%"

    lines = [
        f"Puzzles evaluated: {report['puzzles']} (skipped {report['skipped']})",
        "",
        f"{'theme':<20}{'TP':>6}{'FP':>6}{'FN':>6}{'precision':>11}{'recall':>9}{'F1':>8}",
    ]
    for row in report["themes"]:
        lines.append(
            f"{row['theme']:<20}{row['tp']:>6}{row['fp']:>6}{row['fn']:>6}"
            f"{cell(row['precision']):>11}{cell(row['recall']):>9}{cell(row['f1']):>8}"
        )
    lines.append("")
    lines.append(
        "Precision: of the puzzles the detector tagged, how many Lichess also tagged. "
        "Recall: of the puzzles Lichess tagged, how many the detector found."
    )
    return "\n".join(lines)
