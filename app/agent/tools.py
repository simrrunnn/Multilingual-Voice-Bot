"""LLM-callable tools for the voice agent.

Two tools, matching the CORE DESIGN PRINCIPLE in the README:

* `record_customer_info` lets the LLM report structured facts it extracted
  from natural speech. Arguments are validated through
  `CustomerRequirementsUpdate` (Pydantic) before being merged into session
  state — the LLM's raw output is never trusted as-is.
* `get_policy_recommendation` is the ONLY way the LLM can learn which
  policy to recommend. It runs `app.insurance.recommender.recommend_policy`
  (pure Python, deterministic) and returns its structured result. The LLM
  may only narrate what this returns; it never picks a policy itself.
"""

from __future__ import annotations

from livekit.agents import RunContext, function_tool

from app.agent.state import AgentUserdata
from app.insurance.models import CustomerRequirementsUpdate, FamilyMember


@function_tool
async def record_customer_info(
    context: RunContext[AgentUserdata],
    name: str | None = None,
    age: int | None = None,
    city: str | None = None,
    family_size: int | None = None,
    family_members: list[FamilyMember] | None = None,
    existing_conditions: list[str] | None = None,
    existing_insurance: bool | None = None,
    desired_coverage: int | None = None,
    annual_budget: int | None = None,
) -> str:
    """Record or update structured facts the caller has stated about themselves.

    Call this as soon as the caller states any new detail, even just one
    field — do not wait to collect everything first. Only pass fields that
    were actually stated or clearly implied in the latest message; leave
    every other field as null. Convert spoken amounts to plain INR integers
    (e.g. "ten lakh" -> 1000000, "twenty thousand" -> 20000).

    Args:
        name: The caller's own name, if stated.
        age: The caller's own age in years, if stated.
        city: The caller's city, if stated.
        family_size: Total number of people to be insured, including the caller.
        family_members: Family members to insure, each with a relationship (e.g. "spouse", "child") and age if known.
        existing_conditions: Pre-existing health conditions the caller declares for anyone to be insured.
        existing_insurance: Whether the caller already holds a health insurance policy.
        desired_coverage: Desired sum insured, in INR.
        annual_budget: Approximate annual premium budget, in INR.
    """

    update = CustomerRequirementsUpdate(
        name=name,
        age=age,
        city=city,
        family_size=family_size,
        family_members=family_members or [],
        existing_conditions=existing_conditions or [],
        existing_insurance=existing_insurance,
        desired_coverage=desired_coverage,
        annual_budget=annual_budget,
    )
    updated = context.userdata.session_manager.update_requirements(update)
    response = f"Recorded. Known caller information so far: {updated.model_dump_json(exclude_none=True)}"
    if updated.is_complete_enough_for_recommendation():
        response += (
            " You now have enough information to produce a recommendation. Unless the caller is "
            "clearly still mid-thought, call get_policy_recommendation next and explain the result "
            "before ending the call -- do not wait for the caller to ask for one."
        )
    return response


@function_tool
async def get_policy_recommendation(context: RunContext[AgentUserdata]) -> str:
    """Get the deterministic policy recommendation for the caller gathered so far.

    Call this only once you have gathered enough information to make it
    meaningful (at minimum, some sense of desired coverage, budget, or
    family size). This runs fixed Python business rules against the
    fictional demo policy catalogue and is the ONLY source of truth for
    which policy fits and what it costs or covers. When explaining the
    result, use ONLY the fields returned here — never state a benefit,
    price, or limit that is not present in this JSON.
    """

    manager = context.userdata.session_manager
    if not manager.session.requirements.is_complete_enough_for_recommendation():
        return (
            '{"error": "not_enough_information", "message": '
            '"Ask the caller for desired coverage, budget, or family size before recommending."}'
        )
    recommendation = manager.generate_recommendation()
    return recommendation.model_dump_json(exclude_none=True)


ALL_TOOLS = [record_customer_info, get_policy_recommendation]
