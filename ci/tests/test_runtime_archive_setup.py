"""Synthetic Git/spec and local capture checks; no downloads or host acceptance."""
import copy
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime_native_phase
from products.inventory import canonical_json_bytes, sha256_bytes, write_canonical_json
from products.receipt import compute_build_key
from products.registry import NATIVE_TARGETS
from ci.tests import test_runtime_native_archive as archive_fixture


class RuntimeArchiveSetupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        archive_fixture.RuntimeNativeArchiveTest.setUpClass.__func__(cls)

    setUp = archive_fixture.RuntimeNativeArchiveTest.setUp
    plan = archive_fixture.RuntimeNativeArchiveTest.plan

    def spec(self, plan=None):
        return runtime_native_phase.archive_spec(
            self.plan() if plan is None else plan,
            repository_root=self.repository, revision=self.revision)

    def cli(self, command, *arguments):
        plan_path = self.work / "phase-plan.json"
        write_canonical_json(plan_path, self.plan())
        return runtime_native_phase.main([
            command, "--phase-plan", str(plan_path), "--revision", self.revision,
            "--repository-root", str(self.repository), *arguments])

    def test_all_five_specs_have_exact_git_pinned_url_asset_and_digest(self):
        for target in NATIVE_TARGETS:
            with self.subTest(target=target):
                asset = f"codex-{target}.tar.gz"
                self.assertEqual({"asset": asset,
                                  "url": f"https://github.com/openai/codex/releases/download/rust-v0.149.0/{asset}",
                                  "sha256": sha256_bytes(self.archives[target])}, self.spec(self.plan(target)))

    def test_working_copy_does_not_supply_url_or_hash_authority(self):
        original = self.manifest_path.read_bytes()
        try:
            self.manifest_path.write_bytes(b"not a manifest")
            self.assertEqual(sha256_bytes(self.archives["linux-arm64"]), self.spec()["sha256"])
        finally:
            self.manifest_path.write_bytes(original)

    def test_coherently_keyed_unsafe_release_and_asset_are_rejected(self):
        for version, asset in (("0.149.0/../../other", "codex.tar.gz"),
                               ("0.149.0\nurl=evil", "codex.tar.gz"),
                               ("0.149.0", "codex?redirect=evil"),
                               ("0.149.0", "codex%2fother")):
            with self.subTest(version=version, asset=asset):
                manifest = copy.deepcopy(self.manifest)
                manifest.update(version=version, releaseTag=f"rust-v{version}")
                for record in manifest["distributions"]:
                    record["asset"] = asset
                raw = canonical_json_bytes(manifest)
                plan = self.plan()
                plan["inputs"]["inventory"] = [{"relativePath": runtime_native_phase._DISTRIBUTION_MANIFEST,
                                                   "bytes": len(raw), "sha256": sha256_bytes(raw)}]
                plan["inputs"]["phaseInputDigest"] = sha256_bytes(canonical_json_bytes(plan["inputs"]["inventory"]))
                plan["buildKey"] = compute_build_key(product="runtime", component="linux-arm64", phase="binary",
                                                     target="linux-arm64", inputs=plan["inputs"])
                with mock.patch.object(runtime_native_phase, "git_regular_blob_bytes", return_value=raw):
                    with self.assertRaises(ValueError):
                        self.spec(plan)

    def test_cli_outputs_spec_then_captures_verifies_and_never_overwrites_cache(self):
        spec = self.spec()
        cache = self.repository / "build/runtime-upstream" / spec["sha256"].removeprefix("sha256:")
        # The class TemporaryDirectory owns this synthetic cache and its cleanup.
        github_output = self.work / "github-output"
        with mock.patch.object(runtime_native_phase.sys, "stdout") as stdout:
            stdout.buffer = io.BytesIO()
            self.assertEqual(0, self.cli("archive-spec", "--github-output", str(github_output)))
            self.assertEqual(canonical_json_bytes(spec), stdout.buffer.getvalue())
        lines = dict(line.split("=", 1) for line in github_output.read_text().splitlines())
        self.assertEqual({**spec, "directory": str(cache), "archive": str(cache / spec["asset"])}, lines)
        self.assertFalse(cache.exists())
        before = self.source.read_bytes()
        self.assertEqual(0, self.cli("capture-archive", "--source", str(self.source)))
        self.assertEqual(0, self.cli("verify-archive"))
        self.assertEqual(before, self.source.read_bytes())
        self.assertEqual(before, (cache / spec["asset"]).read_bytes())
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.cli("archive-spec")
        with self.assertRaisesRegex(ValueError, "must not exist"):
            self.cli("capture-archive", "--source", str(self.source))
        (cache / "unexpected").write_bytes(b"not an archive")
        with self.assertRaisesRegex(ValueError, "exactly"):
            self.cli("verify-archive")
        (cache / "unexpected").unlink()
        (cache / spec["asset"]).write_bytes(b"corrupt restored cache")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.cli("verify-archive")

    def test_action_is_content_pinned_bounded_https_only_and_verifies_cache_hits(self):
        action = (Path(__file__).resolve().parents[2] / ".github/actions/setup-runtime-archive/action.yml").read_text()
        self.assertIn("actions/cache/restore@0057852bfaa89a56745cba8c7296529d2fc39830", action)
        self.assertIn("actions/cache/save@55cc8345863c7cc4c66a329aec7e433d2d1c52a9", action)
        self.assertNotIn("restore-keys:", action)
        self.assertIn("key: runtime-upstream-v1-${{ steps.spec.outputs.sha256 }}", action)
        self.assertIn("--proto '=https' --proto-redir '=https'", action)
        self.assertIn("--max-filesize 536870912", action)
        self.assertIn('--output "$runtime_archive_download" "$ARCHIVE_URL"', action)
        self.assertIn('mktemp "$RUNNER_TEMP/runtime-upstream.XXXXXXXX"', action)
        verify = action.split("- name: Verify restored or captured archive", 1)[1].split("- if:", 1)[0]
        self.assertNotIn("if:", verify)
        self.assertIn("verify-archive", verify)
        self.assertLess(action.index("archive-spec"), action.index("actions/cache/restore@"))
        self.assertLess(action.index("verify-archive"), action.index("actions/cache/save@"))
        self.assertNotIn("gradlew", action)
