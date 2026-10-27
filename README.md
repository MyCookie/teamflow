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

**Auto mode.** In one GitHub-mode session in auto mode, the classifier
refused `tf issue close 114` as an external system write ("[External System
Writes]"); read-only `tf issue view` and the `tf setup` dry run were not
refused. After `"Bash(tf *)"` was added to `permissions.allow` in
`.claude/settings.local.json`, the same command exited 0. If auto mode stops
your sessions the same way, add the rule once:

```json
{ "permissions": { "allow": ["Bash(tf *)"] } }
```

`.claude/settings.local.json` is per user and uncommitted, and is the file
that was tested. The shared `.claude/settings.json` is committed and applies
to everyone who clones; the rule there is untested, and which file to use is
your decision. The rule allows every `tf` subcommand, including `tf pr merge`
and `tf setup --apply`, and in the shared file it grants that to every
collaborator's sessions. `tf setup` does not add `settings.local.json` to
`.gitignore` (it adds only `.manager-state.json`, `.claude/worktrees/` and
`.env`), so ignore it yourself. Not verified: whether a session already
running picks the rule up without a restart, whether subagents in other
worktrees inherit it, whether other `tf` writes or local mode are ever
refused (only `tf issue close` in GitHub mode was observed).

**Settings** live in `.claude/teamflow.json`; defaults apply for anything
unset, and `teamflow-config` prints the effective values:

```json
{ "forge": "local", "remote": "origin", "base": "main", "tdd": "required",
  "teamflow_auto_approve": "low",
  "loop": { "max_iterations": 3, "exit_severity_threshold": "medium",
            "human_checkpoint": "every_cycle", "max_open_issues_to_continue": 0 } }
```

`tdd` is `required` or `recommended`: how strictly reviewers grade missing
red/green evidence. `teamflow_auto_approve` is `low` (default) or `none`:
under `low` the manager skips the plan approval and the loop checkpoint for
a batch of only `severity:low` Issues, with conditions the workflow skill
defines; `none` turns it off. This flow has not been run live. `tf` and `teamflow-config` read the file from the main
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

## Release

A merged change reaches the agents only after a release. Sessions run the
installed copy under `~/.claude/plugins/cache/`, not the repository. With
marketplace auto-update off, as on the maintainer's install (their answer to
#33, Q4), nothing moves that copy forward on its own; whether it is on by
default for a marketplace is not verified here, and with it on, a version
bump would arrive without `claude plugin update`.

The release rule itself (when a release is needed, the bump, the branch,
the sequencing, the release line and what the manager asks of you) is stated
once, in [`skills/workflow/SKILL.md`](skills/workflow/SKILL.md), Handoffs,
"Release". What follows is only what a human needs.

- **Where the version lives.** `version` in `.claude-plugin/plugin.json`,
  and nowhere else. The marketplace entry carries none; the manifest's
  version overrides the entry's (Claude Code docs, plugins-reference.md,
  "Metadata precedence", as quoted in #33; not re-checked here).
- **Why it stays.** With a `version` in the manifest, Claude Code keeps every
  user on the cached copy until the string changes (docs, plugins/loading.md,
  "Versions and updates", as quoted in #33). Leaving it out would use the
  commit SHA instead, but on a scratch copy without it, `claude plugin
  validate --strict` (part of `./scripts/gate.sh`) failed with "version: No
  version specified" (research-lead's run for #33; not re-run here).
- **Reaching the agents.** When the manager reports a release, run the
  update command it gives you, then fully restart every teamflow session.
  Agents do not run the update: it changes your install outside the
  repository. The manager waits for you to confirm, or to skip, before the
  review phase.
- **Not tested.** The update command's behaviour (it refreshes the
  marketplace and installs the new copy when the version changed) is taken
  from the Claude Code docs, not run here. Whether `/reload-plugins`
  refreshes subagent definitions is untested, so a full restart is required.
  The release sequencing, the four release-line forms, the manager's check of
  the line and the main-worktree update step have not been run by a live
  impl-lead and manager. Also not run: `tf pr gate` on a PR whose
  auto-merge is already queued, and the `merge state:` value `behind`
  from `tf pr view` (only `blocked` on an open PR and `unknown` on a merged
  PR were observed; `behind` is expected, not observed). The
  Queued merge procedure as a whole, and whether the one re-read of
  `tf pr view` is enough given the unmeasured merge delay, have not been
  run by a live impl-lead.

No tag, changelog or extra gate step is needed; `git log` is the record.

## License

Copyright 2026 Ashish Kansara. Licensed under the Apache License, Version 2.0; see [LICENSE](LICENSE).
