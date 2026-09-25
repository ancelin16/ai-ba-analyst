import pytest
from pydantic import ValidationError

from app.models.analysis import Analysis
from app.models.artifacts import (
    AcceptanceCriteriaResult,
    BusinessProblemAnalysis,
    ClarifyingQuestion,
    RequirementsResult,
    TestCasesResult,
    UserStoriesResult,
)
from app.models.common import Basis, Priority, ScenarioType
from app.models.inputs import ClarificationAnswer, ProjectInput


# --- Enum tolerance ---------------------------------------------------------

@pytest.mark.parametrize("raw", ["Must Have", "must have", "MUST_HAVE", "Must-Have", "musthave"])
def test_priority_accepts_formatting_variants(raw):
    assert Priority(raw) is Priority.MUST


def test_other_enums_are_lenient():
    assert Priority("won't have") is Priority.WONT
    assert ScenarioType("edge_case") is ScenarioType.EDGE_CASE
    assert Basis("ASSUMED") is Basis.ASSUMED


def test_unknown_priority_is_rejected():
    with pytest.raises(ValueError):
        Priority("Critical")


# --- Requirements -----------------------------------------------------------

def test_requirements_parse(order_stages):
    result = RequirementsResult.model_validate(order_stages["requirements"])
    assert result.functional[2].priority is Priority.MUST
    assert result.functional[2].objective_ids == ["BO-01", "BO-02"]
    assert result.non_functional[0].basis is Basis.ASSUMED


@pytest.mark.parametrize("bad_id", ["FR-1", "FR001", "REQ-001", "fr-001", "FR-0001"])
def test_requirement_id_format_enforced(order_stages, bad_id):
    order_stages["requirements"]["functional"][0]["id"] = bad_id
    with pytest.raises(ValidationError):
        RequirementsResult.model_validate(order_stages["requirements"])


def test_duplicate_requirement_ids_rejected(order_stages):
    order_stages["requirements"]["functional"][1]["id"] = "FR-001"
    with pytest.raises(ValidationError, match="duplicate IDs in functional: FR-001"):
        RequirementsResult.model_validate(order_stages["requirements"])


def test_requirement_needs_rationale(order_stages):
    order_stages["requirements"]["functional"][0]["rationale"] = "   "
    with pytest.raises(ValidationError):
        RequirementsResult.model_validate(order_stages["requirements"])


def test_at_least_one_functional_requirement(order_stages):
    order_stages["requirements"]["functional"] = []
    with pytest.raises(ValidationError):
        RequirementsResult.model_validate(order_stages["requirements"])


# --- User stories & acceptance criteria -------------------------------------

def test_user_story_text_format(order_stages):
    story = UserStoriesResult.model_validate(order_stages["stories"]).stories[0]
    assert story.text == (
        "As a customer, I want to look up my order by its order number, "
        "so that I know when it will arrive without calling customer service."
    )


def test_user_story_must_trace_to_a_requirement(order_stages):
    order_stages["stories"]["stories"][0]["requirement_ids"] = []
    with pytest.raises(ValidationError):
        UserStoriesResult.model_validate(order_stages["stories"])


def test_acceptance_criterion_given_when_then(order_stages):
    ac = AcceptanceCriteriaResult.model_validate(order_stages["criteria"]).criteria[0]
    assert ac.text == (
        "Given a customer has a valid order number,\n"
        "When the customer submits the order number,\n"
        "Then the system displays the current order status."
    )


def test_acceptance_criteria_cover_positive_and_negative(order_stages):
    criteria = AcceptanceCriteriaResult.model_validate(order_stages["criteria"]).criteria
    assert {c.scenario_type for c in criteria} == {ScenarioType.POSITIVE, ScenarioType.NEGATIVE}


def test_acceptance_criterion_requires_all_three_clauses(order_stages):
    del order_stages["criteria"]["criteria"][0]["then"]
    with pytest.raises(ValidationError):
        AcceptanceCriteriaResult.model_validate(order_stages["criteria"])


# --- Test cases ---------------------------------------------------------------

def test_test_cases_parse(order_stages):
    cases = TestCasesResult.model_validate(order_stages["test_cases"]).test_cases
    assert cases[1].scenario_type is ScenarioType.NEGATIVE
    assert cases[1].preconditions == []


def test_test_case_may_reference_nfr(order_stages):
    order_stages["test_cases"]["test_cases"][0]["requirement_ids"].append("NFR-001")
    TestCasesResult.model_validate(order_stages["test_cases"])


def test_test_case_needs_steps(order_stages):
    order_stages["test_cases"]["test_cases"][0]["steps"] = []
    with pytest.raises(ValidationError):
        TestCasesResult.model_validate(order_stages["test_cases"])


# --- Clarifying questions & problem analysis --------------------------------

def test_critical_question_requires_rationale():
    with pytest.raises(ValidationError, match="must explain why they matter"):
        ClarifyingQuestion(id="Q-01", question="Must customers log in?", category="Critical")


def test_non_critical_question_rationale_optional():
    q = ClarifyingQuestion(id="Q-02", question="Preferred brand colours?", category="nice to know")
    assert q.rationale == ""


def test_problem_analysis_needs_an_objective(order_stages):
    order_stages["problem"]["objectives"] = []
    with pytest.raises(ValidationError):
        BusinessProblemAnalysis.model_validate(order_stages["problem"])


# --- Input & aggregate --------------------------------------------------------

def test_clarification_answers_appear_in_prompt_context(order_input):
    project = ProjectInput(
        **order_input,
        clarifications=[
            ClarificationAnswer(question_id="Q-01", question="Must customers log in?", answer="No, order number + email"),
            ClarificationAnswer(question_id="Q-02", question="Unanswered question?", answer=""),
        ],
    )
    ctx = project.as_prompt_context()
    assert "Q-01 Must customers log in?\n  Answer: No, order number + email" in ctx
    assert "Q-02" not in ctx


def test_analysis_round_trips_through_json(order_input, order_stages):
    analysis = Analysis(
        input=ProjectInput(**order_input),
        problem=order_stages["problem"],
        requirements=order_stages["requirements"],
    )
    restored = Analysis.model_validate_json(analysis.model_dump_json())
    assert restored.requirements.functional[0].id == "FR-001"
    assert restored.problem.objectives[0].basis is Basis.STATED
    assert not restored.is_complete
