"""Original native SDK metadata admission through the existing full five-host gate.

This returns an unchanged receipt, not a planner, producer, or release capability.
The caller must still authenticate the selected original metadata source/key.
"""

import os
from pathlib import Path
import subprocess
import tempfile

from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    regular_file_inventory, require_array, require_exact_keys, require_integer,
    require_object, require_regular_directory, sha256_bytes, snapshot_regular_tree,
)
from .receipt import output_inventory_digest, validate_phase_receipt, verify_output_manifest_identity
from .registry import NATIVE_BINDINGS, NATIVE_TARGETS
from .sdk_inputs import REQUEST_NAME, stage_sdk_inputs
from .sdk_package import _require_capability_output_separate
from .sdk_validation_inputs import _request_inventory
from .tooling import verified_tooling_capture


_LIMIT = 16 * 1024 * 1024
_OUTPUT = "outputs/evidence/native-metadata.json"


def _inventory(path, *, allow_empty=False):
    path = Path(path).absolute()
    for parent in path.parents:
        require_regular_directory(parent, "Native metadata input ancestry")
    return regular_file_inventory(path, allow_empty=allow_empty)


def verify_sdk_native_metadata_content(
    *, repository: Path, component: str, metadata_stage: Path, metadata_receipt: Path,
    package_stage: Path, package_receipt: Path, compatibility_request: Path,
    runtime_stages: Path, staged_sdks: Path, validation_stages: Path, validation_receipts: Path,
    tooling_evidence: Path, tooling_public_key: Path, java_executable: Path,
    policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
) -> tuple[dict, bytes]:
    """Reconstruct all five full host results and compare the sole original output.

    No caller-supplied content, command, digest, or callback can replace the fixed
    authenticated tooling invocation. K/R authentication and native matching run
    in that existing gate; metadata source/plan replay belongs to its caller.
    """
    if component not in NATIVE_BINDINGS:
        raise ValueError("Native SDK metadata requires an exact language")
    if (type(policy_revision) is not str or len(policy_revision) != 40
            or any(character not in "0123456789abcdef" for character in policy_revision)):
        raise ValueError("Native SDK metadata requires an exact caller-pinned Git policy")
    java_executable = Path(java_executable)
    if not java_executable.is_absolute() or java_executable.name not in {"java", "java.exe"}:
        raise ValueError("Native SDK metadata requires an explicit trusted Java executable")
    java_bytes = read_regular_file_bytes(java_executable, max_bytes=128 * 1024 * 1024,
                                         reject_symlink_parents=True)
    trees = {"metadata": Path(metadata_stage), "package": Path(package_stage),
             "runtime": Path(runtime_stages), "sdks": Path(staged_sdks),
             "validations": Path(validation_stages), "validation-receipts": Path(validation_receipts)}
    before = {name: _inventory(path) for name, path in trees.items()}
    paths = {"metadata.json": Path(metadata_receipt), "package.json": Path(package_receipt),
             "original-request.json": Path(compatibility_request)}
    originals = {name: read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True)
                 for name, path in paths.items()}
    request_inventory = _request_inventory(paths["original-request.json"])
    receipts = {phase: validate_phase_receipt(load_canonical_json_bytes(originals[f"{phase}.json"]))
                for phase in ("metadata", "package")}
    metadata, package = receipts["metadata"], receipts["package"]
    version = metadata["productVersion"]
    for phase, receipt in receipts.items():
        if ((receipt["product"], receipt["component"], receipt["phase"], receipt["target"]) !=
                ("sdk", component, phase, "desktop") or receipt["productVersion"] != version):
            raise ValueError("Native metadata and package receipts have different phase/version identities")
    with tempfile.TemporaryDirectory(prefix="sdk-native-metadata-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, [*trees.values(), *paths.values(),
            *request_inventory, Path(repository), Path(tooling_evidence), Path(tooling_public_key),
            java_executable, *(Path(path) for path in (tooling_keyring, tooling_keys_directory) if path is not None)])
        for name, source in trees.items():
            snapshot_regular_tree(source, private / name)
            if _inventory(private / name) != before[name]:
                raise ValueError("Native metadata original tree changed during capture")
        for name, data in originals.items():
            (private / name).write_bytes(data)
        for phase, receipt in receipts.items():
            manifest = verify_output_manifest_identity(private / phase, "sdk", component, phase, "desktop", version)
            if manifest["outputs"] != receipt["outputs"]:
                raise ValueError("Native metadata/package stage differs from its original receipt")
        if (len(metadata["outputs"]) != 1 or metadata["outputs"][0]["relativePath"] != _OUTPUT
                or metadata["outputs"][0]["kind"] != "native-wrapper-metadata"):
            raise ValueError("Native metadata requires its sole exact content output")
        targets = sorted(NATIVE_TARGETS)
        if (sorted(path.name for path in (private / "validations").iterdir()) != targets
                or {record["relativePath"] for record in before["validation-receipts"]} !=
                {f"{target}.json" for target in targets}):
            raise ValueError("Native metadata requires exactly five original host stages and receipts")
        hosts = {}
        for target in targets:
            raw = read_regular_file_bytes(private / "validation-receipts" / f"{target}.json", max_bytes=_LIMIT)
            receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
            if ((receipt["product"], receipt["component"], receipt["phase"], receipt["target"]) !=
                    ("sdk", component, "validation", target) or receipt["productVersion"] != version):
                raise ValueError("Native metadata host receipt has a different original identity")
            manifest = verify_output_manifest_identity(private / "validations" / target,
                                                       "sdk", component, "validation", target, version)
            if manifest["outputs"] != receipt["outputs"]:
                raise ValueError("Native metadata host stage differs from its original receipt")
            hosts[target] = receipt, raw
        # Existing S858 capture authenticates and rebases every original K/R input;
        # it does not replace the five complete native gates below.
        stage_sdk_inputs(private / "original-request.json", private / "compatibility",
                         request_directory=paths["original-request.json"].parent)
        compatibility_before = _inventory(private / "compatibility", allow_empty=True)
        output = private / "verified-content.json"
        with verified_tooling_capture(tooling_evidence, repository, tooling_public_key,
                required_trust_domain=required_trust_domain, keyring=tooling_keyring,
                keys_directory=tooling_keys_directory, policy_revision=policy_revision) as jar:
            arguments = {"repository": repository, "language": component, "sdk-version": version,
                "package-stage": private / "package", "package-receipt": private / "package.json",
                "compatibility-request": private / "compatibility" / REQUEST_NAME,
                "runtime-stages": private / "runtime", "staged-sdks": private / "sdks",
                "validation-stages": private / "validations", "validation-receipts": private / "validation-receipts",
                "content-output": output}
            command = [str(java_executable), "-jar", str(jar), "write-native-wrapper-metadata-content"]
            command += [part for name, value in arguments.items() for part in (f"--{name}", str(value))]
            environment = {key: value for key, value in os.environ.items() if key in {
                "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL"}}
            subprocess.run(command, cwd=private, env=environment, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        content = read_regular_file_bytes(output, max_bytes=_LIMIT, reject_symlink_parents=True)
        if content != read_regular_file_bytes(private / "metadata" / _OUTPUT, max_bytes=_LIMIT):
            raise ValueError("Original native metadata differs from the complete authenticated five-host result")
        value = require_exact_keys(load_canonical_json_bytes(content),
            {"schemaVersion", "kind", "component", "sdkVersion", "contractDigest", "canonicalApiDigest",
             "canonicalCoverageDigest", "packageOutputsDigest", "hosts"}, "Native metadata content")
        if (require_integer(value["schemaVersion"], "Native metadata schema", 1) != 1
                or value["kind"] != "sdk-native-metadata-content" or value["component"] != component
                or value["sdkVersion"] != version
                or value["packageOutputsDigest"] != output_inventory_digest(package["outputs"])):
            raise ValueError("Full native metadata result differs from the original package identity")
        contents = [require_object(host, "Native metadata host")
                    for host in require_array(value["hosts"], "Native metadata hosts")]
        if [host.get("target") for host in contents] != targets:
            raise ValueError("Full native metadata result lacks exact ordered host contents")
        # Reuse the planner's record representation, without planning or granting
        # source authority here. Every semantic digest binds an original raw receipt.
        from .plan import _upstream_record
        expected = [_upstream_record(package)]
        for host in contents:
            receipt, raw = hosts[host["target"]]
            expected.append(_upstream_record(receipt, semantic_projection={
                "schemaVersion": 1, "kind": "sdk-native-validation-content",
                "sha256": sha256_bytes(canonical_json_bytes(host)), "receiptSha256": sha256_bytes(raw)}))
        expected.sort(key=lambda member: tuple(member[field] for field in ("product", "component", "phase", "target")))
        if metadata["inputs"]["upstreamArtifacts"] != expected:
            raise ValueError("Native metadata does not bind its exact original package and five host projections")
        for name, source in trees.items():
            if _inventory(source) != before[name] or _inventory(private / name) != before[name]:
                raise ValueError("Original or private native metadata inputs changed during verification")
        for name, source in paths.items():
            if any(read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True) != originals[name]
                   for path in (source, private / name)):
                raise ValueError("Original or private native metadata receipt/request changed during verification")
        if (_inventory(private / "compatibility", allow_empty=True) != compatibility_before
                or _request_inventory(paths["original-request.json"]) != request_inventory):
            raise ValueError("Native metadata original or captured K/R compatibility inputs changed")
    if read_regular_file_bytes(java_executable, max_bytes=128 * 1024 * 1024,
                               reject_symlink_parents=True) != java_bytes:
        raise ValueError("Trusted Java executable changed during native metadata verification")
    return metadata, originals["metadata.json"]
