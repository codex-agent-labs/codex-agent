"""Real original Git/planner replay; compiler, S858 and tooling boundaries are simulated."""

from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import (
    canonical_json_bytes, git_product_versions, load_canonical_json_bytes, regular_file_inventory, sha256_bytes,
)
from ci.products.plan import NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST, plan_phase
from ci.products.receipt import compute_build_key
from ci.products.registry import NATIVE_TARGETS, PhaseInstanceId
from ci.products.sdk_native_metadata import verify_sdk_native_metadata_content
from ci.products.sdk_native_metadata_admission import verify_sdk_native_metadata_admission
from ci.products.sdk_validation import verify_sdk_validation_projection
from ci.products.selection import phase_git_inventory
from ci.tests.product_chain_support import write_receipt
from ci.tests import test_sdk_native_metadata as native_fixture


_RUN = subprocess.run
_TEMPORARY = tempfile.TemporaryDirectory


class SdkNativeMetadataAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.support = native_fixture.SdkNativeMetadataTest()
        self.support.setUp()
        self.addCleanup(self.support.doCleanups)
        self.support.fixture()
        self.root = self.support.root
        self.repository = self.root / "repository"
        self.repository.mkdir()
        for name in ("contract", "runtime", "sdk"):
            path = self.repository / f"gradle/release/versions/{name}.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"0.2.0\n")
        self.source = self.repository / "gradle/build-logic/src/main/kotlin/CrossLanguageNativeWrapperValidationEvidence.kt"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b"// synthetic original metadata input\n")
        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic SDK Replay")
        self.git("config", "user.email", "sdk-replay@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "original metadata policy")
        self.commit = self.git("rev-parse", "HEAD").strip()
        self.tree = self.git("rev-parse", "HEAD^{tree}").strip()
        self.support.args["repository"] = self.repository
        self.support.args["policy_revision"] = self.commit
        self.instance = PhaseInstanceId("sdk", "python", "metadata", "desktop")
        self.proofs = self.original_proofs()
        self.upstream = [self.support.package] + [load_canonical_json_bytes(
            (self.support.args["validation_receipts"] / f"{target}.json").read_bytes()) for target in sorted(NATIVE_TARGETS)]
        self.plan = plan_phase(self.instance, inventory=phase_git_inventory(self.repository, self.commit, self.instance),
            versions=git_product_versions(self.repository, self.commit), upstream_receipts=self.upstream,
            toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST, flags_digest=NOT_APPLICABLE_FLAGS_DIGEST,
            output_schema_version=1, sdk_validation_projections=self.proofs)
        self.assertTrue(self.plan["inputs"]["inventory"])
        self.write_metadata(self.plan)
        self.after_content = lambda arguments: None

    def git(self, *arguments):
        return _RUN(["git", *arguments], cwd=self.repository, check=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout

    def original_proofs(self):
        def execute(command, **kwargs):
            self.assertEqual("write-native-wrapper-validation-content", command[3])
            fields = dict(zip(command[4::2], command[5::2]))
            Path(fields["--content-output"]).write_bytes(
                (self.root / "host-contents" / f"{fields['--target']}.json").read_bytes())
            return subprocess.CompletedProcess(command, 0)
        arguments = self.support.args
        proofs = []
        with patch("ci.products.tooling.verified_tooling_capture", self.support.tooling), \
                patch("ci.products.sdk_validation.subprocess.run", side_effect=execute):
            for target in sorted(NATIVE_TARGETS):
                proofs.append(verify_sdk_validation_projection(
                    **{name: arguments[name] for name in ("repository", "component", "package_stage", "package_receipt",
                        "compatibility_request", "runtime_stages", "staged_sdks", "tooling_evidence", "tooling_public_key",
                        "java_executable", "policy_revision", "required_trust_domain")}, target=target,
                    validation_stage=arguments["validation_stages"] / target,
                    validation_receipt=arguments["validation_receipts"] / f"{target}.json"))
        return tuple(proofs)

    def write_metadata(self, plan, *, producer=None):
        current = load_canonical_json_bytes(self.support.args["metadata_receipt"].read_bytes())
        context = {"producer": {**self.support.context["producer"], "commit": self.commit, "tree": self.tree,
                                **({} if producer is None else producer)},
                   "plan_factory": lambda _identity, _upstream: plan}
        return write_receipt(self.support.args["metadata_receipt"], product="sdk", component="python",
            phase="metadata", target="desktop", version="0.2.0", version_identity="0.2.0",
            outputs=current["outputs"], upstream=self.support.upstream, context=context)

    def verify(self, *, proofs=None, **overrides):
        def content(**arguments):
            result = verify_sdk_native_metadata_content(**arguments)
            self.after_content(arguments)
            return result
        def execute(command, **kwargs):
            # Original Git and planner work are real. Only the declared JVM
            # matcher process is simulated; no caller success callback exists.
            if command[0] == "git":
                return _RUN(command, **kwargs)
            return self.support.execute(command, **kwargs)
        with patch("ci.products.sdk_native_metadata_admission.verify_sdk_native_metadata_content", side_effect=content), \
                patch("ci.products.sdk_native_metadata.verified_tooling_capture", self.support.tooling), \
                patch("ci.products.sdk_native_metadata.stage_sdk_inputs", self.support.capture_inputs), \
                patch("ci.products.sdk_native_metadata._request_inventory", side_effect=lambda _: {
                    self.support.request_source: sha256_bytes(self.support.request_source.read_bytes())}), \
                patch("ci.products.sdk_native_metadata.subprocess.run", side_effect=execute):
            return verify_sdk_native_metadata_admission(**{**self.support.args, **overrides},
                sdk_validation_projections=self.proofs if proofs is None else proofs)

    def test_original_git_and_full_planner_replay_preserve_exact_receipt_and_sources(self):
        before = regular_file_inventory(self.root)
        def private_receipts(arguments):
            for name in ("metadata_receipt", "package_receipt"):
                self.assertNotEqual(self.support.args[name], arguments[name])
                self.assertEqual(self.support.args[name].read_bytes(), arguments[name].read_bytes())
            self.assertEqual(regular_file_inventory(self.support.args["validation_receipts"]),
                             regular_file_inventory(arguments["validation_receipts"]))
        self.after_content = private_receipts
        with patch.dict(sys.modules, {"product_reuse": None, "ci.product_reuse": None}):
            receipt, original = self.verify()
        self.assertEqual(original, self.support.args["metadata_receipt"].read_bytes())
        self.assertEqual(self.plan["inputs"], receipt["inputs"])
        self.assertEqual(self.plan["buildKey"], receipt["buildKey"])
        self.assertEqual(before, regular_file_inventory(self.root))
        self.assertEqual(1, len(self.support.calls))

    def test_same_receipt_replays_original_commit_after_checkout_moves(self):
        self.source.write_bytes(b"// changed current metadata input\n")
        self.git("add", ".")
        self.git("commit", "-qm", "later current checkout")
        self.assertNotEqual(self.commit, self.git("rev-parse", "HEAD").strip())
        receipt, _ = self.verify()
        self.assertEqual(self.commit, receipt["producer"]["commit"])
        self.assertEqual(self.plan["buildKey"], receipt["buildKey"])

    def test_self_consistent_but_invented_source_inventory_and_authorities_reject(self):
        original = self.support.args["metadata_receipt"].read_bytes()
        for field in ("inventory", "toolchainProfileDigest", "flagsDigest"):
            changed = deepcopy(self.plan)
            if field == "inventory":
                changed["inputs"][field][0]["sha256"] = "sha256:" + "f" * 64
                changed["inputs"]["phaseInputDigest"] = sha256_bytes(canonical_json_bytes(changed["inputs"][field]))
            else:
                changed["inputs"][field] = "sha256:" + "f" * 64
            changed["buildKey"] = compute_build_key(product="sdk", component="python", phase="metadata",
                target="desktop", inputs=changed["inputs"])
            self.write_metadata(changed)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "original authenticated plan"):
                self.verify()
            self.support.args["metadata_receipt"].write_bytes(original)
        self.assertEqual([], self.support.calls)

    def test_wrong_original_tree_missing_commit_and_original_version_reject(self):
        original = self.support.args["metadata_receipt"].read_bytes()
        for producer in ({"tree": "f" * 40}, {"commit": "f" * 40}):
            self.write_metadata(self.plan, producer=producer)
            with self.assertRaisesRegex(ValueError, "original (commit/tree|source commit)"):
                self.verify()
            self.support.args["metadata_receipt"].write_bytes(original)
        version = self.repository / "gradle/release/versions/sdk.txt"
        version.write_bytes(b"0.2.1\n")
        self.git("add", ".")
        self.git("commit", "-qm", "different producer version")
        self.write_metadata(self.plan, producer={"commit": self.git("rev-parse", "HEAD").strip(),
                                                "tree": self.git("rev-parse", "HEAD^{tree}").strip()})
        with self.assertRaisesRegex(ValueError, "original source version"):
            self.verify()
        self.assertEqual([], self.support.calls)

    def test_missing_reordered_or_caller_fabricated_projections_are_rejected(self):
        for proofs in ((), self.proofs[:-1], tuple(reversed(self.proofs)), (True,) * 5):
            with self.subTest(proofs=len(proofs)), self.assertRaises(ValueError):
                self.verify(proofs=proofs)
        self.assertEqual([], self.support.calls)

    def test_original_and_private_receipt_mutations_are_rejected(self):
        original = self.support.args["metadata_receipt"].read_bytes()
        for private in (False, True):
            def mutate(arguments):
                path = arguments["metadata_receipt"] if private else self.support.args["metadata_receipt"]
                self.assertTrue(path.is_file())
                path.write_bytes(path.read_bytes() + b"changed\n")
            self.after_content = mutate
            with self.subTest(private=private), self.assertRaisesRegex(ValueError, "changed"):
                self.verify()
            self.support.args["metadata_receipt"].write_bytes(original)

    def test_private_snapshot_overlap_is_rejected_without_changing_inputs(self):
        before = regular_file_inventory(self.root)
        with patch("ci.products.sdk_native_metadata_admission.tempfile.TemporaryDirectory",
                   side_effect=lambda **kwargs: _TEMPORARY(dir=self.support.args["runtime_stages"], **kwargs)), \
                self.assertRaisesRegex(ValueError, "overlaps"):
            self.verify()
        self.assertEqual(before, regular_file_inventory(self.root))
        self.assertEqual([], self.support.calls)


if __name__ == "__main__":
    unittest.main()
