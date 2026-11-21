#!/usr/bin/env python
"""Plot CLI. Run from the repository root:

    python scripts/plot_results.py --summary results/synthetic/summary.json \
        --out-dir results/synthetic/plots --allow-synthetic
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.errors import EvaluationError  # noqa: E402
from src.evaluation.plots import generate_plots  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate charts from summary.json.")
    parser.add_argument("--summary", required=True, help="summary.json from scripts/summarize.py")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--allow-synthetic", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = generate_plots(args.summary, args.out_dir, allow_synthetic=args.allow_synthetic)
        print(f"wrote {len(paths)} chart files:")
        for path in paths:
            print(f"  {path}")
        return 0
    except EvaluationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
