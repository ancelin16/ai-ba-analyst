"""The full stage 2-6 pipeline, run against a fake AI client."""

import pytest

from app.models.analysis import Analysis
from app.models.inputs import ProjectInput
from app.services.pipeline import (
    DOWNSTREAM,
    apply_clarifications,
    run_analysis,
    run_stage_one,
    unresolved_questions,
)
from app.utils.errors import AIResponseError, AIServiceError, InsufficientInformationError
from tests.fakes import FakeLLMClient


@pytest.fixture
def project(order_input):
    return ProjectInput(**order_input)


def full_run(client, project) -> Analysis:
    return run_analysis(client, run_stage_one(client, project))


def test_full_pipeline_fills_every_section(project, fake_responses):
    client = FakeLLMClient(fake_responses)
    analysis = full_run(client, project)

    assert analysis.is_complete
    assert len(client.calls) == 10
    assert analysis.test_cases.test_cases[0].id == "TC-001"


def test_stages_run_in_dependency_order(project, fake_responses):
    client = FakeLLMClient(fake_responses)
    full_run(client, project)
    order = [r["stage"] for r in client.requests]

    def position(stage):
        return order.index(stage)

    for earlier, later in [
        ("business_problem", "stakeholders"),
        ("risk_analysis", "requirements"),
        ("stakeholders", "requirements"),
        ("requirements", "user_stories"),
        ("requirements", "use_cases"),
        ("user_stories", "acceptance_criteria"),
        ("acceptance_criteria", "test_cases"),
    ]:
        assert position(earlier) < position(later), f"{earlier} should run before {later}"


def test_earlier_results_are_passed_forward(project, fake_responses):
    client = FakeLLMClient(fake_responses)
    full_run(client, project)

    requirements_prompt = client.prompt_for("requirements")
    assert "<stakeholders>" in requirements_prompt and "Data Protection Officer" in requirements_prompt
    assert "<process_analysis>" in requirements_prompt
    assert "BO-01" in requirements_prompt
    assert "FR-002" in client.prompt_for("user_stories")
    assert "Order split into multiple shipments" in client.prompt_for("acceptance_criteria")
    assert "AC-002" in client.prompt_for("test_cases")


def test_unanswered_questions_become_assumption_input(project, fake_responses):
    client = FakeLLMClient(fake_responses)
    full_run(client, project)
    risk_prompt = client.prompt_for("risk_analysis")
    assert "Q-01 [Critical] Must customers sign in" in risk_prompt
    assert "Q-03" not in risk_prompt  # Nice-to-know questions are not forced into assumptions


# --- The clarification gate -----------------------------------------------

def test_vague_request_blocks_the_pipeline(project, fake_responses):
    fake_responses["business_problem"] |= {"is_too_vague": True, "missing_information": ["Who the users are"]}
    client = FakeLLMClient(fake_responses)
    analysis = run_stage_one(client, project)

    with pytest.raises(InsufficientInformationError, match="Who the users are"):
        run_analysis(client, analysis)
    assert len(client.calls) == 2  # nothing generated past the gate


def test_clarifications_rerun_problem_and_reset_downstream(project, fake_responses):
    client = FakeLLMClient(fake_responses)
    analysis = full_run(client, project)

    apply_clarifications(client, analysis, {"Q-01": "No login. Order number plus email.", "Q-02": "  "})

    assert [c.question_id for c in analysis.input.clarifications] == ["Q-01"]  # blank answers ignored
    assert all(getattr(analysis, key) is None for key in DOWNSTREAM)
    assert "Order number plus email" in client.requests[-1]["prompt"]
    assert "Q-01" not in unresolved_questions(analysis)
    assert "Q-02" in unresolved_questions(analysis)


def test_no_answers_changes_nothing(project, fake_responses):
    client = FakeLLMClient(fake_responses)
    analysis = full_run(client, project)
    apply_clarifications(client, analysis, {"Q-01": ""})
    assert analysis.is_complete
    assert len(client.calls) == 10


# --- Failure handling & resume -----------------------------------------------

