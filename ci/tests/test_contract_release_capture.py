"""Complete synthetic CI capture/signing pipeline; never protected-host acceptance."""

from collections.abc import Mapping
import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest import mock
import zipfile

from ci.tests import test_contract_ci_originals as originals_fixture
from ci.tests.test_contract_bundle import VERSION
from ci.tests.test_contract_release_context import contract_context, trusted_repository
from products.contract_attestation import build_contract_attestation, verify_contract_attestation
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes,
    publish_regular_tree as actual_publish_regular_tree,
    regular_file_inventory, sha256_bytes,
)
from products.signatures import generate_development_key
from ci import contract_release


SECRET = "CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"


class ObservedEnvironment(Mapping):
    def __init__(self, values):
        self.values = values
        self.secret_reads = 0
        self.forbid_secret = False

    def __getitem__(self, key):
        if key == SECRET:
            self.secret_reads += 1
            if self.forbid_secret:
                raise AssertionError("Private signing key was read before original evidence admission")
        return self.values[key]

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)


@unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH signing tool unavailable")
class ContractReleaseCaptureTest(unittest.TestCase):
    def setUp(self):
        originals_fixture.ContractOriginalCiCaptureTest.setUp(self)
        self.private_key, self.public_key, development = generate_development_key(self.root / "signer")
        self.signing = {**development, "trustDomain": "release"}
        self.repository_root = self.root / "trusted-source"
        trusted_repository(self.repository_root)
        self.keyring = self.repository_root / "gradle/release/product-signing-keys.json"
        self.keys = self.repository_root / "gradle/release/keys"
        self.keys.mkdir(exist_ok=True)
        (self.keys / f"{self.signing['keyId']}.pub").write_bytes(self.public_key.read_bytes())
        self.keyring.write_bytes(canonical_json_bytes({
            "schemaVersion": 1, "namespace": self.signing["namespace"], "algorithm": self.signing["algorithm"],
            "trustDomain": "release", "activeKey": {"keyId": self.signing["keyId"],
            "fingerprint": self.signing["fingerprint"]}, "retiredKeys": [],
        }))
        subprocess.run(("git", "add", "--", "gradle/release"), cwd=self.repository_root, check=True)
        subprocess.run(("git", "commit", "-qm", "tracked public fixture policy"), cwd=self.repository_root, check=True)
        self.source_sha = subprocess.run(("git", "rev-parse", "HEAD"), cwd=self.repository_root,
                                         check=True, capture_output=True, text=True).stdout.strip()
        _, self.event, environment = contract_context()
        environment.update({"GITHUB_SHA": self.producer["commit"], "GITHUB_RUN_ID": str(self.producer["runId"]),
                            "GITHUB_RUN_ATTEMPT": str(self.producer["runAttempt"]), SECRET: self.private_key.read_text()})
        self.event["pull_request"]["head"]["sha"] = self.run["head_sha"]
        self.event["pull_request"]["base"]["sha"] = self.commit["parents"][0]["sha"]
        self.environment = ObservedEnvironment(environment)
        upload = self.root / "current-upload"
        shutil.copytree(self.capture_root / "phases", upload / "phases")
        shutil.copytree(self.capture_root / "execution-closure", upload / "execution-closure")
        self.upload_bytes = originals_fixture.archive_tree(upload)
        self.upload_artifact = {
            "id": 700, "name": f"codex-agent-contract-attestation-inputs-{self.producer['tree']}",
            "size_in_bytes": len(self.upload_bytes), "digest": sha256_bytes(self.upload_bytes), "expired": False,
            "created_at": "2026-09-06T10:15:00Z",
            "archive_download_url": f"https://api.github.com/repos/{originals_fixture.REPOSITORY}/actions/artifacts/700/zip",
            "workflow_run": {"id": self.producer["runId"], "head_sha": self.run["head_sha"]},
        }
        self.destination = self.root / "signed-result"

    def api(self, **original_changes):
        original = originals_fixture.ContractOriginalCiCaptureTest.api(self, **original_changes)

        def request(url, token):
            self.assertEqual("not-a-real-token", token)
            if url == self.upload_artifact["archive_download_url"]:
                return self.upload_bytes
            if url == self.upload_artifact["archive_download_url"].removesuffix("/zip"):
                return json.dumps(self.upload_artifact).encode()
            return original(url, token)

        return request

    def attest(self, release_handoffs=(), **workflow_policy):
        return contract_release.attest_contract_ci(
            self.repository_root, self.destination, trusted_source_sha=self.source_sha,
            trusted_workflow_sha=self.pin, artifact_id=self.upload_artifact["id"],
            artifact_sha256=self.upload_artifact["digest"], transport_producer=self.producer,
            contract_version=VERSION, event_payload=self.event, environment=self.environment,
            token="not-a-real-token", release_handoffs=release_handoffs,
            **workflow_policy)

    def assert_public_caller_policy(self):
        policy = self.destination / "caller-policy"
        key_name = f"{self.signing['keyId']}.pub"
        self.assertEqual({"product-signing-keys.json", f"keys/{key_name}"},
                         {record["relativePath"] for record in regular_file_inventory(policy)})
        self.assertEqual(self.keyring.read_bytes(), (policy / "product-signing-keys.json").read_bytes())
        self.assertEqual(self.public_key.read_bytes(), (policy / "keys" / key_name).read_bytes())

    def test_complete_original_ci_pipeline_signs_exact_payload_and_preserves_external_originals(self):
        original_payload = self.payload.read_bytes()
        original_receipts = {phase: path.read_bytes() for phase, path in self.receipts.items()}
        source_inventory = regular_file_inventory(self.source, allow_empty=True)
        with mock.patch("reuse.api_request", side_effect=self.api()):
            self.attest()
        handoff = self.destination / "contract-input"
        stem = f"codex-agent-contract-{VERSION}"
        payload = handoff / f"{stem}.zip"
        self.assertEqual(original_payload, payload.read_bytes())
        self.assertEqual(source_inventory, regular_file_inventory(self.source, allow_empty=True))
        self.assertGreater(self.environment.secret_reads, 0)
        verify_contract_attestation(
            payload, handoff / "execution-closure/receipts/metadata.json", handoff / f"{stem}.attestation.json",
            handoff / f"{stem}.attestation.sig", handoff / "public-key.pub", required_trust_domain="release",
            keyring=self.keyring, keys_directory=self.keys)
        self.assertEqual(10, len(regular_file_inventory(handoff)))
        originals = self.destination / "original-evidence"
        for phase, raw in original_receipts.items():
            self.assertEqual(raw, (handoff / f"execution-closure/receipts/{phase}.json").read_bytes())
            self.assertEqual(raw, (originals / f"original-phases/{phase}/phase-receipt.json").read_bytes())
            self.assertEqual(raw, self.receipts[phase].read_bytes())
        evidence = load_canonical_json_bytes((originals / "transport/original-ci-phases.json").read_bytes())
        self.assertEqual({phase: sha256_bytes(raw) for phase, raw in original_receipts.items()}, evidence["receiptSha256s"])
        self.assertTrue((originals / "contract-input/transport/ci-artifact.json").is_file())
        self.assertTrue((self.destination / "caller.json").is_file())
        self.assert_public_caller_policy()
        secret_bytes = self.private_key.read_bytes()
        self.assertFalse(any(secret_bytes in path.read_bytes() for path in self.destination.rglob("*") if path.is_file()))

    def test_child_workflow_path_and_jobs_are_pinned_before_signing(self):
        path = ".github/workflows/contract-validation.yml"
        binary_job = "product-validation / contract-validation / product-contracts"
        continuation_job = "product-validation / contract-validation / contract-continuation"
        self.run["referenced_workflows"] = [{
            "path": f"{originals_fixture.REPOSITORY}/{path}@{self.pin}", "sha": self.pin,
        }]
        self.jobs[0]["name"] = binary_job
        self.jobs[1]["name"] = continuation_job
        policy = {
            "trusted_contract_workflow_path": path,
            "trusted_contract_binary_job": binary_job,
            "trusted_contract_continuation_job": continuation_job,
        }
        for changes in (
            {"trusted_contract_binary_job": "product-validation / wrong"},
            {"trusted_contract_continuation_job": "product-validation / wrong"},
            {"trusted_contract_workflow_path": ".github/workflows/wrong.yml"},
            {"trusted_contract_workflow_path": None},
        ):
            with self.subTest(changes=changes), \
                    mock.patch("reuse.api_request", side_effect=self.api()), \
                    self.assertRaises(ValueError):
                self.attest(**{**policy, **changes})
            self.assertFalse(self.destination.exists())
            self.assertEqual(0, self.environment.secret_reads)
        with mock.patch("reuse.api_request", side_effect=self.api()):
            self.attest(**policy)
        self.assertTrue((self.destination / "contract-input" / f"codex-agent-contract-{VERSION}.zip").is_file())
        observed = load_canonical_json_bytes((self.destination / "original-evidence/transport/original-ci-phases.json").read_bytes())
        self.assertEqual(self.jobs, observed["observed"][0]["jobs"])

    def test_current_upload_outside_pinned_job_window_cannot_reach_signer(self):
        for created_at in ("2026-09-06T09:59:59Z", "2026-09-06T10:30:01Z"):
            self.upload_artifact["created_at"] = created_at
            with self.subTest(created_at=created_at), \
                    mock.patch("reuse.api_request", side_effect=self.api()), \
                    self.assertRaises(ValueError):
                self.attest()
            self.assertFalse(self.destination.exists())
            self.assertEqual(0, self.environment.secret_reads)

    def test_cli_forwards_pinned_child_policy(self):
        event_path = self.root / "event.json"
        event_path.write_bytes(canonical_json_bytes(self.event))
        arguments = [
            "contract_release.py", "--repository-root", str(self.repository_root),
            "--destination", str(self.destination), "--trusted-source-sha", self.source_sha,
            "--trusted-workflow-sha", self.pin,
            "--trusted-contract-workflow-path", ".github/workflows/contract-validation.yml",
            "--trusted-contract-binary-job", "product-validation / contract-validation / product-contracts",
            "--trusted-contract-continuation-job", "product-validation / contract-validation / contract-continuation",
            "--artifact-id", "700", "--artifact-sha256", self.upload_artifact["digest"],
            "--validation-tree", self.producer["tree"], "--contract-version", VERSION,
        ]
        with mock.patch.object(sys, "argv", arguments), \
                mock.patch.dict("os.environ", {**self.environment.values,
                                                "GITHUB_EVENT_PATH": str(event_path),
                                                "GITHUB_EVENT_NAME": "pull_request",
                                                "GITHUB_REPOSITORY": originals_fixture.REPOSITORY}), \
                mock.patch.object(contract_release, "attest_contract_ci") as attest:
            contract_release.main()
        self.assertEqual(".github/workflows/contract-validation.yml",
                         attest.call_args.kwargs["trusted_contract_workflow_path"])
        self.assertEqual("product-validation / contract-validation / product-contracts",
                         attest.call_args.kwargs["trusted_contract_binary_job"])
        self.assertEqual("product-validation / contract-validation / contract-continuation",
                         attest.call_args.kwargs["trusted_contract_continuation_job"])

    def test_late_prepared_payload_mutation_cannot_be_published(self):
        original = self.payload.read_bytes()
        published = []

        def mutate_then_publish(source, destination, **kwargs):
            payload = Path(source) / "contract-input" / f"codex-agent-contract-{VERSION}.zip"
            payload.write_bytes(payload.read_bytes() + b"late mutation\n")
            published.append(payload)
            actual_publish_regular_tree(source, destination, **kwargs)

        with mock.patch("reuse.api_request", side_effect=self.api()), \
                mock.patch.object(contract_release, "publish_regular_tree", side_effect=mutate_then_publish), \
                self.assertRaises(ValueError):
            self.attest()
        self.assertEqual(1, len(published))
        self.assertFalse(self.destination.exists())
        self.assertEqual(original, self.payload.read_bytes())

    def test_exact_existing_release_handoff_is_forwarded_without_secret_or_signing(self):
        handoff = self.root / "existing-release"
        build_contract_attestation(
            self.payload, self.receipts["metadata"], self.signing, self.private_key, self.public_key,
            handoff, execution_closure=self.capture_root / "execution-closure",
            keyring=self.keyring, keys_directory=self.keys, complete_handoff=True)
        original = regular_file_inventory(handoff)
        self.assertEqual(10, len(original))
        original_receipts = {phase: path.read_bytes() for phase, path in self.receipts.items()}
        current_api = self.api()

        def current_only(url, token):
            if "/actions/runs/71/artifacts?" in url or any(
                f"/actions/artifacts/{artifact['id']}" in url for artifact in self.artifacts.values()
            ):
                raise AssertionError("Exact release evidence must not query original phase uploads")
            return current_api(url, token)

        self.environment.forbid_secret = True
        with mock.patch("reuse.api_request", side_effect=current_only) as api, \
                mock.patch.object(contract_release, "build_contract_attestation",
                                  side_effect=AssertionError("Existing handoff must not be signed again")) as signer:
            self.attest(release_handoffs=(handoff,))
        signer.assert_not_called()
        self.assertEqual(0, self.environment.secret_reads)
        self.assertTrue(any(call.args[0] == self.upload_artifact["archive_download_url"] for call in api.call_args_list))
        self.assertEqual(original, regular_file_inventory(self.destination / "contract-input"))
        self.assertEqual(original, regular_file_inventory(handoff))
        originals = self.destination / "original-evidence"
        self.assertEqual(original, regular_file_inventory(originals / "release-handoffs/0"))
        self.assertFalse((originals / "original-phases").exists())
        evidence = load_canonical_json_bytes((originals / "transport/original-ci-phases.json").read_bytes())
        self.assertEqual([], evidence["observed"])
        self.assertEqual({}, evidence["artifacts"])
        self.assertEqual({phase: 0 for phase in originals_fixture.PHASES}, evidence["releaseAttestations"])
        self.assertEqual({phase: sha256_bytes(raw) for phase, raw in original_receipts.items()}, evidence["receiptSha256s"])
        current = load_canonical_json_bytes((originals / "contract-input/transport/ci-artifact.json").read_bytes())
        self.assertEqual(self.upload_artifact, current["artifact"])
        self.assertEqual(self.producer, current["captureProducer"])
        for phase, raw in original_receipts.items():
            self.assertEqual(raw, self.receipts[phase].read_bytes())
        self.assertTrue((self.destination / "caller.json").is_file())
        self.assert_public_caller_policy()

    def test_missing_or_tampered_original_phase_never_reads_private_secret_or_publishes(self):
        changed = io.BytesIO()
        receipt_changed = False
        with zipfile.ZipFile(io.BytesIO(self.archives["binary"])) as source, zipfile.ZipFile(changed, "w") as output:
            for name in source.namelist():
                raw = source.read(name)
                if name == "phase-receipt.json":
                    receipt_changed = True
                    value = load_canonical_json_bytes(raw)
                    raw = canonical_json_bytes({**value, "producer": {**value["producer"], "runId": 999}})
                output.writestr(name, raw)
        tampered = changed.getvalue()
        self.assertTrue(receipt_changed, "Fixture must mutate the actual original phase receipt")
        self.assertNotEqual(self.archives["binary"], tampered)
        artifacts = copy.deepcopy(self.artifacts)
        artifacts["binary"].update(size_in_bytes=len(tampered), digest=sha256_bytes(tampered))
        cases = (
            {"artifacts": {phase: artifact for phase, artifact in self.artifacts.items() if phase != "binary"}},
            {"artifacts": artifacts, "details": artifacts, "archives": {**self.archives, "binary": tampered}},
        )
        self.environment.forbid_secret = True
        for changes in cases:
            with self.subTest(changes=tuple(changes)), mock.patch("reuse.api_request", side_effect=self.api(**changes)):
                with self.assertRaises(ValueError):
                    self.attest()
            self.assertEqual(0, self.environment.secret_reads)
            self.assertFalse(self.destination.exists())

    def test_private_key_must_match_tracked_public_release_policy(self):
        private, _, _ = generate_development_key(self.root / "wrong-signer")
        self.environment.values[SECRET] = private.read_text()
        with mock.patch("reuse.api_request", side_effect=self.api()), self.assertRaises(ValueError):
            self.attest()
        self.assertGreater(self.environment.secret_reads, 0)
        self.assertFalse(self.destination.exists())
