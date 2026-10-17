"""Synthetic official-API evidence and real Git; not hosted acceptance."""

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from ci.tests.test_contract_attestation_workflow import workflow_job
from ci.tests.test_runtime_aggregate_attestation_workflow import shell

HELPER = Path(__file__).resolve().parents[2] / ".github/actions/prepare-runtime-signing/recovery_acceptance.py"
SPEC = importlib.util.spec_from_file_location("runtime_recovery_acceptance", HELPER)
recovery = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = recovery
SPEC.loader.exec_module(recovery)
SELECTOR = "ci/products/selection.py"


class RuntimeRecoveryAcceptanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from products.inventory import regular_file_inventory
        cls.fixture = cls(methodName="runTest")
        cls.addClassCleanup(cls.fixture.doCleanups)
        cls.fixture._create_fixture()
        before = regular_file_inventory(cls.fixture.root, allow_empty=True)
        cls.addClassCleanup(lambda: cls.fixture.assertEqual(
            before, regular_file_inventory(cls.fixture.root, allow_empty=True)))

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="runtime-recovery-acceptance-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        # Copy bytes, including Git objects: fault-injection tests must never
        # share writable files or metadata with the class fixture or each other.
        shutil.copytree(self.fixture.root, self.root, dirs_exist_ok=True)
        self.trusted, self.candidate = self.root / "trusted", self.root / "candidate"
        self.event_path = self.root / "event.json"
        for name in ("ci", "base", "correction", "product_correction", "reuse_correction",
                     "reviewed", "cache_correction", "activation", "merge"):
            setattr(self, name, getattr(self.fixture, name))
        values = copy.deepcopy({name: getattr(self.fixture, name) for name in
                                ("producer", "event", "environment", "run", "job", "tested")})
        for name, value in values.items():
            setattr(self, name, value)
        self.environment["GITHUB_EVENT_PATH"] = str(self.event_path)
        self.git(self.candidate, "remote", "set-url", "origin", str(self.trusted))
        self._patch_reviewed()

    def test_sdk_selector_pin_matches_reviewed_native_staging_bytes(self):
        root = HELPER.parents[3]
        self.assertEqual("bd83cc6cbd3b5cae6954bed7e91ac1cf106a3715", recovery.SDK_SELECTION_REVISION)
        self.assertEqual(recovery._blob(root, recovery.SDK_SELECTION_REVISION, recovery.SDK_SELECTOR),
                         (root / recovery.SDK_SELECTOR).read_bytes())

    def test_current_full_caller_preserves_historical_transport_assertions(self):
        root = Path(__file__).resolve().parents[2]
        caller = (root / '.github/workflows/ci.yml').read_bytes()
        self.assertIn(b'trustedWorkflowSha: ${{ inputs.trustedWorkflowSha }}', caller)
        self.assertEqual(caller, recovery._activated_ci(caller, "b" * 40))
        for name in (b'trustedWorkflowSha', b'trustedSourceSha'):
            invalid = caller.replace(b'      sdkRecoveryOnly: true\n',
                b'      sdkRecoveryOnly: true\n      ' + name + b': ' + b'a' * 40 + b'\n')
            with self.subTest(name=name), self.assertRaises(ValueError):
                recovery._activated_ci(invalid, "b" * 40)

    def test_protected_caller_is_hash_free_and_cannot_choose_source(self):
        source = (b"    uses: codex-agent-labs/codex-agent/.github/workflows/product-validation.yml@"
                  + b"a" * 40 + b"\n      trustedWorkflowSha: " + b"a" * 40 + b"\n")
        expected = b"    uses: codex-agent-labs/codex-agent/.github/workflows/product-validation.yml@reuse-authority\n"
        self.assertEqual(expected, recovery._activated_ci(source, "b" * 40))
        self.assertEqual(expected, recovery._activated_ci(expected, "c" * 40))
        for invalid in (source + source, expected + b"      trustedWorkflowSha: " + b"a" * 40 + b"\n",
                        expected + b"      trustedWorkflowSha: ${{ inputs.sha }}\n",
                        expected + b"      trustedSourceSha: " + b"a" * 40 + b"\n",
                        expected.replace(b"reuse-authority", b"main"),
                        expected.replace(b"reuse-authority", b"${{ inputs.sha }}")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                recovery._activated_ci(invalid, "b" * 40)

    def test_scoped_recovery_cannot_pass_the_final_merge_gate(self):
        for repository in (self.trusted, self.candidate):
            self.assertEqual("false", self.git(repository, "config", "--get", "maintenance.auto").strip())
            self.assertEqual("0", self.git(repository, "config", "--get", "gc.auto").strip())
        root = Path(__file__).resolve().parents[2]
        workflow = (root / '.github/workflows/product-validation.yml').read_text()
        self.assertIn("!inputs.runtimeRecoveryOnly", workflow_job(workflow, "consumers"))
        gate = workflow_job(workflow, 'merge-gate')
        step = re.split(r'(?=^      - )', gate, flags=re.MULTILINE)[1]
        result = subprocess.run(['bash', '-c', shell(step)],
            env={**os.environ, 'RECOVERY_ONLY': 'true'}, capture_output=True, text=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIn('does not satisfy full-current-head acceptance', result.stderr)
        caller = (root / '.github/workflows/ci.yml').read_text()
        self.assertIn('test "$FULL_ACCEPTANCE_CURRENT" = true', caller)

    def _create_fixture(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="runtime-recovery-acceptance-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.trusted = self.root / "trusted"
        self.trusted.mkdir()
        self.git(self.trusted, "init", "--quiet")
        self.git(self.trusted, "config", "core.autocrlf", "false")
        self.git(self.trusted, "config", "gc.auto", "0")
        self.ci = (
            "permissions: read\n    uses: codex-agent-labs/codex-agent/.github/workflows/product-validation.yml@"
            + recovery.BASELINE_WORKFLOW + "\n      trustedWorkflowSha: " + recovery.BASELINE_WORKFLOW + "\n"
        )
        files = {
            recovery.CI: self.ci, ".github/workflows/product-validation.yml": "name: original\n",
            SELECTOR: '[\n    "ci/runtime_candidate_transport.py",\n]\n',
            ".github/actions/prepare-runtime-signing/action.yml": "original action\n",
            "ci/tests/test_prepare_runtime_signing_action.py": "original test\n",
            "ci/runtime_preparation_capture.py": "original inline capture\n",
            "ci/tests/test_runtime_preparation_capture.py": "original capture test\n",
            "ci/runtime_prepared_release.py": "original redundant forwarding\n",
            "ci/tests/test_runtime_prepared_release.py": "original forwarding test\n",
            "ci/runtime_original_ci.py": "original raw provenance capture\n",
            "ci/tests/test_runtime_aggregate_original_ci.py": "original provenance tests\n",
            "ci/runtime_aggregate_release.py": "original aggregate signer\n",
            "ci/tests/test_runtime_aggregate_release.py": "original aggregate signer tests\n",
            "ci/products/runtime_aggregate_handoff.py": "original raw provenance reader\n",
            "ci/tests/test_runtime_aggregate_handoff.py": "original aggregate reader tests\n",
            "ci/tests/test_runtime_native_attestation_workflow.py": "original native signer pin\n",
            "ci/tests/test_runtime_aggregate_attestation_workflow.py": "original aggregate signer pin\n",
            "runtime/product.txt": "unchanged product\n",
        }
        for name, contents in files.items():
            self.write(self.trusted, name, contents)
        for name in recovery.PRODUCT_CORRECTION_FILES:
            self.write(self.trusted, name, "original metadata verifier\n")
        for name in recovery.REUSE_FIXED_FILES - recovery.REUSE_NEW_FILES:
            if name != SELECTOR:
                self.write(self.trusted, name, "original reuse control\n")
        for name in recovery.CACHE_FIXED_FILES - recovery.CACHE_NEW_FILES:
            if not (self.trusted / name).exists():
                self.write(self.trusted, name, "original cache control\n")
        self.base = self.commit(self.trusted, "baseline")
        self.producer = dict(recovery.BASELINE_PRODUCER,
            tree=self.git(self.trusted, "rev-parse", "HEAD^{tree}").strip())
        self.write(self.trusted, ".github/actions/prepare-runtime-signing/action.yml", "reviewed correction\n")
        self.write(self.trusted, "ci/tests/test_prepare_runtime_signing_action.py", "reviewed composition test\n")
        self.correction = self.commit(self.trusted, "fixed action")
        for name in recovery.PRODUCT_CORRECTION_FILES:
            self.write(self.trusted, name, "fixed reviewed metadata verifier\n")
        self.product_correction = self.commit(self.trusted, "fixed metadata verifier")
        for name in recovery.REUSE_FIXED_FILES | (recovery.REFERENCE_TRANSPORT_FILES & recovery.REUSE_NEW_FILES):
            self.write(self.trusted, name, "fixed reviewed reuse control\n")
        self.reuse_correction = self.commit(self.trusted, "fixed reuse controls")
        for name in recovery.NEW_FILES - recovery.REUSE_NEW_FILES:
            self.write(self.trusted, name, "reviewed control\n")
        self.write(self.trusted, ".github/workflows/product-validation.yml", "name: reviewed recovery\n")
        for name in ("ci/runtime_preparation_capture.py", "ci/tests/test_runtime_preparation_capture.py",
                     "ci/runtime_prepared_release.py", "ci/tests/test_runtime_prepared_release.py",
                     "ci/runtime_original_ci.py", "ci/tests/test_runtime_aggregate_original_ci.py",
                     "ci/runtime_aggregate_release.py", "ci/tests/test_runtime_aggregate_release.py",
                     "ci/products/runtime_aggregate_handoff.py", "ci/tests/test_runtime_aggregate_handoff.py",
                     "ci/tests/test_runtime_native_attestation_workflow.py",
                     "ci/tests/test_runtime_aggregate_attestation_workflow.py"):
            self.write(self.trusted, name, "reviewed streaming control\n")
        self.reviewed = self.commit(self.trusted, "reviewed recovery")
        for name in recovery.CACHE_FIXED_FILES:
            self.write(self.trusted, name, "fixed independently reviewed cache control\n")
        self.cache_correction = self.commit(self.trusted, "fixed cache controls")
        self.reviewed = self.cache_correction
        self.candidate = self.root / "candidate"
        self.git(self.root, "clone", "--quiet", "--local", str(self.trusted), str(self.candidate))
        self.write(self.candidate, recovery.CI,
            recovery._activated_ci(self.ci.encode(), self.reviewed).decode())
        self.activation = self.commit(self.candidate, "literal caller activation")
        self.make_merge()
        self.event_path = self.root / "event.json"
        repository = {"full_name": self.producer["repository"], "fork": False}
        self.event = {"action": "labeled", "number": 31, "label": {"name": "ci:remote-final"},
            "repository": repository, "pull_request": {"number": 31, "draft": False,
                "labels": [{"name": "merge-ready"}, {"name": "ci:remote-final"}],
                "base": {"sha": self.base, "repo": repository},
                "head": {"sha": self.activation, "repo": repository}}}
        self.environment = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": repository["full_name"],
            "GITHUB_EVENT_NAME": "pull_request", "GITHUB_SHA": self.merge,
            "GITHUB_REF": "refs/pull/31/merge", "GITHUB_EVENT_PATH": str(self.event_path)}
        self.run = {"id": self.producer["runId"], "run_attempt": 1, "path": self.producer["workflowPath"],
            "event": "pull_request", "repository": repository, "head_repository": repository,
            "head_sha": "d" * 40, "status": "completed", "conclusion": "failure",
            "pull_requests": [{"number": 31, "base": {"sha": "b" * 40}, "head": {"sha": "d" * 40}}],
            "referenced_workflows": [{"path": repository["full_name"]
                + "/.github/workflows/product-validation.yml@" + recovery.BASELINE_WORKFLOW,
                "sha": recovery.BASELINE_WORKFLOW}]}
        self.job = {"id": recovery.BASELINE_JOB, "name": recovery.JOB_NAME,
            "run_id": self.producer["runId"], "head_sha": self.run["head_sha"],
            "status": "completed", "conclusion": "success"}
        self.tested = {"sha": self.producer["commit"], "tree": {"sha": self.producer["tree"]},
            "parents": [{"sha": "b" * 40}, {"sha": "d" * 40}]}

    def _patch_reviewed(self):
        for attribute, value in (("BASELINE_PRODUCER", self.producer), ("CORRECTION_REVISION", self.correction),
                                 ("PRODUCT_CORRECTION_REVISION", self.product_correction),
                                 ("REUSE_CONTROL_REVISION", self.reuse_correction),
                                 ("REFERENCE_TRANSPORT_REVISION", self.reviewed),
                                 ("CACHE_CONTROL_REVISION", self.cache_correction),
                                 ("__file__", str(self.trusted / recovery.HELPER))):
            patcher = mock.patch.object(recovery, attribute, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def git(self, root, *arguments):
        # Keep fixture writes synchronous, including the separately cloned repo.
        result = subprocess.run(["git", "-c", "maintenance.auto=false", "-c", "gc.auto=0", *arguments], cwd=root, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout.decode()

    def write(self, root, name, contents):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def commit(self, root, message):
        self.git(root, "add", ".")
        self.git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "commit", "--quiet", "-m", message)
        return self.git(root, "rev-parse", "HEAD").strip()

    def make_merge(self):
        tree = self.git(self.candidate, "rev-parse", "HEAD^{tree}").strip()
        self.merge = self.git(self.candidate, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "commit-tree", tree, "-p", self.base, "-p", self.activation, "-m", "synthetic tested merge").strip()
        self.git(self.candidate, "checkout", "--quiet", "--detach", self.merge)

    def verify(self, *, event=None, environment=None, job=None, run=None,
               publisher=None, source=None):
        self.event_path.write_text(json.dumps(self.event if event is None else event), encoding="utf-8")
        old_run = self.run if run is None else run

        def api(url, token):
            self.assertEqual("synthetic-token", token)
            if url.endswith("/attempts/1"):
                return copy.deepcopy(old_run)
            self.assertTrue(url.endswith("/git/commits/" + self.producer["commit"]), url)
            return copy.deepcopy(self.tested)

        with mock.patch.object(recovery.products, "api_json", side_effect=api), \
                mock.patch.object(recovery.products, "paginated_items",
                    return_value=[self.job if job is None else job]):
            return recovery.verify_recovery_acceptance(self.candidate, publisher or self.reviewed,
                token="synthetic-token", environ=self.environment if environment is None else environment,
                trusted_source_sha=source)

    def test_native_publisher_is_not_substituted_for_approved_source(self):
        result = self.verify(publisher="e" * 40, source=self.reviewed)
        self.assertEqual("e" * 40, result["executing_workflow_sha"])
        self.assertEqual(self.reviewed, result["reviewed_source_sha"])
        self.assertFalse(result["full_acceptance_current"])
        with self.assertRaisesRegex(ValueError, "clean pinned source"):
            self.verify(publisher="e" * 40, source=self.base)

    def change_candidate(self, path, contents):
        self.git(self.candidate, "checkout", "--quiet", "--detach", self.activation)
        self.write(self.candidate, path, contents)
        self.activation = self.commit(self.candidate, "unreviewed change")
        self.make_merge()
        self.event["pull_request"]["head"]["sha"] = self.activation
        self.environment["GITHUB_SHA"] = self.merge

    def sdk_mode(self, *, product_change=False, sdk_change=False, executable_mode=None, aggregate_correction=None):
        # Real Git trees exercise the shared inventory policy; API identities
        # remain explicit fixtures, never genuine hosted acceptance evidence.
        self.git(self.trusted, "checkout", "--quiet", "--detach", self.reviewed)
        self.write(self.trusted, recovery.SDK_REGISTRY,
            (HELPER.parents[3] / recovery.SDK_REGISTRY).read_text())
        if executable_mode is not None:
            self.write(self.trusted, "ci/run-lane.sh", "#!/bin/sh\n# original tooling producer\n")
            (self.trusted / "ci/run-lane.sh").chmod(0o755)
        if aggregate_correction is not None:
            self.write(self.trusted, "ci/products/sdk_maven.py", "original Maven writer\n")
        frozen = self.commit(self.trusted, "frozen SDK registry and product inputs")
        if aggregate_correction is not None:
            self.write(self.trusted, "ci/products/sdk_maven.py", "reviewed canonical Maven writer\n")
            correction = self.commit(self.trusted, "independently reviewed aggregate correction")
            patcher = mock.patch.object(recovery, "SDK_AGGREGATE_CORRECTION", correction)
            patcher.start()
            self.addCleanup(patcher.stop)
            if aggregate_correction == "unreviewed":
                self.write(self.trusted, "ci/products/sdk_maven.py", "another unreviewed writer\n")
        if executable_mode is not None:
            self.write(self.trusted, "ci/run-lane.sh", "#!/bin/sh\n# reviewed tooling producer\n")
            (self.trusted / "ci/run-lane.sh").chmod(executable_mode)
        self.write(self.trusted, recovery.CI, self.ci
            + "      runtimeRecoveryOnly: false\n      sdkRecoveryOnly: true\n")
        self.write(self.trusted, ".github/actions/run-ci-lane/sdk-current-control.py", "reviewed control-only continuation\n")
        if product_change:
            self.write(self.trusted, "runtime/product.txt", "changed product\n")
        if sdk_change:
            self.write(self.trusted, "ci/products/sdk_archive.py", "# reviewed SDK-only archive validation\n")
        self.reviewed = self.commit(self.trusted, "reviewed SDK continuation")
        for name, value in (("SDK_FROZEN_REVISION", frozen), ("SDK_SELECTION_REVISION", frozen)):
            patcher = mock.patch.object(recovery, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.git(self.candidate, "fetch", "--quiet", str(self.trusted), self.reviewed)
        self.git(self.candidate, "checkout", "--quiet", "--detach", self.reviewed)
        caller = self.git(self.trusted, "show", f"{self.reviewed}:{recovery.CI}")
        self.write(self.candidate, recovery.CI, recovery._activated_ci(caller.encode(), self.reviewed).decode())
        self.activation = self.commit(self.candidate, "activate exact reviewed SDK source")
        self.make_merge()
        self.event["pull_request"]["head"]["sha"] = self.activation
        self.environment["GITHUB_SHA"] = self.merge

    def test_sdk_continuation_admits_only_exact_frozen_inputs_and_never_full_acceptance(self):
        self.sdk_mode()
        with mock.patch.object(recovery, "_phase_git_inventories", wraps=recovery._phase_git_inventories) as inventory:
            result = self.verify()
        instances = tuple(instance for instance in recovery.PHASE_INSTANCE_IDS if instance.product != "sdk")
        self.assertEqual(50, len(instances))
        self.assertEqual(2, inventory.call_count)
        inventory.assert_has_calls([
            mock.call(self.trusted, recovery.SDK_FROZEN_REVISION, instances),
            mock.call(self.trusted, self.reviewed, instances),
        ])
        self.assertTrue(result["recovery_control_admitted"])
        self.assertFalse(result["full_acceptance_current"])
        self.assertEqual(self.producer, result["historical_acceptance_producer"])

    def test_sdk_reviewed_product_input_change_is_rejected(self):
        self.sdk_mode(product_change=True)
        with self.assertRaisesRegex(ValueError, "changes frozen product inputs"):
            self.verify()

    def test_reviewed_aggregate_correction_preserves_historical_only_acceptance(self):
        self.sdk_mode(aggregate_correction="reviewed")
        result = self.verify()
        self.assertTrue(result["recovery_control_admitted"])
        self.assertFalse(result["full_acceptance_current"])
        self.assertEqual(self.producer, result["historical_acceptance_producer"])

    def test_aggregate_exception_rejects_unreviewed_writer(self):
        self.sdk_mode(aggregate_correction="unreviewed")
        with self.assertRaisesRegex(ValueError, "changes frozen product inputs"):
            self.verify()

    def test_aggregate_exception_does_not_admit_other_product_changes(self):
        self.sdk_mode(aggregate_correction="reviewed", product_change=True)
        with self.assertRaisesRegex(ValueError, "changes frozen product inputs"):
            self.verify()

    def test_sdk_tooling_producer_preserves_existing_executable_mode(self):
        self.sdk_mode(executable_mode=0o755)
        self.assertTrue(self.verify()["recovery_control_admitted"])

    def test_sdk_tooling_producer_mode_change_is_rejected(self):
        self.sdk_mode(executable_mode=0o644)
        with self.assertRaisesRegex(ValueError, "modes, symlinks or deletions"):
            self.verify()

    def test_reviewed_sdk_input_change_does_not_claim_current_sdk_acceptance(self):
        self.sdk_mode(sdk_change=True)
        result = self.verify()
        self.assertTrue(result["recovery_control_admitted"])
        self.assertFalse(result["full_acceptance_current"])
        self.assertEqual(self.producer, result["historical_acceptance_producer"])

    def test_sdk_control_tree_mismatch_and_unauthorized_event_are_rejected(self):
        self.sdk_mode()
        with self.assertRaisesRegex(ValueError, "same-repository PR"):
            self.verify(environment=dict(self.environment, GITHUB_EVENT_NAME="workflow_dispatch"))
        unauthorized = copy.deepcopy(self.event)
        unauthorized["action"] = "synchronize"
        unauthorized.pop("label")
        unauthorized["pull_request"]["labels"] = []
        with self.assertRaisesRegex(ValueError, "not authorized"):
            self.verify(event=unauthorized)
        self.change_candidate(".github/actions/run-ci-lane/sdk-current-control.py", "candidate self-authorized change\n")
        with self.assertRaisesRegex(ValueError, "independently reviewed control tree"):
            self.verify()

    def test_prior_green_job_admits_only_reviewed_recovery_and_preserves_historical_identity(self):
        result = self.verify()
        self.assertTrue(result["recovery_control_admitted"])
        self.assertFalse(result["full_acceptance_current"])
        self.assertEqual(self.producer, result["historical_acceptance_producer"])
        self.assertEqual(recovery.BASELINE_JOB, result["historical_acceptance_job_id"])
        self.assertEqual(recovery.BASELINE_WORKFLOW, result["historical_acceptance_workflow_sha"])

    def test_unreviewed_product_action_selector_and_caller_changes_are_rejected(self):
        for path in ("runtime/product.txt", ".github/actions/prepare-runtime-signing/action.yml",
                     "ci/products/aggregate.py", SELECTOR, recovery.CI,
                     ".github/actions/hydrated-evidence-cache/cache.mjs", "ci/hydrated_evidence.py"):
            with self.subTest(path=path):
                original = (self.candidate / path).read_text()
                self.change_candidate(path, original + "unreviewed\n")
                with self.assertRaises(ValueError):
                    self.verify()
                self.change_candidate(path, original)

    def test_reviewed_revision_still_rejects_changed_product_correction_selector_and_mode(self):
        for path in ("runtime/product.txt", ".github/actions/prepare-runtime-signing/action.yml",
                     "ci/products/aggregate.py", "ci/products/verified_evidence.py",
                     "ci/runtime_reference_archive.py", "ci/tests/test_reference_archive_download.py",
                     SELECTOR, recovery.HELPER):
            with self.subTest(path=path):
                original = self.reviewed
                self.git(self.trusted, "checkout", "--quiet", "--detach", original)
                if path == recovery.HELPER:
                    (self.trusted / path).chmod(0o755)
                else:
                    self.write(self.trusted, path, (self.trusted / path).read_text() + "not admissible\n")
                self.reviewed = self.commit(self.trusted, "inadmissible reviewed delta")
                with self.assertRaises(ValueError):
                    self.verify()
                self.git(self.trusted, "checkout", "--quiet", "--detach", original)
                self.reviewed = original

    def test_wrong_failed_job_workflow_and_dispatch_are_rejected(self):
        for job in (dict(self.job, id=1), dict(self.job, conclusion="failure"), dict(self.job, status="in_progress")):
            with self.subTest(job=job):
                with self.assertRaises(ValueError):
                    self.verify(job=job)
        run = copy.deepcopy(self.run)
        run["referenced_workflows"][0]["sha"] = "a" * 40
        with self.assertRaises(ValueError):
            self.verify(run=run)
        with self.assertRaises(ValueError):
            self.verify(environment=dict(self.environment, GITHUB_EVENT_NAME="workflow_dispatch"))


if __name__ == "__main__":
    unittest.main()
