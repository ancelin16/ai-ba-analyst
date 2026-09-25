"""Stage 5: Given/When/Then acceptance criteria for each user story."""

from app.models.artifacts import AcceptanceCriteriaResult, RequirementsResult, RiskAnalysisResult, UserStoriesResult
from app.models.inputs import ProjectInput
from app.prompts.base import render_prompt

OUTPUT_MODEL = AcceptanceCriteriaResult

INSTRUCTIONS = """\
Task: write acceptance criteria in Given/When/Then (Gherkin) format for every \
user story.

Each criterion (AC-001, AC-002, and so on, numbered across all stories):
- story_id: the story it belongs to.
- title: a short scenario name, e.g. "Order number not found".
- scenario_type: "Positive" (expected success), "Negative" (invalid input or \
failure handled correctly) or "Edge Case" (boundary or unusual situation).
- given: the starting context, without the word "Given".
- when: the single action or event, without the word "When".
- then: the observable, verifiable outcome, without the word "Then".

Rules:
- Every story needs at least one Positive criterion. Add Negative and Edge \
Case criteria wherever the story involves input, validation, permissions or \
data that can be missing. The edge cases listed below are a good source.
- Aim for 2 to 4 criteria per story.
- The "then" clause must be testable. Say what the user sees or what the \
system records, never "works correctly".
- Do not invent specifics such as exact messages, limits or timings that the \
requirements do not state. Describe the expected behavior instead, e.g. \
"an error message explains the order was not found".
- Only reference story IDs that appear in the user stories below.
"""


def build_prompt(
    project: ProjectInput, stories: UserStoriesResult, requirements: RequirementsResult, risks: RiskAnalysisResult
) -> str:
    edge_cases = "\n".join(f"- {e}" for e in risks.edge_cases)
    checklist = (
        "Write criteria for every one of these stories: "
        f"{', '.join(s.id for s in stories.stories)}. Check the list before answering."
    )
    return render_prompt(
        INSTRUCTIONS, project,
        {"user_stories": stories, "requirements": requirements, "edge_cases": edge_cases, "coverage_checklist": checklist},
    )
