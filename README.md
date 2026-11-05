# teamflow

A Claude Code plugin that runs a three-team agent pipeline in any repository:
research turns goals into Issues, implementation works them in isolated
worktrees, and review takes part in every PR before it merges, under a
manager that routes each handoff. Every PR is reviewed by the review team: a
fresh review-lead runs five fresh specialist reviewers, records the one
verdict, and is the only actor that arms or runs a merge. A post-merge
review that files follow-up Issues is optional and runs only when you ask
for it.

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

## Local or GitHub

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

To adopt GitHub mode, run `tf setup --forge github` as above. The ruleset
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

## Run

One session, started from the repository root:

```bash
claude --agent teamflow:manager     # then state your goal
```

The manager spawns research-lead, impl-lead and review-lead as subagents, and
research-lead and impl-lead spawn their workers; review-lead spawns the five
specialists. Every handoff runs through the manager, including each PR's
review rounds: impl-lead opens a PR and returns, the manager spawns a fresh
review-lead for it, and the manager resumes impl-lead with the verdict.
A PR is reviewed and merged before the batch is reported; a
post-merge review (the manager's route "Review what we just built") runs only
if you ask. A lead can still be started alone, for example
`claude --agent teamflow:impl-lead`, and then reports to you in that session;
a lone impl-lead has no manager to hand its PRs to, so it reports them open
and unreviewed. Per-PR review and the optional loop are read in
`skills/workflow/SKILL.md` and `agents/`, not run live (see **What was run**).
The workflow rules live in the `teamflow:workflow` skill. Subagents preload
it; the manager and the leads load it as their first step.

**What was run.** On 2026-11-03, Claude Code 2.1.308, `claude -p` from a
checkout of this branch (details under Headless). Observed: the plugin loads
from the checkout; with `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` the manager
stops at startup, names the variable and spawns nothing; the spawn hook
allows manager to impl-lead and impl-lead to implementer, and denies
review-lead to implementer. One interactive run, with the human at the
terminal in auto permission mode (Claude Code 2.1.308, a checkout at
a554110), went from goal to a merged PR: the manager had a plan-only
impl-lead return the plan and asked; after "yes, approved" it spawned a fresh
impl-lead with the table verbatim; that lead spawned the implementer (depth
2), which opened PR #246; the lead spawned a fresh code-reviewer in an
isolated worktree (that was the pipeline before per-PR review moved to the
review team; `teamflow:code-reviewer` is now archived in
`archive/code-reviewer.md` and no longer spawned), which recorded APPROVE on head 60d47f7; #246 merged (merge
64e3f42 on `main`, local and origin), #240 closed, and the run stopped after
implementation. The lead's report reached the manager only after the
reviewer was done: it ended its turn while each worker ran and was resumed
when the worker finished. That timing comes from hook events and is observed
for one run only. **Not run:** the subagent panel, the update path,
`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`, a restart, a per-PR round with the
review team (review-lead and its five specialists, as merged on `main`; only
the old code-reviewer path above ran), a post-merge review and its loop, a
three-layer spawn chain (the design needs none), and a headless run to a
merged PR (see Headless). The spawn hook's table was read in
`hooks/check-spawn` for the new layout; the observed hook allows above are
from before it.

**Requirements.** The versions and defaults are from the Claude Code docs and
the research on Issue #21, not tested with teamflow, except that the depth
stop was observed.

- Claude Code 2.1.304 or later.
- Leave fork mode on: do not set `CLAUDE_CODE_FORK_SUBAGENT=0`. It is on by
  default from v2.1.302.
- Nesting needs `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` at 2 or more: the
  manager, a lead, its worker. No handoff needs a third layer, because every
  handoff runs through the manager (`skills/workflow/SKILL.md`, Teams, *Spawn
  depth*); a three-layer chain was never run (the spike, #259, was closed as
  not needed). The variable is 3 by default from v2.1.219. The manager stops
  at startup if it reads `1` (observed under `-p`, above).

