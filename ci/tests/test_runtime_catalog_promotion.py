"""Real signed synthetic originals; mocked HTTP is not protected CI authority."""

import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ci.tests import test_runtime_aggregate_handoff as fixture
from ci.tests.test_contract_release_capture import ObservedEnvironment, SECRET
from ci.tests.test_contract_release_context import trusted_repository
from ci import runtime_catalog_promotion as caller
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory,
    sha256_bytes, snapshot_regular_tree,
)
from products.index import SignedProductIndex, verify_release_product_index
from products.restore import object_relative_path
from products.signatures import generate_development_key


class RuntimeCatalogPromotionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.RuntimeAggregateHandoffTest.setUpClass()
        cls.addClassCleanup(fixture.RuntimeAggregateHandoffTest.doClassCleanups)
        original = fixture.RuntimeAggregateHandoffTest
        cls.source, cls.carrier = original.source, original.carrier
        cls.trusted = cls.source.repository
        cls.source_pin = cls.source.pin
        cls.workflow_pin, cls.promotion_pin = "c" * 40, "e" * 40
        temporary = tempfile.TemporaryDirectory(prefix="runtime-promotion-fixture-")
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name).resolve()
        cls.candidate = cls.root / "candidate"
        cls.final = trusted_repository(cls.candidate)
        cls.tree = cls.git("rev-parse", "HEAD^{tree}")
        # Two real immutable commits with exactly the same tree. No source build.
        cls.tested = subprocess.run(["git", "commit-tree", cls.tree, "-p", cls.final], cwd=cls.candidate,
            input="synthetic merge-group tested commit\n", capture_output=True, text=True, check=True).stdout.strip()
        cls.producer = {"repository": caller.REPOSITORY, "workflowPath": ".github/workflows/ci.yml",
            "event": "merge_group", "commit": cls.tested, "tree": cls.tree,
            "runId": 901, "runAttempt": 2, "pullRequest": None}
        cls.wrapper = cls.root / "protected-output"
        snapshot_regular_tree(cls.carrier, cls.wrapper / "retained-release", allow_empty=True)
        snapshot_regular_tree(cls.carrier / "selected-inputs", cls.wrapper / "selected-inputs", allow_empty=True)
        snapshot_regular_tree(cls.carrier / "trust", cls.wrapper / "trust")
        selected = load_canonical_json_bytes((cls.wrapper / "selected-inputs/selection.json").read_bytes())
        selected["producer"] = cls.producer
        (cls.wrapper / "selected-inputs/selection.json").write_bytes(canonical_json_bytes(selected))
        cls.receipt = load_canonical_json_bytes((cls.carrier / "aggregate-input/metadata-receipt.json").read_bytes())
        cls.digest = sha256_bytes((cls.carrier / "aggregate-input/metadata-receipt.json").read_bytes())
        provenance = load_canonical_json_bytes((cls.carrier / "caller.json").read_bytes())
        provenance.update(transportProducer=cls.producer, trustedWorkflowSha=cls.workflow_pin,
                          releaseDirectory="retained-release")
        (cls.wrapper / "caller.json").write_bytes(canonical_json_bytes(provenance))
        cls.original_inventory = regular_file_inventory(cls.carrier, allow_empty=True)

    @classmethod
    def git(cls, *arguments):
        return subprocess.run(["git", *arguments], cwd=cls.candidate, capture_output=True,
                              text=True, check=True).stdout.strip()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="runtime-promotion-test-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.destination = self.work / "promotion"
        self.environment = ObservedEnvironment({
            "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": caller.REPOSITORY,
            "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": self.final,
            "GITHUB_REF": "refs/heads/main", "GITHUB_REF_PROTECTED": "true",
            "GITHUB_WORKFLOW_REF": f"{caller.REPOSITORY}/.github/workflows/promote.yml@refs/heads/main",
            "GITHUB_WORKFLOW_SHA": self.promotion_pin,
            "GITHUB_RUN_ID": "902", "GITHUB_RUN_ATTEMPT": "1",
            SECRET: self.source.context["private_key"].read_text(),
        })
        self.event = {"repository": {"full_name": caller.REPOSITORY},
                      "ref": "refs/heads/main", "after": self.final, "deleted": False}
        self.run = {"id": 901, "run_attempt": 2, "head_sha": self.tested,
            "path": ".github/workflows/ci.yml", "event": "merge_group", "status": "completed", "conclusion": "success",
            "repository": {"full_name": caller.REPOSITORY, "fork": False},
            "head_repository": {"full_name": caller.REPOSITORY, "fork": False},
            "referenced_workflows": [{"path": f"{caller.REPOSITORY}/.github/workflows/product-validation.yml@{self.workflow_pin}",
                                      "sha": self.workflow_pin}]}
        self.listed_run = copy.deepcopy(self.run)
        self.job = {"id": 910, "name": caller.JOB, "run_id": 901, "head_sha": self.tested,
            "status": "completed", "conclusion": "success", "started_at": "2026-09-06T10:00:00Z",
            "completed_at": "2026-09-06T10:30:00Z"}
        self.commit = {"sha": self.tested, "tree": {"sha": self.tree}, "parents": [{"sha": self.final}]}
        self.pack(self.wrapper)

    def pack(self, root):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            # Official transport order is not the inner product object contract.
            for record in reversed(regular_file_inventory(root, allow_empty=True)):
                archive.writestr(record["relativePath"], (root / record["relativePath"]).read_bytes())
        self.archive = output.getvalue()
        self.artifact = {"id": 920, "name": f"codex-agent-runtime-aggregate-release-handoff-{self.tree}-attempt-2",
            "digest": sha256_bytes(self.archive), "size_in_bytes": len(self.archive), "expired": False,
            "workflow_run": {"id": 901, "head_sha": self.tested}, "created_at": "2026-09-06T10:15:00Z",
            "archive_download_url": f"https://api.github.com/repos/{caller.REPOSITORY}/actions/artifacts/920/zip"}

    def api(self, url, token):
        self.assertEqual("synthetic-token", token)
        base = f"https://api.github.com/repos/{caller.REPOSITORY}"
        if url.startswith(base + "/actions/workflows/ci.yml/runs?"):
            value = {"workflow_runs": [self.listed_run]}
        elif url == base + f"/git/commits/{self.tested}":
            value = self.commit
        elif url == base + "/actions/runs/901/attempts/2":
            value = self.run
        elif url.startswith(base + "/actions/runs/901/attempts/2/jobs?"):
            value = {"jobs": [self.job]}
        elif url.startswith(base + "/actions/runs/901/artifacts?"):
            value = {"artifacts": [self.artifact]}
        elif url == self.artifact["archive_download_url"]:
            return self.archive
        elif url == base + "/actions/artifacts/920":
            value = self.artifact
        else:
            raise AssertionError(f"Unexpected HTTP request: {url}")
        return json.dumps(value).encode()

    def invoke(self, **changes):
        arguments = dict(trusted_source_sha=self.source_pin, trusted_workflow_sha=self.workflow_pin,
            trusted_promotion_workflow_sha=self.promotion_pin, final_commit=self.final,
            event_payload=self.event, environment=self.environment, token="synthetic-token")
        arguments.update(changes)
        with patch("reuse.api_request", side_effect=self.api):
            return caller.promote_runtime_aggregate_catalog(self.trusted, self.candidate, self.destination, **arguments)

    def test_equal_tree_retained_upload_full_signature_object_catalog_and_original_history(self):
        self.assertNotEqual(self.final, self.tested)
        with patch("products.runtime_aggregate.sign_manifest", side_effect=AssertionError("Product re-sign")):
            result = self.invoke()
        self.assertEqual(1, self.environment.secret_reads)
        self.assertEqual(self.final, result["context"]["commit"])
        self.assertEqual(self.archive, (self.destination / "original-evidence/upload.zip").read_bytes())
        self.assertEqual(regular_file_inventory(self.wrapper, allow_empty=True),
                         regular_file_inventory(self.destination / "original-evidence/original", allow_empty=True))
        catalog = self.destination / "catalog"
        index, _ = verify_release_product_index(SignedProductIndex(catalog / "product-index.json", catalog / "product-index.sig"),
            keyring_path=self.source.keyring, keys_directory=self.source.keys)
        self.assertEqual(result, index)
        relative = object_relative_path(self.receipt["buildKey"], self.digest)
        original = self.carrier / "original-evidence/phases/runtime-aggregate-metadata-aggregate/original/shard" / relative
        self.assertEqual(original.read_bytes(), (catalog / relative).read_bytes())
        self.assertEqual(self.original_inventory, regular_file_inventory(self.carrier, allow_empty=True))
        self.assertEqual(self.source.keyring.read_bytes(), (self.destination / "trust/product-signing-keys.json").read_bytes())
        for row in regular_file_inventory(self.destination, allow_empty=True):
            relative = Path(row["relativePath"])
            self.assertNotEqual("signing-key", relative.name)
            self.assertNotIn(self.environment.values[SECRET].encode("utf-8"),
                             (self.destination / relative).read_bytes())

    def test_preflight_wrong_push_pin_dirty_checkout_and_output_collision_never_contact_http(self):
        self.environment.forbid_secret = True
        for field, value in (("GITHUB_REF", "refs/heads/other"), ("GITHUB_EVENT_NAME", "pull_request"),
                             ("GITHUB_WORKFLOW_SHA", "f" * 40), ("GITHUB_REF_PROTECTED", "false")):
            previous = self.environment.values[field]
            self.environment.values[field] = value
            try:
                with self.subTest(field=field), patch("reuse.api_request", side_effect=AssertionError("HTTP before preflight")), self.assertRaises(ValueError):
                    caller.promote_runtime_aggregate_catalog(self.trusted, self.candidate, self.destination,
                        trusted_source_sha=self.source_pin, trusted_workflow_sha=self.workflow_pin,
                        trusted_promotion_workflow_sha=self.promotion_pin, final_commit=self.final,
                        event_payload=self.event, environment=self.environment, token="synthetic-token")
            finally:
                self.environment.values[field] = previous
        tracked = self.candidate / "gradle/release/versions/contract.txt"
        original = tracked.read_bytes()
        try:
            tracked.write_bytes(original + b"changed\n")
            with self.assertRaisesRegex(ValueError, "modified tracked"):
                self.invoke()
        finally:
            tracked.write_bytes(original)
        self.destination.mkdir()
        sentinel = self.destination / "original"
        sentinel.write_bytes(b"preserve")
        with self.assertRaisesRegex(ValueError, "must not exist"):
            self.invoke()
        self.assertEqual(b"preserve", sentinel.read_bytes())

    def test_wrong_equal_tree_attempt_job_window_and_digest_reject_before_secret(self):
        self.environment.forbid_secret = True
        cases = ((self.commit["tree"], "sha", "a" * 40), (self.run, "run_attempt", 3),
                 (self.job, "conclusion", "failure"), (self.artifact, "created_at", "2026-09-06T11:00:00Z"),
                 (self.artifact, "digest", "sha256:" + "0" * 64))
        for record, name, value in cases:
            previous = record[name]
            record[name] = value
            try:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    self.invoke()
                self.assertFalse(self.destination.exists())
            finally:
                record[name] = previous
        self.assertEqual(0, self.environment.secret_reads)

    def test_tampered_signed_original_or_recursive_wrapper_reject_before_secret(self):
        self.environment.forbid_secret = True
        root = self.work / "tampered"
        snapshot_regular_tree(self.wrapper, root, allow_empty=True)
        receipt = root / "retained-release/aggregate-input/metadata-receipt.json"
        raw = receipt.read_bytes()
        receipt.write_bytes(raw + b"\n")
        self.pack(root)
        with self.assertRaises(ValueError):
            self.invoke()
        receipt.write_bytes(raw)
        value = load_canonical_json_bytes((root / "caller.json").read_bytes())
        value["releaseDirectory"] = "retained-release/retained-release"
        (root / "caller.json").write_bytes(canonical_json_bytes(value))
        self.pack(root)
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertEqual(0, self.environment.secret_reads)
        self.assertFalse(self.destination.exists())

    def test_unrelated_private_key_cannot_publish_under_caller_public_policy(self):
        private, _, _ = generate_development_key(self.work / "unrelated-key")
        self.environment.values[SECRET] = private.read_text()
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertEqual(1, self.environment.secret_reads)
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.original_inventory, regular_file_inventory(self.carrier, allow_empty=True))

    def test_late_candidate_mutation_cannot_publish_even_after_real_catalog_verification(self):
        original_stage = caller.transport.stage_promoted_aggregate_catalog
        tracked = self.candidate / "gradle/release/versions/contract.txt"
        before = tracked.read_bytes()

        def stage(*args, **kwargs):
            result = original_stage(*args, **kwargs)
            tracked.write_bytes(before + b"late change\n")
            return result

        try:
            with patch.object(caller.transport, "stage_promoted_aggregate_catalog", side_effect=stage), \
                    self.assertRaisesRegex(ValueError, "modified tracked"):
                self.invoke()
        finally:
            tracked.write_bytes(before)
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.original_inventory, regular_file_inventory(self.carrier, allow_empty=True))


if __name__ == "__main__":
    unittest.main()
