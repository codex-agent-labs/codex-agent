"""A failed Runtime validation keeps successful predecessors for exact reuse."""

from contextlib import ExitStack
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest import mock

from ci.products.inventory import canonical_json_bytes, load_canonical_json, regular_file_inventory
from ci.products.receipt import write_output_manifest
from ci.products.restore import PHASE_PLAN_KEYS
from ci.products.restore import finalize_phase_object
from ci.tests import test_runtime_resumed_phase as fixture
from ci.tests.test_product_toolchain import profile


adapter = fixture.adapter
TARGET = "macos-arm64"
BINARY, PACKAGE, VALIDATION, METADATA = (
    adapter.PhaseInstanceId("runtime", TARGET, phase, TARGET)
    for phase in ("binary", "package", "validation", "metadata")
)


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class RuntimeLatePhaseRecoveryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        owner = fixture.resume_fixture.fixture.ProductReuseAdapterTest
        create_repository = owner.contract_repository

        def repository_with_fixture_profile(helper):
            repository, _, _ = create_repository(helper)
            source = Path(__file__).resolve().parents[2]
            native_inputs = (
                "codex-agent-runtime-desktop/native/c-api/abi-contract.json",
                "codex-agent-runtime-desktop/native/c-api/binary-flags.json",
                "codex-agent-runtime-desktop/native/c-api/include/codex_agent.h",
                "codex-agent-runtime-desktop/native/c-api/exports/macos.exports",
                "codex-agent-runtime-desktop/native/c-api/exports/linux.map",
                "codex-agent-runtime-desktop/native/c-api/exports/windows.def",
                "codex-agent-runtime-desktop/codex-app-server-distributions.json",
            )
            for relative in native_inputs:
                destination = repository / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / relative, destination)
            selected = repository / f"gradle/release/toolchains/runtime/{TARGET}.json"
            selected.parent.mkdir(parents=True)
            selected.write_bytes(canonical_json_bytes(profile(TARGET)))
            subprocess.run(("git", "add", "gradle/release/toolchains/runtime", "codex-agent-runtime-desktop"),
                           cwd=repository, check=True)
            subprocess.run(("git", "commit", "-qm", "fixture-only native authorities"),
                           cwd=repository, check=True)
            def revision(value):
                return subprocess.run(("git", "rev-parse", value), cwd=repository, check=True,
                                      capture_output=True, text=True).stdout.strip()
            return repository, revision("HEAD"), revision("HEAD^{tree}")

        with mock.patch.object(owner, "contract_repository", repository_with_fixture_profile):
            fixture.RuntimeResumedPhaseTest.setUpClass.__func__(cls)

    setUp = fixture.RuntimeResumedPhaseTest.setUp
    tearDown = fixture.RuntimeResumedPhaseTest.tearDown
    resume = fixture.RuntimeResumedPhaseTest.resume

    @classmethod
    def control_seams(cls):
        stack = ExitStack()
        stack.enter_context(mock.patch.object(adapter, "_validate_plan", return_value=cls.plan))
        stack.enter_context(mock.patch.object(adapter, "_requested", return_value=(METADATA,)))
        return stack

    def phase_shard(self, state: Path, instance, name: str):
        plan_name = "-".join((instance.product, instance.component, instance.phase, instance.target))
        plan = load_canonical_json(state / "phase-plans" / f"{plan_name}.json")
        # Native identity is a worker preflight projection, not a receipt field.
        plan = {key: plan[key] for key in PHASE_PLAN_KEYS}
        stage = self.scratch / f"{name}-stage"
        output = stage / "outputs/fixture.bin"
        output.parent.mkdir(parents=True)
        output.write_bytes(f"synthetic {instance.phase} payload\n".encode())
        write_output_manifest(stage, instance.product, instance.component, instance.phase,
                              instance.target, "0.2.0", {"fixture": "outputs"})
        shard = self.scratch / f"{name}-shard"
        descriptor = finalize_phase_object(
            stage_root=stage, phase_plan=plan, producer=self.producer,
            product_version="0.2.0", trust_domain="development", destination=shard)
        return shard, descriptor

    def advance(self, discovery: Path, state: Path | None, shards: list[Path], name: str, *, failed=()):
        destination = self.scratch / name
        with self.control_seams():
            result = adapter.advance_products(
                self.plan_path, discovery, state, shards, destination,
                self.scratch / f"{name}-github-output", repository_root=self.repository,
                environ=self.environment, failed_instances=failed)
        return destination, result

    def test_failed_validation_preserves_binary_and_package_receipts_and_objects(self):
        discovery = self.resume()
        state = discovery
        originals = {}
        for instance, name in ((BINARY, "binary"), (PACKAGE, "package")):
            shard, descriptor = self.phase_shard(state, instance, name)
            originals[instance] = (descriptor["receiptBytes"], descriptor["objectSha256"],
                                   regular_file_inventory(shard))
            state, result = self.advance(discovery, None if state == discovery else state,
                                         [shard], f"after-{name}")
            self.assertEqual(originals[instance][2], regular_file_inventory(shard))
            self.assertEqual("retained", next(phase for phase in result["phases"]
                                              if adapter._identity(phase) == instance)["state"])

        elected = load_canonical_json(state / f"phase-plans/runtime-{TARGET}-validation-{TARGET}.json")
        failed_state, result = self.advance(discovery, state, [], "failed-validation", failed=(VALIDATION,))
        self.assertEqual([VALIDATION], [adapter._identity(row) for row in result["matrices"]["runtime"]])
        phases = {adapter._identity(row): row for row in result["phases"]}
        self.assertEqual("build", phases[VALIDATION]["state"])
        self.assertEqual("waiting", phases[METADATA]["state"])
        self.assertEqual(elected["buildKey"], phases[VALIDATION]["buildKey"])
        self.assertFalse((failed_state / f"phase-plans/runtime-{TARGET}-metadata-{TARGET}.json").exists())
        self.assertEqual([VALIDATION], [adapter._identity(row) for row in load_canonical_json(
            failed_state / "wave-failures.json")["failedPhases"]])

        carrier = adapter.verify_carrier(
            failed_state / "reused-carrier",
            tuple(sorted((adapter._identity(row) for row in result["phases"]
                          if row["state"] in {"retained", "reused"}))),
            adapter._consumer(self.plan, self.environment))
        records = {adapter._identity(row): row for row in carrier["objects"]}
        for instance in (BINARY, PACKAGE):
            record = records[instance]
            restored = adapter.verify_object(
                failed_state / "reused-carrier" /
                adapter.object_relative_path(record["buildKey"], record["receiptSha256"]),
                build_key=record["buildKey"], receipt_sha256=record["receiptSha256"],
                object_sha256=record["objectSha256"])
            self.assertEqual(originals[instance][0], restored["receiptBytes"])
            self.assertEqual(originals[instance][1], record["objectSha256"])

        with self.control_seams():
            inspected = adapter.inspect_products(
                self.plan_path, discovery, failed_state, repository_root=self.repository,
                environ=self.environment)
        self.assertEqual([elected], inspected["readyPlans"])
        self.assertEqual(result, inspected["result"])

    def test_prior_failed_phases_replay_under_new_consumer(self):
        discovery = self.resume()
        state = discovery
        old_producer = {**self.producer, "runId": self.producer["runId"] - 1,
                        "runAttempt": 1}
        originals = {}
        for instance, phase in ((BINARY, "binary"), (PACKAGE, "package")):
            current, _ = self.phase_shard(state, instance, f"current-{phase}")
            plan = load_canonical_json(state / f"phase-plans/runtime-{TARGET}-{phase}-{TARGET}.json")
            old = self.scratch / f"old-{phase}-shard"
            finalize_phase_object(
                stage_root=self.scratch / f"current-{phase}-stage",
                phase_plan={key: plan[key] for key in PHASE_PLAN_KEYS},
                producer=old_producer, product_version="0.2.0",
                trust_domain="development", destination=old)
            originals[phase] = old
            state, _ = self.advance(discovery, None if state == discovery else state,
                                    [current], f"current-after-{phase}")
        validation = load_canonical_json(state / f"phase-plans/runtime-{TARGET}-validation-{TARGET}.json")

        calls = []

        def captured(_plan, _producer, requested, destination, **_):
            self.assertEqual(_producer, self.producer)
            calls.append(requested)
            retained = {}
            for instance, key in requested.items():
                shard = originals.get(instance.phase)
                if shard is None:
                    continue
                self.assertEqual(key, load_canonical_json(shard / "phase-receipt.json")["buildKey"])
                shutil.copytree(shard, destination / instance.component / instance.phase / instance.target /
                                "phases" / instance.phase / "original/shard")
                observation = destination / instance.component / instance.phase / instance.target / "transport"
                observation.mkdir()
                (observation / "original-ci-phases.json").write_bytes(canonical_json_bytes(
                    {"observed": [], "artifacts": {}}))
                retained[instance] = {"syntheticOriginalAdmission": True}
            return retained

        official = {
            "id": old_producer["runId"], "run_attempt": old_producer["runAttempt"],
            "event": "pull_request", "path": ".github/workflows/ci.yml",
            "status": "completed", "conclusion": "failure",
            "pull_requests": [{"number": old_producer["pullRequest"]}],
            "repository": {"full_name": old_producer["repository"], "fork": False},
            "head_repository": {"full_name": old_producer["repository"], "fork": False},
            "referenced_workflows": [{
                "path": "codex-agent-labs/codex-agent/.github/workflows/product-validation.yml@" + "c" * 40,
                "sha": "c" * 40,
            }],
        }

        resumed = self.scratch / "new-attempt-resume"
        environment = {**self.environment, "GITHUB_TOKEN": "fixture-only"}
        with self.control_seams(), mock.patch.object(adapter, "_prior_failed_pr_attempts",
                                                     return_value=(official,)), mock.patch.object(
                                                         adapter, "capture_prior_failed_runtime_phases",
                                                         side_effect=captured):
            adapter.resume_products(
                self.plan_path, self.discovery, self.state, self.handoff,
                resumed, self.scratch / "new-attempt-output", repository_root=self.repository,
                environ=environment, sdk_original_workflow_sha="c" * 40)
        self.assertEqual([BINARY, PACKAGE, VALIDATION],
                         [next(iter(requested)) for requested in calls])
        result = load_canonical_json(resumed / "reuse-wave-result.json")
        states = {adapter._identity(row): row for row in result["phases"]}
        self.assertEqual("retained", states[BINARY]["state"])
        self.assertEqual("retained", states[PACKAGE]["state"])
        self.assertEqual([VALIDATION], [adapter._identity(row) for row in result["matrices"]["runtime"]])
        self.assertEqual(validation["buildKey"], result["matrices"]["runtime"][0]["buildKey"])
        carrier = adapter.verify_carrier(resumed / "reused-carrier", tuple(sorted(
            adapter._identity(row) for row in result["phases"] if row["state"] in {"retained", "reused"})),
            adapter._consumer(self.plan, environment))
        for phase, instance in (("binary", BINARY), ("package", PACKAGE)):
            record = next(row for row in carrier["objects"] if adapter._identity(row) == instance)
            stored = adapter.verify_object(
                resumed / "reused-carrier" / adapter.object_relative_path(
                    record["buildKey"], record["receiptSha256"]),
                build_key=record["buildKey"], receipt_sha256=record["receiptSha256"],
                object_sha256=record["objectSha256"])
            self.assertEqual((originals[phase] / "phase-receipt.json").read_bytes(), stored["receiptBytes"])

        def recheck(receipts, destination, **_):
            phase = next(iter(receipts))
            shutil.copytree(resumed / "prior-failed-runtime" / TARGET / phase / TARGET, destination)
            return adapter._canonical_control(destination / "transport/original-ci-phases.json", "fixture")

        with self.control_seams(), mock.patch.object(adapter, "api_json", return_value={
            **official, "id": old_producer["runId"] - 1}):
            with self.assertRaisesRegex(ValueError, "official CI"):
                adapter.inspect_products(
                    self.plan_path, resumed, repository_root=self.repository,
                    environ=environment, sdk_original_workflow_sha="c" * 40)

        with self.control_seams(), mock.patch.object(adapter, "capture_runtime_original_ci_phases",
                                                     side_effect=recheck), mock.patch.object(
                                                         adapter, "api_json", return_value=official):
            inspected = adapter.inspect_products(
                self.plan_path, resumed, repository_root=self.repository,
                environ=environment, sdk_original_workflow_sha="c" * 40)
        self.assertEqual([validation], inspected["readyPlans"])
        self.assertEqual(result, inspected["result"])


class PriorRuntimeElectionTest(unittest.TestCase):
    def test_catalog_winner_does_not_use_prior_phase_shard(self):
        prior = {**adapter._identity_record(BINARY), "buildKey": "prior",
                 "receiptSha256": "prior-receipt", "objectSha256": "prior-object"}
        catalog = {**prior, "buildKey": "catalog", "receiptSha256": "catalog-receipt",
                   "objectSha256": "catalog-object", "state": "reused"}
        self.assertEqual({}, adapter._elected_prior_runtime_records([prior], (BINARY,), {BINARY: catalog}))
        retained = {**prior, "state": "retained"}
        self.assertEqual({BINARY: prior}, adapter._elected_prior_runtime_records(
            [prior], (BINARY,), {BINARY: retained}))


if __name__ == "__main__":
    unittest.main()
