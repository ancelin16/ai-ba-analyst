"""Render each analysis section as Markdown.

Used by the per-section copy buttons and the full-document export, so a
section reads the same wherever it ends up (Jira, Confluence, email, Word).
"""

from collections.abc import Callable

from app.models.analysis import Analysis
from app.models.artifacts import QuestionCategory
from app.services.traceability import build_traceability


def _bullets(items: list[str], empty: str = "_None identified._") -> str:
    return "\n".join(f"- {item}" for item in items) if items else empty


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def _table(headers: list[str], rows: list[list]) -> str:
    if not rows:
        return "_None._"
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


# --- Sections -----------------------------------------------------------------

def overview_md(a: Analysis) -> str:
    p = a.problem
    parts = [f"# {a.input.project_name}", "## Original request", f"> {a.input.request}"]
    if p:
        parts += ["## Problem statement", p.problem_statement]
        parts += ["## Business objectives", _table(
            ["ID", "Objective", "Success measure", "Basis"],
            [[o.id, o.description, o.success_measure or "To be defined", o.basis.value] for o in p.objectives],
        )]
    if a.requirements:
        report = build_traceability(a)
        m = report.metrics
        parts += ["## Summary", _bullets([
            f"{len(a.requirements.functional)} functional and {len(a.requirements.non_functional)} non-functional requirements",
            f"{m['stories']} user stories, {m['acceptance_criteria']} acceptance criteria, {m['test_cases']} test cases",
            f"Test coverage: {m['requirements_tested']} of {m['requirements_in_scope']} in-scope requirements ({m['test_coverage_pct']}%)",
            f"Traceability gaps: {len(report.gaps)}",
        ])]
    return "\n\n".join(parts)


def problem_md(a: Analysis) -> str:
    p = a.problem
    if not p:
        return ""
    parts = [
        "## Business Problem Analysis",
        "### Problem statement", p.problem_statement,
        "### Objectives", _table(
            ["ID", "Objective", "Success measure", "Basis"],
            [[o.id, o.description, o.success_measure or "To be defined", o.basis.value] for o in p.objectives],
        ),
        "### Target users", _bullets(p.target_users),
        "### Current state", p.current_state or "_Not described in the request._",
        "### Desired future state", p.future_state or "_Not described in the request._",
        "### In scope", _bullets(p.in_scope),
        "### Out of scope", _bullets(p.out_of_scope),
        "### Ambiguities", _bullets(p.ambiguities),
        "### Conflicting requirements", _bullets(p.conflicts, "_No conflicts detected._"),
    ]
    if p.is_too_vague:
        parts += ["### ⚠ Information needed before requirements can be written", _bullets(p.missing_information)]
    return "\n\n".join(parts)


def stakeholders_md(a: Analysis) -> str:
    if not a.stakeholders:
        return ""
    rows = [
        [s.id, s.name + (" ⚠ not mentioned in request" if s.potentially_missing else ""), s.type.value,
         s.interest, s.influence.value, s.impact.value, s.basis.value]
        for s in a.stakeholders.stakeholders
    ]
    return "## Stakeholders\n\n" + _table(
        ["ID", "Stakeholder", "Type", "Interest", "Influence", "Impact", "Basis"], rows
    )


def requirements_md(a: Analysis) -> str:
    r = a.requirements
    if not r:
        return ""
    fr = _table(
        ["ID", "Requirement", "Priority", "Rationale", "Objectives", "Basis"],
        [[x.id, x.description, x.priority.value, x.rationale, ", ".join(x.objective_ids), x.basis.value]
         for x in r.functional],
    )
    nfr = _table(
        ["ID", "Category", "Requirement", "Priority", "Why it matters", "Target", "Basis"],
        [[x.id, x.category.value, x.description, x.priority.value, x.rationale,
          x.measurable_target or "To be agreed", x.basis.value] for x in r.non_functional],
    )
    return f"## Functional Requirements\n\n{fr}\n\n## Non-Functional Requirements\n\n{nfr}"


def stories_md(a: Analysis) -> str:
    if not a.stories:
        return ""
    criteria = a.criteria.criteria if a.criteria else []
    parts = ["## User Stories"]
    for s in a.stories.stories:
        parts.append(
            f"### {s.id} ({s.priority.value})\n\n**{s.text}**\n\n"
            f"- Business value: {s.business_value}\n- Requirements: {', '.join(s.requirement_ids)}"
        )
        story_criteria = [c for c in criteria if c.story_id == s.id]
        if story_criteria:
            parts.append("Acceptance criteria:\n\n" + "\n".join(f"- {c.id}: {c.title}" for c in story_criteria))
    return "\n\n".join(parts)


def criteria_md(a: Analysis) -> str:
    if not a.criteria:
        return ""
    parts = ["## Acceptance Criteria"]
    stories = {s.id: s for s in a.stories.stories} if a.stories else {}
    for story_id in dict.fromkeys(c.story_id for c in a.criteria.criteria):
        heading = f"### {story_id}"
        if story_id in stories:
            heading += f": {stories[story_id].want}"
        parts.append(heading)
        for c in (c for c in a.criteria.criteria if c.story_id == story_id):
            parts.append(
                f"**{c.id}: {c.title}** _({c.scenario_type.value})_\n\n"
                f"**Given** {c.given},  \n**When** {c.when},  \n**Then** {c.then}."
            )
    return "\n\n".join(parts)


def _flows(flows) -> str:
    return "\n".join(
        f"- **{f.name}**\n" + "\n".join(f"  {i}. {step}" for i, step in enumerate(f.steps, 1)) for f in flows
    ) or "_None._"


