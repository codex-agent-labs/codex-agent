"""Deterministic bootstrap content, emitted only after the full Runtime raw gate.

This projector is not an authentication or reuse-admission API. Original raw
compiler/JUnit evidence and receipts remain mandatory external proof.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from typing import Any

from .contract_model import (
    _canonical_api_projection, _execution_tree_digest, _verify_extracted_contract_directory,
    validate_contract_manifest,
)
from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, load_json_bytes, read_regular_file_bytes,
    regular_file_inventory, require_array, require_exact_keys, require_integer,
    require_relative_path, require_sha256, sha256_bytes,
)
from .test_results import read_canonical_test_report


def _record(value: Any, label: str, *, multiline: bool = False) -> str:
    if type(value) is not str or not value or value != value.strip() or any(
        ord(char) < 32 and not (multiline and char == "\n") for char in value
    ) or "\x7f" in value:
        raise ValueError(f"Invalid bootstrap {label}")
    return value


def _strings(value: Any, label: str) -> list[str]:
    rows = [_record(row, label) for row in require_array(value, label)]
    if not rows or rows != sorted(set(rows)):
        raise ValueError(f"Bootstrap {label} must be exact sorted unique records")
    return rows


def _digest(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64:
        raise ValueError(f"Invalid bootstrap {label} digest")
    return require_sha256("sha256:" + value, label)


def bootstrap_content(raw: Path, contract_directory: Path) -> dict[str, Any]:
    """Project validated raw facts; never replace the original full compiler gate."""
    manifest, api = _verify_extracted_contract_directory(
        contract_directory, required_components=("common", "macos-arm64"),
        include_canonical_api_projection=True,
    )
    assert api is not None
    return _bootstrap_content(raw, manifest, api)


def _bootstrap_content(raw: Path, manifest: dict, api: dict) -> dict[str, Any]:
    """Shared content model; caller must authenticate the original Contract first."""
    data = read_regular_file_bytes(raw, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    report = require_exact_keys(load_json_bytes(data), {
        "schemaVersion", "protocol", "result", "milestone", "language", "canonical",
        "toolchain", "artifacts", "compilerConsumers", "linkedPublicSymbols", "nativeTests", "claims",
    }, "C ABI bootstrap")
    if require_integer(report["schemaVersion"], "bootstrap schema", 1) != 1 or (
        report["protocol"], report["result"], report["milestone"], report["language"]
    ) != ("codex-agent-c-abi-bootstrap-evidence-v1", "observed", "D104", "c-abi"):
        raise ValueError("Bootstrap identity is not exact observed D104 c-abi evidence")
    canonical = require_exact_keys(report["canonical"], {
        "apiReportSha256", "coverageReceiptSha256", "nativeTargetSha256", "capabilityCount",
        "observedCapabilityCount", "observedCapabilitySha256", "observedCapabilityKeys", "missingCapabilityKeys",
    }, "bootstrap canonical")
    for name in ("apiReportSha256", "coverageReceiptSha256"):
        if canonical[name] != api["canonical"][name]:
            raise ValueError(f"Bootstrap {name} differs from verified Contract")
    if canonical["nativeTargetSha256"] != api["targetSha256"]["native"]:
        raise ValueError("Bootstrap native target differs from verified Contract")
    keys = _strings(canonical["observedCapabilityKeys"], "capability keys")
    if keys != api["memberKeys"] or canonical["missingCapabilityKeys"] != [] or any(
        require_integer(canonical[name], name, 1) != 556
        for name in ("capabilityCount", "observedCapabilityCount")
    ) or _digest(canonical["observedCapabilitySha256"], "capability") != sha256_bytes(
        "".join(key + "\n" for key in keys).encode("utf-8")
    ):
        raise ValueError("Bootstrap capability partition differs from verified Contract")
    toolchain = require_exact_keys(report["toolchain"], {
        "clang", "clangCpp", "clangVersion", "macosSdk",
    }, "bootstrap toolchain")
    for name, value in toolchain.items():
        _record(value, name, multiline=name == "clangVersion")
    artifacts = require_exact_keys(report["artifacts"], {
        "reviewedHeaderSha256", "cinteropDefinitionSha256", "exportPolicySha256", "generatedHeaderSha256",
        "releaseLibrarySha256", "nativeTestExecutableSha256", "nativeMainSourcesSha256",
        "nativeTestSourcesSha256", "nativeTestResultsSha256", "fileIdentity", "installName",
    }, "bootstrap artifacts")
    for name, value in artifacts.items():
        _digest(value, name) if name.endswith("Sha256") else _record(value, name)
    consumers = []
    for row in require_array(report["compilerConsumers"], "bootstrap compiler consumers"):
        consumer = require_exact_keys(row, {
            "id", "sourceSha256", "artifactSha256", "executed",
        }, "bootstrap compiler consumer")
        _record(consumer["id"], "consumer id")
        _digest(consumer["artifactSha256"], "consumer artifact")
        if type(consumer["executed"]) is not bool:
            raise ValueError("Bootstrap consumer executed must be boolean")
        consumers.append({
            "id": consumer["id"], "sourceSha256": _digest(consumer["sourceSha256"], "consumer source"),
            "executed": consumer["executed"],
        })
    consumer_ids = [row["id"] for row in consumers]
    if not consumers or len(consumer_ids) != len(set(consumer_ids)):
        raise ValueError("Bootstrap compiler consumers are missing or duplicated")
    symbols = _strings(report["linkedPublicSymbols"], "linked symbols")
    tests = []
    for row in require_array(report["nativeTests"], "bootstrap native tests"):
        test = require_exact_keys(row, {"testId", "status"}, "bootstrap native test")
        _record(test["testId"], "test ID")
        if test["status"] != "passed":
            raise ValueError("Bootstrap native test did not pass")
        tests.append(test)
    test_ids = _strings([row["testId"] for row in tests], "native test IDs")
    claims = []
    for row in require_array(report["claims"], "bootstrap claims"):
        claim = require_exact_keys(row, {
            "capabilityKey", "headerReferences", "consumerReferences", "publicSymbols", "nativeTestIds",
        }, "bootstrap claim")
        _record(claim["capabilityKey"], "claim key")
        for name in ("headerReferences", "consumerReferences", "publicSymbols", "nativeTestIds"):
            _strings(claim[name], name)
        if not set(claim["publicSymbols"]) <= set(symbols) or not set(claim["nativeTestIds"]) <= set(test_ids):
            raise ValueError("Bootstrap claim lacks passed test or linked symbol")
        claims.append(claim)
    if [row["capabilityKey"] for row in claims] != keys:
        raise ValueError("Bootstrap claims do not match the exact Contract capability set")
    if read_regular_file_bytes(raw, reject_symlink_parents=True) != data:
        raise ValueError("Bootstrap raw evidence changed during projection")
    return {
        "schemaVersion": 1, "kind": "runtime-c-abi-bootstrap-content", "target": "macos-arm64",
        "contractDigest": manifest["contractDigest"],
        "contractComponentDigest": manifest["components"]["macos-arm64"]["sha256"],
        "canonicalApiDigest": manifest["canonicalApiDigest"],
        "canonicalCoverageDigest": manifest["canonicalCoverageDigest"],
        "capabilityCount": 556,
        "artifacts": {name: _digest(artifacts[name], name) for name in (
            "reviewedHeaderSha256", "cinteropDefinitionSha256", "exportPolicySha256",
            "releaseLibrarySha256", "nativeMainSourcesSha256", "nativeTestSourcesSha256",
        )},
        "compilerConsumers": sorted(consumers, key=lambda row: row["id"]),
        "linkedPublicSymbols": symbols, "nativeTests": tests, "claims": claims,
    }


def _verify_bootstrap_handoff(inputs: Path) -> None:
    """Rehash the private H already bound to authenticated original phase outputs.

    This is not standalone receipt/host admission. The SDK input verifier owns
    original signatures, inventories and plans; the Kotlin matcher still owns
    exact per-capability/scenario correspondence. No imported code is executed.
    """
    bootstrap, reference = inputs / "bootstrap", inputs / "bootstrap-reference"
    contract, sdk = inputs / "contract", inputs / "sdks/macos-arm64"
    roots = (bootstrap, reference, contract, sdk)
    before = [regular_file_inventory(root) for root in roots]
    manifest = validate_contract_manifest(load_canonical_json_bytes(
        read_regular_file_bytes(contract / "contract-manifest.json", reject_symlink_parents=True)))
    api = _canonical_api_projection({f"evidence/{name}": read_regular_file_bytes(contract / name)
                                     for name in ("canonical-api.json", "canonical-coverage.json")})
    raw = bootstrap / "bootstrap-evidence.json"
    content = _bootstrap_content(raw, manifest, api)
    report = load_json_bytes(read_regular_file_bytes(raw))
    artifacts = report["artifacts"]
    for field, path in {
        "reviewedHeaderSha256": reference / "include/codex_agent.h",
        "cinteropDefinitionSha256": bootstrap / "reference/codex_agent_c.def",
        "exportPolicySha256": reference / "export-policy/macos.exports",
        "generatedHeaderSha256": bootstrap / "original-runner/compiler-header/libcodex_agent_api.h",
        "releaseLibrarySha256": sdk / "lib/libcodex_agent.dylib",
        "nativeTestExecutableSha256": bootstrap / "original-runner/test.kexe",
    }.items():
        if _digest(artifacts[field], field) != sha256_bytes(read_regular_file_bytes(path, reject_symlink_parents=True)):
            raise ValueError(f"Bootstrap raw artifact differs: {field}")
    for field, path in {
        "nativeMainSourcesSha256": bootstrap / "original-runner/source/nativeMain",
        "nativeTestSourcesSha256": bootstrap / "original-runner/source/nativeTest",
        "nativeTestResultsSha256": bootstrap / "native-junit",
    }.items():
        if artifacts[field] != _execution_tree_digest(path):
            raise ValueError(f"Bootstrap raw tree differs: {field}")
    sources = regular_file_inventory(reference / "consumer")
    consumed = []
    artifact_paths = []
    for consumer in report["compilerConsumers"]:
        identity = require_relative_path(consumer["id"], "Bootstrap compiler consumer ID")
        if "/" in identity:
            raise ValueError("Bootstrap compiler consumer ID must be a filename")
        matching = [record for record in sources if record["sha256"] == _digest(consumer["sourceSha256"], "source")]
        if len(matching) != 1:
            raise ValueError("Bootstrap compiler source is missing or ambiguous")
        consumed.append(read_regular_file_bytes(reference / "consumer" / matching[0]["relativePath"]))
        name = identity if consumer["executed"] else identity + ".o"
        artifact_paths.append(name)
        if _digest(consumer["artifactSha256"], "compiler artifact") != sha256_bytes(
            read_regular_file_bytes(bootstrap / "consumers" / name, reject_symlink_parents=True)
        ):
            raise ValueError("Bootstrap compiled consumer artifact differs")
    if sorted(artifact_paths) != [record["relativePath"] for record in regular_file_inventory(bootstrap / "consumers")]:
        raise ValueError("Bootstrap compiler artifact inventory differs")
    tests = []
    tasks = set()
    for path in sorted((bootstrap / "native-junit").iterdir()):
        if path.suffix != ".xml" or ".capi." not in path.name:
            continue  # Exact same report selection as the original Runtime producer.
        for test in read_canonical_test_report(path):
            task, _, suffix = test.test_id.partition(".")
            tasks.add(task)
            if (task not in {"macosArm64Test", "testImportedMacosArm64CAbi"}
                    or not suffix.startswith("io.github.codex_agent_labs.codexagent.capi.")
                    or not suffix.endswith("[macosArm64]")):
                raise ValueError("Bootstrap JUnit has a foreign task/package/target")
            tests.append({"testId": "macosArm64Test." + suffix, "status": test.status.value})
    if len(tasks) != 1 or sorted(tests, key=lambda row: row["testId"]) != report["nativeTests"]:
        raise ValueError("Bootstrap raw JUnit differs from the exact passed native test inventory")
    symbols = read_regular_file_bytes(reference / "export-policy/macos.exports").decode("utf-8").splitlines()
    if symbols != ["_" + symbol for symbol in report["linkedPublicSymbols"]]:
        raise ValueError("Bootstrap linked symbols differ from authenticated export policy")
    header = read_regular_file_bytes(reference / "include/codex_agent.h").decode("utf-8")
    consumer_text = "\n".join(source.decode("utf-8") for source in consumed)
    for claim in report["claims"]:
        for field, text in (("headerReferences", header), ("consumerReferences", consumer_text)):
            if any(re.search(r"(?<![A-Za-z0-9_])" + re.escape(value) + r"(?![A-Za-z0-9_])", text) is None
                   for value in claim[field]):
                raise ValueError(f"Bootstrap claim lacks authenticated {field}")
    if canonical_json_bytes(content) != read_regular_file_bytes(bootstrap / "bootstrap-content.json"):
        raise ValueError("Bootstrap content sidecar differs from its authenticated raw closure")
    if before != [regular_file_inventory(root) for root in roots]:
        raise ValueError("Bootstrap private inputs changed during verification")


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("bootstrap",))
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--contract-directory", type=Path, required=True)
    args = parser.parse_args(arguments)
    sys.stdout.buffer.write(canonical_json_bytes(bootstrap_content(args.raw, args.contract_directory)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
