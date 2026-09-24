"""Mocked original upload transport; captured bytes still require full replay."""
import copy
import io
from pathlib import Path
import stat
import unittest
from unittest import mock
import zipfile

from ci.tests import test_runtime_supervisor_capture as supervisor_fixture
from ci.tests.test_product_resume_capture import archive, product_reuse
from ci.products.inventory import (load_canonical_json, publish_regular_tree as actual_publish_regular_tree,
                                   sha256_bytes)


class RuntimeResumeCaptureTest(unittest.TestCase):
    def setUp(self):
        fixture = supervisor_fixture.RuntimeSupervisorCaptureTest()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        for name in ("root", "plan_path", "environment", "producer", "pin", "run", "commit", "job", "artifact"):
            setattr(self, name, copy.deepcopy(getattr(fixture, name)))
        self.job["name"] = "product-validation / product-resume"
        self.contents = {
            "product-resume-inputs/plan/impact-plan.json": self.plan_path.read_bytes(),
            "product-resume-inputs/transport.json": b"untrusted nested provenance is retained, not authority\n",
            "product-resume-state/reuse-wave-result.json": b"synthetic state; full replay deliberately not exercised\n",
            "product-resume-state/raw/gradle.log": b"",
        }
        self.raw = archive(self.contents)
        self.artifact.update(name=f"codex-agent-product-resume-{self.producer['tree']}",
                             digest=sha256_bytes(self.raw), size_in_bytes=len(self.raw))

    def capture(self, destination, *, run=None, commit=None, jobs=None, artifact=None, raw=None):
        with mock.patch.object(product_reuse, "api_json", side_effect=[
            self.run if run is None else run, self.commit if commit is None else commit,
            self.artifact if artifact is None else artifact,
        ]) as query, mock.patch.object(product_reuse, "paginated_items", return_value=(
            [self.job] if jobs is None else jobs
        )) as listing, mock.patch.object(product_reuse, "download_artifact", return_value=(
            self.raw if raw is None else raw
        )) as download:
            result = product_reuse.capture_runtime_resume_upload(
                self.plan_path, destination, artifact_id=101, artifact_sha256=self.artifact["digest"],
                trusted_workflow_sha=self.pin, repository_root=self.root,
                environ=self.environment, token="not-a-real-token")
        return result, query, listing, download

    def capture_members(self, destination, members):
        raw = archive(members)
        original = self.artifact
        self.artifact = {**original, "digest": sha256_bytes(raw), "size_in_bytes": len(raw)}
        try:
            return self.capture(destination, raw=raw)
        finally:
            self.artifact = original

    def test_exact_original_upload_preserves_empty_logs_nested_claims_and_caller_plan(self):
        before = self.plan_path.read_bytes()
        destination = self.root / "build/resume-capture"
        result, query, listing, download = self.capture(destination)
        originals = destination / "original"
        self.assertEqual({"product-resume-inputs", "product-resume-state"}, {path.name for path in originals.iterdir()})
        self.assertEqual(set(self.contents), {path.relative_to(originals).as_posix()
                                            for path in originals.rglob("*") if path.is_file()})
        for name, contents in self.contents.items():
            self.assertEqual(contents, (originals / name).read_bytes(), name)
        self.assertEqual(before, self.plan_path.read_bytes())
        self.assertEqual(result, load_canonical_json(destination / "capture-transport.json"))
        self.assertEqual(self.producer, result["captureProducer"])
        self.assertEqual(self.artifact, result["artifact"])
        self.assertEqual(self.run, result["observed"][0]["run"])
        self.assertEqual(self.commit, result["observed"][0]["testedCommit"])
        self.assertEqual([self.job], result["observed"][0]["jobs"])
        self.assertEqual(3, query.call_count)
        listing.assert_called_once_with(
            "https://api.github.com/repos/codex-agent-labs/codex-agent/actions/runs/91/attempts/3/jobs",
            "jobs", "not-a-real-token")
        download.assert_called_once_with(self.artifact, "not-a-real-token")
        # The fixture state is not valid JSON; capture therefore proves no phase replay.
        self.assertNotIn("fullReuse", result)

    def test_late_original_mutation_cannot_publish(self):
        destination = self.root / "build/rejected-resume-late-copy"

        def mutate_during_copy(source, output, **kwargs):
            (Path(source) / "original/product-resume-state/reuse-wave-result.json").write_bytes(
                b"changed during copy")
            actual_publish_regular_tree(source, output, **kwargs)

        with mock.patch.object(product_reuse, "publish_regular_tree", side_effect=mutate_during_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.capture(destination)
        self.assertFalse(destination.exists())

    def test_cli_forwards_only_explicit_upload_and_workflow_bindings(self):
        destination = self.root / "build/cli-resume-capture"
        with mock.patch.object(product_reuse, "capture_runtime_resume_upload") as capture, \
                mock.patch.dict(product_reuse.os.environ, {"GITHUB_TOKEN": "not-a-real-token"}, clear=True):
            self.assertEqual(0, product_reuse.main([
                "capture-runtime-resume-upload", "--plan", str(self.plan_path),
                "--destination", str(destination), "--artifact-id", "101",
                "--artifact-sha256", self.artifact["digest"], "--trusted-workflow-sha", self.pin]))
        capture.assert_called_once_with(
            self.plan_path, destination, artifact_id=101, artifact_sha256=self.artifact["digest"],
            trusted_workflow_sha=self.pin, token="not-a-real-token")

    def test_failed_unrelated_duplicate_or_crosspaired_original_job_is_rejected(self):
        cases = [dict(jobs=[]), dict(jobs=[self.job, self.job])]
        cases.extend(dict(jobs=[{**self.job, **changes}]) for changes in (
            {"name": "product-validation / runtime-linux-arm64-supervisor"},
            {"status": "in_progress"}, {"conclusion": "failure"},
            {"run_id": 92}, {"head_sha": "f" * 40},
        ))
        cases.extend(dict(run={**self.run, **changes}) for changes in (
            {"run_attempt": 2}, {"referenced_workflows": []}, {"event": "push"},
            {"pull_requests": [{**self.run["pull_requests"][0], "number": 999}]},
        ))
        cases.extend((dict(commit={**self.commit, "tree": {"sha": "f" * 40}}),
                      dict(commit={**self.commit, "parents": list(reversed(self.commit["parents"]))})))
        for index, case in enumerate(cases):
            destination = self.root / f"build/rejected-resume-job-{index}"
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.capture(destination, **case)
            self.assertFalse(destination.exists())

    def test_original_upload_id_name_digest_size_and_run_are_mandatory(self):
        cases = [dict(raw=b"not the caller-pinned archive bytes")]
        cases.extend(dict(artifact={**self.artifact, **changes}) for changes in (
            {"id": 102}, {"name": "codex-agent-product-resume-wrong-tree"}, {"expired": True},
            {"digest": "sha256:" + "0" * 64}, {"size_in_bytes": 1},
            {"workflow_run": {"id": 92, "head_sha": self.producer["commit"]}},
            {"workflow_run": {"id": 91, "head_sha": "f" * 40}},
            {"archive_download_url": "https://untrusted.invalid/archive.zip"},
        ))
        for index, case in enumerate(cases):
            destination = self.root / f"build/rejected-resume-upload-{index}"
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.capture(destination, **case)
            self.assertFalse(destination.exists())

    def test_root_shape_and_exact_caller_plan_binding_fail_closed(self):
        plan_name = "product-resume-inputs/plan/impact-plan.json"
        cases = [
            {name: contents for name, contents in self.contents.items() if not name.startswith("product-resume-state/")},
            {name: contents for name, contents in self.contents.items() if name != plan_name},
            {**self.contents, plan_name: b"different caller plan\n"},
            {**self.contents, plan_name: self.contents[plan_name] + b"\n"},
            {**self.contents, "unexpected/extra": b"extra"},
            {**self.contents, "unexpected-file": b"extra"},
            {**{name: data for name, data in self.contents.items() if not name.startswith("product-resume-state/")},
             "product-resume-state": b"not a directory"},
        ]
        for index, members in enumerate(cases):
            destination = self.root / f"build/rejected-resume-shape-{index}"
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.capture_members(destination, members)
            self.assertFalse(destination.exists())

    def test_hostile_archive_and_existing_destination_preserve_original_files(self):
        before = self.plan_path.read_bytes()
        destination = self.root / "build/resume-existing"
        destination.mkdir(parents=True)
        sentinel = destination / "original"
        sentinel.write_bytes(b"immutable prior capture")
        with mock.patch.object(product_reuse, "api_json") as query:
            with self.assertRaises(ValueError):
                product_reuse.capture_runtime_resume_upload(
                    self.plan_path, destination, artifact_id=101, artifact_sha256=self.artifact["digest"],
                    trusted_workflow_sha=self.pin, repository_root=self.root,
                    environ=self.environment, token="not-a-real-token")
        query.assert_not_called()
        self.assertEqual(b"immutable prior capture", sentinel.read_bytes())
        traversal_destination = self.root / "build/rejected-resume-traversal"
        with self.assertRaises(ValueError):
            self.capture_members(traversal_destination, {**self.contents, "../escape": b"bad"})
        self.assertFalse(traversal_destination.exists())
        self.assertFalse((self.root / "escape").exists())
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as zipped:
            for name, contents in sorted(self.contents.items()):
                zipped.writestr(name, contents)
            member = zipfile.ZipInfo("product-resume-state/symbolic")
            member.create_system = 3
            member.external_attr = (stat.S_IFLNK | 0o777) << 16
            zipped.writestr(member, "../../original")
        raw = output.getvalue()
        self.artifact.update(digest=sha256_bytes(raw), size_in_bytes=len(raw))
        symbolic_destination = self.root / "build/rejected-resume-symbolic"
        with self.assertRaises(ValueError):
            self.capture(symbolic_destination, raw=raw)
        self.assertFalse(symbolic_destination.exists())
        self.assertEqual(before, self.plan_path.read_bytes())
