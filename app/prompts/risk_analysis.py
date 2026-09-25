"""Stage 2c: risks, assumptions, constraints and edge cases."""

from app.models.artifacts import BusinessProblemAnalysis, RiskAnalysisResult
from app.models.inputs import ProjectInput
from app.prompts.base import render_prompt

OUTPUT_MODEL = RiskAnalysisResult

INSTRUCTIONS = """\
Task: build the project's risk register, assumptions log and constraints \
list, and identify edge cases the solution must handle.

Risks (RK-01, RK-02, and so on):
- Cover the sources that apply: business, process, technical, data, \
compliance, adoption and project delivery.
- Each risk is a specific uncertain event and its consequence, e.g. "Order \
status in the source system lags behind reality, so customers see outdated \
status and still call." Avoid generic risks that could apply to any project.
- Rate likelihood and impact (High, Medium or Low) and give a practical mitigation.

Assumptions (AS-01, AS-02, and so on):
- Record every assumption the analysis depends on. This must include each \
unresolved question listed below that the analysis has to proceed without \
answering.
- impact_if_wrong: what changes if the assumption proves false.
- validate_with: the role that should confirm it.

Constraints (CN-01, CN-02, and so on):
- Include only limits that are stated or clearly implied, such as an existing \
system that must be used. Use basis "Stated" or "Inferred". Do not invent \
budgets, deadlines or technology mandates.

Edge cases:
- Unusual but realistic situations the solution must handle correctly, e.g. \
partial shipments, cancelled orders, or records that exist in one system but \
not another.

Aim for about 5 to 10 risks, 3 to 10 assumptions and 4 to 10 edge cases.
"""


def build_prompt(project: ProjectInput, problem: BusinessProblemAnalysis, open_questions: str) -> str:
    return render_prompt(
        INSTRUCTIONS, project, {"problem_analysis": problem, "unresolved_questions": open_questions}
    )
