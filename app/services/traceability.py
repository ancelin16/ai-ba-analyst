"""Requirements Traceability Matrix (RTM) and coverage checks.

Built deterministically from the IDs each stage cites, with no AI involved:

    Business Objective -> Requirement -> User Story -> Acceptance Criterion -> Test Case

The AI proposes the links and this module verifies them. It reports:
- the matrix: one row per requirement with everything linked to it;
- coverage gaps: e.g. a Must Have requirement with no test, or a story with
  no acceptance criteria. A BA would review these before sign-off;
- dangling references: links to IDs that don't exist. The pipeline already
  rejects these, so this matters mainly for data loaded from elsewhere.
"""

from collections import defaultdict
from dataclasses import dataclass, field

import pandas as pd

from app.models.analysis import Analysis
from app.models.common import Priority

MATRIX_COLUMNS = [
    "Business Objectives", "Requirement", "Type", "Description", "Priority",
    "User Stories", "Acceptance Criteria", "Test Cases", "Trace Status",
]

FULLY_TRACED = "Fully traced"
PARTIAL = "Partially traced"
NOT_TESTED = "Not tested"
OUT_OF_SCOPE = "Out of scope (Won't Have)"


@dataclass
class CoverageGap:
    severity: str  # "High" or "Medium"
    item_id: str
    message: str


@dataclass
class TraceabilityReport:
    matrix: pd.DataFrame
    gaps: list[CoverageGap] = field(default_factory=list)
    dangling_references: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    @property
    def is_clean(self) -> bool:
        return not self.gaps and not self.dangling_references


def _join(ids) -> str:
    return ", ".join(sorted(set(ids)))


def build_traceability(analysis: Analysis) -> TraceabilityReport:
    problem, reqs = analysis.problem, analysis.requirements
    if problem is None or reqs is None:
        return TraceabilityReport(matrix=pd.DataFrame(columns=MATRIX_COLUMNS))

    stories = analysis.stories.stories if analysis.stories else []
    criteria = analysis.criteria.criteria if analysis.criteria else []
    tests = analysis.test_cases.test_cases if analysis.test_cases else []
    requirements = [*reqs.functional, *reqs.non_functional]

    objective_ids = {o.id for o in problem.objectives}
    requirement_ids = {r.id for r in requirements}
    story_ids = {s.id for s in stories}
    criterion_ids = {c.id for c in criteria}

    # Index the links in both directions.
    stories_by_req = defaultdict(set)
    for s in stories:
        for rid in s.requirement_ids:
            stories_by_req[rid].add(s.id)
    criteria_by_story = defaultdict(set)
    for c in criteria:
        criteria_by_story[c.story_id].add(c.id)
    tests_by_req, tests_by_criterion = defaultdict(set), defaultdict(set)
    for t in tests:
        for rid in t.requirement_ids:
            tests_by_req[rid].add(t.id)
        for cid in t.criterion_ids:
            tests_by_criterion[cid].add(t.id)

    # --- Matrix -----------------------------------------------------------------
    rows, tests_for = [], {}
    for req in requirements:
        is_fr = req.id.startswith("FR-")
        req_stories = stories_by_req[req.id]
        req_criteria = {c for s in req_stories for c in criteria_by_story[s]}
        # A requirement is tested directly, or through the criteria of its stories.
        req_tests = tests_by_req[req.id] | {t for c in req_criteria for t in tests_by_criterion[c]}
        tests_for[req.id] = req_tests

        if req.priority == Priority.WONT:
            status = OUT_OF_SCOPE
        elif not req_tests:
            status = NOT_TESTED
        elif req.objective_ids and (not is_fr or (req_stories and req_criteria)):
            status = FULLY_TRACED
        else:
            status = PARTIAL

        rows.append({
            "Business Objectives": _join(req.objective_ids),
            "Requirement": req.id,
            "Type": "Functional" if is_fr else f"Non-functional ({req.category.value})",
            "Description": req.description,
            "Priority": req.priority.value,
            "User Stories": _join(req_stories) if is_fr else "n/a",
            "Acceptance Criteria": _join(req_criteria) if is_fr else "n/a",
            "Test Cases": _join(req_tests),
            "Trace Status": status,
        })
    matrix = pd.DataFrame(rows, columns=MATRIX_COLUMNS)

    # --- Coverage gaps ------------------------------------------------------------
    gaps: list[CoverageGap] = []
    in_scope = [r for r in requirements if r.priority != Priority.WONT]
    supported_objectives = {oid for r in in_scope for oid in r.objective_ids}

    for obj in problem.objectives:
        if obj.id not in supported_objectives:
            gaps.append(CoverageGap("High", obj.id, f"{obj.id} has no requirements supporting it."))
    for req in in_scope:
        if not req.objective_ids:
            gaps.append(CoverageGap("Medium", req.id, f"{req.id} is not linked to any business objective."))
        if req.id.startswith("FR-") and analysis.stories and not stories_by_req[req.id]:
            gaps.append(CoverageGap("High", req.id, f"{req.id} is not covered by any user story."))
        if analysis.test_cases and req.priority in (Priority.MUST, Priority.SHOULD) and not tests_for[req.id]:
            gaps.append(CoverageGap("High", req.id, f"{req.id} ({req.priority.value}) has no test case."))
    for req in requirements:
        if req.priority == Priority.WONT and (stories_by_req[req.id] or tests_by_req[req.id]):
            gaps.append(CoverageGap(
                "Medium", req.id, f"{req.id} is marked Won't Have but still has stories or tests; check the scope."
            ))
    if analysis.criteria:
        for s in stories:
            if not criteria_by_story[s.id]:
                gaps.append(CoverageGap("High", s.id, f"{s.id} has no acceptance criteria."))
    if analysis.test_cases:
        for c in criteria:
            if not tests_by_criterion[c.id]:
                gaps.append(CoverageGap("Medium", c.id, f"{c.id} is not verified by any test case."))

    # --- Dangling references ------------------------------------------------------
    dangling = []
    def check(owner, refs, valid):
        dangling.extend(f"{owner} -> {ref}" for ref in refs if ref not in valid)
    for r in requirements:
        check(r.id, r.objective_ids, objective_ids)
    for s in stories:
        check(s.id, s.requirement_ids, requirement_ids)
    for c in criteria:
        check(c.id, [c.story_id], story_ids)
    for t in tests:
        check(t.id, t.requirement_ids, requirement_ids)
        check(t.id, t.criterion_ids, criterion_ids)
    for uc in (analysis.use_cases.use_cases if analysis.use_cases else []):
        check(uc.id, uc.requirement_ids, requirement_ids)

    # --- Metrics ----------------------------------------------------------------------
    in_scope_rows = matrix[matrix["Trace Status"] != OUT_OF_SCOPE]
    total = len(in_scope_rows)
    tested = int((in_scope_rows["Test Cases"] != "").sum())
    metrics = {
        "requirements_in_scope": total,
        "requirements_tested": tested,
        "test_coverage_pct": round(100 * tested / total) if total else 0,
        "fully_traced": int((matrix["Trace Status"] == FULLY_TRACED).sum()),
        "objectives": len(objective_ids),
        "stories": len(stories),
        "acceptance_criteria": len(criteria),
        "test_cases": len(tests),
    }
    return TraceabilityReport(matrix=matrix, gaps=gaps, dangling_references=dangling, metrics=metrics)
