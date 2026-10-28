"""Actual resumed phase planning over synthetic bytes, not JVM compilation."""

import shutil
import unittest

from ci.tests import test_product_contract_resume as resume_fixture
from ci.tests.test_runtime_evidence import RuntimeEvidenceFixture, write_zip
from ci.products.inventory import load_canonical_json, regular_file_inventory
from ci.products.receipt import write_output_manifest


adapter = resume_fixture.adapter
JVM = resume_fixture.JVM


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class RuntimeResumedPhaseTest(unittest.TestCase):
    # Reuse fixture construction, never inherit or collect its other test cases.
    setUpClass = classmethod(resume_fixture.ContractProductResumeTest.setUpClass.__func__)
    control_seams = classmethod(resume_fixture.ContractProductResumeTest.control_seams.__func__)
    setUp = resume_fixture.ContractProductResumeTest.setUp
    tearDown = resume_fixture.ContractProductResumeTest.tearDown
    resume = resume_fixture.ContractProductResumeTest.resume

    def binary_shard(self, resumed, name, *, producer=None, version="0.2.0"):
        ready = load_canonical_json(resumed / "phase-plans/runtime-jvm-binary-jvm.json")
        evidence = RuntimeEvidenceFixture(self.scratch / f"{name}-runner-fixture")
        stage = self.scratch / f"{name}-stage"
        jar = stage / "outputs/adapter/codex-agent-runtime-desktop-jvm-0.2.0.jar"
        jar.parent.mkdir(parents=True)
        # Real archive shape, deliberately not compiled class bytes. This test
        # exercises receipt/phase admission only, not product execution validity.
        write_zip(jar, {"META-INF/MANIFEST.MF": b"Manifest-Version: 1.0\n\n",
                        "fixture/SyntheticRuntime.class": b"synthetic JVM binary, not compiler output\n"})
        runner = stage / "outputs/validation-runner" / evidence.jvm_runner.name
        runner.parent.mkdir(parents=True)
        shutil.copyfile(evidence.jvm_runner, runner)
        write_output_manifest(stage, "runtime", "jvm", "binary", "jvm", version, {
            "adapter": "outputs/adapter", "validation-runner": "outputs/validation-runner",
        })
        shard = self.scratch / f"{name}-shard"
        resume_fixture.fixture.finalize_phase_object(
            stage_root=stage, phase_plan=ready,
            producer=self.producer if producer is None else producer,
            product_version=version, trust_domain="development", destination=shard,
        )
        descriptor = adapter.verify_phase_shard(shard, JVM)
        self.assertEqual(ready["buildKey"], descriptor["buildKey"])
        self.assertEqual({"adapter", "validation-runner"},
                         {output["kind"] for output in descriptor["receipt"]["outputs"]})
        return shard, descriptor

    def advance(self, resumed, shard, destination):
        with self.control_seams():
            return adapter.advance_products(
                self.plan_path, resumed, None, [shard], destination,
                self.scratch / f"{destination.name}-github-output",
                repository_root=self.repository, environ=self.environment,
            )

    def test_actual_resumed_jvm_binary_shard_completes_only_its_requested_phase(self):
        resumed = self.resume()
        shard, descriptor = self.binary_shard(resumed, "valid")
        resumed_before = regular_file_inventory(resumed)
        shard_before = regular_file_inventory(shard)
        hidden = []
        destination = self.scratch / "advanced"
        try:
            # All authority must come from the retained resumed handoff, not
            # accidental access to the previous discovery/signing locations.
            for source in (self.discovery, self.state, self.handoff):
                target = source.with_name(source.name + "-hidden")
                source.rename(target)
                hidden.append((source, target))
            result = self.advance(resumed, shard, destination)
        finally:
            for source, target in reversed(hidden):
                target.rename(source)
        self.assertTrue(result["fullReuse"])
        self.assertEqual({"contract": [], "runtime": [], "sdk": []}, result["matrices"])
        identities = tuple(sorted(adapter._identity(phase) for phase in result["phases"]))
        self.assertEqual({JVM, *(adapter.PhaseInstanceId("contract", "contract", phase, "common")
                                for phase in self.receipts)}, set(identities))
        carrier = adapter.verify_carrier(destination / "carrier", identities,
                                         adapter._consumer(self.plan, self.environment))
        by_identity = {adapter._identity(record): record for record in carrier["objects"]}
        for phase, raw in self.original_bytes.items():
            identity = adapter.PhaseInstanceId("contract", "contract", phase, "common")
            record = by_identity[identity]
            original = adapter.verify_object(
                destination / "carrier" / adapter.object_relative_path(record["buildKey"], record["receiptSha256"]),
                build_key=record["buildKey"], receipt_sha256=record["receiptSha256"],
                object_sha256=record["objectSha256"],
            )
            self.assertEqual(raw, original["receiptBytes"])
        selected = by_identity[JVM]
        self.assertEqual(descriptor["receiptSha256"], selected["receiptSha256"])
        self.assertEqual(descriptor["objectSha256"], selected["objectSha256"])
        self.assertEqual(resumed_before, regular_file_inventory(resumed))
        self.assertEqual(shard_before, regular_file_inventory(shard))
        # Completion here is exactly Contract4 + JVM binary, not JVM package,
        # host validation, metadata, other hosts, or SDK product acceptance.

    def test_self_consistent_runtime_shards_with_wrong_producer_or_version_are_rejected(self):
        resumed = self.resume()
        before = regular_file_inventory(resumed)
        cases = (("producer", {**self.producer, "runAttempt": self.producer["runAttempt"] + 1}, "0.2.0"),
                 ("version", self.producer, "0.2.1"))
        for name, producer, version in cases:
            with self.subTest(mismatch=name):
                shard, _ = self.binary_shard(resumed, name, producer=producer, version=version)
                original = regular_file_inventory(shard)
                destination = self.scratch / f"rejected-{name}"
                with self.assertRaisesRegex(ValueError, "elected plan and producer"):
                    self.advance(resumed, shard, destination)
                self.assertFalse(destination.exists())
                self.assertEqual(original, regular_file_inventory(shard))
                self.assertEqual(before, regular_file_inventory(resumed))
