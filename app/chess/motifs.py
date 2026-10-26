from __future__ import annotations

from typing import Optional

import chess

from app.chess.pieces import PIECE_NAMES, see_value
from app.chess.see import best_exchange, static_exchange, victim_value

DIRECTIONS = {
    chess.BISHOP: ((-1, -1), (-1, 1), (1, -1), (1, 1)),
    chess.ROOK: ((-1, 0), (1, 0), (0, -1), (0, 1)),
    chess.QUEEN: (
        (-1, -1),
        (-1, 1),
        (1, -1),
        (1, 1),
        (-1, 0),
        (1, 0),
        (0, -1),
        (0, 1),
    ),
}

SLIDERS = tuple(DIRECTIONS)


def _with_side_to_move(
    board: chess.Board, color: chess.Color
) -> Optional[chess.Board]:
    probe = board.copy(stack=False)
    if probe.turn == color:
        return probe
    if probe.is_check() or probe.is_game_over():
        return None
    probe.push(chess.Move.null())
    return probe


def describe(piece: chess.Piece) -> str:
    return PIECE_NAMES[piece.piece_type]


def _names(*squares: Optional[int]) -> list[str]:
    names: list[str] = []
    for square in squares:
        if square is None:
            continue
        name = chess.square_name(square)
        if name not in names:
            names.append(name)
    return names


def mate_threats(board: chess.Board) -> list[dict]:
    found = []
    for move in board.legal_moves:
        if not board.gives_check(move):
            continue
        board.push(move)
        try:
            if not board.is_checkmate():
                continue
            king_square = board.king(board.turn)
            back_rank = (
                king_square is not None
                and chess.square_rank(king_square) in (0, 7)
                and all(
                    chess.square_rank(square) == chess.square_rank(king_square)
                    for square in board.checkers()
                )
            )
        finally:
            board.pop()
        found.append(
            {
                "kind": "mate",
                "move": move.uci(),
                "back_rank": back_rank,
                "at": chess.square_name(move.to_square),
                "squares": _names(
                    move.from_square,
                    move.to_square,
                    board.king(not board.turn),
                ),
            }
        )
    return found


def forks(board: chess.Board) -> list[dict]:
    found = []

    for move in board.legal_moves:
        board.push(move)
        try:
            piece = board.piece_at(move.to_square)
            if piece is None:
                continue
            attacker = see_value(piece)
            gives_check = board.is_check()

            victims = []
            for square in board.attacks(move.to_square):
                target = board.piece_at(square)
                if target is None or target.color == piece.color:
                    continue
                if target.piece_type == chess.KING:
                    values = 0
                else:
                    defended = bool(board.attackers(not piece.color, square))
                    if defended and see_value(target) <= attacker:
                        continue
                    values = see_value(target)
                victims.append(
                    {
                        "square": chess.square_name(square),
                        "piece": target.symbol(),
                        "name": describe(target),
                        "value": values,
                    }
                )

            if len(victims) < 2:
                continue

            if gives_check:
                safe = True
            else:
                cost, _ = best_exchange(board, move.to_square)
                safe = cost == 0
            if not safe:
                continue

            found.append(
                {
                    "kind": "fork",
                    "move": move.uci(),
                    "at": chess.square_name(move.to_square),
                    "piece": piece.symbol(),
                    "name": describe(piece),
                    "check": gives_check,
                    "victims": victims,
                    "squares": _names(move.from_square, move.to_square)
                    + [victim["square"] for victim in victims],
                }
            )
        finally:
            board.pop()
    return found


def _ray_targets(
    board: chess.Board, square: chess.Square, piece_type: int
) -> list[tuple[chess.Square, chess.Square]]:
    pairs = []
    file_index = chess.square_file(square)
    rank_index = chess.square_rank(square)

    for file_step, rank_step in DIRECTIONS[piece_type]:
        seen: list[chess.Square] = []
        file_cursor = file_index + file_step
        rank_cursor = rank_index + rank_step
        while 0 <= file_cursor <= 7 and 0 <= rank_cursor <= 7:
            cursor = chess.square(file_cursor, rank_cursor)
            if board.piece_at(cursor) is not None:
                seen.append(cursor)
                if len(seen) == 2:
                    break
            file_cursor += file_step
            rank_cursor += rank_step
        if len(seen) == 2:
            pairs.append((seen[0], seen[1]))
    return pairs


