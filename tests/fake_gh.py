#!/usr/bin/env python3
"""A stand-in for the `gh` subcommands tf uses, for tests only.

State lives in the JSON file $FAKE_GH_STATE. PR heads are read from the bare
repository $FAKE_GH_BARE, which plays GitHub's copy of the branches.
$FAKE_GH_LOGGED_OUT makes `gh auth status` fail. "rulesets_forbidden" in the
state makes the rulesets API answer 403, as on a free private repository;
"rulesets_error" makes it fail with a 500. "remote_files" lists the paths the
contents API finds on the default branch. "check_seq" maps a head SHA to a list
of buckets for the `gate` check: each `pr checks` call reads the first and drops
it, except the last, which stays. A bucket of "empty" answers with no checks, and
"error" fails the call with an HTTP 502. "required_errors" is a count of
`pr checks --required` calls that fail that way before the rest answer. "reads" counts the `pr checks`
calls, as {"required": n, "all": m}. "checks_stdout" makes every `pr checks` call print that text
and exit 1 with nothing on stderr. "revoke_on_pending" makes a `pr checks`
answer that holds a pending check also record a failure of the review status on the head, as
a reviewer rejecting it meanwhile would. "change_on_pending" does the same with a dict of PR fields
(`base`, `state`, `oid` for a new head SHA) that it sets on the PR, as a push, a retarget or a close would. A `pr checks`
answer that holds a pending check exits 8, which `gh pr checks --help` documents as
"8: Checks pending". The help does not say what `--json` prints or exits with, so that
the JSON is still printed alongside exit 8 is unverified; it is what this fake does.
A PR's "auto_merge" key (set by `pr merge --auto`) makes `autoMergeRequest` an object, else null;
that real gh prints null for an unarmed PR was not checked, and tf treats null and a missing key alike.
"""

import json
import os
import re
import subprocess
import sys

STATE = os.environ["FAKE_GH_STATE"]
BARE = os.environ.get("FAKE_GH_BARE", "")


def load():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"next": 1, "issues": {}, "prs": {}, "statuses": {}, "checks": {},
                "required": False, "reviews": [], "merges": []}


def save(state):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def opt(args, name, many=False):
    values = [args[i + 1] for i, a in enumerate(args[:-1]) if a == name]
    return values if many else (values[-1] if values else None)


def git(*args):
    return subprocess.run(["git", "--git-dir", BARE, *args], text=True, capture_output=True).stdout.strip()


def pr_json(state, n):
    p = state["prs"][n]
    head = p.get("oid") or git("rev-parse", f"refs/heads/{p['head']}")
    files = git("diff", "--name-only", f"{p['base']}...{head}").split()
    return {"title": p["title"], "body": p["body"], "state": p["state"], "headRefName": p["head"],
            "baseRefName": p["base"], "headRefOid": head, "files": [{"path": f} for f in files],
            "mergeStateStatus": p.get("merge_state", "CLEAN"),
            "autoMergeRequest": {"enabledBy": {"login": "fake"}, "mergeMethod": "SQUASH"} if p.get("auto_merge") else None}


