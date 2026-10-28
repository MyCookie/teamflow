---
name: setup
description: >
  Set a repository up for teamflow, or check that a teamflow setup works.
  Use when teamflow is enabled in a repository that has no
  .claude/teamflow.json or scripts/gate.sh, when adopting GitHub mode, or
  before a first pipeline run.
---

# Set up a repository for teamflow

A plugin cannot change project settings, so `tf setup` applies what the
plugin cannot. Prepare it on a branch in its own worktree, like any other
change, so the main worktree stays on the base branch:

```bash
git worktree add ../<repo>-setup -b chore/teamflow-setup
cd ../<repo>-setup
```

## 1. See the plan

```bash
tf setup                      # local mode: no forge needed
tf setup --forge github       # GitHub mode; remote: --remote, else teamflow.json, else origin
```

Without `--apply` it is a dry run: it prints `would ...` for each change
and `ok: ...` for what is already in place, and changes nothing.

## 2. Apply it

```bash
tf setup --apply
tf setup --forge github --apply
```

GitHub mode creates labels, turns on auto-merge and deletion of merged
branches, and (once the CI workflow is on the default branch) creates the
`teamflow: reviewed and gated` ruleset on the shared repository. Those are visible to everyone with access: get the
human's explicit go-ahead before running `--apply` with `--forge github`.

`tf setup` never overwrites a file and never commits. Running it again is
safe and changes nothing that is already in place. On a private repository
on a free plan, rulesets are unavailable: it says so, and GitHub mode then
runs unenforced, with `tf` checking the gate and the verdict itself.

## 3. Finish by hand

1. Add the project's lint and test steps to `scripts/gate.sh`, and in GitHub
   mode the toolchain to `.github/workflows/gate.yml`. Make the gate green:
   on a red base branch every review fails.
2. Commit the files on the setup branch and merge it the way the repository
   merges today (a GitHub PR, or a local merge). This one merge happens
   before teamflow runs, so it does not go through `tf`.
3. GitHub mode: the ruleset requires the CI gate, so `tf setup` creates it
   only once `.github/workflows/gate.yml` is on the default branch; until
   then it prints `later: ...`. After the setup branch merges, update the
   main worktree and run `tf setup --forge github --apply` there once more.
4. Start the leads (README, "Run").

## 4. Check that it works

Each check is cheap and catches a different failure:

1. `/agents` lists the teamflow agents.
2. In the manager session, `ListAgents` shows the three leads. If not, the
   sessions started from different directories, or `crossSessionInbound`
   in `.claude/settings.json` is not `accept`.
3. `tf mode` prints the intended mode, and `teamflow-config` the intended
   loop bounds.
4. Asked to edit a source file, the manager refuses.
5. A trivial Issue (a typo) goes through the implementation path: impl-lead
   shows a plan and waits, the implementer works in its own worktree and
   opens the PR with `tf pr create`, and exactly one code-reviewer claims,
   reviews and merges it.

Afterwards remove leftover worktrees (`git worktree list`) and the
`worktree-agent-*` branches that isolated subagents leave behind.
