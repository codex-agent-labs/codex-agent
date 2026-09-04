from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


CI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CI_ROOT))

import product_reuse  # noqa: E402
from products.inventory import canonical_json_bytes, sha256_bytes  # noqa: E402
from products.registry import PHASE_INSTANCE_IDS, PhaseInstanceId  # noqa: E402


COMMIT = "a" * 40
TREE = "b" * 40


def impact_plan(*, changed: list[str], full_requested: bool = False, event: str = "pull_request") -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "event": event,
        "repository": "codex-agent-labs/codex-agent",
        "pullRequest": 31 if event != "workflow_dispatch" else None,
        "baseCommit": "c" * 40,
        "headCommit": COMMIT,
        "validationCommit": COMMIT,
        "validationTree": TREE,
        "mergeReady": True,
        "remoteBuildAuthorized": True,
        "remoteBuildAuthorizationReason": "pull-request-final" if event == "pull_request" else "workflow-dispatch",
        "androidEvidenceRequired": False,
        "fullRequested": full_requested,
        "full": True,
        "unknownPaths": [],
        "changedPaths": changed,
        "lanes": {},
    }


class ProductReuseAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.plan_path = self.root / "impact-plan.json"
        self.output = self.root / "github-output"
        self.destination = self.root / "reuse"

    def write_plan(self, value: dict[str, object]) -> None:
        self.plan_path.write_text(json.dumps(value), encoding="utf-8")

    def run_discover(self, plan: dict[str, object], **patches: object) -> dict[str, object]:
        self.write_plan(plan)
        selection = patches.pop("selection", mock.Mock(instances=(), unknown_paths=()))
        with mock.patch.object(product_reuse, "validate_remote_build_authorization"), \
                mock.patch.object(product_reuse, "validate_legacy_lane_projection"), \
                mock.patch.object(product_reuse, "_git_value", side_effect=(COMMIT, TREE)), \
                mock.patch.object(product_reuse, "classify_paths", return_value=selection), \
                (mock.patch.multiple(product_reuse, **patches) if patches else nullcontext()):
            return product_reuse.discover(
                self.plan_path, self.destination, self.output,
                repository_root=self.root, environ={},
            )

    def outputs(self) -> dict[str, str]:
        return dict(line.split("=", 1) for line in self.output.read_text().splitlines())

    def test_no_product_work_is_the_only_vacuous_full_reuse(self) -> None:
        result = self.run_discover(impact_plan(changed=["README.md"]))
        self.assertEqual("no-product-work", result["reason"])
        self.assertTrue(result["fullReuse"])
        self.assertFalse(result["targetJobsRequired"])
        self.assertEqual("false", self.outputs()["target_jobs_required"])
        persisted = json.loads((self.destination / "request.json").read_text())
        self.assertEqual([], persisted["requested"])

    def test_plan_full_does_not_broaden_the_product_selection(self) -> None:
        selected = PhaseInstanceId("contract", "contract", "binary", "common")
        selection = mock.Mock(instances=(selected,), unknown_paths=())
        result = self.run_discover(
            impact_plan(changed=["known.kt"], full_requested=False),
            selection=selection,
            _dependency_closure=mock.Mock(return_value=(selected,)),
            _authorities=mock.Mock(return_value=(None, "phase-authority-unavailable")),
        )
        self.assertEqual([product_reuse._identity_record(selected)], result["requested"])
        self.assertTrue(result["targetJobsRequired"])

    def test_explicit_full_request_selects_every_registered_phase(self) -> None:
        result = self.run_discover(
            impact_plan(changed=["known.kt"], full_requested=True),
            selection=mock.Mock(instances=(), unknown_paths=()),
            _dependency_closure=mock.Mock(return_value=PHASE_INSTANCE_IDS),
            _authorities=mock.Mock(return_value=(None, "toolchain-profile-unavailable")),
        )
        self.assertEqual(len(PHASE_INSTANCE_IDS), len(result["requested"]))
        self.assertEqual("toolchain-profile-unavailable", result["reason"])

    def test_unknown_path_selects_every_registered_phase(self) -> None:
        plan = impact_plan(changed=["unknown/new.file"])
        plan["unknownPaths"] = ["unknown/new.file"]
        result = self.run_discover(
            plan,
            selection=mock.Mock(instances=PHASE_INSTANCE_IDS, unknown_paths=("unknown/new.file",)),
            _dependency_closure=mock.Mock(return_value=PHASE_INSTANCE_IDS),
            _authorities=mock.Mock(return_value=(None, "phase-authority-unavailable")),
        )
        self.assertEqual(len(PHASE_INSTANCE_IDS), len(result["requested"]))

    def test_workflow_dispatch_never_discovers_remote_catalogs(self) -> None:
        selected = PhaseInstanceId("contract", "contract", "binary", "common")
        discover_catalogs = mock.Mock()
        result = self.run_discover(
            impact_plan(changed=["known.kt"], event="workflow_dispatch"),
            selection=mock.Mock(instances=(selected,), unknown_paths=()),
            _discover_catalogs=discover_catalogs,
        )
        self.assertEqual("workflow-dispatch-reuse-disabled", result["reason"])
        discover_catalogs.assert_not_called()

    def test_checkout_mismatch_fails_after_writing_safe_default_outputs(self) -> None:
        self.write_plan(impact_plan(changed=[]))
        with mock.patch.object(product_reuse, "validate_remote_build_authorization"), \
                mock.patch.object(product_reuse, "validate_legacy_lane_projection"), \
                mock.patch.object(product_reuse, "_git_value", return_value="d" * 40):
            with self.assertRaisesRegex(ValueError, "Checkout commit"):
                product_reuse.discover(
                    self.plan_path, self.destination, self.output,
                    repository_root=self.root, environ={},
                )
        self.assertEqual("true", self.outputs()["target_jobs_required"])
        self.assertEqual("false", self.outputs()["full_reuse"])

    def test_destination_rejects_leaf_and_parent_symlinks(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        leaf = self.root / "leaf"
        leaf.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "unsafe parent"):
            product_reuse._prepare_destination(leaf, self.root)
        parent = self.root / "parent"
        parent.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "unsafe parent"):
            product_reuse._prepare_destination(parent / "reuse", self.root)
        (outside / "existing").mkdir()
        nested = self.root / "nested"
        nested.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "unsafe parent"):
            product_reuse._prepare_destination(nested / "existing" / "reuse", self.root)
        with self.assertRaisesRegex(ValueError, "inside the repository"):
            product_reuse._prepare_destination(outside.parent / "elsewhere", outside)

    def test_matching_catalog_with_unexpected_member_is_rejected(self) -> None:
        catalog = self.root / "catalog.zip"
        index = {
            "schemaVersion": 1,
            "repository": "codex-agent-labs/codex-agent",
            "context": {
                "kind": "pull-request", "pullRequest": 31, "commit": COMMIT, "tree": TREE,
                "runId": 7, "runAttempt": 1,
            },
            "entries": [],
            "trustDomain": "development",
            "signing": {
                "algorithm": "ssh-ed25519", "namespace": "codex-agent-product-v1",
                "keyId": "development", "fingerprint": sha256_bytes(b"key"),
            },
            "producer": {
                "repository": "codex-agent-labs/codex-agent",
                "workflowPath": ".github/workflows/product-validation.yml",
                "commit": COMMIT, "tree": TREE, "event": "pull_request", "runId": 7,
                "runAttempt": 1, "pullRequest": 31,
            },
        }
        with zipfile.ZipFile(catalog, "w") as archive:
            archive.writestr("product-index.json", canonical_json_bytes(index))
            archive.writestr("product-index.sig", b"signature")
            archive.writestr("public-key.pub", b"key")
            archive.writestr("unexpected.txt", b"no")
        artifact = {
            "id": 7,
            "archive_download_url": "https://example.invalid/archive",
            "digest": sha256_bytes(catalog.read_bytes()),
        }
        with mock.patch.object(product_reuse, "download_artifact", return_value=catalog.read_bytes()), \
                mock.patch.object(product_reuse, "validate_product_index", return_value=index):
            with self.assertRaisesRegex(ValueError, "file set"):
                product_reuse._materialize_catalog(
                    "same-pr", artifact, "token", self.root / "materialized",
                    "codex-agent-labs/codex-agent", 31, None, {
                        "id": 7, "run_attempt": 1, "head_sha": COMMIT,
                    },
                )

    def test_catalog_discovery_is_source_ordered_and_downloads_one_artifact_per_index(self) -> None:
        artifacts = [
            {"id": 2, "name": "codex-agent-product-catalog-v1-stable-sdk-0.2.0", "expired": False},
            {"id": 5, "name": "codex-agent-product-catalog-v1-promoted-main-new", "expired": False},
            {"id": 4, "name": "codex-agent-product-catalog-v1-promoted-main-old", "expired": False},
            {"id": 7, "name": "codex-agent-product-catalog-v1-pull-request-31-new", "expired": False},
            {"id": 6, "name": "codex-agent-product-catalog-v1-pull-request-31-old", "expired": False},
        ]
        trust = product_reuse.ReleaseTrust(self.root / "keyring", self.root / "keys")

        def materialize(source: str, artifact: dict[str, object], *_: object) -> product_reuse.Catalog:
            return product_reuse.Catalog(source, {}, str(artifact["id"]), {}, {})

        with mock.patch.object(product_reuse, "paginated_items", return_value=artifacts) as listed, \
                mock.patch.object(product_reuse, "_same_pr_run", return_value={
                    "id": 7, "run_attempt": 1, "head_sha": COMMIT,
                }), \
                mock.patch.object(product_reuse, "_materialize_catalog", side_effect=materialize) as downloaded:
            catalogs = product_reuse._discover_catalogs(
                impact_plan(changed=["known.kt"]), self.root / "catalogs", trust,
                {
                    "GITHUB_TOKEN": "token", "GITHUB_API_URL": "https://api.github.test",
                    "GITHUB_REPOSITORY": "codex-agent-labs/codex-agent",
                },
                {
                    "contract": "0.2.0", "runtime-release": "0.2.0",
                    "runtime-compatibility": "0.2.0", "sdk": "0.2.0",
                },
            )
        self.assertEqual(
            [("stable", "2"), ("promoted-main", "5"), ("same-pr", "7")],
            [(catalog.source, catalog.index_sha256) for catalog in catalogs],
        )
        listed.assert_called_once()
        self.assertEqual(3, downloaded.call_count)

    def test_same_pr_catalog_requires_actual_successful_ci_run_and_matching_claims(self) -> None:
        artifact = {
            "workflow_run": {"id": 7, "head_sha": COMMIT},
        }
        good_run = {
            "id": 7, "run_attempt": 2, "status": "completed", "conclusion": "success",
            "event": "pull_request", "path": ".github/workflows/ci.yml", "head_sha": COMMIT,
            "pull_requests": [{"number": 31}],
        }
        with mock.patch.object(product_reuse, "api_json", return_value=good_run):
            self.assertEqual(
                good_run,
                product_reuse._same_pr_run(
                    artifact, "https://api.github.test", "codex-agent-labs/codex-agent", 31, "token",
                ),
            )
        for change in (
            {"conclusion": "failure"},
            {"path": ".github/workflows/untrusted.yml"},
            {"head_sha": "d" * 40},
            {"pull_requests": [{"number": 32}]},
        ):
            with self.subTest(change=change), mock.patch.object(
                product_reuse, "api_json", return_value={**good_run, **change},
            ):
                with self.assertRaisesRegex(ValueError, "allowed successful CI run"):
                    product_reuse._same_pr_run(
                        artifact, "https://api.github.test", "codex-agent-labs/codex-agent", 31, "token",
                    )

    def test_complete_result_is_reverified_before_jobs_can_be_skipped(self) -> None:
        selected = PhaseInstanceId("contract", "contract", "binary", "common")
        authorities = [{
            **product_reuse._identity_record(selected),
            "toolchainProfileDigest": sha256_bytes(b"toolchain"),
            "flagsDigest": sha256_bytes(b"flags"),
            "outputSchemaVersion": 1,
        }]
        reuse = {
            "schemaVersion": 1, "result": "complete", "fullReuse": True,
            "phases": [], "matrices": {"contract": [], "runtime": [], "sdk": []},
        }
        reverify = mock.Mock()
        result = self.run_discover(
            impact_plan(changed=["known.kt"]),
            selection=mock.Mock(instances=(selected,), unknown_paths=()),
            _dependency_closure=mock.Mock(return_value=(selected,)),
            _authorities=mock.Mock(return_value=(authorities, None)),
            _versions=mock.Mock(return_value={
                "contract": "0.2.0", "runtime-release": "0.2.0",
                "runtime-compatibility": "0.2.0", "sdk": "0.2.0",
            }),
            _release_trust=mock.Mock(return_value=None),
            _discover_catalogs=mock.Mock(return_value=[]),
            plan_reuse_wave=mock.Mock(return_value=reuse),
            _reverify_complete=reverify,
        )
        reverify.assert_called_once()
        self.assertEqual("verified-full-reuse", result["reason"])
        self.assertFalse(result["targetJobsRequired"])

    def test_incomplete_result_keeps_target_jobs_required(self) -> None:
        selected = PhaseInstanceId("contract", "contract", "binary", "common")
        authorities = [{
            **product_reuse._identity_record(selected),
            "toolchainProfileDigest": sha256_bytes(b"toolchain"),
            "flagsDigest": sha256_bytes(b"flags"),
            "outputSchemaVersion": 1,
        }]
        reuse = {
            "schemaVersion": 1, "result": "build-required", "fullReuse": False,
            "phases": [], "matrices": {"contract": [{}], "runtime": [], "sdk": []},
        }
        result = self.run_discover(
            impact_plan(changed=["known.kt"]),
            selection=mock.Mock(instances=(selected,), unknown_paths=()),
            _dependency_closure=mock.Mock(return_value=(selected,)),
            _authorities=mock.Mock(return_value=(authorities, None)),
            _versions=mock.Mock(return_value={
                "contract": "0.2.0", "runtime-release": "0.2.0",
                "runtime-compatibility": "0.2.0", "sdk": "0.2.0",
            }),
            _release_trust=mock.Mock(return_value=None),
            _discover_catalogs=mock.Mock(return_value=[]),
            plan_reuse_wave=mock.Mock(return_value=reuse),
        )
        self.assertEqual("product-build-required", result["reason"])
        self.assertTrue(result["targetJobsRequired"])


if __name__ == "__main__":
    unittest.main()
