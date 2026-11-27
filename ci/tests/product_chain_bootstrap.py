"""Optional self-consistent Mac bootstrap fixture, never compiler/host acceptance.

All Contract capabilities intentionally share one synthetic reference/test. This
exercises authenticated byte closure and semantic keys, NOT the Kotlin matcher's
per-capability correspondence or actual native execution.
"""

from pathlib import Path
from typing import Any
import zipfile

from ci.products.c_abi import C_ABI_REPOSITORY_ROOT, COMPILE_ONLY_CONSUMERS
from ci.products.contract_model import _canonical_api_projection, _execution_tree_digest
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, sha256_bytes, sha256_file,
)
from ci.products.sdk_runtime_content import _bootstrap_content


def write_synthetic_bootstrap(
    bootstrap: Path, reference: Path, c_abi_sdk: Path, contract: dict[str, Any],
) -> None:
    """Retain original fixture inputs and emit a deterministic synthetic closure."""
    with zipfile.ZipFile(contract["payload"]) as archive:
        manifest = load_canonical_json_bytes(archive.read("contract-manifest.json"))
        api = _canonical_api_projection({
            f"evidence/{name}": archive.read(f"evidence/{name}")
            for name in ("canonical-api.json", "canonical-coverage.json")
        })
    test_class = "io.github.codex_agent_labs.codexagent.capi.SyntheticBootstrapFixture"
    test_name = "syntheticBootstrap[macosArm64]"
    test_id = f"macosArm64Test.{test_class}#{test_name}"
    files = {
        "reference/codex_agent_c.def": (
            C_ABI_REPOSITORY_ROOT / "codex-agent-runtime-desktop/src/nativeInterop/cinterop/codex_agent_c.def"
        ).read_bytes(),
        "original-runner/compiler-header/libcodex_agent_api.h":
            b"S786 synthetic compiler header; not Kotlin Native output\n",
        "original-runner/test.kexe": b"S786 synthetic native runner; never executed\n",
        "original-runner/source/nativeMain/Fixture.kt": b"// S786 synthetic native implementation fixture\n",
        "original-runner/source/nativeTest/Fixture.kt": b"// S786 synthetic native test fixture\n",
        f"native-junit/TEST-testImportedMacosArm64CAbi.{test_class}.xml": (
            '<testsuite tests="1" skipped="0" failures="0" errors="0">\n'
            f'  <testcase classname="testImportedMacosArm64CAbi.{test_class}" name="{test_name}"/>\n'
            '</testsuite>\n'
        ).encode(),
    }
    consumers = []
    for source in sorted((reference / "consumer").iterdir()):
        identity = f"synthetic-{source.name}"
        executed = source.name not in COMPILE_ONLY_CONSUMERS
        artifact = f"consumers/{identity}" + ("" if executed else ".o")
        files[artifact] = f"S786 synthetic compiled artifact for {source.name}; never compiled or executed\n".encode()
        consumers.append({
            "id": identity, "sourceSha256": sha256_file(source)[7:],
            "artifactSha256": sha256_bytes(files[artifact])[7:], "executed": executed,
        })
    for name, data in files.items():
        path = bootstrap / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    artifact_files = {
        "reviewedHeaderSha256": reference / "include/codex_agent.h",
        "exportPolicySha256": reference / "export-policy/macos.exports",
        "cinteropDefinitionSha256": bootstrap / "reference/codex_agent_c.def",
        "generatedHeaderSha256": bootstrap / "original-runner/compiler-header/libcodex_agent_api.h",
        "releaseLibrarySha256": c_abi_sdk / "lib/libcodex_agent.dylib",
        "nativeTestExecutableSha256": bootstrap / "original-runner/test.kexe",
    }
    artifact_trees = {
        "nativeMainSourcesSha256": bootstrap / "original-runner/source/nativeMain",
        "nativeTestSourcesSha256": bootstrap / "original-runner/source/nativeTest",
        "nativeTestResultsSha256": bootstrap / "native-junit",
    }
    symbols = [line.removeprefix("_") for line in
               (reference / "export-policy/macos.exports").read_text().splitlines()]
    keys = api["memberKeys"]
    report = {
        "schemaVersion": 1, "protocol": "codex-agent-c-abi-bootstrap-evidence-v1",
        "result": "observed", "milestone": "D104", "language": "c-abi",
        "canonical": {
            **api["canonical"], "nativeTargetSha256": api["targetSha256"]["native"],
            "capabilityCount": len(keys), "observedCapabilityCount": len(keys),
            "observedCapabilitySha256": sha256_bytes("".join(key + "\n" for key in keys).encode())[7:],
            "observedCapabilityKeys": keys, "missingCapabilityKeys": [],
        },
        "toolchain": {"clang": "/synthetic/clang", "clangCpp": "/synthetic/clang++",
                      "clangVersion": "S786 synthetic tool identity; no compiler ran", "macosSdk": "/synthetic/sdk"},
        "artifacts": {
            **{name: sha256_file(path)[7:] for name, path in artifact_files.items()},
            **{name: _execution_tree_digest(path) for name, path in artifact_trees.items()},
            "fileIdentity": "S786 synthetic library fixture", "installName": "@rpath/libcodex_agent.dylib",
        },
        "compilerConsumers": consumers,
        "linkedPublicSymbols": symbols,
        "nativeTests": [{"testId": test_id, "status": "passed"}],
        "claims": [{"capabilityKey": key, "headerReferences": ["codex_agent_abi_version"],
                    "consumerReferences": ["codex_agent_abi_version"], "publicSymbols": ["codex_agent_abi_version"],
                    "nativeTestIds": [test_id]} for key in keys],
    }
    raw = bootstrap / "bootstrap-evidence.json"
    raw.write_bytes(canonical_json_bytes(report))
    (bootstrap / "bootstrap-content.json").write_bytes(canonical_json_bytes(_bootstrap_content(raw, manifest, api)))
