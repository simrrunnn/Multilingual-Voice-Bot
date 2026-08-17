"""Tests for Pydantic validation of insurance/customer data models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.insurance.models import CustomerRequirements, CustomerRequirementsUpdate, FamilyMember, Policy


def test_customer_requirements_defaults_are_all_optional():
    requirements = CustomerRequirements()
    assert requirements.name is None
    assert requirements.family_members == []
    assert requirements.existing_conditions == []


def test_customer_requirements_rejects_negative_age():
    with pytest.raises(ValidationError):
        CustomerRequirements(age=-5)


def test_customer_requirements_rejects_unrealistic_age():
    with pytest.raises(ValidationError):
        CustomerRequirements(age=200)


def test_customer_requirements_rejects_negative_budget():
    with pytest.raises(ValidationError):
        CustomerRequirements(annual_budget=-1)


def test_customer_requirements_existing_conditions_string_normalizes_to_list():
    requirements = CustomerRequirements(existing_conditions="diabetes")
    assert requirements.existing_conditions == ["diabetes"]


def test_customer_requirements_existing_conditions_none_normalizes_to_empty_list():
    requirements = CustomerRequirements(existing_conditions=None)
    assert requirements.existing_conditions == []


def test_max_family_age_considers_caller_and_members():
    requirements = CustomerRequirements(
        age=40,
        family_members=[FamilyMember(relationship="child", age=10), FamilyMember(relationship="parent", age=70)],
    )
    assert requirements.max_family_age() == 70


def test_max_family_age_none_when_no_ages_known():
    requirements = CustomerRequirements()
    assert requirements.max_family_age() is None


def test_is_complete_enough_for_recommendation_requires_sizing_signal():
    assert CustomerRequirements().is_complete_enough_for_recommendation() is False
    assert CustomerRequirements(family_size=2).is_complete_enough_for_recommendation() is True
    assert CustomerRequirements(desired_coverage=500_000).is_complete_enough_for_recommendation() is True
    assert CustomerRequirements(annual_budget=15_000).is_complete_enough_for_recommendation() is True


def test_family_member_age_bounds():
    with pytest.raises(ValidationError):
        FamilyMember(relationship="child", age=150)


def test_customer_requirements_update_extraction_schema_matches_requirements_fields():
    update_fields = set(CustomerRequirementsUpdate.model_fields.keys())
    requirements_fields = set(CustomerRequirements.model_fields.keys())
    assert update_fields == requirements_fields


def test_policy_requires_positive_coverage_and_premium():
    with pytest.raises(ValidationError):
        Policy(
            id="bad",
            name="Bad Policy",
            description="x",
            coverage=0,
            annual_premium=1000,
            max_family_size=2,
            max_insured_age=50,
            covers_pre_existing_conditions=False,
        )
