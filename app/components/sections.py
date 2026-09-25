"""Renderers for the 12 result tabs. Each takes the Analysis and draws one tab.

Tables use pandas DataFrames (sortable, searchable in the UI). Narrative
content uses Markdown with colored badges for priority, basis and scenario type.
"""

import pandas as pd
import streamlit as st

from app.components.common import empty_state, section_header, subsection
from app.models.analysis import Analysis
from app.models.artifacts import QuestionCategory
from app.services.markdown_export import SECTIONS
from app.services.traceability import FULLY_TRACED, NOT_TESTED, OUT_OF_SCOPE, PARTIAL, build_traceability
from app.utils.formatting import basis_badge, level_badge, priority_badge, risk_score, scenario_badge
from app.utils.process_diagram import process_to_dot


def _header(key: str, a: Analysis, caption: str = "") -> None:
    title, render_md = SECTIONS[key]
    section_header(title, render_md(a), key, caption)


def _bullets(items: list[str], empty: str = "None identified.") -> None:
    if items:
        st.markdown("\n".join(f"- {i}" for i in items))
    else:
        st.caption(empty)


def _table(rows: list[dict], **column_config) -> None:
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True, column_config=column_config or None)


# --- 1. Overview ---------------------------------------------------------------------

def overview(a: Analysis) -> None:
    _header("overview", a)
    if a.is_demo:
        st.info("You're viewing a pre-generated example analysis.", icon=":material/visibility:")
    with subsection("Original request"):
        st.markdown(f"> {a.input.request}")
        context = {
            "Industry": a.input.industry, "Stakeholders": a.input.stakeholders,
            "Existing systems": a.input.existing_systems, "Constraints": a.input.constraints,
        }
        st.caption(" · ".join(f"**{k}:** {v}" for k, v in context.items() if v) or "No optional context provided.")

    if a.requirements:
        report = build_traceability(a)
        m = report.metrics
        cols = st.columns(5)
        cols[0].metric("Requirements", len(a.requirements.functional) + len(a.requirements.non_functional),
                       help="Functional + non-functional")
        cols[1].metric("User stories", m["stories"])
        cols[2].metric("Test cases", m["test_cases"])
        cols[3].metric("Test coverage", f"{m['test_coverage_pct']}%", help="In-scope requirements with at least one test")
        if a.is_complete:
            cols[4].metric("Trace gaps", len(report.gaps), delta=None if report.gaps else "fully traced",
                           delta_color="off")
        else:
            cols[4].metric("Trace gaps", "–", help="Available once the analysis is complete")

    p = a.problem
    with subsection("Problem & objectives"):
        st.markdown(f"**Problem statement:** {p.problem_statement}")
        for o in p.objectives:
            measure = f" · _Success measure:_ {o.success_measure}" if o.success_measure else " · _Success measure: to be defined_"
            st.markdown(f"- **{o.id}** {o.description} {basis_badge(o.basis)}{measure}")

    if a.questions or (a.risks and a.risks.assumptions):
        with subsection("What still needs confirming"):
            critical = [q for q in a.questions.questions if q.category == QuestionCategory.CRITICAL] if a.questions else []
            answered = {c.question_id for c in a.input.clarifications}
            open_critical = [q for q in critical if q.id not in answered]
            c1, c2, c3 = st.columns(3)
            c1.metric("Open critical questions", len(open_critical))
            c2.metric("Documented assumptions", len(a.risks.assumptions) if a.risks else 0)
            c3.metric("Conflicts detected", len(p.conflicts))
            if p.conflicts:
                st.warning("\n".join(f"- {c}" for c in p.conflicts), icon=":material/call_split:")


# --- 2. Business problem ---------------------------------------------------------

