from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


CI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CI_ROOT))

import product_reuse  # noqa: E402
from products.contract_attestation import capture_contract_execution_closure  # noqa: E402
from products.inventory import (  # noqa: E402
    canonical_json_bytes,
    load_canonical_json_bytes,
    regular_file_inventory,
    sha256_bytes,
)
from products.registry import PhaseInstanceId  # noqa: E402
from products.restore import finalize_phase_object, verify_phase_shard  # noqa: E402
from ci.tests.test_contract_bundle import TREE, VERSION  # noqa: E402
from ci.tests.test_contract_execution_closure import execution_closure_fixture  # noqa: E402


PHASES = ("binary", "package", "validation", "metadata")
REPOSITORY = "codex-agent-labs/codex-agent"


def archive_tree(root: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(value for value in root.rglob("*") if value.is_file()):
            archive.writestr(path.relative_to(root).as_posix(), path.read_bytes())
    return buffer.getvalue()


class ContractOriginalCiCaptureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="contract-original-ci-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.pin = "c" * 40
        self.producer = {
            "repository": REPOSITORY,
            "workflowPath": ".github/workflows/ci.yml",
            "commit": "0123456789abcdef0123456789abcdef01234567",
            "tree": TREE,
            "event": "pull_request",
            "runId": 71,
            "runAttempt": 2,
            "pullRequest": 31,
        }
        self.run = {
            "id": 71,
            "run_attempt": 2,
            "path": self.producer["workflowPath"],
            "head_sha": "f" * 40,
            "event": "pull_request",
            "status": "completed",
            "conclusion": "success",
            "pull_requests": [{
                "number": 31,
                "base": {"sha": "1" * 40},
                "head": {"sha": "f" * 40},
            }],
            "repository": {"full_name": REPOSITORY, "fork": False},
            "head_repository": {"full_name": REPOSITORY, "fork": False},
            "referenced_workflows": [{
                "path": f"{REPOSITORY}/.github/workflows/product-validation.yml@{self.pin}",
                "sha": self.pin,
            }],
        }
        self.commit = {
            "sha": self.producer["commit"],
            "tree": {"sha": TREE},
            "parents": [{"sha": "1" * 40}, {"sha": "f" * 40}],
        }
        self.jobs = [{
            "id": number,
            "name": f"product-validation / {name}",
            "run_id": 71,
            "head_sha": self.run["head_sha"],
            "status": "completed",
            "conclusion": "success",
            "started_at": "2026-09-06T10:00:00Z",
            "completed_at": "2026-09-06T10:30:00Z",
        } for number, name in enumerate(("product-contracts", "contract-continuation"), 801)]

        self.source = self.root / "source"
        self.payload, self.receipts, self.execution_archive = execution_closure_fixture(
            self.source, producer=self.producer,
        )
        self.capture_root = self.root / "capture"
        shutil.copytree(
            self.payload.parent.parent,
            self.capture_root / "phases/metadata/stage",
        )
        capture_contract_execution_closure(
            self.payload,
            self.receipts,
            self.execution_archive,
            self.capture_root / "execution-closure",
        )
        (self.capture_root / "transport").mkdir()
        (self.capture_root / "transport/ci-artifact.json").write_bytes(canonical_json_bytes({
            "artifact": {"id": 700},
            "captureProducer": self.producer,
            "observed": [{"run": self.run, "testedCommit": self.commit, "jobs": self.jobs}],
        }))

        stage_names = {
            "binary": "binary-stage",
            "package": "package-stage",
            "validation": "validation-stage",
            "metadata": "metadata-stage",
        }
        self.shards: dict[str, Path] = {}
        self.archives: dict[str, bytes] = {}
        self.artifacts: dict[str, dict[str, object]] = {}
        for index, phase in enumerate(PHASES, 101):
            receipt = load_canonical_json_bytes(self.receipts[phase].read_bytes())
            shard = self.root / "shards" / phase
            finalize_phase_object(
                stage_root=self.source / stage_names[phase],
                phase_plan={
                    "schemaVersion": 1,
                    "product": "contract",
                    "component": "contract",
                    "phase": phase,
                    "target": "common",
                    "buildKey": receipt["buildKey"],
                    "inputs": receipt["inputs"],
                },
                producer=receipt["producer"],
                product_version=receipt["productVersion"],
                trust_domain=receipt["trustDomain"],
                destination=shard,
            )
            raw = archive_tree(shard)
            name = f"codex-agent-product-phase-contract-contract-{phase}-common-{TREE}"
            url = f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/{index}"
            artifact = {
                "id": index,
                "name": name,
                "size_in_bytes": len(raw),
                "digest": sha256_bytes(raw),
                "expired": False,
                "created_at": "2026-09-06T10:15:00Z",
                "archive_download_url": f"{url}/zip",
                "workflow_run": {"id": 71, "head_sha": self.run["head_sha"]},
            }
            self.shards[phase] = shard
            self.archives[phase] = raw
            self.artifacts[phase] = artifact
        self.output = self.root / "originals"

    def api(self, *, artifacts=None, details=None, archives=None, run=None, commit=None, jobs=None):
        listed = list((self.artifacts if artifacts is None else artifacts).values())
        selected_details = self.artifacts if details is None else details
        selected_archives = self.archives if archives is None else archives
        by_id = {value["id"]: value for value in selected_details.values()}
        raw_by_url = {
            self.artifacts[phase]["archive_download_url"]: selected_archives[phase]
            for phase in PHASES
        }

        def request(url: str, token: str) -> bytes:
            self.assertEqual("not-a-real-token", token)
            if url == f"https://api.github.com/repos/{REPOSITORY}/actions/runs/71/attempts/2":
                return json.dumps(self.run if run is None else run).encode()
            if url == f"https://api.github.com/repos/{REPOSITORY}/git/commits/{self.producer['commit']}":
                return json.dumps(self.commit if commit is None else commit).encode()
            if url.startswith(f"https://api.github.com/repos/{REPOSITORY}/actions/runs/71/attempts/2/jobs?"):
                return json.dumps({"jobs": self.jobs if jobs is None else jobs}).encode()
            if url.startswith(f"https://api.github.com/repos/{REPOSITORY}/actions/runs/71/artifacts?"):
                return json.dumps({"artifacts": listed}).encode()
            if url in raw_by_url:
                return raw_by_url[url]
            prefix = f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/"
            if url.startswith(prefix) and url.removeprefix(prefix).isdigit():
                return json.dumps(by_id[int(url.removeprefix(prefix))]).encode()
            raise AssertionError(f"Unexpected API request: {url}")

        return request

    def capture(self, **api_changes):
        with mock.patch("reuse.api_request", side_effect=self.api(**api_changes)):
            return product_reuse.capture_contract_original_ci_phases(
                self.capture_root,
                self.output,
                contract_version=VERSION,
                trusted_workflow_sha=self.pin,
                token="not-a-real-token",
            )

    def test_cli_captures_exact_original_shards_and_preserves_all_inputs(self) -> None:
        before_capture = regular_file_inventory(self.capture_root)
        before_source = regular_file_inventory(self.source, allow_empty=True)
        with mock.patch("reuse.api_request", side_effect=self.api()), \
                mock.patch.dict(os.environ, {"GITHUB_TOKEN": "not-a-real-token"}):
            self.assertEqual(0, product_reuse.main([
                "capture-contract-original-ci",
                "--capture-root", str(self.capture_root),
                "--destination", str(self.output),
                "--contract-version", VERSION,
                "--trusted-workflow-sha", self.pin,
            ]))
        self.assertEqual(before_capture, regular_file_inventory(self.capture_root))
        self.assertEqual(before_source, regular_file_inventory(self.source, allow_empty=True))
        self.assertEqual(
            before_capture,
            regular_file_inventory(self.output / "contract-input"),
        )
        evidence = load_canonical_json_bytes(
            (self.output / "transport/original-ci-phases.json").read_bytes(),
        )
        self.assertEqual(self.artifacts, evidence["artifacts"])
        for phase in PHASES:
            verified = verify_phase_shard(
                self.output / "original-phases" / phase,
                PhaseInstanceId("contract", "contract", phase, "common"),
            )
            expected = self.receipts[phase].read_bytes()
            self.assertEqual(expected, verified["receiptBytes"])
            self.assertEqual(sha256_bytes(expected), evidence["receiptSha256s"][phase])
        self.assertEqual(
            [{"run": self.run, "testedCommit": self.commit, "jobs": self.jobs}],
            evidence["observed"],
        )

    def test_artifact_identity_and_cross_pair_mutations_fail_atomically(self) -> None:
        cases = []
        for change in (
            {"id": 999},
            {"digest": sha256_bytes(b"wrong")},
            {"expired": True},
            {"name": "wrong"},
            {"workflow_run": {"id": 72, "head_sha": self.run["head_sha"]}},
            {"workflow_run": {"id": 71, "head_sha": "e" * 40}},
            {"created_at": "2026-09-06T09:59:59Z"},
            {"created_at": "2026-09-06T10:30:01Z"},
            {"created_at": None},
            {"created_at": "not-a-timestamp"},
            {"created_at": "2026-09-06T10:15:00"},
            {"created_at": "2026-09-06T12:15:00+02:00"},
        ):
            changed = {**self.artifacts, "binary": {**self.artifacts["binary"], **change}}
            cases.append((changed, changed, None))
        crossed = {**self.artifacts, "binary": {
            **self.artifacts["binary"],
            "size_in_bytes": len(self.archives["package"]),
            "digest": sha256_bytes(self.archives["package"]),
        }}
        cases.extend((
            ({phase: value for phase, value in self.artifacts.items() if phase != "binary"}, None, None),
            ({**self.artifacts, "extra": {**self.artifacts["binary"], "id": 999}}, None, None),
            (crossed, crossed, {**self.archives, "binary": self.archives["package"]}),
        ))
        for number, (artifacts, details, archives) in enumerate(cases):
            with self.subTest(number=number), self.assertRaises((ValueError, KeyError)):
                self.capture(artifacts=artifacts, details=details, archives=archives)
            self.assertFalse(self.output.exists())

    def test_wrong_original_run_and_tampered_capture_transport_fail_without_publication(self) -> None:
        for run in (
            {**self.run, "run_attempt": 1},
            {**self.run, "head_sha": "e" * 40},
            {**self.run, "event": "push"},
            {**self.run, "referenced_workflows": []},
        ):
            with self.subTest(run=run), self.assertRaises(ValueError):
                self.capture(run=run)
            self.assertFalse(self.output.exists())

        transport = self.capture_root / "transport/ci-artifact.json"
        original = transport.read_bytes()
        mutations = (
            b"{}\n",
            canonical_json_bytes({
                "artifact": {}, "captureProducer": self.producer, "observed": [],
            }),
            original.rstrip(b"\n") + b" \n",
        )
        for contents in mutations:
            with self.subTest(contents=contents):
                transport.write_bytes(contents)
                with mock.patch("reuse.api_request") as request, self.assertRaises(ValueError):
                    product_reuse.capture_contract_original_ci_phases(
                        self.capture_root,
                        self.output,
                        contract_version=VERSION,
                        trusted_workflow_sha=self.pin,
                        token="not-a-real-token",
                    )
                request.assert_not_called()
                self.assertFalse(self.output.exists())
        transport.write_bytes(original)

    def test_nested_destination_rejects_before_api_and_preserves_capture(self) -> None:
        before = regular_file_inventory(self.capture_root)
        destination = self.capture_root / "nested-output"
        with mock.patch("reuse.api_request") as request, self.assertRaisesRegex(
            ValueError, "must not overlap",
        ):
            product_reuse.capture_contract_original_ci_phases(
                self.capture_root,
                destination,
                contract_version=VERSION,
                trusted_workflow_sha=self.pin,
                token="not-a-real-token",
            )
        request.assert_not_called()
        self.assertFalse(destination.exists())
        self.assertEqual(before, regular_file_inventory(self.capture_root))


if __name__ == "__main__":
    unittest.main()
