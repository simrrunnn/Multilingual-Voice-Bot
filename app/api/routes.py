"""Read-only FastAPI routes for retrieving completed/in-progress session data.

This API only reads from Supabase (via app.database.repository) — it never
writes. Writing happens exclusively from the voice agent as a call
progresses (see app.sessions.manager.SessionManager).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.database.client import SupabaseNotConfiguredError, is_configured
from app.database.repository import get_session, list_sessions
from app.sessions.models import CallSession

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "database_configured": is_configured()}


@router.get("/sessions")
def get_sessions(limit: int = 50) -> list[dict]:
    if not is_configured():
        raise HTTPException(status_code=503, detail="Supabase is not configured on this server.")
    try:
        return list_sessions(limit=limit)
    except Exception:
        logger.exception("Failed to list sessions")
        raise HTTPException(status_code=502, detail="Failed to read sessions from the database.")


@router.get("/sessions/{session_id}", response_model=CallSession)
def get_session_by_id(session_id: str) -> CallSession:
    if not is_configured():
        raise HTTPException(status_code=503, detail="Supabase is not configured on this server.")
    try:
        session = get_session(session_id)
    except SupabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        logger.exception("Failed to fetch session %s", session_id)
        raise HTTPException(status_code=502, detail="Failed to read session from the database.")

    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found.")
    return session
