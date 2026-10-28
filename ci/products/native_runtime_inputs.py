"""External original K/R evidence transport; never a product or trust authority."""

from pathlib import Path
import argparse
import tempfile

from .contract_attestation import CONTRACT_EXECUTION_CLOSURE_DIRECTORY
from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, require_relative_path, snapshot_regular_tree,
    regular_file_inventory,
)
from .reuse import _native_comparison_provider, _native_comparison_records
from .sdk_inputs import _copy_file
from .signatures import load_keyring, public_key_path


REQUEST_NAME = "native-runtime-evidence.json"


def _completed_native_content(target, receipt, contract, component_id, stage):
    """Project already-authenticated facts; this helper grants no authority.

    Keep byte-equivalence with sdk_runtime_content's full gate. Moving that
    product-owned projector now would invalidate the genuine completed keys.
    """
    from .runtime_evidence import PRODUCT_RUNTIME_TARGETS, derive_authenticated_runtime_validation_projection
    from .sdk_runtime_content import _digest
    evidence_target = next(name for name, value in PRODUCT_RUNTIME_TARGETS.items() if value == target)
    report = load_canonical_json_bytes(read_regular_file_bytes(
        stage / f"outputs/c-abi/c-abi-package-{target}.json", reject_symlink_parents=True))
    if report.get("schemaVersion") != 2:
        raise ValueError("Completed native projection requires the qualified projected C ABI schema")
    c_abi = {name: value for name, value in report.items()
             if name not in {"producerCommit", "producerTree", "tools", "consumers", "gnuConsumers"}}
    for name in c_abi:
        if name.endswith("Sha256"):
            c_abi[name] = _digest(c_abi[name], name)
    c_abi["importLibraries"] = [{"path": item["path"], "sha256": _digest(item["sha256"], "import library")}
                                for item in report["importLibraries"]]
    c_abi["tools"] = [{"id": item["id"]} for item in report["tools"]]
    for name in ("consumers", "gnuConsumers"):
        c_abi[name] = [{key: item[key] for key in ("source", "sourceSha256", "language", "linked", "executed", "exitCode")}
                       for item in report[name]]
        for item in c_abi[name]:
            item["sourceSha256"] = _digest(item["sourceSha256"], "consumer source")
    prefix = "outputs/c-abi-reference/"
    reference = [{"relativePath": item["relativePath"][len(prefix):], "bytes": item["bytes"], "sha256": item["sha256"]}
                 for item in receipt["outputs"] if item["kind"] == "c-abi-reference" and item["relativePath"].startswith(prefix)]
    return {
        "schemaVersion": 1, "kind": "runtime-native-validation-content", "target": target,
        "componentId": component_id, "contract": {"digest": contract["contractDigest"],
            "componentDigest": contract["componentDigests"][target]},
        "validationInputs": {name: receipt["inputs"][name] for name in
                             ("phaseInputDigest", "toolchainProfileDigest", "flagsDigest", "outputSchemaVersion")},
        "referenceFiles": sorted(reference, key=lambda row: row["relativePath"]),
        "desktop": derive_authenticated_runtime_validation_projection(target,
            [stage / f"outputs/native/desktop-runtime-{evidence_target}.json"], [receipt]),
        "cAbi": c_abi,
        "bootstrap": (load_canonical_json_bytes(read_regular_file_bytes(
            stage / "outputs/c-abi-bootstrap/bootstrap-content.json", reject_symlink_parents=True))
            if target == "macos-arm64" else None),
    }


