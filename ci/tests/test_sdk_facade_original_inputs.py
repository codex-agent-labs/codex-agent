"""Offline orchestration checks; existing capture and selector suites own admission."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_facade_original_inputs as inputs
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, sha256_bytes
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


if __name__ == "__main__":
    unittest.main()
