from __future__ import annotations

import argparse
import fnmatch
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from typing import Any
import zipfile

from ci.impact import inventory, inventory_paths, run_git

from .contract_model import (
    CONTRACT_ARTIFACT_COMPONENTS,
    CONTRACT_COMPONENTS,
    CONTRACT_EVIDENCE_PATH_ROLES,
    contract_component_digest,
    contract_digest,
    contract_evidence_identity,
    contract_maven_identity,
    validate_contract_maven_inventory,
    validate_contract_manifest,
    verify_contract_git_inventories,
    verify_contract_bundle,
)
from .inventory import (
    load_canonical_json,
    regular_file_inventory,
    require_semver,
    sha256_file,
    write_canonical_json,
)
from .receipt import validate_producer
from .signatures import (
    generate_development_key,
    sign_manifest,
    validate_signing_metadata,
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


def _write_contract_zip(root: Path, output: Path) -> None:
    records = regular_file_inventory(root)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for record in records:
            info = zipfile.ZipInfo(record["relativePath"], (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, (root / record["relativePath"]).read_bytes())


def build_contract_bundle(
    staging_root: Path,
    output: Path,
    contract_version: str,
    producer: dict[str, Any],
    private_key: Path,
    public_key: Path,
    signing: dict[str, Any],
) -> dict[str, Any]:
    root = Path(staging_root)
    output = Path(output)
    require_semver(contract_version, "Contract version")
    validate_producer(producer, "Contract manifest.producer")
    validate_signing_metadata(signing, trust_domain="development")
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Contract staging root is missing or unsafe")
    _reject_symlinked_output_parent(output, root)
    if output.resolve().is_relative_to(root.resolve()):
        raise ValueError("Contract Bundle output must be outside the staging root")
    expected_name = f"codex-agent-contract-{contract_version}.zip"
    if output.name != expected_name:
        raise ValueError(f"Contract Bundle output must be named {expected_name}")
    existing = regular_file_inventory(root)
    if any(record["relativePath"] in {"contract-manifest.json", "contract-manifest.sig"} for record in existing):
        raise ValueError("Contract staging root contains a stale manifest or signature")
    if any(not record["relativePath"].startswith(("maven/", "evidence/", "inventories/")) for record in existing):
        raise ValueError("Contract staging root contains an unsupported file")

    maven_files = _maven_records(root, contract_version)
    maven_contents = {record["path"]: (root / record["path"]).read_bytes() for record in maven_files}
    evidence_files = _evidence_records(root)
    verify_contract_git_inventories(root, producer)
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
    manifest = {
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
        "signing": signing,
        "producer": producer,
    }
    manifest_path = root / "contract-manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_directory = tempfile.TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent)
    temporary = Path(temporary_directory.name) / output.name
    signature_path = root / "contract-manifest.sig"
    try:
        validate_contract_manifest(manifest, maven_contents)
        write_canonical_json(manifest_path, manifest)
        sign_manifest(manifest_path, private_key, signing)
        _write_contract_zip(root, temporary)
        verify_contract_bundle(temporary, public_key, expected_trust_domain="development")
        if output.exists() or output.is_symlink():
            if output.is_symlink() or not output.is_file() or sha256_file(output) != sha256_file(temporary):
                raise ValueError("Stable Contract Bundle version already exists with different bytes")
        else:
            try:
                os.link(temporary, output)
            except FileExistsError:
                if output.is_symlink() or not output.is_file() or sha256_file(output) != sha256_file(temporary):
                    raise ValueError("Stable Contract Bundle version was concurrently published with different bytes")
        verify_contract_bundle(output, public_key, expected_trust_domain="development")
    finally:
        temporary_directory.cleanup()
        signature_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
    return manifest


def _development_key(directory: Path) -> None:
    private_key, _, signing = generate_development_key(directory)
    write_canonical_json(private_key.parent / "signing-metadata.json", signing)


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


def build_development_contract_bundle(
    staging_root: Path,
    output_directory: Path,
    contract_version: str,
    producer: dict[str, Any],
) -> dict[str, Any]:
    output = Path(output_directory)
    requested_staging = Path(os.path.abspath(staging_root))
    staging = requested_staging.resolve()
    _reject_symlinked_output_parent(output, requested_staging)
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise ValueError("Contract development Bundle directory is unsafe")
    for candidate in {Path(os.path.abspath(output)), Path(os.path.abspath(output)).resolve()}:
        if candidate == staging or candidate.is_relative_to(staging) or staging.is_relative_to(candidate):
            raise ValueError("Contract development Bundle directory overlaps its staging input")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="contract-development-signing-", dir=output.parent) as temporary:
        workspace = Path(temporary)
        private_key, public_key, signing = generate_development_key(workspace / "key")
        prepared = workspace / "bundle"
        archive_name = f"codex-agent-contract-{contract_version}.zip"
        manifest = build_contract_bundle(
            staging_root,
            prepared / archive_name,
            contract_version,
            producer,
            private_key,
            public_key,
            signing,
        )
        _atomic_write(prepared / "development-ed25519.pub", public_key.read_bytes())
        verify_contract_bundle(
            prepared / archive_name,
            prepared / "development-ed25519.pub",
            expected_trust_domain="development",
        )
        _publish_prepared_directory(prepared, output)
    return manifest


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
    repository: str,
    workflow_path: str,
    event: str,
    run_id: int,
    run_attempt: int,
    pull_request: int | None,
) -> dict[str, Any]:
    requested_root = Path(os.path.abspath(repository_root))
    root = requested_root.resolve()
    output = Path(output_directory)
    _reject_symlinked_output_parent(output, requested_root)
    commit = str(run_git(root, "rev-parse", f"{revision}^{{commit}}")).strip()
    tree = str(run_git(root, "rev-parse", f"{commit}^{{tree}}")).strip()
    producer = {
        "repository": repository,
        "workflowPath": workflow_path,
        "commit": commit,
        "tree": tree,
        "event": event,
        "runId": run_id,
        "runAttempt": run_attempt,
        "pullRequest": pull_request,
    }
    validate_producer(producer, "Contract input producer")
    try:
        run_git(root, "cat-file", "-e", f"{commit}:{workflow_path}")
    except subprocess.CalledProcessError as error:
        raise ValueError("Contract producer workflow does not exist at the requested revision") from error
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
        contract_input_paths.update(inventory_paths(records))
        inventory_contents[name] = f"tree\t{tree}\n{records}".encode("utf-8")
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
        write_canonical_json(prepared / "producer.json", producer)
        for name, contents in inventory_contents.items():
            path = prepared / "inventories" / name
            _atomic_write(path, contents)
            if path.read_bytes() != contents:
                raise ValueError(f"Prepared Contract Git inventory does not match revision: {name}")
        if load_canonical_json(prepared / "producer.json") != producer:
            raise ValueError("Prepared Contract producer does not match its canonical bytes")
        verify_contract_git_inventories(prepared, producer)
        expected = {
            "producer.json",
            "inventories/contract-binary-inputs.git-tree",
            "inventories/contract-validation-inputs.git-tree",
        }
        if {record["relativePath"] for record in regular_file_inventory(prepared)} != expected:
            raise ValueError("Prepared Contract metadata inventory is incomplete or unexpected")
        _publish_prepared_directory(prepared, output)
    finally:
        temporary_directory.cleanup()
    return producer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and verify the signed Codex Contract Bundle")
    commands = parser.add_subparsers(dest="command", required=True)
    key = commands.add_parser("development-key")
    key.add_argument("--directory", type=Path, required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--repository-root", type=Path, required=True)
    prepare.add_argument("--output-directory", type=Path, required=True)
    prepare.add_argument("--revision", default="HEAD")
    prepare.add_argument("--repository", required=True)
    prepare.add_argument("--workflow-path", required=True)
    prepare.add_argument("--event", required=True)
    prepare.add_argument("--run-id", type=int, required=True)
    prepare.add_argument("--run-attempt", type=int, required=True)
    prepare.add_argument("--pull-request", type=int)
    build = commands.add_parser("build")
    build.add_argument("--staging-root", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--contract-version", required=True)
    build.add_argument("--producer", type=Path, required=True)
    build.add_argument("--private-key", type=Path, required=True)
    build.add_argument("--public-key", type=Path, required=True)
    build.add_argument("--signing-metadata", type=Path, required=True)
    development_build = commands.add_parser("development-build")
    development_build.add_argument("--staging-root", type=Path, required=True)
    development_build.add_argument("--output-directory", type=Path, required=True)
    development_build.add_argument("--contract-version", required=True)
    development_build.add_argument("--producer", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--archive", type=Path, required=True)
    verify.add_argument("--public-key", type=Path, required=True)
    arguments = parser.parse_args(argv)
    if arguments.command == "development-key":
        _development_key(arguments.directory)
    elif arguments.command == "prepare":
        prepare_contract_inputs(
            arguments.repository_root,
            arguments.output_directory,
            arguments.revision,
            arguments.repository,
            arguments.workflow_path,
            arguments.event,
            arguments.run_id,
            arguments.run_attempt,
            arguments.pull_request,
        )
    elif arguments.command == "build":
        build_contract_bundle(
            arguments.staging_root,
            arguments.output,
            arguments.contract_version,
            load_canonical_json(arguments.producer),
            arguments.private_key,
            arguments.public_key,
            load_canonical_json(arguments.signing_metadata),
        )
    elif arguments.command == "development-build":
        build_development_contract_bundle(
            arguments.staging_root,
            arguments.output_directory,
            arguments.contract_version,
            load_canonical_json(arguments.producer),
        )
    else:
        verify_contract_bundle(arguments.archive, arguments.public_key, expected_trust_domain="development")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
