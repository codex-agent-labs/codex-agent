from __future__ import annotations

import argparse
import fnmatch
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from typing import Any
import zipfile

from .contract_model import (
    CONTRACT_ARTIFACT_COMPONENTS,
    CONTRACT_COMPONENTS,
    CONTRACT_EVIDENCE_PATH_ROLES,
    contract_component_digest,
    contract_digest,
    contract_evidence_identity,
    contract_maven_identity,
    project_contract_execution_evidence,
    _snapshot_execution_tree,
    validate_contract_maven_inventory,
    validate_contract_manifest,
    verify_contract_git_inventories,
    verify_contract_bundle,
    verify_extracted_contract_directory,
    verify_extracted_contract_directory_projection,
)
from .inventory import (
    canonical_json_bytes,
    git_inventory as inventory,
    git_inventory_paths as inventory_paths,
    load_canonical_json_bytes,
    read_regular_file_bytes,
    publish_regular_tree,
    regular_file_inventory,
    require_array,
    require_exact_keys,
    require_integer,
    require_sha256,
    require_semver,
    run_git,
    sha256_bytes,
    sha256_file,
    snapshot_regular_tree,
    verified_zip_contents,
    write_canonical_json,
)
from .receipt import (
    output_inventory_digest,
    validate_phase_receipt,
    verify_output_manifest_identity,
)


def _maven_records(root: Path, contract_version: str) -> list[dict[str, Any]]:
    records = regular_file_inventory(root / "maven")
    result: list[dict[str, Any]] = []
    artifacts: set[str] = set()
    for record in records:
        identity = contract_maven_identity(f"maven/{record['relativePath']}", contract_version)
        artifacts.add(identity["artifact"])
        result.append({
            "path": f"maven/{record['relativePath']}",
            "role": identity["role"],
            "bytes": record["bytes"],
            "sha256": record["sha256"],
            "component": identity["component"],
        })
    if artifacts != set(CONTRACT_ARTIFACT_COMPONENTS):
        raise ValueError("Contract Maven repository does not contain exactly the 12 core publications")
    return validate_contract_maven_inventory(
        sorted(result, key=lambda record: record["path"]), contract_version,
    )


def _evidence_records(root: Path) -> list[dict[str, Any]]:
    records = [
        record for record in regular_file_inventory(root)
        if record["relativePath"].startswith(("evidence/", "inventories/"))
    ]
    actual = {record["relativePath"] for record in records}
    if actual != set(CONTRACT_EVIDENCE_PATH_ROLES):
        raise ValueError("Contract evidence staging tree is incomplete or unexpected")
    return [
        {
            "path": record["relativePath"],
            "role": CONTRACT_EVIDENCE_PATH_ROLES[record["relativePath"]],
            "bytes": record["bytes"],
            "sha256": record["sha256"],
        }
        for record in records
    ]


