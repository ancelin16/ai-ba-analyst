"""SQLite persistence for analyses and AI usage.

Two tables:

  analyses  one row per analysis. Summary columns (name, status, model,
            timestamps) are plain columns so they can be listed and filtered
            with SQL; the full analysis is stored as JSON in `data_json`.
  ai_calls  one row per AI call, giving a cost and performance audit trail.

Plain SQL through the standard-library sqlite3 module keeps it transparent.
Every query uses ? placeholders (never string formatting) to prevent SQL
injection.
"""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.models.analysis import Analysis
from app.services.llm_client import CallRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name  TEXT    NOT NULL,
    request       TEXT    NOT NULL,
    status        TEXT    NOT NULL CHECK (status IN ('awaiting_clarification', 'too_vague', 'incomplete', 'complete')),
    model         TEXT,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL,
    data_json     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analyses_updated ON analyses (updated_at DESC);

CREATE TABLE IF NOT EXISTS ai_calls (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id    INTEGER NOT NULL REFERENCES analyses (id) ON DELETE CASCADE,
    stage          TEXT    NOT NULL,
    attempts       INTEGER NOT NULL,
    input_tokens   INTEGER NOT NULL,
    output_tokens  INTEGER NOT NULL,
    seconds        REAL    NOT NULL,
    succeeded      INTEGER NOT NULL,
    created_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_calls_analysis ON ai_calls (analysis_id);
"""


@dataclass(frozen=True)
class AnalysisSummary:
    id: int
    project_name: str
    status: str
    model: str
    updated_at: str


def status_of(analysis: Analysis) -> str:
    if analysis.problem and analysis.problem.is_too_vague:
        return "too_vague"
    if analysis.is_complete:
        return "complete"
    if analysis.stakeholders is None and analysis.requirements is None:
        return "awaiting_clarification"
    return "incomplete"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AnalysisRepository:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        """One short-lived connection per operation: commit on success, roll back on error."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # --- Analyses -----------------------------------------------------------------

    def save(self, analysis: Analysis, analysis_id: int | None = None) -> int:
        """Insert a new analysis, or update an existing one. Returns its ID."""
        values = (
            analysis.input.project_name, analysis.input.request, status_of(analysis),
            analysis.model, _now(), analysis.model_dump_json(),
        )
        with self._connect() as conn:
            if analysis_id is not None:
                cursor = conn.execute(
                    """UPDATE analyses
                       SET project_name = ?, request = ?, status = ?, model = ?, updated_at = ?, data_json = ?
                       WHERE id = ?""",
                    (*values, analysis_id),
                )
                if cursor.rowcount:
                    return analysis_id
            cursor = conn.execute(
                """INSERT INTO analyses (project_name, request, status, model, updated_at, data_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (*values, analysis.created_at.isoformat(timespec="seconds")),
            )
            return cursor.lastrowid

    def get(self, analysis_id: int) -> Analysis | None:
        with self._connect() as conn:
            row = conn.execute("SELECT data_json FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
        return Analysis.model_validate_json(row["data_json"]) if row else None

    def list_recent(self, limit: int = 20) -> list[AnalysisSummary]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, project_name, status, model, updated_at
                   FROM analyses
                   ORDER BY updated_at DESC, id DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        return [AnalysisSummary(**dict(row)) for row in rows]

    def delete(self, analysis_id: int) -> bool:
        """Permanently delete an analysis and its usage log (ON DELETE CASCADE)."""
        with self._connect() as conn:
            return conn.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,)).rowcount > 0

    # --- AI usage ----------------------------------------------------------------

    def log_calls(self, analysis_id: int, calls: list[CallRecord]) -> None:
        if not calls:
            return
        with self._connect() as conn:
            conn.executemany(
                """INSERT INTO ai_calls
                   (analysis_id, stage, attempts, input_tokens, output_tokens, seconds, succeeded, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [(analysis_id, c.stage, c.attempts, c.input_tokens, c.output_tokens, c.seconds, int(c.succeeded), _now())
                 for c in calls],
            )

    def usage_by_stage(self, analysis_id: int) -> list[dict]:
        """Token and time totals per stage, e.g. to find the most expensive step."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT stage,
                          COUNT(*)            AS calls,
                          SUM(attempts)       AS attempts,
                          SUM(input_tokens)   AS input_tokens,
                          SUM(output_tokens)  AS output_tokens,
                          ROUND(SUM(seconds), 1) AS seconds
                   FROM ai_calls
                   WHERE analysis_id = ?
                   GROUP BY stage
                   ORDER BY SUM(output_tokens) DESC""",
                (analysis_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def usage_totals(self) -> dict:
        """Totals across every analysis in the database."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT COUNT(DISTINCT analysis_id)       AS analyses,
                          COUNT(*)                          AS calls,
                          COALESCE(SUM(input_tokens), 0)    AS input_tokens,
                          COALESCE(SUM(output_tokens), 0)   AS output_tokens,
                          COALESCE(SUM(attempts - 1), 0)    AS retries
                   FROM ai_calls"""
            ).fetchone()
        return dict(row)
