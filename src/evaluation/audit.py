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
from .io import episode_fingerprint, is_synthetic_record, read_json
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
    condition_config_shas: dict[str, str] | None = None,
    expected_code_commit: str | None = None,
    expected_model_revision: str | None = None,
    require_version_checks: bool | None = None,
) -> dict:
    """Audit a set of episodes and return a JSON-serializable report.

    Formal mode (allow_synthetic=False) requires split DEV or EVAL and uses
    manifest[split] as the expected task set.  Synthetic mode requires an
    explicit synthetic_tasks list.  The report is written even when the status
    is FAIL/INCOMPLETE so nothing silently disappears.

    Formal version checks are mandatory: a formal audit cannot claim PASS while
    silently skipping version/config verification.  Config hashes are checked
    per condition (``condition_config_shas``), because A/B/C/D legitimately have
    different full configs; the four conditions are NOT required to share one
    hash.
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

    if require_version_checks is None:
        require_version_checks = not allow_synthetic
    if require_version_checks and not allow_synthetic:
        missing_expectations = []
        if not condition_config_shas and not expected_config_sha:
            missing_expectations.append("config hash (--condition-config-sha / --expected-config-sha)")
        if not expected_code_commit:
            missing_expectations.append("code commit (--expected-code-commit)")
        if not expected_model_revision:
            missing_expectations.append("model revision (--expected-model-revision)")
        if missing_expectations:
            # A formal audit may not skip version verification and still PASS.
            issue(errors, "formal_version_expectation_missing", None,
                  "formal audit missing required version expectations: "
                  + "; ".join(missing_expectations), OWNER_B)

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

        # --- Version / config identity ---
        ep_config = ep.get("config_sha256")
        if require_version_checks and not allow_synthetic:
            # Required fields may not be "present-only" checks: absence is a FAIL.
            if not ep_config:
                issue(errors, "config_sha256_missing", ep,
                      "formal episode is missing config_sha256", OWNER_B)
            if "code_commit" not in ep:
                issue(errors, "code_commit_missing", ep,
                      "formal episode is missing code_commit", OWNER_A)
            if "model_revision" not in ep:
                issue(errors, "model_revision_missing", ep,
                      "formal episode is missing model_revision", OWNER_A)

        if condition_config_shas:
            expected_for_condition = condition_config_shas.get(condition)
            if expected_for_condition is None:
                issue(errors, "condition_config_sha_missing", ep,
                      f"no expected config hash supplied for condition {condition!r}", OWNER_B)
            elif ep_config != expected_for_condition:
                # Per-condition check: A/B/C/D may legitimately differ in full config.
                issue(errors, "config_hash_mismatch", ep,
                      f"condition {condition}: config_sha256={ep_config!r} != "
                      f"{expected_for_condition!r}", OWNER_B)
        elif expected_config_sha is not None:
            if ep_config != expected_config_sha:
                issue(errors, "config_hash_mismatch", ep,
                      f"config_sha256={ep_config!r} != {expected_config_sha!r}", OWNER_B)
        elif not require_version_checks:
            unverifiable.append({"code": "config_hash_not_checked", "slot": key,
                                 "detail": "no expected config hash supplied (allowed in "
                                           "synthetic mode; formal audits require one)",
                                 "owner": OWNER_B})

        if expected_code_commit is not None:
            actual_commit = ep.get("code_commit")
            if actual_commit is None:
                issue(errors, "code_commit_missing", ep,
                      "episode has no code_commit to compare", OWNER_A)
            elif actual_commit != expected_code_commit:
                issue(errors, "version_mismatch", ep,
                      f"code_commit={actual_commit!r} != {expected_code_commit!r}", OWNER_A)
        if expected_model_revision is not None:
            actual_revision = ep.get("model_revision")
            if actual_revision is None:
                issue(errors, "model_revision_missing", ep,
                      "episode has no model_revision to compare", OWNER_A)
            elif actual_revision != expected_model_revision:
                issue(errors, "version_mismatch", ep,
                      f"model_revision={actual_revision!r} != {expected_model_revision!r}",
                      OWNER_A)

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
                    # Two final-answer concepts, checked separately.
                    produced = usage["final_answer_turns"]
                    final_only = usage["final_only_turns"]
                    has_answer = ep.get("final_answer") is not None
                    if has_answer and len(produced) != 1:
                        issue(errors, "final_answer_call_missing", ep,
                              "episode has a final answer but produced_final_answer "
                              f"turns={produced} (expected exactly one)", OWNER_A)
                    if not has_answer and produced:
                        issue(errors, "answer_state_mismatch", ep,
                              f"episode has no final_answer but turns {produced} set "
                              "produced_final_answer", OWNER_A)
                    if len(final_only) > 1:
                        issue(errors, "multiple_final_only_turns", ep,
                              f"is_final_answer_turn turns={final_only}", OWNER_A)
                    if final_only:
                        if final_only != [turns[-1]["turn_index"]]:
                            issue(errors, "final_only_turn_not_last", ep,
                                  f"final-only turn(s) {final_only} must be the last "
                                  f"turn_index {turns[-1]['turn_index']}", OWNER_A)
                        if turns[-1].get("events"):
                            issue(errors, "tool_in_final_answer_turn", ep,
                                  f"final-only turn has {len(turns[-1]['events'])} tool "
                                  "events; tools do not execute in the final turn", OWNER_A)

                    # Course budget checks that require the per-call log.
                    interaction_cap = limits.get("interaction_turns")
                    interaction_count = len(turns) - len(final_only)
                    if interaction_cap is not None and interaction_count > int(interaction_cap):
                        issue(errors, "turn_budget_exceeded", ep,
                              f"{interaction_count} interaction turns > {interaction_cap}", OWNER_A)
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
                        # Only the dedicated final-only turn gets the 128 cap.  An
                        # interaction turn that produced the Answer still gets 384.
                        cap = final_cap if turn["is_final_answer_turn"] else per_turn_cap
                        if cap is not None and out > int(cap):
                            issue(errors, "turn_token_limit_exceeded", ep,
                                  f"turn {turn['turn_index']} output_tokens={out} > {cap} "
                                  f"(is_final_answer_turn={turn['is_final_answer_turn']})",
                                  OWNER_A)
                    per_action = limits.get("tool_attempts_per_action")
                    if per_action is not None:
                        turn_by_index = {str(t["turn_index"]): t for t in turns}
                        for index, count in usage["tool_events_per_turn"].items():
                            turn_obj = turn_by_index.get(index, {})
                            if count > int(per_action) and not turn_obj.get("is_final_answer_turn"):
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

    run_ids = sorted({str(ep.get("run_id")) for ep in episodes if isinstance(ep, dict)})
    config_sets: dict[str, set[str]] = {}
    for ep in episodes:
        if not isinstance(ep, dict):
            continue
        config_sets.setdefault(str(ep.get("condition")), set()).add(str(ep.get("config_sha256")))
    config_by_condition = {k: sorted(v) for k, v in config_sets.items()}

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
        # Identity of the audited input; summarize.py recomputes this from the
        # scored file and refuses to treat a stale audit as authoritative.
        "input_fingerprint": episode_fingerprint(episodes),
        "run_ids": run_ids,
        "config_by_condition": config_by_condition,
        "formal_version_checks": bool(require_version_checks),
        "final_answer_semantics": (
            "produced_final_answer marks the call whose output is the final Answer "
            "(interaction turn, 384 cap); is_final_answer_turn marks the dedicated "
            "final-only turn after budget exhaustion (128 cap, no tools). Pending "
            "A's real turns schema; map fields once in turns_reader."
        ),
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
