"""Exact native family projection; no election, host or source authority claim."""

from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import product_reuse
import sdk_workflow
from products.inventory import canonical_json_bytes, regular_file_inventory
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PHASE_INSTANCE_IDS, PhaseInstanceId
from runtime_native_phase import _HOSTS


class SdkNativeFamilySelectionTest(unittest.TestCase):
    def test_native_validation_is_exactly_five_languages_on_five_native_hosts(self):
        expected = {PhaseInstanceId("sdk", language, "validation", target)
                    for language in NATIVE_BINDINGS for target in NATIVE_TARGETS}
        self.assertEqual(25, len(expected))
        self.assertTrue(expected.issubset(PHASE_INSTANCE_IDS))
        self.assertEqual(expected, {identity for identity in PHASE_INSTANCE_IDS
            if product_reuse._sdk_family_worker_instance(identity, "native-validation")})
        self.assertEqual({"linux-arm64", "linux-x64", "macos-arm64", "macos-x64", "windows-x64"},
                         {identity.target for identity in expected})

    def test_native_metadata_is_exactly_five_desktop_instances_not_five_host_fanout(self):
        expected = {PhaseInstanceId("sdk", language, "metadata", "desktop") for language in NATIVE_BINDINGS}
        self.assertEqual(5, len(expected))
        self.assertTrue(expected.issubset(PHASE_INSTANCE_IDS))
        self.assertEqual(expected, {identity for identity in PHASE_INSTANCE_IDS
            if product_reuse._sdk_family_worker_instance(identity, "native-metadata")})

    def test_wrong_product_component_phase_and_target_never_enter_native_families(self):
        for family, phase, target in (("native-validation", "validation", "linux-x64"),
                                      ("native-metadata", "metadata", "desktop")):
            invalid = [PhaseInstanceId(product, "python", phase, target) for product in ("contract", "runtime", "other")]
            invalid += [PhaseInstanceId("sdk", component, phase, target) for component in
                        ("javascript", "sdk-ios", "sdk-core", "sdk-android", "unknown")]
            invalid += [PhaseInstanceId("sdk", "python", other, target) for other in
                        ("binary", "package", "validation", "metadata", "other") if other != phase]
            invalid += [PhaseInstanceId("sdk", "python", phase, other) for other in
                        ("desktop", "node", "ios", "common", "aggregate", "unknown", *NATIVE_TARGETS)
                        if (other not in NATIVE_TARGETS if family == "native-validation" else other != "desktop")]
            for identity in invalid:
                with self.subTest(family=family, identity=identity):
                    self.assertFalse(product_reuse._sdk_family_worker_instance(identity, family))

    def test_unknown_or_non_string_family_fails_closed(self):
        identity = PhaseInstanceId("sdk", "python", "validation", "linux-x64")
        for family in ("native", "validation", "metadata", "native-validation ", "", None, True, 1, [], {}):
            with self.subTest(family=family), self.assertRaises(ValueError):
                product_reuse._sdk_family_worker_instance(identity, family)


