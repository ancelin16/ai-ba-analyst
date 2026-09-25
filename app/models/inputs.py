"""The business request as entered by the user."""

from pydantic import BaseModel, ConfigDict, Field

from app.config import (
    MAX_OPTIONAL_FIELD_CHARS,
    MAX_PROJECT_NAME_CHARS,
    MAX_REQUEST_CHARS,
)


class ClarificationAnswer(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question_id: str
    question: str
    answer: str = ""


class ProjectInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    project_name: str = Field(min_length=1, max_length=MAX_PROJECT_NAME_CHARS)
    request: str = Field(min_length=1, max_length=MAX_REQUEST_CHARS)
    industry: str = Field(default="", max_length=MAX_OPTIONAL_FIELD_CHARS)
    stakeholders: str = Field(default="", max_length=MAX_OPTIONAL_FIELD_CHARS)
    existing_systems: str = Field(default="", max_length=MAX_OPTIONAL_FIELD_CHARS)
    constraints: str = Field(default="", max_length=MAX_OPTIONAL_FIELD_CHARS)
    # Stakeholder answers collected at the clarification step.
    clarifications: list[ClarificationAnswer] = Field(default_factory=list)

    def as_prompt_context(self) -> str:
        """Render the input as a labelled block for AI prompts.

        Empty optional fields are stated as "Not provided" so the model knows
        the information is missing rather than silently filling the gap.
        """
        def show(value: str) -> str:
            return value or "Not provided"

        lines = [
            f"Project name: {self.project_name}",
            f"Business request:\n{self.request}",
            f"Industry: {show(self.industry)}",
            f"Known stakeholders: {show(self.stakeholders)}",
            f"Existing systems: {show(self.existing_systems)}",
            f"Known constraints: {show(self.constraints)}",
        ]
        answered = [c for c in self.clarifications if c.answer]
        if answered:
            answers = "\n".join(f"- {c.question_id} {c.question}\n  Answer: {c.answer}" for c in answered)
            lines.append(f"Stakeholder answers to clarifying questions:\n{answers}")
        return "\n\n".join(lines)
