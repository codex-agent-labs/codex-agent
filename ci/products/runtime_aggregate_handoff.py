"""Read complete original aggregate caller evidence under caller-pinned trust.

The main release signature authenticates product receipts/content; compact
external CI proofs carry a separate signature by the same release key. Neither
unsigned caller/selection nor historical observations become fresh CI authority.
This reader does not elect state, sign, contact CI, or rebuild an aggregate.
"""

from contextlib import contextmanager
from pathlib import Path
import tempfile

from .aggregate import verify_runtime_aggregate_artifacts
from .contract_projection import verify_contract_component_projection
from .inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, regular_file_inventory,
    require_array, require_exact_keys, require_integer, require_regular_directory,
    require_sha256, sha256_bytes, sha256_file,
    snapshot_regular_tree, verified_zip_contents,
)
from .receipt import verify_output_manifest_identity
from .registry import NATIVE_TARGETS, PhaseInstanceId
from .restore import verify_phase_shard
from .runtime_aggregate import _adapter_receipt_identities
from .runtime_attestation import read_runtime_variant_handoff
from .sdk_runtime_content import verify_native_runtime_validation_content
from .signatures import load_keyring, public_key_path, verify_manifest_signature


def _json(path):
    return load_canonical_json_bytes(read_regular_file_bytes(
        path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))


