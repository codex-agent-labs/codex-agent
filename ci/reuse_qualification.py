"""Native-attested original verification records; never cache authority.

The caller owns immutable issuer/source pins. A signed record delegates only
completed original authentication; all product admission gates still run.
"""
import json
from contextlib import contextmanager
from pathlib import Path
import re
import subprocess
import tempfile
import time
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_array, require_exact_keys, require_sha256,
    require_sorted_unique_records, sha256_bytes, validate_file_record,
)
from products.receipt import validate_phase_receipt
from runtime_reference_transport import measured, count


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


def _changed_inventory_paths(before, after):
    """Compare complete Git entries; validate unchanged paths as well as changes."""
    from products.selection import _normalized_paths
    paths = set(_normalized_paths(before)) | set(_normalized_paths(after))
    return tuple(sorted(path for path in paths if before.get(path) != after.get(path)))


def validate(value):
    value = require_exact_keys(value, {"schemaVersion", "sourceCommit", "verifierPolicySha256", "originals"},
                               "Reuse qualification")
    if type(value["schemaVersion"]) is not int or value["schemaVersion"] not in (1, 2):
        raise ValueError("Unsupported qualification schema")
    _commit(value["sourceCommit"])
    policy = require_sha256(value["verifierPolicySha256"], "Qualification verifier policy")
    originals = require_array(value["originals"], "Qualified originals")
    if not 1 <= len(originals) <= (46 if value["schemaVersion"] == 1 else 47):
        raise ValueError("Qualification exceeds the original phase bound")
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
        sdk_binary = tuple(receipt[k] for k in ("product", "component", "phase", "target")) == (
            "sdk", "sdk-ios", "binary", "ios")
        if receipt["product"] != "runtime" and not (value["schemaVersion"] == 2 and sdk_binary):
            raise ValueError("Qualification does not support this original phase")
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
            if sdk_binary and not row["relativePath"].startswith("shard/"):
                raise ValueError("SDK qualification covers only the fully verified original shard")
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
        if source["kind"] not in {"phase", "sdk-binary"}:
            raise ValueError("Original qualification cannot replace aggregate signature admission")
        artifact, _original, observed, workflow = products._authenticate_runtime_original_reference_source(
            plan, producer, source, trusted_workflow_sha=trusted_workflow_sha, token=token)
        instance = products._identity(source["receipt"])
        prefix = "sdk" if source["kind"] == "sdk-binary" else "runtime"
        job_name = f"product-validation / {prefix}-{instance.component}-{instance.phase}-{instance.target}"
        matches = products._matching_ci_jobs(observed[0]["jobs"], job_name,
            **({"expected_build_key": source["receipt"]["buildKey"]} if prefix == "sdk" else {}))
        if len(matches) != 1:
            raise ValueError("Qualified original job is missing or ambiguous")
        job = matches[0]
        locator = products._runtime_original_locator(artifact, workflow, instance, job)
        record = persistent.read(locator)
        if record is None or record["receipt"] != source["receipt"]:
            raise ValueError("Original qualification requires completed exact original authentication")
        originals.append({**record, "receiptSha256": sha256_bytes(canonical_json_bytes(record["receipt"]))})
    if persistent.policy != policy or _source_identity() != policy:
        raise ValueError("Qualification verifier policy changed during issue")
    value = validate({"schemaVersion": 2 if any(row["receipt"]["product"] == "sdk" for row in originals) else 1,
                      "sourceCommit": source_commit,
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
        sources = {}
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
            sources[relative] = oid
        blobs = read_blobs(root, sources.values(), max_bytes=LIMIT, total_bytes=64 * 1024 * 1024)
        if sum(len(blobs[oid]) for oid in sources.values()) > 64 * 1024 * 1024:
            raise ValueError("Qualification baseline exceeds source-byte bound")
        for relative, oid in sources.items():
            raw = blobs[oid]
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
    require_sha256(policy_sha256, "Current qualification policy")
    _authenticate_native_subject(raw, signature, "qualification.json",
        signer_commit=signer_commit, source_commit=source_commit)
    value = validate(load_canonical_json_bytes(raw))
    # A reusable issuer executes its own source; native source-digest separately
    # binds the caller repository revision recorded in SLSA provenance.
    if value["sourceCommit"] != signer_commit or (value["verifierPolicySha256"] != policy_sha256
            and (not compatible or not _compatible_verifier(signer_commit))):
        raise QualificationIncompatible("Qualification has incompatible source or verifier policy")
    return value


@measured
def _authenticate_native_subject(raw, signature, name, *, signer_commit, source_commit):
    """Only native signature authentication; the distinct caller validates its claim."""
    _commit(signer_commit)
    _commit(source_commit)
    if name not in {"qualification.json", "completion.json"}:
        raise ValueError("Unsupported native reuse subject")
    with tempfile.TemporaryDirectory(prefix="reuse-qualification-") as temporary:
        subject, signed = Path(temporary) / name, Path(temporary) / "bundle.jsonl"
        subject.write_bytes(raw)
        signed.write_bytes(signature)
        command = [
            "gh", "attestation", "verify", str(subject), "--bundle", str(signed),
            "--repo", REPOSITORY, "--signer-workflow", f"{REPOSITORY}/{ISSUER_WORKFLOW}",
            "--signer-digest", signer_commit, "--source-digest", source_commit,
            "--cert-oidc-issuer", "https://token.actions.githubusercontent.com",
            "--deny-self-hosted-runners", "--format", "json",
        ]
        for attempt in range(2):
            try:
                result = subprocess.run(command, check=True, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, timeout=120)
                break
            except subprocess.CalledProcessError as error:
                if error.stderr:
                    print(error.stderr.decode("utf-8", errors="replace"), file=sys.stderr, end="")
                if (attempt or error.returncode != 1 or not any(message in (error.stderr or b"") for message in (
                        b"public good verifier is not available (initialization may have failed)",
                        b"error creating Sigstore verifier: no valid Sigstore verifiers could be initialized"))):
                    raise
                # Retry only verifier startup, never an invalid attestation.
                # The same private bytes, identity pins and full crypto gate run
                # again; a second failure remains fatal. No healthy-path delay.
                count("nativeSignatureInitializationRetries")
                time.sleep(2)
        verified = json.loads(result.stdout)
        if not isinstance(verified, list) or not verified or any(
                not isinstance(row, dict) or not row.get("verificationResult") for row in verified):
            raise ValueError("Native qualification authority returned no verified attestation")
        if subject.read_bytes() != raw or signed.read_bytes() != signature:
            raise ValueError("Qualification changed during native authority verification")


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
    from products.verified_evidence import _source_identity
    from products.inventory import write_canonical_json

    started = time.perf_counter()
    report, _ = _fetch_qualification_archive(destination, artifact_id=artifact_id,
        artifact_sha256=artifact_sha256, run_id=run_id, run_attempt=run_attempt,
        signer_commit=signer_commit, source_commit=source_commit, token=token)
    destination = Path(destination).resolve()
    value = authenticate(destination / "qualification.json", destination / "bundle.jsonl",
        signer_commit=signer_commit, source_commit=source_commit,
        policy_sha256=_source_identity(), compatible=True)
    report.update(qualificationSha256=sha256_bytes(canonical_json_bytes(value)),
                  seconds=str(time.perf_counter() - started))
    write_canonical_json(destination / "qualification-restore.json", report)
    return report


@measured
def _fetch_qualification_archive(destination, *, artifact_id, artifact_sha256, run_id, run_attempt,
                                 signer_commit, source_commit, token, _completed_sdk=False):
    """Fresh native origin and whole ZIP authentication shared by distinct consumers."""
    import io
    import stat
    import zipfile
    import product_reuse as products
    from products.inventory import require_integer
    from products.restore import bounded_verify
    _commit(signer_commit)
    _commit(source_commit)
    require_integer(run_id, "Qualification run", 1)
    require_integer(run_attempt, "Qualification attempt", 1)
    url = f"https://api.github.com/repos/{REPOSITORY}/actions/runs/{run_id}/attempts/{run_attempt}"
    # Independent fresh reads from caller-pinned endpoints; join every result
    # before validating the issuer or reading any artifact body.
    source, run, jobs = bounded_verify(lambda read: read(), (
        lambda: products.api_json(f"https://api.github.com/repos/{REPOSITORY}/git/commits/{source_commit}", token),
        lambda: products.api_json(url, token),
        lambda: products.paginated_items(f"{url}/jobs", "jobs", token)))
    if source.get("sha") != source_commit:
        raise ValueError("Qualification source metadata differs from caller pin")
    tree = _commit(source["tree"]["sha"])
    producer = {"commit": source_commit, "tree": tree, "runId": run_id, "runAttempt": run_attempt,
                "event": "pull_request", "repository": REPOSITORY, "pullRequest": 31,
                "workflowPath": ".github/workflows/portable-reuse-proof.yml"}
    job = "completion / completed-sdk" if _completed_sdk else "cold / qualify"
    # Product producers remain restricted to ci.yml. This separate fixed
    # authority observer elects no product and accepts only this proof issuer.
    if (require_integer(run.get("id"), "Issuer run", 1) != run_id
            or require_integer(run.get("run_attempt"), "Issuer attempt", 1) != run_attempt
            or run.get("path") != producer["workflowPath"] or run.get("event") != "pull_request"
            or not products.run_matches_pr(run, 31)
            or any(not isinstance(run.get(field), dict)
                   or run[field].get("full_name") != REPOSITORY or run[field].get("fork") is not False
                   for field in ("repository", "head_repository"))):
        raise ValueError("Qualification issuer attempt differs from its fixed original producer")
    products._require_ci_workflow_reference(run, f"{REPOSITORY}/{ISSUER_WORKFLOW}@{signer_commit}", signer_commit)
    tested = products._validate_tested_commit(run, source,
        expected_commit=source_commit, expected_tree=tree, pull_request=31)
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
    name = f"{'sdk-completed-reuse' if _completed_sdk else 'reuse-qualification'}-{run_id}-{run_attempt}"
    artifact = products._contract_ci_upload_metadata(artifact_id, artifact_sha256, name,
        producer, observed[0]["run"], token)
    products._require_artifact_job_window(observed[0], job, artifact)
    size, limit = artifact["size_in_bytes"], 32 * 1024 * 1024
    if size > limit:
        raise ValueError("Contract uploaded artifact exceeds the transport limit")
    _, raw = products._reuse_contract_ci_upload(artifact, producer, run, token,
        destination=None, limit=limit, artifact_sha256=artifact_sha256, size=size)
    expected = ({"completion.json", "bundle.jsonl"} if _completed_sdk else
                {"qualification.json", "bundle.jsonl", "qualification-issue.json", "proof.json",
                 "prepare.json", "cache-save.json"})
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
        captured = {}
        for row in members:
            captured[row.filename] = archive.read(row)  # Native CRC checked before any consumer sees bytes.
            with (destination / row.filename).open("xb") as output:
                output.write(captured[row.filename])
    return {"artifact": artifact, "downloadedQualificationBytes": len(raw)}, captured


_COMPLETED_FROZEN = object()
_SDK_COMPLETED_SPEC = "ci/tests/data/sdk-completed-resume.json"
_PHASE_FIELDS = ("product", "component", "phase", "target")
_OBJECT_FIELDS = ("buildKey", "receiptSha256", "objectSha256")


def _frozen_spec_path(root, commit):
    """Only the caller-pinned native issuer tree can select its fixed successor."""
    successor = "ci/tests/data/requalified-frozen-reuse.json"
    found = subprocess.run(["git", "--no-replace-objects", "-C", str(root),
        "cat-file", "-e", _commit(commit) + ":" + successor], capture_output=True, timeout=30)
    return successor if found.returncode == 0 else "ci/tests/data/hosted-frozen-reuse.json"


def _sdk_original_spec_path(root, commit):
    """Keep the original cold bootstrap's fixed SDK fixture immutable."""
    successor = "ci/tests/data/requalified-sdk-ios-qualification.json"
    found = subprocess.run(["git", "--no-replace-objects", "-C", str(root),
        "cat-file", "-e", _commit(commit) + ":" + successor], capture_output=True, timeout=30)
    return successor if found.returncode == 0 else "ci/tests/data/sdk-ios-qualification.json"


def _sdk_completed_spec_path(root, commit):
    """Historical native SDK proofs retain their original fixed recipe."""
    successor = "ci/tests/data/requalified-sdk-completed-resume.json"
    found = subprocess.run(["git", "--no-replace-objects", "-C", str(root),
        "cat-file", "-e", _commit(commit) + ":" + successor], capture_output=True, timeout=30)
    return successor if found.returncode == 0 else _SDK_COMPLETED_SPEC


def _phase_records(records, label):
    from products.registry import PHASE_INSTANCE_IDS, PhaseInstanceId
    result = {}
    for record in require_array(records, label):
        instance = PhaseInstanceId(*(record.get(field) for field in _PHASE_FIELDS))
        if instance not in PHASE_INSTANCE_IDS or instance in result:
            raise ValueError(f"{label} has an unknown or duplicate phase")
        result[instance] = record
    return result


def _completed_sdk_controls(spec, controls, frozen, original):
    """Check exact preserved controls; native authentication is required separately."""
    if set(controls) != {row["relativePath"] for row in spec["controls"]}:
        raise ValueError("Completed SDK proof changes its fixed control members")
    for row in spec["controls"]:
        validate_file_record(row, "Completed SDK control", with_kind=False)
        raw = canonical_json_bytes(controls[row["relativePath"]])
        if len(raw) != row["bytes"] or sha256_bytes(raw) != row["sha256"]:
            raise ValueError("Completed SDK control differs from its approved original")
    prefix = "product-resume-state/"
    request, result = (controls[prefix + name] for name in ("reuse-wave-request.json", "reuse-wave-result.json"))
    phases = _phase_records(result["phases"], "Completed SDK result")
    available = _phase_records(request["availableObjects"], "Completed SDK originals")
    retained = [row for row in phases.values() if row["state"] == "retained"]
    count = spec.get("retainedPhaseCount", 52)
    if type(count) is not int or count not in (51, 52):
        raise ValueError("Completed SDK source requires its fixed fifty-one or fifty-two phase scope")
    if (len(retained) != count or len(available) != count or result["matrices"]["contract"]
            or result["matrices"]["runtime"] or request["catalogs"] != frozen["request"]["catalogs"]
            or request["repositoryRevision"] != spec["producer"]["commit"]
            or request["repository"] != REPOSITORY or request["pullRequest"] != 31
            or request["versions"] != frozen["request"]["versions"]):
        raise ValueError("Completed SDK proof changes the successful original resume scope")
    for instance, row in _phase_records(frozen["expectedResult"]["phases"], "Frozen phases").items():
        if (phases.get(instance, {}).get("state") != "retained" or any(
                phases[instance][field] != row[field] or available.get(instance, {}).get(field) != row[field]
                for field in _OBJECT_FIELDS)):
            raise ValueError("Completed SDK proof changes a frozen predecessor")
    from products.registry import PhaseInstanceId
    instance = PhaseInstanceId("sdk", "sdk-ios", "binary", "ios")
    if count == 51 and (set(available) != set(_phase_records(frozen["expectedResult"]["phases"],
            "Frozen phases")) | {instance} or set(available) != {key for key, row in phases.items()
                                                               if row["state"] == "retained"}):
        raise ValueError("Completed SDK first successor contains unrelated phases")
    phase = phases[instance]
    receipt = validate_phase_receipt(controls[
        prefix + "prior-failed-sdk/sdk-ios/binary/ios/original/shard/phase-receipt.json"])
    if (phase["state"] != "retained" or spec["completedPhase"] != {
            field: phase[field] for field in (*_PHASE_FIELDS, *_OBJECT_FIELDS)}
            or any(available[instance][field] != phase[field] for field in _OBJECT_FIELDS)
            or receipt != original["receipt"]
            or sha256_bytes(canonical_json_bytes(receipt)) != phase["receiptSha256"]
            or original["objectSha256"] != phase["objectSha256"]):
        raise ValueError("Completed SDK proof changes the approved iOS receipt or object")
    from products.restore import object_relative_path
    member = prefix + available[instance]["objectPath"]
    if member != (prefix + "prior-failed-sdk/sdk-ios/binary/ios/original/shard/"
                  + object_relative_path(phase["buildKey"], phase["receiptSha256"])):
        raise ValueError("Completed SDK proof changes the exact preserved object member")
    return request, phase, receipt, member


def _observe_completed_sdk_resume(spec, token):
    import product_reuse as products
    from products.registry import PhaseInstanceId
    role = spec.get("sourceRole", "resume")
    if role not in ("resume", "plan"):
        raise ValueError("Completed SDK source has an unsupported fixed job role")
    job = "product-validation / " + ("plan" if role == "plan" else "product-resume")
    observed = products._observe_ci_producer_jobs({"resume": spec["producer"]},
        jobs_by_phase={"resume": job}, trusted_workflow_sha=spec["workflowSha"], token=token)
    selected = products._matching_ci_jobs(observed[0]["jobs"], job)
    if len(selected) != 1 or selected[0]["id"] != spec["jobId"]:
        raise ValueError("Completed SDK resume differs from its approved successful job")
    name = f"codex-agent-{'planned-' if role == 'plan' else ''}product-resume-{spec['producer']['tree']}"
    artifact = products._contract_ci_upload_metadata(spec["artifactId"], spec["artifactSha256"],
        name, spec["producer"], observed[0]["run"], token)
    if artifact["size_in_bytes"] != spec["artifactBytes"]:
        raise ValueError("Completed SDK resume changes its exact transport size")
    products._require_artifact_job_window(observed[0], job, artifact)
    locator = products._runtime_original_locator(artifact, spec["workflowSha"],
        PhaseInstanceId("sdk", "sdk-ios", "binary", "ios"), selected[0])
    return artifact, observed, locator


def _observe_completed_sdk_original(original, plan, producer, token):
    import product_reuse as products
    source = {"kind": "sdk-binary", "receipt": original["receipt"],
              "artifactId": original["artifactId"], "artifactSha256": original["artifactSha256"]}
    artifact, _, observed, workflow = products._authenticate_runtime_original_reference_source(
        plan, producer, source, trusted_workflow_sha=original["workflowSha"], token=token)
    instance = products._identity(original["receipt"])
    selected = products._matching_ci_jobs(observed[0]["jobs"],
        "product-validation / sdk-sdk-ios-binary-ios", expected_build_key=original["receipt"]["buildKey"])
    if len(selected) != 1:
        raise ValueError("Completed SDK original job is missing or ambiguous")
    return artifact, observed, products._runtime_original_locator(artifact, workflow, instance, selected[0])


def _observe_completed_sdk_inputs(spec, token):
    import product_reuse as products
    from runtime_reference_transport import validate_sdk_input_source
    value = spec["sdkInputs"]
    source = validate_sdk_input_source(value["source"])
    producer, job = source["producer"], "product-validation / sdk-inputs"
    observed = products._observe_ci_producer_jobs({"inputs": producer}, jobs_by_phase={"inputs": job},
        trusted_workflow_sha=source["workflowSha"], token=token)
    selected = products._matching_ci_jobs(observed[0]["jobs"], job)
    if len(selected) != 1 or selected[0]["id"] != value["jobId"]:
        raise ValueError("Completed SDK inputs differ from their approved staging job")
    artifact = products._contract_ci_upload_metadata(source["artifactId"], source["artifactSha256"],
        f"codex-agent-sdk-inputs-{producer['tree']}-attempt-{producer['runAttempt']}",
        producer, observed[0]["run"], token)
    if artifact["size_in_bytes"] != value["bytes"]:
        raise ValueError("Completed SDK input transport size changed")
    products._require_artifact_job_window(observed[0], job, artifact)
    # This locator identifies a transport job, never a new SDK product phase.
    locator = {"artifact": {field: artifact.get(field) for field in
        ("id", "name", "digest", "size_in_bytes", "created_at", "workflow_run")},
        "job": {field: selected[0].get(field) for field in
        ("id", "name", "run_id", "head_sha", "status", "conclusion", "started_at", "completed_at")}}
    return artifact, observed, locator


def _sdk_input_members(value):
    require_exact_keys(value, {"locator", "files"}, "Native SDK input member proof")
    rows = require_sorted_unique_records(value["files"], "Native SDK input members")
    controls = {"runtime-capture/plan/impact-plan.json", "runtime-capture/capture-transport.json"}
    if not 3 <= len(rows) <= 1024:
        raise ValueError("Native SDK input member count exceeds its bound")
    for row in rows:
        validate_file_record(row, "Native SDK input member", with_kind=False, allow_empty=True)
        if row["relativePath"] not in controls and not row["relativePath"].startswith("sdk-inputs/"):
            raise ValueError("Native SDK input proof includes unrelated Runtime history")
    if (not controls <= {row["relativePath"] for row in rows}
            or sum(row["bytes"] for row in rows) > 1024**3):
        raise ValueError("Native SDK input proof is missing controls or exceeds its byte bound")
    return rows


def _issue_sdk_input_members(spec, work, root, token):
    import product_reuse as products
    from sdk_handoff import _ensure_observed_sdk_commit
    source = spec["sdkInputs"]["source"]
    artifact, observed, locator = _observe_completed_sdk_inputs(spec, token)
    _ensure_observed_sdk_commit(root, source["producer"], token)
    with tempfile.TemporaryDirectory(prefix="completed-sdk-inputs-", dir=work) as temporary:
        archive = Path(temporary) / "original.zip"
        products._download_contract_ci_upload(source["artifactId"], source["artifactSha256"], artifact["name"],
            source["producer"], observed[0]["run"], token, destination=archive, max_bytes=spec["sdkInputs"]["bytes"])
        physical, _, plan_bytes = products._sdk_binding_source_inventory(archive,
            {"source": source, "runtimeSource": spec["sdkInputs"]["runtimeSource"]}, b"")
        plan_path = Path(temporary) / "original-plan.json"
        plan_path.write_bytes(plan_bytes)
        plan = products._validate_plan(plan_path, root, expected_revision=source["producer"]["commit"])
        if (plan["remoteBuildAuthorized"] is not True or plan["event"] == "workflow_dispatch"
                or products._consumer(plan, {}, original_run_id=source["producer"]["runId"],
                    original_run_attempt=source["producer"]["runAttempt"])["producer"] != source["producer"]):
            raise ValueError("Completed SDK input plan differs from its approved native producer")
        value = {"locator": locator, "files": [row for row in physical
            if row["relativePath"].startswith("sdk-inputs/") or row["relativePath"] in {
                "runtime-capture/plan/impact-plan.json", "runtime-capture/capture-transport.json"}]}
        _sdk_input_members(value)
        return value


def _completed_frozen_controls(spec, proof, qualification):
    """Check semantic proof contents; this pure check grants no authority."""
    phases = _phase_records(spec["expectedResult"]["phases"], "Frozen result")
    if (len(phases) != 50 or spec["expectedResult"]["fullReuse"] is not True
            or any(spec["expectedResult"]["matrices"].values())
            or proof.get("resultSha256") != sha256_bytes(canonical_json_bytes(spec["expectedResult"]))
            or proof.get("verificationPolicySha256") != qualification["verifierPolicySha256"]
            or type(proof.get("frozenPhases")) is not int or proof["frozenPhases"] != 50
            or type(proof.get("selectedProductPhases")) is not int or proof["selectedProductPhases"] != 0
            or type(proof.get("changedFrozenInventories")) is not int or proof["changedFrozenInventories"] != 0
            or proof.get("checkpoint") != spec["signedCheckpoint"]):
        raise ValueError("Native semantic proof differs from the fixed completed fifty-phase result")
    original_phases = _phase_records(proof.get("freshOriginalPhases"), "Semantic original phases")
    runtime = {instance: row for instance, row in phases.items() if instance.product == "runtime"}
    originals = _phase_records([row["receipt"] for row in qualification["originals"]], "Qualified receipts")
    if len(runtime) != 46 or set(original_phases) != set(runtime):
        raise ValueError("Native semantic proof lacks the exact forty-six original Runtime phases")
    for instance, row in phases.items():
        if row["state"] != "retained" or any(row.get(field) is None for field in _OBJECT_FIELDS):
            raise ValueError("Native semantic proof contains an incomplete phase")
        if instance in runtime and (instance not in originals
                or sha256_bytes(canonical_json_bytes(originals[instance])) != row["receiptSha256"]
                or original_phases[instance].get("receiptSha256") != row["receiptSha256"]):
            raise ValueError("Semantic proof differs from its independently authenticated original receipt")
    for row in qualification["originals"]:
        instance = next((key for key in runtime if all(row["receipt"][field] == value
                         for field, value in ((field, getattr(key, field)) for field in _PHASE_FIELDS))), None)
        if instance is not None and any(row[field] != runtime[instance][field]
                                       for field in ("receiptSha256", "objectSha256")):
            raise ValueError("Semantic proof differs from its authenticated original object")
    return phases


def _completed_contract_source(spec, receipts, originals):
    """Find native-qualified stage members for the exact four completed receipts."""
    expected = {row["phase"]: row for row in spec["expectedResult"]["phases"]
                if row["product"] == "contract"}
    selected = {row["phase"]: row for row in receipts if row["product"] == "contract"}
    if not selected:
        return None
    if set(selected) != set(expected) or set(expected) != {"binary", "package", "validation", "metadata"}:
        raise ValueError("Completed Contract requires exactly four original receipts")
    members = {}
    for phase, receipt in selected.items():
        validate_phase_receipt(receipt)
        raw = canonical_json_bytes(receipt)
        if (sha256_bytes(raw) != expected[phase]["receiptSha256"]
                or any(receipt[field] != expected[phase][field] for field in (*_PHASE_FIELDS, "buildKey"))):
            raise ValueError("Completed Contract receipt differs from its native semantic proof")
        prefix = f"inputs/predecessors/contract-contract-{phase}-common/"
        manifest = canonical_json_bytes({"schemaVersion": 1, **{field: receipt[field]
            for field in (*_PHASE_FIELDS, "productVersion", "outputs")}})
        members[phase] = [
            {"relativePath": prefix + "phase-receipt.json", "bytes": len(raw), "sha256": sha256_bytes(raw)},
            {"relativePath": prefix + "stage/output-manifest.json", "bytes": len(manifest),
             "sha256": sha256_bytes(manifest)},
            *({"relativePath": prefix + "stage/" + row["relativePath"],
               "bytes": row["bytes"], "sha256": row["sha256"]} for row in receipt["outputs"]),
        ]
    for original in originals:
        files = {row["relativePath"]: row for row in original["originalFiles"]}
        if all(files.get(row["relativePath"]) == row for rows in members.values() for row in rows):
            return {"locator": original["identity"]["locator"], "receipt": original["receipt"],
                    "members": members}
    return None  # Ordinary body verification remains required without complete native member coverage.


def _capture_completed_contract_receipts(spec, sdk, originals, destination, token):
    """Read only receipt controls, bound by both independent native proofs."""
    import hydrated_evidence
    from runtime_reference_archive import open_reference_archive, copy_reference_member
    phases = {row["phase"]: row for row in spec["expectedResult"]["phases"] if row["product"] == "contract"}
    if set(phases) != {"binary", "package", "validation", "metadata"}:
        raise ValueError("Completed Contract receipt capture requires all four native phases")
    qualified = {row["relativePath"]: row for row in _sdk_input_members(sdk["proof"]["sdkInputs"])}
    rows = []
    for phase, expected in sorted(phases.items()):
        path = f"sdk-inputs/inputs/contractAttestation/execution-closure/receipts/{phase}.json"
        row = qualified.get(path)
        if row is None or row["sha256"] != expected["receiptSha256"] or not 0 < row["bytes"] <= LIMIT:
            raise ValueError("Native SDK receipt member differs from completed Contract evidence")
        rows.append(row)
    if "extension" in sdk:
        files = sdk["extension"]["proof"]["contractFiles"]
        receipts = []
        for row in rows:
            name = row["relativePath"].removeprefix("sdk-inputs/inputs/contractAttestation/")
            raw = files["contract-input/" + name].encode("utf-8")
            if len(raw) != row["bytes"] or sha256_bytes(raw) != row["sha256"]:
                raise ValueError("Incremental Contract receipt changes its native-qualified original")
            receipts.append(validate_phase_receipt(load_canonical_json_bytes(raw)))
        if _completed_contract_source(spec, receipts, originals) is None:
            raise QualificationIncompatible("Completed Contract lacks native-qualified original stage coverage")
        return receipts
    artifact, _, locator = _observe_completed_sdk_inputs(sdk["spec"], token)
    if locator != sdk["proof"]["sdkInputs"]["locator"]:
        raise ValueError("Completed Contract receipt source changed after native qualification")
    destination = Path(destination)
    missing = [row for row in rows if not hydrated_evidence.copy(row, destination / row["relativePath"])]
    if missing:
        with open_reference_archive(artifact, token) as (archive, _stream):
            for row in missing:
                copy_reference_member(archive, row["relativePath"], destination / row["relativePath"], row)
    receipts = [validate_phase_receipt(load_canonical_json_bytes(read_regular_file_bytes(
        destination / row["relativePath"], max_bytes=LIMIT, reject_symlink_parents=True))) for row in rows]
    if _completed_contract_source(spec, receipts, originals) is None:
        raise QualificationIncompatible("Completed Contract lacks exact native-qualified original stage coverage")
    return receipts


class CompletedFrozenReuse:
    """Exact native semantic completion, separate from body qualification.

    This capability contains immutable controls, never stages or deserialized
    private product state. Bodies remain digest-checked when actually consumed.
    Only fetch_completed_frozen can create it after fresh native authentication.
    """
    __slots__ = ("_spec", "_receipts", "_verified", "_revision", "_originals", "_files", "_bodies", "_sdk", "_contract", "_body_cache", "_eligible", "_sdk_context")

    def __init__(self, spec, receipts, verified, *, revision, originals=(), sdk=None, body_cache=None):
        if verified is not _COMPLETED_FROZEN:
            raise TypeError("Completed reuse requires native semantic authentication")
        self._spec = canonical_json_bytes(spec)
        self._receipts = tuple((tuple(row[field] for field in _PHASE_FIELDS), canonical_json_bytes(row))
                               for row in receipts)
        self._verified = verified
        self._revision = revision
        self._eligible = None
        self._sdk = None if sdk is None else canonical_json_bytes(sdk)
        self._sdk_context = None
        extension = sdk.get("extension") if sdk is not None else None
        if extension is not None and extension["spec"].get("schemaVersion") == 4:
            from completed_sdk_reuse import source_predecessors
            context_spec = extension["spec"]
            context = source_predecessors(context_spec)
            self._sdk_context = (context_spec["source"]["inventoryCommit"],
                frozenset(_phase_records(context_spec["completedPhases"], "Context-qualified SDK phases")),
                canonical_json_bytes([context[key] for key in sorted(context)]))
        self._body_cache = None if body_cache is None else str(Path(body_cache))
        self._originals = frozenset((canonical_json_bytes(record["identity"]["locator"]),
            sha256_bytes(canonical_json_bytes(record["receipt"]))) for record in originals)
        self._files = tuple((canonical_json_bytes(record["identity"]["locator"]),
            canonical_json_bytes(record["originalFiles"])) for record in originals)
        from products.restore import object_relative_path
        bodies = []
        for record in originals:
            member = "shard/" + object_relative_path(record["receipt"]["buildKey"], record["receiptSha256"])
            rows = [row for row in record.get("originalFiles", []) if row["relativePath"] == member]
            if len(rows) != 1 or rows[0]["sha256"] != record["objectSha256"]:
                raise ValueError("Completed original lacks its exact native-qualified object member")
            bodies.append((record["receiptSha256"], canonical_json_bytes({
                "locator": record["identity"]["locator"], "member": rows[0]})))
        self._bodies = tuple(bodies)
        contract = _completed_contract_source(spec,
            [load_canonical_json_bytes(raw) for _, raw in self._receipts], originals)
        self._contract = None if contract is None else canonical_json_bytes(contract)

    def _values(self):
        if self._verified is not _COMPLETED_FROZEN:
            raise TypeError("Completed reuse has no semantic authority")
        spec = load_canonical_json_bytes(self._spec)
        phases = _phase_records(spec["expectedResult"]["phases"], "Frozen phases")
        return spec, {identity: row for identity, row in phases.items()
                      if self._eligible is None or identity in self._eligible}

    def completed_phases(self):
        return tuple(sorted(self._values()[1]))

    def check_request(self, request):
        """Require exact current candidates; additions never disappear into a hit."""
        spec, phases = self._values()
        if request.get("repositoryRevision") != self._revision:
            raise QualificationIncompatible("Completed reuse request differs from the checked Git revision")
        for field in ("repository", "pullRequest", "versions", "catalogs"):
            if request.get(field) != spec["request"][field]:
                raise QualificationIncompatible(f"Completed reuse requires unchanged {field}")
        if request.get("sdkRuntimeSource") is not None:
            raise QualificationIncompatible("Frozen reuse cannot elect an external SDK Runtime")
        from products.reuse import _dependency_closure
        requested = _phase_records(request["requested"], "Current requested phases")
        closure = set(_dependency_closure(tuple(requested)))
        phases = {instance: row for instance, row in phases.items() if instance in closure}
        current = _phase_records(request["availableObjects"], "Current available objects")
        authorities = _phase_records(request["phaseAuthorities"], "Current phase authorities")
        expected = _phase_records(spec["request"]["phaseAuthorities"], "Frozen phase authorities")
        for instance, row in phases.items():
            if (instance not in current or any(current[instance].get(field) != row[field]
                                               for field in _OBJECT_FIELDS)
                    or authorities.get(instance) != expected[instance]):
                raise QualificationIncompatible("Completed reuse requires exact frozen candidates and authorities")
        return tuple(sorted(phases))

    def check_consumer(self, consumer):
        self._values()
        producer = consumer.get("producer", {})
        if (consumer.get("kind") != "ci" or producer.get("repository") != REPOSITORY
                or producer.get("pullRequest") != 31 or producer.get("event") != "pull_request"):
            raise QualificationIncompatible("Completed frozen carrier requires its original PR scope")

    def deferred_objects(self, *, include_contract=False):
        """Body identities that routing may leave at their immutable original sources."""
        _, phases = self._values()
        return frozenset(row["objectSha256"] for instance, row in phases.items()
                         if instance.product in {"runtime", "sdk"}
                         or instance.product == "contract" and include_contract and self._contract is not None)

    def sdk_original(self):
        """Historical source controls; use envelope/eligible phases for admission.

        Requalification may invalidate SDK phases while these original controls
        still authenticate unchanged Contract inputs.
        """
        self._values()
        return None if self._sdk is None else load_canonical_json_bytes(self._sdk)

    def sdk_extension(self):
        sdk = self.sdk_original()
        return None if sdk is None else sdk.get("extension")

    def observe_extended_sdk(self, record, *, producer, token):
        from completed_sdk_reuse import observe_original, observe_source
        import product_reuse as products
        self.check_consumer({"kind": "ci", "producer": producer})
        envelope = self.envelope(record)
        extension = self.sdk_extension()
        if extension is None or envelope is None:
            raise ValueError("Incremental original lacks its concrete native completion")
        spec, proof = extension["spec"], extension["proof"]
        source = spec["source"]["producer"]
        if (source["runId"], source["runAttempt"]) >= (producer["runId"], producer["runAttempt"]):
            raise ValueError("Incremental completion must precede its consumer")
        artifact, _, locator = observe_source(spec["source"], token, native_locator=proof["source"])
        if locator != proof["source"]:
            raise ValueError("Incremental admitted source changed")
        instance = products._identity(record)
        originals = _phase_records(spec["originals"], "Incremental SDK originals")
        if instance not in originals:
            raise ValueError("Incremental original is outside its exact approved scope")
        native = [locator for locator in proof["originals"]
                  if locator["instance"] == {field: record[field] for field in _PHASE_FIELDS}]
        if len(native) != 1:
            raise ValueError("Incremental original native locator is missing or ambiguous")
        original, observed, locator = observe_original(originals[instance], envelope["receipt"], token,
            native_locator=native[0])
        if locator not in proof["originals"]:
            raise ValueError("Incremental original changed after native admission")
        return artifact, original, observed

    def contract_members(self):
        """Exact handoff members already consumed by the independent native SDK issuer."""
        sdk = self.sdk_original()
        if sdk is None or self._contract is None:
            return None
        result = {}
        for row in _sdk_input_members(sdk["proof"]["sdkInputs"]):
            for prefix in ("contractAttestation", "contractAttestationSignature", "contractPublicKey", "contractPayload"):
                source = f"sdk-inputs/inputs/{prefix}/"
                if row["relativePath"].startswith(source):
                    name = row["relativePath"].removeprefix(source)
                    if name in result:
                        raise ValueError("Completed Contract member is ambiguous")
                    result[name] = {**row, "relativePath": name}
        return result

    def verify_contract_handoff(self, handoff, *, keyring, keys_directory):
        """Reauthenticate small release controls; native proof binds the deferred bodies.

        The frozen native semantic proof checked Contract content. The separate
        native SDK member proof binds its original signed handoff controls.
        Neither an unqualified ZIP index nor body qualification alone grants
        semantic projection authority.
        """
        from products.contract_attestation import validate_contract_attestation
        from products.contract_model import validate_contract_manifest
        from products.inventory import regular_file_inventory
        from products.signatures import load_keyring, public_key_for_metadata, validate_signing_metadata, verify_manifest_signature
        rows = self.contract_members()
        if rows is None:
            raise ValueError("Contract controls lack independent native semantic authority")
        handoff = Path(handoff)
        controls = {name: row for name, row in rows.items() if not name.endswith(".zip")}
        expected = set(controls) | {"contract-manifest.json"}
        before = regular_file_inventory(handoff)
        if {row["relativePath"] for row in before} != expected:
            raise ValueError("Completed Contract control handoff inventory is not exact")
        for name, row in controls.items():
            raw = read_regular_file_bytes(handoff / name, max_bytes=LIMIT, reject_symlink_parents=True)
            if len(raw) != row["bytes"] or sha256_bytes(raw) != row["sha256"]:
                raise ValueError("Completed Contract control differs from its native-qualified original")
        names = [name for name in controls if name.endswith(".attestation.json")]
        if len(names) != 1:
            raise ValueError("Completed Contract requires one original attestation")
        attestation = handoff / names[0]
        value = validate_contract_attestation(load_canonical_json_bytes(read_regular_file_bytes(attestation)))
        raw = read_regular_file_bytes(handoff / "contract-manifest.json", max_bytes=LIMIT, reject_symlink_parents=True)
        if sha256_bytes(raw) != value["manifestSha256"]:
            raise ValueError("Completed Contract manifest differs from its authenticated original")
        manifest = validate_contract_manifest(load_canonical_json_bytes(raw))
        payload = rows.get(value["payload"]["fileName"])
        if (payload is None or any(payload[field] != value["payload"][field] for field in ("bytes", "sha256"))
                or manifest["contractVersion"] != value["contractVersion"]
                or controls["execution-closure/contract-execution-closure.json"]["sha256"] != value["executionClosureSha256"]):
            raise ValueError("Completed Contract release differs from its native payload and closure")
        # A signature and a qualified SDK upload alone do not prove Contract
        # semantics. Bind the manifest to projections actually admitted by the
        # original frozen native planner for this exact immutable bundle.
        projections = [upstream["contractProjection"]
            for fields, receipt_raw in self._receipts if fields[0] == "runtime"
            for upstream in load_canonical_json_bytes(receipt_raw)["inputs"]["upstreamArtifacts"]
            if "contractProjection" in upstream and
               upstream["contractProjection"]["bundleSha256"] == payload["sha256"]]
        if not projections or any(projection["manifestSha256"] != sha256_bytes(raw)
                or projection["contractVersion"] != manifest["contractVersion"]
                or projection["contractDigest"] != manifest["contractDigest"]
                or any(manifest["components"][row["component"]]["sha256"] != row["sha256"]
                       for row in projection["componentDigests"]) for projection in projections):
            raise ValueError("Completed Contract manifest lacks the exact native semantic projection")
        _, phases = self._values()
        from products.registry import PhaseInstanceId
        for phase in ("binary", "package", "validation", "metadata"):
            record = phases[PhaseInstanceId("contract", "contract", phase, "common")]
            self.envelope(record, read_regular_file_bytes(handoff / f"execution-closure/receipts/{phase}.json"))
        if value["metadataReceiptSha256"] != controls["execution-closure/receipts/metadata.json"]["sha256"]:
            raise ValueError("Completed Contract release receipt differs from native completion")
        signing = validate_signing_metadata(value["signing"], trust_domain="release")
        trusted = public_key_for_metadata(signing, load_keyring(keyring, keys_directory), keys_directory, allow_retired=True)
        if read_regular_file_bytes(trusted, reject_symlink_parents=True) != read_regular_file_bytes(handoff / "public-key.pub"):
            raise ValueError("Completed Contract release public key differs from current trust")
        verify_manifest_signature(attestation, handoff / names[0].replace(".json", ".sig"),
                                  handoff / "public-key.pub", signing)
        if regular_file_inventory(handoff) != before:
            raise ValueError("Completed Contract controls changed during verification")
        return manifest

    def contract_projection(self, evidence, *, version, components, receipt_bytes):
        """Reuse only the exact native-verified payload's authenticated manifest projection."""
        from products.contract_projection import VerifiedContractProjection, _VERIFIED
        if evidence["expectedTrustDomain"] != "release":
            raise ValueError("Completed Contract projection requires release trust")
        manifest = self.verify_contract_handoff(Path(evidence["attestation"]).parent,
            keyring=evidence["keyring"], keys_directory=evidence["keysDirectory"])
        from products.registry import PhaseInstanceId
        _, phases = self._values()
        envelope = self.envelope(phases[PhaseInstanceId("contract", "contract", "metadata", "common")], receipt_bytes)
        outputs = envelope["receipt"]["outputs"]
        if manifest["contractVersion"] != version or len(outputs) != 1:
            raise ValueError("Completed Contract projection version or payload changed")
        value = {"schemaVersion": 1, "receiptSha256": envelope["receiptSha256"],
            "bundlePath": outputs[0]["relativePath"], "bundleSha256": outputs[0]["sha256"],
            "manifestSha256": sha256_bytes(canonical_json_bytes(manifest)),
            "contractVersion": version, "contractDigest": manifest["contractDigest"],
            "componentDigests": [{"component": name, "sha256": row["sha256"]}
                                 for name, row in sorted(manifest["components"].items())]}
        return VerifiedContractProjection(value, _VERIFIED, manifest["canonicalCoverageDigest"]).restrict(components)

    def observe_sdk(self, *, plan, producer, token):
        """Recheck both the admission source and original producer without their bodies."""
        self.check_consumer({"kind": "ci", "producer": producer})
        sdk = self.sdk_original()
        if sdk is None:
            raise ValueError("Completed SDK reuse lacks its distinct native proof")
        source = sdk["spec"]["producer"]
        if (source["runId"], source["runAttempt"]) >= (producer["runId"], producer["runAttempt"]):
            raise ValueError("Completed SDK admission must precede its consumer")
        artifact, _, locator = _observe_completed_sdk_resume(sdk["spec"], token)
        original_artifact, observed, original_locator = _observe_completed_sdk_original(
            sdk["original"], plan, producer, token)
        if locator != sdk["proof"]["source"] or original_locator != sdk["proof"]["original"]:
            raise ValueError("Completed SDK fresh native identity changed")
        return artifact, original_artifact, observed

    def sdk_input_members(self, binding):
        """Only the independently selected input source may use the native member claim."""
        sdk = self.sdk_original()
        if sdk is None:
            return None
        expected = sdk["spec"]["sdkInputs"]
        if binding["source"] != expected["source"] or binding["runtimeSource"] != expected["runtimeSource"]:
            raise QualificationIncompatible("SDK binding differs from its approved native member source")
        return _sdk_input_members(sdk["proof"]["sdkInputs"])

    def capture_sdk_input_members(self, binding, destination, token):
        from runtime_reference_archive import open_reference_archive, copy_reference_member
        import hydrated_evidence
        rows = self.sdk_input_members(binding)
        if rows is None:
            raise ValueError("SDK member capture lacks native transport qualification")
        sdk = self.sdk_original()
        artifact, observed, locator = _observe_completed_sdk_inputs(sdk["spec"], token)
        if locator != sdk["proof"]["sdkInputs"]["locator"]:
            raise ValueError("SDK input source changed after native qualification")
        missing = [row for row in rows if not hydrated_evidence.copy(row, Path(destination) / row["relativePath"])]
        if missing:
            with open_reference_archive(artifact, token) as (archive, _stream):
                for row in missing:
                    copy_reference_member(archive, row["relativePath"], Path(destination) / row["relativePath"], row)
        if self._body_cache is not None:
            from runtime_reference_transport import _copy_exact
            for row in rows:
                if (row["relativePath"].startswith("sdk-inputs/inputs/contractPayload/")
                        or row["relativePath"].endswith("/execution/contract-execution.zip")):
                    cached = Path(self._body_cache) / row["sha256"][7:]
                    if not cached.exists():
                        _copy_exact(Path(destination) / row["relativePath"], cached, row)
        return rows, artifact, observed

    def require_original_locator(self, locator, receipt):
        """Match fresh native observations to the original that the semantic issuer checked."""
        self._values()
        if (canonical_json_bytes(locator), sha256_bytes(canonical_json_bytes(receipt))) not in self._originals:
            raise ValueError("Fresh original locator differs from completed native evidence")

    def original_files(self, locator, receipt):
        """Copied native-qualified member identities, after fresh original observation."""
        from products.registry import PhaseInstanceId
        self.require_original_locator(locator, receipt)
        instance = PhaseInstanceId(*(receipt[field] for field in _PHASE_FIELDS))
        if instance not in self._values()[1]:
            raise ValueError("Original members are outside current native completion")
        key = canonical_json_bytes(locator)
        matches = [raw for original, raw in self._files if original == key]
        if len(matches) != 1:
            raise ValueError("Native original member inventory is missing or ambiguous")
        return load_canonical_json_bytes(matches[0])

    @measured
    def capture_object(self, record, destination, *, plan, producer, trusted_workflow_sha, token):
        """Fetch one consumed object; never hydrate unrelated original-upload members."""
        import product_reuse as products
        from runtime_reference_archive import open_reference_archive, copy_reference_member
        self.check_consumer({"kind": "ci", "producer": producer})
        envelope = self.envelope(record)
        if envelope is None or record.get("product") not in {"contract", "runtime", "sdk"}:
            raise ValueError("Deferred object is outside completed native authority")
        if record["product"] == "contract":
            self._capture_contract_object(record, envelope, destination, plan=plan, producer=producer,
                trusted_workflow_sha=trusted_workflow_sha, token=token)
            return
        if record["product"] == "sdk":
            from completed_sdk_reuse import IOS_PACKAGE, original_worker_member
            limits = {}
            extension = self.sdk_extension()
            if extension is not None and products._identity(record) in _phase_records(
                    extension["spec"]["completedPhases"], "Incremental SDK phases"):
                artifact, original, _ = self.observe_extended_sdk(record, producer=producer, token=token)
                if original_worker_member(extension["spec"]):
                    artifact = original
                    limits = products._worker_upload_reference_limits(products._identity(record))
                members = [row for row in extension["proof"]["members"] if row["sha256"] == record["objectSha256"]]
                if len(members) != 1:
                    raise ValueError("Incremental SDK object member is missing or ambiguous")
                member = members[0]
            else:
                artifact, _, _ = self.observe_sdk(plan=plan, producer=producer, token=token)
                member = self.sdk_original()["proof"]["member"]
            import hydrated_evidence
            with tempfile.TemporaryDirectory(prefix="completed-sdk-body-cache-") as temporary:
                cache_controls = Path(temporary).resolve()
                hydrated_evidence.hosted_records("restore", [member], cache_controls)
                if hydrated_evidence.copy(member, destination):
                    count("sdkObjectCacheHitBytes", member["bytes"])
                else:
                    with open_reference_archive(artifact, token, **limits) as (archive, stream):
                        copy_reference_member(archive, member["relativePath"], destination, member)
                        if stream is not None:
                            count("sdkObjectOriginalRangeBytes", stream.transferred)
                    hydrated_evidence.retain(member, destination)
                    hydrated_evidence.hosted_records("save", [member], cache_controls,
                        already_compressed=products._identity(record) == IOS_PACKAGE)
            return
        body = load_canonical_json_bytes(next(raw for receipt, raw in self._bodies
                                              if receipt == record["receiptSha256"]))
        source = {"kind": "phase", "receipt": envelope["receipt"],
                  "artifactId": body["locator"]["artifact"]["id"],
                  "artifactSha256": body["locator"]["artifact"]["digest"]}
        artifact, _, observed, workflow = products._authenticate_runtime_original_reference_source(
            plan, producer, source, trusted_workflow_sha=trusted_workflow_sha, token=token)
        instance = products._identity(envelope["receipt"])
        name = f"product-validation / runtime-{instance.component}-{instance.phase}-{instance.target}"
        matches = products._matching_ci_jobs(observed[0]["jobs"], name)
        if len(matches) != 1:
            raise ValueError("Deferred original job is missing or ambiguous")
        self.require_original_locator(products._runtime_original_locator(
            artifact, workflow, instance, matches[0]), envelope["receipt"])
        import hydrated_evidence
        if not hydrated_evidence.copy(body["member"], destination):
            with open_reference_archive(artifact, token) as (archive, _stream):
                copy_reference_member(archive, body["member"]["relativePath"], destination, body["member"])
            hydrated_evidence.retain(body["member"], destination)
        # The caller still performs ordinary object/receipt/manifest verification
        # and extraction before exposing any bytes to a product worker.

    def _capture_contract_object(self, record, envelope, destination, *, plan, producer,
                                 trusted_workflow_sha, token):
        import product_reuse as products
        import hydrated_evidence
        from products.restore import _write_object, verify_object
        from runtime_reference_archive import open_reference_archive, copy_reference_member
        from runtime_reference_transport import _copy_exact
        if self._contract is None:
            raise ValueError("Deferred Contract lacks native-qualified original stage members")
        original = load_canonical_json_bytes(self._contract)
        source = {"kind": "phase", "receipt": original["receipt"],
                  "artifactId": original["locator"]["artifact"]["id"],
                  "artifactSha256": original["locator"]["artifact"]["digest"]}
        artifact, _, observed, workflow = products._authenticate_runtime_original_reference_source(
            plan, producer, source, trusted_workflow_sha=trusted_workflow_sha, token=token)
        instance = products._identity(original["receipt"])
        name = f"product-validation / runtime-{instance.component}-{instance.phase}-{instance.target}"
        jobs = products._matching_ci_jobs(observed[0]["jobs"], name)
        if len(jobs) != 1:
            raise ValueError("Deferred Contract original job is missing or ambiguous")
        self.require_original_locator(products._runtime_original_locator(
            artifact, workflow, instance, jobs[0]), original["receipt"])
        with tempfile.TemporaryDirectory(prefix="completed-contract-object-") as temporary:
            root = Path(temporary).resolve()
            rows = original["members"][record["phase"]]
            prefix = root / f"inputs/predecessors/contract-contract-{record['phase']}-common"
            sdk = self.sdk_original()
            if sdk is not None:
                # The same qualified payload supplies hundreds of stage members.
                # Fetch two bundle members once, not one range request per file.
                import zipfile
                sdk_artifact, _, locator = _observe_completed_sdk_inputs(sdk["spec"], token)
                if locator != sdk["proof"]["sdkInputs"]["locator"]:
                    raise ValueError("Deferred Contract SDK source changed after qualification")
                members = [row for row in _sdk_input_members(sdk["proof"]["sdkInputs"])
                    if row["relativePath"].startswith("sdk-inputs/inputs/contractPayload/")
                    or record["phase"] == "binary" and row["relativePath"].endswith("/execution/contract-execution.zip")]
                payloads = [row for row in members if "/contractPayload/" in row["relativePath"]]
                if len(payloads) != 1:
                    raise ValueError("Deferred Contract requires one native-qualified payload")
                missing_members = []
                for row in members:
                    target = root / row["relativePath"]
                    cached = None if self._body_cache is None else Path(self._body_cache) / row["sha256"][7:]
                    if cached is not None and (cached.exists() or cached.is_symlink()):
                        _copy_exact(cached, target, row)
                    elif not hydrated_evidence.copy(row, target):
                        missing_members.append(row)
                if missing_members:
                    with open_reference_archive(sdk_artifact, token) as (archive, _stream):
                        for row in missing_members:
                            copy_reference_member(archive, row["relativePath"], root / row["relativePath"], row)
                for row in members:
                    if self._body_cache is not None:
                        cached = Path(self._body_cache) / row["sha256"][7:]
                        if not cached.exists():
                            _copy_exact(root / row["relativePath"], cached, row)
                prefix.mkdir(parents=True)
                (prefix / "stage").mkdir()
                (prefix / "phase-receipt.json").write_bytes(envelope["receiptBytes"])
                (prefix / "stage/output-manifest.json").write_bytes(canonical_json_bytes({"schemaVersion": 1,
                    **{field: envelope["receipt"][field] for field in (*_PHASE_FIELDS, "productVersion", "outputs")}}))
                with zipfile.ZipFile(root / payloads[0]["relativePath"]) as archive:
                    for output in envelope["receipt"]["outputs"]:
                        target = prefix / "stage" / output["relativePath"]
                        if record["phase"] == "metadata":
                            _copy_exact(root / payloads[0]["relativePath"], target, output)
                        elif output["relativePath"] == "outputs/execution/contract-execution.zip":
                            execution = [row for row in members if row["relativePath"].endswith("/execution/contract-execution.zip")]
                            if len(execution) != 1:
                                raise ValueError("Deferred Contract execution archive is missing")
                            _copy_exact(root / execution[0]["relativePath"], target, output)
                        elif output["relativePath"].removeprefix("outputs/") in archive.namelist():
                            copy_reference_member(archive, output["relativePath"].removeprefix("outputs/"), target, output)
            missing = [row for row in rows if not (root / row["relativePath"]).exists()
                       and not hydrated_evidence.copy(row, root / row["relativePath"])]
            if missing:
                with open_reference_archive(artifact, token) as (archive, _stream):
                    for row in missing:
                        copy_reference_member(archive, row["relativePath"], root / row["relativePath"], row)
            if read_regular_file_bytes(prefix / "phase-receipt.json") != envelope["receiptBytes"]:
                raise ValueError("Deferred Contract original receipt changed during capture")
            body = root / "object.zip"
            _write_object(prefix / "stage", envelope["receiptBytes"], body)
            # Reconstruction must reproduce the original archive byte for byte.
            # It never issues a new receipt or substitutes a merely equivalent object.
            verified = verify_object(body, build_key=record["buildKey"],
                receipt_sha256=record["receiptSha256"], object_sha256=record["objectSha256"])
            _copy_exact(body, Path(destination),
                {"bytes": verified["objectBytes"], "sha256": record["objectSha256"]})

    def runtime_sources(self):
        """Return copied original locators; each still needs fresh native observation."""
        _, phases = self._values()
        result = []
        for instance, phase in phases.items():
            if instance.product != "runtime":
                continue
            envelope = self.envelope(phase)
            body = load_canonical_json_bytes(next(raw for receipt, raw in self._bodies
                                                  if receipt == phase["receiptSha256"]))
            result.append({"kind": "phase", "receipt": envelope["receipt"],
                "artifactId": body["locator"]["artifact"]["id"],
                "artifactSha256": body["locator"]["artifact"]["digest"],
                "objectSha256": envelope["objectSha256"]})
        return result

    def sdk_receipts(self, arguments):
        """Join fully signature-verified SDK inputs to this exact completed Runtime."""
        from products.registry import PhaseInstanceId
        spec, phases = self._values()
        result = {PhaseInstanceId(*fields): raw for fields, raw in self._receipts if fields[0] == "runtime"}
        for product, component, target in (("contract", "contract", "common"),
                                           ("runtime", "runtime-aggregate", "aggregate")):
            identity = PhaseInstanceId(product, component, "metadata", target)
            raw = read_regular_file_bytes(arguments[f"{product}_metadata_receipt"],
                max_bytes=LIMIT, reject_symlink_parents=True)
            self.envelope(phases[identity], raw)
            result[identity] = raw
        checkpoint = {Path(row["relativePath"]).name: row for row in spec["signedCheckpoint"]}
        for argument in ("runtime_manifest", "runtime_attestation", "runtime_attestation_signature"):
            path = Path(arguments[argument])
            row = checkpoint.get(path.name)
            raw = read_regular_file_bytes(path, max_bytes=LIMIT, reject_symlink_parents=True)
            if row is None or len(raw) != row["bytes"] or sha256_bytes(raw) != row["sha256"]:
                raise ValueError("SDK signed Runtime differs from the completed semantic checkpoint")
        return result

    def envelope(self, record, receipt_bytes=None):
        """Authenticate small receipt controls by the completed proof's exact digest."""
        from products.registry import PhaseInstanceId
        spec, phases = self._values()
        instance = PhaseInstanceId(*(record.get(field) for field in _PHASE_FIELDS))
        if instance not in phases:
            return None  # Later SDK originals require their ordinary full gates.
        expected = phases[instance]
        if any(record.get(field) != expected[field] for field in _OBJECT_FIELDS):
            raise ValueError("Completed original differs from its exact proved identity")
        if receipt_bytes is None:
            identity = tuple(record[field] for field in _PHASE_FIELDS)
            receipt_bytes = next((raw for fields, raw in self._receipts if fields == identity), None)
            if receipt_bytes is None:
                return None  # Contract receipts must be supplied from retained controls.
        if type(receipt_bytes) is not bytes or sha256_bytes(receipt_bytes) != expected["receiptSha256"]:
            raise ValueError("Completed original receipt bytes differ from their proved digest")
        receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
        if any(receipt[field] != expected[field] for field in (*_PHASE_FIELDS, "buildKey")):
            raise ValueError("Completed original receipt changes phase identity")
        return {"receipt": receipt, "receiptBytes": receipt_bytes,
                "receiptSha256": expected["receiptSha256"], "objectSha256": expected["objectSha256"]}

    def phase_plan(self, instance, values, envelope, upstream):
        """Reuse the proved key only for identical current direct and upstream inputs."""
        from products.restore import PHASE_PLAN_KEYS
        from products.registry import PhaseInstanceId
        from products.plan import _phase_version_identity
        instance = PhaseInstanceId(*(getattr(instance, field) for field in _PHASE_FIELDS))
        spec, phases = self._values()
        if instance not in phases:
            return None
        selected = self.envelope({**{field: getattr(instance, field) for field in _PHASE_FIELDS}, **{
            field: envelope[field] if field != "buildKey" else envelope["receipt"][field]
            for field in _OBJECT_FIELDS}}, envelope["receiptBytes"])
        receipt = selected["receipt"]
        authority = _phase_records(spec["request"]["phaseAuthorities"], "Frozen authorities")[instance]
        if (set(values) != {"inventory", "versions", "toolchain_profile_digest", "flags_digest", "output_schema_version"}
                or values.get("versions") != spec["request"]["versions"]
                or values.get("inventory") != receipt["inputs"]["inventory"]
                or receipt["inputs"]["versionIdentity"] != _phase_version_identity(instance, values["versions"])
                or any(values.get(argument) != authority[field] for argument, field in (
                    ("flags_digest", "flagsDigest"), ("toolchain_profile_digest", "toolchainProfileDigest"),
                    ("output_schema_version", "outputSchemaVersion")))):
            raise QualificationIncompatible("Completed phase has changed current inputs")
        from products.registry import phase_instance_dependencies
        actual = _phase_records([value["receipt"] for value in upstream], "Current upstream receipts")
        if self._sdk_context is not None and instance in self._sdk_context[1]:
            # Observation-only predecessors never become native claims. The
            # planner must resolve their ordinary authentication gates first.
            context = _phase_records(load_canonical_json_bytes(self._sdk_context[2]), "SDK source predecessors")
            dependencies = {**phases, **context}
            if set(actual) != set(phase_instance_dependencies(instance)):
                raise QualificationIncompatible("Completed SDK has changed source dependencies")
            for value in upstream:
                identity = PhaseInstanceId(*(value["receipt"][field] for field in _PHASE_FIELDS))
                expected = dependencies.get(identity)
                if (expected is None or value["receipt"]["buildKey"] != expected["buildKey"]
                        or sha256_bytes(canonical_json_bytes(value["receipt"])) != expected["receiptSha256"]
                        or value.get("receiptSha256") != expected["receiptSha256"]
                        or value.get("objectSha256") != expected["objectSha256"]):
                    raise QualificationIncompatible("Completed SDK has changed source dependencies")
            return {field: receipt[field] for field in PHASE_PLAN_KEYS}
        if set(actual) != set(phase_instance_dependencies(instance)) or any(
                dependency not in phases or sha256_bytes(canonical_json_bytes(original)) !=
                phases[dependency]["receiptSha256"] for dependency, original in actual.items()):
            raise QualificationIncompatible("Completed phase has changed original dependencies")
        return {field: receipt[field] for field in PHASE_PLAN_KEYS}


@measured
def fetch_completed_frozen(destination, *, consumer_commit, verifier_policy_sha256,
                           repository_root, revision, sdk_completion=None,
                           requalification_baseline=None, **original):
    """Use an independently approved frozen semantic issuer for an approved consumer.

    All pins are caller policy. In particular the old verifier policy cannot be
    read from an untrusted envelope, and the current consumer is independently
    pinned rather than silently declared compatible with an earlier verifier.
    The six-file native artifact includes proof.json from the actual full planner;
    qualification.json alone is deliberately insufficient.
    """
    import product_reuse as products
    from products.inventory import git_regular_blob_bytes, tree_entries
    from products.selection import phase_inventory_paths

    _commit(consumer_commit)
    _commit(revision)
    require_sha256(verifier_policy_sha256, "Approved frozen semantic verifier policy")
    if not _compatible_verifier(consumer_commit):
        raise QualificationIncompatible("Completed reuse consumer differs from its independent approval")
    root = Path(repository_root).resolve(strict=True)
    current_revision = revision
    if requalification_baseline is not None:
        revision = _commit(requalification_baseline)
    # Signers keep candidate Git separate from the bootstrapped trusted checkout.
    _ensure_native_issuer_commit(root, original["signer_commit"], original.get("token"))
    spec = load_canonical_json_bytes(git_regular_blob_bytes(root, original["signer_commit"],
        _frozen_spec_path(root, original["signer_commit"]), max_bytes=LIMIT))
    for historical in sorted({spec["inventoryBaseline"], revision}):
        _ensure_native_issuer_commit(root, historical, original.get("token"))

    def authenticate_frozen():
        report, captured = _fetch_qualification_archive(destination, **original)
        qualified = _authenticate_bytes(captured["qualification.json"], captured["bundle.jsonl"],
            signer_commit=original["signer_commit"], source_commit=original["source_commit"],
            policy_sha256=verifier_policy_sha256)  # Exact approved old policy, no compatibility fallback.
        proof = load_canonical_json_bytes(captured["proof.json"])
        phases = _completed_frozen_controls(spec, proof, qualified)
        baseline, current = (dict(tree_entries(root, commit)) for commit in (spec["inventoryBaseline"], revision))
        changed = _changed_inventory_paths(baseline, current)
        for instance in phases:
            if phase_inventory_paths(changed, instance):
                raise QualificationIncompatible(f"Completed phase owning inputs changed: {instance}")
        # Revoked/rotated public trust must not inherit an older completion decision.
        authority = dict(tree_entries(root, original["signer_commit"]))
        def public_policy(entries):
            return {path: value for path, value in entries.items() if path ==
                    "gradle/release/product-signing-keys.json" or path.startswith("gradle/release/keys/")}
        if public_policy(authority) != public_policy(current):
            raise QualificationIncompatible("Completed reuse public trust changed")
        authorities, unavailable = products._authorities(root, revision, tuple(sorted(phases)))
        if (unavailable or authorities != spec["request"]["phaseAuthorities"]
                or products._versions(root, revision) != spec["request"]["versions"]):
            raise QualificationIncompatible("Completed reuse current Git authority or versions changed")
        return report, qualified, phases, proof

    sdk = None
    if sdk_completion is None:
        report, qualified, phases, proof = authenticate_frozen()
    else:
        from products.restore import bounded_verify
        frozen_result, sdk = bounded_verify(lambda verify: verify(), (
            authenticate_frozen,
            lambda: _fetch_completed_sdk(Path(destination).parent / "sdk-native", sdk_completion,
                root=root, revision=revision, frozen=spec, token=original["token"],
                consumer_revision=current_revision)))
        report, qualified, phases, proof = frozen_result

    receipts = [row["receipt"] for row in qualified["originals"] if row["receipt"]["product"] == "runtime"]
    if sdk is None and "contractReceipts" in proof:
        contract = require_array(proof["contractReceipts"], "Requalified Contract receipts")
        if (len(contract) != 4 or any(not isinstance(row, dict) or row.get("product") != "contract" for row in contract)
                or _completed_contract_source(spec, contract, qualified["originals"]) is None):
            raise ValueError("Requalified Contract controls lack complete native original coverage")
        receipts.extend(contract)
    if sdk is not None:
        receipts.extend(_capture_completed_contract_receipts(spec, sdk, qualified["originals"],
            Path(destination).parent / "contract-controls", original["token"]))
        request, phase, receipt, _ = _completed_sdk_controls(
            sdk["spec"], sdk["proof"]["controls"], spec, sdk["original"])
        instance = products._identity(receipt)
        for field in ("availableObjects", "phaseAuthorities"):
            spec["request"][field] = sorted([*spec["request"][field],
                _phase_records(request[field], field)[instance]], key=products._identity)
        spec["expectedResult"]["phases"] = sorted([*spec["expectedResult"]["phases"], phase], key=products._identity)
        receipts.append(receipt)
        if "extension" in sdk:
            from completed_sdk_reuse import validate_controls
            extension = sdk["extension"]
            request, additions, added_receipts = validate_controls(extension["spec"], extension["proof"]["controls"], spec)
            identities = {products._identity(row) for row in additions}
            for field in ("availableObjects", "phaseAuthorities"):
                spec["request"][field] = sorted([*spec["request"][field],
                    *(row for row in request[field] if products._identity(row) in identities)], key=products._identity)
            spec["expectedResult"]["phases"] = sorted([*spec["expectedResult"]["phases"], *additions], key=products._identity)
            receipts.extend(added_receipts)
    count = int(sdk is not None) + (len(sdk["extension"]["spec"]["completedPhases"]) if sdk and "extension" in sdk else 0)
    report.update(completedFrozenPhases=len(phases), completedSdkPhases=count, productBodiesDownloaded=0)
    cap = CompletedFrozenReuse(spec, receipts, _COMPLETED_FROZEN, revision=revision,
        originals=qualified["originals"], sdk=sdk, body_cache=Path(destination).parent / "contract-bodies")
    if requalification_baseline is not None:
        invalidated = _restrict_completed_reuse(cap, root, current_revision)
        report.update(requalificationBaseline=revision,
            invalidatedPhases=[products._identity_record(instance) for instance in invalidated],
            completedFrozenPhases=sum(instance.product != "sdk" for instance in cap.completed_phases()),
            completedSdkPhases=sum(instance.product == "sdk" for instance in cap.completed_phases()))
    return cap, report


def _restrict_completed_reuse(cap, root, revision):
    """Remove changed phases and descendants from an already authenticated capability."""
    import product_reuse as products
    from products.inventory import tree_entries
    from products.registry import phase_instance_dependencies
    from products.selection import phase_inventory_paths
    _commit(revision)
    spec, phases = cap._values()
    before, after = (dict(tree_entries(root, commit)) for commit in (cap._revision, revision))
    changed = _changed_inventory_paths(before, after)
    if any(path == "gradle/release/product-signing-keys.json" or path.startswith("gradle/release/keys/")
           for path in changed):
        raise QualificationIncompatible("Requalification changes public trust")
    authorities, unavailable = products._authorities(root, revision, tuple(sorted(phases)))
    expected = _phase_records(spec["request"]["phaseAuthorities"], "Native predecessor authorities")
    if (unavailable or authorities != [expected[instance] for instance in sorted(phases)]
            or products._versions(root, revision) != spec["request"]["versions"]):
        raise QualificationIncompatible("Requalification changes current authorities or versions")
    eligible = {instance for instance in phases if not phase_inventory_paths(changed, instance)}
    contextual, context_dependencies = frozenset(), frozenset()
    if cap._sdk_context is not None:
        baseline, contextual, raw_context = cap._sdk_context
        source = dict(tree_entries(root, baseline))
        sdk_changed = _changed_inventory_paths(source, after)
        eligible.difference_update(contextual)
        eligible.update(instance for instance in contextual if instance in phases
                        and not phase_inventory_paths(sdk_changed, instance))
        context_dependencies = frozenset(_phase_records(load_canonical_json_bytes(raw_context),
                                                       "SDK source predecessors"))
    while True:
        retained = {instance for instance in eligible if set(phase_instance_dependencies(instance)) <=
                    (eligible | context_dependencies if instance in contextual else eligible)}
        if retained == eligible:
            break
        eligible = retained
    if any(instance.product == "contract" and instance not in eligible for instance in phases):
        raise QualificationIncompatible("Requalification requires unchanged complete Contract evidence")
    cap._eligible = frozenset(eligible)
    cap._revision = revision
    return tuple(sorted(set(phases) - eligible))


def _native_pin_arguments(value):
    require_exact_keys(value, {"artifactId", "artifactSha256", "runId", "runAttempt",
                              "signerCommit", "sourceCommit"}, "Completed SDK native pins")
    return {argument: value[field] for argument, field in (
        ("artifact_id", "artifactId"), ("artifact_sha256", "artifactSha256"), ("run_id", "runId"),
        ("run_attempt", "runAttempt"), ("signer_commit", "signerCommit"), ("source_commit", "sourceCommit"))}


def _fetch_completed_sdk(destination, pins, *, root, revision, frozen, token, consumer_revision=None):
    import product_reuse as products
    from products.inventory import git_regular_blob_bytes, tree_entries
    from products.selection import phase_inventory_paths
    arguments = _native_pin_arguments(pins)
    _, captured = _fetch_qualification_archive(destination, **arguments, token=token, _completed_sdk=True)
    _authenticate_native_subject(captured["completion.json"], captured["bundle.jsonl"], "completion.json",
        signer_commit=arguments["signer_commit"], source_commit=arguments["source_commit"])
    proof = load_canonical_json_bytes(captured["completion.json"])
    return _validate_completed_sdk(proof, arguments, root=root, revision=revision, frozen=frozen, token=token,
        **({"consumer_revision": consumer_revision} if consumer_revision is not None else {}))


def _validate_completed_sdk(proof, arguments, *, root, revision, frozen, token, consumer_revision=None):
    """Validate only after native subject admission (or an admitted native parent)."""
    import product_reuse as products
    from products.inventory import git_regular_blob_bytes, tree_entries
    from products.selection import phase_inventory_paths
    _ensure_native_issuer_commit(root, arguments["signer_commit"], token)
    raw = git_regular_blob_bytes(root, arguments["signer_commit"],
        _sdk_completed_spec_path(root, arguments["signer_commit"]), max_bytes=LIMIT)
    spec = load_canonical_json_bytes(raw)
    if spec.get("schemaVersion") in (2, 3, 4):
        from completed_sdk_reuse import validate_extension
        return validate_extension(spec, proof, arguments, root=root, revision=revision, frozen=frozen, token=token,
            **({"consumer_revision": consumer_revision} if spec["schemaVersion"] == 4 else {}))
    proof = require_exact_keys(proof, {
        "schemaVersion", "kind", "issuerCommit", "specSha256", "source", "original", "controls", "member", "sdkInputs"},
        "Native completed SDK proof")
    original = load_canonical_json_bytes(git_regular_blob_bytes(root, arguments["signer_commit"],
        _sdk_original_spec_path(root, arguments["signer_commit"]), max_bytes=LIMIT))
    if (type(proof["schemaVersion"]) is not int or proof["schemaVersion"] != 1
            or proof["kind"] != "completed-sdk-reuse" or proof["issuerCommit"] != arguments["signer_commit"]
            or proof["specSha256"] != sha256_bytes(raw)):
        raise ValueError("Native completed SDK proof differs from its approved issuer")
    request, phase, receipt, member = _completed_sdk_controls(spec, proof["controls"], frozen, original)
    validate_file_record(proof["member"], "Completed SDK object member", with_kind=False)
    if (proof["member"]["relativePath"] != member or proof["member"]["sha256"] != phase["objectSha256"]
            or proof["member"]["bytes"] > 8 * 1024**3):
        raise ValueError("Native completed SDK proof changes its consumed object")
    instance = products._identity(receipt)
    _ensure_native_issuer_commit(root, spec["producer"]["commit"], token)
    before, after = (dict(tree_entries(root, commit)) for commit in (spec["producer"]["commit"], revision))
    if phase_inventory_paths(_changed_inventory_paths(before, after), instance):
        raise QualificationIncompatible("Completed SDK owning inputs changed")
    expected = _phase_records(request["phaseAuthorities"], "Completed SDK authority")[instance]
    authorities, unavailable = products._authorities(root, revision, (instance,))
    if unavailable or authorities != [expected]:
        raise QualificationIncompatible("Completed SDK current authority changed")
    from products.restore import bounded_verify
    _sdk_input_members(proof["sdkInputs"])
    # These are independent read-only observations. All must finish before the
    # native capability exists; their private batch cannot outlive this admission.
    with products._ci_observation_batch():
        source_locator, original_locator, inputs_locator = bounded_verify(lambda observe: observe()[2], (
            lambda: _observe_completed_sdk_resume(spec, token),
            lambda: _observe_completed_sdk_original(original,
                {"repository": REPOSITORY, "event": "pull_request"}, spec["producer"], token),
            lambda: _observe_completed_sdk_inputs(spec, token)))
    if proof["source"] != source_locator or proof["original"] != original_locator:
        raise ValueError("Completed SDK native original or admission source changed")
    if inputs_locator != proof["sdkInputs"]["locator"]:
        raise ValueError("Completed SDK input native source changed")
    return {"spec": spec, "original": original, "proof": proof}


def _ensure_native_issuer_commit(root, commit, token):
    """A full branch fetch does not retain historical PR merge issuer commits."""
    import product_reuse as products
    from sdk_handoff import _ensure_pinned_git_commit
    commit = _commit(commit)
    present = subprocess.run(["git", "--no-replace-objects", "-C", str(root),
        "cat-file", "-e", commit + "^{commit}"], capture_output=True, timeout=30)
    if present.returncode == 0:
        return
    source = products.api_json(f"https://api.github.com/repos/{REPOSITORY}/git/commits/{commit}", token)
    if source.get("sha") != commit:
        raise ValueError("Native issuer Git source differs from its authenticated pin")
    _ensure_pinned_git_commit(root, commit, _commit(source["tree"]["sha"]), token)


def add_completed_frozen_argument(parser):
    parser.add_argument("--completed-frozen-policy", type=Path,
        help="Independent caller-owned native semantic issuer/consumer pins; never retained product state")


def validate_completed_reuse_policy(policy):
    """One exact caller policy schema for hosted and local read-only consumers."""
    extra = {name for name in ("sdkCompletion", "requalificationBaseline")
             if type(policy) is dict and name in policy}
    require_exact_keys(policy, {
        "schemaVersion", "kind", "consumerCommit", "verifierPolicySha256", "artifactId", "artifactSha256",
        "runId", "runAttempt", "signerCommit", "sourceCommit"} | extra, "Caller completed reuse policy")
    if (type(policy["schemaVersion"]) is not int or policy["schemaVersion"] != 1
            or policy["kind"] != "completed-frozen-reuse"):
        raise ValueError("Unsupported completed reuse policy")
    return extra


@contextmanager
def completed_frozen_options(arguments, *, defer=False):
    """Authenticate explicit CLI policy once for this invocation, without ambient fallback."""
    import os
    values = vars(arguments) if not isinstance(arguments, dict) else arguments
    path = values.get("completed_frozen_policy")
    if isinstance(arguments, dict):
        arguments.pop("completed_frozen_policy", None)
    if path is None:
        yield {}
        return
    import product_reuse as products
    root = Path(values.get("repository_root") or Path(__file__).resolve().parents[1]).resolve(strict=True)
    plan = values.get("plan")
    if plan is None and values.get("input_root") is not None:
        plan = Path(values["input_root"]) / "product-resume-inputs/plan/impact-plan.json"
    if plan is None:
        raise ValueError("Completed reuse policy requires the current invocation plan")
    plan_path = Path(plan).absolute()
    path = Path(path).absolute()
    if path.resolve(strict=True) != path:
        raise ValueError("Completed policy path must be normalized and non-symbolic")
    original_plan = read_regular_file_bytes(plan_path, max_bytes=LIMIT, reject_symlink_parents=True)
    original_policy = read_regular_file_bytes(path, max_bytes=4096, reject_symlink_parents=True)
    policy = load_canonical_json_bytes(original_policy)
    extra = validate_completed_reuse_policy(policy)
    plan = products._validate_plan(plan_path, root)
    def unchanged():
        if (read_regular_file_bytes(path, max_bytes=4096, reject_symlink_parents=True) != original_policy
                or read_regular_file_bytes(plan_path, max_bytes=LIMIT, reject_symlink_parents=True) != original_plan):
            raise ValueError("Completed reuse caller policy or current plan changed during use")
    with tempfile.TemporaryDirectory(prefix="completed-reuse-authority-") as temporary:
        def authenticate():
            cap, _ = fetch_completed_frozen(Path(temporary).resolve() / "native", repository_root=root,
                revision=plan["validationCommit"], token=os.environ.get("GITHUB_TOKEN", ""),
                **({"sdk_completion": policy["sdkCompletion"]} if "sdkCompletion" in extra else {}),
                **({"requalification_baseline": policy["requalificationBaseline"]}
                   if "requalificationBaseline" in extra else {}),
                **{argument: policy[field] for argument, field in (
                    ("consumer_commit", "consumerCommit"), ("verifier_policy_sha256", "verifierPolicySha256"),
                    ("artifact_id", "artifactId"), ("artifact_sha256", "artifactSha256"), ("run_id", "runId"),
                    ("run_attempt", "runAttempt"), ("signer_commit", "signerCommit"), ("source_commit", "sourceCommit"))})
            cap.check_consumer(products._consumer(plan, os.environ))
            unchanged()
            return cap
        if defer:
            from concurrent.futures import ThreadPoolExecutor
            from contextvars import copy_context
            # Discovery may read independent catalogs/tooling while this runs.
            # Keep custody alive and join even if the caller never asks for it.
            with ThreadPoolExecutor(max_workers=1) as executor:
                pending = executor.submit(copy_context().run, authenticate)
                try:
                    yield {"completed_frozen_future": pending}
                finally:
                    try:
                        pending.result()
                    finally:
                        unchanged()
        else:
            cap = authenticate()
            try:
                yield {"completed_frozen": cap}
            finally:
                unchanged()


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


def _qualify_frozen_sdk_ios(work, root, commit, token):
    """Fixed issuer-owned original, never a caller-selected SDK authority."""
    import hydrated_evidence
    import product_reuse as products
    from products.inventory import git_regular_blob_bytes, write_canonical_json
    from products.restore import verify_phase_shard
    from products.registry import PhaseInstanceId

    path = "ci/tests/data/sdk-ios-qualification.json"
    raw = read_regular_file_bytes(root / path, max_bytes=LIMIT, reject_symlink_parents=True)
    if git_regular_blob_bytes(root, commit, path, max_bytes=LIMIT) != raw:
        raise ValueError("Fixed SDK qualification fixture differs from issuer source")
    spec = require_exact_keys(load_canonical_json_bytes(raw), {
        "schemaVersion", "artifactId", "artifactSha256", "workflowSha", "receiptSha256",
        "objectSha256", "plan", "receipt"}, "Fixed SDK qualification")
    receipt = validate_phase_receipt(spec["receipt"])
    if (spec["schemaVersion"] != 1 or spec["artifactId"] != 11641964270
            or spec["artifactSha256"] != "sha256:15cf919b4d5cd388c1dc7b12e7933ae5fa75f3ef73de1f155da6bce2eb229f9b"
            or spec["workflowSha"] != "4dcf10739d30dc0462eb03090e17612d4ca6a97b"
            or sha256_bytes(canonical_json_bytes(receipt)) != spec["receiptSha256"]
            or spec["receiptSha256"] != "sha256:03cc3614dd1f44e844c30fc73fda7a4716c8a0783f20fd7468818908cf751d00"
            or spec["objectSha256"] != "sha256:d77bf933a9b15d375cd2e65c3f3d504c7f83e3b55ddf86c480439221481c655c"
            or spec["plan"]["validationCommit"] != receipt["producer"]["commit"]
            or spec["plan"]["validationTree"] != receipt["producer"]["tree"]):
        raise ValueError("Fixed SDK qualification changes its independently reviewed original")
    plan_path, receipt_path = work / "sdk-original-plan.json", work / "sdk-original-receipt.json"
    write_canonical_json(plan_path, spec["plan"])
    write_canonical_json(receipt_path, receipt)
    capture = work / "sdk-original-capture"
    products.capture_sdk_ios_binary_upload(plan_path, capture,
        binary_receipt_path=receipt_path, artifact_id=spec["artifactId"],
        artifact_sha256=spec["artifactSha256"], trusted_workflow_sha=spec["workflowSha"],
        repository_root=root, token=token, compact_recovery=True, qualify_original=True)
    verified = verify_phase_shard(capture / "original/shard", PhaseInstanceId("sdk", "sdk-ios", "binary", "ios"))
    if verified["receiptSha256"] != spec["receiptSha256"] or verified["objectSha256"] != spec["objectSha256"]:
        raise ValueError("Cold SDK qualification changes original receipt/object")
    files = products.regular_file_inventory(capture / "original", allow_empty=True)
    for row in files:
        hydrated_evidence.retain(row, capture / "original" / row["relativePath"])
    manifest = work / "cache-manifest.json"
    existing = load_canonical_json_bytes(read_regular_file_bytes(manifest))
    write_canonical_json(manifest, [*existing, *({"bytes": row["bytes"], "sha256": row["sha256"]} for row in files)])
    return {"kind": "sdk-binary", "receipt": receipt, "artifactId": spec["artifactId"],
            "artifactSha256": spec["artifactSha256"]}


def issue_completed_sdk(work, token):
    """Authenticate one successful completed resume once; never replay or rebuild it."""
    import hashlib
    import os
    import stat
    import zipfile
    import product_reuse as products
    from products.inventory import git_regular_blob_bytes, write_canonical_json
    commit = _commit(os.environ["QUALIFICATION_ISSUER_SHA"])
    root = Path(__file__).resolve().parents[1]
    if (os.environ["QUALIFICATION_ISSUER_REPOSITORY"] != REPOSITORY
            or os.environ["QUALIFICATION_ISSUER_PATH"] != ISSUER_WORKFLOW
            or subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip() != commit
            or not _compatible_verifier(commit)):
        raise ValueError("Completed SDK issuer differs from its native source")
    def source(path):
        raw = git_regular_blob_bytes(root, commit, path, max_bytes=LIMIT)
        if read_regular_file_bytes(root / path, max_bytes=LIMIT, reject_symlink_parents=True) != raw:
            raise ValueError("Completed SDK fixed policy differs from its native issuer source")
        return load_canonical_json_bytes(raw)
    spec, original, frozen = (source(path) for path in (
        _sdk_completed_spec_path(root, commit), _sdk_original_spec_path(root, commit), _frozen_spec_path(root, commit)))
    work = Path(work).resolve()
    work.mkdir(exist_ok=False)
    if spec.get("schemaVersion") in (2, 3, 4):
        from completed_sdk_reuse import issue_extension
        return issue_extension(spec, work, root=root, revision=commit, frozen=frozen, token=token)
    artifact, observed, locator = _observe_completed_sdk_resume(spec, token)
    _, _, original_locator = _observe_completed_sdk_original(original,
        {"repository": REPOSITORY, "event": "pull_request"}, spec["producer"], token)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="completed-sdk-original-", dir=work) as temporary:
        zipped = Path(temporary) / "original.zip"
        products._download_contract_ci_upload(spec["artifactId"], spec["artifactSha256"], artifact["name"],
            spec["producer"], observed[0]["run"], token, destination=zipped, max_bytes=spec["artifactBytes"])
        with zipfile.ZipFile(zipped) as archive:
            entries = archive.infolist()
            if len(entries) > 16384 or len({row.filename for row in entries}) != len(entries):
                raise ValueError("Completed SDK original has duplicate or oversized ZIP directory")
            def member(name, size):
                entry = archive.getinfo(name)
                if (entry.is_dir() or entry.file_size != size or entry.flag_bits & 1
                        or stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG)
                        or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                    raise ValueError("Completed SDK selected member is not exact regular evidence")
                return entry
            controls = {}
            for row in spec["controls"]:
                if row["bytes"] > LIMIT:
                    raise ValueError("Completed SDK control exceeds its bound")
                raw = archive.read(member(row["relativePath"], row["bytes"]))
                if sha256_bytes(raw) != row["sha256"]:
                    raise ValueError("Completed SDK original control digest changed")
                controls[row["relativePath"]] = load_canonical_json_bytes(raw)
            _, phase, _, path = _completed_sdk_controls(spec, controls, frozen, original)
            size = archive.getinfo(path).file_size
            if not 0 < size <= 8 * 1024**3:
                raise ValueError("Completed SDK object exceeds its fixed bound")
            digest = hashlib.sha256()
            with archive.open(member(path, size)) as incoming:
                while chunk := incoming.read(16 * 1024 * 1024):
                    digest.update(chunk)
            if "sha256:" + digest.hexdigest() != phase["objectSha256"]:
                raise ValueError("Completed SDK admitted object differs from its original bytes")
    sdk_inputs = _issue_sdk_input_members(spec, work, root, token)
    value = {"schemaVersion": 1, "kind": "completed-sdk-reuse", "issuerCommit": commit,
        "specSha256": sha256_bytes(canonical_json_bytes(spec)), "source": locator, "original": original_locator,
        "controls": controls, "member": {"relativePath": path, "bytes": size, "sha256": phase["objectSha256"]},
        "sdkInputs": sdk_inputs}
    write_canonical_json(work / "completion.json", value)
    report = {"downloadedOriginalBytes": spec["artifactBytes"] + spec["sdkInputs"]["bytes"], "verifiedObjectBytes": size,
              "sdkConsumerBytes": sum(row["bytes"] for row in sdk_inputs["files"]),
              "controlBytes": sum(row["bytes"] for row in spec["controls"]),
              "seconds": str(time.perf_counter() - started), "productPhasesExecuted": 0}
    print(json.dumps(report), flush=True)
    return report


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
    # Fail before cold acquisition; final verification repeats this over the
    # actually authenticated planner result, not merely the expected fixture.
    proof.verify_frozen_inventories(spec["inventoryBaseline"], spec["expectedResult"]["phases"])
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
        sources.append(_qualify_frozen_sdk_ios(work, root, commit, token))
        if len(sources) != 47 or session.get("downloadedArtifactCount", 0) < 48:
            raise ValueError("Controlled cold issuer did not freshly authenticate every original upload")
        export_originals(sources, work / "qualification.json",
            plan={"event": "pull_request", "pullRequest": 31, "repository": REPOSITORY},
            producer={"pullRequest": 31, "runId": int(os.environ["GITHUB_RUN_ID"]),
                      "runAttempt": int(os.environ["GITHUB_RUN_ATTEMPT"])}, source_commit=commit,
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


# Keep this issuer in the existing native authority module: no new product-owning
# path, and the executing functions remain bound by the existing source identity.
from products.registry import PhaseInstanceId as _RequalifiedPhaseInstanceId

_REQUALIFIED_FROZEN_SPEC = "ci/tests/data/requalified-frozen-reuse.json"
_REQUALIFIED_AGGREGATE = _RequalifiedPhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")


def _inherit_requalified_originals(parent, cap, current, *, policy):
    """Reissue only unchanged native records; preserve every original identity."""
    import product_reuse as products
    if type(cap) is not CompletedFrozenReuse:
        raise ValueError("Requalification requires concrete independently authenticated native authority")
    parent, current = validate(parent), validate(current)
    expected = set(cap.completed_phases())
    if len(expected) != 49 or _REQUALIFIED_AGGREGATE in expected or any(row.product == "sdk" for row in expected):
        raise ValueError("Requalified issuer requires exactly unchanged native49")
    if (len(current["originals"]) != 1
            or products._identity(current["originals"][0]["receipt"]) != _REQUALIFIED_AGGREGATE
            or current["verifierPolicySha256"] != policy):
        raise ValueError("Requalified issuer requires one fully authenticated current aggregate")
    inherited = []
    for row in parent["originals"]:
        instance = products._identity(row["receipt"])
        if instance not in expected:
            continue
        record = {**products._identity_record(instance), "buildKey": row["receipt"]["buildKey"],
                  "receiptSha256": row["receiptSha256"], "objectSha256": row["objectSha256"]}
        if cap.envelope(record, canonical_json_bytes(row["receipt"])) is None:
            raise ValueError("Inherited original has no exact unchanged native completion")
        if cap.original_files(row["identity"]["locator"], row["receipt"]) != row["originalFiles"]:
            raise ValueError("Inherited original member inventory differs from its native parent")
        # This is a new, independently signed delegation, never an edit to the
        # parent's qualification. The report retains its exact native pins/hash.
        inherited.append({**row, "identity": {**row["identity"], "policy": policy}})
    if ({products._identity(row["receipt"]) for row in inherited}
            != {instance for instance in expected if instance.product == "runtime"}):
        raise ValueError("Native parent lacks the exact forty-five unchanged originals")
    return validate({**current, "schemaVersion": 1,
        "originals": sorted([*inherited, *current["originals"]],
                            key=lambda row: products._identity(row["receipt"]))})


def _requalified_signed_checkpoint(spec, work, root, token):
    """The cold proof's signature/payload gate with an explicit signing origin."""
    import product_reuse as products
    from runtime_reference_archive import open_reference_archive, copy_reference_member
    from products.inventory import sha256_file
    from products.signatures import load_keyring, public_key_for_metadata, verify_manifest_signature
    source = spec["requalification"]["signedSource"]
    producer, job = source["producer"], "product-validation / runtime-aggregate-attestation"
    observed = products._observe_ci_producer_jobs({"aggregate": producer},
        jobs_by_phase={"aggregate": job}, trusted_workflow_sha=source["workflowSha"], token=token)
    artifact = products._contract_ci_upload_metadata(source["artifactId"], source["artifactSha256"],
        f"codex-agent-runtime-aggregate-release-handoff-{producer['tree']}-attempt-{producer['runAttempt']}",
        producer, observed[0]["run"], token)
    products._require_artifact_job_window(observed[0], job, artifact)
    signed = work / "signed"
    names = {row["relativePath"] for row in spec["signedCheckpoint"]}
    version = spec["request"]["versions"]["runtime-release"]
    prefix = f"aggregate-input/codex-agent-runtime-{version}"
    expected = {prefix + suffix for suffix in (".attestation.json", ".attestation.sig", "-manifest.json")}
    if (names != expected or len(spec["signedCheckpoint"]) != len(expected)
            or sum(row["bytes"] for row in spec["signedCheckpoint"]) > LIMIT):
        raise ValueError("Requalified checkpoint requires its exact signed control members")
    with open_reference_archive(artifact, token) as (archive, stream):
        for row in spec["signedCheckpoint"]:
            copy_reference_member(archive, row["relativePath"], signed / row["relativePath"], row)
        transferred = stream.transferred
    attestation_path = signed / (prefix + ".attestation.json")
    attestation = load_canonical_json_bytes(read_regular_file_bytes(attestation_path))
    keys = root / "gradle/release/keys"
    public = public_key_for_metadata(attestation["signing"],
        load_keyring(root / "gradle/release/product-signing-keys.json", keys), keys, allow_retired=True)
    verify_manifest_signature(attestation_path, signed / (prefix + ".attestation.sig"),
                              public, attestation["signing"])
    payload = attestation["payload"]
    manifest = signed / "aggregate-input" / payload["fileName"]
    phase = next(row for row in spec["expectedResult"]["phases"] if products._identity(row) == _REQUALIFIED_AGGREGATE)
    if (manifest != signed / (prefix + "-manifest.json")
            or manifest.stat().st_size != payload["bytes"] or sha256_file(manifest) != payload["sha256"]
            or attestation["metadataReceiptSha256"] != phase["receiptSha256"]):
        raise ValueError("Requalified signature changes the exact current aggregate receipt/payload")
    return transferred


def issue_requalified_frozen(work, token):
    """One full changed-original gate, native49, real planner, independent signature."""
    import copy
    import io
    import os
    import zipfile
    import product_reuse as products
    from products.inventory import git_regular_blob_bytes, tree_entries, write_canonical_json
    from products.restore import verification_session
    from products.selection import phase_inventory_paths
    from products.verified_evidence import _source_identity
    root = Path(__file__).resolve().parents[1]
    commit = _commit(os.environ["QUALIFICATION_ISSUER_SHA"])
    if (os.environ["QUALIFICATION_ISSUER_REPOSITORY"] != REPOSITORY
            or os.environ["QUALIFICATION_ISSUER_PATH"] != ISSUER_WORKFLOW
            or subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip() != commit
            or not _compatible_verifier(commit)):
        raise ValueError("Requalified issuer differs from its native source")
    raw = git_regular_blob_bytes(root, commit, _REQUALIFIED_FROZEN_SPEC, max_bytes=LIMIT)
    if read_regular_file_bytes(root / _REQUALIFIED_FROZEN_SPEC, reject_symlink_parents=True) != raw:
        raise ValueError("Requalified fixed fixture differs from native issuer Git")
    spec = load_canonical_json_bytes(raw)
    inputs = require_exact_keys(spec["requalification"], {
        "parent", "parentQualificationSha256", "stateSource", "aggregateOriginal", "signedSource"},
        "Fixed requalification inputs")
    source, parent = inputs["stateSource"], inputs["parent"]
    producer = source["producer"]
    work = Path(work).resolve()
    work.mkdir(exist_ok=False)
    started = time.perf_counter()
    candidate = work / "candidate"
    _ensure_native_issuer_commit(root, producer["commit"], token)
    subprocess.run(["git", "clone", "--shared", "--no-checkout", str(root), str(candidate)], check=True)
    subprocess.run(["git", "-C", str(candidate), "checkout", "--detach", producer["commit"]], check=True)
    if subprocess.check_output(["git", "-C", str(candidate), "rev-parse", "HEAD^{tree}"], text=True).strip() != producer["tree"]:
        raise ValueError("Requalified state Git differs from its fixed producer")
    with verification_session() as session:
        if session.get("portableQualificationInputs"):
            raise ValueError("Requalified issuer must authenticate its explicit native parent")
        cap, native_report = fetch_completed_frozen(work / "parent",
            consumer_commit=commit, verifier_policy_sha256=parent["verifierPolicySha256"],
            repository_root=candidate, revision=producer["commit"],
            sdk_completion=parent["sdkCompletion"], requalification_baseline=parent["requalificationBaseline"],
            **_native_pin_arguments({key: parent[key] for key in (
                "artifactId", "artifactSha256", "runId", "runAttempt", "signerCommit", "sourceCommit")}), token=token)
        parent_raw = read_regular_file_bytes(work / "parent/qualification.json", reject_symlink_parents=True)
        if sha256_bytes(parent_raw) != inputs["parentQualificationSha256"]:
            raise ValueError("Native parent qualification differs from its fixed identity")
        parent_value = load_canonical_json_bytes(parent_raw)
        current_source = inputs["aggregateOriginal"]
        receipt = products.validate_phase_receipt(current_source["receipt"])
        if products._identity(receipt) != _REQUALIFIED_AGGREGATE:
            raise ValueError("Requalification may replace only the aggregate original")
        expected = next(row for row in spec["expectedResult"]["phases"] if products._identity(row) == _REQUALIFIED_AGGREGATE)
        if (receipt["buildKey"] != expected["buildKey"]
                or sha256_bytes(canonical_json_bytes(receipt)) != expected["receiptSha256"]):
            raise ValueError("Changed original differs from the fixed current phase")
        receipt_path = work / "aggregate-receipt.json"
        write_canonical_json(receipt_path, receipt)
        # Before any reference projection exists, the ordinary capture must
        # complete its whole-original gate and create verifier-owned custody.
        products.capture_runtime_original_ci_phases({"metadata": receipt_path}, work / "aggregate",
            target="runtime-aggregate", original_instance=_REQUALIFIED_AGGREGATE,
            trusted_workflow_sha=current_source["workflowSha"], token=token, recovery_projection=True)
        current = export_originals([{"kind": "phase", "receipt": receipt,
            "artifactId": current_source["artifactId"], "artifactSha256": current_source["artifactSha256"]}],
            work / "current-original.json", plan={"repository": REPOSITORY, "event": "pull_request"},
            producer={"pullRequest": 31, "runId": int(os.environ["GITHUB_RUN_ID"]),
                      "runAttempt": int(os.environ["GITHUB_RUN_ATTEMPT"])},
            source_commit=commit, trusted_workflow_sha=current_source["workflowSha"], token=token)
        policy = _source_identity()
        qualified = _inherit_requalified_originals(parent_value, cap, current, policy=policy)
        if next(row for row in qualified["originals"]
                if products._identity(row["receipt"]) == _REQUALIFIED_AGGREGATE)["objectSha256"] != expected["objectSha256"]:
            raise ValueError("New aggregate original changes its fixed object")
        job, name = "product-validation / product-resume", f"codex-agent-product-resume-{producer['tree']}"
        observed = products._observe_ci_producer_jobs({"state": producer}, jobs_by_phase={"state": job},
            trusted_workflow_sha=source["workflowSha"], token=token)
        artifact, carrier = products._download_contract_ci_upload(source["artifactId"], source["artifactSha256"],
            name, producer, observed[0]["run"], token, max_bytes=16 * 1024**2)
        products._require_artifact_job_window(observed[0], job, artifact)
        plan = candidate / "build/requalified-plan.json"
        plan.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(carrier)) as archive:
            entry = archive.getinfo("product-resume-inputs/plan/impact-plan.json")
            if entry.file_size > LIMIT:
                raise ValueError("Requalified source plan exceeds its control bound")
            plan.write_bytes(archive.read(entry))
        environment = {**os.environ, "GITHUB_TOKEN": token, "GITHUB_RUN_ID": str(producer["runId"]),
                       "GITHUB_RUN_ATTEMPT": str(producer["runAttempt"])}
        captured = candidate / "build/requalified-state"
        products.capture_runtime_resume_upload(plan, captured,
            artifact_id=source["artifactId"], artifact_sha256=source["artifactSha256"],
            trusted_workflow_sha=source["workflowSha"], repository_root=candidate,
            environ=environment, token=token, completed_frozen=cap)
        state = captured / "original/product-resume-state"
        verified = products._verified_product_state(plan, state, state, candidate, environment, None,
            sdk_original_workflow_sha=source["workflowSha"], completed_frozen=cap)
        wanted = set(cap.completed_phases()) | {_REQUALIFIED_AGGREGATE}
        if set(verified.prior_carrier_phases) != wanted:
            raise ValueError("Requalified source must retain exactly fifty current phases")
        request = copy.deepcopy(verified.rebased_request)
        request["requested"] = [products._identity_record(_REQUALIFIED_AGGREGATE)]
        for field in ("phaseAuthorities", "availableObjects", "runtimeValidationEvidence"):
            request[field] = [row for row in request[field] if products._identity(row) in wanted]
        normalized = {**request, "artifactRoot": ".", "repositoryRoot": "."}
        if normalized != spec["request"]:
            raise ValueError("Requalified request differs from its fixed original controls")
        result = products.plan_reuse_wave(request, completed_frozen=cap)
        if result != spec["expectedResult"] or not result["fullReuse"] or any(result["matrices"].values()):
            raise ValueError("Requalified real planner must retain exactly fifty and elect nothing")
        baseline = dict(tree_entries(candidate, producer["commit"]))
        current_tree = dict(tree_entries(root, commit))
        changed = _changed_inventory_paths(baseline, current_tree)
        if any(phase_inventory_paths(changed, instance) for instance in wanted):
            raise ValueError("Requalified issuer changes a completed owning inventory")
        if any(path == "gradle/release/product-signing-keys.json" or path.startswith("gradle/release/keys/")
               for path in changed):
            raise ValueError("Requalified issuer changes the authenticated public trust")
        authorities, unavailable = products._authorities(root, commit, tuple(sorted(wanted)))
        if (unavailable or authorities != spec["request"]["phaseAuthorities"]
                or products._versions(root, commit) != spec["request"]["versions"]):
            raise ValueError("Requalified issuer changes the authenticated authorities or versions")
        if spec["inventoryBaseline"] != producer["commit"]:
            raise ValueError("Requalified inventory baseline must equal the verified source")
        signed_range_bytes = _requalified_signed_checkpoint(spec, work, root, token)
        receipts = [load_canonical_json_bytes(raw) for fields, raw in cap._receipts if fields[0] == "contract"]
        if _completed_contract_source(spec, receipts, qualified["originals"]) is None:
            raise ValueError("Requalified Contract controls lack complete inherited native coverage")
        proof = {"frozenPhases": 50, "selectedProductPhases": 0, "changedFrozenInventories": 0,
            "resultSha256": sha256_bytes(canonical_json_bytes(result)), "verificationPolicySha256": policy,
            "freshOriginalPhases": [{**products._identity_record(products._identity(row["receipt"])),
                "receiptSha256": row["receiptSha256"]} for row in qualified["originals"]],
            "checkpoint": spec["signedCheckpoint"], "contractReceipts": receipts}
        _completed_frozen_controls(spec, proof, qualified)
        if _source_identity() != policy or not _compatible_verifier(commit):
            raise ValueError("Requalified issuer changed during verification")
        report = {"mode": "native-parent-requalification", "parent": parent,
            "parentQualificationSha256": inputs["parentQualificationSha256"],
            "nativeParent": native_report, "inheritedOriginals": 45, "fullyAuthenticatedNewOriginals": 1,
            "downloadedArtifactCount": session.get("downloadedArtifactCount", 0),
            "downloadedArtifactBytes": session.get("downloadedArtifactBytes", 0),
            "signedCheckpointRangeBytes": signed_range_bytes,
            "selectedProductPhases": 0, "seconds": str(time.perf_counter() - started)}
        for name, value in (("qualification.json", qualified), ("proof.json", proof),
                ("qualification-issue.json", report), ("prepare.json", {"source": source}),
                ("cache-save.json", {"mode": "not-required", "uploadedProductBytes": 0})):
            write_canonical_json(work / name, value)
    return report


if __name__ == "__main__":
    import argparse
    import os
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("issue-frozen", "issue-requalified-frozen", "issue-completed-sdk", "fetch"))
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
    elif args.mode == "issue-requalified-frozen":
        reuse_qualification.issue_requalified_frozen(args.work, os.environ["GITHUB_TOKEN"])
    elif args.mode == "issue-completed-sdk":
        reuse_qualification.issue_completed_sdk(args.work, os.environ["GITHUB_TOKEN"])
    else:
        reuse_qualification.fetch_qualification(args.work, artifact_id=args.artifact_id,
            artifact_sha256=args.artifact_sha256, run_id=args.run_id, run_attempt=args.run_attempt,
            signer_commit=args.signer_commit, source_commit=args.source_commit, token=os.environ["GITHUB_TOKEN"])


