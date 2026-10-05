"""Resolve owner-approved immutable controls; this file runs from the protected ref."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

REPOSITORY = "codex-agent-labs/codex-agent"
BRANCH = "reuse-authority"
OWNER = ("ciurlaro", 19213191)
LIMIT = 2 * 1024 * 1024


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Repeated authority field")
        value[key] = item
    return value


def decode(raw):
    if len(raw) > LIMIT:
        raise ValueError("Authority response exceeds bound")
    return json.loads(raw, object_pairs_hook=unique)


def commit(value):
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{40}", value):
        raise ValueError("Authority requires an exact immutable commit")
    return value


def digest(value):
    if not isinstance(value, str) or not re.fullmatch("sha256:[0-9a-f]{64}", value):
        raise ValueError("Authority requires an exact content hash")


def protection(value):
    restrictions = value.get("restrictions", {})
    users = restrictions.get("users", [])
    if ([(u.get("login"), u.get("id")) for u in users] != [OWNER]
            or restrictions.get("teams") != [] or restrictions.get("apps") != []
            or value.get("enforce_admins", {}).get("enabled") is not True
            or value.get("block_creations", {}).get("enabled") is not True
            or value.get("allow_force_pushes", {}).get("enabled") is not False
            or value.get("allow_deletions", {}).get("enabled") is not False):
        raise ValueError("Approval source is not protected for the sole owner")


def manifest(value):
    if set(value) != {"schemaVersion", "activeVerifier", "approvedVerifiers", "qualifications"} or type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1:
        raise ValueError("Unsupported authority manifest")
    approved = value["approvedVerifiers"]
    if not isinstance(approved, list) or not approved or len(approved) > 100:
        raise ValueError("Missing or excessive approved verifier identities")
    if len(set(map(commit, approved))) != len(approved) or commit(value["activeVerifier"]) not in approved:
        raise ValueError("Conflicting verifier approval")
    seen = set()
    records = value["qualifications"]
    if not isinstance(records, list) or not records or len(records) > 100:
        raise ValueError("Missing or excessive retained qualifications")
    for row in records:
        if set(row) != {"artifactId", "artifactSha256", "runId", "runAttempt", "issuerSha", "qualificationSha256"}:
            raise ValueError("Unexpected qualification locator fields")
        for key in ("artifactId", "runId", "runAttempt"):
            if type(row[key]) is not int or row[key] <= 0:
                raise ValueError("Qualification locator is not an exact positive identity")
        for key in ("artifactSha256", "qualificationSha256"):
            digest(row[key])
        if commit(row["issuerSha"]) not in approved or row["artifactId"] in seen:
            raise ValueError("Unapproved or conflicting qualification authority")
        seen.add(row["artifactId"])
    return value


def api(path):
    environment = os.environ.copy()
    credential = environment.get("REUSE_AUTHORITY_READ_TOKEN")
    if environment.get("GITHUB_ACTIONS") == "true" and not credential:
        raise ValueError("Hosted authority resolution needs REUSE_AUTHORITY_READ_TOKEN")
    if credential:
        environment["GH_TOKEN"] = credential
    result = subprocess.run(["gh", "api", "--hostname", "github.com", "--method", "GET",
                             f"repos/{REPOSITORY}/{path}"], env=environment,
                            capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError("Cannot freshly read the independent approval source")
    return decode(result.stdout)


def contents(path, revision):
    value = api(f"contents/{path}?ref={commit(revision)}")
    if value.get("type") != "file" or value.get("path") != path or value.get("encoding") != "base64":
        raise ValueError("Approval source member is not a regular immutable file")
    raw = base64.b64decode(value["content"].replace("\n", ""), validate=True)
    if len(raw) > 64 * 1024:
        raise ValueError("Approval source member exceeds bound")
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if blob != value.get("sha"):
        raise ValueError("Approval member differs from its immutable Git identity")
    return raw


def resolve(expected=None):
    if expected is not None:
        commit(expected)
    elif os.environ.get("GITHUB_ACTIONS") == "true":
        raise ValueError("Hosted resolution requires the native authority commit")
    branch = api(f"branches/{BRANCH}")
    revision = commit(branch["commit"]["sha"])
    if branch.get("name") != BRANCH or branch.get("protected") is not True or (expected is not None and expected != revision):
        raise ValueError("Native approval revision is missing, stale or cross-paired")
    protection(api(f"branches/{BRANCH}/protection"))
    # The native protected workflow/action and the fresh ref must agree.
    if contents(".reuse/resolve.py", revision) != Path(__file__).read_bytes():
        raise ValueError("Executing resolver differs from owner-approved code")
    raw = contents(".reuse/approvals.json", revision)
    value = manifest(decode(raw))
    protection(api(f"branches/{BRANCH}/protection"))
    if api(f"branches/{BRANCH}")["commit"]["sha"] != revision:
        raise ValueError("Approval reference changed during resolution")
    return {"authorityCommit": revision, "manifestSha256": "sha256:" + hashlib.sha256(raw).hexdigest(), **value}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--expected-authority-commit")
    args = parser.parse_args()
    print(json.dumps(resolve(args.expected_authority_commit), sort_keys=True))
