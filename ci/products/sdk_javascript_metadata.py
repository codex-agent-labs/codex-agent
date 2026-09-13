"""Original JavaScript metadata content replay through authenticated tooling.

This reader returns the unchanged metadata receipt, never a source/projection
authority token. Its caller authenticates original phase sources, full K/R/S858
and package evidence, and the original consumer directory independently.
"""

import os
from pathlib import Path
import subprocess
import tempfile

from .inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, regular_file_inventory,
    require_regular_directory, snapshot_regular_tree,
)
from .plan import _upstream_record
from .receipt import validate_phase_receipt, verify_output_manifest_identity
from .sdk_package import _require_capability_output_separate
from .tooling import verified_tooling_capture


_LIMIT = 16 * 1024 * 1024
_OUTPUT = "outputs/binding-evidence/javascript-typescript-parity.json"


def _inventory(path):
    path = Path(path)
    if not path.is_absolute() or path != Path(os.path.normpath(path)):
        raise ValueError("JavaScript metadata requires normalized absolute stage paths")
    for parent in (path, *path.parents):
        require_regular_directory(parent, "JavaScript metadata stage ancestry")
    return regular_file_inventory(path)


def verify_sdk_javascript_metadata_content(
    *, contract_stage: Path, contract_receipt: Path,
    package_stage: Path, package_receipt: Path,
    validation_stage: Path, validation_receipt: Path,
    runtime_validation_stage: Path, runtime_validation_receipt: Path,
    metadata_stage: Path, metadata_receipt: Path,
    original_consumer_directory: Path,
    repository: Path, tooling_evidence: Path, tooling_public_key: Path,
    java_executable: Path, policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
) -> tuple[dict, bytes]:
    if (type(policy_revision) is not str or len(policy_revision) != 40
            or any(character not in "0123456789abcdef" for character in policy_revision)):
        raise ValueError("JavaScript metadata requires an exact trusted Git policy revision")
    original_consumer_directory = Path(original_consumer_directory)
    if (not original_consumer_directory.is_absolute()
            or original_consumer_directory != Path(os.path.normpath(original_consumer_directory))):
        raise ValueError("JavaScript metadata requires its exact authenticated original consumer directory")
    java_executable = Path(java_executable)
    if not java_executable.is_absolute() or java_executable.name not in {"java", "java.exe"}:
        raise ValueError("JavaScript metadata requires an explicit trusted Java executable")
    trees = {"contract": Path(contract_stage), "package": Path(package_stage),
             "validation": Path(validation_stage), "runtime": Path(runtime_validation_stage),
             "metadata": Path(metadata_stage)}
    paths = {"contract": Path(contract_receipt), "package": Path(package_receipt),
             "validation": Path(validation_receipt), "runtime": Path(runtime_validation_receipt),
             "metadata": Path(metadata_receipt)}
    # Baseline all originals before invoking any receipt or tooling verifier.
    before = {name: _inventory(path) for name, path in trees.items()}
    originals = {name: read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True)
                 for name, path in paths.items()}
    java_bytes = read_regular_file_bytes(java_executable, max_bytes=128 * 1024 * 1024,
                                         reject_symlink_parents=True)
    resolved = [path.resolve() for path in trees.values()]
    if any(left == right or left in right.parents or right in left.parents
           for index, left in enumerate(resolved) for right in resolved[index + 1:]):
        raise ValueError("JavaScript metadata original stages overlap")
    identities = {"contract": ("contract", "contract", "binary", "common"),
                  "runtime": ("runtime", "node-js", "validation", "node-js-binding"),
                  **{phase: ("sdk", "javascript", phase, "node")
                     for phase in ("package", "validation", "metadata")}}
    with tempfile.TemporaryDirectory(prefix="sdk-javascript-metadata-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, [*trees.values(), *paths.values(),
            Path(repository), Path(tooling_evidence), Path(tooling_public_key), java_executable,
            *(Path(path) for path in (tooling_keyring, tooling_keys_directory) if path is not None)])
        for name, source in trees.items():
            snapshot_regular_tree(source, private / name)
            if _inventory(private / name) != before[name]:
                raise ValueError("JavaScript metadata original stage changed during capture")
        captured_receipts = private / "receipts"
        captured_receipts.mkdir()
        for name, data in originals.items():
            (captured_receipts / f"{name}.json").write_bytes(data)
        receipts = {name: validate_phase_receipt(load_canonical_json_bytes(data))
                    for name, data in originals.items()}
        for name, receipt in receipts.items():
            if tuple(receipt[field] for field in ("product", "component", "phase", "target")) != identities[name]:
                raise ValueError("JavaScript metadata original receipt has the wrong phase identity")
            manifest = verify_output_manifest_identity(private / name, *identities[name], receipt["productVersion"])
            if manifest["outputs"] != receipt["outputs"]:
                raise ValueError("JavaScript metadata stage differs from its exact original receipt")
        metadata = receipts["metadata"]
        version = metadata["productVersion"]
        if any(receipts[name]["productVersion"] != version for name in ("package", "validation")):
            raise ValueError("JavaScript package validation and metadata SDK versions differ")
        if (len(metadata["outputs"]) != 1 or metadata["outputs"][0]["relativePath"] != _OUTPUT
                or metadata["outputs"][0]["kind"] != "binding-evidence"):
            raise ValueError("JavaScript metadata requires its sole exact semantic output")
        if metadata["inputs"]["upstreamArtifacts"] != [_upstream_record(receipts["validation"])]:
            raise ValueError("JavaScript metadata does not bind its original validation")
        expected = [_upstream_record(receipts[name]) for name in ("package", "runtime")]
        expected.sort(key=lambda record: tuple(record[field] for field in ("product", "component", "phase", "target")))
        if receipts["validation"]["inputs"]["upstreamArtifacts"] != expected:
            raise ValueError("JavaScript validation does not bind its original package and Runtime program")
        content_output = private / "replayed.json"
        with verified_tooling_capture(tooling_evidence, repository, tooling_public_key,
                required_trust_domain=required_trust_domain, keyring=tooling_keyring,
                keys_directory=tooling_keys_directory, policy_revision=policy_revision) as jar:
            arguments = {"contract-stage": private / "contract", "package-stage": private / "package",
                "validation-stage": private / "validation", "runtime-validation-stage": private / "runtime",
                "original-consumer-directory": original_consumer_directory,
                "contract-version": receipts["contract"]["productVersion"], "sdk-version": version,
                "runtime-version": receipts["runtime"]["productVersion"], "content-output": content_output}
            command = [str(java_executable), "-jar", str(jar), "write-javascript-metadata-content"]
            command += [part for name, value in arguments.items() for part in (f"--{name}", str(value))]
            environment = {key: value for key, value in os.environ.items() if key in {
                "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL"}}
            subprocess.run(command, cwd=private, env=environment, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        content = read_regular_file_bytes(content_output, max_bytes=_LIMIT, reject_symlink_parents=True)
        if not content or content != read_regular_file_bytes(private / "metadata" / _OUTPUT, max_bytes=_LIMIT):
            raise ValueError("Original JavaScript metadata differs from the full authenticated replay")
        for name, source in trees.items():
            if any(_inventory(path) != before[name] for path in (source, private / name)):
                raise ValueError("Original or private JavaScript metadata stage changed during verification")
        for name, source in paths.items():
            if any(read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True) != originals[name]
                   for path in (source, captured_receipts / f"{name}.json")):
                raise ValueError("Original or private JavaScript metadata receipt changed during verification")
    if read_regular_file_bytes(java_executable, max_bytes=128 * 1024 * 1024,
                               reject_symlink_parents=True) != java_bytes:
        raise ValueError("Trusted Java executable changed during JavaScript metadata verification")
    return metadata, originals["metadata"]
