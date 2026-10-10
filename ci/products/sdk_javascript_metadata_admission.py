"""Original JavaScript metadata Git/plan/content binding, not CI admission.

The caller still authenticates full package/K/R evidence and the original
consumer directory. No serialized projection or inferred command grants trust.
"""

from pathlib import Path
import subprocess
import tempfile

from .inventory import (
    git_product_versions, git_regular_blob_bytes, load_canonical_json_bytes,
    read_regular_file_bytes, regular_file_inventory, run_git, snapshot_regular_tree,
)
from .plan import NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST, plan_phase
from .receipt import validate_phase_receipt
from .registry import PhaseInstanceId
from .sdk_javascript_metadata import (
    _inventory, javascript_metadata_uses_raw_validation, verify_sdk_javascript_metadata_content,
)
from .sdk_package import _require_capability_output_separate
from .selection import phase_git_inventory


_LIMIT = 16 * 1024 * 1024
# Exact inventory required by CrossLanguageJavaScriptBindingEvidence.kt, not a
# substitute for its compiler/surface/scenario matcher.
_CONSUMER_FILES = frozenset(("package-lock.json", "package.json", "negative.ts", "smoke.cjs",
                             "smoke.mjs", "smoke.ts", "tsconfig.json", "verify.mjs"))


def _original_versions(repository, receipt):
    commit, tree = receipt["producer"]["commit"], receipt["producer"]["tree"]
    try:
        actual_commit = run_git(repository, "rev-parse", f"{commit}^{{commit}}").strip()
        actual_tree = run_git(repository, "rev-parse", f"{commit}^{{tree}}").strip()
    except subprocess.CalledProcessError as error:
        raise ValueError("JavaScript original source commit is unavailable") from error
    if actual_commit != commit or actual_tree != tree:
        raise ValueError("JavaScript original producer commit/tree differs from Git history")
    if git_regular_blob_bytes(repository, commit, "gradle/release/versions/sdk.txt", max_bytes=256) != \
            (receipt["productVersion"] + "\n").encode("utf-8"):
        raise ValueError("JavaScript original SDK version differs from its producer Git version")
    return git_product_versions(repository, commit)


