"""hooks/check-spawn: the PreToolUse hook that enforces the spawn table (R4).

An `Agent(type)` list in frontmatter binds only a main-thread agent, so a lead
running as a subagent could spawn anything (seen live: impl-lead spawned
teamflow:researcher). The hook checks the caller's agent_type against
tool_input.subagent_type at every depth.

    python3 -m unittest discover -s tests
"""

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "check-spawn"

REVIEWERS = ["architect", "security", "quality", "docs", "simplicity"]
ALLOWED = {
    "manager": ["research-lead", "impl-lead", "review-lead"],
    "research-lead": ["researcher"],
    "impl-lead": ["implementer", "code-reviewer"],
    "review-lead": [f"{r}-reviewer" for r in REVIEWERS] + ["code-reviewer"],
}
EVERY_TYPE = {t for types in ALLOWED.values() for t in types} | {
    "manager", "research-lead", "impl-lead", "review-lead", "implementer",
}


def run(stdin):
    """(exit code, stdout, stderr) of the hook for raw stdin text."""
    p = subprocess.run([str(HOOK)], input=stdin, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def spawn(caller, subagent_type="__absent__"):
    event = {"hook_event_name": "PreToolUse", "tool_name": "Agent", "tool_input": {}}
    if subagent_type != "__absent__":
        event["tool_input"]["subagent_type"] = subagent_type
    if caller is not None:
        event["agent_type"] = caller
    return run(json.dumps(event))


class SpawnHook(unittest.TestCase):
    def assertNoDecision(self, result):
        self.assertEqual(result, (0, "", ""))

    def assertDenied(self, result, *mentions):
        code, out, err = result
        self.assertEqual(code, 0, err)
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(decision["hookEventName"], "PreToolUse")
        self.assertEqual(decision["permissionDecision"], "deny")
        for text in mentions:
            self.assertIn(text, decision["permissionDecisionReason"])

    def test_every_pair_in_the_table_gets_no_decision(self):
        for caller, types in ALLOWED.items():
            for t in types:
                with self.subTest(caller=caller, spawns=t):
                    self.assertNoDecision(spawn(f"teamflow:{caller}", f"teamflow:{t}"))

    def test_every_pair_outside_the_table_is_denied(self):
        for caller in [*ALLOWED, "implementer", "researcher", "code-reviewer"]:
            for t in sorted(EVERY_TYPE):
                if t in ALLOWED.get(caller, []):
                    continue
                with self.subTest(caller=caller, spawns=t):
                    self.assertDenied(spawn(f"teamflow:{caller}", f"teamflow:{t}"),
                                      f"teamflow:{caller}", f"teamflow:{t}")

    def test_named_denials(self):
        self.assertDenied(spawn("teamflow:review-lead", "teamflow:implementer"))
        self.assertDenied(spawn("teamflow:implementer", "teamflow:researcher"))
        self.assertDenied(spawn("teamflow:manager", "teamflow:implementer"))

    def test_denial_names_what_the_caller_may_spawn(self):
        self.assertDenied(spawn("teamflow:impl-lead", "teamflow:researcher"),
                          "teamflow:implementer", "teamflow:code-reviewer")

    def test_missing_or_non_string_subagent_type_is_denied(self):
        self.assertDenied(spawn("teamflow:research-lead"), "teamflow:research-lead")
        for bad in (None, 7, ["teamflow:researcher"], {"a": 1}):
            with self.subTest(subagent_type=bad):
                self.assertDenied(spawn("teamflow:research-lead", bad))

    def test_recorded_main_thread_spawn_gets_no_decision(self):
        self.assertNoDecision(run(
            '{"hook_event_name": "PreToolUse", "tool_name": "Agent", '
            '"tool_input": {"subagent_type": "teamflow:impl-lead"}}'))

    def test_recorded_impl_lead_to_implementer_gets_no_decision(self):
        self.assertNoDecision(run(
            '{"hook_event_name": "PreToolUse", "tool_name": "Agent", '
            '"tool_input": {"subagent_type": "teamflow:implementer"}, '
            '"agent_type": "teamflow:impl-lead"}'))

    def test_recorded_impl_lead_to_researcher_is_denied(self):
        self.assertDenied(run(
            '{"hook_event_name": "PreToolUse", "tool_name": "Agent", '
            '"tool_input": {"subagent_type": "teamflow:researcher"}, '
            '"agent_type": "teamflow:impl-lead"}'))

    def test_non_teamflow_caller_gets_no_decision(self):
        self.assertNoDecision(spawn("other:agent", "teamflow:implementer"))
        self.assertNoDecision(spawn("general-purpose", "anything"))
        self.assertNoDecision(spawn("", "teamflow:implementer"))

    def test_missing_agent_type_gets_no_decision(self):
        self.assertNoDecision(spawn(None, "teamflow:implementer"))

    def test_non_string_agent_type_gets_no_decision(self):
        self.assertNoDecision(run(json.dumps(
            {"tool_input": {"subagent_type": "x"}, "agent_type": 5})))

    def test_unparseable_input_blocks_with_exit_2(self):
        for text in ("", "not json", "[1, 2]", '"teamflow:manager"', "null"):
            with self.subTest(stdin=text):
                code, out, err = run(text)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertIn("check-spawn", err)

    def test_non_object_tool_input_by_a_teamflow_caller_is_denied(self):
        self.assertDenied(run(json.dumps(
            {"tool_input": "x", "agent_type": "teamflow:manager"})))


if __name__ == "__main__":
    unittest.main()
