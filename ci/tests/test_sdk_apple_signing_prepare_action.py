"""Executed no-secret action composition; both controller processes are mocked."""

import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from ci.products.inventory import canonical_json_bytes, sha256_bytes


ROOT = Path(__file__).resolve().parents[2]
TREE, KEY = "a" * 40, "sha256:" + "b" * 64


class AppleSigningPrepareActionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="apple-signing-prepare-action-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repository, self.scratch = self.root / "candidate checkout", self.root / "runner temp"
        self.repository.mkdir()
        self.scratch.mkdir()
        self.original = self.repository / "source"
        self.original.write_bytes(b"original source\x00\xff")
        self.plan, self.policy = self.root / "original plan.json", self.root / "caller policy.json"
        self.plan.write_bytes(canonical_json_bytes({"validationTree": TREE}))
        self.tooling = {"evidence": "/caller/tooling evidence", "publicKey": "/caller/tooling.pub",
            "javaExecutable": "/caller/java", "requiredTrustDomain": "release",
            "keyring": "/caller/tooling keyring", "keysDirectory": "/caller/tooling keys"}
        self.policy.write_bytes(canonical_json_bytes(self.tooling))
        self.output = self.root / "github-output"
        self.environment = {"GITHUB_WORKSPACE": str(self.repository), "RUNNER_TEMP": str(self.scratch),
            "PLAN_PATH": str(self.plan), "TOOLING_POLICY": str(self.policy), "GITHUB_OUTPUT": str(self.output),
            "TARGET": "ios-arm64", "BUILD_KEY": KEY, "TREE": TREE, "TRUSTED_WORKFLOW_SHA": "c" * 40,
            "POLICY_REVISION": "d" * 40, "GITHUB_TOKEN": "observer-token"}
        self.receipt = b"exact original receipt from mocked authenticated capture\n"
        self.digest = sha256_bytes(self.receipt)
        self.upload_digest = "sha256:" + "e" * 64
        self.calls = []
        self.action = (ROOT / ".github/actions/prepare-sdk-apple-signing/action.yml").read_text()

    def execute(self):
        source = textwrap.dedent(self.action.split("        python3 -B - <<'PY'\n", 1)[1].split("\n        PY", 1)[0])
        with patch.dict(os.environ, self.environment, clear=True):
            exec(compile(source, "apple-signing-prepare-action", "exec"), {})

    def child(self, argv, **kwargs):
        self.assertEqual([sys.executable, "-B", "-m"], argv[:3])
        self.assertEqual(self.repository, kwargs["cwd"])
        self.assertIs(os.environ, kwargs["env"])
        self.assertEqual("observer-token", kwargs["env"]["GITHUB_TOKEN"])
        self.assertTrue(kwargs["check"])
        self.assertNotIn("shell", kwargs)
        if argv[3] == "ci.sdk_apple_worker_capture":
            self.assertEqual([], self.calls)
            fields = dict(zip(argv[4::2], argv[5::2]))
            worker = Path(fields.pop("--destination"))
            self.assertEqual({"--plan": str(self.plan), "--candidate-root": str(self.repository),
                "--target": self.environment["TARGET"], "--expected-build-key": KEY,
                "--trusted-workflow-sha": "c" * 40}, fields)
            self.assertTrue(worker.is_relative_to(self.scratch))
            self.assertFalse(worker.exists())
            self.assertEqual(subprocess.PIPE, kwargs["stdout"])
            receipt = worker / "original/shard/phase-receipt.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_bytes(self.receipt)
            self.worker = worker
            self.calls.append("capture")
            return subprocess.CompletedProcess(argv, 0, stdout=canonical_json_bytes({
                "artifact_id": 91, "artifact_sha256": self.upload_digest,
                "receipt_path": str(receipt), "receipt_sha256": self.digest}))
        self.assertEqual(["ci.sdk_apple_release_cli", "prepare"], argv[3:5])
        self.assertEqual(["capture"], self.calls)
        fields = dict(zip(argv[5::2], argv[6::2]))
        prepared = Path(fields.pop("--destination"))
        self.assertEqual(self.worker.parent, prepared.parent)
        self.assertFalse(prepared.exists())
        self.assertEqual({"--plan": str(self.plan),
            "--validation-receipt": str(self.worker / "original/shard/phase-receipt.json"),
            "--repository-root": str(self.repository), "--target": self.environment["TARGET"],
            "--expected-receipt-sha256": self.digest, "--artifact-id": "91", "--artifact-sha256": self.upload_digest,
            "--trusted-workflow-sha": "c" * 40, "--keyring": str(self.repository / "gradle/release/product-signing-keys.json"),
            "--keys-directory": str(self.repository / "gradle/release/keys"),
            "--tooling-evidence": self.tooling["evidence"], "--tooling-public-key": self.tooling["publicKey"],
            "--java-executable": self.tooling["javaExecutable"], "--policy-revision": "d" * 40,
            "--tooling-keyring": self.tooling["keyring"], "--tooling-keys-directory": self.tooling["keysDirectory"]}, fields)
        self.assertNotIn("stdout", kwargs)
        (prepared / "capture").mkdir(parents=True)
        (prepared / "capture/raw.bin").write_bytes(b"original complete capture fixture\x00\xff")
        (prepared / "capture/empty.log").write_bytes(b"")
        (prepared / "preparation.json").write_bytes(b"mocked full preparation controller result\n")
        self.prepared = prepared
        self.calls.append("prepare")
        return subprocess.CompletedProcess(argv, 0)

    def test_both_targets_exact_capture_then_prepare_with_external_paths_and_preserved_inputs(self):
        for target in ("ios-arm64", "ios-simulator-arm64"):
            self.calls = []
            self.environment["TARGET"] = target
            with self.subTest(target=target), patch("subprocess.run", side_effect=self.child) as process:
                self.execute()
            self.assertEqual(2, process.call_count)
            self.assertEqual(["capture", "prepare"], self.calls)
            self.assertEqual("preparation_path=" + str(self.prepared) + "\n", self.output.read_text())
            self.output.unlink()
            self.assertEqual({"source"}, {path.name for path in self.repository.iterdir()})
            self.assertEqual(b"original source\x00\xff", self.original.read_bytes())
            self.assertEqual(self.receipt, (self.worker / "original/shard/phase-receipt.json").read_bytes())
            self.assertEqual(canonical_json_bytes(self.tooling), self.policy.read_bytes())

    def test_secret_invalid_scope_policy_and_paths_reject_before_allocation(self):
        baseline = dict(self.environment)
        for changes in ({"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""}, {"TARGET": "ios"},
                        {"TREE": "f" * 40}, {"BUILD_KEY": "bad"}, {"PLAN_PATH": "relative"},
                        {"RUNNER_TEMP": str(self.repository)}, {"RUNNER_TEMP": str(self.root)}):
            self.environment = {**baseline, **changes}
            with self.subTest(changes=changes), patch("tempfile.mkdtemp") as allocate, \
                    patch("subprocess.run") as process, self.assertRaises(ValueError):
                self.execute()
            allocate.assert_not_called()
            process.assert_not_called()
            self.assertFalse(self.output.exists())
        self.environment = baseline
        for changes in ({"requiredTrustDomain": "development"}, {"keyring": None},
                        {"keysDirectory": None}, {"evidence": "relative"}, {"extra": "unknown"}):
            self.policy.write_bytes(canonical_json_bytes({**self.tooling, **changes}))
            with self.subTest(policy=changes), patch("tempfile.mkdtemp") as allocate, \
                    patch("subprocess.run") as process, self.assertRaises(ValueError):
                self.execute()
            allocate.assert_not_called()
            process.assert_not_called()

    def test_capture_or_prepare_failure_never_publishes_preparation_output(self):
        for failure in ("capture", "prepare"):
            self.calls = []
            def child(argv, **kwargs):
                if (argv[3] == "ci.sdk_apple_worker_capture") == (failure == "capture"):
                    raise subprocess.CalledProcessError(1, argv)
                return self.child(argv, **kwargs)
            with self.subTest(failure=failure), patch("subprocess.run", side_effect=child), \
                    self.assertRaises(subprocess.CalledProcessError):
                self.execute()
            self.assertFalse(self.output.exists())

    def test_capture_mismatch_or_late_policy_secret_mutation_stops_before_prepare(self):
        for mutation in ("receipt-path", "receipt-hash", "policy", "plan", "secret"):
            self.calls = []
            self.plan.write_bytes(canonical_json_bytes({"validationTree": TREE}))
            self.policy.write_bytes(canonical_json_bytes(self.tooling))
            def child(argv, **kwargs):
                result = self.child(argv, **kwargs)
                if mutation == "policy": self.policy.write_bytes(b"changed")
                elif mutation == "plan": self.plan.write_bytes(b"changed")
                elif mutation == "secret": os.environ["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"] = ""
                else:
                    from ci.products.inventory import load_canonical_json_bytes
                    value = load_canonical_json_bytes(result.stdout)
                    value["receipt_path" if mutation == "receipt-path" else "receipt_sha256"] = (
                        "/other/receipt" if mutation == "receipt-path" else "sha256:" + "0" * 64)
                    result.stdout = canonical_json_bytes(value)
                return result
            with self.subTest(mutation=mutation), patch("subprocess.run", side_effect=child) as process, \
                    self.assertRaises(ValueError):
                self.execute()
            self.assertEqual(1, process.call_count)
            self.assertEqual(["capture"], self.calls)
            self.assertFalse(self.output.exists())

    def test_complete_result_required_and_mutation_after_prepare_never_exposes_upload_path(self):
        for mutation in ("extra-root", "missing-record", "policy", "secret"):
            self.calls = []
            self.policy.write_bytes(canonical_json_bytes(self.tooling))
            def child(argv, **kwargs):
                result = self.child(argv, **kwargs)
                if argv[3] == "ci.sdk_apple_release_cli":
                    if mutation == "extra-root": (self.prepared / "extra").write_bytes(b"unexpected")
                    elif mutation == "missing-record": (self.prepared / "preparation.json").unlink()
                    elif mutation == "policy": self.policy.write_bytes(b"changed")
                    else: os.environ["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"] = ""
                return result
            with self.subTest(mutation=mutation), patch("subprocess.run", side_effect=child), self.assertRaises(ValueError):
                self.execute()
            self.assertFalse(self.output.exists())

    def test_exact_preparation_upload_without_secret_or_signer_interface(self):
        inputs = self.action.split("inputs:\n", 1)[1].split("outputs:\n", 1)[0]
        self.assertEqual({"plan-path", "target", "build-key", "tree", "trusted-workflow-sha", "policy-revision", "tooling-policy"},
                         set(re.findall(r"^  ([a-z0-9-]+):$", inputs, re.MULTILINE)))
        self.assertIn("name: codex-agent-sdk-apple-signing-preparation-${{ inputs.target }}-${{ inputs.tree }}-attempt-${{ github.run_attempt }}", self.action)
        for value in ("path: ${{ steps.prepare.outputs.preparation_path }}", "if-no-files-found: error",
                      "include-hidden-files: true", "overwrite: false", "compression-level: 0"):
            self.assertIn(value, self.action)
        for forbidden in ("secrets.", "PRIVATE_KEY", "'sign'", "ssh-keygen", "setup-kmp", "setup-java", "--token"):
            self.assertNotIn(forbidden, self.action)


if __name__ == "__main__":
    unittest.main()
