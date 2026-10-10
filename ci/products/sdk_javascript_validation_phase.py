"""Readmit original JavaScript SDK validation through the full installed matcher.

This verifies source, plan, stage, receipt, and executed-evidence content. The
caller still authenticates the original hosted producer and Runtime dependency.
"""

from pathlib import Path
import os
import subprocess
import tempfile

from .inventory import (
    canonical_json_bytes, git_regular_blob_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    regular_file_inventory, sha256_bytes, snapshot_regular_tree,
)
from .plan import NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST, plan_phase
from .receipt import output_inventory_digest, validate_phase_receipt, verify_output_manifest_identity
from .registry import PhaseInstanceId
from .sdk_javascript_metadata import _inventory
from .sdk_javascript_metadata_admission import _CONSUMER_FILES, _original_versions
from .sdk_package import _require_capability_output_separate
from .selection import phase_git_inventory
from .tooling import verified_tooling_capture


_LIMIT = 16 * 1024 * 1024
_IDENTITIES = {
    "contract": ("contract", "contract", "binary", "common"),
    "package": ("sdk", "javascript", "package", "node"),
    "validation": ("sdk", "javascript", "validation", "node"),
    "runtime": ("runtime", "node-js", "validation", "node-js-binding"),
}
_BINDING_RECEIPT = "outputs/binding-evidence/javascript-typescript-parity.json"
_VALIDATION_OUTPUTS = {
    ("binding-evidence", _BINDING_RECEIPT),
    ("compiler-evidence", "outputs/compiler-evidence/public-api.json"),
    ("test-report", "outputs/test-report/packed-tests.xml"),
    *(("execution", f"outputs/execution/{name}") for name in (
        "packed-consumer-execution.json", "typescript-execution.json")),
    *(("test-program", f"outputs/test-program/{name}") for name in _CONSUMER_FILES),
}
_VERIFIED = object()
_IDENTITY = ("product", "component", "phase", "target", "productVersion", "buildKey")


class VerifiedJavaScriptValidationProjection:
    """Comparison view only; every original raw byte and producer stays external."""

    __slots__ = ("_receipt", "_content", "_verified", "_policy_revision")

    def __init__(self, receipt: bytes, content: bytes, verified: object, policy_revision=None):
        if verified is not _VERIFIED:
            raise TypeError("JavaScript projection requires the authenticated full matcher")
        self._receipt, self._content, self._verified = receipt, content, verified
        self._policy_revision = policy_revision

    @property
    def policy_revision(self):
        """External invoking-verifier provenance, never comparison/key content."""
        return self._policy_revision

    def output_inventory(self, receipt_sha256, outputs, *, identity=None):
        receipt = load_canonical_json_bytes(self._receipt)
        if (self._verified is not _VERIFIED or receipt_sha256 != sha256_bytes(self._receipt)
                or outputs != receipt["outputs"] or identity is None
                or any(identity.get(field) != receipt[field] for field in _IDENTITY)):
            raise ValueError("JavaScript comparison differs from its original receipt/identity/outputs")
        return [{"kind": "sdk-javascript-validation-content",
                 "relativePath": "outputs/sdk-javascript-validation-content.json",
                 "bytes": len(self._content), "sha256": sha256_bytes(self._content)}]

    def upstream_record(self, receipt):
        from .plan import _upstream_record

        inventory = self.output_inventory(sha256_bytes(canonical_json_bytes(receipt)),
                                          receipt["outputs"], identity=receipt)
        return {**_upstream_record(receipt), "outputsDigest": output_inventory_digest(inventory)}

    def content_bytes(self, receipt):
        self.output_inventory(sha256_bytes(canonical_json_bytes(receipt)),
                              receipt["outputs"], identity=receipt)
        return self._content


def verify_sdk_javascript_validation_phase(**arguments) -> tuple[dict, bytes]:
    """Keep the original reader contract; this is not hosted/transport admission."""
    receipt, raw, _ = _verify_sdk_javascript_validation(**arguments)
    return receipt, raw


def verify_sdk_javascript_validation_projection(**arguments) -> VerifiedJavaScriptValidationProjection:
    """Mint a receipt-bound view only after the same fixed full matcher succeeds."""
    _, raw, content = _verify_sdk_javascript_validation(**arguments)
    return VerifiedJavaScriptValidationProjection(raw, content, _VERIFIED, arguments.get("policy_revision"))


