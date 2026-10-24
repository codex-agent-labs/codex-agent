"""Acquisition plumbing around the unchanged owner-approved production verifier."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
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
    ".github/workflows/ci.yml",
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


def git(root, *args, data=None):
    for attempt in range(2):
        try:
            return subprocess.run(["git", "--no-replace-objects", "-C", str(root), *args],
                                  input=data, check=True, capture_output=True, timeout=120).stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            if args[:1] != ("fetch",):
                raise
            raw = error.stderr or b""
            text = raw.lower()
            kind = "unknown"
            for category, markers in (
                ("authentication", (b"authentication failed", b"could not read username",
                                    b"permission denied", b"repository not found")),
                ("certificate", (b"certificate", b"ssl peer")),
                ("object-unavailable", (b"not our ref", b"couldn't find remote ref",
                                        b"unadvertised object", b"bad object", b"not a valid object")),
            ):
                if any(marker in text for marker in markers):
                    kind = category
                    break
            status = re.findall(rb"requested url returned error: ([0-9]{3})(?:\D|$)", text)
            if kind == "unknown":
                if status:
                    transient = all(int(code) == 429 or 500 <= int(code) <= 599 for code in status)
                    kind = "http-transient" if transient else "http-permanent"
                elif isinstance(error, subprocess.TimeoutExpired) or any(message in text for message in (
                        b"operation timed out", b"connection timed out")):
                    kind = "transport-timeout"
                elif any(message in text for message in (
                        b"connection reset by peer", b"recv failure: connection was reset",
                        b"send failure: connection was reset")):
                    kind = "transport-reset"
            retry = attempt == 0 and kind in {"http-transient", "transport-timeout", "transport-reset"}
            # Never echo Git's untrusted stderr, URLs, headers or credentials.
            print(json.dumps({"gitFetchFailure": kind, "attempt": attempt + 1,
                "exitCode": getattr(error, "returncode", None), "retry": retry,
                "stderrSha256": "sha256:" + hashlib.sha256(raw).hexdigest()}, sort_keys=True), file=sys.stderr)
            if not retry:
                raise
            time.sleep(2)


def blobs(root, objects):
    objects = tuple(dict.fromkeys(objects))
    request = b"".join((authority.commit(oid) + "\n").encode() for oid in objects)
    headers = git(root, "cat-file", "--batch-check", data=request).splitlines()
    if len(headers) != len(objects):
        raise ValueError("Approved Git blob metadata is incomplete")
    sizes = []
    for oid, header in zip(objects, headers):
        fields = header.split()
        if len(fields) != 3 or fields[:2] != [oid.encode(), b"blob"]:
            raise ValueError("Approved Git blob metadata differs")
        size = int(fields[2])
        if not 0 <= size <= 16 * 1024 * 1024:
            raise ValueError("Approved execution source exceeds bound")
        sizes.append(size)
    if sum(sizes) > 64 * 1024 * 1024:
        raise ValueError("Approved execution source exceeds total bound")
    stream = io.BytesIO(git(root, "cat-file", "--batch", data=request))
    result = {}
    for oid, header, size in zip(objects, headers, sizes):
        if stream.readline() != header + b"\n":
            raise ValueError("Approved Git blob response differs")
        raw = stream.read(size)
        if len(raw) != size or stream.read(1) != b"\n":
            raise ValueError("Approved Git blob response is incomplete")
        result[oid] = raw
    if stream.read(1):
        raise ValueError("Approved Git blob response has trailing bytes")
    return result


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
        expected[path.as_posix()] = (oid, mode)
    originals = blobs(root, (oid for oid, _ in expected.values()))
    expected = {name: (originals[oid], mode) for name, (oid, mode) in expected.items()}
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
    builder = predicate["runDetails"]["builder"]["id"]
    workflow = REPOSITORY_URL + "/.github/workflows/reuse-qualification.yml@"
    relative_builder = workflow + "refs/pull/31/merge"
    if (statement.get("predicateType") != "https://slsa.dev/provenance/v1"
            or statement.get("subject") != [{"name": "qualification.json", "digest": {
                "sha256": record["qualificationSha256"].removeprefix("sha256:")}}]
            or definition.get("externalParameters", {}).get("workflow") != {
                "path": ".github/workflows/portable-reuse-proof.yml", "ref": "refs/pull/31/merge",
                "repository": REPOSITORY_URL}
            or builder not in (workflow + record["issuerSha"], relative_builder)
            or predicate["runDetails"]["metadata"]["invocationId"] != REPOSITORY_URL +
                f"/actions/runs/{record['runId']}/attempts/{record['runAttempt']}"
            or len(dependencies) != 1 or dependencies[0]["uri"] != "git+" + REPOSITORY_URL + "@refs/pull/31/merge"
            or builder == relative_builder and dependencies[0]["digest"]["gitCommit"] != record["issuerSha"]):
        raise ValueError("Verified historical qualification provenance is cross-paired")
    return authority.commit(dependencies[0]["digest"]["gitCommit"])


def restore(root, work, value, artifact_id, token):
    import product_reuse as products
    import reuse_qualification as qualification
    from products.inventory import sha256_file, load_canonical_json_bytes
    records = [r for r in value["qualifications"]
               if (r["issuerSha"] == value["activeVerifier"] if artifact_id is None
                   else r["artifactId"] == artifact_id)]
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


def completed_descriptor(raw, value):
    """Owner policy selects separate semantic authority; never relabel body qualification."""
    from products.inventory import load_canonical_json_bytes, require_exact_keys, canonical_json_bytes
    from runtime_reference_transport import validate_sdk_input_source
    document = load_canonical_json_bytes(raw)
    require_exact_keys(document, {"schemaVersion", "policy", "retainedSdkInputsSource", "gitHistory"},
                       "Protected completed-reuse descriptor")
    if type(document["schemaVersion"]) is not int or document["schemaVersion"] != 1:
        raise ValueError("Unsupported protected completed reuse descriptor")
    policy = document["policy"]
    extra = {"requalificationBaseline"} if type(policy) is dict and "requalificationBaseline" in policy else set()
    require_exact_keys(policy, {"schemaVersion", "kind", "consumerCommit", "verifierPolicySha256",
        "artifactId", "artifactSha256", "runId", "runAttempt", "signerCommit", "sourceCommit", "sdkCompletion"} | extra,
        "Protected completed reuse policy")
    if (type(policy["schemaVersion"]) is not int or policy["schemaVersion"] != 1
            or policy["kind"] != "completed-frozen-reuse"
            or policy["consumerCommit"] != value["activeVerifier"]):
        raise ValueError("Completed reuse policy differs from active approved consumer")
    authority.digest(policy["verifierPolicySha256"])
    if len(canonical_json_bytes(policy)) > 4096:
        raise ValueError("Completed reuse policy exceeds consumer bound")
    import reuse_qualification as qualification
    qualification._native_pin_arguments(policy["sdkCompletion"])
    for pins in (policy, policy["sdkCompletion"]):
        authority.digest(pins["artifactSha256"])
        for key in ("artifactId", "runId", "runAttempt"):
            if type(pins[key]) is not int or pins[key] <= 0:
                raise ValueError("Completed native locator is not a positive exact identity")
        for key in ("signerCommit", "sourceCommit"):
            if authority.commit(pins[key]) not in value["approvedVerifiers"]:
                raise ValueError("Completed reuse issuer/source is not independently approved")
    original = [row for row in value["qualifications"] if row["artifactId"] == policy["artifactId"]]
    if len(original) != 1 or any(original[0][field] != policy[field] for field in
            ("artifactId", "artifactSha256", "runId", "runAttempt")) or original[0]["issuerSha"] != policy["signerCommit"]:
        raise ValueError("Completed frozen proof differs from preserved qualification identity")
    validate_sdk_input_source(document["retainedSdkInputsSource"])
    records = document["gitHistory"]
    if not isinstance(records, list) or not 1 <= len(records) <= 145:
        raise ValueError("Completed reuse Git history is missing or excessive")
    seen = set()
    for record in records:
        require_exact_keys(record, {"repository", "commit", "tree"}, "Approved original Git identity")
        if record["repository"] != authority.REPOSITORY or authority.commit(record["commit"]) in seen:
            raise ValueError("Conflicting completed reuse Git history")
        authority.commit(record["tree"])
        seen.add(record["commit"])
    if extra:
        baseline = authority.commit(policy["requalificationBaseline"])
        if baseline not in value["approvedVerifiers"] or baseline not in seen:
            raise ValueError("Requalification baseline lacks independent approval and exact Git custody")
    return document


def completed_sdk_spec(root, document, value):
    """Resolve the retained source through the approved native issuer's fixed parent."""
    from products.inventory import git_regular_blob_bytes, load_canonical_json_bytes
    from reuse_qualification import _sdk_completed_spec_path
    issuer = document["policy"]["sdkCompletion"]["signerCommit"]
    spec = load_canonical_json_bytes(git_regular_blob_bytes(root,
        issuer, _sdk_completed_spec_path(root, issuer), max_bytes=16 * 1024 * 1024))
    count = 1
    if spec.get("schemaVersion") in (2, 3, 4):
        from completed_sdk_reuse import _spec
        _spec(spec)
        if any(spec["parent"][field] not in value["approvedVerifiers"] for field in ("signerCommit", "sourceCommit")):
            raise ValueError("Incremental native parent is not independently approved")
        count += len(spec["completedPhases"])
        parent = spec["parent"]["signerCommit"]
        spec = load_canonical_json_bytes(git_regular_blob_bytes(root,
            parent, _sdk_completed_spec_path(root, parent), max_bytes=16 * 1024 * 1024))
    if type(spec.get("schemaVersion")) is not int or spec["schemaVersion"] != 1:
        raise ValueError("Completed reuse requires the fixed original native SDK source")
    return spec, count


