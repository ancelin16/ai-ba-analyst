"""Streamlit entry point. Run with:  streamlit run main.py

This file only wires things together. Each screen lives in app/components:

    input_form     -> Screen 1: describe the request (or load an example)
    clarification  -> Screen 2: review understanding, answer clarifying questions
    results        -> Screen 3: the 12-tab results dashboard
"""

import streamlit as st

from app.components import clarification, input_form, progress, results, sidebar, state

st.set_page_config(
    page_title="AI Business Requirements Analyst",
    page_icon=":material/assignment:",
    layout="wide",
    initial_sidebar_state="expanded",
)

state.init()
sidebar.render()

# If AI work is running (for example the page re-ran because the user clicked
# something), reattach to it instead of losing it. The screen is drawn after it finishes.
if progress.is_running():
    progress.watch()

SCREENS = {state.INPUT: input_form.render, state.CLARIFY: clarification.render, state.RESULTS: results.render}
SCREENS[st.session_state.step]()