class SdkNativeFamilyOrchestrationTest(unittest.TestCase):
    """Mocked replay/transport/advancement; real fixed routing and file retention."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-native-family-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plan = self.root / "plan.json"
        self.discovery, self.state = self.root / "discovery", self.root / "state"
        self.tooling = {"evidence": "caller-owned opaque tooling seam"}
        self.environment = {"CONTROL": "explicit environment"}

    def test_replayed_matrices_forward_caller_tooling_and_exact_fixed_hosts(self):
        ready = [{**product_reuse._identity_record(identity), "buildKey": "sha256:" + "a" * 64}
                 for identity in PHASE_INSTANCE_IDS]
        for family, count in (("native-validation", 25), ("native-metadata", 5)):
            with self.subTest(family=family), patch.object(product_reuse, "inspect_products",
                    return_value={"readyPlans": ready}) as inspect:
                result = sdk_workflow.matrix(self.plan, self.discovery, self.state, self.root / family,
                    family=family, repository_root=self.root, environ=self.environment,
                    sdk_validation_tooling=self.tooling)
                inspect.assert_called_once_with(self.plan, self.discovery, self.state,
                    repository_root=self.root, environ=self.environment, sdk_validation_tooling=self.tooling)
                self.assertIs(self.tooling, inspect.call_args.kwargs["sdk_validation_tooling"])
                self.assertEqual(count, len(result["include"]))
                for row in result["include"]:
                    self.assertTrue(product_reuse._sdk_family_worker_instance(product_reuse._identity(row), family))
                    host = row["target"] if family == "native-validation" else "linux-x64"
                    self.assertEqual(_HOSTS[host], (row["runner"], row["runnerOs"], row["runnerArch"]))

    def test_original_state_capture_forwards_same_policy_to_authenticated_matrix(self):
        destination, output = self.root / "capture", self.root / "capture-output"
        with patch.object(product_reuse, "capture_runtime_resume_upload") as capture, \
                patch.object(sdk_workflow, "matrix", return_value={"include": []}) as matrix:
            result = sdk_workflow.capture(self.plan, destination, output, artifact_id=71,
                artifact_sha256="sha256:" + "b" * 64, trusted_workflow_sha="c" * 40,
                sdk_state_wave=7, family="native-metadata", repository_root=self.root,
                environ=self.environment, token="synthetic", sdk_validation_tooling=self.tooling)
        self.assertEqual(7, capture.call_args.kwargs["sdk_state_wave"])
        self.assertIs(self.tooling, matrix.call_args.kwargs["sdk_validation_tooling"])
        self.assertEqual("native-metadata", matrix.call_args.kwargs["family"])
        self.assertEqual(destination / "original/runtime-state", result["state_root"])
        self.assertEqual(result["state_root"], matrix.call_args.args[2])

    def test_waves_preserve_siblings_and_forward_successful_validation_carriers_only(self):
        original = self.root / "original"
        for name in ("product-resume-inputs", "product-resume-state", "runtime-state"):
            path = original / name
            path.mkdir(parents=True)
            (path / "original.bin").write_bytes(name.encode() + b"\x00\xff")
            (path / "empty.log").write_bytes(b"")
        before = regular_file_inventory(original, allow_empty=True)
        for family, wave, phase in (("native-validation", 7, "validation"), ("native-metadata", 8, "metadata")):
            for failure in (False, True):
                with self.subTest(family=family, failure=failure):
                    destination = self.root / f"{family}-{failure}"
                    identities = [PhaseInstanceId("sdk", language, phase,
                        target if phase == "validation" else "desktop")
                        for language, target in (("python", "macos-arm64"), ("rust", "windows-x64"))]
                    rows = [{**product_reuse._identity_record(identity),
                        "result": "failure" if failure and index else "success",
                        "shardDirectory": None if failure and index else f"rows/{index}/original/shard",
                        "sdkValidationEvidenceDirectory": None if failure and index else f"rows/{index}/original/sdk-validation-evidence"}
                        for index, identity in enumerate(identities)]

                    def collect(*args, **kwargs):
                        for index in range(2):
                            path = args[3] / f"rows/{index}/original"
                            path.mkdir(parents=True)
                            (path / "gradle.log").write_bytes(b"original failure" if failure and index else b"")
                        return {"rows": rows}

                    def advance(*args, **kwargs):
                        self.assertIs(self.tooling, kwargs["sdk_validation_tooling"])
                        self.assertEqual(family, kwargs["sdk_family"])
                        successes = [row for row in rows if row["result"] == "success"]
                        self.assertEqual([destination / "collection" / row["shardDirectory"] for row in successes], args[3])
                        self.assertEqual((identities[1],) if failure else (), kwargs["failed_instances"])
                        if family == "native-validation":
                            self.assertEqual(tuple(destination / "collection" / row["sdkValidationEvidenceDirectory"]
                                                   for row in successes), kwargs["sdk_evidence_roots"])
                        else:
                            self.assertNotIn("sdk_evidence_roots", kwargs)
                        args[4].mkdir(parents=True)
                        (args[4] / "retained").write_bytes(b"synthetic advanced control")
                        return {"synthetic": "advanced"}

                    with patch.object(product_reuse, "collect_runtime_workers", side_effect=collect) as collector, \
                            patch.object(product_reuse, "advance_products", side_effect=advance) as advanced, \
                            patch.object(sdk_workflow, "matrix", return_value={"include": []}) as matrix:
                        result = sdk_workflow.collect(original, destination, self.root / f"output-{family}-{failure}",
                            wave=wave, family=family, trusted_workflow_sha="c" * 40, repository_root=self.root,
                            environ=self.environment, token="synthetic", sdk_validation_tooling=self.tooling)
                    self.assertEqual({"synthetic": "advanced"}, result)
                    self.assertIs(self.tooling, collector.call_args.kwargs["sdk_validation_tooling"])
                    self.assertIs(self.tooling, advanced.call_args.kwargs["sdk_validation_tooling"])
                    self.assertEqual(family, collector.call_args.kwargs["sdk_family"])
                    if failure:
                        matrix.assert_not_called()
                        self.assertEqual(b"original failure", (destination / "collection/rows/1/original/gradle.log").read_bytes())
                    else:
                        matrix.assert_called_once()
                        self.assertIs(self.tooling, matrix.call_args.kwargs["sdk_validation_tooling"])
                        self.assertEqual(family, matrix.call_args.kwargs["family"])
                    for name in ("product-resume-inputs", "product-resume-state"):
                        self.assertEqual(regular_file_inventory(original / name, allow_empty=True),
                                         regular_file_inventory(destination / "handoff" / name, allow_empty=True))
                    self.assertEqual(before, regular_file_inventory(original, allow_empty=True))

    def test_wrong_wave_or_mixed_binary_family_rejects_before_collection(self):
        with patch.object(product_reuse, "collect_runtime_workers") as collect:
            for family, wave, extra in (("native-validation", 8, {}), ("native-metadata", 7, {}),
                                       ("native-validation", 7, {"ios_binary": True})):
                with self.subTest(family=family, wave=wave, extra=extra), self.assertRaises(ValueError):
                    sdk_workflow.collect(self.root / "original", self.root / "destination", self.root / "output",
                        wave=wave, family=family, trusted_workflow_sha="c" * 40,
                        repository_root=self.root, token="synthetic", sdk_validation_tooling=self.tooling, **extra)
            collect.assert_not_called()

    def cli_arguments(self, command, family, wave, policy):
        args = [command, "--family", family, "--github-output", str(self.root / "output"),
                "--repository-root", str(self.root), "--sdk-validation-tooling", str(policy)]
        if command == "matrix":
            return [*args, "--plan", str(self.plan), "--discovery-root", str(self.discovery),
                    "--state-root", str(self.state)]
        args += ["--destination", str(self.root / "destination"), "--trusted-workflow-sha", "c" * 40]
        if command == "capture":
            return [*args, "--plan", str(self.plan), "--artifact-id", "71",
                    "--artifact-sha256", "sha256:" + "b" * 64, "--sdk-state-wave", str(wave)]
        return [*args, "--input-root", str(self.root / "original"), "--wave", str(wave)]

    def test_cli_reads_external_canonical_policy_for_matrix_capture_and_waves_seven_eight(self):
        policy = self.root / "caller tooling.json"
        policy.write_bytes(canonical_json_bytes(self.tooling))
        for command in ("matrix", "capture", "collect"):
            for family, wave in (("native-validation", 7), ("native-metadata", 8)):
                with self.subTest(command=command, family=family), \
                        patch.dict(os.environ, {"GITHUB_TOKEN": "environment only"}, clear=True), \
                        patch.object(product_reuse, "_canonical_control", wraps=product_reuse._canonical_control) as read, \
                        patch.object(sdk_workflow, command) as dispatch:
                    self.assertEqual(0, sdk_workflow.main(self.cli_arguments(command, family, wave, policy)))
                    read.assert_called_once_with(policy, "Caller SDK tooling policy")
                    dispatch.assert_called_once()
                    kwargs = dispatch.call_args.kwargs
                    self.assertEqual(self.tooling, kwargs["sdk_validation_tooling"])
                    self.assertEqual(family, kwargs["family"])
                    self.assertIs(os.environ, kwargs["environ"])
                    if command == "matrix":
                        self.assertNotIn("token", kwargs)
                    else:
                        self.assertEqual("environment only", kwargs["token"])
                        self.assertEqual(wave, kwargs["sdk_state_wave" if command == "capture" else "wave"])
        self.assertEqual(canonical_json_bytes(self.tooling), policy.read_bytes())

    def test_cli_rejects_malformed_nonobject_or_noncanonical_policy_before_dispatch(self):
        policy = self.root / "invalid-tooling.json"
        for command in ("matrix", "capture", "collect"):
            for raw in (b"{", b"[]\n", b'{ "evidence": "not canonical" }\n'):
                policy.write_bytes(raw)
                with self.subTest(command=command, raw=raw), patch.object(sdk_workflow, command) as dispatch, \
                        redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                    sdk_workflow.main(self.cli_arguments(command, "native-validation", 7, policy))
                self.assertEqual(2, failure.exception.code)
                dispatch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
