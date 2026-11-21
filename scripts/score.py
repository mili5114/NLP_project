#!/usr/bin/env python
"""Offline scorer CLI. Run from the repository root:

    python scripts/score.py --episodes fixtures/episode.synthetic.json \
        --references fixtures/reference.synthetic.json \
        --out results/synthetic/scored.jsonl --allow-synthetic
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.errors import EvaluationError, InputError  # noqa: E402
from src.evaluation.io import (  # noqa: E402
    assert_synthetic_allowed,
    load_episodes,
    load_reference_index,
    write_jsonl,
)
from src.evaluation.scoring import score_episode  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Score offline CodeAct episodes against a fixed reference file."
    )
    parser.add_argument("--episodes", required=True,
                        help="episode JSON, JSONL index, or directory of episode JSON")
    parser.add_argument("--references", required=True,
                        help="offline reference JSON (task_id, answer_type, reference)")
    parser.add_argument("--out", required=True, help="output scored JSONL (never overwrote online logs)")
    parser.add_argument("--allow-synthetic", action="store_true",
                        help="required when any episode or the reference file is synthetic")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        references = load_reference_index(args.references)
        assert_synthetic_allowed(
            [{"synthetic": references.synthetic, "split": "SYNTHETIC" if references.synthetic else "OFFLINE"}],
            args.allow_synthetic,
            context="reference file",
        )

        episodes, sources = load_episodes(args.episodes)
        any_synthetic = assert_synthetic_allowed(episodes, args.allow_synthetic, context="episodes")

        scored = []
        for episode, source in zip(episodes, sources):
            task_id = episode.get("task_id")
            if task_id not in references.index:
                raise InputError(
                    f"missing reference for task_id={task_id!r} (episode from {source})"
                )
            ref = references.index[task_id]
            scored.append(
                score_episode(
                    episode,
                    reference=ref["reference"],
                    answer_type=ref["answer_type"],
                )
            )

        write_jsonl(args.out, scored)
        success_count = sum(1 for record in scored if record.get("success") is True)
        print(
            f"scored={len(scored)} success={success_count} "
            f"synthetic={any_synthetic or references.synthetic} out={args.out}"
        )
        return 0
    except EvaluationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
