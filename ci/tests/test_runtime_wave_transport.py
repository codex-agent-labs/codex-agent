"""Successor Runtime state upload transport; replay grants admission elsewhere."""

from pathlib import Path
import unittest
from unittest import mock

from ci.products.inventory import load_canonical_json, sha256_bytes
from ci.tests.test_product_resume_capture import archive
from ci.tests import test_runtime_resume_capture as resume_fixture

product_reuse = resume_fixture.product_reuse


class RuntimeWaveTransportTest(unittest.TestCase):
    # Reuse the existing official API/ZIP fixture without collecting its tests.
    setUp = resume_fixture.RuntimeResumeCaptureTest.setUp

    def wave_values(self, wave: int, members=None):
        contents = {
            **self.contents,
            "runtime-state/reuse-wave-result.json": b"successor state bytes\n",
        } if members is None else members
        raw = archive(contents)
        artifact = {
            **self.artifact,
            "name": (
                f"codex-agent-runtime-wave-{wave}-state-{self.producer['tree']}"
                f"-attempt-{self.producer['runAttempt']}"
            ),
            "digest": sha256_bytes(raw),
            "size_in_bytes": len(raw),
        }
        job = {**self.job, "name": f"product-validation / runtime-collect-{wave}"}
        return contents, raw, artifact, job

    def capture(self, wave: int, destination: Path, *, members=None, artifact_changes=None,
                job_changes=None):
        contents, raw, artifact, job = self.wave_values(wave, members)
        artifact.update({} if artifact_changes is None else artifact_changes)
        job.update({} if job_changes is None else job_changes)
        with mock.patch.object(product_reuse, "api_json", side_effect=[
            self.run, self.commit, artifact,
        ]) as query, mock.patch.object(
            product_reuse, "paginated_items", return_value=[job],
        ) as listing, mock.patch.object(
            product_reuse, "download_artifact", return_value=raw,
        ) as download:
            result = product_reuse.capture_runtime_resume_upload(
                self.plan_path, destination, artifact_id=101,
                artifact_sha256=sha256_bytes(raw), trusted_workflow_sha=self.pin,
                repository_root=self.root, environ=self.environment,
                token="not-a-real-token", state_wave=wave,
            )
        return result, contents, artifact, job, query, listing, download

    def test_successor_waves_use_exact_job_artifact_attempt_and_three_roots(self):
        original_plan = self.plan_path.read_bytes()
        for wave in (1, 4):
            destination = self.root / f"build/runtime-wave-{wave}"
            result, contents, artifact, job, query, listing, download = self.capture(
                wave, destination,
            )
            captured = destination / "original"
            self.assertEqual(
                {"product-resume-inputs", "product-resume-state", "runtime-state"},
                {path.name for path in captured.iterdir()},
            )
            self.assertEqual(
                set(contents),
                {path.relative_to(captured).as_posix()
                 for path in captured.rglob("*") if path.is_file()},
            )
            for name, value in contents.items():
                self.assertEqual(value, (captured / name).read_bytes(), name)
            self.assertEqual(wave, result["stateWave"])
            self.assertEqual(artifact, result["artifact"])
            self.assertEqual([job], result["observed"][0]["jobs"])
            self.assertEqual(result, load_canonical_json(destination / "capture-transport.json"))
            self.assertEqual(3, query.call_count)
            listing.assert_called_once_with(
                "https://api.github.com/repos/codex-agent-labs/codex-agent/"
                "actions/runs/91/attempts/3/jobs",
                "jobs", "not-a-real-token",
            )
            download.assert_called_once_with(artifact, "not-a-real-token")
        self.assertEqual(original_plan, self.plan_path.read_bytes())

    def test_wave_range_names_attempt_and_exact_root_set_fail_closed(self):
        with mock.patch.object(product_reuse, "_observe_ci_producer_jobs") as observe:
            for number, wave in enumerate((-1, 5, True)):
                destination = self.root / f"build/rejected-wave-{number}"
                with self.subTest(wave=wave), self.assertRaisesRegex(
                    ValueError, "integer from zero through four",
                ):
                    product_reuse.capture_runtime_resume_upload(
                        self.plan_path, destination, artifact_id=101,
                        artifact_sha256=self.artifact["digest"],
                        trusted_workflow_sha=self.pin, repository_root=self.root,
                        environ=self.environment, token="not-a-real-token", state_wave=wave,
                    )
                self.assertFalse(destination.exists())
            observe.assert_not_called()

        full, _, _, _ = self.wave_values(2)
        cases = (
            ("missing-runtime-state",
             {name: value for name, value in full.items() if not name.startswith("runtime-state/")},
             None, None, "exact original directories"),
            ("extra-root", {**full, "extra/value": b"unexpected\n"},
             None, None, "exact original directories"),
            ("wrong-artifact-wave", full, {"name": "codex-agent-runtime-wave-3-state-wrong"},
             None, "transport identity"),
            ("wrong-attempt", full,
             {"name": f"codex-agent-runtime-wave-2-state-{self.producer['tree']}-attempt-2"},
             None, "transport identity"),
            ("wrong-job", full, None,
             {"name": "product-validation / runtime-collect-3"}, "producer job"),
        )
        before = self.plan_path.read_bytes()
        for name, members, artifact_changes, job_changes, message in cases:
            destination = self.root / f"build/rejected-{name}"
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, message):
                self.capture(2, destination, members=members,
                             artifact_changes=artifact_changes, job_changes=job_changes)
            self.assertFalse(destination.exists())
            self.assertEqual(before, self.plan_path.read_bytes())

    def test_cli_forwards_only_nonzero_state_wave(self):
        common = [
            "capture-runtime-resume-upload", "--plan", str(self.plan_path),
            "--destination", str(self.root / "build/cli-wave"),
            "--artifact-id", "101", "--artifact-sha256", self.artifact["digest"],
            "--trusted-workflow-sha", self.pin,
        ]
        with mock.patch.object(product_reuse, "capture_runtime_resume_upload") as capture:
            self.assertEqual(0, product_reuse.main([*common, "--state-wave", "3"]))
            self.assertEqual(3, capture.call_args.kwargs["state_wave"])
        with mock.patch.object(product_reuse, "capture_runtime_resume_upload") as capture:
            self.assertEqual(0, product_reuse.main(common))
            self.assertNotIn("state_wave", capture.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
