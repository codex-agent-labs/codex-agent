"""Native-attested original verification records; never cache authority.

The caller owns immutable issuer/source pins. A signed record delegates only
completed original authentication; all product admission gates still run.
"""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time

from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_array, require_exact_keys, require_sha256,
    require_sorted_unique_records, sha256_bytes, validate_file_record,
)
from products.receipt import validate_phase_receipt


REPOSITORY = "codex-agent-labs/codex-agent"
ISSUER_WORKFLOW = ".github/workflows/reuse-qualification.yml"
LIMIT = 16 * 1024 * 1024


class QualificationIncompatible(ValueError):
    """Authenticated qualification requires ordinary cold authentication instead."""


def configure(session, environment):
    """Caller-owned pins and independent artifact files, never cached authority.

    Trusted workflows supply these values; the envelope cannot nominate its own
    issuer. This also covers later SDK CLI processes inheriting the job inputs.
    """
    names = {"path": "CODEX_AGENT_REUSE_QUALIFICATION", "bundle": "CODEX_AGENT_REUSE_QUALIFICATION_BUNDLE",
             "signer_commit": "CODEX_AGENT_REUSE_QUALIFICATION_ISSUER",
             "source_commit": "CODEX_AGENT_REUSE_QUALIFICATION_SOURCE"}
    options = {key: environment.get(name, "") for key, name in names.items()}
    if not any(options.values()):
        return
    if not all(type(value) is str and value for value in options.values()):
        raise ValueError("Portable qualification requires complete caller-owned artifact and authority pins")
    _commit(options["signer_commit"])
    _commit(options["source_commit"])
    session["portableQualificationInputs"] = options