def pins_and_skewers(board: chess.Board) -> list[dict]:
    found = []
    ours = board.turn

    for square, piece in board.piece_map().items():
        if piece.color != ours or piece.piece_type not in SLIDERS:
            continue
        for front, back in _ray_targets(board, square, piece.piece_type):
            front_piece = board.piece_at(front)
            back_piece = board.piece_at(back)
            if front_piece.color == ours or back_piece.color == ours:
                continue

            detail = {
                "squares": _names(square, front, back),
                "attacker": chess.square_name(square),
                "attacker_piece": piece.symbol(),
                "front": chess.square_name(front),
                "front_piece": front_piece.symbol(),
                "back": chess.square_name(back),
                "back_piece": back_piece.symbol(),
            }

            if back_piece.piece_type == chess.KING:
                found.append({**detail, "kind": "pin", "absolute": True})
            elif see_value(back_piece) > see_value(front_piece):
                found.append({**detail, "kind": "pin", "absolute": False})
            elif see_value(front_piece) > see_value(back_piece):
                found.append({**detail, "kind": "skewer", "absolute": False})

    return found


def detect_motifs(board: chess.Board, color: chess.Color) -> list[dict]:
    probe = _with_side_to_move(board, color)
    if probe is None:
        return []
    motifs = mate_threats(probe)
    motifs.extend(forks(probe))
    motifs.extend(pins_and_skewers(probe))
    for motif in motifs:
        motif["detail"] = describe_motif(motif)
    return motifs


def motif_kinds(motifs: list[dict]) -> list[str]:
    order = ("mate", "fork", "pin", "skewer")
    present = {motif["kind"] for motif in motifs}
    return [kind for kind in order if kind in present]


def summarise(motifs: list[dict]) -> list[str]:
    return [describe_motif(motif) for motif in motifs]


def describe_motif(motif: dict) -> str:
    if motif["kind"] == "mate":
        where = " on the back rank" if motif.get("back_rank") else ""
        return f"mate in one{where} with {motif['move']}"
    if motif["kind"] == "fork":
        names = ", ".join(victim["name"] for victim in motif["victims"])
        check = " with check" if motif.get("check") else ""
        return f"fork {motif['move']}{check} winning {names}"
    if motif["kind"] == "pin":
        kind = "absolute" if motif.get("absolute") else "relative"
        return (
            f"{kind} pin: {motif['front_piece']} on {motif['front']} "
            f"held by {motif['attacker_piece']} on {motif['attacker']}"
        )
    if motif["kind"] == "skewer":
        return (
            f"skewer: {motif['attacker_piece']} on {motif['attacker']} takes "
            f"{motif['front_piece']} on {motif['front']}, exposing "
            f"{motif['back_piece']} on {motif['back']}"
        )
    if motif["kind"] == "discovered_attack":
        what = "discovered check" if motif.get("check") else "discovered attack"
        return (
            f"{what} with {motif['move']}: {motif['slider_piece']} on {motif['slider']} "
            f"now hits {motif['target_piece']} on {motif['target']}"
        )
    if motif["kind"] == "trapped_piece":
        return f"trapped {motif['name']} on {motif['square']}: no safe square to go to"
    if motif["kind"] == "back_rank_weakness":
        return f"back-rank weakness: king on {motif['king']} has no escape square"
    if motif["kind"] == "promotion":
        return f"promotion with {motif['move']}"
    if motif["kind"] == "passed_pawn":
        return f"advanced passed pawn on {motif['square']}"
    if motif["kind"] == "overloaded_defender":
        guarded = ", ".join(motif["guards"])
        return f"overloaded defender: {motif['name']} on {motif['square']} guards {guarded}"
    if motif["kind"] == "remove_defender":
        return (
            f"remove the defender: {motif['move']} takes the {motif['name']} that guards "
            f"{motif['target_piece']} on {motif['target']}"
        )
    return motif["kind"]


def _significant(piece: chess.Piece) -> bool:
    return piece.piece_type != chess.PAWN and see_value(piece) >= 300


def _slider_pairs(
    board: chess.Board, color: chess.Color, skip: Optional[chess.Square]
) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for square, piece in board.piece_map().items():
        if piece.color != color or piece.piece_type not in SLIDERS or square == skip:
            continue
        for target in board.attacks(square):
            victim = board.piece_at(target)
            if victim is None or victim.color == color:
                continue
            pairs.add((square, target))
    return pairs


