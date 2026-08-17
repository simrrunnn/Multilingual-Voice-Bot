"""Tests for the FastAPI read API (app.api.routes).

Supabase is fully mocked here so these tests run without any real Supabase
project or credentials, per the assignment's testing requirements.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import app.api.routes as routes
from app.insurance.models import CustomerRequirements, RecommendationResult
from app.main import app
from app.sessions.models import CallSession, SessionStatus, TranscriptMessage

client = TestClient(app)


def test_health_endpoint_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_sessions_list_returns_503_when_supabase_not_configured(monkeypatch):
    monkeypatch.setattr(routes, "is_configured", lambda: False)
    response = client.get("/sessions")
    assert response.status_code == 503


def test_get_session_returns_503_when_supabase_not_configured(monkeypatch):
    monkeypatch.setattr(routes, "is_configured", lambda: False)
    response = client.get("/sessions/some-id")
    assert response.status_code == 503


def test_sessions_list_returns_mocked_data(monkeypatch):
    monkeypatch.setattr(routes, "is_configured", lambda: True)
    monkeypatch.setattr(
        routes,
        "list_sessions",
        lambda limit=50: [
            {
                "id": "abc-123",
                "started_at": "2026-08-17T10:00:00+00:00",
                "ended_at": "2026-08-17T10:05:00+00:00",
                "status": "completed",
                "primary_language": "en",
                "detected_languages": ["en", "hi"],
            }
        ],
    )
    response = client.get("/sessions")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == "abc-123"


def test_get_session_not_found_returns_404(monkeypatch):
    monkeypatch.setattr(routes, "is_configured", lambda: True)
    monkeypatch.setattr(routes, "get_session", lambda session_id: None)
    response = client.get("/sessions/does-not-exist")
    assert response.status_code == 404


def test_get_session_returns_full_session(monkeypatch):
    session = CallSession(
        id="abc-123",
        livekit_session_id="room-1",
        started_at=datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 8, 17, 10, 5, tzinfo=timezone.utc),
        status=SessionStatus.COMPLETED,
        primary_language="hi",
        detected_languages=["en", "hi"],
        requirements=CustomerRequirements(name="Rahul", age=34, family_size=4, annual_budget=20000),
        recommendation=RecommendationResult(
            eligible=True,
            policy_id="health_plus",
            policy_name="Health Plus",
            coverage=1_000_000,
            annual_premium=22_000,
            reasons=["Matches requested coverage", "Within stated budget"],
        ),
        transcript=[
            TranscriptMessage(speaker="assistant", text="Hi there!", language="en"),
            TranscriptMessage(speaker="user", text="मुझे इंश्योरेंस चाहिए", language="hi"),
        ],
    )

    monkeypatch.setattr(routes, "is_configured", lambda: True)
    monkeypatch.setattr(routes, "get_session", lambda session_id: session)

    response = client.get("/sessions/abc-123")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "abc-123"
    assert body["requirements"]["name"] == "Rahul"
    assert body["recommendation"]["policy_id"] == "health_plus"
    assert len(body["transcript"]) == 2
    assert body["detected_languages"] == ["en", "hi"]
