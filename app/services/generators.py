"""One function per analysis stage: pair a prompt with its output schema.

Generators know nothing about Streamlit, databases or API details. They take
inputs plus a client and return validated models, which keeps them easy to
test and to reuse.

Stages that cite earlier artifacts pass `known_ids`, so a reference to an ID
that doesn't exist fails validation and triggers the client's corrective retry.
"""

from concurrent.futures import ThreadPoolExecutor

from app.models.artifacts import (
    AcceptanceCriteriaResult,
    BusinessProblemAnalysis,
    ClarifyingQuestionsResult,
    ProcessAnalysis,
    RequirementsResult,
    RiskAnalysisResult,
    StakeholderResult,
    TestCasesResult,
    UseCasesResult,
    UserStoriesResult,
    UserStory,
)
from app.models.common import Priority
from app.models.inputs import ProjectInput
from app.prompts import (
    acceptance_criteria,
    business_problem,
    clarifying_questions,
    process_analysis,
    requirements as requirements_prompt,
    risk_analysis,
    stakeholders as stakeholders_prompt,
    test_cases as test_cases_prompt,
    use_cases as use_cases_prompt,
    user_stories,
)
from app.prompts.base import BA_SYSTEM_PROMPT
from app.services.llm_client import LLMClient


def _run(
    client: LLMClient,
    stage: str,
    module,
    prompt: str,
    known_ids: set[str] | None = None,
    must_cover: list[tuple[str, set[str], str]] | None = None,
):
    """Call the AI for one stage.

    known_ids:  IDs this stage may cite; citing anything else fails validation.
    must_cover: (field, ids, label) rules; every id must be cited in `field`.
    """
    context = {}
    if known_ids is not None:
        context["known_ids"] = known_ids
    if must_cover:
        context["must_cover"] = must_cover
    return client.generate(
        stage=stage,
        system=BA_SYSTEM_PROMPT,
        prompt=prompt,
        output_model=module.OUTPUT_MODEL,
        context=context or None,
    )


def in_scope_functional_ids(requirements: RequirementsResult) -> set[str]:
    return {r.id for r in requirements.functional if r.priority != Priority.WONT}


def must_test_ids(requirements: RequirementsResult) -> set[str]:
    """Must Have and Should Have requirements, functional and non-functional."""
    return {
        r.id
        for r in [*requirements.functional, *requirements.non_functional]
        if r.priority in (Priority.MUST, Priority.SHOULD)
    }


# --- Stage 1 ---------------------------------------------------------------

def generate_clarifying_questions(client: LLMClient, project: ProjectInput) -> ClarifyingQuestionsResult:
    return _run(client, "clarifying_questions", clarifying_questions, clarifying_questions.build_prompt(project))


def analyze_business_problem(client: LLMClient, project: ProjectInput) -> BusinessProblemAnalysis:
    return _run(client, "business_problem", business_problem, business_problem.build_prompt(project))


# --- Stage 2 ---------------------------------------------------------------

def analyze_stakeholders(client: LLMClient, project: ProjectInput, problem: BusinessProblemAnalysis) -> StakeholderResult:
    return _run(client, "stakeholders", stakeholders_prompt, stakeholders_prompt.build_prompt(project, problem))


def analyze_process(client: LLMClient, project: ProjectInput, problem: BusinessProblemAnalysis) -> ProcessAnalysis:
    return _run(client, "process_analysis", process_analysis, process_analysis.build_prompt(project, problem))


def analyze_risks(
    client: LLMClient, project: ProjectInput, problem: BusinessProblemAnalysis, open_questions: str
) -> RiskAnalysisResult:
    return _run(client, "risk_analysis", risk_analysis, risk_analysis.build_prompt(project, problem, open_questions))


# --- Stages 3-6 --------------------------------------------------------------

def generate_requirements(
    client: LLMClient,
    project: ProjectInput,
    problem: BusinessProblemAnalysis,
    stakeholders: StakeholderResult,
    process: ProcessAnalysis,
    risks: RiskAnalysisResult,
) -> RequirementsResult:
    prompt = requirements_prompt.build_prompt(project, problem, stakeholders, process, risks)
    return _run(client, "requirements", requirements_prompt, prompt, known_ids={o.id for o in problem.objectives})


def generate_user_stories(
    client: LLMClient, project: ProjectInput, stakeholders: StakeholderResult, requirements: RequirementsResult
) -> UserStoriesResult:
    must_cover = in_scope_functional_ids(requirements)
    prompt = user_stories.build_prompt(project, stakeholders, requirements, must_cover)
    return _run(
        client, "user_stories", user_stories, prompt,
        known_ids={r.id for r in requirements.functional},
        must_cover=[("requirement_ids", must_cover, "functional requirements")],
    )


