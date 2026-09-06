"""Receipt-bound SDK comparison proof from the authenticated full tooling gate."""

import os
from pathlib import Path
import subprocess
import tempfile

from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes, regular_file_inventory,
    require_exact_keys, require_integer, require_sha256, sha256_bytes, snapshot_regular_tree,
)
from .receipt import output_inventory_digest, validate_phase_receipt, verify_output_manifest_identity
from .registry import NATIVE_BINDINGS, NATIVE_TARGETS


_VERIFIED = object()
_IDENTITY = ("product", "component", "phase", "target", "productVersion", "buildKey")
_LIMIT = 16 * 1024 * 1024


class VerifiedSdkValidationProjection:
    """Comparison only; original producer/receipt/signing bytes stay external."""

    __slots__ = ("_receipt", "_content", "_verified")

    def __init__(self, receipt: bytes, content: bytes, verified: object):
        if verified is not _VERIFIED:
            raise TypeError("SDK validation projection requires the authenticated full verifier")
        self._receipt, self._content, self._verified = receipt, content, verified

    def output_inventory(self, receipt_sha256, outputs, *, identity=None):
        receipt = load_canonical_json_bytes(self._receipt)
        if (self._verified is not _VERIFIED or receipt_sha256 != sha256_bytes(self._receipt)
                or outputs != receipt["outputs"] or identity is None
                or any(identity.get(field) != receipt[field] for field in _IDENTITY)):
            raise ValueError("SDK comparison differs from its exact original receipt/identity/outputs")
        return [{"kind": "sdk-native-validation-content", "relativePath": "outputs/sdk-native-validation-content.json",
                 "bytes": len(self._content), "sha256": sha256_bytes(self._content)}]

    def receipt_value(self, receipt, package_receipt):
        self.output_inventory(sha256_bytes(canonical_json_bytes(receipt)), receipt["outputs"], identity=receipt)
        content = load_canonical_json_bytes(self._content)
        if (tuple(package_receipt.get(field) for field in _IDENTITY[:4]) !=
                ("sdk", receipt["component"], "package", "desktop")
                or package_receipt["productVersion"] != content["sdkVersion"]
                or output_inventory_digest(package_receipt["outputs"]) != content["packageOutputsDigest"]):
            raise ValueError("SDK validation projection belongs to another metadata package")
        return {"schemaVersion": 1, "kind": "sdk-native-validation-content",
                "sha256": sha256_bytes(self._content), "receiptSha256": sha256_bytes(self._receipt)}