def _verify_original_ci_proof(proof_path, signature, public_key, signing, receipt_bytes, workflow_sha):
    """Verify a release-only assertion of completed original upload gates.

    Signed historical API observations are not fresh API authority. The issuer
    authenticated complete uploads before signing; retained stages/receipts and
    the main aggregate signature still undergo their independent full gates.
    """
    from product_reuse import (
        _CATALOG_LIMIT, _OID, _matching_ci_jobs, _require_artifact_job_window,
        _runtime_prior_workflow_sha, run_matches_pr,
    )

    proof = require_exact_keys(_json(proof_path),
        {"target", "observed", "artifacts", "receiptSha256s", "signing"}, "Signed original aggregate transport evidence")
    if proof["signing"] != signing:
        raise ValueError("Original aggregate proof differs from the authenticated aggregate signer")
    verify_manifest_signature(proof_path, signature, public_key, signing)
    identities = [*_adapter_receipt_identities(), ("runtime-aggregate", "metadata", "aggregate")]
    names = {"-".join(identity) for identity in identities}
    require_exact_keys(proof["artifacts"], names, "Original aggregate artifacts")
    require_exact_keys(proof["receiptSha256s"], names, "Original aggregate receipt digests")
    if proof["target"] != "aggregate":
        raise ValueError("Original aggregate proof target is invalid")
    attempts = {}
    for observation in require_array(proof["observed"], "Original aggregate observations"):
        require_exact_keys(observation, {"run", "testedCommit", "jobs"}, "Original aggregate observation")
        run = observation["run"]
        if not isinstance(run, dict) or not isinstance(observation["testedCommit"], dict):
            raise ValueError("Original aggregate observation run/commit is malformed")
        identity = (require_integer(run.get("id"), "Original aggregate run", 1),
                    require_integer(run.get("run_attempt"), "Original aggregate attempt", 1))
        if identity in attempts:
            raise ValueError("Original aggregate observations repeat an attempt")
        attempts[identity] = observation
    used = set()
    for identity in identities:
        name = "-".join(identity)
        raw = receipt_bytes[PhaseInstanceId("runtime", *identity)]
        receipt = load_canonical_json_bytes(raw)
        producer = receipt["producer"]
        attempt = (producer["runId"], producer["runAttempt"])
        observation = attempts.get(attempt)
        if observation is None or proof["receiptSha256s"][name] != sha256_bytes(raw):
            raise ValueError("Original aggregate proof changes an original receipt/producer")
        used.add(attempt)
        run, commit = observation["run"], observation["testedCommit"]
        if (run.get("path") != producer["workflowPath"] or run.get("event") != producer["event"]
                or producer["event"] not in {"pull_request", "merge_group"}
                or producer["repository"] != "codex-agent-labs/codex-agent"
                or any(not isinstance(run.get(field), dict)
                       or run[field].get("full_name") != producer["repository"] or run[field].get("fork") is not False
                       for field in ("repository", "head_repository"))
                or producer["event"] == "pull_request" and not run_matches_pr(run, producer["pullRequest"])
                or commit.get("sha") != producer["commit"]
                or not isinstance(commit.get("tree"), dict) or commit["tree"].get("sha") != producer["tree"]
                or _runtime_prior_workflow_sha(run, workflow_sha) is None):
            raise ValueError("Original aggregate proof differs from its reviewed original producer")
        trigger_head = run.get("head_sha")
        if not isinstance(trigger_head, str) or _OID.fullmatch(trigger_head) is None:
            raise ValueError("Original aggregate proof lacks its triggering head")
        if producer["event"] == "pull_request":
            requests = [request for request in require_array(run.get("pull_requests"), "Original aggregate pull requests")
                        if isinstance(request, dict) and request.get("number") == producer["pullRequest"]]
            if len(requests) != 1:
                raise ValueError("Original aggregate proof pull request is ambiguous")
            heads = [requests[0].get(field) for field in ("base", "head")]
            if any(not isinstance(head, dict) or not isinstance(head.get("sha"), str)
                   or _OID.fullmatch(head["sha"]) is None for head in heads):
                raise ValueError("Original aggregate proof lacks exact pull-request base/head")
            original_head = trigger_head if trigger_head != producer["commit"] else heads[1]["sha"]
            parents = require_array(commit.get("parents"), "Original aggregate tested merge parents")
            if [parent.get("sha") if isinstance(parent, dict) else None for parent in parents] != [heads[0]["sha"], original_head]:
                raise ValueError("Original aggregate proof tested merge differs from its original base/head")
        elif trigger_head != producer["commit"]:
            raise ValueError("Original aggregate proof merge group differs from its tested commit")
        jobs = require_array(observation["jobs"], "Original aggregate jobs")
        if any(not isinstance(job, dict) for job in jobs):
            raise ValueError("Original aggregate proof jobs are malformed")
        job_name = f"product-validation / runtime-{name}"
        selected = _matching_ci_jobs(jobs, job_name)
        if (len(selected) != 1 or selected[0].get("run_id") != producer["runId"]
                or selected[0].get("head_sha") != run.get("head_sha")
                or selected[0].get("status") != "completed" or selected[0].get("conclusion") != "success"):
            raise ValueError("Original aggregate proof job did not succeed for its exact producer")
        require_integer(selected[0].get("id"), "Original aggregate job ID", 1)
        require_integer(selected[0].get("run_id"), "Original aggregate job run", 1)
        artifact = proof["artifacts"][name]
        if not isinstance(artifact, dict):
            raise ValueError("Original aggregate proof artifact is malformed")
        artifact_id = require_integer(artifact.get("id"), "Original aggregate artifact ID", 1)
        size = require_integer(artifact.get("size_in_bytes"), "Original aggregate artifact bytes", 1)
        require_sha256(artifact.get("digest"), "Original aggregate artifact digest")
        transport = artifact.get("workflow_run")
        expected_name = (f"codex-agent-runtime-worker-{name}-{receipt['buildKey'][7:]}-"
                         f"{producer['tree']}-attempt-{producer['runAttempt']}")
        if (size > _CATALOG_LIMIT or artifact.get("expired") is not False or artifact.get("name") != expected_name
                or artifact.get("archive_download_url") != f"https://api.github.com/repos/{producer['repository']}/actions/artifacts/{artifact_id}/zip"
                or not isinstance(transport, dict) or transport.get("id") != producer["runId"]
                or transport.get("head_sha") != run.get("head_sha")):
            raise ValueError("Original aggregate proof artifact differs from its original producer")
        require_integer(transport.get("id"), "Original aggregate artifact run", 1)
        _require_artifact_job_window(observation, job_name, artifact)
    if used != set(attempts):
        raise ValueError("Original aggregate proof has unrelated observations")
    return proof