def problem(a: Analysis) -> None:
    _header("problem", a)
    p = a.problem
    if p.is_too_vague:
        st.error("**Too vague to write requirements.** Missing:\n\n" + "\n".join(f"- {m}" for m in p.missing_information))
    with subsection("Problem statement & objectives"):
        st.markdown(p.problem_statement)
        _table([{"ID": o.id, "Objective": o.description, "Success measure": o.success_measure or "To be defined",
                 "Basis": o.basis.value} for o in p.objectives])
        st.markdown("**Target users:** " + (", ".join(p.target_users) or "_not specified_"))
    with subsection("Current state → future state"):
        c1, c2 = st.columns(2)
        c1.markdown("**Current state**")
        c1.markdown(p.current_state or "_Not described in the request._")
        c2.markdown("**Desired future state**")
        c2.markdown(p.future_state or "_Not described in the request._")
    with subsection("Scope"):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**In scope**")
            _bullets(p.in_scope)
        with c2:
            st.markdown("**Out of scope**")
            _bullets(p.out_of_scope)
    with subsection(f"Ambiguities ({len(p.ambiguities)}) & conflicts ({len(p.conflicts)})"):
        st.markdown("**Ambiguities**: statements that could be read more than one way")
        _bullets(p.ambiguities)
        st.markdown("**Conflicting requirements**")
        _bullets(p.conflicts, "No conflicts detected.")


# --- 3. Stakeholders ----------------------------------------------------------------

def stakeholders(a: Analysis) -> None:
    if not a.stakeholders:
        return empty_state("Stakeholder analysis has not been generated yet.")
    _header("stakeholders", a, "Influence = power over decisions · Impact = how much the change affects them")
    items = a.stakeholders.stakeholders
    missing = [s for s in items if s.potentially_missing]
    if missing:
        st.warning(
            f"**{len(missing)} stakeholder(s) not mentioned in the request** but likely needed: "
            + ", ".join(s.name for s in missing),
            icon=":material/person_search:",
        )
    with subsection("Stakeholder register"):
        _table([{
            "ID": s.id, "Stakeholder": s.name, "Type": s.type.value, "Interest": s.interest,
            "Influence": s.influence.value, "Impact": s.impact.value, "Basis": s.basis.value,
            "Not in request": "⚠" if s.potentially_missing else "",
        } for s in items], Interest=st.column_config.TextColumn(width="large"))
    with subsection("Engagement grid (influence × impact)"):
        grid = {
            ("High", "High"): "Manage closely", ("High", "Medium"): "Manage closely",
            ("High", "Low"): "Keep satisfied", ("Medium", "High"): "Keep informed & involved",
            ("Low", "High"): "Keep informed", ("Medium", "Medium"): "Keep informed",
        }
        groups: dict[str, list[str]] = {}
        for s in items:
            strategy = grid.get((s.influence.value, s.impact.value), "Monitor")
            groups.setdefault(strategy, []).append(s.name)
        cols = st.columns(len(groups))
        for col, (strategy, names) in zip(cols, groups.items()):
            col.markdown(f"**{strategy}**")
            col.markdown("\n".join(f"- {n}" for n in names))


# --- 4. Requirements ------------------------------------------------------------------

def requirements(a: Analysis) -> None:
    if not a.requirements:
        return empty_state("Requirements have not been generated yet.")
    r = a.requirements
    _header("requirements", a, "MoSCoW priority · every requirement traces to a business objective")
    counts = pd.Series([x.priority.value for x in r.functional + r.non_functional]).value_counts()
    cols = st.columns(4)
    for col, label in zip(cols, ["Must Have", "Should Have", "Could Have", "Won't Have"]):
        col.metric(label, int(counts.get(label, 0)))

    with subsection(f"Functional requirements ({len(r.functional)})"):
        _table([{
            "ID": x.id, "Requirement": x.description, "Priority": x.priority.value, "Rationale": x.rationale,
            "Objectives": ", ".join(x.objective_ids), "Basis": x.basis.value,
        } for x in r.functional], Requirement=st.column_config.TextColumn(width="large"),
            Rationale=st.column_config.TextColumn(width="medium"))
    with subsection(f"Non-functional requirements ({len(r.non_functional)})"):
        for x in r.non_functional:
            st.markdown(f"**{x.id}** · **{x.category.value}** {priority_badge(x.priority)} {basis_badge(x.basis)}")
            st.markdown(x.description)
            st.caption(f"Why it matters: {x.rationale}")
            st.caption(f"Target: {x.measurable_target or 'to be agreed with stakeholders (not specified in the request)'}")


