"""Run the analysis pipeline live against the Claude API from the command line.

Usage:
    .venv/bin/python -m scripts.run_analysis                        # order-tracking example, full analysis
    .venv/bin/python -m scripts.run_analysis --stage-one            # questions + problem only (2 calls)
    .venv/bin/python -m scripts.run_analysis --example 02_it_equipment --save-demo

--example picks a scenario from data/examples. --save-demo writes the result
into that example file so it can be viewed in Demo Mode without an API key.
Otherwise the result is saved to data/samples/<example>_analysis.json.
"""

import argparse
import json
import time

from app.config import PROJECT_ROOT, get_settings
from app.services.examples import EXAMPLES_DIR
from app.services.llm_client import ClaudeClient, summarize_usage
from app.services.pipeline import STAGE_LABELS, needs_more_information, run_analysis, run_stage_one
from app.services.traceability import build_traceability
from app.utils.errors import AppError
from app.utils.validation import validate_project_input


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage-one", action="store_true", help="stop after clarifying questions")
    parser.add_argument("--example", default="01_order_tracking", help="example file name without .json")
    parser.add_argument("--save-demo", action="store_true", help="store the result in the example file")
    args = parser.parse_args()

    example_path = EXAMPLES_DIR / f"{args.example}.json"
    example = json.loads(example_path.read_text())
    settings = get_settings()
    validation = validate_project_input(example["input"])
    if not validation.ok:
        raise SystemExit("\n".join(validation.errors))

    started = time.monotonic()

    def progress(stage: str, status: str) -> None:
        if status == "done":
            print(f"  [{time.monotonic() - started:5.1f}s] done: {STAGE_LABELS[stage]}")

    print(f"Model: {settings.model}\n")
    try:
        client = ClaudeClient(settings=settings)
        analysis = run_stage_one(client, validation.input, settings.model, on_progress=progress)
        if needs_more_information(analysis):
            print("\nRequest too vague. Missing:", *analysis.problem.missing_information, sep="\n  - ")
        elif not args.stage_one:
            run_analysis(client, analysis, on_progress=progress)
    except AppError as exc:
        raise SystemExit(f"\nError: {exc.user_message}\n(detail: {exc.detail})")

    print("\nOUTPUT COUNTS")
    counts = {
        "Clarifying questions": len(analysis.questions.questions),
        "Business objectives": len(analysis.problem.objectives),
    }
    if analysis.is_complete:
        counts |= {
            "Stakeholders": len(analysis.stakeholders.stakeholders),
            "Process steps (current/future)": f"{len(analysis.process.current_state)}/{len(analysis.process.future_state)}",
            "Risks / assumptions / constraints": (
                f"{len(analysis.risks.risks)}/{len(analysis.risks.assumptions)}/{len(analysis.risks.constraints)}"
            ),
            "Functional / non-functional reqs": (
                f"{len(analysis.requirements.functional)}/{len(analysis.requirements.non_functional)}"
            ),
            "User stories": len(analysis.stories.stories),
            "Use cases": len(analysis.use_cases.use_cases),
            "Acceptance criteria": len(analysis.criteria.criteria),
            "Test cases": len(analysis.test_cases.test_cases),
        }
    for label, value in counts.items():
        print(f"  {label:36} {value}")

    if analysis.is_complete:
        report = build_traceability(analysis)
        print("\nTRACEABILITY", report.metrics)
        print("  Coverage gaps:", len(report.gaps))
        for gap in report.gaps:
            print(f"    [{gap.severity}] {gap.message}")
        print("  Dangling references:", report.dangling_references or "none")

    print("\nUSAGE", summarize_usage(client.calls), f"wall time {time.monotonic() - started:.0f}s")
    for call in client.calls:
        print(f"  {call.stage:22} {call.attempts} attempt(s)  {call.input_tokens:>6} in  {call.output_tokens:>6} out  {call.seconds:>5}s")

    if args.save_demo:
        example["analysis"] = json.loads(analysis.model_dump_json())
        example_path.write_text(json.dumps(example, indent=2))
        print(f"\nSaved into demo example {example_path.name}")
    else:
        out = PROJECT_ROOT / "data" / "samples" / f"{args.example}_analysis.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(analysis.model_dump_json(indent=2))
        print(f"\nSaved to {out.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
