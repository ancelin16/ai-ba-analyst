"""Reusable UI building blocks."""

from contextlib import contextmanager

import streamlit as st

from app.utils.errors import AppError


def copy_button(text: str, key: str, label: str = "Copy") -> None:
    """A popover holding the text in a code block. Streamlit code blocks have
    a built-in copy-to-clipboard icon in the top-right corner."""
    with st.popover(f":material/content_copy: {label}", use_container_width=False):
        st.caption("Use the copy icon in the top-right corner of the box.")
        st.code(text, language="markdown", wrap_lines=True)


def section_header(title: str, copy_text: str, key: str, caption: str = "") -> None:
    """Tab heading with a copy button on the right."""
    left, right = st.columns([5, 1], vertical_alignment="bottom")
    with left:
        st.subheader(title)
        if caption:
            st.caption(caption)
    with right:
        if copy_text:
            copy_button(copy_text, key=f"copy_{key}")


@contextmanager
def subsection(title: str, expanded: bool = True):
    """A collapsible block inside a tab."""
    with st.expander(title, expanded=expanded):
        yield


def show_error(exc: Exception) -> None:
    """Friendly message first; technical detail tucked away."""
    if isinstance(exc, AppError):
        st.error(exc.user_message, icon=":material/error:")
        if exc.detail and exc.detail != exc.user_message:
            with st.expander("Technical details"):
                st.code(exc.detail[:2000])
    else:
        st.error("An unexpected error occurred. Please try again.", icon=":material/error:")
        with st.expander("Technical details"):
            st.code(f"{type(exc).__name__}: {exc}"[:2000])


def empty_state(message: str) -> None:
    st.info(message, icon=":material/info:")