def read_blobs(repository, objects, *, max_bytes, total_bytes):
    """Read exact blob IDs in two processes; bound bytes before requesting bodies."""
    if any(type(limit) is not int or limit < 0 for limit in (max_bytes, total_bytes)):
        raise ValueError("Control Git byte bounds must be nonnegative integers")
    identifiers = tuple(dict.fromkeys(objects))
    if any(type(oid) is not str or re.fullmatch(r"[0-9a-f]{40}", oid) is None for oid in identifiers):
        raise ValueError("Control Git reads require exact object IDs")
    if not identifiers:
        return {}
    command = ["git", "--no-replace-objects", "-C", str(repository), "cat-file"]
    request = "".join(oid + "\n" for oid in identifiers).encode("ascii")
    def batch(mode):
        # A seekable request avoids both ends blocking on full pipes (observed
        # with large control inventories on macOS). Keep the same bounded reads.
        with tempfile.TemporaryFile() as source:
            source.write(request)
            source.seek(0)
            return subprocess.run(command + [mode], stdin=source,
                capture_output=True, check=True, timeout=30).stdout
    headers = batch("--batch-check").splitlines()
    if len(headers) != len(identifiers):
        raise ValueError("Control Git metadata count differs")
    sizes, total = [], 0
    for oid, header in zip(identifiers, headers, strict=True):
        fields = header.split()
        if len(fields) != 3 or fields[:2] != [oid.encode(), b"blob"] or not fields[2].isdigit():
            raise ValueError("Control Git object is missing or is not the exact blob")
        size = int(fields[2])
        total += size
        if size > max_bytes or total > total_bytes:
            raise ValueError("Control Git blobs exceed the source-byte bound")
        sizes.append(size)
    raw = batch("--batch")
    result, offset = {}, 0
    for oid, size in zip(identifiers, sizes, strict=True):
        header = f"{oid} blob {size}\n".encode("ascii")
        if raw[offset:offset + len(header)] != header:
            raise ValueError("Control Git blob identity or size changed")
        start = offset + len(header)
        offset = start + size + 1
        if len(raw[start:offset - 1]) != size or raw[offset - 1:offset] != b"\n":
            raise ValueError("Control Git blob response is truncated")
        result[oid] = raw[start:offset - 1]
    if offset != len(raw):
        raise ValueError("Control Git batch has unexpected trailing data")
    return result