def generate_use_cases(
    client: LLMClient, project: ProjectInput, requirements: RequirementsResult, process: ProcessAnalysis
) -> UseCasesResult:
    prompt = use_cases_prompt.build_prompt(project, requirements, process)
    return _run(client, "use_cases", use_cases_prompt, prompt, known_ids={r.id for r in requirements.functional})


# --- Batching ---------------------------------------------------------------------
# Long lists are unreliable in one AI call. In live testing, responses ended
# normally (not truncated) after roughly 10 list items, even when asked for
# more and even after a corrective retry. Criteria and tests are therefore
# generated for a few stories at a time, in parallel, then merged and
# renumbered, which keeps each response well under that ceiling.

STORIES_PER_BATCH = 2
MAX_EXTRA_REQUIREMENTS_IN_LAST_BATCH = 3


def _batches(items: list, size: int = STORIES_PER_BATCH) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _in_parallel(fn, jobs: list) -> list:
    """Run fn(job) for each job concurrently; results keep the input order."""
    if len(jobs) == 1:
        return [fn(jobs[0])]
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        return list(pool.map(fn, jobs))


def _renumber(items: list, prefix: str) -> list:
    """Give merged batch results one continuous sequence: AC-001, AC-002, ..."""
    return [item.model_copy(update={"id": f"{prefix}-{i:03d}"}) for i, item in enumerate(items, 1)]


def generate_acceptance_criteria(
    client: LLMClient,
    project: ProjectInput,
    stories: UserStoriesResult,
    requirements: RequirementsResult,
    risks: RiskAnalysisResult,
) -> AcceptanceCriteriaResult:
    def one_batch(batch: list[UserStory]) -> AcceptanceCriteriaResult:
        story_ids = {s.id for s in batch}
        prompt = acceptance_criteria.build_prompt(project, UserStoriesResult(stories=batch), requirements, risks)
        return _run(
            client, "acceptance_criteria", acceptance_criteria, prompt,
            known_ids=story_ids,
            must_cover=[("story_id", story_ids, "user stories")],
        )

    results = _in_parallel(one_batch, _batches(stories.stories))
    return AcceptanceCriteriaResult(criteria=_renumber([c for r in results for c in r.criteria], "AC"))


def generate_test_cases(
    client: LLMClient,
    project: ProjectInput,
    requirements: RequirementsResult,
    stories: UserStoriesResult,
    criteria: AcceptanceCriteriaResult,
) -> TestCasesResult:
    all_requirement_ids = {r.id for r in requirements.functional} | {r.id for r in requirements.non_functional}
    must_test = must_test_ids(requirements)

    # Each batch covers its stories' criteria, plus the Must/Should requirements
    # those stories deliver (each requirement assigned to exactly one batch).
    # Whatever remains, mainly non-functional requirements, joins the last batch
    # if there are only a few, or gets a batch of its own.
    jobs, assigned = [], set()
    for batch in _batches(stories.stories):
        story_ids = {s.id for s in batch}
        batch_criteria = [c for c in criteria.criteria if c.story_id in story_ids]
        batch_requirements = {rid for s in batch for rid in s.requirement_ids} & must_test - assigned
        assigned |= batch_requirements
        jobs.append({"stories": batch, "criteria": batch_criteria, "must_test": batch_requirements})
    remaining = must_test - assigned
    if len(remaining) <= MAX_EXTRA_REQUIREMENTS_IN_LAST_BATCH:
        jobs[-1]["must_test"] |= remaining
    else:
        jobs.append({"stories": [], "criteria": [], "must_test": remaining})

    def one_batch(job: dict) -> TestCasesResult:
        criterion_ids = {c.id for c in job["criteria"]}
        prompt = test_cases_prompt.build_prompt(project, requirements, job["stories"], job["criteria"], job["must_test"])
        must_cover = []
        if criterion_ids:
            must_cover.append(("criterion_ids", criterion_ids, "acceptance criteria"))
        if job["must_test"]:
            must_cover.append(("requirement_ids", job["must_test"], "Must Have / Should Have requirements"))
        return _run(
            client, "test_cases", test_cases_prompt, prompt,
            known_ids=all_requirement_ids | criterion_ids,
            must_cover=must_cover,
        )

    results = _in_parallel(one_batch, jobs)
    return TestCasesResult(test_cases=_renumber([t for r in results for t in r.test_cases], "TC"))
