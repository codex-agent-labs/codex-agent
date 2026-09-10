"""Source-binding tests; synthetic Git/CI fixtures are not hosted Apple proof."""

from argparse import Namespace
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ci import receipt as lane_receipt
from ci.products import contract_model
from ci.products.inventory import regular_file_inventory, sha256_bytes, write_canonical_json
from ci.products.sdk_apple_source import verify_sdk_apple_original_source
from ci.tests import test_ci as ci_fixture
from ci.tests import test_contract_projection as contract_fixture


class SdkAppleSourceImportTest(unittest.TestCase):
    def test_clean_package_and_script_namespace_imports(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        environment = {
            key: value for key, value in os.environ.items()
            if key not in {"PYTHONHOME", "PYTHONPATH"}
        }
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        commands = (
            [sys.executable, "-B", "-c", "import ci.products.sdk_apple_source"],
            [sys.executable, "-B", "-c",
             "import sys; sys.path.insert(0, 'ci'); import products.sdk_apple_source"],
        )
        for command in commands:
            with self.subTest(command=command[-1]):
                result = subprocess.run(
                    command, cwd=repository, env=environment,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                )
                self.assertEqual(0, result.returncode, result.stderr.decode(errors="replace"))


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class SdkAppleSourceTest(ci_fixture.GitFixture):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.root.resolve()
        self.contract_fixture = contract_fixture.ContractProjectionTest()
        self.contract_fixture.setUp()
        self.addCleanup(self.contract_fixture.doCleanups)
        self.projection = self.contract_fixture._verify()
        self.contract_bundle = self.contract_fixture.bundle
        self.contract_version = self.contract_fixture.manifest["contractVersion"]
        self.sdk_version = "0.2.0"

        self.git_sources = {
            "Package.swift": b"// synthetic original Swift package\n",
            "codex-agent-runtime-ios/native/provenance.json": b'{"synthetic":true}\n',
            "codex-agent-runtime-ios/apple/CompilerEvidence/CodexFailureSwiftConsumer.swift":
                b"// synthetic Swift consumer\n",
            "codex-agent-runtime-ios/apple/CompilerEvidence/CodexFailureObjectiveCConsumer.m":
                b"// synthetic Objective-C consumer\n",
            "gradle/release/versions/sdk.txt": (self.sdk_version + "\n").encode(),
            "gradle/release/versions/contract.txt": (self.contract_version + "\n").encode(),
        }
        for relative, contents in self.git_sources.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        self.git("add", ".")
        self.git("commit", "-qm", "Apple source fixture")
        _, self.plan, self.commit = self.make_plan(
            "ios-swift-auth-tests/source-binding.kt", force_full=True,
        )
        self.tree = self.git("rev-parse", f"{self.commit}^{{tree}}")

        self.distribution = self.root / "apple-distribution"
        self.execution = self.root / "apple-execution"
        self.lane = self.root / "apple-lane"
        self.distribution.mkdir()
        self.execution.mkdir()
        self.lane.mkdir()
        self.compatibility_bytes = b'{"sdkVersion":"0.2.0"}\n'
        (self.execution / "sdk-compatibility.json").write_bytes(self.compatibility_bytes)
        proof = {
            "candidateCommit": self.commit,
            "candidateTree": self.tree,
            "version": self.sdk_version,
        }
        write_canonical_json(self.distribution / "verified-distribution-proof.json", proof)

        source_map = {
            "source/Package.swift": "Package.swift",
            "source/native-provenance.json": "codex-agent-runtime-ios/native/provenance.json",
            "consumer/CodexFailureSwiftConsumer.swift":
                "codex-agent-runtime-ios/apple/CompilerEvidence/CodexFailureSwiftConsumer.swift",
            "consumer/CodexFailureObjectiveCConsumer.m":
                "codex-agent-runtime-ios/apple/CompilerEvidence/CodexFailureObjectiveCConsumer.m",
        }
        for destination, source in source_map.items():
            path = self.execution / destination
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.git_sources[source])
        with zipfile.ZipFile(self.contract_bundle) as archive:
            for name in ("canonical-api.json", "canonical-coverage.json"):
                path = self.execution / "canonical" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(f"evidence/{name}"))

        trees = {
            "compiler-raw/operation/stdout.bin":
                "payload/codex-agent-runtime-ios/build/apple-compiler-evidence-task/raw/operation/stdout.bin",
            "compiler-raw/operation/stderr.bin":
                "payload/codex-agent-runtime-ios/build/apple-compiler-evidence-task/raw/operation/stderr.bin",
            "xctest-raw/attempt-0/tests/stdout.bin":
                "payload/codex-agent-runtime-ios/build/swift-authentication-evidence-task/raw/attempt-0/tests/stdout.bin",
            "xctest-raw/attempt-0/tests/stderr.bin":
                "payload/codex-agent-runtime-ios/build/swift-authentication-evidence-task/raw/attempt-0/tests/stderr.bin",
            "xcresult/result.json":
                "payload/codex-agent-runtime-ios/build/swift-authentication-tests.xcresult/result.json",
        }
        for index, (execution_path, lane_path) in enumerate(trees.items()):
            contents = b"" if execution_path.endswith("stderr.bin") else f"raw-{index}\n".encode()
            for root, relative in ((self.execution, execution_path), (self.lane, lane_path)):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(contents)

        reports = {
            "reports/cross-language-api/apple/compiler-evidence.json":
                "payload/codex-agent-runtime-ios/build/reports/cross-language-api/apple/compiler-evidence.json",
            "reports/cross-language-api/apple/binding-evidence.json":
                "payload/codex-agent-runtime-ios/build/reports/cross-language-api/apple/binding-evidence.json",
            "reports/cross-language-api/bindings/swift-parity.json":
                "payload/codex-agent-runtime-ios/build/reports/cross-language-api/bindings/swift-parity.json",
            "reports/cross-language-api/bindings/objective-c-parity.json":
                "payload/codex-agent-runtime-ios/build/reports/cross-language-api/bindings/objective-c-parity.json",
            "reports/swift-authentication-tests-summary.json":
                "payload/codex-agent-runtime-ios/build/swift-authentication-tests-summary.json",
        }
        for index, (distribution_path, lane_path) in enumerate(reports.items()):
            contents = f"synthetic-report-{index}\n".encode()
            for root, relative in ((self.distribution, distribution_path), (self.lane, lane_path)):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(contents)

        evidence = [
            f"{record['relativePath']}=synthetic-apple-observation"
            for record in regular_file_inventory(self.lane, allow_empty=True)
        ]
        lane_receipt.create_receipt(Namespace(
            plan=self.plan, lane="ios-swift-tests", output=self.lane,
            workflow_path=".github/workflows/ci.yml",
            artifact_name=f"codex-agent-ci-ios-swift-tests-{self.tree}", run_id=91, run_attempt=2,
            runner=["os=macOS", "arch=ARM64"],
            toolchain=["xcode=26.3", "swift=6.2.3", "validationActions=build,metadata,test"],
            artifact=[], evidence=evidence,
        ))
        self.receipt_digest = sha256_bytes((self.lane / "lane-receipt.json").read_bytes())
        caller = self.root / "caller"
        caller.mkdir()
        self.expected_proof = caller / "verified-distribution-proof.json"
        self.expected_proof.write_bytes((self.distribution / self.expected_proof.name).read_bytes())
        self.expected_compatibility = caller / "sdk-compatibility.json"
        self.expected_compatibility.write_bytes(self.compatibility_bytes)
        self.tooling_evidence = caller / "tooling-evidence.zip"
        self.tooling_evidence.write_bytes(b"synthetic tooling evidence\n")
        self.tooling_public_key = caller / "tooling-public-key.pub"
        self.tooling_public_key.write_bytes(b"synthetic public key\n")
        self.java_executable = caller / "java"
        self.java_executable.write_bytes(b"synthetic java\n")

    def _assert_private_replay(self, **arguments) -> None:
        distribution = Path(arguments["distribution_directory"])
        execution = Path(arguments["execution_directory"])
        self.assertNotEqual(self.distribution, distribution)
        self.assertNotEqual(self.execution, execution)
        self.assertEqual(
            regular_file_inventory(self.distribution), regular_file_inventory(distribution),
        )
        self.assertEqual(
            regular_file_inventory(self.execution, allow_empty=True),
            regular_file_inventory(execution, allow_empty=True),
        )
        self.assertEqual(
            self.expected_proof.read_bytes(),
            Path(arguments["expected_distribution_proof"]).read_bytes(),
        )
        self.assertEqual(
            self.expected_compatibility.read_bytes(),
            Path(arguments["expected_sdk_compatibility"]).read_bytes(),
        )

    def verify(self, *, replay=None, **changes) -> None:
        arguments = {
            "repository": self.root,
            "distribution_directory": self.distribution,
            "execution_directory": self.execution,
            "ios_swift_tests_root": self.lane,
            "impact_plan": self.plan,
            "expected_lane_receipt_sha256": self.receipt_digest,
            "expected_producer_commit": self.commit,
            "expected_producer_tree": self.tree,
            "expected_distribution_proof": self.expected_proof,
            "expected_sdk_compatibility": self.expected_compatibility,
            "contract_bundle": self.contract_bundle,
            "contract_projection": self.projection,
            "tooling_evidence": self.tooling_evidence,
            "tooling_public_key": self.tooling_public_key,
            "java_executable": self.java_executable,
            "policy_revision": self.commit,
            "required_trust_domain": "development",
        }
        with patch(
            "ci.products.sdk_apple_source.verify_sdk_apple_original_execution",
            side_effect=replay or self._assert_private_replay,
        ):
            return verify_sdk_apple_original_source(**{**arguments, **changes})

    def test_real_git_lane_receipt_and_contract_projection_bind_exact_originals(self) -> None:
        before = {
            name: regular_file_inventory(path, allow_empty=True)
            for name, path in (("distribution", self.distribution), ("execution", self.execution),
                               ("lane", self.lane))
        }
        self.assertIsNone(self.verify())
        self.assertEqual(before, {
            name: regular_file_inventory(path, allow_empty=True)
            for name, path in (("distribution", self.distribution), ("execution", self.execution),
                               ("lane", self.lane))
        })
        self.assertEqual(b"", (self.execution / "compiler-raw/operation/stderr.bin").read_bytes())

    def test_wrong_caller_or_retained_source_identity_rejects(self) -> None:
        cases = (
            ("lane receipt", {"expected_lane_receipt_sha256": sha256_bytes(b"wrong")}),
            ("producer commit", {"expected_producer_commit": "a" * 40}),
            ("producer tree", {"expected_producer_tree": "b" * 40}),
            ("proof alias", {"expected_distribution_proof":
                             self.distribution / "verified-distribution-proof.json"}),
            ("projection", {"contract_projection": object()}),
        )
        for name, changes in cases:
            with self.subTest(name=name), self.assertRaises((TypeError, ValueError)):
                self.verify(**changes)

        source = self.execution / "source/Package.swift"
        original = source.read_bytes()
        source.write_bytes(b"changed retained source\n")
        try:
            with self.assertRaisesRegex(ValueError, "differs from original Git"):
                self.verify()
        finally:
            source.write_bytes(original)

    def test_raw_lane_report_and_authenticated_contract_cross_pairs_reject(self) -> None:
        cases = (
            (self.lane / "payload/codex-agent-runtime-ios/build/apple-compiler-evidence-task/raw/operation/stdout.bin",
             "receipt file"),
            (self.distribution / "reports/cross-language-api/apple/compiler-evidence.json",
             "original lane"),
            (self.execution / "canonical/canonical-api.json", "authenticated Contract"),
        )
        for path, message in cases:
            original = path.read_bytes()
            path.write_bytes(b"cross-paired\n")
            try:
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, message):
                    self.verify()
            finally:
                path.write_bytes(original)

    def test_original_and_private_post_validation_mutations_reject(self) -> None:
        original_verify = contract_model.verify_contract_bundle
        original = (self.execution / "source/Package.swift").read_bytes()

        def mutate_original(bundle):
            result = original_verify(bundle)
            (self.execution / "source/Package.swift").write_bytes(b"changed during gate\n")
            return result

        try:
            with patch("ci.products.sdk_apple_source.verify_contract_bundle", side_effect=mutate_original), \
                    self.assertRaisesRegex(ValueError, "changed during verification"):
                self.verify(replay=lambda **arguments: None)
        finally:
            (self.execution / "source/Package.swift").write_bytes(original)

        def mutate_private(bundle):
            result = original_verify(bundle)
            private_lane = Path(bundle).parent.parent / "lane"
            target = private_lane / \
                "payload/codex-agent-runtime-ios/build/apple-compiler-evidence-task/raw/operation/stdout.bin"
            target.write_bytes(b"changed private lane\n")
            return result

        with patch("ci.products.sdk_apple_source.verify_contract_bundle", side_effect=mutate_private), \
                self.assertRaisesRegex(ValueError, "changed during verification"):
            self.verify()

    def test_replay_rejection_is_not_converted_to_source_acceptance(self) -> None:
        def reject(**arguments):
            self._assert_private_replay(**arguments)
            raise ValueError("existing full Apple replay rejected")

        with self.assertRaisesRegex(ValueError, "existing full Apple replay rejected"):
            self.verify(replay=reject)


if __name__ == "__main__":
    unittest.main()
