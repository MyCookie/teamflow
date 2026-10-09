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

A plugin can't change project settings, so each repository needs:

1. **Messaging between sessions.** In `.claude/settings.json`:
   ```json
   { "crossSessionInbound": "accept" }
   ```
2. **The gate.** Copy `templates/gate.sh` to `scripts/gate.sh`, add the
   project's lint and test steps, and make it green on `main`. Copy
   `templates/pull_request_template.md` to `.github/`.
3. **Loop bounds** (optional). Defaults apply without a file; override any of
   them in `.claude/teamflow.json`:
   ```json
   { "loop": { "max_iterations": 3, "exit_severity_threshold": "medium",
               "human_checkpoint": "every_cycle", "max_open_issues_to_continue": 0 } }
   ```
   `teamflow-config` prints the effective values.
4. **Ignore runtime state:** add `.manager-state.json`, `.claude/worktrees/`
   and `.env` to `.gitignore`.

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
  reviewer's second gate run, and GitHub merges once both pass. A branch
  ruleset enforces it.

To adopt GitHub mode in a repository:

1. `.claude/teamflow.json`: `{ "forge": "github", "remote": "<the GitHub remote>" }`
2. Copy `templates/ci.yml` to `.github/workflows/gate.yml`, add the
   toolchain steps, and get it green on `main`.
3. Allow auto-merge and delete merged branches:
   `gh api -X PATCH repos/OWNER/REPO -F allow_auto_merge=true -F delete_branch_on_merge=true`
4. Apply the ruleset (requires a public repository or a paid plan):
   `gh api -X POST repos/OWNER/REPO/rulesets --input templates/branch-ruleset.json`
5. Create the labels; `gh issue create` fails on a missing one:
   ```bash
   for l in severity:high severity:medium severity:low \
            area:architecture area:security area:quality area:docs area:simplicity area:research \
            type:feature type:bug type:task needs-discussion; do
     gh label create "$l" 2>/dev/null || true
   done
   ```
6. `tf mode` prints `github`. If `gh` is missing, logged out, or the remote
   isn't GitHub, every `tf` command stops with exit 2 rather than falling
   back to local.

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