def retained_sdk_binding_current(root, document):
    baseline = document["policy"].get("requalificationBaseline")
    if baseline is None:
        return True
    from products.inventory import tree_entries
    from products.registry import NATIVE_BINDINGS, PHASE_INSTANCE_IDS
    from products.selection import phase_inventory_paths
    from reuse_qualification import _changed_inventory_paths
    before, after = (dict(tree_entries(root, revision)) for revision in
                     (baseline, document["policy"]["consumerCommit"]))
    changed = _changed_inventory_paths(before, after)
    # The transport producer and public trust are inputs even where their
    # product inventory is owned only by native SDK consumers.
    if "ci/products/sdk_inputs.py" in changed or any(path.startswith("gradle/release/keys/") for path in changed):
        return False
    # Android and native SDK adapters do not produce the shared input bundle.
    # This exports only a locator; consumers still authenticate exact inputs.
    return not any(phase_inventory_paths(changed, phase) for phase in PHASE_INSTANCE_IDS
                   if phase.component not in {"sdk-android", *NATIVE_BINDINGS})


def completed_environment(root, work, value):
    from products.inventory import canonical_json_bytes, git_regular_blob_bytes, load_canonical_json_bytes
    raw = authority.contents(".reuse/completed-reuse.json", value["authorityCommit"])
    document = completed_descriptor(raw, value)
    acquired = [history(root, record) for record in document["gitHistory"]]
    spec, _ = completed_sdk_spec(root, document, value)
    if document["retainedSdkInputsSource"] != spec["sdkInputs"]["source"]:
        raise ValueError("Approved SDK source pin differs from the native issuer's fixed source")
    # This only distributes caller-owned pins. Each actual CLI independently
    # acquires native proof and checks current inputs before any completed reuse.
    paths = {}
    for name, field in (("completed-reuse-policy.json", "policy"),
                        ("retained-sdk-inputs-source.json", "retainedSdkInputsSource")):
        path = work / name
        with path.open("xb") as output:
            output.write(canonical_json_bytes(document[field]))
        paths[field] = str(path)
    if authority.contents(".reuse/completed-reuse.json", value["authorityCommit"]) != raw:
        raise ValueError("Approved completed reuse descriptor changed during provisioning")
    result = {"kind": "completed-reuse-policy", "authorityCommit": value["authorityCommit"],
              "approvedConsumerCommit": value["activeVerifier"],
              "descriptorSha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
              "originalGit": acquired, "productArtifactDownloads": 0,
              "nativeAuthentication": "required by each explicit consumer"}
    return result, {"CODEX_AGENT_COMPLETED_REUSE_POLICY": paths["policy"],
                    "CODEX_AGENT_RETAINED_SDK_INPUTS_SOURCE": (
                        paths["retainedSdkInputsSource"] if retained_sdk_binding_current(root, document) else "")}


