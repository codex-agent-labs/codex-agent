"""S808 whole-chain Runtime variants built from explicit synthetic test fixtures."""

from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile
from typing import Any

from ci.products.c_abi import (
    C_ABI_CONTRACT,
    C_ABI_IDENTITY_SCHEMA_VERSION,
    C_ABI_REPOSITORY_ROOT,
    C_ABI_REVIEWED_EXPORT_PATHS,
    C_ABI_REVIEWED_HEADER_PATH,
    C_ABI_SYMBOL_COUNT,
    COMPILE_ONLY_CONSUMERS,
    GNU_CONSUMERS,
    STRICT_CONSUMERS,
    TARGET_SPECS,
    CAbiConsumerProof,
    CAbiEvidenceValues,
    CAbiPackageInput,
    c_abi_archive_file_name,
    c_abi_expected_symbols,
    c_abi_linux_symbol_versions,
    package_c_abi_sdk,
    portable_verify_c_abi_package_evidence,
    write_c_abi_package_evidence,
)
from ci.products.contract_model import CONTRACT_CHECKSUM_SUFFIXES
from ci.products.inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    write_canonical_json,
)
from ci.products.receipt import write_output_manifest
from ci.products.runtime_attestation import build_runtime_variant_attestation
from ci.products.runtime_evidence import (
    PRODUCT_RUNTIME_TARGETS,
    RUNTIME_TARGETS,
    build_desktop_evidence,
    imported_desktop_test_task,
    inspect_classifier,
    read_distribution_manifest,
)
from ci.products.runtime_identity import derive_runtime_identity
from ci.products.runtime_variant import produce_runtime_variant
from ci.tests.product_chain_support import (
    TOOLCHAIN,
    contract_reference,
    output,
    reference,
    write_receipt,
)
from ci.tests.test_runtime_evidence import write_zip


_VERSION = "0.2.7"
_COMPATIBILITY = "0.2.0"
_APP_SERVER_VERSION = "0.145.0"
_CONSUMER_ROOT = C_ABI_REPOSITORY_ROOT / "codex-agent-runtime-desktop/native/c-api/consumer"


