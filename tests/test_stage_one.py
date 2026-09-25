"""Stage 1 (clarifying questions + problem analysis) with a fake AI client."""

import pytest

from app.models.artifacts import QuestionCategory
from app.models.inputs import ClarificationAnswer, ProjectInput
from app.prompts.base import BA_SYSTEM_PROMPT
from app.services.pipeline import needs_more_information, run_stage_one
from app.utils.errors import AIServiceError
from tests.fakes import FakeLLMClient

QUESTIONS = {
    "questions": [
        {"id": "Q-01", "question": "Must customers sign in to track an order, or is the order number enough?",
         "category": "Critical", "area": "Security",
         "rationale": "Showing order details from an order number alone could expose personal data."},
        {"id": "Q-02", "question": "How often does the OMS update order status?",
         "category": "Important", "area": "Data"},
        {"id": "Q-03", "question": "Should the page match the existing website branding?",
         "category": "Nice to Know", "area": "Usability"},
    ]
}


@pytest.fixture
def project(order_input):
    return ProjectInput(**order_input)


def test_stage_one_returns_questions_and_problem(project, order_stages):
    client = FakeLLMClient({"clarifying_questions": QUESTIONS, "business_problem": order_stages["problem"]})
    analysis = run_stage_one(client, project, model_name="test-model")

    assert analysis.model == "test-model"
    assert [q.category for q in analysis.questions.questions] == [
        QuestionCategory.CRITICAL, QuestionCategory.IMPORTANT, QuestionCategory.NICE_TO_KNOW,
    ]
    assert analysis.problem.objectives[0].id == "BO-01"
    assert not needs_more_information(analysis)
    assert {c.stage for c in client.calls} == {"clarifying_questions", "business_problem"}


def test_every_stage_uses_the_ba_system_prompt(project, order_stages):
    client = FakeLLMClient({"clarifying_questions": QUESTIONS, "business_problem": order_stages["problem"]})
    run_stage_one(client, project)
    assert all(r["system"] == BA_SYSTEM_PROMPT for r in client.requests)


def test_prompts_contain_input_and_flag_missing_fields(project, order_stages):
    client = FakeLLMClient({"clarifying_questions": QUESTIONS, "business_problem": order_stages["problem"]})
    run_stage_one(client, project)
    for stage in ("clarifying_questions", "business_problem"):
        prompt = client.prompt_for(stage)
        assert "too many calls asking about order status" in prompt
        assert "Known constraints: Not provided" in prompt


def test_clarification_answers_are_passed_to_the_ai(order_input, order_stages):
    project = ProjectInput(
        **order_input,
        clarifications=[ClarificationAnswer(question_id="Q-01", question="Must customers sign in?",
                                            answer="No. Order number plus email address.")],
    )
    client = FakeLLMClient({"clarifying_questions": QUESTIONS, "business_problem": order_stages["problem"]})
    run_stage_one(client, project)
    assert "Order number plus email address" in client.prompt_for("business_problem")


def test_vague_request_stops_the_pipeline(project, order_stages):
    vague = order_stages["problem"] | {
        "is_too_vague": True,
        "missing_information": ["Who the users are", "What problem the change should solve"],
    }
    client = FakeLLMClient({"clarifying_questions": QUESTIONS, "business_problem": vague})
    analysis = run_stage_one(client, project)
    assert needs_more_information(analysis)
    assert analysis.problem.missing_information[0] == "Who the users are"


def test_api_error_in_one_stage_propagates(project, order_stages):
    client = FakeLLMClient({
        "clarifying_questions": AIServiceError("boom"),
        "business_problem": order_stages["problem"],
    })
    with pytest.raises(AIServiceError):
        run_stage_one(client, project)
