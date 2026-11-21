#!/usr/bin/env python
"""Aggregation CLI. Run from the repository root:

    python scripts/summarize.py --scored results/synthetic/scored_all.jsonl \
        --audit results/synthetic/audit.json --split SYNTHETIC \
        --conditions A B C D --allow-synthetic \
        --synthetic-tasks fixtures/evaluation/tasks.json \
        --out-dir results/synthetic
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.aggregation import (  # noqa: E402
    build_per_task_rows,
    compute_condition_summary,
    paired_comparison,
    validate_binding,
    write_summary,
)
from src.evaluation.audit import load_manifest  # noqa: E402
from src.evaluation.errors import EvaluationError, InputError  # noqa: E402
from src.evaluation.io import (  # noqa: E402
    assert_synthetic_allowed,
    read_json,
    read_jsonl,
    resolve_synthetic_tasks,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build per-task table, condition main table and paired comparisons."
    )
    parser.add_argument("--scored", required=True, help="scored JSONL from scripts/score.py")
    parser.add_argument("--audit", required=True, help="audit JSON from scripts/audit_results.py")
    parser.add_argument("--split", required=True, help="DEV, EVAL, or SYNTHETIC")
    parser.add_argument("--conditions", nargs="+", required=True, choices=["A", "B", "C", "D"])
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--allow-synthetic", action="store_true")
    parser.add_argument("--synthetic-tasks", default=None,
                        help="explicit synthetic task list; never added to the official manifest")
    parser.add_argument("--manifest", default=str(REPO_ROOT / "configs/course/split_manifest.json"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        scored = read_jsonl(args.scored)
        assert_synthetic_allowed(scored, args.allow_synthetic, context="scored records")
        audit_report = read_json(args.audit)
        synthetic_tasks = resolve_synthetic_tasks(args.synthetic_tasks)
        if synthetic_tasks and not args.allow_synthetic:
            raise InputError("--synthetic-tasks requires --allow-synthetic")
        if audit_report.get("synthetic") and not args.allow_synthetic:
            raise InputError("audit report is synthetic; re-run with --allow-synthetic")

        if synthetic_tasks:
            expected_tasks = synthetic_tasks
        else:
            if not args.allow_synthetic and args.split not in ("DEV", "EVAL"):
                raise InputError(f"formal split must be DEV or EVAL, got {args.split!r}")
            expected_tasks = load_manifest(args.manifest)[args.split]

        synthetic = bool(synthetic_tasks or audit_report.get("synthetic"))
        # Re-derive integrity from the scored file; audit.complete is only one input.
        binding = validate_binding(
            scored, split=args.split, conditions=args.conditions,
            expected_tasks=expected_tasks, audit_report=audit_report,
        )
        complete = binding["complete"]

        rows = build_per_task_rows(scored, expected_tasks=expected_tasks, synthetic=synthetic)
        summaries = compute_condition_summary(
            rows, expected_tasks=expected_tasks, conditions=args.conditions,
            audit_complete=complete, synthetic=synthetic,
        )
        paired: dict[str, dict] = {}
        for base, target in (("C", "B"), ("C", "D")):
            if base in args.conditions and target in args.conditions:
                paired[f"{base}_vs_{target}"] = paired_comparison(
                    rows, base=base, target=target, expected_tasks=expected_tasks,
                    synthetic=synthetic, audit_complete=complete,
                )

        paths = write_summary(
            args.out_dir, rows=rows, condition_summaries=summaries, paired=paired,
            expected_tasks=expected_tasks, audit_report=audit_report,
            binding=binding, complete=complete, synthetic=synthetic,
            conditions=args.conditions,
        )
        for summary in summaries:
            print(
                f"{summary['condition']}: N={summary['N_recorded']}/{summary['N_expected']} "
                f"success={summary['success_count']} rate={summary['success_rate']} "
                f"in_tok={summary['mean_input_tokens']} out_tok={summary['mean_output_tokens']} "
                f"status={summary['status']}"
            )
        if binding["problems"]:
            print(f"BINDING PROBLEMS: {[p['code'] for p in binding['problems']]}", file=sys.stderr)
        print(f"effective_complete={complete} artifacts={paths}")
        return 0 if complete else 2
    except EvaluationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
