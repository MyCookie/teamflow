"""tf setup: dry run, apply, idempotence, and the github steps against tests/fake_gh.py.

    python3 -m unittest discover -s tests
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from test_tf import FAKE_GH, TF, git, sh

TEMPLATES = Path(TF).resolve().parents[1] / "templates"


class Setup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.repo = base / "repo"
        self.repo.mkdir()
        git("init", "-q", "-b", "main", cwd=self.repo)
        (self.repo / "README.md").write_text("demo\n")
        git("add", "-A", cwd=self.repo)
        git("commit", "-qm", "init", cwd=self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def tf(self, *args, env=None, code=0, cwd=None):
        result = sh(TF, "setup", *args, cwd=cwd or self.repo, env=env)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def tree(self):
        return sorted(str(p.relative_to(self.repo)) for p in self.repo.rglob("*") if ".git" not in p.parts)

    def test_dry_run_changes_nothing(self):
        before = self.tree()
        out = self.tf()
        self.assertIn("would create scripts/gate.sh", out)
        self.assertEqual(self.tree(), before)

    def test_apply_creates_local_files_and_keeps_settings(self):
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "settings.json").write_text(json.dumps({"env": {"X": "1"}}))
        (self.repo / ".gitignore").write_text(".env\n")
        self.tf("--apply")
        settings = json.loads((self.repo / ".claude" / "settings.json").read_text())
        self.assertEqual(settings, {"env": {"X": "1"}, "crossSessionInbound": "accept"})
        self.assertEqual((self.repo / "scripts" / "gate.sh").read_text(), (TEMPLATES / "gate.sh").read_text())
        self.assertTrue(os.access(self.repo / "scripts" / "gate.sh", os.X_OK))
        self.assertEqual((self.repo / ".github" / "pull_request_template.md").read_text(),
                         (TEMPLATES / "pull_request_template.md").read_text())
        ignores = (self.repo / ".gitignore").read_text().splitlines()
        self.assertEqual(ignores, [".env", ".manager-state.json", ".claude/worktrees/"])
        self.assertEqual(json.loads((self.repo / ".claude" / "teamflow.json").read_text()), {"forge": "local"})
        self.assertFalse((self.repo / ".github" / "workflows").exists())  # github only

    def test_never_commits(self):
        head = git("rev-parse", "HEAD", cwd=self.repo)
        self.tf("--apply")
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.repo), head)
        self.assertEqual(git("status", "--porcelain", "--untracked-files=no", cwd=self.repo), "")

    def test_runs_on_a_branch_in_a_linked_worktree(self):
        # the setup PR is prepared on a branch, away from the main checkout
        wt = Path(self.tmp.name) / "setup-wt"
        git("worktree", "add", "-q", "-b", "chore/teamflow-setup", str(wt), cwd=self.repo)
        self.tf("--apply", cwd=wt)
        self.assertTrue((wt / "scripts" / "gate.sh").is_file())
        self.assertFalse((self.repo / "scripts").exists())

    def test_invalid_json_is_a_setup_error_not_a_traceback(self):
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "settings.json").write_text("{nope")
        out = self.tf(code=2)
        self.assertIn("settings.json is not valid JSON", out)
        self.assertNotIn("Traceback", out)

    def test_json_that_is_not_an_object_is_a_setup_error_not_a_traceback(self):
        (self.repo / ".claude").mkdir()
        for name in ("settings.json", "teamflow.json"):
            (self.repo / ".claude" / name).write_text("[]")
            with self.subTest(file=name):
                out = self.tf(code=2)
                self.assertIn(f"{name} is not a JSON object", out)
                self.assertNotIn("Traceback", out)
            (self.repo / ".claude" / name).unlink()

    def test_a_broken_template_is_a_setup_error_not_a_traceback(self):
        plugin = Path(self.tmp.name) / "plugin"
        (plugin / "bin").mkdir(parents=True)
        for name in ("tf", "teamflow-config"):
            shutil.copy(Path(TF).parent / name, plugin / "bin" / name)
        shutil.copytree(TEMPLATES, plugin / "templates")
        (plugin / "templates" / "branch-ruleset.json").write_text("{nope")
        self.github_repo()
        env = self.fake_gh_env(remote_files=[".github/workflows/gate.yml"])
        result = sh(str(plugin / "bin" / "tf"), "setup", "--forge", "github", cwd=self.repo, env=env)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("branch-ruleset.json is not valid JSON", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_second_apply_changes_nothing_and_never_overwrites(self):
        self.tf("--apply")
        (self.repo / "scripts" / "gate.sh").write_text("#!/bin/sh\n# customised\n")
        before = {p: (self.repo / p).read_text() for p in self.tree() if (self.repo / p).is_file()}
        out = self.tf("--apply")
        self.assertNotIn("create", out)
        self.assertNotIn("set ", out)
        self.assertEqual({p: (self.repo / p).read_text() for p in before}, before)

    def test_existing_config_with_another_forge_is_reported_not_changed(self):
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "teamflow.json").write_text(json.dumps({"forge": "local"}))
        git("remote", "add", "origin", str(Path(self.tmp.name) / "github.com" / "me" / "repo.git"), cwd=self.repo)
        out = self.tf("--forge", "github", env=self.fake_gh_env())
        self.assertIn("forge local", out)
        self.assertEqual(json.loads((self.repo / ".claude" / "teamflow.json").read_text()), {"forge": "local"})

    def test_github_uses_the_remote_the_config_names_unless_one_is_given(self):
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "teamflow.json").write_text(json.dumps({"forge": "github", "remote": "upstream"}))
        git("remote", "add", "upstream", str(Path(self.tmp.name) / "github.com" / "me" / "repo.git"), cwd=self.repo)
        env = self.fake_gh_env()
        self.tf("--forge", "github", env=env)  # no origin remote at all: only the configured one works
        out = self.tf("--forge", "github", "--remote", "origin", env=env, code=2)
        self.assertIn("remote 'origin'", out)

    def fake_gh_env(self, **state):
        fakebin = Path(self.tmp.name) / "fakebin"
        fakebin.mkdir(exist_ok=True)
        if not (fakebin / "gh").exists():
            (fakebin / "gh").symlink_to(FAKE_GH)
        self.state = Path(self.tmp.name) / "gh-state.json"
        self.state.write_text(json.dumps({"next": 1, "issues": {}, "prs": {}, "statuses": {}, "checks": {},
                                          "required": False, "reviews": [], "merges": [], "labels": ["type:bug"],
                                          "repo": {"allow_auto_merge": False, "delete_branch_on_merge": False},
                                          **state}))
        return {"PATH": f"{fakebin}{os.pathsep}{os.environ['PATH']}", "FAKE_GH_STATE": str(self.state)}

    def github_repo(self):
        git("remote", "add", "origin", str(Path(self.tmp.name) / "github.com" / "me" / "repo.git"), cwd=self.repo)

    def test_github_checks_gh_and_remote_before_writing_anything(self):
        git("remote", "add", "origin", "ssh://git@example.com/me/repo.git", cwd=self.repo)
        before = self.tree()
        out = self.tf("--forge", "github", "--apply", env=self.fake_gh_env(), code=2)
        self.assertIn("not a GitHub repository", out)
        self.assertEqual(self.tree(), before)

    def test_ruleset_waits_until_the_gate_workflow_is_on_the_base_branch(self):
        self.github_repo()
        out = self.tf("--forge", "github", "--apply", env=self.fake_gh_env())
        self.assertIn("run tf setup --forge github --apply again after", out)
        self.assertNotIn("rulesets", json.loads(self.state.read_text()))

    def test_a_rulesets_error_other_than_403_is_an_error(self):
        self.github_repo()
        out = self.tf("--forge", "github", "--apply", code=1,
                      env=self.fake_gh_env(rulesets_error=True, remote_files=[".github/workflows/gate.yml"]))
        self.assertIn("HTTP 500", out)
        self.assertNotIn("unenforced", out)

    def test_github_apply_sets_up_labels_settings_ruleset_and_ci(self):
        self.github_repo()
        env = self.fake_gh_env(remote_files=[".github/workflows/gate.yml"])
        self.tf("--forge", "github", "--apply", env=env)
        state = json.loads(self.state.read_text())
        self.assertIn("severity:high", state["labels"])
        self.assertEqual(state["labels"].count("type:bug"), 1)  # existing label not recreated
        self.assertEqual(state["repo"], {"allow_auto_merge": True, "delete_branch_on_merge": True})
        self.assertEqual([r["name"] for r in state["rulesets"]], ["teamflow: reviewed and gated"])
        self.assertTrue((self.repo / ".github" / "workflows" / "gate.yml").is_file())
        self.assertEqual(json.loads((self.repo / ".claude" / "teamflow.json").read_text()),
                         {"forge": "github", "remote": "origin"})
        out = self.tf("--forge", "github", "--apply", env=env)  # idempotent on GitHub too
        self.assertEqual(len(json.loads(self.state.read_text())["rulesets"]), 1)
        self.assertNotIn("create", out)

    def test_rulesets_unavailable_is_reported_not_fatal(self):
        self.github_repo()
        out = self.tf("--forge", "github", "--apply",
                      env=self.fake_gh_env(rulesets_forbidden=True, remote_files=[".github/workflows/gate.yml"]))
        self.assertIn("rulesets unavailable", out)
        self.assertNotIn("rulesets", json.loads(self.state.read_text()))


if __name__ == "__main__":
    unittest.main()
