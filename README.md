# teamflow

A Claude Code plugin that runs a three-team agent pipeline in any repository:
research turns goals into Issues, implementation works them in isolated
worktrees, and review files follow-up Issues, under a manager that governs
the review-implement loop. Every PR is reviewed by a fresh, independent
`code-reviewer`, the only actor allowed to merge.

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
can't: cross-session messaging in `.claude/settings.json`, the gate and PR
template, `.gitignore` entries and `.claude/teamflow.json`; with
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

Then add the project's lint and test steps to `scripts/gate.sh`, commit,
and merge the branch the way you merge today. teamflow's own review flow
starts once this is on the base branch. The `teamflow:setup` skill walks
through it and lists the checks that the team works.

**Settings** live in `.claude/teamflow.json`; defaults apply for anything
unset, and `teamflow-config` prints the effective values:

```json
{ "forge": "local", "remote": "origin", "base": "main", "tdd": "required",
  "loop": { "max_iterations": 3, "exit_severity_threshold": "medium",
            "human_checkpoint": "every_cycle", "max_open_issues_to_continue": 0 } }
```

`tdd` is `required` or `recommended`: how strictly reviewers grade missing
red/green evidence. `tf` and `teamflow-config` read the file from the main
worktree, which must stay on the base branch (`tf` stops otherwise), so a
PR under review can't change the rules its own review runs under. Work on
other branches in separate worktrees.

## Local or GitHub

Agents reach Issues and PRs only through `tf`, which works in one of two
modes, set by `forge` in `.claude/teamflow.json`:

- **`local` (default).** No forge and no `gh` needed. Issues and PRs are
  records in the git common directory (`.git/teamflow/`), shared by every
  worktree and never committed or pushed. The code-reviewer runs the gate and
  merges into `main` itself. Separation of reviewer and author is a process
  rule.
- **`github` (opt-in).** Issues and PRs live on GitHub. The local
  duplicates switch off: a `teamflow/code-review` commit status on the
  reviewed head replaces review labels, CI's `gate` check replaces the
  reviewer's second gate run. With the teamflow branch ruleset, GitHub
  enforces both and merges once they pass. Without a ruleset (for example a
  private repository on a free plan), `tf` checks them itself and merges:
  the same process control as local mode.

To adopt GitHub mode, run `tf setup --forge github` as above. The ruleset
requires the CI gate, so `tf setup` creates it only once
`.github/workflows/gate.yml` is on the default branch: after the setup PR
merges, run `tf setup --forge github --apply` once more from the main
worktree. Rulesets need a public repository or a paid plan; without them
`tf setup` says so and GitHub mode runs unenforced.

`tf mode` then prints `github`. If `gh` is missing, logged out, or the
remote isn't GitHub, every `tf` command stops with exit 2 rather than
falling back to local.

## Run

One terminal per lead, from the repository root; start the manager last.

```bash
claude --agent teamflow:research-lead --name research-lead
claude --agent teamflow:impl-lead     --name impl-lead
claude --agent teamflow:review-lead   --name review-lead
claude --agent teamflow:manager       --name manager     # then state your goal
```

The workflow rules live in the `teamflow:workflow` skill. Subagents preload
it; leads load it as their first step.

## What's in the plugin

| Path | What it is |
|---|---|
| `agents/` | The manager, three leads, and eight workers, named `teamflow:<agent>` |
| `skills/workflow/` | The pipeline rules every agent follows |
| `bin/tf` | Issues and PRs in either mode: create, list, claim, gate, diff, review, merge |
| `bin/teamflow-config` | Print the repository's effective configuration |
| `templates/` | `gate.sh` and the PR template for every repository; `ci.yml` and `branch-ruleset.json` for GitHub mode |
| `tests/` | `python3 -m unittest discover -s tests` |

`bin/` is on the shell `PATH` while the plugin is enabled, for leads and
subagents alike.

## License

Copyright 2026 Ashish Kansara. Licensed under the Apache License, Version 2.0; see [LICENSE](LICENSE).
