import json
import unittest
from pathlib import Path

from src.feedback.dispatcher import build_feedback


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "feedback_input.json"


class SelectiveFeedbackTest(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.settings = {"feedback_characters": 2000, **self.fixture["method_config"]}

    def render(self, condition, stdout, events=None):
        return build_feedback(
            python_output=stdout,
            events=self.fixture["events"] if events is None else events,
            condition=condition,
            settings=self.settings,
        )

    def test_fixture_filters_only_the_duplicate(self):
        stdout = self.fixture["python_output"]
        c = self.render("C", stdout)
        d = self.render("D", stdout)
        for key, value in self.fixture["expected_selection_before_rendering"].items():
            self.assertEqual(c["metadata"][key], value)
        self.assertEqual(d["metadata"]["selected_event_indices"], [1, 2, 3])
        self.assertEqual(c["metadata"]["fully_visible_event_indices"], [2, 3])
        self.assertTrue(c["metadata"]["visible_feedback_changed"])
        self.assertEqual(c["metadata"]["chars_before_filtering"], len(d["text"]))
        self.assertEqual(c["metadata"]["chars_after_filtering"], len(c["text"]))
        self.assertEqual(
            c["text"].splitlines(),
            [line for line in d["text"].splitlines() if not line.startswith("[1] example_tool")],
        )

    def test_hidden_result_and_truncated_python_output(self):
        value = self.fixture["events"][0]["result_repr"]
        for stdout in ("", "x" * 1000 + value):
            with self.subTest(stdout_length=len(stdout)):
                c = self.render("C", stdout)
                self.assertEqual(c["text"], self.render("D", stdout)["text"])
                self.assertEqual(c["metadata"]["rule_trigger_count"], 0)
        self.assertTrue(c["metadata"]["python_truncated"])

    def test_whitespace_normalizes_but_partial_and_short_values_remain(self):
        first = self.fixture["events"][0]
        stdout = "The synthetic\treturn value is already\nprinted. 1234"
        events = [first, {**first, "index": 2, "result_repr": "1234"},
                  {**first, "index": 3, "result_repr": "The synthetic return value is incomplete"}]
        c = self.render("C", stdout, events)
        self.assertEqual(c["metadata"]["omitted_event_indices"], [1])
        self.assertEqual(c["metadata"]["selected_event_indices"], [2, 3])

    def test_error_blocked_and_clipped_return_stay_in_trace(self):
        marker = "\n[Output Truncated]"
        first = self.fixture["events"][0]
        events = [{**first, "execution_status": "error", "error_repr": "example error"},
                  {**first, "index": 2, "execution_status": "blocked", "error_repr": "limit"},
                  {**first, "index": 3, "result_repr": first["result_repr"] + marker}]
        c = self.render("C", first["result_repr"] + marker, events)
        self.assertEqual(c["metadata"]["selected_event_indices"], [1, 2, 3])

    def test_trace_limit_and_trigger_that_does_not_change_the_visible_text(self):
        first = self.fixture["events"][0]
        events = [{**first, "result_repr": "x" * 2000}, {**first, "index": 2}]
        stdout = self.fixture["python_output"]
        c = self.render("C", stdout, events)
        self.assertEqual(c["text"], self.render("D", stdout, events)["text"])
        self.assertEqual(len(c["text"]), 2000)
        self.assertEqual(c["metadata"]["rule_trigger_count"], 1)
        self.assertFalse(c["metadata"]["visible_feedback_changed"])
        self.assertTrue(c["metadata"]["trace_truncated"])
        self.assertEqual(c["metadata"]["fully_visible_event_indices"], [])

    def test_all_filtered_omits_trace_header(self):
        stdout = self.fixture["python_output"]
        self.assertEqual(self.render("C", stdout, self.fixture["events"][:1])["text"],
                         "Python output:\n" + stdout)

    def test_candidate_threshold_changes_c_selection(self):
        stdout = self.fixture["python_output"]
        d = self.render("D", stdout)
        self.settings["min_match_chars"] = 48
        self.assertEqual(self.render("C", stdout)["text"], d["text"])
        self.assertEqual(self.render("D", stdout)["text"], d["text"])
