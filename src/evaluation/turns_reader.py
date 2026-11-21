"""Adapter layer for turns.jsonl (the per-model-call log).

IMPORTANT — scope of this schema:
  The minimal field set below is defined by C for *synthetic offline testing*.
  It is NOT a claim that A's final runtime logger has committed to these names.
  Section 3 of docs/interfaces.md lists A's semantic fields but no per-line
  schema yet.  When A's real logs arrive, add one explicit field mapping here
  (a single adapter change), rather than silently accepting arbitrary keys or
  filling missing token usage with zeros.

Two separate final-answer concepts (course rules, Assignment_Attachment §2):
  * produced_final_answer — THIS call's parsed output is the final Answer.
    A normal interaction turn may produce it ("the first parseable Answer ends
    the task"); such a turn is still an interaction turn and is bounded by the
    384-token interaction limit.
  * is_final_answer_turn — the extra final-answer-only turn appended AFTER the
    interaction budget is exhausted. It executes no tools and is bounded by the
    128-token final-answer limit.
  Do not collapse these into one boolean: an interaction turn that answers is
  not subject to the 128-token final limit.

Synthetic turns minimal schema (one JSON object per model call; the call that
produces the final answer is also written as a row):
  turn_index: int >= 1                     # 1-based order within the episode
  is_final_answer_turn: bool               # dedicated final-only turn (128 cap)
  produced_final_answer: bool              # this call's output is the final Answer
  messages: list
  generation_settings: dict
  raw_model_text: str
  parsed_action: object
  action: str | null
  python_output: str | null
  events: list[dict]                       # tool events (ok/error/blocked)
  feedback: str | null                     # model-visible feedback text
  feedback_metadata: dict
  input_tokens: int >= 0                   # may be absent -> flagged, never 0
  output_tokens: int >= 0                  # may be absent -> flagged, never 0
  wall_seconds: number >= 0
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import InputError
from .io import read_jsonl

REQUIRED_TURN_FIELDS = (
    "turn_index",
    "is_final_answer_turn",
    "produced_final_answer",
    "messages",
    "raw_model_text",
    "events",
    "feedback",
)


def read_turns(path: str | Path) -> list[dict]:
    """Read and structurally validate a turns.jsonl file."""
    records = read_jsonl(path)
    for i, turn in enumerate(records, 1):
        missing = [f for f in REQUIRED_TURN_FIELDS if f not in turn]
        if missing:
            raise InputError(f"turns line {i} in {path} missing fields: {missing}")
        if not isinstance(turn["turn_index"], int) or isinstance(turn["turn_index"], bool):
            raise InputError(f"turns line {i} in {path} has invalid turn_index")
        for flag in ("is_final_answer_turn", "produced_final_answer"):
            if not isinstance(turn[flag], bool):
                raise InputError(f"turns line {i} in {path} has non-bool {flag}")
        if not isinstance(turn["events"], list):
            raise InputError(f"turns line {i} in {path} has non-list events")
    indices = [t["turn_index"] for t in records]
    if indices != sorted(indices):
        raise InputError(f"turns in {path} are not in increasing turn_index order")
    if len(set(indices)) != len(indices):
        raise InputError(f"turns in {path} contain duplicate turn_index values")
    return records


def summarize_turn_usage(turns: list[dict]) -> dict:
    """Sum token usage over every call; missing usage is reported, never zero-filled.

    Returns the two final-answer concepts separately:
      final_answer_turns — calls whose output is the final Answer (interaction
                           or final-only); normally exactly one when an answer exists.
      final_only_turns   — dedicated final-answer-only turns (128-token cap).
    """
    input_total = 0
    output_total = 0
    missing: list[int] = []
    invalid: list[dict] = []
    final_answer_turns: list[int] = []
    final_only_turns: list[int] = []

    for turn in turns:
        index = turn["turn_index"]
        if turn["produced_final_answer"]:
            final_answer_turns.append(index)
        if turn["is_final_answer_turn"]:
            final_only_turns.append(index)
        pair = {}
        for field in ("input_tokens", "output_tokens"):
            value = turn.get(field)
            if value is None:
                pair[field] = None
            elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
                invalid.append({"turn_index": index, "field": field, "value": value})
                pair[field] = None
            else:
                pair[field] = value
        if pair["input_tokens"] is None or pair["output_tokens"] is None:
            missing.append(index)
        else:
            input_total += pair["input_tokens"]
            output_total += pair["output_tokens"]

    return {
        "model_calls": len(turns),
        "input_tokens": input_total if not (missing or invalid) else None,
        "output_tokens": output_total if not (missing or invalid) else None,
        "missing_usage_turns": missing,
        "invalid_usage": invalid,
        "final_answer_turns": final_answer_turns,
        "final_only_turns": final_only_turns,
        "max_feedback_chars": max(
            (len(t["feedback"]) for t in turns if isinstance(t.get("feedback"), str)),
            default=0,
        ),
        "tool_events_per_turn": {str(t["turn_index"]): len(t["events"]) for t in turns},
    }
