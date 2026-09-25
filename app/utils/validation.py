"""Input validation that runs locally before any AI call.

Two levels:
- errors block the analysis (empty, too long, too short to analyse);
- warnings let it proceed but tell the user what a BA would find missing.

The vagueness check here is a cheap heuristic. The AI does a deeper
assessment in Stage 1 and can still stop the pipeline.
"""

import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.config import (
    MAX_OPTIONAL_FIELD_CHARS,
    MAX_PROJECT_NAME_CHARS,
    MAX_REQUEST_CHARS,
    MIN_REQUEST_WORDS,
)
from app.models.inputs import ProjectInput

# Signals that the request names who is affected.
ACTOR_TERMS = (
    "customer", "client", "user", "employee", "staff", "team", "manager",
    "agent", "rep", "patient", "student", "vendor", "supplier", "partner",
    "admin", "department", "sales", "hr", "finance", "it ", "traveler",
    "traveller", "member", "guest", "buyer", "seller", "driver", "technician",
)
# Signals that the request explains why the change is needed.
PURPOSE_TERMS = (
    "because", "so that", "so we", "in order to", "to reduce", "to improve",
    "to increase", "too many", "too much", "too long", "slow", "manual",
    "error", "mistake", "delay", "complain", "cost", "time-consuming",
    "inefficien", "lose", "losing", "lost", "difficult", "hard to", "problem",
    "issue", "struggle", "frustrat", "backlog", "spreadsheet", "paper",
)
# Signals of a desired capability or outcome.
CAPABILITY_TERMS = (
    "want", "need", "should", "would like", "able to", "allow", "enable",
    "automate", "track", "manage", "request", "book", "schedule", "view",
    "report", "notify", "approve", "replace", "build", "create", "system",
)

FIELD_LABELS = {
    "project_name": "Project name",
    "request": "Business request",
    "industry": "Industry",
    "stakeholders": "Stakeholders",
    "existing_systems": "Existing systems",
    "constraints": "Constraints",
}


@dataclass
class ValidationResult:
    input: ProjectInput | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and self.input is not None


def normalize_text(value: str | None) -> str:
    """Trim, collapse runs of spaces/tabs, and cap blank lines at one."""
    if not value:
        return ""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n\s*\n+", "\n\n", value)
    return value.strip()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def assess_vagueness(request: str) -> list[str]:
    """Return plain-language descriptions of what the request seems to lack."""
    text = f" {request.lower()} "
    missing = []
    if not _contains_any(text, ACTOR_TERMS):
        missing.append("Who is affected: which users, customers or teams have this problem?")
    if not _contains_any(text, PURPOSE_TERMS):
        missing.append("Why it matters: what problem, cost or pain point is driving the request?")
    if not _contains_any(text, CAPABILITY_TERMS):
        missing.append("What is wanted: what should people be able to do after the change?")
    return missing


def validate_project_input(raw: dict) -> ValidationResult:
    """Validate and normalize raw form data into a ProjectInput."""
    result = ValidationResult()
    data = {key: normalize_text(raw.get(key)) for key in FIELD_LABELS}

    if not data["project_name"]:
        result.errors.append("Project name is required.")
    elif len(data["project_name"]) > MAX_PROJECT_NAME_CHARS:
        result.errors.append(f"Project name must be {MAX_PROJECT_NAME_CHARS} characters or fewer.")

    request = data["request"]
    word_count = len(request.split())
    if not request:
        result.errors.append("Please describe the business request or problem.")
    elif len(request) > MAX_REQUEST_CHARS:
        result.errors.append(
            f"The business request is {len(request):,} characters. The limit is "
            f"{MAX_REQUEST_CHARS:,}. Summarise it, or split it into separate projects."
        )
    elif word_count < MIN_REQUEST_WORDS:
        result.errors.append(
            f"The business request is too short to analyse ({word_count} words). "
            "Describe who has the problem, what the problem is, and what outcome you want."
        )
    else:
        gaps = assess_vagueness(request)
        if len(gaps) >= 2:
            result.warnings.append(
                "This request is quite vague. The analysis will focus on clarifying questions. Consider adding:"
            )
            result.warnings.extend(gaps)
        elif gaps:
            result.warnings.append(f"Consider adding: {gaps[0]}")

    for key in ("industry", "stakeholders", "existing_systems", "constraints"):
        if len(data[key]) > MAX_OPTIONAL_FIELD_CHARS:
            result.errors.append(
                f"{FIELD_LABELS[key]} must be {MAX_OPTIONAL_FIELD_CHARS:,} characters or fewer."
            )

    if result.errors:
        return result

    try:
        result.input = ProjectInput(**data)
    except ValidationError as exc:  # defensive: the checks above should catch everything
        result.errors.extend(
            f"{FIELD_LABELS.get(str(err['loc'][0]), err['loc'][0])}: {err['msg']}" for err in exc.errors()
        )
    return result
