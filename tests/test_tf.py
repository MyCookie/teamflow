"""End-to-end checks for bin/tf: local mode, and github mode against tests/fake_gh.py.

    python3 -m unittest discover -s tests
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

TF = str(Path(__file__).resolve().parents[1] / "bin" / "tf")
FAKE_GH = str(Path(__file__).resolve().parent / "fake_gh.py")
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

    def test_issue_edit_labels(self):
        self.ok("issue", "create", "--title", "Bug", "--body-file", str(self.body),
                "--label", "needs-discussion", "--label", "severity:medium")
        # the 2026-10-27 case: swap labels in one call
        self.ok("issue", "edit", "1", "--remove-label", "needs-discussion", "--remove-label", "severity:medium",
                "--add-label", "severity:low")
        self.assertIn("labels: severity:low\n", self.ok("issue", "view", "1"))
        self.assertIn("labels: severity:low, a", self.ok("issue", "edit", "1", "--add-label", "a",
                                                          "--add-label", "severity:low"))  # no duplicate, order kept
        self.assertIn("labels: severity:low, a, b\n", self.ok("issue", "edit", "1", "--add-label", "b",
                                                              "--add-label", "b"))  # a repeated new label is stored once
        self.ok("issue", "edit", "1", "--remove-label", "b")
        self.assertIn("labels: severity:low", self.ok("issue", "edit", "1", "--remove-label", "a", "--remove-label", "nope"))
        self.assertIn("labels: -", self.ok("issue", "edit", "1", "--remove-label", "severity:low"))
        self.ok("issue", "close", "1")
        self.ok("issue", "edit", "1", "--add-label", "late")  # closed Issues can be relabelled, not reopened
        view = self.ok("issue", "view", "1")
        self.assertIn("state: closed", view)
        self.assertIn("labels: late\n", view)

    def test_issue_edit_refusals(self):
        self.ok("issue", "create", "--title", "Bug", "--body-file", str(self.body), "--label", "x")
        self.assertIn("issue edit needs --add-label or --remove-label", self.refused("issue", "edit", "1", code=2))
        self.assertIn("label on both --add-label and --remove-label: y",
                      self.refused("issue", "edit", "1", "--add-label", "y", "--remove-label", "y", code=2))
        for bad in ("", "a,b", "a\nb", "a\x1bb", "a\x85b"):  # empty, comma, control characters (C0 and C1)
            for flag in ("--add-label", "--remove-label"):
                self.assertIn("invalid label", self.refused("issue", "edit", "1", flag, bad, code=2))
            self.assertIn("invalid label", self.refused("issue", "create", "--title", "t", "--body", "b",
                                                        "--label", bad, code=2))
        self.assertIn("labels: x\n", self.ok("issue", "view", "1"))  # nothing changed
        self.refused("issue", "view", "2")  # no Issue was created
        self.refused("issue", "edit", "99", "--add-label", "x")  # missing
        git("worktree", "add", "-q", "-b", "feat/1-v2", str(self.impl), cwd=self.main)
        (self.impl / "app.txt").write_text("v2\n")
        git("commit", "-qam", "feat: v2", cwd=self.impl)
        self.assertIn("#2", self.ok("pr", "create", "--title", "feat: v2", "--body-file", str(self.body), cwd=self.impl))
        self.refused("issue", "edit", "2", "--add-label", "x")  # a PR is not an Issue

    def test_body_from_stdin_is_stored_verbatim(self):
        # a quoted heredoc on stdin: the shell expands nothing, apostrophes included
        body = "It doesn't `rm -rf /`, and $HOME stays literal: it's text.\n"
        result = subprocess.run([TF, "issue", "create", "--title", "t", "--body-file", "-"], input=body,
                                cwd=self.main, text=True, capture_output=True, env={**os.environ, **GIT_ENV})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(body.strip(), self.ok("issue", "view", "1"))

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
        # a gate.sh killed by a signal (subprocess reports a negative code) is red too, not a crash
        (self.rev / "scripts" / "gate.sh").write_text("#!/bin/sh\nkill -KILL $$\n")
        result = self.tf("pr", "gate", "2", cwd=self.rev)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        git("checkout", "--quiet", "--", "scripts/gate.sh", cwd=self.rev)
        # a gate.sh exit of 2, 3 or 127 must not read as a setup problem or a STOP: any red is exit 1
        for gate_exit in ("2", "3", "127"):
            self.assertEqual(self.tf("pr", "gate", "2", cwd=self.rev, env={"GATE_EXIT": gate_exit}).returncode, 1, gate_exit)

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

    def test_config_comes_from_the_main_worktree_not_the_pr_under_review(self):
        # a PR that rewrites the config must not change the rules its own review runs under
        # The PR targets `dev` and its head moves `base` to `dev`: judged by its own
        # config it would merge into dev.
        git("branch", "dev", cwd=self.main)
        git("worktree", "add", "-q", "-b", "feat/1-cfg", str(self.impl), cwd=self.main)
        (self.impl / ".claude").mkdir()
        (self.impl / ".claude" / "teamflow.json").write_text(json.dumps({"base": "dev"}))
        git("add", ".claude", cwd=self.impl)
        git("commit", "-qm", "chore: rewrite config", cwd=self.impl)
        self.ok("pr", "create", "--title", "cfg", "--body", "x", "--base", "dev", cwd=self.impl)
        git("worktree", "add", "-q", "--detach", str(self.rev), cwd=self.main)
        self.ok("pr", "checkout", "1", cwd=self.rev)
        sha = git("rev-parse", "HEAD", cwd=self.rev)
        self.ok("pr", "review", "1", "--verdict", "APPROVE", "--sha", sha, "--body", "ok", cwd=self.rev)
        config = sh(str(Path(TF).parent / "teamflow-config"), "base", cwd=self.rev)
        self.assertEqual(config.stdout.strip(), "main", config.stderr)
        self.assertIn("targets dev, not main", self.refused("pr", "merge", "1", cwd=self.rev))

    def test_main_worktree_off_the_base_branch_is_a_setup_problem(self):
        # Its working copy is the trusted config only while it is on the base branch.
        git("switch", "-q", "-c", "feat/9-local", cwd=self.main)
        self.assertIn("must be on main", self.refused("mode", code=2))
        git("switch", "-q", "main", cwd=self.main)
        self.assertEqual(self.ok("mode").strip(), "local")

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

    def test_unknown_forge_is_a_setup_problem(self):
        (self.main / ".claude").mkdir()
        (self.main / ".claude" / "teamflow.json").write_text(json.dumps({"forge": "GitHub"}))
        self.assertIn("'forge' must be one of", self.refused("mode", code=2))

    def test_bare_main_checkout_is_named_as_such(self):
        # The bare dir has no trusted config: a stray, malformed one is never read, and
        # the message names no branch.
        bare = Path(self.tmp.name) / "bare.git"
        git("clone", "-q", "--bare", str(self.main), str(bare), cwd=self.main)
        (bare / ".claude").mkdir()
        (bare / ".claude" / "teamflow.json").write_text('{"base": "trunk", not json')
        wt = Path(self.tmp.name) / "wt"
        git("--git-dir", str(bare), "worktree", "add", "-q", str(wt), "main", cwd=self.main)
        result = self.tf("mode", cwd=wt)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("bare repository", result.stderr)
        self.assertNotIn("not valid JSON", result.stderr)
        self.assertNotIn("trunk", result.stderr)
        self.assertNotIn("on main", result.stderr)

    def test_tdd_defaults_to_required_and_accepts_only_two_values(self):
        config = str(Path(TF).parent / "teamflow-config")
        result = sh(config, "tdd", cwd=self.main)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "required"), result.stderr)
        (self.main / ".claude").mkdir()
        (self.main / ".claude" / "teamflow.json").write_text(json.dumps({"tdd": "recommended"}))
        self.assertEqual(sh(config, "tdd", cwd=self.main).stdout.strip(), "recommended")
        (self.main / ".claude" / "teamflow.json").write_text(json.dumps({"tdd": "optional"}))
        result = sh(config, "tdd", cwd=self.main)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("'tdd' must be one of", result.stderr)

    def test_auto_approve_defaults_to_low_and_accepts_only_two_values(self):
        config = str(Path(TF).parent / "teamflow-config")
        result = sh(config, "teamflow_auto_approve", cwd=self.main)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "low"), result.stderr)
        (self.main / ".claude").mkdir()
        (self.main / ".claude" / "teamflow.json").write_text(json.dumps({"teamflow_auto_approve": "none"}))
        self.assertEqual(sh(config, "teamflow_auto_approve", cwd=self.main).stdout.strip(), "none")
        (self.main / ".claude" / "teamflow.json").write_text(json.dumps({"teamflow_auto_approve": "medium"}))
        result = sh(config, "teamflow_auto_approve", cwd=self.main)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("'teamflow_auto_approve' must be one of", result.stderr)

    def test_removed_loop_keys_are_unknown_keys_and_not_printed(self):
        config = str(Path(TF).parent / "teamflow-config")
        printed = sh(config, "loop", cwd=self.main)
        self.assertEqual(printed.returncode, 0, printed.stderr)
        for key in ("max_iterations", "human_checkpoint"):
            self.assertNotIn(key, printed.stdout)
        (self.main / ".claude").mkdir()
        path = self.main / ".claude" / "teamflow.json"
        for key, value in (("max_iterations", 3), ("human_checkpoint", "every_cycle")):
            path.write_text(json.dumps({"loop": {key: value}}))
            result = sh(config, "loop", cwd=self.main)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(f"unknown key 'loop.{key}'", result.stderr)

    def test_bad_config_is_a_setup_problem(self):
        (self.main / ".claude").mkdir()
        (self.main / ".claude" / "teamflow.json").write_text("{not json")
        self.assertIn("not valid JSON", self.refused("mode", code=2))
        # the manager calls teamflow-config directly, so its own exit code matters too
        direct = sh(str(Path(TF).parent / "teamflow-config"), cwd=self.main)
        self.assertEqual(direct.returncode, 2, direct.stderr)
        self.assertIn("not valid JSON", direct.stderr)

    def test_adopted_github_without_github_remote_stops(self):
        (self.main / ".claude").mkdir()
        (self.main / ".claude" / "teamflow.json").write_text(json.dumps({"forge": "github"}))
        git("remote", "add", "origin", "ssh://git@example.com/me/repo.git", cwd=self.main)
        self.assertIn("not a GitHub repository", self.refused("mode", code=2))
        self.refused("issue", "list", code=2)  # never a silent fallback to local



class GitHubFlow(unittest.TestCase):
    """github mode, with GitHub played by tests/fake_gh.py and a bare repository."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.bare = base / "github.com" / "me" / "repo.git"  # the path satisfies tf's GitHub-remote check
        self.main, self.impl, self.rev = base / "main", base / "impl", base / "rev"
        self.state = base / "gh-state.json"
        fakebin = base / "fakebin"
        fakebin.mkdir()
        (fakebin / "gh").symlink_to(FAKE_GH)
        self.env = {"PATH": f"{fakebin}{os.pathsep}{os.environ['PATH']}",
                    "FAKE_GH_STATE": str(self.state), "FAKE_GH_BARE": str(self.bare),
                    "TF_GATE_WAIT": "0", "TF_GATE_POLL": "0.01"}  # no waiting unless a test asks

        self.bare.mkdir(parents=True)
        git("init", "-q", "--bare", "-b", "main", cwd=self.bare)
        self.main.mkdir()
        git("init", "-q", "-b", "main", cwd=self.main)
        (self.main / ".claude").mkdir()
        (self.main / ".claude" / "teamflow.json").write_text(json.dumps({"forge": "github"}))
        (self.main / "app.txt").write_text("v1\n")
        git("add", "-A", cwd=self.main)
        git("commit", "-qm", "init", cwd=self.main)
        git("remote", "add", "origin", str(self.bare), cwd=self.main)
        git("push", "-q", "origin", "main", cwd=self.main)

    def tearDown(self):
        self.tmp.cleanup()

    def tf(self, *args, cwd=None, env=None):
        return sh(TF, *args, cwd=cwd or self.main, env={**self.env, **(env or {})})

    def ok(self, *args, cwd=None):
        result = self.tf(*args, cwd=cwd)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def code(self, expected, *args, cwd=None):
        result = self.tf(*args, cwd=cwd)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result.stderr

    def gh_state(self):
        return json.loads(self.state.read_text())

    def set_checks(self, sha, bucket, required=False):
        state = self.gh_state()
        state["checks"][sha] = [{"name": "gate", "bucket": bucket}]
        state.get("check_seq", {}).pop(sha, None)
        state["required"] = required
        self.state.write_text(json.dumps(state))

    def set_check_seq(self, sha, buckets):
        """The gate check reads these buckets on successive polls, then keeps the last."""
        state = self.gh_state()
        state.setdefault("check_seq", {})[sha] = buckets
        self.state.write_text(json.dumps(state))

    def open_pr(self):
        self.ok("issue", "create", "--title", "Ship v2", "--body", "Make it v2.", "--label", "type:feature")
        git("worktree", "add", "-q", "-b", "feat/1-v2", str(self.impl), cwd=self.main)
        (self.impl / "app.txt").write_text("v2\n")
        git("commit", "-qam", "feat: v2", cwd=self.impl)
        self.ok("pr", "create", "--title", "feat: v2", "--body", "Closes #1", cwd=self.impl)  # pushes the branch
        git("worktree", "add", "-q", "--detach", str(self.rev), cwd=self.main)
        self.ok("pr", "checkout", "2", cwd=self.rev)
        return git("rev-parse", "HEAD", cwd=self.rev)

    def test_issue_view_prints_without_a_terminal(self):
        self.assertEqual(self.ok("mode").strip(), "github")
        self.ok("issue", "create", "--title", "Bug", "--body", "It breaks.", "--label", "type:bug")
        self.ok("issue", "comment", "1", "--body", "Seen on main.")
        view = self.ok("issue", "view", "1")  # captured output: no terminal, as for an agent
        for text in ("#1 Bug", "labels: type:bug", "It breaks.", "Seen on main."):
            self.assertIn(text, view)
        self.assertIn("#1", self.ok("issue", "list", "--label", "area:docs", "--label", "type:bug"))
        self.assertEqual(self.ok("issue", "list", "--label", "area:docs"), "")

    def test_issue_edit_labels(self):
        self.ok("issue", "create", "--title", "Bug", "--body", "It breaks.",
                "--label", "needs-discussion", "--label", "severity:medium")
        self.ok("issue", "edit", "1", "--remove-label", "needs-discussion", "--remove-label", "severity:medium",
                "--add-label", "severity:low")
        self.assertIn("labels: severity:low\n", self.ok("issue", "view", "1"))
        self.assertIn("#1", self.ok("issue", "list", "--label", "severity:low"))
        self.assertEqual(self.ok("issue", "list", "--label", "needs-discussion"), "")
        self.assertIn("issue edit needs --add-label or --remove-label", self.code(2, "issue", "edit", "1"))
        self.assertIn("label on both --add-label and --remove-label: y",
                      self.code(2, "issue", "edit", "1", "--add-label", "y", "--remove-label", "y"))
        for bad in ("", "a,b", "a\nb", "a\x1bb", "a\x85b"):  # empty, comma, control characters (C0 and C1)
            for flag in ("--add-label", "--remove-label"):
                self.assertIn("invalid label", self.code(2, "issue", "edit", "1", flag, bad))
            self.assertIn("invalid label", self.code(2, "issue", "create", "--title", "t", "--body", "b", "--label", bad))
        self.assertIn("labels: severity:low\n", self.ok("issue", "view", "1"))  # nothing changed
        self.assertEqual(list(self.gh_state()["issues"]), ["1"])  # the bad create made no Issue

    def test_issue_edit_matches_local_mode(self):
        self.open_pr()  # Issue #1, PR #2
        # prints the labels read back after the edit, as local mode does
        out = self.ok("issue", "edit", "1", "--add-label", "a", "--add-label", "b", "--remove-label", "type:feature")
        self.assertEqual(out.strip(), "#1: labels: a, b")
        self.assertEqual(self.ok("issue", "edit", "1", "--remove-label", "a", "--remove-label", "b").strip(), "#1: labels: -")
        # a PR number and a missing number are refused (exit 3) before gh edits anything
        before = self.gh_state()
        self.assertIn("#2 is a PR, not an Issue", self.code(3, "issue", "edit", "2", "--add-label", "x"))
        self.assertIn("#99 does not exist", self.code(3, "issue", "edit", "99", "--add-label", "x"))
        self.assertEqual(self.gh_state(), before)  # fake_gh's answers; real gh not run (#171)

    def test_pr_view_shows_the_merge_state(self):
        self.open_pr()
        self.assertIn("merge state: clean", self.ok("pr", "view", "2"))
        state = self.gh_state()
        state["prs"]["2"]["merge_state"] = "BEHIND"
        self.state.write_text(json.dumps(state))
        self.assertIn("merge state: behind", self.ok("pr", "view", "2"))

    def test_claim_gate_review_and_unenforced_merge(self):
        head = self.open_pr()
        self.assertIn("files: app.txt", self.ok("pr", "view", "2"))

        self.ok("pr", "claim", "2")
        self.code(3, "pr", "claim", "2")  # pending status = claimed
        self.ok("pr", "release", "2")
        self.assertIn("error", self.ok("pr", "view", "2"))  # abandoned claim
        self.ok("pr", "claim", "2")

        self.code(2, "pr", "gate", "2", cwd=self.rev)  # no gate check at all
        self.set_checks(head, "pending")
        self.code(3, "pr", "gate", "2", cwd=self.rev)
        self.set_checks(head, "fail")
        self.code(1, "pr", "gate", "2", cwd=self.rev)
        self.set_checks(head, "pass")
        self.ok("pr", "gate", "2", cwd=self.rev)

        self.code(3, "pr", "review", "2", "--verdict", "APPROVE", "--sha", "0" * 40, "--body", "x", cwd=self.rev)
        self.ok("pr", "review", "2", "--verdict", "APPROVE", "--sha", head, "--body", "**Verdict: APPROVE**", cwd=self.rev)
        self.assertIn("success (APPROVE", self.ok("pr", "view", "2"))
        self.assertEqual(self.gh_state()["reviews"][-1]["body"], "**Verdict: APPROVE**")

        # a push after the approval: the new head has no verdict
        (self.impl / "late.txt").write_text("late\n")
        git("add", "late.txt", cwd=self.impl)
        git("commit", "-qm", "feat: late", cwd=self.impl)
        git("push", "-q", "origin", "feat/1-v2", cwd=self.impl)
        self.assertIn("no APPROVE", self.code(3, "pr", "merge", "2", cwd=self.rev))

        self.ok("pr", "checkout", "2", cwd=self.rev)
        head = git("rev-parse", "HEAD", cwd=self.rev)
        self.ok("pr", "review", "2", "--verdict", "APPROVE", "--sha", head, "--body", "ok", cwd=self.rev)
        self.set_checks(head, "fail")
        self.code(1, "pr", "merge", "2", cwd=self.rev)  # no ruleset: tf itself refuses a red gate
        self.assertEqual(self.gh_state()["merges"], [])
        self.set_checks(head, "pass")
        self.ok("pr", "merge", "2", cwd=self.rev)
        merge = self.gh_state()["merges"][-1]
        self.assertFalse(merge["auto"])
        self.assertEqual(merge["subject"], "Merge feat/1-v2: feat: v2")
        self.assertEqual(self.gh_state()["prs"]["2"]["state"], "MERGED")

    def test_gate_waits_for_pending_checks(self):
        head = self.open_pr()
        wait = {"TF_GATE_WAIT": "30", "TF_GATE_POLL": "0.01"}

        self.set_check_seq(head, ["pending", "pending", "pass"])  # A1
        result = self.tf("pr", "gate", "2", cwd=self.rev, env=wait)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count("waiting for: gate"), 1)  # announced once, not per poll

        self.set_check_seq(head, ["pending", "fail"])  # A3
        self.assertEqual(self.tf("pr", "gate", "2", cwd=self.rev, env=wait).returncode, 1)

        self.set_checks(head, "pending")  # A2: still pending at the bound
        result = self.tf("pr", "gate", "2", cwd=self.rev, env={"TF_GATE_WAIT": "0.1", "TF_GATE_POLL": "0.01"})
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("gate", result.stderr)
        self.assertIn("did not finish", result.stderr)

    def test_gate_retries_a_failed_or_empty_poll(self):
        head = self.open_pr()
        wait = {"TF_GATE_WAIT": "30", "TF_GATE_POLL": "0.01"}
        for seq in (["pending", "error", "pending", "pass"], ["empty", "pending", "pass"], ["error", "pass"]):
            self.set_check_seq(head, seq)  # a 502 or a not-yet-registered check run, then CI finishes
            result = self.tf("pr", "gate", "2", cwd=self.rev, env=wait)
            self.assertEqual(result.returncode, 0, f"{seq}: {result.stdout}{result.stderr}")

        # a transient failure of the --required query must not narrow the poll to `gate` alone
        state = self.gh_state()
        state["checks"][head] = [{"name": "gate", "bucket": "pass"}, {"name": "lint", "bucket": "fail"}]
        state["check_seq"].pop(head)
        state["required"], state["required_errors"] = True, 1
        self.state.write_text(json.dumps(state))
        result = self.tf("pr", "gate", "2", cwd=self.rev, env=wait)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("lint: fail", result.stdout)

        # still failing or empty at the bound: CI's state is unknown, so a failed poll is a STOP (3),
        # not exit 1 (a red check); an empty list is a missing `gate` check (2)
        bound = {"TF_GATE_WAIT": "0.1", "TF_GATE_POLL": "0.01"}
        self.set_check_seq(head, ["error"])
        result = self.tf("pr", "gate", "2", cwd=self.rev, env=bound)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("could not read CI", result.stderr)
        self.assertIn("502", result.stderr)
        self.set_check_seq(head, ["empty"])
        result = self.tf("pr", "gate", "2", cwd=self.rev, env=bound)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("no `gate` check", result.stderr)

    def test_gate_rejects_wait_settings_that_would_crash_or_hang(self):
        head = self.open_pr()
        self.set_check_seq(head, ["pending", "pass"])
        for env in ({"TF_GATE_WAIT": "abc"}, {"TF_GATE_POLL": "-1"}, {"TF_GATE_POLL": "0"}, {"TF_GATE_POLL": "nan"},
                    {"TF_GATE_WAIT": "nan"}, {"TF_GATE_WAIT": "-1"}, {"TF_GATE_WAIT": "inf"}, {"TF_GATE_POLL": "inf"}):
            result = self.tf("pr", "gate", "2", cwd=self.rev, env={"TF_GATE_WAIT": "30", "TF_GATE_POLL": "0.01", **env})
            self.assertEqual(result.returncode, 2, f"{env}: {result.stdout}{result.stderr}")
            self.assertIn("TF_GATE_WAIT", result.stderr)
        env = {"TF_GATE_WAIT": "0", "TF_GATE_POLL": "0.01"}  # 0 is a valid wait: poll once
        self.assertEqual(self.tf("pr", "gate", "2", cwd=self.rev, env=env).returncode, 3)

    def test_unenforced_merge_waits_for_pending_checks(self):
        head = self.open_pr()
        self.ok("pr", "review", "2", "--verdict", "APPROVE", "--sha", head, "--body", "ok", cwd=self.rev)
        self.set_check_seq(head, ["pending", "pass"])
        result = self.tf("pr", "merge", "2", cwd=self.rev, env={"TF_GATE_WAIT": "30", "TF_GATE_POLL": "0.01"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.gh_state()["prs"]["2"]["state"], "MERGED")

    def test_merge_treats_unreadable_ci_as_a_stop_not_an_error(self):
        head = self.open_pr()
        self.set_checks(head, "pass", required=True)
        self.ok("pr", "review", "2", "--verdict", "APPROVE", "--sha", head, "--body", "ok", cwd=self.rev)
        wait = {"TF_GATE_WAIT": "30", "TF_GATE_POLL": "0.01"}

        state = self.gh_state()  # a 502 on the required-checks poll that clears: retried like tf pr gate
        self.assertEqual(len(state["merges"]), 1)  # the review armed auto-merge; tf pr merge below is the fallback
        state["merges"], state["required_errors"] = [], 2
        self.state.write_text(json.dumps(state))
        result = self.tf("pr", "merge", "2", cwd=self.rev, env=wait)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.gh_state()["merges"][-1]["auto"])

        state = self.gh_state()  # still failing at the bound: exit 3, nothing merged
        state["merges"], state["required_errors"] = [], 10**6
        self.state.write_text(json.dumps(state))
        result = self.tf("pr", "merge", "2", cwd=self.rev, env={"TF_GATE_WAIT": "0.1", "TF_GATE_POLL": "0.01"})
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("could not read CI", result.stderr)
        self.assertIn("502", result.stderr)
        self.assertEqual(self.gh_state()["merges"], [])
        self.assertEqual(self.gh_state()["prs"]["2"]["state"], "OPEN")

    def test_unenforced_merge_treats_an_unreadable_gate_check_as_a_stop(self):
        head = self.open_pr()
        self.ok("pr", "review", "2", "--verdict", "APPROVE", "--sha", head, "--body", "ok", cwd=self.rev)
        self.set_checks(head, "pass")  # no ruleset: only the gate check is read
        self.set_check_seq(head, ["error"])
        result = self.tf("pr", "merge", "2", cwd=self.rev, env={"TF_GATE_WAIT": "0.1", "TF_GATE_POLL": "0.01"})
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("could not read CI", result.stderr)
        self.assertEqual(self.gh_state()["merges"], [])
        self.assertEqual(self.gh_state()["prs"]["2"]["state"], "OPEN")

    def test_merge_without_a_ruleset_has_one_deadline_and_never_reads_the_required_checks(self):
        head = self.open_pr()
        self.ok("pr", "review", "2", "--verdict", "APPROVE", "--sha", head, "--body", "ok", cwd=self.rev)
        self.set_checks(head, "pending")  # no ruleset, and the `gate` check never finishes
        self.set_check_seq(head, ["error"] * 7 + ["pending"])  # 7 failed reads: a second wait would show
        wait, poll = 3, 0.2
        result = self.tf("pr", "merge", "2", cwd=self.rev, env={"TF_GATE_WAIT": str(wait), "TF_GATE_POLL": str(poll)})
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("still running: gate", result.stderr)
        reads = self.gh_state()["reads"]
        self.assertEqual(reads["required"], 0)  # tf's own path judges `gate`; the required list is not its business
        self.assertLessEqual(reads["all"], wait / poll + 1)  # one deadline
        self.assertEqual(self.gh_state()["merges"], [])

    def merge_while_the_pr_changes(self, change):
        """tf pr merge on an approved head whose CI is pending; the PR then changes as `change` says."""
        head = self.open_pr()
        self.ok("pr", "review", "2", "--verdict", "APPROVE", "--sha", head, "--body", "ok", cwd=self.rev)
        self.set_check_seq(head, ["pending", "pass"])
        self.set_check_seq("1" * 40, ["pass"])
        state = self.gh_state()
        state["change_on_pending"] = change
        self.state.write_text(json.dumps(state))
        result = self.tf("pr", "merge", "2", cwd=self.rev, env={"TF_GATE_WAIT": "30", "TF_GATE_POLL": "0.01"})
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertEqual(self.gh_state()["merges"], [])
        return result.stderr

    def test_merge_refuses_a_head_that_moved_during_the_wait(self):
        self.assertIn("head moved", self.merge_while_the_pr_changes({"oid": "1" * 40}))

    def test_merge_refuses_a_pr_retargeted_during_the_wait(self):
        self.assertIn("targets feat/0-dep", self.merge_while_the_pr_changes({"base": "feat/0-dep"}))

    def test_merge_refuses_a_pr_closed_during_the_wait(self):
        self.assertIn("not open", self.merge_while_the_pr_changes({"state": "CLOSED"}))

    def test_gate_treats_a_non_list_or_stdout_only_failure_as_unreadable_ci(self):
        head = self.open_pr()
        self.set_checks(head, "pass")
        bound = {"TF_GATE_WAIT": "0.1", "TF_GATE_POLL": "0.01"}
        for stdout in ('{"message": "boom"}', "<html>boom</html>"):  # gh failures that print only to stdout
            with self.subTest(stdout=stdout):
                state = self.gh_state()
                state["checks_stdout"] = stdout
                self.state.write_text(json.dumps(state))
                result = self.tf("pr", "gate", "2", cwd=self.rev, env=bound)
                self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
                self.assertIn("could not read CI", result.stderr)
                self.assertIn("boom", result.stderr)

    def test_unenforced_merge_rereads_the_approval_after_the_wait(self):
        head = self.open_pr()
        self.ok("pr", "review", "2", "--verdict", "APPROVE", "--sha", head, "--body", "ok", cwd=self.rev)
        self.set_check_seq(head, ["pending", "pass"])  # a reviewer rejects the head while CI runs
        state = self.gh_state()
        state["revoke_on_pending"] = True
        self.state.write_text(json.dumps(state))
        result = self.tf("pr", "merge", "2", cwd=self.rev, env={"TF_GATE_WAIT": "30", "TF_GATE_POLL": "0.01"})
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("no APPROVE", result.stderr)
        self.assertEqual(self.gh_state()["merges"], [])
        self.assertEqual(self.gh_state()["prs"]["2"]["state"], "OPEN")

    def test_merge_on_a_ruleset_repository_validates_the_wait_settings(self):
        head = self.open_pr()
        self.set_checks(head, "pass", required=True)
        self.ok("pr", "review", "2", "--verdict", "APPROVE", "--sha", head, "--body", "ok", cwd=self.rev)
        state = self.gh_state()
        self.assertEqual(len(state["merges"]), 1)  # the review armed auto-merge; only tf pr merge is under test here
        state["merges"] = []
        self.state.write_text(json.dumps(state))
        for env in ({"TF_GATE_WAIT": "abc"}, {"TF_GATE_WAIT": "-1"}, {"TF_GATE_POLL": "0"}):
            result = self.tf("pr", "merge", "2", cwd=self.rev, env=env)
            self.assertEqual(result.returncode, 2, f"{env}: {result.stdout}{result.stderr}")
            self.assertIn("TF_GATE_WAIT", result.stderr)
        self.assertEqual(self.gh_state()["merges"], [])
        state = self.gh_state()  # 0 is a valid wait: read once, then exit 3 if the read fails
        state["required_errors"] = 10**6
        self.state.write_text(json.dumps(state))
        self.code(3, "pr", "merge", "2", cwd=self.rev)
        self.assertEqual(self.gh_state()["merges"], [])

    def test_merge_refuses_a_rejected_or_merely_claimed_head(self):
        head = self.open_pr()
        self.set_checks(head, "pass")
        self.ok("pr", "claim", "2")  # pending status only
        self.assertIn("no APPROVE", self.code(3, "pr", "merge", "2", cwd=self.rev))
        self.ok("pr", "review", "2", "--verdict", "REQUEST_CHANGES", "--sha", head, "--body", "no", cwd=self.rev)
        self.assertIn("no APPROVE", self.code(3, "pr", "merge", "2", cwd=self.rev))
        self.assertEqual(self.gh_state()["merges"], [])

    def test_merge_refuses_a_pr_that_does_not_target_the_base(self):
        head = self.open_pr()
        state = self.gh_state()
        state["prs"]["2"]["base"] = "feat/0-dep"
        self.state.write_text(json.dumps(state))
        self.set_checks(head, "pass")
        self.ok("pr", "review", "2", "--verdict", "APPROVE", "--sha", head, "--body", "ok", cwd=self.rev)
        self.assertIn("not main", self.code(3, "pr", "merge", "2", cwd=self.rev))
        self.assertEqual(self.gh_state()["merges"], [])

    def test_gate_requires_every_required_check_not_only_gate(self):
        head = self.open_pr()
        state = self.gh_state()
        state["checks"][head] = [{"name": "gate", "bucket": "pass"}, {"name": "lint", "bucket": "fail"}]
        state["required"] = True
        self.state.write_text(json.dumps(state))
        result = self.tf("pr", "gate", "2", cwd=self.rev)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("lint: fail", result.stdout)

    def test_enforced_repository_uses_auto_merge(self):
        head = self.open_pr()
        self.set_checks(head, "pass", required=True)
        self.ok("pr", "gate", "2", cwd=self.rev)
        self.ok("pr", "review", "2", "--verdict", "APPROVE", "--sha", head, "--body", "ok", cwd=self.rev)
        self.assertEqual([m["auto"] for m in self.gh_state()["merges"]], [True])  # armed by the review itself
        self.assertEqual(self.gh_state()["prs"]["2"]["state"], "OPEN")  # GitHub merges it later
        self.ok("pr", "merge", "2", cwd=self.rev)  # the fallback when arming failed: arms again
        self.assertEqual([m["auto"] for m in self.gh_state()["merges"]], [True, True])
        self.assertEqual(self.gh_state()["prs"]["2"]["state"], "OPEN")

    def test_pr_view_shows_the_auto_merge_state(self):
        head = self.open_pr()
        self.set_checks(head, "pass", required=True)
        self.assertIn("merge state: clean\nauto-merge: off\n", self.ok("pr", "view", "2"))
        self.ok("pr", "gate", "2", cwd=self.rev)
        self.ok("pr", "review", "2", "--verdict", "APPROVE", "--sha", head, "--body", "ok", cwd=self.rev)  # ruleset: arms auto-merge
        self.assertIn("merge state: clean\nauto-merge: on\n", self.ok("pr", "view", "2"))

    def test_ruleset_merge_does_not_wait_for_unfinished_or_red_required_checks(self):
        """With a ruleset GitHub enforces the required checks: tf enables auto-merge at once, whatever their bucket."""
        head = self.open_pr()
        self.ok("pr", "review", "2", "--verdict", "APPROVE", "--sha", head, "--body", "ok", cwd=self.rev)
        for bucket in ("pending", "fail"):
            with self.subTest(bucket=bucket):
                self.set_checks(head, bucket, required=True)
                state = self.gh_state()
                state["merges"], state["reads"] = [], {"required": 0, "all": 0}
                self.state.write_text(json.dumps(state))
                result = self.tf("pr", "merge", "2", cwd=self.rev, env={"TF_GATE_WAIT": "30", "TF_GATE_POLL": "0.01"})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(self.gh_state()["reads"], {"required": 1, "all": 0})  # one read, no waiting
                self.assertTrue(self.gh_state()["merges"][-1]["auto"])

    def approved_head_with_foreign_protection(self, gate_bucket):
        """An approved head whose only ruleset requirement is `build`: no `gate`, no `teamflow/code-review`."""
        head = self.open_pr()
        state = self.gh_state()
        state["checks"][head] = [{"name": "build", "bucket": "pass"}, {"name": "gate", "bucket": gate_bucket}]
        state.update(required=True, required_names=["build"], rule_contexts=["build"])
        self.state.write_text(json.dumps(state))
        self.ok("pr", "review", "2", "--verdict", "APPROVE", "--sha", head, "--body", "ok", cwd=self.rev)
        self.assertEqual(self.gh_state()["merges"], [])  # the review armed nothing
        return head

    def test_merge_does_not_trust_a_ruleset_that_lacks_the_gate_and_review_contexts(self):
        self.approved_head_with_foreign_protection("fail")  # `build` is green, `gate` is red
        result = self.tf("pr", "merge", "2", cwd=self.rev)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("gate: fail", result.stdout)
        self.assertEqual(self.gh_state()["merges"], [])  # no --auto, no merge
        self.assertEqual(self.gh_state()["prs"]["2"]["state"], "OPEN")

    def test_merge_uses_its_own_path_when_the_ruleset_lacks_the_gate_and_review_contexts(self):
        self.approved_head_with_foreign_protection("pass")
        self.ok("pr", "merge", "2", cwd=self.rev)
        self.assertEqual([m["auto"] for m in self.gh_state()["merges"]], [False])
        self.assertEqual(self.gh_state()["prs"]["2"]["state"], "MERGED")

    def test_merge_does_not_arm_auto_merge_on_an_unreadable_ruleset(self):
        head = self.open_pr()
        self.set_checks(head, "pass", required=True)
        self.ok("pr", "review", "2", "--verdict", "APPROVE", "--sha", head, "--body", "ok", cwd=self.rev)
        state = self.gh_state()
        state.update(merges=[], rules_error=True)
        self.state.write_text(json.dumps(state))
        result = self.tf("pr", "merge", "2", cwd=self.rev)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("could not read the ruleset", result.stdout)
        self.assertEqual([m["auto"] for m in self.gh_state()["merges"]], [False])
        self.assertEqual(self.gh_state()["prs"]["2"]["state"], "MERGED")

    def review(self, head, verdict="APPROVE", body="ok"):
        return self.tf("pr", "review", "2", "--verdict", verdict, "--sha", head, "--body", body, cwd=self.rev)

    def test_approve_arms_auto_merge_on_a_ruleset_repository(self):
        head = self.open_pr()
        self.set_checks(head, "pass", required=True)
        result = self.review(head, body="Closes #9 in the review body, which must not be used")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        merges = self.gh_state()["merges"]
        self.assertEqual(len(merges), 1)  # exactly one, with no tf pr merge after the review
        self.assertEqual(merges[0], {"pr": "2", "auto": True, "subject": "Merge feat/1-v2: feat: v2",
                                     "body": "Closes #1\nReviewed-by: teamflow:code-reviewer", "match": head})
        self.assertIn("success (APPROVE", self.ok("pr", "view", "2"))
        self.assertIn("auto-merge: on", self.ok("pr", "view", "2"))

    def test_approve_that_makes_the_pr_clean_can_merge_it_at_once(self):
        head = self.open_pr()
        self.set_checks(head, "pass", required=True)
        state = self.gh_state()
        state["auto_merges_when_clean"] = True
        self.state.write_text(json.dumps(state))
        result = self.review(head)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("state: merged", self.ok("pr", "view", "2"))

    def test_approve_on_a_stacked_pr_arms_nothing(self):
        head = self.open_pr()
        self.set_checks(head, "pass", required=True)
        state = self.gh_state()
        state["prs"]["2"]["base"] = "feat/0-dep"
        state["auto_merges_when_clean"] = True  # arming would merge it into its dependency
        self.state.write_text(json.dumps(state))
        result = self.review(head)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("not main", result.stdout)
        self.assertEqual(self.gh_state()["merges"], [])
        self.assertIn("success (APPROVE", self.ok("pr", "view", "2"))

    def test_approve_arms_nothing_unless_the_ruleset_requires_both_contexts(self):
        head = self.open_pr()
        for contexts in ([], ["gate"], ["teamflow/code-review"]):
            with self.subTest(contexts=contexts):
                self.set_checks(head, "pass", required=True)  # `pr checks --required` is non-empty, as it is with only a gate rule
                state = self.gh_state()
                state["rule_contexts"] = contexts
                self.state.write_text(json.dumps(state))
                result = self.review(head)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("tf pr merge 2", result.stdout)
                self.assertEqual(self.gh_state()["merges"], [])

    def test_request_changes_arms_nothing(self):
        head = self.open_pr()
        self.set_checks(head, "pass", required=True)
        result = self.review(head, verdict="REQUEST_CHANGES", body="no")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.gh_state()["merges"], [])
        self.assertIn("failure (REQUEST_CHANGES", self.ok("pr", "view", "2"))

    def test_arming_failure_after_the_verdict_exits_4_and_keeps_the_verdict(self):
        head = self.open_pr()
        self.set_checks(head, "pass", required=True)
        for key in ("merge_error", "rules_error"):  # gh refuses the merge; the ruleset cannot be read
            with self.subTest(key=key):
                state = self.gh_state()
                state[key] = True
                self.state.write_text(json.dumps(state))
                result = self.review(head)
                self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
                self.assertIn("verdict recorded", result.stderr)
                self.assertIn("tf pr merge 2", result.stderr)
                self.assertIn("success (APPROVE", self.ok("pr", "view", "2"))
                self.assertEqual(self.gh_state()["merges"], [])
                state = self.gh_state()
                state.pop(key)
                self.state.write_text(json.dumps(state))

    def test_missing_gh_stops(self):
        bare_path = Path(self.tmp.name) / "nogh"
        bare_path.mkdir()
        for tool in ("git", "python3"):
            (bare_path / tool).symlink_to(shutil.which(tool))
        result = self.tf("mode", env={"PATH": str(bare_path)})
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("gh is not installed", result.stderr)

    def test_logged_out_gh_stops(self):
        result = self.tf("issue", "list", env={"FAKE_GH_LOGGED_OUT": "1"})
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("not authenticated", result.stderr)


class Usage(unittest.TestCase):
    def test_every_command_that_takes_a_body_file_says_it_may_be_stdin(self):
        out = sh(TF, "--help", cwd=tempfile.gettempdir()).stdout
        for command in ("issue create", "issue comment", "pr create", "pr review"):
            with self.subTest(command=command):
                line = next(l for l in out.splitlines() if l.strip().startswith(f"tf {command} "))
                self.assertIn("--body-file", line)
                self.assertIn("stdin", line)


if __name__ == "__main__":
    unittest.main()
