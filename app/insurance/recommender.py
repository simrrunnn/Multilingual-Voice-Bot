"""Deterministic health insurance policy recommendation engine.

CORE DESIGN PRINCIPLE (see README "Recommendation Design"): the LLM never
decides which policy to recommend. This module is pure, deterministic
Python -- it filters ineligible policies and scores the remainder, with no
network calls and no dependency on `app.agent`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.insurance.models import (
    CustomerRequirements,
    Policy,
    PolicyCatalogue,
    RecommendationResult,
)

POLICIES_PATH = Path(__file__).parent / "policies.json"


@lru_cache(maxsize=1)
def load_policy_catalogue(path: Path = POLICIES_PATH) -> PolicyCatalogue:
    """Load and validate the policy catalogue from policies.json.

    Cached because the catalogue is static for the lifetime of the process;
    tests that need a fresh read can call `load_policy_catalogue.cache_clear()`.
    """

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return PolicyCatalogue.model_validate(raw)


def _eligibility_reason(policy: Policy, requirements: CustomerRequirements) -> str | None:
    """Return why `policy` is ineligible for `requirements`, or None if eligible.

    Hard constraints (a violation makes the policy entirely unsuitable):
      * family size must fit within the policy's max family size
      * the oldest insured person's age must not exceed the policy's max age
      * the policy's coverage must meet or exceed the caller's desired coverage
      * the policy's annual premium must not exceed the caller's stated budget
    """

    if requirements.family_size is not None and requirements.family_size > policy.max_family_size:
        return (
            f"Supports up to {policy.max_family_size} family members, "
            f"but {requirements.family_size} were requested"
        )

    max_age = requirements.max_family_age()
    if max_age is not None and max_age > policy.max_insured_age:
        return f"Maximum insurable age is {policy.max_insured_age}, but oldest member is {max_age}"

    if requirements.desired_coverage is not None and policy.coverage < requirements.desired_coverage:
        return (
            f"Coverage of ₹{policy.coverage:,} is below the requested ₹{requirements.desired_coverage:,}"
        )

    if requirements.annual_budget is not None and policy.annual_premium > requirements.annual_budget:
        return (
            f"Annual premium of ₹{policy.annual_premium:,} exceeds the stated budget of "
            f"₹{requirements.annual_budget:,}"
        )

    return None


def _score_policy(policy: Policy, requirements: CustomerRequirements) -> tuple[float, list[str]]:
    """Score an eligible policy against requirements. Higher is better.

    Returns the score plus a human-readable list of reasons that justify it,
    which are surfaced directly to the caller (and to the LLM for narration).
    """

    score = 0.0
    reasons: list[str] = []

    if requirements.desired_coverage:
        reasons.append(f"Meets the requested ₹{requirements.desired_coverage:,} coverage")
        score += 10
        excess_ratio = (policy.coverage - requirements.desired_coverage) / requirements.desired_coverage
        # Reward policies that are close to (not wastefully above) the requested cover.
        score += max(0.0, 5 - excess_ratio * 5)
    else:
        score += 2

    if requirements.annual_budget:
        reasons.append(f"Annual premium of ₹{policy.annual_premium:,} is within the stated budget")
        score += 10
        margin_ratio = (requirements.annual_budget - policy.annual_premium) / requirements.annual_budget
        score += margin_ratio * 3
    else:
        score += 2

    if requirements.family_size:
        reasons.append(f"Covers the caller's family size of {requirements.family_size}")
        score += 5

    max_age = requirements.max_family_age()
    if max_age is not None:
        reasons.append(f"All insured members are within the {policy.max_insured_age}-year age limit")
        score += 5

    if requirements.existing_conditions:
        if policy.covers_pre_existing_conditions:
            reasons.append("Covers the declared pre-existing health conditions")
            score += 8
        else:
            score -= 6

    return score, reasons


def recommend_policy(
    requirements: CustomerRequirements,
    catalogue: PolicyCatalogue | None = None,
) -> RecommendationResult:
    """Select the best-matching policy for `requirements`, or explain why none fit.

    This is the single entry point the conversational layer should call.
    Deterministic and side-effect free: same input always yields same output.
    """

    catalogue = catalogue or load_policy_catalogue()
    policies = catalogue.policies

    ineligible: dict[str, str] = {}
    eligible: list[Policy] = []
    for policy in policies:
        reason = _eligibility_reason(policy, requirements)
        if reason is None:
            eligible.append(policy)
        else:
            ineligible[policy.id] = reason

    if not eligible:
        detail = "; ".join(f"{pid}: {reason}" for pid, reason in ineligible.items())
        return RecommendationResult(
            eligible=False,
            reasons=[],
            message=(
                "No policy in the demo catalogue fits all of the stated requirements. "
                f"Details: {detail}"
                if detail
                else "No policy in the demo catalogue fits the stated requirements."
            ),
            considered_policy_ids=[p.id for p in policies],
        )

    scored = [(_score_policy(p, requirements), p) for p in eligible]
    scored.sort(key=lambda item: (-item[0][0], item[1].annual_premium))
    (best_score, best_reasons), best_policy = scored[0]

    return RecommendationResult(
        eligible=True,
        policy_id=best_policy.id,
        policy_name=best_policy.name,
        coverage=best_policy.coverage,
        annual_premium=best_policy.annual_premium,
        reasons=best_reasons,
        considered_policy_ids=[p.id for p in policies],
    )
