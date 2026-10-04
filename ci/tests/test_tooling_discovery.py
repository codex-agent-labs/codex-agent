"""Synthetic signed-tooling discovery checks; never hosted execution acceptance."""

import io
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from ci import tooling_discovery
from ci.products.inventory import load_canonical_json_bytes, sha256_bytes
from ci.tests import test_tooling_capture as capture_fixture


TOKEN = "not-a-real-token"
WORKFLOW_PIN = "c" * 40


@unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH signing tool unavailable")
class ToolingDiscoveryTest(unittest.TestCase):
    def test_original_nested_workflow_survives_pin_rotation_and_rejects_mismatch(self):
        prior = '084542245fba5fca34be4ad52e8113ac3f701f16'
        run = copy.deepcopy(self.fixture.run)
        run['referenced_workflows'] = [
            {'path': f'codex-agent-labs/codex-agent/.github/workflows/{name}@{prior}', 'sha': prior}
            for name in ('product-validation.yml', 'contract-validation.yml')]
        with mock.patch.object(tooling_discovery, 'api_json', return_value=run):
            policy = tooling_discovery._original_tooling_workflow(self.fixture.producer, WORKFLOW_PIN, TOKEN)
            self.assertEqual(prior, policy['trusted_workflow_sha'])
            self.assertEqual('.github/workflows/contract-validation.yml', policy['trusted_workflow_path'])
            run['referenced_workflows'][1]['sha'] = WORKFLOW_PIN
            with self.assertRaises(ValueError):
                tooling_discovery._original_tooling_workflow(self.fixture.producer, WORKFLOW_PIN, TOKEN)
            run['referenced_workflows'][0]['sha'] = WORKFLOW_PIN
            with self.assertRaises(ValueError):
                tooling_discovery._original_tooling_workflow(self.fixture.producer, WORKFLOW_PIN, TOKEN)

    def setUp(self):
        fixture = capture_fixture.ToolingCaptureTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.addCleanup(fixture.tearDown)
        self.fixture = fixture
        temporary = tempfile.TemporaryDirectory(prefix="tooling-discovery-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.destination = self.root / "discovery"
        self.listed_runs = []

    def artifact(self, identifier: int, raw: bytes, *, name=None, run_id=None, expired=False):
        producer = self.fixture.producer
        run_id = producer["runId"] if run_id is None else run_id
        url = (f"https://api.github.com/repos/{capture_fixture.release_fixture.REPOSITORY}"
               f"/actions/artifacts/{identifier}")
        return {
            "id": identifier,
            "name": name or self.fixture.name,
            "size_in_bytes": len(raw),
            "digest": sha256_bytes(raw),
            "expired": expired,
            "created_at": "2026-09-13T09:15:00Z",
            "archive_download_url": f"{url}/zip",
            "workflow_run": {"id": run_id, "head_sha": self.fixture.run["head_sha"]},
        }

    def api(self, listings, payloads):
        fixture = self.fixture

        def request(url, token):
            self.assertEqual(TOKEN, token)
            prefix = (f"https://api.github.com/repos/{capture_fixture.release_fixture.REPOSITORY}"
                      "/actions")
            if url.startswith(f"{prefix}/runs/") and "/artifacts?" in url:
                run_id = int(url.removeprefix(f"{prefix}/runs/").split("/", 1)[0])
                self.listed_runs.append(run_id)
                return json.dumps({"artifacts": listings.get(run_id, [])}).encode()
            run_root = f"{prefix}/runs/{fixture.producer['runId']}"
            if url == f"{run_root}/attempts/{fixture.producer['runAttempt']}":
                return json.dumps(fixture.run).encode()
            if url == (f"https://api.github.com/repos/{capture_fixture.release_fixture.REPOSITORY}"
                       f"/git/commits/{fixture.producer['commit']}"):
                return json.dumps(fixture.source.commit).encode()
            if url.startswith(f"{run_root}/attempts/{fixture.producer['runAttempt']}/jobs?"):
                return json.dumps({"jobs": fixture.jobs}).encode()
            for artifact, raw in payloads.values():
                detail = artifact["archive_download_url"].removesuffix("/zip")
                if url == detail:
                    return json.dumps(artifact).encode()
                if url == artifact["archive_download_url"]:
                    return raw
            raise AssertionError(f"Unexpected API request: {url}")

        return request

    def discover(self, run_ids, api):
        with mock.patch("reuse.api_request", side_effect=api):
            return tooling_discovery.discover_tooling_ci(
                self.destination, self.fixture.source.repository,
                candidate_run_ids=run_ids, trusted_workflow_sha=WORKFLOW_PIN,
                policy_revision=self.fixture.source.source_sha,
                java_executable=self.fixture.java, token=TOKEN,
            )

    def test_deduplicates_ordered_runs_skips_bad_then_selects_full_signed_candidate(self):
        malformed = b"not a ZIP"
        bad = self.artifact(910, malformed)
        tampered_upload = self.root / "tampered-upload"
        shutil.copytree(self.fixture.source.destination, tampered_upload)
        tampered_jar = tampered_upload / (
            "tooling-evidence/original/lane/payload/gradle/build-logic/build/libs/"
            "codex-agent-release-tooling.jar"
        )
        tampered_jar.write_bytes(tampered_jar.read_bytes() + b"tampered signed original\n")
        tampered_raw = capture_fixture.archive_tree(tampered_upload)
        tampered = self.artifact(911, tampered_raw)
        uploaded = self.fixture.uploaded_copy()
        (uploaded / "caller-policy/product-signing-keys.json").write_bytes(b"untrusted locator policy\n")
        for key in (uploaded / "caller-policy/keys").iterdir():
            key.write_bytes(b"untrusted locator key\n")
        valid_raw = capture_fixture.archive_tree(uploaded)
        valid = self.artifact(912, valid_raw)
        ignored = self.artifact(913, valid_raw, name="unrelated-artifact")
        expired = self.artifact(914, valid_raw, expired=True)
        listings = {404: [], self.fixture.producer["runId"]: [ignored, expired, bad, tampered, valid]}
        payloads = {910: (bad, malformed), 911: (tampered, tampered_raw), 912: (valid, valid_raw)}

        report = self.discover((404, 404, self.fixture.producer["runId"], 404,
                                self.fixture.producer["runId"]), self.api(listings, payloads))

        self.assertEqual([404, self.fixture.producer["runId"]], self.listed_runs)
        self.assertEqual(["miss", "miss", "selected"],
                         [item["result"] for item in report["attempts"]])
        self.assertTrue(report["attempts"][0]["reason"])
        self.assertIn("integrity-mismatched receipt file", report["attempts"][1]["reason"])
        self.assertEqual([910, 911, 912], [item["artifactId"] for item in report["attempts"]])
        self.assertEqual({
            "artifactId": 912,
            "artifactSha256": valid["digest"],
            "transportProducer": self.fixture.producer,
        }, report["selected"])
        self.assertEqual(report, load_canonical_json_bytes(
            (self.destination / "discovery.json").read_bytes()))
        policy = report["toolingPolicy"]
        self.assertEqual(str(self.destination / "capture/evidence"), policy["evidence"])
        self.assertEqual(self.fixture.source.keyring.read_bytes(),
                         (self.destination / "capture/policy/product-signing-keys.json").read_bytes())
        self.assertNotEqual(b"untrusted locator key\n", Path(policy["publicKey"]).read_bytes())
        self.assertEqual(valid_raw,
                         (self.destination / "capture/transport/original-upload.zip").read_bytes())

    def test_no_compatible_candidate_publishes_only_an_explicit_no_hit_report(self):
        unrelated = self.artifact(920, self.fixture.raw, name="unrelated")
        expired = self.artifact(921, self.fixture.raw, expired=True)
        api = self.api({505: [unrelated, expired]}, {})
        with mock.patch.object(tooling_discovery, "capture_tooling_ci",
                               side_effect=AssertionError("no-hit discovery attempted capture")) as capture:
            report = self.discover((505, 505), api)
        capture.assert_not_called()
        self.assertEqual([505], self.listed_runs)
        self.assertEqual({
            "schemaVersion": 1,
            "selected": None,
            "attempts": [],
            "toolingPolicy": None,
        }, report)
        self.assertEqual(report, load_canonical_json_bytes(
            (self.destination / "discovery.json").read_bytes()))
        self.assertEqual(["discovery.json"], sorted(
            path.relative_to(self.destination).as_posix()
            for path in self.destination.rglob("*") if path.is_file()))


class ToolingDiscoveryCliTest(unittest.TestCase):
    def test_cli_forwards_ordered_candidates_and_rejects_artifact_or_key_authority(self):
        with tempfile.TemporaryDirectory(prefix="tooling-discovery-cli-") as temporary:
            root = Path(temporary).resolve()
            argv = [
                "--destination", str(root / "output"),
                "--repository-root", str(root / "repository"),
                "--java-executable", str(root / "java"),
                "--trusted-workflow-sha", "a" * 40,
                "--policy-revision", "b" * 40,
                "--candidate-run-id", "17",
                "--candidate-run-id", "19",
            ]
            with mock.patch.dict(os.environ, {"GITHUB_TOKEN": TOKEN}, clear=True), \
                    mock.patch.object(tooling_discovery, "discover_tooling_ci") as discover:
                self.assertEqual(0, tooling_discovery.main(argv))
                discover.assert_called_once_with(
                    root / "output", root / "repository", candidate_run_ids=[17, 19],
                    trusted_workflow_sha="a" * 40, policy_revision="b" * 40,
                    java_executable=root / "java", token=TOKEN,
                )
                discover.reset_mock()
                for option in ("--artifact-id", "--artifact-sha256", "--private-key", "--keyring"):
                    with self.subTest(option=option), mock.patch("sys.stderr", new=io.StringIO()), \
                            self.assertRaises(SystemExit) as failure:
                        tooling_discovery.main([*argv, option, "untrusted"])
                    self.assertEqual(2, failure.exception.code)
                discover.assert_not_called()


if __name__ == "__main__":
    unittest.main()