def verify_completed(root, work, value, token):
    """Freshly verify semantic completion authority; no body-replay/projection claim."""
    import reuse_qualification as qualification
    from products.inventory import load_canonical_json_bytes
    document = completed_descriptor(authority.contents(".reuse/completed-reuse.json", value["authorityCommit"]), value)
    policy = document["policy"]
    pins = {key: policy[key] for key in ("artifactId", "artifactSha256", "runId", "runAttempt", "signerCommit", "sourceCommit")}
    cap, report = qualification.fetch_completed_frozen(work / "verification-authority",
        consumer_commit=value["activeVerifier"], verifier_policy_sha256=policy["verifierPolicySha256"],
        sdk_completion=policy["sdkCompletion"], repository_root=root,
        **({"requalification_baseline": policy["requalificationBaseline"]}
           if "requalificationBaseline" in policy else {}),
        revision=git(root, "rev-parse", "HEAD").decode().strip(), token=token,
        **qualification._native_pin_arguments(pins))
    _, expected_sdk = completed_sdk_spec(root, document, value)
    invalidated = report.get("invalidatedPhases", [])
    if (report["productBodiesDownloaded"] != 0
            or report["completedFrozenPhases"] + report["completedSdkPhases"] + len(invalidated) != 50 + expected_sdk
            or report.get("requalificationBaseline") != policy.get("requalificationBaseline")
            or ("requalificationBaseline" not in policy and (
                report["completedFrozenPhases"] != 50 or report["completedSdkPhases"] != expected_sdk or invalidated))):
        raise ValueError("Completed reuse verifier differs from its exact retained coverage")
    return {"kind": "completed-reuse-verification", "approvedConsumerCommit": value["activeVerifier"],
            "nativeCompletion": report, "selectedProductPhases": 0}


