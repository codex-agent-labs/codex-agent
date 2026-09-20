"""Translate caller-authenticated iOS validation inputs; no execution or admission."""

from pathlib import Path
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.inventory import require_semver
from sdk_ios_phase import _directory, _request, _GIT_ID


def validation_properties(*, target, sdk_version, contract_version, candidate_tree,
                          package_stage: Path, contract_binary_stage: Path,
                          sdk_compatibility: Path, test_application: Path,
                          compiler_consumers: Path) -> dict[str, str]:
    """Map exact original paths to imported-only validation properties.

    The caller must authenticate the selected phase, original receipts/stages,
    compatibility bytes, test-application and compiler-consumer sources before
    using this mapper. Path and version checks
    here do not establish source, signature, Apple host or semantic authority.
    Tree IDs follow the current receipt producer contract: 40 lowercase hex.
    """
    if type(target) is not str or target not in ("ios-arm64", "ios-simulator-arm64"):
        raise ValueError("iOS SDK validation requires an exact iOS target")
    version = require_semver(sdk_version, "Selected SDK version")
    contract = require_semver(contract_version, "Original Contract version")
    if type(candidate_tree) is not str or _GIT_ID.fullmatch(candidate_tree) is None:
        raise ValueError("iOS SDK validation requires an exact candidate tree")
    consumers = _directory(compiler_consumers, "Authenticated iOS validation compiler consumers")
    for name in ("CodexFailureSwiftConsumer.swift", "CodexFailureObjectiveCConsumer.m"):
        _request(compiler_consumers / name, "Authenticated iOS validation compiler consumer")
    return {
        "codexAgent.product": "sdk",
        "codexAgent.component": "sdk-ios",
        "codexAgent.phase": "validation",
        "codexAgent.target": target,
        "codexAgent.iosValidationPackageStage": _directory(package_stage, "Original iOS SDK package stage"),
        "codexAgent.contractBinaryStage": _directory(contract_binary_stage, "Original Contract binary stage"),
        "codexAgent.sdkCompatibilityFile": _request(sdk_compatibility, "Authenticated SDK compatibility"),
        "codexAgent.iosValidationTestApplicationDirectory": _directory(
            test_application, "Authenticated iOS validation test application"),
        "codexAgent.iosValidationCompilerConsumersDirectory": consumers,
        "codexAgent.sdkVersion": version,
        "codexAgent.contractVersion": contract,
        "codexAgent.candidateTree": candidate_tree,
    }