# --- 5. User stories ------------------------------------------------------------------

def stories(a: Analysis) -> None:
    if not a.stories:
        return empty_state("User stories have not been generated yet.")
    _header("stories", a)
    criteria = a.criteria.criteria if a.criteria else []
    for s in a.stories.stories:
        with subsection(f"{s.id} · {s.want[:80]}"):
            st.markdown(f"{priority_badge(s.priority)} · Requirements: `{'`, `'.join(s.requirement_ids)}`")
            st.markdown(f"> **As a** {s.role},  \n> **I want** {s.want},  \n> **so that** {s.so_that}.")
            st.markdown(f"**Business value:** {s.business_value}")
            story_criteria = [c for c in criteria if c.story_id == s.id]
            if story_criteria:
                st.markdown("**Acceptance criteria**")
                for c in story_criteria:
                    st.markdown(f"- {scenario_badge(c.scenario_type)} **{c.id}** {c.title}")


# --- 6. Acceptance criteria ------------------------------------------------------------

def criteria(a: Analysis) -> None:
    if not a.criteria:
        return empty_state("Acceptance criteria have not been generated yet.")
    _header("criteria", a, "Given / When / Then · positive, negative and edge-case scenarios")
    items = a.criteria.criteria
    counts = pd.Series([c.scenario_type.value for c in items]).value_counts()
    cols = st.columns(3)
    for col, label in zip(cols, ["Positive", "Negative", "Edge Case"]):
        col.metric(label, int(counts.get(label, 0)))
    stories_by_id = {s.id: s for s in a.stories.stories} if a.stories else {}
    for story_id in dict.fromkeys(c.story_id for c in items):
        story = stories_by_id.get(story_id)
        with subsection(f"{story_id} · {story.want[:80] if story else ''}"):
            for c in (c for c in items if c.story_id == story_id):
                st.markdown(f"{scenario_badge(c.scenario_type)} **{c.id}: {c.title}**")
                st.markdown(f"**Given** {c.given},  \n**When** {c.when},  \n**Then** {c.then}.")


# --- 7. Use cases -----------------------------------------------------------------------

def use_cases(a: Analysis) -> None:
    if not a.use_cases:
        return empty_state("Use cases have not been generated yet.")
    _header("use_cases", a)
    for uc in a.use_cases.use_cases:
        with subsection(f"{uc.id}: {uc.name}"):
            c1, c2 = st.columns(2)
            c1.markdown(f"**Primary actor:** {uc.primary_actor}  \n**Goal:** {uc.goal}")
            c2.markdown(f"**Related requirements:** {', '.join(uc.requirement_ids) or 'n/a'}")
            st.markdown("**Preconditions**")
            _bullets(uc.preconditions, "None.")
            st.markdown("**Main flow**")
            st.markdown("\n".join(f"{i}. {step}" for i, step in enumerate(uc.main_flow, 1)))
            for label, flows in (("Alternative flows", uc.alternative_flows), ("Exceptions", uc.exceptions)):
                st.markdown(f"**{label}**")
                if not flows:
                    st.caption("None.")
                for f in flows:
                    st.markdown(f"*{f.name}*\n" + "\n".join(f"{i}. {step}" for i, step in enumerate(f.steps, 1)))
            st.markdown("**Postconditions**")
            _bullets(uc.postconditions, "None.")


# --- 8. Process analysis ----------------------------------------------------------------

