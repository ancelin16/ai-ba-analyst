"""Stage 1a: the questions a BA would ask before writing requirements."""

from app.models.artifacts import ClarifyingQuestionsResult
from app.models.inputs import ProjectInput
from app.prompts.base import render_prompt

OUTPUT_MODEL = ClarifyingQuestionsResult

INSTRUCTIONS = """\
Task: identify the questions a Business Analyst must ask stakeholders before \
the requirements for this request can be finalized.

Look for gaps in:
- Users and stakeholders: who uses it, who approves it, who is affected but not mentioned
- Scope: what is included and excluded, which channels, which regions or business units
- Data and systems: where the data lives, how current it is, which integrations are needed
- Business rules: validations, exceptions, error handling, approval rules
- Security and access: authentication, authorization, who may see what
- Compliance and privacy: personal data, regulations, retention
- Success measures: how the business will know the change worked
- Constraints: budget, timeline, technology, staffing

Categorize each question:
- "Critical": requirements would be wrong or incomplete without the answer. \
You must give a rationale explaining what goes wrong if it stays unanswered.
- "Important": it significantly shapes the design or priorities. A rationale is recommended.
- "Nice to Know": it refines the solution but does not block it.

Guidance:
- Do not ask about anything the input already answers.
- If stakeholder answers are included below, do not repeat questions they \
resolved. Ask follow-ups only where an answer raises something new.
- Make each question specific and answerable, not "Tell me more about X".
- Aim for roughly 8 to 15 questions for a typical request, and more if it is \
very vague. Put the most important questions first.
- Set "area" to a short topic label such as Users, Scope, Data, Integration, \
Security, Compliance, Business Rules, Success Metrics or Constraints.
"""


def build_prompt(project: ProjectInput) -> str:
    return render_prompt(INSTRUCTIONS, project)
