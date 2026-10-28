"""Real package composition over synthetic products, not hosted admission evidence."""

from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_native_phase as worker
from ci.tests.product_chain_sdk import _materialize_sources, _stage_sdks
from ci.tests.test_product_native_chain import build_chain
from native_wrappers import package_all, set_source_sdk_version
from products.inventory import canonical_json_bytes, regular_file_inventory
from products.receipt import write_output_manifest


@unittest.skipUnless(shutil.which("ssh-keygen") and shutil.which("dart"),
                     "OpenSSH and Dart are required for the content fixture")
class NativePythonPackageContentTest(unittest.TestCase):
    def test_python_recipe_matches_existing_task_composition_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory(prefix="native-python-package-content-") as temporary:
            root = Path(temporary).resolve()
            chain = build_chain(root / "synthetic-products", 31)
            inputs = root / "inputs"
            inputs.mkdir()
            sdks, version = _stage_sdks(inputs, chain["variants"], chain["compatibility"], chain["context"])
            sources = _materialize_sources(inputs, sdks, ("dart",))
            set_source_sdk_version(sources, version, ("dart",))
            version_file = root / "gradle/release/versions/sdk.txt"
            version_file.parent.mkdir(parents=True)
            version_file.write_text(version + "\n", encoding="utf-8")
            request = root / "request.json"
            request.write_bytes(canonical_json_bytes({"fixture": "caller authenticates this request"}))
            fields = {"codexAgent." + key: value for key, value in {
                "product": "sdk", "component": "dart", "phase": "package", "target": "desktop",
                "sdkVersion": version, "candidateCommit": "a" * 40, "candidateTree": "b" * 40,
                "nativeWrapperRuntimeStageRoot": str(chain["variants"]["stages"]),
                "nativeWrapperPackageSourcesRoot": str(sources),
                "nativeWrapperPackageSdksRoot": str(sdks), "sdkCompatibilityRequest": str(request),
            }.items()}
            before = regular_file_inventory(inputs)
            # Host/source admission is deliberately a fixture seam. The actual
            # package producer, archive checks and canonical manifest writer run.
            with patch("native_wrappers.host_classifier", return_value="linux-x64"), \
                    patch("product_reuse._runtime_worker_checkout"), \
                    patch("native_wrappers.run", side_effect=AssertionError("Unexpected build/pub command")):
                worker._package_only(root, fields, {})
                expected = root / "existing-task-composition"
                package_all(sources, sdks, expected / "outputs", version, ("dart",))
                evidence = expected / "outputs/evidence"
                evidence.mkdir()
                for name in ("sdk-compatibility.json", "sdk-runtime-root.pub"):
                    shutil.copyfile(sdks / name, evidence / name)
                write_output_manifest(expected, "sdk", "dart", "package", "desktop", version,
                                      {"evidence": "outputs/evidence", "package": "outputs/dart"})
                actual = root / "codex-agent-sdk/build/product-stage/sdk/dart/package"
                self.assertEqual(regular_file_inventory(expected), regular_file_inventory(actual))
                self.assertEqual(before, regular_file_inventory(inputs))
                shutil.rmtree(actual)  # Only this fixture's disposable output.
                library = sources / "dart/lib/src/native/linux-x64/libcodex_agent.so"
                library.write_bytes(library.read_bytes() + b"tampered")
                with self.assertRaises(ValueError):
                    worker._package_only(root, fields, {})
                self.assertFalse((actual / "output-manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
