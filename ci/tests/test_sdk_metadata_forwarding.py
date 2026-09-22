"""Invocation-only forwarding; mocked state/planner gates grant no admission."""

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci import sdk_workflow
from products.inventory import canonical_json_bytes


products = sdk_workflow.product_reuse


class MetadataForwardingTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="metadata-forwarding-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.plan = self.root / "plan.json"
        self.plan_bytes = canonical_json_bytes({"fixture": "mocked plan authority"})
        self.plan.write_bytes(self.plan_bytes)
        self.discovery, self.state = self.root / "discovery", self.root / "state"
        self.admissions = {"sdk_facade_metadata_admission": object(),
                           "sdk_android_metadata_admission": object()}

    def cases(self):
        yield {}
        yield dict.fromkeys(self.admissions)
        for selected in self.admissions:
            yield {name: value if name == selected else None for name, value in self.admissions.items()}
        yield dict(self.admissions)

    def assert_forwarded(self, call, supplied):
        for name in self.admissions:
            if supplied.get(name) is None:
                self.assertNotIn(name, call.kwargs)
            else:
                self.assertIs(supplied[name], call.kwargs[name])

    def assert_not_serialized(self, value):
        raw = canonical_json_bytes(value)
        for name in self.admissions:
            self.assertNotIn(name.encode(), raw)
        self.assertEqual(self.plan_bytes, self.plan.read_bytes())

    def test_inspection_forwards_exact_objects_to_verified_state_only(self):
        verified = SimpleNamespace(rebased_request={}, prior={"phases": []}, prior_ready_plans={})
        selection = {"fixture": "SDK selection"}
        tooling, apple = {"fixture": "tooling"}, {"fixture": "Apple policy"}
        environment = {"fixture": "environment"}
        for supplied in self.cases():
            with self.subTest(supplied=tuple(supplied)), \
                    patch.object(products, "_verified_product_state", return_value=verified) as replay, \
                    patch.object(products, "_retained_aggregate_handoffs", return_value=[]), \
                    patch.object(products, "_sdk_input_selection", return_value=selection):
                result = products.inspect_products(self.plan, self.discovery, self.state,
                    repository_root=self.root, environ=environment, include_sdk_selection=True,
                    sdk_validation_tooling=tooling, sdk_apple_validation_policy=apple, **supplied)
            replay.assert_called_once()
            self.assertEqual((self.plan, self.discovery, self.state, self.root, environment, tooling),
                             replay.call_args.args)
            self.assertIs(apple, replay.call_args.kwargs["sdk_apple_validation_policy"])
            self.assert_forwarded(replay.call_args, supplied)
            self.assertIs(selection, result["sdkInputSelection"])
            self.assert_not_serialized(result)
            self.assertEqual({}, verified.rebased_request)

    def test_planner_forwards_admissions_as_kwargs_never_retained_or_invocation_json(self):
        request = {"sdkValidationEvidence": []}
        request_bytes = canonical_json_bytes(request)
        tooling = {"fixture": "independent tooling"}
        result = {"fixture": "mocked planner result"}
        for supplied in self.cases():
            # The generic planner forwards kwargs unchanged. Public callers
            # normalize omission with this existing shared helper first.
            optional = products._metadata_admissions(
                supplied.get("sdk_facade_metadata_admission"),
                supplied.get("sdk_android_metadata_admission"))
            with self.subTest(supplied=tuple(supplied)), \
                    patch.object(products, "plan_reuse_wave", return_value=result) as planner:
                actual = products._plan_with_sdk_tooling(request, tooling, **optional)
            planner.assert_called_once()
            self.assert_forwarded(planner.call_args, supplied)
            invocation, = planner.call_args.args
            self.assertIsNot(invocation, request)
            self.assertIs(tooling, invocation["sdkValidationTooling"])
            self.assert_not_serialized(invocation)
            self.assertEqual(request_bytes, canonical_json_bytes(request))
            self.assertIs(result, actual)

    def test_sdk_selection_forwards_admissions_only_to_inspection_and_preserves_plan_bytes(self):
        validated = {"fixture": "mocked validated plan"}
        selection = {"fixture": "mocked selected inputs"}
        tooling, apple = {"fixture": "tooling"}, {"fixture": "Apple policy"}
        environment = {"fixture": "environment"}
        for supplied in self.cases():
            with self.subTest(supplied=tuple(supplied)), \
                    patch.object(products, "_validate_plan", return_value=validated) as validate, \
                    patch.object(products, "inspect_products", return_value={"sdkInputSelection": selection}) as inspect:
                actual = sdk_workflow._selection(self.plan, self.discovery, self.state, self.root, environment,
                    sdk_validation_tooling=tooling, sdk_apple_validation_policy=apple, **supplied)
            validate.assert_called_once_with(self.plan, self.root)
            inspect.assert_called_once()
            self.assert_forwarded(inspect.call_args, supplied)
            self.assertIs(tooling, inspect.call_args.kwargs["sdk_validation_tooling"])
            self.assertIs(apple, inspect.call_args.kwargs["sdk_apple_validation_policy"])
            self.assertIs(True, inspect.call_args.kwargs["include_sdk_selection"])
            self.assertIs(actual[0], validated)
            self.assertIs(actual[1], selection)
            self.assertEqual(self.plan_bytes, actual[2])
            self.assert_not_serialized(selection)


if __name__ == "__main__":
    unittest.main()
