"""Markdown and Word export, process diagrams and the bundled example files."""

import io
import json

import pytest
from docx import Document

from app.models.analysis import Analysis
from app.models.artifacts import ProcessStep
from app.models.common import Level
from app.models.inputs import ProjectInput
from app.services.docx_export import build_docx
from app.services.examples import EXAMPLES_DIR, load_examples
from app.services.markdown_export import SECTIONS, full_report_md
from app.utils.formatting import risk_score
from app.utils.process_diagram import process_to_dot
from app.utils.validation import validate_project_input


@pytest.fixture
def complete(order_input, order_stages) -> Analysis:
    return Analysis(input=ProjectInput(**order_input), model="test-model", **order_stages)


# --- Markdown --------------------------------------------------------------------

def test_every_section_renders_markdown(complete):
    for key, (title, render) in SECTIONS.items():
        assert render(complete).strip(), f"{key} rendered empty"


def test_full_report_contains_all_artifacts(complete):
    md = full_report_md(complete)
    for fragment in ("# Online Order Tracking", "FR-003", "NFR-001", "US-001", "**Given** a customer",
                     "UC-01", "TC-003", "RK-01", "Q-01", "Requirements Traceability Matrix", "No gaps"):
        assert fragment in md


def test_markdown_escapes_table_pipes(complete):
    complete.requirements.functional[0].description = "The system shall accept A|B"
    assert "A\\|B" in full_report_md(complete)


def test_partial_analysis_skips_missing_sections(order_input, order_stages):
    partial = Analysis(input=ProjectInput(**order_input), problem=order_stages["problem"],
                       questions=order_stages["questions"])
    md = full_report_md(partial)
    assert "Business Problem Analysis" in md and "Clarifying Questions" in md
    assert "Functional Requirements" not in md


# --- Word ---------------------------------------------------------------------------

def test_docx_contains_headings_and_tables(complete):
    doc = Document(io.BytesIO(build_docx(complete)))
    headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
    for heading in ("1. Business Problem Analysis", "4. Requirements", "8. Requirements Traceability Matrix",
                    "10. Open and Answered Questions"):
        assert heading in headings
    cell_text = {c.text for t in doc.tables for row in t.rows for c in row.cells}
    assert {"FR-003", "NFR-001", "TC-003", "Fully traced"} <= cell_text


def test_docx_builds_for_partial_analysis(order_input, order_stages):
    partial = Analysis(input=ProjectInput(**order_input), problem=order_stages["problem"])
    assert build_docx(partial)[:2] == b"PK"  # .docx files are zip archives


# --- Process diagrams ------------------------------------------------------------

def steps(*specs):
    return [ProcessStep(id=i, actor=a, description=d, **extra) for i, a, d, extra in specs]


def test_linear_process_links_in_order():
    dot = process_to_dot(steps(("CS-01", "Customer", "Calls", {}), ("CS-02", "Agent", "Looks up", {})))
    assert 'start -> "CS-01";' in dot
    assert '"CS-01" -> "CS-02";' in dot
    assert '"CS-02" -> end;' in dot


def test_branches_and_unknown_targets():
    dot = process_to_dot(steps(
        ("FS-01", "System", "Validate", {"next_step_ids": ["FS-03", "FS-99"]}),
        ("FS-02", "System", "Show error", {}),
        ("FS-03", "System", "Show status", {}),
    ))
    assert '"FS-01" -> "FS-03";' in dot
    assert "FS-99" not in dot  # unknown targets are ignored, never drawn as broken nodes
    assert '"FS-01" -> "FS-02";' not in dot


def test_labels_are_escaped_and_colored():
    dot = process_to_dot(steps(('CS-01', 'Agent', 'Says "hello"', {"is_bottleneck": True})))
    assert 'Says \\"hello\\"' in dot
    assert "#F5B7B1" in dot and "⚠" in dot


def test_empty_process():
    assert "digraph" in process_to_dot([])


# --- Examples & helpers -------------------------------------------------------------

def test_bundled_examples_load_and_pass_validation():
    examples = load_examples()
    assert len(examples) >= 6
    for example in examples:
        assert validate_project_input(example.input).ok, example.slug


def test_broken_example_file_is_skipped(tmp_path):
    (tmp_path / "good.json").write_text((EXAMPLES_DIR / "06_vague.json").read_text())
    (tmp_path / "bad.json").write_text("{not json")
    (tmp_path / "missing.json").write_text(json.dumps({"summary": "no title or input"}))
    assert [e.slug for e in load_examples(tmp_path)] == ["good"]


def test_risk_score():
    assert risk_score(Level.HIGH, Level.HIGH) == 9
    assert risk_score(Level.LOW, Level.MEDIUM) == 2
