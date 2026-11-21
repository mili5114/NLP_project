"""Charts generated from summary.json. No result values are hard-coded."""

from __future__ import annotations

from pathlib import Path

from .errors import InputError
from .io import read_json

# Use a non-interactive backend: plotting must work on a headless CI machine.
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BANNER_TEXT = "SYNTHETIC — NOT EXPERIMENTAL RESULTS"
INCOMPLETE_TEXT = "INCOMPLETE — NOT FINAL RESULTS"


def _finish(fig, path: Path, title: str, banner: str) -> None:
    fig.suptitle(title, fontsize=13, fontweight="bold", y=0.98)
    if banner:
        fig.text(0.5, 0.01, banner, ha="center", va="bottom", fontsize=10,
                 color="#9a3412", fontweight="bold")
        fig.subplots_adjust(bottom=0.16, top=0.88)
    else:
        fig.subplots_adjust(bottom=0.12, top=0.88)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    fig.savefig(path.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def generate_plots(summary_path: str | Path, out_dir: str | Path, *,
                   allow_synthetic: bool = False) -> list[str]:
    """Generate success/token/paired charts; return the list of written files."""
    summary = read_json(summary_path)
    if summary.get("synthetic") and not allow_synthetic:
        raise InputError("summary.json is synthetic; re-run with --allow-synthetic")
    banner = summary.get("banner") or ""
    if not summary.get("complete", False) and not banner:
        banner = INCOMPLETE_TEXT

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    condition_rows = summary.get("condition_summary", [])
    if not condition_rows:
        raise InputError("summary.json has no condition_summary rows")
    conditions = [str(r["condition"]) for r in condition_rows]

    # 1. Success rate by condition (denominator = expected tasks).
    fig, ax = plt.subplots(figsize=(7, 4.5))
    rates = [float(r["success_rate"] or 0) for r in condition_rows]
    successes = [int(r["success_count"]) for r in condition_rows]
    bars = ax.bar(conditions, rates, color=["#3b82f6", "#60a5fa", "#0ea5e9", "#7dd3fc"][:len(conditions)])
    ax.set_ylabel("Success rate (all expected tasks in denominator)")
    ax.set_title(f"Success rate (success count / expected tasks): {successes}")
    ax.set_ylim(0, 1.05)
    for bar, rate, count in zip(bars, rates, successes):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                f"{rate:.2f}\n(n={count})", ha="center", va="bottom", fontsize=9)
    _finish(fig, out / "success_rate.png", "Success rate by condition", banner)
    written += [str(out / "success_rate.png"), str(out / "success_rate.pdf")]

    # 2. Mean input / output tokens per task (sum over all calls first).
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    x_positions = range(len(conditions))
    width = 0.36
    in_tokens = [float(r["mean_input_tokens"] or 0) for r in condition_rows]
    out_tokens = [float(r["mean_output_tokens"] or 0) for r in condition_rows]
    ax.bar([x - width / 2 for x in x_positions], in_tokens, width,
           label="mean input tokens / task", color="#2563eb")
    ax.bar([x + width / 2 for x in x_positions], out_tokens, width,
           label="mean output tokens / task", color="#f59e0b")
    ax.set_xticks(list(x_positions), conditions)
    ax.set_ylabel("Tokens per task")
    ax.set_title("Token cost — sum all calls per task, then average over tasks")
    ax.legend(fontsize=9)
    _finish(fig, out / "token_cost.png", "Mean input / output tokens by condition", banner)
    written += [str(out / "token_cost.png"), str(out / "token_cost.pdf")]

    # 3. Paired outcomes.
    pairs = summary.get("paired", {})
    if pairs:
        fig, axes = plt.subplots(1, len(pairs), figsize=(6 * len(pairs), 4.5), squeeze=False)
        outcome_labels = ["both_success", "base_only", "target_only", "both_fail",
                          "missing_base", "missing_target"]
        colors = ["#16a34a", "#f97316", "#8b5cf6", "#9ca3af", "#dc2626", "#fbbf24"]
        for ax, (name, pair) in zip(axes[0], pairs.items()):
            counts = [int(pair["counts"].get(key, 0)) for key in outcome_labels]
            ax.bar(range(len(counts)), counts, color=colors)
            ax.set_xticks(range(len(counts)), [k.replace("_", "\n") for k in outcome_labels], fontsize=8)
            ax.set_ylabel("Number of tasks")
            ax.set_title(f"{pair['base']} vs {pair['target']} (base vs target)")
        _finish(fig, out / "paired_outcomes.png", "Paired task outcomes", banner)
        written += [str(out / "paired_outcomes.png"), str(out / "paired_outcomes.pdf")]

    return written
