"""Check the Android Maven composite's pre-setup boundary and shell routing."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from ci.products.inventory import (canonical_json_bytes, regular_file_inventory,
    sha256_bytes, sha256_file)


ROOT = Path(__file__).resolve().parents[2]
ACTION = ROOT / ".github/actions/sdk-android-maven-worker/action.yml"
KEY = "sha256:" + "a" * 64


class AndroidMavenWorkerActionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "build").mkdir(exist_ok=True)
        cls.action = ACTION.read_text()
        cls.shell = shutil.which("bash")

    @classmethod
    def script(cls, marker):
        match = re.search(rf"(?ms)^    - {marker}\n(.*?)(?=^    - |\Z)", cls.action)
        if match is None:
            raise AssertionError(f"Missing action step: {marker}")
        return textwrap.dedent(match[1].split("      run: |\n", 1)[1])

    def test_current_state_is_captured_before_any_platform_setup(self):
        action = self.action
        self.assertLess(action.index("- id: policy"), action.index("- id: before"))
        for earlier, later in (("- id: before", "- id: core14"),
                               ("- id: core14", "- id: core14_admitted"),
                               ("- id: core14_admitted", "uses: ./.github/actions/setup-kmp")):
            self.assertLess(action.index(earlier), action.index(later))
        for marker in ("id: before", "id: core14", "id: selected"):
            self.assertIn('--state-wave "$STATE_WAVE" ${wave[@]+"${wave[@]}"}', self.script(marker))
            self.assertNotRegex(self.script(marker), r"--sdk-state-wave (13|14|15)(?:\s|$)")
        self.assertIn("ci.sdk_android_core14_caller preflight", self.script("id: core14_admitted"))
        for marker in ("id: core14_admitted", "id: execute"):
            self.assertIn('--binary-original-workflow-path "$BINARY_ORIGINAL_WORKFLOW_PATH"',
                          self.script(marker))
            self.assertIn('--binary-original-job-name "$BINARY_ORIGINAL_JOB_NAME"',
                          self.script(marker))
        self.assertLess(action.index("- id: selected"), action.index("- id: identity"))
        self.assertLess(action.index("- id: identity"), action.index("uses: ./.github/actions/setup-kmp"))
        self.assertLess(action.index("- id: identity"), action.index("uses: android-actions/setup-android@"))
        for field in ("plan-id", "artifact-id", "artifact-sha256", "trusted-workflow-sha",
                      "core13-artifact-id", "core13-state-wave", "core13-sdk-state-wave",
                      "core14-artifact-id", "core14-state-wave", "core14-sdk-state-wave",
                      "core14-metadata-receipt", "core14-reused-context-signature"):
            self.assertIn(f"inputs.{field}", action)
        identity = self.script("id: identity")
        for check in ("host_classifier() != 'linux-x64'", "len(rows) != 1",
                      "('sdk', 'sdk-android', phase, 'android')", "rows[0].get('buildKey') != key",
                      "('ubuntu-24.04', 'Linux', 'X64')", "os.environ['POLICY_SHA256']",
                      "plan['validationTree'] != tree", "git_regular_blob_bytes", "sha256_file(archive",
                      "_context(package['BINARY_ORIGINAL_CONTEXT'], 'binary')"):
            self.assertIn(check, identity)
        self.assertIn("require_no_signing_secret(os.environ)", self.script("id: policy"))
        self.assertIn("sha256_bytes(canonical_json_bytes(pins))", self.script(
            "id: execute"))
        for marker in ("id: policy", "id: identity", "id: execute"):
            script = self.script(marker)
            for name in ("BINARY_ORIGINAL_WORKFLOW_PATH", "BINARY_ORIGINAL_JOB_NAME"):
                self.assertIn(f"'{name}': os.environ['{name}']", script)

    def test_binary_original_context_and_upload_outputs_require_success(self):
        self.assertLess(self.action.index("- id: identity"), self.action.index("- id: context"))
        self.assertLess(self.action.index("- id: context"), self.action.index("uses: ./.github/actions/setup-kmp"))
        self.assertIn("if: inputs.phase == 'binary'", self.action)
        outputs = self.action.split("\noutputs:\n", 1)[1].split("\nruns:\n", 1)[0]
        self.assertIn("steps.context.outputs.value", outputs)
        context_expression = outputs.split("  binary-original-context:", 1)[1].split(
            "\n  binary-artifact-id:", 1)[0]
        for guard in ("inputs.phase == 'binary'", "steps.execute.outcome == 'success'",
                      "steps.upload.outcome == 'success'",
                      "steps.upload.outputs.artifact-id != ''",
                      "steps.upload.outputs.artifact-digest != ''"):
            self.assertIn(guard, context_expression)
        for name in ("binary-artifact-id", "binary-artifact-sha256"):
            expression = outputs.split("  " + name + ":", 1)[1].split("\n  binary-", 1)[0]
            for guard in ("inputs.phase == 'binary'", "steps.execute.outcome == 'success'",
                          "steps.upload.outcome == 'success'",
                          "steps.upload.outputs.artifact-id != ''",
                          "steps.upload.outputs.artifact-digest != ''"):
                self.assertIn(guard, expression)
        for name in ("package-artifact-id", "package-artifact-sha256"):
            expression = outputs.split("  " + name + ":", 1)[1].split("\n  package-", 1)[0]
            for guard in ("inputs.phase == 'package'", "steps.execute.outcome == 'success'",
                          "steps.upload.outcome == 'success'",
                          "steps.upload.outputs.artifact-id != ''",
                          "steps.upload.outputs.artifact-digest != ''"):
                self.assertIn(guard, expression)
        self.assertIn("- id: execute", self.action)
        self.assertIn("- id: upload", self.action)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            output = root / "github-output"
            with patch.dict(os.environ, {"GITHUB_WORKSPACE": str(root), "GITHUB_OUTPUT": str(output)}, clear=True):
                source = self.script("id: context").split("python3 -B - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
                exec(compile(source, "android-context", "exec"), {})
            self.assertEqual(canonical_json_bytes({
                "repositoryRoot": str(root),
                "workerRoot": str(root / "build/sdk-android-maven-worker"),
            }), output.read_text().removeprefix("value=").encode())
            alias = root / "checkout-alias"
            alias.symlink_to(root, target_is_directory=True)
            with patch.dict(os.environ, {"GITHUB_WORKSPACE": str(alias), "GITHUB_OUTPUT": str(output)}, clear=True):
                with self.assertRaisesRegex(ValueError, "canonical original path"):
                    exec(compile(source, "android-context", "exec"), {})

    def run_execution(self, phase, *, bad_digest=False, reused=False):
        with tempfile.TemporaryDirectory(prefix="android-maven-action-", dir=ROOT / "build") as temporary:
            root = Path(temporary)
            binary = root / "bin"
            binary.mkdir()
            recorder = binary / "python3"
            recorder.write_text("#!/bin/sh\n"
                "if [ \"$1\" = -B ] && [ \"$2\" = - ]; then "
                "exec \"$REAL_PYTHON\" \"$@\"; fi\n"
                "printf '%s\\0' \"$@\" > \"$RECORDED_ARGS\"\n")
            recorder.chmod(0o700)
            record = root / "arguments"
            archive = root / "original.tar.gz"
            archive.write_bytes(b"pinned archive fixture")
            contract, context = root / "contract.json", root / "context.json"
            contract.write_bytes(canonical_json_bytes({}))
            context.write_bytes(canonical_json_bytes({}))
            core_receipt, core_policy, core_context = (root / name for name in
                ("core-receipt.json", "core-policy.json", "core-context.json"))
            for path in (core_receipt, core_policy, core_context):
                path.write_bytes(canonical_json_bytes({}))
            actual_digest = sha256_bytes(archive.read_bytes())
            workflow_path = ".github/workflows/sdk-android-binary-validation.yml" if phase == "package" else ""
            worker_job = ("product-validation / sdk-android-binary-result / sdk-android-binary-android"
                          if phase == "package" else "")
            pins = {"ANDROID_ARCHIVE": actual_digest,
                "BINARY_ORIGINAL_WORKFLOW_PATH": workflow_path,
                "BINARY_ORIGINAL_JOB_NAME": worker_job,
                "CORE14_METADATA_RECEIPT": sha256_bytes(core_receipt.read_bytes()),
                "CORE14_REPLAY_POLICY": sha256_bytes(core_policy.read_bytes()),
                "CORE14_ORIGINAL_CONTEXT": sha256_bytes(core_context.read_bytes())}
            if phase == "package":
                pins.update(BINARY_CONTRACT_EVIDENCE=sha256_bytes(contract.read_bytes()),
                            BINARY_ORIGINAL_CONTEXT=sha256_bytes(context.read_bytes()))
            reused_inputs = {}
            if reused:
                carrier = root / "carrier"
                carrier.mkdir()
                reused_inputs = {"CORE14_REUSED_CATALOG_ROOT": str(carrier),
                    "CORE14_REUSED_CATALOG_SOURCE": "same-pr"}
                for name in ("CORE14_REUSED_CATALOG", "CORE14_REUSED_RECEIPT_SHA256",
                             "CORE14_REUSED_PUBLIC_KEY", "CORE14_REUSED_CONTEXT_MANIFEST",
                             "CORE14_REUSED_CONTEXT_SIGNATURE", "CORE14_REUSED_CONTEXT_KEYRING"):
                    path = root / (name.lower() + ".json")
                    path.write_bytes(canonical_json_bytes({"fixture": name}))
                    reused_inputs[name] = str(path)
                    pins[name] = sha256_file(path)
                keys = root / "context-keys"
                keys.mkdir()
                (keys / "release.pub").write_bytes(b"fixture release key")
                reused_inputs["CORE14_REUSED_CONTEXT_KEYS_DIRECTORY"] = str(keys)
                pins["CORE14_REUSED_CONTEXT_KEYS_DIRECTORY"] = sha256_bytes(
                    canonical_json_bytes(regular_file_inventory(keys)))
            environment = {"PATH": str(binary) + os.pathsep + os.environ["PATH"],
                "RECORDED_ARGS": str(record), "REAL_PYTHON": sys.executable,
                "PYTHONPATH": str(ROOT),
                "GITHUB_WORKSPACE": str(root), "PLAN": str(root / "plan.json"),
                "DISCOVERY": str(root / "discovery"), "STATE": str(root / "state"),
                "BEFORE_STATE": str(root / "before-state"),
                "CORE14_STATE": str(root / "core14-state"),
                "PHASE": phase, "BUILD_KEY": KEY, "ANDROID_ARCHIVE": str(archive),
                "CORE14_BUILD_KEY": KEY,
                "CORE14_METADATA_RECEIPT": str(core_receipt),
                "CORE14_METADATA_RECEIPT_SHA256": sha256_bytes(core_receipt.read_bytes()),
                "CORE14_METADATA_ARTIFACT_ID": "" if reused else "73",
                "CORE14_METADATA_ARTIFACT_SHA256": "" if reused else KEY,
                "CORE14_REPLAY_POLICY": str(core_policy),
                "CORE14_ORIGINAL_CONTEXT": str(core_context),
                **{name: "" for name in (
                    "CORE14_REUSED_CATALOG", "CORE14_REUSED_CATALOG_ROOT",
                    "CORE14_REUSED_CATALOG_SOURCE", "CORE14_REUSED_RECEIPT_SHA256",
                    "CORE14_REUSED_PUBLIC_KEY", "CORE14_REUSED_KEYRING",
                    "CORE14_REUSED_KEYS_DIRECTORY", "CORE14_REUSED_CONTEXT_MANIFEST",
                    "CORE14_REUSED_CONTEXT_SIGNATURE", "CORE14_REUSED_CONTEXT_KEYRING",
                    "CORE14_REUSED_CONTEXT_KEYS_DIRECTORY")},
                **reused_inputs,
                "ARCHIVE_SHA256": actual_digest if not bad_digest else KEY,
                "POLICY_SHA256": sha256_bytes(canonical_json_bytes(pins)),
                "SDK_INPUTS_ID": "71", "SDK_INPUTS_SHA256": KEY,
                "BINARY_ARTIFACT_ID": "72", "BINARY_ARTIFACT_SHA256": KEY,
                "BINARY_CONTRACT_EVIDENCE": str(contract) if phase == "package" else "",
                "BINARY_ORIGINAL_CONTEXT": str(context) if phase == "package" else "",
                "BINARY_ORIGINAL_WORKFLOW_PATH": workflow_path,
                "BINARY_ORIGINAL_JOB_NAME": worker_job,
                "SDK_VALIDATION_TOOLING": "", "SDK_APPLE_VALIDATION_POLICY": "",
                "SDK_FACADE_METADATA_POLICY": "", "SDK_ANDROID_METADATA_POLICY": "",
                "TRUSTED_WORKFLOW_SHA": "c" * 40}
            result = subprocess.run([self.shell, "--noprofile", "--norc", "-c",
                self.script("id: execute")],
                cwd=root, env=environment, capture_output=True, text=True, check=False)
            arguments = record.read_bytes().decode().split("\0")[:-1] if record.exists() else None
            return result, arguments

    def test_pre_capture_policy_rejects_missing_package_inputs_and_signing_secret(self):
        with tempfile.TemporaryDirectory(prefix="android-maven-policy-", dir=ROOT / "build") as temporary:
            root = Path(temporary)
            archive, output = root / "archive.tar.gz", root / "output"
            archive.write_bytes(b"original archive")
            environment = {**os.environ, "PHASE": "binary", "ANDROID_ARCHIVE": str(archive),
                "CORE13_ARTIFACT_ID": "71", "CORE13_ARTIFACT_SHA256": KEY,
                "CORE13_STATE_WAVE": "0", "CORE13_SDK_STATE_WAVE": "13",
                "CORE14_ARTIFACT_ID": "", "CORE14_ARTIFACT_SHA256": "",
                "CORE14_STATE_WAVE": "", "CORE14_SDK_STATE_WAVE": "",
                "SELECTED_STATE_WAVE": "0", "SELECTED_SDK_STATE_WAVE": "14",
                "CORE14_BUILD_KEY": KEY,
                "CORE14_METADATA_RECEIPT": str(root / "core-receipt.json"),
                "CORE14_METADATA_RECEIPT_SHA256": sha256_bytes(canonical_json_bytes({})),
                "CORE14_METADATA_ARTIFACT_ID": "73",
                "CORE14_METADATA_ARTIFACT_SHA256": KEY,
                "CORE14_REPLAY_POLICY": str(root / "core-policy.json"),
                "CORE14_ORIGINAL_CONTEXT": str(root / "core-context.json"),
                **{name: "" for name in (
                    "CORE14_REUSED_CATALOG", "CORE14_REUSED_CATALOG_ROOT",
                    "CORE14_REUSED_CATALOG_SOURCE", "CORE14_REUSED_RECEIPT_SHA256",
                    "CORE14_REUSED_PUBLIC_KEY", "CORE14_REUSED_KEYRING",
                    "CORE14_REUSED_KEYS_DIRECTORY", "CORE14_REUSED_CONTEXT_MANIFEST",
                    "CORE14_REUSED_CONTEXT_SIGNATURE", "CORE14_REUSED_CONTEXT_KEYRING",
                    "CORE14_REUSED_CONTEXT_KEYS_DIRECTORY")},
                "SDK_INPUTS_ID": "", "SDK_INPUTS_SHA256": "", "BINARY_ARTIFACT_ID": "",
                "BINARY_ARTIFACT_SHA256": "", "BINARY_CONTRACT_EVIDENCE": "",
                "BINARY_ORIGINAL_CONTEXT": "", "BINARY_ORIGINAL_WORKFLOW_PATH": "",
                "BINARY_ORIGINAL_JOB_NAME": "", "SDK_VALIDATION_TOOLING": "",
                "SDK_APPLE_VALIDATION_POLICY": "", "SDK_FACADE_METADATA_POLICY": "",
                "SDK_ANDROID_METADATA_POLICY": "", "GITHUB_OUTPUT": str(output)}
            for name in ("core-receipt.json", "core-policy.json", "core-context.json"):
                (root / name).write_bytes(canonical_json_bytes({}))
            script = self.script("id: policy")
            command = [self.shell, "--noprofile", "--norc", "-c", script]
            good = subprocess.run(command, cwd=ROOT,
                env=environment, capture_output=True, text=True, check=False)
            self.assertEqual(0, good.returncode, good.stderr)
            self.assertRegex(output.read_text(), r"^policy_sha256=sha256:[0-9a-f]{64}\n$")
            absent_core = subprocess.run(command, cwd=ROOT,
                env={**environment, "CORE14_METADATA_RECEIPT": ""},
                capture_output=True, text=True, check=False)
            self.assertNotEqual(0, absent_core.returncode)
            self.assertIn("current Core caller authority", absent_core.stderr)
            missing = subprocess.run(command, cwd=ROOT,
                env={**environment, "PHASE": "package"}, capture_output=True, text=True, check=False)
            self.assertNotEqual(0, missing.returncode)
            self.assertIn("package requires all original inputs", missing.stderr)
            secret = subprocess.run(command, cwd=ROOT,
                env={**environment, "CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""},
                capture_output=True, text=True, check=False)
            self.assertNotEqual(0, secret.returncode)
            unsigned_reuse = subprocess.run(command, cwd=ROOT,
                env={**environment, "CORE14_REUSED_CATALOG": str(root / "unsigned-catalog.json"),
                    "CORE14_METADATA_ARTIFACT_ID": "", "CORE14_METADATA_ARTIFACT_SHA256": ""},
                capture_output=True, text=True, check=False)
            self.assertNotEqual(0, unsigned_reuse.returncode)
            self.assertIn("signed context, catalog and twelve independent receipt pins",
                unsigned_reuse.stderr)
            carrier, keys = root / "carrier", root / "context-keys"
            carrier.mkdir()
            keys.mkdir()
            (keys / "release.pub").write_bytes(b"release key fixture")
            reused = {**environment, "CORE13_SDK_STATE_WAVE": "11",
                "SELECTED_SDK_STATE_WAVE": "12", "CORE14_METADATA_ARTIFACT_ID": "",
                "CORE14_METADATA_ARTIFACT_SHA256": "",
                "CORE14_REUSED_CATALOG_ROOT": str(carrier),
                "CORE14_REUSED_CATALOG_SOURCE": "same-pr",
                "CORE14_REUSED_CONTEXT_KEYS_DIRECTORY": str(keys)}
            for name in ("CORE14_REUSED_CATALOG", "CORE14_REUSED_RECEIPT_SHA256",
                         "CORE14_REUSED_PUBLIC_KEY", "CORE14_REUSED_CONTEXT_MANIFEST",
                         "CORE14_REUSED_CONTEXT_SIGNATURE", "CORE14_REUSED_CONTEXT_KEYRING"):
                path = root / (name.lower() + ".json")
                path.write_bytes(canonical_json_bytes({"fixture": name}))
                reused[name] = str(path)
            accepted = subprocess.run(command, cwd=ROOT, env=reused,
                capture_output=True, text=True, check=False)
            self.assertEqual(0, accepted.returncode, accepted.stderr)
            missing_signature = subprocess.run(command, cwd=ROOT,
                env={**reused, "CORE14_REUSED_CONTEXT_SIGNATURE": ""},
                capture_output=True, text=True, check=False)
            self.assertNotEqual(0, missing_signature.returncode)
            self.assertIn("signed context, catalog and twelve independent receipt pins",
                missing_signature.stderr)

    def test_transport_capture_uses_exact_forwarded_current_wave(self):
        with tempfile.TemporaryDirectory(prefix="android-maven-capture-", dir=ROOT / "build") as temporary:
            root = Path(temporary)
            binary = root / "bin"
            binary.mkdir()
            recorder = binary / "python3"
            recorder.write_text("#!/bin/sh\nprintf '%s\\0' \"$@\" > \"$RECORDED_ARGS\"\n")
            recorder.chmod(0o700)
            record = root / "args"
            common = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"],
                "RECORDED_ARGS": str(record), "ARTIFACT_ID": "71",
                "ARTIFACT_SHA256": KEY, "TRUSTED_WORKFLOW_SHA": "c" * 40,
                "GITHUB_WORKSPACE": str(root), "GITHUB_OUTPUT": str(root / "output")}
            for marker in ("id: before", "id: core14", "id: selected"):
                for state, sdk in (("0", "12"), ("5", "")):
                    with self.subTest(marker=marker, wave=(state, sdk)):
                        environment = {**common, "STATE_WAVE": state, "SDK_STATE_WAVE": sdk,
                            "CORE14_SDK_STATE_WAVE": sdk, "PHASE": "binary"}
                        result = subprocess.run([self.shell, "--noprofile", "--norc", "-c",
                            self.script(marker)], cwd=root, env=environment,
                            capture_output=True, text=True, check=False)
                        self.assertEqual(0, result.returncode, result.stderr)
                        args = record.read_bytes().decode().split("\0")[:-1]
                        self.assertEqual(state, args[args.index("--state-wave") + 1])
                        if sdk:
                            self.assertEqual(sdk, args[args.index("--sdk-state-wave") + 1])
                        else:
                            self.assertNotIn("--sdk-state-wave", args)
            result = subprocess.run([self.shell, "--noprofile", "--norc", "-c",
                self.script("id: core14")], cwd=root,
                env={**common, "STATE_WAVE": "5", "SDK_STATE_WAVE": "15",
                     "CORE14_SDK_STATE_WAVE": "", "PHASE": "package"},
                capture_output=True, text=True, check=False)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertNotIn("--sdk-state-wave", record.read_bytes().decode().split("\0"))

    def test_binary_and_package_pass_only_their_fixed_original_inputs(self):
        for phase in ("binary", "package"):
            with self.subTest(phase=phase):
                result, args = self.run_execution(phase)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(["-B", "-m", "ci.sdk_android_core14_caller", "execute"], args[:4])
                self.assertIn("--expected-build-key", args)
                self.assertIn("--android-runtime-archive", args)
                self.assertEqual("c" * 40, args[args.index("--trusted-workflow-sha") + 1])
                if phase == "binary":
                    self.assertIn("--before-state-root", args)
                    self.assertIn("--expected-metadata-receipt-sha256", args)
                    self.assertIn("--expected-metadata-artifact-id", args)
                    self.assertIn("--expected-metadata-artifact-sha256", args)
                    for flag in ("--sdk-inputs-artifact-id", "--binary-artifact-id",
                                 "--binary-contract-evidence", "--binary-original-context",
                                 "--binary-original-workflow-path", "--binary-original-job-name"):
                        self.assertNotIn(flag, args)
                else:
                    self.assertEqual("package", args[args.index("--phase") + 1])
                    self.assertIn("--selected-state-root", args)
                    for flag in ("--sdk-inputs-artifact-id", "--binary-artifact-id",
                                 "--binary-contract-evidence", "--binary-original-context",
                                 "--binary-original-workflow-path", "--binary-original-job-name",
                                 "--trusted-workflow-sha", "--keyring", "--keys-directory"):
                        self.assertIn(flag, args)

    def test_archive_mutation_before_execution_fails_without_controller(self):
        result, args = self.run_execution("package", bad_digest=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIsNone(args)

    def test_reused_core_passes_signed_controls_without_fresh_worker_upload(self):
        for phase in ("binary", "package"):
            with self.subTest(phase=phase):
                result, args = self.run_execution(phase, reused=True)
                self.assertEqual(0, result.returncode, result.stderr)
                for flag in ("--reused-catalog", "--reused-catalog-root",
                             "--reused-catalog-source", "--reused-receipt-sha256",
                             "--reused-public-key", "--reused-context-manifest",
                             "--reused-context-signature", "--reused-context-keyring",
                             "--reused-context-keys-directory"):
                    self.assertIn(flag, args)
                self.assertNotIn("--expected-metadata-artifact-id", args)
                self.assertNotIn("--expected-metadata-artifact-sha256", args)


if __name__ == "__main__":
    unittest.main()
