#!/usr/bin/env bash
# The merge gate. One script, so what the implementer ran and what the
# code-reviewer ran cannot drift (teamflow workflow rules).
#
# Every step runs even after an earlier one fails: a reviewer wants the whole
# picture, not the first thing that broke. Exits non-zero if any step failed.
#
set -uo pipefail

cd "$(dirname "$0")/.."

results=()
failed=0

step() {
    local name="$1"
    shift
    printf '\n\033[1m── %s ─────────────────────────────\033[0m\n' "$name"
    if "$@"; then
        results+=("$name|pass")
    else
        results+=("$name|FAIL")
        failed=1
    fi
}

# Credentials: load .env ourselves rather than asking the caller to export it.
# No shell state survives between an agent's commands, so "export, then run
# the gate" in two commands leaves the gate with nothing.
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi

# The scripts are the runbook, so a broken one is a broken process. Matched by
# shebang, not by *.sh, so extensionless scripts are not silently skipped.
shell_syntax() {
    local rc=0 f
    for f in scripts/*; do
        [ -f "$f" ] || continue
        case "$(head -1 "$f")" in
            '#!'*sh*) bash -n "$f" || { echo "gate: $f does not parse" >&2; rc=1; } ;;
        esac
    done
    return "$rc"
}
step "shell scripts parse" shell_syntax

# -- project checks ------------------------------------------------------------

compile_python() {
    python3 - bin/tf bin/teamflow-config tests/*.py <<'PY'
import sys
for path in sys.argv[1:]:
    compile(open(path, encoding="utf-8").read(), path, "exec")
PY
}
step "python compiles" compile_python

manifests_parse() {
    python3 -c 'import json, sys; [json.load(open(p)) for p in sys.argv[1:]]' \
        .claude-plugin/plugin.json .claude-plugin/marketplace.json templates/branch-ruleset.json
}
step "manifests parse" manifests_parse

step "unit tests" python3 -m unittest discover -s tests

# Agents copy these command shapes. In double quotes the shell runs backtick
# spans as commands, and Markdown bodies are full of backticks (#9).
quoting_is_safe() {
    ! grep -rnE -- '--(body|title) "' agents skills README.md
}
step "agent docs single-quote text" quoting_is_safe

# Plugin validation needs the claude CLI (no login). CI installs it, so in CI
# a missing claude fails the gate rather than skipping a required check.
missing_claude() {
    echo "gate: claude is not installed; CI must install it to validate the plugin" >&2
    return 1
}
if command -v claude >/dev/null 2>&1; then
    step "plugin validates" claude plugin validate --strict .claude-plugin/plugin.json
    step "marketplace validates" claude plugin validate --strict .
elif [ -n "${CI:-}" ]; then
    step "plugin validates" missing_claude
    step "marketplace validates" missing_claude
else
    results+=("plugin validates|skipped — claude not installed")
    results+=("marketplace validates|skipped — claude not installed")
fi

# -- summary: paste this table into the PR body / review ----------------------

printf '\n\033[1m── gate summary ─────────────────────────────\033[0m\n\n'
echo '| check | result |'
echo '| :--- | :--- |'
for row in "${results[@]}"; do
    echo "| ${row%%|*} | ${row#*|} |"
done
echo

if [ "$failed" -ne 0 ]; then
    echo "gate: FAILED — do not open a PR, do not merge." >&2
    exit 1
fi
echo "gate: green."
