"""Traceability matrix and coverage-gap detection (pure Python, no AI)."""

import pytest

from app.models.analysis import Analysis
from app.models.common import Priority
from app.models.inputs import ProjectInput
from app.services.traceability import FULLY_TRACED, NOT_TESTED, OUT_OF_SCOPE, PARTIAL, build_traceability


@pytest.fixture
def analysis(order_input, order_stages) -> Analysis:
    return Analysis(input=ProjectInput(**order_input), **order_stages)


def row(report, requirement_id):
    return report.matrix.set_index("Requirement").loc[requirement_id]


def gap_messages(report):
    return [g.message for g in report.gaps]


def test_complete_chain_is_fully_traced(analysis):
    report = build_traceability(analysis)

    fr3 = row(report, "FR-003")
    assert fr3["Business Objectives"] == "BO-01, BO-02"
    assert fr3["User Stories"] == "US-001"
    assert fr3["Acceptance Criteria"] == "AC-001, AC-002"
    assert fr3["Test Cases"] == "TC-001, TC-002"  # TC-001 directly, TC-002 via AC-002
    assert fr3["Trace Status"] == FULLY_TRACED
    assert report.is_clean
    assert report.metrics["test_coverage_pct"] == 100


def test_nfr_is_traced_without_stories(analysis):
    nfr = row(build_traceability(analysis), "NFR-001")
    assert nfr["Type"] == "Non-functional (Data Privacy)"
    assert nfr["User Stories"] == "n/a"
    assert nfr["Test Cases"] == "TC-003"
    assert nfr["Trace Status"] == FULLY_TRACED


def test_untested_must_have_is_flagged(analysis):
    analysis.test_cases.test_cases = [t for t in analysis.test_cases.test_cases if t.id != "TC-003"]
    report = build_traceability(analysis)
    assert row(report, "NFR-001")["Trace Status"] == NOT_TESTED
    assert "NFR-001 (Must Have) has no test case." in gap_messages(report)
    assert report.metrics["test_coverage_pct"] == 75


def test_requirement_without_story_is_flagged(analysis):
    analysis.stories.stories[0].requirement_ids = ["FR-001", "FR-003"]
    report = build_traceability(analysis)
    assert "FR-002 is not covered by any user story." in gap_messages(report)
    assert row(report, "FR-002")["Trace Status"] == PARTIAL  # still tested directly by TC-002


def test_story_without_criteria_is_flagged(analysis):
    analysis.criteria.criteria = []
    report = build_traceability(analysis)
    assert "US-001 has no acceptance criteria." in gap_messages(report)


def test_criterion_without_test_is_flagged(analysis):
    analysis.test_cases.test_cases[1].criterion_ids = []
    report = build_traceability(analysis)
    assert "AC-002 is not verified by any test case." in gap_messages(report)


def test_objective_without_requirements_is_flagged(analysis):
    for req in analysis.requirements.functional + analysis.requirements.non_functional:
        req.objective_ids = [o for o in req.objective_ids if o != "BO-01"]
    report = build_traceability(analysis)
    assert "BO-01 has no requirements supporting it." in gap_messages(report)


def test_wont_have_is_out_of_scope_and_excluded_from_coverage(analysis):
    from app.models.artifacts import FunctionalRequirement
    analysis.requirements.functional.append(FunctionalRequirement(
        id="FR-004", description="The system shall allow order cancellation online.",
        priority="Won't Have", rationale="Deferred to a later release.", basis="Assumed",
    ))
    report = build_traceability(analysis)
    assert row(report, "FR-004")["Trace Status"] == OUT_OF_SCOPE
    assert report.metrics["requirements_in_scope"] == 4
    assert report.is_clean  # no story/test expected for Won't Have


def test_wont_have_with_stories_is_flagged(analysis):
    analysis.requirements.functional[1].priority = Priority.WONT
    report = build_traceability(analysis)
    assert any("FR-002 is marked Won't Have" in m for m in gap_messages(report))


def test_dangling_references_are_reported(analysis):
    analysis.stories.stories[0].requirement_ids.append("FR-777")
    analysis.use_cases.use_cases[0].requirement_ids.append("FR-888")
    report = build_traceability(analysis)
    assert report.dangling_references == ["US-001 -> FR-777", "UC-01 -> FR-888"]
    assert not report.is_clean


def test_matrix_before_requirements_exist_is_empty(order_input, order_stages):
    partial = Analysis(input=ProjectInput(**order_input), problem=order_stages["problem"])
    report = build_traceability(partial)
    assert report.matrix.empty
    assert report.gaps == []
