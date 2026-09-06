from __future__ import annotations

import copy
import io
from pathlib import Path
import sys
import unittest
from unittest import mock
import zipfile


CI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CI_ROOT))

import product_reuse  # noqa: E402
from products.inventory import load_canonical_json, sha256_bytes  # noqa: E402
from ci.tests.test_ci import GitFixture


NAMES = {
    "plan": "ci-plan",
    "state": "contract-phase-state",
    "release": "contract-release-handoff",
}


def archive(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as result:
        for name, contents in sorted(files.items()):
            result.writestr(name, contents)
    return output.getvalue()


class ProductResumeCaptureTest(GitFixture):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.root.resolve()
        _, self.plan_path, _ = self.make_plan("configured/contracts.txt")
        self.plan_path = self.plan_path.resolve(strict=True)
        self.plan_bytes = self.plan_path.read_bytes()
        self.environment = {"GITHUB_RUN_ID": "91", "GITHUB_RUN_ATTEMPT": "3"}
        self.producer = product_reuse._consumer(
            product_reuse._validate_plan(self.plan_path, self.root), self.environment,
        )["producer"]
        self.observed = [{
            "run": {"id": 91, "run_attempt": 3, "head_sha": "f" * 40},
            "testedCommit": {"sha": self.producer["commit"], "tree": {"sha": self.producer["tree"]}},
            "jobs": [{"id": 901, "name": "product-validation / contract-continuation"}],
        }]
        self.contents = {
            "plan": {"impact-plan.json": self.plan_bytes},
            "state": {"contract-reuse-result.json": b"state-bytes\n"},
            "release": {"codex-agent-contract-0.2.0.zip": b"release-bytes\n"},
        }
        self.archives = {name: archive(contents) for name, contents in self.contents.items()}
        self.artifacts = {}
        self.uploads = {}
        for artifact_id, name in enumerate(NAMES, 101):
            raw = self.archives[name]
            url = f"https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/{artifact_id}"
            artifact = {
                "id": artifact_id,
                "name": f"codex-agent-{NAMES[name]}-{self.producer['tree']}",
                "size_in_bytes": len(raw),
                "digest": sha256_bytes(raw),
                "expired": False,
                "archive_download_url": f"{url}/zip",
                "workflow_run": {"id": 91, "head_sha": self.observed[0]["run"]["head_sha"]},
            }
            self.artifacts[name] = artifact
            self.uploads[name] = {"artifactId": artifact_id, "artifactSha256": artifact["digest"]}

    def capture(
        self,
        destination: Path,
        *,
        uploads: dict | None = None,
        artifacts: dict | None = None,
        archives: dict | None = None,
        expected_error: str | None = None,
    ):
        selected_artifacts = self.artifacts if artifacts is None else artifacts
        selected_archives = self.archives if archives is None else archives
        by_id = {self.uploads[name]["artifactId"]: selected_artifacts[name] for name in NAMES}

        def api_json(url: str, token: str):
            self.assertEqual("not-a-real-token", token)
            return by_id[int(url.rsplit("/", 1)[-1])]

        def download_artifact(artifact_record: dict, token: str) -> bytes:
            self.assertEqual("not-a-real-token", token)
            selected = next(name for name, value in selected_artifacts.items() if value is artifact_record)
            return selected_archives[selected]

        with mock.patch.object(
            product_reuse, "_observe_contract_producer_runs", return_value=self.observed,
        ) as observe, mock.patch.object(
            product_reuse, "api_json", side_effect=api_json,
        ) as query, mock.patch.object(
            product_reuse, "download_artifact", side_effect=download_artifact,
        ) as download:
            arguments = {
                "uploads": self.uploads if uploads is None else uploads,
                "trusted_workflow_sha": "c" * 40,
                "repository_root": self.root,
                "environ": self.environment,
                "token": "not-a-real-token",
            }
            if expected_error is None:
                result = product_reuse.capture_product_resume_inputs(
                    self.plan_path, destination, **arguments,
                )
            else:
                with self.assertRaisesRegex(ValueError, expected_error):
                    product_reuse.capture_product_resume_inputs(
                        self.plan_path, destination, **arguments,
                    )
                result = None
        return result, observe, query, download

    def test_captures_exact_local_archives_and_external_transport(self) -> None:
        destination = self.root / "build/resume-capture"
        result, observe, query, download = self.capture(destination)
        observe.assert_called_once_with(
            {"metadata": self.producer}, phases=("metadata",),
            trusted_workflow_sha="c" * 40, token="not-a-real-token",
        )
        self.assertEqual(self.plan_bytes, self.plan_path.read_bytes())
        self.assertEqual(self.plan_bytes, (destination / "plan/impact-plan.json").read_bytes())
        self.assertEqual(b"state-bytes\n", (destination / "state/contract-reuse-result.json").read_bytes())
        self.assertEqual(
            b"release-bytes\n", (destination / "release/codex-agent-contract-0.2.0.zip").read_bytes(),
        )
        self.assertEqual({
            "artifacts": self.artifacts,
            "captureProducer": self.producer,
            "observed": self.observed,
        }, result)
        self.assertEqual(result, load_canonical_json(destination / "capture-transport.json"))
        self.assertEqual(3, query.call_count)
        self.assertEqual(3, download.call_count)

    def test_transport_identity_archive_and_plan_failures_publish_nothing(self) -> None:
        cases = []

        uploads = copy.deepcopy(self.uploads)
        uploads["plan"]["artifactSha256"] = sha256_bytes(b"wrong")
        cases.append(("caller digest", uploads, None, None, "transport identity", (1, 1, 0)))

        artifacts = copy.deepcopy(self.artifacts)
        artifacts["plan"]["id"] = 999
        cases.append(("artifact id", None, artifacts, None, "transport identity", (1, 1, 0)))

        artifacts = copy.deepcopy(self.artifacts)
        artifacts["plan"]["name"] = "wrong"
        cases.append(("artifact name", None, artifacts, None, "transport identity", (1, 1, 0)))

        uploads = copy.deepcopy(self.uploads)
        del uploads["release"]
        cases.append(("missing upload", uploads, None, None, "fields are invalid", (0, 0, 0)))

        uploads = copy.deepcopy(self.uploads)
        uploads["release"]["artifactId"] = uploads["state"]["artifactId"]
        cases.append(("duplicate artifact id", uploads, None, None, "IDs must be distinct", (0, 0, 0)))

        archives = copy.deepcopy(self.archives)
        archives["plan"] = b"corrupt transport bytes"
        cases.append(("corrupt bytes", None, None, archives, "bytes differ", (1, 1, 1)))

        for label, changed_plan, error, calls in (
            ("missing plan", {"unrelated.txt": b"not a plan\n"}, "missing or unsafe", (1, 3, 3)),
            ("different plan", {"impact-plan.json": b"{}\n"}, "differs from the validated", (1, 3, 3)),
            ("unsafe zip", {"../escape": b"unsafe\n"}, "ZIP member path is not normalized", (1, 1, 1)),
        ):
            archives = copy.deepcopy(self.archives)
            archives["plan"] = archive(changed_plan)
            artifacts = copy.deepcopy(self.artifacts)
            artifacts["plan"]["size_in_bytes"] = len(archives["plan"])
            artifacts["plan"]["digest"] = sha256_bytes(archives["plan"])
            uploads = copy.deepcopy(self.uploads)
            uploads["plan"]["artifactSha256"] = artifacts["plan"]["digest"]
            cases.append((label, uploads, artifacts, archives, error, calls))

        before = self.plan_path.read_bytes()
        for number, (label, uploads, artifacts, archives, error, calls) in enumerate(cases):
            destination = self.root / f"build/rejected-{number}"
            with self.subTest(label=label):
                _, observe, query, download = self.capture(
                    destination, uploads=uploads, artifacts=artifacts, archives=archives,
                    expected_error=error,
                )
                self.assertEqual(calls, (observe.call_count, query.call_count, download.call_count))
                self.assertFalse(destination.exists())
                self.assertEqual(before, self.plan_path.read_bytes())

    def test_existing_destination_is_rejected_without_observation_or_deletion(self) -> None:
        destination = self.root / "build/existing-resume"
        destination.mkdir(parents=True)
        sentinel = destination / "keep.txt"
        sentinel.write_bytes(b"keep\n")
        with mock.patch.object(product_reuse, "_observe_contract_producer_runs") as observe, \
                self.assertRaises(ValueError):
            product_reuse.capture_product_resume_inputs(
                self.plan_path,
                destination,
                uploads=self.uploads,
                trusted_workflow_sha="c" * 40,
                repository_root=self.root,
                environ=self.environment,
                token="not-a-real-token",
            )
        observe.assert_not_called()
        self.assertEqual(b"keep\n", sentinel.read_bytes())


if __name__ == "__main__":
    unittest.main()