def _commit(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ValueError("Qualification requires an immutable reviewed source commit")
    return value


def validate(value):
    value = require_exact_keys(value, {"schemaVersion", "sourceCommit", "verifierPolicySha256", "originals"},
                               "Reuse qualification")
    if type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1:
        raise ValueError("Unsupported qualification schema")
    _commit(value["sourceCommit"])
    policy = require_sha256(value["verifierPolicySha256"], "Qualification verifier policy")
    originals = require_array(value["originals"], "Qualified originals")
    if not 1 <= len(originals) <= 46:
        raise ValueError("Qualification exceeds the Runtime original phase bound")
    locators, outputs = set(), {}
    for record in originals:
        require_exact_keys(record, {"identity", "receipt", "receiptSha256", "objectSha256", "originalFiles"},
                           "Qualified original")
        identity = require_exact_keys(record["identity"], {"policy", "locator"}, "Qualified identity")
        if identity["policy"] != policy:
            raise ValueError("Qualification mixes verifier policies")
        locator = require_exact_keys(identity["locator"], {"instance", "workflowSha", "artifact", "job"},
                                     "Qualified original locator")
        _commit(locator["workflowSha"])
        receipt = validate_phase_receipt(record["receipt"])
        # Aggregate metadata is also an original phase object. The distinct
        # signed release handoff remains outside export_originals' phase gate.
        if receipt["product"] != "runtime":
            raise ValueError("Qualification is limited to original Runtime phases")
        if locator["instance"] != {k: receipt[k] for k in ("product", "component", "phase", "target")}:
            raise ValueError("Qualification changes its original phase")
        receipt_sha = sha256_bytes(canonical_json_bytes(receipt))
        if record["receiptSha256"] != receipt_sha:
            raise ValueError("Qualification changes its exact original receipt")
        require_sha256(record["objectSha256"], "Qualified original object")
        files = require_sorted_unique_records(record["originalFiles"], "Qualified original inventory")
        if not files or len(files) > 16384:
            raise ValueError("Qualified original inventory exceeds its fixed bound")
        for row in files:
            validate_file_record(row, "Qualified original member", with_kind=False, allow_empty=True)
        if sum(row["bytes"] for row in files) > 16 * 1024**3:
            raise ValueError("Qualified original inventory exceeds its byte bound")
        key = canonical_json_bytes(locator)
        if key in locators:
            raise ValueError("Qualification repeats an original identity")
        locators.add(key)
        phase_key = tuple(receipt[k] for k in ("product", "component", "phase", "target", "buildKey"))
        # Match the existing all-candidate collision gate: equal product outputs
        # may have distinct original producer/receipt/object identities.
        output = canonical_json_bytes(receipt["outputs"])
        if phase_key in outputs and outputs[phase_key] != output:
            raise ValueError("Same phase key has conflicting qualified outputs")
        outputs[phase_key] = output
    return value


def export_originals(sources, destination, *, plan, producer, source_commit, trusted_workflow_sha, token):
    """Construct claims from verifier-owned completed records, never caller JSON.

    The fixed issuer must first complete ordinary original authentication. A
    missing private completion record cannot issue a qualification.
    """
    import product_reuse as products
    from products.verified_evidence import runtime_original_cache, _source_identity

    _commit(source_commit)
    persistent = runtime_original_cache()
    if persistent is None:
        raise ValueError("Qualification issuer lacks completed original verification custody")
    policy = _source_identity()
    originals = []
    for source in sources:
        if source["kind"] != "phase":
            raise ValueError("Original qualification cannot replace aggregate signature admission")
        artifact, _original, observed, workflow = products._authenticate_runtime_original_reference_source(
            plan, producer, source, trusted_workflow_sha=trusted_workflow_sha, token=token)
        instance = products._identity(source["receipt"])
        job_name = f"product-validation / runtime-{instance.component}-{instance.phase}-{instance.target}"
        job = next(row for row in observed[0]["jobs"] if row.get("name") == job_name)
        locator = products._runtime_original_locator(artifact, workflow, instance, job)
        record = persistent.read(locator)
        if record is None or record["receipt"] != source["receipt"]:
            raise ValueError("Original qualification requires completed exact original authentication")
        originals.append({**record, "receiptSha256": sha256_bytes(canonical_json_bytes(record["receipt"]))})
    if persistent.policy != policy or _source_identity() != policy:
        raise ValueError("Qualification verifier policy changed during issue")
    value = validate({"schemaVersion": 1, "sourceCommit": source_commit,
                      "verifierPolicySha256": policy, "originals": originals})
    # The fixed issuer owns a private output directory. Never rewrite an issued
    # claim; native attestation subsequently signs these exact immutable bytes.
    with Path(destination).open("xb") as output:
        output.write(canonical_json_bytes(value))
    return value


def _compatible_verifier(commit):
    """Compare loaded consumer code to independently pinned Git bytes locally.

    The issuer's runtime-specific policy is never relabelled. Only checkout
    filenames are normalized; both profiles execute under this interpreter.
    """
    import sys
    from products.verified_evidence import _source_identity, _portable_source_path
    from products.inventory import require_relative_path

    _commit(commit)
    root = Path(__file__).resolve().parents[1]
    command = ["git", "--no-replace-objects", "-C", str(root)]
    listing = subprocess.run(command + ["ls-tree", "-rz", commit, "--", "ci", ".github"],
                             check=True, capture_output=True, timeout=30).stdout
    if len(listing) > 2 * 1024 * 1024:
        raise ValueError("Qualification baseline exceeds control-tree bound")
    expected = {}
    suffixes = {".py", ".json", ".yml", ".yaml", ".sh", ".js", ".mjs"}
    with tempfile.TemporaryDirectory(prefix="reuse-policy-baseline-") as temporary:
        baseline = Path(temporary).resolve()
        total = 0
        for entry in listing.split(b"\0"):
            if not entry:
                continue
            header, name = entry.split(b"\t", 1)
            relative = Path(require_relative_path(name.decode(), "Trusted verifier source"))
            if "tests" in relative.parts or "__pycache__" in relative.parts or "node_modules" in relative.parts:
                continue
            if relative.suffix not in suffixes:
                continue
            if not _portable_source_path(relative):
                continue
            mode, kind, oid = header.decode().split()
            if mode not in {"100644", "100755"} or kind != "blob":
                raise ValueError("Trusted verifier source is not a regular Git blob")
            raw = subprocess.run(command + ["cat-file", "blob", oid], check=True,
                                 capture_output=True, timeout=30).stdout
            total += len(raw)
            if len(raw) > LIMIT or total > 64 * 1024 * 1024:
                raise ValueError("Qualification baseline exceeds source-byte bound")
            expected[relative.as_posix()] = sha256_bytes(raw)
            target = baseline / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        def current_sources():
            observed = {}
            for directory in (root / "ci", root / ".github"):
                for target in directory.rglob("*"):
                    relative = target.relative_to(root)
                    if (target.is_file() and target.suffix in suffixes
                            and _portable_source_path(relative)
                            and not {"tests", "__pycache__", "node_modules"}.intersection(relative.parts)):
                        observed[relative.as_posix()] = sha256_bytes(read_regular_file_bytes(
                            target, max_bytes=LIMIT, reject_symlink_parents=True))
            return observed
        if current_sources() != expected:
            raise QualificationIncompatible("Current control sources differ from the authenticated issuer")
        current = _source_identity(portable=True)
        # Isolated interpreter: no caller PYTHONPATH, sitecustomize or mutable
        # checkout imports. The snapshot contains only pinned regular Git blobs.
        script = ("import sys; sys.path.insert(0, sys.argv[1]); "
                  "from products.verified_evidence import _source_identity; "
                  "print(_source_identity(portable=True))")
        result = subprocess.run([sys.executable, "-I", "-S", "-c", script, str(baseline / "ci")],
                                check=True, capture_output=True, timeout=60, cwd=baseline)
        if (len(result.stdout) > 1024 or result.stdout.decode().strip() != current
                or current_sources() != expected or _source_identity(portable=True) != current):
            raise QualificationIncompatible("Loaded verifier differs from its independently pinned source")
    return current


def authenticate(path, bundle, *, signer_commit, source_commit, policy_sha256, compatible=False):
    raw = read_regular_file_bytes(Path(path), max_bytes=LIMIT, reject_symlink_parents=True)
    signature = read_regular_file_bytes(Path(bundle), max_bytes=LIMIT, reject_symlink_parents=True)
    return _authenticate_bytes(raw, signature, signer_commit=signer_commit,
                               source_commit=source_commit, policy_sha256=policy_sha256, compatible=compatible)


def _authenticate_bytes(raw, signature, *, signer_commit, source_commit, policy_sha256, compatible=False):
    """Verify a private snapshot against caller-owned native authority pins.

    Unsupported CLI options, invalid bundles and incompatible policies fail
    closed. Nothing here elects phases or admits products.
    """
    _commit(signer_commit)
    _commit(source_commit)
    require_sha256(policy_sha256, "Current qualification policy")
    with tempfile.TemporaryDirectory(prefix="reuse-qualification-") as temporary:
        subject, signed = Path(temporary) / "qualification.json", Path(temporary) / "bundle.jsonl"
        subject.write_bytes(raw)
        signed.write_bytes(signature)
        result = subprocess.run([
            "gh", "attestation", "verify", str(subject), "--bundle", str(signed),
            "--repo", REPOSITORY, "--signer-workflow", f"{REPOSITORY}/{ISSUER_WORKFLOW}",
            "--signer-digest", signer_commit, "--source-digest", source_commit,
            "--cert-oidc-issuer", "https://token.actions.githubusercontent.com",
            "--deny-self-hosted-runners", "--format", "json",
        ], check=True, capture_output=True, timeout=120)
        verified = json.loads(result.stdout)
        if not isinstance(verified, list) or not verified or any(
                not isinstance(row, dict) or not row.get("verificationResult") for row in verified):
            raise ValueError("Native qualification authority returned no verified attestation")
        if subject.read_bytes() != raw or signed.read_bytes() != signature:
            raise ValueError("Qualification changed during native authority verification")
    value = validate(load_canonical_json_bytes(raw))
    # A reusable issuer executes its own source; native source-digest separately
    # binds the caller repository revision recorded in SLSA provenance.
    if value["sourceCommit"] != signer_commit or (value["verifierPolicySha256"] != policy_sha256
            and (not compatible or not _compatible_verifier(signer_commit))):
        raise QualificationIncompatible("Qualification has incompatible source or verifier policy")
    return value


def projection(locator, path, bundle, *, signer_commit, source_commit):
    """Materialize an exact freshly observed original inside private custody.

    Callers must build the locator through their existing fresh GitHub gates.
    The returned witness remains process-private; another process authenticates
    the signed envelope again. No product semantic gate is bypassed.
    """
    import hydrated_evidence
    from products.restore import _VERIFICATION_SESSION, _stage_fingerprint, verify_phase_shard
    from products.verified_evidence import _source_identity
    from products.registry import PhaseInstanceId
    from products.inventory import regular_file_inventory

    session = _VERIFICATION_SESSION.get()
    if session is None or hydrated_evidence.root() is None:
        return None
    policy = _source_identity()
    raw = read_regular_file_bytes(Path(path), max_bytes=LIMIT, reject_symlink_parents=True)
    signature = read_regular_file_bytes(Path(bundle), max_bytes=LIMIT, reject_symlink_parents=True)
    identity = policy, signer_commit, source_commit, sha256_bytes(raw), sha256_bytes(signature)
    qualified = session.get("portableQualification")
    if qualified is None or qualified[0] != identity:
        started = time.perf_counter()
        value = _authenticate_bytes(raw, signature, signer_commit=signer_commit,
                                    source_commit=source_commit, policy_sha256=policy, compatible=True)
        if _source_identity() != policy:
            raise ValueError("Portable qualification policy changed during authentication")
        session["qualificationVerificationSeconds"] = session.get("qualificationVerificationSeconds", 0) + (
            time.perf_counter() - started)
        session["portableQualification"] = identity, value
    else:
        value = qualified[1]
    matches = [row for row in value["originals"] if row["identity"]["locator"] == locator]
    if not matches:
        session["qualificationMisses"] = session.get("qualificationMisses", 0) + 1
        return None
    if len(matches) != 1:
        raise ValueError("Portable qualification has ambiguous original identity")
    record = matches[0]
    receipt = record["receipt"]
    instance = PhaseInstanceId(*(receipt[k] for k in ("product", "component", "phase", "target")))
    key = canonical_json_bytes(locator)
    completed = session.get("qualifiedOriginalProjections", {}).get(key)
    if completed is not None:
        if completed[2:] != (record["originalFiles"], policy):
            raise ValueError("Same original identity has conflicting qualifications")
        if _stage_fingerprint(completed[0].parent) != completed[1]:
            raise ValueError("Portable qualified projection custody changed")
        verified = verify_phase_shard(completed[0] / "shard", instance)
        if (verified["receipt"] != receipt or sha256_bytes(verified["receiptBytes"]) != record["receiptSha256"]
                or verified["objectSha256"] != record["objectSha256"]):
            raise ValueError("Same original identity has conflicting qualified receipt/object")
        return completed
    parent = session["root"] / "portable-originals" / sha256_bytes(key)[7:]
    original = parent / "original"
    rows = [row for row in record["originalFiles"] if not row["relativePath"].startswith("inputs/")]
    for row in rows:
        if not hydrated_evidence.copy(row, original / row["relativePath"]):
            # Do not leave a partial projection available to later callers.
            import shutil
            if parent.exists():
                shutil.rmtree(parent)
            session["qualificationMisses"] = session.get("qualificationMisses", 0) + 1
            return None
        session["qualificationBodyReadBytes"] = session.get("qualificationBodyReadBytes", 0) + row["bytes"]
    verified = verify_phase_shard(original / "shard", instance)
    if (verified["receipt"] != receipt or sha256_bytes(verified["receiptBytes"]) != record["receiptSha256"]
            or verified["objectSha256"] != record["objectSha256"]
            or regular_file_inventory(original, allow_empty=True) != rows or _source_identity() != policy):
        raise ValueError("Portable original differs from its authenticated qualification")
    completed = original, _stage_fingerprint(parent), record["originalFiles"], policy
    session.setdefault("qualifiedOriginalProjections", {})[key] = completed
    session["qualificationHits"] = session.get("qualificationHits", 0) + 1
    return completed


def fetch_qualification(destination, *, artifact_id, artifact_sha256, run_id, run_attempt,
                        signer_commit, source_commit, token):
    """Restore independent authority from its exact successful issuer job.

    Caller pins are explicit inputs. The cache and qualification payload choose
    neither the issuer workflow nor the original source revision.
    """
    import io
    import stat
    import zipfile
    import product_reuse as products
    from products.inventory import require_integer
    from products.verified_evidence import _source_identity

    started = time.perf_counter()
    _commit(signer_commit)
    _commit(source_commit)
    require_integer(run_id, "Qualification run", 1)
    require_integer(run_attempt, "Qualification attempt", 1)
    source = products.api_json(f"https://api.github.com/repos/{REPOSITORY}/git/commits/{source_commit}", token)
    if source.get("sha") != source_commit:
        raise ValueError("Qualification source metadata differs from caller pin")
    tree = _commit(source["tree"]["sha"])
    producer = {"commit": source_commit, "tree": tree, "runId": run_id, "runAttempt": run_attempt,
                "event": "pull_request", "repository": REPOSITORY, "pullRequest": 31,
                "workflowPath": ".github/workflows/portable-reuse-proof.yml"}
    job = "cold / qualify"
    # Product producers remain restricted to ci.yml. This separate fixed
    # authority observer elects no product and accepts only this proof issuer.
    url = f"https://api.github.com/repos/{REPOSITORY}/actions/runs/{run_id}/attempts/{run_attempt}"
    run = products.api_json(url, token)
    if (require_integer(run.get("id"), "Issuer run", 1) != run_id
            or require_integer(run.get("run_attempt"), "Issuer attempt", 1) != run_attempt
            or run.get("path") != producer["workflowPath"] or run.get("event") != "pull_request"
            or not products.run_matches_pr(run, 31)
            or any(not isinstance(run.get(field), dict)
                   or run[field].get("full_name") != REPOSITORY or run[field].get("fork") is not False
                   for field in ("repository", "head_repository"))):
        raise ValueError("Qualification issuer attempt differs from its fixed original producer")
    products._require_ci_workflow_reference(run, f"{REPOSITORY}/{ISSUER_WORKFLOW}@{signer_commit}", signer_commit)
    tested = products._observe_tested_commit(run, api="https://api.github.com", repository=REPOSITORY,
        token=token, expected_commit=source_commit, expected_tree=tree, pull_request=31)
    jobs = products.paginated_items(f"{url}/jobs", "jobs", token)
    if any(not isinstance(row, dict) for row in jobs):
        raise ValueError("Qualification issuer jobs are malformed")
    selected = products._matching_ci_jobs(jobs, job)
    if len(selected) != 1:
        raise ValueError("Qualification issuer job is missing or ambiguous")
    original_job = selected[0]
    require_integer(original_job.get("id"), "Qualification issuer job", 1)
    if (require_integer(original_job.get("run_id"), "Issuer job run", 1) != run_id
            or original_job.get("head_sha") != run["head_sha"]
            or original_job.get("status") != "completed" or original_job.get("conclusion") != "success"):
        raise ValueError("Qualification issuer job did not succeed for its exact source")
    observed = [{"run": run, "testedCommit": tested, "jobs": jobs}]
    name = f"reuse-qualification-{run_id}-{run_attempt}"
    artifact = products._contract_ci_upload_metadata(artifact_id, artifact_sha256, name,
        producer, observed[0]["run"], token)
    products._require_artifact_job_window(observed[0], job, artifact)
    _, raw = products._download_contract_ci_upload(artifact_id, artifact_sha256, name,
        producer, observed[0]["run"], token, max_bytes=32 * 1024 * 1024)
    expected = {"qualification.json", "bundle.jsonl", "qualification-issue.json", "proof.json",
                "prepare.json", "cache-save.json"}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if (len(members) != len(expected) or {row.filename for row in members} != expected
                or sum(row.file_size for row in members) > 32 * 1024 * 1024):
            raise ValueError("Qualification artifact has unexpected or repeated members")
        for row in members:
            mode = row.external_attr >> 16
            if row.file_size > LIMIT or (stat.S_IFMT(mode) not in (0, stat.S_IFREG)):
                raise ValueError("Qualification artifact is not bounded regular evidence")
        destination = Path(destination).resolve()
        destination.mkdir(exist_ok=False)
        for row in members:
            with (destination / row.filename).open("xb") as output:
                output.write(archive.read(row))  # Native ZIP CRC checked; no product ZIP policy change.
    value = authenticate(destination / "qualification.json", destination / "bundle.jsonl",
        signer_commit=signer_commit, source_commit=source_commit,
        policy_sha256=_source_identity(),
        compatible=True)
    report = {"artifact": artifact, "qualificationSha256": sha256_bytes(canonical_json_bytes(value)),
              "downloadedQualificationBytes": len(raw), "seconds": str(time.perf_counter() - started)}
    from products.inventory import write_canonical_json
    write_canonical_json(destination / "qualification-restore.json", report)
    return report


def _original_receipt_bytes(source, references):
    """Exact authenticated receipt copy; original full-upload verification follows."""
    raw = canonical_json_bytes(source["receipt"])
    expected = [row for row in references
                if row["relativePath"] == source["relativePath"] + "/shard/phase-receipt.json"
                and row["source"] == source["relativePath"]
                and row["sourcePath"] == "shard/phase-receipt.json"]
    if (len(expected) != 1 or expected[0]["sha256"] != sha256_bytes(raw)
            or expected[0]["bytes"] != len(raw)):
        raise ValueError("Expected original receipt differs from its authenticated carrier member")
    return raw


def process_read_bytes():
    """Linux root-process rchar; child tools/cache transport are measured separately."""
    path = Path("/proc/self/io")
    if not path.exists():
        return None
    fields = dict(line.split(": ", 1) for line in path.read_text().splitlines())
    return int(fields["rchar"])


def issue_frozen(work, token):
    """Fixed issuer entrypoint: authenticate preserved evidence, produce no bytes."""
    import os
    import shutil
    import hydrated_evidence
    import hosted_reuse_proof as proof
    import product_reuse as products
    from products.restore import verification_session
    from products.inventory import git_regular_blob_bytes, write_canonical_json

    commit = _commit(os.environ["QUALIFICATION_ISSUER_SHA"])
    if (os.environ["QUALIFICATION_ISSUER_REPOSITORY"] != REPOSITORY
            or os.environ["QUALIFICATION_ISSUER_PATH"] != ISSUER_WORKFLOW):
        raise ValueError("Qualification issuer is not the fixed native workflow")
    root = Path(__file__).resolve().parents[1]
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                          capture_output=True, timeout=30).stdout.decode().strip()
    if head != commit or not _compatible_verifier(commit):
        raise ValueError("Qualification issuer checkout differs from its native workflow identity")
    spec_bytes = read_regular_file_bytes(proof.SPEC, max_bytes=LIMIT, reject_symlink_parents=True)
    if git_regular_blob_bytes(root, commit, "ci/tests/data/hosted-frozen-reuse.json", max_bytes=LIMIT) != spec_bytes:
        raise ValueError("Fixed frozen closure fixture differs from the issuer source")
    spec = load_canonical_json_bytes(spec_bytes)
    work = Path(work).resolve()
    work.mkdir(exist_ok=False)
    started = time.perf_counter()
    read_before = process_read_bytes()
    with verification_session() as session:
        if session.get("portableQualificationInputs"):
            raise ValueError("The original issuer cannot consume portable qualification")
        proof.prepare(spec, work, token)
        from runtime_reference_transport import validate_original_references
        refs = validate_original_references(load_canonical_json_bytes(read_regular_file_bytes(
            work / "original/runtime-original-references.json", reject_symlink_parents=True)))
        sources = [source for source in refs["sources"] if source["kind"] == "phase"]
        if len(sources) != 46:
            raise ValueError("Issuer changes the frozen original closure")
        for number, source in enumerate(sources):
            receipt = source["receipt"]
            instance = products._identity(receipt)
            capture = work / "cold-capture"
            raw = _original_receipt_bytes(source, refs["references"])
            receipt_path = work / "expected-receipt.json"
            with receipt_path.open("xb") as output:
                output.write(raw)
            products.capture_runtime_original_ci_phases(
                {instance.phase: receipt_path},
                capture, target=instance.component, original_instance=instance,
                trusted_workflow_sha=spec["carrier"]["workflowSha"], token=token, recovery_projection=True)
            original = capture / "phases" / instance.phase / "original"
            for row in products.regular_file_inventory(original, allow_empty=True):
                hydrated_evidence.retain(row, original / row["relativePath"])
            shutil.rmtree(capture)
            receipt_path.unlink()
            print(json.dumps({"fullyAuthenticatedOriginal": number + 1, "of": 46}), flush=True)
        if session.get("downloadedArtifactCount", 0) < 47:
            raise ValueError("Controlled cold issuer did not freshly authenticate every original upload")
        export_originals(sources, work / "qualification.json",
            plan={"event": "pull_request", "pullRequest": 31, "repository": REPOSITORY},
            producer=proof.PRODUCER, source_commit=commit,
            trusted_workflow_sha=spec["carrier"]["workflowSha"], token=token)
        proof.verify(spec, work, token)
        report = {"mode": "cold-original-qualification", "seconds": str(time.perf_counter() - started),
                  "downloadedArtifactCount": session.get("downloadedArtifactCount", 0),
                  "downloadedArtifactBytes": session.get("downloadedArtifactBytes", 0),
                  "originalColdArchiveBytes": session.get("runtimeColdArchiveBytes", 0),
                  "qualifiedOriginals": len(sources), "selectedProductPhases": 0,
                  "rootProcessReadBytes": process_read_bytes() - read_before if read_before is not None else None,
                  "qualificationSha256": sha256_bytes((work / "qualification.json").read_bytes())}
        write_canonical_json(work / "qualification-issue.json", report)
    return report


if __name__ == "__main__":
    import argparse
    import os
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("issue-frozen", "fetch"))
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--artifact-id", type=int)
    parser.add_argument("--artifact-sha256")
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--run-attempt", type=int)
    parser.add_argument("--signer-commit")
    parser.add_argument("--source-commit")
    args = parser.parse_args()
    import reuse_qualification
    if args.mode == "issue-frozen":
        reuse_qualification.issue_frozen(args.work, os.environ["GITHUB_TOKEN"])
    else:
        reuse_qualification.fetch_qualification(args.work, artifact_id=args.artifact_id,
            artifact_sha256=args.artifact_sha256, run_id=args.run_id, run_attempt=args.run_attempt,
            signer_commit=args.signer_commit, source_commit=args.source_commit, token=os.environ["GITHUB_TOKEN"])
