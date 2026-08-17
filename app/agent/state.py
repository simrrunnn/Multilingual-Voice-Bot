"""Per-call state shared across the LiveKit `Agent`/`AgentSession` and its tools.

Passed as `AgentSession(userdata=...)`, reached inside hooks/tools via
`RunContext.userdata` or `self.session.userdata`. Composes `SessionManager` and `LanguageTracker`, both free of LiveKit
imports so they stay unit-testable without a LiveKit runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agent.language import DEFAULT_LANGUAGE, LanguageTracker
from app.sessions.manager import SessionManager


@dataclass
class AgentUserdata:
    session_manager: SessionManager
    language_tracker: LanguageTracker = field(default_factory=lambda: LanguageTracker(DEFAULT_LANGUAGE))