def _verify_sdk_javascript_validation(
    *, repository: Path, contract_stage: Path, contract_receipt: Path,
    package_stage: Path, package_receipt: Path,
    validation_stage: Path, validation_receipt: Path,
    runtime_validation_stage: Path, runtime_validation_receipt: Path,
    original_consumer_directory: Path,
    tooling_evidence: Path, tooling_public_key: Path, java_executable: Path,
    policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
) -> tuple[dict, bytes, bytes]:
    """Return unchanged validation receipt after original-plan and full matcher replay."""
    repository = Path(repository)
    original_consumer_directory = Path(original_consumer_directory)
    if (not original_consumer_directory.is_absolute() or
            original_consumer_directory != Path(os.path.normpath(original_consumer_directory))):
        raise ValueError("JavaScript validation requires its authenticated original consumer directory")
    java_executable = Path(java_executable)
    if not java_executable.is_absolute() or java_executable.name not in {"java", "java.exe"}:
        raise ValueError("JavaScript validation requires an explicit trusted Java executable")
    java_bytes = read_regular_file_bytes(java_executable, max_bytes=128 * 1024 * 1024,
                                         reject_symlink_parents=True)
    trees = {"contract": Path(contract_stage), "package": Path(package_stage),
             "validation": Path(validation_stage), "runtime": Path(runtime_validation_stage)}
    paths = {"contract": Path(contract_receipt), "package": Path(package_receipt),
             "validation": Path(validation_receipt), "runtime": Path(runtime_validation_receipt)}
    before = {name: _inventory(stage) for name, stage in trees.items()}
    raw = {name: read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True)
           for name, path in paths.items()}
    receipts = {name: validate_phase_receipt(load_canonical_json_bytes(value))
                for name, value in raw.items()}
    for name, receipt in receipts.items():
        if tuple(receipt[field] for field in ("product", "component", "phase", "target")) != _IDENTITIES[name]:
            raise ValueError(f"JavaScript validation {name} receipt has the wrong phase identity")
    validation = receipts["validation"]
    version = validation["productVersion"]
    if receipts["package"]["productVersion"] != version:
        raise ValueError("JavaScript validation and package SDK versions differ")
    if {(record["kind"], record["relativePath"]) for record in validation["outputs"]} != _VALIDATION_OUTPUTS:
        raise ValueError("JavaScript validation original output inventory is incomplete or unexpected")
    versions = _original_versions(repository, validation)
    instance = PhaseInstanceId(*_IDENTITIES["validation"])
    planned = plan_phase(instance,
        inventory=phase_git_inventory(repository, validation["producer"]["commit"], instance),
        versions=versions, upstream_receipts=[receipts["package"], receipts["runtime"]],
        toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,
        flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1)
    if validation["inputs"] != planned["inputs"] or validation["buildKey"] != planned["buildKey"]:
        raise ValueError("JavaScript validation inputs/build key differ from its original producer plan")
    program = trees["validation"] / "outputs/test-program"
    if {record["relativePath"] for record in regular_file_inventory(program)} != _CONSUMER_FILES:
        raise ValueError("JavaScript validation consumer source inventory differs from the full matcher")
    for name in sorted(_CONSUMER_FILES):
        source = git_regular_blob_bytes(repository, validation["producer"]["commit"],
            f"codex-agent-bindings/javascript/consumer/{name}", max_bytes=_LIMIT)
        if not source or source != read_regular_file_bytes(program / name, max_bytes=_LIMIT,
                                                           reject_symlink_parents=True):
            raise ValueError("JavaScript validation consumer program differs from original Git source")
    with tempfile.TemporaryDirectory(prefix="javascript-validation-phase-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, [repository, *trees.values(), *paths.values(),
            Path(tooling_evidence), Path(tooling_public_key), java_executable,
            *(Path(path) for path in (tooling_keyring, tooling_keys_directory) if path is not None)])
        captured = {}
        for name, source in trees.items():
            captured[name] = private / name
            snapshot_regular_tree(source, captured[name])
            if _inventory(captured[name]) != before[name]:
                raise ValueError("JavaScript validation original stage changed during capture")
            receipt = receipts[name]
            manifest = verify_output_manifest_identity(captured[name], *_IDENTITIES[name], receipt["productVersion"])
            if manifest["outputs"] != receipt["outputs"]:
                raise ValueError("JavaScript validation original stage differs from its receipt")
        original_binding = read_regular_file_bytes(captured["validation"] / _BINDING_RECEIPT,
                                                   max_bytes=_LIMIT, reject_symlink_parents=True)
        output = private / "replayed.json"
        with verified_tooling_capture(tooling_evidence, repository, tooling_public_key,
                required_trust_domain=required_trust_domain, keyring=tooling_keyring,
                keys_directory=tooling_keys_directory, policy_revision=policy_revision) as jar:
            arguments = {"contract-stage": captured["contract"], "package-stage": captured["package"],
                "validation-stage": captured["validation"], "runtime-validation-stage": captured["runtime"],
                "original-consumer-directory": original_consumer_directory,
                "contract-version": receipts["contract"]["productVersion"], "sdk-version": version,
                "runtime-version": receipts["runtime"]["productVersion"], "content-output": output}
            command = [str(java_executable), "-jar", str(jar), "write-javascript-metadata-content"]
            command += [part for name, value in arguments.items() for part in (f"--{name}", str(value))]
            environment = {key: value for key, value in os.environ.items() if key in {
                "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL"}}
            subprocess.run(command, cwd=private, env=environment, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if read_regular_file_bytes(output, max_bytes=_LIMIT, reject_symlink_parents=True) != original_binding:
            raise ValueError("JavaScript validation binding receipt differs from full authenticated replay")
        for name, source in trees.items():
            if _inventory(source) != before[name] or _inventory(captured[name]) != before[name]:
                raise ValueError("JavaScript validation stage changed during replay")
        for name, path in paths.items():
            if read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True) != raw[name]:
                raise ValueError("JavaScript validation original receipt changed during replay")
    if read_regular_file_bytes(java_executable, max_bytes=128 * 1024 * 1024,
                               reject_symlink_parents=True) != java_bytes:
        raise ValueError("Trusted Java executable changed during JavaScript validation")
    return validation, raw["validation"], original_binding
