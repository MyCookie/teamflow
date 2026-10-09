"""End-to-end checks for bin/tf in local mode, plus the github-mode refusal.

    python3 -m unittest discover -s tests
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

TF = str(Path(__file__).resolve().parents[1] / "bin" / "tf")
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def sh(*cmd, cwd, env=None):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, env={**os.environ, **GIT_ENV, **(env or {})})


def git(*args, cwd):
    result = sh("git", *args, cwd=cwd)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


class LocalFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.main, self.impl, self.rev = base / "main", base / "impl", base / "rev"
        self.main.mkdir()
        git("init", "-q", "-b", "main", cwd=self.main)
        (self.main / "scripts").mkdir()
        (self.main / "scripts" / "gate.sh").write_text("#!/bin/sh\nexit ${GATE_EXIT:-0}\n")
        (self.main / "scripts" / "gate.sh").chmod(0o755)
        (self.main / ".github").mkdir()
        (self.main / ".github" / "pull_request_template.md").write_text("## Issue\n")
        (self.main / "app.txt").write_text("v1\n")
        git("add", "-A", cwd=self.main)
        git("commit", "-q", "-m", "init", cwd=self.main)
        self.body = base / "body.md"
        self.body.write_text("Adds v2.\n\nCloses #1\n")

    def tearDown(self):
        self.tmp.cleanup()

    def tf(self, *args, cwd=None, env=None):
        return sh(TF, *args, cwd=cwd or self.main, env=env)

    def ok(self, *args, cwd=None):
        result = self.tf(*args, cwd=cwd)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def refused(self, *args, cwd=None, code=3):
        result = self.tf(*args, cwd=cwd)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result.stderr

    def test_issue_lifecycle(self):
        self.assertEqual(self.ok("mode").strip(), "local")
        self.assertEqual(self.ok("issue", "create", "--title", "Bug", "--body-file", str(self.body),
                                 "--label", "type:bug", "--label", "severity:high").strip(), "#1")
        self.ok("issue", "create", "--title", "Doc", "--body-file", str(self.body), "--label", "area:docs")
        self.assertEqual(len(self.ok("issue", "list").splitlines()), 2)
        # labels filter with OR semantics, the trap the gh --label flag fell into
        listed = self.ok("issue", "list", "--label", "area:docs", "--label", "type:bug")
        self.assertEqual(len(listed.splitlines()), 2)
        self.assertIn("#2", self.ok("issue", "list", "--label", "area:docs"))
        self.ok("issue", "comment", "1", "--body", "inline comment")
        self.assertIn("inline comment", self.ok("issue", "view", "1"))
        self.refused("issue", "comment", "1", code=2)  # a body is required (argparse exits 2)
        self.assertIn("--- comment", self.ok("issue", "view", "1"))
        self.ok("issue", "close", "2")
        self.assertNotIn("#2", self.ok("issue", "list"))
        self.refused("pr", "view", "1")  # an Issue is not a PR

    def test_pr_review_and_merge(self):
        self.ok("issue", "create", "--title", "Ship v2", "--body-file", str(self.body))
        git("worktree", "add", "-q", "-b", "feat/1-v2", str(self.impl), cwd=self.main)
        (self.impl / "app.txt").write_text("v2\n")

        self.refused("pr", "create", "--title", "t", "--body-file", str(self.body), cwd=self.impl)  # dirty
        git("commit", "-qam", "feat: v2", cwd=self.impl)
        template = self.main / ".github" / "pull_request_template.md"
        self.refused("pr", "create", "--title", "t", "--body-file", str(template), cwd=self.impl)  # unedited
        self.refused("pr", "create", "--title", "t", "--body", template.read_text(), cwd=self.impl)  # inline too
        self.refused("pr", "create", "--title", "t", "--body-file", str(self.body))  # from main
        self.assertIn("#2", self.ok("pr", "create", "--title", "feat: v2", "--body-file", str(self.body), cwd=self.impl))
        self.refused("pr", "create", "--title", "again", "--body-file", str(self.body), cwd=self.impl)  # duplicate

        self.ok("pr", "claim", "2")
        self.refused("pr", "claim", "2")  # one reviewer per PR
        self.assertIn("claimed: yes", self.ok("pr", "view", "2"))

        git("worktree", "add", "-q", "--detach", str(self.rev), cwd=self.main)
        self.refused("pr", "checkout", "2")  # never in the main worktree
        self.refused("pr", "gate", "2", cwd=self.rev)  # not yet at the PR head
        self.ok("pr", "checkout", "2", cwd=self.rev)
        self.ok("pr", "gate", "2", cwd=self.rev)
        self.assertIn("+v2", self.ok("pr", "diff", "2", "app.txt", cwd=self.rev))
        self.assertEqual(self.ok("pr", "diff", "2", "nothing.txt", cwd=self.rev).strip(), "")
        self.assertEqual(self.tf("pr", "gate", "2", cwd=self.rev, env={"GATE_EXIT": "1"}).returncode, 1)

        first = git("rev-parse", "HEAD", cwd=self.rev)
        self.refused("pr", "review", "2", "--verdict", "APPROVE", "--sha", "0" * 40, "--body-file", str(self.body), cwd=self.rev)
        self.ok("pr", "review", "2", "--verdict", "REQUEST_CHANGES", "--sha", first, "--body-file", str(self.body), cwd=self.rev)
        self.refused("pr", "merge", "2", cwd=self.rev)  # rejected

        # rework: an approval of an older head must not merge the new one
        (self.impl / "app.txt").write_text("v2 fixed\n")
        git("commit", "-qam", "fix: review", cwd=self.impl)
        self.refused("pr", "review", "2", "--verdict", "APPROVE", "--sha", first, "--body-file", str(self.body), cwd=self.rev)
        self.ok("pr", "checkout", "2", cwd=self.rev)
        second = git("rev-parse", "HEAD", cwd=self.rev)
        self.ok("pr", "review", "2", "--verdict", "APPROVE", "--sha", second, "--body-file", str(self.body), cwd=self.rev)

        # a commit after the approval invalidates it
        (self.impl / "late.txt").write_text("late\n")
        git("add", "late.txt", cwd=self.impl)
        git("commit", "-qm", "feat: late", cwd=self.impl)
        self.assertIn("no APPROVE", self.refused("pr", "merge", "2", cwd=self.rev))
        self.ok("pr", "checkout", "2", cwd=self.rev)
        second = git("rev-parse", "HEAD", cwd=self.rev)
        self.ok("pr", "review", "2", "--verdict", "APPROVE", "--sha", second, "--body-file", str(self.body), cwd=self.rev)

        # a dirty main checkout is the human's work: refuse rather than touch it
        (self.main / "app.txt").write_text("human edit\n")
        self.refused("pr", "merge", "2", cwd=self.rev)
        git("checkout", "--", "app.txt", cwd=self.main)

        self.ok("pr", "merge", "2", cwd=self.rev)
        self.assertEqual((self.main / "app.txt").read_text(), "v2 fixed\n")  # main checkout advanced
        log = git("log", "-1", "--format=%s%n%b", cwd=self.main)
        self.assertIn("Merge feat/1-v2: feat: v2", log)
        self.assertIn("Closes #1", log)
        self.assertIn("Reviewed-by: teamflow:code-reviewer (round 3)", log)
        self.assertIn("state: closed", self.ok("issue", "view", "1"))
        merged = self.ok("pr", "view", "2")
        self.assertIn("state: merged", merged)
        self.assertIn("files: app.txt, late.txt", merged)
        self.refused("pr", "merge", "2", cwd=self.rev)  # already merged
        self.ok("pr", "release", "2")

    def test_stacked_pr_must_target_base(self):
        git("worktree", "add", "-q", "-b", "feat/1-a", str(self.impl), cwd=self.main)
        (self.impl / "a.txt").write_text("a\n")
        git("add", "a.txt", cwd=self.impl)
        git("commit", "-qm", "feat: a", cwd=self.impl)
        self.ok("pr", "create", "--title", "a", "--body-file", str(self.body), "--base", "feat/0-dep", cwd=self.impl)
        git("worktree", "add", "-q", "--detach", str(self.rev), cwd=self.main)
        self.ok("pr", "checkout", "1", cwd=self.rev)
        sha = git("rev-parse", "HEAD", cwd=self.rev)
        self.ok("pr", "review", "1", "--verdict", "APPROVE", "--sha", sha, "--body-file", str(self.body), cwd=self.rev)
        self.assertIn("not main", self.refused("pr", "merge", "1", cwd=self.rev))

    def test_merging_a_dependency_retargets_its_stacked_pr(self):
        git("worktree", "add", "-q", "-b", "feat/1-dep", str(self.impl), cwd=self.main)
        (self.impl / "dep.txt").write_text("dep\n")
        git("add", "dep.txt", cwd=self.impl)
        git("commit", "-qm", "feat: dep", cwd=self.impl)
        self.ok("pr", "create", "--title", "dep", "--body-file", str(self.body), cwd=self.impl)
        stacked = self.impl.parent / "stacked"
        git("worktree", "add", "-q", "-b", "feat/2-top", str(stacked), "feat/1-dep", cwd=self.main)
        (stacked / "top.txt").write_text("top\n")
        git("add", "top.txt", cwd=stacked)
        git("commit", "-qm", "feat: top", cwd=stacked)
        self.ok("pr", "create", "--title", "top", "--body-file", str(self.body), "--base", "feat/1-dep", cwd=stacked)

        git("worktree", "add", "-q", "--detach", str(self.rev), cwd=self.main)
        self.ok("pr", "checkout", "1", cwd=self.rev)
        sha = git("rev-parse", "HEAD", cwd=self.rev)
        self.ok("pr", "review", "1", "--verdict", "APPROVE", "--sha", sha, "--body-file", str(self.body), cwd=self.rev)
        self.assertIn("#2: retargeted to main", self.ok("pr", "merge", "1", cwd=self.rev))
        self.assertIn("feat/2-top -> main", self.ok("pr", "view", "2"))
        self.assertIn("files: top.txt", self.ok("pr", "view", "2"))  # only its own change

    def approved_pr(self, change):
        git("worktree", "add", "-q", "-b", "feat/1-c", str(self.impl), cwd=self.main)
        (self.impl / "app.txt").write_text(change)
        git("commit", "-qam", "feat: c", cwd=self.impl)
        self.ok("pr", "create", "--title", "c", "--body", "Closes #9", cwd=self.impl)
        git("worktree", "add", "-q", "--detach", str(self.rev), cwd=self.main)
        self.ok("pr", "checkout", "1", cwd=self.rev)
        sha = git("rev-parse", "HEAD", cwd=self.rev)
        self.ok("pr", "review", "1", "--verdict", "APPROVE", "--sha", sha, "--body", "ok", cwd=self.rev)

    def test_conflict_is_refused_as_a_rebase(self):
        self.approved_pr("branch\n")
        (self.main / "app.txt").write_text("main moved\n")
        git("commit", "-qam", "chore: move main", cwd=self.main)
        self.assertIn("conflicts with main in app.txt", self.refused("pr", "merge", "1", cwd=self.rev))
        self.assertEqual(git("status", "--porcelain", cwd=self.rev), "")  # merge aborted cleanly

    def test_a_failed_merge_that_is_not_a_conflict_is_an_error(self):
        self.approved_pr("branch\n")
        git("config", "user.useConfigOnly", "true", cwd=self.main)
        env = {k: "" for k in GIT_ENV} | {"GIT_CONFIG_GLOBAL": "/dev/null", "EMAIL": ""}
        result = subprocess.run([TF, "pr", "merge", "1"], cwd=self.rev, text=True, capture_output=True,
                                env={k: v for k, v in os.environ.items() if k not in GIT_ENV} | env)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("conflicts", result.stderr)
        self.assertIn("merging #1 failed", result.stderr)

    def test_env_example_without_env_stops_checkout(self):
        (self.main / ".env.example").write_text("TOKEN=\n")
        git("add", ".env.example", cwd=self.main)
        git("commit", "-qm", "env example", cwd=self.main)
        git("worktree", "add", "-q", "-b", "feat/1-b", str(self.impl), cwd=self.main)
        git("commit", "-q", "--allow-empty", "-m", "feat: b", cwd=self.impl)
        self.ok("pr", "create", "--title", "b", "--body-file", str(self.body), cwd=self.impl)
        git("worktree", "add", "-q", "--detach", str(self.rev), cwd=self.main)
        self.refused("pr", "checkout", "1", cwd=self.rev, code=2)
        (self.main / ".env").write_text("TOKEN=x\n")
        self.ok("pr", "checkout", "1", cwd=self.rev)
        self.assertEqual((self.rev / ".env").read_text(), "TOKEN=x\n")

    def test_adopted_github_without_github_remote_stops(self):
        (self.main / ".claude").mkdir()
        (self.main / ".claude" / "teamflow.json").write_text(json.dumps({"forge": "github"}))
        git("remote", "add", "origin", "ssh://git@example.com/me/repo.git", cwd=self.main)
        self.assertIn("not a GitHub repository", self.refused("mode", code=2))
        self.refused("issue", "list", code=2)  # never a silent fallback to local


if __name__ == "__main__":
    unittest.main()