def use_cases_md(a: Analysis) -> str:
    if not a.use_cases:
        return ""
    parts = ["## Use Cases"]
    for uc in a.use_cases.use_cases:
        parts.append("\n\n".join([
            f"### {uc.id}: {uc.name}",
            f"- **Primary actor:** {uc.primary_actor}\n- **Goal:** {uc.goal}\n"
            f"- **Related requirements:** {', '.join(uc.requirement_ids) or 'n/a'}",
            "**Preconditions**\n\n" + _bullets(uc.preconditions),
            "**Main flow**\n\n" + "\n".join(f"{i}. {step}" for i, step in enumerate(uc.main_flow, 1)),
            "**Alternative flows**\n\n" + _flows(uc.alternative_flows),
            "**Exceptions**\n\n" + _flows(uc.exceptions),
            "**Postconditions**\n\n" + _bullets(uc.postconditions),
        ]))
    return "\n\n".join(parts)


def process_md(a: Analysis) -> str:
    p = a.process
    if not p:
        return ""

    def steps(items):
        return _table(
            ["Step", "Actor", "Activity", "Manual", "Bottleneck"],
            [[s.id, s.actor, s.description, "Yes" if s.is_manual else "", "Yes" if s.is_bottleneck else ""]
             for s in items],
        )

    parts = ["## Process Analysis"]
    if not p.sufficient_detail:
        parts.append("> ⚠ The request does not describe the current process in enough detail to map it fully.")
    if p.notes:
        parts.append(p.notes)
    parts += [
        "### Current state", steps(p.current_state),
        "### Future state", steps(p.future_state),
        "### Bottlenecks", _bullets(p.bottlenecks),
        "### Manual activities", _bullets(p.manual_activities),
        "### Inefficiencies", _bullets(p.inefficiencies),
        "### Automation opportunities", _bullets(p.automation_opportunities),
    ]
    return "\n\n".join(parts)


def traceability_md(a: Analysis) -> str:
    report = build_traceability(a)
    if report.matrix.empty:
        return ""
    m = report.matrix
    parts = [
        "## Requirements Traceability Matrix",
        _table(list(m.columns), m.astype(str).values.tolist()),
        "### Coverage gaps",
        _bullets([f"[{g.severity}] {g.message}" for g in report.gaps], "_No gaps: every in-scope requirement is traced._"),
    ]
    if report.dangling_references:
        parts += ["### Broken references", _bullets(report.dangling_references)]
    return "\n\n".join(parts)


def test_cases_md(a: Analysis) -> str:
    if not a.test_cases:
        return ""
    rows = [
        [t.id, ", ".join(t.requirement_ids + t.criterion_ids), t.scenario, t.scenario_type.value,
         "\n".join(t.preconditions) or "-", "\n".join(f"{i}. {s}" for i, s in enumerate(t.steps, 1)),
         t.expected_result, t.priority.value]
        for t in a.test_cases.test_cases
    ]
    return "## Test Cases\n\n" + _table(
        ["ID", "Traces to", "Scenario", "Type", "Preconditions", "Steps", "Expected result", "Priority"], rows
    )


def risks_md(a: Analysis) -> str:
    r = a.risks
    if not r:
        return ""
    return "\n\n".join([
        "## Risk Register",
        _table(["ID", "Risk", "Source", "Likelihood", "Impact", "Mitigation"],
               [[x.id, x.description, x.source.value, x.likelihood.value, x.impact.value, x.mitigation]
                for x in r.risks]),
        "## Assumptions",
        _table(["ID", "Assumption", "Impact if wrong", "Validate with"],
               [[x.id, x.description, x.impact_if_wrong, x.validate_with or "-"] for x in r.assumptions]),
        "## Constraints",
        _table(["ID", "Constraint", "Type", "Basis"],
               [[x.id, x.description, x.type or "-", x.basis.value] for x in r.constraints]),
        "## Edge cases",
        _bullets(r.edge_cases),
    ])


def questions_md(a: Analysis) -> str:
    if not a.questions:
        return ""
    answers = {c.question_id: c.answer for c in a.input.clarifications}
    parts = ["## Clarifying Questions"]
    for category in QuestionCategory:
        items = [q for q in a.questions.questions if q.category == category]
        if not items:
            continue
        parts.append(f"### {category.value}")
        for q in items:
            line = f"- **{q.id}** ({q.area or 'General'}): {q.question}"
            if q.rationale:
                line += f"\n  - _Why it matters:_ {q.rationale}"
            if q.id in answers:
                line += f"\n  - **Answer:** {answers[q.id]}"
            parts.append(line)
    return "\n\n".join(parts)


# Tab key -> (tab label, renderer). Order matches the results dashboard.
SECTIONS: dict[str, tuple[str, Callable[[Analysis], str]]] = {
    "overview": ("Overview", overview_md),
    "problem": ("Business Problem", problem_md),
    "stakeholders": ("Stakeholders", stakeholders_md),
    "requirements": ("Requirements", requirements_md),
    "stories": ("User Stories", stories_md),
    "criteria": ("Acceptance Criteria", criteria_md),
    "use_cases": ("Use Cases", use_cases_md),
    "process": ("Process Analysis", process_md),
    "traceability": ("Traceability Matrix", traceability_md),
    "test_cases": ("Test Cases", test_cases_md),
    "risks": ("Risks & Assumptions", risks_md),
    "questions": ("Clarifying Questions", questions_md),
}


def full_report_md(a: Analysis) -> str:
    """The whole analysis as one Markdown document."""
    return "\n\n---\n\n".join(md for _, render in SECTIONS.values() if (md := render(a)))
