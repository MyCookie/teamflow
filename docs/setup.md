# Install and set up

## Install

```
/plugin marketplace add MyCookie/teamflow
/plugin install teamflow@teamflow
```

teamflow depends on `ponytail@ponytail` (the simplicity-reviewer's engine) and
`mattpocock-skills@mattpocock`. Installing teamflow installs both from their
own marketplaces. A copy synced from claude.ai (`ponytail@synced`) does not
satisfy the dependency; install the marketplace copy.

To try a local checkout without installing:

```bash
claude --plugin-dir /path/to/teamflow \
       --plugin-dir ~/.claude/plugins/marketplaces/ponytail \
       --plugin-dir ~/.claude/plugins/marketplaces/mattpocock
```

## Set up a repository

A plugin can't change project settings, so `tf setup` applies what it
can't: the gate and PR template, `.gitignore` entries and
`.claude/teamflow.json`; with
`--forge github` also the CI workflow, labels, repository settings and the
branch ruleset. It is a dry run unless given `--apply`, never overwrites a
file, never commits, and is safe to run again. Prepare the setup on a
branch, like any other change:

```bash
git worktree add ../myrepo-setup -b chore/teamflow-setup
cd ../myrepo-setup
tf setup                      # dry run; add --forge github for GitHub mode
tf setup --apply
```

Then add the project's lint and test steps to `scripts/gate.sh` (in GitHub
mode also the toolchain to `.github/workflows/gate.yml`), commit, and merge
the branch the way you merge today. teamflow's own review flow starts once
this is on the base branch. The `teamflow:setup` skill walks through it and
lists the checks that the team works.

**Auto mode.** A manager session reported on 2026-10-27 (Claude Code
version not recorded; not re-run here) that auto mode refused `tf issue
close` ("[External System Writes]") until `"Bash(tf *)"` was in
`permissions.allow`, and refused reviewer `tf pr merge` runs ("[Merge Without
Review]") even with the rule in the shared file, cause unverified. A count
over that project's session transcripts (a research-lead, reported on #227;
not re-run here) found plain `tf pr merge <N>` refused 0 times and run 21
times, and `tf pr merge <N>` with more on the same line (for example `; echo
"exit=$?"`) refused 10 times and run 42 times. That is a correlation, not an
established cause. The reasons and rule syntax were not checked against
Claude Code's docs. In GitHub mode with the ruleset, `tf pr review
--verdict APPROVE` now arms auto-merge itself, so the reviewer runs no merge
command on the normal path (decided on #227; the merging actor is now
review-lead, whose prompt carries the same steps, read, not run). Auto mode reads the command
text, not what `tf` runs inside it, and whether it treats `tf pr review`
differently from `tf pr merge` is untested. If auto
mode stops your sessions, add the rule to an existing `permissions.allow` in
the repository root where you start the manager:

- `.claude/settings.json` is committed, so every worktree and collaborator
  gets the rule. It matches every `tf` subcommand, `tf pr merge` and `tf
  setup --apply` included; that it lets a merge pass is unverified. teamflow's
  own repository carries it here; whether it also needs `settings.local.json`
  is untested.
- `.claude/settings.local.json` is per user and uncommitted; a later worktree
  has no copy (checked in a scratch repository), and `tf setup` does not
  gitignore it.

The choice is yours. Other cases are untested.

**Settings** live in `.claude/teamflow.json`; defaults apply for anything
unset, and `teamflow-config` prints the effective values:

```json
{ "forge": "local", "remote": "origin", "base": "main", "tdd": "required",
  "teamflow_auto_approve": "low",
  "loop": { "exit_severity_threshold": "medium", "max_open_issues_to_continue": 0 } }
```

`tdd` is `required` or `recommended`: how strictly reviewers grade missing
red/green evidence. `teamflow_auto_approve` is `low` (default) or `none`:
under `low` the manager can skip some human gates for a batch of only
`severity:low` Issues; `none` turns that off. The conditions, what is
skipped and what still waits for you are defined in the workflow skill
(`skills/workflow/SKILL.md`, Handoffs, Auto-approval). This flow has not been
run live.

**Migrating:** `loop.max_iterations` and `loop.human_checkpoint` are removed.
A `.claude/teamflow.json` that still sets either makes `teamflow-config`, and
so every `tf` command that reads the config, exit 2 with `unknown key '...'`
(the test covers `teamflow-config` directly); delete the key. `tf setup` is the
exception: it does not call `teamflow-config`, reading only `forge` from the
file, so it does not exit 2 on a removed key (it does exit 2 on invalid JSON).
No iteration cap remains, by a human decision. Each PR has its own loop
(implement, then review and rework rounds until it merges or is escalated at
five rounds); the review-implement loop runs only after a post-merge review
you asked for. When that loop ends or pauses is in the manager's loop check
(`agents/manager.md`); these rules have not been run live. Post-merge review
has no config key: it is off unless you ask (#258 D6).

`tf` and `teamflow-config` read the file from the main worktree, which must
stay on the base branch (`tf` stops otherwise; `tf setup` is the exception,
it runs on a setup branch), so a PR under review can't change the rules its
own review runs under. Work on other branches in separate worktrees.