def test_failed_stage_keeps_earlier_results_and_resumes(project, fake_responses):
    good_criteria = fake_responses["acceptance_criteria"]
    fake_responses["acceptance_criteria"] = AIServiceError("temporary outage")
    client = FakeLLMClient(fake_responses)
    analysis = run_stage_one(client, project)

    with pytest.raises(AIServiceError):
        run_analysis(client, analysis)
    assert analysis.requirements is not None and analysis.stories is not None
    assert analysis.criteria is None and analysis.test_cases is None

    fake_responses["acceptance_criteria"] = good_criteria
    calls_before = len(client.calls)
    run_analysis(client, analysis)
    assert analysis.is_complete
    assert [c.stage for c in client.calls[calls_before:]] == ["acceptance_criteria", "test_cases"]


def test_parallel_stage_failure_keeps_sibling_results(project, fake_responses):
    fake_responses["process_analysis"] = AIServiceError("boom")
    client = FakeLLMClient(fake_responses)
    analysis = run_stage_one(client, project)
    with pytest.raises(AIServiceError):
        run_analysis(client, analysis)
    assert analysis.stakeholders is not None and analysis.risks is not None
    assert analysis.process is None


def test_progress_callback_reports_each_stage(project, fake_responses):
    events = []
    client = FakeLLMClient(fake_responses)
    analysis = run_stage_one(client, project, on_progress=lambda s, st: events.append((s, st)))
    run_analysis(client, analysis, on_progress=lambda s, st: events.append((s, st)))
    done = [s for s, status in events if status == "done"]
    assert sorted(done) == sorted(["questions", "problem", *DOWNSTREAM])


# --- Cross-stage reference checks ------------------------------------------

def test_story_citing_unknown_requirement_is_rejected(project, fake_responses):
    fake_responses["user_stories"]["stories"][0]["requirement_ids"] = ["FR-001", "FR-099"]
    client = FakeLLMClient(fake_responses)
    with pytest.raises(AIResponseError, match="US-001 -> FR-099"):
        full_run(client, project)


def test_requirement_citing_unknown_objective_is_rejected(project, fake_responses):
    fake_responses["requirements"]["functional"][0]["objective_ids"] = ["BO-07"]
    client = FakeLLMClient(fake_responses)
    with pytest.raises(AIResponseError, match="FR-001 -> BO-07"):
        full_run(client, project)


def test_test_case_citing_unknown_criterion_is_rejected(project, fake_responses):
    fake_responses["test_cases"]["test_cases"][0]["criterion_ids"] = ["AC-042"]
    client = FakeLLMClient(fake_responses)
    with pytest.raises(AIResponseError, match="TC-001 -> AC-042"):
        full_run(client, project)


# --- Coverage rules (enforced during validation, so the AI retries) -----------

def test_stories_must_cover_every_in_scope_requirement(project, fake_responses):
    fake_responses["user_stories"]["stories"][0]["requirement_ids"] = ["FR-001"]
    client = FakeLLMClient(fake_responses)
    with pytest.raises(AIResponseError, match="functional requirements are not covered by any item: FR-002, FR-003"):
        full_run(client, project)


def test_wont_have_requirements_need_no_story(project, fake_responses):
    fake_responses["requirements"]["functional"].append({
        "id": "FR-004", "description": "The system shall allow online order cancellation.",
        "priority": "Won't Have", "rationale": "Deferred to a later release.", "basis": "Assumed",
    })
    analysis = full_run(FakeLLMClient(fake_responses), project)
    assert analysis.is_complete


def test_every_story_needs_acceptance_criteria(project, fake_responses):
    fake_responses["user_stories"]["stories"].append({
        "id": "US-002", "role": "customer service agent", "want": "to see the same status the customer sees",
        "so_that": "I can answer the remaining calls consistently", "priority": "Should Have",
        "business_value": "Consistent answers", "requirement_ids": ["FR-003"],
    })
    client = FakeLLMClient(fake_responses)
    with pytest.raises(AIResponseError, match="user stories are not covered by any item: US-002"):
        full_run(client, project)


def test_every_criterion_and_must_have_needs_a_test(project, fake_responses):
    fake_responses["test_cases"]["test_cases"].pop()  # drop TC-003, the only NFR-001 test
    fake_responses["test_cases"]["test_cases"][1]["criterion_ids"] = []  # AC-002 now untested
    client = FakeLLMClient(fake_responses)
    with pytest.raises(AIResponseError) as info:
        full_run(client, project)
    assert "acceptance criteria are not covered by any item: AC-002" in info.value.detail
    assert "Must Have / Should Have requirements are not covered by any item: NFR-001" in info.value.detail


