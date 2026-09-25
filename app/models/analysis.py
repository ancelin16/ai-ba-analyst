"""The complete analysis for one project: the input plus every stage's output.

Stages fill this in progressively, so every section is optional. `None` means
"not generated yet". It never means "empty".
"""

from datetime import datetime, timezone

from pydantic import BaseModel, Field

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
)
from app.models.inputs import ProjectInput


class Analysis(BaseModel):
    input: ProjectInput
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model: str = ""
    is_demo: bool = False

    # Stage 1: understand the request, gate on clarification
    questions: ClarifyingQuestionsResult | None = None
    problem: BusinessProblemAnalysis | None = None
    # Stage 2: context
    stakeholders: StakeholderResult | None = None
    process: ProcessAnalysis | None = None
    risks: RiskAnalysisResult | None = None
    # Stages 3-6: requirements chain
    requirements: RequirementsResult | None = None
    stories: UserStoriesResult | None = None
    use_cases: UseCasesResult | None = None
    criteria: AcceptanceCriteriaResult | None = None
    test_cases: TestCasesResult | None = None

    @property
    def is_complete(self) -> bool:
        return all(
            getattr(self, name) is not None
            for name in (
                "questions", "problem", "stakeholders", "process", "risks",
                "requirements", "stories", "use_cases", "criteria", "test_cases",
            )
        )
