"""Synthetic official API plus real local signed Contract/PGP caller evidence."""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from ci import contract_phase10_sidecar_caller as caller
from ci.tests import test_contract_equal_tree_original as original_fixture
from products.contract_phase10_inventory import verify_contract_phase10_inventory
from products.contract_phase10_maven import verify_contract_phase10_maven
from products.inventory import (
    load_canonical_json, publish_regular_tree as actual_publish_regular_tree,
    regular_file_inventory, sha256_bytes, write_canonical_json as actual_write_canonical_json,
)


class ContractPhase10SidecarCallerTest(unittest.TestCase):
    def setUp(self) -> None:
        fixture = original_fixture.ContractEqualTreeOriginalTest(
            "test_exact_equal_tree_original_retains_signed_handoff_and_public_policy",
        )
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.destination = fixture.root / "contract-sidecar-release"
        self.key = fixture.root / "publication-pgp-key.asc"
        home = tempfile.TemporaryDirectory(prefix="ct-gpg-", dir="/tmp")
        self.addCleanup(home.cleanup)
        self.home = Path(home.name)

    def invoke(self, fingerprint: str, **workflow_policy) -> dict:
        fixture = self.fixture
        with mock.patch("reuse.api_request", side_effect=fixture.api):
            return caller.produce_authenticated_contract_maven_sidecars(
                fixture.trusted, fixture.candidate, self.destination,
                trusted_source_sha=fixture.source_sha,
                trusted_workflow_sha=fixture.workflow_sha,
                trusted_promotion_workflow_sha=fixture.promotion_sha,
                final_commit=fixture.final, event_payload=fixture.event,
                environment=fixture.environment, token="synthetic-token",
                pgp_public_key=self.key,
                expected_pgp_key_sha256=sha256_bytes(self.key.read_bytes()),
                signing_home=self.home, signing_fingerprint=fingerprint, passphrase="",
                **workflow_policy,
            )

    def test_split_child_policy_reaches_signer_only_for_exact_path_and_job(self) -> None:
        self.key.write_bytes(b"independently pinned fixture PGP key\n")
        path = ".github/workflows/contract-validation.yml"
        job = "contract-validation / contract-attestation"
        self.fixture.run["referenced_workflows"] = [{
            "path": f"{self.fixture.producer['repository']}/{path}@{self.fixture.workflow_sha}",
            "sha": self.fixture.workflow_sha,
        }]
        self.fixture.job["name"] = job
        policy = {"trusted_workflow_path": path, "trusted_job_name": job}
        for changes in (
            {"trusted_workflow_path": ".github/workflows/wrong.yml"},
            {"trusted_job_name": "contract-validation / wrong"},
            {"trusted_workflow_path": None},
            {"trusted_job_name": None},
        ):
            with self.subTest(changes=changes), \
                    mock.patch.object(caller, "produce_contract_phase10_maven_sidecars") as signer, \
                    self.assertRaises(ValueError):
                self.invoke("A" * 40, **{**policy, **changes})
            signer.assert_not_called()
            self.assertFalse(self.destination.exists())
        with mock.patch.object(caller, "produce_contract_phase10_maven_sidecars",
                               side_effect=RuntimeError("admitted before signing")) as signer, \
                self.assertRaisesRegex(RuntimeError, "admitted before signing"):
            self.invoke("A" * 40, **policy)
        signer.assert_called_once()
        self.assertFalse(self.destination.exists())

    def test_wrong_official_upload_cannot_reach_pgp_signer(self) -> None:
        self.key.write_bytes(b"independently pinned fixture PGP key\n")
        original = self.fixture.artifact["digest"]
        self.fixture.artifact["digest"] = "sha256:" + "0" * 64
        try:
            with mock.patch.object(caller, "produce_contract_phase10_maven_sidecars") as signer:
                with self.assertRaises(ValueError):
                    self.invoke("A" * 40)
                signer.assert_not_called()
        finally:
            self.fixture.artifact["digest"] = original
        self.assertFalse(self.destination.exists())

    def test_mutated_public_key_at_publication_cannot_return_success(self) -> None:
        self.key.write_bytes(b"independently pinned fixture PGP key\n")
        fixture = self.fixture
        captured = {}

        def signed(payload, sidecars, *_args):
            sidecars.mkdir()
            (sidecars / "fixture.asc").write_bytes(b"external signature\n")
            captured["signed"] = {"contractVersion": original_fixture.VERSION,
                                  "payloadSha256": sha256_bytes(payload.read_bytes()),
                                  "sidecarFiles": regular_file_inventory(sidecars)}
            return captured["signed"]

        def mutate_then_publish(source, destination, **kwargs):
            (Path(source) / "publication-pgp-public-key.asc").write_bytes(b"changed after verification\n")
            actual_publish_regular_tree(source, destination, **kwargs)

        with mock.patch.object(caller, "produce_contract_phase10_maven_sidecars", side_effect=signed), \
                mock.patch.object(caller, "verify_contract_phase10_maven",
                                  side_effect=lambda *_: captured["signed"]), \
                mock.patch.object(caller, "publish_regular_tree", side_effect=mutate_then_publish):
            with self.assertRaisesRegex(ValueError, "pinned inventory"):
                self.invoke("A" * 40)
        self.assertFalse(self.destination.exists())

    def test_mutated_selection_before_inventory_cannot_become_baseline(self) -> None:
        self.key.write_bytes(b"independently pinned fixture PGP key\n")
        captured = {}

        def signed(payload, sidecars, *_args):
            sidecars.mkdir()
            (sidecars / "fixture.asc").write_bytes(b"external signature\n")
            captured["signed"] = {"contractVersion": original_fixture.VERSION,
                                  "payloadSha256": sha256_bytes(payload.read_bytes()),
                                  "sidecarFiles": regular_file_inventory(sidecars)}
            return captured["signed"]

        def altered_control(path, value):
            actual_write_canonical_json(path, value)
            if Path(path).name == "sidecar-selection.json":
                Path(path).write_bytes(b"{}\n")

        with mock.patch.object(caller, "produce_contract_phase10_maven_sidecars", side_effect=signed), \
                mock.patch.object(caller, "verify_contract_phase10_maven",
                                  side_effect=lambda *_: captured["signed"]), \
                mock.patch.object(caller, "write_canonical_json", side_effect=altered_control), \
                mock.patch.object(caller, "publish_regular_tree") as publish:
            with self.assertRaisesRegex(ValueError, "original or PGP key changed"):
                self.invoke("A" * 40)
            publish.assert_not_called()
        self.assertFalse(self.destination.exists())

    @unittest.skipUnless(shutil.which("gpg") and shutil.which("ssh-keygen"),
                         "GnuPG and ssh-keygen are required")
    def test_official_original_is_retained_and_only_external_sidecars_are_new(self) -> None:
        command = ["gpg", "--homedir", str(self.home), "--batch", "--no-tty",
                   "--pinentry-mode", "loopback", "--passphrase", ""]
        generated = subprocess.run(
            [*command, "--quick-generate-key", "Contract Caller <caller@example.test>",
             "ed25519", "sign", "0"], capture_output=True, timeout=60,
        )
        self.assertEqual(0, generated.returncode, generated.stderr.decode())
        self.key.write_bytes(subprocess.run(
            [*command, "--armor", "--export", "caller@example.test"],
            check=True, capture_output=True, timeout=60,
        ).stdout)
        listing = subprocess.run(
            [*command, "--with-colons", "--fingerprint", "--list-secret-keys"],
            check=True, capture_output=True, timeout=60,
        ).stdout.decode()
        fingerprint = next(line.split(":")[9] for line in listing.splitlines()
                           if line.startswith("fpr:"))
        output = self.invoke(fingerprint)
        captured = self.destination / "original"
        record = verify_contract_phase10_inventory(captured / "contract-record")
        self.assertEqual(record, output["originalSelection"]["handoffInventory"])
        payload = (captured / "contract-record/handoff" /
                   f"codex-agent-contract-{record['contractVersion']}.zip")
        self.assertEqual(output["mavenSidecars"], verify_contract_phase10_maven(
            payload, self.destination / "maven-sidecars",
            self.destination / "publication-pgp-public-key.asc", sha256_bytes(self.key.read_bytes()),
        ))
        self.assertEqual(self.fixture.archive,
                         (captured / "original-evidence/upload.zip").read_bytes())
        self.assertEqual(self.key.read_bytes(),
                         (self.destination / "publication-pgp-public-key.asc").read_bytes())
        self.assertEqual(output["mavenSidecars"]["sidecarFiles"],
                         regular_file_inventory(self.destination / "maven-sidecars"))
        selected = load_canonical_json(self.destination / "sidecar-selection.json")
        self.assertEqual(output["originalSelection"], selected["originalSelection"])
        self.assertEqual(output["mavenSidecars"], selected["mavenSidecars"])
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.invoke(fingerprint)

    def test_cli_help_without_pythonpath(self) -> None:
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        checked = subprocess.run(
            [sys.executable, "-B", str(Path(caller.__file__).resolve()), "--help"],
            cwd=self.fixture.root, env=environment, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(0, checked.returncode, checked.stderr)
        self.assertIn("--expected-pgp-key-sha256", checked.stdout)
        self.assertIn("--trusted-workflow-path", checked.stdout)
        self.assertIn("--trusted-job-name", checked.stdout)

    def test_cli_forwards_paired_child_policy(self) -> None:
        event = self.fixture.root / "push-event.json"
        event.write_text(json.dumps(self.fixture.event), encoding="utf-8")
        arguments = [
            "--repository-root", str(self.fixture.trusted),
            "--candidate-root", str(self.fixture.candidate),
            "--destination", str(self.destination),
            "--trusted-source-sha", self.fixture.source_sha,
            "--trusted-workflow-sha", self.fixture.workflow_sha,
            "--trusted-workflow-path", ".github/workflows/contract-validation.yml",
            "--trusted-job-name", "contract-validation / contract-attestation",
            "--trusted-promotion-workflow-sha", self.fixture.promotion_sha,
            "--final-commit", self.fixture.final,
            "--pgp-public-key", str(self.key),
            "--expected-pgp-key-sha256", "sha256:" + "a" * 64,
            "--signing-home", str(self.home),
            "--signing-fingerprint", "A" * 40,
        ]
        with mock.patch.dict(os.environ, {"GITHUB_EVENT_PATH": str(event),
                                         "GITHUB_TOKEN": "synthetic-token"}), \
                mock.patch.object(caller, "produce_authenticated_contract_maven_sidecars",
                                  return_value={}) as produce, \
                mock.patch.object(sys, "stdin", io.StringIO("synthetic passphrase")), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, caller.main(arguments))
        self.assertEqual(".github/workflows/contract-validation.yml",
                         produce.call_args.kwargs["trusted_workflow_path"])
        self.assertEqual("contract-validation / contract-attestation",
                         produce.call_args.kwargs["trusted_job_name"])


if __name__ == "__main__":
    unittest.main()