def _bare_digest(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def _write_runtime_inputs(root: Path) -> tuple[Path, dict[str, Path], dict[str, Any]]:
    app_server = b"S808 synthetic App Server fixture; not hosted evidence\n"
    supervisor = b"S808 synthetic process supervisor fixture; not hosted evidence\n"
    archives: dict[str, Path] = {}
    distributions = []
    for evidence_target, spec in RUNTIME_TARGETS.items():
        windows = evidence_target == "mingwX64"
        executable = "codex-app-server.exe" if windows else "codex-app-server"
        supervisor_name = "codex-process-supervisor.exe" if windows else "codex-process-supervisor"
        payload = {
            executable: app_server,
            supervisor_name: supervisor,
            "openai-codex-LICENSE.txt": b"S808 synthetic App Server license fixture\n",
            "openai-codex-NOTICE.txt": b"S808 synthetic App Server notice fixture\n",
        }
        runtime_manifest = canonical_json_bytes({
            "schemaVersion": 1,
            "libraryVersion": _COMPATIBILITY,
            "appServerVersion": _APP_SERVER_VERSION,
            "target": evidence_target,
            "classifier": spec.classifier,
            "members": [
                {
                    "name": name,
                    "size": len(contents),
                    "sha256": _bare_digest(contents),
                    "executable": name in {executable, supervisor_name},
                }
                for name, contents in sorted(payload.items())
            ],
        })
        archive = root / f"codex-agent-runtime-desktop-{_COMPATIBILITY}-{spec.classifier}.zip"
        write_zip(archive, dict(sorted({
            **payload, "codex-runtime-manifest.json": runtime_manifest,
        }.items())))
        archives[evidence_target] = archive
        distributions.append({
            "target": evidence_target,
            "classifier": spec.classifier,
            "asset": f"{evidence_target}.tar.gz",
            "archiveSha256": sha256_file(archive).removeprefix("sha256:"),
            "archiveEntry": executable,
            "binarySha256": _bare_digest(app_server),
            "executableName": executable,
            "supervisorExecutableName": supervisor_name,
        })
    manifest_path = root / "codex-app-server-distributions.json"
    write_canonical_json(manifest_path, {
        "version": _APP_SERVER_VERSION,
        "releaseTag": f"rust-v{_APP_SERVER_VERSION}",
        "distributions": distributions,
    })
    manifest = read_distribution_manifest(manifest_path)
    return manifest_path, archives, {
        target: inspect_classifier(target, manifest, archive)
        for target, archive in archives.items()
    }


def _c_abi_values(
    target: str,
    snapshot: Any,
    producer: dict[str, Any],
    consumer_sources: list[Path],
) -> CAbiEvidenceValues:
    spec = TARGET_SPECS[target]
    export_policy = C_ABI_REVIEWED_EXPORT_PATHS[spec.format]
    symbols = c_abi_expected_symbols(export_policy)
    tools = {
        tool: _bare_digest(f"S808 synthetic {target} {tool} tool output fixture".encode())
        for tool in spec.required_tool_ids
    }
    source_digests = {
        source.name: _bare_digest(source.read_bytes()) for source in consumer_sources
    }

    def proof(name: str, *, gnu: bool = False) -> CAbiConsumerProof:
        language = "c++17" if name.endswith(".cpp") else "c11"
        compiler = (
            "gnuCpp" if language == "c++17" else "gnuC"
        ) if gnu else ("cpp" if language == "c++17" else "c")
        compile_only = name in COMPILE_ONLY_CONSUMERS and not gnu
        label = f"S808 synthetic {target} {name} gnu={gnu}"
        return CAbiConsumerProof(
            source=name,
            source_sha256=source_digests[name],
            language=language,
            compiler_identity_sha256=tools[compiler],
            compile_output_sha256=_bare_digest(f"{label} compiler output fixture".encode()),
            artifact_sha256=_bare_digest(f"{label} artifact fixture".encode()),
            linked=not compile_only,
            executed=not compile_only,
            exit_code=0,
        )

    return CAbiEvidenceValues(
        target=target,
        classifier=spec.classifier,
        library_version=_COMPATIBILITY,
        producer_commit=producer["commit"],
        producer_tree=producer["tree"],
        runner_os=spec.runner_os,
        runner_arch=spec.runner_arch,
        archive_sha256=snapshot.archive_sha256,
        header_sha256=snapshot.header_sha256,
        library_sha256=snapshot.library_sha256,
        public_symbols=symbols,
        public_symbol_versions=(
            c_abi_linux_symbol_versions(export_policy) if spec.format == "elf" else {}
        ),
        format=spec.format,
        architecture=spec.architecture,
        loader_identity=spec.loader_identity,
        version_identity=spec.version_identity,
        import_libraries={path: snapshot.members[path] for path in spec.import_library_paths},
        tool_proofs=tools,
        consumers=tuple(proof(name) for name in sorted(STRICT_CONSUMERS)),
        gnu_consumers=(
            tuple(proof(name, gnu=True) for name in sorted(GNU_CONSUMERS))
            if spec.format == "pe" else ()
        ),
    )


def _checksum(contents: bytes, suffix: str) -> bytes:
    return hashlib.new(suffix.removeprefix("."), contents).hexdigest().encode("ascii") + b"\n"


def build_variants(root: Path, contract: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Build five authenticated Runtime variants from deterministic fixture payloads."""
    root = Path(root)
    root.mkdir(parents=True)
    producer = dict(context["producer"])
    stages = root / "stages"
    inputs = root / "inputs"
    inputs.mkdir()
    license_path = inputs / "LICENSE.txt"
    notice_path = inputs / "THIRD_PARTY_NOTICES.md"
    license_path.write_bytes(b"S808 synthetic native library license fixture\n")
    notice_path.write_bytes(b"S808 synthetic native library notice fixture\n")
    consumer_sources = sorted(_CONSUMER_ROOT / name for name in STRICT_CONSUMERS)
    distribution_manifest, app_archives, app_proofs = _write_runtime_inputs(inputs)

    variant_bundles: dict[str, Path] = {}
    variant_phase_receipts: dict[str, dict[str, Path]] = {}
    variant_attestations: dict[str, Path] = {}
    variant_signatures: dict[str, Path] = {}
    variant_public_keys: dict[str, Path] = {}
    validation_evidence: dict[str, Path] = {}
    manifests: dict[str, dict[str, Any]] = {}
    receipts: dict[str, dict[str, dict[str, Any]]] = {}
    raw_sdks: dict[str, dict[str, Any]] = {}
    runtime_maven_files: list[dict[str, Any]] = []

    for evidence_target, target in PRODUCT_RUNTIME_TARGETS.items():
        spec = TARGET_SPECS[evidence_target]
        package_stage = stages / target / "package"
        validation_stage = stages / target / "validation"
        c_abi_dir = package_stage / "outputs/c-abi"
        app_dir = package_stage / "outputs/app-server"
        maven_dir = package_stage / "outputs/maven" / target
        for directory in (c_abi_dir, app_dir, maven_dir, validation_stage / "outputs/c-abi", validation_stage / "outputs/native"):
            directory.mkdir(parents=True, exist_ok=True)

        library = inputs / evidence_target / "library"
        library.parent.mkdir()
        library.write_bytes(f"S808 synthetic {target} native library fixture\n".encode())
        gnu_import = msvc_import = None
        if spec.format == "pe":
            gnu_import = inputs / evidence_target / "libcodex_agent.dll.a"
            msvc_import = inputs / evidence_target / "codex_agent.lib"
            gnu_import.write_bytes(b"S808 synthetic GNU import library fixture\n")
            msvc_import.write_bytes(b"S808 synthetic MSVC import library fixture\n")
        package_input = CAbiPackageInput(
            target=evidence_target,
            classifier=spec.classifier,
            library_version=_COMPATIBILITY,
            producer_commit=producer["commit"],
            producer_tree=producer["tree"],
            reviewed_header=C_ABI_REVIEWED_HEADER_PATH,
            license=license_path,
            notice=notice_path,
            library=library,
            export_policy=C_ABI_REVIEWED_EXPORT_PATHS[spec.format],
            gnu_import_library=gnu_import,
            msvc_import_library=msvc_import,
        )
        c_abi_archive = c_abi_dir / c_abi_archive_file_name(_COMPATIBILITY, evidence_target)
        snapshot = package_c_abi_sdk(package_input, c_abi_archive)
        app_archive = app_dir / app_archives[evidence_target].name
        app_archive.write_bytes(app_archives[evidence_target].read_bytes())

        maven_primary = maven_dir / "runtime.klib"
        maven_contents = f"S808 synthetic {target} Maven runtime fixture\n".encode()
        maven_primary.write_bytes(maven_contents)
        runtime_maven_files.append({
            "path": f"maven/{target}/runtime.klib",
            "role": "runtime-resolution",
            "component": target,
            "file": maven_primary,
        })
        for suffix in CONTRACT_CHECKSUM_SUFFIXES:
            sidecar = maven_primary.with_name(maven_primary.name + suffix)
            sidecar.write_bytes(_checksum(maven_contents, suffix))
            runtime_maven_files.append({
                "path": f"maven/{target}/runtime.klib{suffix}",
                "role": "checksum",
                "component": target,
                "file": sidecar,
            })

        raw_evidence = validation_stage / "outputs/c-abi" / f"c-abi-package-{target}.json"
        write_c_abi_package_evidence(
            _c_abi_values(evidence_target, snapshot, producer, consumer_sources), raw_evidence,
        )
        verified_sdk = root / "raw-sdks" / target
        portable_verify_c_abi_package_evidence(
            evidence_target,
            _COMPATIBILITY,
            producer["commit"],
            producer["tree"],
            c_abi_archive,
            raw_evidence,
            C_ABI_REVIEWED_HEADER_PATH,
            license_path,
            notice_path,
            C_ABI_REVIEWED_EXPORT_PATHS[spec.format],
            consumer_sources,
            verified_sdk,
        )

        proof = app_proofs[evidence_target]
        desktop_evidence = validation_stage / "outputs/native" / f"desktop-runtime-{evidence_target}.json"
        write_canonical_json(desktop_evidence, build_desktop_evidence(
            producer["commit"],
            evidence_target,
            proof.binary_sha256,
            proof.supervisor_sha256,
            proof.archive_sha256,
            test_task=imported_desktop_test_task(evidence_target),
        ))
        references = validation_stage / "outputs/c-abi-reference"
        reference_files = {
            "include/codex_agent.h": C_ABI_REVIEWED_HEADER_PATH,
            "legal/LICENSE": license_path,
            "legal/THIRD_PARTY_NOTICES.md": notice_path,
            f"export-policy/{C_ABI_REVIEWED_EXPORT_PATHS[spec.format].name}": C_ABI_REVIEWED_EXPORT_PATHS[spec.format],
            **{f"consumer/{source.name}": source for source in consumer_sources},
        }
        for relative, source in reference_files.items():
            destination = references / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
        package_outputs = write_output_manifest(
            package_stage, "runtime", target, "package", target, _VERSION,
            {"c-abi": "outputs/c-abi", "app-server": "outputs/app-server", "maven": "outputs/maven"},
        )["outputs"]
        validation_outputs = write_output_manifest(
            validation_stage, "runtime", target, "validation", target, _VERSION,
            {"c-abi": "outputs/c-abi", "native": "outputs/native", "c-abi-reference": "outputs/c-abi-reference"},
        )["outputs"]

        receipt_paths = {
            phase: root / "receipts" / target / f"{phase}.json"
            for phase in ("binary", "package", "validation", "metadata")
        }
        binary = write_receipt(
            receipt_paths["binary"], component=target, phase="binary", target=target,
            outputs=[output("runtime-binary", f"outputs/binary/{library.name}", library.read_bytes())],
            upstream=[contract_reference(contract, target)], context=context,
        )
        package = write_receipt(
            receipt_paths["package"], component=target, phase="package", target=target,
            outputs=package_outputs, upstream=[reference(binary)], context=context,
        )
        validation = write_receipt(
            receipt_paths["validation"], component=target, phase="validation", target=target,
            outputs=validation_outputs, upstream=[reference(package)], context=context,
        )
        identity = derive_runtime_identity({
            "schemaVersion": 1,
            "binaryBuildKey": binary["buildKey"],
            "runtimeCompatibilityVersion": _COMPATIBILITY,
            "target": target,
            "contract": {
                "digest": contract["manifest"]["contractDigest"],
                "componentDigest": contract["manifest"]["components"][target]["sha256"],
            },
            "cAbi": {
                "version": C_ABI_CONTRACT.current.semver,
                "minimumCompatibleVersion": C_ABI_CONTRACT.minimum_compatible.semver,
                "identitySchemaVersion": C_ABI_IDENTITY_SCHEMA_VERSION,
                "headerSha256": f"sha256:{snapshot.header_sha256}",
                "symbolSetSha256": f"sha256:{snapshot.public_symbols_sha256}",
                "symbolCount": C_ABI_SYMBOL_COUNT,
            },
            "appServer": {
                "version": _APP_SERVER_VERSION,
                "releaseTag": f"rust-v{_APP_SERVER_VERSION}",
                "binarySha256": f"sha256:{proof.binary_sha256}",
            },
            "toolchainProfile": {"id": target, "digest": TOOLCHAIN},
        })
        variant_output = root / "variants" / target
        variant_output.mkdir(parents=True)
        bundle_result = produce_runtime_variant(
            identity_envelope=identity,
            binary_receipt=receipt_paths["binary"],
            package_receipt=receipt_paths["package"],
            validation_receipt=receipt_paths["validation"],
            c_abi_archive=c_abi_archive,
            app_server_archive=app_archive,
            validation_evidence=desktop_evidence,
            distribution_manifest=distribution_manifest,
            output_directory=variant_output,
        )
        bundle = bundle_result["bundlePath"]
        with zipfile.ZipFile(bundle) as archive:
            manifest = load_canonical_json_bytes(archive.read("runtime-variant-manifest.json"))
        validation_projection = next(
            artifact["sha256"] for artifact in manifest["innerArtifacts"]
            if artifact["role"] == "validation"
        )
        metadata_upstream = reference(validation)
        metadata_upstream["semanticProjection"] = {
            "schemaVersion": 1,
            "kind": "runtime-validation-content",
            "sha256": validation_projection,
        }
        metadata = write_receipt(
            receipt_paths["metadata"], component=target, phase="metadata", target=target,
            outputs=[output(
                "runtime-variant", f"outputs/{bundle.name}", bundle.read_bytes(),
            )],
            upstream=[metadata_upstream], context=context,
        )
        attestation_dir = root / "attestations" / target
        build_runtime_variant_attestation(
            bundle,
            receipt_paths["binary"],
            receipt_paths["package"],
            receipt_paths["validation"],
            receipt_paths["metadata"],
            desktop_evidence,
            context["signing"],
            context["private_key"],
            context["public_key"],
            attestation_dir,
        )
        attestation = attestation_dir / f"{bundle.stem}.attestation.json"
        signature = attestation_dir / f"{bundle.stem}.attestation.sig"

        variant_bundles[target] = bundle
        variant_phase_receipts[target] = receipt_paths
        variant_attestations[target] = attestation
        variant_signatures[target] = signature
        variant_public_keys[target] = context["public_key"]
        validation_evidence[target] = desktop_evidence
        manifests[target] = manifest
        receipts[target] = {
            "binary": binary,
            "package": package,
            "validation": validation,
            "metadata": metadata,
        }
        raw_sdks[target] = {
            "archive": c_abi_archive,
            "evidence": raw_evidence,
            "verified_sdk": verified_sdk,
            "evidence_target": evidence_target,
            "reviewed_header": C_ABI_REVIEWED_HEADER_PATH,
            "export_policy": C_ABI_REVIEWED_EXPORT_PATHS[spec.format],
            "license": license_path,
            "notice": notice_path,
            "consumer_sources": consumer_sources,
        }

    return {
        "variant_bundles": variant_bundles,
        "variant_phase_receipts": variant_phase_receipts,
        "variant_attestations": variant_attestations,
        "variant_attestation_signatures": variant_signatures,
        "variant_public_keys": variant_public_keys,
        "variant_validation_evidence": validation_evidence,
        "manifests": manifests,
        "receipts": receipts,
        "stages": stages,
        "raw_sdks": raw_sdks,
        "runtime_maven_files": runtime_maven_files,
    }
