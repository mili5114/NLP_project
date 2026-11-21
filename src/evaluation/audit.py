"""Experiment-completeness audit for C's offline toolchain.

The official task list is read from configs/course/split_manifest.json; this
module never keeps its own copy.  Synthetic audits use an *explicit* task list
supplied by the caller and never inject synthetic tasks into the official
manifest.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import InputError
from .io import is_synthetic_record, read_json
from .turns_reader import read_turns, summarize_turn_usage

OWNER_A = "A (runtime / online logs)"
OWNER_B = "B (method / frozen config)"
OWNER_C = "C (offline reference / expectations)"

FAILURE_TERMINATIONS = {
    "no_answer",
    "timeout",
    "time_limit",
    "budget_exhausted",
    "token_budget_exhausted",
    "tool_budget_exhausted",
    "max_turns",
    "context_limit",
    "error",
    "execution_error",
    "parse_error",
}

OWNER_HINTS = {
    "A": "trajectory_path, turns.jsonl fields, token usage, versions in manifest/episode",
    "B": "condition config, frozen commit/config_sha256, method-side feedback metadata",
    "C": "reference file, explicit synthetic expectation set, offline aggregation",
}


def load_manifest(path: str | Path) -> dict[str, list[str]]:
    """Load and sanity-check the course split manifest (the only task-list source)."""
    value = read_json(path)
    if not isinstance(value, dict) or "DEV" not in value or "EVAL" not in value:
        raise InputError(f"manifest {path} must contain DEV and EVAL lists")
    manifest: dict[str, list[str]] = {}
    for split in ("DEV", "EVAL"):
        tasks = value[split]
        if not isinstance(tasks, list) or not all(isinstance(t, str) and t for t in tasks):
            raise InputError(f"manifest {path}: {split} must be a list of non-empty strings")
        if len(tasks) != len(set(tasks)):
            raise InputError(f"manifest {path}: {split} contains duplicate task ids")
        manifest[split] = tasks
    if set(manifest["DEV"]) & set(manifest["EVAL"]):
        raise InputError(f"manifest {path}: DEV and EVAL share task ids")
    return manifest


def _slot(task_id: Any, condition: Any) -> str:
    return f"{task_id}|{condition}"


def audit_episodes(
    episodes: list[dict],
    *,
    split: str,
    conditions: list[str],
    manifest: dict[str, list[str]] | None = None,
    settings: dict[str, Any] | None = None,
    allow_synthetic: bool = False,
    synthetic_tasks: list[str] | None = None,
    trajectory_root: str | Path | None = None,
    episode_sources: list[str] | None = None,
    expected_config_sha: str | None = None,
    expected_code_commit: str | None = None,
    expected_model_revision: str | None = None,
) -> dict:
    """Audit a set of episodes and return a JSON-serializable report.

    Formal mode (allow_synthetic=False) requires split DEV or EVAL and uses
    manifest[split] as the expected task set.  Synthetic mode requires an
    explicit synthetic_tasks list.  The report is written even when the status
    is FAIL/INCOMPLETE so nothing silently disappears.
    """
    if not conditions:
        raise InputError("conditions must not be empty")
    unknown_conditions = [c for c in conditions if c not in {"A", "B", "C", "D"}]
    if unknown_conditions:
        raise InputError(f"unknown conditions: {unknown_conditions}")

    mode = "synthetic" if allow_synthetic else "formal"
    if not allow_synthetic and split not in ("DEV", "EVAL"):
        raise InputError(f"formal audit split must be DEV or EVAL, got {split!r}")
    if manifest is None and not synthetic_tasks:
        raise InputError("manifest or explicit synthetic_tasks is required")

    if synthetic_tasks is not None:
        expected_tasks = list(synthetic_tasks)
    else:
        expected_tasks = list(manifest[split])  # type: ignore[index]
    expected_slots = {_slot(t, c) for t in expected_tasks for c in conditions}
    if not allow_synthetic and split == "EVAL" and conditions == ["A", "B", "C", "D"]:
        if len(expected_tasks) != 27 or len(expected_slots) != 108:
            raise InputError(
                f"formal EVAL must be 27 tasks x 4 conditions = 108 slots; "
                f"got {len(expected_tasks)} tasks / {len(expected_slots)} slots"
            )

    limits = (settings or {}).get("limits", {})
    root = Path(trajectory_root) if trajectory_root else Path.cwd()

    errors: list[dict] = []
    warnings: list[dict] = []
    unverifiable: list[dict] = []

    def issue(bucket: list[dict], code: str, ep: dict | None, detail: str, owner: str) -> None:
        entry = {
            "code": code,
            "task_id": ep.get("task_id") if ep else None,
            "condition": ep.get("condition") if ep else None,
            "run_id": ep.get("run_id") if ep else None,
            "detail": detail,
            "owner": owner,
        }
        bucket.append(entry)

    seen: dict[str, dict] = {}
    duplicates: list[str] = []
    unknown_tasks: list[str] = []
    wrong_split: list[str] = []
    unknown_condition: list[str] = []
    recorded_failures: list[dict] = []
    eps_with_synthetic = 0

    for idx, ep in enumerate(episodes):
        if not isinstance(ep, dict):
            issue(errors, "malformed_episode", None,
                  f"episodes[{idx}] is not an object", OWNER_C)
            continue
        source = episode_sources[idx] if episode_sources and idx < len(episode_sources) else f"episodes[{idx}]"
        task_id, condition = ep.get("task_id"), ep.get("condition")
        key = _slot(task_id, condition)

        if key in seen:
            duplicates.append(key)
            issue(errors, "duplicate_slot", ep,
                  f"slot {key} already recorded from {seen[key]}", OWNER_A)
        else:
            seen[key] = source

        if task_id not in expected_tasks:
            unknown_tasks.append(key)
            issue(errors, "unknown_task", ep,
                  f"{key} is not in the expected task set for split={split}", OWNER_C)
        if str(ep.get("split", "")).upper() != str(split).upper():
            wrong_split.append(key)
            issue(errors, "wrong_split", ep,
                  f"episode split={ep.get('split')!r}, expected {split!r}", OWNER_A)
        if condition not in conditions:
            unknown_condition.append(key)
            issue(errors, "condition_not_requested", ep,
                  f"condition={condition!r} not in requested {conditions}", OWNER_B)

        if is_synthetic_record(ep):
            eps_with_synthetic += 1
            if not allow_synthetic:
                issue(errors, "synthetic_contamination", ep,
                      f"synthetic episode present in formal {split} audit", OWNER_A)
        elif allow_synthetic:
            issue(warnings, "non_synthetic_in_synthetic_audit", ep,
                  "non-synthetic episode included in synthetic audit", OWNER_C)

        # Recorded experimental failure is NOT the same as a missing record.
        termination = str(ep.get("termination_reason", "")).lower()
        is_failure = (
            ep.get("final_answer") is None
            or termination in FAILURE_TERMINATIONS
            or (ep.get("status") not in (None, "finished", "complete", "completed"))
        )
        if is_failure:
            recorded_failures.append({
                "slot": key,
                "termination_reason": ep.get("termination_reason"),
                "status": ep.get("status"),
                "has_answer": ep.get("final_answer") is not None,
            })

        # Version / config hash cross-checks (only when an expected value is given).
        if expected_config_sha is not None:
            if ep.get("config_sha256") != expected_config_sha:
                issue(errors, "config_hash_mismatch", ep,
                      f"config_sha256={ep.get('config_sha256')!r} != {expected_config_sha!r}",
                      OWNER_B)
        else:
            unverifiable.append({"code": "config_hash_not_checked", "slot": key,
                                 "detail": "no expected config hash supplied", "owner": OWNER_B})
        for field, expected in (("code_commit", expected_code_commit),
                                ("model_revision", expected_model_revision)):
            if expected is not None and field in ep and ep[field] != expected:
                issue(errors, "version_mismatch", ep,
                      f"{field}={ep[field]!r} != {expected!r}", OWNER_A)

        # Trajectory + per-call log checks.
        traj = ep.get("trajectory_path")
        turns = None
        if not traj:
            if allow_synthetic:
                issue(warnings, "trajectory_path_null_synthetic", ep,
                      "synthetic fixture has no trajectory file", OWNER_A)
            else:
                issue(errors, "trajectory_path_missing", ep,
                      "trajectory_path is null/empty in formal episode", OWNER_A)
        else:
            traj_path = Path(str(traj))
            if not traj_path.is_absolute():
                traj_path = root / traj_path
            if not traj_path.is_file():
                issue(errors, "trajectory_file_missing", ep,
                      f"trajectory not found: {traj_path}", OWNER_A)
            else:
                try:
                    turns = read_turns(traj_path)
                except InputError as exc:
                    issue(errors, "turns_invalid", ep, str(exc), OWNER_A)
                else:
                    usage = summarize_turn_usage(turns)
                    if usage["missing_usage_turns"]:
                        issue(errors, "missing_token_usage", ep,
                              f"turns without usage: {usage['missing_usage_turns']} "
                              "(not filled with 0)", OWNER_A)
                    if usage["invalid_usage"]:
                        issue(errors, "invalid_token_usage", ep,
                              f"invalid usage entries: {usage['invalid_usage']}", OWNER_A)
                    if usage["model_calls"] != ep.get("model_calls"):
                        issue(errors, "model_call_count_mismatch", ep,
                              f"turns have {usage['model_calls']} calls, "
                              f"episode.model_calls={ep.get('model_calls')}", OWNER_A)
                    if usage["input_tokens"] is not None:
                        for field, actual in (("input_tokens", usage["input_tokens"]),
                                              ("output_tokens", usage["output_tokens"])):
                            declared = ep.get(field)
                            if declared is None:
                                issue(warnings, "episode_total_missing", ep,
                                      f"episode.{field} absent; cannot cross-check", OWNER_A)
                            elif declared != actual:
                                issue(errors, "token_total_mismatch", ep,
                                      f"sum(turns.{field})={actual} != episode.{field}={declared}",
                                      OWNER_A)
                    if ep.get("final_answer") is not None and not usage["final_answer_turns"]:
                        issue(errors, "final_answer_call_missing", ep,
                              "episode has a final answer but no turn is marked is_final",
                              OWNER_A)
                    if len(usage["final_answer_turns"]) > 1:
                        issue(errors, "multiple_final_answer_calls", ep,
                              f"is_final turns: {usage['final_answer_turns']}", OWNER_A)

                    # Course budget checks that require the per-call log.
                    interaction_cap = limits.get("interaction_turns")
                    if interaction_cap is not None and len(turns) > int(interaction_cap) + 1:
                        issue(errors, "turn_budget_exceeded", ep,
                              f"{len(turns)} model calls > {interaction_cap}+1", OWNER_A)
                    feedback_cap = limits.get("feedback_characters")
                    if feedback_cap is not None and usage["max_feedback_chars"] > int(feedback_cap):
                        issue(errors, "feedback_char_limit_exceeded", ep,
                              f"max visible feedback={usage['max_feedback_chars']} > "
                              f"{feedback_cap}", OWNER_B)
                    per_turn_cap = limits.get("tokens_per_interaction")
                    final_cap = limits.get("final_answer_tokens")
                    for turn in turns:
                        out = turn.get("output_tokens")
                        if not isinstance(out, int) or isinstance(out, bool):
                            continue
                        cap = final_cap if turn["is_final"] else per_turn_cap
                        if cap is not None and out > int(cap):
                            issue(errors, "turn_token_limit_exceeded", ep,
                                  f"turn {turn['turn_index']} output_tokens={out} > {cap}",
                                  OWNER_A)
                    per_action = limits.get("tool_attempts_per_action")
                    if per_action is not None:
                        turn_by_index = {str(t["turn_index"]): t for t in turns}
                        for index, count in usage["tool_events_per_turn"].items():
                            turn_obj = turn_by_index.get(index, {})
                            if count > int(per_action) and not turn_obj.get("is_final"):
                                issue(errors, "tool_attempts_per_action_exceeded", ep,
                                      f"turn {index} has {count} tool events > {per_action}",
                                      OWNER_A)
                    total_cap = limits.get("total_generated_tokens")
                    if total_cap is not None and usage["output_tokens"] is not None:
                        if usage["output_tokens"] > int(total_cap):
                            issue(errors, "total_token_budget_exceeded", ep,
                                  f"sum output_tokens={usage['output_tokens']} > {total_cap}",
                                  OWNER_A)

        # Episode-level budget checks that do not need the turns file.
        per_task = limits.get("tool_attempts_per_task")
        if per_task is not None:
            executed = ep.get("tool_attempts_executed")
            blocked = ep.get("tool_attempts_blocked")
            if isinstance(executed, int) and isinstance(blocked, int):
                if executed + blocked > int(per_task):
                    issue(errors, "tool_attempts_per_task_exceeded", ep,
                          f"executed+blocked={executed + blocked} > {per_task}", OWNER_A)
        task_seconds = limits.get("task_seconds")
        wall = ep.get("wall_seconds")
        if task_seconds is not None and isinstance(wall, (int, float)) and not isinstance(wall, bool):
            if wall > float(task_seconds):
                issue(warnings, "wall_time_over_task_limit", ep,
                      f"wall_seconds={wall} > {task_seconds}; may include measurement "
                      "overhead, keep sample and explain rather than auto-delete", OWNER_A)
        if not limits:
            unverifiable.append({"code": "course_limits_not_loaded", "slot": key,
                                 "detail": "no runtime_settings.limits supplied", "owner": OWNER_A})

    missing_slots = sorted(expected_slots - set(seen))
    for slot in missing_slots:
        issue(errors, "missing_slot", None, f"no episode for expected slot {slot}", OWNER_A)

    if errors:
        status = "FAIL"
    elif missing_slots:
        status = "INCOMPLETE"
    else:
        status = "PASS"

    return {
        "mode": mode,
        "synthetic": bool(eps_with_synthetic) or allow_synthetic,
        "split": split,
        "conditions": conditions,
        "expected_task_count": len(expected_tasks),
        "expected_slot_count": len(expected_slots),
        "expected_slots": sorted(expected_slots),
        "recorded_slot_count": len(seen),
        "recorded_slots": sorted(seen),
        "missing_slots": missing_slots,
        "duplicate_slots": sorted(set(duplicates)),
        "unknown_task_slots": sorted(set(unknown_tasks)),
        "wrong_split_slots": sorted(set(wrong_split)),
        "condition_mismatch_slots": sorted(set(unknown_condition)),
        "recorded_failures": recorded_failures,
        "errors": errors,
        "warnings": warnings,
        "unverifiable": unverifiable,
        "complete": status == "PASS",
        "status": status,
        "owner_hints": OWNER_HINTS,
    }
