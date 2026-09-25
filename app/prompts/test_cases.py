"""Stage 6: test cases derived from acceptance criteria and requirements."""

from app.models.artifacts import AcceptanceCriterion, RequirementsResult, TestCasesResult, UserStory
from app.models.inputs import ProjectInput
from app.prompts.base import render_prompt, to_prompt_json

OUTPUT_MODEL = TestCasesResult

INSTRUCTIONS = """\
Task: write the test cases a QA analyst would execute to verify this solution.

Each test case (TC-001, TC-002, and so on):
- requirement_ids: the requirements it verifies (FR-xxx and/or NFR-xxx). At \
least one is required.
- criterion_ids: the acceptance criteria (AC-xxx) it verifies, if any.
- scenario: a short description of what is being tested.
- scenario_type: "Positive", "Negative" or "Edge Case".
- preconditions: the data and state needed before the test starts. Use \
clearly fictional sample values such as "Order ORD-1001 exists with status \
Shipped".
- steps: concrete, numbered-style actions a tester performs.
- expected_result: the specific, observable outcome that means the test passed.
- priority: High, Medium or Low, based on the business risk if this behavior fails.

Coverage rules:
- Every acceptance criterion must be verified by at least one test case.
- Every "Must Have" and "Should Have" requirement must be verified by at \
least one test case, including non-functional ones where a practical test \
exists, e.g. access control or accessibility checks.
- Do not write tests for "Won't Have" requirements.
- Include Positive, Negative and Edge Case tests.
- Only reference requirement and criterion IDs that appear below.
"""


def build_prompt(
    project: ProjectInput,
    requirements: RequirementsResult,
    stories: list[UserStory],
    criteria: list[AcceptanceCriterion],
    must_test: set[str],
) -> str:
    checklist = []
    if criteria:
        checklist.append(
            "Every one of these acceptance criteria must appear in some test's criterion_ids: "
            + ", ".join(c.id for c in criteria) + "."
        )
    if must_test:
        checklist.append(
            "Every one of these requirements must appear in some test's requirement_ids: "
            + ", ".join(sorted(must_test)) + "."
        )
    checklist.append("Write tests only for the stories, criteria and requirements listed here. Check the lists before answering.")
    return render_prompt(
        INSTRUCTIONS,
        project,
        {
            "requirements": requirements,
            "user_stories": to_prompt_json(stories) if stories else None,
            "acceptance_criteria": to_prompt_json(criteria) if criteria else None,
            "coverage_checklist": "\n".join(checklist),
        },
    )
