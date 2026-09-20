"""Deterministic content projection, never Apple validation authority.

The caller must first authenticate the original package/Contract and replay the
full compiler, XCTest, device and binding evidence gates. These structural
checks do not replace any of those gates or establish complete API coverage.
Original receipts and execution evidence remain external to this content.
"""

from typing import Any

from .inventory import (
    canonical_json_bytes,
    load_json_bytes,
    require_array,
    require_exact_keys,
    require_integer,
    require_semver,
    require_sha256,
    require_string,
)


_LANGUAGES = ("objective-c", "swift")
_CANONICAL_FIELDS = {"apiReportSha256", "coverageReceiptSha256"}
_SEMANTIC_FIELDS = ("phase", "language", "publicSymbols", "tests", "scenarios", "claims", "exclusions")
_RECEIPT_FIELDS = {
    "schema", "result", "canonical", "artifacts", "hostConsumerProofs",
    "testProgramSha256", "testResultsSha256", *_SEMANTIC_FIELDS,
}
_ARTIFACT_IDS = (
    "apple-binding-evidence", "apple-compiler-evidence", "apple-xctest-evidence",
    "codex-agent-xcframework",
)
# Existing CrossLanguageBindingScenario vocabulary, not a capability matcher.
_SCENARIOS = (
    "async-failure", "async-success", "cancellation", "collection-immutability-ordering",
    "identity", "nullability", "parent-child-ownership", "repeated-close-dispose",
    "state-current-value", "state-subsequent-value", "structured-failure",
    "subscription-cancellation", "terminal-delivery", "value-conversion",
)


def _raw_sha256(value: Any, label: str) -> str:
    value = require_string(value, label)
    require_sha256("sha256:" + value, label)
    return value


def _record(value: Any, label: str) -> str:
    value = require_string(value, label)
    if value != value.strip() or "*" in value or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value):
        raise ValueError(f"{label} is not an exact binding record")
    return value


def _strings(value: Any, label: str) -> list[str]:
    values = [_record(member, label) for member in require_array(value, label)]
    if not values or values != sorted(set(values)):
        raise ValueError(f"{label} must be nonempty, sorted and unique")
    return values


def _rows(value: Any, fields: set[str], key: str, label: str) -> list[dict[str, Any]]:
    rows = [require_exact_keys(row, fields, label) for row in require_array(value, label)]
    _strings([row[key] for row in rows], label)
    return rows


def _binding(receipt: Any, language: str, expected_canonical: dict[str, str]) -> dict[str, Any]:
    receipt = require_exact_keys(receipt, _RECEIPT_FIELDS, f"{language} receipt")
    if require_integer(receipt["schema"], "Apple receipt schema") != 4 or \
            receipt["result"] != "passed" or receipt["phase"] != "M8" or receipt["language"] != language:
        raise ValueError("Apple binding receipt identity is invalid")
    canonical = require_exact_keys(receipt["canonical"], _CANONICAL_FIELDS, "Apple canonical identity")
    if canonical != expected_canonical:
        raise ValueError("Apple receipt does not match caller-owned canonical identity")
    artifacts = _rows(receipt["artifacts"], {"id", "sha256"}, "id", "Apple artifacts")
    if tuple(row["id"] for row in artifacts) != _ARTIFACT_IDS:
        raise ValueError("Apple artifact inventory changed")
    for row in artifacts:
        _raw_sha256(row["sha256"], "Apple artifact SHA-256")
    for field in ("testProgramSha256", "testResultsSha256"):
        _raw_sha256(receipt[field], field)
    for field in ("hostConsumerProofs", "exclusions"):
        if require_array(receipt[field], field):
            raise ValueError(f"Apple {field} must be empty")

    symbols = set(_strings(receipt["publicSymbols"], "Apple public symbols"))
    tests = _rows(receipt["tests"], {"id", "status"}, "id", "Apple tests")
    if any(row["status"] != "passed" for row in tests):
        raise ValueError("Apple binding tests must pass")
    test_ids = {row["id"] for row in tests}
    scenarios = _rows(receipt["scenarios"], {"id", "testIds"}, "id", "Apple scenarios")
    if tuple(row["id"] for row in scenarios) != _SCENARIOS:
        raise ValueError("Apple shared scenario inventory changed")
    for row in scenarios:
        if not set(_strings(row["testIds"], "Apple scenario tests")).issubset(test_ids):
            raise ValueError("Apple scenario names an unknown test")
    claims = _rows(receipt["claims"], {
        "capabilityKey", "publicSymbols", "executedTests", "sharedScenarios",
    }, "capabilityKey", "Apple claims")
    for claim in claims:
        for field, known in (("publicSymbols", symbols), ("executedTests", test_ids),
                             ("sharedScenarios", set(_SCENARIOS))):
            if not set(_strings(claim[field], f"Apple claim {field}")).issubset(known):
                raise ValueError(f"Apple claim names unknown {field}")
    return {field: receipt[field] for field in _SEMANTIC_FIELDS}


def apple_validation_content(
    *,
    target: str,
    sdk_version: str,
    package_outputs_digest: str,
    contract_digest: str,
    expected_canonical: dict[str, str],
    binding_receipts: dict[str, Any],
) -> dict[str, Any]:
    """Project already verified receipts; the returned ordinary dict grants no authority.

    Expected canonical identity comes independently from the authenticated
    Contract caller. Its apiReportSha256 hashes the complete canonical report,
    NOT Contract's targets-independent semantic canonicalApiDigest. The caller
    separately supplies the authenticated package inventory and Contract digest.
    """
    if target not in ("ios-arm64", "ios-simulator-arm64"):
        raise ValueError("Apple validation target is invalid")
    canonical = require_exact_keys(expected_canonical, _CANONICAL_FIELDS, "Expected canonical identity")
    for field in _CANONICAL_FIELDS:
        _raw_sha256(canonical[field], f"Expected {field}")
    receipts = require_exact_keys(binding_receipts, _LANGUAGES, "Apple binding receipts")
    content = {
        "schemaVersion": 1,
        "kind": "sdk-apple-validation-content",
        "component": "sdk-ios",
        "target": target,
        "sdkVersion": require_semver(sdk_version, "SDK version"),
        "packageOutputsDigest": require_sha256(package_outputs_digest, "Package outputs digest"),
        "contractDigest": require_sha256(contract_digest, "Contract digest"),
        "canonical": canonical,
        "bindings": [_binding(receipts[language], language, canonical) for language in _LANGUAGES],
    }
    # Return independent content; subsequent mutations of original evidence must
    # not silently change what the caller serializes with the canonical writer.
    return load_json_bytes(canonical_json_bytes(content))
