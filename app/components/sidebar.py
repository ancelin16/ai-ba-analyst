"""Sidebar: connection status, optional session API key, usage and navigation."""

import streamlit as st

from app.components import progress, state
from app.services.llm_client import summarize_usage


def render() -> None:
    with st.sidebar:
        st.markdown("### :material/assignment: AI Requirements Analyst")
        st.caption("Turns unstructured business requests into structured, traceable requirements.")

        busy = progress.is_running()
        if busy:
            st.info("Analysis in progress…", icon=":material/hourglass_top:")
        if st.button(":material/add: New analysis", use_container_width=True, disabled=busy):
            state.start_over()
            st.rerun()

        st.divider()
        _connection()
        _usage()
        st.divider()
        _history(disabled=busy)
        st.divider()
        _legend()


def _connection() -> None:
    settings = state.settings()
    st.markdown("**AI connection**")
    if settings.has_api_key:
        source = "session key" if st.session_state.user_api_key else ".env file"
        st.success(f"Live analysis available\n\nModel: `{settings.model}` ({source})", icon=":material/check_circle:")
    else:
        st.warning(
            "No API key configured. You can explore the pre-generated examples, "
            "or add a key below to run live analyses.",
            icon=":material/key_off:",
        )
    with st.expander("Use my own API key"):
        st.text_input(
            "Anthropic API key",
            type="password",
            key="user_api_key",
            help="Kept only in this browser session. It is never saved to disk or written to logs.",
        )


def _usage() -> None:
    calls = st.session_state.usage
    if not calls:
        return
    totals = summarize_usage(calls)
    st.markdown("**This analysis**")
    col1, col2 = st.columns(2)
    col1.metric("AI calls", totals["calls"], help="Includes any corrective retries")
    col2.metric("Tokens", f"{(totals['input_tokens'] + totals['output_tokens']) / 1000:.1f}K")


STATUS_LABELS = {
    "complete": ":green[:material/check_circle:]",
    "incomplete": ":orange[:material/pending:]",
    "awaiting_clarification": ":blue[:material/quiz:]",
    "too_vague": ":red[:material/block:]",
}


def _history(disabled: bool = False) -> None:
    st.markdown("**Saved analyses**")
    try:
        saved = state.repository().list_recent(limit=10)
    except Exception:  # history is a convenience: never let it break the page
        st.caption("History is unavailable.")
        return
    if not saved:
        st.caption("Analyses you run are saved here automatically.")
        return
    current = st.session_state.analysis_id
    for item in saved:
        left, right = st.columns([5, 1], vertical_alignment="center")
        label = f"{STATUS_LABELS.get(item.status, '')} {item.project_name}"
        left.button(
            label, key=f"open_{item.id}", use_container_width=True, disabled=disabled,
            type="primary" if item.id == current else "secondary",
            help=f"{item.status.replace('_', ' ').capitalize()} · updated {item.updated_at[:16].replace('T', ' ')} UTC",
            on_click=state.open_saved, args=(item.id,),
        )
        with right.popover(":material/delete:", help="Delete"):
            st.caption(f"Permanently delete **{item.project_name}**? This cannot be undone.")
            st.button("Delete", key=f"delete_{item.id}", type="primary", disabled=disabled,
                      on_click=state.delete_saved, args=(item.id,))


def _legend() -> None:
    st.markdown("**Reading the badges**")
    st.markdown(
        ":green-background[Stated] explicitly in the request  \n"
        ":blue-background[Inferred] reasonable conclusion  \n"
        ":orange-background[Assumed] must be confirmed"
    )
    st.caption("The analyst never presents an assumption as a fact.")
