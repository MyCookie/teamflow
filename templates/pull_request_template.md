<!-- Everything here is a hint for the code-reviewer, never evidence: it
     re-derives all of it independently. State only what you ran. -->

## Issue

Closes #<n>

<one paragraph: what this branch makes true that was not true before>

## Evidence

One row per acceptance criterion of the Issue:

| Criterion | How it was verified | Result |
| :--- | :--- | :--- |
| A1 | <test name, command, or what was read> | <observed result> |

## Red/green

For each new or changed test: its name, the command, the failing output
before the change (red), and that it passes after (green). For a change
that cannot be tested, say so and why.

## Gate

Output of `./scripts/gate.sh` at <head SHA>:

| check | result |
| :--- | :--- |
| | |

## Not verified

<Every claim above you did not check yourself, every skipped check, and
anything refused by a permission prompt. "None" only if that is true.>

## Decisions

<Ambiguities in the Issue or docs and how they were resolved, with the doc
change or ADR that records them. "None" if none.>

## Pre-existing tests touched

<Every modified pre-existing test, with its justification, or "none". A test
that looks wrong is a question for the Issue author, not an edit.>
