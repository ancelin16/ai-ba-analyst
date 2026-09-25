"""Orchestrates the analysis stages in order and passes results forward.

    Stage 1  clarifying questions + problem analysis (parallel)   -> GATE
    Stage 2  stakeholders + process + risks (parallel)
    Stage 3  requirements
    Stage 4  user stories + use cases (parallel)
    Stage 5  acceptance criteria
    Stage 6  test cases
    (The traceability matrix is then built in code, not by the AI.)

Stage 1 is a gate: if the AI judges the request too vague, the pipeline stops
and reports what is missing instead of generating requirements from guesswork.

Results are written onto the Analysis object as each stage finishes. If a
stage fails, the finished stages are kept, and calling `run_analysis` again
resumes from the failed stage.
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from app.models.analysis import Analysis
from app.models.artifacts import QuestionCategory
from app.models.inputs import ClarificationAnswer, ProjectInput
from app.services import generators as gen
from app.services.llm_client import LLMClient
from app.utils.errors import InsufficientInformationError

# (stage key on Analysis, label shown to the user)
STAGES = [
    ("questions", "Clarifying questions"),
    ("problem", "Business problem analysis"),
    ("stakeholders", "Stakeholder analysis"),
    ("process", "Process analysis"),
    ("risks", "Risks, assumptions & constraints"),
    ("requirements", "Functional & non-functional requirements"),
    ("stories", "User stories"),
    ("use_cases", "Use cases"),
    ("criteria", "Acceptance criteria"),
    ("test_cases", "Test cases"),
]
STAGE_LABELS = dict(STAGES)

# Everything generated after the problem analysis. Cleared when the problem changes.
DOWNSTREAM = [key for key, _ in STAGES[2:]]

ProgressCallback = Callable[[str, str], None]  # (stage key, "started" | "done")


def _notify(on_progress: ProgressCallback | None, stage: str, status: str) -> None:
    if on_progress:
        on_progress(stage, status)


def _run_parallel(analysis: Analysis, tasks: dict, on_progress: ProgressCallback | None) -> None:
    """Run {stage_key: zero-arg callable} concurrently, skipping finished stages."""
    pending = {key: fn for key, fn in tasks.items() if getattr(analysis, key) is None}
    if not pending:
        return
    for key in pending:
        _notify(on_progress, key, "started")
    with ThreadPoolExecutor(max_workers=len(pending)) as pool:
        futures = {key: pool.submit(fn) for key, fn in pending.items()}
        errors = []
        # Save every stage that succeeded before raising, so a retry only reruns failures.
        for key, future in futures.items():
            try:
                setattr(analysis, key, future.result())
                _notify(on_progress, key, "done")
            except Exception as exc:
                errors.append(exc)
    if errors:
        raise errors[0]


# --- Stage 1 and the clarification gate -----------------------------------

def run_stage_one(
    client: LLMClient, project: ProjectInput, model_name: str = "", on_progress: ProgressCallback | None = None
) -> Analysis:
    """Generate clarifying questions and the problem analysis (in parallel)."""
    analysis = Analysis(input=project, model=model_name)
    _run_parallel(
        analysis,
        {
            "questions": lambda: gen.generate_clarifying_questions(client, project),
            "problem": lambda: gen.analyze_business_problem(client, project),
        },
        on_progress,
    )
    return analysis


def apply_clarifications(
    client: LLMClient,
    analysis: Analysis,
    answers: dict[str, str],
    on_progress: ProgressCallback | None = None,
) -> Analysis:
    """Record stakeholder answers and re-run the problem analysis with them.

    `answers` maps question ID to answer text. Blank answers are ignored.
    Downstream stages are cleared because they depend on the problem analysis.
    """
    questions = {q.id: q.question for q in analysis.questions.questions}
    analysis.input = analysis.input.model_copy(
        update={
            "clarifications": [
                ClarificationAnswer(question_id=qid, question=questions[qid], answer=text.strip())
                for qid, text in answers.items()
                if qid in questions and text and text.strip()
            ]
        }
    )
    if not analysis.input.clarifications:
        return analysis
    for key in ["problem", *DOWNSTREAM]:
        setattr(analysis, key, None)
    _run_parallel(analysis, {"problem": lambda: gen.analyze_business_problem(client, analysis.input)}, on_progress)
    return analysis


def needs_more_information(analysis: Analysis) -> bool:
    """True when the request is too vague to continue to requirements."""
    return bool(analysis.problem and analysis.problem.is_too_vague)


def unresolved_questions(analysis: Analysis) -> str:
    """Critical and Important questions nobody answered, as a bulleted list.

    These are passed to later stages, which must treat them as assumptions.
    """
    if not analysis.questions:
        return ""
    answered = {c.question_id for c in analysis.input.clarifications}
    return "\n".join(
        f"- {q.id} [{q.category.value}] {q.question}"
        for q in analysis.questions.questions
        if q.id not in answered and q.category != QuestionCategory.NICE_TO_KNOW
    )


# --- Stages 2-6 ----------------------------------------------------------------

def run_analysis(client: LLMClient, analysis: Analysis, on_progress: ProgressCallback | None = None) -> Analysis:
    """Run every remaining stage after the Stage 1 gate. Finished stages are skipped."""
    if analysis.questions is None or analysis.problem is None:
        raise ValueError("Run stage one before the full analysis")
    if needs_more_information(analysis):
        missing = "; ".join(analysis.problem.missing_information) or "see clarifying questions"
        raise InsufficientInformationError(f"Request too vague: {missing}")

    project, problem = analysis.input, analysis.problem
    a = analysis  # shorter name for the lambdas below; they read results as earlier stages fill them in

    _run_parallel(a, {
        "stakeholders": lambda: gen.analyze_stakeholders(client, project, problem),
        "process": lambda: gen.analyze_process(client, project, problem),
        "risks": lambda: gen.analyze_risks(client, project, problem, unresolved_questions(a)),
    }, on_progress)

    _run_parallel(a, {
        "requirements": lambda: gen.generate_requirements(client, project, problem, a.stakeholders, a.process, a.risks),
    }, on_progress)

    _run_parallel(a, {
        "stories": lambda: gen.generate_user_stories(client, project, a.stakeholders, a.requirements),
        "use_cases": lambda: gen.generate_use_cases(client, project, a.requirements, a.process),
    }, on_progress)

    _run_parallel(a, {
        "criteria": lambda: gen.generate_acceptance_criteria(client, project, a.stories, a.requirements, a.risks),
    }, on_progress)

    _run_parallel(a, {
        "test_cases": lambda: gen.generate_test_cases(client, project, a.requirements, a.stories, a.criteria),
    }, on_progress)

    return a