def test_coverage_checklist_lists_the_required_ids(project, fake_responses):
    client = FakeLLMClient(fake_responses)
    full_run(client, project)
    assert "FR-001, FR-002, FR-003" in client.prompt_for("user_stories")
    assert "FR-001, FR-002, FR-003, NFR-001" in client.prompt_for("test_cases")


def test_empty_non_functional_list_is_rejected(project, fake_responses):
    fake_responses["requirements"]["non_functional"] = []
    client = FakeLLMClient(fake_responses)
    with pytest.raises(AIResponseError, match="non_functional"):
        full_run(client, project)


# --- Batching of long lists ---------------------------------------------------------

def _ids_after(prompt: str, marker: str, prefix: str) -> list[str]:
    """IDs listed on the checklist line that starts with `marker`."""
    import re
    line = next((ln for ln in prompt.splitlines() if ln.startswith(marker)), "")
    return re.findall(rf"{prefix}-\d+", line)


def fake_criteria(prompt):
    stories = _ids_after(prompt, "Write criteria for every one of these stories", "US")
    return {"criteria": [
        {"id": f"AC-{i:03d}", "story_id": sid, "title": "Happy path", "scenario_type": "Positive",
         "given": "a valid order", "when": "the customer looks it up", "then": "the status is shown"}
        for i, sid in enumerate(stories, 1)  # batch-local numbering: IDs repeat across batches
    ]}


def fake_tests(prompt):
    criteria = _ids_after(prompt, "Every one of these acceptance criteria", "AC")
    requirements = _ids_after(prompt, "Every one of these requirements", "(?:FR|NFR)")
    tests = [{"id": f"TC-{i:03d}", "requirement_ids": ["FR-001"], "criterion_ids": [cid], "scenario": "Check",
              "scenario_type": "Positive", "steps": ["Do it"], "expected_result": "Works", "priority": "High"}
             for i, cid in enumerate(criteria, 1)]
    if requirements:
        tests.append({"id": "TC-900", "requirement_ids": requirements, "scenario": "Requirement check",
                      "scenario_type": "Positive", "steps": ["Do it"], "expected_result": "Works", "priority": "High"})
    return {"test_cases": tests}


def test_long_story_lists_are_batched_merged_and_renumbered(project, fake_responses):
    base = fake_responses["user_stories"]["stories"][0]
    fake_responses["user_stories"] = {"stories": [base | {"id": f"US-{i:03d}"} for i in range(1, 7)]}
    fake_responses["acceptance_criteria"] = fake_criteria
    fake_responses["test_cases"] = fake_tests
    client = FakeLLMClient(fake_responses)

    analysis = full_run(client, project)

    stages = [c.stage for c in client.calls]
    assert stages.count("acceptance_criteria") == 3  # 6 stories -> 3 batches of 2
    assert stages.count("test_cases") == 3
    criteria_ids = [c.id for c in analysis.criteria.criteria]
    assert criteria_ids == [f"AC-{i:03d}" for i in range(1, 7)]  # renumbered, no duplicates
    assert [c.story_id for c in analysis.criteria.criteria] == [f"US-{i:03d}" for i in range(1, 7)]
    assert [t.id for t in analysis.test_cases.test_cases] == [f"TC-{i:03d}" for i in range(1, 9)]
    # Non-functional requirements are tested in the last batch; every Must Have is covered once.
    from app.services.traceability import build_traceability
    assert build_traceability(analysis).is_clean


def test_many_non_functional_requirements_get_their_own_test_batch(project, fake_responses):
    nfr = fake_responses["requirements"]["non_functional"][0]
    fake_responses["requirements"]["non_functional"] = [nfr | {"id": f"NFR-{i:03d}"} for i in range(1, 6)]
    fake_responses["test_cases"] = fake_tests
    client = FakeLLMClient(fake_responses)
    analysis = full_run(client, project)

    test_prompts = [r["prompt"] for r in client.requests if r["stage"] == "test_cases"]
    assert len(test_prompts) == 2  # one story batch + one batch for the 5 NFRs
    assert "<acceptance_criteria>" not in test_prompts[1]
    assert "NFR-001, NFR-002, NFR-003, NFR-004, NFR-005" in test_prompts[1]
    from app.services.traceability import build_traceability
    assert build_traceability(analysis).is_clean
