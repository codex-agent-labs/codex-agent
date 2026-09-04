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
from products.plan import plan_phase  # noqa: E402
from products.receipt import write_output_manifest  # noqa: E402
from products.registry import PHASE_INSTANCE_IDS, PhaseInstanceId  # noqa: E402
from products.restore import finalize_phase_object, verify_carrier, verify_phase_shard  # noqa: E402


COMMIT = "a" * 40
TREE = "b" * 40
VERSIONS = {
    "contract": "0.2.0",
    "runtime-release": "0.2.0",
    "runtime-compatibility": "0.2.0",
    "sdk": "0.2.0",
}


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
        environment = patches.pop("environ", {})
        with mock.patch.object(product_reuse, "validate_remote_build_authorization"), \
                mock.patch.object(product_reuse, "validate_legacy_lane_projection"), \
                mock.patch.object(product_reuse, "_git_value", side_effect=(COMMIT, TREE)), \
                mock.patch.object(product_reuse, "classify_paths", return_value=selection), \
                (mock.patch.multiple(product_reuse, **patches) if patches else nullcontext()):
            return product_reuse.discover(
                self.plan_path, self.destination, self.output,
                repository_root=self.root, environ=environment,
            )

    def outputs(self) -> dict[str, str]:
        return dict(line.split("=", 1) for line in self.output.read_text().splitlines())

    def test_authorities_are_derived_and_native_profiles_fail_closed(self) -> None:
        contract = PhaseInstanceId("contract", "contract", "binary", "common")
        native = PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64")
        with mock.patch.object(product_reuse, "tree_entries", return_value=[]), \
                mock.patch.object(product_reuse, "git_regular_blob_bytes") as read_blob:
            records, reason = product_reuse._authorities(self.root, COMMIT, (contract,))
            self.assertIsNone(reason)
            self.assertEqual([{
                **product_reuse._identity_record(contract),
                "toolchainProfileDigest": product_reuse.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                "flagsDigest": product_reuse.NOT_APPLICABLE_FLAGS_DIGEST,
                "outputSchemaVersion": 1,
            }], records)
            read_blob.assert_not_called()

            records, reason = product_reuse._authorities(self.root, COMMIT, (native,))
            self.assertIsNone(records)
            self.assertEqual("toolchain-profile-unavailable", reason)
            read_blob.assert_not_called()

    def test_malformed_present_authority_is_a_hard_failure(self) -> None:
        native = PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64")
        profile = product_reuse.required_toolchain_profile(native)
        with mock.patch.object(
            product_reuse,
            "tree_entries",
            return_value=[(f"{product_reuse._PROFILE_ROOT}/{profile}.json", object())],
        ), mock.patch.object(
            product_reuse, "git_regular_blob_bytes", return_value=b"{}"
        ), self.assertRaises(ValueError):
            product_reuse._authorities(self.root, COMMIT, (native,))

    def test_native_profile_lookup_waits_until_contract_is_fully_reused(self) -> None:
        native = PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64")
        contract_records = [{
            **product_reuse._identity_record(instance),
            "toolchainProfileDigest": product_reuse.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            "flagsDigest": product_reuse.NOT_APPLICABLE_FLAGS_DIGEST,
            "outputSchemaVersion": 1,
        } for instance in product_reuse._dependency_closure((
            PhaseInstanceId("contract", "contract", "metadata", "common"),
        ))]
        contract_result = {
            "schemaVersion": 1,
            "result": "complete",
            "fullReuse": True,
            "phases": [],
            "matrices": {"contract": [], "runtime": [], "sdk": []},
        }
        authorities = mock.Mock(side_effect=(
            (contract_records, None),
            (None, "toolchain-profile-unavailable"),
        ))
        wave = mock.Mock(return_value=contract_result)
        result = self.run_discover(
            impact_plan(changed=["native.kt"]),
            selection=mock.Mock(instances=(native,), unknown_paths=()),
            _authorities=authorities,
            _versions=mock.Mock(return_value=VERSIONS),
            _release_trust=mock.Mock(return_value=None),
            _discover_catalogs=mock.Mock(return_value=[]),
            _wave_request=mock.Mock(return_value={}),
            plan_reuse_wave=wave,
            _contract_evidence=mock.Mock(return_value=object()),
        )
        self.assertEqual("toolchain-profile-unavailable", result["reason"])
        self.assertEqual(2, authorities.call_count)
        wave.assert_called_once()

    def test_native_request_emits_only_the_ready_contract_plan_without_profiles(self) -> None:
        native = PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64")
        contract_binary = PhaseInstanceId("contract", "contract", "binary", "common")
        contract_records = [{
            **product_reuse._identity_record(instance),
            "toolchainProfileDigest": product_reuse.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            "flagsDigest": product_reuse.NOT_APPLICABLE_FLAGS_DIGEST,
            "outputSchemaVersion": 1,
        } for instance in product_reuse._dependency_closure((
            PhaseInstanceId("contract", "contract", "metadata", "common"),
        ))]
        phase_plan = {
            "schemaVersion": 1,
            **product_reuse._identity_record(contract_binary),
            "buildKey": sha256_bytes(b"contract-build"),
            "inputs": {"authority": "planner-owned"},
        }

        def contract_wave(_request, *, build_plan_consumer):
            build_plan_consumer(contract_binary, phase_plan)
            return {
                "schemaVersion": 1,
                "result": "build-required",
                "fullReuse": False,
                "phases": [],
                "matrices": {"contract": [{}], "runtime": [], "sdk": []},
            }

        authorities = mock.Mock(return_value=(contract_records, None))
        result = self.run_discover(
            impact_plan(changed=["native.kt"]),
            selection=mock.Mock(instances=(native,), unknown_paths=()),
            _authorities=authorities,
            _versions=mock.Mock(return_value=VERSIONS),
            _release_trust=mock.Mock(return_value=None),
            _discover_catalogs=mock.Mock(return_value=[]),
            _wave_request=mock.Mock(return_value={}),
            plan_reuse_wave=mock.Mock(side_effect=contract_wave),
            environ={"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"},
        )
        self.assertEqual("product-build-required", result["reason"])
        authorities.assert_called_once()
        self.assertEqual(
            canonical_json_bytes(phase_plan),
            (self.destination / "phase-plans/contract-contract-binary-common.json").read_bytes(),
        )

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
            _versions=mock.Mock(return_value=VERSIONS),
            _release_trust=mock.Mock(return_value=None),
            _discover_catalogs=mock.Mock(return_value=[]),
        )
        self.assertEqual([product_reuse._identity_record(selected)], result["requested"])
        self.assertTrue(result["targetJobsRequired"])

    def test_explicit_full_request_selects_every_registered_phase(self) -> None:
        contract_closure = tuple(
            instance for instance in PHASE_INSTANCE_IDS if instance.product == "contract"
        )
        result = self.run_discover(
            impact_plan(changed=["known.kt"], full_requested=True),
            selection=mock.Mock(instances=(), unknown_paths=()),
            _dependency_closure=mock.Mock(side_effect=lambda requested: (
                contract_closure if requested == (
                    PhaseInstanceId("contract", "contract", "metadata", "common"),
                ) else PHASE_INSTANCE_IDS
            )),
            _authorities=mock.Mock(return_value=([{
                **product_reuse._identity_record(instance),
                "toolchainProfileDigest": product_reuse.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                "flagsDigest": product_reuse.NOT_APPLICABLE_FLAGS_DIGEST,
                "outputSchemaVersion": 1,
            } for instance in contract_closure], None)),
            _versions=mock.Mock(return_value=VERSIONS),
            _release_trust=mock.Mock(return_value=None),
            _discover_catalogs=mock.Mock(return_value=[]),
            plan_reuse_wave=mock.Mock(return_value={
                "schemaVersion": 1, "result": "build-required", "fullReuse": False,
                "phases": [], "matrices": {"contract": [{}], "runtime": [], "sdk": []},
            }),
        )
        self.assertEqual(len(PHASE_INSTANCE_IDS), len(result["requested"]))
        self.assertEqual("product-build-required", result["reason"])

    def test_unknown_path_selects_every_registered_phase(self) -> None:
        plan = impact_plan(changed=["unknown/new.file"])
        plan["unknownPaths"] = ["unknown/new.file"]
        contract_closure = tuple(
            instance for instance in PHASE_INSTANCE_IDS if instance.product == "contract"
        )
        result = self.run_discover(
            plan,
            selection=mock.Mock(instances=PHASE_INSTANCE_IDS, unknown_paths=("unknown/new.file",)),
            _dependency_closure=mock.Mock(side_effect=lambda requested: (
                contract_closure if requested == (
                    PhaseInstanceId("contract", "contract", "metadata", "common"),
                ) else PHASE_INSTANCE_IDS
            )),
            _authorities=mock.Mock(return_value=([{
                **product_reuse._identity_record(instance),
                "toolchainProfileDigest": product_reuse.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                "flagsDigest": product_reuse.NOT_APPLICABLE_FLAGS_DIGEST,
                "outputSchemaVersion": 1,
            } for instance in contract_closure], None)),
            _versions=mock.Mock(return_value=VERSIONS),
            _release_trust=mock.Mock(return_value=None),
            _discover_catalogs=mock.Mock(return_value=[]),
            plan_reuse_wave=mock.Mock(return_value={
                "schemaVersion": 1, "result": "build-required", "fullReuse": False,
                "phases": [], "matrices": {"contract": [{}], "runtime": [], "sdk": []},
            }),
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
            environ={"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"},
        )
        reverify.assert_called_once()
        self.assertEqual(
            {
                "kind": "ci",
                "producer": {
                    "repository": "codex-agent-labs/codex-agent",
                    "workflowPath": ".github/workflows/ci.yml",
                    "commit": COMMIT,
                    "tree": TREE,
                    "event": "pull_request",
                    "runId": 7,
                    "runAttempt": 2,
                    "pullRequest": 31,
                },
            },
            reverify.call_args.args[4],
        )
        self.assertEqual("verified-full-reuse", result["reason"])
        self.assertFalse(result["targetJobsRequired"])

    def test_partial_remote_reuse_is_preserved_as_an_exact_prefix_carrier(self) -> None:
        requested = PhaseInstanceId("contract", "contract", "metadata", "common")
        closure = product_reuse._dependency_closure((requested,))
        binary = PhaseInstanceId("contract", "contract", "binary", "common")
        package = PhaseInstanceId("contract", "contract", "package", "common")
        build_key = sha256_bytes(b"binary-plan")
        package_build_key = sha256_bytes(b"package-plan")
        receipt_digest = sha256_bytes(b"binary-receipt")
        object_digest = sha256_bytes(b"binary-object")
        phases = []
        for instance in closure:
            reused = instance == binary
            build = instance == package
            phases.append({
                **product_reuse._identity_record(instance),
                "buildKey": build_key if reused else package_build_key if build else None,
                "state": "reused" if reused else "build" if build else "waiting",
                "source": "same-pr" if reused else None,
                "transportSource": {
                    "kind": "same-pr",
                    "indexSha256": sha256_bytes(b"index"),
                    "artifactName": "contract.bin",
                    "artifactSha256": sha256_bytes(b"artifact"),
                } if reused else None,
                "receiptSha256": receipt_digest if reused else None,
                "objectSha256": object_digest if reused else None,
                "misses": [
                    {"source": source, "reason": "fixture-miss"}
                    for source in product_reuse.SOURCES
                ] if build else [
                    {"source": source, "reason": "fixture-miss"}
                    for source in product_reuse.SOURCES[:2]
                ] if reused else [],
            })
        result = {
            "schemaVersion": 1,
            "result": "build-required",
            "fullReuse": False,
            "phases": phases,
            "matrices": {"contract": [{
                **product_reuse._identity_record(package),
                "buildKey": package_build_key,
            }], "runtime": [], "sdk": []},
        }
        object_path = self.root / "binary.zip"
        catalog = product_reuse.Catalog(
            "same-pr", {}, sha256_bytes(b"index"), {}, {build_key: object_path},
        )
        receipt = {**product_reuse._identity_record(binary)}
        with mock.patch.object(
            product_reuse,
            "verify_object",
            return_value={"receipt": receipt},
        ), mock.patch.object(product_reuse, "write_carrier") as write:
            self.assertTrue(product_reuse._write_reused_carrier(
                result,
                (requested,),
                [catalog],
                self.root / "carrier",
                {"kind": "ci", "producer": {}},
                require_complete=False,
            ))
        normalized = write.call_args.args[1]
        self.assertEqual([phases[closure.index(binary)]], normalized["phases"])
        self.assertEqual((binary,), write.call_args.args[2])
        self.assertEqual({binary: object_path}, write.call_args.args[3])
        self.assertEqual("complete", normalized["result"])
        self.assertTrue(normalized["fullReuse"])

        contradictions = []
        wrong_completion = json.loads(json.dumps(result))
        wrong_completion["fullReuse"] = True
        contradictions.append(("contradicts", wrong_completion))
        wrong_matrix = json.loads(json.dumps(result))
        wrong_matrix["matrices"]["contract"] = []
        contradictions.append(("matrices", wrong_matrix))
        wrong_schema = json.loads(json.dumps(result))
        wrong_schema["schemaVersion"] = 2
        contradictions.append(("schemaVersion", wrong_schema))
        unknown_result_key = json.loads(json.dumps(result))
        unknown_result_key["unexpected"] = True
        contradictions.append(("fields are invalid", unknown_result_key))
        unknown_phase_key = json.loads(json.dumps(result))
        unknown_phase_key["phases"][0]["unexpected"] = True
        contradictions.append(("fields are invalid", unknown_phase_key))
        build_evidence = json.loads(json.dumps(result))
        build_evidence["phases"][closure.index(package)]["receiptSha256"] = receipt_digest
        contradictions.append(("materialized evidence", build_evidence))
        waiting_evidence = json.loads(json.dumps(result))
        waiting_evidence["phases"][2]["source"] = "stable"
        contradictions.append(("materialized evidence", waiting_evidence))
        missing_build_miss = json.loads(json.dumps(result))
        missing_build_miss["phases"][closure.index(package)]["misses"].pop()
        contradictions.append(("every lookup miss", missing_build_miss))
        reordered_build_misses = json.loads(json.dumps(result))
        reordered_build_misses["phases"][closure.index(package)]["misses"].reverse()
        contradictions.append(("every lookup miss", reordered_build_misses))
        duplicate_build_miss = json.loads(json.dumps(result))
        duplicate_build_miss["phases"][closure.index(package)]["misses"].append(
            duplicate_build_miss["phases"][closure.index(package)]["misses"][-1]
        )
        contradictions.append(("every lookup miss", duplicate_build_miss))
        missing_reuse_miss = json.loads(json.dumps(result))
        missing_reuse_miss["phases"][closure.index(binary)]["misses"].pop()
        contradictions.append(("source ordered", missing_reuse_miss))
        reordered_reuse_misses = json.loads(json.dumps(result))
        reordered_reuse_misses["phases"][closure.index(binary)]["misses"].reverse()
        contradictions.append(("source ordered", reordered_reuse_misses))
        duplicate_reuse_miss = json.loads(json.dumps(result))
        duplicate_reuse_miss["phases"][closure.index(binary)]["misses"].append(
            duplicate_reuse_miss["phases"][closure.index(binary)]["misses"][-1]
        )
        contradictions.append(("source ordered", duplicate_reuse_miss))
        for error, contradictory in contradictions:
            with self.subTest(error=error), mock.patch.object(
                product_reuse,
                "verify_object",
                return_value={"receipt": receipt},
            ), mock.patch.object(product_reuse, "write_carrier") as rejected_write:
                with self.assertRaisesRegex(ValueError, error):
                    product_reuse._write_reused_carrier(
                        contradictory,
                        (requested,),
                        [catalog],
                        self.root / "rejected-carrier",
                        {"kind": "ci", "producer": {}},
                        require_complete=False,
                    )
                rejected_write.assert_not_called()

    def test_partial_reuse_carrier_rejects_a_nonclosed_phase_set(self) -> None:
        requested = PhaseInstanceId("contract", "contract", "metadata", "common")
        closure = product_reuse._dependency_closure((requested,))
        package = PhaseInstanceId("contract", "contract", "package", "common")
        build_key = sha256_bytes(b"package-plan")
        receipt_digest = sha256_bytes(b"package-receipt")
        object_digest = sha256_bytes(b"package-object")
        phases = [{
            **product_reuse._identity_record(instance),
            "buildKey": build_key if instance == package else None,
            "state": "reused" if instance == package else "waiting",
            "source": "stable" if instance == package else None,
            "transportSource": {
                "kind": "stable",
                "indexSha256": sha256_bytes(b"index"),
                "artifactName": "contract.bin",
                "artifactSha256": sha256_bytes(b"artifact"),
            } if instance == package else None,
            "receiptSha256": receipt_digest if instance == package else None,
            "objectSha256": object_digest if instance == package else None,
            "misses": [],
        } for instance in closure]
        result = {
            "schemaVersion": 1,
            "result": "build-required",
            "fullReuse": False,
            "phases": phases,
            "matrices": {"contract": [], "runtime": [], "sdk": []},
        }
        catalog = product_reuse.Catalog(
            "stable", {}, sha256_bytes(b"index"), {}, {build_key: self.root / "package.zip"},
        )
        with mock.patch.object(
            product_reuse,
            "verify_object",
            return_value={"receipt": product_reuse._identity_record(package)},
        ), mock.patch.object(product_reuse, "write_carrier") as write:
            with self.assertRaisesRegex(ValueError, "dependency-closed"):
                product_reuse._write_reused_carrier(
                    result,
                    (requested,),
                    [catalog],
                    self.root / "carrier",
                    {"kind": "ci", "producer": {}},
                    require_complete=False,
                )
        write.assert_not_called()

    def test_reused_carrier_preserves_real_object_and_receipt_bytes(self) -> None:
        binary = PhaseInstanceId("contract", "contract", "binary", "common")
        resolved_root = self.root.resolve()
        stage = resolved_root / "stage"
        output = stage / "outputs/value.bin"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"value")
        write_output_manifest(
            stage, "contract", "contract", "binary", "common", "0.2.0",
            {"artifact": "outputs"},
        )
        plan = plan_phase(
            binary,
            inventory=[{"relativePath": "input.kt", "bytes": 1, "sha256": sha256_bytes(b"i")}],
            versions=VERSIONS,
            upstream_receipts=[],
            toolchain_profile_digest=product_reuse.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            flags_digest=product_reuse.NOT_APPLICABLE_FLAGS_DIGEST,
        )
        consumer = product_reuse._consumer(
            impact_plan(changed=["input.kt"]),
            {"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "1"},
        )
        shard = resolved_root / "shard"
        finalize_phase_object(
            stage_root=stage,
            phase_plan=plan,
            producer=consumer["producer"],
            product_version="0.2.0",
            trust_domain="development",
            destination=shard,
        )
        verified_shard = verify_phase_shard(shard, binary)
        descriptor = verified_shard
        source = {
            "kind": "same-pr",
            "indexSha256": sha256_bytes(b"index"),
            "artifactName": "value.bin",
            "artifactSha256": sha256_bytes(b"value"),
        }
        result = {
            "schemaVersion": 1,
            "result": "complete",
            "fullReuse": True,
            "phases": [{
                **product_reuse._identity_record(binary),
                "buildKey": descriptor["buildKey"],
                "state": "reused",
                "source": "same-pr",
                "transportSource": source,
                "receiptSha256": descriptor["receiptSha256"],
                "objectSha256": descriptor["objectSha256"],
                "misses": [
                    {"source": name, "reason": "fixture-miss"}
                    for name in product_reuse.SOURCES[:2]
                ],
            }],
            "matrices": {"contract": [], "runtime": [], "sdk": []},
        }
        catalog = product_reuse.Catalog(
            "same-pr", {}, source["indexSha256"], {}, {
                descriptor["buildKey"]: shard / descriptor["objectPath"],
            },
        )
        carrier = resolved_root / "carrier"
        self.assertTrue(product_reuse._write_reused_carrier(
            result, (binary,), [catalog], carrier, consumer, require_complete=False,
        ))
        verified_carrier = verify_carrier(carrier, (binary,), consumer)
        self.assertEqual(
            (shard / "phase-receipt.json").read_bytes(),
            verified_carrier["objects"][0]["receiptBytes"],
        )

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
        phase_plan = {
            "schemaVersion": 1,
            **product_reuse._identity_record(selected),
            "buildKey": sha256_bytes(b"build"),
            "inputs": {"exact": "planner-owned"},
        }

        def plan_wave(_request, *, build_plan_consumer):
            build_plan_consumer(selected, phase_plan)
            return reuse

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
            plan_reuse_wave=mock.Mock(side_effect=plan_wave),
            environ={"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"},
        )
        self.assertEqual("product-build-required", result["reason"])
        self.assertTrue(result["targetJobsRequired"])
        self.assertEqual(
            canonical_json_bytes(phase_plan),
            (self.destination / "phase-plans/contract-contract-binary-common.json").read_bytes(),
        )
        self.assertEqual(
            product_reuse._consumer(
                impact_plan(changed=["known.kt"]),
                {"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"},
            )["producer"],
            json.loads((self.destination / "producer.json").read_text()),
        )


if __name__ == "__main__":
    unittest.main()
