"""Screen 3: the results dashboard (12 tabs) plus export and resume."""

import re

import streamlit as st

from app.components import sections, state
from app.components.clarification import start_full_analysis
from app.components.common import show_error
from app.services.docx_export import build_docx
from app.services.markdown_export import SECTIONS, full_report_md


def render() -> None:
    analysis = state.analysis()
    if analysis is None:
        state.go(state.INPUT)
        st.rerun()

    left, right = st.columns([3, 1.3], vertical_alignment="bottom")
    with left:
        st.title(analysis.input.project_name)
        stamp = analysis.created_at.strftime("%d %b %Y %H:%M UTC")
        st.caption(f"Generated {stamp}" + (f" · model `{analysis.model}`" if analysis.model else "")
                   + (" · pre-generated example" if analysis.is_demo else ""))
    with right:
        _export(analysis)

    if not analysis.is_complete and not analysis.problem.is_too_vague:
        _resume_banner(analysis)

    tabs = st.tabs([label for label, _ in SECTIONS.values()])
    for tab, key in zip(tabs, SECTIONS):
        with tab:
            sections.RENDERERS[key](analysis)


def _export(analysis) -> None:
    slug = re.sub(r"[^a-z0-9]+", "-", analysis.input.project_name.lower()).strip("-") or "analysis"
    with st.popover(":material/download: Export", use_container_width=True):
        st.caption("Download the complete analysis as a document.")
        st.download_button(
            ":material/description: Word document (.docx)",
            data=build_docx(analysis),
            file_name=f"{slug}-requirements.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )
        st.download_button(
            ":material/markdown: Markdown (.md)",
            data=full_report_md(analysis),
            file_name=f"{slug}-requirements.md",
            mime="text/markdown",
            use_container_width=True,
            help="Paste into Confluence, GitHub, Notion or Jira.",
        )


def _resume_banner(analysis) -> None:
    st.warning("This analysis is incomplete: a step failed or was interrupted. Completed sections are shown below.",
               icon=":material/warning:")
    if st.button(":material/replay: Resume analysis", disabled=not state.live_mode_available()):
        try:
            client = state.new_client()
        except Exception as exc:
            show_error(exc)
            return
        start_full_analysis(client, analysis)
