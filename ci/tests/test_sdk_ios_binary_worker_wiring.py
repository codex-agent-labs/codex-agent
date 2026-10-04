"""Static composite wiring checks; these do not establish hosted Apple execution."""

import json
import os
from pathlib import Path
import re
import tempfile
import textwrap
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
KEY = "sha256:" + "a" * 64
TREE = "b" * 40


class SdkIosBinaryWorkerWiringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.action = (ROOT / ".github/actions/sdk-ios-binary-worker/action.yml").read_text()
        cls.workflow = (ROOT / ".github/workflows/product-validation.yml").read_text()
        matches = re.findall(
            r"^        python3 - <<'PY'\n(.*?)^        PY$",
            cls.action, re.MULTILINE | re.DOTALL,
        )
        if len(matches) != 1:
            raise AssertionError("Expected the sole iOS SDK election guard")
        cls.identity = textwrap.dedent(matches[0])
        cls.collect_parent = cls.parent_script("sdk-collect-3")
        cls.sdk_parent = cls.parent_script("sdk-plan")

    @classmethod
    def job(cls, name):
        return re.search(
            rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)",
            cls.workflow,
        )[0]

    @classmethod
    def parent_script(cls, job):
        matches = re.findall(
            r"^          python3 - <<'PY'\n(.*?)^          PY$",
            cls.job(job), re.MULTILINE | re.DOTALL,
        )
        if len(matches) != 1:
            raise AssertionError(f"Expected the sole {job} parent selector")
        return textwrap.dedent(matches[0])

    def test_capture_and_exact_identity_precede_read_only_apple_setup(self):
        capture = self.action.index("uses: ./.github/actions/capture-runtime-state")
        identity = self.action.index("iOS SDK worker differs from the original replay election")
        setup = self.action.index("uses: ./.github/actions/setup-kmp")
        self.assertLess(capture, identity)
        self.assertLess(identity, setup)
        for value in (
            "product: sdk-ios-binary", "cache-read-only: 'true'",
            "product-worker: 'true'", "xcode-fingerprint: auto",
        ):
            self.assertIn(value, self.action)
        self.assertNotIn("setup-xcode", self.action)
        self.assertNotIn("xcodebuild", self.action[:setup])

    def run_identity(self, rows, *, required="true", key=KEY, tree=TREE, sentinel=""):
        with tempfile.TemporaryDirectory(prefix="sdk-ios-worker-identity-") as temporary:
            output = Path(temporary) / "github-output"
            if sentinel:
                output.write_text(sentinel)
            environment = {
                "MATRIX": json.dumps({"include": rows}), "REQUIRED": required,
                "BUILD_KEY": key, "TREE": tree, "GITHUB_OUTPUT": str(output),
            }
            with patch.dict(os.environ, environment, clear=True):
                if sentinel:
                    with self.assertRaises(ValueError):
                        exec(compile(self.identity, "sdk-ios-worker-identity", "exec"), {})
                    self.assertEqual(sentinel, output.read_text())
                    return
                exec(compile(self.identity, "sdk-ios-worker-identity", "exec"), {})
            self.assertEqual("key_hex=" + "a" * 64 + "\n", output.read_text())

    def test_identity_requires_the_sole_exact_elected_row_key_and_tree(self):
        row = {"product": "sdk", "component": "sdk-ios", "phase": "binary",
               "target": "ios", "buildKey": KEY}
        self.run_identity([row])
        cases = (
            ([{**row, "target": "macos-arm64"}], "true", KEY, TREE),
            ([row, row], "true", KEY, TREE),
            ([row], "false", KEY, TREE),
            ([row], "true", "sha256:" + "c" * 64, TREE),
            ([row], "true", KEY, "not-a-tree"),
        )
        for rows, required, key, tree in cases:
            with self.subTest(rows=rows, required=required, key=key, tree=tree):
                self.run_identity(rows, required=required, key=key, tree=tree, sentinel="preserve\n")

    def test_fixed_cli_forwards_all_three_original_native_uploads(self):
        self.assertIn("python3 -B -m ci.sdk_workflow ios-binary", self.action)
        for argument in (
            "--plan \"$PLAN\"", "--discovery-root \"$DISCOVERY\"",
            "--state-root \"$STATE\"", "--expected-build-key \"$BUILD_KEY\"",
            "--trusted-workflow-sha \"$TRUSTED_WORKFLOW_SHA\"",
            "--native-tests-artifact-id \"$NATIVE_TESTS_ID\"",
            "--native-tests-artifact-sha256 \"$NATIVE_TESTS_SHA256\"",
            "--rust-device-artifact-id \"$RUST_DEVICE_ID\"",
            "--rust-device-artifact-sha256 \"$RUST_DEVICE_SHA256\"",
            "--rust-simulator-artifact-id \"$RUST_SIMULATOR_ID\"",
            "--rust-simulator-artifact-sha256 \"$RUST_SIMULATOR_SHA256\"",
        ):
            self.assertIn(argument, self.action)
        self.assertNotIn("ssh-keygen", self.action)
        self.assertNotRegex(self.action, r"secrets\.|PRIVATE_KEY")

    def test_failure_collection_is_attempt_unique_immutable_and_complete(self):
        upload = self.action.split("uses: actions/upload-artifact@", 1)[1]
        self.assertIn("if: always() && steps.identity.outcome == 'success'", self.action)
        self.assertIn(
            "name: codex-agent-sdk-worker-sdk-ios-binary-ios-${{ steps.identity.outputs.key_hex }}-"
            "${{ inputs.tree }}-attempt-${{ github.run_attempt }}",
            upload,
        )
        for value in (
            "path: build/sdk-ios-worker", "if-no-files-found: warn",
            "overwrite: false", "include-hidden-files: true", "compression-level: 0",
        ):
            self.assertIn(value, upload)

    def run_parent(self, source, needs, *, rejected=False):
        with tempfile.TemporaryDirectory(prefix="sdk-ios-parent-") as temporary:
            output = Path(temporary) / "github-output"
            sentinel = "preserve\n"
            if rejected:
                output.write_text(sentinel)
            environment = {"PREDECESSORS": json.dumps(needs), "GITHUB_OUTPUT": str(output)}
            with patch.dict(os.environ, environment, clear=True):
                if rejected:
                    with self.assertRaises((KeyError, TypeError, ValueError)):
                        exec(compile(source, "sdk-ios-parent", "exec"), {})
                    self.assertEqual(sentinel, output.read_text())
                    return None
                exec(compile(source, "sdk-ios-parent", "exec"), {})
            return dict(line.split("=", 1) for line in output.read_text().splitlines())

    def test_early_binary_election_and_worker_use_only_the_required_sources(self):
        plan = self.job("sdk-ios-binary-plan")
        self.assertRegex(plan, r"(?m)^    needs: \[plan, product-resume, contract-validation\]$")
        self.assertIn("uses: ./.github/actions/capture-sdk-tooling", plan)
        self.assertIn("artifact-id: ${{ needs.contract-validation.outputs.tooling_artifact_id }}", plan)
        self.assertIn("artifact-sha256: ${{ needs.contract-validation.outputs.tooling_artifact_sha256 }}", plan)
        self.assertIn("sdk-validation-tooling: ${{ steps.tooling.outputs.tooling-policy }}", plan)
        self.assertIn("sdk-apple-validation-policy: ${{ steps.tooling.outputs.apple-policy }}", plan)
        self.assertNotIn("runtime-continuation", plan)
        self.assertNotIn("runtime-aggregate-continuation", plan)
        binary = self.job("sdk-ios-binary")
        self.assertIn("needs: [plan, product-resume, sdk-ios-binary-plan, apple, contract-validation]", binary)
        self.assertIn("uses: ./.github/actions/capture-sdk-tooling", binary)
        for name in ("native_tests", "rust_device", "rust_simulator"):
            self.assertIn(f"needs.apple.outputs.{name}_artifact_id", binary)
            self.assertIn(f"needs.apple.outputs.{name}_artifact_digest", binary)
        self.assertIn("needs.apple.result == 'success'", binary)
        for name in ("native_tests", "rust_device", "rust_simulator"):
            self.assertIn(f"needs.apple.outputs.{name}_artifact_id != ''", binary)
        self.assertEqual(9, binary.count("needs.apple.outputs."))
        self.assertIn("DEVELOPER_DIR: /Applications/Xcode_26.6.app/Contents/Developer", binary)

    def test_sdk_recovery_excludes_runtime_execution_signing_and_phase10(self):
        names = ('product', 'android', 'android-runtime-evidence', 'desktop', 'consumers',
                 'runtime-linux-arm64-supervisor', 'runtime-signing-prepare-native',
                 'runtime-native-attestation', 'runtime-aggregate',
                 'runtime-signing-prepare-aggregate', 'runtime-aggregate-attestation',
                 'runtime-phase10-maven', 'contract-phase10-pgp-authority',
                 'contract-phase10-maven', 'contract-phase10-output-record')
        names += tuple(f'runtime-{kind}-{wave}' for wave in range(1, 5) for kind in ('workers', 'collect'))
        for name in names:
            with self.subTest(job=name):
                guard = self.job(name).split('    if: ', 1)[1].split('    runs-on:', 1)[0].split('    strategy:', 1)[0]
                self.assertTrue('!inputs.sdkRecoveryOnly' in guard or 'inputs.sdkRecoveryOnly != true' in guard)
        self.assertIn('test "$CONTRACT_NEXT_PHASE" = none', self.job('plan'))
        self.assertIn('test "$RUNTIME_WORKERS_REQUIRED" = false', self.job('product-resume'))
        self.assertIn('test -z "$SUPERVISOR_KEY"', self.job('product-resume'))
        self.assertIn('test "$AGGREGATE_STATE" = completed', self.job('runtime-continuation'))
        self.assertIn('test "$AGGREGATE_PAYLOAD_COMPLETE" = true', self.job('runtime-continuation'))

    def test_sdk_recovery_preserves_original_handoff_and_separates_replay_authority(self):
        caller = (ROOT / '.github/workflows/ci.yml').read_text()
        locator = json.loads(re.search(r"^      runtimeAggregateHandoffRecovery: '([^']+)'$", caller, re.MULTILINE)[1])
        self.assertEqual({'artifactId', 'artifactSha256', 'originalProducer', 'trustedWorkflowSha'}, set(locator))
        self.assertEqual(11271945915, locator['artifactId'])
        self.assertEqual('sha256:79e7b75470ab73b2ce3b14304bde1efa9da738956a14117e611754914db3529b', locator['artifactSha256'])
        self.assertEqual('cec458a479c0556d39aa6a75b18311500ce66d71', locator['trustedWorkflowSha'])
        self.assertEqual((37081083913, 1, 'db38c174a2db6f02ff6b6e2091e809681d83a4d9',
                          '9e500ae9373416a16f09fb4a264cd0c9c22513e8'),
                         tuple(locator['originalProducer'][field] for field in ('runId', 'runAttempt', 'commit', 'tree')))
        inputs = self.job('sdk-inputs')
        for value in ('needs.runtime-aggregate-continuation.outputs.aggregate_key',
                      'needs.runtime-aggregate-continuation.outputs.aggregate_receipt_sha256',
                      '--runtime-original-producer', '--runtime-original-workflow-sha',
                      '--trusted-workflow-sha "$TRUSTED_WORKFLOW_SHA"'):
            self.assertIn(value, inputs)
        self.assertNotIn('ssh-keygen', inputs)
        self.assertNotIn('PRIVATE_KEY', inputs)
        apple = self.job('apple')
        self.assertIn('needs.sdk-ios-binary-plan.outputs.sdk_workers_required', apple)
        self.assertIn('needs.runtime-continuation.result', apple)
        self.assertIn('sdkBinaryOnly: ${{ inputs.sdkRecoveryOnly }}', apple)
        child = (ROOT / '.github/workflows/apple-runtime-evidence.yml').read_text()
        selected = re.search(r'(?ms)^      - id: lanes\n.*?(?=^  native-tests:)', child)[0]
        self.assertIn('lanes=(--lane ios-native-tests --lane ios-rust-device --lane ios-rust-simulator)', selected)
        self.assertIn('if [ "$SDK_BINARY_ONLY" != true ]; then', selected)
        self.assertIn('RECOVERY_ONLY: ${{ inputs.runtimeRecoveryOnly || inputs.sdkRecoveryOnly }}', self.job('merge-gate'))

    def test_binary_collection_uses_latest_runtime_state_and_rejects_incomplete_state(self):
        collect = self.job("sdk-collect-3")
        self.assertIn("sdk-ios-binary", collect.split("runs-on:", 1)[0])
        self.assertIn("artifact-id: ${{ steps.parent.outputs.artifact_id }}", collect)
        self.assertNotIn("needs.product-resume", collect)
        runtime = {"result": "success", "outputs": {
            "aggregate_state": "not-selected", "artifact_id": "101",
            "artifact_digest": "sha256:" + "1" * 64, "state_wave": "4",
        }}
        aggregate = {"result": "success", "outputs": {
            "artifact_id": "202", "artifact_digest": "sha256:" + "2" * 64,
            "state_wave": "5",
        }}
        actual = self.run_parent(self.collect_parent, {
            "runtime-continuation": runtime,
            "runtime-aggregate-continuation": aggregate,
        })
        self.assertEqual({"artifact_id": "101", "artifact_digest": "sha256:" + "1" * 64,
                          "state_wave": "4"}, actual)
        selected = {**runtime, "outputs": {**runtime["outputs"], "aggregate_state": "completed"}}
        actual = self.run_parent(self.collect_parent, {
            "runtime-continuation": selected,
            "runtime-aggregate-continuation": aggregate,
        })
        self.assertEqual({"artifact_id": "202", "artifact_digest": "sha256:" + "2" * 64,
                          "state_wave": "5"}, actual)
        for broken in (
            {"runtime-continuation": {**runtime, "result": "failure"},
             "runtime-aggregate-continuation": aggregate},
            {"runtime-continuation": selected,
             "runtime-aggregate-continuation": {**aggregate, "result": "skipped"}},
            {"runtime-continuation": {"result": "success", "outputs": {"aggregate_state": "not-selected"}},
             "runtime-aggregate-continuation": aggregate},
        ):
            with self.subTest(broken=broken):
                self.run_parent(self.collect_parent, broken, rejected=True)

    def test_sdk_plan_selects_collected_binary_wave_and_js_forwards_it(self):
        runtime = {"result": "success", "outputs": {
            "sdk_input_selection": json.dumps({"source": "released-default"}),
            "aggregate_state": "completed",
            "artifact_id": "101", "artifact_digest": "sha256:" + "1" * 64,
            "state_wave": "4",
        }}
        aggregate = {"result": "success", "outputs": {
            "artifact_id": "202", "artifact_digest": "sha256:" + "2" * 64,
            "state_wave": "5",
        }}
        binary = {"result": "success", "outputs": {
            "artifact_id": "303", "artifact_digest": "sha256:" + "3" * 64,
            "wave_failed": "false",
        }}
        needs = {"runtime-continuation": runtime, "runtime-aggregate-continuation": aggregate,
                 "sdk-ios-binary-plan": {"outputs": {"sdk_workers_required": "true"}},
                 "sdk-collect-3": binary}
        self.assertEqual({
            "artifact_id": "303", "artifact_digest": "sha256:" + "3" * 64,
            "state_wave": "0", "sdk_state_wave": "3",
        }, self.run_parent(self.sdk_parent, needs))
        for field, value in (("sdk_workers_required", None), ("sdk_workers_required", "unknown")):
            broken = json.loads(json.dumps(needs))
            if value is None:
                del broken["sdk-ios-binary-plan"]["outputs"][field]
            else:
                broken["sdk-ios-binary-plan"]["outputs"][field] = value
            with self.subTest(field=field, value=value):
                self.run_parent(self.sdk_parent, broken, rejected=True)
        for field, value in (("wave_failed", "true"), ("artifact_id", None)):
            broken = json.loads(json.dumps(needs))
            if value is None:
                del broken["sdk-collect-3"]["outputs"][field]
            else:
                broken["sdk-collect-3"]["outputs"][field] = value
            with self.subTest(field=field, value=value):
                self.run_parent(self.sdk_parent, broken, rejected=True)
        forwarding = "sdk-state-wave: ${{ needs.sdk-plan.outputs.sdk_state_wave }}"
        self.assertIn(forwarding, self.job("sdk-workers-1"))
        self.assertIn(forwarding, self.job("sdk-collect-1"))


if __name__ == "__main__":
    unittest.main()
