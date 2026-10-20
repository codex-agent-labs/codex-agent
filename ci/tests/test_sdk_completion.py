"""SDK final routing over an explicit mocked authenticated inspection boundary.

Fixtures use the real result field names and registered identities, not product
or CI proof. The production inspector retains all original evidence validation.
"""

from contextlib import contextmanager, nullcontext, redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from ci import sdk_completion as completion
from products.inventory import canonical_json_bytes
from products.registry import PHASE_INSTANCE_IDS


def inspected(phases):
    complete = all(row["state"] in {"retained", "reused"} for row in phases)
    return {"result": {"schemaVersion": 1, "result": "complete" if complete else "build-required",
        "fullReuse": complete, "phases": phases, "matrices": {"contract": [], "runtime": [], "sdk": []},
        "continuationRequirements": []}, "readyPlans": []}


def phase(identity, state="retained"):
    done = state in {"retained", "reused"}
    return {"product": identity.product, "component": identity.component, "phase": identity.phase,
        "target": identity.target, "state": state, "buildKey": "sha256:" + "a" * 64 if state != "waiting" else None,
        "receiptSha256": "sha256:" + "b" * 64 if done else None,
        "objectSha256": "sha256:" + "c" * 64 if done else None,
        "source": "stable" if state == "reused" else None, "transportSource": None, "misses": []}


