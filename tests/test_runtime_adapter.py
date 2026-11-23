import unittest
from src.evaluation.runtime_adapter import adapt_episode, adapt_turn, prompt_signature_issues
from src.evaluation.errors import InputError


class RuntimeAdapterTests(unittest.TestCase):
    def test_signature_annotations_do_not_hide_wrong_names(self):
        self.assertEqual(prompt_signature_issues(
            'Signature: find_flights(destination: str, date: str) -> List[Dict]'),
            ['unadapted_find_flights_prompt'])
        self.assertEqual(prompt_signature_issues('Signature: reverse_string(text: str) -> str'),
                         ['unadapted_reverse_string_prompt'])
        self.assertEqual(prompt_signature_issues(
            'Signature: find_flights(from_location: str, to_location: str, date: str)'), [])

    def turn(self):
        return dict(turn_index=0, messages=[], generation_settings={"is_final_turn": False},
                    raw_text="Answer: 42", parsed={"type": "answer", "content": "42"},
                    action=None, tool_events=[], python_output=None, feedback_text=None,
                    feedback_metadata=None, input_tokens=20, output_tokens=4, elapsed_seconds=1)

    def test_interaction_answer_is_not_final_only(self):
        raw = self.turn()
        out = adapt_turn(raw)
        self.assertTrue(out["produced_final_answer"])
        self.assertFalse(out["is_final_answer_turn"])
        self.assertEqual(out["turn_index"], 1)
        self.assertEqual(raw["turn_index"], 0)

    def test_final_only_without_answer(self):
        raw = self.turn()
        raw["generation_settings"]["is_final_turn"] = True
        raw["parsed"] = {"type": "invalid"}
        out = adapt_turn(raw)
        self.assertFalse(out["produced_final_answer"])
        self.assertTrue(out["is_final_answer_turn"])

    def test_missing_or_unknown_fields_fail(self):
        raw = self.turn()
        del raw["input_tokens"]
        with self.assertRaises(InputError):
            adapt_turn(raw)
        raw = self.turn()
        raw["parsed"]["type"] = "unknown"
        with self.assertRaises(InputError):
            adapt_turn(raw)

    def test_manifest_mapping_and_identity(self):
        ep = dict(schema_version="1", run_id="r", task_id="t", split="DEV", condition="A",
                  config_sha256="h", trajectory_path="cluster/turns.jsonl")
        mf = {**ep, "team_commit": "commit", "model": {"revision": "revision"},
              "course_hashes": {"runtime_settings.json": "h"}}
        out = adapt_episode(ep, mf, trajectory_path="local/turns.jsonl")
        self.assertEqual(out["code_commit"], "commit")
        self.assertEqual(out["source_trajectory_path"], "cluster/turns.jsonl")
        mf["condition"] = "B"
        with self.assertRaises(InputError):
            adapt_episode(ep, mf, trajectory_path="x")
