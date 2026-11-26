"""Python-first feedback for C, with D as the filtering ablation."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from .baselines import DEFAULT_TRACE_FORMAT, _event_line

PYTHON_HEADER = "Python output:\n"
DEFAULT_PYTHON_BODY_BUDGET = 1000
DEFAULT_MIN_MATCH_CHARS = 12
OBSERVER_TRUNCATION_MARKER = "\n[Output Truncated]"


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _matchable_return(event: dict[str, Any], min_chars: int) -> str:
    """Use the observer's raw string or representation of a normal tool return."""
    value = event.get("result_repr")
    if event["execution_status"] != "ok" or not isinstance(value, str):
        return ""
    if value.endswith(OBSERVER_TRUNCATION_MARKER):
        return ""
    normalized = _normalize(value)
    if normalized == "None" or (normalized.startswith("<") and normalized.endswith(">")):
        return ""
    return normalized if len(normalized) >= min_chars else ""


def _truncate(text: str, limit: int, marker: str) -> tuple[str, str]:
    """Keep the source prefix separate from the inserted truncation marker."""
    if len(text) <= limit:
        return text, ""
    marker = marker[:limit]
    return text[:limit - len(marker)], marker


def _render_trace(
    lines: list[tuple[int, str]], *, header: str, limit: int, marker: str
) -> tuple[str, list[int], int]:
    if not lines:
        return "", [], 0
    trace = header + "\n".join(line for _, line in lines)
    visible, suffix = _truncate(trace, limit, marker)
    complete = []
    offset = len(header)
    for index, line in lines:
        offset += len(line)
        if offset > len(visible):
            break
        complete.append(index)
        offset += 1  # separator between trace events
    return visible + suffix, complete, len(trace)


def build_feedback_for_condition(
    *, python_output: str, events: list[dict[str, Any]], condition: str,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Render Python output first, then the selected trace in the remaining room."""
    if condition not in {"C", "D"}:
        raise ValueError(f"Unsupported selective feedback condition: {condition}")
    limit = settings["feedback_characters"]
    body_budget = settings.get("python_body_budget", DEFAULT_PYTHON_BODY_BUDGET)
    min_chars = settings.get("min_match_chars", DEFAULT_MIN_MATCH_CHARS)
    if limit < len(PYTHON_HEADER) or body_budget < 1 or min_chars < 1:
        raise ValueError("Invalid selective feedback character budget or matching threshold")

    marker = settings.get("truncation_marker", OBSERVER_TRUNCATION_MARKER)
    body_limit = min(body_budget, limit - len(PYTHON_HEADER))
    visible_python, python_suffix = _truncate(python_output, body_limit, marker)
    python_block = PYTHON_HEADER + visible_python + python_suffix
    normalized_python = _normalize(visible_python)

    fmt = {**DEFAULT_TRACE_FORMAT, **settings.get("full_trace_format", {})}
    all_lines = []
    selected_lines = []
    filtered = {}
    matchable_event_count = 0
    for event in events:
        index = event["index"]
        line = _event_line(event, fmt)
        all_lines.append((index, line))
        value = _matchable_return(event, min_chars)
        matchable_event_count += bool(value)
        if condition == "C" and value and value in normalized_python:
            filtered[index] = "return_text_already_visible_in_python_output"
        else:
            selected_lines.append((index, line))

    trace_settings = {"header": "\n\n" + fmt["prefix"],
                      "limit": limit - len(python_block), "marker": marker}
    trace, fully_visible, selected_chars = _render_trace(selected_lines, **trace_settings)
    unfiltered_chars = selected_chars
    visible_feedback_changed = False
    if filtered:
        unfiltered_trace, _, unfiltered_chars = _render_trace(all_lines, **trace_settings)
        visible_feedback_changed = trace != unfiltered_trace

    text = python_block + trace
    python_truncated = len(visible_python) < len(python_output)
    trace_truncated = selected_chars > trace_settings["limit"]
    return {
        "text": text,
        "metadata": {
            "event_count": len(events),
            "matchable_event_count": matchable_event_count,
            "rule_trigger_count": len(filtered),
            "omitted_event_indices": list(filtered),
            "filter_reasons": filtered,
            "selected_event_indices": [index for index, _ in selected_lines],
            "fully_visible_event_indices": fully_visible,
            "python_truncated": python_truncated,
            "trace_truncated": trace_truncated,
            "truncated": python_truncated or trace_truncated,
            "chars_before_filtering": len(python_block) + unfiltered_chars,
            "chars_after_filtering": len(python_block) + selected_chars,
            "feedback_chars": len(text),
            "feedback_sha256": sha256(text.encode("utf-8")).hexdigest(),
            "visible_feedback_changed": visible_feedback_changed,
        },
    }
