"""Separate executed native validation evidence from reusable content bytes."""

from __future__ import annotations

from pathlib import Path

from .c_abi import (
    CAbiPackageInput, COMPILE_ONLY_CONSUMERS, GNU_CONSUMERS, STRICT_CONSUMERS, TARGET_SPECS,
    _repository_contract, _sorted_newline_sha256, c_abi_archive_file_name,
    c_abi_expected_symbols, c_abi_linux_symbol_versions,
    inspect_c_abi_package, portable_verify_c_abi_package_evidence,
)
from .inventory import (
    load_canonical_json_bytes, load_json_bytes, read_regular_file_bytes, require_exact_keys, require_regular_directory,
    require_sha256, sha256_bytes, write_canonical_json,
)
from .receipt import verify_output_manifest_identity, write_output_manifest
from .runtime_evidence import (
    DESKTOP_KEYS, DESKTOP_RUNTIME_TEST_CLASS, DESKTOP_RUNTIME_TEST_METHODS,
    PRODUCT_RUNTIME_TARGETS, RUNTIME_TARGETS, _check_common_report,
    desktop_test_task, imported_desktop_test_task,
)


_C_ABI_PROJECTION_KEYS = {
    "schemaVersion", "artifactId", "target", "classifier", "libraryVersion", "runnerOs", "runnerArch",
    "abiCurrent", "abiMinimum", "abiEncoded", "archiveSha256", "headerSha256", "libraryPath",
    "librarySha256", "publicSymbolCount", "publicSymbolsSha256", "publicSymbols", "publicSymbolVersions",
    "format", "architecture", "loaderIdentity", "versionIdentity", "importLibraries", "tools",
    "consumers", "gnuConsumers", "result",
}