def completed_native_runtime_provider(completed, request, *, plan, producer, trusted_workflow_sha, token):
    """Reuse a full native/signing gate; never promote a supplied report or digest.

    The protected aggregate signer already ran full K/R semantics for the exact
    four receipts per target. Native completion binds those immutable originals
    and their member inventories to unchanged current inputs. Only their small
    consumed facts are fetched here; product consumers still verify package bytes.
    """
    import product_reuse as products
    from reuse_qualification import CompletedFrozenReuse, _requalified_signed_checkpoint
    from runtime_reference_archive import open_reference_archive, copy_reference_member
    from .aggregate import validate_runtime_aggregate
    from .contract_projection import VerifiedContractProjection
    from .inventory import sha256_bytes
    from .plan import native_runtime_validation_dependencies
    from .registry import PhaseInstanceId
    from .restore import bounded_verify, _VERIFICATION_SESSION, memoized_file_inventory
    from .runtime_aggregate import validate_runtime_aggregate_attestation
    from .runtime_evidence import PRODUCT_RUNTIME_TARGETS
    from .sdk_runtime_content import VerifiedNativeRuntimeProjection, _VERIFIED_NATIVE_RUNTIME, _native_contract_identity
    from runtime_reference_transport import count, measured

    if type(completed) is not CompletedFrozenReuse:
        raise TypeError("Native projection requires concrete completed native authority")
    completed.check_request(request)
    completed.check_consumer({"kind": "ci", "producer": producer})
    spec, phases = completed._values()
    if "requalification" not in spec or request.get("sdkRuntimeSource") is not None:
        return None  # Other releases retain their ordinary complete K/R gate.
    cache, checkpoint, sources = {}, {}, {}
    root = Path(request["repositoryRoot"])
    session = _VERIFICATION_SESSION.get()

    def authority():
        return sha256_bytes(canonical_json_bytes({
            "plan": plan, "producer": producer, "workflow": trusted_workflow_sha,
            "root": str(root.resolve(strict=True)), "version": request["versions"]["runtime-release"],
            "spec": completed._values()[0],
            "keyring": sha256_bytes(read_regular_file_bytes(root / "gradle/release/product-signing-keys.json",
                reject_symlink_parents=True)),
            "keys": memoized_file_inventory(root / "gradle/release/keys"),
        }))

    admitted_authority = authority() if session is not None else None
    if session is not None:
        # Concrete capability + exact caller/key policy, only in this process
        # lifetime. No serialized success marker or cross-run authentication hit.
        pool = session.setdefault("completedNativeProjections", {})
        key = (completed, admitted_authority)
        if key in pool:
            cache, checkpoint, sources = pool[key]
            count("nativeProjectionProviderReuses")
        elif len(pool) < 4:
            pool[key] = cache, checkpoint, sources

    def signed_checkpoint():
        if not checkpoint:
            with tempfile.TemporaryDirectory(prefix="completed-native-signature-") as temporary:
                private = Path(temporary).resolve()
                transferred = _requalified_signed_checkpoint(spec, private, root, token)
                prefix = private / "signed/aggregate-input" / ("codex-agent-runtime-" + request["versions"]["runtime-release"])
                manifest = validate_runtime_aggregate(load_canonical_json_bytes(
                    read_regular_file_bytes(Path(str(prefix) + "-manifest.json"))))
                attestation = validate_runtime_aggregate_attestation(load_canonical_json_bytes(
                    read_regular_file_bytes(Path(str(prefix) + ".attestation.json"))))
                for row, signed in zip(manifest["variants"], attestation["variants"], strict=True):
                    if any(row[field] != signed[field] for field in row):
                        raise ValueError("Completed native aggregate and attestation variants differ")
                checkpoint.update(manifest=manifest, attestation=attestation)
                count("nativeProjectionSignedRangeBytes", transferred)
        return checkpoint

    def target_projection(value):
        target, original, projection = value
        identity = _native_contract_identity(projection, target)
        key = (target, original["receiptSha256"], canonical_json_bytes(identity))
        if key in cache:
            count("nativeProjectionMemoHits")
            return cache[key]
        signed = signed_checkpoint()
        if signed["manifest"]["contract"]["digest"] != identity["contractDigest"]:
            raise ValueError("Completed native aggregate differs from current Contract")
        variant, = [row for row in signed["attestation"]["variants"] if row["target"] == target]
        receipts = {}
        for phase in ("binary", "package", "validation", "metadata"):
            record = phases[PhaseInstanceId("runtime", target, phase, target)]
            envelope = completed.envelope(record)
            if envelope["receiptSha256"] != variant["phaseReceipts"][phase]:
                raise ValueError("Completed native signed phase differs from its original")
            receipts[phase] = envelope["receipt"]
        if canonical_json_bytes(receipts["validation"]) != original["receiptBytes"]:
            raise ValueError("Completed native projection changed its selected validation")
        contract, = [row["contractProjection"] for row in receipts["binary"]["inputs"]["upstreamArtifacts"]
                     if row["product"] == "contract" and "contractProjection" in row]
        if (contract["contractDigest"] != identity["contractDigest"] or
                {row["component"]: row["sha256"] for row in contract["componentDigests"]}.get(target) != identity["componentDigests"][target]):
            raise ValueError("Completed native original differs from current Contract components")
        if target == "macos-arm64":
            coverage, = [row["contractProjection"] for row in receipts["validation"]["inputs"]["upstreamArtifacts"]
                         if row["product"] == "contract" and "contractProjection" in row]
            if coverage.get("canonicalCoverageDigest") != identity["canonicalCoverageDigest"]:
                raise ValueError("Completed native bootstrap Contract coverage changed")
        source = sources[PhaseInstanceId("runtime", target, "metadata", target)]
        artifact, _, observed, workflow = products._authenticate_runtime_original_reference_source(
            plan, producer, source, trusted_workflow_sha=trusted_workflow_sha, token=token)
        name = f"product-validation / runtime-{target}-metadata-{target}"
        job, = products._matching_ci_jobs(observed[0]["jobs"], name)
        locator = products._runtime_original_locator(artifact, workflow, products._identity(source["receipt"]), job)
        inventory = {row["relativePath"]: row for row in completed.original_files(locator, receipts["metadata"])}
        evidence_target = next(name for name, value in PRODUCT_RUNTIME_TARGETS.items() if value == target)
        names = [f"outputs/c-abi/c-abi-package-{target}.json", f"outputs/native/desktop-runtime-{evidence_target}.json"]
        if target == "macos-arm64":
            names.append("outputs/c-abi-bootstrap/bootstrap-content.json")
        outputs = {row["relativePath"]: row for row in receipts["validation"]["outputs"]}
        prefix = f"inputs/predecessors/runtime-{target}-validation-{target}/stage/"
        with tempfile.TemporaryDirectory(prefix="completed-native-facts-") as temporary:
            stage = Path(temporary).resolve()
            with open_reference_archive(artifact, token) as (archive, stream):
                for name in names:
                    member = inventory.get(prefix + name)
                    output = outputs.get(name)
                    if (member is None or output is None or not 0 < member["bytes"] <= 16 * 1024**2
                            or any(member[field] != output[field] for field in ("bytes", "sha256"))):
                        raise ValueError("Completed native fact differs from its qualified original and receipt")
                    copy_reference_member(archive, prefix + name, stage / name, member)
                if stream is not None:
                    count("nativeProjectionOriginalRangeBytes", stream.transferred)
            content = canonical_json_bytes(_completed_native_content(
                target, receipts["validation"], identity, variant["componentId"], stage))
        cache[key] = VerifiedNativeRuntimeProjection(original["receiptBytes"], sha256_bytes(content),
            identity, _VERIFIED_NATIVE_RUNTIME, content)
        return cache[key]

    @measured
    def verify_completed_native_projection(instance, envelopes, projection):
        if session is not None:
            if _VERIFICATION_SESSION.get() is not session or authority() != admitted_authority:
                raise ValueError("Completed native projection outlived or changed its caller authority")
        dependencies = native_runtime_validation_dependencies(instance)
        if not dependencies or len(envelopes) != len(dependencies) or type(projection) is not VerifiedContractProjection:
            raise ValueError("Completed native projection requires exact SDK dependencies and Contract")
        for dependency, original in zip(dependencies, envelopes, strict=True):
            required = [PhaseInstanceId("runtime", dependency.target, phase, dependency.target)
                        for phase in ("binary", "package", "validation", "metadata")]
            if not all(identity in phases for identity in required):
                return None
            expected = completed.envelope(phases[dependency], original["receiptBytes"])
            if expected != original:
                raise ValueError("Completed native projection differs from the selected original")
        if not sources:
            sources.update((products._identity(row["receipt"]), row) for row in completed.runtime_sources())
        # Authenticate one shared checkpoint before parallel target reads; no
        # duplicate signature/original body work for the other SDK languages.
        signed_checkpoint()
        with products._ci_observation_batch():
            result = tuple(bounded_verify(target_projection,
                [(dependency.target, original, projection) for dependency, original in zip(dependencies, envelopes, strict=True)]))
        if session is not None and authority() != admitted_authority:
            raise ValueError("Completed native projection changed its caller authority during admission")
        return result
    return verify_completed_native_projection


