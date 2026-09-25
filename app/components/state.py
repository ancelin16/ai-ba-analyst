"""Session state in one place: which screen is showing, the current analysis,
and how to build an AI client.

Streamlit re-runs the whole script on every click. Anything that must survive
a click lives in st.session_state, accessed through these helpers.
"""

import logging
import sqlite3
from dataclasses import replace

import streamlit as st

from app.config import get_settings
from app.models.analysis import Analysis
from app.services.llm_client import CallRecord, ClaudeClient
from app.services.storage import AnalysisRepository, status_of

logger = logging.getLogger(__name__)

INPUT, CLARIFY, RESULTS = "input", "clarify", "results"
FORM_FIELDS = ("project_name", "request", "industry", "stakeholders", "existing_systems", "constraints")


def init() -> None:
    defaults = {
        "step": INPUT,
        "analysis": None,
        "analysis_id": None,  # database row of the current analysis
        "usage": [],  # CallRecords from the current analysis
        "user_api_key": "",  # "bring your own key": this browser session only, never saved
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    for field in FORM_FIELDS:
        st.session_state.setdefault(f"form_{field}", "")


def go(step: str) -> None:
    st.session_state.step = step


def analysis() -> Analysis | None:
    return st.session_state.analysis


def set_analysis(value: Analysis | None, step: str | None = None) -> None:
    st.session_state.analysis = value
    if step:
        go(step)


def start_over() -> None:
    st.session_state.analysis = None
    st.session_state.analysis_id = None
    st.session_state.usage = []
    for key in [k for k in st.session_state if str(k).startswith("answer_")]:
        del st.session_state[key]
    go(INPUT)


def load_form(values: dict) -> None:
    for field in FORM_FIELDS:
        st.session_state[f"form_{field}"] = values.get(field, "")


def form_values() -> dict:
    return {field: st.session_state.get(f"form_{field}", "") for field in FORM_FIELDS}


def settings():
    """App settings, with the sidebar key (if entered) taking precedence."""
    base = get_settings()
    user_key = st.session_state.get("user_api_key", "").strip()
    return replace(base, anthropic_api_key=user_key) if user_key else base


def live_mode_available() -> bool:
    return settings().has_api_key


def new_client() -> ClaudeClient:
    """Raises MissingCredentialsError (with a friendly message) if no key is set."""
    return ClaudeClient(settings=settings())


def record_usage(calls: list[CallRecord]) -> None:
    st.session_state.usage = [*st.session_state.usage, *calls]


# --- History (SQLite) ---------------------------------------------------------------

@st.cache_resource
def repository() -> AnalysisRepository:
    return AnalysisRepository(get_settings().database_path)


def save_progress(analysis: Analysis | None, calls: list[CallRecord]) -> None:
    """Record usage and save the analysis, including partial results after a failure.

    Pre-generated demo analyses are never saved. A database problem must not
    lose the user's on-screen results, so it is reported as a notice rather
    than an error.
    """
    record_usage(calls)
    if analysis is None or analysis.is_demo:
        return
    try:
        repo = repository()
        st.session_state.analysis_id = repo.save(analysis, st.session_state.analysis_id)
        repo.log_calls(st.session_state.analysis_id, calls)
    except (sqlite3.Error, OSError):
        logger.exception("Could not save analysis to history")
        st.toast("Couldn't save this analysis to history. Results are still shown on screen.",
                 icon=":material/warning:")


def open_saved(analysis_id: int) -> None:
    loaded = repository().get(analysis_id)
    if loaded is None:
        st.toast("That analysis no longer exists.", icon=":material/error:")
        return
    start_over()
    load_form(loaded.input.model_dump())
    st.session_state.analysis_id = analysis_id
    status = status_of(loaded)
    set_analysis(loaded, CLARIFY if status in ("awaiting_clarification", "too_vague") else RESULTS)


def delete_saved(analysis_id: int) -> None:
    repository().delete(analysis_id)
    if st.session_state.analysis_id == analysis_id:
        start_over()
