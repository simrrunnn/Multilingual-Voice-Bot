"""Runtime session domain models.

These model an in-progress or completed call. They are the shared shape
used by the voice agent (which builds them up turn by turn), the database
repository layer (which persists/reconstructs them from Supabase), and the
FastAPI read API (which returns them as-is).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from app.insurance.models import CustomerRequirements, RecommendationResult


class SessionStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


Speaker = Literal["user", "assistant"]


class TranscriptMessage(BaseModel):
    speaker: Speaker
    text: str
    language: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CallSession(BaseModel):
    """The full state of a single phone call, from greeting to hangup."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    livekit_session_id: Optional[str] = None
    call_id: Optional[str] = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None
    status: SessionStatus = SessionStatus.IN_PROGRESS
    primary_language: str = "en"
    detected_languages: list[str] = Field(default_factory=lambda: ["en"])
    requirements: CustomerRequirements = Field(default_factory=CustomerRequirements)
    recommendation: Optional[RecommendationResult] = None
    transcript: list[TranscriptMessage] = Field(default_factory=list)

    def add_message(self, speaker: Speaker, text: str, language: str) -> None:
        self.transcript.append(TranscriptMessage(speaker=speaker, text=text, language=language))
        if language not in self.detected_languages:
            self.detected_languages.append(language)

    def mark_completed(self) -> None:
        self.status = SessionStatus.COMPLETED
        self.ended_at = datetime.now(timezone.utc)

    def mark_failed(self) -> None:
        self.status = SessionStatus.FAILED
        self.ended_at = datetime.now(timezone.utc)
