"""Audit ordered tool attempts: blocked events consume attempts, not executions.

An over-limit call is expected to appear as a blocked event. Counting all events
and rejecting >4/>32 incorrectly rejects evidence of working enforcement.
"""
from __future__ import annotations


def audit_tool_attempts(turns: list[dict], limits: dict) -> dict:
    issues = []
    attempted = executed = blocked = 0
    action_cap = limits.get("tool_attempts_per_action")
    task_cap = limits.get("tool_attempts_per_task")

    def add(code, turn, detail):
        issues.append({"code": code, "detail": f"turn {turn['turn_index']}: {detail}"})

    for turn in turns:
        for position, event in enumerate(turn["events"], 1):
            # Count every listed invocation attempt, including blocked ones.
            attempted += 1
            if not isinstance(event, dict):
                add("invalid_tool_event", turn, f"event {position} is not an object")
                continue
            if type(event.get("index")) is not int or event["index"] != position:
                add("tool_event_index_mismatch", turn,
                    f"event position {position} has index={event.get('index')!r}")
            status = event.get("execution_status")
            if not isinstance(status, str) or status not in {"ok", "error", "blocked"}:
                add("invalid_tool_status", turn, f"event {position} status={status!r}")
                continue
            if status == "blocked":
                blocked += 1
            else:
                # A tool exception is still an execution attempt.
                executed += 1
            over_action = action_cap is not None and position > action_cap
            over_task = task_cap is not None and attempted > task_cap
            if (over_action or over_task) and status != "blocked":
                add("unblocked_over_budget_tool", turn,
                    f"event {position}, task attempt {attempted} executed as {status}")
            if status == "blocked" and action_cap is not None and task_cap is not None:
                if not over_action and not over_task:
                    add("premature_tool_block", turn,
                        f"event {position}, task attempt {attempted} blocked before budget limit")
                if event.get("result_repr") is not None:
                    add("blocked_tool_has_result", turn, f"event {position} has a return value")
    return {"attempted": attempted, "executed": executed, "blocked": blocked,
            "issues": issues}
