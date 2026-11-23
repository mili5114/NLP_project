"""Explicit adapter for A's schema_version=1 records; never modifies raw logs."""
from __future__ import annotations

import re

from .errors import InputError


def prompt_signature_issues(text: str) -> list[str]:
    """Check parameter names in explicit Signature lines, including annotations."""
    expected = {"find_flights": ["from_location", "to_location", "date"],
                "reverse_string": ["s"], "string_length": ["s"]}
    issues = []
    for name, parameters in expected.items():
        for match in re.finditer(r"Signature:\s*" + name + r"\(([^)]*)\)", text):
            actual = [p.split(":", 1)[0].split("=", 1)[0].strip()
                      for p in match[1].split(",") if p.strip()]
            if actual != parameters:
                issues.append(f"unadapted_{name}_prompt")
    return sorted(set(issues))


def adapt_turn(turn: dict) -> dict:
    required = ("turn_index", "messages", "generation_settings", "raw_text", "parsed",
                "action", "tool_events", "python_output", "feedback_text",
                "feedback_metadata", "input_tokens", "output_tokens", "elapsed_seconds")
    missing = [key for key in required if key not in turn]
    if missing:
        raise InputError(f"runtime v1 turn missing {missing}")
    index = turn["turn_index"]
    settings, parsed = turn["generation_settings"], turn["parsed"]
    if type(index) is not int or index < 0:
        raise InputError("runtime v1 turn_index must be a nonnegative integer")
    if not isinstance(settings, dict) or type(settings.get("is_final_turn")) is not bool:
        raise InputError("runtime v1 requires boolean generation_settings.is_final_turn")
    if not isinstance(parsed, dict) or parsed.get("type") not in {"answer", "action", "invalid"}:
        raise InputError("runtime v1 has unknown parsed type")
    return {
        **turn,
        "turn_index": index + 1,
        "source_turn_index": index,
        "is_final_answer_turn": settings["is_final_turn"],
        "produced_final_answer": parsed["type"] == "answer",
        "raw_model_text": turn["raw_text"],
        "events": turn["tool_events"],
        "feedback": turn["feedback_text"],
        "wall_seconds": turn["elapsed_seconds"],
    }


def adapt_episode(episode: dict, manifest: dict, *, trajectory_path: str) -> dict:
    if episode.get("schema_version") != "1" or manifest.get("schema_version") != "1":
        raise InputError("adapter supports only A's runtime schema_version=1")
    for key in ("run_id", "task_id", "split", "condition"):
        if not episode.get(key) or episode.get(key) != manifest.get(key):
            raise InputError(f"episode/manifest identity mismatch: {key}")
    commit = manifest.get("team_commit")
    model = manifest.get("model", {})
    if not commit or not model.get("revision"):
        raise InputError("manifest missing team_commit or model.revision")
    if episode.get("config_sha256") != manifest.get("course_hashes", {}).get("runtime_settings.json"):
        raise InputError("episode runtime settings hash differs from manifest")
    return {**episode, "trajectory_path": trajectory_path,
            "code_commit": commit, "model_revision": model["revision"],
            "source_trajectory_path": episode.get("trajectory_path"),
            "config_hash_scope": "course runtime_settings.json only; not full condition freeze"}
