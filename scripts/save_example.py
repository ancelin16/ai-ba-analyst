"""Copy a saved analysis from the database into an example file for Demo Mode.

Usage:  .venv/bin/python -m scripts.save_example <analysis_id> <example_slug>
e.g.    .venv/bin/python -m scripts.save_example 1 05_sales_leads
"""

import json
import sys

from app.config import get_settings
from app.services.examples import EXAMPLES_DIR
from app.services.storage import AnalysisRepository


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    analysis_id, slug = int(sys.argv[1]), sys.argv[2]
    path = EXAMPLES_DIR / f"{slug}.json"
    if not path.exists():
        raise SystemExit(f"No example file {path.name}")
    analysis = AnalysisRepository(get_settings().database_path).get(analysis_id)
    if analysis is None:
        raise SystemExit(f"No analysis with id {analysis_id}")
    example = json.loads(path.read_text())
    example["analysis"] = json.loads(analysis.model_dump_json())
    path.write_text(json.dumps(example, indent=2))
    print(f"Saved analysis {analysis_id} ({analysis.input.project_name}) into {path.name}")


if __name__ == "__main__":
    main()