def process(a: Analysis) -> None:
    if not a.process:
        return empty_state("Process analysis has not been generated yet.")
    p = a.process
    _header("process", a)
    if not p.sufficient_detail:
        st.warning("The request doesn't describe the current process in enough detail to map it fully. "
                   + (p.notes or ""), icon=":material/info:")
    st.caption(":orange-background[Manual step] · :red-background[Bottleneck ⚠] · :blue-background[System step]")
    for title, steps, expanded in (("Current state", p.current_state, True), ("Future state", p.future_state, True)):
        with subsection(f"{title} process ({len(steps)} steps)", expanded=expanded):
            if steps:
                st.graphviz_chart(process_to_dot(steps), use_container_width=True)
            else:
                st.caption("Not enough information to map this process.")
    with subsection("Analysis"):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Bottlenecks**")
            _bullets(p.bottlenecks)
            st.markdown("**Manual activities**")
            _bullets(p.manual_activities)
        with c2:
            st.markdown("**Inefficiencies**")
            _bullets(p.inefficiencies)
            st.markdown("**Automation opportunities**")
            _bullets(p.automation_opportunities)


# --- 9. Traceability -----------------------------------------------------------------

STATUS_ICONS = {FULLY_TRACED: "✅", PARTIAL: "🟡", NOT_TESTED: "❌", OUT_OF_SCOPE: "⚪"}


def traceability(a: Analysis) -> None:
    report = build_traceability(a)
    if report.matrix.empty:
        return empty_state("The traceability matrix is available once requirements are generated.")
    _header("traceability", a, "Business Objective → Requirement → User Story → Acceptance Criteria → Test Case")
    m = report.metrics
    cols = st.columns(4)
    cols[0].metric("Fully traced", f"{m['fully_traced']} / {m['requirements_in_scope']}")
    cols[1].metric("Test coverage", f"{m['test_coverage_pct']}%")
    cols[2].metric("Coverage gaps", len(report.gaps))
    cols[3].metric("Broken links", len(report.dangling_references))
    st.caption("Built by code from the IDs each artifact cites, not by the AI, so it independently audits the AI's output.")

    with subsection("Coverage check", expanded=bool(report.gaps or report.dangling_references)):
        if not a.is_complete:
            st.info("The coverage check is partial until stories, acceptance criteria and test cases are all generated.",
                    icon=":material/pending:")
        elif report.is_clean:
            st.success("Every in-scope requirement traces from a business objective through to at least one test.",
                       icon=":material/verified:")
        for g in report.gaps:
            st.markdown(f"- {level_badge_from_text(g.severity)} {g.message}")
        for ref in report.dangling_references:
            st.markdown(f"- :red-background[Broken link] {ref}")

    with subsection("Matrix"):
        matrix = report.matrix.copy()
        matrix["Trace Status"] = matrix["Trace Status"].map(lambda s: f"{STATUS_ICONS.get(s, '')} {s}")
        status_filter = st.multiselect("Filter by status", list(STATUS_ICONS), key="rtm_filter",
                                       placeholder="All statuses")
        if status_filter:
            matrix = matrix[report.matrix["Trace Status"].isin(status_filter)]
        st.dataframe(matrix, hide_index=True, use_container_width=True,
                     column_config={"Description": st.column_config.TextColumn(width="medium")})


def level_badge_from_text(severity: str) -> str:
    return f":{'red' if severity == 'High' else 'orange'}-background[{severity}]"


# --- 10. Test cases ------------------------------------------------------------------

