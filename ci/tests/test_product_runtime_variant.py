from __future__ import annotations

import contextlib
import copy
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from ci.products.aggregate import validate_runtime_variant
from ci.products.inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    verified_zip_contents,
    write_canonical_json,
)
from ci.products.receipt import compute_build_key, output_inventory_digest
from ci.products.runtime_evidence import (
    RUNTIME_TARGETS as EVIDENCE_TARGETS,
    build_desktop_evidence,
    desktop_test_task,
    imported_desktop_test_task,
)
from ci.products.runtime_identity import derive_runtime_identity
from ci.products.runtime_variant import main, produce_runtime_variant
from ci.products.signatures import generate_development_key


TARGET = "linux-x64"
RUNTIME_VERSION = "0.2.7"
COMPATIBILITY_VERSION = "0.2.0"
DIGEST_A = sha256_bytes(b"a")
DIGEST_B = sha256_bytes(b"b")
DIGEST_C = sha256_bytes(b"c")


def _producer() -> dict[str, object]:
    return {
        "repository": "owner/repository",
        "workflowPath": ".github/workflows/runtime.yml",
        "commit": "a" * 40,
        "tree": "b" * 40,
        "event": "pull_request",
        "runId": 1,
        "runAttempt": 1,
        "pullRequest": 31,
    }


def _record(path: str, contents: bytes, kind: str) -> dict[str, object]:
    return {
        "kind": kind,
        "relativePath": path,
        "bytes": len(contents),
        "sha256": sha256_bytes(contents),
    }


def _inputs(name: str, upstream: list[dict], toolchain: str) -> dict[str, object]:
    inventory = [{
        "relativePath": f"inputs/{name}.txt",
        "bytes": 1,
        "sha256": sha256_bytes(name.encode()),
    }]
    return {
        "inventory": inventory,
        "phaseInputDigest": sha256_bytes(canonical_json_bytes(inventory)),
        "versionIdentity": COMPATIBILITY_VERSION,
        "upstreamArtifacts": upstream,
        "toolchainProfileDigest": toolchain,
        "flagsDigest": DIGEST_C,
        "outputSchemaVersion": 1,
    }


def _reference(receipt: dict) -> dict[str, object]:
    return {
        "product": receipt["product"],
        "component": receipt["component"],
        "phase": receipt["phase"],
        "target": receipt["target"],
        "buildKey": receipt["buildKey"],
        "outputsDigest": output_inventory_digest(receipt["outputs"]),
    }


def _receipt(phase: str, inputs: dict, outputs: list[dict], trust_domain: str) -> dict:
    value = {
        "schemaVersion": 1,
        "product": "runtime",
        "component": TARGET,
        "phase": phase,
        "target": TARGET,
        "productVersion": RUNTIME_VERSION,
        "buildKey": "",
        "inputs": inputs,
        "outputs": sorted(outputs, key=lambda output: output["relativePath"]),
        "producer": _producer(),
        "trustDomain": trust_domain,
        "result": "success",
    }
    value["buildKey"] = compute_build_key(
        product=value["product"],
        component=value["component"],
        phase=value["phase"],
        target=value["target"],
        inputs=value["inputs"],
    )
    return value


