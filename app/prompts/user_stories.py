"""Stage 4a: Agile user stories derived from functional requirements."""

from app.models.artifacts import RequirementsResult, StakeholderResult, UserStoriesResult
from app.models.inputs import ProjectInput
from app.prompts.base import render_prompt

OUTPUT_MODEL = UserStoriesResult

INSTRUCTIONS = """\
Task: convert the functional requirements into Agile user stories.

Each story (US-001, US-002, and so on):
- role: a specific user role from the stakeholders, e.g. "customer" or \
"customer service agent". Never use "user" or "system" when a real role exists.
- want: the capability from that user's point of view, written to complete \
the sentence "I want ...", so it normally starts with "to", e.g. "to look up \
my order by its order number".
- so_that: the business value or outcome for that user. It must not simply \
restate the "want".
- priority: MoSCoW, normally the highest priority of the requirements it covers.
- business_value: one sentence on why the business benefits, linked to the \
objectives where possible.
- requirement_ids: the functional requirements (FR-xxx) the story delivers.

Rules:
- Every functional requirement except "Won't Have" ones must be covered by at \
least one story; see the coverage checklist at the end. Do not write stories \
for "Won't Have" requirements.
- A typical project needs several stories, often one per distinct user goal \
or capability. One story rarely covers everything.
- Follow INVEST: each story should be independent, negotiable, valuable, \
estimable, small and testable. Group closely related requirements, such as \
entering and validating an order number, into one story rather than one \
story per requirement.
- Only reference requirement IDs that appear in the requirements below.

Acceptance criteria are written in a later step, so do not include them here.
"""


def build_prompt(
    project: ProjectInput, stakeholders: StakeholderResult, requirements: RequirementsResult, must_cover: set[str]
) -> str:
    checklist = (
        "Each of these functional requirements must appear in at least one story's "
        f"requirement_ids: {', '.join(sorted(must_cover))}. Check the list before answering."
    )
    return render_prompt(
        INSTRUCTIONS, project,
        {"stakeholders": stakeholders, "requirements": requirements, "coverage_checklist": checklist},
    )