def _write_contract_zip(root: Path, output: Path, *, raw_execution: bool = False) -> None:
    records = regular_file_inventory(root, allow_empty=raw_execution)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for record in records:
            info = zipfile.ZipInfo(record["relativePath"], (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, (root / record["relativePath"]).read_bytes())


def verify_contract_execution_archive(
    archive: Path, *, semantic_root: Path | None = None,
) -> dict[str, Any]:
    records, contents, _ = verified_zip_contents(
        archive, canonical_stored=True, allow_empty_members=True,
        max_archive_bytes=512 * 1024 * 1024, max_total_bytes=512 * 1024 * 1024,
        max_members=16_384, max_entry_bytes=64 * 1024 * 1024,
    )
    evidence_paths = {path for path in CONTRACT_EVIDENCE_PATH_ROLES if path.startswith("evidence/")}
    if {path for path in contents if path.startswith("evidence/")} != evidence_paths or \
            any(not path.startswith(("evidence/", "compiled-tests/", "test-results/")) for path in contents) or \
            any(record["bytes"] == 0 and not record["relativePath"].startswith("test-results/") for record in records):
        raise ValueError("Contract execution archive has an invalid raw evidence inventory")
    with tempfile.TemporaryDirectory(prefix="contract-execution-verify-") as temporary:
        root = Path(temporary).resolve()
        for relative, data in contents.items():
            output = root / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(data)
        projection = project_contract_execution_evidence(root, root / "compiled-tests", root / "test-results")
        if semantic_root is not None:
            replacements = {
                "evidence/canonical-coverage.json": canonical_json_bytes(projection["coverage"]),
                "evidence/kotlin-parity.json": canonical_json_bytes(projection["kotlin"]),
            }
            for path in evidence_paths:
                actual = read_regular_file_bytes(semantic_root / path, reject_symlink_parents=True)
                if actual != replacements.get(path, contents[path]):
                    raise ValueError("Contract semantic evidence differs from its raw execution proof")
        return projection


def capture_contract_execution_evidence(
    staging_root: Path, compiled_tests: Path, test_results: Path,
) -> dict[str, Any]:
    """Finalize fresh stage evidence, preserving all original raw bytes externally."""
    root = Path(staging_root)
    destination = root / "execution/contract-execution.zip"
    _reject_symlinked_output_parent(destination, root)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Contract execution archive already exists; never rewrite original evidence")
    with tempfile.TemporaryDirectory(prefix="contract-execution-capture-") as temporary:
        workspace = Path(temporary).resolve()
        raw = workspace / "raw"
        raw.mkdir()
        snapshot_regular_tree(root / "evidence", raw / "evidence")
        _snapshot_execution_tree(compiled_tests, raw / "compiled-tests")
        _snapshot_execution_tree(test_results, raw / "test-results")
        projection = project_contract_execution_evidence(raw, raw / "compiled-tests", raw / "test-results")
        external = workspace / "external"
        external.mkdir()
        archive = external / "contract-execution.zip"
        _write_contract_zip(raw, archive, raw_execution=True)
        expected_inventory = regular_file_inventory(external)
        if verify_contract_execution_archive(archive) != projection:
            raise ValueError("Contract execution archive changed its semantic projection")
        if regular_file_inventory(external) != expected_inventory:
            raise ValueError("Contract execution archive changed after verification")
        # Preserve the original raw evidence before replacing only the fresh stage copies.
        publish_regular_tree(external, destination.parent, expected_inventory=expected_inventory)
        write_canonical_json(root / "evidence/canonical-coverage.json", projection["coverage"])
        write_canonical_json(root / "evidence/kotlin-parity.json", projection["kotlin"])
        contract_evidence_identity(root)
        return projection


def _contract_payload_identity(
    root: Path,
    contract_version: str,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    require_semver(contract_version, "Contract version")
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Contract staging root is missing or unsafe")
    existing = regular_file_inventory(root)
    if any(record["relativePath"] in {"contract-manifest.json", "contract-manifest.sig"} for record in existing):
        raise ValueError("Contract staging root contains a stale manifest or signature")
    if any(not record["relativePath"].startswith(("maven/", "evidence/", "inventories/")) for record in existing):
        raise ValueError("Contract staging root contains an unsupported file")

    maven_files = _maven_records(root, contract_version)
    maven_contents = {record["path"]: (root / record["path"]).read_bytes() for record in maven_files}
    evidence_files = _evidence_records(root)
    verify_contract_git_inventories(root)
    resolution = {
        component: [
            record for record in maven_files
            if record["component"] == component and (
                record["role"] == "runtime-resolution" or
                (record["role"] == "module-metadata" and
                 contract_maven_identity(record["path"], contract_version)["kind"] in {"pom", "gradle-module"})
            )
        ]
        for component in CONTRACT_COMPONENTS
    }
    components: dict[str, Any] = {}
    for component in CONTRACT_COMPONENTS:
        owners = ("common",) if component == "common" else ("common", component)
        records = sorted(
            [record for owner in owners for record in resolution[owner]],
            key=lambda record: record["path"],
        )
        components[component] = {
            "mavenPaths": [record["path"] for record in records],
            "sha256": contract_component_digest(records, contract_version, maven_contents),
        }
    identity = contract_evidence_identity(root)
    return ({
        "schemaVersion": 1,
        "product": "contract",
        "contractVersion": contract_version,
        "contractDigest": contract_digest(
            identity["canonicalApiDigest"],
            identity["protocolDigest"],
            components["common"]["sha256"],
        ),
        **identity,
        "components": components,
        "mavenFiles": maven_files,
        "evidenceFiles": evidence_files,
    }, maven_contents)


def build_contract_bundle(
    staging_root: Path,
    output: Path,
    contract_version: str,
) -> dict[str, Any]:
    root = Path(staging_root)
    output = Path(output)
    _reject_symlinked_output_parent(output, root)
    if output.resolve().is_relative_to(root.resolve()):
        raise ValueError("Contract Bundle output must be outside the staging root")
    expected_name = f"codex-agent-contract-{contract_version}.zip"
    if output.name != expected_name:
        raise ValueError(f"Contract Bundle output must be named {expected_name}")
    manifest, maven_contents = _contract_payload_identity(root, contract_version)
    manifest_path = root / "contract-manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_directory = tempfile.TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent)
    temporary = Path(temporary_directory.name) / output.name
    try:
        validate_contract_manifest(manifest, maven_contents)
        write_canonical_json(manifest_path, manifest)
        _write_contract_zip(root, temporary)
        verify_contract_bundle(temporary)
        if output.exists() or output.is_symlink():
            if output.is_symlink() or not output.is_file() or sha256_file(output) != sha256_file(temporary):
                raise ValueError("Stable Contract Bundle version already exists with different bytes")
        else:
            try:
                os.link(temporary, output)
            except FileExistsError:
                if output.is_symlink() or not output.is_file() or sha256_file(output) != sha256_file(temporary):
                    raise ValueError("Stable Contract Bundle version was concurrently published with different bytes")
        verify_contract_bundle(output)
    finally:
        temporary_directory.cleanup()
        manifest_path.unlink(missing_ok=True)
    return manifest


def _atomic_write(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _remove_directory_entry(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


def _reject_symlinked_output_parent(path: Path, trusted_path: Path) -> None:
    parent = Path(os.path.abspath(path)).parent
    try:
        trusted = Path(os.path.commonpath((parent, Path(os.path.abspath(trusted_path)))))
    except ValueError:
        trusted = Path(parent.anchor)
    ancestors: list[Path] = []
    ancestor = parent
    while ancestor != trusted:
        ancestors.append(ancestor)
        ancestor = ancestor.parent
    for ancestor in ancestors:
        try:
            metadata = ancestor.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise ValueError("Contract output directory is unsafe") from error
        if stat.S_ISLNK(metadata.st_mode) or (
            getattr(metadata, "st_file_attributes", 0) &
            getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ):
            raise ValueError("Contract output directory is unsafe")


def _reject_contract_output_overlap(
    repository_root: Path,
    output: Path,
    pathspecs: tuple[str, ...],
    input_paths: set[str],
    git_directories: tuple[Path, ...],
) -> None:
    root = repository_root.resolve()
    protected_git = {root / ".git", *(path.resolve() for path in git_directories)}
    absolute_output = Path(os.path.abspath(output))
    for candidate in {absolute_output, absolute_output.resolve()}:
        if candidate == root or root.is_relative_to(candidate):
            raise ValueError("Contract metadata output overlaps repository inputs")
        if any(
            candidate == git or candidate.is_relative_to(git) or git.is_relative_to(candidate)
            for git in protected_git
        ):
            raise ValueError("Contract metadata output overlaps repository inputs")
        try:
            relative_output = candidate.relative_to(root).as_posix()
        except ValueError:
            relative_output = None
        if relative_output is not None and any(
            fnmatch.fnmatchcase(relative_output, pathspec) for pathspec in pathspecs
        ):
            raise ValueError("Contract metadata output overlaps repository inputs")
        if any((root / path).is_relative_to(candidate) for path in input_paths):
            raise ValueError("Contract metadata output overlaps repository inputs")


def _publish_prepared_directory(source: Path, output: Path) -> None:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("Prepared Contract metadata directory is missing or unsafe")
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise ValueError("Contract metadata output directory is unsafe")
    backup = Path(tempfile.mkdtemp(prefix=f".{output.name}-backup-", dir=output.parent))
    backup.rmdir()
    replaced = False
    published = False
    try:
        if output.exists():
            os.replace(output, backup)
            replaced = True
        try:
            os.replace(source, output)
            published = True
        except BaseException:
            if replaced:
                try:
                    os.replace(backup, output)
                    replaced = False
                except BaseException as restore_error:
                    raise RuntimeError(
                        f"Contract metadata rollback failed; original preserved at {backup}",
                    ) from restore_error
            raise
    finally:
        if (published or not replaced) and (backup.exists() or backup.is_symlink()):
            _remove_directory_entry(backup)


CONTRACT_VALIDATION_REPORT_NAME = "contract-validation.json"


def _receipt_reference(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "product": receipt["product"],
        "component": receipt["component"],
        "phase": receipt["phase"],
        "target": receipt["target"],
        "buildKey": receipt["buildKey"],
        "outputsDigest": output_inventory_digest(receipt["outputs"]),
    }


def _read_contract_receipt(
    path: Path,
    expected_sha256: str,
    phase: str,
    contract_version: str,
) -> tuple[dict[str, Any], bytes]:
    expected = require_sha256(expected_sha256, f"expected Contract {phase} receipt SHA-256")
    contents = read_regular_file_bytes(
        Path(path), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    if sha256_bytes(contents) != expected:
        raise ValueError(f"Contract {phase} receipt does not match its authenticated digest")
    receipt = validate_phase_receipt(load_canonical_json_bytes(contents))
    if (
        receipt["product"],
        receipt["component"],
        receipt["phase"],
        receipt["target"],
        receipt["productVersion"],
    ) != ("contract", "contract", phase, "common", contract_version):
        raise ValueError(f"Contract {phase} receipt identity is invalid")
    return receipt, contents


def validate_contract_validation_report(value: Any) -> dict[str, Any]:
    report = require_exact_keys(
        value,
        {
            "schemaVersion",
            "product",
            "component",
            "phase",
            "target",
            "contractVersion",
            "packageOutputManifestSha256",
            "contractDigest",
            "canonicalApiDigest",
            "canonicalCoverageDigest",
            "protocolDigest",
            "capabilityCount",
            "componentDigests",
            "result",
        },
        "Contract validation report",
    )
    if require_integer(report["schemaVersion"], "Contract validation report.schemaVersion", 1) != 1:
        raise ValueError("Unsupported Contract validation report schemaVersion")
    for field, expected in {
        "product": "contract",
        "component": "contract",
        "phase": "validation",
        "target": "common",
        "result": "passed",
    }.items():
        if report[field] != expected:
            raise ValueError(f"Contract validation report {field} is invalid")
    require_semver(report["contractVersion"], "Contract validation report.contractVersion")
    for field in (
        "packageOutputManifestSha256",
        "contractDigest",
        "canonicalApiDigest",
        "canonicalCoverageDigest",
        "protocolDigest",
    ):
        require_sha256(report[field], f"Contract validation report.{field}")
    if require_integer(
        report["capabilityCount"], "Contract validation report.capabilityCount", 1,
    ) != 556:
        raise ValueError("Contract validation report capabilityCount must be 556")
    component_digests = require_array(
        report["componentDigests"], "Contract validation report.componentDigests",
    )
    expected_components = sorted(CONTRACT_COMPONENTS)
    if [record.get("component") if type(record) is dict else None for record in component_digests] != expected_components:
        raise ValueError("Contract validation report component digests are incomplete or unordered")
    for index, record in enumerate(component_digests):
        value = require_exact_keys(
            record, {"component", "sha256"},
            f"Contract validation report.componentDigests[{index}]",
        )
        require_sha256(
            value["sha256"], f"Contract validation report.componentDigests[{index}].sha256",
        )
    return report


def validate_contract_package_stage(
    package_stage: Path,
    package_receipt_path: Path,
    package_receipt_sha256: str,
    binary_receipt_path: Path,
    binary_receipt_sha256: str,
    output_directory: Path,
    contract_version: str,
) -> dict[str, Any]:
    require_semver(contract_version, "Contract version")
    output = Path(output_directory)
    package_stage = Path(package_stage)
    _reject_symlinked_output_parent(output, package_stage)
    lexical_output = Path(os.path.abspath(output))
    lexical_package = Path(os.path.abspath(package_stage))
    resolved_output = lexical_output.parent.resolve(strict=False) / lexical_output.name
    resolved_package = lexical_package.resolve(strict=True)
    for left, right in (
        (lexical_output, lexical_package),
        (resolved_output, resolved_package),
    ):
        if left == right or left in right.parents or right in left.parents:
            raise ValueError("Contract validation output overlaps its package input")
    if output.exists() or output.is_symlink():
        raise ValueError("Contract validation output directory must not exist")
    package_receipt, _ = _read_contract_receipt(
        package_receipt_path, package_receipt_sha256, "package", contract_version,
    )
    binary_receipt, _ = _read_contract_receipt(
        binary_receipt_path, binary_receipt_sha256, "binary", contract_version,
    )
    binary_reference = _receipt_reference(binary_receipt)
    binary_reference["semanticProjection"] = {
        "schemaVersion": 1,
        "kind": "contract-execution-content",
        "sha256": output_inventory_digest([
            record for record in binary_receipt["outputs"] if record["kind"] != "contract-execution"
        ]),
        "receiptSha256": binary_receipt_sha256,
    }
    if package_receipt["inputs"]["upstreamArtifacts"] != [binary_reference]:
        raise ValueError("Contract package receipt does not bind the supplied binary receipt")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="contract-package-validation-", dir=output.parent) as temporary:
        workspace = Path(temporary)
        snapshot = workspace / "package"
        snapshot_regular_tree(package_stage, snapshot)
        manifest = verify_output_manifest_identity(
            snapshot, "contract", "contract", "package", "common", contract_version,
        )
        if package_receipt["outputs"] != manifest["outputs"]:
            raise ValueError("Contract package receipt and output manifest disagree")
        execution = [output for output in binary_receipt["outputs"] if output["kind"] == "contract-execution"]
        if len(execution) != 1 or execution[0]["relativePath"] != "outputs/execution/contract-execution.zip":
            raise ValueError("Contract binary receipt must retain exactly one external execution archive")
        if [output for output in binary_receipt["outputs"] if output["kind"] != "contract-execution"] != manifest["outputs"]:
            raise ValueError("Contract package payload differs from its binary predecessor")
        payload, _ = _contract_payload_identity(snapshot / "outputs", contract_version)
        report = validate_contract_validation_report({
            "schemaVersion": 1,
            "product": "contract",
            "component": "contract",
            "phase": "validation",
            "target": "common",
            "contractVersion": contract_version,
            "packageOutputManifestSha256": sha256_bytes(canonical_json_bytes(manifest)),
            "contractDigest": payload["contractDigest"],
            "canonicalApiDigest": payload["canonicalApiDigest"],
            "canonicalCoverageDigest": payload["canonicalCoverageDigest"],
            "protocolDigest": payload["protocolDigest"],
            "capabilityCount": payload["capabilityCount"],
            "componentDigests": [
                {"component": component, "sha256": payload["components"][component]["sha256"]}
                for component in sorted(CONTRACT_COMPONENTS)
            ],
            "result": "passed",
        })
        prepared = workspace / "result"
        write_canonical_json(prepared / CONTRACT_VALIDATION_REPORT_NAME, report)
        if regular_file_inventory(prepared) != [{
            "relativePath": CONTRACT_VALIDATION_REPORT_NAME,
            "bytes": len(canonical_json_bytes(report)),
            "sha256": sha256_bytes(canonical_json_bytes(report)),
        }]:
            raise ValueError("Contract validation output inventory is invalid")
        _publish_prepared_directory(prepared, output)
    return report


CONTRACT_INPUT_PATHSPEC_FILES = {
    "contract-binary-inputs.git-tree": "ci/lanes/contract-product.production.pathspec",
    "contract-validation-inputs.git-tree": "ci/lanes/contract-product.test.pathspec",
}


def _contract_input_pathspecs(root: Path, revision: str) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for inventory_name, path in CONTRACT_INPUT_PATHSPEC_FILES.items():
        contents = run_git(root, "show", f"{revision}:{path}", binary=True)
        try:
            text = contents.decode("utf-8")
        except UnicodeError as error:
            raise ValueError(f"Contract pathspec policy is not UTF-8: {path}") from error
        result[inventory_name] = tuple(
            line
            for raw in text.splitlines()
            if (line := raw.strip()) and not line.startswith("#")
        )
        if not result[inventory_name]:
            raise ValueError(f"Contract pathspec policy is empty: {path}")
        if result[inventory_name] != tuple(sorted(set(result[inventory_name]))):
            raise ValueError(f"Contract pathspec policy must be sorted and unique: {path}")
        if path not in result[inventory_name]:
            raise ValueError(f"Contract pathspec policy must include itself: {path}")
    return result


def _git_paths(root: Path, *arguments: str) -> tuple[str, ...]:
    raw = run_git(root, *arguments, binary=True)
    try:
        return tuple(path.decode("utf-8") for path in raw.split(b"\0") if path)
    except UnicodeError as error:
        raise ValueError("Contract Git input path is not UTF-8") from error


def contract_worktree_mismatches(
    repository_root: Path,
    revision: str,
    pathspecs: dict[str, tuple[str, ...]] | None = None,
) -> tuple[tuple[str, str], ...]:
    """Return Contract input paths whose worktree state differs from revision."""
    root = Path(repository_root).resolve()
    commit = str(run_git(root, "rev-parse", f"{revision}^{{commit}}")).strip()
    trusted_pathspecs = pathspecs or _contract_input_pathspecs(root, commit)
    flattened_pathspecs = tuple(sorted({
        spec
        for specs in trusted_pathspecs.values()
        for spec in specs
    }))
    policy_paths = frozenset(CONTRACT_INPUT_PATHSPEC_FILES.values())

    def matches(path: str) -> bool:
        return path in policy_paths or any(
            fnmatch.fnmatchcase(path, pathspec) for pathspec in flattened_pathspecs
        )

    tracked = _git_paths(
        root,
        "diff",
        "--name-only",
        "-z",
        "--no-renames",
        "--no-ext-diff",
        "--no-textconv",
        "--ignore-submodules=none",
        commit,
        "--",
    )
    # Do not apply ignore rules: an ignored source under a Contract pathspec can
    # still affect a build and therefore cannot be omitted from provenance.
    untracked = _git_paths(root, "ls-files", "--others", "-z")
    return tuple(sorted(
        [(path, "tracked") for path in tracked if matches(path)] +
        [(path, "untracked") for path in untracked if matches(path)],
    ))


def verify_contract_worktree_matches_revision(
    repository_root: Path,
    revision: str,
    pathspecs: dict[str, tuple[str, ...]] | None = None,
) -> None:
    mismatches = contract_worktree_mismatches(repository_root, revision, pathspecs)
    if mismatches:
        rendered = ", ".join(f"{kind}:{path}" for path, kind in mismatches)
        raise ValueError(
            "Contract input worktree does not match the requested revision: " + rendered,
        )


def prepare_contract_inputs(
    repository_root: Path,
    output_directory: Path,
    revision: str,
) -> dict[str, Any]:
    requested_root = Path(os.path.abspath(repository_root))
    root = requested_root.resolve()
    output = Path(output_directory)
    _reject_symlinked_output_parent(output, requested_root)
    commit = str(run_git(root, "rev-parse", f"{revision}^{{commit}}")).strip()
    tree = str(run_git(root, "rev-parse", f"{commit}^{{tree}}")).strip()
    pathspecs = _contract_input_pathspecs(root, commit)
    git_directory = Path(str(run_git(root, "rev-parse", "--absolute-git-dir")).strip())
    common_git_directory = Path(str(run_git(root, "rev-parse", "--git-common-dir")).strip())
    if not common_git_directory.is_absolute():
        common_git_directory = root / common_git_directory
    inventory_contents: dict[str, bytes] = {}
    contract_input_paths: set[str] = set()
    for name, specs in pathspecs.items():
        records = inventory(root, commit, specs)
        if not records:
            raise ValueError(f"Contract Git inventory is empty: {name}")
        # Payload identity binds content, not source executable bits. The original
        # modes remain recoverable from producer commit/tree; non-regular modes fail validation.
        records = "".join(sorted(
            line.replace("100755\tblob\t", "100644\tblob\t", 1) + "\n"
            for line in records.splitlines()
        ))
        contract_input_paths.update(inventory_paths(records))
        inventory_contents[name] = records.encode("utf-8")
    verify_contract_worktree_matches_revision(root, commit, pathspecs)
    _reject_contract_output_overlap(
        root,
        output,
        tuple(spec for specs in pathspecs.values() for spec in specs),
        contract_input_paths,
        (git_directory, common_git_directory),
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise ValueError("Contract metadata output directory is unsafe")
    temporary_directory = tempfile.TemporaryDirectory(
        prefix=f".{output.name}-prepare-",
        dir=output.parent,
    )
    prepared = Path(temporary_directory.name)
    try:
        for name, contents in inventory_contents.items():
            path = prepared / "inventories" / name
            _atomic_write(path, contents)
            if path.read_bytes() != contents:
                raise ValueError(f"Prepared Contract Git inventory does not match revision: {name}")
        verify_contract_git_inventories(prepared)
        expected = {
            "inventories/contract-binary-inputs.git-tree",
            "inventories/contract-validation-inputs.git-tree",
        }
        if {record["relativePath"] for record in regular_file_inventory(prepared)} != expected:
            raise ValueError("Prepared Contract metadata inventory is incomplete or unexpected")
        _publish_prepared_directory(prepared, output)
    finally:
        temporary_directory.cleanup()
    return {"commit": commit, "tree": tree}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and verify the deterministic Codex Contract Bundle")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--repository-root", type=Path, required=True)
    prepare.add_argument("--output-directory", type=Path, required=True)
    prepare.add_argument("--revision", default="HEAD")
    build = commands.add_parser("build")
    build.add_argument("--staging-root", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--contract-version", required=True)
    capture = commands.add_parser("capture-execution")
    capture.add_argument("--staging-root", type=Path, required=True)
    capture.add_argument("--compiled-tests", type=Path, required=True)
    capture.add_argument("--test-results", type=Path, required=True)
    validate_package = commands.add_parser("validate-package")
    validate_package.add_argument("--package-stage", type=Path, required=True)
    validate_package.add_argument("--package-receipt", type=Path, required=True)
    validate_package.add_argument("--package-receipt-sha256", required=True)
    validate_package.add_argument("--binary-receipt", type=Path, required=True)
    validate_package.add_argument("--binary-receipt-sha256", required=True)
    validate_package.add_argument("--output-directory", type=Path, required=True)
    validate_package.add_argument("--contract-version", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--archive", type=Path, required=True)
    verify_directory = commands.add_parser("verify-directory")
    verify_directory.add_argument("--directory", type=Path, required=True)
    verify_directory.add_argument("--expected-contract-version")
    verify_directory.add_argument(
        "--required-component",
        action="append",
        default=[],
        choices=CONTRACT_COMPONENTS,
    )
    verify_directory.add_argument("--print-canonical-api", action="store_true")
    verify_directory.add_argument("--output-directory", type=Path)
    verify_directory.add_argument("--reuse-output-directory", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.command == "verify-directory":
        if arguments.reuse_output_directory and arguments.output_directory is None:
            parser.error("verify-directory --reuse-output-directory requires --output-directory")
    if arguments.command == "prepare":
        prepare_contract_inputs(
            arguments.repository_root,
            arguments.output_directory,
            arguments.revision,
        )
    elif arguments.command == "build":
        build_contract_bundle(
            arguments.staging_root,
            arguments.output,
            arguments.contract_version,
        )
    elif arguments.command == "capture-execution":
        capture_contract_execution_evidence(arguments.staging_root, arguments.compiled_tests, arguments.test_results)
    elif arguments.command == "validate-package":
        validate_contract_package_stage(
            arguments.package_stage,
            arguments.package_receipt,
            arguments.package_receipt_sha256,
            arguments.binary_receipt,
            arguments.binary_receipt_sha256,
            arguments.output_directory,
            arguments.contract_version,
        )
    elif arguments.command == "verify":
        verify_contract_bundle(arguments.archive)
    else:
        if arguments.print_canonical_api:
            if arguments.output_directory is not None or arguments.reuse_output_directory:
                parser.error("verify-directory --print-canonical-api rejects output-directory options")
            projection = verify_extracted_contract_directory_projection(
                arguments.directory,
                expected_contract_version=arguments.expected_contract_version,
                required_components=arguments.required_component,
            )
            sys.stdout.write(canonical_json_bytes(projection).decode())
        else:
            verify_extracted_contract_directory(
                arguments.directory,
                expected_contract_version=arguments.expected_contract_version,
                required_components=arguments.required_component,
                output_directory=arguments.output_directory,
                reuse_output_directory=arguments.reuse_output_directory,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
