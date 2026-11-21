"""Per-task aggregation, condition summaries, paired comparisons and input binding.

Statistics deliberately:
  * include every recorded failure in the denominator;
  * sum token usage over ALL model calls within a task first, then average over
    tasks (never average per-turn values directly);
  * never turn missing usage into 0 — it is excluded and counted separately;
  * mark INCOMPLETE when the audit is not clean, and carry the SYNTHETIC
    banner so demo output can never be mistaken for experimental results.

Summarize must NOT blindly trust an externally supplied audit JSON.  The audit
is bound to the scored file by (a) a canonical input fingerprint, (b) the exact
recorded slot set and (c) run/config identity.  A stale audit paired with new
data therefore yields INCOMPLETE, never COMPLETE.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .errors import InputError
from .io import episode_fingerprint, write_json

SYNTHETIC_BANNER = "SYNTHETIC — NOT EXPERIMENTAL RESULTS"
INCOMPLETE_BANNER = "INCOMPLETE — NOT FINAL RESULTS"

PER_TASK_FIELDS = [
    "task_id", "condition", "success", "termination_reason",
    "input_tokens", "output_tokens", "model_calls",
    "tool_attempts_executed", "tool_attempts_blocked", "wall_seconds",
    "run_id", "evidence_path", "scoring_reason", "synthetic",
]

SUMMARY_FIELDS = [
    "condition", "N_expected", "N_recorded", "N_scored", "missing_slots",
    "success_count", "success_rate", "mean_input_tokens", "mean_output_tokens",
    "mean_model_calls", "mean_wall_seconds", "n_with_usage", "n_with_output_usage",
    "status", "banner",
]

PAIRED_OUTCOMES = ("both_success", "base_only", "target_only", "both_fail",
                   "missing_base", "missing_target")


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _slot(task_id: Any, condition: Any) -> str:
    return f"{task_id}|{condition}"


def _config_by_condition(records: list[dict]) -> dict[str, list[str]]:
    sets: dict[str, set[str]] = {}
    for record in records:
        sets.setdefault(str(record.get("condition")), set()).add(str(record.get("config_sha256")))
    return {key: sorted(value) for key, value in sets.items()}


def validate_binding(
    scored: list[dict], *, split: str, conditions: list[str],
    expected_tasks: list[str], audit_report: dict,
) -> dict:
    """Re-derive integrity from the scored file; do not trust audit.complete.

    Returns a dict with ``problems`` (each ``{code, detail}``), identity fields
    and an effective ``complete`` that requires the audit to be genuinely bound
    to this exact scored set.
    """
    problems: list[dict] = []

    def add(code: str, detail: str) -> None:
        problems.append({"code": code, "detail": detail})

    # --- success must be a real boolean for every record ---
    bad_success = [_slot(r.get("task_id"), r.get("condition"))
                   for r in scored if not isinstance(r.get("success"), bool)]
    if bad_success:
        add("non_boolean_success", f"success is not bool for slots: {sorted(set(bad_success))}")

    # --- duplicates / split / conditions re-checked here ---
    seen: dict[str, int] = {}
    duplicates: list[str] = []
    for record in scored:
        key = _slot(record.get("task_id"), record.get("condition"))
        if key in seen:
            duplicates.append(key)
        else:
            seen[key] = 1
    if duplicates:
        add("duplicate_slot", f"duplicate scored slots: {sorted(set(duplicates))}")

    wrong_split = [_slot(r.get("task_id"), r.get("condition"))
                   for r in scored
                   if str(r.get("split", "")).upper() != str(split).upper()]
    if wrong_split:
        add("wrong_split", f"split != {split!r} for slots: {sorted(set(wrong_split))}")

    cond_mismatch = [_slot(r.get("task_id"), r.get("condition"))
                     for r in scored if r.get("condition") not in conditions]
    if cond_mismatch:
        add("condition_mismatch", f"condition not in {conditions}: {sorted(set(cond_mismatch))}")

    unknown_tasks = [_slot(r.get("task_id"), r.get("condition"))
                     for r in scored if r.get("task_id") not in set(expected_tasks)]
    if unknown_tasks:
        add("unknown_task", f"task_id not in expected set: {sorted(set(unknown_tasks))}")

    # Independent missing-slot check: do not rely on the audit's own set.
    expected_slots = {_slot(t, c) for t in expected_tasks for c in conditions}
    missing_slots = sorted(expected_slots - set(seen))
    if missing_slots:
        add("missing_slot", f"expected slots without a scored record: {missing_slots}")

    # --- fingerprint + slot-set + run/config binding to the audit ---
    scored_fingerprint = episode_fingerprint(scored)
    audit_fingerprint = audit_report.get("input_fingerprint")
    fingerprint_match = bool(audit_fingerprint) and audit_fingerprint == scored_fingerprint
    if not audit_fingerprint:
        add("audit_missing_fingerprint",
            "audit report has no input_fingerprint; cannot prove it matches this scored file")
    elif not fingerprint_match:
        add("audit_fingerprint_mismatch",
            "audit input_fingerprint does not match the scored file (stale audit or new data)")

    scored_slots = sorted(seen)
    audit_slots = audit_report.get("recorded_slots")
    slot_match = isinstance(audit_slots, list) and sorted(audit_slots) == scored_slots
    if not slot_match:
        add("audit_slot_mismatch",
            "audit recorded_slots do not equal the scored slot set")

    scored_run_ids = sorted({str(r.get("run_id")) for r in scored})
    audit_run_ids = sorted(audit_report.get("run_ids") or [])
    run_match = scored_run_ids == audit_run_ids
    if not run_match:
        add("run_identity_mismatch",
            f"run_ids scored={scored_run_ids} audit={audit_run_ids}")

    scored_config = _config_by_condition(scored)
    audit_config = {k: sorted(v) for k, v in (audit_report.get("config_by_condition") or {}).items()}
    config_match = scored_config == audit_config
    if not config_match:
        add("config_identity_mismatch",
            f"config_by_condition scored={scored_config} audit={audit_config}")

    audit_complete = bool(audit_report.get("complete"))
    if not audit_complete:
        add("audit_not_complete", f"audit status={audit_report.get('status')!r}")

    return {
        "problems": problems,
        "scored_fingerprint": scored_fingerprint,
        "audit_fingerprint": audit_fingerprint,
        "fingerprint_match": fingerprint_match,
        "slot_match": slot_match,
        "run_identity_match": run_match,
        "config_identity_match": config_match,
        "audit_complete": audit_complete,
        "complete": audit_complete and not problems,
    }


def build_per_task_rows(
    scored: list[dict], *, expected_tasks: list[str], synthetic: bool
) -> list[dict]:
    """One row per unique (task_id, condition); duplicates keep the first and are
    excluded by validate_binding, so a duplicate can never inflate success > 100%.
    """
    expected = set(expected_tasks)
    rows: list[dict] = []
    seen: set[str] = set()
    for record in scored:
        if not isinstance(record, dict):
            raise InputError("scored input contains a non-object line")
        task_id = record.get("task_id")
        if task_id not in expected:
            raise InputError(f"scored record for unexpected task_id={task_id!r}")
        key = _slot(task_id, record.get("condition"))
        if key in seen:
            continue  # already counted; validation reports the duplicate
        seen.add(key)
        success = record.get("success")
        rows.append({
            "task_id": task_id,
            "condition": record.get("condition"),
            # Keep non-bool success as None so it is never counted as True.
            "success": success if isinstance(success, bool) else None,
            "termination_reason": record.get("termination_reason"),
            "input_tokens": record.get("input_tokens"),
            "output_tokens": record.get("output_tokens"),
            "model_calls": record.get("model_calls"),
            "tool_attempts_executed": record.get("tool_attempts_executed"),
            "tool_attempts_blocked": record.get("tool_attempts_blocked"),
            "wall_seconds": record.get("wall_seconds"),
            "run_id": record.get("run_id"),
            "evidence_path": record.get("trajectory_path"),
            "scoring_reason": record.get("scoring_reason"),
            "synthetic": bool(synthetic or record.get("synthetic", False)),
            "in_expectation_set": True,
        })
    return rows


def compute_condition_summary(
    rows: list[dict], *, expected_tasks: list[str], conditions: list[str],
    audit_complete: bool, synthetic: bool,
) -> list[dict]:
    """Compute the main table.  Denominator is expected tasks, not recorded rows."""
    n_expected = len(expected_tasks)
    status = "INCOMPLETE" if not audit_complete else "COMPLETE"
    banner = SYNTHETIC_BANNER if synthetic else (INCOMPLETE_BANNER if not audit_complete else "")
    summaries: list[dict] = []
    for condition in conditions:
        group = [r for r in rows if r["condition"] == condition]
        successes = [r for r in group if r["success"] is True]
        scored = [r for r in group if isinstance(r["success"], bool)]
        input_rows = [r for r in group if isinstance(r.get("input_tokens"), int)
                      and not isinstance(r.get("input_tokens"), bool)]
        output_rows = [r for r in group if isinstance(r.get("output_tokens"), int)
                       and not isinstance(r.get("output_tokens"), bool)]
        success_rate = None
        if n_expected:
            # Conservative cap: even a malformed/duplicated input can never
            # report more than 100% success.
            success_rate = round(min(1.0, len(successes) / n_expected), 4)
        summaries.append({
            "condition": condition,
            "N_expected": n_expected,
            "N_recorded": len(group),
            "N_scored": len(scored),
            "missing_slots": max(0, n_expected - len(group)),
            "success_count": len(successes),
            "success_rate": success_rate,
            "mean_input_tokens": _mean([float(r["input_tokens"]) for r in input_rows]),
            "mean_output_tokens": _mean([float(r["output_tokens"]) for r in output_rows]),
            "mean_model_calls": _mean([float(r["model_calls"]) for r in group
                                       if isinstance(r.get("model_calls"), int)]),
            "mean_wall_seconds": _mean([float(r["wall_seconds"]) for r in group
                                        if isinstance(r.get("wall_seconds"), (int, float))]),
            "n_with_usage": len(input_rows),
            "n_with_output_usage": len(output_rows),
            "status": status,
            "banner": banner,
        })
    return summaries


def paired_comparison(
    rows: list[dict], *, base: str, target: str, expected_tasks: list[str],
    synthetic: bool, audit_complete: bool,
) -> dict:
    """Task-aligned C vs B / C vs D counts and token deltas (target - base)."""
    by_key = {(r["task_id"], r["condition"]): r for r in rows}
    outcome_rows: list[dict] = []
    counts = {outcome: 0 for outcome in PAIRED_OUTCOMES}

    for task_id in expected_tasks:
        b = by_key.get((task_id, base))
        t = by_key.get((task_id, target))
        if b is None:
            counts["missing_base"] += 1
            outcome_rows.append({"task_id": task_id, "outcome": "missing_base"})
            continue
        if t is None:
            counts["missing_target"] += 1
            outcome_rows.append({"task_id": task_id, "outcome": "missing_target"})
            continue
        b_ok, t_ok = b.get("success") is True, t.get("success") is True
        if b_ok and t_ok:
            outcome = "both_success"
        elif b_ok and not t_ok:
            outcome = "base_only"
        elif t_ok and not b_ok:
            outcome = "target_only"
        else:
            outcome = "both_fail"
        counts[outcome] += 1

        def delta(field: str):
            bv, tv = b.get(field), t.get(field)
            if isinstance(bv, int) and isinstance(tv, int):
                return tv - bv
            return None  # missing usage must not become 0

        outcome_rows.append({
            "task_id": task_id,
            "outcome": outcome,
            "base_success": b_ok,
            "target_success": t_ok,
            "input_tokens_delta": delta("input_tokens"),
            "output_tokens_delta": delta("output_tokens"),
        })

    if (base, target) == ("C", "D"):
        interpretation = (
            "C vs D holds format, order and budget fixed and changes only the "
            "filtering rule; differences are attributable to filtering."
        )
    elif (base, target) == ("C", "B"):
        interpretation = (
            "C vs B changes BOTH information organization/ordering AND filtering; "
            "do NOT attribute the whole effect to filtering. Use C vs D for that."
        )
    else:
        interpretation = "Descriptive pair only; no causal attribution assumed."

    banner = SYNTHETIC_BANNER if synthetic else (INCOMPLETE_BANNER if not audit_complete else "")
    return {
        "base": base,
        "target": target,
        "counts": counts,
        "rows": outcome_rows,
        "interpretation": interpretation,
        "status": "INCOMPLETE" if not audit_complete else "COMPLETE",
        "banner": banner,
    }


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: ("" if row.get(key) is None else row.get(key)) for key in fields})


def write_summary(
    out_dir: str | Path, *, rows: list[dict], condition_summaries: list[dict],
    paired: dict[str, dict], expected_tasks: list[str], audit_report: dict,
    binding: dict, complete: bool, synthetic: bool, conditions: list[str],
) -> dict[str, str]:
    """Write CSVs plus summary.json; ``complete`` is the *effective* status."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "per_task": str(out / "per_task.csv"),
        "condition_summary": str(out / "condition_summary.csv"),
        "paired_C_vs_B": str(out / "paired_C_vs_B.csv"),
        "paired_C_vs_D": str(out / "paired_C_vs_D.csv"),
        "summary_json": str(out / "summary.json"),
    }
    _write_csv(out / "per_task.csv", PER_TASK_FIELDS, rows)
    _write_csv(out / "condition_summary.csv", SUMMARY_FIELDS, condition_summaries)
    for name, pair in paired.items():
        _write_csv(
            out / f"paired_{pair['base']}_vs_{pair['target']}.csv",
            ["task_id", "outcome", "base_success", "target_success",
             "input_tokens_delta", "output_tokens_delta"],
            pair["rows"],
        )

    banner = SYNTHETIC_BANNER if synthetic else (INCOMPLETE_BANNER if not complete else "")
    payload = {
        "banner": banner,
        "synthetic": synthetic,
        # Effective completeness comes from binding, not audit.complete alone.
        "complete": bool(complete),
        "binding": binding,
        "split": audit_report.get("split"),
        "conditions": conditions,
        "expected_tasks": expected_tasks,
        "expected_slot_count": len(expected_tasks) * len(conditions),
        "N_recorded": len(rows),
        "condition_summary": condition_summaries,
        "paired": paired,
        "audit_status": audit_report.get("status"),
        "audit_errors": len(audit_report.get("errors", [])),
        "audit_warnings": len(audit_report.get("warnings", [])),
        "recorded_failures": audit_report.get("recorded_failures", []),
        "note": "Token means sum all model calls per task first, then average over tasks. "
                "Missing usage is excluded, never filled with 0. Failures stay in the denominator.",
    }
    write_json(out / "summary.json", payload)
    return paths
