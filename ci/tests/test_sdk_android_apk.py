"""APK transport checks do not stand in for genuine product/device admission."""

from argparse import Namespace
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from ci import sdk_android_evidence_capture as apk
from ci import sdk_android_evidence_capture as capture
from ci.products import sdk_android_observation as observation
from ci.tests import test_ci as fixtures


class AndroidApkTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ReceiptTest(methodName="runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.plan = self.f.plan_path.resolve()
        self.value = json.loads(self.plan.read_bytes())
        self.value["androidEvidenceRequired"] = True
        self.plan.write_text(json.dumps(self.value))
        self.lane = self.f.root.resolve() / "apk"
        self.lane.mkdir()
        self.originals = set(apk.SUBMISSION_FILES.values()) - {"lane-receipt.json"}
        for relative in apk.CONTROL_FILES | self.originals:
            target = self.lane / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((relative + " fixture\n").encode())
        apk.write_canonical_json(self.lane / "apk-execution.json", {
            "kind": apk.SCOPE, "tasks": list(apk.TASKS), "exitCode": 0,
            "candidateCommit": self.value["validationCommit"], "candidateTree": self.value["validationTree"],
            **{phase + "ReceiptSha256": apk.sha256_bytes((self.lane / (phase + "-receipt.json")).read_bytes())
               for phase in ("binary", "package")},
        })
        self.receipt()

    def receipt(self, actions="build"):
        apk.create_receipt(Namespace(plan=self.plan, lane="android", output=self.lane,
            workflow_path=".github/workflows/ci.yml",
            artifact_name="codex-agent-ci-android-" + self.value["validationTree"],
            run_id=101, run_attempt=2, runner=["os=Linux", "arch=X64"],
            toolchain=["java=fixture", "evidenceScope=" + apk.SCOPE, "validationActions=" + actions],
            artifact=[p + "=apk-consumer-input" for p in sorted(apk.CONTROL_FILES | self.originals)], evidence=[]))

    def firebase(self):
        source = self.f.root.resolve() / "firebase-apk"
        source.mkdir()
        for relative in capture._FIREBASE_FILES:
            name = Path(relative).name
            original = next((p for p in self.originals if Path(p).name == name), None)
            (source / name).write_bytes((self.lane / original).read_bytes() if original else b"fixture evidence\n")
        return source

    def test_build_only_initial_and_separate_final_preserve_original(self):
        before = apk.regular_file_inventory(self.lane, allow_empty=True)
        checked = apk.check(self.plan, self.lane)
        self.assertEqual("build", checked["toolchain"]["validationActions"])
        with self.assertRaisesRegex(ValueError, "action coverage mismatch"):
            apk.validate_receipt(self.lane / "lane-receipt.json", self.plan, self.lane, "android")
        observed = self.f.root.resolve() / "apk-observation"
        arguments = dict(repository=self.f.root.resolve(), lane=self.lane, plan=self.plan, observation=observed,
            candidate_commit=self.value["validationCommit"], candidate_tree=self.value["validationTree"],
            trusted_source_commit=self.value["validationCommit"], trusted_source_tree=self.value["validationTree"],
            apk_consumer=True)
        observation.bind_submission(**arguments, create=True)
        observation.bind_submission(**arguments, create=False)
        self.assertEqual((self.lane / "lane-receipt.json").read_bytes(), (observed / "lane-receipt.json").read_bytes())
        final = self.f.root.resolve() / "final-apk"
        apk.attach(self.plan, self.lane, self.firebase(), final)
        result = apk.check(self.plan, final, final=True)
        self.assertEqual(before, apk.regular_file_inventory(self.lane, allow_empty=True))
        self.assertEqual(apk.CONTROL_FILES, {r["relativePath"] for r in result["artifacts"]})
        self.assertEqual(capture._FIREBASE_FILES, {r["relativePath"] for r in result["evidence"]})
        self.assertTrue(all(not (final / name).exists() for name in self.originals))
        self.assertEqual(checked["runId"], result["runId"])
        self.assertEqual((final / "lane-receipt.json").read_bytes(),
                         capture._check_lane(self.plan, final, self.value))

    def test_reject_invented_test_claim_and_unsuccessful_execution(self):
        self.receipt(actions="build,metadata,test")
        with self.assertRaisesRegex(ValueError, "build only"):
            apk.check(self.plan, self.lane)
        for exit_code in (False, 1):
            execution = json.loads((self.lane / "apk-execution.json").read_bytes())
            execution["exitCode"] = exit_code
            apk.write_canonical_json(self.lane / "apk-execution.json", execution)
            self.receipt()
            with self.assertRaisesRegex(ValueError, "execution differs"):
                apk.check(self.plan, self.lane)

    def test_final_rejects_substitution_extra_files_and_overwrite(self):
        source = self.firebase()
        final = self.f.root.resolve() / "final-apk"
        target = source / "codex-agent-runtime-android-release.aar"
        raw = target.read_bytes()
        target.write_bytes(raw + b"tamper")
        with self.assertRaisesRegex(ValueError, "substituted"):
            apk.attach(self.plan, self.lane, source, final)
        target.write_bytes(raw)
        (source / "extra").write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "seven-file"):
            apk.attach(self.plan, self.lane, source, final)
        self.assertFalse(final.exists())
        with self.assertRaises(ValueError):
            apk.attach(self.plan, self.lane, source, self.lane)

    def test_failed_consumer_preserves_diagnostics_without_success_receipt(self):
        root = self.f.root.resolve()
        policy = {name: str(self.lane / (name + ".json")) for name in apk.POLICY_PROPERTIES}
        for name, path in policy.items():
            Path(path).write_bytes(b'{"productVersion":"0.8.0"}\n')
        destination = root / "failed-consumer"
        real_run = subprocess.run

        def run(argv, **kwargs):
            if argv[0] == "fixture-gradle":
                self.assertEqual("--init-script", argv[1])
                self.assertEqual(apk.CONTRACT_ANDROID_INIT, Path(argv[2]).read_text())
                kwargs["stdout"].write(b"causal consumer failure\n")
                return subprocess.CompletedProcess(argv, 7)
            return real_run(argv, **kwargs)

        with patch.dict(os.environ, {"GITHUB_RUN_ID": "101", "GITHUB_RUN_ATTEMPT": "2"}), \
                patch.object(apk, "command", return_value=["fixture-gradle"]), \
                patch.object(apk.subprocess, "run", side_effect=run), \
                self.assertRaises(subprocess.CalledProcessError):
            apk.produce(root, self.plan, policy, destination)
        diagnostics = destination.with_name(destination.name + "-diagnostics")
        self.assertEqual(b"causal consumer failure\n", (diagnostics / "apk-build.log").read_bytes())
        self.assertEqual(7, json.loads((diagnostics / "apk-execution.json").read_bytes())["exitCode"])
        self.assertEqual(apk.sha256_bytes(apk.CONTRACT_ANDROID_INIT.encode()),
            json.loads((diagnostics / "apk-execution.json").read_bytes())["repositoryPolicySha256"])
        self.assertFalse(destination.exists())
        self.assertFalse((diagnostics / "lane-receipt.json").exists())

    def test_command_only_uses_two_allowed_consumer_tasks_and_explicit_artifacts(self):
        root = self.f.root.resolve()
        policy = {name: str(self.lane / (name + ".json")) for name in apk.POLICY_PROPERTIES}
        for path in policy.values():
            Path(path).write_bytes(b"fixture\n")
        request = {name: Path(policy["compatibilityRequest"]) for name in (
            "contract_payload", "contract_metadata_receipt", "contract_attestation",
            "contract_attestation_signature", "contract_public_key")}
        version = root / "gradle/release/versions/contract.txt"
        version.parent.mkdir(parents=True, exist_ok=True)
        version.write_text("0.8.0\n")
        with patch.object(apk, "load_sdk_compatibility_request", return_value=request):
            command = apk.command(root, policy)
            self.assertEqual(list(apk.TASKS), [part for part in command if part.startswith(":")])
            self.assertEqual(12, len([part for part in command if part.startswith("-PcodexAgent.")]))
            self.assertIn("-PcodexAgent.contractVersion=0.8.0", command)
            with self.assertRaisesRegex(ValueError, "exact six"):
                apk.command(root, {**policy, "extra": str(root)})


if __name__ == "__main__":
    unittest.main()
