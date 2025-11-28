"""Pydantic models describing structured LLM outputs."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field, conlist


class NarrationPayload(BaseModel):
    """Structured payload enforced via OpenAI structured outputs."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    game_last_objects: conlist(str, min_length=5, max_length=5) = Field(
        alias="game-last-objects",
        description="One item per object: 'object — room — actions'",
    )
    game_room_path: str = Field(alias="game-room-path")
    game_last_changes: conlist(str, min_length=5, max_length=5) = Field(
        alias="game-last-changes",
        description="One item per change: 'change — trigger'",
    )
    game_intent: str = Field(alias="game-intent")
    game_meta_intent: str = Field(alias="game-meta-intent")
    hidden_next_command: str = Field(alias="hidden-next-command")
    hidden_next_command_confidence: int = Field(
        alias="hidden-next-command-confidence",
        ge=0,
        le=100,
    )
    narration: str = Field(alias="narration")


__all__ = ["NarrationPayload"]
