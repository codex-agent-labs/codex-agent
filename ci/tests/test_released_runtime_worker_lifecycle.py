"""Real planned worker replay over synthetic signed products, never host evidence.

Only outer impact selection and catalog download/discovery are substituted.
Original plans, objects, release selection, Contract/native proofs, continuation,
and the public predecessor materializer all run their production implementations.
"""

from contextlib import ExitStack, contextmanager
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ci.tests import test_release_catalog_assembly as catalog_fixture
from ci.tests import test_product_contract_resume as contract_fixture
from ci.tests.test_contract_execution_closure import execution_closure_fixture
from ci.products.contract_attestation import build_contract_attestation, capture_contract_execution_closure
from ci.products.plan import plan_phase
from ci.products.selection import phase_git_inventory
from products.inventory import load_canonical_json, regular_file_inventory, snapshot_regular_tree, write_canonical_json
from products.receipt import verify_output_manifest_identity


adapter = contract_fixture.adapter
SDK = adapter.PhaseInstanceId("sdk", "python", "package", "desktop")
JVM = adapter.PhaseInstanceId("runtime", "jvm", "binary", "jvm")


class ReleasedRuntimeWorkerLifecycleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        catalog_fixture.ReleaseCatalogAssemblyTest.setUpClass()
        cls.addClassCleanup(catalog_fixture.ReleaseCatalogAssemblyTest.doClassCleanups)
        cls.catalog = catalog_fixture.ReleaseCatalogAssemblyTest
        temporary = tempfile.TemporaryDirectory(prefix="released-runtime-worker-")
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name).resolve()
        helper = contract_fixture.fixture.ProductReuseAdapterTest()
        helper.root = cls.root
        cls.repository, _, _ = helper.contract_repository()
        versions = cls.repository / "gradle/release/versions"
        (versions / "runtime.txt").write_text("0.2.8\n")
        (versions / "sdk.txt").write_text("0.2.9\n")
        (versions.parent / "sdk-default-runtime.txt").write_text("0.2.7\n")
        source = cls.repository / "codex-agent-bindings/python/pyproject.toml"
        source.parent.mkdir(parents=True)
        source.write_text('[project]\nname = "synthetic-sdk-worker-input"\nversion = "0.2.9"\n')
        runtime_source = cls.repository / "codex-agent-runtime-desktop/src/jvmMain/kotlin/Fixture.kt"
        runtime_source.parent.mkdir(parents=True)
        runtime_source.write_text("package synthetic\n// Current Runtime source inventory, not compiled evidence.\n")
        keyring = cls.repository / "gradle/release/product-signing-keys.json"
        keyring.write_bytes(cls.catalog.keyring.read_bytes())
        keys = cls.repository / "gradle/release/keys"
        snapshot_regular_tree(cls.catalog.keys, keys)

        def git(*arguments):
            return subprocess.run(["git", *arguments], cwd=cls.repository, check=True,
                                  capture_output=True, text=True).stdout.strip()

        git("add", "-A")
        git("commit", "-qm", "synthetic newer Runtime and independently pinned SDK default")
        cls.commit, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
        cls.plan = {**contract_fixture.fixture.impact_plan(changed=[source.relative_to(cls.repository).as_posix()]),
                    "headCommit": cls.commit, "validationCommit": cls.commit, "validationTree": tree}
        cls.plan_path = cls.repository / "impact-plan.json"
        write_canonical_json(cls.plan_path, cls.plan)
        cls.environment = {"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"}
        cls.producer = adapter._consumer(cls.plan, cls.environment)["producer"]
        current_versions = adapter._versions(cls.repository, cls.commit)

        def original_plan(instance, **arguments):
            identity = adapter.PhaseInstanceId(instance.product, instance.component, instance.phase, instance.target)
            authorities, unavailable = adapter._authorities(cls.repository, cls.commit, (identity,))
            if authorities is None:
                raise AssertionError(unavailable)
            authority = authorities[0]
            arguments.update(inventory=phase_git_inventory(cls.repository, cls.commit, instance), versions=current_versions,
                toolchain_profile_digest=authority["toolchainProfileDigest"], flags_digest=authority["flagsDigest"],
                output_schema_version=authority["outputSchemaVersion"])
            return plan_phase(instance, **arguments)

        # Same canonical Contract fixture content, but freshly planned original
        # receipts for this candidate. Historical catalog receipts are untouched.
        cls.contract_source = cls.repository / "build/original-contract"
        payload, cls.contract_receipts, execution = execution_closure_fixture(
            cls.contract_source, context="current-sdk-consumer", producer=cls.producer, plan_factory=original_plan)
        closure = cls.repository / "build/original-contract-closure"
        capture_contract_execution_closure(payload, cls.contract_receipts, execution, closure)
        cls.handoff = cls.repository / "build/current-contract-handoff"
        context = cls.catalog.source.context
        build_contract_attestation(payload, cls.contract_receipts["metadata"],
            {**context["signing"], "trustDomain": "release"}, context["private_key"], context["public_key"],
            cls.handoff, execution_closure=closure, keyring=keyring, keys_directory=keys, complete_handoff=True)

        buffer = io.BytesIO()
        for_inventory = regular_file_inventory(cls.catalog.layout, allow_empty=True)
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for row in for_inventory:
                archive.writestr(row["relativePath"], (cls.catalog.layout / row["relativePath"]).read_bytes())

        def downloaded_catalog(plan, destination, trust, *_arguments):
            # Only official transport/discovery is a seam. The production catalog
            # importer still verifies the actual index, object and complete carrier.
            with patch.object(adapter, "download_artifact", return_value=buffer.getvalue()):
                return [adapter._materialize_catalog("promoted-main", {"id": 991}, "synthetic-token",
                    destination, cls.producer["repository"], cls.producer["pullRequest"], trust)]

        cls.downloaded_catalog = staticmethod(downloaded_catalog)
        cls.discovery = cls.repository / "build/product-reuse"
        with cls.control_seams(), patch.object(adapter, "_discover_catalogs", side_effect=downloaded_catalog):
            adapter.discover(cls.plan_path, cls.discovery, cls.root / "discovery-output",
                             repository_root=cls.repository, environ=cls.environment)
            state = cls.discovery
            for phase in ("binary", "package", "validation", "metadata"):
                elected = load_canonical_json(state / f"phase-plans/contract-contract-{phase}-common.json")
                shard = cls.repository / f"build/current-contract-shards/{phase}"
                contract_fixture.fixture.finalize_phase_object(stage_root=cls.contract_source / f"{phase}-stage",
                    phase_plan=elected, producer=cls.producer, product_version="0.2.0", trust_domain="development",
                    destination=shard)
                identity = adapter.PhaseInstanceId("contract", "contract", phase, "common")
                verified = adapter.verify_phase_shard(shard, identity)
                if verified["receiptBytes"] != cls.contract_receipts[phase].read_bytes():
                    raise AssertionError("Original Contract receipt differs from actual elected plan")
                advanced = cls.repository / f"build/after-contract-{phase}"
                result = adapter.advance_contract(cls.plan_path, cls.discovery,
                    None if state == cls.discovery else state, [shard], advanced, cls.root / f"output-{phase}",
                    repository_root=cls.repository, environ=cls.environment)
                state = advanced
            if result["fullReuse"] is not True:
                raise AssertionError("Actual Contract continuation did not complete")
            cls.resumed = cls.repository / "build/resumed-sdk"
            adapter.resume_products(cls.plan_path, cls.discovery, state, cls.handoff, cls.resumed,
                cls.root / "resume-output", repository_root=cls.repository, environ=cls.environment)
        cls.ready = load_canonical_json(cls.resumed / "phase-plans/sdk-python-package-desktop.json")
        cls.immutable = {path: regular_file_inventory(path, allow_empty=True)
                         for path in (cls.catalog.layout, cls.catalog.carrier, cls.contract_source, cls.discovery, cls.resumed,
                                      cls.handoff, cls.repository / "build/current-contract-shards")}

    @classmethod
    def control_seams(cls, requested=(SDK,)):
        stack = ExitStack()
        stack.enter_context(patch.object(adapter, "_validate_plan", return_value=cls.plan))
        stack.enter_context(patch.object(adapter, "_requested", return_value=tuple(sorted(requested))))
        stack.enter_context(patch("reuse.api_request", side_effect=AssertionError("Unexpected real HTTP")))
        return stack

    def tearDown(self):
        for path, inventory in self.immutable.items():
            self.assertEqual(inventory, regular_file_inventory(path, allow_empty=True), str(path))

    @contextmanager
    def simultaneous_discovery(self, root):
        # The decoder requires its original canonical artifact root. Preserve
        # the first synthetic control tree unchanged instead of editing requests.
        root.mkdir(parents=True)
        saved = root / "saved-sdk-only-discovery"
        self.discovery.rename(saved)
        try:
            yield
        finally:
            if self.discovery.exists():
                self.discovery.rename(root / "second-discovery")
            saved.rename(self.discovery)

    def test_real_replay_materializes_original_released_runtime_and_current_contract(self):
        result = load_canonical_json(self.resumed / "reuse-wave-result.json")
        self.assertEqual([], result["matrices"]["runtime"])
        self.assertEqual(1, len(result["matrices"]["sdk"]))
        self.assertEqual(self.ready["buildKey"], result["matrices"]["sdk"][0]["buildKey"])
        request = load_canonical_json(self.resumed / "reuse-wave-request.json")
        self.assertEqual("released-default", request["sdkRuntimeSource"])
        self.assertEqual("0.2.8", request["versions"]["runtime-release"])
        destination = self.repository / "build/materialized-sdk"
        with self.control_seams():
            actual = adapter.materialize_product_predecessors(self.plan_path, self.resumed, self.resumed,
                SDK, destination, expected_build_key=self.ready["buildKey"],
                repository_root=self.repository, environ=self.environment)
        self.assertEqual(self.ready, actual)
        expected = set(adapter._dependency_closure((SDK,))) - {SDK}
        self.assertEqual({"phase-plan.json", "producer.json", *("-".join(adapter._identity_record(i).values()) for i in expected)},
                         {path.name for path in destination.iterdir()})
        for identity in expected:
            directory = destination / "-".join(adapter._identity_record(identity).values())
            receipt = load_canonical_json(directory / "phase-receipt.json")
            if identity.product == "contract":
                raw = self.contract_receipts[identity.phase].read_bytes()
                original_stage = self.contract_source / f"{identity.phase}-stage"
            else:
                original = self.catalog.carrier / "selected-inputs/predecessors" / directory.name
                raw = (original / "phase-receipt.json").read_bytes()
                original_stage = original / "stage"
                self.assertEqual("0.2.7", receipt["productVersion"])
            self.assertEqual(raw, (directory / "phase-receipt.json").read_bytes())
            self.assertEqual(regular_file_inventory(original_stage), regular_file_inventory(directory / "stage"))
            manifest = verify_output_manifest_identity(directory / "stage", identity.product, identity.component,
                identity.phase, identity.target, receipt["productVersion"])
            self.assertEqual(receipt["outputs"], manifest["outputs"])
        self.assertFalse(list(self.repository.glob("codex-agent-sdk-runtime-inputs-*")))

    def test_wrong_elected_key_cannot_publish_even_with_valid_released_runtime(self):
        destination = self.repository / "build/wrong-sdk-key"
        with self.control_seams(), self.assertRaisesRegex(ValueError, "not ready"):
            adapter.materialize_product_predecessors(self.plan_path, self.resumed, self.resumed,
                SDK, destination, expected_build_key="sha256:" + "0" * 64,
                repository_root=self.repository, environ=self.environment)
        self.assertFalse(destination.exists())
        self.assertFalse(list(self.repository.glob("codex-agent-sdk-runtime-inputs-*")))

    def test_simultaneous_current_jvm_and_sdk_keep_distinct_runtime_dependencies(self):
        # A second controller history imports the SAME existing Contract shards.
        # No original product receipt, object, handoff or catalog is regenerated.
        root = self.repository / "build/simultaneous"
        discovery, resumed = self.discovery, root / "resumed"
        requested = (SDK, JVM)
        with self.simultaneous_discovery(root), self.control_seams(requested), \
                patch.object(adapter, "_discover_catalogs", side_effect=self.downloaded_catalog):
            adapter.discover(self.plan_path, discovery, self.root / "simultaneous-discovery-output",
                repository_root=self.repository, environ=self.environment)
            state = discovery
            for phase in ("binary", "package", "validation", "metadata"):
                elected = load_canonical_json(state / f"phase-plans/contract-contract-{phase}-common.json")
                shard = self.repository / f"build/current-contract-shards/{phase}"
                identity = adapter.PhaseInstanceId("contract", "contract", phase, "common")
                original = adapter.verify_phase_shard(shard, identity)
                self.assertEqual(original["buildKey"], elected["buildKey"])
                self.assertEqual(self.contract_receipts[phase].read_bytes(), original["receiptBytes"])
                advanced = root / f"after-contract-{phase}"
                result = adapter.advance_contract(self.plan_path, discovery,
                    None if state == discovery else state, [shard], advanced, self.root / f"simultaneous-{phase}-output",
                    repository_root=self.repository, environ=self.environment)
                state = advanced
            self.assertTrue(result["fullReuse"])
            adapter.resume_products(self.plan_path, discovery, state, self.handoff, resumed,
                self.root / "simultaneous-resume-output", repository_root=self.repository, environ=self.environment)
            result = load_canonical_json(resumed / "reuse-wave-result.json")
            jvm = load_canonical_json(resumed / "phase-plans/runtime-jvm-binary-jvm.json")
            sdk = load_canonical_json(resumed / "phase-plans/sdk-python-package-desktop.json")
            self.assertEqual(self.ready, sdk)
            self.assertEqual([jvm["buildKey"]], [record["buildKey"] for record in result["matrices"]["runtime"]])
            self.assertEqual([sdk["buildKey"]], [record["buildKey"] for record in result["matrices"]["sdk"]])
            self.assertEqual(adapter._identity_record(JVM), {name: jvm[name] for name in adapter._IDENTITY_KEYS})
            self.assertIn("codex-agent-runtime-desktop/src/jvmMain/kotlin/Fixture.kt",
                          {record["relativePath"] for record in jvm["inputs"]["inventory"]})
            request = load_canonical_json(resumed / "reuse-wave-request.json")
            self.assertEqual("0.2.8", request["versions"]["runtime-release"])
            self.assertEqual("released-default", request["sdkRuntimeSource"])
            for identity, ready in ((JVM, jvm), (SDK, sdk)):
                destination = root / f"materialized-{identity.component}"
                actual = adapter.materialize_product_predecessors(self.plan_path, resumed, resumed,
                    identity, destination, expected_build_key=ready["buildKey"],
                    repository_root=self.repository, environ=self.environment)
                self.assertEqual(ready, actual)
                dependencies = set(adapter._dependency_closure((identity,))) - {identity}
                if identity == JVM:
                    self.assertEqual({"contract"}, {dependency.product for dependency in dependencies})
                else:
                    self.assertIn(adapter.PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate"), dependencies)
                self.assertEqual({"phase-plan.json", "producer.json", *("-".join(adapter._identity_record(i).values()) for i in dependencies)},
                                 {path.name for path in destination.iterdir()})
                for dependency in dependencies:
                    directory = destination / "-".join(adapter._identity_record(dependency).values())
                    receipt = load_canonical_json(directory / "phase-receipt.json")
                    if dependency.product == "contract":
                        raw = self.contract_receipts[dependency.phase].read_bytes()
                        stage = self.contract_source / f"{dependency.phase}-stage"
                    else:
                        original = self.catalog.carrier / "selected-inputs/predecessors" / directory.name
                        raw, stage = (original / "phase-receipt.json").read_bytes(), original / "stage"
                        self.assertEqual("0.2.7", receipt["productVersion"])
                    self.assertEqual(raw, (directory / "phase-receipt.json").read_bytes())
                    self.assertEqual(regular_file_inventory(stage), regular_file_inventory(directory / "stage"))
        self.assertFalse(list(self.repository.glob("codex-agent-sdk-runtime-inputs-*")))


if __name__ == "__main__":
    unittest.main()
