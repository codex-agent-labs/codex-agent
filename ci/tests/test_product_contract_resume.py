"""Real local K4-to-JVM planning with synthetic products, not Runtime execution."""

from contextlib import ExitStack
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from ci.products.contract_attestation import build_contract_attestation, capture_contract_execution_closure
from ci.products.inventory import (
    load_canonical_json, publish_regular_tree as actual_publish_regular_tree,
    regular_file_inventory, sha256_file, write_canonical_json,
)
from ci.products.plan import plan_phase
from ci.products.selection import phase_git_inventory
from ci.products.signatures import generate_development_key, sign_manifest
from ci.tests.test_contract_execution_closure import execution_closure_fixture
from ci.tests import test_product_reuse_adapter as fixture


adapter = fixture.product_reuse
JVM = adapter.PhaseInstanceId("runtime", "jvm", "binary", "jvm")


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class ContractProductResumeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="contract-products-resume-")
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name).resolve()
        helper = fixture.ProductReuseAdapterTest()
        helper.root = cls.root
        cls.repository, _, _ = helper.contract_repository()
        private, public, development = generate_development_key(cls.root / "signing")
        signing = {**development, "trustDomain": "release", "keyId": "fixture-release"}
        keys = cls.repository / "gradle/release/keys"
        keys.mkdir(parents=True)
        shutil.copyfile(public, keys / "fixture-release.pub")
        keyring = cls.repository / "gradle/release/product-signing-keys.json"
        write_canonical_json(keyring, {
            "schemaVersion": 1, "algorithm": signing["algorithm"], "namespace": signing["namespace"],
            "trustDomain": "release", "activeKey": {
                "keyId": signing["keyId"], "fingerprint": signing["fingerprint"],
            }, "retiredKeys": [],
        })
        def git(*arguments):
            return subprocess.run(["git", *arguments], cwd=cls.repository, check=True,
                                  capture_output=True, text=True).stdout.strip()
        git("add", "gradle/release")
        git("commit", "-qm", "synthetic public release policy")
        cls.commit, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
        cls.plan = {**fixture.impact_plan(changed=["codex-agent-runtime-desktop/src/jvmMain/Fixture.kt"]),
                    "headCommit": cls.commit, "validationCommit": cls.commit, "validationTree": tree}
        cls.plan_path = cls.repository / "impact-plan.json"
        write_canonical_json(cls.plan_path, cls.plan)
        cls.environment = {"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"}
        cls.producer = adapter._consumer(cls.plan, cls.environment)["producer"]

        def original_plan(instance, **arguments):
            outer = adapter.PhaseInstanceId(instance.product, instance.component, instance.phase, instance.target)
            authorities, unavailable = adapter._authorities(cls.repository, cls.commit, (outer,))
            if authorities is None:
                raise AssertionError(unavailable)
            authority = authorities[0]
            arguments.update(inventory=phase_git_inventory(cls.repository, cls.commit, instance), versions=fixture.VERSIONS,
                             toolchain_profile_digest=authority["toolchainProfileDigest"],
                             flags_digest=authority["flagsDigest"], output_schema_version=authority["outputSchemaVersion"])
            return plan_phase(instance, **arguments)

        cls.original = cls.repository / "build/original-contract"
        payload, cls.receipts, raw = execution_closure_fixture(
            cls.original, producer=cls.producer, plan_factory=original_plan)
        closure = cls.repository / "build/original-closure"
        capture_contract_execution_closure(payload, cls.receipts, raw, closure)
        cls.handoff = cls.repository / "build/release-handoff"
        build_contract_attestation(payload, cls.receipts["metadata"], signing, private, public, cls.handoff,
                                   execution_closure=closure, keyring=keyring, keys_directory=keys,
                                   complete_handoff=True)

        def saved_unavailable_catalog(_plan, destination, *_args):
            producer = cls.producer
            # The signed original exists, but its object is unavailable: normal
            # lookup must miss and elect the actual Contract build sequence.
            entry = fixture.ProductReuseAdapterTest.product_index_entry({
                "receipt": load_canonical_json(cls.receipts["binary"]),
                "receiptSha256": sha256_file(cls.receipts["binary"]),
            })
            index = {
                "schemaVersion": 1, "repository": producer["repository"],
                "context": {"kind": "pull-request", **{field: producer[field] for field in
                            ("pullRequest", "commit", "tree", "runId", "runAttempt")}},
                "entries": [entry], "trustDomain": "development", "signing": development, "producer": producer,
            }
            manifest = destination / "catalog/product-index.json"
            write_canonical_json(manifest, index)
            signature = sign_manifest(manifest, private, development)
            retained_key = manifest.parent / "public-key.pub"
            shutil.copyfile(public, retained_key)
            request = {
                "manifest": manifest.relative_to(destination).as_posix(),
                "signature": signature.relative_to(destination).as_posix(),
                "publicKey": retained_key.relative_to(destination).as_posix(),
                "keyring": None, "keysDirectory": None, "contractAttestation": None,
                "contractAttestationSignature": None, "contractPublicKey": None,
                "objects": [{"buildKey": entry["buildKey"], "objectPath": None}],
            }
            return [adapter.Catalog("same-pr", index, sha256_file(manifest), request, {})]

        cls.discovery = cls.repository / "build/product-reuse"
        with cls.control_seams(), mock.patch.object(adapter, "_discover_catalogs", side_effect=saved_unavailable_catalog):
            adapter.discover(cls.plan_path, cls.discovery, cls.root / "discovery-output",
                             repository_root=cls.repository, environ=cls.environment)
            state = cls.discovery
            for phase in ("binary", "package", "validation", "metadata"):
                elected = load_canonical_json(state / f"phase-plans/contract-contract-{phase}-common.json")
                shard = cls.repository / f"build/original-shards/{phase}"
                fixture.finalize_phase_object(
                    stage_root=cls.original / f"{phase}-stage", phase_plan=elected,
                    producer=cls.producer, product_version="0.2.0", trust_domain="development", destination=shard)
                descriptor = adapter.verify_phase_shard(shard, adapter.PhaseInstanceId("contract", "contract", phase, "common"))
                if descriptor["receiptBytes"] != cls.receipts[phase].read_bytes():
                    raise AssertionError("Original fixture receipt differs from real elected phase plan")
                next_state = cls.repository / f"build/contract-after-{phase}"
                result = adapter.advance_contract(
                    cls.plan_path, cls.discovery, None if state == cls.discovery else state, [shard],
                    next_state, cls.root / f"contract-{phase}-output",
                    repository_root=cls.repository, environ=cls.environment)
                state = next_state
            if result["fullReuse"] is not True:
                raise AssertionError("Actual four-phase Contract continuation did not complete")
        cls.state = state
        cls.original_bytes = {phase: path.read_bytes() for phase, path in cls.receipts.items()}
        cls.immutable = {path: regular_file_inventory(path, allow_empty=True)
                         for path in (cls.original, cls.discovery, cls.state, cls.handoff)}

    @classmethod
    def control_seams(cls):
        # Substitute only impact validation/selection. All inventories, authorities and plans are real.
        stack = ExitStack()
        stack.enter_context(mock.patch.object(adapter, "_validate_plan", return_value=cls.plan))
        stack.enter_context(mock.patch.object(adapter, "_requested", return_value=(JVM,)))
        return stack

    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp(prefix="resume-case-", dir=self.repository))
        self.addCleanup(shutil.rmtree, self.scratch)

    def tearDown(self):
        for path, inventory in self.immutable.items():
            self.assertEqual(inventory, regular_file_inventory(path, allow_empty=True), str(path))

    def resume(self, *, handoff=None, environ=None, destination=None):
        destination = self.scratch / "resumed" if destination is None else destination
        with self.control_seams():
            adapter.resume_products(self.plan_path, self.discovery, self.state,
                                    self.handoff if handoff is None else handoff, destination,
                                    self.scratch / "github-output", repository_root=self.repository,
                                    environ=self.environment if environ is None else environ)
        return destination

    def test_prior_attempt_contract_snapshot_preserves_originals_and_current_consumer(self):
        baseline = self.resume(destination=self.scratch / "baseline")
        current = {**self.environment, "GITHUB_RUN_ATTEMPT": "3"}
        resumed = self.resume(environ=current)
        self.assertEqual(adapter._consumer(self.plan, current)["producer"],
                         load_canonical_json(resumed / "producer.json"))
        self.assertEqual(load_canonical_json(baseline / "phase-plans/runtime-jvm-binary-jvm.json"),
                         load_canonical_json(resumed / "phase-plans/runtime-jvm-binary-jvm.json"))
        request = load_canonical_json(resumed / "reuse-wave-request.json")
        for record in request["availableObjects"]:
            original = adapter.verify_object(resumed / record["objectPath"], build_key=record["buildKey"],
                                             receipt_sha256=record["receiptSha256"], object_sha256=record["objectSha256"])
            self.assertEqual(self.original_bytes[record["phase"]], original["receiptBytes"])
            self.assertEqual(self.producer, original["receipt"]["producer"])

    def test_future_attempt_and_different_run_contract_snapshots_reject(self):
        for field, value in (("GITHUB_RUN_ATTEMPT", "1"), ("GITHUB_RUN_ID", "8")):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Contract.*consumer"):
                self.resume(environ={**self.environment, field: value},
                            destination=self.scratch / field)
            self.assertFalse((self.scratch / field).exists())

    def test_completed_original_contract_unlocks_real_runtime_plan_and_retains_signed_catalog(self):
        resumed = self.resume()
        request = load_canonical_json(resumed / "reuse-wave-request.json")
        result = load_canonical_json(resumed / "reuse-wave-result.json")
        self.assertFalse(result["fullReuse"])
        self.assertEqual([], result["matrices"]["contract"])
        self.assertEqual([], result["matrices"]["sdk"])
        self.assertEqual(1, len(result["matrices"]["runtime"]))
        ready = load_canonical_json(resumed / "phase-plans/runtime-jvm-binary-jvm.json")
        self.assertEqual(ready["buildKey"], result["matrices"]["runtime"][0]["buildKey"])
        self.assertEqual(adapter._identity_record(JVM), {field: ready[field] for field in adapter._IDENTITY_KEYS})
        self.assertEqual("release", request["contractEvidence"]["expectedTrustDomain"])
        self.assertEqual(4, len(request["availableObjects"]))
        for record in request["availableObjects"]:
            original = adapter.verify_object(resumed / record["objectPath"], build_key=record["buildKey"],
                                             receipt_sha256=record["receiptSha256"], object_sha256=record["objectSha256"])
            self.assertEqual(self.original_bytes[record["phase"]], original["receiptBytes"])
        for field, basename in (("manifest", "product-index.json"), ("signature", "product-index.sig"),
                                ("publicKey", "public-key.pub")):
            self.assertEqual((self.discovery / "catalog" / basename).read_bytes(),
                             (resumed / request["catalogs"]["samePr"][field]).read_bytes())

    def test_later_continuation_replays_captured_inputs_without_original_discovery_or_handoff(self):
        resumed = self.resume()
        hidden = []
        try:
            for source in (self.discovery, self.state, self.handoff):
                target = source.with_name(source.name + "-hidden")
                source.rename(target)
                hidden.append((source, target))
            with self.control_seams(), self.assertRaisesRegex(ValueError, "shards and failures do not exactly partition"):
                # A JVM build remains genuinely required; do not synthesize a success receipt.
                adapter.advance_products(self.plan_path, resumed, None, [], self.scratch / "advanced",
                                         self.scratch / "advance-output", repository_root=self.repository,
                                         environ=self.environment)
        finally:
            for source, target in reversed(hidden):
                target.rename(source)

    def test_changed_signed_handoff_rejects_before_runtime_plans_are_published(self):
        changed = self.scratch / "changed-handoff"
        shutil.copytree(self.handoff, changed)
        receipt = changed / "execution-closure/receipts/metadata.json"
        receipt.write_bytes(receipt.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self.resume(handoff=changed)
        self.assertFalse((self.scratch / "resumed").exists())

    def test_late_resume_control_mutation_cannot_publish(self):
        def mutate_during_copy(source, destination, **kwargs):
            if (Path(source) / "reuse-wave-result.json").exists():
                (Path(source) / "reuse-wave-result.json").write_bytes(b"changed during copy")
            actual_publish_regular_tree(source, destination, **kwargs)

        with mock.patch.object(adapter, "publish_regular_tree", side_effect=mutate_during_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.resume()
        self.assertFalse((self.scratch / "resumed").exists())


if __name__ == "__main__":
    unittest.main()