class SdkCompletionTest(unittest.TestCase):
    def setUp(self):
        self.sdk = sorted(identity for identity in PHASE_INSTANCE_IDS if identity.product == "sdk")
        self.paths = (Path("/original/plan"), Path("/original/discovery"), Path("/original/state"))
        self.root = Path("/caller/repository")
        self.environment = {"CALLER": "original environment"}

    def call(self, value, **changes):
        with patch.object(completion.products, "inspect_products", return_value=value) as inspect:
            result = completion.require_sdk_completion(*self.paths, repository_root=self.root,
                environ=self.environment, **changes)
        self.inspect = inspect
        return result

    def test_all_registered_sdk_phases_must_be_retained_or_reused_and_originals_stay_unchanged(self):
        value = inspected([phase(identity, "retained" if index % 2 else "reused") for index, identity in enumerate(self.sdk)])
        original = deepcopy(value)
        self.assertEqual({"complete": True, "phaseCount": len(self.sdk), "fullReuse": True}, self.call(value))
        self.assertEqual(original, value)
        self.inspect.assert_called_once_with(*self.paths, repository_root=self.root, environ=self.environment)

    def test_repository_completion_uses_full_authenticated_dag_without_rewriting_originals(self):
        value = inspected([phase(identity) for identity in sorted(PHASE_INSTANCE_IDS)])
        original = deepcopy(value)
        policy = object()
        with patch.object(completion.products, "inspect_products", return_value=value) as inspect:
            report = completion.require_repository_completion(*self.paths,
                repository_root=self.root, environ=self.environment, completed_frozen=policy)
        inspect.assert_called_once_with(*self.paths, repository_root=self.root,
            environ=self.environment, completed_frozen=policy)
        self.assertEqual("passed", report["result"])
        self.assertEqual(len(PHASE_INSTANCE_IDS), report["phaseCount"])
        self.assertEqual(["contract", "runtime", "sdk"], [row["product"] for row in report["products"]])
        self.assertEqual([("contract", "runtime"), ("contract", "sdk"), ("runtime", "sdk")],
                         [(row["producerProduct"], row["consumerProduct"]) for row in report["edges"]])
        self.assertEqual(value["result"]["phases"], report["originalPhases"])
        self.assertEqual(original, value)
        # Every edge is transitive in the actual registry, not an invented
        # direct reference added to one of the immutable metadata receipts.
        terminals = {row["product"]: completion.products._identity(row) for row in report["products"]}
        for producer, consumer in (("contract", "runtime"), ("contract", "sdk"), ("runtime", "sdk")):
            self.assertNotIn(terminals[producer],
                             completion.products.phase_instance_dependencies(terminals[consumer]))

    def test_repository_completion_rejects_partial_state_and_authentication_failure(self):
        rows = [phase(identity) for identity in sorted(PHASE_INSTANCE_IDS)]
        for bad in (rows[:-1], rows + [rows[-1]], rows[1:] + rows[:1], []):
            with self.subTest(count=len(bad)), \
                    patch.object(completion.products, "inspect_products", return_value=inspected(bad)), \
                    self.assertRaises(ValueError):
                completion.require_repository_completion(*self.paths)
        for identity in PHASE_INSTANCE_IDS:
            bad = [phase(item, "waiting" if item == identity else "retained")
                   for item in sorted(PHASE_INSTANCE_IDS)]
            with self.subTest(identity=identity), \
                    patch.object(completion.products, "inspect_products", return_value=inspected(bad)), \
                    self.assertRaises(ValueError):
                completion.require_repository_completion(*self.paths)
        with patch.object(completion.products, "inspect_products", side_effect=ValueError("bad original")):
            with self.assertRaisesRegex(ValueError, "bad original"):
                completion.require_repository_completion(*self.paths)

    def test_repository_cli_holds_authority_until_exit_and_never_emits_failed_report(self):
        argv = ["--repository", "--plan", str(self.paths[0]), "--discovery-root", str(self.paths[1]),
                "--state-root", str(self.paths[2]), "--repository-root", str(self.root)]
        report = {"schemaVersion": 1, "result": "passed", "phaseCount": len(PHASE_INSTANCE_IDS)}
        for fail_exit in (False, True):
            @contextmanager
            def authority(_):
                yield {"completed_frozen": "fixture boundary, not genuine authority"}
                if fail_exit:
                    raise ValueError("authority changed")
            stdout = io.StringIO()
            with patch.object(completion, "completed_frozen_options", authority), \
                    patch.object(completion, "require_repository_completion", return_value=report) as verify, \
                    redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                if fail_exit:
                    with self.assertRaises(SystemExit):
                        completion.main(argv)
                    self.assertEqual("", stdout.getvalue())
                else:
                    self.assertEqual(0, completion.main(argv))
                    self.assertEqual(canonical_json_bytes(report).decode(), stdout.getvalue())
                verify.assert_called_once_with(*self.paths, repository_root=self.root, environ=os.environ,
                    completed_frozen="fixture boundary, not genuine authority")
        for extra in (["--partial-catalog-destination", "/unused"], ["--github-output", "/unused"]):
            with patch.object(completion, "require_repository_completion") as verify, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                completion.main(argv + extra)
            verify.assert_not_called()

    def test_local_repository_uses_current_inputs_and_original_capability_without_ci_identity(self):
        import reuse_qualification as native
        from products import reuse
        instances = tuple(sorted(PHASE_INSTANCE_IDS))
        revision = "d" * 40
        policy = dict(schemaVersion=1, kind="completed-frozen-reuse", consumerCommit=revision,
            verifierPolicySha256="sha256:" + "a" * 64, artifactId=123, artifactSha256="sha256:" + "b" * 64,
            runId=45, runAttempt=1, signerCommit="e" * 40, sourceCommit="e" * 40)
        authorities = [dict(zip(completion.products._IDENTITY_KEYS, (
            item.product, item.component, item.phase, item.target)),
            flagsDigest="sha256:" + "c" * 64, toolchainProfileDigest="sha256:" + "e" * 64,
            outputSchemaVersion=1) for item in instances]
        phases = {item: phase(item) for item in instances}
        capability = Mock()
        capability.completed_phases.return_value = instances
        capability._values.return_value = ({}, phases)
        capability.envelope.side_effect = lambda row: {"original": row}
        expected = inspected(list(phases.values()))["result"]
        with tempfile.TemporaryDirectory(prefix="repository-local-") as temporary:
            root = Path(temporary).resolve()
            pinned = root / "policy.json"
            pinned.write_bytes(canonical_json_bytes(policy))
            for mutation in ("none", "policy", "source", "incomplete"):
                pinned.write_bytes(canonical_json_bytes(policy))
                capability.completed_phases.return_value = instances[:-1] if mutation == "incomplete" else instances
                def planned(*args, **kwargs):
                    if mutation == "policy":
                        pinned.write_bytes(canonical_json_bytes({**policy, "artifactId": 124}))
                    return deepcopy(expected), {}
                with patch.object(native, "fetch_completed_frozen", return_value=(capability, {})) as authenticate, \
                        patch.object(completion.products, "_git_value",
                            side_effect=[revision, "f" * 40] if mutation == "source" else lambda *_: revision), \
                        patch.object(completion.products, "_authorities", return_value=(authorities, None)), \
                        patch.object(completion.products, "_versions", return_value={"current": "Git versions"}), \
                        patch.object(reuse, "_phase_git_inventories", return_value={
                            item: ["current Git inventory"] for item in instances}) as inventories, \
                        patch.object(reuse, "advance_reuse", side_effect=planned) as advance:
                    if mutation != "none":
                        with self.assertRaises(ValueError):
                            completion.require_local_repository_completion(root, pinned, environ={"GH_TOKEN": "fixture-token"})
                        if mutation == "incomplete":
                            advance.assert_not_called()
                        continue
                    report = completion.require_local_repository_completion(root, pinned, environ={"GH_TOKEN": "fixture-token"})
                    self.assertEqual({"kind": "local", "commit": revision,
                        "completedPolicySha256": completion.sha256_bytes(canonical_json_bytes(policy))},
                        report["verificationContext"])
                    self.assertEqual(len(instances), report["phaseCount"])
                    self.assertEqual(expected["phases"], report["originalPhases"])
                    self.assertEqual(revision, authenticate.call_args.kwargs["revision"])
                    self.assertEqual(revision, authenticate.call_args.kwargs["consumer_commit"])
                    self.assertNotIn("producer", authenticate.call_args.kwargs)
                    self.assertIs(capability, advance.call_args.kwargs["completed_frozen"])
                    inventories.assert_called_once_with(root, revision, instances)
                    self.assertEqual(instances, advance.call_args.args[0])
                    self.assertEqual(set(instances), set(advance.call_args.args[1]))
                    for row in advance.call_args.args[1].values():
                        self.assertEqual(["current Git inventory"], row["inventory"])
                        self.assertEqual({"current": "Git versions"}, row["versions"])

    def test_local_repository_cli_rejects_hosted_or_mixed_controls_and_does_not_emit_failed_proof(self):
        argv = ["--repository", "--local", "--repository-root", "/actual/repository",
                "--completed-frozen-policy", "/actual/policy.json"]
        report = {"result": "passed", "verificationContext": {"kind": "local"}}
        with patch.object(completion, "require_local_repository_completion", return_value=report) as gate, \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, completion.main(argv))
            self.assertEqual(canonical_json_bytes(report).decode(), output.getvalue())
            gate.assert_called_once_with(Path("/actual/repository"), Path("/actual/policy.json"))
        for extra in (["--plan", "/CI/plan"], ["--github-output", "/CI/output"],
                      ["--sdk-validation-tooling", "/CI/tooling"], ["--discovery-root", "/CI/state"]):
            with patch.object(completion, "require_local_repository_completion") as gate, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                completion.main(argv + extra)
            gate.assert_not_called()
        for environment in ({"GITHUB_ACTIONS": "true"}, {"GITHUB_RUN_ID": "123"}):
            with self.assertRaisesRegex(ValueError, "hosted execution identity"):
                completion.require_local_repository_completion("/unused", "/unused", environ=environment)
        with patch.object(completion, "require_local_repository_completion", side_effect=ValueError("bad original")), \
                redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            completion.main(argv)
        self.assertEqual("", output.getvalue())

    def test_local_gradle_routes_only_repository_gate_and_preserves_failure(self):
        argv = ["--repository", "--local", "--gradle", "--repository-root", "/actual/repository",
                "--completed-frozen-policy", "/actual/policy.json"]
        with patch.object(completion, "run_local_repository_gradle", return_value={"result": "passed"}) as gate, \
                patch.object(completion, "require_local_repository_completion") as duplicate, \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, completion.main(argv))
            gate.assert_called_once_with(Path("/actual/repository"), Path("/actual/policy.json"))
            duplicate.assert_not_called()
            self.assertEqual('{"result":"passed"}\n', output.getvalue())
        with tempfile.TemporaryDirectory(prefix="repository-gradle-") as temporary:
            root = Path(temporary).resolve()
            policy = root / "caller.json"
            policy.write_text("{}\n")
            report = root / "build/reports/repository/imported-product-evidence.json"
            def gradle(command, **options):
                script = Path(command[command.index("--init-script", command.index("--init-script") + 1) + 1])
                self.assertEqual(completion.LOCAL_REPOSITORY_INIT, script.read_text())
                self.assertEqual(":verifyRepository", command[-1])
                self.assertIn("--offline", command)
                self.assertTrue(options["check"])
                report.parent.mkdir(parents=True)
                report.write_bytes(canonical_json_bytes({"result": "passed"}))
            with patch.object(completion.subprocess, "run", side_effect=gradle) as run:
                self.assertEqual({"result": "passed"}, completion.run_local_repository_gradle(root, policy))
                self.assertEqual(1, run.call_count)
            with patch.object(completion.subprocess, "run", side_effect=completion.subprocess.CalledProcessError(1, "gradle")), \
                    self.assertRaises(completion.subprocess.CalledProcessError):
                completion.run_local_repository_gradle(root, policy)
            self.assertFalse(report.exists())
            report.symlink_to(policy)
            with patch.object(completion.subprocess, "run") as run, self.assertRaises(ValueError):
                completion.run_local_repository_gradle(root, policy)
            run.assert_not_called()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            completion.main(["--gradle", "--repository-root", "/unused"])

    def test_every_unresolved_sdk_identity_rejects_even_when_all_worker_matrices_are_empty(self):
        for identity in self.sdk:
            for state in ("build", "waiting"):
                with self.subTest(identity=identity, state=state):
                    value = inspected([phase(identity, state)])
                    with self.assertRaisesRegex(ValueError, "Selected SDK phases remain unresolved") as error:
                        self.call(value)
                    self.assertIn(f"{identity.component}/{identity.phase}/{identity.target}: {state}", str(error.exception))

    def test_other_product_misses_and_zero_sdk_selection_do_not_claim_sdk_production(self):
        other = next(identity for identity in PHASE_INSTANCE_IDS if identity.product == "runtime")
        self.assertEqual({"complete": True, "phaseCount": 0, "fullReuse": False}, self.call(inspected([phase(other, "build")])))
        self.assertEqual({"complete": True, "phaseCount": 1, "fullReuse": False}, self.call(inspected([
            phase(other, "waiting"), phase(self.sdk[0])])))
        self.assertEqual({"complete": True, "phaseCount": 0, "fullReuse": True}, self.call(inspected([])))

    def test_exact_caller_tooling_is_forwarded_and_replay_error_cannot_be_overridden(self):
        policy = {"synthetic": "caller-owned policy boundary"}
        apple = {"synthetic": "independent caller-owned Apple policy"}
        before = deepcopy(apple)
        self.call(inspected([]), sdk_validation_tooling=policy, sdk_apple_validation_policy=apple)
        self.assertIs(policy, self.inspect.call_args.kwargs["sdk_validation_tooling"])
        self.assertIs(apple, self.inspect.call_args.kwargs["sdk_apple_validation_policy"])
        self.assertEqual(before, apple)
        self.call(inspected([]), sdk_apple_validation_policy=apple)
        self.inspect.assert_called_once_with(*self.paths, repository_root=self.root,
            environ=self.environment, sdk_apple_validation_policy=apple)
        self.call(inspected([]), sdk_apple_validation_policy=None)
        self.inspect.assert_called_once_with(*self.paths, repository_root=self.root, environ=self.environment)
        with patch.object(completion.products, "inspect_products", side_effect=ValueError("original evidence rejected")):
            with self.assertRaisesRegex(ValueError, "original evidence rejected"):
                completion.require_sdk_completion(*self.paths, sdk_apple_validation_policy=apple)
        self.call(inspected([]), sdk_apple_validation_policy=apple,
                  sdk_original_workflow_sha="d" * 40)
        self.inspect.assert_called_once_with(*self.paths, repository_root=self.root,
            environ=self.environment, sdk_apple_validation_policy=apple,
            sdk_original_workflow_sha="d" * 40)

    def test_metadata_admissions_are_independent_opaque_caller_objects(self):
        admissions = {name: object() for name in (
            "sdk_facade_metadata_admission", "sdk_android_metadata_admission")}
        for selected in ((), tuple(admissions), *((name,) for name in admissions)):
            with self.subTest(selected=selected):
                optional = {name: value if name in selected else None
                            for name, value in admissions.items()}
                self.assertEqual({"complete": True, "phaseCount": 0, "fullReuse": True},
                                 self.call(inspected([]), **optional))
                for name, value in admissions.items():
                    if name in selected:
                        self.assertIs(value, self.inspect.call_args.kwargs[name])
                    else:
                        self.assertNotIn(name, self.inspect.call_args.kwargs)

    def test_completed_capability_is_forwarded_explicitly_and_held_until_replay_finishes(self):
        capability = object()  # Mocked authentication boundary, never evidence.
        self.call(inspected([]), completed_frozen=capability)
        self.assertIs(capability, self.inspect.call_args.kwargs["completed_frozen"])
        events = []
        @contextmanager
        def authority(args):
            self.assertEqual(Path("/caller/completed.json"), args.completed_frozen_policy)
            events.append("enter")
            yield {"completed_frozen": capability}
            events.append("exit")
        def replay(*args, **kwargs):
            self.assertEqual(["enter"], events)
            self.assertIs(capability, kwargs["completed_frozen"])
            return {"complete": True, "phaseCount": 0, "fullReuse": True}
        argv = ["--plan", str(self.paths[0]), "--discovery-root", str(self.paths[1]),
                "--repository-root", str(self.root), "--completed-frozen-policy", "/caller/completed.json"]
        with patch.object(completion, "completed_frozen_options", authority), \
                patch.object(completion, "require_sdk_completion", side_effect=replay), redirect_stdout(io.StringIO()):
            self.assertEqual(0, completion.main(argv))
        self.assertEqual(["enter", "exit"], events)

    def test_completed_apple_validations_do_not_complete_unresolved_ios_metadata(self):
        validations = sorted(identity for identity in self.sdk
                             if identity.component == "sdk-ios" and identity.phase == "validation")
        self.assertEqual(["ios-arm64", "ios-simulator-arm64"], [identity.target for identity in validations])
        metadata = next(identity for identity in self.sdk
                        if (identity.component, identity.phase, identity.target) == ("sdk-ios", "metadata", "ios"))
        for state in ("build", "waiting"):
            value = inspected([*(phase(identity) for identity in validations), phase(metadata, state)])
            before = deepcopy(value)
            with self.subTest(state=state), self.assertRaisesRegex(ValueError, "sdk-ios/metadata/ios: " + state):
                self.call(value, sdk_apple_validation_policy={"synthetic": "caller policy"})
            self.assertEqual(before, value)

    def test_malformed_or_duplicate_inspected_rows_cannot_claim_completion(self):
        row = phase(self.sdk[0])
        for rows in ([row, row], [{**row, "state": "success"}], [{**row, "receiptSha256": None}],
                     [{**row, "phase": "unknown"}], [{**row, "extra": True}],
                     [{key: value for key, value in row.items() if key != "state"}]):
            value = inspected([row])
            value["result"]["phases"] = rows
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.call(value)
        for changes in ({"schemaVersion": True}, {"result": "success"}, {"fullReuse": "true"}):
            value = inspected([])
            value["result"].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.call(value)

    def test_cli_canonical_policy_paths_and_output_only_after_success(self):
        with tempfile.TemporaryDirectory(prefix="sdk-completion-cli-") as temporary:
            root = Path(temporary).resolve()
            policy_path, output = root / "policy.json", root / "github-output"
            apple_path = root / "apple-policy.json"
            policy = {"synthetic": "caller policy"}
            apple = {"synthetic": "caller Apple policy"}
            policy_path.write_bytes(canonical_json_bytes(policy))
            apple_path.write_bytes(canonical_json_bytes(apple))
            argv = ["--plan", str(self.paths[0]), "--discovery-root", str(self.paths[1]),
                "--state-root", str(self.paths[2]), "--repository-root", str(self.root),
                "--sdk-validation-tooling", str(policy_path), "--sdk-apple-validation-policy", str(apple_path),
                "--github-output", str(output)]
            with patch.object(completion, "require_sdk_completion", return_value={"complete": True, "phaseCount": 2, "fullReuse": False}) as gate:
                self.assertEqual(0, completion.main(argv))
            gate.assert_called_once_with(*self.paths, repository_root=self.root, environ=os.environ,
                                         sdk_validation_tooling=policy, sdk_apple_validation_policy=apple)
            self.assertEqual("complete=true\nphaseCount=2\nfullReuse=false\n", output.read_text())
            self.assertEqual(canonical_json_bytes(apple), apple_path.read_bytes())
            with patch.object(completion, "require_sdk_completion", return_value={"complete": True, "phaseCount": 2, "fullReuse": False}) as gate:
                self.assertEqual(0, completion.main([*argv, "--sdk-original-workflow-sha", "d" * 40]))
            self.assertEqual("d" * 40, gate.call_args.kwargs["sdk_original_workflow_sha"])
            output.unlink()
            with patch.object(completion, "require_sdk_completion", side_effect=ValueError("unresolved")), \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                completion.main(argv)
            self.assertFalse(output.exists())
            for bad in (argv + ["--phase", "metadata"], argv + ["--command", "arbitrary"],
                        argv + ["--repository", str(self.root)]):
                with patch.object(completion, "require_sdk_completion") as gate, redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    completion.main(bad)
                gate.assert_not_called()
            for malformed in (b'{"synthetic": "noncanonical"}', b'{"a":1,"a":2}\n'):
                apple_path.write_bytes(malformed)
                with patch.object(completion, "require_sdk_completion") as gate, redirect_stderr(io.StringIO()), \
                        self.assertRaises(SystemExit):
                    completion.main(argv)
                gate.assert_not_called()
                self.assertFalse(output.exists())

    def test_cli_omitted_policy_preserves_legacy_shape_and_prints_concise_summary(self):
        argv = ["--plan", str(self.paths[0]), "--discovery-root", str(self.paths[1]), "--repository-root", str(self.root)]
        stdout = io.StringIO()
        with patch.object(completion, "require_sdk_completion", return_value={"complete": True, "phaseCount": 0, "fullReuse": True}) as gate, redirect_stdout(stdout):
            self.assertEqual(0, completion.main(argv))
        gate.assert_called_once_with(*self.paths[:2], None, repository_root=self.root, environ=os.environ)
        self.assertEqual('{"complete":true,"fullReuse":true,"phaseCount":0}\n', stdout.getvalue())


    def test_partial_cli_replays_with_explicit_authority_before_catalog_and_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="sdk-partial-cli-") as temporary:
            root = Path(temporary).resolve()
            plan, discovery, state = (root / name for name in ("plan", "discovery", "state"))
            destination, output = root / "catalog", root / "github-output"
            argv = ["--plan", str(plan), "--discovery-root", str(discovery), "--state-root", str(state),
                    "--repository-root", str(root), "--sdk-original-workflow-sha", "a" * 40,
                    "--partial-catalog-destination", str(destination), "--github-output", str(output)]
            capability, verified = object(), object()
            with patch.object(completion, "completed_frozen_options", return_value=nullcontext(
                    {"completed_frozen": capability})), \
                    patch.object(completion.products, "_verified_product_state", return_value=verified) as replay, \
                    patch.object(completion, "stage_partial_catalog", return_value={"phaseCount": 0, "objectBytes": 0}) as stage:
                self.assertEqual(0, completion.main(argv))
                replay.assert_called_once_with(plan, discovery, state, root, os.environ,
                    sdk_validation_tooling=None, sdk_original_workflow_sha="a" * 40, completed_frozen=capability)
                stage.assert_called_once_with(verified, destination)
            self.assertEqual("phaseCount=0\nobjectBytes=0\n", output.read_text())
            output.unlink()
            with patch.object(completion.products, "_verified_product_state", side_effect=ValueError("unqualified missing object")), \
                    patch.object(completion, "stage_partial_catalog") as stage, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                completion.main(argv)
            stage.assert_not_called()
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
