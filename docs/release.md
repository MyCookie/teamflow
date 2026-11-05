# Release

A merged change reaches the agents only after a release. Sessions run the
installed copy under `~/.claude/plugins/cache/`, not the repository, and with
marketplace auto-update off, as on the maintainer's install, nothing moves
that copy forward on its own. The release rule itself (when a release is
needed, the bump, the sequencing, the release line) is stated once, in
[`skills/workflow/SKILL.md`](../skills/workflow/SKILL.md), Handoffs, "Release".
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
  docs, which a research-lead session read and this page did not re-check
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
