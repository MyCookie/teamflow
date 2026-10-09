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
3. **Labels** (`gh issue create` fails on a missing one):
   ```bash
   for l in severity:high severity:medium severity:low \
            area:architecture area:security area:quality area:docs area:simplicity area:research \
            type:feature type:bug type:task \
            needs-discussion review:approved review:changes-requested review:in-progress; do
     gh label create "$l" 2>/dev/null || true
   done
   ```
4. **Loop bounds** (optional). Defaults apply without a file; override any of
   them in `.claude/teamflow.json`:
   ```json
   { "loop": { "max_iterations": 3, "exit_severity_threshold": "medium",
               "human_checkpoint": "every_cycle", "max_open_issues_to_continue": 0 } }
   ```
   `teamflow-config` prints the effective values.
5. **Ignore runtime state:** add `.manager-state.json`, `.claude/worktrees/`
   and `.env` to `.gitignore`.

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
| `bin/open-pr` | Push the branch and open its PR, refusing a dirty tree, `main`, or an unedited template |
| `bin/review-setup` | Prepare a code-reviewer worktree for one branch |
| `bin/teamflow-config` | Print the repository's effective configuration |
| `templates/` | `gate.sh` and the PR template, copied into each repository |

`bin/` is on the shell `PATH` while the plugin is enabled, for leads and
subagents alike.
