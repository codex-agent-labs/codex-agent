"""Produce deterministic Android validation content after every original gate.

This module stages content only.  It does not create a phase receipt or grant
worker, Firebase, source, tool, signature, or reuse authority.  The caller owns
the producer/source policy passed to the existing complete gates.
"""

import os
from pathlib import Path
import re
import tempfile

from .contract_attestation import CONTRACT_EXECUTION_CLOSURE_DIRECTORY
from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, load_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_integer, sha256_bytes, write_canonical_json,
)
from .receipt import (
    output_inventory_digest, validate_phase_receipt, validate_producer,
    write_output_manifest,
)
from .sdk_android_validation_admission import verify_sdk_android_validation_original_content
from .sdk_android_validation_content import android_validation_content
from .sdk_maven import COMPONENT_CARRIERS, MAVEN_GROUPS
from .sdk_package import _require_capability_output_separate, verify_sdk_package_inputs
from .sdk_validation_inputs import _request_inventory
from .signing_isolation import require_no_signing_secret


OUTPUT_KIND = "android-validation-content"
OUTPUT_PATH = "outputs/validation/android-validation.json"
_VERIFICATION_PATH = (
    "original/payload/external/android-runtime-evidence/"
    "firebase-android-runtime-verification.json"
)
_CONTRACT_KEYS = {
    "stageRoot", "phaseReceipt", "attestation", "attestationSignature",
    "publicKey", "expectedTrustDomain", "keyring", "keysDirectory",
}
_VERIFICATION_KEYS = {
    "schemaVersion", "result", "evidenceSha256", "firebaseMatrixSha256",
    "testReportSha256", "applicationApkSha256", "testApkSha256",
    "releaseAarSha256", "bundledRuntimeSha256",
}
_RAW_SHA256 = re.compile(r"[0-9a-f]{64}")


def _read(path: Path, *, maximum: int = 16 * 1024 * 1024) -> bytes:
    return read_regular_file_bytes(
        Path(path), max_bytes=maximum, reject_symlink_parents=True)


def _contract_sources(evidence):
    evidence = require_exact_keys(evidence, _CONTRACT_KEYS, "Android binary Contract evidence")
    if (evidence["keyring"] is None) != (evidence["keysDirectory"] is None):
        raise ValueError("Android binary Contract keyring and keys directory must be paired")
    files = {
        "contract/" + name: Path(evidence[name])
        for name in ("phaseReceipt", "attestation", "attestationSignature", "publicKey")
    }
    trees = {
        "contract/stage": Path(evidence["stageRoot"]),
        "contract/closure": Path(evidence["attestation"]).parent /
            CONTRACT_EXECUTION_CLOSURE_DIRECTORY,
    }
    if evidence["keyring"] is not None:
        files["contract/keyring"] = Path(evidence["keyring"])
        trees["contract/keys"] = Path(evidence["keysDirectory"])
    return trees, files


def _verification_record(final_capture: Path) -> dict:
    value = require_exact_keys(load_json_bytes(_read(
        final_capture / _VERIFICATION_PATH)), _VERIFICATION_KEYS,
        "Android Firebase verification record")
    if (require_integer(value["schemaVersion"], "Android Firebase verification schema") != 1
            or value["result"] != "passed"):
        raise ValueError("Android Firebase verification record identity is invalid")
    for field in _VERIFICATION_KEYS - {"schemaVersion", "result"}:
        if type(value[field]) is not str or _RAW_SHA256.fullmatch(value[field]) is None:
            raise ValueError(f"Android Firebase verification {field} is not a raw SHA-256 digest")
    return value


