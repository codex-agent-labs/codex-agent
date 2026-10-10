"""Bind retained Apple observations to caller-authenticated source identities.

This module does not authenticate an upload or CI run. The caller supplies the
already-authenticated lane receipt digest and producer Git identity. This gate
then runs full Apple replay over the same privately captured original inputs.
"""

from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

if __package__ == "products":  # Script entry points in ci/ use this namespace.
    from receipt import INPUT_NAMES, validate_receipt
else:
    from ..receipt import INPUT_NAMES, validate_receipt
from .contract_model import verify_contract_bundle
from .contract_projection import VerifiedContractProjection
from .inventory import (
    git_regular_blob_bytes, load_json_bytes, read_regular_file_bytes,
    regular_file_inventory, require_semver, require_sha256, run_git, sha256_bytes,
    snapshot_regular_tree,
)
from .sdk_apple_content import verify_sdk_apple_original_execution


_LIMIT = 16 * 1024 * 1024
_BUNDLE_LIMIT = 512 * 1024 * 1024
_GIT_ID = re.compile(r"[0-9a-f]{40}")
_GIT_SOURCES = {
    "source/Package.swift": "Package.swift",
    "source/native-provenance.json": "codex-agent-runtime-ios/native/provenance.json",
    "consumer/CodexFailureSwiftConsumer.swift":
        "codex-agent-runtime-ios/apple/CompilerEvidence/CodexFailureSwiftConsumer.swift",
    "consumer/CodexFailureObjectiveCConsumer.m":
        "codex-agent-runtime-ios/apple/CompilerEvidence/CodexFailureObjectiveCConsumer.m",
}
_LANE_TREES = {
    "compiler-raw": "payload/codex-agent-runtime-ios/build/apple-compiler-evidence-task/raw",
    "xctest-raw": "payload/codex-agent-runtime-ios/build/swift-authentication-evidence-task/raw",
    "xcresult": "payload/codex-agent-runtime-ios/build/swift-authentication-tests.xcresult",
}
_LANE_REPORTS = {
    "reports/cross-language-api/apple/compiler-evidence.json":
        "payload/codex-agent-runtime-ios/build/reports/cross-language-api/apple/compiler-evidence.json",
    "reports/cross-language-api/apple/binding-evidence.json":
        "payload/codex-agent-runtime-ios/build/reports/cross-language-api/apple/binding-evidence.json",
    "reports/cross-language-api/bindings/swift-parity.json":
        "payload/codex-agent-runtime-ios/build/reports/cross-language-api/bindings/swift-parity.json",
    "reports/cross-language-api/bindings/objective-c-parity.json":
        "payload/codex-agent-runtime-ios/build/reports/cross-language-api/bindings/objective-c-parity.json",
    "reports/swift-authentication-tests-summary.json":
        "payload/codex-agent-runtime-ios/build/swift-authentication-tests-summary.json",
}


def _inventory(path: Path, *, allow_empty: bool = False):
    return regular_file_inventory(path, allow_empty=allow_empty)


def _read(path: Path) -> bytes:
    return read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True)


def _same_tree(left: Path, right: Path) -> bool:
    return _inventory(left, allow_empty=True) == _inventory(right, allow_empty=True)


def _require_private_root_separate(root: Path, inputs) -> None:
    private = root.resolve()
    for value in inputs:
        source = Path(value).resolve(strict=True)
        if source == private or source in private.parents or private in source.parents:
            raise ValueError("Apple source verification work overlaps an original input")


