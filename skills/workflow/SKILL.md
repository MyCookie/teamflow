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

| Session | Start with | Spawns | Job |
|---|---|---|---|
| manager | `claude --agent teamflow:manager --name manager` | nothing | Routes goals, runs handoffs, governs the review-implement loop |
| research-lead | `claude --agent teamflow:research-lead --name research-lead` | `researcher` | Decomposes goals into Issues; implements nothing |
| impl-lead | `claude --agent teamflow:impl-lead --name impl-lead` | `implementer`, `code-reviewer` | One worktree and PR per non-overlapping unit; owns each PR's review rounds to merge |
| review-lead | `claude --agent teamflow:review-lead --name review-lead` | five specialist reviewers; `code-reviewer` in merge-review mode | Diff-reviews the cycle's merged PRs and files follow-up Issues |

## Routing (manager)

| Input | Route to |
|---|---|
| Vague goal, feature idea, open-ended question | Research |
| Specific task with no existing Issue | Research |
| Specific Issue number(s), "fix #N" | Implementation |
| "Review what we just built" | Review, diff-review mode |
| A PR the implementation team did not open | Review, merge-review mode (outside the loop) |

## Handoffs

- **Research → Implementation.** research-lead → @manager: tracking Issue
  URL, Issue count, priority order. Manager → @impl-lead: "Begin planning
  pass on open Issues. Show the plan before spawning."
- **Implementation → Review.** impl-lead → @manager: PR URLs, Issues each
  closes, each PR's final code-reviewer verdict. Manager → @review-lead:
  "diff-review mode. Review PRs: [list]. File new Issues for anything that
  needs fixing."
- **Review → Implementation (loop).** Manager checks the loop bounds; if
  continuing, sends @impl-lead the new Issue list; if stopping, reports to
  the human.
- **Review → Done.** Zero new Issues, or bounds reached: the manager reports
  final state to the human.

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

## Messaging
- Address sessions by `@name`. Lead with status, then detail. Keep it short.
- No progress updates mid-task unless blocked. Do not poll; use idle
  notifications when waiting on a phase.
- Leads and the manager hold `SendMessage` and `ListAgents`; subagents hold
  `SendMessage` only. Sessions receive messages only when the project sets
  `crossSessionInbound: accept` in `.claude/settings.json`.
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
  `SendMessage(to: "<subagent name>")`, which resumes it.
- Escalate to the human, not just your lead, when a file-ownership conflict
  cannot be resolved, a critical security problem is found, or a loop
  iteration produces more high-severity Issues than it resolves.

## Issues and PRs: `tf`
Every agent reaches Issues and PRs through `tf` (on PATH from the plugin),
never `gh` directly. The repository's `.claude/teamflow.json` sets `forge`;
`tf mode` prints it.

| | `local` (default) | `github` (adopted) |
|---|---|---|
| Issues and PRs | Records in the git common dir, shared by all worktrees, never committed | GitHub Issues and PRs |
| One reviewer per PR | `tf pr claim`: a lock | `tf pr claim`: a pending `teamflow/code-review` status on the head |
| Gate at review | The reviewer runs `scripts/gate.sh` (`tf pr gate`) | CI's required checks on the head (`tf pr gate`); no second local run |
| Verdict | Recorded against the reviewed head SHA | A PR comment plus a `teamflow/code-review` status on that SHA |
| Merge | `tf pr merge` merges into the base branch; nothing is pushed | With a ruleset, `tf pr merge` enables auto-merge and GitHub merges once required checks pass; without one, `tf` checks the CI `gate` check and the verdict itself, then merges |
| Stacked PR after its dependency merges | `tf` retargets it to the base branch | GitHub retargets it |

A repository that adopted `github` but lacks `gh`, its login, or a GitHub
remote makes every `tf` command stop with exit 2. Never fall back to local
or to raw `git`/`gh` to get around it: report it.

Exit codes: 0 ok, 1 error, 2 setup or usage problem, 3 refused because of PR state
(claimed, moved head, no approval). Exit 3 is a STOP, not a retry signal.

## Issues
Labels: `severity:high|medium|low`, `needs-discussion`,
`area:architecture|security|quality|docs|simplicity|research`,
`type:feature|bug|task`. Research Issues use `type:task`; review findings
use their `area:` label. File with
`tf issue create --title "..." --body "..." --label <l> [--label <l>]`.
Pass bodies inline with `--body`; no scratch file is needed.

Every Issue carries:
- **Severity**: high / medium / low / needs-discussion, grounded in a
  documented convention or a clear correctness defect
- **Location**: file:line where applicable
- **Finding / Task**: what needs doing and why
- **Convention violated**: the specific rule, or needs-discussion

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
  stacked unit.
- Atomic Conventional Commits: `<type>(<scope>): <description>` with a
  `Refs: #<n>` trailer; `<type>` matches the branch prefix. Code and its
  tests in the same commit.
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

## Opening a PR
```bash
cp .github/pull_request_template.md /tmp/pr-body-<issue>.md   # then fill it in
tf pr create --title "<type>(<scope>): <description>" --body-file /tmp/pr-body-<issue>.md [--base <branch>]
```
`tf pr create` refuses a dirty tree, the base branch, a detached HEAD, or an
unedited template, and pushes the branch first on GitHub. The body carries
`Closes #<n>` for each resolved Issue. It is a hint for the reviewer, never
evidence.

## Review and merge
- **Per PR:** a fresh `teamflow:code-reviewer` checks the gate, reviews
  against the Issue and these rules, records its verdict for the exact head
  it reviewed, and merges on `APPROVE` with `tf pr merge`. It is the only
  actor that merges.
- **Who spawns it:** `impl-lead` for its team's PRs, owning the rounds;
  `review-lead` only in merge-review mode.
- **One reviewer per PR.** The spawning lead runs `tf pr claim <N>` first
  and does not spawn if it refuses; `tf pr release <N>` when the verdict
  lands or the reviewer dies.
- **Fresh each round,** prompted with only the PR number, branch and Issue.
  Naming risks or suggesting what to check undermines independence.
- **A verdict is for one commit.** A push after an approval needs a new
  review; `tf` refuses to merge a head nobody approved.
- **Stacked PRs** are reviewed in dependency order: spawn a stacked PR's
  reviewer only once it targets the base branch.
- **Rework:** on `REQUEST_CHANGES` the implementer fixes every `blocker` and
  `major` on the same branch and re-runs the gate; a new reviewer re-reviews
  everything. A suggested fix is an argument, not a tested patch.
- **Escalate to the human** when a finding is re-argued without new
  evidence, when the dispute is about what the Issue requires, or at five
  rounds. Leave the PR open.

Locally this is a process control: every agent runs as the same OS user.
On GitHub the teamflow branch ruleset enforces that no merge happens
without the CI gate and an approving `teamflow/code-review` status on the
current head, so a push after approval always needs a new review. It does
not prove who reviewed: every agent shares one `gh` login and could set that
status. Without the ruleset, `tf` checks the same things itself.

## Cleanup
When a unit merges: `git worktree remove <path>`, delete the branch, and
delete leftover `worktree-agent-*` branches.
