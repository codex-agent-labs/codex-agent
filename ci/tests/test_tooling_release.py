"""Synthetic protected-tooling caller checks; never hosted signing acceptance."""

from argparse import Namespace
from collections.abc import Mapping
import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile

from ci import tooling_release
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory,
    sha256_bytes,
)
from ci.products.signatures import generate_development_key
from ci.products.tooling import JAR, verified_tooling_capture
from ci.receipt import create_receipt
from ci.tests import test_product_tooling as tooling_fixture


REPOSITORY = "codex-agent-labs/codex-agent"
WORKFLOW_PIN = "c" * 40
SECRET = "CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"


def archive_tree(root: Path) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(value for value in root.rglob("*") if value.is_file()):
            archive.writestr(path.relative_to(root).as_posix(), path.read_bytes())
    return output.getvalue()


class ObservedEnvironment(Mapping):
    def __init__(self, values):
        self.values = dict(values)
        self.secret_reads = 0
        self.forbid_secret = False

    def __getitem__(self, key):
        if key == SECRET:
            self.secret_reads += 1
            if self.forbid_secret:
                raise AssertionError("Private key was read before tooling admission")
        return self.values[key]

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)


@unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH signing tool unavailable")
class ToolingReleaseTest(unittest.TestCase):
    def setUp(self):
        fixture = tooling_fixture.ToolingAttestationTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.fixture = fixture
        self.repository = fixture.root.resolve()
        self.plan_path, self.lane = fixture.plan_path, fixture.lane
        self.plan = json.loads(self.plan_path.read_bytes())
        self.producer = {
            "repository": self.plan["repository"], "workflowPath": ".github/workflows/ci.yml",
            "commit": self.plan["validationCommit"], "tree": self.plan["validationTree"],
            "event": self.plan["event"], "runId": 101, "runAttempt": 2,
            "pullRequest": self.plan["pullRequest"],
        }
        self.name = f"codex-agent-ci-contracts-{self.producer['tree']}"
        create_receipt(Namespace(
            plan=self.plan_path, lane="contracts", output=self.lane,
            workflow_path=self.producer["workflowPath"], artifact_name=self.name,
            run_id=self.producer["runId"], run_attempt=self.producer["runAttempt"],
            runner=["os=synthetic-fixture", "arch=synthetic-fixture"],
            toolchain=["java=synthetic-fixture", "validationActions=build,metadata,test"],
            artifact=[f"{JAR}=release-tooling"], evidence=[],
        ))

        self.private_key, self.public_key, development = generate_development_key(
            self.repository / "protected-signer")
        self.signing = {**development, "trustDomain": "release"}
        self.keys = self.repository / "gradle/release/keys"
        self.keys.mkdir(parents=True, exist_ok=True)
        (self.keys / f"{self.signing['keyId']}.pub").write_bytes(self.public_key.read_bytes())
        self.keyring = self.repository / "gradle/release/product-signing-keys.json"
        self.keyring.write_bytes(canonical_json_bytes({
            "schemaVersion": 1, "namespace": self.signing["namespace"],
            "algorithm": self.signing["algorithm"], "trustDomain": "release",
            "activeKey": {name: self.signing[name] for name in ("keyId", "fingerprint")},
            "retiredKeys": [],
        }))
        subprocess.run(("git", "add", "--", "gradle/release"), cwd=self.repository, check=True)
        subprocess.run(("git", "commit", "-qm", "tracked protected tooling policy"),
                       cwd=self.repository, check=True)
        self.source_sha = subprocess.run(("git", "rev-parse", "HEAD"), cwd=self.repository,
            check=True, capture_output=True, text=True).stdout.strip()

        head = self.plan["headCommit"]
        self.event = fixture.pull_request_event(
            base=self.plan["baseCommit"], target=self.plan["headCommit"],
            pull_request=self.producer["pullRequest"],
        )
        self.environment = ObservedEnvironment({
            "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": REPOSITORY,
            "GITHUB_EVENT_NAME": self.producer["event"], "GITHUB_SHA": self.producer["commit"],
            "GITHUB_RUN_ID": str(self.producer["runId"]),
            "GITHUB_RUN_ATTEMPT": str(self.producer["runAttempt"]),
            "GITHUB_REF": f"refs/pull/{self.producer['pullRequest']}/merge",
            SECRET: self.private_key.read_text(),
        })
        self.run = {
            "id": self.producer["runId"], "run_attempt": self.producer["runAttempt"],
            "path": self.producer["workflowPath"], "event": self.producer["event"],
            "status": "completed", "conclusion": "success", "head_sha": head,
            "repository": {"full_name": REPOSITORY, "fork": False},
            "head_repository": {"full_name": REPOSITORY, "fork": False},
            "pull_requests": [{"number": self.producer["pullRequest"],
                "base": {"sha": self.plan["baseCommit"]}, "head": {"sha": head}}],
            "referenced_workflows": [{
                "path": f"{REPOSITORY}/.github/workflows/product-validation.yml@{WORKFLOW_PIN}",
                "sha": WORKFLOW_PIN,
            }],
        }
        self.commit = {"sha": self.producer["commit"], "tree": {"sha": self.producer["tree"]},
                       "parents": [{"sha": self.plan["baseCommit"]}, {"sha": head}]}
        self.jobs = [{
            "id": 801, "name": "product-validation / product-contracts",
            "run_id": self.producer["runId"], "head_sha": head,
            "status": "completed", "conclusion": "success",
            "started_at": "2026-09-13T08:00:00Z", "completed_at": "2026-09-13T08:30:00Z",
        }]
        self.archive = archive_tree(self.lane)
        self.artifact = self.artifact_for(self.archive)
        output = tempfile.TemporaryDirectory(prefix="tooling-release-output-")
        self.addCleanup(output.cleanup)
        self.destination = Path(output.name).resolve() / "result"

    def artifact_for(self, raw):
        url = "https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/701"
        return {
            "id": 701, "name": self.name, "size_in_bytes": len(raw),
            "digest": sha256_bytes(raw), "expired": False,
            "created_at": "2026-09-13T08:15:00Z", "archive_download_url": f"{url}/zip",
            "workflow_run": {"id": self.producer["runId"], "head_sha": self.run["head_sha"]},
        }

    def api(self, *, run=None, jobs=None, artifacts=None, artifact=None, archive=None):
        selected_run = self.run if run is None else run
        selected_jobs = self.jobs if jobs is None else jobs
        selected_artifact = self.artifact if artifact is None else artifact
        listed = [selected_artifact] if artifacts is None else artifacts
        selected_archive = self.archive if archive is None else archive

        def request(url, token):
            self.assertEqual("not-a-real-token", token)
            run_root = f"https://api.github.com/repos/{REPOSITORY}/actions/runs/{self.producer['runId']}"
            if url == f"{run_root}/attempts/{self.producer['runAttempt']}":
                return json.dumps(selected_run).encode()
            if url == f"https://api.github.com/repos/{REPOSITORY}/git/commits/{self.producer['commit']}":
                return json.dumps(self.commit).encode()
            if url.startswith(f"{run_root}/attempts/{self.producer['runAttempt']}/jobs?"):
                return json.dumps({"jobs": selected_jobs}).encode()
            if url.startswith(f"{run_root}/artifacts?"):
                return json.dumps({"artifacts": listed}).encode()
            detail = selected_artifact["archive_download_url"].removesuffix("/zip")
            if url == detail:
                return json.dumps(selected_artifact).encode()
            if url == selected_artifact["archive_download_url"]:
                return selected_archive
            raise AssertionError(f"Unexpected API request: {url}")

        return request

    def attest(self, **changes):
        arguments = {
            "trusted_source_sha": self.source_sha, "trusted_workflow_sha": WORKFLOW_PIN,
            "transport_producer": self.producer, "event_payload": self.event,
            "environment": self.environment, "token": "not-a-real-token",
        }
        arguments.update(changes)
        return tooling_release.attest_tooling_ci(
            self.repository, self.plan_path, self.destination, **arguments)

    def test_signs_exact_original_ci_closure_and_preserves_external_transport(self):
        before_lane = regular_file_inventory(self.lane, allow_empty=True)
        before_plan = regular_file_inventory(self.plan_path.parent, allow_empty=True)
        with mock.patch("reuse.api_request", side_effect=self.api()):
            caller = self.attest()
        evidence = self.destination / "tooling-evidence"
        policy = self.destination / "caller-policy"
        key = policy / f"keys/{self.signing['keyId']}.pub"
        with verified_tooling_capture(evidence, self.repository, key,
                required_trust_domain="release", keyring=policy / self.keyring.name,
                keys_directory=policy / "keys") as jar:
            self.assertEqual((self.lane / JAR).read_bytes(), jar.read_bytes())
        self.assertEqual(before_lane, regular_file_inventory(evidence / "original/lane", allow_empty=True))
        self.assertEqual(self.plan_path.read_bytes(), (evidence / "original/plan.json").read_bytes())
        self.assertEqual(before_lane, regular_file_inventory(self.lane, allow_empty=True))
        self.assertEqual(before_plan, regular_file_inventory(self.plan_path.parent, allow_empty=True))
        self.assertEqual(self.archive, (self.destination / "transport/original-ci.zip").read_bytes())
        transport = load_canonical_json_bytes((self.destination / "transport/original-ci.json").read_bytes())
        self.assertEqual(self.artifact, transport["artifact"])
        self.assertEqual(self.producer, transport["producer"])
        self.assertEqual(caller, load_canonical_json_bytes((self.destination / "caller.json").read_bytes()))
        self.assertGreater(self.environment.secret_reads, 0)
        secret = self.private_key.read_bytes()
        self.assertFalse(any(secret in path.read_bytes() for path in self.destination.rglob("*") if path.is_file()))

    def test_secret_transport_without_final_newline_still_signs(self):
        self.environment.values[SECRET] = self.environment.values[SECRET].rstrip("\n")
        with mock.patch("reuse.api_request", side_effect=self.api()):
            self.attest()
        self.assertTrue((self.destination / "caller.json").is_file())

    def test_child_workflow_pin_authenticates_original_tooling_job(self):
        path = ".github/workflows/contract-validation.yml"
        job = "product-validation / contract-validation / product-contracts"
        self.run["referenced_workflows"] = [{
            "path": f"{REPOSITORY}/{path}@{WORKFLOW_PIN}", "sha": WORKFLOW_PIN,
        }]
        self.jobs[0]["name"] = job + " (contracts, true, true, true)"
        with mock.patch("reuse.api_request", side_effect=self.api()):
            self.attest(trusted_workflow_path=path, trusted_job_name=job)
        self.assertTrue((self.destination / "tooling-evidence").is_dir())

    def test_partial_child_workflow_pin_fails_before_secret_access(self):
        with self.assertRaisesRegex(ValueError, "pinned together"):
            self.attest(trusted_workflow_path=".github/workflows/contract-validation.yml")
        self.assertEqual(0, self.environment.secret_reads)
        self.assertFalse(self.destination.exists())

    def test_empty_child_job_pin_cannot_fall_back_to_legacy_job(self):
        with mock.patch("reuse.api_request", side_effect=self.api()), self.assertRaises(ValueError):
            self.attest(
                trusted_workflow_path=".github/workflows/contract-validation.yml",
                trusted_job_name="")
        self.assertEqual(0, self.environment.secret_reads)
        self.assertFalse(self.destination.exists())

    def test_unobserved_child_workflow_pin_fails_before_secret_access(self):
        with mock.patch("reuse.api_request", side_effect=self.api()), self.assertRaises(ValueError):
            self.attest(
                trusted_workflow_path=".github/workflows/contract-validation.yml",
                trusted_job_name="product-validation / contract-validation / product-contracts")
        self.assertEqual(0, self.environment.secret_reads)
        self.assertFalse(self.destination.exists())

    def test_invalid_context_fails_before_network_or_secret(self):
        self.environment.forbid_secret = True
        changed = copy.deepcopy(self.event)
        changed["pull_request"]["draft"] = True
        with mock.patch("reuse.api_request", side_effect=AssertionError("invalid context contacted API")), \
                self.assertRaises(ValueError):
            self.attest(event_payload=changed)
        self.assertEqual(0, self.environment.secret_reads)
        self.assertFalse(self.destination.exists())

    def test_tampered_upload_ambiguous_job_and_wrong_attempt_fail_before_secret(self):
        changed_lane = Path(tempfile.mkdtemp(prefix="changed-tooling-lane-"))
        self.addCleanup(shutil.rmtree, changed_lane)
        shutil.copytree(self.lane, changed_lane, dirs_exist_ok=True)
        (changed_lane / JAR).write_bytes(b"tampered original executable\n")
        tampered = archive_tree(changed_lane)
        tampered_artifact = self.artifact_for(tampered)
        cases = (
            {"archive": tampered, "artifact": tampered_artifact},
            {"jobs": [*self.jobs, dict(self.jobs[0], id=802)]},
            {"jobs": [*self.jobs, dict(self.jobs[0], id=802,
                                       name=self.jobs[0]["name"] + " (contracts, true, true, true)")]},
            {"run": {**self.run, "run_attempt": 1}},
        )
        self.environment.forbid_secret = True
        for changes in cases:
            with self.subTest(changes=tuple(changes)), \
                    mock.patch("reuse.api_request", side_effect=self.api(**changes)), \
                    self.assertRaises(ValueError):
                self.attest()
            self.assertEqual(0, self.environment.secret_reads)
            self.assertFalse(self.destination.exists())

    def test_exact_release_envelope_is_reused_without_secret_or_resigning(self):
        with mock.patch("reuse.api_request", side_effect=self.api()):
            self.attest()
        retained = Path(tempfile.mkdtemp(prefix="retained-tooling-")).resolve()
        self.addCleanup(shutil.rmtree, retained)
        shutil.copytree(self.destination / "tooling-evidence", retained, dirs_exist_ok=True)
        original = regular_file_inventory(retained, allow_empty=True)
        shutil.rmtree(self.destination)
        self.environment.secret_reads = 0
        self.environment.forbid_secret = True
        with mock.patch("reuse.api_request", side_effect=self.api()), \
                mock.patch.object(tooling_release, "sign_manifest",
                    side_effect=AssertionError("exact release envelope was re-signed")) as signer:
            self.attest(release_handoffs=(retained,))
        signer.assert_not_called()
        self.assertEqual(0, self.environment.secret_reads)
        self.assertEqual(original, regular_file_inventory(retained, allow_empty=True))
        self.assertEqual(original, regular_file_inventory(self.destination / "tooling-evidence", allow_empty=True))


