# Local or GitHub

Agents reach Issues and PRs only through `tf`, which works in one of two
modes, set by `forge` in `.claude/teamflow.json`:

- **`local` (default).** No forge and no `gh` needed. Issues and PRs are
  records in the git common directory (`.git/teamflow/`), shared by every
  worktree and never committed or pushed. review-lead runs the gate and
  merges into `main` itself with `tf pr merge`. Separation of reviewer and author is a process
  rule.
- **`github` (opt-in).** Issues and PRs live on GitHub. The local
  duplicates switch off: a `teamflow/code-review` commit status on the
  reviewed head replaces review labels, CI's `gate` check replaces
  review-lead's second gate run. With the teamflow branch ruleset, GitHub
  enforces both: review-lead's `tf pr review --verdict APPROVE` arms
  auto-merge, pinned to the reviewed head, and GitHub merges once they pass
  (at once if the PR is already clean). `tf pr merge` is then only the
  fallback, when arming fails (`tf pr review` exits 4 with the verdict
  recorded). `tf pr review` arms nothing for a stacked PR or a repository
  whose rules do not name both `gate` and `teamflow/code-review`, and says so.
  Without such a ruleset (none, for example a private repository on a free
  plan; one lacking either context; or one `tf` cannot read), review-lead runs
  `tf pr merge`, which never arms auto-merge there: it waits for the `gate`
  check, checks it and the verdict itself, and merges directly: the same
  process control as local mode. Another required check (say `build`) does not
  stand in for `gate`: a red `gate` stops the merge. If such a check is red or
  pending, GitHub is expected to refuse the direct merge too (exit 1, where the
  old path queued it); read, not observed, and the fake `gh` does not model it.

To adopt GitHub mode, run `tf setup --forge github` (see [setup.md](setup.md)). The ruleset
requires the CI gate, so `tf setup` creates it only once
`.github/workflows/gate.yml` is on the default branch: after the setup PR
merges, run `tf setup --forge github --apply` once more from the main
worktree. Rulesets need a public repository or a paid plan; without them
`tf setup` says so and GitHub mode runs unenforced.

On GitHub, `tf pr gate` and `tf pr merge` can wait for CI (`tf pr review`
has no wait, read in `bin/tf`), bounded by
`TF_GATE_WAIT` and polled every `TF_GATE_POLL`; if your CI takes long, see
`tf --help` for both settings and how long the wait can run.

`tf mode` then prints `github`. If `gh` is missing, logged out, or the
remote isn't GitHub, every `tf` command stops with exit 2 rather than
falling back to local.

If your token for the repository is kept in a variable not named `GH_TOKEN`,
override `GH_TOKEN` for one command (never write the token itself in the
command; it would land in your shell history):

```bash
GH_TOKEN="$OTHER_VAR" tf issue view 12      # or: env GH_TOKEN="$OTHER_VAR" tf issue view 12
```

This works because `tf` does not read a token (`bin/tf` contains no
`GH_TOKEN` or `GITHUB_TOKEN`, read); it runs `gh`, which reads `GH_TOKEN` from
its environment (read). Run: `tf issue view` and `tf pr view` (the `env` form),
`tf issue view` (the shell-prefix form), `tf issue create` and
`tf issue comment` (shell-prefix form), all returning correct data, and a bad
value in either form makes `tf` exit 2 with "gh is not authenticated", so the
overridden value is the one used. Not verified: the other write commands
(`tf issue edit`, `tf issue close`, `tf pr create`, `tf pr claim`,
`tf pr review`, `tf pr merge`, `tf pr release`); they go through the same
`gh` calls, a reading of `bin/tf`, not a run. The push inside `tf pr create` is
a `git push` to the configured remote (read, not run), so it authenticates
with git's credential for that remote (an SSH key for an SSH remote), not with
`GH_TOKEN`; for an HTTPS remote it depends on your git credential helper, not
verified. The override applies to that one command. Whether starting the
session as `GH_TOKEN="$OTHER_VAR" claude --agent teamflow:manager` makes every
agent's `tf` use that token is not verified: a profile that sets `GH_TOKEN`
could override it in each command's shell.
