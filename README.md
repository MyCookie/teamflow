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
/plugin marketplace add Ribhu-Labs/teamflow
/plugin install teamflow@teamflow
```

Launch `claude` and ask it to setup the teamflow plugin.

## How it works

```mermaid
flowchart TD
    Goal["Goal, or Issue numbers, from the human"] --> Manager["manager: routes every handoff"]
    Manager -->|"goal or task with no Issue"| Research["research-lead and researchers: file Issues and a tracking Issue"]
    Manager -.->|"Issue numbers given: research skipped (optional)"| Plan
    Manager -.->|"Review what we just built (optional)"| Post
    Research --> Plan
    Plan["impl-lead, plan only: returns the plan table"] --> Approve{"plan approval"}
    Approve -->|"human approves"| Exec
    Approve -->|"all-low batch, teamflow_auto_approve low: manager auto-approves"| Exec
    Exec["fresh impl-lead executes the plan: implementers, one worktree each, open PRs"] --> Round

    subgraph prloop ["PR loop, one per PR"]
        Round["fresh review-lead per round: claim, gate, five specialist reviewers, one verdict"] --> Verdict{"verdict"}
        Verdict -->|"REQUEST_CHANGES"| Rework["impl-lead's implementer reworks"]
        Rework --> Round
        Verdict -->|"APPROVE"| Merge["review-lead arms or runs the merge"]
    end

    Verdict -.->|"fifth round without a merge, or a dispute"| Human["escalate to the human"]
    Merge --> Rel{"shipped path changed?"}
    Rel -->|"yes"| Release["release unit bumps the version after the other units merge; manager asks the human to run the plugin update"]
    Rel -->|"no"| Next
    Release --> Next{"post-merge review asked for?"}
    Next -.->|"yes (optional)"| Post
    Next -->|"no"| Done["Done: manager reports to the human"]
    Post["review-lead, diff-review mode: files new Issues"] --> Loop{"manager's loop check"}
    Loop -->|"continue: next iteration plans exactly the new Issues"| Plan
    Loop -->|"no new Issues, or the loop stops"| Done
```

The diagram is drawn from `skills/workflow/SKILL.md` and `agents/manager.md`;
where the two differ, the workflow rules win. How to run it is in
[docs/running.md](docs/running.md), which also records that per-PR review and
the optional loop were read in the rules, not run live.

## License

Copyright 2026 Ashish Kansara. Licensed under the Apache License, Version 2.0; see [LICENSE](LICENSE).