class ToolingReleaseCliTest(unittest.TestCase):
    def test_cli_forwards_fixed_context_and_rejects_authority_overrides(self):
        with tempfile.TemporaryDirectory(prefix="tooling-release-cli-") as temporary:
            root = Path(temporary).resolve()
            event = root / "event.json"
            event.write_text('{"number":17}\n', encoding="utf-8")
            argv = [
                "--repository-root", str(root / "repository"),
                "--plan", str(root / "plan.json"),
                "--destination", str(root / "output"),
                "--trusted-source-sha", "a" * 40,
                "--trusted-workflow-sha", "b" * 40,
                "--validation-tree", "c" * 40,
                "--release-handoff", str(root / "retained"),
            ]
            environment = {
                "GITHUB_EVENT_PATH": str(event),
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_REPOSITORY": REPOSITORY,
                "GITHUB_SHA": "d" * 40,
                "GITHUB_RUN_ID": "81",
                "GITHUB_RUN_ATTEMPT": "3",
            }
            with mock.patch.dict(os.environ, environment, clear=True), \
                    mock.patch.object(tooling_release, "attest_tooling_ci", return_value={}) as attest:
                self.assertEqual(0, tooling_release.main(argv))
                positional, keywords = attest.call_args
                self.assertEqual((root / "repository", root / "plan.json", root / "output"), positional)
                self.assertEqual("a" * 40, keywords["trusted_source_sha"])
                self.assertEqual("b" * 40, keywords["trusted_workflow_sha"])
                self.assertEqual({
                    "repository": REPOSITORY,
                    "workflowPath": ".github/workflows/ci.yml",
                    "commit": "d" * 40,
                    "tree": "c" * 40,
                    "event": "pull_request",
                    "runId": 81,
                    "runAttempt": 3,
                    "pullRequest": 17,
                }, keywords["transport_producer"])
                self.assertEqual({"number": 17}, keywords["event_payload"])
                self.assertIs(os.environ, keywords["environment"])
                self.assertEqual([root / "retained"], keywords["release_handoffs"])
                self.assertIsNone(keywords["trusted_workflow_path"])
                self.assertIsNone(keywords["trusted_job_name"])

                attest.reset_mock()
                self.assertEqual(0, tooling_release.main([
                    *argv, "--trusted-workflow-path", ".github/workflows/contract-validation.yml",
                    "--trusted-job-name", "product-validation / contract-validation / product-contracts",
                ]))
                self.assertEqual(".github/workflows/contract-validation.yml",
                                 attest.call_args.kwargs["trusted_workflow_path"])
                self.assertEqual("product-validation / contract-validation / product-contracts",
                                 attest.call_args.kwargs["trusted_job_name"])

                attest.reset_mock()
                for forbidden in ("--private-key", "--transport-producer"):
                    with self.subTest(forbidden=forbidden), \
                            mock.patch("sys.stderr", new=io.StringIO()), \
                            self.assertRaises(SystemExit) as failure:
                        tooling_release.main([*argv, forbidden, "untrusted"])
                    self.assertEqual(2, failure.exception.code)
                attest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