def test_cases(a: Analysis) -> None:
    if not a.test_cases:
        return empty_state("Test cases have not been generated yet.")
    _header("test_cases", a)
    items = a.test_cases.test_cases
    counts = pd.Series([t.scenario_type.value for t in items]).value_counts()
    cols = st.columns(4)
    cols[0].metric("Total", len(items))
    for col, label in zip(cols[1:], ["Positive", "Negative", "Edge Case"]):
        col.metric(label, int(counts.get(label, 0)))
    with subsection("Test case table"):
        _table([{
            "ID": t.id, "Scenario": t.scenario, "Type": t.scenario_type.value, "Priority": t.priority.value,
            "Requirements": ", ".join(t.requirement_ids), "Criteria": ", ".join(t.criterion_ids),
            "Expected result": t.expected_result,
        } for t in items], Scenario=st.column_config.TextColumn(width="medium"),
            **{"Expected result": st.column_config.TextColumn(width="large")})
    with subsection("Test case details", expanded=False):
        for t in items:
            st.markdown(f"**{t.id}: {t.scenario}** {scenario_badge(t.scenario_type)} {level_badge(t.priority, 'Priority: ')}")
            st.caption(f"Traces to {', '.join(t.requirement_ids + t.criterion_ids)}")
            if t.preconditions:
                st.markdown("*Preconditions:* " + "; ".join(t.preconditions))
            st.markdown("\n".join(f"{i}. {s}" for i, s in enumerate(t.steps, 1)))
            st.markdown(f"*Expected result:* {t.expected_result}")
            st.divider()


# --- 11. Risks & assumptions ------------------------------------------------------------

def risks(a: Analysis) -> None:
    if not a.risks:
        return empty_state("Risk analysis has not been generated yet.")
    r = a.risks
    _header("risks", a)
    with subsection(f"Risk register ({len(r.risks)})"):
        ordered = sorted(r.risks, key=lambda x: -risk_score(x.likelihood, x.impact))
        _table([{
            "ID": x.id, "Risk": x.description, "Source": x.source.value, "Likelihood": x.likelihood.value,
            "Impact": x.impact.value, "Score": risk_score(x.likelihood, x.impact), "Mitigation": x.mitigation,
        } for x in ordered], Risk=st.column_config.TextColumn(width="large"),
            Mitigation=st.column_config.TextColumn(width="large"),
            Score=st.column_config.ProgressColumn(min_value=0, max_value=9, format="%d",
                                                  help="Likelihood × impact (1-9)"))
    with subsection(f"Assumptions ({len(r.assumptions)})"):
        st.caption("Each assumption must be validated. If it's wrong, the requirements may change.")
        _table([{"ID": x.id, "Assumption": x.description, "Impact if wrong": x.impact_if_wrong,
                 "Validate with": x.validate_with} for x in r.assumptions],
               Assumption=st.column_config.TextColumn(width="large"))
    with subsection(f"Constraints ({len(r.constraints)})"):
        _table([{"ID": x.id, "Constraint": x.description, "Type": x.type, "Basis": x.basis.value}
                for x in r.constraints]) if r.constraints else st.caption("No constraints stated or implied.")
    with subsection(f"Edge cases ({len(r.edge_cases)})"):
        _bullets(r.edge_cases)


# --- 12. Clarifying questions -----------------------------------------------------------

def questions(a: Analysis) -> None:
    if not a.questions:
        return empty_state("No clarifying questions generated.")
    _header("questions", a, "Questions a Business Analyst would ask before sign-off")
    answers = {c.question_id: c.answer for c in a.input.clarifications}
    for category in QuestionCategory:
        items = [q for q in a.questions.questions if q.category == category]
        if not items:
            continue
        with subsection(f"{category.value} ({len(items)})", expanded=category == QuestionCategory.CRITICAL):
            for q in items:
                status = ":green-background[Answered]" if q.id in answers else ":gray-background[Open]"
                st.markdown(f"**{q.id}** {status} *{q.area}*  \n{q.question}")
                if q.rationale:
                    st.caption(f"Why it matters: {q.rationale}")
                if q.id in answers:
                    st.markdown(f"> **Answer:** {answers[q.id]}")


# Tab key -> renderer, in dashboard order (labels come from markdown_export.SECTIONS).
RENDERERS = {
    "overview": overview, "problem": problem, "stakeholders": stakeholders, "requirements": requirements,
    "stories": stories, "criteria": criteria, "use_cases": use_cases, "process": process,
    "traceability": traceability, "test_cases": test_cases, "risks": risks, "questions": questions,
}
