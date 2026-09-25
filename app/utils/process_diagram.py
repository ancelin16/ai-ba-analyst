"""Build Graphviz DOT process-flow diagrams from structured process steps.

The AI returns steps as data (actor, action, flags, next steps). This module
draws them, so the AI never writes diagram syntax directly and a diagram can
never be syntactically broken.
"""

from app.models.artifacts import ProcessStep

COLORS = {
    "manual": "#FDEBD0",      # light orange
    "bottleneck": "#F5B7B1",  # light red
    "system": "#D6EAF8",      # light blue
    "default": "#FFFFFF",
}


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _wrap(text: str, width: int = 28) -> str:
    """Wrap long labels so boxes stay readable."""
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return "\\n".join(_escape(part) for part in lines)


def _fill(step: ProcessStep) -> str:
    if step.is_bottleneck:
        return COLORS["bottleneck"]
    if step.is_manual:
        return COLORS["manual"]
    actor = step.actor.lower()
    if any(word in actor for word in ("system", "application", "portal", "platform", "website", "app ")) or actor == "app":
        return COLORS["system"]
    return COLORS["default"]


def process_to_dot(steps: list[ProcessStep], title: str = "") -> str:
    """Return a left-to-right DOT flowchart. Steps link in list order unless
    `next_step_ids` names explicit successors (for branches)."""
    ids = {s.id for s in steps}
    lines = [
        "digraph process {",
        '  rankdir=LR; bgcolor="transparent";',
        '  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10];',
        '  edge [color="#566573"];',
    ]
    if title:
        lines.append(f'  label="{_escape(title)}"; labelloc=t; fontname="Helvetica"; fontsize=12;')
    lines.append('  start [shape=circle, label="", width=0.2, style=filled, fillcolor="#2E4053"];')
    lines.append('  end [shape=doublecircle, label="", width=0.15, style=filled, fillcolor="#2E4053"];')

    for step in steps:
        flag = " ⚠" if step.is_bottleneck else ""
        label = f"{step.id}{flag}\\n{_wrap(step.actor)}\\n—\\n{_wrap(step.description)}"
        lines.append(f'  "{step.id}" [label="{label}", fillcolor="{_fill(step)}"];')

    if steps:
        lines.append(f'  start -> "{steps[0].id}";')
    for i, step in enumerate(steps):
        targets = [t for t in step.next_step_ids if t in ids]
        if not targets:
            targets = [steps[i + 1].id] if i + 1 < len(steps) else ["end"]
        for target in targets:
            lines.append(f'  "{step.id}" -> "{target}";' if target != "end" else f'  "{step.id}" -> end;')
    lines.append("}")
    return "\n".join(lines)