**Restart.** The manager's rules for a process start, `--resume` included
(`agents/manager.md`, Startup), in order: it first closes any still-open
tracking Issue it recorded. Then, with no stored goal, it takes your goal as
new (rule B). If its last message was a question to you, your message answers
it and it carries on (rule C, which is how `claude -p --resume <session id>
"yes"` works). If a non-auto-approved iteration has an unconfirmed release,
it asks you to confirm or skip the update (rule U). Otherwise it stops and
asks what to do, showing the goal, the iteration, the recorded PRs and
releases, `tf pr list` and the worktrees (rule D). Not run live, beyond the
headless resume described below.

**Headless (`claude -p`).** Run on 2026-11-03 with Claude Code 2.1.308,
from a checkout of this branch: `--plugin-dir` for the checkout and for
`ponytail` (`mattpocock-skills` came from its user-scope install), `PATH` with the checkout's `bin/` first, the prompt on stdin.
The plan-then-resume path ran as far as the first worker. **A headless run
from goal to merged PR is not verified.**

- Both dependencies, `ponytail` and `mattpocock-skills`, must load. In the
  live runs only `ponytail` got its own `--plugin-dir`; `mattpocock-skills`
  loaded from its user-scope install (observed). Read `plugin_errors` in the
  `init` event. With only teamflow's
  `--plugin-dir`, from another path, teamflow failed with
  `dependency-unsatisfied` (`ponytail@ponytail`) and the run still exited 0
  (seen in a clone on 2026-11-02).
- Permission prompts can't be answered, so pass `--permission-mode` or
  `--allowedTools`.
- **Workers cannot work under `-p` as observed.** Claude Code refused a Bash
  command that `cd`s into a directory and then runs git, even with
  `Bash(cd *)` and `Bash(git *)` in `--allowedTools`; it treats that as a
  safety check. The implementer's first command, `cd <worktree> && ...`, was
  refused, so nothing was implemented, reviewed or merged in that run. Only
  an interactive session can approve such a command. In the interactive
  auto-mode run above, the workers' `cd <worktree> && git ...` commands ran.
  Headless runs stop at the first worker `cd`; an interactive session gets
  past it.
