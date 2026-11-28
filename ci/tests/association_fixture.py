"""Shared fixture for live pull-request association reads (9.5.0 I2/I3).

A live association of any PR other than the owner-pinned PR 31 needs fresh
``pulls/N`` and ``compare`` reads. ``live(run, commit)`` makes a run fixture's
live association realistic (``head_branch``, ``base.ref`` main, ``head.ref``)
and returns the consistent API responses the production binding reads, keyed by
full URL: an open same-repository PR targeting main whose head is the bound run
head, the run head within the PR head, and the tested base on main.
"""

API = "https://api.github.com/repos/codex-agent-labs/codex-agent"


def compare(ancestor, *, behind=0, status="ahead"):
    return {"status": status, "behind_by": behind, "ahead_by": 0 if status == "identical" else 1,
            "base_commit": {"sha": ancestor}, "merge_base_commit": {"sha": ancestor}}


def live(run, commit, *, branch="feature", api=API, pull_head=None):
    """Mutate ``run`` into a realistic live association; return URL -> response reads.

    ``pull_head`` is the PR's current head (default: the bound run head); the
    run head is served as its ancestor.
    """
    run.setdefault("head_branch", branch)
    branch = run["head_branch"]
    reads = {}
    for entry in run.get("pull_requests") or ():
        if not isinstance(entry, dict) or not isinstance(entry.get("number"), int):
            continue
        if isinstance(entry.get("base"), dict):
            entry["base"].setdefault("ref", "main")
        if isinstance(entry.get("head"), dict):
            entry["head"].setdefault("ref", branch)
        head = run.get("head_sha")
        if head == commit.get("sha") and isinstance(entry.get("head"), dict):
            head = entry["head"].get("sha")
        base = commit["parents"][0]["sha"]
        current = head if pull_head is None else pull_head
        reads[f"{api}/pulls/{entry['number']}"] = {
            "number": entry["number"], "state": "open", "merged": False,
            "head": {"sha": current, "ref": branch, "repo": dict(run["head_repository"])},
            "base": {"ref": "main", "repo": dict(run["repository"])}}
        reads[f"{api}/compare/{head}...{current}?per_page=1"] = compare(
            head, status="identical" if head == current else "ahead")
        reads[f"{api}/compare/{base}...main?per_page=1"] = compare(base)
    return reads


def sequence(responses, association):
    """An ``api_json`` fake: association URLs by key, everything else in order."""
    remaining = iter(responses)

    def respond(url, *args, **kwargs):
        if url in association:
            return association[url]
        return next(remaining)
    return respond
