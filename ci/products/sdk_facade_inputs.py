"""Authenticate existing Core inputs and prepare an artifact-only Maven union.

This reuses package/source/Contract gates, not source publications. It is a
prerequisite, NOT facade admission: the existing Kotlin facade publication
verifier must additionally check dependency semantics before compilation and
again during original admission. Consumer template/init-script and hosted
execution authentication also remain the outer caller's responsibility.
"""

import argparse
import os
from pathlib import Path
import tempfile

from .contract import verify_contract_bundle
from .contract_attestation import CONTRACT_EXECUTION_CLOSURE_DIRECTORY
from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, require_exact_keys, require_semver, require_string,
    snapshot_regular_tree, verified_zip_contents, write_canonical_json,
)
from .plan import _contract_projection_from_request
from .receipt import output_inventory_digest, validate_phase_receipt
from .registry import PhaseInstanceId, SDK_FACADE_CONTRACT_COMPONENTS, SDK_FACADE_TARGETS
from .sdk_compatibility import load_sdk_compatibility_request
from .sdk_facade_validation import _inventory, verify_facade_consumer_evidence
from .sdk_inputs import COMPATIBILITY_NAME, REQUEST_NAME, stage_sdk_inputs
from .sdk_maven import MAVEN_GROUPS
from .sdk_package import _require_capability_output_separate, verify_sdk_package_inputs
from .sdk_validation_inputs import _request_inventory


OUTPUT_KIND = "sdk-facade-validation-content"
OUTPUT_PATH = "outputs/validation/facade-validation.json"
_LIMIT = 16 * 1024 * 1024
_PATH_FIELDS = ("packageStage", "packageReceipt", "binaryStage", "binaryReceipt", "compatibilityRequest")
_EVIDENCE_FIELDS = {"stageRoot", "phaseReceipt", "attestation", "attestationSignature", "publicKey",
                    "expectedTrustDomain", "keyring", "keysDirectory"}


def _read(path):
    return read_regular_file_bytes(Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)


def _path(value, label):
    path = Path(require_string(value, label))
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError(f"{label} must be an existing normalized non-symbolic absolute path")
    return path


def _request(path):
    raw = _read(path)
    value = require_exact_keys(load_canonical_json_bytes(raw), {
        "target", "sdkVersion", "runtimeVersion", "contractVersion", "repository", *_PATH_FIELDS,
        "binaryContractEvidence", "validationContractEvidence",
    }, "Facade input request")
    if type(value["target"]) is not str or value["target"] not in SDK_FACADE_TARGETS:
        raise ValueError("Facade input target is unsupported")
    for field in ("sdkVersion", "runtimeVersion", "contractVersion"):
        require_semver(value[field], field)
    for field in ("repository", *_PATH_FIELDS):
        _path(value[field], field)
    for field in ("binaryContractEvidence", "validationContractEvidence"):
        evidence = require_exact_keys(value[field], _EVIDENCE_FIELDS, field)
        if evidence["expectedTrustDomain"] not in ("development", "release"):
            raise ValueError("Facade Contract trust domain is invalid")
        if (evidence["keyring"] is None) != (evidence["keysDirectory"] is None):
            raise ValueError("Facade Contract keyring and directory must be paired")
        for name in _EVIDENCE_FIELDS - {"expectedTrustDomain"}:
            if evidence[name] is not None:
                _path(evidence[name], f"{field}.{name}")
            elif name not in {"keyring", "keysDirectory"}:
                raise ValueError("Facade Contract evidence is missing a required path")
    return value, raw


def _fresh(destination, sources):
    destination = Path(destination).absolute()
    if destination.resolve(strict=False) != destination or destination.exists() or destination.is_symlink():
        raise ValueError("Facade destination must be fresh, normalized and non-symbolic")
    _require_capability_output_separate(destination, sources)
    return destination


