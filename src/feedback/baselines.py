"""条件 A / B 的反馈基线（A 侧实现；C / D 由 B 在 src/feedback/selective.py 实现）。

两个条件共用同一套硬上限：2000 字符、同一截断标记、同样的拼装顺序规则。
不要为了"看起来更完整"而在 B 里偷偷放宽预算或换顺序——这正是被比较的对象。
"""

from __future__ import annotations

from typing import Any

DEFAULT_TRACE_FORMAT = {
    "prefix": "Tool execution trace (actual calls, in execution order):\n",
    "event": "[{index}] {tool} args={args_repr} kwargs={kwargs_repr} [{execution_status}] -> {result_or_error}",
    "python_separator": "\nPython output:\n",
}


def _limit_of(settings: dict[str, Any]) -> int:
    return int(settings.get("feedback_characters", 2000))


def _marker_of(settings: dict[str, Any]) -> str:
    return str(settings.get("truncation_marker", "\n[Output Truncated]"))


def _truncate(text: str, limit: int, marker: str) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    keep = max(0, limit - len(marker))
    return text[:keep] + marker, True


def _event_line(event: dict[str, Any], fmt: dict[str, str]) -> str:
    status = event.get("execution_status", "ok")
    payload = event.get("result_repr") if status == "ok" else event.get("error_repr")
    return fmt["event"].format(
        index=event.get("index"),
        tool=event.get("tool"),
        args_repr=event.get("args_repr", ""),
        kwargs_repr=event.get("kwargs_repr", ""),
        execution_status=status,
        result_or_error="None" if payload is None else payload,
    )


def feedback_official_output(
    *,
    python_output: str,
    events: list[dict[str, Any]],
    settings: dict[str, Any],
    condition: str = "A",
) -> dict[str, Any]:
    """条件 A：官方实现的做法——只把 Python 原始输出送回模型。"""
    limit = _limit_of(settings)
    text, truncated = _truncate(python_output, limit, _marker_of(settings))
    return {
        "text": text,
        "metadata": {
            "selected_event_indices": [],
            "omitted_event_indices": [e.get("index") for e in events],
            "truncated": truncated,
            "feedback_chars": len(text),
            "rule_trigger_count": 0,
            "python_output_omitted": False,
        },
    }


def feedback_trace_first(
    *,
    python_output: str,
    events: list[dict[str, Any]],
    settings: dict[str, Any],
    condition: str = "B",
) -> dict[str, Any]:
    """条件 B：先放工具调用轨迹（按真实执行顺序），剩余预算才给 Python 输出。

    这就是被研究的对象：预算紧张时被挤掉的往往是 Python 输出，
    因为轨迹行先占位。不要改这个顺序。
    """
    limit = _limit_of(settings)
    marker = _marker_of(settings)
    fmt = {**DEFAULT_TRACE_FORMAT, **settings.get("full_trace_format", {})}

    header = fmt["prefix"]
    separator = fmt["python_separator"]

    used = len(header)
    lines: list[str] = []
    selected: list[int] = []
    omitted: list[int] = []

    for event in events:
        line = _event_line(event, fmt) + "\n"
        if used + len(line) > limit:
            omitted.append(event.get("index"))
            continue
        lines.append(line)
        selected.append(event.get("index"))
        used += len(line)

    trace_text = header + "".join(lines)

    # Python 输出拿剩下的空间
    remaining = limit - used - len(separator)
    python_part = ""
    python_omitted = False
    truncated = bool(omitted)
    if remaining > 0 and python_output:
        body, cut = _truncate(python_output, remaining, marker)
        if cut:
            truncated = True
        if body:
            python_part = separator + body
    elif python_output:
        python_omitted = True
        truncated = True

    text = trace_text + python_part
    # 兜底，防浮点/多字节导致越界
    if len(text) > limit:
        text, cut = _truncate(text, limit, marker)
        truncated = truncated or cut

    return {
        "text": text,
        "metadata": {
            "selected_event_indices": selected,
            "omitted_event_indices": omitted,
            "truncated": truncated,
            "feedback_chars": len(text),
            "rule_trigger_count": 0,
            "python_output_omitted": python_omitted,
        },
    }


BASELINES = {
    "A": feedback_official_output,
    "B": feedback_trace_first,
}