def discovered_attacks(board: chess.Board) -> list[dict]:
    found = []
    ours = board.turn
    for move in board.legal_moves:
        mover = board.piece_at(move.from_square)
        if mover is None:
            continue
        before = _slider_pairs(board, ours, move.from_square)
        captured_here = board.is_capture(move)
        gives_check = board.gives_check(move)
        board.push(move)
        try:
            after = _slider_pairs(board, ours, move.to_square)
            attacks_valuable = any(
                (victim := board.piece_at(square)) is not None
                and victim.color != ours
                and _significant(victim)
                for square in board.attacks(move.to_square)
            )
            opened = []
            for slider, target in after - before:
                victim = board.piece_at(target)
                slider_piece = board.piece_at(slider)
                if victim is None or slider_piece is None:
                    continue
                if victim.piece_type == chess.KING:
                    opened.append((slider, target, victim, slider_piece, True))
                elif _significant(victim) and (
                    not board.attackers(not ours, target)
                    or see_value(victim) > see_value(slider_piece)
                ):
                    if captured_here or gives_check or attacks_valuable:
                        opened.append((slider, target, victim, slider_piece, False))
        finally:
            board.pop()
        for slider, target, victim, slider_piece, is_check in opened:
            found.append(
                {
                    "kind": "discovered_attack",
                    "move": move.uci(),
                    "check": is_check,
                    "slider": chess.square_name(slider),
                    "slider_piece": slider_piece.symbol(),
                    "target": chess.square_name(target),
                    "target_piece": victim.symbol(),
                    "squares": _names(move.from_square, move.to_square, slider, target),
                }
            )
    return found


def trapped_pieces(board: chess.Board, color: chess.Color) -> list[dict]:
    attacker_probe = _with_side_to_move(board, not color)
    owner_probe = _with_side_to_move(board, color)
    if attacker_probe is None or owner_probe is None:
        return []
    found = []
    for square, piece in board.piece_map().items():
        if piece.color != color or piece.piece_type in (chess.PAWN, chess.KING):
            continue
        attackers = attacker_probe.attackers(not color, square)
        if not attackers:
            continue
        cheapest = min(see_value(attacker_probe.piece_at(a)) for a in attackers)
        threatened = best_exchange(attacker_probe, square)[0] > 0 or cheapest < see_value(piece)
        if not threatened:
            continue

        rescued = False
        safe_squares = 0
        for move in owner_probe.legal_moves:
            if move.to_square in attackers and owner_probe.is_capture(move):
                if static_exchange(owner_probe, move) >= 0:
                    rescued = True
                    break
            if move.from_square != square:
                continue
            captured = victim_value(owner_probe, move) if owner_probe.is_capture(move) else 0
            owner_probe.push(move)
            try:
                lost = best_exchange(owner_probe, move.to_square)[0]
            finally:
                owner_probe.pop()
            if captured - lost >= 0:
                safe_squares += 1
        if rescued or safe_squares:
            continue
        found.append(
            {
                "kind": "trapped_piece",
                "square": chess.square_name(square),
                "piece": piece.symbol(),
                "name": describe(piece),
                "attackers": [chess.square_name(a) for a in attackers],
                "squares": _names(square, *attackers),
            }
        )
    return found


def back_rank_weakness(board: chess.Board, color: chess.Color) -> list[dict]:
    king = board.king(color)
    if king is None or board.is_check():
        return []
    back = 0 if color == chess.WHITE else 7
    if chess.square_rank(king) != back:
        return []
    forward_rank = back + (1 if color == chess.WHITE else -1)
    blockers = []
    for file_index in range(chess.square_file(king) - 1, chess.square_file(king) + 2):
        if not 0 <= file_index <= 7:
            continue
        square = chess.square(file_index, forward_rank)
        occupant = board.piece_at(square)
        if occupant is None or occupant.color != color:
            return []
        blockers.append(square)
    if not blockers:
        return []
    attacker = _with_side_to_move(board, not color)
    if attacker is None:
        return []
    checkers = []
    for move in attacker.legal_moves:
        piece = attacker.piece_at(move.from_square)
        if piece is None or piece.piece_type not in (chess.ROOK, chess.QUEEN):
            continue
        if chess.square_rank(move.to_square) != back or not attacker.gives_check(move):
            continue
        checkers.append(move.from_square)
    if not checkers:
        return []
    return [
        {
            "kind": "back_rank_weakness",
            "king": chess.square_name(king),
            "color": "white" if color == chess.WHITE else "black",
            "squares": _names(king, *blockers, *checkers[:2]),
        }
    ]


