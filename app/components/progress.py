"""Long-running AI work in a background thread, with live progress that
survives page re-runs.

Why this is needed:
- The pipeline runs stages in parallel worker threads, and Streamlit can
  only draw from its own script thread. Workers therefore report progress
  through a queue, and the script thread polls it.
- Streamlit re-runs the whole page whenever the user interacts with it.
  A re-run would normally abandon the loop that was watching the worker,
  and the worker would carry on invisibly. To prevent that, the running job
  is stored in session state, and every page run first reattaches to any
  job in progress (see main.py). Its `on_finish` callback runs exactly once,
  in whichever page run sees the job complete.
"""

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import streamlit as st

from app.services.pipeline import STAGE_LABELS

POLL_SECONDS = 0.4
JOB_KEY = "active_job"

# on_finish(result, error): exactly one of the two is set.
FinishCallback = Callable[[object, Exception | None], None]


@dataclass
class Job:
    label: str
    stages: list[str]
    on_finish: FinishCallback
    started: float = field(default_factory=time.monotonic)
    events: queue.Queue = field(default_factory=queue.Queue)
    outcome: dict = field(default_factory=dict)
    phases: dict = field(default_factory=dict)  # stage -> (phase, seconds since start)
    thread: threading.Thread | None = None


def is_running() -> bool:
    return JOB_KEY in st.session_state


def start(
    label: str,
    task: Callable,
    stages: list[str],
    on_finish: FinishCallback,
    already_done: set[str] | None = None,
) -> None:
    """Run `task(on_progress)` in the background and watch it until it finishes."""
    if is_running():
        watch()  # never start a second job alongside the first
        return
    job = Job(label=label, stages=stages, on_finish=on_finish)
    job.phases = {s: ("done", None) if s in (already_done or set()) else ("waiting", None) for s in stages}

    def worker():
        try:
            job.outcome["value"] = task(lambda stage, status: job.events.put((stage, status, time.monotonic())))
        except Exception as exc:  # delivered to on_finish in the script thread
            job.outcome["error"] = exc

    job.thread = threading.Thread(target=worker, daemon=True)
    st.session_state[JOB_KEY] = job
    job.thread.start()
    watch()


def watch() -> None:
    """Show live progress for the running job (if any) until it finishes, then
    hand the result to its on_finish callback."""
    job: Job | None = st.session_state.get(JOB_KEY)
    if job is None:
        return

    with st.status(job.label, expanded=True) as status:
        st.caption("Please keep this tab open until the analysis finishes.")
        timer = st.empty()
        rows = {stage: st.empty() for stage in job.stages}
        _render(job, rows)
        while job.thread.is_alive() or not job.events.empty():
            changed = False
            while not job.events.empty():
                stage, phase, at = job.events.get()
                job.phases[stage] = ("done" if phase == "done" else "running", at - job.started)
                changed = True
            if changed:
                _render(job, rows)
            timer.caption(f"Elapsed: {time.monotonic() - job.started:.0f}s. Each AI step typically takes 10 to 90 seconds.")
            time.sleep(POLL_SECONDS)

        # Claim the job before running on_finish, so it can never run twice.
        if st.session_state.pop(JOB_KEY, None) is not job:
            return
        elapsed = time.monotonic() - job.started
        if "error" in job.outcome:
            status.update(label="Stopped: a step failed", state="error", expanded=True)
        else:
            status.update(label=f"{job.label}: complete ({elapsed:.0f}s)", state="complete", expanded=False)
    job.on_finish(job.outcome.get("value"), job.outcome.get("error"))


def _render(job: Job, rows: dict) -> None:
    for stage, (phase, at) in job.phases.items():
        name = STAGE_LABELS.get(stage, stage)
        if phase == "done":
            suffix = f" · {at:.0f}s" if at is not None else " · already done"
            rows[stage].markdown(f":material/check_circle: {name}:gray[{suffix}]")
        elif phase == "running":
            rows[stage].markdown(f":material/progress_activity: **{name}**: in progress…")
        else:
            rows[stage].markdown(f":gray[:material/radio_button_unchecked: {name}]")
