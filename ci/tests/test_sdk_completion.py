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
import zipfile
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

    def test_original_parity_consumes_held_bytes_and_checks_exact_inputs_not_retrieval_state(self):
        # Small archive fixture at explicit mocked official observation boundaries.
        # It is not a hosted proof or an independently admissible success marker.
        from products.registry import NATIVE_BINDINGS
        rows = [phase(item) for item in sorted(PHASE_INSTANCE_IDS)]
        producer = dict(repository="codex-agent-labs/codex-agent", workflowPath=".github/workflows/ci.yml",
            commit="a" * 40, tree="b" * 40, event="pull_request", pullRequest=31, runId=12, runAttempt=1)
        job = dict(id=13, name="product-validation / sdk-parity / sdk-parity",
            started_at="2026-10-20T12:00:00Z", completed_at="2026-10-20T13:00:00Z")
        observation = dict(run={"head_sha": "c" * 40}, jobs=[job])
        names = {"canonical-api.json", "canonical-coverage.json", "binding-obligations-m11.json",
            *(name + "-parity.json" for name in (*NATIVE_BINDINGS, "kotlin", "java",
                "javascript-typescript", "swift", "objective-c", "c-abi"))}
        evidence = {name: canonical_json_bytes({"fixture": name}) for name in names}
        digest = lambda value: completion.sha256_bytes(value).removeprefix("sha256:")
        baseline = dict(schemaVersion=2, phase="M11", result="passed", capabilityCount=556,
            languageCount=11, scenarioCount=14, active=6104, pending=0, excluded=12, satisfied=6104, missing=0,
            canonicalApiSha256=digest(evidence["canonical-api.json"]),
            canonicalCoverageSha256=digest(evidence["canonical-coverage.json"]),
            evidenceFiles=[dict(path=name, bytes=len(raw), sha256=digest(raw))
                           for name, raw in sorted(evidence.items())])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            policy_path, archive = root / "policy.json", root / "original.zip"
            for mutation in ("none", "retrieval", "key", "receipt", "duplicate", "missing", "count",
                             "inventory", "extra", "archive", "recipe", "job", "window", "policy", "authentication",
                             "fetch", "oversize"):
                originals, report = deepcopy(rows), deepcopy(baseline)
                if mutation == "retrieval":
                    originals[0].update(state="reused", source="stable", transportSource="stable")
                if mutation in ("key", "receipt"):
                    originals[0]["buildKey" if mutation == "key" else "receiptSha256"] = "sha256:" + "f" * 64
                if mutation == "duplicate":
                    originals.append(originals[-1])
                if mutation == "count":
                    report["satisfied"] -= 1
                if mutation == "inventory":
                    report["evidenceFiles"][0]["sha256"] = "e" * 64
                with zipfile.ZipFile(archive, "w") as zipped:
                    for name, raw in evidence.items():
                        zipped.writestr("m11/" + name, raw)
                    zipped.writestr("sdk-parity.json", canonical_json_bytes(report))
                    if mutation != "missing":
                        zipped.writestr("original-phase-identities.json", canonical_json_bytes(originals))
                    zipped.writestr("consumer.log", b"fixture only\n")
                    if mutation == "extra":
                        zipped.writestr("unexpected", b"extra")
                policy = dict(schemaVersion=1, kind="completed-sdk-parity", producer=producer,
                    workflowSha="d" * 40, jobId=14 if mutation == "job" else 13,
                    artifactId=15, artifactSha256=completion.sha256_bytes(archive.read_bytes()))
                policy_path.write_bytes(canonical_json_bytes(policy))
                metadata = dict(size_in_bytes=archive.stat().st_size, created_at=(
                    "2026-10-21T12:30:00Z" if mutation == "window" else "2026-10-20T12:30:00Z"))
                if mutation == "archive":
                    metadata["size_in_bytes"] += 1
                metadata["name"] = "codex-agent-sdk-binding-parity-" + producer["tree"]
                if mutation == "oversize":
                    metadata["size_in_bytes"] = 32 * 1024 * 1024 + 1
                original_bytes = archive.read_bytes()
                def download(artifact, token, destination, limit, digest, size):
                    self.assertIs(artifact, metadata)
                    self.assertEqual(32 * 1024 * 1024, limit)
                    self.assertEqual(len(original_bytes), size)
                    self.assertEqual(completion.sha256_bytes(original_bytes), digest)
                    with destination.open("xb") as stream:
                        stream.write(original_bytes)
                    return artifact, destination
                def official(*args, **kwargs):
                    if mutation == "policy":
                        policy_path.write_bytes(b"{}\n")
                    return metadata
                with self.subTest(mutation=mutation), \
                        patch.object(completion.products, "_observe_ci_producer_jobs",
                            side_effect=ValueError("failed original") if mutation == "authentication" else None,
                            return_value=[observation]) as observe, \
                        patch.object(completion.products, "_contract_ci_upload_metadata", side_effect=official) as metadata_read, \
                        patch.object(completion.products, "_download_contract_ci_upload_bytes", side_effect=download) as transport, \
                        patch.object(completion.products, "_download_contract_ci_upload",
                            side_effect=AssertionError("A second metadata acquisition is forbidden")), \
                        patch.object(completion, "git_inventory",
                            side_effect=["original", "changed" if mutation == "recipe" else "original"]) as recipe:
                    supplied_archive = None if mutation in {"fetch", "oversize"} else archive
                    if mutation not in ("none", "retrieval", "fetch"):
                        with self.assertRaises(ValueError):
                            completion._completed_parity(root, "e" * 40, inspected(rows)["result"],
                                                         policy_path, supplied_archive, "token")
                        transport.assert_not_called()
                        continue
                    result = completion._completed_parity(root, "e" * 40, inspected(rows)["result"],
                                                         policy_path, supplied_archive, "token")
                    metadata_read.assert_called_once()
                    self.assertEqual(1 if mutation == "fetch" else 0, transport.call_count)
                    self.assertEqual(original_bytes, archive.read_bytes())
                    self.assertEqual(producer, result["producer"])
                    self.assertEqual(112, result["phaseCount"])
                    self.assertEqual(6104, result["satisfied"])
                    self.assertEqual(policy["artifactSha256"], result["artifactSha256"])
                    self.assertEqual(producer["tree"], recipe.call_args_list[0].args[1])
                    self.assertEqual("e" * 40, recipe.call_args_list[1].args[1])
                    self.assertEqual({"parity": {
                        "path": ".github/workflows/sdk-binding-parity.yml", "sha": "d" * 40}},
                        observe.call_args.kwargs["trusted_workflows_by_phase"])
                    self.assertNotIn("native_job_ids_by_phase", observe.call_args.kwargs)

    def test_hosted_parity_reuses_current_private_state_and_rejects_missing_authority_or_phase(self):
        self.assertTrue(hasattr(completion, "require_hosted_sdk_parity"))
        # Native/state authentication and original parity are explicit fixture seams;
        # the real repository closure checker and actual hosted consumer identity run.
        rows = [phase(item) for item in sorted(PHASE_INSTANCE_IDS)]
        environment = {"GITHUB_ACTIONS": "true", "GITHUB_JOB": "sdk-parity", "GITHUB_TOKEN": "fixture",
                       "GITHUB_RUN_ID": "21", "GITHUB_RUN_ATTEMPT": "2"}
        plan = dict(repository="codex-agent-labs/codex-agent", event="pull_request", pullRequest=31,
                    validationCommit="e" * 40, validationTree="f" * 40)
        consumer = completion.products._consumer(plan, environment)
        for mode in ("ok", "incomplete", "authority", "job", "local", "late-state", "late-source"):
            native = Mock()
            selected = inspected(rows[:-1] if mode == "incomplete" else rows)["result"]
            state = Mock(completed_frozen=native, consumer=consumer, producer=consumer["producer"],
                         plan=plan, prior=selected)
            original = deepcopy(selected)
            env = dict(environment)
            if mode == "job":
                env["GITHUB_JOB"] = "not-parity"
            if mode == "local":
                env.pop("GITHUB_ACTIONS")
            def inspect(*args, **options):
                self.assertIs(env, options["environ"])
                self.assertIs(native, options["completed_frozen"])
                options["_verified_state_consumer"](state)
                if mode == "late-state":
                    raise ValueError("late state failure")
                return {"result": selected}
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary, \
                    patch.object(completion.products, "inspect_products", side_effect=inspect) as replay, \
                    patch.object(completion.products, "_git_value",
                        return_value="0" * 40 if mode == "late-source" else plan["validationCommit"]), \
                    patch.object(completion, "_completed_parity", return_value={"result": "passed", "artifactId": 15}) as parity:
                def call():
                    return completion.require_hosted_sdk_parity(*self.paths, repository_root=Path(temporary),
                        parity_policy=Path("/approved/original.json"), environ=env,
                        completed_frozen=None if mode == "authority" else native)
                if mode != "ok":
                    with self.assertRaises(ValueError):
                        call()
                else:
                    report = call()
                    self.assertEqual(112, report["phaseCount"])
                    self.assertEqual("hosted-original-parity-reuse", report["verificationContext"]["kind"])
                    self.assertEqual(consumer["producer"], report["verificationContext"]["producer"])
                    self.assertEqual(rows, report["originalPhases"])
                    native.check_consumer.assert_called_once_with(consumer)
                    parity.assert_called_once_with(Path(temporary).resolve(), plan["validationCommit"],
                        selected, Path("/approved/original.json"), None, "fixture")
                self.assertEqual(original, selected)
                if mode in {"incomplete", "authority", "job", "local"}:
                    parity.assert_not_called()
                if mode in {"authority", "job", "local"}:
                    replay.assert_not_called()

    def test_hosted_parity_cli_keeps_native_lifetime_and_emits_nothing_on_late_failure(self):
        self.assertTrue(hasattr(completion, "require_hosted_sdk_parity"))
        argv = ["--hosted-parity", "--plan", str(self.paths[0]), "--discovery-root", str(self.paths[1]),
                "--state-root", str(self.paths[2]), "--repository-root", str(self.root),
                "--completed-frozen-policy", "/approved/native.json", "--parity-policy", "/approved/parity.json"]
        native = object()
        events = []
        report = {"result": "passed", "fixture": "not hosted evidence"}
        for late in (False, True):
            @contextmanager
            def authority(args):
                self.assertEqual(Path("/approved/native.json"), args.completed_frozen_policy)
                events.append("enter")
                yield {"completed_frozen": native}
                events.append("exit")
                if late:
                    raise ValueError("native policy changed")
            def verify(*args, **options):
                self.assertEqual("enter", events[-1])
                self.assertIs(os.environ, options["environ"])
                self.assertEqual("true", options["environ"]["GITHUB_ACTIONS"])
                self.assertIs(native, options["completed_frozen"])
                self.assertEqual(Path("/approved/parity.json"), options["parity_policy"])
                return report
            stdout = io.StringIO()
            with patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "GITHUB_JOB": "sdk-parity"}), \
                    patch.object(completion, "completed_frozen_options", authority), \
                    patch.object(completion, "require_hosted_sdk_parity", side_effect=verify), \
                    redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                if late:
                    with self.assertRaises(SystemExit):
                        completion.main(argv)
                    self.assertEqual("", stdout.getvalue())
                else:
                    self.assertEqual(0, completion.main(argv))
                    self.assertEqual(canonical_json_bytes(report).decode(), stdout.getvalue())
                self.assertEqual("true", os.environ["GITHUB_ACTIONS"])
        for extra in (["--local"], ["--repository"], ["--parity-archive", "/untrusted/held.zip"],
                      ["--github-output", "/unused"], ["--partial-catalog-destination", "/unused"]):
            with patch.object(completion, "require_hosted_sdk_parity") as verify, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                completion.main(argv + extra)
            verify.assert_not_called()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            completion.main(argv[:argv.index("--completed-frozen-policy")] + argv[-2:])

    def test_local_sdk_routes_root_to_authenticated_closure_and_original_parity_only(self):
        argv = ["--sdk", "--local", "--repository-root", "/actual/repository",
            "--completed-frozen-policy", "/actual/completed.json",
            "--parity-policy", "/actual/parity.json", "--parity-archive", "/actual/parity.zip"]
        for gradle in (False, True):
            name = "run_local_repository_gradle" if gradle else "require_local_repository_completion"
            with patch.object(completion, name, return_value={"result": "passed"}) as verify, \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(0, completion.main(argv + (["--gradle"] if gradle else [])))
                verify.assert_called_once_with(Path("/actual/repository"), Path("/actual/completed.json"),
                    parity_policy=Path("/actual/parity.json"), parity_archive=Path("/actual/parity.zip"))
        for bad in (argv + ["--repository"], argv[:-2], argv[1:], argv + ["--plan", "/unused"]):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                completion.main(bad)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            policy = root / "caller.json"
            policy.write_bytes(b"{}\n")
            report = root / "build/reports/sdk/completed-sdk-evidence.json"
            def gradle(command, **options):
                init = Path(command[command.index("--init-script", command.index("--init-script") + 1) + 1]).read_text()
                self.assertIn("root.tasks.named('verifySdk').configure", init)
                self.assertIn("setDependsOn([authenticated])", init)
                self.assertIn("'--sdk', '--local'", init)
                self.assertNotIn("verifyRepository", init)
                self.assertEqual(":verifySdk", command[-1])
                report.parent.mkdir(parents=True)
                report.write_bytes(b'{"result":"passed"}\n')
            with patch.object(completion.subprocess, "run", side_effect=gradle):
                self.assertEqual({"result": "passed"}, completion.run_local_repository_gradle(root, policy,
                    parity_policy=root / "parity.json", parity_archive=root / "parity.zip"))

    def test_runtime_scope_authenticates_all_fifty_originals_without_fetching_sdk_extension(self):
        import reuse_qualification as native
        from products import reuse
        instances = tuple(sorted(item for item in PHASE_INSTANCE_IDS if item.product != "sdk"))
        self.assertEqual(50, len(instances))
        rows = {item: phase(item) for item in instances}
        authorities = [dict(zip(completion.products._IDENTITY_KEYS, (
            item.product, item.component, item.phase, item.target)),
            flagsDigest="sha256:" + "c" * 64, toolchainProfileDigest="sha256:" + "e" * 64,
            outputSchemaVersion=1) for item in instances]
        capability = Mock()
        capability.completed_phases.return_value = instances
        capability._values.return_value = ({}, rows)
        capability.envelope.side_effect = lambda row: {"original": row}
        revision = "d" * 40
        policy = dict(schemaVersion=1, kind="completed-frozen-reuse", consumerCommit=revision,
            verifierPolicySha256="sha256:" + "a" * 64, artifactId=123, artifactSha256="sha256:" + "b" * 64,
            runId=45, runAttempt=1, signerCommit="e" * 40, sourceCommit="e" * 40,
            sdkCompletion={"fixture": "must not be acquired in Runtime scope"})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            pinned = root / "policy.json"
            pinned.write_bytes(canonical_json_bytes(policy))
            with patch.object(native, "validate_completed_reuse_policy"), \
                    patch.object(native, "fetch_completed_frozen", return_value=(capability, {})) as fetch, \
                    patch.object(completion.products, "_git_value", return_value=revision), \
                    patch.object(completion.products, "_authorities", return_value=(authorities, None)), \
                    patch.object(completion.products, "_versions", return_value={}), \
                    patch.object(reuse, "_phase_git_inventories", return_value={item: [] for item in instances}), \
                    patch.object(reuse, "advance_reuse", return_value=(inspected(list(rows.values()))["result"], {})):
                result = completion.require_local_repository_completion(root, pinned,
                    runtime_only=True, environ={"GH_TOKEN": "fixture"})
                self.assertEqual(50, result["phaseCount"])
                self.assertEqual(["contract", "runtime"], [row["product"] for row in result["products"]])
                self.assertEqual(1, len(result["edges"]))
                self.assertNotIn("sdk_completion", fetch.call_args.kwargs)
                capability.completed_phases.return_value = instances[:-1]
                with self.assertRaises(ValueError):
                    completion.require_local_repository_completion(root, pinned,
                        runtime_only=True, environ={"GH_TOKEN": "fixture"})

    def test_standalone_adapter_preserves_settings_contract_gate_and_binds_its_manifest(self):
        argv = ["--runtime", "--local", "--gradle", "--repository-root", "/actual/repository",
            "--completed-frozen-policy", "/actual/completed.json",
            "--runtime-contract-policy", "/actual/contract.json"]
        with patch.object(completion, "run_local_repository_gradle", return_value={"result": "passed"}) as gate, \
                redirect_stdout(io.StringIO()):
            self.assertEqual(0, completion.main(argv))
            gate.assert_called_once_with(Path("/actual/repository"), Path("/actual/completed.json"),
                                        runtime_contract_policy=Path("/actual/contract.json"))
        for bad in (argv[:-2], argv + ["--sdk"], argv + ["--repository"],
                    argv + ["--runtime-contract-manifest", "/fake/settings-manifest"]):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                completion.main(bad)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            policy = root / "inputs.json"
            inputs = dict(schemaVersion=1, contractVersion="0.8.0", runtimeVersion="0.8.0", target="jvm")
            for name in ("contractPayload", "contractMetadataReceipt", "contractAttestation",
                         "contractAttestationSignature", "contractPublicKey"):
                path = root / name
                path.write_bytes(b"{}\n")
                inputs[name] = str(path)
            policy.write_bytes(canonical_json_bytes(inputs))
            report = root / "runtime/build/reports/runtime/completed-runtime-evidence.json"
            def gradle(command, **options):
                init = Path(command[command.index("--init-script", command.index("--init-script") + 1) + 1]).read_text()
                self.assertIn("root.tasks.named('verifyRuntime').configure", init)
                self.assertIn("setDependsOn([authenticated])", init)
                self.assertIn("'--runtime', '--local'", init)
                self.assertIn("get('codexAgent.verifiedContractManifest').absolutePath", init)
                self.assertEqual(str(root / "runtime"), command[command.index("--project-dir") + 1])
                self.assertEqual(":verifyRuntime", command[-1])
                for name, value in inputs.items():
                    if name != "schemaVersion":
                        self.assertIn("-PcodexAgent." + name + "=" + value, command)
                report.parent.mkdir(parents=True)
                report.write_bytes(b'{"result":"passed"}\n')
            with patch.object(completion.subprocess, "run", side_effect=gradle):
                self.assertEqual({"result": "passed"}, completion.run_local_repository_gradle(
                    root, policy, runtime_contract_policy=policy))
            metadata = dict(product="contract", component="contract", phase="metadata", target="common",
                receiptSha256=completion.sha256_bytes(b"{}\n"))
            manifest = root / "runtime/.gradle/verified-contracts/current/contract-manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_bytes(b'{"fixture":"current manifest"}\n')
            digest = "sha256:" + "f" * 64
            with patch.object(completion.products, "validate_phase_receipt",
                    return_value=dict(productVersion="0.8.0", outputs=[dict(bytes=50, sha256=digest)])), \
                    patch.object(completion, "verified_zip_contents", return_value=(
                        [], {"contract-manifest.json": manifest.read_bytes()}, dict(bytes=50, sha256=digest))):
                versions = {"contract": "0.8.0", "runtime-release": "0.8.0"}
                result = completion._bind_runtime_contract(root, {"phases": [metadata]}, policy, manifest, versions)
                self.assertEqual(digest, result["payloadSha256"])
                manifest.write_bytes(b'{"fixture":"tampered manifest"}\n')
                with self.assertRaisesRegex(ValueError, "manifest/payload"):
                    completion._bind_runtime_contract(root, {"phases": [metadata]}, policy, manifest, versions)
                metadata["receiptSha256"] = digest
                with self.assertRaisesRegex(ValueError, "current authenticated"):
                    completion._bind_runtime_contract(root, {"phases": [metadata]}, policy, manifest, versions)

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
