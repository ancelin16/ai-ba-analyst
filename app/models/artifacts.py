"""Business-analysis artifacts produced by the AI pipeline.

Each pipeline stage returns one of the `*Result` models at the bottom of this
file. The AI is asked for JSON matching these schemas, and anything that does
not validate is rejected before it reaches the UI.

Cross-references between artifacts (e.g. a user story citing FR-003) are plain
ID strings. They are checked in the traceability service, not trusted blindly.
"""

from pydantic import Field, model_validator

from app.models.common import (
    ArtifactModel,
    AssumptionId,
    Basis,
    ConstraintId,
    CriterionId,
    FunctionalReqId,
    Level,
    NonEmptyStr,
    NonFunctionalReqId,
    ObjectiveId,
    Priority,
    ProcessStepId,
    QuestionId,
    RiskId,
    ScenarioType,
    StakeholderId,
    StoryId,
    TestCaseId,
    UseCaseId,
    LenientEnum,
    StageResult,
)


# --- Clarifying questions -------------------------------------------------

class QuestionCategory(LenientEnum):
    CRITICAL = "Critical"
    IMPORTANT = "Important"
    NICE_TO_KNOW = "Nice to Know"


class ClarifyingQuestion(ArtifactModel):
    id: QuestionId
    question: NonEmptyStr
    category: QuestionCategory
    area: str = Field(default="", description="Topic, e.g. Users, Data, Security, Scope")
    rationale: str = Field(default="", description="Why the answer matters")

    @model_validator(mode="after")
    def critical_questions_need_rationale(self):
        if self.category == QuestionCategory.CRITICAL and not self.rationale:
            raise ValueError(f"{self.id}: critical questions must explain why they matter")
        return self


# --- Business problem analysis --------------------------------------------

class BusinessObjective(ArtifactModel):
    id: ObjectiveId
    description: NonEmptyStr
    success_measure: str = Field(default="", description="How success would be measured, if known")
    basis: Basis


class BusinessProblemAnalysis(StageResult):
    problem_statement: NonEmptyStr
    objectives: list[BusinessObjective] = Field(min_length=1)
    target_users: list[str] = Field(default_factory=list)
    current_state: str = ""
    future_state: str = ""
    in_scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list, description="Contradictions found in the request")
    # Set when the request lacks enough detail to produce meaningful requirements.
    is_too_vague: bool = False
    missing_information: list[str] = Field(default_factory=list)


# --- Stakeholders ----------------------------------------------------------

class StakeholderType(LenientEnum):
    INTERNAL = "Internal"
    EXTERNAL = "External"


class Stakeholder(ArtifactModel):
    id: StakeholderId
    name: NonEmptyStr = Field(description="Role or group, e.g. 'Customer Service Team'")
    type: StakeholderType
    interest: NonEmptyStr = Field(description="What they need from or care about in the project")
    influence: Level
    impact: Level = Field(description="How strongly the change affects them")
    basis: Basis
    # True when the stakeholder was not mentioned but a BA would expect them.
    potentially_missing: bool = False


# --- Requirements ----------------------------------------------------------

class FunctionalRequirement(ArtifactModel):
    id: FunctionalReqId
    description: NonEmptyStr = Field(description="'The system shall ...' statement")
    priority: Priority
    rationale: NonEmptyStr
    objective_ids: list[ObjectiveId] = Field(default_factory=list)
    basis: Basis


class NFRCategory(LenientEnum):
    PERFORMANCE = "Performance"
    SECURITY = "Security"
    AVAILABILITY = "Availability"
    SCALABILITY = "Scalability"
    ACCESSIBILITY = "Accessibility"
    USABILITY = "Usability"
    DATA_PRIVACY = "Data Privacy"
    RELIABILITY = "Reliability"
    COMPLIANCE = "Compliance"
    MAINTAINABILITY = "Maintainability"


class NonFunctionalRequirement(ArtifactModel):
    id: NonFunctionalReqId
    category: NFRCategory
    description: NonEmptyStr
    priority: Priority
    rationale: NonEmptyStr = Field(description="Why this matters for this specific project")
    measurable_target: str = Field(default="", description="Only if a target was provided or clearly implied")
    objective_ids: list[ObjectiveId] = Field(default_factory=list)
    basis: Basis


# --- User stories & acceptance criteria ----------------------------------

class UserStory(ArtifactModel):
    id: StoryId
    role: NonEmptyStr
    want: NonEmptyStr = Field(description="Completes 'I want ...', e.g. 'to look up my order'")
    so_that: NonEmptyStr = Field(description="Completes 'so that ...', e.g. 'I know when it will arrive'")
    priority: Priority
    business_value: NonEmptyStr
    requirement_ids: list[FunctionalReqId] = Field(min_length=1)

    @property
    def text(self) -> str:
        return f"As a {self.role}, I want {self.want}, so that {self.so_that}."


