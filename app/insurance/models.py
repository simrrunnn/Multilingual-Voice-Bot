"""Pydantic models for the insurance domain.

These models are shared by the deterministic recommendation engine
(`recommender.py`) and by the conversational layer, which uses them to
validate whatever structured data the LLM extracts from the caller before
it is ever trusted.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Policy(BaseModel):
    """A single fictional demo insurance policy loaded from policies.json."""

    id: str
    name: str
    description: str
    coverage: int = Field(gt=0)
    annual_premium: int = Field(gt=0)
    max_family_size: int = Field(gt=0)
    max_insured_age: int = Field(gt=0)
    covers_pre_existing_conditions: bool
    notes: str = ""


class PolicyCatalogue(BaseModel):
    """The full contents of policies.json."""

    disclaimer: str
    policies: list[Policy]


class FamilyMember(BaseModel):
    """A single family member the caller wants to insure alongside themselves."""

    relationship: str
    age: Optional[int] = Field(default=None, ge=0, le=120)


class CustomerRequirements(BaseModel):
    """Structured caller information, accumulated over the conversation.

    Every field is optional because information arrives incrementally as the
    caller speaks. `sessions/manager.py` merges partial updates into this
    model turn by turn; `recommender.py` reads the final (or best-so-far)
    snapshot to produce a recommendation.
    """

    name: Optional[str] = None
    age: Optional[int] = Field(default=None, ge=0, le=120)
    city: Optional[str] = None
    family_size: Optional[int] = Field(default=None, ge=1, le=20)
    family_members: list[FamilyMember] = Field(default_factory=list)
    existing_conditions: list[str] = Field(default_factory=list)
    existing_insurance: Optional[bool] = None
    desired_coverage: Optional[int] = Field(default=None, ge=0)
    annual_budget: Optional[int] = Field(default=None, ge=0)

    @field_validator("existing_conditions", mode="before")
    @classmethod
    def _normalize_conditions(cls, v: object) -> object:
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        return v

    def max_family_age(self) -> Optional[int]:
        """The oldest age across the caller and any declared family members."""

        ages = [a.age for a in self.family_members if a.age is not None]
        if self.age is not None:
            ages.append(self.age)
        return max(ages) if ages else None

    def is_complete_enough_for_recommendation(self) -> bool:
        """Whether we have enough signal to produce a meaningful recommendation.

        We deliberately keep the bar low: a recommendation only strictly
        needs *some* sizing signal (coverage, budget, or family size). Age
        and conditions refine the result but are not mandatory.
        """

        return any(
            [
                self.desired_coverage is not None,
                self.annual_budget is not None,
                self.family_size is not None,
            ]
        )


class CustomerRequirementsUpdate(BaseModel):
    """Partial extraction result returned by the LLM for a single turn.

    Mirrors `CustomerRequirements` but every field defaults to `None`/empty
    so it can represent "nothing new was said about this field" without
    clobbering previously known information when merged.
    """

    name: Optional[str] = None
    age: Optional[int] = Field(default=None, ge=0, le=120)
    city: Optional[str] = None
    family_size: Optional[int] = Field(default=None, ge=1, le=20)
    family_members: list[FamilyMember] = Field(default_factory=list)
    existing_conditions: list[str] = Field(default_factory=list)
    existing_insurance: Optional[bool] = None
    desired_coverage: Optional[int] = Field(default=None, ge=0)
    annual_budget: Optional[int] = Field(default=None, ge=0)

    @field_validator("existing_conditions", mode="before")
    @classmethod
    def _normalize_conditions(cls, v: object) -> object:
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        return v


class RecommendationResult(BaseModel):
    """Structured output of the deterministic recommendation engine."""

    eligible: bool
    policy_id: Optional[str] = None
    policy_name: Optional[str] = None
    coverage: Optional[int] = None
    annual_premium: Optional[int] = None
    reasons: list[str] = Field(default_factory=list)
    message: Optional[str] = None
    considered_policy_ids: list[str] = Field(default_factory=list)
