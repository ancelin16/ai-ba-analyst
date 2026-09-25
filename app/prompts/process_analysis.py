"""Stage 2b: current-state and future-state process analysis."""

from app.models.artifacts import BusinessProblemAnalysis, ProcessAnalysis
from app.models.inputs import ProjectInput
from app.prompts.base import render_prompt

OUTPUT_MODEL = ProcessAnalysis

INSTRUCTIONS = """\
Task: map the business process behind this request as it works today \
(current state) and as it should work after the change (future state), then \
analyze it for improvement.

Process steps:
- Current-state steps use IDs CS-01, CS-02, and so on. Future-state steps use \
FS-01, FS-02, and so on.
- Each step has one actor (a role or system) and one short action in verb-object \
form, e.g. "Looks up order in order system".
- Steps run in list order by default. Use next_step_ids only for a branch or \
decision, e.g. a step that leads to either FS-04 or FS-06. Refer only to step \
IDs within the same state.
- Set is_manual for steps done by a person without system support, and \
is_bottleneck for steps that cause delay, queues or rework.
- Keep each state to about 4 to 10 steps at the level a business stakeholder \
would recognize.

Analysis:
- bottlenecks, manual_activities, inefficiencies: specific to the steps above.
- automation_opportunities: where technology could remove or speed up a step. \
Name the step and the benefit.

Set sufficient_detail to false if the input says too little about how work \
is done today to map it credibly. In that case, return only the steps that \
can reasonably be inferred, and explain in notes what information is needed \
to complete the map. Do not invent detailed process steps to fill the gap.
"""


def build_prompt(project: ProjectInput, problem: BusinessProblemAnalysis) -> str:
    return render_prompt(INSTRUCTIONS, project, {"problem_analysis": problem})