def main():
    args = sys.argv[1:]
    if "-R" in args:
        i = args.index("-R")
        del args[i:i + 2]
    state = load()
    noun, verb, rest = (args + ["", ""])[0], (args + ["", ""])[1], args[2:]

    if noun == "auth" and verb == "status":
        sys.exit(1 if os.environ.get("FAKE_GH_LOGGED_OUT") else 0)

    if noun == "issue":
        if verb == "create":
            n = str(state["next"])
            state["next"] += 1
            state["issues"][n] = {"title": opt(rest, "--title"), "body": opt(rest, "--body"),
                                  "labels": opt(rest, "--label", many=True), "state": "OPEN", "comments": []}
            save(state)
            print(f"https://github.com/me/repo/issues/{n}")
        elif verb == "list":
            wanted = re.findall(r'"([^"]+)"', opt(rest, "--search") or "")
            out = [{"number": int(n), "title": i["title"], "labels": [{"name": l} for l in i["labels"]]}
                   for n, i in state["issues"].items()
                   if i["state"] == "OPEN" and (not wanted or set(wanted) & set(i["labels"]))]
            print(json.dumps(out))
        elif verb in ("view", "comment", "edit", "close") and rest[0] not in state["issues"]:
            # gh: "GraphQL: Could not resolve to an Issue" (not run against real gh)
            sys.exit("could not resolve to an Issue with the number of " + rest[0])
        elif verb == "view":
            i = state["issues"][rest[0]]
            print(json.dumps({"title": i["title"], "state": i["state"], "body": i["body"],
                              "labels": [{"name": l} for l in i["labels"]], "comments": i["comments"]}))
        elif verb == "comment":
            state["issues"][rest[0]]["comments"].append({"createdAt": "2026-01-01T00:00:00Z", "body": opt(rest, "--body")})
            save(state)
        elif verb == "edit":
            i = state["issues"][rest[0]]
            drop = opt(rest, "--remove-label", many=True)
            i["labels"] = [l for l in i["labels"] if l not in drop] + \
                [l for l in opt(rest, "--add-label", many=True) if l not in i["labels"]]
            save(state)
        elif verb == "close":
            state["issues"][rest[0]]["state"] = "CLOSED"
            save(state)
        return

    if noun == "label":
        if verb == "list":
            print(json.dumps([{"name": l} for l in state.get("labels", [])]))
        elif verb == "create":
            state.setdefault("labels", []).append(rest[0])
            save(state)
        return

    if noun == "pr":
        if verb == "create":
            n = str(state["next"])
            state["next"] += 1
            state["prs"][n] = {"title": opt(rest, "--title"), "body": opt(rest, "--body"),
                               "head": opt(rest, "--head"), "base": opt(rest, "--base"), "state": "OPEN"}
            save(state)
            print(f"https://github.com/me/repo/pull/{n}")
        elif verb == "list":
            print(json.dumps([{"number": int(n), "title": p["title"], "headRefName": p["head"], "baseRefName": p["base"]}
                              for n, p in state["prs"].items() if p["state"] == "OPEN"]))
        elif verb == "view":
            wanted = (opt(rest, "--json") or "").split(",")
            print(json.dumps({k: v for k, v in pr_json(state, rest[0]).items() if k in wanted}))
        elif verb == "checks":
            reads = state.setdefault("reads", {"required": 0, "all": 0})
            reads["required" if "--required" in rest else "all"] += 1
            save(state)
            if "checks_stdout" in state:
                print(state["checks_stdout"])
                sys.exit(1)
            if "--required" in rest and state.get("required_errors", 0) > 0:
                state["required_errors"] -= 1
                save(state)
                print("gh: HTTP 502", file=sys.stderr)
                sys.exit(1)
            if "--required" in rest and not state["required"]:
                print("no required checks reported on the 'x' branch", file=sys.stderr)
                sys.exit(1)
            sha = pr_json(state, rest[0])["headRefOid"]
            seq = state.get("check_seq", {}).get(sha)
            if seq:
                if len(seq) > 1:
                    state["check_seq"][sha] = seq[1:]
                    save(state)
                if seq[0] == "error":
                    print("gh: HTTP 502", file=sys.stderr)
                    sys.exit(1)
                checks = [] if seq[0] == "empty" else [{"name": "gate", "bucket": seq[0]}]
            else:
                checks = state["checks"].get(sha, [])
            pending = any(c["bucket"] == "pending" for c in checks)
            if pending and state.get("revoke_on_pending"):
                state["statuses"].setdefault(sha, []).insert(
                    0, {"context": "teamflow/code-review", "state": "failure", "description": "REQUEST_CHANGES"})
                save(state)
            if pending and state.get("change_on_pending"):
                state["prs"][rest[0]].update(state.pop("change_on_pending"))
                save(state)
            print(json.dumps(checks))
            sys.exit(8 if pending else 0)
        elif verb == "review":
            state["reviews"].append({"pr": rest[0], "body": opt(rest, "--body")})
            save(state)
        elif verb == "merge":
            if opt(rest, "--match-head-commit") != pr_json(state, rest[0])["headRefOid"]:
                print("head branch was modified", file=sys.stderr)
                sys.exit(1)
            state["merges"].append({"pr": rest[0], "auto": "--auto" in rest, "subject": opt(rest, "--subject")})
            if "--auto" in rest:
                state["prs"][rest[0]]["auto_merge"] = True
            else:
                state["prs"][rest[0]]["state"] = "MERGED"
            save(state)
        return

    if noun == "api":
        path = next(a for a in rest + [verb] if a.startswith("repos/"))
        method = opt(args, "--method") or "GET"
        if path.endswith("/rulesets"):
            if state.get("rulesets_error"):
                print("gh: Server Error (HTTP 500)", file=sys.stderr)
                sys.exit(1)
            if state.get("rulesets_forbidden"):
                print('{"message":"Upgrade to GitHub Pro or make this repository public to enable this feature.","status":"403"}')
                print("gh: Upgrade to GitHub Pro or make this repository public to enable this feature. (HTTP 403)", file=sys.stderr)
                sys.exit(1)
            if method == "POST":
                with open(opt(args, "--input"), encoding="utf-8") as f:
                    state.setdefault("rulesets", []).append(json.load(f))
                save(state)
            print(json.dumps(state.get("rulesets", [])))
            return
        if "/contents/" in path:
            wanted = path.split("/contents/", 1)[1].split("?", 1)[0]
            if wanted not in state.get("remote_files", []):
                print("gh: Not Found (HTTP 404)", file=sys.stderr)
                sys.exit(1)
            print(json.dumps({"path": wanted}))
            return
        found = re.fullmatch(r"repos/[^/]+/[^/]+/issues/(\d+)", path)
        if found:
            # GitHub's REST issues endpoint also answers for PRs, marked by a "pull_request" key
            # (documented; not run against real gh)
            n = found.group(1)
            if n in state["prs"]:
                print(json.dumps({"number": int(n), "pull_request": {}}))
            elif n in state["issues"]:
                print(json.dumps({"number": int(n)}))
            else:
                print("gh: Not Found (HTTP 404)", file=sys.stderr)
                sys.exit(1)
            return
        if re.fullmatch(r"repos/[^/]+/[^/]+", path):
            if method == "PATCH":
                for field in opt(args, "-F", many=True):
                    key, value = field.split("=", 1)
                    state.setdefault("repo", {})[key] = value == "true"
                save(state)
            print(json.dumps(state.get("repo", {})))
            return
        sha = path.rsplit("/", 2)[-2] if path.endswith("/status") else path.rsplit("/", 1)[-1]
        if "--method" in args:
            fields = dict(f.split("=", 1) for f in opt(args, "-f", many=True))
            state["statuses"].setdefault(sha, []).insert(0, fields)
            save(state)
        else:
            latest, seen = [], set()
            for s in state["statuses"].get(sha, []):
                if s["context"] not in seen:
                    seen.add(s["context"])
                    latest.append(s)
            print(json.dumps({"statuses": latest}))
        return

    sys.exit(f"fake gh: unsupported command {args}")


if __name__ == "__main__":
    main()