def _verify_raw_original_ci(root, proof_path, receipt_bytes, file, tree):
    """Preserve admission of unchanged historical four-field raw carriers."""
    from product_reuse import _CATALOG_ZIP_LIMITS
    proof = require_exact_keys(_json(proof_path), {"target", "observed", "artifacts", "receiptSha256s"},
                               "Original aggregate transport evidence")
    file(proof_path)
    identities = [*_adapter_receipt_identities(), ("runtime-aggregate", "metadata", "aggregate")]
    names = {"-".join(identity) for identity in identities}
    require_exact_keys(proof["artifacts"], names, "Original aggregate artifacts")
    require_exact_keys(proof["receiptSha256s"], names, "Original aggregate receipt digests")
    if proof["target"] != "aggregate" or not isinstance(proof["observed"], list) or not proof["observed"]:
        raise ValueError("Original aggregate transport context is incomplete")
    for identity in identities:
        name = "-".join(identity)
        directory = root / "original-evidence/phases" / name
        archive = directory / "transport.zip"
        zipped, _, archive_record = verified_zip_contents(archive, retained_paths=(), allow_empty_members=True,
                                                         **_CATALOG_ZIP_LIMITS)
        if (zipped != tree(directory / "original", allow_empty=True)
                or archive_record["sha256"] != proof["artifacts"][name].get("digest")
                or archive_record["bytes"] != proof["artifacts"][name].get("size_in_bytes")):
            raise ValueError("Original aggregate upload/extraction inventory differs")
        file(archive)
        instance = PhaseInstanceId("runtime", *identity)
        shard = verify_phase_shard(directory / "original/shard", instance)
        if shard["receiptBytes"] != receipt_bytes[instance] or proof["receiptSha256s"][name] != sha256_bytes(receipt_bytes[instance]):
            raise ValueError("Original aggregate transport changes a signed original receipt")


def _public_policy(keyring, keys_directory, destination):
    """Capture declared public files only; the caller supplies the authority."""
    if keyring is None or keys_directory is None:
        raise ValueError("Aggregate release handoff requires caller-pinned public policy")
    policy = load_keyring(keyring, keys_directory)
    paths = {"product-signing-keys.json": Path(keyring)}
    for record in ([policy["activeKey"]] if policy["activeKey"] else []) + policy["retiredKeys"]:
        paths[f"keys/{record['keyId']}.pub"] = public_key_path(keys_directory, record["keyId"])
    originals = {name: read_regular_file_bytes(path, max_bytes=64 * 1024, reject_symlink_parents=True)
                 for name, path in paths.items()}
    for name, raw in originals.items():
        output = destination / name
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(raw)
    (destination / "keys").mkdir(exist_ok=True)
    load_keyring(destination / "product-signing-keys.json", destination / "keys")
    return paths, originals


