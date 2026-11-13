"""Shared-verifier isolation/orchestration; mocks are not host acceptance."""

from contextlib import contextmanager
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

from ci.products import sdk_validation as verifier
from ci.products.inventory import load_canonical_json_bytes
from ci.tests.test_sdk_validation_projection import SdkValidationProjectionTest


class SharedSdkVerifierTest(unittest.TestCase):
    def test_fresh_entrypoints_do_not_depend_on_preloaded_package_modules(self):
        repository = Path(__file__).resolve().parents[2]
        bootstrap = "import sys;sys.path[:0]=sys.argv[1:3];"
        for module in ("product_reuse", "ci.product_reuse", "products.aggregate", "ci.products.aggregate"):
            with self.subTest(module=module):
                result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c",
                    bootstrap + "__import__(sys.argv[3])", str(repository / "ci"), str(repository), module],
                    capture_output=True, timeout=30)
                self.assertEqual(0, result.returncode, result.stderr.decode())

    def test_real_collection_scope_shares_worker_across_copied_admission_contexts(self):
        from ci.products.sdk_validation_inputs import collection_admission_scope
        fixture = SdkValidationProjectionTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        arguments = fixture.args
        arguments["tooling_evidence"].mkdir()
        arguments["tooling_public_key"].write_bytes(b"test-only caller key\n")
        worker = Mock()
        worker.verify.return_value = dict(content=fixture.value,
            receiptSha256=verifier.sha256_bytes(arguments["validation_receipt"].read_bytes()))
        closed, late = [], []

        @contextmanager
        def process(**_):
            try:
                yield worker
            finally:
                closed.append(True)

        @collection_admission_scope
        def collect():
            late.append(copy_context())
            with ThreadPoolExecutor(max_workers=2) as pool:
                pending = [pool.submit(copy_context().run, verifier.verify_sdk_validation_projection,
                                       **arguments) for _ in range(2)]
                proofs = [item.result() for item in pending]
            self.assertEqual([], closed)
            self.assertTrue(all(type(proof) is verifier.VerifiedSdkValidationProjection for proof in proofs))

        with patch.object(verifier, "verified_shared_sdk_process", side_effect=process) as factory:
            collect()
            self.assertEqual(1, factory.call_count)
            self.assertEqual(2, worker.verify.call_count)
            self.assertEqual([True], closed)
            with self.assertRaisesRegex(ValueError, "outside its private lifetime"):
                late[0].run(verifier.verify_sdk_validation_projection, **arguments)

    def test_authority_bound_once_exact_proofs_failures_and_expired_scope(self):
        fixture = SdkValidationProjectionTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        arguments = fixture.args
        arguments["tooling_evidence"].mkdir()
        arguments["tooling_public_key"].write_bytes(b"test-only policy seam\n")
        worker = Mock()
        worker.verify.return_value = dict(content=fixture.value,
            receiptSha256=verifier.sha256_bytes(arguments["validation_receipt"].read_bytes()))
        opened, closed = [], []
        @contextmanager
        def process(**fields):
            opened.append(fields)
            try:
                yield worker
            finally:
                closed.append(True)
        with patch.object(verifier, "verified_shared_sdk_process", side_effect=process):
            with verifier.shared_sdk_validation_scope():
                late = copy_context()
                for _ in range(2):
                    proof = verifier.verify_sdk_validation_projection(**arguments)
                    self.assertIs(type(proof), verifier.VerifiedSdkValidationProjection)
                    original = arguments["validation_receipt"].read_bytes()
                    receipt = load_canonical_json_bytes(original)
                    proof.output_inventory(verifier.sha256_bytes(original), receipt["outputs"], identity=receipt)
                worker.verify.side_effect = ValueError("host gate rejected")
                with self.assertRaisesRegex(ValueError, "host gate rejected"):
                    verifier.verify_sdk_validation_projection(**arguments)
                arguments["tooling_public_key"].write_bytes(b"changed policy key\n")
                with self.assertRaisesRegex(ValueError, "authority changed"):
                    verifier.verify_sdk_validation_projection(**arguments)
            with self.assertRaisesRegex(ValueError, "outside its private lifetime"):
                late.run(verifier.verify_sdk_validation_projection, **arguments)
        self.assertEqual(1, len(opened))
        self.assertEqual([True], closed)
        self.assertEqual(3, worker.verify.call_count)

    def test_isolated_fixed_process_rejects_failure_and_mutated_resource(self):
        # Minimal protocol fixture. It has no package verifier and always rejects;
        # only the production context may authenticate a real executable JAR.
        script = b'''import json,sys
print('{"protocol":1}',flush=True)
for line in sys.stdin:
    value=json.loads(line)
    print(json.dumps(dict(id=value['id'],result='failure',error='fixture rejection',metrics=dict(commonChecks=0,commonReuses=0,elapsedSeconds='0.0')),sort_keys=True,separators=(',',':')),flush=True)
'''
        with tempfile.TemporaryDirectory() as temporary, verifier._byte_inventory_scope():
            root = Path(temporary).resolve()
            jar, java = root / "fixture.jar", root / "java"
            java.write_bytes(b"fixture executable identity; never executed\n")
            with ZipFile(jar, "w") as archive:
                archive.writestr("python/ci/products/sdk_validation.py", script)
            worker = verifier._SharedVerifierProcess(root, jar, root, java)
            try:
                with self.assertRaisesRegex(ValueError, "fixture rejection"):
                    worker.verify({}, {})
                resource = worker.code / "ci/products/sdk_validation.py"
                resource.write_bytes(resource.read_bytes() + b"# mutation\n")
                with self.assertRaisesRegex(ValueError, "code or Java changed"):
                    worker.verify({}, {})
            finally:
                with self.assertRaisesRegex(ValueError, "code or Java changed"):
                    worker.close()

    def test_cpp_isolated_verifier_reuses_captured_dependency_layout(self):
        repository = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            code = root / "code"
            for relative in ("ci/products/inventory.py", "ci/products/__init__.py",
                             "codex-agent-bindings/cpp/tools/verify_imported_package.py"):
                destination = code / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((repository / relative).read_bytes())
            (code / "ci/__init__.py").write_bytes(b"")
            jar = root / "fixture.jar"
            with ZipFile(jar, "w") as archive:
                relative = "codex-agent-bindings/cpp/tools/verify_imported_package.py"
                archive.writestr("python/" + relative, (code / relative).read_bytes())
            with patch.object(verifier, "__file__", str(code / "ci/products/sdk_validation.py")):
                with self.assertRaises(subprocess.CalledProcessError) as caught:
                    verifier._host_gates(root / "unused-java", jar,
                        root / "common", root / "missing-host", "cpp", "linux-x64")
            self.assertIn(b"Required regular input is missing or symbolic", caught.exception.stderr)
            self.assertNotIn(b"ModuleNotFoundError", caught.exception.stderr)
            self.assertEqual(["-I", "-S", "-B"], caught.exception.cmd[1:4])
            self.assertEqual(str(code / "codex-agent-bindings/cpp/tools/verify_imported_package.py"),
                             caught.exception.cmd[4])

    def test_failed_tooling_authentication_never_starts_process(self):
        error = subprocess.CalledProcessError(1, "fixed verifier", stderr=b"real causal diagnostic\xff")
        self.assertIn("real causal diagnostic", verifier._failure_detail(error))
        self.assertIn("ValueError: rejected", verifier._failure_detail(ValueError("rejected")))
        with patch("ci.products.tooling.verified_tooling_capture", side_effect=ValueError("bad signature")), \
                patch.object(verifier, "_SharedVerifierProcess") as process:
            with self.assertRaisesRegex(ValueError, "bad signature"):
                with verifier.verified_shared_sdk_process(repository=Path("/fixture"),
                        java_executable=Path("/fixture/bin/java"), tooling_evidence=Path("/fixture/tooling"),
                        tooling_public_key=Path("/fixture/key.pub"), policy_revision="a" * 40,
                        required_trust_domain="development"):
                    self.fail("Unsigned verifier must not start")
            process.assert_not_called()
