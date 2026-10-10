"""Contract original observation and protected Maven signing never share credentials."""

from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from ci import contract_phase10_maven_caller as caller
from ci.tests.test_contract_bundle import VERSION
from ci.tests import test_contract_release_capture as release_fixture
from products.contract_phase10_maven import verify_contract_phase10_maven
from products.inventory import (
    canonical_json_bytes, load_canonical_json, regular_file_inventory,
    sha256_bytes,
)


@unittest.skipUnless(shutil.which("gpg") and shutil.which("ssh-keygen"),
                     "GnuPG and ssh-keygen are required")
class ContractPhase10MavenCallerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        home = tempfile.TemporaryDirectory(prefix="contract-p10-pgp-", dir="/private/tmp")
        cls.addClassCleanup(home.cleanup)
        cls.home = Path(home.name)
        command = ["gpg", "--homedir", str(cls.home), "--batch", "--no-tty",
                   "--pinentry-mode", "loopback", "--passphrase", ""]
        generated = subprocess.run(
            [*command, "--quick-generate-key", "Contract P10 <contract@example.test>",
             "ed25519", "sign", "0"], capture_output=True, timeout=60,
        )
        if generated.returncode != 0:
            raise RuntimeError(generated.stderr.decode())
        cls.public_key = subprocess.run(
            [*command, "--armor", "--export", "contract@example.test"],
            check=True, capture_output=True, timeout=60,
        ).stdout
        listing = subprocess.run(
            [*command, "--with-colons", "--fingerprint", "--list-secret-keys"],
            check=True, capture_output=True, timeout=60,
        ).stdout.decode()
        cls.fingerprint = next(line.split(":")[9] for line in listing.splitlines()
                               if line.startswith("fpr:"))

    def setUp(self) -> None:
        fixture = release_fixture.ContractReleaseCaptureTest(
            "test_complete_original_ci_pipeline_signs_exact_payload_and_preserves_external_originals",
        )
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.prepared = fixture.root / "phase10-maven-prepared"
        self.destination = fixture.root / "phase10-maven"
        self.key = fixture.root / "maven-public.asc"
        self.key.write_bytes(self.public_key)

    def prepare(self, *, key_digest: str | None = None, **policy):
        fixture = self.fixture
        safe_environment = {name: value for name, value in fixture.environment.values.items()
                            if name not in caller._SECRETS}
        with mock.patch("reuse.api_request", side_effect=fixture.api()):
            return caller.prepare_contract_phase10_maven_handoff(
                fixture.repository_root, self.prepared,
                trusted_source_sha=fixture.source_sha, trusted_workflow_sha=fixture.pin,
                artifact_id=fixture.upload_artifact["id"],
                artifact_sha256=fixture.upload_artifact["digest"],
                transport_producer=fixture.producer, contract_version=VERSION,
                event_payload=fixture.event, environment=safe_environment,
                token="not-a-real-token", pgp_public_key=self.key,
                expected_pgp_key_sha256=key_digest or sha256_bytes(self.key.read_bytes()),
                **policy,
            )

    def sign(self, *, preparation_digest: str | None = None, environment=None):
        digest = preparation_digest or sha256_bytes((self.prepared / "preparation.json").read_bytes())
        return caller.sign_contract_phase10_maven_handoff(
            self.prepared, self.destination, expected_preparation_sha256=digest,
            expected_pgp_key_sha256=sha256_bytes(self.key.read_bytes()),
            signing_home=self.home, signing_fingerprint=self.fingerprint,
            product_private_key=self.fixture.private_key.read_text(), passphrase="",
            environment={} if environment is None else environment,
        )

    def invoke(self):
        self.prepare()
        return self.sign()

    def test_exact_original_payload_and_external_phase10_maven_sidecars(self) -> None:
        result = self.invoke()
        release = self.destination / "contract-release-evidence"
        payload = release / "contract-input" / f"codex-agent-contract-{VERSION}.zip"
        self.assertEqual(self.fixture.payload.read_bytes(), payload.read_bytes())
        self.assertEqual(result["releaseFiles"], regular_file_inventory(release))
        self.assertEqual(result["mavenSidecars"], verify_contract_phase10_maven(
            payload, self.destination / "maven-sidecars",
            self.destination / "publication-pgp-public-key.asc", sha256_bytes(self.key.read_bytes()),
        ))
        self.assertEqual(result, load_canonical_json(self.destination / "sidecar-selection.json"))
        self.assertEqual(self.fixture.public_key.read_bytes(),
                         (release / "contract-input/public-key.pub").read_bytes())
        self.assertEqual({"schemaVersion", "releaseCaller", "releaseFiles",
                          "contractInventory", "mavenSidecars"}, set(result))

    def test_no_secret_prepare_and_no_token_sign(self) -> None:
        with self.assertRaisesRegex(ValueError, "forbidden credentials"):
            caller.prepare_contract_phase10_maven_handoff(
                self.fixture.repository_root, self.prepared,
                trusted_source_sha=self.fixture.source_sha, trusted_workflow_sha=self.fixture.pin,
                artifact_id=self.fixture.upload_artifact["id"],
                artifact_sha256=self.fixture.upload_artifact["digest"],
                transport_producer=self.fixture.producer, contract_version=VERSION,
                event_payload=self.fixture.event, environment=self.fixture.environment,
                token="not-a-real-token", pgp_public_key=self.key,
                expected_pgp_key_sha256=sha256_bytes(self.key.read_bytes()),
            )
        self.assertFalse(self.prepared.exists())
        self.prepare()
        with mock.patch("reuse.api_request", side_effect=AssertionError("offline signer used API")):
            for name in caller._TOKENS:
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "forbidden credentials"):
                    self.sign(environment={name: "token"})
                with self.subTest(ambient=name), mock.patch.dict(os.environ, {name: "token"}), \
                        self.assertRaisesRegex(ValueError, "forbidden credentials"):
                    self.sign(environment={})
            self.sign()

    def test_pinned_preparation_and_key_mutations_rejected_without_signing(self) -> None:
        with mock.patch.object(caller, "capture_contract_ci_artifact") as capture, \
                self.assertRaisesRegex(ValueError, "independent pin"):
            self.prepare(key_digest="sha256:" + "0" * 64)
        capture.assert_not_called()
        self.prepare()
        with mock.patch.object(caller, "produce_contract_phase10_maven_sidecars") as signer:
            with self.assertRaisesRegex(ValueError, "independent pin"):
                self.sign(preparation_digest="sha256:" + "0" * 64)
            (self.prepared / "caller.json").write_bytes(b"changed\n")
            with self.assertRaisesRegex(ValueError, "inventory"):
                self.sign()
        signer.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_failed_original_admission_never_reaches_signer(self) -> None:
        original = self.fixture.upload_artifact["digest"]
        self.fixture.upload_artifact["digest"] = "sha256:" + "0" * 64
        with mock.patch.object(caller, "produce_contract_phase10_maven_sidecars") as signer:
            with self.assertRaises(ValueError):
                self.prepare()
            signer.assert_not_called()
        self.fixture.upload_artifact["digest"] = original
        self.assertFalse(self.prepared.exists())

    def test_exact_child_path_and_both_jobs_required_before_signing(self) -> None:
        path = ".github/workflows/contract-validation.yml"
        binary = "product-validation / contract-validation / product-contracts"
        continuation = "product-validation / contract-validation / contract-continuation"
        self.fixture.run["referenced_workflows"] = [{
            "path": f"{self.fixture.producer['repository']}/{path}@{self.fixture.pin}",
            "sha": self.fixture.pin,
        }]
        self.fixture.jobs[0]["name"] = binary
        self.fixture.jobs[1]["name"] = continuation
        policy = {
            "trusted_contract_workflow_path": path,
            "trusted_contract_binary_job": binary,
            "trusted_contract_continuation_job": continuation,
        }
        for changes in (
            {"trusted_contract_workflow_path": ".github/workflows/wrong.yml"},
            {"trusted_contract_binary_job": "product-validation / wrong"},
            {"trusted_contract_continuation_job": "product-validation / wrong"},
            {"trusted_contract_workflow_path": None},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.prepare(**{**policy, **changes})
            self.assertFalse(self.prepared.exists())
        self.prepare(**policy)
        self.sign()

    def test_cli_modes_and_secret_free_prepare(self) -> None:
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        checked = subprocess.run(
            [sys.executable, "-B", str(Path(caller.__file__).resolve()), "--help"],
            cwd=self.fixture.root, env=environment, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(0, checked.returncode, checked.stderr)
        self.assertIn("prepare", checked.stdout)
        self.assertIn("sign", checked.stdout)
        event_path = self.fixture.root / "event.json"
        event_path.write_bytes(canonical_json_bytes(self.fixture.event))
        arguments = ["prepare", "--repository-root", str(self.fixture.repository_root),
                     "--destination", str(self.prepared), "--trusted-source-sha", self.fixture.source_sha,
                     "--trusted-workflow-sha", self.fixture.pin,
                     "--trusted-contract-workflow-path", ".github/workflows/contract-validation.yml",
                     "--trusted-contract-binary-job", "product-validation / contract-validation / product-contracts",
                     "--trusted-contract-continuation-job", "product-validation / contract-validation / contract-continuation",
                     "--artifact-id", str(self.fixture.upload_artifact["id"]),
                     "--artifact-sha256", self.fixture.upload_artifact["digest"],
                     "--validation-tree", self.fixture.producer["tree"], "--contract-version", VERSION,
                     "--pgp-public-key", str(self.key),
                     "--expected-pgp-key-sha256", sha256_bytes(self.key.read_bytes())]
        cli_environment = {name: self.fixture.environment.values[name] for name in (
            "GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_EVENT_NAME",
            "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT",
        )}
        with mock.patch.dict(os.environ, {**cli_environment, "GITHUB_EVENT_PATH": str(event_path)}), \
                mock.patch.object(caller, "prepare_contract_phase10_maven_handoff",
                                  return_value={"schemaVersion": 1}) as prepare, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, caller.main(arguments))
        self.assertEqual(".github/workflows/contract-validation.yml",
                         prepare.call_args.kwargs["trusted_contract_workflow_path"])
        sign_args = ["sign", "--prepared", str(self.prepared),
                     "--destination", str(self.destination),
                     "--expected-preparation-sha256", "sha256:" + "0" * 64,
                     "--expected-pgp-key-sha256", sha256_bytes(self.key.read_bytes()),
                     "--signing-home", str(self.home),
                     "--signing-fingerprint", self.fingerprint]
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "forbidden",
                                       "CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": "private"}), \
                mock.patch.object(sys, "stdin") as input_stream, \
                self.assertRaisesRegex(ValueError, "forbidden credentials"):
            caller.main(sign_args)
        input_stream.read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