def verify_sdk_apple_original_source(
    *, repository: Path, distribution_directory: Path, execution_directory: Path,
    ios_swift_tests_root: Path, impact_plan: Path, expected_lane_receipt_sha256: str,
    expected_producer_commit: str, expected_producer_tree: str,
    expected_distribution_proof: Path, expected_sdk_compatibility: Path,
    contract_bundle: Path, contract_projection: VerifiedContractProjection,
    tooling_evidence: Path, tooling_public_key: Path, java_executable: Path,
    policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
) -> None:
    """Bind source and replay the same private originals without granting run authority."""
    if any(_GIT_ID.fullmatch(value) is None for value in
           (expected_producer_commit, expected_producer_tree)):
        raise ValueError("Apple source verification requires an exact caller producer identity")
    expected_lane_receipt_sha256 = require_sha256(
        expected_lane_receipt_sha256, "Apple source lane receipt digest",
    )
    if type(contract_projection) is not VerifiedContractProjection:
        raise TypeError("Apple source verification requires an authenticated Contract projection")
    projection = contract_projection.receipt_value(include_coverage=True)

    repository = Path(repository).resolve(strict=True)
    directories = {
        "distribution": Path(distribution_directory),
        "execution": Path(execution_directory),
        "lane": Path(ios_swift_tests_root),
    }
    resolved_directories = [path.resolve(strict=True) for path in directories.values()]
    if any(left == right or left in right.parents or right in left.parents
           for index, left in enumerate(resolved_directories)
           for right in resolved_directories[index + 1:]):
        raise ValueError("Apple source verification directories must not overlap")
    originals = {
        name: _inventory(path, allow_empty=name != "distribution")
        for name, path in directories.items()
    }

    impact_plan = Path(impact_plan)
    plan_bytes = _read(impact_plan)
    plan_inventories = {
        name: _read(impact_plan.parent / "inventories/ios-swift-tests" / name)
        for name in INPUT_NAMES.values()
    }
    expected_paths = {
        "proof": Path(expected_distribution_proof),
        "compatibility": Path(expected_sdk_compatibility),
        "contract": Path(contract_bundle),
    }
    expected_bytes = {
        name: read_regular_file_bytes(
            path, max_bytes=_BUNDLE_LIMIT if name == "contract" else _LIMIT,
            reject_symlink_parents=True,
        )
        for name, path in expected_paths.items()
    }
    if not all(expected_bytes.values()):
        raise ValueError("Apple source caller inputs must be nonempty")
    for expected in expected_paths.values():
        resolved = expected.resolve(strict=True)
        if any(resolved == root or resolved in root.parents or root in resolved.parents
               for root in resolved_directories):
            raise ValueError("Apple source caller input overlaps transported evidence")

    try:
        commit = run_git(repository, "rev-parse", f"{expected_producer_commit}^{{commit}}").strip()
        tree = run_git(repository, "rev-parse", f"{expected_producer_commit}^{{tree}}").strip()
    except subprocess.CalledProcessError as error:
        raise ValueError("Apple source producer commit is unavailable") from error
    if (commit, tree) != (expected_producer_commit, expected_producer_tree):
        raise ValueError("Apple source producer commit/tree differs from caller authority")
    git_sources = {
        target: git_regular_blob_bytes(repository, commit, source, max_bytes=_LIMIT)
        for target, source in _GIT_SOURCES.items()
    }
    git_versions = {
        product: git_regular_blob_bytes(
            repository, commit, f"gradle/release/versions/{product}.txt", max_bytes=256,
        )
        for product in ("contract", "sdk")
    }

    all_inputs = [*directories.values(), impact_plan, *(
        impact_plan.parent / "inventories/ios-swift-tests" / name for name in INPUT_NAMES.values()
    ), *expected_paths.values()]
    with tempfile.TemporaryDirectory(prefix="sdk-apple-source-") as temporary:
        root = Path(temporary).resolve()
        _require_private_root_separate(root, all_inputs)
        captured = {}
        for name, source in directories.items():
            captured[name] = root / name
            snapshot_regular_tree(source, captured[name], allow_empty=name != "distribution")
            if _inventory(captured[name], allow_empty=name != "distribution") != originals[name]:
                raise ValueError("Apple source input changed during private capture")

        plan_root = root / "plan"
        private_plan = plan_root / impact_plan.name
        private_plan.parent.mkdir()
        private_plan.write_bytes(plan_bytes)
        for name, data in plan_inventories.items():
            destination = plan_root / "inventories/ios-swift-tests" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        caller = root / "caller"
        caller.mkdir()
        private_expected = {}
        for name, data in expected_bytes.items():
            private_expected[name] = caller / expected_paths[name].name
            if private_expected[name].exists():
                raise ValueError("Apple source caller input basenames overlap")
            private_expected[name].write_bytes(data)

        receipt_path = captured["lane"] / "lane-receipt.json"
        if sha256_bytes(_read(receipt_path)) != expected_lane_receipt_sha256:
            raise ValueError("Apple source lane receipt differs from caller authority")
        receipt = validate_receipt(
            receipt_path, private_plan, captured["lane"], "ios-swift-tests",
            repository_root=repository,
        )
        if (receipt["validationCommit"], receipt["validationTree"]) != (commit, tree):
            raise ValueError("Apple source lane producer differs from caller authority")

        proof_file = captured["distribution"] / "verified-distribution-proof.json"
        compatibility_file = captured["execution"] / "sdk-compatibility.json"
        if _read(proof_file) != _read(private_expected["proof"]):
            raise ValueError("Apple source proof differs from caller authority")
        if _read(compatibility_file) != _read(private_expected["compatibility"]):
            raise ValueError("Apple source compatibility differs from caller authority")
        proof = load_json_bytes(_read(proof_file))
        if type(proof) is not dict or (proof.get("candidateCommit"), proof.get("candidateTree")) != (commit, tree):
            raise ValueError("Apple source proof producer differs from caller authority")
        version = require_semver(proof.get("version"), "Apple source SDK version")
        if git_versions["sdk"] != (version + "\n").encode():
            raise ValueError("Apple source SDK version differs from its original Git source")

        for execution_path, contents in git_sources.items():
            if _read(captured["execution"] / execution_path) != contents:
                raise ValueError(f"Apple retained source differs from original Git: {execution_path}")
        for execution_path, lane_path in _LANE_TREES.items():
            if not _same_tree(captured["execution"] / execution_path, captured["lane"] / lane_path):
                raise ValueError(f"Apple retained execution differs from its original lane: {execution_path}")
        for distribution_path, lane_path in _LANE_REPORTS.items():
            if _read(captured["distribution"] / distribution_path) != _read(captured["lane"] / lane_path):
                raise ValueError(f"Apple retained report differs from its original lane: {distribution_path}")

        private_bundle = private_expected["contract"]
        manifest = verify_contract_bundle(private_bundle)
        with zipfile.ZipFile(private_bundle) as archive:
            manifest_bytes = archive.read("contract-manifest.json")
            canonical = {
                name: archive.read(f"evidence/{name}")
                for name in ("canonical-api.json", "canonical-coverage.json")
            }
        components = {record["component"]: record["sha256"] for record in projection["componentDigests"]}
        if (sha256_bytes(expected_bytes["contract"]) != projection["bundleSha256"]
                or sha256_bytes(manifest_bytes) != projection["manifestSha256"]
                or manifest["contractVersion"] != projection["contractVersion"]
                or manifest["contractDigest"] != projection["contractDigest"]
                or manifest["canonicalCoverageDigest"] != projection["canonicalCoverageDigest"]
                or any(manifest["components"].get(name, {}).get("sha256") != digest
                       for name, digest in components.items())):
            raise ValueError("Apple source Contract bundle differs from its authenticated projection")
        if git_versions["contract"] != (projection["contractVersion"] + "\n").encode():
            raise ValueError("Apple source Contract version differs from its original Git source")
        for name, data in canonical.items():
            if _read(captured["execution"] / "canonical" / name) != data:
                raise ValueError("Apple canonical evidence differs from its authenticated Contract")

        verify_sdk_apple_original_execution(
            distribution_directory=captured["distribution"],
            execution_directory=captured["execution"],
            expected_sdk_compatibility=private_expected["compatibility"],
            expected_distribution_proof=private_expected["proof"],
            repository=repository,
            tooling_evidence=tooling_evidence,
            tooling_public_key=tooling_public_key,
            java_executable=java_executable,
            policy_revision=policy_revision,
            required_trust_domain=required_trust_domain,
            tooling_keyring=tooling_keyring,
            tooling_keys_directory=tooling_keys_directory,
        )

        if any(_inventory(path, allow_empty=name != "distribution") != originals[name]
               for name, path in directories.items()) or any(
                   _inventory(captured[name], allow_empty=name != "distribution") != originals[name]
                   for name in directories):
            raise ValueError("Original or captured Apple source evidence changed during verification")
        if _read(impact_plan) != plan_bytes or any(
            _read(impact_plan.parent / "inventories/ios-swift-tests" / name) != data
            for name, data in plan_inventories.items()
        ) or _read(private_plan) != plan_bytes or any(
            _read(plan_root / "inventories/ios-swift-tests" / name) != data
            for name, data in plan_inventories.items()
        ):
            raise ValueError("Original or captured Apple source plan changed during verification")
        if any(read_regular_file_bytes(
                   path, max_bytes=_BUNDLE_LIMIT if name == "contract" else _LIMIT,
                   reject_symlink_parents=True,
               ) != expected_bytes[name] or read_regular_file_bytes(
                   private_expected[name], max_bytes=_BUNDLE_LIMIT if name == "contract" else _LIMIT,
                   reject_symlink_parents=True,
               ) != expected_bytes[name]
               for name, path in expected_paths.items()):
            raise ValueError("Original or captured Apple source caller input changed during verification")
        if any(git_regular_blob_bytes(repository, commit, source, max_bytes=_LIMIT) != git_sources[target]
               for target, source in _GIT_SOURCES.items()) or any(
            git_regular_blob_bytes(
                repository, commit, f"gradle/release/versions/{product}.txt", max_bytes=256,
            ) != contents for product, contents in git_versions.items()
        ):
            raise ValueError("Apple original Git source changed during verification")
