"""agents/*.md: every agent keeps the Bash tool; disallowedTools never names it.

0.12.0 shipped `disallowedTools: Agent, Bash(tf issue edit *)` and the
pattern removed the whole Bash tool from eight agents (#165, #188).

    python3 -m unittest discover -s tests
"""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "agents"


def field(text, key):
    """Raw value of a frontmatter key: the rest of its line plus any
    continuation lines (indented deeper, or a list item at the key's indent).
    Covers scalar, inline list, block list, folded and indented-key forms.
    shortcut: a line that is exactly `---` inside a block scalar ends the
    frontmatter here; no agent has one, and YAML calls it a document marker."""
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, "no frontmatter"
    k = re.search(rf"^([ \t]*){key}:(.*(?:\n(?:\1[ \t]+|\1-).*)*)", m.group(1), re.M)
    return k.group(2) if k else ""


def bash_patterns(text):
    """Every Bash entry in disallowedTools, in any form: Bash or Bash(...)."""
    return re.findall(r"\bBash\b(?:\([^)]*\))?", field(text, "disallowedTools"))


def has_bash(text):
    """tools lists the whole Bash tool, not just a Bash(...) pattern."""
    return bool(re.search(r"\bBash\b(?!\()", field(text, "tools")))


class AgentDisallowedTools(unittest.TestCase):
    def test_detects_the_0_12_0_frontmatter(self):
        fixture = "---\nname: x\ndisallowedTools: Agent, Bash(tf issue edit *)\n---\nbody\n"
        self.assertEqual(bash_patterns(fixture), ["Bash(tf issue edit *)"])

    def test_detects_the_forms_the_one_line_check_missed(self):
        forms = {
            "block list": "disallowedTools:\n  - Agent\n  - Bash(tf issue edit *)\n",
            "folded scalar": "disallowedTools: >\n  Agent,\n  Bash(tf issue edit *)\n",
            "indented key": "  disallowedTools: Agent, Bash(tf issue edit *)\n",
            "plain Bash": "disallowedTools: Agent, Bash\n",
        }
        for name, field in forms.items():
            with self.subTest(form=name):
                fixture = f"---\nname: x\n{field}---\nbody\n"
                self.assertEqual(len(bash_patterns(fixture)), 1)

    def test_triple_dash_in_a_value_does_not_shift_the_frontmatter(self):
        fixture = "---\ndescription: a --- b\ndisallowedTools: Bash(x)\n---\nbody\n"
        self.assertEqual(bash_patterns(fixture), ["Bash(x)"])

    def test_tools_must_list_bare_bash(self):
        for tools, ok in [("Read, Bash, SendMessage", True), ("Read, SendMessage", False),
                          ("Read, Bash(tf *)", False)]:
            with self.subTest(tools=tools):
                self.assertEqual(has_bash(f"---\nname: x\ntools: {tools}\n---\n"), ok)

    def test_no_agent_denies_a_bash_pattern(self):
        files = sorted(AGENTS.glob("*.md"))
        self.assertTrue(files)
        for f in files:
            with self.subTest(agent=f.name):
                self.assertEqual(bash_patterns(f.read_text()), [])

    def test_every_agent_keeps_bash_in_tools(self):
        # All twelve agents listed Bash before 0.12.0 (checked at 86f827f^).
        for f in sorted(AGENTS.glob("*.md")):
            with self.subTest(agent=f.name):
                self.assertTrue(has_bash(f.read_text()))


class QuotingCheck(unittest.TestCase):
    """scripts/gate.sh quoting_is_safe: flags unsafe tf command lines, not prose (#14)."""

    def flagged(self, line):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "doc.md").write_text(line + "\n")
            script = 'source <(sed -n "/^quoting_is_safe() {/,/^}/p" scripts/gate.sh); quoting_is_safe "$1"'
            r = subprocess.run(["bash", "-c", script, "bash", d], cwd=ROOT, capture_output=True, text=True)
        self.assertIn(r.returncode, (0, 1), r.stderr)
        return r.returncode == 1

    def test_prose_that_is_not_a_command_line_passes(self):
        for line in ["Pass the text with the --body flag, not a file.", "std::cout << x;",
                     "Use the `--body` flag only for one-liners.",
                     "tf pr create --title 'x' --body-file - <<'EOF'"]:
            with self.subTest(line=line):
                self.assertFalse(self.flagged(line))

    def test_unsafe_tf_command_lines_still_fail(self):
        for line in ['tf issue comment 3 --body "text `x`"', "tf issue comment 3 --body='it's'",
                     "tf issue comment 3 --body $TEXT", "tf issue comment 3 --body",
                     "tf issue comment 3 --body `date`", "tf issue comment 3 --body hello",
                     "tf issue comment 3 --body <(echo hi)", "tf  issue comment 3 --body hello",
                     '"$TF" issue comment 3 --body "x"',
                     "cat <<EOF | tf issue create --title 't' --body-file -",
                     "cat <<EOF > body.md", 'body=$(cat <<EOF', "cat << EOF > body.md", "cat <<eof > body.md",
                     'tf issue create --title "a `b`" --body-file -', "tf pr create --title 'x' --body-file - <<EOF",
                     "tf pr review 4 --verdict APPROVE --sha s --body-file - << EOF",
                     '  --body "wrapped"', "  --body-file - <<EOF"]:
            with self.subTest(line=line):
                self.assertTrue(self.flagged(line))


if __name__ == "__main__":
    unittest.main()
