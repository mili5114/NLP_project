import unittest
from src.evaluation.tool_audit import audit_tool_attempts


def turn(statuses, index=1):
    return {"turn_index": index, "events": [
        {"index": i, "execution_status": s, "result_repr": None}
        for i, s in enumerate(statuses, 1)]}


class ToolAuditTests(unittest.TestCase):
    limits = {"tool_attempts_per_action": 4, "tool_attempts_per_task": 32}

    def codes(self, turns, limits=None):
        return [i["code"] for i in audit_tool_attempts(turns, limits or self.limits)["issues"]]

    def test_fifth_attempt_blocked_is_valid(self):
        result = audit_tool_attempts([turn(["ok"] * 4 + ["blocked"] * 3)], self.limits)
        self.assertEqual(result["issues"], [])
        self.assertEqual((result["attempted"], result["executed"], result["blocked"]), (7, 4, 3))

    def test_error_counts_as_executed(self):
        result = audit_tool_attempts([turn(["error"] * 4 + ["blocked"])], self.limits)
        self.assertEqual(result["executed"], 4)
        self.assertEqual(result["issues"], [])

    def test_executed_fifth_attempt_rejected(self):
        self.assertIn("unblocked_over_budget_tool", self.codes([turn(["ok"] * 5)]))

    def test_task_limit_preserves_action_reset(self):
        turns = [turn(["ok"] * 4, i) for i in range(1, 9)] + [turn(["blocked"], 9)]
        self.assertEqual(self.codes(turns), [])
        turns[-1] = turn(["error"], 9)
        self.assertIn("unblocked_over_budget_tool", self.codes(turns))

    def test_blocked_attempts_also_consume_task_attempts(self):
        limits = {"tool_attempts_per_action": 2, "tool_attempts_per_task": 4}
        turns = [turn(["ok", "ok", "blocked"]), turn(["ok", "blocked"], 2)]
        self.assertEqual(self.codes(turns, limits), [])
        turns[-1] = turn(["ok", "ok"], 2)
        self.assertIn("unblocked_over_budget_tool", self.codes(turns, limits))

    def test_premature_block_rejected(self):
        self.assertIn("premature_tool_block", self.codes([turn(["blocked"])]))

    def test_invalid_event_and_index_rejected(self):
        value = turn(["ok"])
        value["events"][0]["index"] = 2
        self.assertIn("tool_event_index_mismatch", self.codes([value]))
        value["events"] = [None, {"index": 2, "execution_status": "unknown"}]
        self.assertEqual(self.codes([value]), ["invalid_tool_event", "invalid_tool_status"])

    def test_blocked_result_not_allowed(self):
        value = turn(["ok"] * 4 + ["blocked"])
        value["events"][-1]["result_repr"] = "unexpected"
        self.assertIn("blocked_tool_has_result", self.codes([value]))
