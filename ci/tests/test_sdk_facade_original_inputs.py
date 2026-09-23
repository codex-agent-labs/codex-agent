"""Offline orchestration checks; existing capture and selector suites own admission."""

from contextlib import ExitStack, contextmanager
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci import sdk_facade_original_inputs as inputs
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, sha256_bytes, sha256_file
from products.registry import SDK_FACADE_TARGETS


class OriginalFacadeInputsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="core-inputs-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "repository"
        self.root.mkdir()
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(b"current plan\n")
        self.paths = {}
        for target in ("common", *SDK_FACADE_TARGETS):
            path = self.root / f"{target}-original-receipt.json"
            path.write_bytes(canonical_json_bytes({"target": target, "original": True}))
            self.paths[target] = path
        self.expected = {target: sha256_bytes(path.read_bytes()) for target, path in self.paths.items()}
        self.policy = {"validations": {target: {
            "validationReceipt": str(self.paths[target]),
            "facadeRequest": str(self.root / f"{target}-request.json"),
            **({"nativeCompilerArchive": str(self.root / f"{target}-compiler.zip")}
               if target in ("linux-arm64", "windows-x64") else {}),
        } for target in SDK_FACADE_TARGETS}}
        self.events = []

    def call(self, **changes):
        arguments = dict(catalog=object(), catalog_source="same-pr",
            metadata_receipt_path=self.paths["common"],
            expected_receipt_sha256=self.expected, replay_policy=self.policy,
            trusted_workflow_sha="c" * 40, repository_root=self.root,
            token="synthetic-token")
        arguments.update(changes)
        return inputs.held_original_facade_metadata_policy(self.plan, **arguments)

    def locator(self, path, *, expected_receipt_sha256, trusted_workflow_sha, token):
        target = next(target for target, value in self.paths.items() if value == path)
        self.assertEqual(self.expected[target], expected_receipt_sha256)
        self.assertEqual("c" * 40, trusted_workflow_sha)
        self.assertEqual("synthetic-token", token)
        self.events.append(("locate", target))
        return {"artifact_id": 700 + len(self.events), "artifact_sha256": sha256_bytes(target.encode())}

    def capture(self, plan, destination, **arguments):
        target = destination.name
        self.assertEqual(self.plan, plan)
        self.assertEqual(self.paths[target], arguments[
            "metadata_receipt_path" if target == "common" else "validation_receipt_path"])
        self.assertEqual(self.root, arguments["repository_root"])
        self.assertEqual("synthetic-token", arguments["token"])
        self.assertFalse(destination.exists())
        destination.mkdir()
        (destination / "original-upload.bin").write_bytes(target.encode())
        self.events.append(("capture", target))

    def select(self, plan, destination, **arguments):
        self.assertEqual(self.plan, plan)
        self.assertEqual(self.paths["common"], arguments["metadata_receipt_path"])
        evidence = arguments["evidence_root"]
        self.assertNotIn(self.root, evidence.parents)
        self.assertEqual({"common", *SDK_FACADE_TARGETS}, {path.name for path in evidence.iterdir()})
        policy = arguments["policy"]
        self.assertEqual(set(SDK_FACADE_TARGETS), set(policy["validations"]))
        for target in SDK_FACADE_TARGETS:
            self.assertEqual(str(evidence / target), policy["validations"][target]["captureRoot"])
            self.assertEqual(self.policy["validations"][target]["nativeCompilerArchive"]
                if "nativeCompilerArchive" in self.policy["validations"][target] else None,
                policy["validations"][target].get("nativeCompilerArchive"))
        self.assertEqual(sorted(self.expected.values()),
            [row["receiptSha256"] for row in arguments["records"]])
        self.events.append(("select", "common"))
        destination.write_bytes(canonical_json_bytes({"allEleven": True}))

    def mocks(self):
        return (patch.object(inputs, "locate_original_facade_upload", side_effect=self.locator),
            patch.object(inputs, "capture_sdk_facade_validation_upload", side_effect=self.capture),
            patch.object(inputs, "capture_sdk_facade_metadata_upload", side_effect=self.capture),
            patch.object(inputs, "write_selected_facade_metadata_policy", side_effect=self.select))

    def test_all_originals_are_officially_located_and_captured_before_strict_selection(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for mock in self.mocks(): stack.enter_context(mock)
            with self.call() as descriptor:
                self.assertEqual({"allEleven": True}, load_canonical_json_bytes(descriptor.read_bytes()))
                self.assertTrue(descriptor.exists())
        self.assertEqual(25, len(self.events))
        self.assertEqual([( "locate", target) for target in (*SDK_FACADE_TARGETS, "common")],
            self.events[::2][:-1])
        self.assertEqual(("select", "common"), self.events[-1])
        self.assertFalse(descriptor.exists())
        self.assertFalse(any("captureRoot" in value for value in self.policy["validations"].values()))

    def test_missing_or_wrong_independent_receipt_selection_never_observes_official_api(self):
        with patch.object(inputs, "locate_original_facade_upload") as locate:
            with self.assertRaises(ValueError):
                with self.call(expected_receipt_sha256={key: value for key, value in self.expected.items()
                    if key != "jvm"}): pass
            locate.assert_not_called()
            with self.assertRaisesRegex(ValueError, "independent selection"):
                with self.call(expected_receipt_sha256={**self.expected, "jvm": "sha256:" + "0" * 64}): pass
            locate.assert_not_called()

    def test_mutation_after_location_fails_before_any_capture_or_selector(self):
        original = self.paths["jvm"].read_bytes()
        def mutate(path, **arguments):
            result = self.locator(path, **arguments)
            if path == self.paths["jvm"]:
                path.write_bytes(b"changed\n")
            return result
        try:
            with patch.object(inputs, "locate_original_facade_upload", side_effect=mutate), \
                    patch.object(inputs, "capture_sdk_facade_validation_upload", side_effect=self.capture), \
                    patch.object(inputs, "write_selected_facade_metadata_policy") as select, \
                    self.assertRaisesRegex(ValueError, "changed"):
                with self.call(): pass
            select.assert_not_called()
        finally:
            self.paths["jvm"].write_bytes(original)

    def fresh_call(self, **changes):
        policy = {**self.policy, "plan": str(self.plan), "toolingEvidence": str(self.root),
            "toolingPublicKey": str(self.plan), "javaExecutable": str(self.plan),
            "toolingKeyring": None, "toolingKeysDirectory": None,
            "toolingTrustDomain": "development", "contractDigest": "sha256:" + "1" * 64,
            "componentDigests": {}}
        arguments = dict(expected_build_key="sha256:" + "2" * 64, replay_policy=policy,
            trusted_workflow_sha="c" * 40, repository_root=self.root, environ={}, token="synthetic-token")
        arguments.update(changes)
        return inputs.held_fresh_facade_metadata_policy(self.plan, self.root / "discovery",
            self.root / "discovery", **arguments)

    def fresh_mocks(self):
        discovery = self.root / "discovery"
        discovery.mkdir()
        (discovery / "state.json").write_bytes(b"fixed state")
        ready = {"buildKey": "sha256:" + "2" * 64}
        elected = SimpleNamespace(prior_ready_plans={inputs._FRESH_INSTANCE: ready},
                                  plan={"validationCommit": "a" * 40})
        def materialize(_plan, _discovery, _state, _instance, destination, **_kwargs):
            destination.mkdir()
            package = destination / "sdk-sdk-core-package-common"
            package.mkdir()
            (package / "phase-receipt.json").write_bytes(b"package\n")
            stage = package / "stage"
            stage.mkdir()
            (stage / "payload").write_bytes(b"package-stage")
            for target in SDK_FACADE_TARGETS:
                selected = destination / f"sdk-sdk-core-validation-{target}"
                selected.mkdir()
                (selected / "phase-receipt.json").write_bytes(self.paths[target].read_bytes())
                stage = selected / "stage"
                stage.mkdir()
                (stage / "payload").write_bytes(target.encode())
            return ready
        def arguments(policy):
            self.assertEqual(set(SDK_FACADE_TARGETS), set(policy["validations"]))
            self.assertNotIn("originalContext", policy)
            self.assertTrue(all("captureRoot" in row for row in policy["validations"].values()))
            return {"validations": policy["validations"], "contract_digest": policy["contractDigest"],
                "component_digests": {}, "tooling_evidence": self.root,
                "tooling_public_key": self.plan, "java_executable": self.plan,
                "required_trust_domain": "development", "tooling_keyring": None,
                "tooling_keys_directory": None}
        @contextmanager
        def verified(**_kwargs):
            base = next(self.root.glob("fresh-core-predecessors-*/inputs"))
            result = {"package": {"receiptBytes": b"package\n",
                "stage": base / "sdk-sdk-core-package-common/stage"}, "validations": {}}
            for target in SDK_FACADE_TARGETS:
                selected = base / f"sdk-sdk-core-validation-{target}"
                result["validations"][target] = {"receiptBytes": self.paths[target].read_bytes(),
                    "stage": selected / "stage"}
            yield result
        return (patch.object(inputs, "_fresh_policy_sources", return_value=(
            {path: sha256_file(path) for path in self.paths.values()}, {})),
            patch.object(inputs.product_reuse, "_verified_product_state", return_value=elected),
            patch.object(inputs.product_reuse, "materialize_product_predecessors", side_effect=materialize),
            patch.object(inputs, "validate_phase_receipt", side_effect=lambda value: {
                "product": "sdk", "component": "sdk-core", "phase": "validation", "target": value["target"]}),
            patch.object(inputs, "locate_original_facade_upload", side_effect=self.locator),
            patch.object(inputs, "capture_sdk_facade_validation_upload", side_effect=self.capture),
            patch.object(inputs, "fresh_metadata_arguments", side_effect=arguments),
            patch.object(inputs, "verified_facade_metadata_inputs", side_effect=verified))

    def test_fresh_descriptor_uses_elected_eleven_without_metadata_receipt(self):
        with ExitStack() as stack:
            for mock in self.fresh_mocks():
                stack.enter_context(mock)
            with self.fresh_call() as descriptor:
                value = load_canonical_json_bytes(descriptor.read_bytes())
                self.assertEqual([], value["records"])
                self.assertNotIn("originalContext", value["policy"])
                self.assertEqual({*SDK_FACADE_TARGETS}, {path.name for path in
                    Path(value["evidenceRoot"]).iterdir()})
                self.assertEqual(11, len([event for event in self.events if event[0] == "capture"]))
        self.assertFalse(descriptor.exists())

    def test_fresh_wrong_key_fails_before_official_observation(self):
        with ExitStack() as stack:
            for mock in self.fresh_mocks():
                stack.enter_context(mock)
            with self.assertRaisesRegex(ValueError, "exact elected build key"):
                with self.fresh_call(expected_build_key="sha256:" + "0" * 64):
                    pass
        self.assertFalse(self.events)

    def test_fresh_receipt_mutation_after_official_location_fails_before_capture(self):
        original = self.paths["jvm"].read_bytes()
        def mutate(path, **arguments):
            result = self.locator(path, **arguments)
            if path == self.paths["jvm"]:
                path.write_bytes(b"changed\n")
            return result
        try:
            with ExitStack() as stack:
                for mock in self.fresh_mocks():
                    stack.enter_context(mock)
                stack.enter_context(patch.object(inputs, "locate_original_facade_upload", side_effect=mutate))
                with self.assertRaisesRegex(ValueError, "caller policy changed"):
                    with self.fresh_call():
                        pass
            self.assertNotIn(("capture", "jvm"), self.events)
        finally:
            self.paths["jvm"].write_bytes(original)


if __name__ == "__main__":
    unittest.main()
