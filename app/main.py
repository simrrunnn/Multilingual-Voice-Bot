"""FastAPI application entrypoint.

Run with: uvicorn app.main:app --reload

This process only serves the read API (GET /health, /sessions,
/sessions/{id}). The voice agent is a separate long-running worker process
started via `python -m app.agent.agent start` — see README "Local
Development".
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(
    title="Multilingual Health Insurance Voice Bot API",
    description="Read API for retrieving demo voice-call session transcripts and recommendations.",
    version="0.1.0",
)

app.include_router(router)
