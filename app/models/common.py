"""Shared types used across all analysis artifacts."""

import re
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator


class LenientEnum(str, Enum):
    """Enum that tolerates small formatting differences in AI output.

    "must have", "MUST_HAVE" and "Must-Have" all resolve to "Must Have".
    Anything that still does not match is rejected by Pydantic as usual.
    """

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            key = re.sub(r"[\s_\-]+", "", value).lower()
            for member in cls:
                if re.sub(r"[\s_\-]+", "", member.value).lower() == key:
                    return member
        return None


class Basis(LenientEnum):
    """Where an item came from — the core guard against invented facts."""

    STATED = "Stated"      # explicitly in the user's input
    INFERRED = "Inferred"  # a reasonable conclusion drawn from the input
    ASSUMED = "Assumed"    # not in the input; must be confirmed with stakeholders


class Priority(LenientEnum):
    """MoSCoW prioritization for requirements and user stories."""

    MUST = "Must Have"
    SHOULD = "Should Have"
    COULD = "Could Have"
    WONT = "Won't Have"


class Level(LenientEnum):
    """Generic High/Medium/Low scale (test priority, risk likelihood/impact, influence)."""

    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class ScenarioType(LenientEnum):
    POSITIVE = "Positive"
    NEGATIVE = "Negative"
    EDGE_CASE = "Edge Case"


def _id(pattern: str, example: str):
    return Annotated[str, Field(pattern=pattern, examples=[example])]


# Stable ID formats. Traceability depends on these being predictable.
ObjectiveId = _id(r"^BO-\d{2}$", "BO-01")
StakeholderId = _id(r"^SH-\d{2}$", "SH-01")
QuestionId = _id(r"^Q-\d{2}$", "Q-01")
FunctionalReqId = _id(r"^FR-\d{3}$", "FR-001")
NonFunctionalReqId = _id(r"^NFR-\d{3}$", "NFR-001")
StoryId = _id(r"^US-\d{3}$", "US-001")
CriterionId = _id(r"^AC-\d{3}$", "AC-001")
UseCaseId = _id(r"^UC-\d{2}$", "UC-01")
TestCaseId = _id(r"^TC-\d{3}$", "TC-001")
RiskId = _id(r"^RK-\d{2}$", "RK-01")
AssumptionId = _id(r"^AS-\d{2}$", "AS-01")
ConstraintId = _id(r"^CN-\d{2}$", "CN-01")
ProcessStepId = _id(r"^(CS|FS)-\d{2}$", "CS-01")

NonEmptyStr = Annotated[str, Field(min_length=1)]


class ArtifactModel(BaseModel):
    """Base for every AI-produced model: trims whitespace, ignores unknown fields."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")


# Fields that point at artifacts produced by earlier stages.
REFERENCE_FIELDS = ("objective_ids", "requirement_ids", "story_id", "criterion_ids")


class StageResult(ArtifactModel):
    """Base for stage results.

    - Rejects duplicate IDs within any list field.
    - When validated with context={"known_ids": {...}}, rejects references to
      IDs that earlier stages never produced, e.g. a story citing FR-099.
    """

    @model_validator(mode="after")
    def ids_are_unique(self):
        for field_name, items in self._item_lists():
            ids = [item.id for item in items if hasattr(item, "id")]
            duplicates = sorted({i for i in ids if ids.count(i) > 1})
            if duplicates:
                raise ValueError(f"duplicate IDs in {field_name}: {', '.join(duplicates)}")
        return self

    @model_validator(mode="after")
    def references_exist(self, info: ValidationInfo):
        known = (info.context or {}).get("known_ids")
        if known is None:
            return self
        unknown = []
        for _, items in self._item_lists():
            for item in items:
                for field_name in REFERENCE_FIELDS:
                    refs = getattr(item, field_name, None)
                    refs = [refs] if isinstance(refs, str) else refs or []
                    unknown += [f"{getattr(item, 'id', '?')} -> {ref}" for ref in refs if ref not in known]
        if unknown:
            raise ValueError(
                "references to IDs that do not exist: " + ", ".join(unknown)
                + f". Valid IDs are: {', '.join(sorted(known))}"
            )
        return self

    @model_validator(mode="after")
    def coverage_is_complete(self, info: ValidationInfo):
        """With context={"must_cover": [(field, ids, label), ...]}, every ID in
        `ids` must be cited in `field` by at least one item. For example,
        every in-scope requirement must appear in some story's requirement_ids."""
        problems = []
        for field_name, required_ids, label in (info.context or {}).get("must_cover", []):
            cited = set()
            for _, items in self._item_lists():
                for item in items:
                    refs = getattr(item, field_name, None)
                    cited.update([refs] if isinstance(refs, str) else refs or [])
            missing = sorted(set(required_ids) - cited)
            if missing:
                problems.append(f"these {label} are not covered by any item: {', '.join(missing)}")
        if problems:
            raise ValueError("; ".join(problems) + ". Every one of them must be referenced at least once.")
        return self

    def _item_lists(self):
        for field_name in type(self).model_fields:
            value = getattr(self, field_name)
            if isinstance(value, list):
                yield field_name, value
