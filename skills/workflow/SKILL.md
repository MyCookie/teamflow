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

## Issues
Labels: `severity:high|medium|low`, `needs-discussion`,
`area:architecture|security|quality|docs|simplicity|research`,
`type:feature|bug|task`; `review:in-progress` (set by the lead that spawns a
code-reviewer), `review:approved`, `review:changes-requested` (set by the
code-reviewer). Research Issues use `type:task`; review findings use their
`area:` label.

Every Issue carries:
- **Severity**: high / medium / low / needs-discussion, grounded in a
  documented convention or a clear correctness defect
- **Location**: file:line where applicable
- **Finding / Task**: what needs doing and why
- **Convention violated**: the specific rule, or needs-discussion

In diff-review mode a finding is **new** if no prior cycle filed it, or a
prior Issue was closed without fixing the root cause. A finding is a
**duplicate** if an open Issue has the same file:line and defect type:
comment on that Issue instead. The manager counts net new Issues.

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
implementer runs it before opening a PR; the code-reviewer runs it again
before merging. Red and unfixable within your owned files: push the branch,
do not open a PR, report the failing checks. A project without
`scripts/gate.sh` has not been set up for teamflow: stop and report.

## Opening a PR
```bash
cp .github/pull_request_template.md /tmp/pr-body-<issue>.md   # then fill it in
open-pr "<type>(<scope>): <description>" /tmp/pr-body-<issue>.md [base]
```
`open-pr` (on PATH from the plugin) refuses a dirty tree, `main`, a detached
HEAD, or an unedited template. The body carries `Closes #<n>` for each
resolved Issue. It is a hint for the reviewer, never evidence.

## Review and merge
- **Per PR:** a fresh `teamflow:code-reviewer` re-runs the gate, reviews
  against the Issue and these rules, posts its verdict on the PR, and merges
  on `APPROVE`. It is the only actor that merges.
- **Who spawns it:** `impl-lead` for its team's PRs, owning the rounds;
  `review-lead` only in merge-review mode.
- **One reviewer per PR.** The spawning lead claims it first: if
  `gh pr view <N> --json labels` shows `review:in-progress`, do not spawn;
  otherwise add it. Remove it when the verdict lands or the reviewer dies.
- **Fresh each round,** prompted with only the PR number, branch and Issue.
  Naming risks or suggesting what to check undermines independence.
- **Stacked PRs** are reviewed in dependency order: spawn a stacked PR's
  reviewer only once its base is `main`. The reviewer refuses to merge into
  anything else.
- **Rework:** on `REQUEST_CHANGES` the implementer fixes every `blocker` and
  `major` on the same branch, re-runs the gate and pushes; a new reviewer
  re-reviews everything. A suggested fix is an argument, not a tested patch.
- **Escalate to the human** when a finding is re-argued without new
  evidence, when the dispute is about what the Issue requires, or at five
  rounds. Leave the PR open.

This is a process control, not an access control: every agent runs as the
same OS and GitHub user. Branch protection on `main` is what enforces it.

## Cleanup
When a unit merges: `git worktree remove <path>`, delete the branch, and
delete leftover `worktree-agent-*` branches.
