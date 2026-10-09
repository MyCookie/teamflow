# teamflow

The teamflow Claude Code plugin. Its own development runs on teamflow in
GitHub mode (`.claude/teamflow.json`).

## Hard rules
- `./scripts/gate.sh` passes, including `claude plugin validate --strict`
  for the plugin and the marketplace where `claude` is installed.
- A change to `bin/tf` or `bin/teamflow-config` comes with a test in
  `tests/` that fails without it.
- Agent prompts and the workflow skill never call `gh` directly: Issues and
  PRs go through `tf`, so both forge modes keep working.
- Docs state only what was run or read. Anything unverified says so.
