#!/usr/bin/env python
"""Completeness audit CLI. Run from the repository root:

    python scripts/audit_results.py --episodes fixtures/evaluation/index.jsonl \
        --split SYNTHETIC --conditions A B C D --allow-synthetic \
        --synthetic-tasks fixtures/evaluation/tasks.json \
        --out results/synthetic/audit.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.audit import audit_episodes, load_manifest  # noqa: E402
from src.evaluation.errors import EvaluationError  # noqa: E402
from src.evaluation.io import (  # noqa: E402
    assert_synthetic_allowed,
    load_episodes,
    read_json,
    resolve_synthetic_tasks,
    write_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit episode/trajectory completeness against the official split manifest."
    )
    parser.add_argument("--episodes", required=True, help="episode JSON / JSONL index / directory")
    parser.add_argument("--split", required=True, help="DEV, EVAL, or SYNTHETIC (with --allow-synthetic)")
    parser.add_argument("--conditions", nargs="+", required=True, choices=["A", "B", "C", "D"])
    parser.add_argument("--out", required=True, help="audit report JSON path")
    parser.add_argument("--allow-synthetic", action="store_true")
    parser.add_argument("--synthetic-tasks", default=None,
                        help="explicit JSON list (or comma-separated ids) for synthetic audits")
    parser.add_argument("--manifest", default=str(REPO_ROOT / "configs/course/split_manifest.json"))
    parser.add_argument("--settings", default=str(REPO_ROOT / "configs/course/runtime_settings.json"))
    parser.add_argument("--trajectory-root", default=str(REPO_ROOT),
                        help="base dir for relative trajectory_path values")
    parser.add_argument("--expected-config-sha", default=None)
    parser.add_argument("--expected-code-commit", default=None)
    parser.add_argument("--expected-model-revision", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        episodes, sources = load_episodes(args.episodes)
        assert_synthetic_allowed(episodes, args.allow_synthetic, context="episodes")
        synthetic_tasks = resolve_synthetic_tasks(args.synthetic_tasks)
        if args.allow_synthetic and not synthetic_tasks:
            raise EvaluationError(
                "synthetic audits require an explicit --synthetic-tasks list "
                "(synthetic tasks are never added to the official manifest)"
            )

        manifest = None if synthetic_tasks else load_manifest(args.manifest)
        settings = read_json(args.settings)
        report = audit_episodes(
            episodes,
            split=args.split,
            conditions=args.conditions,
            manifest=manifest,
            settings=settings,
            allow_synthetic=args.allow_synthetic,
            synthetic_tasks=synthetic_tasks,
            trajectory_root=args.trajectory_root,
            episode_sources=sources,
            expected_config_sha=args.expected_config_sha,
            expected_code_commit=args.expected_code_commit,
            expected_model_revision=args.expected_model_revision,
        )
        write_json(args.out, report)
        print(
            f"audit status={report['status']} expected={report['expected_slot_count']} "
            f"recorded={report['recorded_slot_count']} errors={len(report['errors'])} "
            f"warnings={len(report['warnings'])} synthetic={report['synthetic']} out={args.out}"
        )
        return 0 if report["complete"] else 1
    except EvaluationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
