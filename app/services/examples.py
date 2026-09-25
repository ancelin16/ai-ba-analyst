"""Built-in example scenarios (data/examples/*.json).

Each file holds a realistic business request and, optionally, a pre-generated
analysis. Examples with an analysis can be explored in Demo Mode without an
API key.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.config import PROJECT_ROOT
from app.models.analysis import Analysis

logger = logging.getLogger(__name__)

EXAMPLES_DIR = PROJECT_ROOT / "data" / "examples"


@dataclass(frozen=True)
class Example:
    slug: str
    title: str
    summary: str
    input: dict
    analysis: Analysis | None

    @property
    def has_demo(self) -> bool:
        return self.analysis is not None


def load_examples(directory: Path = EXAMPLES_DIR) -> list[Example]:
    examples = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            analysis = Analysis.model_validate(data["analysis"]) if data.get("analysis") else None
            if analysis:
                analysis.is_demo = True
            examples.append(Example(path.stem, data["title"], data.get("summary", ""), data["input"], analysis))
        except (OSError, KeyError, json.JSONDecodeError, ValidationError) as exc:
            # A broken example file should not take down the app.
            logger.warning("Skipping example %s: %s", path.name, exc)
    return examples