def _sources(value):
    originals = {field: Path(value[field]) for field in _PATH_FIELDS}
    trees = {field: originals[field] for field in ("packageStage", "binaryStage")}
    files = {field: originals[field] for field in ("packageReceipt", "binaryReceipt", "compatibilityRequest")}
    for label in ("binaryContractEvidence", "validationContractEvidence"):
        evidence = value[label]
        trees[label + "/stageRoot"] = Path(evidence["stageRoot"])
        trees[label + "/closure"] = Path(evidence["attestation"]).parent / CONTRACT_EXECUTION_CLOSURE_DIRECTORY
        if evidence["keysDirectory"] is not None:
            trees[label + "/keysDirectory"] = Path(evidence["keysDirectory"])
        for field in ("phaseReceipt", "attestation", "attestationSignature", "publicKey", "keyring"):
            if evidence[field] is not None:
                files[label + "/" + field] = Path(evidence[field])
    return originals, trees, files


def prepare_facade_validation_inputs(request: Path, destination: Path) -> dict:
    """Prepare exact admitted input bytes; no consumer or dependency proof minted.

    The canonical request is explicit caller policy, not downloaded authority.
    Both original binary Contract and separately selected validation Contract
    evidence use the existing eight-field authenticated projection interface.
    A different selected Contract producer is allowed only with the same pinned
    version and target resolution component as the package's authenticated one.
    """
    request = Path(request).absolute()
    value, request_bytes = _request(request)
    originals, trees, files = _sources(value)
    # Capture originals before any authentication or snapshotting callback.
    tree_before = {name: _inventory(path, allow_empty=True) for name, path in trees.items()}
    file_before = {name: _read(path) for name, path in files.items()}
    for field, phase in (("packageReceipt", "package"), ("binaryReceipt", "binary")):
        receipt = validate_phase_receipt(load_canonical_json_bytes(file_before[field]))
        if tuple(receipt[key] for key in ("product", "component", "phase", "target", "productVersion")) != \
                ("sdk", "sdk-core", phase, "common", value["sdkVersion"]):
            raise ValueError("Facade input requires its exact original Core package and binary receipts")
    request_inventory = _request_inventory(originals["compatibilityRequest"])
    destination = _fresh(destination, [request, *trees.values(), *files.values(), *request_inventory])

    def unchanged():
        if (_read(request) != request_bytes or
                any(_inventory(path, allow_empty=True) != tree_before[name] for name, path in trees.items()) or
                any(_read(path) != file_before[name] for name, path in files.items()) or
                _request_inventory(originals["compatibilityRequest"]) != request_inventory):
            raise ValueError("Facade original inputs changed during preparation")

    with tempfile.TemporaryDirectory(prefix="facade-inputs-") as temporary:
        private = Path(temporary).resolve()
        captured = {}
        for name, source in trees.items():
            target = private / "trees" / name
            snapshot_regular_tree(source, target)
            captured[name] = target
        for name, raw in file_before.items():
            target = private / "files" / name / files[name].name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            captured[name] = target
        # Keep each original closure beside its unchanged attestation bytes.
        for label in ("binaryContractEvidence", "validationContractEvidence"):
            snapshot_regular_tree(captured[label + "/closure"],
                captured[label + "/attestation"].parent / CONTRACT_EXECUTION_CLOSURE_DIRECTORY)
        captured_before = _inventory(private, allow_empty=True)

        def captured_unchanged():
            # Only the captured originals, not newly generated output/work trees.
            actual = [*({**row, "relativePath": "trees/" + row["relativePath"]}
                        for row in _inventory(private / "trees", allow_empty=True)),
                      *({**row, "relativePath": "files/" + row["relativePath"]}
                        for row in _inventory(private / "files", allow_empty=True))]
            if sorted(actual, key=lambda row: row["relativePath"]) != captured_before:
                raise ValueError("Facade private inputs changed during preparation")

        def evidence(label):
            return {field: (value[label][field] if field == "expectedTrustDomain" or value[label][field] is None
                            else str(captured[label + "/" + field])) for field in _EVIDENCE_FIELDS}

        try:
            unchanged()
            staged = private / "compatibility"
            stage_sdk_inputs(captured["compatibilityRequest"], staged,
                             request_directory=originals["compatibilityRequest"].parent)
            staged_before = _inventory(staged, allow_empty=True)
            arguments = load_sdk_compatibility_request(staged / REQUEST_NAME)
            compatibility = load_canonical_json_bytes(_read(staged / COMPATIBILITY_NAME))
            aggregate = load_canonical_json_bytes(_read(arguments["runtime_manifest"]))
            if (compatibility["sdkVersion"] != value["sdkVersion"]
                    or compatibility["contract"]["version"] != value["contractVersion"]
                    or aggregate["runtimeVersion"] != value["runtimeVersion"]
                    or any(value[label]["expectedTrustDomain"] != arguments["required_trust_domain"]
                           for label in ("binaryContractEvidence", "validationContractEvidence"))):
                raise ValueError("Facade requested versions or trust differ from authenticated package inputs")
            package, package_bytes = verify_sdk_package_inputs(
                Path(value["repository"]), captured["packageStage"], captured["packageReceipt"], staged / REQUEST_NAME,
                binary_stage_root=captured["binaryStage"], binary_receipt_path=captured["binaryReceipt"],
                binary_contract_evidence=evidence("binaryContractEvidence"))
            if (package_bytes != file_before["packageReceipt"]
                    or canonical_json_bytes(package) != package_bytes
                    or (package["product"], package["component"], package["phase"], package["target"], package["productVersion"]) !=
                    ("sdk", "sdk-core", "package", "common", value["sdkVersion"])):
                raise ValueError("Facade package differs from its exact original receipt")
            versions = {"sdk": value["sdkVersion"], "contract": value["contractVersion"],
                        "runtime-release": value["runtimeVersion"],
                        "runtime-compatibility": aggregate["runtimeCompatibilityVersion"]}
            projection = _contract_projection_from_request(
                PhaseInstanceId("sdk", "sdk-core", "validation", value["target"]), versions,
                evidence("validationContractEvidence")).receipt_value()
            selected_stage = captured["validationContractEvidence/stageRoot"]
            selected_payload = selected_stage / projection["bundlePath"]
            selected_manifest = verify_contract_bundle(selected_payload)
            package_manifest = verify_contract_bundle(arguments["contract_payload"])
            component = SDK_FACADE_CONTRACT_COMPONENTS[value["target"]]
            if (selected_manifest["contractVersion"] != package_manifest["contractVersion"]
                    or selected_manifest["contractDigest"] != package_manifest["contractDigest"]
                    or selected_manifest["components"][component]["sha256"] !=
                    package_manifest["components"][component]["sha256"]):
                raise ValueError("Facade selected Contract differs from package dependency version or target component")
            # Existing signed closure proves these Maven bytes came from original
            # Contract binary. No independent Maven parser or source publication.
            records, members, _ = verified_zip_contents(selected_payload, canonical_stored=True,
                max_archive_bytes=512 * 1024 * 1024, max_total_bytes=1024 * 1024 * 1024, max_members=4096)
            output = private / "prepared"
            snapshot_regular_tree(captured["packageStage"], output / "package-stage")
            snapshot_regular_tree(selected_stage, output / "contract-stage")
            maven = output / "maven-repository"
            snapshot_regular_tree(captured["packageStage"] / "outputs/maven", maven)
            maven_paths = {row["relativePath"] for row in records if row["relativePath"].startswith("maven/")}
            if not maven_paths:
                raise ValueError("Facade selected Contract Maven closure is empty")
            for name in sorted(maven_paths):
                target = maven / name.removeprefix("maven/")
                if target.exists() or target.is_symlink():
                    raise ValueError("Facade package and Contract Maven paths overlap")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(members[name])
            inventory = _inventory(maven)
            write_canonical_json(output / "maven-inventory.json", {
                "schemaVersion": 1, "groupId": MAVEN_GROUPS["sdk-core"], "version": value["sdkVersion"],
                "target": "sdk-facade", "files": [{"fileName": row["relativePath"], "bytes": row["bytes"],
                    "sha256": row["sha256"].removeprefix("sha256:")} for row in inventory]})
            info = {"target": value["target"], "sdkVersion": value["sdkVersion"],
                "runtimeVersion": value["runtimeVersion"], "contractVersion": value["contractVersion"],
                "packageOutputsDigest": output_inventory_digest(package["outputs"]),
                "contractProjection": projection, "inventories": {
                    "package": _inventory(output / "package-stage"),
                    "contract": _inventory(output / "contract-stage"), "repository": inventory}}
            write_canonical_json(output / "inputs.json", info)
            if _inventory(staged, allow_empty=True) != staged_before:
                raise ValueError("Facade private compatibility inputs changed during preparation")
            captured_unchanged()
            unchanged()
        finally:
            captured_unchanged()
            unchanged()
        _fresh(destination, [request, *trees.values(), *files.values(), *request_inventory])
        publish_regular_tree(output, destination)
        return info


