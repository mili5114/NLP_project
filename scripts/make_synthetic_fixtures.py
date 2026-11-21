#!/usr/bin/env python
"""Regenerate the synthetic fixtures used for C's end-to-end demo.

These are NOT experimental results.  They exist only to verify the offline
scorer -> auditor -> summarizer -> plotter chain and its failure detection.

The fixtures deliberately demonstrate BOTH final-answer concepts:
  * an interaction turn whose parseable (possibly wrong) output is the Answer
    (384-token interaction limit), and
  * a dedicated final-answer-only turn appended after budget exhaustion
    (128-token limit, no tools).

    python scripts/make_synthetic_fixtures.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "fixtures" / "evaluation"

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

# Slots that exhaust the interaction budget without a parseable answer and then
# use the dedicated final-answer-only turn.  Everything else answers inside an
# interaction turn.
FINAL_ONLY_SLOTS = {
    ("synthetic/task_beta", "A"),
    ("synthetic/task_gamma", "C"),
}

# interaction (input, output) and final-only (input, output) token usage.
USAGE = {
    "A": ((100, 10), (120, 5)),
    "B": ((110, 12), (130, 6)),
    "C": ((90, 9), (110, 4)),
    "D": ((95, 11), (115, 5)),
}
WALL = {"A": 1.0, "B": 1.2, "C": 0.9, "D": 1.1}
CONDITIONS = ["A", "B", "C", "D"]


def config_sha(condition: str) -> str:
    # Per-condition hashes are intentionally different: C must verify each
    # condition against its own hash, not require all four to be identical.
    return f"synthetic-config-{condition}-sha"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
                    encoding="utf-8", newline="\n")


def interaction_turn(index: int, usage: tuple[int, int], produced_answer: bool) -> dict:
    i_tok, o_tok = usage
    return {
        "turn_index": index,
        "is_final_answer_turn": False,
        "produced_final_answer": produced_answer,
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
        "input_tokens": i_tok,
        "output_tokens": o_tok,
        "wall_seconds": 0.5,
    }


def final_only_turn(index: int, usage: tuple[int, int]) -> dict:
    i_tok, o_tok = usage
    return {
        "turn_index": index,
        "is_final_answer_turn": True,
        "produced_final_answer": False,
        "messages": [{"role": "user", "content": "SYNTHETIC final-answer-only turn"}],
        "generation_settings": {"max_tokens": 128},
        "raw_model_text": "Answer: <no parseable answer>",
        "parsed_action": None,
        "action": None,
        "python_output": None,
        "events": [],
        "feedback": None,
        "feedback_metadata": {},
        "input_tokens": i_tok,
        "output_tokens": o_tok,
        "wall_seconds": 0.4,
    }


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
    write_json(FIXTURES / "condition_config_shas.json",
               {c: config_sha(c) for c in CONDITIONS})
    write_json(FIXTURES / "run_manifest.json", {
        "schema_version": "1.0",
        "synthetic": True,
        "run_id": "synthetic-e2e",
        "split": "SYNTHETIC",
        "condition_config_sha256": {c: config_sha(c) for c in CONDITIONS},
        "note": "SYNTHETIC — NOT EXPERIMENTAL RESULTS",
    })

    index_rows: list[dict] = []
    for task_id, _atype, _ref in TASKS:
        short = task_id.split("/")[-1]
        for condition in CONDITIONS:
            answer, termination = OUTCOMES[(task_id, condition)]
            interaction_usage, final_usage = USAGE[condition]
            uses_final_only = (task_id, condition) in FINAL_ONLY_SLOTS

            if uses_final_only:
                turns = [interaction_turn(1, interaction_usage, produced_answer=False),
                         final_only_turn(2, final_usage)]
            else:
                # Any parseable answer (correct or wrong) ends the task here.
                turns = [interaction_turn(1, interaction_usage, produced_answer=True)]

            in_total = sum(t["input_tokens"] for t in turns)
            out_total = sum(t["output_tokens"] for t in turns)
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
                "input_tokens": in_total,
                "output_tokens": out_total,
                "model_calls": len(turns),
                "tool_attempts_executed": 1,
                "tool_attempts_blocked": 0,
                "wall_seconds": WALL[condition],
                "trajectory_path": f"fixtures/evaluation/turns/{short}_{condition}.jsonl",
                "config_sha256": config_sha(condition),
            }
            ep_name = f"{short}_{condition}"
            write_json(FIXTURES / "episodes" / f"{ep_name}.json", ep)
            # Index paths are resolved relative to the index file's directory.
            index_rows.append({"episode_path": f"episodes/{ep_name}.json"})
            write_jsonl(FIXTURES / "turns" / f"{ep_name}.jsonl", turns)

    write_jsonl(FIXTURES / "index.jsonl", index_rows)
    print(f"wrote {len(index_rows)} synthetic episodes + trajectories under {FIXTURES}")


if __name__ == "__main__":
    main()
