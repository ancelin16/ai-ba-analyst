"""Screen 2: review how the request was understood and answer clarifying questions.

This is the BA "gate". Requirements are only generated once the user has
answered the questions, or has explicitly chosen to proceed with assumptions.
If the request is too vague, proceeding is blocked until more information is given.
"""

import streamlit as st

from app.components import state
from app.components.common import show_error
from app.components import progress
from app.models.analysis import Analysis
from app.models.artifacts import QuestionCategory
from app.services.pipeline import DOWNSTREAM, apply_clarifications, needs_more_information, run_analysis
from app.utils.formatting import basis_badge

CATEGORY_STYLE = {
    QuestionCategory.CRITICAL: (":material/priority_high:", "red", "Requirements could be wrong without these answers."),
    QuestionCategory.IMPORTANT: (":material/help:", "orange", "These significantly shape the design."),
    QuestionCategory.NICE_TO_KNOW: (":material/lightbulb:", "blue", "Useful refinements; they don't block progress."),
}


def render() -> None:
    analysis = state.analysis()
    if analysis is None or analysis.problem is None:
        state.go(state.INPUT)
        st.rerun()

    st.title(analysis.input.project_name)
    st.caption("Step 1 of 2 complete. Review the analyst's understanding before requirements are written.")

    _understanding(analysis)
    answers = _questions(analysis)
    st.divider()
    _actions(analysis, answers)


def _understanding(analysis: Analysis) -> None:
    p = analysis.problem
    with st.container(border=True):
        st.markdown("#### :material/psychology: How the analyst understood the request")
        st.markdown(f"**Problem:** {p.problem_statement}")
        for o in p.objectives:
            st.markdown(f"- **{o.id}** {o.description} {basis_badge(o.basis)}")
        if p.conflicts:
            st.warning("**Conflicting requirements detected**\n\n" + "\n".join(f"- {c}" for c in p.conflicts),
                       icon=":material/call_split:")
        if p.ambiguities:
            with st.expander(f"Ambiguities found ({len(p.ambiguities)})"):
                st.markdown("\n".join(f"- {a}" for a in p.ambiguities))

    if needs_more_information(analysis):
        st.error(
            "**This request is too vague to write meaningful requirements.** "
            "Rather than guess, the analyst needs the following information:\n\n"
            + "\n".join(f"- {m}" for m in p.missing_information),
            icon=":material/block:",
        )
        st.caption("Answer the questions below, or go back and add detail to the request.")


def _questions(analysis: Analysis) -> dict[str, str]:
    st.markdown("#### :material/quiz: Clarifying questions")
    st.caption("Answer what you can. Unanswered Critical and Important questions become documented assumptions.")
    previous = {c.question_id: c.answer for c in analysis.input.clarifications}
    answers = {}
    for category, (icon, color, blurb) in CATEGORY_STYLE.items():
        questions = [q for q in analysis.questions.questions if q.category == category]
        if not questions:
            continue
        with st.expander(f"{icon} **{category.value}** ({len(questions)})", expanded=category != QuestionCategory.NICE_TO_KNOW):
            st.caption(blurb)
            for q in questions:
                st.markdown(f"**{q.id}** :{color}-background[{q.area or 'General'}] {q.question}")
                if q.rationale:
                    st.caption(f"Why it matters: {q.rationale}")
                key = f"answer_{q.id}"
                st.session_state.setdefault(key, previous.get(q.id, ""))
                answers[q.id] = st.text_area(
                    f"Answer to {q.id}", key=key, height=68, label_visibility="collapsed",
                    placeholder="Your answer (optional)",
                )
    return answers


def _actions(analysis: Analysis, answers: dict[str, str]) -> None:
    answered = sum(1 for a in answers.values() if a.strip())
    too_vague = needs_more_information(analysis)
    col1, col2, col3 = st.columns([1.6, 1.8, 1])

    with col1:
        clicked_answers = st.button(
            f":material/send: Continue with {answered} answer{'s' if answered != 1 else ''}",
            type="primary", disabled=answered == 0, use_container_width=True,
            help="Re-checks the problem analysis with your answers, then writes the requirements.",
        )
    with col2:
        clicked_skip = st.button(
            ":material/fast_forward: Skip and proceed with assumptions",
            disabled=too_vague, use_container_width=True,
            help="Blocked because the request is too vague." if too_vague
            else "Unanswered questions will be recorded as assumptions.",
        )
    with col3:
        if st.button(":material/arrow_back: Edit request", use_container_width=True):
            state.go(state.INPUT)
            st.rerun()

    if clicked_answers:
        _generate(analysis, answers)
    elif clicked_skip:
        _generate(analysis, {})


def _generate(analysis: Analysis, answers: dict[str, str]) -> None:
    try:
        client = state.new_client()
    except Exception as exc:
        show_error(exc)
        return
    submitted = {qid: text.strip() for qid, text in answers.items() if text.strip()}
    already_applied = {c.question_id: c.answer for c in analysis.input.clarifications}
    apply_answers = bool(submitted) and submitted != already_applied  # unchanged answers: just resume

    def task(on_progress):
        if apply_answers:
            apply_clarifications(client, analysis, answers, on_progress)
            if needs_more_information(analysis):
                return  # still too vague: stop before writing requirements
        run_analysis(client, analysis, on_progress)

    start_full_analysis(client, analysis, task, include_problem=apply_answers)


def start_full_analysis(client, analysis: Analysis, task=None, include_problem: bool = False) -> None:
    """Run stages 2-6 as a background job. Finished stages are skipped (resume)."""
    stages = (["problem"] if include_problem else []) + DOWNSTREAM
    done = set() if include_problem else {key for key in DOWNSTREAM if getattr(analysis, key) is not None}

    def finish(_, error):
        state.save_progress(analysis, client.calls)
        if error:
            show_error(error)
            return
        state.set_analysis(analysis, state.CLARIFY if needs_more_information(analysis) else state.RESULTS)
        st.rerun()

    progress.start(
        "Step 2 of 2: Writing requirements and supporting artifacts",
        task or (lambda on_progress: run_analysis(client, analysis, on_progress)),
        stages=stages,
        on_finish=finish,
        already_done=done,
    )
