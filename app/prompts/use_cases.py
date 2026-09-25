"""Stage 4b: structured use cases."""

from app.models.artifacts import ProcessAnalysis, RequirementsResult, UseCasesResult
from app.models.inputs import ProjectInput
from app.prompts.base import render_prompt

OUTPUT_MODEL = UseCasesResult

INSTRUCTIONS = """\
Task: write structured use cases for the main goals actors achieve with the \
system.

Each use case (UC-01, UC-02, and so on):
- name: a verb phrase naming the actor's goal, e.g. "Check Order Status".
- primary_actor: the role that starts the use case.
- goal: what the actor wants to achieve.
- preconditions: what must be true before it starts.
- main_flow: the success scenario as numbered-style steps that alternate \
between actor actions and system responses, e.g. "Customer enters order \
number", then "System validates the order number". Usually 4 to 10 steps.
- alternative_flows: other valid paths to the goal. Name each one after the \
main-flow step it branches from, e.g. "3a. Customer looks up by email instead".
- exceptions: error paths where the goal cannot be completed normally, named \
the same way, e.g. "4a. Order number not found". Cover the validation failures \
and edge cases that apply.
- postconditions: what is true after success.
- requirement_ids: the functional requirements (FR-xxx) the use case exercises.

Write 2 to 5 use cases covering the most important actor goals, including \
internal actors such as agents or administrators if the requirements involve \
them. Only reference requirement IDs that appear in the requirements below.
"""


def build_prompt(project: ProjectInput, requirements: RequirementsResult, process: ProcessAnalysis) -> str:
    return render_prompt(INSTRUCTIONS, project, {"requirements": requirements, "process_analysis": process})
