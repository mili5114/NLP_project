import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from src.evaluation.errors import InputError

spec = importlib.util.spec_from_file_location(
    "prepare_records", Path(__file__).resolve().parents[1] / "scripts/prepare_runtime_records.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PrepareRecordsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "runs/DEV"
        self.out = self.root / "derived"
        self.put("configs/course/split_manifest.json", {"DEV": ["group/task"], "EVAL": []})
        self.put("configs/course/runtime_settings.json",
                 {"initial_contract": "contract", "limits": {"total_generated_tokens": 3072}})
        self.ep = dict(schema_version="1", synthetic=False, run_id="r", task_id="group/task",
                       split="DEV", condition="A", config_sha256="h", input_tokens=10,
                       output_tokens=2, model_calls=1, final_answer="42", termination_reason="answer")
        self.base = "runs/DEV/A/task/"
        self.put(self.base + "episode.json", self.ep)
        self.put(self.base + "manifest.json", {**self.ep, "team_commit": "commit",
                 "model": {"revision": "revision"}, "course_hashes": {"runtime_settings.json": "h"}})
        turn = dict(turn_index=0, messages=[{"role": "system", "content": "contract"}],
                    generation_settings={"is_final_turn": False}, raw_text="Answer: 42",
                    parsed={"type": "answer"}, action=None, tool_events=[], python_output=None,
                    feedback_text=None, feedback_metadata=None, input_tokens=10, output_tokens=2,
                    elapsed_seconds=1)
        self.put(self.base + "turns.jsonl", turn)

    def put(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")

    def test_real_mapping_missing_slot_and_raw_unchanged(self):
        path = self.source / "A/task/episode.json"
        before = path.read_bytes()
        report = module.prepare(self.root, self.source, self.out)
        self.assertEqual(report["missing"], [["group/task", "B"]])
        self.assertFalse(report["formal_protocol_certified"])
        self.assertEqual(path.read_bytes(), before)
        derived = json.loads((self.out / "A/task/episode.json").read_text())
        self.assertEqual(derived["code_commit"], "commit")
        self.assertEqual(len(derived["source_sha256"]), 3)
        with self.assertRaises(InputError):
            module.prepare(self.root, self.source, self.out)

    def test_token_mismatch_fails(self):
        self.ep["input_tokens"] = 11
        self.put(self.base + "episode.json", self.ep)
        with self.assertRaises(InputError):
            module.prepare(self.root, self.source, self.out)

    def test_synthetic_rejected(self):
        self.ep["synthetic"] = True
        self.put(self.base + "episode.json", self.ep)
        with self.assertRaises(InputError):
            module.prepare(self.root, self.source, self.out)

    def test_source_output_overlap_rejected(self):
        with self.assertRaises(InputError):
            module.prepare(self.root, self.source, self.source / "derived")
