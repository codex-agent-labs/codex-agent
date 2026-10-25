import copy
import contextlib
import io
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("consumer", Path(__file__).with_name("consumer.py"))
consumer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(consumer)
APPROVAL = {**json.loads(Path(__file__).with_name("approvals.json").read_text()), "authorityCommit": "a" * 40}
RECORD = APPROVAL["qualifications"][0]


class AcquisitionTests(unittest.TestCase):
    def test_completed_history_bound_preserves_exact_identities(self):
        with patch.dict(consumer.sys.modules):
            from products.inventory import canonical_json_bytes
            original = json.loads(Path(__file__).with_name("completed-reuse.json").read_bytes())
            original["policy"].pop("requalificationBaseline", None)
            self.assertEqual(len(original["gitHistory"]), 153)
            self.assertEqual(consumer.completed_descriptor(canonical_json_bytes(original), APPROVAL), original)
            for count in (1, 8, 10, 16, 17, 32, 33, 64, 65, 128, 129, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153):
                value = copy.deepcopy(original)
                value["gitHistory"] = [{"repository": consumer.authority.REPOSITORY,
                    "commit": f"{index + 1:040x}", "tree": "d" * 40} for index in range(count)]
                self.assertEqual(consumer.completed_descriptor(canonical_json_bytes(value), APPROVAL), value)
            for fault in ("empty", "excessive", "duplicate", "repository", "commit", "tree", "extra"):
                with self.subTest(fault=fault):
                    value = copy.deepcopy(original)
                    rows = value["gitHistory"]
                    if fault == "empty": rows.clear()
                    elif fault == "excessive": rows[:] = [{"repository": consumer.authority.REPOSITORY,
                        "commit": f"{index + 1:040x}", "tree": "d" * 40} for index in range(154)]
                    elif fault == "duplicate": rows[-1] = dict(rows[0])
                    elif fault == "extra": rows[0]["untrusted"] = True
                    else: rows[0][fault] = "unreviewed"
                    with self.assertRaises(ValueError):
                        consumer.completed_descriptor(canonical_json_bytes(value), APPROVAL)

    def test_completed_source_and_parent_use_their_independently_pinned_recipe(self):
        from products.inventory import canonical_json_bytes
        issuer, parent = "a" * 40, "b" * 40
        document = {"policy": {"sdkCompletion": {"signerCommit": issuer}}}
        value = {"approvedVerifiers": [issuer, parent]}
        root = Path("unused")
        original = {"schemaVersion": 1, "sdkInputs": {"source": "exact original"}}
        extension = {"schemaVersion": 3, "parent": {"signerCommit": parent, "sourceCommit": parent},
                     "completedPhases": [{"phase": "package"}]}
        for version in (1, 2, 3, 4):
            current = {**extension, "schemaVersion": version}
            if version == 4:
                # Source observations are validated by _spec; none adds a claim.
                current["sourcePredecessors"] = [{"observed": index} for index in range(51)]
            inherited = version != 1
            rows = [canonical_json_bytes(current), canonical_json_bytes(original)] if inherited else [canonical_json_bytes(original)]
            with self.subTest(version=version), \
                    patch("reuse_qualification._sdk_completed_spec_path", side_effect=lambda root, commit: commit + ".json") as select, \
                    patch("products.inventory.git_regular_blob_bytes", side_effect=rows) as read, \
                    patch("completed_sdk_reuse._spec") as validate:
                self.assertEqual((original, 2 if inherited else 1), consumer.completed_sdk_spec(root, document, value))
                self.assertEqual([issuer, parent] if inherited else [issuer], [call.args[1] for call in select.call_args_list])
                self.assertEqual([call.args[1] + ".json" for call in read.call_args_list], [call.args[2] for call in read.call_args_list])
                if inherited:
                    validate.assert_called_once_with(current)
                else:
                    validate.assert_not_called()
        with patch("reuse_qualification._sdk_completed_spec_path", return_value="fixed.json"), \
                patch("products.inventory.git_regular_blob_bytes", return_value=canonical_json_bytes(current)) as read, \
                patch("completed_sdk_reuse._spec", side_effect=ValueError("invalid source context")), \
                self.assertRaisesRegex(ValueError, "invalid source context"):
            consumer.completed_sdk_spec(root, document, value)
        self.assertEqual(1, read.call_count)
        with patch("reuse_qualification._sdk_completed_spec_path", return_value="fixed.json"), \
                patch("products.inventory.git_regular_blob_bytes", return_value=canonical_json_bytes(extension)) as read, \
                patch("completed_sdk_reuse._spec"), self.assertRaisesRegex(ValueError, "independently approved"):
            consumer.completed_sdk_spec(root, document, {"approvedVerifiers": [issuer]})
        self.assertEqual(1, read.call_count)

    def test_requalification_requires_an_approved_baseline_with_exact_git_custody(self):
        from products.inventory import canonical_json_bytes
        original = json.loads(Path(__file__).with_name("completed-reuse.json").read_bytes())
        baseline = original["policy"].get("requalificationBaseline", next(row["commit"] for row in original["gitHistory"] if row["commit"] in APPROVAL["approvedVerifiers"]))
        original["policy"]["requalificationBaseline"] = baseline
        if not any(row["commit"] == baseline for row in original["gitHistory"]):
            original["gitHistory"].append({"repository": consumer.authority.REPOSITORY,
                "commit": baseline, "tree": "d" * 40})
        self.assertEqual(original, consumer.completed_descriptor(canonical_json_bytes(original), APPROVAL))
        for fault in ("approval", "history", "mutable-baseline"):
            value, approvals = copy.deepcopy(original), copy.deepcopy(APPROVAL)
            if fault == "approval": approvals["approvedVerifiers"].remove(baseline)
            elif fault == "history": value["gitHistory"] = [r for r in value["gitHistory"] if r["commit"] != baseline]
            else: value["policy"]["requalificationBaseline"] = "HEAD"
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                consumer.completed_descriptor(canonical_json_bytes(value), approvals)

    def test_requalification_never_exports_the_stale_sdk_input_binding(self):
        from products.inventory import canonical_json_bytes
        original = json.loads(Path(__file__).with_name("completed-reuse.json").read_bytes())
        for requalifying in (False, True):
            document = copy.deepcopy(original)
            if requalifying:
                document["policy"]["requalificationBaseline"] = APPROVAL["activeVerifier"]
            else:
                document["policy"].pop("requalificationBaseline", None)
            with self.subTest(requalifying=requalifying), tempfile.TemporaryDirectory() as temporary, \
                    patch.object(consumer.authority, "contents", return_value=canonical_json_bytes(document)), \
                    patch.object(consumer, "completed_descriptor", return_value=document), \
                    patch.object(consumer, "history", return_value={}), \
                    patch.object(consumer, "retained_sdk_binding_current", return_value=not requalifying), \
                    patch.object(consumer, "completed_sdk_spec", return_value=(
                        {"sdkInputs": {"source": document["retainedSdkInputsSource"]}}, 11)):
                _, environment = consumer.completed_environment(Path(temporary), Path(temporary), APPROVAL)
                self.assertEqual(requalifying, environment["CODEX_AGENT_RETAINED_SDK_INPUTS_SOURCE"] == "")
                self.assertTrue(environment["CODEX_AGENT_COMPLETED_REUSE_POLICY"])

    def test_adapter_only_requalification_retains_the_input_locator_not_authority(self):
        from products import selection
        from products.registry import NATIVE_BINDINGS, PhaseInstanceId
        document = {"policy": {"consumerCommit": "a" * 40, "requalificationBaseline": "b" * 40}}
        for component, expected in (("sdk-android", True), *((name, True) for name in NATIVE_BINDINGS),
                                    ("contract", False), ("runtime-aggregate", False),
                                    ("sdk-core", False), ("sdk-ios", False), ("javascript", False)):
            phase = PhaseInstanceId("sdk", component, "binary", "test")
            with self.subTest(component=component), \
                    patch("products.inventory.tree_entries", side_effect=[[("p", "old")], [("p", "new")]]) as trees, \
                    patch("products.registry.PHASE_INSTANCE_IDS", (phase,)), \
                    patch.object(selection, "phase_inventory_paths", return_value=("p",)):
                self.assertEqual(expected, consumer.retained_sdk_binding_current(Path("unused"), document))
                self.assertEqual(["b" * 40, "a" * 40], [call.args[1] for call in trees.call_args_list])
        with patch("products.inventory.tree_entries", side_effect=ValueError("missing Git")), \
                self.assertRaisesRegex(ValueError, "missing Git"):
            consumer.retained_sdk_binding_current(Path("unused"), document)
        with patch("products.inventory.tree_entries") as trees:
            self.assertTrue(consumer.retained_sdk_binding_current(Path("unused"), {"policy": {}}))
            trees.assert_not_called()

    def test_input_locator_uses_real_shared_product_ownership(self):
        document = {"policy": {"consumerCommit": "a" * 40, "requalificationBaseline": "b" * 40}}
        for path, expected in (("ci/native_wrappers.py", True), ("ci/products/sdk_native.py", True),
                ("ci/products/sdk_inputs.py", False), ("ci/products/sdk_compatibility.py", False),
                ("gradle/release/versions/sdk.txt", False),
                ("gradle/release/keys/sdk-runtime-root.pub", False),
                ("ci/products/contract.py", False), ("ci/products/runtime_aggregate.py", False),
                ("unknown/input", False)):
            with self.subTest(path=path), patch("products.inventory.tree_entries", side_effect=[[(path,"old")],[(path,"new")]]):
                self.assertEqual(expected, consumer.retained_sdk_binding_current(Path("unused"), document))

    def test_batched_blobs_keep_exact_bytes_and_reject_protocol_corruption(self):
        oid = "b" * 40
        header = (oid + " blob 3\n").encode()
        with patch.object(consumer, "git", side_effect=[header, header + b"abc\n"]) as command:
            self.assertEqual(consumer.blobs(Path("unused"), [oid, oid]), {oid: b"abc"})
            self.assertEqual(command.call_count, 2)
            self.assertEqual(command.call_args.kwargs["data"], (oid + "\n").encode())
        for metadata, response in ((b"", b""), (header * 2, b""),
                (header.replace(b"blob", b"tree"), b""),
                (header.replace(b"3\n", b"-1\n"), b""),
                (header.replace(b"3\n", b"16777217\n"), b""),
                (header, header.replace(b"blob", b"tree") + b"abc\n"),
                (header, header + b"ab\n"), (header, header + b"abc!"),
                (header, header + b"abc\nextra")):
            with self.subTest(metadata=metadata, response=response), \
                    patch.object(consumer, "git", side_effect=[metadata, response]), self.assertRaises(ValueError):
                consumer.blobs(Path("unused"), [oid])
        objects = [f"{i:040x}" for i in range(5)]
        metadata = b"".join((x + " blob 16777216\n").encode() for x in objects)
        with patch.object(consumer, "git", return_value=metadata) as command, self.assertRaisesRegex(ValueError, "total bound"):
            consumer.blobs(Path("unused"), objects)
        command.assert_called_once()

    def test_sdk_parity_descriptor_is_canonical_bounded_original_policy(self):
        from products.inventory import canonical_json_bytes
        raw = Path(__file__).with_name("completed-sdk-parity.json").read_bytes()
        policy = json.loads(raw)
        self.assertEqual(consumer.sdk_parity_policy(raw), policy)
        self.assertEqual(policy["artifactId"], 12602670281)
        self.assertEqual(policy["jobId"], 121177434633)
        self.assertNotEqual(policy["workflowSha"], APPROVAL["authorityCommit"])
        for fault in ("extra", "kind", "version", "repository", "workflow", "pr", "run",
                      "job", "artifact", "digest", "publisher", "canonical", "bound"):
            value = copy.deepcopy(policy)
            if fault == "extra": value["consumerCommit"] = APPROVAL["activeVerifier"]
            elif fault == "kind": value["kind"] = "completed-frozen-reuse"
            elif fault == "version": value["schemaVersion"] = True
            elif fault == "repository": value["producer"]["repository"] = "untrusted/fork"
            elif fault == "workflow": value["producer"]["workflowPath"] = ".github/workflows/other.yml"
            elif fault == "pr": value["producer"]["pullRequest"] = 32
            elif fault == "run": value["producer"]["runId"] = True
            elif fault == "job": value["jobId"] = 0
            elif fault == "artifact": value["artifactId"] = True
            elif fault == "digest": value["artifactSha256"] = "wrong"
            elif fault == "publisher": value["workflowSha"] = "reuse-authority"
            modified = canonical_json_bytes(value)
            if fault == "canonical": modified += b" "
            if fault == "bound": modified += b" " * 4096
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                consumer.sdk_parity_policy(modified)

    def test_sdk_parity_provision_uses_same_authority_and_rejects_changed_policy(self):
        from products.inventory import canonical_json_bytes
        document = json.loads(Path(__file__).with_name("completed-reuse.json").read_bytes())
        raw = canonical_json_bytes(document)
        parity = Path(__file__).with_name("completed-sdk-parity.json").read_bytes()
        protection = {"restrictions": {"users": [{"login": "ciurlaro", "id": 19213191}], "teams": [], "apps": []},
            **{name: {"enabled": enabled} for name, enabled in (("enforce_admins", True),
                ("block_creations", True), ("allow_force_pushes", False), ("allow_deletions", False))}}
        original = Path.cwd()
        for fault in ("off", None, "source", "descriptor", "local", "late-local", "occupied", "symlink", "branch"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve();work = root / "private";work.mkdir();export = root / "env"
                policy_path = work / "completed-sdk-parity-policy.json";reads = []
                value = {**APPROVAL, **({"activeVerifier": "f" * 40} if fault == "source" else {})}
                if fault == "occupied": policy_path.write_bytes(parity)
                if fault == "symlink": policy_path.symlink_to(root / "missing")
                def fetch(path, revision):
                    self.assertEqual(revision, APPROVAL["authorityCommit"]);reads.append(path)
                    if path == ".reuse/completed-reuse.json": return raw
                    self.assertEqual(path, ".reuse/completed-sdk-parity.json")
                    if reads.count(path) == 2:
                        if fault == "descriptor": return parity + b" "
                        if fault == "local": policy_path.write_bytes(parity + b" ")
                    return parity
                def observe(path):
                    if path.endswith("/protection"): return protection
                    self.assertEqual(path, "branches/reuse-authority")
                    if fault == "late-local": policy_path.write_bytes(parity + b" ")
                    return {"commit": {"sha": "f" * 40 if fault == "branch" else APPROVAL["authorityCommit"]}}
                try:
                    with patch.dict(os.environ, {"GITHUB_ENV": str(export)}, clear=True), \
                            patch.object(consumer.sys, "argv", ["consumer", "provision", "--repository-root", str(root),
                                "--work", str(work), *([] if fault == "off" else ["--sdk-parity"])]), \
                            patch.object(consumer, "approved", return_value=value) as approved, \
                            patch.object(consumer, "snapshot", return_value={}) as snapshot, \
                            patch.object(consumer.authority, "contents", side_effect=fetch), \
                            patch.object(consumer.authority, "api", side_effect=observe), \
                            patch.object(consumer, "history", return_value={}) as history, \
                            patch.object(consumer, "retained_sdk_binding_current", return_value=True), \
                            patch.object(consumer, "completed_sdk_spec", return_value=({"sdkInputs": {
                                "source": document["retainedSdkInputsSource"]}}, 62)), contextlib.redirect_stdout(io.StringIO()):
                        if fault not in (None, "off"):
                            with self.assertRaises((ValueError, FileExistsError)): consumer.main()
                            self.assertFalse(export.exists())
                            self.assertFalse((work / "provision.json").exists())
                        else:
                            consumer.main()
                            approved.assert_called_once_with(None)
                            snapshot.assert_called_once_with(root, value, work)
                            self.assertEqual(history.call_count, len(document["gitHistory"]))
                            self.assertEqual(reads.count(".reuse/completed-sdk-parity.json"), 0 if fault == "off" else 2)
                            result = json.loads((work / "provision.json").read_bytes())
                            self.assertEqual(result["productArtifactDownloads"], 0)
                            self.assertEqual(result["nativeAuthentication"], "required by each explicit consumer")
                            if fault == "off":
                                self.assertNotIn("SDK_PARITY_POLICY", export.read_text())
                                self.assertFalse(policy_path.exists())
                            else:
                                self.assertEqual(policy_path.read_bytes(), parity)
                                self.assertIn("CODEX_AGENT_COMPLETED_SDK_PARITY_POLICY=" + str(policy_path), export.read_text())
                                self.assertEqual(result["sdkParityAuthentication"], "required by each explicit consumer")
                finally: os.chdir(original)

    def test_sdk_parity_selector_is_provision_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            for mode in ("setup", "restore", "verify"):
                with self.subTest(mode=mode), patch.object(consumer.sys, "argv", ["consumer", mode,
                        "--repository-root", temporary, "--work", temporary + "/work", "--sdk-parity"]), \
                        patch.object(consumer, "approved") as approved, self.assertRaisesRegex(ValueError, "combined provisioning"):
                    consumer.main()
                approved.assert_not_called()

    def test_native_provision_resolves_once_and_checks_fresh_governance_before_export(self):
        protection = {"restrictions": {"users": [{"login": "ciurlaro", "id": 19213191}], "teams": [], "apps": []},
            **{name: {"enabled": enabled} for name, enabled in (("enforce_admins", True),
                ("block_creations", True), ("allow_force_pushes", False), ("allow_deletions", False))}}
        original = Path.cwd()
        for fault in (None, "branch", "protection", "environment", "snapshot", "pins"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve();work = root / "private";export = root / "env"
                selected = copy.deepcopy(protection)
                if fault == "protection": selected["allow_force_pushes"]["enabled"] = True
                revision = "f" * 40 if fault == "branch" else APPROVAL["authorityCommit"]
                try:
                    with patch.dict(os.environ, {"GITHUB_ENV": str(export)}, clear=True), \
                            patch.object(consumer.sys, "argv", ["consumer.py", "provision", "--repository-root", str(root), "--work", str(work)]), \
                            patch.object(consumer, "approved", return_value=APPROVAL) as approved, \
                            patch.object(consumer, "snapshot", return_value={"portableProfile": "retained"},
                                side_effect=ValueError("snapshot") if fault == "snapshot" else None) as snapshot, \
                            patch.object(consumer, "completed_environment", return_value=({"productArtifactDownloads": 0},
                                {"POLICY": "exact\nforged=value" if fault == "environment" else "exact"}),
                                side_effect=ValueError("pins") if fault == "pins" else None) as pins, \
                            patch.object(consumer.authority, "api", side_effect=[selected, {"commit": {"sha": revision}}]) as api, \
                            contextlib.redirect_stdout(io.StringIO()):
                        if fault:
                            with self.assertRaises(ValueError): consumer.main()
                            self.assertFalse(export.exists())
                            self.assertFalse((work / "provision.json").exists())
                        else:
                            consumer.main()
                            self.assertEqual(export.read_text(), "POLICY=exact\n")
                            approved.assert_called_once_with(None)
                            snapshot.assert_called_once_with(root, APPROVAL, work)
                            pins.assert_called_once_with(root, work, APPROVAL)
                            self.assertEqual([c.args[0] for c in api.call_args_list],
                                ["branches/reuse-authority/protection", "branches/reuse-authority"])
                            result = json.loads((work / "provision.json").read_bytes())
                            self.assertEqual(result["executionSnapshot"]["portableProfile"], "retained")
                finally:
                    os.chdir(original)

    def test_native_provision_rejects_body_selectors_and_unpaired_assertions(self):
        fields = ("REQUESTED_ARTIFACT_SHA", "REQUESTED_RUN", "REQUESTED_ATTEMPT", "REQUESTED_ISSUER", "REQUESTED_SOURCE")
        for field in (None, *fields):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary, \
                    patch.dict(os.environ, {field: "unpaired"} if field else {}, clear=True), \
                    patch.object(consumer.sys, "argv", ["consumer.py", "provision", "--repository-root", temporary,
                        "--work", temporary + "/work", *([] if field else ["--artifact-id", "77"])]), \
                    patch.object(consumer, "approved") as approved, self.assertRaisesRegex(ValueError, "only accepts native"):
                consumer.main()
            approved.assert_not_called()

    def test_action_dispatches_native_once_and_retains_explicit_body_restore(self):
        root = Path(__file__).resolve().parents[1]
        action = (root / ".github/actions/restore-reuse-qualification/action.yml").read_text()
        self.assertIn("if: steps.native.outputs.supported == 'true' && inputs.artifact-id != ''", action)
        block = action.split("      run: |\n", 1)[1].split("    - name:", 1)[0]
        script = "\n".join(line[8:] for line in block.splitlines())
        self.assertIn("sdk-parity:\n    default: 'false'", action)
        for selector, expected, nested, parity, valid in (
                ("", "provision", "", "false", True), ("77", "setup", "", "false", True),
                ("", "provision", "/trusted source", "true", True),
                ("77", "setup", "", "true", False), ("", "provision", "", "unknown", False)):
            with self.subTest(selector=selector, nested=nested, parity=parity):
                env = {**os.environ, "REUSE_AUTHORITY_READ_TOKEN": "test-only", "CHECKPOINT_OWNER": "false", "SDK_PARITY": "false", "APPROVED_ARTIFACT_ID": selector,
                    "GITHUB_ACTION_PATH": str(root / ".github/actions/restore-reuse-qualification"),
                    "GITHUB_WORKSPACE": "/consumer with spaces", "CONSUMER_ROOT": nested, "RUNNER_TEMP": "/runner temp", "SDK_PARITY": parity}
                result = subprocess.run(["bash", "-euc", 'uname() { if [ "$1" = -s ]; then echo Linux; else echo x86_64; fi; }; '
                    'python3() { printf "%s\\n" "$@"; }; bash() { :; };\n' + script],
                    env=env, capture_output=True, text=True)
                if not valid:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, "")
                    continue
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines().count("-B"), 1)
                self.assertEqual("--sdk-parity" in result.stdout.splitlines(), parity == "true")
                self.assertEqual(result.stdout.splitlines()[2], expected)
                self.assertEqual(result.stdout.splitlines()[4], nested or env["GITHUB_WORKSPACE"])

    def test_warm_proof_protects_frozen_scope_and_retains_legacy_zero_change_check(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/approved-reuse.yml").read_text()
        block = workflow.split("          q = proof['portableQualification']\n", 1)[1].split("          PY", 1)[0]
        script = "q = proof['portableQualification']\n" + "\n".join(line[10:] for line in block.splitlines())
        proof = {"frozenPhases": 50, "productInventories": 112, "selectedProductPhases": 0,
                 "changedProductInventories": 0, "originalColdArchiveBytes": 0, "originalRangeBytes": 0,
                 "portableQualification": {"qualificationHits": 46, "qualificationMisses": 0,
                    "downloadedArtifactCount": 0, "downloadedArtifactBytes": 0}}
        for changes, accepted in (({}, True), ({"changedProductInventories": 5}, False),
                ({"changedProductInventories": 5, "changedFrozenInventories": 0}, True),
                ({"changedProductInventories": 5, "changedFrozenInventories": 1}, False),
                ({"selectedProductPhases": 1, "changedFrozenInventories": 0}, False)):
            with self.subTest(changes=changes):
                arguments = {"proof": {**proof, **changes}, "storage": {"entries": 1, "hits": 1, "misses": 0}}
                if accepted:
                    exec(compile(script, "warm-proof-check", "exec"), arguments)
                else:
                    with self.assertRaises(AssertionError):
                        exec(compile(script, "warm-proof-check", "exec"), arguments)

    def verdict(self):
        return [{"verificationResult": {"statement": {
            "predicateType": "https://slsa.dev/provenance/v1",
            "subject": [{"name": "qualification.json", "digest": {"sha256": RECORD["qualificationSha256"][7:]}}],
            "predicate": {"buildDefinition": {
                "externalParameters": {"workflow": {"path": ".github/workflows/portable-reuse-proof.yml",
                    "ref": "refs/pull/31/merge", "repository": consumer.REPOSITORY_URL}},
                "resolvedDependencies": [{"uri": "git+" + consumer.REPOSITORY_URL + "@refs/pull/31/merge",
                                          "digest": {"gitCommit": "b" * 40}}]},
                "runDetails": {"builder": {"id": consumer.REPOSITORY_URL +
                    "/.github/workflows/reuse-qualification.yml@" + RECORD["issuerSha"]},
                    "metadata": {"invocationId": consumer.REPOSITORY_URL +
                        f"/actions/runs/{RECORD['runId']}/attempts/{RECORD['runAttempt']}"}}}}}}]

    def test_native_source_is_original_and_cross_pairs_fail(self):
        verdict = self.verdict()
        self.assertEqual(consumer.original_source(verdict, RECORD), "b" * 40)
        for mutation in (
            lambda s: s["subject"][0]["digest"].update(sha256="0" * 64),
            lambda s: s["predicate"]["runDetails"]["builder"].update(id="unreviewed"),
            lambda s: s["predicate"]["runDetails"]["metadata"].update(invocationId="other-run"),
            lambda s: s["predicate"]["buildDefinition"]["externalParameters"]["workflow"].update(repository="other"),
            lambda s: s["predicate"]["buildDefinition"]["resolvedDependencies"].append({}),
            lambda s: s["predicate"]["buildDefinition"]["resolvedDependencies"][0]["digest"].update(gitCommit="latest"),
        ):
            value = copy.deepcopy(verdict); mutation(value[0]["verificationResult"]["statement"])
            with self.assertRaises(ValueError): consumer.original_source(value, RECORD)
        with self.assertRaises(ValueError): consumer.original_source([], RECORD)
        with self.assertRaises(ValueError): consumer.original_source(verdict * 2, RECORD)

    def test_relative_native_builder_requires_exact_approved_issuer_source(self):
        verdict = self.verdict()
        statement = verdict[0]["verificationResult"]["statement"]
        statement["predicate"]["runDetails"]["builder"]["id"] = consumer.REPOSITORY_URL + \
            "/.github/workflows/reuse-qualification.yml@refs/pull/31/merge"
        statement["predicate"]["buildDefinition"]["resolvedDependencies"][0]["digest"]["gitCommit"] = RECORD["issuerSha"]
        self.assertEqual(consumer.original_source(verdict, RECORD), RECORD["issuerSha"])
        for mutation in (
            lambda s: s["predicate"]["buildDefinition"]["resolvedDependencies"][0]["digest"].update(gitCommit="b" * 40),
            lambda s: s["predicate"]["runDetails"]["builder"].update(id=consumer.REPOSITORY_URL +
                "/.github/workflows/reuse-qualification.yml@refs/pull/32/merge"),
            lambda s: s["predicate"]["runDetails"]["metadata"].update(invocationId="other-run"),
        ):
            value = copy.deepcopy(verdict)
            mutation(value[0]["verificationResult"]["statement"])
            with self.assertRaises(ValueError): consumer.original_source(value, RECORD)

    def test_retired_qualification_is_preserved_without_ambiguous_default_selection(self):
        import sys
        # Other cases load verifier modules from their own isolated Git fixture.
        with patch.dict(sys.modules), patch.object(sys, "path", [
                str(Path(__file__).resolve().parents[1] / "ci"), *sys.path]):
            import product_reuse
            new = {**RECORD, "artifactId": RECORD["artifactId"] + 1, "issuerSha": "d" * 40}
            value = {**APPROVAL, "activeVerifier": new["issuerSha"], "qualifications": [RECORD, new]}
            before = copy.deepcopy(value)
            for selector, expected in ((None, new), (RECORD["artifactId"], RECORD)):
                with patch.object(product_reuse, "api_json", side_effect=ValueError("observation boundary")) as observed:
                    with self.assertRaisesRegex(ValueError, "observation boundary"):
                        consumer.restore(Path("."), Path("unused"), value, selector, "test-only")
                    self.assertTrue(observed.call_args.args[0].endswith(f"/artifacts/{expected['artifactId']}"))
            self.assertEqual(before, value)
            with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
                consumer.restore(Path("."), Path("unused"), {**value, "qualifications": [new, new]}, None, "test-only")

    def test_composite_uses_protected_root_and_rejects_modified_acquisition(self):
        root = Path(__file__).resolve().parents[1]
        value = {**APPROVAL}
        with patch.object(consumer.authority, "api", return_value={"commit": {"sha": value["authorityCommit"]}}) as observed, \
             patch.object(consumer.authority, "resolve", return_value=value) as resolved, \
             patch.object(consumer.authority, "contents", side_effect=lambda name, revision: (root / name).read_bytes()):
            self.assertEqual(consumer.approved(None), value)
            observed.assert_called_once_with("branches/reuse-authority")
            resolved.assert_called_once_with(value["authorityCommit"])
        with patch.object(consumer.authority, "resolve", return_value=value), \
             patch.object(consumer.authority, "contents", return_value=b"changed"), self.assertRaisesRegex(ValueError, "source differs"):
            consumer.approved(value["authorityCommit"])

    def test_unsupported_native_platform_skips_setup_but_requires_credential(self):
        action = (Path(__file__).resolve().parents[1] / ".github/actions/restore-reuse-qualification/action.yml").read_text()
        guard = action.split('        test -n "$REUSE_AUTHORITY_READ_TOKEN"', 1)[1].split('        source_root=', 1)[0]
        guard = 'test -n "$REUSE_AUTHORITY_READ_TOKEN"' + guard
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            script = 'set -e\nuname() { echo MINGW64_NT/x86_64; }\n' + guard
            environment = {**os.environ, "GITHUB_OUTPUT": str(output), "REUSE_AUTHORITY_READ_TOKEN": "test-only", "CHECKPOINT_OWNER": "false", "SDK_PARITY": "false"}
            subprocess.run(["bash", "-c", script], env=environment, check=True, capture_output=True)
            self.assertEqual(output.read_text(), "supported=false\n")
            output.unlink()
            environment["REUSE_AUTHORITY_READ_TOKEN"] = ""
            result = subprocess.run(["bash", "-c", script], env=environment, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())

    def test_optional_selector_preserves_arguments_under_bash_nounset(self):
        root = Path(__file__).resolve().parents[1]
        action = (root / ".github/actions/restore-reuse-qualification/action.yml").read_text()
        block = action.split("    - name: Provision independent completion pins or authenticate an explicitly selected body qualification", 1)[1]
        script = "\n".join(line[8:] for line in block.split("      run: |\n", 1)[1].splitlines())
        for selector in ("", "77"):
            with self.subTest(selector=selector):
                environment = {**os.environ, "GITHUB_ACTION_PATH": str(root / ".github/actions/restore-reuse-qualification"),
                    "GITHUB_WORKSPACE": "/consumer with spaces", "RUNNER_TEMP": "/runner temp",
                    "APPROVED_ARTIFACT_ID": selector}
                result = subprocess.run(["/bin/bash", "-euc",
                    'python3() { printf "%s\\n" "$@"; }\n' + script],
                    env=environment, check=True, capture_output=True, text=True)
                expected = ["-B", str(root / ".reuse/consumer.py"), "restore", "--repository-root",
                    environment["GITHUB_WORKSPACE"], "--work", "/runner temp/approved-reuse"]
                self.assertEqual(expected + (["--artifact-id", selector] if selector else []),
                                 result.stdout.splitlines())

    def test_entrypoint_uses_current_consumer_directory_for_production_commands(self):
        original = Path.cwd()
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temporary:
            root, work = Path(temporary) / "product", Path(temporary) / "work"
            root.mkdir()
            try:
                with patch.object(consumer.sys, "argv", ["consumer.py", "setup", "--repository-root", str(root), "--work", str(work)]), \
                     patch.object(consumer, "approved", return_value=APPROVAL), \
                     patch.object(consumer, "snapshot", side_effect=lambda actual, value, private: {
                         "currentDirectoryMatches": Path.cwd() == actual}) as operation:
                    consumer.main()
                    operation.assert_called_once()
                    result = json.loads((work / "setup.json").read_text())
                    self.assertTrue(result["currentDirectoryMatches"])
            finally:
                os.chdir(original)

    def test_history_uses_authenticated_commit_tree_and_fixed_remote(self):
        producer = {"repository": consumer.authority.REPOSITORY, "commit": "b" * 40, "tree": "c" * 40}
        with patch.object(consumer, "git", return_value=("c" * 40 + "\n").encode()) as operation:
            self.assertEqual(consumer.history(Path("unused"), producer)["commit"], "b" * 40)
            self.assertEqual(operation.call_args.args[-1], "b" * 40 + "^{tree}")
        with patch.object(consumer, "git", return_value=b"wrong\n"), self.assertRaises(ValueError):
            consumer.history(Path("unused"), producer)
        with patch.object(consumer, "git") as operation, self.assertRaises(ValueError):
            consumer.history(Path("unused"), {**producer, "repository": "other"})
        operation.assert_not_called()
        missing = subprocess.CalledProcessError(1, ["git"])
        with patch.object(consumer, "git", side_effect=[missing, b"", ("c" * 40 + "\n").encode()]) as operation:
            consumer.history(Path("unused"), producer)
            self.assertEqual(operation.call_args_list[1].args[-2:], (consumer.REPOSITORY_URL + ".git", "b" * 40))

    def test_fetch_retries_recognized_transport_once_without_exposing_stderr(self):
        command = ("fetch", "--no-tags", consumer.REPOSITORY_URL + ".git", "b" * 40)
        for raw in (b"fatal: requested URL returned error: 502", b"fatal: requested URL returned error: 429",
                    b"Recv failure: Connection was reset", b"Connection reset by peer", b"Operation timed out"):
            secret = raw + b"\nAuthorization: secret-value\n::error::untrusted"
            failure = subprocess.CalledProcessError(128, ["git"], stderr=secret)
            with self.subTest(raw=raw), patch.object(consumer.subprocess, "run", side_effect=[
                    failure, subprocess.CompletedProcess([], 0, stdout=b"fetched")]) as run, \
                    patch.object(consumer.time, "sleep") as sleep, contextlib.redirect_stderr(io.StringIO()) as log:
                self.assertEqual(b"fetched", consumer.git(Path("unused"), *command))
            self.assertEqual(2, run.call_count)
            self.assertEqual(run.call_args_list[0], run.call_args_list[1])
            self.assertEqual(list(command), run.call_args.args[0][-4:])
            sleep.assert_called_once_with(2)
            diagnostic = json.loads(log.getvalue())
            self.assertTrue(diagnostic["retry"])
            self.assertEqual("sha256:" + consumer.hashlib.sha256(secret).hexdigest(), diagnostic["stderrSha256"])
            self.assertNotIn("secret-value", log.getvalue())
            self.assertNotIn("::error::", log.getvalue())

    def test_fetch_retry_exhaustion_and_timeout_remain_fatal(self):
        for failure in (subprocess.CalledProcessError(128, ["git"], stderr=b"Connection reset by peer"),
                        subprocess.TimeoutExpired(["git"], 120)):
            with self.subTest(error=type(failure)), patch.object(consumer.subprocess, "run", side_effect=failure) as run, \
                    patch.object(consumer.time, "sleep") as sleep, contextlib.redirect_stderr(io.StringIO()) as log, \
                    self.assertRaises(type(failure)) as result:
                consumer.git(Path("unused"), "fetch", "--no-tags", consumer.REPOSITORY_URL + ".git", "b" * 40)
            self.assertIs(failure, result.exception)
            self.assertEqual(2, run.call_count)
            sleep.assert_called_once_with(2)
            self.assertEqual([True, False], [json.loads(line)["retry"] for line in log.getvalue().splitlines()])

    def test_fetch_permanent_and_unknown_failures_do_not_retry(self):
        for raw, kind in ((b"Authentication failed\nConnection reset by peer", "authentication"),
                          (b"SSL certificate problem\nrequested URL returned error: 503", "certificate"),
                          (b"fatal: not our ref bbbbbbbbb\nOperation timed out", "object-unavailable"),
                          (b"requested URL returned error: 403", "http-permanent"),
                          (b"requested URL returned error: 404", "http-permanent"),
                          (b"requested URL returned error: 503\nrequested URL returned error: 401", "http-permanent"),
                          (b"unclassified server response secret-value", "unknown")):
            failure = subprocess.CalledProcessError(128, ["git"], stderr=raw)
            with self.subTest(raw=raw), patch.object(consumer.subprocess, "run", side_effect=failure) as run, \
                    patch.object(consumer.time, "sleep") as sleep, contextlib.redirect_stderr(io.StringIO()) as log, \
                    self.assertRaises(subprocess.CalledProcessError):
                consumer.git(Path("unused"), "fetch", "--no-tags", consumer.REPOSITORY_URL + ".git", "b" * 40)
            run.assert_called_once()
            sleep.assert_not_called()
            self.assertEqual(kind, json.loads(log.getvalue())["gitFetchFailure"])
            self.assertFalse(json.loads(log.getvalue())["retry"])
            self.assertNotIn("secret-value", log.getvalue())

    def test_local_git_failure_never_retries_or_emits_transport_diagnostics(self):
        for failure in (subprocess.CalledProcessError(128, ["git"], stderr=b"Connection reset by peer"),
                        subprocess.TimeoutExpired(["git"], 120)):
            with self.subTest(error=type(failure)), patch.object(consumer.subprocess, "run", side_effect=failure) as run, \
                    patch.object(consumer.time, "sleep") as sleep, contextlib.redirect_stderr(io.StringIO()) as log, \
                    self.assertRaises(type(failure)):
                consumer.git(Path("unused"), "rev-parse", "b" * 40 + "^{tree}")
            run.assert_called_once()
            sleep.assert_not_called()
            self.assertEqual("", log.getvalue())

    def test_history_rejects_wrong_tree_after_successful_fetch_retry(self):
        producer = {"repository": consumer.authority.REPOSITORY, "commit": "b" * 40, "tree": "c" * 40}
        missing = subprocess.CalledProcessError(128, ["git"], stderr=b"unknown revision")
        reset = subprocess.CalledProcessError(128, ["git"], stderr=b"Connection reset by peer")
        with patch.object(consumer.subprocess, "run", side_effect=[missing, reset,
                subprocess.CompletedProcess([], 0, stdout=b""), subprocess.CompletedProcess([], 0, stdout=b"wrong\n")]) as run, \
                patch.object(consumer.time, "sleep") as sleep, contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaisesRegex(ValueError, "Historical Git tree differs"):
            consumer.history(Path("unused"), producer)
        self.assertEqual(4, run.call_count)
        self.assertEqual(run.call_args_list[1], run.call_args_list[2])
        self.assertEqual("b" * 40 + "^{tree}", run.call_args.args[0][-1])
        sleep.assert_called_once_with(2)

    def test_snapshot_rejects_unapproved_code_and_preserves_product_head(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="approved-source-test-") as temporary:
            root, work = Path(temporary).resolve() / "product", Path(temporary).resolve() / "private"
            subprocess.run(["git", "clone", "--shared", "--quiet", str(source), str(root)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(root), "checkout", "--quiet", APPROVAL["activeVerifier"]], check=True, capture_output=True)
            work.mkdir()
            policy = root / "ci/product_reuse.py"
            old = policy.read_bytes(); policy.write_bytes(old + b"\n# genuine policy change\n")
            with self.assertRaisesRegex(ValueError, "verifier/policy differs"):
                consumer.snapshot(root, APPROVAL, work)
            policy.write_bytes(old)
            extra = root / ".github/unreviewed.py"; extra.write_text("# extra source")
            with self.assertRaisesRegex(ValueError, "inventory differs"):
                consumer.snapshot(root, APPROVAL, work)
            extra.unlink()
            overlay = root / next(iter(consumer.OVERLAY))
            old = overlay.read_bytes(); overlay.unlink(); overlay.symlink_to(policy)
            with self.assertRaisesRegex(ValueError, "symlink"):
                consumer.snapshot(root, APPROVAL, work)
            overlay.unlink(); overlay.write_bytes(old)
            before = consumer.git(root, "rev-parse", "HEAD")
            for name in consumer.OVERLAY:
                file = root / name; file.write_bytes(file.read_bytes() + b"\n# acquisition-only caller change\n")
            result = consumer.snapshot(root, APPROVAL, work)
            self.assertEqual(result["productPhasesOwned"], 0)
            self.assertEqual(len(result["overlaidControlFiles"]), 7)
            self.assertEqual(consumer.git(root, "rev-parse", "HEAD"), before)
            self.assertEqual(consumer.git(root, "diff", "--name-only"), b"")
            self.assertTrue(all((work / "compiled-plumbing" / name).is_file() for name in consumer.OVERLAY))


if __name__ == "__main__": unittest.main()