def _verify_captured(root, keyring, keys_directory):
    # The protected caller later imports this module for reuse. No top-level
    # caller import, second selector, or alternate receipt schema is necessary.
    from runtime_aggregate_release import _selected_originals
    from runtime_aggregate_phase import collect_finalized_inputs

    expected = set()

    def file(path):
        expected.add(path.relative_to(root).as_posix())

    def tree(path, *, allow_empty=False):
        records = regular_file_inventory(path, allow_empty=allow_empty)
        expected.update((path / record["relativePath"]).relative_to(root).as_posix() for record in records)
        return records

    caller = _json(root / "caller.json")
    require_exact_keys(caller, {"schemaVersion", "target", "trustedSourceCommit", "trustedSourceTree",
        "trustedWorkflowSha", "transportProducer", "authorizationReason", "event", "environment",
        "metadataReceiptSha256"}, "Original aggregate caller record")
    if type(caller["schemaVersion"]) is not int or caller["schemaVersion"] != 1 or caller["target"] != "aggregate":
        raise ValueError("Original aggregate caller identity is invalid")
    file(root / "caller.json")
    selected = root / "selected-inputs"
    selection = _json(selected / "selection.json")
    originals = _selected_originals(selected, selection, caller["transportProducer"], selection["metadata"]["buildKey"])
    file(selected / "selection.json")
    receipts, receipt_bytes = {}, {}
    for identity, original in originals.items():
        receipt = original["receipt"]
        outputs = verify_output_manifest_identity(original["stage"], *identity, receipt["productVersion"])["outputs"]
        if outputs != receipt["outputs"]:
            raise ValueError("Aggregate retained stage differs from its original receipt")
        tree(original["stage"])
        file(original["receiptPath"])
        instance = PhaseInstanceId(*identity)
        receipts[instance] = receipt
        receipt_bytes[instance] = read_regular_file_bytes(original["receiptPath"], reject_symlink_parents=True)

    def original(component, phase, target):
        return originals[("runtime", component, phase, target)]

    aggregate = original("runtime-aggregate", "metadata", "aggregate")
    records = collect_finalized_inputs(aggregate["stage"], aggregate["receiptPath"], selection["contractVersion"], original)
    if records["manifest"].relative_to(selected).as_posix() != selection["aggregateManifest"]:
        raise ValueError("Aggregate retained manifest differs from its original selection")
    contract = originals[("contract", "contract", "metadata", "common")]
    version = selection["contractVersion"]
    if contract["receipt"]["productVersion"] != version:
        raise ValueError("Retained Contract version differs from its original receipt")
    handoff = selected / "contract-input"
    stem = f"codex-agent-contract-{version}"
    contract_args = dict(contract_payload=handoff / f"{stem}.zip", contract_metadata_receipt=contract["receiptPath"],
        contract_attestation=handoff / f"{stem}.attestation.json",
        contract_attestation_signature=handoff / f"{stem}.attestation.sig", contract_public_key=handoff / "public-key.pub")
    for name in (f"{stem}.zip", f"{stem}.attestation.json", f"{stem}.attestation.sig", "public-key.pub"):
        file(handoff / name)
    tree(handoff / "execution-closure")  # Existing full Contract gate enforces its exact manifest/inventory.
    for phase in ("binary", "package", "validation", "metadata"):
        if read_regular_file_bytes(handoff / f"execution-closure/receipts/{phase}.json") != \
                receipt_bytes[PhaseInstanceId("contract", "contract", phase, "common")]:
            raise ValueError("Retained Contract handoff changes an original receipt")

    def transported_policy(path):
        # Validate public-only transport shape; NEVER use it for verification.
        policy = load_keyring(path / "product-signing-keys.json", path / "keys")
        file(path / "product-signing-keys.json")
        for record in ([policy["activeKey"]] if policy["activeKey"] else []) + policy["retiredKeys"]:
            file(public_key_path(path / "keys", record["keyId"]))

    transported_policy(root / "trust")
    if (selected / "trust").exists():
        transported_policy(selected / "trust")
    signatures = {name: {} for name in ("variant_attestations", "variant_attestation_signatures", "variant_public_keys")}
    for target in NATIVE_TARGETS:
        native = root / "variant-inputs" / target
        verified = read_runtime_variant_handoff(native, target=target, keyring=keyring, keys_directory=keys_directory)
        tree(native)
        if (any(verified["receiptBytes"][phase] != path.read_bytes()
                for phase, path in records["variant_phase_receipts"][target].items())
                or verified["files"][verified["attestation"]["payload"]["fileName"]] != records["variant_bundles"][target].read_bytes()
                or verified["files"]["validation-evidence.json"] != records["variant_validation_evidence"][target].read_bytes()):
            raise ValueError("Retained native handoff differs from original aggregate inputs")
        payload_stem = Path(verified["attestation"]["payload"]["fileName"]).stem
        signatures["variant_attestations"][target] = native / f"{payload_stem}.attestation.json"
        signatures["variant_attestation_signatures"][target] = native / f"{payload_stem}.attestation.sig"
        signatures["variant_public_keys"][target] = native / "public-key.pub"
        projection = verify_contract_component_projection(contract["stage"], contract["receiptPath"],
            contract_args["contract_attestation"], contract_args["contract_attestation_signature"],
            contract_args["contract_public_key"], expected_trust_domain="release", expected_contract_version=version,
            required_components=("common", target), keyring=keyring, keys_directory=keys_directory)
        for phase in ("package", "validation"):
            staged = root / "runtime-stages" / target / phase
            if tree(staged) != regular_file_inventory(original(target, phase, target)["stage"]):
                raise ValueError("Retained native raw stage differs from selected original")
        verify_native_runtime_validation_content(target, root / "runtime-stages", records["variant_phase_receipts"][target],
            records["variant_bundles"][target], signatures["variant_attestations"][target],
            signatures["variant_attestation_signatures"][target], signatures["variant_public_keys"][target],
            projection, contract_args["contract_payload"], required_trust_domain="release",
            keyring=keyring, keys_directory=keys_directory)

    retained = root / "aggregate-input"
    runtime_version = aggregate["receipt"]["productVersion"]
    manifest = records.pop("manifest")
    metadata = records.pop("metadata_receipt")
    attestation_path = retained / f"codex-agent-runtime-{runtime_version}.attestation.json"
    signature = retained / f"codex-agent-runtime-{runtime_version}.attestation.sig"
    public_key = retained / "public-key.pub"
    for path in (attestation_path, signature, public_key, retained / manifest.name, retained / "metadata-receipt.json"):
        file(path)
    if (read_regular_file_bytes(retained / manifest.name) != read_regular_file_bytes(manifest)
            or read_regular_file_bytes(retained / "metadata-receipt.json") != read_regular_file_bytes(metadata)
            or caller["metadataReceiptSha256"] != sha256_file(metadata)):
        raise ValueError("Retained aggregate handoff differs from exact original payload/receipt")
    value = verify_runtime_aggregate_artifacts(manifest, aggregate_metadata_receipt=metadata,
        aggregate_attestation=attestation_path, aggregate_attestation_signature=signature, aggregate_public_key=public_key,
        **records, **contract_args, **signatures, required_trust_domain="release",
        contract_keyring=keyring, contract_keys_directory=keys_directory,
        variant_keyring=keyring, variant_keys_directory=keys_directory,
        aggregate_keyring=keyring, aggregate_keys_directory=keys_directory)

    # Signed compact proofs attest the original full-upload gates; legacy
    # carriers still require every original ZIP and exact extraction.
    proof_path = root / "original-evidence/transport/original-ci-phases.json"
    proof_signature = proof_path.with_suffix(".sig")
    if proof_signature.exists():
        _verify_original_ci_proof(proof_path, proof_signature, public_key,
                                 _json(attestation_path)["signing"], receipt_bytes, caller["trustedWorkflowSha"])
        file(proof_path)
        file(proof_signature)
    else:
        _verify_raw_original_ci(root, proof_path, receipt_bytes, file, tree)
    current = root / "selected-state-transport"
    if current.exists():
        transport = _json(current / "capture-transport.json")
        keys = {"artifact", "captureProducer", "observed"}
        require_exact_keys(transport, keys | ({"stateWave"} if "stateWave" in transport else set()), "Original state transport")
        wave = transport.get("stateWave", 0)
        if type(wave) is not int or not 0 <= wave <= 5 or transport["captureProducer"] != caller["transportProducer"]:
            raise ValueError("Retained current transport differs from original caller")
        required = {"product-resume-inputs", "product-resume-state"} | ({"runtime-state"} if wave else set())
        if {path.name for path in (current / "original").iterdir()} != required:
            raise ValueError("Retained current transport has unexpected original directories")
        tree(current / "original", allow_empty=True)
        file(current / "capture-transport.json")
    inventory = regular_file_inventory(root, allow_empty=True)
    if {record["relativePath"] for record in inventory} != expected:
        raise ValueError("Aggregate handoff contains missing or unexpected files")
    return {"manifest": value, "attestation": _json(attestation_path), "receipts": receipts,
            "receiptBytes": receipt_bytes, "inventory": inventory,
            "originalPhases": {PhaseInstanceId(*identity): original for identity, original in originals.items()},
            "nativeRuntimeEvidence": {target: {
                "target": target, "stageRoot": str(root / "runtime-stages"),
                "phaseReceipts": {phase: str(path) for phase, path in records["variant_phase_receipts"][target].items()},
                "payload": str(records["variant_bundles"][target]),
                "attestation": str(signatures["variant_attestations"][target]),
                "attestationSignature": str(signatures["variant_attestation_signatures"][target]),
                "publicKey": str(signatures["variant_public_keys"][target]),
                "keyring": str(keyring), "keysDirectory": str(keys_directory),
            } for target in NATIVE_TARGETS},
            "indexInputs": {
                "manifest": manifest, "metadata_receipt": metadata,
                "attestation": attestation_path, "signature": signature, "public_key": public_key,
                **{name: records[name] for name in ("variant_bundles", "variant_phase_receipts",
                    "variant_validation_evidence", "adapter_receipts")},
                **signatures,
                "keyring": keyring, "keys_directory": keys_directory,
                "variant_keyring": keyring, "variant_keys_directory": keys_directory,
            }}


