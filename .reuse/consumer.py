"""Acquisition plumbing around the unchanged owner-approved production verifier."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import zipfile

import resolve as authority

OVERLAY = frozenset({
    ".github/workflows/portable-reuse-proof.yml",
    ".github/workflows/reuse-qualification.yml",
    ".github/workflows/hosted-reuse-cache-proof.yml",
    ".github/actions/restore-reuse-qualification/action.yml",
    ".github/workflows/product-validation.yml",
    ".github/workflows/sdk-core-validation.yml",
})
SUFFIXES = {".py", ".json", ".yml", ".yaml", ".sh", ".js", ".mjs"}
IGNORED = {"tests", "__pycache__", "node_modules"}
REPOSITORY_URL = "https://github.com/" + authority.REPOSITORY


def regular(path, maximum=16 * 1024 * 1024):
    path = Path(path).absolute()
    for parent in (*reversed(path.parents), path):
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("Execution source has a symlink parent or member")
    if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
        raise ValueError("Execution source is not a bounded regular file")
    with path.open("rb") as source:
        raw = source.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError("Execution source exceeds bound")
    return raw


def git(root, *args):
    return subprocess.run(["git", "--no-replace-objects", "-C", str(root), *args],
                          check=True, capture_output=True, timeout=120).stdout


def history(root, producer):
    if producer.get("repository") != authority.REPOSITORY:
        raise ValueError("Historical source repository differs")
    revision, tree = authority.commit(producer["commit"]), authority.commit(producer["tree"])
    try:
        observed = git(root, "rev-parse", revision + "^{tree}").decode().strip()
    except subprocess.CalledProcessError:
        git(root, "fetch", "--no-tags", REPOSITORY_URL + ".git", revision)
        observed = git(root, "rev-parse", revision + "^{tree}").decode().strip()
    if observed != tree:
        raise ValueError("Historical Git tree differs from authenticated provenance")
    return {"commit": revision, "tree": tree}


def approved(expected):
    # Composite actions have no job.workflow_sha for their own repository.
    # Their three executing files must match the independently protected ref;
    # reusable jobs additionally bind the native job.workflow_sha directly.
    if expected is None:
        expected = authority.commit(authority.api(f"branches/{authority.BRANCH}")["commit"]["sha"])
    value = authority.resolve(expected)
    root = Path(__file__).resolve().parents[1]
    for name in (".reuse/consumer.py", ".github/actions/restore-reuse-qualification/action.yml"):
        if authority.contents(name, value["authorityCommit"]) != regular(root / name):
            raise ValueError("Executing acquisition source differs from protected approval")
    return value


def snapshot(root, value, work):
    revision = value["activeVerifier"]
    try:
        git(root, "cat-file", "-e", revision + "^{commit}")
    except subprocess.CalledProcessError:
        git(root, "fetch", "--no-tags", REPOSITORY_URL + ".git", revision)
    before = git(root, "rev-parse", "HEAD").decode().strip()
    expected = {}
    for entry in git(root, "ls-tree", "-rz", revision, "--", "ci", ".github").split(b"\0"):
        if not entry:
            continue
        header, name = entry.split(b"\t", 1)
        path = Path(name.decode())
        if path.suffix not in SUFFIXES or IGNORED.intersection(path.parts):
            continue
        mode, kind, oid = header.decode().split()
        if mode not in {"100644", "100755"} or kind != "blob":
            raise ValueError("Approved execution source is not a regular Git blob")
        raw = git(root, "cat-file", "blob", oid)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError("Approved execution source exceeds bound")
        expected[path.as_posix()] = (raw, mode)
    observed = {p.relative_to(root).as_posix() for directory in (root / "ci", root / ".github")
                for p in directory.rglob("*") if p.is_file() and p.suffix in SUFFIXES
                and not IGNORED.intersection(p.relative_to(root).parts)}
    if not expected or observed != set(expected) or sum(len(raw) for raw, _ in expected.values()) > 64 * 1024 * 1024:
        raise ValueError("Current production control inventory differs from approved source")
    changed = []
    for name, (raw, mode) in expected.items():
        current = regular(root / name)
        if current != raw:
            if name not in OVERLAY:
                raise ValueError("Current verifier/policy differs; owner approval and cold authentication required")
            changed.append((name, raw, mode, current))
    # All Python modules are already exact approved bytes before importing them.
    sys.path.insert(0, str(root / "ci"))
    from products.registry import PHASE_INSTANCE_IDS
    from products.selection import phase_inventory_paths
    if any(phase_inventory_paths(OVERLAY, instance) for instance in PHASE_INSTANCE_IDS):
        raise ValueError("Execution snapshot would alter product-owned files")
    records = []
    for name, raw, mode, current in changed:
        retained = work / "compiled-plumbing" / name
        retained.parent.mkdir(parents=True, exist_ok=True)
        with retained.open("xb") as output:
            output.write(current)
        target = root / name
        descriptor, temporary = tempfile.mkstemp(prefix=".approved-control-", dir=target.parent)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(raw)
                os.fchmod(output.fileno(), 0o755 if mode == "100755" else 0o644)
            os.replace(temporary, target)
        finally:
            if Path(temporary).exists():
                Path(temporary).unlink()
        records.append({"path": name, "compiledCallerSha256": "sha256:" + hashlib.sha256(current).hexdigest(),
                        "executionSnapshotSha256": "sha256:" + hashlib.sha256(raw).hexdigest()})
    if git(root, "rev-parse", "HEAD").decode().strip() != before:
        raise ValueError("Product Git identity changed during approved acquisition")
    import reuse_qualification
    profile = reuse_qualification._compatible_verifier(revision)
    return {"authorityCommit": value["authorityCommit"], "verifierCommit": revision,
            "consumerCommit": before, "portableProfile": profile, "productPhasesOwned": 0,
            "overlaidControlFiles": records}


def original_source(verified, record):
    if not isinstance(verified, list) or len(verified) != 1:
        raise ValueError("Native authority verdict is missing or ambiguous")
    statement = verified[0]["verificationResult"]["statement"]
    predicate = statement["predicate"]
    definition = predicate["buildDefinition"]
    dependencies = definition["resolvedDependencies"]
    if (statement.get("predicateType") != "https://slsa.dev/provenance/v1"
            or statement.get("subject") != [{"name": "qualification.json", "digest": {
                "sha256": record["qualificationSha256"].removeprefix("sha256:")}}]
            or definition.get("externalParameters", {}).get("workflow") != {
                "path": ".github/workflows/portable-reuse-proof.yml", "ref": "refs/pull/31/merge",
                "repository": REPOSITORY_URL}
            or predicate["runDetails"]["builder"]["id"] != REPOSITORY_URL +
                "/.github/workflows/reuse-qualification.yml@" + record["issuerSha"]
            or predicate["runDetails"]["metadata"]["invocationId"] != REPOSITORY_URL +
                f"/actions/runs/{record['runId']}/attempts/{record['runAttempt']}"
            or len(dependencies) != 1 or dependencies[0]["uri"] != "git+" + REPOSITORY_URL + "@refs/pull/31/merge"):
        raise ValueError("Verified historical qualification provenance is cross-paired")
    return authority.commit(dependencies[0]["digest"]["gitCommit"])


def restore(root, work, value, artifact_id, token):
    import product_reuse as products
    import reuse_qualification as qualification
    from products.inventory import sha256_file, load_canonical_json_bytes
    records = [r for r in value["qualifications"] if artifact_id is None or r["artifactId"] == artifact_id]
    if len(records) != 1:
        raise ValueError("Retained qualification authority is missing or ambiguous")
    record = records[0]
    for field, environment in (("artifactSha256", "REQUESTED_ARTIFACT_SHA"), ("runId", "REQUESTED_RUN"),
                               ("runAttempt", "REQUESTED_ATTEMPT"), ("issuerSha", "REQUESTED_ISSUER")):
        requested = os.environ.get(environment)
        if requested and requested != str(record[field]):
            raise ValueError("Caller assertion is cross-paired with approved original authority")
    started = time.perf_counter()
    url = f"https://api.github.com/repos/{authority.REPOSITORY}/actions/artifacts/{record['artifactId']}"
    artifact = products.api_json(url, token)
    if (artifact.get("id") != record["artifactId"] or artifact.get("digest") != record["artifactSha256"]
            or artifact.get("expired") is not False or artifact.get("archive_download_url") != url + "/zip"
            or artifact.get("workflow_run", {}).get("id") != record["runId"]):
        raise ValueError("Preliminary qualification transport differs from approved original")
    archive = work / "source-discovery.zip"
    products.download_artifact_to_file(artifact, token, archive, max_bytes=32 * 1024 * 1024)
    preliminary = work / "source-discovery"
    preliminary.mkdir()
    with zipfile.ZipFile(archive) as zipped:
        members = zipped.infolist()
        if len(members) != 6 or len({m.filename for m in members}) != 6:
            raise ValueError("Qualification ZIP has conflicting members")
        for name in ("qualification.json", "bundle.jsonl"):
            member = zipped.getinfo(name)
            if member.file_size > qualification.LIMIT or stat.S_IFMT(member.external_attr >> 16) not in (0, stat.S_IFREG):
                raise ValueError("Qualification native subject is not bounded regular evidence")
            (preliminary / name).write_bytes(zipped.read(member))
    if sha256_file(preliminary / "qualification.json") != record["qualificationSha256"]:
        raise ValueError("Original qualification subject differs from independent approval")
    # This first native verification locates the historical source only. The
    # unchanged production fetch below repeats every required pin/job/policy gate.
    result = subprocess.run(["gh", "attestation", "verify", str(preliminary / "qualification.json"),
        "--bundle", str(preliminary / "bundle.jsonl"), "--repo", authority.REPOSITORY,
        "--signer-workflow", authority.REPOSITORY + "/.github/workflows/reuse-qualification.yml",
        "--signer-digest", record["issuerSha"], "--cert-oidc-issuer", "https://token.actions.githubusercontent.com",
        "--deny-self-hosted-runners", "--format", "json"], check=True, capture_output=True, timeout=120)
    source = original_source(authority.decode(result.stdout), record)
    if os.environ.get("REQUESTED_SOURCE") and os.environ["REQUESTED_SOURCE"] != source:
        raise ValueError("Caller source assertion differs from authenticated original provenance")
    destination = work / "qualification"
    report = qualification.fetch_qualification(destination, artifact_id=record["artifactId"],
        artifact_sha256=record["artifactSha256"], run_id=record["runId"], run_attempt=record["runAttempt"],
        signer_commit=record["issuerSha"], source_commit=source, token=token)
    if report["qualificationSha256"] != record["qualificationSha256"]:
        raise ValueError("Completed native qualification changed its expected subject")
    qualified_raw = regular(destination / "qualification.json")
    if "sha256:" + hashlib.sha256(qualified_raw).hexdigest() != record["qualificationSha256"]:
        raise ValueError("Authenticated original receipt changed before history acquisition")
    qualified = load_canonical_json_bytes(qualified_raw)
    aggregate = [r for r in qualified["originals"] if all(r["receipt"].get(k) == v for k, v in
        {"product": "runtime", "component": "runtime-aggregate", "phase": "metadata", "target": "aggregate"}.items())]
    if len(aggregate) != 1:
        raise ValueError("Authenticated aggregate metadata receipt is missing or ambiguous")
    historical = history(root, aggregate[0]["receipt"]["producer"])
    return {"seconds": str(time.perf_counter() - started), "originalSourceCommit": source,
            "originalAggregateGit": historical, "issuerCommit": record["issuerSha"],
            "sourceDiscoveryDownloadBytes": archive.stat().st_size,
            "qualificationDownloadBytes": report["downloadedQualificationBytes"], "artifact": record}


def qualification_environment(work, result, body_root):
    return {"CODEX_AGENT_HYDRATED_EVIDENCE": str(body_root),
            "CODEX_AGENT_REUSE_QUALIFICATION": str(work / "qualification/qualification.json"),
            "CODEX_AGENT_REUSE_QUALIFICATION_BUNDLE": str(work / "qualification/bundle.jsonl"),
            "CODEX_AGENT_REUSE_QUALIFICATION_ISSUER": result["issuerCommit"],
            "CODEX_AGENT_REUSE_QUALIFICATION_SOURCE": result["originalSourceCommit"]}


def main():
    started = time.perf_counter()
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("operation", choices=("setup", "restore", "verify"))
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--expected-authority-commit")
    parser.add_argument("--artifact-id", type=int)
    args = parser.parse_args()
    root, work = args.repository_root.resolve(strict=True), args.work.absolute()
    work.mkdir(parents=True, exist_ok=True)
    value = approved(args.expected_authority_commit)
    os.chdir(root)  # Existing production commands use the consumer checkout as cwd.
    if args.operation == "setup":
        result = snapshot(root, value, work)
    else:
        sys.path.insert(0, str(root / "ci"))
        import reuse_qualification
        reuse_qualification._compatible_verifier(value["activeVerifier"])
        token = os.environ.get("GITHUB_TOKEN", "")
        if args.operation == "restore":
            result = restore(root, work, value, args.artifact_id, token)
            environment = qualification_environment(work, result, work / "hydrated-evidence")
            with Path(os.environ["GITHUB_ENV"]).open("a") as output:
                for name, item in environment.items():
                    if "\n" in item or "\r" in item:
                        raise ValueError("Invalid runner environment value")
                    output.write(name + "=" + item + "\n")
        else:
            # A later process freshly reobserves the qualification producer too;
            # private files or environment values are never a portable witness.
            reauthentication = work / "verification-authority"
            reauthentication.mkdir()
            fresh = restore(root, reauthentication, value, args.artifact_id, token)
            os.environ.update(qualification_environment(reauthentication, fresh, work / "hydrated-evidence"))
            import hosted_reuse_proof as proof
            spec = proof.load_canonical_json_bytes(regular(proof.SPEC))
            proof.ROOT = root
            proof.verify(spec, work / "proof", token)
            result = {"approvedVerifierCommit": value["activeVerifier"],
                      "consumerCommit": git(root, "rev-parse", "HEAD").decode().strip(),
                      "freshQualificationAuthority": fresh}
    result["operationSeconds"] = str(time.perf_counter() - started)
    (work / (args.operation + ".json")).write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