def _write_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, contents in sorted(members.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (0o100644) << 16
            archive.writestr(info, contents)


class Fixture:
    def __init__(self, root: Path, private_key: Path, public_key: Path, signing: dict):
        self.root = root
        root.mkdir()
        self.private_key = private_key
        self.public_key = public_key
        self.signing = signing
        self.header = b"reviewed C header\n"
        self.app_binary = b"exact app server binary\n"
        self.c_abi = root / "codex-agent-c.zip"
        self.app_server = root / "codex-agent-runtime-desktop-0.2.0-app-server-linux-x64.zip"
        _write_zip(self.c_abi, {
            "include/codex_agent.h": self.header,
            "lib/libcodex_agent.so": b"runtime library\n",
        })
        self.supervisor = b"supervisor\n"
        classifier_payload = {
            "codex-app-server": self.app_binary,
            "codex-process-supervisor": self.supervisor,
            "openai-codex-LICENSE.txt": b"license\n",
            "openai-codex-NOTICE.txt": b"notice\n",
        }
        classifier_manifest = {
            "schemaVersion": 1,
            "libraryVersion": COMPATIBILITY_VERSION,
            "appServerVersion": "0.149.0",
            "target": "linuxX64",
            "classifier": "app-server-linux-x64",
            "members": [
                {
                    "name": name,
                    "size": len(contents),
                    "sha256": sha256_bytes(contents).removeprefix("sha256:"),
                    "executable": name in {"codex-app-server", "codex-process-supervisor"},
                }
                for name, contents in sorted(classifier_payload.items())
            ],
        }
        _write_zip(self.app_server, {
            **classifier_payload,
            "codex-runtime-manifest.json": canonical_json_bytes(classifier_manifest),
        })
        self.distribution_manifest = root / "codex-app-server-distributions.json"
        write_canonical_json(self.distribution_manifest, {
            "version": "0.149.0",
            "releaseTag": "rust-v0.149.0",
            "distributions": [
                {
                    "target": name,
                    "classifier": spec.classifier,
                    "asset": f"{name}.zip",
                    "archiveSha256": sha256_bytes(name.encode()).removeprefix("sha256:"),
                    "archiveEntry": f"{name}.bin",
                    "binarySha256": (
                        sha256_bytes(self.app_binary).removeprefix("sha256:")
                        if name == "linuxX64" else sha256_bytes(name.encode()).removeprefix("sha256:")
                    ),
                    "executableName": "codex-app-server" if name != "mingwX64" else "codex-app-server.exe",
                    "supervisorExecutableName": (
                        "codex-process-supervisor" if name != "mingwX64"
                        else "codex-process-supervisor.exe"
                    ),
                }
                for name, spec in EVIDENCE_TARGETS.items()
            ],
        })
        self.validation = root / "validation.json"
        write_canonical_json(self.validation, build_desktop_evidence(
            _producer()["commit"],
            "linuxX64",
            sha256_bytes(self.app_binary).removeprefix("sha256:"),
            sha256_bytes(self.supervisor).removeprefix("sha256:"),
            sha256_file(self.app_server).removeprefix("sha256:"),
            test_task=imported_desktop_test_task("linuxX64"),
        ))

        contract_projection = {
            "schemaVersion": 1,
            "receiptSha256": DIGEST_A,
            "bundlePath": "outputs/codex-agent-contract-0.2.0.zip",
            "bundleSha256": DIGEST_B,
            "manifestSha256": DIGEST_C,
            "contractVersion": "0.2.0",
            "contractDigest": DIGEST_A,
            "componentDigests": [{"component": TARGET, "sha256": DIGEST_B}],
        }
        contract_upstream = [{
            "product": "contract",
            "component": "contract",
            "phase": "metadata",
            "target": "common",
            "buildKey": DIGEST_A,
            "outputsDigest": DIGEST_B,
            "contractProjection": contract_projection,
        }]
        self.toolchain = DIGEST_C
        binary_output = _record("binary/libcodex_agent.so", b"runtime library\n", "runtime-binary")
        self.receipts = {
            "binary": _receipt(
                "binary", _inputs("binary", contract_upstream, self.toolchain),
                [binary_output], signing["trustDomain"],
            ),
        }
        package_outputs = [
            {
                "kind": "app-server",
                "relativePath": f"outputs/app-server/{self.app_server.name}",
                "bytes": self.app_server.stat().st_size,
                "sha256": sha256_file(self.app_server),
            },
            {
                "kind": "c-abi",
                "relativePath": "outputs/c-abi/codex-agent-c.zip",
                "bytes": self.c_abi.stat().st_size,
                "sha256": sha256_file(self.c_abi),
            },
            _record("outputs/c-abi-reference/include/codex_agent.h", self.header, "c-abi-reference"),
            _record("outputs/validation-runner/runner.zip", b"runner\n", "validation-runner"),
        ]
        self.receipts["package"] = _receipt(
            "package", _inputs("package", [_reference(self.receipts["binary"])], self.toolchain),
            package_outputs, signing["trustDomain"],
        )
        self.receipts["validation"] = _receipt(
            "validation",
            _inputs("validation", [_reference(self.receipts["package"])], self.toolchain),
            [
                _record("outputs/c-abi/reference.txt", b"reference\n", "c-abi"),
                _record("outputs/native/validation.json", self.validation.read_bytes(), "native"),
                _record("outputs/native/other.json", b"other\n", "native"),
            ],
            signing["trustDomain"],
        )
        self.receipt_paths = {}
        for phase, value in self.receipts.items():
            path = root / f"{phase}-receipt.json"
            write_canonical_json(path, value)
            self.receipt_paths[phase] = path
        self.identity = derive_runtime_identity({
            "schemaVersion": 1,
            "binaryBuildKey": self.receipts["binary"]["buildKey"],
            "runtimeCompatibilityVersion": COMPATIBILITY_VERSION,
            "target": TARGET,
            "contract": {"digest": DIGEST_A, "componentDigest": DIGEST_B},
            "cAbi": {
                "version": "1.13.0",
                "minimumCompatibleVersion": "1.0.0",
                "identitySchemaVersion": 1,
                "headerSha256": sha256_bytes(self.header),
                "symbolSetSha256": DIGEST_A,
                "symbolCount": 778,
            },
            "appServer": {
                "version": "0.149.0",
                "releaseTag": "rust-v0.149.0",
                "binarySha256": sha256_bytes(self.app_binary),
            },
            "toolchainProfile": {"id": TARGET, "digest": self.toolchain},
        })
        self.output = root / "output"
        self.output.mkdir()

    def arguments(self) -> dict:
        return {
            "identity_envelope": self.identity,
            "binary_receipt": self.receipt_paths["binary"],
            "package_receipt": self.receipt_paths["package"],
            "validation_receipt": self.receipt_paths["validation"],
            "c_abi_archive": self.c_abi,
            "app_server_archive": self.app_server,
            "validation_evidence": self.validation,
            "distribution_manifest": self.distribution_manifest,
            "signing_metadata": self.signing,
            "private_key": self.private_key,
            "public_key": self.public_key,
            "output_directory": self.output,
        }

    def rewrite_receipt(self, phase: str, value: dict) -> None:
        value["buildKey"] = compute_build_key(
            product=value["product"], component=value["component"], phase=value["phase"],
            target=value["target"], inputs=value["inputs"],
        )
        write_canonical_json(self.receipt_paths[phase], value)


class RuntimeVariantProducerTest(unittest.TestCase):
    def test_output_is_deterministic_and_preserves_inner_archives(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            private_key, public_key, signing = generate_development_key(root / "keys")
            first = Fixture(root / "first", private_key, public_key, signing)
            second = Fixture(root / "second", private_key, public_key, signing)
            first_result = produce_runtime_variant(**first.arguments())
            second_result = produce_runtime_variant(**second.arguments())
            first_bytes = first_result["bundlePath"].read_bytes()
            self.assertEqual(first_bytes, second_result["bundlePath"].read_bytes())
            self.assertEqual(first_result["bundleSha256"], sha256_bytes(first_bytes))
            records, contents, _ = verified_zip_contents(
                first_result["bundlePath"], retained_paths={
                    "runtime-variant-manifest.json",
                    "c-abi/codex-agent-c.zip",
                    "app-server/codex-app-server.zip",
                }, canonical_stored=True,
            )
            self.assertTrue(records)
            self.assertEqual(first.c_abi.read_bytes(), contents["c-abi/codex-agent-c.zip"])
            self.assertEqual(
                first.app_server.read_bytes(), contents["app-server/codex-app-server.zip"],
            )
            manifest = validate_runtime_variant(load_canonical_json_bytes(
                contents["runtime-variant-manifest.json"],
            ))
            self.assertNotIn("producer", manifest)
            self.assertNotIn("runtimeVersion", manifest)
            self.assertEqual(TARGET, manifest["target"])
            self.assertEqual(TARGET, self.receipts_component(first, "binary"))

    @staticmethod
    def receipts_component(fixture: Fixture, phase: str) -> str:
        return load_canonical_json_bytes(fixture.receipt_paths[phase].read_bytes())["component"]

    def test_receipt_chain_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            private_key, public_key, signing = generate_development_key(root / "keys")
            fixture = Fixture(root / "fixture", private_key, public_key, signing)
            package = copy.deepcopy(fixture.receipts["package"])
            package["inputs"]["upstreamArtifacts"][0]["buildKey"] = DIGEST_C
            fixture.rewrite_receipt("package", package)
            with self.assertRaisesRegex(ValueError, "does not link exactly"):
                produce_runtime_variant(**fixture.arguments())

    def test_receipt_producer_and_release_provenance_do_not_change_bundle_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            private_key, public_key, signing = generate_development_key(root / "keys")
            first = Fixture(root / "first", private_key, public_key, signing)
            second = Fixture(root / "second", private_key, public_key, signing)
            for index, phase in enumerate(("binary", "package", "validation"), start=1):
                receipt = copy.deepcopy(second.receipts[phase])
                receipt["producer"]["commit"] = f"{index:x}" * 40
                receipt["producer"]["tree"] = f"{index + 3:x}" * 40
                receipt["producer"]["runId"] = 100 + index
                receipt["productVersion"] = "0.2.8"
                if phase == "validation":
                    report = load_canonical_json_bytes(second.validation.read_bytes())
                    report["candidateCommit"] = receipt["producer"]["commit"]
                    report["testTask"] = desktop_test_task("linuxX64")
                    write_canonical_json(second.validation, report)
                    selected = next(
                        output for output in receipt["outputs"]
                        if output["relativePath"] == "outputs/native/validation.json"
                    )
                    selected["bytes"] = second.validation.stat().st_size
                    selected["sha256"] = sha256_file(second.validation)
                write_canonical_json(second.receipt_paths[phase], receipt)
            first_result = produce_runtime_variant(**first.arguments())
            second_result = produce_runtime_variant(**second.arguments())
            self.assertEqual(first_result["componentId"], second_result["componentId"])
            self.assertEqual(first_result["bundleSha256"], second_result["bundleSha256"])

    def test_validation_projection_rejects_unrecognized_run_or_release_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            private_key, public_key, signing = generate_development_key(root / "keys")
            fixture = Fixture(root / "fixture", private_key, public_key, signing)
            report = load_canonical_json_bytes(fixture.validation.read_bytes())
            report["runtimeVersion"] = RUNTIME_VERSION
            write_canonical_json(fixture.validation, report)
            receipt = copy.deepcopy(fixture.receipts["validation"])
            selected = next(
                output for output in receipt["outputs"]
                if output["relativePath"] == "outputs/native/validation.json"
            )
            selected["bytes"] = fixture.validation.stat().st_size
            selected["sha256"] = sha256_file(fixture.validation)
            fixture.rewrite_receipt("validation", receipt)
            with self.assertRaisesRegex(ValueError, "fields are invalid"):
                produce_runtime_variant(**fixture.arguments())

    def test_archive_byte_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            private_key, public_key, signing = generate_development_key(root / "keys")
            fixture = Fixture(root / "fixture", private_key, public_key, signing)
            _write_zip(fixture.c_abi, {
                "include/codex_agent.h": fixture.header,
                "lib/libcodex_agent.so": b"tampered runtime library\n",
            })
            with self.assertRaisesRegex(ValueError, "exact package receipt output"):
                produce_runtime_variant(**fixture.arguments())

    def test_declared_app_server_binary_must_be_in_the_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            private_key, public_key, signing = generate_development_key(root / "keys")
            fixture = Fixture(root / "fixture", private_key, public_key, signing)
            with zipfile.ZipFile(fixture.app_server) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            members["codex-app-server"] = b"different app server\n"
            manifest = load_canonical_json_bytes(members["codex-runtime-manifest.json"])
            server = next(
                member for member in manifest["members"] if member["name"] == "codex-app-server"
            )
            server["size"] = len(members["codex-app-server"])
            server["sha256"] = sha256_bytes(members["codex-app-server"]).removeprefix("sha256:")
            members["codex-runtime-manifest.json"] = canonical_json_bytes(manifest)
            _write_zip(fixture.app_server, members)
            package = copy.deepcopy(fixture.receipts["package"])
            output = next(
                value for value in package["outputs"]
                if value["relativePath"].startswith("outputs/app-server/")
            )
            output["bytes"] = fixture.app_server.stat().st_size
            output["sha256"] = sha256_file(fixture.app_server)
            fixture.rewrite_receipt("package", package)
            validation = copy.deepcopy(fixture.receipts["validation"])
            validation["inputs"]["upstreamArtifacts"] = [_reference(package)]
            fixture.rewrite_receipt("validation", validation)
            with self.assertRaisesRegex(ValueError, "App Server hash is not pinned"):
                produce_runtime_variant(**fixture.arguments())

    def test_declared_app_server_version_must_match_the_distribution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            private_key, public_key, signing = generate_development_key(root / "keys")
            fixture = Fixture(root / "fixture", private_key, public_key, signing)
            source = copy.deepcopy(fixture.identity)
            source.pop("componentId")
            source.pop("runtimeIdentityJson")
            source["appServer"]["version"] = "0.150.0"
            source["appServer"]["releaseTag"] = "rust-v0.150.0"
            arguments = fixture.arguments()
            arguments["identity_envelope"] = derive_runtime_identity(source)
            with self.assertRaisesRegex(ValueError, "app-server archive identity mismatch"):
                produce_runtime_variant(**arguments)

    def test_symlink_and_output_extras_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            private_key, public_key, signing = generate_development_key(root / "keys")
            symlink_fixture = Fixture(root / "symlink", private_key, public_key, signing)
            linked = symlink_fixture.root / "linked-validation.json"
            linked.symlink_to(symlink_fixture.validation)
            arguments = symlink_fixture.arguments()
            arguments["validation_evidence"] = linked
            with self.assertRaisesRegex(ValueError, "missing or unsafe"):
                produce_runtime_variant(**arguments)

            extra_fixture = Fixture(root / "extra", private_key, public_key, signing)
            (extra_fixture.output / "unexpected.txt").write_text("extra", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be empty"):
                produce_runtime_variant(**extra_fixture.arguments())

    def test_direct_module_cli_uses_the_same_strict_producer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            private_key, public_key, signing = generate_development_key(root / "keys")
            fixture = Fixture(root / "fixture", private_key, public_key, signing)
            identity = fixture.root / "identity.json"
            signing_path = fixture.root / "signing.json"
            write_canonical_json(identity, fixture.identity)
            write_canonical_json(signing_path, signing)
            arguments = [
                "--identity", str(identity),
                "--binary-receipt", str(fixture.receipt_paths["binary"]),
                "--package-receipt", str(fixture.receipt_paths["package"]),
                "--validation-receipt", str(fixture.receipt_paths["validation"]),
                "--c-abi-archive", str(fixture.c_abi),
                "--app-server-archive", str(fixture.app_server),
                "--validation-evidence", str(fixture.validation),
                "--distribution-manifest", str(fixture.distribution_manifest),
                "--signing-metadata", str(signing_path),
                "--private-key", str(private_key),
                "--public-key", str(public_key),
                "--output-directory", str(fixture.output),
            ]
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(0, main(arguments))
            self.assertEqual(next(fixture.output.iterdir()), Path(output.getvalue().strip()))


if __name__ == "__main__":
    unittest.main()