- **No stored state under `-p`.** `Write` of `.manager-state.json` was
  refused as "a sensitive file", even with `Write` in `--allowedTools`, and a
  path rule (`Write(.manager-state.json)`) was refused too ("you haven't
  granted it yet"). By decision on Issue #21, a headless run keeps its state
  only within a session and its `--resume`. A fresh headless run finds
  nothing stored, so, with no stored goal (`agents/manager.md`, Startup rule
  B), it treats its prompt as a new goal. Not run live.
  Interactively, in auto mode, `Write` of `.manager-state.json` failed three
  times ("The server-side auto mode classifier gave no verdict (it skipped
  this action) ... This is a hard failure"). It succeeded only after the
  human switched the session to the default permission mode and approved the
  write prompt (the switch is in the transcript; that it was done to approve
  the write is inferred). So under auto mode, expect to switch or approve
  each time the state file is written. In that run the manager held the
  approved plan until the state file was written, its own judgement.
- A plan that needs approval ends the run at the question. Continue with
  `claude -p --resume <session id> "<answer>"`. Observed: the manager sent
  impl-lead the plan-only brief, got the table back, declined auto-approval
  for an Issue with no `severity:` label, and ended on the question. On
  `--resume "yes"` it spawned a fresh impl-lead with "Plan approved", and
  that lead spawned the implementer. A lead spawned in the background gives
  the manager a new turn when it finishes, so expect several `result` events
  in stream-json.
- Set `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` above your longest expected lead
  run. The documented default, `600000`, ends the idle wait and drops the
  partial result, and `0` waits indefinitely. This is from the Claude Code
  docs, not tested with teamflow.
- Leads return after their workers where the harness makes them wait:
  interactive, and `-p` or the SDK with fork mode on. Teamflow does not
  support `-p` with fork mode off. A restarted run stops and asks, except a
  fresh headless restart, which keeps no state and starts at Phase 0.

**After an update,** start a fresh `claude --agent teamflow:manager`; never
`--resume` the pre-update session. The resumed session keeps the old prompt
in its history while the new agents and `tf` load. That is from the Claude
Code docs, untested.

**Agent teams.** `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` is not recommended
and is untested with teamflow. If it is on and the leads behave differently,
set it to `0`.

**Settings file.** After a `-p` run that behaves as if a setting is missing,
run `claude doctor` to see what it dropped. Under `-p`, a broken
`.claude/settings.json` gets no dialog: Claude Code skips it and continues
(settings.md:206). A managed settings document that cannot be parsed as a
JSON object instead stops Claude Code at startup, under `-p` too
(errors.md:5921, 5935). A schema problem in a parseable managed document does
not (errors.md:5937). The cites are pages of the Claude Code docs at
`https://code.claude.com/docs/en/`. `tf setup` no longer checks
`.claude/settings.json`; this line replaces that check.

## What's in the plugin

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

## Release

A merged change reaches the agents only after a release. Sessions run the
installed copy under `~/.claude/plugins/cache/`, not the repository, and with
marketplace auto-update off, as on the maintainer's install, nothing moves
that copy forward on its own. The release rule itself (when a release is
needed, the bump, the sequencing, the release line) is stated once, in
[`skills/workflow/SKILL.md`](skills/workflow/SKILL.md), Handoffs, "Release".
What follows is what a human does.

- **Where the version lives.** `version` in `.claude-plugin/plugin.json`,
  and nowhere else. It must stay: without it `claude plugin validate
  --strict` failed on a scratch copy.
- **Reaching the agents.** When the manager reports a release, run
  `claude plugin update teamflow@teamflow --scope project`, then start a
  fresh manager session. Agents never run the update, since it changes your
  install. For an auto-approved run the manager states the update in its
  final report and waits for no answer. Otherwise it asks you to confirm or
  skip it before review.
- **Not tested.** Not verified here: these points come from the Claude Code
  docs, which a research-lead session read and this README did not re-check
  (the manifest's `version` overriding the marketplace entry's, the cached
  copy staying until the string changes, whether auto-update is on by default
  for a marketplace, and the update command's behaviour), and from one
  scratch-copy run of `claude plugin validate --strict` without `version`.
  Whether `/reload-plugins` refreshes subagent definitions is untested, so a
  fresh session is required. No live impl-lead or manager has run the release
  sequencing, the four release-line forms (a version line can also accompany
  a named unmerged PR), the manager's check of the line, or the main-worktree
  update. The Queued merge procedure (`tf pr gate`, then `tf pr view`,
  with one re-read) has not been run live either, nor
  `tf pr gate` on an already-queued auto-merge, nor the `merge state:` value
  `behind` (only `blocked` on an open PR and `unknown` on a merged PR were
  observed).
- **Arming on APPROVE, not tested against GitHub.** `tf pr review` arming
  auto-merge, exit 4, and the no-arm notes were tested only against a fake
  `gh` (`tests/test_tf.py`, `test_approve_*` and related). Unverified: all of
  it against real GitHub; that `--auto` merges an already-clean PR at once
  (read from gh's source, modelled in the fake); what a second `--auto` on an
  armed PR does (spike #226 was not run; the exit-4 fallback `tf pr merge` can
  issue one); whether auto-merge stays armed across a rework push; the rules
  endpoint on a repository without ruleset support (`tf pr review` treats a
  failed read as exit 4, `tf pr merge` says it could not read the ruleset and
  takes its own path); and classic branch protection, which `tf` does not detect. The
  `tf pr merge` paths for a ruleset lacking a context or unreadable are also
  tested only against the fake `gh`.

No tag, changelog or extra gate step is needed; `git log` is the record.

## License

Copyright 2026 Ashish Kansara. Licensed under the Apache License, Version 2.0; see [LICENSE](LICENSE).
