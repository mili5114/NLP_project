"""反馈统一入口：按 condition 分派。

A / B 由 A 侧实现（baselines.py）；C / D 由 B 侧实现（selective.py）。
任何一路失败都不许静默吞掉，否则方法比较会变成"某个条件其实没生效"。
"""

from __future__ import annotations

from typing import Any, Callable

from .baselines import BASELINES, feedback_official_output, feedback_trace_first

FeedbackFn = Callable[..., dict[str, Any]]

CONDITIONS = ("A", "B", "C", "D")


def _resolve(condition: str) -> FeedbackFn:
    condition = condition.upper()
    if condition in BASELINES:
        return BASELINES[condition]
    # C / D 属于 B 的实现，导入失败要明确报错而不是回退到 A/B
    from . import selective  # noqa: PLC0415

    fn = getattr(selective, "build_feedback_for_condition", None)
    if fn is None:
        raise NotImplementedError(
            f"condition {condition} 需要 src/feedback/selective.py 的 build_feedback_for_condition"
        )
    return fn


def build_feedback(
    *,
    python_output: str,
    events: list[dict[str, Any]],
    condition: str,
    settings: dict[str, Any],
) -> dict[str, Any]:
    fn = _resolve(condition)
    result = fn(
        python_output=python_output,
        events=events,
        condition=condition.upper(),
        settings=settings,
    )
    if not isinstance(result, dict) or "text" not in result or "metadata" not in result:
        raise TypeError(f"{condition} 的反馈实现必须返回 {{'text': str, 'metadata': dict}}")
    limit = int(settings.get("feedback_characters", 2000))
    if len(result["text"]) > limit:
        raise ValueError(f"{condition} 反馈超长：{len(result['text'])} > {limit}")
    return result


__all__ = [
    "build_feedback",
    "feedback_official_output",
    "feedback_trace_first",
    "CONDITIONS",
]
