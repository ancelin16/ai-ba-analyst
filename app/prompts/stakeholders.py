"""Stage 2a: stakeholder analysis."""

from app.models.artifacts import BusinessProblemAnalysis, StakeholderResult
from app.models.inputs import ProjectInput
from app.prompts.base import render_prompt

OUTPUT_MODEL = StakeholderResult

INSTRUCTIONS = """\
Task: identify the stakeholders for this project and analyze their interest \
and influence.

Include:
- stakeholders named in the input (basis "Stated");
- stakeholders directly implied by the request, such as the users of the \
system or the team whose workload is being addressed (basis "Inferred");
- stakeholders a BA would expect to be involved who were NOT mentioned. \
Typical examples are the product or process owner who approves requirements, \
IT or the owners of affected systems, security or privacy, legal or \
compliance, support, operations, and training. Set potentially_missing to \
true and basis to "Assumed". Include these only when relevant to this project.

For each stakeholder:
- name: a role or group, never an invented person's name.
- interest: what they need from the project or are concerned about, specific \
to this request.
- influence: their power over project decisions (High, Medium or Low).
- impact: how much the change affects their day-to-day work (High, Medium or Low).

Aim for 4 to 10 stakeholders. Use IDs SH-01, SH-02, and so on.
"""


def build_prompt(project: ProjectInput, problem: BusinessProblemAnalysis) -> str:
    return render_prompt(INSTRUCTIONS, project, {"problem_analysis": problem})
