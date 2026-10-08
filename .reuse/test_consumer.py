import copy
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
            environment = {**os.environ, "GITHUB_OUTPUT": str(output), "REUSE_AUTHORITY_READ_TOKEN": "test-only"}
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
        block = action.split("    - name: Fresh original native admission under the approved verifier", 1)[1]
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