def verify_sdk_validation_projection(
    *, repository: Path, component: str, target: str, package_stage: Path, package_receipt: Path,
    compatibility_request: Path, runtime_stages: Path, staged_sdks: Path,
    validation_stage: Path, validation_receipt: Path, tooling_evidence: Path, tooling_public_key: Path,
    java_executable: Path, policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
) -> VerifiedSdkValidationProjection:
    """Only the existing fixed full matcher can mint this same-snapshot proof.

    Java and the applicable Git policy are trusted invocation/toolchain inputs,
    not fields selected by an imported product record. No arbitrary command,
    success callback, content file or digest can bypass executable admission.
    """
    from .tooling import verified_tooling_capture
    if component not in NATIVE_BINDINGS or target not in NATIVE_TARGETS:
        raise ValueError("SDK comparison requires an exact native language/host")
    java_executable = Path(java_executable)
    if not java_executable.is_absolute() or java_executable.name not in {"java", "java.exe"}:
        raise ValueError("SDK comparison requires an explicit trusted Java executable")
    java_bytes = read_regular_file_bytes(java_executable, max_bytes=128 * 1024 * 1024, reject_symlink_parents=True)
    stages = {"package": Path(package_stage), "validation": Path(validation_stage)}
    receipt_paths = {"package": Path(package_receipt), "validation": Path(validation_receipt)}
    before = {phase: regular_file_inventory(path) for phase, path in stages.items()}
    originals = {phase: read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True)
                 for phase, path in receipt_paths.items()}
    receipts = {phase: validate_phase_receipt(load_canonical_json_bytes(raw)) for phase, raw in originals.items()}
    if receipts["package"]["productVersion"] != receipts["validation"]["productVersion"]:
        raise ValueError("SDK validation and package versions differ")
    with tempfile.TemporaryDirectory(prefix="sdk-validation-proof-") as temporary:
        root = Path(temporary).resolve()
        captured = {}
        for phase, source in stages.items():
            stage = root / phase
            snapshot_regular_tree(source, stage)
            if regular_file_inventory(stage) != before[phase]:
                raise ValueError("SDK original stage changed during capture")
            expected_target = "desktop" if phase == "package" else target
            receipt = receipts[phase]
            if tuple(receipt[field] for field in _IDENTITY[:4]) != ("sdk", component, phase, expected_target):
                raise ValueError("SDK original receipt differs from requested language/host/phase")
            manifest = verify_output_manifest_identity(stage, "sdk", component, phase,
                                                       expected_target, receipt["productVersion"])
            if manifest["outputs"] != receipt["outputs"]:
                raise ValueError("SDK original receipt differs from captured stage outputs")
            captured[phase] = root / f"{phase}-receipt.json"
            captured[phase].write_bytes(originals[phase])
        output = root / "content.json"
        with verified_tooling_capture(tooling_evidence, repository, tooling_public_key,
                required_trust_domain=required_trust_domain, keyring=tooling_keyring,
                keys_directory=tooling_keys_directory, policy_revision=policy_revision) as jar:
            arguments = {"repository": repository, "language": component, "target": target,
                "package-stage": root / "package", "package-receipt": captured["package"],
                "compatibility-request": compatibility_request, "runtime-stages": runtime_stages,
                "staged-sdks": staged_sdks, "validation-stage": root / "validation",
                "validation-receipt": captured["validation"], "content-output": output}
            command = [str(java_executable), "-jar", str(jar), "write-native-wrapper-validation-content"]
            command += [part for key, value in arguments.items() for part in (f"--{key}", str(value))]
            environment = {key: value for key, value in os.environ.items()
                           if key in {"PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL"}}
            subprocess.run(command, cwd=root, env=environment, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        content = read_regular_file_bytes(output, max_bytes=_LIMIT, reject_symlink_parents=True)
        value = require_exact_keys(load_canonical_json_bytes(content),
            {"schemaVersion", "kind", "component", "target", "sdkVersion", "packageOutputsDigest",
             "contractDigest", "canonicalApiDigest", "canonicalCoverageDigest", "files", "packageNegativeCases"},
            "verified SDK validation content")
        if (require_integer(value["schemaVersion"], "SDK content schema", 1) != 2
                or value["kind"] != "sdk-native-validation-content" or value["component"] != component
                or value["target"] != target or value["sdkVersion"] != receipts["package"]["productVersion"]
                or value["packageOutputsDigest"] != output_inventory_digest(receipts["package"]["outputs"])):
            raise ValueError("Full SDK verifier returned a different package/language/host identity")
        for field in ("contractDigest", "canonicalApiDigest", "canonicalCoverageDigest"):
            require_sha256(value[field], f"verified SDK content {field}")
        for phase, source in stages.items():
            if (regular_file_inventory(root / phase) != before[phase] or regular_file_inventory(source) != before[phase]
                    or read_regular_file_bytes(captured[phase]) != originals[phase]
                    or read_regular_file_bytes(receipt_paths[phase], reject_symlink_parents=True) != originals[phase]):
                raise ValueError("Original or private SDK validation inputs changed during verification")
    if read_regular_file_bytes(java_executable, reject_symlink_parents=True) != java_bytes:
        raise ValueError("Trusted Java executable changed during SDK verification")
    return VerifiedSdkValidationProjection(originals["validation"], content, _VERIFIED)
