"""Prepare immutable-derived DEV records; inspect structure without answer keys.

EVAL is intentionally not selected by this entry point: early EVAL baselines must
not drive B's method selection. This is not a formal protocol certification.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.evaluation.io import read_json, read_jsonl, write_json, write_jsonl
from src.evaluation.errors import EvaluationError, InputError
from src.evaluation.runtime_adapter import adapt_episode, adapt_turn, prompt_signature_issues
from src.evaluation.tool_audit import audit_tool_attempts


def prepare(root: Path, source: Path, out: Path) -> dict:
    root, source, out = root.resolve(), source.resolve(), out.resolve()
    if source == out or source in out.parents or out in source.parents:
        raise InputError("source and output must be separate directory trees")
    if out.exists():
        raise InputError("output exists: choose a fresh directory to preserve prior results")
    tasks = read_json(root / "configs/course/split_manifest.json")["DEV"]
    settings = read_json(root / "configs/course/runtime_settings.json")
    rows, excluded, findings, seen = [], [], [], set()
    tool_totals = Counter()
    for path in sorted(source.rglob("episode.json")):
        if "pilot_14051965" in path.parts:
            excluded.append({"path": str(path), "reason": "documented pre-warmup pilot"})
            continue
        ep, mf = read_json(path), read_json(path.parent / "manifest.json")
        if ep.get("synthetic") is not False:
            raise InputError(f"real runtime preparation requires synthetic=false: {path}")
        if ep.get("split") != "DEV" or ep.get("condition") not in {"A", "B"}:
            raise InputError(f"unexpected source record {path}")
        key = (ep["task_id"], ep["condition"])
        if ep["task_id"] not in tasks or key in seen:
            raise InputError(f"unknown or duplicate task-condition: {key}")
        seen.add(key)
        turns_path = path.parent / "turns.jsonl"
        raw = read_jsonl(turns_path)
        if [t.get("turn_index") for t in raw] != list(range(len(raw))):
            raise InputError(f"noncontiguous runtime turn sequence {turns_path}")
        turns = [adapt_turn(t) for t in raw]
        tools = audit_tool_attempts(turns, settings["limits"])
        for key in ("attempted", "executed", "blocked"):
            tool_totals[key] += tools[key]
        for problem in tools["issues"]:
            findings.append({"task_id": ep["task_id"], "condition": ep["condition"],
                             **problem, "owner": "A"})
        for field, key in (("tool_attempts_executed", "executed"),
                           ("tool_attempts_blocked", "blocked")):
            if type(ep.get(field)) is not int or ep[field] != tools[key]:
                raise InputError(f"inconsistent {field} at {path}")
        for metric in ("input_tokens", "output_tokens"):
            values = [t.get(metric) for t in turns]
            if any(type(v) is not int or v < 0 for v in values) or sum(values) != ep.get(metric):
                raise InputError(f"invalid or inconsistent {metric} at {path}")
        if ep.get("model_calls") != len(turns):
            raise InputError(f"inconsistent model_calls at {path}")
        answered = [i for i, t in enumerate(turns) if t["produced_final_answer"]]
        if ((ep.get("final_answer") is not None) != bool(answered)
                or len(answered) > 1 or (answered and answered[0] != len(turns) - 1)):
            raise InputError(f"first-answer termination inconsistent at {path}")
        for code in sorted({code for t in turns for m in t["messages"]
                            if m.get("role") == "system"
                            for code in prompt_signature_issues(m.get("content", ""))}):
            findings.append({"task_id": ep["task_id"], "condition": ep["condition"],
                             "code": code, "owner": "A"})
        if (ep.get("final_answer") is None and turns
                and not any(t["is_final_answer_turn"] for t in turns)
                and ep["termination_reason"] == "token_budget_exhausted"
                and settings["limits"]["total_generated_tokens"] - ep["output_tokens"] > 0):
            findings.append({"task_id": ep["task_id"], "condition": ep["condition"],
                             "code": "reserved_final_tokens_not_used_requires_review", "owner": "A"})
        if turns and settings["initial_contract"] not in turns[0]["messages"][0]["content"]:
            findings.append({"task_id": ep["task_id"], "condition": ep["condition"],
                             "code": "initial_contract_not_in_first_system_message", "owner": "A"})
        derived = out / ep["condition"] / path.parent.name
        normalized = adapt_episode(ep, mf, trajectory_path=str(derived / "turns.jsonl"))
        normalized["source_episode_path"] = str(path.relative_to(root))
        hashes = {name: hashlib.sha256((path.parent / name).read_bytes()).hexdigest()
                  for name in ("episode.json", "manifest.json", "turns.jsonl")}
        normalized["source_sha256"] = hashes
        write_jsonl(derived / "turns.jsonl", turns)
        write_json(derived / "episode.json", normalized)
        rows.append({"episode_path": str((derived / "episode.json").relative_to(out))})
    expected = {(t, c) for t in tasks for c in ("A", "B")}
    report = {
        "scope": "DEV structure and adapter checks only; no reference answers or scoring",
        "formal_protocol_certified": False,
        "expected": len(expected), "recorded": len(seen),
        "missing": [list(k) for k in sorted(expected - seen)], "excluded": excluded,
        "findings": findings, "finding_counts": dict(Counter(f["code"] for f in findings)),
        "tool_totals": dict(tool_totals),
        "limitations": ["EVAL records are not processed", "B frozen package not present",
                        "config_sha256 describes course settings, not full condition configuration",
                        "Tool audit validates recorded events, not unlogged execution or side effects",
                        "Context, timing and answer-isolation compliance need separate validation"],
    }
    write_jsonl(out / "index.jsonl", rows)
    write_json(out / "preflight.json", report)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", default=str(ROOT / "runs/dev_baselines/DEV"))
    p.add_argument("--out-dir", required=True)
    args = p.parse_args()
    try:
        report = prepare(ROOT, Path(args.source), Path(args.out_dir))
        print({k: report[k] for k in ("expected", "recorded", "missing", "finding_counts")})
        sys.exit(1 if report["missing"] or report["findings"] else 0)
    except (EvaluationError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
