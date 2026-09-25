"""Small display helpers: colored badges using Streamlit's Markdown color syntax."""

from app.models.common import Basis, Level, Priority, ScenarioType

BASIS_COLORS = {Basis.STATED: "green", Basis.INFERRED: "blue", Basis.ASSUMED: "orange"}
PRIORITY_COLORS = {Priority.MUST: "red", Priority.SHOULD: "orange", Priority.COULD: "blue", Priority.WONT: "gray"}
SCENARIO_COLORS = {ScenarioType.POSITIVE: "green", ScenarioType.NEGATIVE: "red", ScenarioType.EDGE_CASE: "violet"}
LEVEL_COLORS = {Level.HIGH: "red", Level.MEDIUM: "orange", Level.LOW: "gray"}

BASIS_HELP = {
    Basis.STATED: "Explicitly stated in the request",
    Basis.INFERRED: "A reasonable conclusion from the request",
    Basis.ASSUMED: "Not in the request; confirm with stakeholders",
}


def badge(text: str, color: str) -> str:
    """Streamlit Markdown badge, e.g. :green-background[Stated]."""
    safe = text.replace("[", "(").replace("]", ")")
    return f":{color}-background[{safe}]"


def basis_badge(basis: Basis) -> str:
    return badge(basis.value, BASIS_COLORS[basis])


def priority_badge(priority: Priority) -> str:
    return badge(priority.value, PRIORITY_COLORS[priority])


def scenario_badge(scenario: ScenarioType) -> str:
    return badge(scenario.value, SCENARIO_COLORS[scenario])


def level_badge(level: Level, prefix: str = "") -> str:
    return badge(f"{prefix}{level.value}", LEVEL_COLORS[level])


def risk_score(likelihood: Level, impact: Level) -> int:
    """Likelihood x impact on a 1-3 scale (1-9), for sorting the risk register."""
    value = {Level.LOW: 1, Level.MEDIUM: 2, Level.HIGH: 3}
    return value[likelihood] * value[impact]