class AcceptanceCriterion(ArtifactModel):
    id: CriterionId
    story_id: StoryId
    title: NonEmptyStr
    scenario_type: ScenarioType
    given: NonEmptyStr
    when: NonEmptyStr
    then: NonEmptyStr

    @property
    def text(self) -> str:
        return f"Given {self.given},\nWhen {self.when},\nThen {self.then}."


# --- Use cases -------------------------------------------------------------

class Flow(ArtifactModel):
    name: NonEmptyStr = Field(description="E.g. '3a. Order number not found'")
    steps: list[str] = Field(min_length=1)


class UseCase(ArtifactModel):
    id: UseCaseId
    name: NonEmptyStr
    primary_actor: NonEmptyStr
    goal: NonEmptyStr
    preconditions: list[str] = Field(default_factory=list)
    main_flow: list[str] = Field(min_length=1)
    alternative_flows: list[Flow] = Field(default_factory=list)
    exceptions: list[Flow] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    requirement_ids: list[FunctionalReqId] = Field(default_factory=list)


# --- Process analysis ------------------------------------------------------

class ProcessStep(ArtifactModel):
    id: ProcessStepId
    actor: NonEmptyStr
    description: NonEmptyStr
    is_manual: bool = False
    is_bottleneck: bool = False
    next_step_ids: list[str] = Field(default_factory=list, description="Empty means 'the next step in the list'")


class ProcessAnalysis(StageResult):
    # False when the request does not describe the process well enough to map it.
    sufficient_detail: bool
    current_state: list[ProcessStep] = Field(default_factory=list)
    future_state: list[ProcessStep] = Field(default_factory=list)
    bottlenecks: list[str] = Field(default_factory=list)
    manual_activities: list[str] = Field(default_factory=list)
    inefficiencies: list[str] = Field(default_factory=list)
    automation_opportunities: list[str] = Field(default_factory=list)
    notes: str = ""


# --- Risks, assumptions, constraints -------------------------------------

class RiskSource(LenientEnum):
    BUSINESS = "Business"
    PROCESS = "Process"
    TECHNICAL = "Technical"
    DATA = "Data"
    COMPLIANCE = "Compliance"
    ADOPTION = "Adoption"
    PROJECT = "Project"


class Risk(ArtifactModel):
    id: RiskId
    description: NonEmptyStr
    source: RiskSource
    likelihood: Level
    impact: Level
    mitigation: NonEmptyStr


class Assumption(ArtifactModel):
    id: AssumptionId
    description: NonEmptyStr
    impact_if_wrong: NonEmptyStr
    validate_with: str = Field(default="", description="Who should confirm it")


class Constraint(ArtifactModel):
    id: ConstraintId
    description: NonEmptyStr
    type: str = Field(default="", description="E.g. Budget, Technical, Regulatory, Timeline")
    basis: Basis


# --- Test cases ------------------------------------------------------------

class TestCase(ArtifactModel):
    __test__ = False  # tell pytest this is not a test class

    id: TestCaseId
    requirement_ids: list[FunctionalReqId | NonFunctionalReqId] = Field(min_length=1)
    criterion_ids: list[CriterionId] = Field(default_factory=list)
    scenario: NonEmptyStr
    scenario_type: ScenarioType
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(min_length=1)
    expected_result: NonEmptyStr
    priority: Level


# --- Stage results (one per AI call) -------------------------------------

class ClarifyingQuestionsResult(StageResult):
    questions: list[ClarifyingQuestion]


class StakeholderResult(StageResult):
    stakeholders: list[Stakeholder] = Field(min_length=1)


class RequirementsResult(StageResult):
    functional: list[FunctionalRequirement] = Field(min_length=1)
    non_functional: list[NonFunctionalRequirement] = Field(min_length=1)


class UserStoriesResult(StageResult):
    stories: list[UserStory] = Field(min_length=1)


class AcceptanceCriteriaResult(StageResult):
    criteria: list[AcceptanceCriterion] = Field(min_length=1)


class UseCasesResult(StageResult):
    use_cases: list[UseCase] = Field(min_length=1)


class RiskAnalysisResult(StageResult):
    risks: list[Risk] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    edge_cases: list[str] = Field(default_factory=list)


class TestCasesResult(StageResult):
    __test__ = False

    test_cases: list[TestCase] = Field(min_length=1)