def verify_sdk_javascript_metadata_admission(
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
    repository = Path(repository)
    trees = {"contract_stage": Path(contract_stage), "package_stage": Path(package_stage),
        "validation_stage": Path(validation_stage), "runtime_validation_stage": Path(runtime_validation_stage),
        "metadata_stage": Path(metadata_stage)}
    paths = {"contract_receipt": Path(contract_receipt), "package_receipt": Path(package_receipt),
        "validation_receipt": Path(validation_receipt), "runtime_validation_receipt": Path(runtime_validation_receipt),
        "metadata_receipt": Path(metadata_receipt)}
    before = {name: _inventory(path) for name, path in trees.items()}
    raw = {name: read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True)
           for name, path in paths.items()}
    java_bytes = read_regular_file_bytes(Path(java_executable), max_bytes=128 * 1024 * 1024,
                                         reject_symlink_parents=True)
    with tempfile.TemporaryDirectory(prefix="javascript-metadata-admission-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, [repository, *trees.values(), *paths.values(),
            Path(tooling_evidence), Path(tooling_public_key), Path(java_executable),
            *(Path(path) for path in (tooling_keyring, tooling_keys_directory) if path is not None)])
        captured = {}
        for name, source in trees.items():
            captured[name] = private / name
            snapshot_regular_tree(source, captured[name])
            if _inventory(captured[name]) != before[name]:
                raise ValueError("JavaScript admission original stage changed during capture")
        for name, contents in raw.items():
            captured[name] = private / f"{name}.json"
            captured[name].write_bytes(contents)
        receipts = {name.removesuffix("_receipt"): validate_phase_receipt(load_canonical_json_bytes(contents))
                    for name, contents in raw.items()}
        original_inputs = {}
        for phase in ("validation", "metadata"):
            receipt = receipts[phase]
            instance = PhaseInstanceId("sdk", "javascript", phase, "node")
            if tuple(receipt[field] for field in ("product", "component", "phase", "target")) != (
                    "sdk", "javascript", phase, "node"):
                raise ValueError("JavaScript admission receipt has the wrong phase identity")
            versions = _original_versions(repository, receipt)
            inventory = phase_git_inventory(repository, receipt["producer"]["commit"], instance)
            if inventory != receipt["inputs"]["inventory"]:
                raise ValueError("JavaScript original inventory differs from its producer plan")
            original_inputs[phase] = versions, inventory
        program = captured["validation_stage"] / "outputs/test-program"
        if {record["relativePath"] for record in regular_file_inventory(program)} != _CONSUMER_FILES:
            raise ValueError("JavaScript original consumer source inventory differs from the exact matcher input")
        for name in sorted(_CONSUMER_FILES):
            source = git_regular_blob_bytes(repository, receipts["validation"]["producer"]["commit"],
                f"codex-agent-bindings/javascript/consumer/{name}", max_bytes=_LIMIT)
            if not source or source != read_regular_file_bytes(program / name, max_bytes=_LIMIT,
                                                              reject_symlink_parents=True):
                raise ValueError("JavaScript consumer program differs from its original validation Git source")
        from .sdk_javascript_validation_phase import verify_sdk_javascript_validation_projection

        proof = verify_sdk_javascript_validation_projection(
            **{name: captured[name] for name in (
                "contract_stage", "contract_receipt", "package_stage", "package_receipt",
                "validation_stage", "validation_receipt", "runtime_validation_stage", "runtime_validation_receipt")},
            original_consumer_directory=original_consumer_directory, repository=repository,
            tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key,
            java_executable=java_executable, policy_revision=policy_revision,
            required_trust_domain=required_trust_domain, tooling_keyring=tooling_keyring,
            tooling_keys_directory=tooling_keys_directory)
        for phase in ("validation", "metadata"):
            receipt = receipts[phase]
            instance = PhaseInstanceId("sdk", "javascript", phase, "node")
            versions, inventory = original_inputs[phase]
            upstream = ([receipts["validation"]] if phase == "metadata" else
                        [receipts["package"], receipts["runtime_validation"]])
            projection = ({"sdk_javascript_validation_projection": proof} if phase == "metadata" else {})
            if phase == "metadata" and javascript_metadata_uses_raw_validation(receipt):
                projection["sdk_javascript_legacy_metadata_receipt"] = receipt
            planned = plan_phase(instance, inventory=inventory,
                versions=versions, upstream_receipts=upstream,
                toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1, **projection)
            if receipt["inputs"] != planned["inputs"] or receipt["buildKey"] != planned["buildKey"]:
                raise ValueError("JavaScript original inputs/build key differ from its producer plan")
        metadata, original = verify_sdk_javascript_metadata_content(**captured,
            original_consumer_directory=original_consumer_directory, repository=repository,
            tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key,
            java_executable=java_executable, policy_revision=policy_revision,
            required_trust_domain=required_trust_domain, tooling_keyring=tooling_keyring,
            tooling_keys_directory=tooling_keys_directory, validation_projection=proof)
        if original != raw["metadata_receipt"] or metadata != receipts["metadata"]:
            raise ValueError("JavaScript full content gate returned a different original metadata receipt")
        for name, source in trees.items():
            if any(_inventory(path) != before[name] for path in (source, captured[name])):
                raise ValueError("Original or private JavaScript admission stage changed during verification")
        for name, source in paths.items():
            if any(read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True) != raw[name]
                   for path in (source, captured[name])):
                raise ValueError("Original or private JavaScript admission receipt changed during verification")
    if read_regular_file_bytes(Path(java_executable), max_bytes=128 * 1024 * 1024,
                               reject_symlink_parents=True) != java_bytes:
        raise ValueError("Trusted Java executable changed during JavaScript admission")
    return metadata, original
