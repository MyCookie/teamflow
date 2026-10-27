"""agents/*.md: no Bash(...) pattern in disallowedTools.

0.12.0 shipped `disallowedTools: Agent, Bash(tf issue edit *)` and the
pattern removed the whole Bash tool from eight agents (#165, #188).

    python3 -m unittest discover -s tests
"""

import re
import unittest
from pathlib import Path

AGENTS = Path(__file__).resolve().parents[1] / "agents"


def bash_patterns(text):
    """Bash(...) entries on the disallowedTools line of the frontmatter."""
    front = text.split("---")[1]
    return [
        m
        for line in front.splitlines()
        if line.startswith("disallowedTools:")
        for m in re.findall(r"\bBash\([^)]*\)", line)
    ]


class AgentDisallowedTools(unittest.TestCase):
    def test_detects_the_0_12_0_frontmatter(self):
        fixture = "---\nname: x\ndisallowedTools: Agent, Bash(tf issue edit *)\n---\nbody\n"
        self.assertEqual(bash_patterns(fixture), ["Bash(tf issue edit *)"])

    def test_no_agent_denies_a_bash_pattern(self):
        files = sorted(AGENTS.glob("*.md"))
        self.assertTrue(files)
        for f in files:
            with self.subTest(agent=f.name):
                self.assertEqual(bash_patterns(f.read_text()), [])


if __name__ == "__main__":
    unittest.main()
