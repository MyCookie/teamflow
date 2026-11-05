---
name: workflow
description: >
  The teamflow pipeline rules: roles, routing, handoffs, messaging, Issue and
  research formats, branches, commits, the gate, PRs, and the per-PR review and
  merge. Load before any research, implementation, review, or orchestration
  work in a repository that uses teamflow.
---

# teamflow workflow

A three-team pipeline (research, implementation, review) coordinated by a
manager. These rules apply to every teamflow agent; the project's own
CLAUDE.md adds project facts and hard rules on top.

Two invariants: **`main` is always green**, and **nothing merges on its
author's say-so.**

## Teams

One session: `claude --agent teamflow:manager`, which spawns the three
leads. A lead can run alone (`claude --agent teamflow:<lead>`) and then
reports to the human. A lone impl-lead has no manager to hand its PRs to
review: it opens them, reports them as open and unreviewed, and stops. The
human starts a review (a lone review-lead in per-PR mode, or the manager).

| Agent | Spawns | Job |
|---|---|---|
| manager | the three leads | Routes goals, runs every handoff (including each PR's rounds between impl-lead and review-lead), counts each PR's rounds, governs the optional review-implement loop |
| research-lead | `researcher` | Decomposes goals into Issues; implements nothing |
| impl-lead | `implementer` | One worktree and PR per non-overlapping unit; implements and reworks, never reviews |
| review-lead | five specialist reviewers | Reviews each PR before it merges (per-PR mode): claims it, checks the gate, records the one verdict, arms or runs the merge. On the human's request, diff-reviews merged PRs and files follow-up Issues (diff-review mode) |

The review team takes part in each PR before it merges, so a merge is never
the author's say-so. `teamflow:code-reviewer` is no longer part of the
pipeline (archived, not deleted; #258 D3). The checks it made are the review
team's now: the gate, the Issue's acceptance criteria, test integrity,
red/green, commits and checker changes. review-lead is accountable that each
is covered before it records a verdict.

**Spawn depth.** Every handoff runs through the manager (#258 D1), so no lead
spawns another lead: the manager is the main thread, the leads are layer 1,
their workers layer 2. These rules need no third layer. A chain of three
layers has never been run in teamflow (the spike, #259, was closed as not
needed), so no rule here depends on it.

## Routing (manager)

| Input | Route to |
|---|---|
| Vague goal, feature idea, open-ended question | Research |
| Specific task with no existing Issue | Research |
| Specific Issue number(s), "fix #N" | Implementation; each PR then goes through per-PR review before it merges |
| "Review what we just built" | Review, diff-review mode (post-merge, optional: only on the human's request) |
| A PR the implementation team did not open | Review, per-PR mode, as merge-review (outside the loop) |

## Handoffs

- **Research → Implementation.** research-lead's final report to the manager:
  tracking Issue number, the numbers of the Issues filed, priority order. The
  manager spawns impl-lead with "Plan only. Begin planning pass on Issues #a,
  #b, ... (plan exactly these). Return the plan table as your final message
  and spawn nothing." After approval it spawns a fresh impl-lead with "Plan
  approved. Execute exactly this plan:" plus the table verbatim.
  - *Auto-approval.* The one statement of the rule: the agent prompts point
    here. It applies when `teamflow-config teamflow_auto_approve` is `low`
    (the default; `none` turns it off, and then every plan waits for the
    human, the loop check's severity-threshold stop and human question apply
    as written, and the update is confirmed when the batch is reported).
    - *All-low batch.* Every condition holds: each Issue in impl-lead's plan
      carries exactly one `severity:` label and it is `severity:low` (no
      label, or more than one, is not low); none carries `needs-discussion`;
      no unit recommends a specialist agent or needs a fallback for a
      missing one; no unit's owned files include `.claude/teamflow.json`,
      `scripts/gate.sh`, `templates/branch-ruleset.json`,
      `templates/ci.yml`, anything under `.github/`, anything under
      `agents/`, or anything under `skills/`. The release unit does not
      change the classification: it carries no Issue and owns only
      `.claude-plugin/plugin.json`.
    - *Plan.* impl-lead always produces the plan table, with each unit's
      owned files, and always returns it. The manager does not take
      impl-lead's word for the classification: it reads every planned
      Issue's labels (`tf issue list`, or `tf issue view <n>`) and checks the
      owned files against the list above and the plan for a specialist or
      fallback agent. If it confirms all-low, it tells
      the human the plan was auto-approved and why, and spawns the executing
      impl-lead without waiting. If a check fails, or an
      Issue cannot be read, the plan waits for the human as under `none`.
    - *Loop and pause.* The review-implement loop exists only when a
      post-merge review runs (see *Two loops* under Handoffs). Its rules are
      stated once, in the manager's loop check (`agents/manager.md`), and its
      all-low test is the label conditions of *All-low batch* above, on the
      cycle's new Issues. The PR loop has no new Issues and no pause.
    - *Release.* For an auto-approved iteration the release line is
      validated as usual and the release recorded, but the update
      becomes a statement in the final report, not a question. Agents
      still never run the update. Escalations (disputes, five rounds,
      unmerged or escalated PRs, more high-severity Issues than resolved,
      ownership conflicts, critical security findings) reach the human as
      before (the pause above is the part of that which stops the loop).
- **Two loops.** (#258 D5.) The *PR loop* runs inside every PR: implement,
  then review and rework rounds until the PR merges or is escalated (the next
  handoff). The *review-implement loop* (post-merge review, then a next
  iteration on the Issues it filed) runs only when a post-merge review runs,
  and that happens only when the human asks for it (*Post-merge review*
  below). Without that request an implementation pass ends when its PRs have
  merged or been escalated.
- **Implementation ⇄ Review (the PR loop, one per PR).**
  1. impl-lead opens a PR (`tf pr create`) and returns a *PR-ready report*
     to the manager: for each PR open and ready, its number, branch and the
     Issues it closes. impl-lead does not claim, review or merge.
  2. The manager spawns a fresh review-lead for each PR with "per-PR mode.
     PR #<N>, branch <branch>, Issue #<issue or none>." and nothing more. A
     *round* is one such spawn. review-lead's report to the manager: the
     verdict and the head SHA it applies to, the merge state (merged,
     queued, or unmerged and why), the blocking findings (in the PR's
     verdict comment), how many non-blocking findings the comment holds, and
     the numbers of the Issues it filed for problems outside the PR's diff.
  3. After every round, whatever the outcome, the manager resumes impl-lead
     (by agent ID; leads are resumable only in the same process, so a
     restarted run stops and asks) with the PR number, the verdict and
     review-lead's report, so impl-lead knows each merge and can start units
     that depend on it, the release unit, and its final report. On
     `REQUEST_CHANGES` impl-lead has its implementer fix every `blocker` and
     `major` (Review and merge, *Rework*) and returns a new PR-ready report;
     the manager spawns a fresh review-lead for the next round. On `APPROVE`
     and merged the PR is done. On an unmerged or escalated PR impl-lead
     records that for its final report.
  4. The manager counts rounds per PR and escalates to the human when a
     fifth round does not end in a merge, or on any other reason under
     *Escalate to the human* (Review and merge). The PR stays open.
  5. When every PR of the batch has merged or been escalated, and after the
     release unit (Release, below) has gone through steps 1 to 4, impl-lead
     gives its *final report*: PR URLs, the Issues each closes, each PR's
     final verdict and round count, how many non-blocking findings each PR's
     comment holds (not worked on), the numbers of Issues filed for
     problems outside a PR's diff (from review-lead's reports, which the
     manager passes along with each resume), and the release line.
  The cost of routing through the manager is accepted for now (#258 D1). A
  note-passing agent or a state file read by both leads were considered and
  are not decided.
- **Release (end of Implementation).** The one statement of the release
  rule: `docs/release.md` ("Release") and the agent prompts point here.
  - *Why.* A merged change reaches the agents only after a version bump in
    `.claude-plugin/plugin.json`, the human's update, and a fresh session
    (`/reload-plugins` is untested for subagent definitions).
  - *Trigger.* A unit of the batch touches a shipped path (`agents/`,
    `skills/`, `bin/`, `hooks/`, `templates/`, `.claude-plugin/`). impl-lead
    decides at planning and checks again before it reports.
  - *One bump.* The batch gets exactly one bump, because parallel units
    would otherwise all edit the same line. Normally that is a final release
    unit that changes only the `version` string. If a unit of the batch
    already bumps `version`, that unit carries the bump and there is no
    release unit.
  - *Branch.* The release unit's branch is
    `chore/<lowest Issue number in the batch>-release-<version>`, with a
    `Refs:` trailer per Issue in the batch.
  - *Bump.* Minor (0.x.0) when a release changes a contract agents rely on
    (a `tf` exit code, command, flag or output an agent prompt depends on; a
    workflow rule; an agent's steps), patch otherwise.
  - *Sequencing.* "Merged" means `tf pr view <N>` shows the PR merged; a
    queued auto-merge is not merged (Review and merge, *Queued merge*, makes
    it merged). The release unit is branched from
    up-to-date `main` (never stacked) after every other unit has merged, then
    reviewed and merged like any PR (the PR loop), all before impl-lead gives
    its final report. On GitHub
    units merge remotely, so the main worktree must be fast-forwarded
    (`git pull --ff-only` there) before `main` is read; locally `tf pr merge`
    has already updated `main`. Two readings of `version` in
    `.claude-plugin/plugin.json`, at different times:
    - *Bump from*: read on up-to-date `main` before branching the release
      unit.
    - *Report*: read on `main` after the bumping PR (release unit or carrying
      PR) has merged, after the fast-forward on GitHub. This is the version
      the release line names.
  - *Unmerged.* If any unit, the release PR or the carrying PR is escalated
    or stays unmerged, impl-lead does not hold the final report: it spawns no
    release unit and reports at once, naming the unmerged PR in the report
    body. Merged shipped-path changes left by an unmerged batch are not
    tracked by any mechanism: they ship with the next release that happens.
    PRs merged through per-PR review as merge-review (outside the loop) get no
    automatic release step either.
  - *Release line.* impl-lead ends its final report with exactly one of:
    "Release: <version>, merged in PR #N" (the release unit),
    "Release: <version>, carried by PR #N" (the carrying PR, merged),
    "No release: PR #N unmerged" (the unmerged PR that stopped it), or
    "No release: no shipped path changed". A version bump merged on `main`
    always gets a version line, even if another unit stays unmerged: the
    update follows. "No release: PR #N unmerged" applies only when no bump
    has merged.
  - *Update.* Whenever the line names a version, the manager asks the human to
    run `claude plugin update teamflow@teamflow --scope project`, start a
    fresh session, and confirm or skip, once the batch's release has merged
    and when the manager reports the batch (for an auto-approved iteration,
    see Auto-approval). Per-PR review never waits for the update: it ran
    before the merge. A post-merge review the human asks for starts only after
    the human confirms or skips the update.
    Agents never run the update: it changes the human's install.
- **Post-merge review (optional).** Off by default, with no config key (#258
  D6): it runs only when the human asks, through the route "Review what we
  just built". The manager then spawns review-lead with "diff-review mode.
  Review PRs: [list]. File new Issues for anything that needs fixing." It
  is a second look at merged code, not the merge gate.
- **Review → Implementation (loop, post-merge review only).** review-lead's
  final report to the manager: the numbers of the new Issues, highest
  severity, tracking Issue number, and whether prior-cycle Issues remain
  unfixed. Manager runs the loop check; if continuing, the next iteration
  plans exactly the new Issues; if stopping, reports to the human. Under
  `teamflow_auto_approve` `low` the loop check has exceptions (see
  Auto-approval). Issues filed per PR for problems outside a PR's diff are
  not new Issues of this loop: they wait in the backlog.
- **Review → Done.** No post-merge review was requested, or it filed zero new
  Issues, or the loop check ends the loop: the manager reports final state
  to the human.

## Role bounds
- Every agent has exactly one job. Route out-of-scope work to the right
  session; do not absorb it.
- "Owns X exclusively" means write access to that path only.
- "Read-only" means no Edit, Write, MultiEdit, or destructive Bash. It is
  enforced by `disallowedTools` as a guard rail, not a wall: Bash can still
  write, so keeping the boundary is on you.

## Task states
- **Done**: the defined output exists, checks pass, and you reported.
- **Blocked**: a dependency is unmet or a file-ownership conflict exists.
  Stop and make the blocker your final message; do not proceed.

## Honesty
Every report, PR body, review and Issue states only what you observed.
- **Report what ran.** Give the exact command and its result for every
  check you claim. A check you did not run is "not verified", never "passes".
- **Skipped is not passed.** A skipped, cancelled or unrun check is reported
  as such. A target (say, 95% coverage) is not an achievement until measured.
- **Missing evidence is unresolved.** Treat a claim you cannot trace to a
  command, a file, or a source as open, in your own work and in others'.
- **Never work around a refusal.** If a permission prompt, a hook, or `tf`
  refuses an operation, do not perform it another way (a wrapper script, a
  different tool, an interpreter). Report the check as not verified and say
  what was refused. Rewording a message so a checker accepts it is not a
  workaround, as long as what it says stays accurate and complete: a review
  body may describe a command in words instead of quoting it.
- **Report failures as failures,** with the output, even when a later step
  passed.

## Messaging
- Lead with status, then detail. Keep it short.
- No progress updates mid-task unless blocked. Do not poll.
- Leads and workers report by final message. Leads return after their workers where the harness makes them wait: interactive, and `-p` or the SDK with fork mode on. Teamflow does not support `-p` with fork mode off. A restarted run stops and asks.
- A subagent reports with its final message: it calls `SubagentHandback`
  when it has that tool (async spawns, where plain final text is not
  delivered), otherwise it ends its turn. In a STOP case the blocker is its
  final message, and it does not wait for a reply.
- A subagent's mid-task message goes only to `SendMessage(to: "team-lead")`,
  never `"main"` or the lead's session name: neither works in both spawn
  modes.
- A teammate's final message arrives as an idle-notification `result`; an
  async subagent's (unnamed, or any `isolation: "worktree"` spawn) arrives as
  a `[Subagent hand-back]`. Leads answer with
  `SendMessage(to: "<agent ID>")`, which resumes it.
- Escalate to the human, not just your lead, when a file-ownership conflict
  cannot be resolved, a critical security problem is found, or a loop
  iteration produces more high-severity Issues than it resolves: a lead puts
  it first in its final report, and the manager relays it.

## Issues and PRs: `tf`
Every agent reaches Issues and PRs through `tf` (on PATH from the plugin),
never `gh` directly. The repository's `.claude/teamflow.json` sets `forge`;
`tf mode` prints it. Configuration is always read from the main worktree,
never from the worktree `tf` runs in, so a PR that changes it takes effect
only once merged and pulled. The main worktree must stay on the base branch;
on any other branch every `tf` command stops (exit 2), except `tf setup`,
which runs on a setup branch. All work on other branches happens in separate
worktrees.

| | `local` (default) | `github` (adopted) |
|---|---|---|
| Issues and PRs | Records in the git common dir, shared by all worktrees, never committed | GitHub Issues and PRs |
| One review per PR round | `tf pr claim`: a lock | `tf pr claim`: a pending `teamflow/code-review` status on the head |
| Gate at review | review-lead runs `scripts/gate.sh` (`tf pr gate`) | CI's required checks on the head (`tf pr gate`); no second local run |
| Verdict | Recorded against the reviewed head SHA | A PR comment plus a `teamflow/code-review` status on that SHA |
| Merge | `tf pr merge` merges into the base branch; nothing is pushed | With a ruleset requiring both `gate` and `teamflow/code-review`, `tf pr review --verdict APPROVE` enables auto-merge, pinned to the reviewed head, and GitHub merges once required checks pass (at once if the PR is already clean); `tf pr merge` is only the fallback. Without one (no ruleset, one lacking either context, or one `tf` cannot read), `tf pr review` arms nothing, and `tf pr merge` checks the CI `gate` check and the verdict itself, then merges, waiting for pending CI like `tf pr gate`. Every GitHub `tf pr merge` can block up to `TF_GATE_WAIT`, so it needs the long Bash timeout |
| Stacked PR after its dependency merges | `tf` retargets it to the base branch | GitHub retargets it, because adoption deletes merged branches (`delete_branch_on_merge`); without that it stays on the old base |

A repository that adopted `github` but lacks `gh`, its login, or a GitHub
remote makes every `tf` command stop with exit 2. Never fall back to local
or to raw `git`/`gh` to get around it: report it.

`tf pr checkout` fetches the PR's branch from the configured remote, so PRs
from forks cannot be reviewed.

Exit codes: 0 ok, 1 error, 2 setup or usage problem, 3 refused because of PR
state (claimed, moved head, no approval, or after the wait of `tf pr gate` or
`tf pr merge`, CI still running or unreadable), 4 the verdict of `tf pr review
--verdict APPROVE` is recorded but auto-merge was not armed (its status
stays set; Review and merge, *Merge*, says what to do). Exit 3 is a STOP, not a
retry signal. `tf pr gate` exits 1 for a red gate in both modes (locally, any
nonzero result of `scripts/gate.sh`, so also a gate that could not run: read
its output). On GitHub it reports a red check as soon as every check has
finished, but a missing `gate` check (exit 2), unreadable CI and pending
checks (exit 3) only after the full `TF_GATE_WAIT`. `tf pr merge` on GitHub
uses the same codes: without a ruleset requiring both contexts, exit 1 is a
red `gate` check or a failed merge, exit 2 a missing `gate` check or a bad
`TF_GATE_WAIT` or `TF_GATE_POLL` (also with such a ruleset); locally, exit 1 is
a failed merge that is not a conflict. `tf --help` has the timing of the wait.
If a `tf pr gate` or `tf pr merge` call outlasts its Bash timeout, the tool was
observed to move it to the background, not kill it; a kill was not observed.
Either way the merge or auto-merge may already have happened: run
`tf pr view <N>` before anything else, wait for the backgrounded call's result
if there is one, and do not retry or report the merge as failed meanwhile.

## Domain language
When the project has `CONTEXT.md` (its glossary) or `docs/adr/` (its
recorded decisions), read them before planning, implementing or reviewing,
and use the terms as defined there. Reviewers flag a term used against its
definition. A decision worth keeping (a trade-off, a rejected option, a
convention) becomes an ADR; the `domain-modeling` skill writes ADRs and
`CONTEXT.md` entries; it comes from the `mattpocock-skills` plugin, which
teamflow depends on.

## Issues
Labels on work Issues (tracking Issues, below, carry none):
`severity:high|medium|low`, `needs-discussion`,
`area:architecture|security|quality|docs|simplicity|research`,
`type:feature|bug|task`. Research Issues use `type:task`; review findings
use their `area:` label. File with
```bash
tf issue create --title '<one line>' --label <l> [--label <l>] --body-file - <<'EOF'
<the Issue body>
EOF
```
Every body (Issues, comments, PRs, reviews) goes in a quoted heredoc on
stdin. Inside double quotes the shell runs backtick spans as commands;
inside single quotes an ordinary apostrophe ends the string and does the
same; inside `<<'EOF'` nothing is expanded. Keep titles to one line in
single quotes, with no quotes or backticks. No scratch file is needed.

Relabel with `tf issue edit <n> [--add-label <l> ...] [--remove-label <l> ...]`.
When a human decides an Issue (for example a `needs-discussion` finding),
the agent that records the decision runs `tf issue comment` with the
decision, then `tf issue edit` so the labels match it. Once the human has
answered the questions, remove `needs-discussion`. A `needs-discussion`
Issue may carry no `severity:` label: the recording agent does not add one
of its own choosing, and does not require exactly one. A `severity:` label
changes only when the human's decision names a severity. A label change
records a decision and never stands in for one: no agent changes
`severity:` or `needs-discussion` on its own judgment.
Only the manager and the leads run `tf issue edit`; other agents report a
label change to their lead instead.

**Tracking Issues** are the reports a lead opens at the end of a pass
(research-lead: its Issue list; review-lead: a post-merge review cycle, never a
per-PR round). They carry no
`severity:`, `area:` or `type:` label: a report, not work.
- The lead reports the tracking Issue's number and the numbers of the Issues
  it filed (review-lead: the net new ones), never a URL: `tf issue create`
  prints a URL on GitHub and `#N` locally, and the number is its trailing
  digits. The lead does not close it.
- The manager runs `tf issue view <n>` first. Only if that Issue has none of
  the three labels does it record the number in `.manager-state.json` and run
  `tf issue close <n>`. Otherwise it records nothing, closes nothing and
  reports to the human: a wrong number would close real work, and recording
  it would drop a work Issue from the open-work counts.
- The numbers recorded in `.manager-state.json` identify tracking Issues:
  counts of open or filed work leave them out. On Startup the manager closes
  any recorded one still open, checking its labels again first.

**Research Issues are typed briefs**, so implementation and review can
check each claim:
- **Objective**: one outcome.
- **Requirements**: `R1`, `R2`, ... each marked required or optional.
- **Acceptance criteria**: `A1`, `A2`, ... each with a **Verification**
  method: the test, command, or reading that shows it holds. A criterion
  without one cannot be accepted.
- **Constraints**, **Permitted actions**, **Prohibited actions**.
- **Dependencies**: Issues that must merge first.
- **Open questions**: unresolved ambiguities, stated rather than guessed.

**Review findings** are graded on one of two scales, with no mapping between
them (#258 D4).

*On a PR* (per-PR mode): `blocker`, `major`, `minor`, `nit`. Each finding
carries its grade, its location (file:line where applicable), what is wrong
and why, the rule or requirement it breaks, and a suggested fix (an argument,
not a tested patch).

| Grade | Meaning | Blocks merge |
|---|---|---|
| `blocker` | Hard-rule breach, wrong behaviour, contract violation | yes |
| `major` | Required case missing, pre-existing test weakened, a doc stating a falsehood or a command that does not work | yes |
| `minor` | Clarity, dead code, stale or incomplete docs | no |
| `nit` | Style | no |

These findings live in the PR (the verdict comment) and are not filed as
Issues. `minor` and `nit` findings are collected there and are not worked on
yet. A verdict is `APPROVE` only with zero `blocker` and zero `major`
findings and a green gate.

*As an Issue*: a problem outside the PR's diff, found in per-PR mode, and
every finding of diff-review mode. Severity: high / medium / low /
needs-discussion, grounded in a documented convention or a clear correctness
defect; location; finding / task; convention violated (the specific rule, or
needs-discussion). In per-PR mode review-lead files these Issues once, after
merging the specialists' duplicates. The duplicate rule below applies across
rounds and across concurrent PRs: if an open Issue has the same file:line and
defect type, review-lead comments on it instead of filing again.

In diff-review mode a finding is **new** if no prior cycle filed it, or a
prior Issue was closed without fixing the root cause. A finding is a
**duplicate** if an open Issue has the same file:line and defect type:
`tf issue comment` on that Issue instead. The manager counts net new Issues.

## Research output
Per finding: **Finding**, **Confidence** (high/medium/low), **Source**
(file:line, URL, or document), **Recommendation**, **Conflicts with**.

## Branches and commits
- Never commit to `main`. One branch per unit, named
  `<type>/<issue-number>-<slug>` (`feat/`, `fix/`, `docs/`, `refactor/`,
  `chore/`), from up-to-date `main`, or from the dependency's branch for a
  stacked unit. A release unit's branch is named under Handoffs, Release.
- Atomic Conventional Commits: `<type>(<scope>): <description>` with a
  `Refs: #<n>` trailer. `<type>` is the commit's own change (`test`, `docs`
  and `ci` commits are normal on a `fix/` branch); the branch prefix names
  the unit's main type. Code and its tests in the same commit.
- Never force-push a shared branch. Never merge-then-fix.
- Implementers: `cd` into your worktree first, never touch files outside it,
  and `git status` before opening a PR.

## The gate
The project's `./scripts/gate.sh` is the one definition of green. The
implementer runs it before opening a PR. At review, `tf pr gate` checks it
again: by running it locally, or on GitHub by requiring CI's checks for the
exact head. Red and unfixable within your owned files: commit, do not open a
PR, report the failing checks. A project without `scripts/gate.sh` has not
been set up for teamflow: stop and report.

## Red/green
`teamflow-config tdd` is `required` (the default) or `recommended`. For a
testable change, the implementer writes the test first, runs it, and keeps
the failing output (the red), then makes it pass (the green). The PR body
records, per test: its name, the command, the red output, and that it now
passes. A change that cannot be tested (prose, configuration) says so and
why. A reviewer re-runs a new test against the base branch's code where it
can. Missing red/green evidence on a testable change is a `major` under
`required`, a `minor` under `recommended` (the per-PR grades of Review
findings).

## Opening a PR
```bash
tf pr create --title '<type>(<scope>): <description>' [--base <branch>] --body-file - <<'EOF'
<the filled-in .github/pull_request_template.md>
EOF
```
`tf pr create` refuses a dirty tree, the base branch, a detached HEAD, or an
unedited template, and pushes the branch first on GitHub. The body carries
`Closes #<n>` for each resolved Issue. It is a hint for the reviewer, never
evidence.

## Review and merge
Every PR is reviewed by the review team before it merges, in rounds. The
rules below are the one statement; the agent prompts point here.
- **Who:** one fresh review-lead per round, spawned by the manager with only
  the PR number, branch and Issue (Handoffs, the PR loop). review-lead alone
  claims, checks the gate, spawns the specialists, records the verdict and
  arms or runs the merge. It is the only actor that arms or runs a merge
  (#258 D2): the five specialists never run `tf pr claim`, `release`,
  `review` or `merge`, and impl-lead and the implementer never do. `tf pr
  create` arms nothing (no auto-merge code in it, read in `bin/tf`).
- **Claim.** review-lead runs `tf pr claim <N>` first, once per round, before
  any specialist starts, and spawns nothing if it refuses (it reports that).
  On GitHub a claim overwrites an existing `teamflow/code-review` status of
  the head with `pending` (read in `bin/tf`, `pr_claim`), so a second claim
  in a round would erase a recorded verdict. review-lead pins the round to
  the full SHA on the `head:` line of `tf pr view <N>`, read right after the
  claim (the claim's own output does not give it: locally none, on GitHub 12
  characters, read in `bin/tf`; `tf pr review --sha` needs the full one).
  `tf pr release <N>` once the verdict
  lands; if review-lead dies without one, the manager releases the claim.
- **Gate.** review-lead runs `tf pr checkout <N>` in its own worktree (locally
  `tf pr gate` refuses a worktree not at the head), then `tf pr gate <N>`,
  after the claim and before the specialists, with the long Bash timeout (exit codes: Issues and PRs,
  `tf`). Exit 1 (red) is a `blocker`; the round continues, to give the
  implementer the whole picture. A gate that could not run, or exit 2 or 3,
  is a STOP: the gate is not verified and no verdict is recorded.
- **Specialists.** Five fresh specialists every round, in parallel, each
  prompted with only the PR number, branch, Issue and the head SHA
  review-lead pinned from `tf pr view <N>` (#258 D7, D11; the SHA is a pin,
  not a briefing). No prior-round finding, risk, changed-file list or
  conventions briefing is passed: naming risks or suggesting what to check
  undermines independence. Each checks the PR's head out with
  `tf pr checkout <N>` in its own worktree, confirms `git rev-parse HEAD`
  equals the pinned SHA (else it stops and says so), and reports its findings, graded as in Review findings, to review-lead.
  Specialists review against the Issue and these rules.
- **Verdict: exactly one `tf pr review` per head per round**, made by
  review-lead after all five specialists have reported, recorded against the
  full head SHA it pinned after the claim (`tf` refuses a head that moved). The
  first `APPROVE` on a ruleset repository arms auto-merge and the last
  status per head wins, so a second call, or a call by a specialist, could
  merge a head nobody fully reviewed (read in `bin/tf`, `approved` and
  `arm`). `APPROVE` needs zero `blocker` and `major` from any specialist and
  a green gate; otherwise `REQUEST_CHANGES`. The comment carries the gate
  result, each finding with its grade, and what was checked and how.
  Every round is a full re-review, never a spot-check of the fixes.
- **Merge** (only on `APPROVE`, only review-lead). On `REQUEST_CHANGES`
  nothing is armed or merged. After `APPROVE`, the output and exit code of
  `tf pr review` say what is left: locally, run `tf pr merge <N>`; on GitHub
  with the ruleset the review armed auto-merge, so run no merge command; with
  no ruleset requiring both contexts, run `tf pr merge <N>`; for a stacked PR
  (targets another branch than the base) run none and report it; exit 4 (the
  verdict is recorded, auto-merge was not armed) is the one non-zero exit
  that is not a STOP: run `tf pr merge <N>` once. Any other non-zero exit is a
  STOP. Never `--admin`, a direct `git push`, or a self-approval.
- **A verdict is for one commit.** A push after an approval needs a new
  round; `tf` refuses to merge a head nobody approved.
- **Stacked PRs** are reviewed in dependency order: the manager hands a
  stacked PR to review-lead only once it targets the base branch. A
  dependency that is escalated or stays unmerged (see *Queued merge*) leaves
  its stacked PR unreviewed; it is escalated too.
- **Queued merge** (GitHub with the ruleset, armed by `tf pr review` or by
  the fallback `tf pr merge`; locally `tf pr merge` merges at once). A queued
  auto-merge has no event source, so review-lead, the actor that armed it,
  drives it right after each `APPROVE` that leaves one, for every PR,
  stacked dependencies included. No human is involved and nobody polls.
  1. Run `tf pr gate <N>` once, with the long Bash timeout. When it returns
     is described in the exit-code paragraph of "Issues and PRs: `tf`".
     Exit 0: go to 2. Exit 1 (red), 2 (no `gate` check) or 3 (CI pending or
     unreadable after the wait): the PR *stays unmerged*. review-lead
     reports that to the manager with the output, and `tf pr view` and step
     2 do not run.
  2. Run `tf pr view <N>`. `state: merged`: done, ignoring `merge state:`.
     Otherwise (open) read its `merge state:` line (GitHub's
     `mergeStateStatus`, lowercased).
     - `behind`: the base moved on and the ruleset holds the merge.
       review-lead reports it; the manager resumes impl-lead, whose
       implementer merges the base into its branch (never rebase or
       force-push), and runs a new round. That round's `APPROVE` arms
       auto-merge again, so this procedure runs again for it, including one
       new `tf pr gate`. The five-round limit bounds the loop.
       Whether the earlier auto-merge stays armed across the push, and what
       a second `--auto` on an armed PR does, are unverified (spike #226 was
       not run).
     - Any other value: run `tf pr view <N>` once more, without waiting,
       because GitHub can merge a moment after the checks finish. Merged:
       done. Still open: the PR *stays unmerged*. review-lead reports that
       to the manager, which escalates, and does not wait a second time. The
       escalation may be spurious, because the merge delay was not measured.
  Observed `merge state:` values (a reviewer ran `tf pr view` against real
  PRs): `blocked` on an open PR before it merged, `unknown` on a merged PR.
  `behind` was not observed; it is expected for a branch the base has moved
  past, from GitHub's documented `mergeStateStatus`. The `state:` line
  decides first: a merged PR is done whatever `merge state:` reads, so
  `unknown` there is never "not behind". Only an open PR is judged by
  `merge state:`.
- **Rework:** on `REQUEST_CHANGES` the implementer fixes every `blocker` and
  `major` on the same branch, re-runs the gate, and on GitHub pushes the
  fix; a fresh round then re-reviews everything with a fresh review-lead and
  five fresh specialists. A suggested fix is an argument, not a tested patch.
- **Escalate to the human** when a finding is re-argued without new
  evidence, when the dispute is about what the Issue requires, or at five
  rounds. The manager relays it. Leave the PR open.
- **A PR the implementation team did not open** (merge-review) uses the same
  per-PR review. There is no implementer to resume, so the manager relays a
  `REQUEST_CHANGES` to the human and the author reworks.

Locally this is a process control: every agent runs as the same OS user.
On GitHub the teamflow branch ruleset enforces that no merge happens
without the CI gate and an approving `teamflow/code-review` status on the
current head, so a push after approval always needs a new review. It does
not prove who reviewed: every agent shares one `gh` login and could set that
status. Without the ruleset, `tf` checks the same things itself. Arming
auto-merge adds no check of its own: the ruleset's required contexts still
decide when GitHub merges. The merge behaviour of `tf pr review` is tested
against a fake `gh` (`tests/test_tf.py`: `test_approve_arms_auto_merge_on_a_ruleset_repository`,
`test_approve_on_a_stacked_pr_arms_nothing`,
`test_approve_arms_nothing_unless_the_ruleset_requires_both_contexts`,
`test_request_changes_arms_nothing`,
`test_arming_failure_after_the_verdict_exits_4_and_keeps_the_verdict`),
not against real GitHub. That `--auto` merges a clean PR at once is read
from gh's source (modelled in `test_approve_that_makes_the_pr_clean_can_merge_it_at_once`), not run.

## Cleanup
When a unit merges: `git worktree remove <path>`, delete the branch, and
delete leftover `worktree-agent-*` branches.
