"""Synthetic tooling upload capture checks; never hosted execution acceptance."""

from argparse import Namespace
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

from ci import tooling_capture
from ci.products.inventory import (
    canonical_json_bytes, git_regular_blob_bytes, load_canonical_json_bytes,
    regular_file_inventory, sha256_bytes,
)
from ci.products.signatures import generate_development_key
from ci.products.tooling import JAR, verified_tooling_capture
from ci.receipt import create_receipt
from ci.tests import test_tooling_release as release_fixture


WORKFLOW_PIN = "c" * 40
TOKEN = "not-a-real-token"


def archive_tree(root: Path) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            archive.writestr(path.relative_to(root).as_posix(), path.read_bytes())
    return output.getvalue()


@unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH signing tool unavailable")
class ToolingCaptureTest(unittest.TestCase):
    def setUp(self):
        class SeededToolingFixture(release_fixture.tooling_fixture.ToolingAttestationTest):
            def make_plan(self, *args, **kwargs):
                if not (self.root / "ci/products/sdk_package.py").exists():
                    self.commit("ci/products/sdk_package.py", "# synthetic packaged verifier resource\n")
                return super().make_plan(*args, **kwargs)

        with mock.patch.object(release_fixture.tooling_fixture, "ToolingAttestationTest", SeededToolingFixture):
            source = release_fixture.ToolingReleaseTest(methodName="runTest")
            source.setUp()
        self.addCleanup(source.doCleanups)
        self.addCleanup(source.tearDown)
        self.source = source

        jar = source.lane / JAR
        with zipfile.ZipFile(jar, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(
                "python/ci/products/sdk_package.py",
                git_regular_blob_bytes(source.repository, source.producer["commit"],
                                       "ci/products/sdk_package.py", max_bytes=64 * 1024 * 1024),
            )
        create_receipt(Namespace(
            plan=source.plan_path, lane="contracts", output=source.lane,
            workflow_path=source.producer["workflowPath"], artifact_name=source.name,
            run_id=source.producer["runId"], run_attempt=source.producer["runAttempt"],
            runner=["os=synthetic-fixture", "arch=synthetic-fixture"],
            toolchain=["java=synthetic-fixture", "validationActions=build,metadata,test"],
            artifact=[f"{JAR}=release-tooling"], evidence=[],
        ))
        source.archive = archive_tree(source.lane)
        source.artifact = source.artifact_for(source.archive)
        with mock.patch("reuse.api_request", side_effect=source.api()):
            source.attest()

        temporary = tempfile.TemporaryDirectory(prefix="tooling-capture-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.java = self.root / "installed-java"
        self.java.write_bytes(b"caller-selected Java; deliberately not executable\n")
        self.destination = self.root / "captured"
        self.producer = copy.deepcopy(source.producer)
        self.name = (f"codex-agent-release-tooling-{self.producer['tree']}"
                     f"-attempt-{self.producer['runAttempt']}")
        self.run = copy.deepcopy(source.run)
        self.jobs = [{
            "id": 991, "name": "product-validation / tooling-attestation",
            "run_id": self.producer["runId"], "head_sha": self.run["head_sha"],
            "status": "completed", "conclusion": "success",
            "started_at": "2026-09-13T09:00:00Z", "completed_at": "2026-09-13T09:30:00Z",
        }]
        self.raw = archive_tree(source.destination)
        self.artifact = self.artifact_for(self.raw)

    def artifact_for(self, raw: bytes, **changes) -> dict:
        identifier = 901
        url = f"https://api.github.com/repos/{release_fixture.REPOSITORY}/actions/artifacts/{identifier}"
        value = {
            "id": identifier, "name": self.name, "size_in_bytes": len(raw),
            "digest": sha256_bytes(raw), "expired": False,
            "created_at": "2026-09-13T09:15:00Z", "archive_download_url": f"{url}/zip",
            "workflow_run": {"id": self.producer["runId"], "head_sha": self.run["head_sha"]},
        }
        value.update(changes)
        return value

    def api(self, *, run=None, jobs=None, artifact=None, raw=None):
        selected_run = self.run if run is None else run
        selected_jobs = self.jobs if jobs is None else jobs
        selected_artifact = self.artifact if artifact is None else artifact
        selected_raw = self.raw if raw is None else raw

        def request(url, token):
            self.assertEqual(TOKEN, token)
            run_root = (f"https://api.github.com/repos/{release_fixture.REPOSITORY}/actions/runs/"
                        f"{self.producer['runId']}")
            if url == f"{run_root}/attempts/{self.producer['runAttempt']}":
                return json.dumps(selected_run).encode()
            if url == (f"https://api.github.com/repos/{release_fixture.REPOSITORY}/git/commits/"
                       f"{self.producer['commit']}"):
                return json.dumps(self.source.commit).encode()
            if url.startswith(f"{run_root}/attempts/{self.producer['runAttempt']}/jobs?"):
                return json.dumps({"jobs": selected_jobs}).encode()
            detail = selected_artifact["archive_download_url"].removesuffix("/zip")
            if url == detail:
                return json.dumps(selected_artifact).encode()
            if url == selected_artifact["archive_download_url"]:
                return selected_raw
            raise AssertionError(f"Unexpected API request: {url}")

        return request

    def capture(self, *, raw=None, artifact=None, policy_revision=None, api=None):
        selected_raw = self.raw if raw is None else raw
        selected_artifact = self.artifact_for(selected_raw) if artifact is None else artifact
        with mock.patch("reuse.api_request", side_effect=api or self.api(
                artifact=selected_artifact, raw=selected_raw)):
            return tooling_capture.capture_tooling_ci(
                self.destination, self.source.repository,
                artifact_id=selected_artifact["id"], artifact_sha256=selected_artifact["digest"],
                transport_producer=self.producer, trusted_workflow_sha=WORKFLOW_PIN,
                policy_revision=policy_revision or self.source.source_sha,
                java_executable=self.java, token=TOKEN,
            )

    def uploaded_copy(self) -> Path:
        root = self.root / "uploaded-copy"
        shutil.copytree(self.source.destination, root)
        return root

    def test_captures_exact_evidence_with_git_policy_and_never_executes_or_signs(self):
        uploaded = self.uploaded_copy()
        (uploaded / "caller-policy/product-signing-keys.json").write_bytes(b"untrusted upload policy\n")
        for key in (uploaded / "caller-policy/keys").iterdir():
            key.write_bytes(b"untrusted upload key\n")
        raw = archive_tree(uploaded)
        original = regular_file_inventory(self.source.destination / "tooling-evidence", allow_empty=True)
        signer_module = tooling_capture.verified_tooling_capture.__module__
        with mock.patch(f"{signer_module}.sign_manifest",
                        side_effect=AssertionError("capture attempted to sign")) as signer:
            policy = self.capture(raw=raw)
        signer.assert_not_called()
        self.assertEqual(original, regular_file_inventory(self.destination / "evidence", allow_empty=True))
        self.assertEqual(
            (self.source.destination / "tooling-evidence/original/lane/lane-receipt.json").read_bytes(),
            (self.destination / "evidence/original/lane/lane-receipt.json").read_bytes(),
        )
        self.assertEqual(raw, (self.destination / "transport/original-upload.zip").read_bytes())
        self.assertEqual(policy, load_canonical_json_bytes(
            (self.destination / "tooling-policy.json").read_bytes()))
        self.assertEqual(self.source.keyring.read_bytes(),
                         (self.destination / "policy/product-signing-keys.json").read_bytes())
        self.assertNotEqual(b"untrusted upload key\n", Path(policy["publicKey"]).read_bytes())
        secret = self.source.private_key.read_bytes()
        self.assertFalse(any(secret in path.read_bytes()
                             for path in self.destination.rglob("*") if path.is_file()))
        with verified_tooling_capture(
                Path(policy["evidence"]), self.source.repository, Path(policy["publicKey"]),
                required_trust_domain="release", keyring=Path(policy["keyring"]),
                keys_directory=Path(policy["keysDirectory"]), policy_revision=self.source.source_sha) as jar:
            self.assertEqual((self.source.lane / JAR).read_bytes(), jar.read_bytes())
        capture = load_canonical_json_bytes((self.destination / "transport/capture.json").read_bytes())
        self.assertEqual(self.artifact_for(raw), capture["artifact"])
        self.assertEqual(self.producer, capture["captureProducer"])

    def test_wrong_git_key_and_tampered_signed_evidence_never_publish_policy(self):
        _, public, signing = generate_development_key(self.source.repository / "replacement-key")
        signing = {**signing, "trustDomain": "release"}
        keys = self.source.repository / "gradle/release/keys"
        shutil.rmtree(keys)
        keys.mkdir()
        (keys / f"{signing['keyId']}.pub").write_bytes(public.read_bytes())
        (self.source.repository / "gradle/release/product-signing-keys.json").write_bytes(
            canonical_json_bytes({
                "schemaVersion": 1, "namespace": signing["namespace"],
                "algorithm": signing["algorithm"], "trustDomain": "release",
                "activeKey": {name: signing[name] for name in ("keyId", "fingerprint")},
                "retiredKeys": [],
            }))
        subprocess.run(("git", "add", "--", "gradle/release"), cwd=self.source.repository, check=True)
        subprocess.run(("git", "commit", "-qm", "replacement policy"),
                       cwd=self.source.repository, check=True)
        revision = subprocess.run(("git", "rev-parse", "HEAD"), cwd=self.source.repository,
                                  check=True, capture_output=True, text=True).stdout.strip()
        with self.assertRaises(ValueError):
            self.capture(policy_revision=revision)
        self.assertFalse(self.destination.exists())

        uploaded = self.uploaded_copy()
        path = uploaded / f"tooling-evidence/original/lane/{JAR}"
        path.write_bytes(path.read_bytes() + b"tampered\n")
        with self.assertRaises(ValueError):
            self.capture(raw=archive_tree(uploaded), policy_revision=self.source.source_sha)
        self.assertFalse(self.destination.exists())

    def test_wrong_attempt_ambiguous_job_and_out_of_window_upload_never_publish(self):
        cases = (
            self.api(run={**self.run, "run_attempt": 1}),
            self.api(jobs=[*self.jobs, dict(self.jobs[0], id=992)]),
            self.api(artifact=self.artifact_for(self.raw, created_at="2026-09-13T10:00:00Z")),
        )
        for api in cases:
            with self.subTest(api=api), self.assertRaises(ValueError):
                self.capture(api=api)
            self.assertFalse(self.destination.exists())


class ToolingCaptureCliTest(unittest.TestCase):
    def test_cli_forwards_caller_inputs_and_rejects_key_overrides(self):
        with tempfile.TemporaryDirectory(prefix="tooling-capture-cli-") as temporary:
            root = Path(temporary).resolve()
            producer = root / "producer.json"
            value = {"repository": "fixture/repository", "tree": "a" * 40}
            producer.write_bytes(canonical_json_bytes(value))
            argv = [
                "--destination", str(root / "output"), "--repository-root", str(root / "repository"),
                "--transport-producer", str(producer), "--java-executable", str(root / "java"),
                "--artifact-id", "91", "--artifact-sha256", "sha256:" + "b" * 64,
                "--trusted-workflow-sha", "c" * 40, "--policy-revision", "d" * 40,
            ]
            with mock.patch.dict(os.environ, {"GITHUB_TOKEN": TOKEN}, clear=True), \
                    mock.patch.object(tooling_capture, "capture_tooling_ci") as capture:
                self.assertEqual(0, tooling_capture.main(argv))
                capture.assert_called_once_with(
                    root / "output", root / "repository", artifact_id=91,
                    artifact_sha256="sha256:" + "b" * 64, transport_producer=value,
                    trusted_workflow_sha="c" * 40, policy_revision="d" * 40,
                    java_executable=root / "java", token=TOKEN,
                )
                capture.reset_mock()
                for option in ("--private-key", "--keyring", "--keys-directory"):
                    with self.subTest(option=option), mock.patch("sys.stderr", new=io.StringIO()), \
                            self.assertRaises(SystemExit) as failure:
                        tooling_capture.main([*argv, option, "untrusted"])
                    self.assertEqual(2, failure.exception.code)
                capture.assert_not_called()


if __name__ == "__main__":
    unittest.main()
