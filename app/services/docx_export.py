"""Export an analysis as a Word document (.docx), the format BA teams usually
circulate for review and sign-off.

Built from the structured data (not from Markdown), so tables are real Word
tables that reviewers can edit and comment on.
"""

from io import BytesIO

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from app.models.analysis import Analysis
from app.models.artifacts import QuestionCategory
from app.services.traceability import build_traceability

ACCENT = RGBColor(0x1F, 0x3A, 0x5F)
MUTED = RGBColor(0x5D, 0x6D, 0x7E)


def _shade(cell, hex_fill: str) -> None:
    props = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), hex_fill)
    props.append(shading)


def _table(doc: Document, headers: list[str], rows: list[list], widths: list[float] | None = None) -> None:
    if not rows:
        _note(doc, "None.")
        return
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for cell, header in zip(table.rows[0].cells, headers):
        cell.text = ""
        run = cell.paragraphs[0].add_run(header)
        run.bold = True
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        _shade(cell, "1F3A5F")
    for row in rows:
        cells = table.add_row().cells
        for cell, value in zip(cells, row):
            cell.text = ""
            run = cell.paragraphs[0].add_run(str(value))
            run.font.size = Pt(9)
    # Repeat the header row on each printed page.
    header_props = table.rows[0]._tr.get_or_add_trPr()
    repeat = OxmlElement("w:tblHeader")
    repeat.set(qn("w:val"), "true")
    header_props.append(repeat)
    doc.add_paragraph()


def _bullets(doc: Document, items: list[str], empty: str = "None identified.") -> None:
    if not items:
        _note(doc, empty)
        return
    for item in items:
        doc.add_paragraph(item, style="List Bullet")


def _note(doc: Document, text: str) -> None:
    run = doc.add_paragraph().add_run(text)
    run.italic = True
    run.font.color.rgb = MUTED


def _label(doc: Document, label: str, text: str) -> None:
    p = doc.add_paragraph()
    p.add_run(f"{label}: ").bold = True
    p.add_run(text)


def build_docx(a: Analysis) -> bytes:
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    for level in (1, 2, 3):
        doc.styles[f"Heading {level}"].font.color.rgb = ACCENT

    _cover(doc, a)
    _problem(doc, a)
    if a.stakeholders:
        _stakeholders(doc, a)
    if a.process:
        _process(doc, a)
    if a.requirements:
        _requirements(doc, a)
    if a.stories:
        _stories(doc, a)
    if a.use_cases:
        _use_cases(doc, a)
    if a.test_cases:
        _tests(doc, a)
    if a.requirements:
        _traceability(doc, a)
    if a.risks:
        _risks(doc, a)
    if a.questions:
        _questions(doc, a)

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


# --- Sections -------------------------------------------------------------------

