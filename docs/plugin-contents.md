# What's in the plugin

| Path | What it is |
|---|---|
| `agents/` | The manager, three leads, and seven workers (researcher, implementer, five specialist reviewers), named `teamflow:<agent>` |
| `archive/` | `code-reviewer.md`, retired from the pipeline (#258 D3), kept outside `agents/`, so not among the agents the plugin ships (not checked by loading the plugin) |
| `skills/workflow/` | The pipeline rules every agent follows |
| `hooks/` | The spawn hook (`hooks/check-spawn`, `hooks/hooks.json`): denies any spawn outside the spawn table, at every depth |
| `bin/tf` | Issues and PRs in either mode; `tf -h` lists every command |
| `bin/teamflow-config` | Print the repository's effective configuration |
| `templates/` | `gate.sh` and the PR template for every repository; `ci.yml` and `branch-ruleset.json` for GitHub mode |
| `tests/` | `python3 -m unittest discover -s tests` |

`bin/` is on the shell `PATH` while the plugin is enabled, for leads and
subagents alike.

## Models on this branch (demo only)

`demo/cheaper-models` is a one-off demo branch with lower-cost models. It is
not merged into `main`. Each agent runs one tier below its model on `main`:

| Agents | `main` | This branch |
|---|---|---|
| manager, research-lead, impl-lead, review-lead | `claude-opus-5-5` | `claude-sonnet-5-5` |
| researcher, implementer, the five specialist reviewers | `claude-sonnet-5-5` | `claude-haiku-5-5` |

The `model:` line in each `agents/*.md` file sets the agent's model.
