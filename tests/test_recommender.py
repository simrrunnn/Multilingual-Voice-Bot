"""Tests for the deterministic recommendation engine (app.insurance.recommender).

These are the most important tests in the repo: the recommendation engine
is pure Python business logic and must be fully deterministic and
independently correct, with no LLM involved.
"""

from __future__ import annotations

import pytest

from app.insurance.models import CustomerRequirements, FamilyMember
from app.insurance.recommender import load_policy_catalogue, recommend_policy


@pytest.fixture(scope="module")
def catalogue():
    return load_policy_catalogue()


def test_catalogue_loads_three_demo_policies(catalogue):
    ids = {p.id for p in catalogue.policies}
    assert ids == {"health_basic", "health_plus", "health_premium"}


def test_recommendation_output_structure(catalogue):
    requirements = CustomerRequirements(family_size=2, desired_coverage=500_000, annual_budget=15_000)
    result = recommend_policy(requirements, catalogue)

    assert result.eligible is True
    assert result.policy_id in {p.id for p in catalogue.policies}
    assert isinstance(result.policy_name, str)
    assert isinstance(result.coverage, int)
    assert isinstance(result.annual_premium, int)
    assert isinstance(result.reasons, list)
    assert len(result.reasons) > 0
    assert all(isinstance(r, str) for r in result.reasons)


def test_low_budget_small_family_gets_basic(catalogue):
    requirements = CustomerRequirements(age=30, family_size=2, annual_budget=13_000)
    result = recommend_policy(requirements, catalogue)

    assert result.eligible is True
    assert result.policy_id == "health_basic"


def test_mid_budget_family_of_four_gets_plus(catalogue):
    requirements = CustomerRequirements(
        age=34, family_size=4, desired_coverage=1_000_000, annual_budget=25_000
    )
    result = recommend_policy(requirements, catalogue)

    assert result.eligible is True
    assert result.policy_id == "health_plus"


def test_large_family_high_coverage_gets_premium(catalogue):
    requirements = CustomerRequirements(
        age=40, family_size=6, desired_coverage=2_000_000, annual_budget=45_000
    )
    result = recommend_policy(requirements, catalogue)

    assert result.eligible is True
    assert result.policy_id == "health_premium"


def test_family_size_exceeding_all_policies_is_ineligible(catalogue):
    requirements = CustomerRequirements(family_size=10)
    result = recommend_policy(requirements, catalogue)

    assert result.eligible is False
    assert result.policy_id is None
    assert result.message is not None
    assert len(result.considered_policy_ids) == 3


def test_age_exceeding_all_policies_is_ineligible(catalogue):
    requirements = CustomerRequirements(age=80)
    result = recommend_policy(requirements, catalogue)

    assert result.eligible is False


def test_oldest_family_member_age_is_used_not_just_caller_age(catalogue):
    requirements = CustomerRequirements(
        age=40,
        family_size=2,
        family_members=[FamilyMember(relationship="parent", age=80)],
    )
    result = recommend_policy(requirements, catalogue)

    # Every policy caps max_insured_age below 80, so nothing should qualify.
    assert result.eligible is False


def test_budget_below_cheapest_policy_is_ineligible(catalogue):
    requirements = CustomerRequirements(annual_budget=5_000)
    result = recommend_policy(requirements, catalogue)

    assert result.eligible is False


def test_desired_coverage_above_all_policies_is_ineligible(catalogue):
    requirements = CustomerRequirements(desired_coverage=5_000_000)
    result = recommend_policy(requirements, catalogue)

    assert result.eligible is False


def test_coverage_requirement_filters_out_insufficient_policies(catalogue):
    requirements = CustomerRequirements(desired_coverage=1_500_000, annual_budget=45_000)
    result = recommend_policy(requirements, catalogue)

    assert result.eligible is True
    assert result.coverage >= 1_500_000


def test_pre_existing_conditions_prefer_covering_policy(catalogue):
    requirements = CustomerRequirements(
        age=30, family_size=1, annual_budget=45_000, existing_conditions=["diabetes"]
    )
    result = recommend_policy(requirements, catalogue)

    assert result.eligible is True
    chosen = next(p for p in catalogue.policies if p.id == result.policy_id)
    assert chosen.covers_pre_existing_conditions is True
    assert any("pre-existing" in reason.lower() for reason in result.reasons)


def test_no_requirements_still_returns_a_result_without_crashing(catalogue):
    requirements = CustomerRequirements()
    result = recommend_policy(requirements, catalogue)

    assert result.eligible is True
    assert result.policy_id is not None


def test_recommendation_is_deterministic(catalogue):
    requirements = CustomerRequirements(age=45, family_size=3, desired_coverage=1_000_000, annual_budget=25_000)
    first = recommend_policy(requirements, catalogue)
    second = recommend_policy(requirements, catalogue)

    assert first.policy_id == second.policy_id
    assert first.reasons == second.reasons


def test_cheaper_policy_preferred_on_score_tie(catalogue):
    # With no sizing signal at all, every policy scores identically on the
    # neutral baseline; the tie-break must prefer the cheaper premium.
    requirements = CustomerRequirements()
    result = recommend_policy(requirements, catalogue)
    assert result.policy_id == "health_basic"