def load_native_runtime_evidence(root: Path) -> list[dict]:
    records = load_canonical_json_bytes(read_regular_file_bytes(
        root / REQUEST_NAME, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
    decoded = _native_comparison_records(root, records)
    expected = {REQUEST_NAME}

    def tree(source):
        path = Path(source)
        expected.update((path / item["relativePath"]).relative_to(root).as_posix()
                        for item in regular_file_inventory(path))

    for contract, runtime in decoded.values():
        for value in (contract, runtime):
            for field in ("attestation", "attestationSignature", "publicKey", "keyring", "phaseReceipt", "payload"):
                if value.get(field) is not None:
                    expected.add(Path(value[field]).relative_to(root).as_posix())
            if value.get("keysDirectory") is not None:
                keys = Path(value["keysDirectory"])
                keyring = load_keyring(Path(value["keyring"]), keys)
                for key in ([keyring["activeKey"]] if keyring["activeKey"] else []) + keyring["retiredKeys"]:
                    expected.add(public_key_path(keys, key["keyId"]).relative_to(root).as_posix())
        tree(contract["stageRoot"])
        tree(Path(contract["attestation"]).parent / CONTRACT_EXECUTION_CLOSURE_DIRECTORY)
        for phase in ("package", "validation"):
            tree(Path(runtime["stageRoot"]) / runtime["target"] / phase)
        expected.update(Path(path).relative_to(root).as_posix() for path in runtime["phaseReceipts"].values())
    if expected != {item["relativePath"] for item in regular_file_inventory(root)}:
        raise ValueError("Native Runtime handoff contains missing or unexpected files")
    return records


def stage_native_runtime_evidence(records, source_root: Path, destination: Path, *,
                                  keyring: Path | None = None, keys_directory: Path | None = None) -> list[dict]:
    """Capture declared original bytes, verify the capture, then publish once.

    Path relocation is transport only. Original receipts and attestations are
    never rewritten, and no private signing key is copied. Reusing an existing
    handoff should rebase its records, not call this producer again.
    """
    decoded = _native_comparison_records(source_root, records)
    destination = Path(destination).absolute()
    for contract, runtime in decoded.values():
        for source in (Path(contract["stageRoot"]), Path(contract["attestation"]).parent,
                       Path(runtime["stageRoot"]), Path(runtime["attestation"]).parent):
            if destination == source or source in destination.parents or destination in source.parents:
                raise ValueError("Native evidence destination overlaps original inputs")
    with tempfile.TemporaryDirectory(prefix="native-runtime-inputs-") as temporary:
        root = Path(temporary).resolve() / "handoff"
        root.mkdir()
        relocated = []
        contracts = {}
        for digest, (contract, runtime) in decoded.items():
            if contract["expectedTrustDomain"] == "release":
                if keyring is None or keys_directory is None:
                    raise ValueError("Release native handoff requires a caller-pinned product keyring")
                pinned = {"keyring": str(keyring), "keysDirectory": str(keys_directory)}
                contract, runtime = {**contract, **pinned}, {**runtime, **pinned}
            prefix = Path("originals") / digest.removeprefix("sha256:")

            def file(value, relative):
                if value is None:
                    return None
                source = Path(value)
                path = relative / require_relative_path(source.name, "Native evidence basename")
                _copy_file(source, root / path, max_bytes=1024 * 1024 * 1024)
                return path.as_posix()

            def directory(value, relative):
                snapshot_regular_tree(Path(value), root / relative)
                return relative.as_posix()

            def trust(value, relative):
                result = {name: file(value[name], relative / name) for name in
                          ("attestation", "attestationSignature", "publicKey", "keyring")}
                result["keysDirectory"] = None
                if value["keysDirectory"] is not None:
                    keys = Path(value["keysDirectory"])
                    keyring = load_keyring(root / result["keyring"], keys)
                    path = relative / "keysDirectory"
                    (root / path).mkdir(parents=True)
                    for key in ([keyring["activeKey"]] if keyring["activeKey"] else []) + keyring["retiredKeys"]:
                        _copy_file(public_key_path(keys, key["keyId"]), root / path / f"{key['keyId']}.pub")
                    result["keysDirectory"] = path.as_posix()
                return result

            kroot, rroot = prefix / "contract", prefix / "runtime"
            contract_key = canonical_json_bytes(contract)
            if contract_key not in contracts:
                captured_contract = {
                    **trust(contract, kroot),
                    "stageRoot": directory(contract["stageRoot"], kroot / "stage"),
                    "phaseReceipt": file(contract["phaseReceipt"], kroot / "receipt"),
                    "expectedTrustDomain": contract["expectedTrustDomain"],
                }
                closure = CONTRACT_EXECUTION_CLOSURE_DIRECTORY
                directory(Path(contract["attestation"]).parent / closure,
                          Path(captured_contract["attestation"]).parent / closure)
                contracts[contract_key] = captured_contract
            captured_contract = contracts[contract_key]
            stage = rroot / "stages"
            for phase in ("package", "validation"):
                directory(Path(runtime["stageRoot"]) / runtime["target"] / phase,
                          stage / runtime["target"] / phase)
            captured_runtime = {
                **trust(runtime, rroot), "target": runtime["target"], "stageRoot": stage.as_posix(),
                "payload": file(runtime["payload"], rroot / "payload"),
                "phaseReceipts": {phase: file(path, rroot / "receipts" / phase)
                                  for phase, path in runtime["phaseReceipts"].items()},
            }
            relocated.append({"receiptSha256": digest, "contractEvidence": captured_contract,
                              "runtimeEvidence": captured_runtime})
        provider = _native_comparison_provider(root, relocated, keyring=keyring, keys_directory=keys_directory)
        for record in relocated:
            # This authenticates complete original K/R content. Indexed-object
            # admission separately checks the selected original carrier object.
            provider({"receiptSha256": record["receiptSha256"],
                      "target": record["runtimeEvidence"]["target"]}, None).output_inventory(
                record["receiptSha256"], load_canonical_json_bytes(read_regular_file_bytes(
                    root / record["runtimeEvidence"]["phaseReceipts"]["validation"],
                    max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))["outputs"])
        (root / REQUEST_NAME).write_bytes(canonical_json_bytes(relocated))
        publish_regular_tree(root, destination)
    return relocated


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--keyring", type=Path)
    parser.add_argument("--keys-directory", type=Path)
    args = parser.parse_args(argv)
    try:
        records = load_canonical_json_bytes(read_regular_file_bytes(
            args.request, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
        stage_native_runtime_evidence(records, args.source_root, args.output,
                                      keyring=args.keyring, keys_directory=args.keys_directory)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