def verify_projected_c_abi_evidence(
    target: str, library_version: str, producer_commit: str, producer_tree: str,
    archive: Path, evidence: Path, reviewed_header: Path, license: Path, notice: Path,
    export_policy: Path, consumer_sources, output_directory: Path | None = None,
) -> dict:
    """Verify reusable C ABI facts; raw compile hashes stay in original transport."""
    spec = TARGET_SPECS[target]
    report = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(
        Path(evidence), reject_symlink_parents=True)), _C_ABI_PROJECTION_KEYS, "Projected C ABI evidence")
    contract = _repository_contract()
    if (type(report["schemaVersion"]) is not int or report["schemaVersion"] != 2 or report["artifactId"] != spec.proof_id
            or report["target"] != target or report["classifier"] != spec.classifier
            or report["libraryVersion"] != library_version or report["runnerOs"] != spec.runner_os
            or report["runnerArch"] != spec.runner_arch or report["abiCurrent"] != contract.current.line
            or report["abiMinimum"] != contract.minimum_compatible.line
            or report["abiEncoded"] != contract.current.encoded_hex or report["format"] != spec.format
            or report["architecture"] != spec.architecture or report["loaderIdentity"] != spec.loader_identity
            or report["versionIdentity"] != spec.version_identity or report["result"] != "passed"):
        raise ValueError("Projected C ABI product/runner/ABI identity mismatch")
    sources = tuple(sorted((Path(path) for path in consumer_sources), key=lambda path: path.name))
    if len(sources) != len(STRICT_CONSUMERS) or {path.name for path in sources} != STRICT_CONSUMERS:
        raise ValueError("Projected C ABI strict consumer inventory is incomplete")
    source_bytes = {path.name: read_regular_file_bytes(path, reject_symlink_parents=True) for path in sources}
    if any(not contents for contents in source_bytes.values()):
        raise ValueError("Projected C ABI consumer sources are empty")
    expected_sources = {name: sha256_bytes(contents).removeprefix("sha256:")
                        for name, contents in source_bytes.items()}
    if (type(report["tools"]) is not list
            or any(type(item) is not dict for item in report["tools"])
            or [item.get("id") for item in report["tools"]] != sorted(spec.required_tool_ids)):
        raise ValueError("Projected C ABI tool inventory mismatch")
    for tool in report["tools"]:
        require_exact_keys(tool, {"id", "outputSha256"}, "Projected C ABI tool")
        require_sha256("sha256:" + tool["outputSha256"], "Projected C ABI tool digest")
    tools = {item["id"]: item["outputSha256"] for item in report["tools"]}
    for group, names in (("consumers", STRICT_CONSUMERS),
                         ("gnuConsumers", GNU_CONSUMERS if spec.format == "pe" else frozenset())):
        proofs = report[group]
        if (type(proofs) is not list or any(type(item) is not dict for item in proofs)
                or [item.get("source") for item in proofs] != sorted(names)):
            raise ValueError(f"Projected C ABI {group} identity mismatch")
        for proof in proofs:
            require_exact_keys(proof, {"source", "sourceSha256", "language", "compilerIdentitySha256",
                                       "compileOutputSha256", "linked", "executed", "exitCode"},
                               "Projected C ABI consumer")
            linked = group == "gnuConsumers" or proof["source"] not in COMPILE_ONLY_CONSUMERS
            language = "c++17" if proof["source"].endswith(".cpp") else "c11"
            compiler = (("gnuCpp" if language == "c++17" else "gnuC")
                        if group == "gnuConsumers" else ("cpp" if language == "c++17" else "c"))
            if (proof["sourceSha256"] != expected_sources[proof["source"]]
                    or proof["language"] != language or proof["compilerIdentitySha256"] != tools[compiler]
                    or proof["linked"] is not linked or proof["executed"] is not linked
                    or type(proof["exitCode"]) is not int or proof["exitCode"] != 0):
                raise ValueError("Projected C ABI consumer execution mismatch")
            for field in ("compilerIdentitySha256", "compileOutputSha256"):
                require_sha256("sha256:" + proof[field], f"Projected C ABI {field}")
    # The package verifier checks exact archive layout, bytes, header, symbols,
    # export policy and import libraries independently of the validation report.
    from .c_abi import _extract_package
    import tempfile
    with tempfile.TemporaryDirectory(prefix="projected-c-abi-") as temporary:
        root = Path(temporary) / "sdk"
        _extract_package(Path(archive), root)
        package_input = CAbiPackageInput(
            target, spec.classifier, library_version, producer_commit, producer_tree,
            Path(reviewed_header), Path(license), Path(notice), root / spec.library_path,
            Path(export_policy),
            root / spec.import_library_paths[0] if spec.import_library_paths else None,
            root / spec.import_library_paths[1] if len(spec.import_library_paths) > 1 else None,
        )
        snapshot = inspect_c_abi_package(Path(archive), package_input)
    symbols = sorted(c_abi_expected_symbols(Path(export_policy)))
    versions = c_abi_linux_symbol_versions(Path(export_policy)) if spec.format == "elf" else {}
    if (report["archiveSha256"] != snapshot.archive_sha256
            or report["headerSha256"] != snapshot.header_sha256
            or report["librarySha256"] != snapshot.library_sha256
            or report["libraryPath"] != spec.library_path
            or type(report["publicSymbolCount"]) is not int
            or report["publicSymbolCount"] != len(symbols) or report["publicSymbols"] != symbols
            or report["publicSymbolVersions"] != [{"symbol": symbol, "version": version}
                                                    for symbol, version in sorted(versions.items())]
            or report["publicSymbolsSha256"] != snapshot.public_symbols_sha256
            or report["publicSymbolsSha256"] != _sorted_newline_sha256(report["publicSymbols"])
            or report["importLibraries"] != [{"path": path, "sha256": snapshot.members[path]}
                                               for path in sorted(spec.import_library_paths)]):
        raise ValueError("Projected C ABI package digest or symbol identity mismatch")
    if output_directory is not None:
        from .c_abi import C_ABI_STAGED_EVIDENCE_PATH, _publish_immutable_directory
        with tempfile.TemporaryDirectory(prefix="projected-c-abi-stage-") as temporary:
            root = Path(temporary) / "sdk"
            _extract_package(Path(archive), root)
            (root / C_ABI_STAGED_EVIDENCE_PATH).write_bytes(read_regular_file_bytes(
                Path(evidence), reject_symlink_parents=True))
            Path(output_directory).parent.mkdir(parents=True, exist_ok=True)
            _publish_immutable_directory(root, Path(output_directory))
    return report