def _is_passed(board: chess.Board, square: chess.Square, color: chess.Color) -> bool:
    file_index = chess.square_file(square)
    rank_index = chess.square_rank(square)
    step = 1 if color == chess.WHITE else -1
    for other_square, piece in board.piece_map().items():
        if piece.piece_type != chess.PAWN or piece.color == color:
            continue
        if abs(chess.square_file(other_square) - file_index) > 1:
            continue
        ahead = (chess.square_rank(other_square) - rank_index) * step
        if ahead > 0:
            return False
    return True


def promotion_threats(board: chess.Board) -> list[dict]:
    found = []
    ours = board.turn
    for move in board.legal_moves:
        if move.promotion != chess.QUEEN:
            continue
        if static_exchange(board, move) < 0:
            continue
        found.append(
            {
                "kind": "promotion",
                "move": move.uci(),
                "at": chess.square_name(move.to_square),
                "squares": _names(move.from_square, move.to_square),
            }
        )
    promoting_from = {item["squares"][0] for item in found}
    for square, piece in board.piece_map().items():
        if piece.color != ours or piece.piece_type != chess.PAWN:
            continue
        relative = chess.square_rank(square) if ours == chess.WHITE else 7 - chess.square_rank(square)
        if relative < 5 or chess.square_name(square) in promoting_from:
            continue
        if not _is_passed(board, square, ours):
            continue
        found.append(
            {
                "kind": "passed_pawn",
                "square": chess.square_name(square),
                "rank": relative + 1,
                "squares": _names(square),
            }
        )
    return found


def overloaded_defenders(board: chess.Board) -> list[dict]:
    ours = board.turn
    found = []
    for defender_square, defender in board.piece_map().items():
        if defender.color == ours or defender.piece_type == chess.KING:
            continue
        guards = []
        for target_square in board.attacks(defender_square):
            target = board.piece_at(target_square)
            if target is None or target.color == ours or target.piece_type == chess.KING:
                continue
            if not board.is_attacked_by(ours, target_square):
                continue
            if best_exchange(board, target_square)[0] > 0:
                continue
            without = board.copy(stack=False)
            without.remove_piece_at(defender_square)
            if best_exchange(without, target_square)[0] > 0:
                guards.append(target_square)
        if len(guards) >= 2:
            found.append(
                {
                    "kind": "overloaded_defender",
                    "square": chess.square_name(defender_square),
                    "piece": defender.symbol(),
                    "name": describe(defender),
                    "guards": [chess.square_name(g) for g in guards],
                    "squares": _names(defender_square, *guards),
                }
            )
    return found


def remove_defender(board: chess.Board) -> list[dict]:
    ours = board.turn
    found = []
    for move in board.legal_moves:
        if not board.is_capture(move) or board.is_en_passant(move):
            continue
        defender = board.piece_at(move.to_square)
        if defender is None or defender.piece_type == chess.KING:
            continue
        if static_exchange(board, move) < -50:
            continue
        candidates = []
        for target_square in board.attacks(move.to_square):
            target = board.piece_at(target_square)
            if target is None or target.color == ours or target.piece_type == chess.KING:
                continue
            if target_square == move.to_square or not board.is_attacked_by(ours, target_square):
                continue
            if best_exchange(board, target_square)[0] > 0:
                continue
            candidates.append(target_square)
        if not candidates:
            continue
        board.push(move)
        try:
            probe = _with_side_to_move(board, ours)
            if probe is None:
                continue
            for target_square in candidates:
                if best_exchange(probe, target_square)[0] > 0:
                    target = probe.piece_at(target_square)
                    found.append(
                        {
                            "kind": "remove_defender",
                            "move": move.uci(),
                            "name": describe(defender),
                            "target": chess.square_name(target_square),
                            "target_piece": target.symbol() if target else "?",
                            "squares": _names(move.from_square, move.to_square, target_square),
                        }
                    )
        finally:
            board.pop()
    return found


def detect_extended(board: chess.Board, color: chess.Color) -> list[dict]:
    probe = _with_side_to_move(board, color)
    if probe is None:
        return []
    motifs = discovered_attacks(probe)
    motifs.extend(promotion_threats(probe))
    motifs.extend(overloaded_defenders(probe))
    motifs.extend(remove_defender(probe))
    for motif in motifs:
        motif["detail"] = describe_motif(motif)
    return motifs


def detect_weaknesses(board: chess.Board, color: chess.Color) -> list[dict]:
    found = trapped_pieces(board, color)
    found.extend(back_rank_weakness(board, color))
    for item in found:
        item["detail"] = describe_motif(item)
    return found