def main():
    started = time.perf_counter()
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("operation", choices=("setup", "provision", "restore", "verify"))
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--expected-authority-commit")
    parser.add_argument("--artifact-id", type=int)
    args = parser.parse_args()
    root, work = args.repository_root.resolve(strict=True), args.work.absolute()
    work.mkdir(parents=True, exist_ok=True)
    if args.operation == "provision" and (args.artifact_id is not None or any(os.environ.get(name)
            for name in ("REQUESTED_ARTIFACT_SHA", "REQUESTED_RUN", "REQUESTED_ATTEMPT",
                         "REQUESTED_ISSUER", "REQUESTED_SOURCE"))):
        raise ValueError("Combined provisioning only accepts native completion pins")
    value = approved(args.expected_authority_commit)
    os.chdir(root)  # Existing production commands use the consumer checkout as cwd.
    environment = None
    if args.operation in {"setup", "provision"}:
        result = snapshot(root, value, work)
        if args.operation == "provision":
            snapshot_result = result
            result, environment = completed_environment(root, work, value)
            authority.protection(authority.api(f"branches/{authority.BRANCH}/protection"))
            if authority.api(f"branches/{authority.BRANCH}")["commit"]["sha"] != value["authorityCommit"]:
                raise ValueError("Approval reference changed during provisioning")
            result["executionSnapshot"] = snapshot_result
    else:
        sys.path.insert(0, str(root / "ci"))
        import reuse_qualification
        reuse_qualification._compatible_verifier(value["activeVerifier"])
        token = os.environ.get("GITHUB_TOKEN", "")
        if args.operation == "restore":
            if args.artifact_id is None:
                if any(os.environ.get(name) for name in ("REQUESTED_ARTIFACT_SHA", "REQUESTED_RUN",
                        "REQUESTED_ATTEMPT", "REQUESTED_ISSUER", "REQUESTED_SOURCE")):
                    raise ValueError("Original qualification assertions require an explicit artifact selector")
                result, environment = completed_environment(root, work, value)
            else:
                result = restore(root, work, value, args.artifact_id, token)
                environment = qualification_environment(work, result, work / "hydrated-evidence")
        elif args.artifact_id is None:
            result = verify_completed(root, work, value, token)
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
    if environment is not None:
        if any("\n" in item or "\r" in item for item in environment.values()):
            raise ValueError("Invalid runner environment value")
        with Path(os.environ["GITHUB_ENV"]).open("a") as output:
            for name, item in environment.items():
                output.write(name + "=" + item + "\n")
    result["operationSeconds"] = str(time.perf_counter() - started)
    (work / (args.operation + ".json")).write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