def write_facade_validation_content(*, request: Path, inputs: Path, evidence: Path,
                                    gradle_wrapper: str, consumer_directory: str, output: Path) -> dict:
    """Reauthenticate explicit originals, compare prepared bytes, project raw capture.

    inputs.json is NOT authority. The complete preparation gate runs again and
    must reproduce the entire supplied prepared tree before it is consumed.
    Facade dependency/host/source admission remains external as documented above.
    """
    request, inputs, evidence = Path(request).absolute(), Path(inputs).absolute(), Path(evidence).absolute()
    request_bytes = _read(request)
    before = {"inputs": _inventory(inputs, allow_empty=True), "evidence": _inventory(evidence, allow_empty=True)}
    value, _ = _request(request)
    originals, trees, files = _sources(value)
    tree_before = {name: _inventory(path, allow_empty=True) for name, path in trees.items()}
    file_before = {name: _read(path) for name, path in files.items()}
    request_files = _request_inventory(originals["compatibilityRequest"])
    sources = [request, inputs, evidence, *trees.values(), *files.values(), *request_files]
    output = _fresh(output, sources)

    def unchanged():
        if (_read(request) != request_bytes or _inventory(inputs, allow_empty=True) != before["inputs"]
                or _inventory(evidence, allow_empty=True) != before["evidence"]
                or any(_inventory(path, allow_empty=True) != tree_before[name] for name, path in trees.items())
                or any(_read(path) != file_before[name] for name, path in files.items())
                or _request_inventory(originals["compatibilityRequest"]) != request_files):
            raise ValueError("Facade prepared inputs or execution evidence changed during projection")

    try:
        with tempfile.TemporaryDirectory(prefix="facade-content-") as temporary:
            regenerated = Path(temporary).resolve() / "inputs"
            info = prepare_facade_validation_inputs(request, regenerated)
            if _inventory(regenerated, allow_empty=True) != before["inputs"]:
                raise ValueError("Facade prepared inputs differ from independently reauthenticated originals")
            content = verify_facade_consumer_evidence(evidence_directory=evidence, target=info["target"],
                sdk_version=info["sdkVersion"], runtime_version=info["runtimeVersion"], contract_version=info["contractVersion"],
                package_stage=inputs / "package-stage", contract_stage=inputs / "contract-stage",
                imported_repository=inputs / "maven-repository",
                expected_package_inventory=info["inventories"]["package"],
                expected_contract_inventory=info["inventories"]["contract"],
                expected_repository_inventory=info["inventories"]["repository"],
                expected_contract_projection=info["contractProjection"], original_context={
                    "gradleWrapper": gradle_wrapper, "consumerDirectory": consumer_directory,
                    "repositoryDirectory": str(inputs / "maven-repository"),
                    "outcomeInitScript": str(Path(consumer_directory) / ".codex-consumer-task-outcomes.init.gradle.kts"),
                    "environment": {}})
            unchanged()
    finally:
        unchanged()
    _fresh(output, sources)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".facade-content-", dir=output.parent) as temporary:
        staged = Path(temporary) / "content.json"
        write_canonical_json(staged, content)
        unchanged()
        _fresh(output, sources)
        os.link(staged, output, follow_symlinks=False)
    return content


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    prepare = modes.add_parser("prepare")
    prepare.add_argument("--request", type=Path, required=True)
    prepare.add_argument("--destination", type=Path, required=True)
    content = modes.add_parser("content")
    for name in ("request", "inputs", "evidence", "output"):
        content.add_argument("--" + name, type=Path, required=True)
    for name in ("gradle-wrapper", "consumer-directory"):
        content.add_argument("--" + name, required=True)
    arguments = vars(parser.parse_args(argv))
    mode = arguments.pop("mode")
    try:
        if mode == "prepare": prepare_facade_validation_inputs(**arguments)
        else: write_facade_validation_content(**arguments)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
