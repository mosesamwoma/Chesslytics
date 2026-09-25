from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    white: Mapped[str] = mapped_column(String(128), default="")
    black: Mapped[str] = mapped_column(String(128), default="")
    result: Mapped[str] = mapped_column(String(16), default="")
    date: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    event: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    site: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    eco: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    opening: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    variation: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    time_control: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    white_elo: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    black_elo: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    pgn: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    analyzed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    analyzed_depth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    moves: Mapped[list["Move"]] = relationship(
        back_populates="game", cascade="all, delete-orphan", order_by="Move.ply"
    )
    mistakes: Mapped[list["Mistake"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )


class Move(Base):
    __tablename__ = "moves"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    ply: Mapped[int] = mapped_column(Integer, index=True)
    move_number: Mapped[int] = mapped_column(Integer)
    color: Mapped[str] = mapped_column(String(8))
    san: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    uci: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    fen_before: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fen_after: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    eval_before_cp: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    eval_after_cp: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    eval_before_mate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    eval_after_mate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    loss_cp: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    winpct_before: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    winpct_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    best_move_uci: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    best_move_san: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    depth_reached: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    phase: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    clock_before: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    clock_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    material_before: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    material_after: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_capture: Mapped[bool] = mapped_column(Boolean, default=False)
    is_check: Mapped[bool] = mapped_column(Boolean, default=False)
    is_mate: Mapped[bool] = mapped_column(Boolean, default=False)
    is_promotion: Mapped[bool] = mapped_column(Boolean, default=False)
    is_castling: Mapped[bool] = mapped_column(Boolean, default=False)
    is_en_passant: Mapped[bool] = mapped_column(Boolean, default=False)
    best_move_was_capture: Mapped[bool] = mapped_column(Boolean, default=False)
    best_move_was_check: Mapped[bool] = mapped_column(Boolean, default=False)
    best_move_was_mate: Mapped[bool] = mapped_column(Boolean, default=False)
    hanging_after: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    king_safety_after: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    game: Mapped["Game"] = relationship(back_populates="moves")


class Mistake(Base):
    __tablename__ = "mistakes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    ply: Mapped[int] = mapped_column(Integer)
    move_number: Mapped[int] = mapped_column(Integer)
    color: Mapped[str] = mapped_column(String(8))
    player: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    opponent: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    played_move: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    best_move: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    fen: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    eval_before: Mapped[float] = mapped_column(Float, default=0.0)
    eval_after: Mapped[float] = mapped_column(Float, default=0.0)
    loss: Mapped[float] = mapped_column(Float, index=True)
    loss_cp: Mapped[int] = mapped_column(Integer)
    winpct_before: Mapped[float] = mapped_column(Float, default=0.0)
    winpct_after: Mapped[float] = mapped_column(Float, default=0.0)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    category_basis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    phase: Mapped[str] = mapped_column(String(16), index=True)
    opening: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    in_time_pressure: Mapped[bool] = mapped_column(Boolean, default=False)
    time_remaining: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    game_decided: Mapped[bool] = mapped_column(Boolean, default=False)
    facts: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    game: Mapped["Game"] = relationship(back_populates="mistakes")


class PlayerProfile(Base):
    __tablename__ = "player_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    color: Mapped[str] = mapped_column(String(8), default="both")
    games_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    moves_scored: Mapped[int] = mapped_column(Integer, default=0)
    moves_failed: Mapped[int] = mapped_column(Integer, default=0)
    mistake_count: Mapped[int] = mapped_column(Integer, default=0)
    average_loss: Mapped[float] = mapped_column(Float, default=0.0)
    depth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    engine: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    patterns: Mapped[list["Pattern"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class Pattern(Base):
    __tablename__ = "patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32), index=True)
    key: Mapped[str] = mapped_column(String(255), index=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    games: Mapped[int] = mapped_column(Integer, default=0)
    recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    profile: Mapped[Optional["PlayerProfile"]] = relationship(back_populates="patterns")