def produce_sdk_android_validation_phase(
    *, repository: Path, package_stage: Path, package_receipt: Path,
    binary_stage: Path, binary_receipt: Path, compatibility_request: Path,
    binary_contract_evidence: dict, final_capture: Path, protected_capture: Path,
    expected_capture_producer: dict, expected_original_producer: dict,
    trusted_source_commit: str, trusted_source_tree: str,
    tooling_evidence: Path, tooling_public_key: Path, java_executable: Path,
    apkanalyzer_executable: Path, policy_revision: str,
    required_trust_domain: str, destination: Path,
    tooling_keyring: Path | None = None,
    tooling_keys_directory: Path | None = None,
) -> dict:
    """Run existing full gates and publish only a deterministic output stage."""
    require_no_signing_secret(os.environ)
    repository = Path(repository).resolve(strict=True)
    trees = {
        "package": Path(package_stage).absolute(),
        "binary": Path(binary_stage).absolute(),
        "final": Path(final_capture).absolute(),
        "protected": Path(protected_capture).absolute(),
        "tooling": Path(tooling_evidence).absolute(),
    }
    files = {
        "packageReceipt": Path(package_receipt).absolute(),
        "binaryReceipt": Path(binary_receipt).absolute(),
        "compatibilityRequest": Path(compatibility_request).absolute(),
        "toolingPublicKey": Path(tooling_public_key).absolute(),
        "javaExecutable": Path(java_executable).absolute(),
        "apkanalyzerExecutable": Path(apkanalyzer_executable).absolute(),
    }
    contract_trees, contract_files = _contract_sources(binary_contract_evidence)
    trees.update(contract_trees)
    files.update(contract_files)
    if tooling_keyring is not None:
        files["toolingKeyring"] = Path(tooling_keyring).absolute()
    if tooling_keys_directory is not None:
        trees["toolingKeys"] = Path(tooling_keys_directory).absolute()
    if (tooling_keyring is None) != (tooling_keys_directory is None):
        raise ValueError("Android tooling keyring and keys directory must be paired")

    destination = Path(destination).absolute()
    sources = [*trees.values(), *files.values()]
    if (destination.resolve(strict=False) != destination or destination.exists()
            or destination.is_symlink()):
        raise ValueError("Android validation destination must be fresh and normalized")
    _require_capability_output_separate(destination, sources)

    tree_before = {
        name: regular_file_inventory(path, allow_empty=True)
        for name, path in trees.items()
    }
    file_before = {name: _read(path, maximum=512 * 1024 * 1024)
                   for name, path in files.items()}
    request_before = _request_inventory(files["compatibilityRequest"])
    policy_before = canonical_json_bytes({
        "binaryContractEvidence": binary_contract_evidence,
        "captureProducer": expected_capture_producer,
        "originalProducer": expected_original_producer,
        "trustedSourceCommit": trusted_source_commit,
        "trustedSourceTree": trusted_source_tree,
        "policyRevision": policy_revision,
        "requiredTrustDomain": required_trust_domain,
    })
    package = validate_phase_receipt(load_canonical_json_bytes(file_before["packageReceipt"]))
    binary = validate_phase_receipt(load_canonical_json_bytes(file_before["binaryReceipt"]))
    expected_original = validate_producer(expected_original_producer, "Android original producer")
    if ((package["product"], package["component"], package["phase"], package["target"])
            != ("sdk", "sdk-android", "package", "android")
            or (binary["product"], binary["component"], binary["phase"], binary["target"])
            != ("sdk", "sdk-android", "binary", "android")
            or package["productVersion"] != binary["productVersion"]
            or binary["producer"] != expected_original):
        raise ValueError("Android validation requires its exact package/binary identity and original producer")

    artifact, (extension, _) = next(iter(COMPONENT_CARRIERS["sdk-android"].items()))
    if len(COMPONENT_CARRIERS["sdk-android"]) != 1 or extension != "aar":
        raise ValueError("Android validation requires the fixed single AAR binary carrier")
    version = package["productVersion"]
    original_aar = (trees["binary"] / "outputs/maven" /
        Path(*MAVEN_GROUPS["sdk-android"].split(".")) / artifact / version /
        f"{artifact}-{version}.aar")
    aar_bytes = _read(original_aar, maximum=512 * 1024 * 1024)
    if not aar_bytes:
        raise ValueError("Android validation binary AAR is empty")

    def unchanged():
        require_no_signing_secret(os.environ)
        if (canonical_json_bytes({
                "binaryContractEvidence": binary_contract_evidence,
                "captureProducer": expected_capture_producer,
                "originalProducer": expected_original_producer,
                "trustedSourceCommit": trusted_source_commit,
                "trustedSourceTree": trusted_source_tree,
                "policyRevision": policy_revision,
                "requiredTrustDomain": required_trust_domain,
            }) != policy_before
                or any(regular_file_inventory(path, allow_empty=True) != tree_before[name]
                       for name, path in trees.items())
                or any(_read(path, maximum=512 * 1024 * 1024) != file_before[name]
                       for name, path in files.items())
                or _request_inventory(files["compatibilityRequest"]) != request_before
                or _read(original_aar, maximum=512 * 1024 * 1024) != aar_bytes):
            raise ValueError("Android validation original inputs or caller policy changed")

    try:
        verified, verified_bytes = verify_sdk_package_inputs(
            repository, trees["package"], files["packageReceipt"],
            files["compatibilityRequest"], binary_stage_root=trees["binary"],
            binary_receipt_path=files["binaryReceipt"],
            binary_contract_evidence=binary_contract_evidence,
        )
        if verified != package or verified_bytes != file_before["packageReceipt"]:
            raise ValueError("Android package gate returned a different original receipt")
        unchanged()
        with tempfile.TemporaryDirectory(prefix="sdk-android-validation-phase-") as temporary:
            private = Path(temporary).resolve()
            private_aar = private / "codex-agent-runtime-android-release.aar"
            private_aar.write_bytes(aar_bytes)
            verify_sdk_android_validation_original_content(
                final_capture=trees["final"], protected_capture=trees["protected"],
                expected_binary_aar=private_aar,
                expected_capture_producer=expected_capture_producer,
                expected_original_producer=expected_original_producer,
                trusted_source_commit=trusted_source_commit,
                trusted_source_tree=trusted_source_tree, repository=repository,
                tooling_evidence=trees["tooling"],
                tooling_public_key=files["toolingPublicKey"],
                java_executable=files["javaExecutable"],
                apkanalyzer_executable=files["apkanalyzerExecutable"],
                policy_revision=policy_revision,
                required_trust_domain=required_trust_domain,
                tooling_keyring=tooling_keyring,
                tooling_keys_directory=tooling_keys_directory,
            )
            if _read(private_aar, maximum=512 * 1024 * 1024) != aar_bytes:
                raise ValueError("Android validation private AAR changed during the full gate")
            record = _verification_record(trees["final"])
            release_digest = sha256_bytes(aar_bytes)
            if record["releaseAarSha256"] != release_digest.removeprefix("sha256:"):
                raise ValueError("Android Firebase verification differs from the exact binary AAR")
            content = android_validation_content(
                sdk_version=version,
                package_outputs_digest=output_inventory_digest(package["outputs"]),
                release_aar_sha256=release_digest,
                bundled_runtime_sha256="sha256:" + record["bundledRuntimeSha256"],
            )
            staged = private / "stage"
            output = staged / OUTPUT_PATH
            output.parent.mkdir(parents=True)
            write_canonical_json(output, content)
            manifest = write_output_manifest(
                staged, "sdk", "sdk-android", "validation", "android", version,
                {OUTPUT_KIND: "outputs/validation"},
                expected_output_paths=[OUTPUT_PATH],
            )
            unchanged()
            if destination.exists() or destination.is_symlink():
                raise ValueError("Android validation destination must remain fresh")
            publish_regular_tree(staged, destination)
        unchanged()
        return manifest
    finally:
        unchanged()
