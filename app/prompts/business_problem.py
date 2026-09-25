"""Stage 1b: understand the business problem and decide whether it is analysable."""

from app.models.artifacts import BusinessProblemAnalysis
from app.models.inputs import ProjectInput
from app.prompts.base import render_prompt

OUTPUT_MODEL = BusinessProblemAnalysis

INSTRUCTIONS = """\
Task: analyze the business problem behind this request.

Produce:
- problem_statement: the underlying business problem in one to three \
sentences. Describe the problem, not the requested solution. For example, \
"customers can't see order status, so they call" rather than "build a tracking page".
- objectives: measurable business outcomes, as BO-01, BO-02, and so on. Set \
success_measure only if the input gives or clearly implies a measure. \
Otherwise leave it empty; do not invent targets such as "reduce calls by 30%".
- target_users: the people who will directly use the solution.
- current_state / future_state: short descriptions of how things work today \
and how they should work afterwards, based only on the input.
- in_scope / out_of_scope: include only what can be reasonably determined. \
Put boundaries that are unclear under ambiguities instead.
- ambiguities: statements that could be read in more than one way, or terms \
that need defining.
- conflicts: requirements or goals in the input that contradict each other. \
Leave this empty if there are none, and do not manufacture conflicts.
- is_too_vague: true only if the input lacks enough information to write \
meaningful requirements, for example because you cannot tell who the users \
are or what problem is being solved. A request that has gaps but a clear core \
need is NOT too vague.
- missing_information: the specific information needed before \
requirements can be written. This is required when is_too_vague is true.

Even when the request is too vague, give your best reading of the problem \
and at least one objective, marked "Assumed", so the stakeholder can see how \
it was interpreted.
"""


def build_prompt(project: ProjectInput) -> str:
    return render_prompt(INSTRUCTIONS, project)
