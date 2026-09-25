"""Stage 3: functional and non-functional requirements."""

from app.models.artifacts import (
    BusinessProblemAnalysis,
    ProcessAnalysis,
    RequirementsResult,
    RiskAnalysisResult,
    StakeholderResult,
)
from app.models.inputs import ProjectInput
from app.prompts.base import render_prompt

OUTPUT_MODEL = RequirementsResult

INSTRUCTIONS = """\
Task: write the functional and non-functional requirements for this project.

Functional requirements (FR-001, FR-002, and so on):
- Each one is a single, testable "The system shall ..." statement describing \
one behavior. Split compound statements.
- Describe WHAT the system must do, not HOW it is built. Name no specific \
technologies, vendors or UI widgets unless the input requires them.
- Cover the main flow, the validation and error handling that correct \
behavior depends on, and the needs of each user group, taking the future-state \
process and edge cases into account.
- priority uses MoSCoW:
  - "Must Have": the solution fails its objective without it.
  - "Should Have": important, but a workaround exists.
  - "Could Have": desirable if time allows.
  - "Won't Have": explicitly out of scope for this release. Include one or \
two where a scope boundary needs recording, e.g. a feature stakeholders might \
assume is included.
- rationale: why the requirement exists, tied to the problem or an objective.
- objective_ids: the business objectives (BO-xx) it supports. Every \
requirement except Won't Have ones must support at least one objective.
- Aim for about 8 to 15 functional requirements.

Non-functional requirements (NFR-001, NFR-002, and so on):
- Consider each category (performance, security, availability, scalability, \
accessibility, usability, data privacy, reliability, compliance, \
maintainability) and include those that genuinely matter for this project, \
e.g. security and data privacy when personal data is shown, or accessibility \
for a public-facing interface. Omit irrelevant categories. Nearly every system \
has at least a few relevant quality requirements, so an empty list is almost \
always a mistake.
- rationale must explain why the quality matters for THIS project.
- measurable_target: fill this in only if the input states or clearly \
implies a target. Otherwise leave it empty and phrase the requirement so a \
target can be agreed later. Never invent figures such as "2 seconds" or "99.9%".
- Aim for about 4 to 8 non-functional requirements.

Only reference objective IDs that appear in the problem analysis below.
"""


def build_prompt(
    project: ProjectInput,
    problem: BusinessProblemAnalysis,
    stakeholders: StakeholderResult,
    process: ProcessAnalysis,
    risks: RiskAnalysisResult,
) -> str:
    return render_prompt(
        INSTRUCTIONS,
        project,
        {
            "problem_analysis": problem,
            "stakeholders": stakeholders,
            "process_analysis": process,
            "risks_assumptions_constraints": risks,
        },
    )