@contextmanager
def verified_runtime_aggregate_handoff(root: Path, *, keyring: Path, keys_directory: Path):
    """Yield only a private full-gate capture; recheck inputs on context exit.

    The caller compares these exact original receipts with its selected current
    closure and copies `directory` while this context is open. Retired release
    keys are valid through the existing signature policy; transported policy is
    never substituted for the caller's pin. No signing or network is performed.

    ``indexInputs`` exposes only existing index-admission keyword arguments from
    this private verified capture, not a new admission token. Use them inside
    this context with the existing index verifier; publish only after context
    exit has rechecked every original, private byte and captured caller policy.
    ``originalPhases`` exposes the already verified stage, receiptPath and receipt
    for every original PhaseInstanceId. Its paths share this context's lifetime;
    they are not a serialized transport or an independent admission token.
    ``nativeRuntimeEvidence`` supplies the existing native projection request
    records from these same originals and the caller's captured public policy.
    Its absolute paths are valid only inside this context; a consumer must still
    invoke the existing projector with its own authenticated Contract projection.
    """
    root = Path(root).absolute()
    for path in (root, *root.parents):
        require_regular_directory(path, "Aggregate handoff ancestry")
    roots = {"aggregate-input", "caller.json", "original-evidence", "runtime-stages", "selected-inputs",
             "trust", "variant-inputs"}
    names = {path.name for path in root.iterdir()}
    if names not in (roots, roots | {"selected-state-transport"}):
        raise ValueError("Aggregate handoff requires its exact direct original carrier layout")
    before = regular_file_inventory(root, allow_empty=True)
    with tempfile.TemporaryDirectory(prefix="runtime-aggregate-handoff-") as temporary:
        private = Path(temporary).resolve()
        paths, policy_bytes = _public_policy(keyring, keys_directory, private / "policy")
        policy_inventory = regular_file_inventory(private / "policy")
        captured = private / "handoff"
        snapshot_regular_tree(root, captured, allow_empty=True)
        if regular_file_inventory(captured, allow_empty=True) != before:
            raise ValueError("Aggregate handoff changed during capture")
        value = _verify_captured(captured, private / "policy/product-signing-keys.json", private / "policy/keys")

        def unchanged():
            if ({path.name for path in root.iterdir()} != names
                    or {path.name for path in captured.iterdir()} != names
                    or regular_file_inventory(root, allow_empty=True) != before
                    or regular_file_inventory(captured, allow_empty=True) != before
                    or regular_file_inventory(private / "policy") != policy_inventory
                    or any(read_regular_file_bytes(path, max_bytes=64 * 1024, reject_symlink_parents=True) != policy_bytes[name]
                           for name, path in paths.items())):
                raise ValueError("Original or captured aggregate handoff/policy changed during verification")

        unchanged()
        yield {**value, "directory": captured}
        unchanged()
