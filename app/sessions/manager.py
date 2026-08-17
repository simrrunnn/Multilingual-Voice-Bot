"""In-call session orchestration.

`SessionManager` is the glue between the voice agent and the rest of the
application: it holds the authoritative in-memory `CallSession`, merges
incremental LLM extractions into it, invokes the deterministic
recommendation engine, and best-effort persists everything to Supabase as
it goes so a mid-call crash loses as little as possible.

Persistence is intentionally optional: if Supabase isn't configured (e.g.
running purely for local testing of the conversation/recommendation logic),
`SessionManager` degrades to an in-memory-only session instead of raising.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.database import repository
from app.database.client import SupabaseNotConfiguredError, is_configured
from app.insurance.models import CustomerRequirements, CustomerRequirementsUpdate, RecommendationResult
from app.insurance.recommender import recommend_policy
from app.sessions.models import CallSession, Speaker

logger = logging.getLogger(__name__)


def _merge_requirements(
    base: CustomerRequirements, update: CustomerRequirementsUpdate
) -> CustomerRequirements:
    """Merge a partial LLM extraction into the accumulated requirements.

    Scalars from `update` overwrite `base` only when present (non-None), so
    a turn that mentions nothing new leaves prior fields untouched.
    Family members are merged by relationship; conditions are unioned.
    """

    data = base.model_dump()
    update_data = update.model_dump(exclude_unset=False)

    for field in ("name", "age", "city", "family_size", "existing_insurance", "desired_coverage", "annual_budget"):
        if update_data.get(field) is not None:
            data[field] = update_data[field]

    if update.existing_conditions:
        merged = list(base.existing_conditions)
        for condition in update.existing_conditions:
            if condition not in merged:
                merged.append(condition)
        data["existing_conditions"] = merged

    if update.family_members:
        by_relationship = {m.relationship: m.model_dump() for m in base.family_members}
        for member in update.family_members:
            by_relationship[member.relationship] = member.model_dump()
        data["family_members"] = list(by_relationship.values())

    return CustomerRequirements.model_validate(data)


class SessionManager:
    """Owns a single call's state and mediates all persistence for it."""

    def __init__(self, session: Optional[CallSession] = None, persist: Optional[bool] = None):
        self.session: CallSession = session or CallSession()
        self.persist: bool = is_configured() if persist is None else persist
        if self.persist:
            try:
                repository.create_session(self.session)
            except SupabaseNotConfiguredError:
                logger.warning("Supabase not configured; session %s will not be persisted", self.session.id)
                self.persist = False

    def record_message(self, speaker: Speaker, text: str, language: str) -> None:
        self.session.add_message(speaker, text, language)
        if self.persist:
            repository.add_transcript_message(self.session.id, self.session.transcript[-1])

    def update_requirements(self, update: CustomerRequirementsUpdate) -> CustomerRequirements:
        self.session.requirements = _merge_requirements(self.session.requirements, update)
        if self.persist:
            repository.upsert_caller_profile(self.session.id, self.session.requirements)
        return self.session.requirements

    def generate_recommendation(self) -> RecommendationResult:
        recommendation = recommend_policy(self.session.requirements)
        self.session.recommendation = recommendation
        if self.persist:
            repository.save_recommendation(self.session.id, recommendation)
        return recommendation

    def complete(self) -> None:
        self.session.mark_completed()
        if self.persist:
            repository.update_session(self.session)

    def fail(self) -> None:
        self.session.mark_failed()
        if self.persist:
            repository.update_session(self.session)
