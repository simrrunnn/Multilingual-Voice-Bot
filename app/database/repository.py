"""Supabase-backed persistence for call sessions.

This is the only module that issues Supabase queries — the voice agent and
the API never touch `supabase-py` directly, they go through the functions
below. All writes are defensive: a database hiccup during a live call must
never crash the agent (see `README.md` "Session Management"), so every
write is wrapped and logged rather than raised.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.database.client import get_supabase_client
from app.insurance.models import CustomerRequirements, RecommendationResult
from app.sessions.models import CallSession, SessionStatus, TranscriptMessage

logger = logging.getLogger(__name__)


def _safe_execute(description: str, fn):
    """Run a Supabase call, swallowing and logging any failure.

    Returns the query result on success, or None on failure. Used for
    writes made mid-call, where raising would tear down the whole session.
    """

    try:
        return fn()
    except Exception:  # noqa: BLE001 - deliberately broad; this must never propagate
        logger.exception("Supabase write failed: %s", description)
        return None


def create_session(session: CallSession) -> None:
    client = get_supabase_client()
    _safe_execute(
        "create_session",
        lambda: client.table("sessions")
        .insert(
            {
                "id": session.id,
                "livekit_session_id": session.livekit_session_id,
                "call_id": session.call_id,
                "started_at": session.started_at.isoformat(),
                "ended_at": session.ended_at.isoformat() if session.ended_at else None,
                "status": session.status.value,
                "primary_language": session.primary_language,
                "detected_languages": session.detected_languages,
            }
        )
        .execute(),
    )


def update_session(session: CallSession) -> None:
    client = get_supabase_client()
    _safe_execute(
        "update_session",
        lambda: client.table("sessions")
        .update(
            {
                "ended_at": session.ended_at.isoformat() if session.ended_at else None,
                "status": session.status.value,
                "primary_language": session.primary_language,
                "detected_languages": session.detected_languages,
            }
        )
        .eq("id", session.id)
        .execute(),
    )


def upsert_caller_profile(session_id: str, requirements: CustomerRequirements) -> None:
    client = get_supabase_client()
    payload = {
        "session_id": session_id,
        "name": requirements.name,
        "age": requirements.age,
        "city": requirements.city,
        "family_size": requirements.family_size,
        "existing_conditions": requirements.existing_conditions,
        "existing_insurance": requirements.existing_insurance,
        "desired_coverage": requirements.desired_coverage,
        "annual_budget": requirements.annual_budget,
        "family_members": [m.model_dump() for m in requirements.family_members],
    }
    _safe_execute(
        "upsert_caller_profile",
        lambda: client.table("caller_profiles").upsert(payload, on_conflict="session_id").execute(),
    )


def save_recommendation(session_id: str, recommendation: RecommendationResult) -> None:
    if not recommendation.eligible:
        return
    client = get_supabase_client()
    payload = {
        "session_id": session_id,
        "policy_id": recommendation.policy_id,
        "policy_name": recommendation.policy_name,
        "coverage": recommendation.coverage,
        "annual_premium": recommendation.annual_premium,
        "reasons": recommendation.reasons,
    }
    _safe_execute(
        "save_recommendation",
        lambda: client.table("recommendations").insert(payload).execute(),
    )


def add_transcript_message(session_id: str, message: TranscriptMessage) -> None:
    client = get_supabase_client()
    payload = {
        "session_id": session_id,
        "speaker": message.speaker,
        "text": message.text,
        "language": message.language,
        "timestamp": message.timestamp.isoformat(),
    }
    _safe_execute(
        "add_transcript_message",
        lambda: client.table("transcript_messages").insert(payload).execute(),
    )


def get_session(session_id: str) -> Optional[CallSession]:
    """Reconstruct a full CallSession from Supabase, or None if not found.

    Unlike the write helpers, this is allowed to raise — the API layer
    turns failures into an HTTP error response rather than silently hiding
    them from a client explicitly asking to read data.
    """

    client = get_supabase_client()

    session_res = client.table("sessions").select("*").eq("id", session_id).limit(1).execute()
    if not session_res.data:
        return None
    row = session_res.data[0]

    profile_res = (
        client.table("caller_profiles").select("*").eq("session_id", session_id).limit(1).execute()
    )
    profile_row = profile_res.data[0] if profile_res.data else {}

    rec_res = (
        client.table("recommendations")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rec_row = rec_res.data[0] if rec_res.data else None

    transcript_res = (
        client.table("transcript_messages")
        .select("*")
        .eq("session_id", session_id)
        .order("timestamp")
        .execute()
    )

    requirements = CustomerRequirements(
        name=profile_row.get("name"),
        age=profile_row.get("age"),
        city=profile_row.get("city"),
        family_size=profile_row.get("family_size"),
        existing_conditions=profile_row.get("existing_conditions") or [],
        existing_insurance=profile_row.get("existing_insurance"),
        desired_coverage=profile_row.get("desired_coverage"),
        annual_budget=profile_row.get("annual_budget"),
        family_members=profile_row.get("family_members") or [],
    )

    recommendation = None
    if rec_row:
        recommendation = RecommendationResult(
            eligible=True,
            policy_id=rec_row.get("policy_id"),
            policy_name=rec_row.get("policy_name"),
            coverage=rec_row.get("coverage"),
            annual_premium=rec_row.get("annual_premium"),
            reasons=rec_row.get("reasons") or [],
        )

    transcript = [
        TranscriptMessage(
            speaker=m["speaker"],
            text=m["text"],
            language=m["language"],
            timestamp=m["timestamp"],
        )
        for m in transcript_res.data
    ]

    return CallSession(
        id=row["id"],
        livekit_session_id=row.get("livekit_session_id"),
        call_id=row.get("call_id"),
        started_at=row["started_at"],
        ended_at=row.get("ended_at"),
        status=SessionStatus(row.get("status", "in_progress")),
        primary_language=row.get("primary_language", "en"),
        detected_languages=row.get("detected_languages") or ["en"],
        requirements=requirements,
        recommendation=recommendation,
        transcript=transcript,
    )


def list_sessions(limit: int = 50) -> list[dict]:
    """Return lightweight summaries of recent sessions (no transcript/profile join)."""

    client = get_supabase_client()
    res = (
        client.table("sessions")
        .select("id,started_at,ended_at,status,primary_language,detected_languages")
        .order("started_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data