def project_native_validation_stage(
    stage: Path, package_stage: Path, diagnostic_root: Path, *, target: str,
    version: str, producer: dict,
) -> None:
    """Verify raw Gradle evidence, keep it in transport, then stage stable facts.

    The original raw reports remain outside the reusable phase object. Its
    immutable worker upload and original receipt retain run/producer custody.
    """
    evidence_target = next((name for name, product in PRODUCT_RUNTIME_TARGETS.items()
                            if product == target), None)
    if evidence_target is None or target not in {spec.classifier.removeprefix("c-abi-")
                                                  for spec in TARGET_SPECS.values()}:
        raise ValueError("Unsupported native Runtime validation target")
    stage = require_regular_directory(Path(stage), "Native validation stage")
    package_stage = require_regular_directory(Path(package_stage), "Original Runtime package stage")
    original = verify_output_manifest_identity(stage, "runtime", target, "validation", target, version)
    desktop_path = stage / "outputs/native" / f"desktop-runtime-{evidence_target}.json"
    c_abi_path = stage / "outputs/c-abi" / f"c-abi-package-{target}.json"
    desktop_bytes = read_regular_file_bytes(desktop_path, reject_symlink_parents=True)
    c_abi_bytes = read_regular_file_bytes(c_abi_path, reject_symlink_parents=True)
    desktop = require_exact_keys(load_json_bytes(desktop_bytes), DESKTOP_KEYS, "Raw Desktop validation")
    spec = RUNTIME_TARGETS[evidence_target]
    if (desktop["candidateCommit"] != producer["commit"] or desktop["target"] != evidence_target
            or desktop["classifier"] != spec.classifier or desktop["runnerOs"] != spec.runner_os
            or desktop["runnerArch"] != spec.runner_arch or desktop["result"] != "passed"):
        raise ValueError("Raw Desktop validation differs from its original producer or target")
    _check_common_report(desktop, schema=3, target=evidence_target, commit=producer["commit"],
                         test_class=DESKTOP_RUNTIME_TEST_CLASS,
                         test_methods=DESKTOP_RUNTIME_TEST_METHODS)
    if desktop["testTask"] not in {desktop_test_task(evidence_target),
                                   imported_desktop_test_task(evidence_target)}:
        raise ValueError("Raw Desktop validation test task mismatch")
    c_abi = load_json_bytes(c_abi_bytes)
    if (type(c_abi) is not dict or c_abi.get("producerCommit") != producer["commit"]
            or c_abi.get("producerTree") != producer["tree"] or c_abi.get("target") != evidence_target):
        raise ValueError("Raw C ABI validation differs from its original producer or target")
    classifier_archive = (package_stage / "outputs/app-server" /
                          f"codex-agent-runtime-desktop-{c_abi['libraryVersion']}-{spec.classifier}.zip")
    if sha256_bytes(read_regular_file_bytes(classifier_archive, reject_symlink_parents=True)) != (
            "sha256:" + desktop["classifierArchiveSha256"]):
        raise ValueError("Raw Desktop validation classifier package mismatch")
    c_abi_spec = TARGET_SPECS[evidence_target]
    reference = stage / "outputs/c-abi-reference"
    policy = {"mach-o": "macos.exports", "elf": "linux.map", "pe": "windows.def"}[c_abi_spec.format]
    portable_verify_c_abi_package_evidence(
        evidence_target, c_abi["libraryVersion"], producer["commit"], producer["tree"],
        package_stage / "outputs/c-abi" / c_abi_archive_file_name(c_abi["libraryVersion"], evidence_target),
        c_abi_path, reference / "include/codex_agent.h", reference / "legal/LICENSE",
        reference / "legal/THIRD_PARTY_NOTICES.md", reference / "export-policy" / policy,
        tuple((reference / "consumer").iterdir()),
    )
    for group in ("consumers", "gnuConsumers"):
        for consumer in c_abi[group]:
            require_sha256("sha256:" + consumer["artifactSha256"], "Transient C ABI consumer artifact")
    diagnostic_root = Path(diagnostic_root)
    diagnostic_root.mkdir(parents=True, exist_ok=False)
    (diagnostic_root / desktop_path.name).write_bytes(desktop_bytes)
    (diagnostic_root / c_abi_path.name).write_bytes(c_abi_bytes)
    desktop_projection, c_abi_projection = _project_verified_reports(desktop, c_abi)
    write_canonical_json(desktop_path, desktop_projection)
    write_canonical_json(c_abi_path, c_abi_projection)
    roots = {kind: f"outputs/{kind}" for kind in
             ("c-abi", "c-abi-reference", "native", "execution")}
    if target == "macos-arm64":
        roots["c-abi-bootstrap"] = "outputs/c-abi-bootstrap"
    rewritten = write_output_manifest(stage, "runtime", target, "validation", target, version,
                                        roots, expected_output_paths=[item["relativePath"]
                                                                      for item in original["outputs"]])
    if ([(item["kind"], item["relativePath"]) for item in rewritten["outputs"]]
            != [(item["kind"], item["relativePath"]) for item in original["outputs"]]):
        raise ValueError("Native validation projection changed the declared output set")


def _project_verified_reports(desktop: dict, c_abi: dict) -> tuple[dict, dict]:
    """Project only after raw execution and package proof have been verified."""
    desktop_projection = {name: value for name, value in desktop.items()
                          if name not in {"candidateCommit", "testTask"}}
    desktop_projection["schemaVersion"] = 4
    c_abi_projection = {name: value for name, value in c_abi.items()
                        if name not in {"producerCommit", "producerTree"}}
    c_abi_projection["schemaVersion"] = 2
    for group in ("consumers", "gnuConsumers"):
        c_abi_projection[group] = [{name: value for name, value in consumer.items()
                                    if name != "artifactSha256"} for consumer in c_abi[group]]
    return desktop_projection, c_abi_projection