def _cover(doc: Document, a: Analysis) -> None:
    title = doc.add_heading(a.input.project_name, level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    sub = doc.add_paragraph().add_run("Business Requirements Analysis")
    sub.font.size = Pt(14)
    sub.font.color.rgb = MUTED
    _label(doc, "Prepared", a.created_at.strftime("%d %B %Y"))
    if a.model:
        _label(doc, "Generated with", f"AI Business Requirements Analyst ({a.model})")
    _note(doc, "AI-assisted draft for stakeholder review. Items marked 'Assumed' and all open questions must be "
               "confirmed before sign-off.")

    doc.add_heading("Original request", level=1)
    doc.add_paragraph(a.input.request)
    context = [(k, v) for k, v in (
        ("Industry", a.input.industry), ("Known stakeholders", a.input.stakeholders),
        ("Existing systems", a.input.existing_systems), ("Constraints", a.input.constraints),
    ) if v]
    for label, value in context:
        _label(doc, label, value)
    if a.input.clarifications:
        doc.add_heading("Stakeholder clarifications", level=2)
        for c in a.input.clarifications:
            _label(doc, f"{c.question_id} {c.question}", c.answer)

    if a.requirements:
        report = build_traceability(a)
        m = report.metrics
        doc.add_heading("Summary", level=1)
        _bullets(doc, [
            f"{len(a.requirements.functional)} functional and {len(a.requirements.non_functional)} "
            f"non-functional requirements",
            f"{m['stories']} user stories, {m['acceptance_criteria']} acceptance criteria, {m['test_cases']} test cases",
            f"Test coverage: {m['requirements_tested']} of {m['requirements_in_scope']} in-scope requirements "
            f"({m['test_coverage_pct']}%)",
            f"Traceability gaps: {len(report.gaps)}",
        ])


def _problem(doc: Document, a: Analysis) -> None:
    p = a.problem
    doc.add_heading("1. Business Problem Analysis", level=1)
    if p.is_too_vague:
        _note(doc, "The request was assessed as too vague to write requirements. Information needed:")
        _bullets(doc, p.missing_information)
    doc.add_heading("Problem statement", level=2)
    doc.add_paragraph(p.problem_statement)
    doc.add_heading("Business objectives", level=2)
    _table(doc, ["ID", "Objective", "Success measure", "Basis"],
           [[o.id, o.description, o.success_measure or "To be defined", o.basis.value] for o in p.objectives])
    doc.add_heading("Current and future state", level=2)
    _label(doc, "Current state", p.current_state or "Not described in the request.")
    _label(doc, "Future state", p.future_state or "Not described in the request.")
    _label(doc, "Target users", ", ".join(p.target_users) or "Not specified")
    doc.add_heading("Scope", level=2)
    doc.add_paragraph().add_run("In scope").bold = True
    _bullets(doc, p.in_scope)
    doc.add_paragraph().add_run("Out of scope").bold = True
    _bullets(doc, p.out_of_scope)
    doc.add_heading("Ambiguities and conflicts", level=2)
    _bullets(doc, p.ambiguities)
    doc.add_paragraph().add_run("Conflicting requirements").bold = True
    _bullets(doc, p.conflicts, "No conflicts detected.")


def _stakeholders(doc: Document, a: Analysis) -> None:
    doc.add_heading("2. Stakeholders", level=1)
    _table(doc, ["ID", "Stakeholder", "Type", "Interest", "Influence", "Impact", "Basis"], [
        [s.id, s.name + (" (not in request)" if s.potentially_missing else ""), s.type.value, s.interest,
         s.influence.value, s.impact.value, s.basis.value]
        for s in a.stakeholders.stakeholders
    ])


def _process(doc: Document, a: Analysis) -> None:
    p = a.process
    doc.add_heading("3. Process Analysis", level=1)
    if not p.sufficient_detail:
        _note(doc, "The request does not describe the current process in enough detail to map it fully. " + p.notes)
    for title, steps in (("Current state", p.current_state), ("Future state", p.future_state)):
        doc.add_heading(title, level=2)
        _table(doc, ["Step", "Actor", "Activity", "Manual", "Bottleneck"], [
            [s.id, s.actor, s.description, "Yes" if s.is_manual else "", "Yes" if s.is_bottleneck else ""]
            for s in steps
        ])
    for title, items in (("Bottlenecks", p.bottlenecks), ("Manual activities", p.manual_activities),
                         ("Inefficiencies", p.inefficiencies), ("Automation opportunities", p.automation_opportunities)):
        doc.add_heading(title, level=3)
        _bullets(doc, items)


def _requirements(doc: Document, a: Analysis) -> None:
    r = a.requirements
    doc.add_heading("4. Requirements", level=1)
    doc.add_heading("Functional requirements", level=2)
    _table(doc, ["ID", "Requirement", "Priority", "Rationale", "Objectives", "Basis"], [
        [x.id, x.description, x.priority.value, x.rationale, ", ".join(x.objective_ids), x.basis.value]
        for x in r.functional
    ])
    doc.add_heading("Non-functional requirements", level=2)
    _table(doc, ["ID", "Category", "Requirement", "Priority", "Why it matters", "Target"], [
        [x.id, x.category.value, x.description, x.priority.value, x.rationale, x.measurable_target or "To be agreed"]
        for x in r.non_functional
    ])


def _stories(doc: Document, a: Analysis) -> None:
    doc.add_heading("5. User Stories and Acceptance Criteria", level=1)
    criteria = a.criteria.criteria if a.criteria else []
    for s in a.stories.stories:
        doc.add_heading(f"{s.id} ({s.priority.value})", level=2)
        doc.add_paragraph().add_run(s.text).italic = True
        _label(doc, "Business value", s.business_value)
        _label(doc, "Requirements", ", ".join(s.requirement_ids))
        for c in (c for c in criteria if c.story_id == s.id):
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(f"{c.id} {c.title} ({c.scenario_type.value}): ").bold = True
            p.add_run(f"Given {c.given}, when {c.when}, then {c.then}.")


def _use_cases(doc: Document, a: Analysis) -> None:
    doc.add_heading("6. Use Cases", level=1)
    for uc in a.use_cases.use_cases:
        doc.add_heading(f"{uc.id}: {uc.name}", level=2)
        _label(doc, "Primary actor", uc.primary_actor)
        _label(doc, "Goal", uc.goal)
        _label(doc, "Related requirements", ", ".join(uc.requirement_ids) or "n/a")
        doc.add_paragraph().add_run("Preconditions").bold = True
        _bullets(doc, uc.preconditions, "None.")
        doc.add_paragraph().add_run("Main flow").bold = True
        for step in uc.main_flow:
            doc.add_paragraph(step, style="List Number")
        for label, flows in (("Alternative flows", uc.alternative_flows), ("Exceptions", uc.exceptions)):
            doc.add_paragraph().add_run(label).bold = True
            if not flows:
                _note(doc, "None.")
            for f in flows:
                doc.add_paragraph(f"{f.name}: " + " → ".join(f.steps), style="List Bullet")
        doc.add_paragraph().add_run("Postconditions").bold = True
        _bullets(doc, uc.postconditions, "None.")


def _tests(doc: Document, a: Analysis) -> None:
    doc.add_heading("7. Test Cases", level=1)
    _table(doc, ["ID", "Traces to", "Scenario", "Type", "Preconditions", "Steps", "Expected result", "Priority"], [
        [t.id, ", ".join(t.requirement_ids + t.criterion_ids), t.scenario, t.scenario_type.value,
         "; ".join(t.preconditions) or "-", "\n".join(f"{i}. {s}" for i, s in enumerate(t.steps, 1)),
         t.expected_result, t.priority.value]
        for t in a.test_cases.test_cases
    ])


def _traceability(doc: Document, a: Analysis) -> None:
    report = build_traceability(a)
    doc.add_heading("8. Requirements Traceability Matrix", level=1)
    m = report.matrix
    columns = ["Business Objectives", "Requirement", "Priority", "User Stories", "Acceptance Criteria",
               "Test Cases", "Trace Status"]
    _table(doc, columns, m[columns].astype(str).values.tolist())
    doc.add_heading("Coverage check", level=2)
    _bullets(doc, [f"[{g.severity}] {g.message}" for g in report.gaps] + report.dangling_references,
             "No gaps: every in-scope requirement traces from a business objective to at least one test.")


def _risks(doc: Document, a: Analysis) -> None:
    r = a.risks
    doc.add_heading("9. Risks, Assumptions and Constraints", level=1)
    doc.add_heading("Risk register", level=2)
    _table(doc, ["ID", "Risk", "Source", "Likelihood", "Impact", "Mitigation"],
           [[x.id, x.description, x.source.value, x.likelihood.value, x.impact.value, x.mitigation] for x in r.risks])
    doc.add_heading("Assumptions", level=2)
    _table(doc, ["ID", "Assumption", "Impact if wrong", "Validate with"],
           [[x.id, x.description, x.impact_if_wrong, x.validate_with or "-"] for x in r.assumptions])
    doc.add_heading("Constraints", level=2)
    _table(doc, ["ID", "Constraint", "Type", "Basis"],
           [[x.id, x.description, x.type or "-", x.basis.value] for x in r.constraints])
    doc.add_heading("Edge cases", level=2)
    _bullets(doc, r.edge_cases)


def _questions(doc: Document, a: Analysis) -> None:
    doc.add_heading("10. Open and Answered Questions", level=1)
    answers = {c.question_id: c.answer for c in a.input.clarifications}
    for category in QuestionCategory:
        items = [q for q in a.questions.questions if q.category == category]
        if not items:
            continue
        doc.add_heading(category.value, level=2)
        _table(doc, ["ID", "Area", "Question", "Why it matters", "Answer"], [
            [q.id, q.area or "-", q.question, q.rationale or "-", answers.get(q.id, "Open")] for q in items
        ])
