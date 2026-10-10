"""Real CLI parsing, mocked policy assembly and replay; no hosted authority."""

from contextlib import contextmanager, ExitStack, redirect_stderr
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_completion, sdk_workflow


products = sdk_workflow.product_reuse


class MetadataCliTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="metadata-cli-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plan = self.root / "current plan.json"
        self.paths = {"sdk_facade_metadata_policy": self.root / "facade caller.json",
                      "sdk_android_metadata_policy": self.root / "android caller.json"}
        self.digest = "sha256:" + "a" * 64

    def argv(self, command, values):
        return ([command] if command else []) + [item for name, value in values.items()
            for item in ("--" + name, str(value))]

    def product_routes(self):
        base = {"plan": self.plan, "discovery-root": self.root / "discovery",
                "destination": self.root / "output"}
        output = {"github-output": self.root / "github-output"}
        key = {"expected-build-key": self.digest}
        for command, values in (
            ("discover", {"plan": self.plan, "destination": self.root / "output",
                          "handoff": self.root / "handoff", **output}),
            ("advance-products", {**base, **output}),
            ("resume-products", {**base, **output, "state-root": self.root / "state",
                                 "contract-handoff": self.root / "contract"}),
            ("collect-runtime-workers", {**base, "trusted-workflow-sha": "b" * 40}),
            ("runtime-worker-matrix", {"plan": self.plan, "discovery-root": self.root / "discovery", **output}),
            ("execute-runtime-supervisor", {**base, **key}),
            ("execute-sdk-metadata", {**base, **key, "component": "rust",
                "compatibility-request": self.root / "compatibility", "runtime-stages": self.root / "runtime",
                "staged-sdks": self.root / "sdks", "sdk-validation-tooling": self.root / "tooling.json"}),
            ("execute-runtime-aggregate", {**base, **key, "variant-trust-root": self.root / "variants"}),
            *((command, {**base, **key, "product": "runtime", "component": "linux-x64",
                         "phase": "binary", "target": "linux-x64"}) for command in (
                "materialize-product-predecessors", "prepare-runtime-phase", "execute-runtime-phase")),
        ):
            yield products, self.argv(command, values), command.replace("-", "_")

    def sdk_routes(self):
        base = {"plan": self.plan, "discovery-root": self.root / "discovery",
                "state-root": self.root / "state", "destination": self.root / "output",
                "repository-root": self.root}
        keys = {"keyring": self.root / "keyring", "keys-directory": self.root / "keys"}
        upload = {"artifact-id": 5, "artifact-sha256": self.digest,
                  "trusted-workflow-sha": "b" * 40, "expected-build-key": self.digest}
        for command, operation, values in (
            (None, "stage", {**base, **keys}),
            ("javascript", "execute_javascript", {**base, **keys, **upload, "phase": "package"}),
            ("native-prepare", "prepare_native", {**base, **keys, **upload, "component": "rust"}),
            ("ios-binary", "execute_ios_binary", {**base, "trusted-workflow-sha": "b" * 40,
                "expected-build-key": self.digest,
                **{lane + "-artifact-id": index for index, lane in enumerate(
                    ("native-tests", "rust-device", "rust-simulator"), 1)},
                **{lane + "-artifact-sha256": self.digest for lane in (
                    "native-tests", "rust-device", "rust-simulator")}}),
            ("matrix", "matrix", {"plan": self.plan, "discovery-root": self.root / "discovery",
                "state-root": self.root / "state", "repository-root": self.root,
                "github-output": self.root / "github-output"}),
            ("capture", "capture", {"plan": self.plan, "destination": self.root / "output",
                "repository-root": self.root, "github-output": self.root / "github-output",
                "trusted-workflow-sha": "b" * 40, "artifact-id": 5, "artifact-sha256": self.digest}),
            ("collect", "collect", {"input-root": self.root / "original", "destination": self.root / "output",
                "repository-root": self.root, "github-output": self.root / "github-output",
                "trusted-workflow-sha": "b" * 40, "wave": 1}),
        ):
            yield sdk_workflow, self.argv(command, values), operation

    def completion_route(self):
        return sdk_completion, self.argv(None, {"plan": self.plan,
            "discovery-root": self.root / "discovery", "repository-root": self.root,
            "github-output": self.root / "github-output"}), "require_sdk_completion"

    def check_route(self, module, argv, operation, selected, failure=None):
        events = []
        admissions = {name.replace("_policy", "_admission"): object() for name in selected}

        @contextmanager
        def held(args):
            values = args if isinstance(args, dict) else vars(args)
            if operation == "collect":
                self.assertEqual(self.root / "original", values["input_root"])
            else:
                self.assertEqual(self.plan, values["plan"])
            if module is not products:
                self.assertEqual(self.root, values["repository_root"])
            for name, path in self.paths.items():
                self.assertEqual(path if name in selected else None, values.get(name))
                if isinstance(args, dict):
                    args.pop(name)
            events.append("enter")
            if failure == "enter":
                raise ValueError("independent policy rejected")
            yield admissions
            events.append("exit")
            if failure == "exit":
                raise ValueError("independent policy changed")

        def execute(*args, **kwargs):
            self.assertEqual("enter", events[0])
            self.assertNotIn("exit", events)
            for name in ("sdk_facade_metadata_admission", "sdk_android_metadata_admission"):
                if name in admissions:
                    self.assertIs(admissions[name], kwargs[name])
                else:
                    self.assertNotIn(name, kwargs)
            self.assertFalse(set(self.paths) & set(kwargs))
            for path in self.paths.values():
                self.assertNotIn(str(path), repr((args, kwargs)))
            if "token" in kwargs:
                self.assertEqual("environment-token", kwargs["token"])
            events.append("execute")
            return {"include": [], "complete": True, "phaseCount": 0, "fullReuse": True}

        def output(*args, **kwargs):
            self.assertIn("enter", events)
            self.assertNotIn("exit", events)
            for name, path in self.paths.items():
                self.assertNotIn(name, repr((args, kwargs)))
                self.assertNotIn(str(path), repr((args, kwargs)))
            events.append("output")

        options = [item for name in selected for item in (
            "--" + name.replace("_", "-"), str(self.paths[name]))]
        with self.subTest(operation=operation, selected=selected, failure=failure), ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"GITHUB_TOKEN": "environment-token"}, clear=True))
            stack.enter_context(patch.object(module, "metadata_admission_options", side_effect=held))
            worker = stack.enter_context(patch.object(module, operation, side_effect=execute))
            stack.enter_context(patch.object(products, "_canonical_control", return_value={"fixture": "tooling"}))
            stack.enter_context(patch.object(module, "github_output", side_effect=output))
            if module is products:
                stack.enter_context(patch.object(products, "publish_regular_tree", side_effect=output))
            if failure:
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as rejected:
                    module.main([*argv, *options])
                self.assertEqual(2, rejected.exception.code)
            else:
                self.assertEqual(0, module.main([*argv, *options]))
            self.assertEqual(0 if failure == "enter" else 1, worker.call_count)
            if operation in {"require_sdk_completion", "discover"}:
                self.assertEqual(0 if failure == "enter" else 1, events.count("output"))
            self.assertEqual(["enter"] if failure == "enter" else ["enter", "execute", "exit"],
                             [event for event in events if event != "output"])

    def check_routes(self, routes):
        for module, argv, operation in routes:
            for selected in ((), *(tuple([name]) for name in self.paths), tuple(self.paths)):
                self.check_route(module, argv, operation, selected)
            for failure in ("enter", "exit"):
                self.check_route(module, argv, operation, tuple(self.paths), failure)

    def test_all_eleven_product_replay_routes_hold_only_explicit_admission_objects(self):
        routes = list(self.product_routes())
        self.assertEqual(11, len(routes))
        self.check_routes(routes)

    def test_all_seven_common_sdk_routes_hold_only_explicit_admission_objects(self):
        routes = list(self.sdk_routes())
        self.assertEqual(7, len(routes))
        self.check_routes(routes)

    def test_completion_output_stays_inside_policy_lifetime(self):
        self.check_routes([self.completion_route()])

    def test_object_switches_and_missing_policy_values_fail_before_policy_or_execution(self):
        for module, argv, operation in [*self.product_routes(), *self.sdk_routes(), self.completion_route()]:
            for extra in (("--sdk-facade-metadata-admission", "not-authority"),
                          ("--sdk-android-metadata-admission", "not-authority"),
                          ("--sdk-facade-metadata-policy",), ("--sdk-android-metadata-policy",)):
                with self.subTest(operation=operation, extra=extra), \
                        patch.object(module, "metadata_admission_options") as policy, \
                        patch.object(module, operation) as worker, \
                        redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    module.main([*argv, *extra])
                policy.assert_not_called()
                worker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
