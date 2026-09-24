"""Core metadata bootstrap must derive all eleven requests from selected originals."""

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci import sdk_core_metadata_bootstrap as bootstrap
from ci.products.inventory import sha256_bytes, write_canonical_json


_KEY = "sha256:" + "a" * 64


class CoreMetadataBootstrapTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve(strict=True)
        self.root = self.base / "checkout"
        self.root.mkdir()
        (self.root / "build").mkdir()
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(b"plan\n")
        self.discovery = self.root / "build/discovery"
        self.state = self.root / "build/state"
        self.discovery.mkdir()
        self.state.mkdir()
        self.tooling = self.base / "tooling.json"
        write_canonical_json(self.tooling, {"evidence": "/tooling", "publicKey": "/key",
            "javaExecutable": "/java", "requiredTrustDomain": "release",
            "keyring": "/keyring", "keysDirectory": "/keys"})
        self.receipts = {}
        retained = {}
        for target in bootstrap.SDK_FACADE_TARGETS:
            value = {"product": "sdk", "component": "sdk-core", "phase": "validation",
                     "target": target, "buildKey": _KEY}
            receipt = bootstrap.product_reuse.canonical_json_bytes(value)
            self.receipts[target] = receipt
            retained[bootstrap.PhaseInstanceId("sdk", "sdk-core", "validation", target)] = {
                "state": "retained", "buildKey": _KEY,
                "receiptSha256": sha256_bytes(receipt)}
        self.verified = SimpleNamespace(prior_ready_plans={bootstrap._METADATA: {"buildKey": _KEY}},
            prior_by_instance=retained, sources={phase: object() for phase in retained},
            plan={"validationCommit": "b" * 40})

    def invoke(self, *, bad_target=None):
        def request(_plan, _discovery, _state, output, **kwargs):
            target = kwargs["target"]
            self.assertEqual(_KEY, kwargs["expected_metadata_build_key"])
            self.assertEqual(_KEY, kwargs["expected_build_key"])
            self.assertNotIn("facade_request", kwargs)
            receipt = output / f"predecessors/sdk-sdk-core-validation-{target}/phase-receipt.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_bytes(self.receipts["jvm" if target == bad_target else target])
            path = output / "facade-request.json"
            path.write_bytes(b"{}\n")
            return {"facadeRequest": str(path)}

        def projection(instance, _versions, _evidence):
            return SimpleNamespace(receipt_value=lambda: {
                "contractVersion": "0.8.0", "contractDigest": "sha256:" + "c" * 64,
                "componentDigests": [{"component": instance.target,
                                      "sha256": "sha256:" + "d" * 64}]})

        archives = {target: self.base / "caller-archive.tar.gz" for target in bootstrap._NATIVE}
        with (patch.object(bootstrap.product_reuse, "_verified_product_state", return_value=self.verified),
              patch.object(bootstrap, "_native_archives", return_value=(archives, {})),
              patch.object(bootstrap, "prepare_validation_request", side_effect=request) as prepared,
              patch.object(bootstrap, "validate_phase_receipt", side_effect=lambda value: value),
              patch.object(bootstrap, "_request", return_value=(
                  {"contractVersion": "0.8.0", "validationContractEvidence": {}}, b"{}\n")),
              patch.object(bootstrap, "_contract_projection_from_request", side_effect=projection)):
            value = bootstrap.prepare(self.plan, self.discovery, self.state,
                self.root / "build/metadata-requests", self.base / "bootstrap.json",
                expected_build_key=_KEY, sdk_inputs_artifact_id=7,
                sdk_inputs_artifact_sha256=_KEY, trusted_workflow_sha="e" * 40,
                sdk_validation_tooling=self.tooling, native_compiler_archives={},
                keyring=self.root / "keyring", keys_directory=self.root / "keys",
                repository_root=self.root, environ={}, token="local-token")
        return value, prepared

    def test_projects_all_elected_originals_without_uploaded_request_authority(self):
        output, prepared = self.invoke()
        self.assertEqual(11, prepared.call_count)
        policy = bootstrap.load_canonical_json_bytes(output.read_bytes())
        self.assertEqual(set(bootstrap.SDK_FACADE_TARGETS), set(policy["validations"]))
        self.assertEqual("sha256:" + "c" * 64, policy["contractDigest"])
        self.assertEqual(set(bootstrap.SDK_FACADE_CONTRACT_COMPONENTS.values()),
                         set(policy["componentDigests"]))
        self.assertTrue(all("nativeCompilerArchive" in policy["validations"][target]
                            for target in bootstrap._NATIVE))
        self.assertTrue(all("nativeCompilerArchive" not in policy["validations"][target]
                            for target in bootstrap._NON_NATIVE_TARGETS))

    def test_cross_paired_original_fails_before_policy_publication(self):
        with self.assertRaisesRegex(ValueError, "selected original validation"):
            self.invoke(bad_target="linux-x64")
        self.assertFalse((self.base / "bootstrap.json").exists())

    def test_native_hosts_require_exact_git_pinned_archive_names_without_download(self):
        archives = {}
        for target in bootstrap._NATIVE:
            archive = self.base / (target + ".tar.gz")
            archive.write_bytes(b"local-only")
            archives[target] = archive
        sources = iter((b"[versions]\nkotlin = '2.3.10'\n", b"immutable metadata"))
        names = []

        def pin(_metadata, name):
            names.append(name)
            return "sha256:" + "f" * 64

        with (patch.object(bootstrap, "git_regular_blob_bytes", side_effect=lambda *_args, **_kw: next(sources)),
              patch.object(bootstrap, "_metadata_checksum", side_effect=pin),
              patch.object(bootstrap, "sha256_file", return_value="sha256:" + "f" * 64)):
            selected, _ = bootstrap._native_archives(self.root, "b" * 40, archives)
        self.assertEqual(archives, selected)
        self.assertEqual({f"kotlin-native-prebuilt-2.3.10-{suffix}.tar.gz" for suffix in
            ("macos-aarch64", "macos-x86_64", "linux-aarch64", "linux-x86_64")} |
            {"kotlin-native-prebuilt-2.3.10-windows-x86_64.zip"}, set(names))

        # A legacy Windows TAR pin must not authorize the published Windows ZIP.
        digest = "f" * 64
        legacy = ("<verification-metadata>" + "".join(
            f'<artifact name="kotlin-native-prebuilt-2.3.10-{suffix}.tar.gz">'
            f'<sha256 value="{digest}"/></artifact>' for suffix in
            ("macos-aarch64", "macos-x86_64", "linux-aarch64", "linux-x86_64", "windows-x86_64")) +
            "</verification-metadata>").encode()
        sources = iter((b"[versions]\nkotlin = '2.3.10'\n", legacy))
        with (patch.object(bootstrap, "git_regular_blob_bytes", side_effect=lambda *_args, **_kw: next(sources)),
              patch.object(bootstrap, "sha256_file", return_value="sha256:" + "f" * 64),
              self.assertRaisesRegex(ValueError, "windows-x86_64.zip")):
            bootstrap._native_archives(self.root, "b" * 40, archives)

        sources = iter((b"[versions]\nkotlin = '2.3.10'\n", b"only the macOS Arm64 pin exists"))
        with (patch.object(bootstrap, "git_regular_blob_bytes", side_effect=lambda *_args, **_kw: next(sources)),
              patch.object(bootstrap, "_metadata_checksum", side_effect=ValueError("no immutable pin")),
              patch.object(bootstrap, "sha256_file", return_value="sha256:" + "f" * 64),
              self.assertRaisesRegex(ValueError, "no immutable pin")):
            bootstrap._native_archives(self.root, "b" * 40, archives)


if __name__ == "__main__":
    unittest.main()
