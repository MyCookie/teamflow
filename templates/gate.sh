#!/usr/bin/env bash
# The merge gate. One script, so what the implementer ran and what the
# code-reviewer ran cannot drift (teamflow workflow rules).
#
# Every step runs even after an earlier one fails: a reviewer wants the whole
# picture, not the first thing that broke. Exits non-zero if any step failed.
#
# Add your project's checks in the marked section below, one `step` each.
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

# -- project checks: add lint, type-check, tests, coverage here ---------------
# step "lint" <command>
# step "tests" <command>

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
