"""Screen 1: describe the business request, or load an example."""

import streamlit as st

from app.components import state
from app.components.common import show_error
from app.components import progress
from app.config import MAX_OPTIONAL_FIELD_CHARS, MAX_REQUEST_CHARS
from app.services.examples import load_examples
from app.services.pipeline import run_stage_one
from app.utils.validation import validate_project_input


@st.cache_data(show_spinner=False)
def _examples():
    return load_examples()


def render() -> None:
    st.title("Business Requirements Analyst")
    st.markdown(
        "Describe a business need in plain language. The analyst will ask the clarifying questions a "
        "Business Analyst would ask, then produce requirements, user stories, acceptance criteria, use "
        "cases, process analysis, test cases and a traceability matrix."
    )
    _example_picker()
    st.divider()
    _form()


def _example_picker() -> None:
    examples = _examples()
    with st.container(border=True):
        st.markdown("**Start from an example scenario**")
        options = {e.slug: e for e in examples}
        slug = st.selectbox(
            "Example",
            options,
            format_func=lambda s: f"{options[s].title}: {options[s].summary}"
            + ("  ·  pre-generated" if options[s].has_demo else ""),
            label_visibility="collapsed",
        )
        example = options[slug]
        col1, col2, _ = st.columns([1.2, 1.6, 3])
        col1.button(":material/edit_note: Load into form", use_container_width=True,
                    on_click=state.load_form, args=(example.input,))
        if example.has_demo:
            col2.button(
                ":material/visibility: View pre-generated analysis", use_container_width=True,
                help="Explore a complete analysis without using the API.",
                on_click=_open_demo, args=(example,),
            )


def _open_demo(example) -> None:
    state.start_over()
    state.load_form(example.input)
    analysis = example.analysis.model_copy(deep=True)
    state.set_analysis(analysis, state.RESULTS if analysis.requirements else state.CLARIFY)


def _form() -> None:
    st.markdown("#### Business request")
    st.text_input("Project name *", key="form_project_name", max_chars=100,
                  placeholder="e.g. Online Order Tracking")
    request = st.text_area(
        "Business problem or request *",
        key="form_request",
        height=160,
        max_chars=MAX_REQUEST_CHARS,
        placeholder="What problem are you trying to solve, who is affected, and what outcome do you want?",
    )
    st.caption(f"{len(request):,} / {MAX_REQUEST_CHARS:,} characters")

    with st.expander("Optional context (improves the analysis)", expanded=False):
        col1, col2 = st.columns(2)
        col1.text_input("Industry", key="form_industry", max_chars=MAX_OPTIONAL_FIELD_CHARS,
                        placeholder="e.g. Healthcare, Retail")
        col2.text_input("Known stakeholders", key="form_stakeholders", max_chars=MAX_OPTIONAL_FIELD_CHARS,
                        placeholder="e.g. Customer service team, customers")
        col1.text_area("Existing systems", key="form_existing_systems", max_chars=MAX_OPTIONAL_FIELD_CHARS,
                       height=90, placeholder="e.g. Order Management System, CRM")
        col2.text_area("Known constraints", key="form_constraints", max_chars=MAX_OPTIONAL_FIELD_CHARS,
                       height=90, placeholder="e.g. Budget, deadline, required technology, regulations")
        st.caption("Leave anything you don't know blank. The analyst will flag it as a question rather than guess.")

    live = state.live_mode_available()
    clicked = st.button(
        ":material/manage_search: Analyze Requirements",
        type="primary",
        disabled=not live,
        help=None if live else "Add an API key in the sidebar, or view a pre-generated example above.",
    )
    if not live:
        st.caption("Live analysis needs an Anthropic API key. Pre-generated examples work without one.")
    if clicked:
        _analyze()


def _analyze() -> None:
    result = validate_project_input(state.form_values())
    for message in result.errors:
        st.error(message, icon=":material/error:")
    if not result.ok:
        return
    if result.warnings:
        st.warning("\n\n".join(result.warnings), icon=":material/lightbulb:")

    state.start_over()  # a new request is a new analysis
    try:
        client = state.new_client()
    except Exception as exc:
        show_error(exc)
        return

    def finish(analysis, error):
        state.save_progress(analysis, client.calls)
        if error:
            show_error(error)
            return
        state.set_analysis(analysis, state.CLARIFY)
        st.rerun()

    progress.start(
        "Step 1 of 2: Understanding the request",
        lambda on_progress: run_stage_one(client, result.input, client.settings.model, on_progress),
        stages=["questions", "problem"],
        on_finish=finish,
    )
