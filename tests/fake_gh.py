#!/usr/bin/env python3
"""A stand-in for the `gh` subcommands tf uses, for tests only.

State lives in the JSON file $FAKE_GH_STATE. PR heads are read from the bare
repository $FAKE_GH_BARE, which plays GitHub's copy of the branches.
$FAKE_GH_LOGGED_OUT makes `gh auth status` fail.
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
    head = git("rev-parse", f"refs/heads/{p['head']}")
    files = git("diff", "--name-only", f"{p['base']}...{head}").split()
    return {"title": p["title"], "body": p["body"], "state": p["state"], "headRefName": p["head"],
            "baseRefName": p["base"], "headRefOid": head, "files": [{"path": f} for f in files]}


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
        elif verb == "view":
            i = state["issues"][rest[0]]
            print(json.dumps({"title": i["title"], "state": i["state"], "body": i["body"],
                              "labels": [{"name": l} for l in i["labels"]], "comments": i["comments"]}))
        elif verb == "comment":
            state["issues"][rest[0]]["comments"].append({"createdAt": "2026-01-01T00:00:00Z", "body": opt(rest, "--body")})
            save(state)
        elif verb == "close":
            state["issues"][rest[0]]["state"] = "CLOSED"
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
            print(json.dumps(pr_json(state, rest[0])))
        elif verb == "checks":
            if "--required" in rest and not state["required"]:
                print("no required checks reported on the 'x' branch", file=sys.stderr)
                sys.exit(1)
            print(json.dumps(state["checks"].get(pr_json(state, rest[0])["headRefOid"], [])))
        elif verb == "review":
            state["reviews"].append({"pr": rest[0], "body": opt(rest, "--body")})
            save(state)
        elif verb == "merge":
            if opt(rest, "--match-head-commit") != pr_json(state, rest[0])["headRefOid"]:
                print("head branch was modified", file=sys.stderr)
                sys.exit(1)
            state["merges"].append({"pr": rest[0], "auto": "--auto" in rest, "subject": opt(rest, "--subject")})
            if "--auto" not in rest:
                state["prs"][rest[0]]["state"] = "MERGED"
            save(state)
        return

    if noun == "api":
        path = next(a for a in rest + [verb] if a.startswith("repos/"))
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
