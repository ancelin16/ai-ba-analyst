"""Headless UI tests with Streamlit's AppTest: the real app runs without a browser.

These cover the paths that need no AI calls: loading the page, form validation,
examples, opening a pre-generated analysis, and rendering every results tab.
"""

from types import SimpleNamespace

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from app.components import state
from app.config import PROJECT_ROOT, get_settings
from tests.fakes import FakeLLMClient


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Isolate from the developer's .env: no API key, and a throwaway database.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "ui-test.db"))
    get_settings.cache_clear()
    st.cache_resource.clear()  # fresh database repository per test
    at = AppTest.from_file(str(PROJECT_ROOT / "main.py"), default_timeout=30)
    at.run()
    yield at
    get_settings.cache_clear()


def button(at: AppTest, label_fragment: str):
    return next(b for b in at.button if label_fragment in b.label)


def test_home_page_loads_without_errors(app):
    assert not app.exception
    assert app.title[0].value == "Business Requirements Analyst"
    assert len(app.selectbox[0].options) >= 6


def test_live_analysis_disabled_without_api_key(app):
    assert button(app, "Analyze Requirements").disabled
    assert any("No API key configured" in w.value for w in app.sidebar.warning)


def test_load_example_fills_the_form(app):
    app.selectbox[0].select("05_sales_leads").run()
    button(app, "Load into form").click().run()
    assert app.text_input(key="form_project_name").value == "Sales Lead Management"
    assert "sales director" in app.text_area(key="form_request").value


def test_pre_generated_example_renders_all_tabs(app):
    button(app, "View pre-generated analysis").click().run()
    assert not app.exception
    assert app.title[0].value == "Online Order Tracking"
    assert len(app.tabs) == 12
    headings = {h.value for h in app.subheader}
    for expected in ("Overview", "Requirements", "Traceability Matrix", "Test Cases", "Clarifying Questions"):
        assert expected in headings


def test_demo_analysis_is_not_saved_to_history(app):
    button(app, "View pre-generated analysis").click().run()
    assert any("Analyses you run are saved here" in c.value for c in app.sidebar.caption)


def test_new_analysis_returns_to_input(app):
    button(app, "View pre-generated analysis").click().run()
    button(app, "New analysis").click().run()
    assert app.title[0].value == "Business Requirements Analyst"


# --- Full journey with a fake AI (exercises the background-job machinery) ---------

@pytest.fixture
def fake_ai(app, monkeypatch, fake_responses):
    client = FakeLLMClient(fake_responses)
    client.settings = SimpleNamespace(model="fake-model")
    monkeypatch.setattr(state, "new_client", lambda: client)
    monkeypatch.setattr(state, "live_mode_available", lambda: True)
    app.run()  # redraw with live mode enabled
    return client


def test_full_journey_request_to_results(app, fake_ai):
    app.text_input(key="form_project_name").input("Online Order Tracking")
    app.text_area(key="form_request").input(
        "We want customers to be able to track their orders online because our customer service "
        "team receives too many calls asking about order status."
    )
    button(app, "Analyze Requirements").click().run()
    assert not app.exception
    assert "Step 1 of 2 complete" in app.caption[0].value  # clarification screen

    button(app, "Skip and proceed").click().run()
    assert not app.exception
    assert len(app.tabs) == 12
    assert len(fake_ai.calls) == 10
    # Saved to history automatically, marked complete.
    saved = state.repository().list_recent()
    assert [(s.project_name, s.status) for s in saved] == [("Online Order Tracking", "complete")]


def test_answers_are_sent_to_the_ai(app, fake_ai):
    app.text_input(key="form_project_name").input("Online Order Tracking")
    app.text_area(key="form_request").input(
        "We want customers to be able to track their orders online because our customer service "
        "team receives too many calls asking about order status."
    )
    button(app, "Analyze Requirements").click().run()
    app.text_area(key="answer_Q-01").input("No login: order number plus email address.")
    app.run()
    button(app, "Continue with 1 answer").click().run()
    assert not app.exception
    assert "order number plus email address" in fake_ai.prompt_for("requirements")


def test_vague_request_blocks_skip_in_the_ui(app, fake_ai, fake_responses):
    fake_responses["business_problem"] |= {"is_too_vague": True, "missing_information": ["Who the users are"]}
    app.text_input(key="form_project_name").input("Vague")
    app.text_area(key="form_request").input("We need a better system for our team because people are frustrated.")
    button(app, "Analyze Requirements").click().run()
    assert any("too vague" in e.value for e in app.error)
    assert button(app, "Skip and proceed").disabled


def test_vague_demo_opens_on_the_clarification_gate(app):
    app.selectbox[0].select("06_vague").run()
    button(app, "View pre-generated analysis").click().run()
    assert not app.exception
    assert any("too vague" in e.value for e in app.error)


def test_sales_demo_shows_resolved_conflict_answer(app):
    app.selectbox[0].select("05_sales_leads").run()
    button(app, "View pre-generated analysis").click().run()
    assert not app.exception
    assert len(app.tabs) == 12
    assert any("Answer:" in m.value and "strategic accounts" in m.value for m in app.markdown)
