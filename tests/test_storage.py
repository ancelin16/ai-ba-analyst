"""SQLite repository: save, update, list, delete and usage logging."""

import sqlite3

import pytest

from app.models.analysis import Analysis
from app.models.inputs import ProjectInput
from app.services.llm_client import CallRecord
from app.services.storage import AnalysisRepository, status_of


@pytest.fixture
def repo(tmp_path):
    return AnalysisRepository(tmp_path / "test.db")


@pytest.fixture
def complete(order_input, order_stages) -> Analysis:
    return Analysis(input=ProjectInput(**order_input), model="test-model", **order_stages)


def test_save_and_reload_round_trip(repo, complete):
    analysis_id = repo.save(complete)
    loaded = repo.get(analysis_id)
    assert loaded == complete
    assert loaded.requirements.functional[2].id == "FR-003"


def test_update_keeps_the_same_row(repo, complete):
    analysis_id = repo.save(complete)
    complete.input = complete.input.model_copy(update={"project_name": "Renamed"})
    assert repo.save(complete, analysis_id) == analysis_id
    assert [s.project_name for s in repo.list_recent()] == ["Renamed"]


def test_update_of_missing_row_inserts_new(repo, complete):
    new_id = repo.save(complete, analysis_id=999)
    assert repo.get(new_id) is not None


def test_list_recent_newest_first_and_limited(repo, complete):
    ids = [repo.save(complete.model_copy(update={"input": complete.input.model_copy(update={"project_name": f"P{i}"})}))
           for i in range(3)]
    listed = repo.list_recent(limit=2)
    assert [s.id for s in listed] == [ids[2], ids[1]]
    assert listed[0].status == "complete"


def test_get_missing_returns_none(repo):
    assert repo.get(12345) is None


def test_delete_removes_analysis_and_usage(repo, complete):
    analysis_id = repo.save(complete)
    repo.log_calls(analysis_id, [CallRecord("requirements", 1, 100, 50, 2.0, True)])
    assert repo.delete(analysis_id)
    assert repo.get(analysis_id) is None
    assert repo.usage_by_stage(analysis_id) == []
    assert not repo.delete(analysis_id)


def test_usage_is_aggregated_with_sql(repo, complete):
    analysis_id = repo.save(complete)
    repo.log_calls(analysis_id, [
        CallRecord("requirements", 2, 1000, 600, 10.0, True),
        CallRecord("user_stories", 1, 500, 200, 4.0, True),
        CallRecord("requirements", 1, 900, 500, 8.0, True),
    ])
    by_stage = repo.usage_by_stage(analysis_id)
    assert by_stage[0] == {"stage": "requirements", "calls": 2, "attempts": 3, "input_tokens": 1900,
                           "output_tokens": 1100, "seconds": 18.0}
    assert repo.usage_totals() == {"analyses": 1, "calls": 3, "input_tokens": 2400, "output_tokens": 1300, "retries": 1}


def test_queries_are_parameterized_against_injection(repo, complete):
    """A malicious project name is stored as plain text and the table survives."""
    evil = "x'); DROP TABLE analyses; --"
    complete.input = complete.input.model_copy(update={"project_name": evil})
    analysis_id = repo.save(complete)
    assert repo.get(analysis_id).input.project_name == evil
    assert len(repo.list_recent()) == 1


def test_status_constraint_enforced_by_database(repo):
    with sqlite3.connect(repo.db_path) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO analyses (project_name, request, status, created_at, updated_at, data_json) "
            "VALUES ('p', 'r', 'bogus', 'now', 'now', '{}')"
        )


@pytest.mark.parametrize(
    ("keep", "expected"),
    [
        ({"questions", "problem"}, "awaiting_clarification"),
        ({"questions", "problem", "stakeholders", "process", "risks", "requirements"}, "incomplete"),
    ],
)
def test_status_of_partial_analyses(order_input, order_stages, keep, expected):
    partial = Analysis(input=ProjectInput(**order_input), **{k: v for k, v in order_stages.items() if k in keep})
    assert status_of(partial) == expected


def test_status_of_vague_analysis(order_input, order_stages):
    order_stages["problem"]["is_too_vague"] = True
    vague = Analysis(input=ProjectInput(**order_input), problem=order_stages["problem"])
    assert status_of(vague) == "too_vague"
