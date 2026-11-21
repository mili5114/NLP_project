#!/usr/bin/env python
"""Regenerate the synthetic fixtures used for C's end-to-end demo.

These are NOT experimental results.  They exist only to verify the offline
scorer -> auditor -> summarizer -> plotter chain and its failure detection.

    python scripts/make_synthetic_fixtures.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "fixtures" / "evaluation"
SYNTHETIC_CONFIG_SHA = "synthetic-config-sha-placeholder"

TASKS = [
    ("synthetic/task_alpha", "numeric", "42"),
    ("synthetic/task_beta", "string", "paris"),
    ("synthetic/task_gamma", "numeric", "100"),
]

# (answer, termination_reason) per task x condition.  None answer is a
# recorded experimental failure, never a dropped sample.
OUTCOMES = {
    ("synthetic/task_alpha", "A"): ("42", "first_parseable_answer"),
    ("synthetic/task_alpha", "B"): ("41", "first_parseable_answer"),
    ("synthetic/task_alpha", "C"): ("42", "first_parseable_answer"),
    ("synthetic/task_alpha", "D"): ("99", "first_parseable_answer"),
    ("synthetic/task_beta", "A"): (None, "no_answer"),
    ("synthetic/task_beta", "B"): ("paris", "first_parseable_answer"),
    ("synthetic/task_beta", "C"): (" paris ", "first_parseable_answer"),
    ("synthetic/task_beta", "D"): ("PARIS", "first_parseable_answer"),
    ("synthetic/task_gamma", "A"): ("100", "first_parseable_answer"),
    ("synthetic/task_gamma", "B"): ("100.5", "first_parseable_answer"),
    ("synthetic/task_gamma", "C"): (None, "budget_exhausted"),
    ("synthetic/task_gamma", "D"): ("100", "first_parseable_answer"),
}

# (turn1 input, turn1 output, final input, final output) per condition.
USAGE = {
    "A": (100, 10, 120, 5),
    "B": (110, 12, 130, 6),
    "C": (90, 9, 110, 4),
    "D": (95, 11, 115, 5),
}
WALL = {"A": 1.0, "B": 1.2, "C": 0.9, "D": 1.1}
CONDITIONS = ["A", "B", "C", "D"]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
                    encoding="utf-8", newline="\n")


def main() -> None:
    (FIXTURES / "episodes").mkdir(parents=True, exist_ok=True)
    (FIXTURES / "turns").mkdir(parents=True, exist_ok=True)

    write_json(FIXTURES / "tasks.json", [t[0] for t in TASKS])
    write_json(FIXTURES / "reference.json", {
        "synthetic": True,
        "offline_only": True,
        "references": [
            {"task_id": tid, "answer_type": atype, "reference": ref}
            for tid, atype, ref in TASKS
        ],
        "note": "SYNTHETIC — NOT EXPERIMENTAL RESULTS. Never pass into runtime or feedback.",
    })
    write_json(FIXTURES / "run_manifest.json", {
        "schema_version": "1.0",
        "synthetic": True,
        "run_id": "synthetic-e2e",
        "split": "SYNTHETIC",
        "config_sha256": SYNTHETIC_CONFIG_SHA,
        "note": "SYNTHETIC — NOT EXPERIMENTAL RESULTS",
    })

    index_rows: list[dict] = []
    for task_id, _atype, _ref in TASKS:
        short = task_id.split("/")[-1]
        for condition in CONDITIONS:
            answer, termination = OUTCOMES[(task_id, condition)]
            i1, o1, i2, o2 = USAGE[condition]
            ep = {
                "schema_version": "1.0",
                "synthetic": True,
                "run_id": "synthetic-e2e",
                "task_id": task_id,
                "split": "SYNTHETIC",
                "condition": condition,
                "status": "finished",
                "termination_reason": termination,
                "final_answer": answer,
                "input_tokens": i1 + i2,
                "output_tokens": o1 + o2,
                "model_calls": 2,
                "tool_attempts_executed": 1,
                "tool_attempts_blocked": 0,
                "wall_seconds": WALL[condition],
                "trajectory_path": f"fixtures/evaluation/turns/{short}_{condition}.jsonl",
                "config_sha256": SYNTHETIC_CONFIG_SHA,
            }
            ep_name = f"{short}_{condition}"
            write_json(FIXTURES / "episodes" / f"{ep_name}.json", ep)
            # Index paths are resolved relative to the index file's directory.
            index_rows.append({"episode_path": f"episodes/{ep_name}.json"})

            turns = [
                {
                    "turn_index": 1,
                    "is_final": False,
                    "messages": [{"role": "user", "content": "SYNTHETIC interaction turn"}],
                    "generation_settings": {"max_tokens": 384},
                    "raw_model_text": "Action: ```python\nprint('synthetic')\n```",
                    "parsed_action": "```python\nprint('synthetic')\n```",
                    "action": "python",
                    "python_output": "synthetic\n",
                    "events": [{
                        "index": 1, "tool": "example_tool", "args_repr": "()",
                        "kwargs_repr": "{}", "execution_status": "ok",
                        "result_repr": "synthetic", "error_repr": None,
                        "elapsed_seconds": 0.01,
                    }],
                    "feedback": "synthetic feedback " + "x" * 80,
                    "feedback_metadata": {"selected_event_indices": [1]},
                    "input_tokens": i1,
                    "output_tokens": o1,
                    "wall_seconds": 0.5,
                },
                {
                    "turn_index": 2,
                    "is_final": True,
                    "messages": [{"role": "user", "content": "SYNTHETIC final-answer turn"}],
                    "generation_settings": {"max_tokens": 128},
                    "raw_model_text": f"Answer: {answer if answer is not None else '<no answer>'}",
                    "parsed_action": None,
                    "action": None,
                    "python_output": None,
                    "events": [],
                    "feedback": None,
                    "feedback_metadata": {},
                    "input_tokens": i2,
                    "output_tokens": o2,
                    "wall_seconds": 0.4,
                },
            ]
            write_jsonl(FIXTURES / "turns" / f"{ep_name}.jsonl", turns)

    write_jsonl(FIXTURES / "index.jsonl", index_rows)
    print(f"wrote {len(index_rows)} synthetic episodes + trajectories under {FIXTURES}")


if __name__ == "__main__":
    main()
