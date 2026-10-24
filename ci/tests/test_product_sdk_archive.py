from __future__ import annotations

import io
from pathlib import Path
import shutil
import stat
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json, load_canonical_json_bytes,
    regular_file_inventory, sha256_bytes, snapshot_regular_tree,
)
from ci.products.receipt import (
    compute_build_key, output_inventory_digest, write_output_manifest, write_phase_receipt,
)
from ci.products.sdk_archive import (
    NPM_COMPATIBILITY_PATH, main, verify_javascript_sdk_package_phase,
    verify_npm_sdk_compatibility,
)
from ci.tests.test_product_native_chain import build_chain
from ci.tests.test_product_sdk_inputs import _request
from ci.tests.test_products import phase_receipt, sdk_compatibility


def _tar(path: Path, members: list[tuple[str, bytes]]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, contents in members:
            entry = tarfile.TarInfo(name)
            entry.mode = stat.S_IFREG | 0o644
            entry.size = len(contents)
            archive.addfile(entry, io.BytesIO(contents))


class SdkArchiveTest(unittest.TestCase):
    def test_npm_directory_names_share_one_canonical_member_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            compatibility = root / "sdk-compatibility.json"
            compatibility.write_bytes(canonical_json_bytes(sdk_compatibility()))
            archive = root / "codex-agent-0.2.0.tgz"
            output = root / "evidence.json"
            for directories, collision, valid in (
                (("package", "package/dist"), None, True),
                (("package/", "package/dist/"), None, True),
                (("package", "package/"), None, False),
                (("package",), "package", False),
                (("package//dist",), None, False),
            ):
                with self.subTest(directories=directories, collision=collision):
                    with tarfile.open(archive, "w:gz") as package:
                        for name in directories:
                            entry = tarfile.TarInfo(name)
                            entry.type = tarfile.DIRTYPE
                            package.addfile(entry)
                        for name, contents in (
                            (NPM_COMPATIBILITY_PATH, compatibility.read_bytes()),
                            ("package/package.json", b'{"name":"@codex-agent-labs/codex-agent","version":"0.2.0"}'),
                            *([(collision, b"collision")] if collision else []),
                        ):
                            entry = tarfile.TarInfo(name)
                            entry.size = len(contents)
                            package.addfile(entry, io.BytesIO(contents))
                    if not valid:
                        with self.assertRaisesRegex(ValueError, "unsafe or duplicate"):
                            verify_npm_sdk_compatibility(archive, compatibility, output, sdk_version="0.2.0")
                    else:
                        verify_npm_sdk_compatibility(archive, compatibility, output, sdk_version="0.2.0")

    def test_npm_archive_binds_one_exact_compatibility_member(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            compatibility = root / "sdk-compatibility.json"
            compatibility.write_bytes(canonical_json_bytes(sdk_compatibility()))
            archive = root / "codex-agent-0.2.0.tgz"
            output = root / "evidence.json"
            metadata = ("package/package.json", b'{"name":"@codex-agent-labs/codex-agent","version":"0.2.0"}')
            _tar(archive, [(NPM_COMPATIBILITY_PATH, compatibility.read_bytes()), metadata])
            verify_npm_sdk_compatibility(archive, compatibility, output, sdk_version="0.2.0")
            evidence = load_canonical_json(output)
            self.assertEqual("passed", evidence["result"])
            self.assertEqual(NPM_COMPATIBILITY_PATH, evidence["sdkCompatibility"]["path"])
            self.assertEqual(
                ["linux-arm64", "linux-x64", "macos-arm64", "macos-x64", "windows-x64"],
                evidence["sdkCompatibility"]["embeddedTargets"],
            )

            for members in (
                [("package/wrong/sdk-compatibility.json", compatibility.read_bytes())],
                [(NPM_COMPATIBILITY_PATH, b"changed")],
                [(NPM_COMPATIBILITY_PATH, compatibility.read_bytes())] * 2,
                [(NPM_COMPATIBILITY_PATH, compatibility.read_bytes()), ("package/a//b", b"")],
                [(NPM_COMPATIBILITY_PATH, compatibility.read_bytes()), ("package/bad\nname", b"")],
            ):
                with self.subTest(members=members):
                    _tar(archive, members)
                    with self.assertRaisesRegex(ValueError, "inventory mismatch|duplicate"):
                        verify_npm_sdk_compatibility(archive, compatibility, output, sdk_version="0.2.0")

            compatibility.write_bytes(b'{"schemaVersion":1}\n')
            _tar(archive, [(NPM_COMPATIBILITY_PATH, compatibility.read_bytes())])
            with self.assertRaises(ValueError):
                verify_npm_sdk_compatibility(archive, compatibility, output, sdk_version="0.2.0")

    def test_npm_identity_matches_requested_phase_and_compatibility_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            compatibility = root / "sdk-compatibility.json"
            archive = root / "codex-agent-0.2.0.tgz"
            output = root / "evidence.json"
            declaration = sdk_compatibility()
            compatibility.write_bytes(canonical_json_bytes(declaration))
            metadata = ("package/package.json", b'{"name":"@codex-agent-labs/codex-agent","version":"0.2.0"}')

            def pack(record: tuple[str, bytes] | None = metadata) -> None:
                _tar(archive, [(NPM_COMPATIBILITY_PATH, compatibility.read_bytes())]
                     + ([record] if record else []))

            pack()
            self.assertEqual(0, main([
                "--archive", str(archive), "--compatibility", str(compatibility),
                "--output", str(output), "--version", "0.2.0",
            ]))
            self.assertEqual("0.2.0", load_canonical_json(output)["sdkVersion"])
            for contents in (
                b'{"name":"@codex-agent-labs/codex-agent","version":"0.2.1"}',
                b'{"name":"other","version":"0.2.0"}',
                b'{"name":"@codex-agent-labs/codex-agent","version":"0.2.1","version":"0.2.0"}',
                b'[]',
            ):
                with self.subTest(metadata=contents):
                    pack(("package/package.json", contents))
                    with self.assertRaises(ValueError):
                        verify_npm_sdk_compatibility(archive, compatibility, output, sdk_version="0.2.0")
            pack(None)
            with self.assertRaises(ValueError):
                verify_npm_sdk_compatibility(archive, compatibility, output, sdk_version="0.2.0")
            pack()
            with self.assertRaisesRegex(ValueError, "archive SDK version"):
                verify_npm_sdk_compatibility(archive, compatibility, output, sdk_version="0.2.1")
            declaration["sdkVersion"] = "0.2.1"
            compatibility.write_bytes(canonical_json_bytes(declaration))
            pack()
            with self.assertRaisesRegex(ValueError, "compatibility SDK version"):
                verify_npm_sdk_compatibility(archive, compatibility, output, sdk_version="0.2.0")

    def test_npm_archive_rejects_oversized_json_members_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            compatibility = root / "sdk-compatibility.json"
            compatibility.write_bytes(canonical_json_bytes(sdk_compatibility()))
            archive = root / "codex-agent-0.2.0.tgz"
            output = root / "evidence.json"
            oversized = b"x" * (16 * 1024 * 1024 + 1)
            metadata = b'{"name":"@codex-agent-labs/codex-agent","version":"0.2.0"}'
            for members, error in (
                ([(NPM_COMPATIBILITY_PATH, oversized), ("package/package.json", metadata)],
                 "compatibility member exceeds"),
                ([(NPM_COMPATIBILITY_PATH, compatibility.read_bytes()),
                  ("package/package.json", oversized)], "package metadata exceeds"),
            ):
                with self.subTest(error=error):
                    _tar(archive, members)
                    with self.assertRaisesRegex(ValueError, error):
                        verify_npm_sdk_compatibility(archive, compatibility, output, sdk_version="0.2.0")
                    self.assertFalse(output.exists())
            with patch("ci.products.sdk_archive._ARCHIVE_LIMIT", 1024 * 1024):
                _tar(archive, [("package/large.bin", b"x" * (1024 * 1024 + 1))])
                with self.assertRaisesRegex(ValueError, "expanded bytes exceed"):
                    verify_npm_sdk_compatibility(archive, compatibility, output, sdk_version="0.2.0")
            with tarfile.open(archive, "w:gz") as package:
                directory = tarfile.TarInfo("package/odd/")
                directory.type = tarfile.DIRTYPE
                directory.size = 12
                package.addfile(directory, io.BytesIO(b"bad-data-123"))
            with self.assertRaisesRegex(ValueError, "unsafe or duplicate npm archive member"):
                verify_npm_sdk_compatibility(archive, compatibility, output, sdk_version="0.2.0")


@unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH signing tool unavailable")
class JavaScriptSdkPackagePhaseTest(unittest.TestCase):
    """Synthetic signed products prove semantics, not execution or campaign admission."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="javascript-sdk-package-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.chain = build_chain(cls.root / "synthetic-products", 79)
        aggregate = load_canonical_json(cls.chain["compatibility_args"]["runtime_manifest"])
        cls.runtime_compatibility_version = aggregate["runtimeCompatibilityVersion"]
        cls.aggregate_runtime_version = aggregate["runtimeVersion"]
        cls.runtime_package_version = "0.2.6"
        cls.request = cls.root / "sdk-compatibility-request.json"
        cls.request.write_bytes(canonical_json_bytes(_request(cls.chain["compatibility_args"])))

        cls.runtime_stage = cls.root / "runtime-stage"
        adapter = cls.runtime_stage / "outputs/adapter"
        adapter.mkdir(parents=True)
        cls.runtime_files = {
            "runtime.js": b"export const runtime = 1;\n",
            "runtime.js.map": b'{"version":3}\n',
        }
        for name, contents in cls.runtime_files.items():
            (adapter / name).write_bytes(contents)
        (adapter / "runtime.d.ts").write_bytes(b"export declare const generated: number;\n")
        write_output_manifest(
            cls.runtime_stage, "runtime", "node-js", "package", "node-js",
            cls.runtime_package_version,
            {"adapter": "outputs/adapter"},
        )
        runtime_inputs = phase_receipt()["inputs"]
        runtime_inputs["versionIdentity"] = cls.runtime_compatibility_version
        runtime_receipts = cls.root / "runtime-receipt"
        runtime_receipts.mkdir()
        write_phase_receipt(
            cls.runtime_stage, runtime_receipts, "runtime", "node-js", "package", "node-js",
            cls.runtime_package_version, compute_build_key(
                product="runtime", component="node-js", phase="package", target="node-js",
                inputs=runtime_inputs,
            ), runtime_inputs, cls.chain["context"]["producer"], "development",
        )
        cls.runtime_receipt = runtime_receipts / "phase-receipt.json"

        cls.stage = cls.root / "sdk-stage"
        archive = cls.stage / "outputs/package/codex-agent-0.2.9.tgz"
        archive.parent.mkdir(parents=True)
        compatibility = cls.chain["compatibility"].read_bytes()
        _tar(archive, [
            (NPM_COMPATIBILITY_PATH, compatibility),
            ("package/package.json",
             b'{"name":"@codex-agent-labs/codex-agent","version":"0.2.9"}'),
            ("package/index.d.ts", b"export declare const reviewed: string;\n"),
            *((f"package/dist/{name}", contents) for name, contents in cls.runtime_files.items()),
        ])
        evidence = cls.stage / "outputs/evidence"
        evidence.mkdir(parents=True)
        (evidence / "sdk-compatibility.json").write_bytes(compatibility)
        verify_npm_sdk_compatibility(
            archive, evidence / "sdk-compatibility.json",
            evidence / "sdk-compatibility-archive.json", sdk_version="0.2.9",
        )
        write_output_manifest(
            cls.stage, "sdk", "javascript", "package", "node", "0.2.9",
            {"evidence": "outputs/evidence", "package": "outputs/package"},
        )
        runtime = load_canonical_json(cls.runtime_receipt)
        runtime_reference = {
            key: runtime[key] for key in ("product", "component", "phase", "target", "buildKey")
        }
        runtime_reference["outputsDigest"] = output_inventory_digest(runtime["outputs"])
        sdk_inputs = phase_receipt()["inputs"]
        sdk_inputs["versionIdentity"] = "0.2.9"
        sdk_inputs["upstreamArtifacts"] = [runtime_reference]
        sdk_receipts = cls.root / "sdk-receipt"
        sdk_receipts.mkdir()
        write_phase_receipt(
            cls.stage, sdk_receipts, "sdk", "javascript", "package", "node", "0.2.9",
            compute_build_key(
                product="sdk", component="javascript", phase="package", target="node",
                inputs=sdk_inputs,
            ), sdk_inputs, cls.chain["context"]["producer"], "development",
        )
        cls.receipt = sdk_receipts / "phase-receipt.json"

    def _copy(self, root: Path) -> tuple[Path, Path, Path, Path, Path]:
        stage, runtime = root / "stage", root / "runtime"
        snapshot_regular_tree(self.stage, stage)
        snapshot_regular_tree(self.runtime_stage, runtime)
        receipt, runtime_receipt, request = (
            root / "receipt.json", root / "runtime-receipt.json", root / "request.json",
        )
        receipt.write_bytes(self.receipt.read_bytes())
        runtime_receipt.write_bytes(self.runtime_receipt.read_bytes())
        request.write_bytes(self.request.read_bytes())
        return stage, receipt, request, runtime, runtime_receipt

    @staticmethod
    def _rebind(stage: Path, receipt: Path, product: str, component: str,
                phase: str, target: str, version: str, roots: dict[str, str],
                *, version_identity: str | None = None) -> None:
        manifest = write_output_manifest(stage, product, component, phase, target, version, roots)
        value = load_canonical_json(receipt)
        value.update(product=product, component=component, phase=phase,
                     target=target, productVersion=version)
        if version_identity is not None:
            value["inputs"]["versionIdentity"] = version_identity
        value["outputs"] = manifest["outputs"]
        value["buildKey"] = compute_build_key(
            product=product, component=component, phase=phase, target=target,
            inputs=value["inputs"],
        )
        receipt.write_bytes(canonical_json_bytes(value))

    def test_exact_runtime_javascript_package_is_verified_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            arguments = self._copy(Path(temporary).resolve())
            stage, receipt, request, runtime, runtime_receipt = arguments
            before = regular_file_inventory(stage), regular_file_inventory(runtime)
            receipt_bytes = receipt.read_bytes()
            result, encoded = verify_javascript_sdk_package_phase(*arguments)
            self.assertEqual("0.2.0", self.runtime_compatibility_version)
            self.assertEqual("0.2.6", self.runtime_package_version)
            self.assertEqual("0.2.7", self.aggregate_runtime_version)
            self.assertEqual(result, load_canonical_json_bytes(receipt_bytes))
            self.assertEqual(encoded, receipt_bytes)
            self.assertEqual(before, (regular_file_inventory(stage), regular_file_inventory(runtime)))
            with tarfile.open(stage / "outputs/package/codex-agent-0.2.9.tgz", "r:gz") as package:
                self.assertEqual(
                    b"export declare const reviewed: string;\n",
                    package.extractfile("package/index.d.ts").read(),
                )

    def test_stage_receipt_compatibility_and_runtime_cross_pairs_fail_closed(self) -> None:
        for case in (
            "sdk-identity", "runtime-identity", "runtime-version", "runtime-version-identity",
            "compatibility", "report", "runtime-bytes", "archive-bytes",
            "missing-runtime-reference",
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                stage, receipt, request, runtime, runtime_receipt = self._copy(
                    Path(temporary).resolve(),
                )
                if case == "sdk-identity":
                    self._rebind(
                        stage, receipt, "sdk", "sdk-core", "package", "node", "0.2.9",
                        {"evidence": "outputs/evidence", "package": "outputs/package"},
                    )
                elif case == "runtime-identity":
                    self._rebind(
                        runtime, runtime_receipt, "runtime", "node-wasm", "package",
                        "node-js", self.runtime_package_version, {"adapter": "outputs/adapter"},
                    )
                elif case == "runtime-version":
                    self._rebind(
                        runtime, runtime_receipt, "runtime", "node-js", "package",
                        "node-js", "0.3.0", {"adapter": "outputs/adapter"},
                        version_identity=self.runtime_compatibility_version,
                    )
                elif case == "runtime-version-identity":
                    self._rebind(
                        runtime, runtime_receipt, "runtime", "node-js", "package",
                        "node-js", self.runtime_package_version, {"adapter": "outputs/adapter"},
                        version_identity="0.2.1",
                    )
                elif case in {"compatibility", "report"}:
                    path = stage / "outputs/evidence" / (
                        "sdk-compatibility.json" if case == "compatibility"
                        else "sdk-compatibility-archive.json"
                    )
                    path.write_bytes(path.read_bytes() + b"\n")
                    self._rebind(
                        stage, receipt, "sdk", "javascript", "package", "node", "0.2.9",
                        {"evidence": "outputs/evidence", "package": "outputs/package"},
                    )
                elif case == "runtime-bytes":
                    (runtime / "outputs/adapter/runtime.js").write_bytes(b"changed\n")
                    self._rebind(
                        runtime, runtime_receipt, "runtime", "node-js", "package",
                        "node-js", self.runtime_package_version, {"adapter": "outputs/adapter"},
                    )
                elif case == "archive-bytes":
                    archive = stage / "outputs/package/codex-agent-0.2.9.tgz"
                    compatibility = (stage / "outputs/evidence/sdk-compatibility.json").read_bytes()
                    _tar(archive, [
                        (NPM_COMPATIBILITY_PATH, compatibility),
                        ("package/package.json",
                         b'{"name":"@codex-agent-labs/codex-agent","version":"0.2.9"}'),
                        ("package/index.d.ts", b"export declare const reviewed: string;\n"),
                        ("package/dist/runtime.js", b"changed\n"),
                        ("package/dist/runtime.js.map", self.runtime_files["runtime.js.map"]),
                    ])
                    verify_npm_sdk_compatibility(
                        archive, stage / "outputs/evidence/sdk-compatibility.json",
                        stage / "outputs/evidence/sdk-compatibility-archive.json",
                        sdk_version="0.2.9",
                    )
                    self._rebind(
                        stage, receipt, "sdk", "javascript", "package", "node", "0.2.9",
                        {"evidence": "outputs/evidence", "package": "outputs/package"},
                    )
                else:
                    value = load_canonical_json(receipt)
                    value["inputs"]["upstreamArtifacts"] = []
                    value["buildKey"] = compute_build_key(
                        product="sdk", component="javascript", phase="package", target="node",
                        inputs=value["inputs"],
                    )
                    receipt.write_bytes(canonical_json_bytes(value))
                with self.assertRaises(ValueError):
                    verify_javascript_sdk_package_phase(
                        stage, receipt, request, runtime, runtime_receipt,
                    )

if __name__ == "__main__":
    unittest.main()
