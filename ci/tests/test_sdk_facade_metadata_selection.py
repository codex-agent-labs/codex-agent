"""Real signed catalogs/object lookup; original compiler replay/Git mocked.

Ephemeral keys authenticate only these fixture catalogs, not hosted execution
or missing compiler-byte policy. The concrete metadata adapter remains real.
"""

from dataclasses import replace
from copy import deepcopy
from contextlib import redirect_stderr
import io
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

from ci import sdk_facade_metadata_selection as selection
from ci.tests import test_sdk_facade_metadata_policy as fixtures
from products.index import IndexEntrySource, build_product_index
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object, object_relative_path
from products.signatures import generate_development_key, sign_manifest
import sdk_facade_metadata_policy as writer


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class FacadeMetadataSelectionTest(unittest.TestCase):
    def setUp(self):
        real_run = subprocess.run
        self.f = fixtures.FacadeMetadataPolicyTest(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        fixture_run = subprocess.run

        def run(command, *args, **kwargs):
            # The inherited workflow mocks subprocess globally. Only fixture
            # SSH key/signature operations may escape that compiler boundary.
            invoke = real_run if command[0] == "ssh-keygen" else fixture_run
            return invoke(command, *args, **kwargs)

        self.enterContext(patch.object(subprocess, "run", side_effect=run))
        self.a = self.f.f
        self.output = self.f.output
        self.root = self.a.root
        self.enterContext(patch.object(selection, "_request_inventory",
            side_effect=lambda path: {path: writer.sha256_file(path)}))
        self.enterContext(patch.object(writer, "_request_inventory",
            side_effect=lambda path: {path: writer.sha256_file(path)}))
        original = self.a.envelope["receipt"]["producer"]
        self.f.plan_check.return_value.update(repository=original["repository"], pullRequest=original["pullRequest"],
            remoteBuildAuthorized=True, event="pull_request")
        # Rebuild validation fixtures as PR originals through the actual shard
        # writer. Producer fields do not alter their phase key or outputs, so
        # metadata's existing deterministic upstream lineage stays unchanged.
        predecessors = []
        for envelope in self.a.predecessors:
            receipt = deepcopy(envelope["receipt"])
            target = receipt["target"]
            capture = self.root / ("pr-validation-" + target)
            shard = finalize_phase_object(stage_root=self.a.f.f.f.f.stages[target],
                phase_plan={key: receipt[key] for key in PHASE_PLAN_KEYS}, producer=deepcopy(original),
                product_version=receipt["productVersion"], trust_domain="development",
                destination=capture / "original/shard")
            self.assertEqual(receipt["buildKey"], shard["receipt"]["buildKey"])
            self.assertEqual(receipt["outputs"], shard["receipt"]["outputs"])
            selected_receipt = capture / "selected-receipt.json"
            selected_receipt.write_bytes(shard["receiptBytes"])
            self.a.policy["validations"][target].update(validationReceipt=str(selected_receipt), captureRoot=str(capture))
            predecessors.append({key: shard[key] for key in ("receipt", "receiptBytes", "receiptSha256", "objectSha256")})
        self.a.predecessors = predecessors
        catalog_root = self.root / "independent-signed-catalogs"
        private, public, signing = generate_development_key(catalog_root / "key")
        sources, objects = [], {}
        for envelope in (self.a.envelope, *self.a.predecessors):
            receipt = envelope["receipt"]
            target = receipt["target"]
            sources.append(IndexEntrySource(envelope["receiptBytes"], receipt["outputs"][0]["relativePath"]))
            capture = self.a.f.retained if target == "common" else Path(self.a.policy["validations"][target]["captureRoot"])
            archive = capture / "original/shard" / object_relative_path(receipt["buildKey"], envelope["receiptSha256"])
            objects[receipt["buildKey"]] = archive
        index = build_product_index(sources, repository=original["repository"], context={"kind": "pull-request",
            **{name: original[name] for name in ("pullRequest", "commit", "tree", "runId", "runAttempt")}},
            trust_domain="development", signing=signing, producer=original, stable_history=None)
        manifest = catalog_root / "index.json"
        manifest.write_bytes(selection.canonical_json_bytes(index))
        signature = sign_manifest(manifest, private, signing)
        self.catalog = selection.RemoteCatalog(manifest, signature, objects, public_key=public)

    def call(self, **changes):
        arguments = dict(catalog=self.catalog, catalog_source="same-pr", metadata_receipt_path=self.a.f.receipt_path,
            evidence_root=self.root, records=self.a.records, policy=self.a.policy, repository_root=self.root)
        arguments.update(changes)
        return selection.write_selected_facade_metadata_policy(self.f.plan, self.output, **arguments)

    def cli(self):
        external = self.output.parent
        descriptor = external / "catalog.json"
        records = external / "records.json"
        policy = external / "policy.json"
        public = external / "caller-pinned.pub"
        shutil.copyfile(self.catalog.public_key, public)
        relative = lambda path: Path(path).relative_to(self.root).as_posix()
        descriptor.write_bytes(selection.canonical_json_bytes({
            "manifest": relative(self.catalog.manifest), "signature": relative(self.catalog.signature),
            "publicKey": None, "keyring": None, "keysDirectory": None,
            "contractAttestation": None, "contractAttestationSignature": None,
            "contractPublicKey": None,
            "objects": [{"buildKey": key, "objectPath": relative(path)}
                        for key, path in sorted(self.catalog.objects.items())],
        }))
        records.write_bytes(selection.canonical_json_bytes(self.a.records))
        policy.write_bytes(selection.canonical_json_bytes(self.a.policy))
        argv = ["--plan", str(self.f.plan), "--destination", str(self.output),
                "--catalog", str(descriptor), "--catalog-root", str(self.root),
                "--catalog-source", "same-pr", "--public-key", str(public),
                "--metadata-receipt", str(self.a.f.receipt_path), "--evidence-root", str(self.root),
                "--records", str(records), "--policy", str(policy), "--repository-root", str(self.root)]
        return argv, descriptor, policy

    def test_cli_replays_signed_catalog_with_independent_caller_controls(self):
        argv, _, _ = self.cli()
        self.assertEqual(0, selection.main(argv))
        self.assertEqual(["enter", "exit"], self.a.events)
        self.assertEqual(self.a.records, selection.load_canonical_json_bytes(self.output.read_bytes())["records"])

    def test_cli_rejects_carrier_supplied_key_and_policy(self):
        argv, descriptor, _ = self.cli()
        value = selection.load_canonical_json_bytes(descriptor.read_bytes())
        value["publicKey"] = self.catalog.public_key.relative_to(self.root).as_posix()
        descriptor.write_bytes(selection.canonical_json_bytes(value))
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
            selection.main(argv)
        self.assertEqual(2, failure.exception.code)
        self.assertEqual([], self.a.events)
        self.assertFalse(self.output.exists())
        descriptor.write_bytes(selection.canonical_json_bytes({**value, "publicKey": None}))
        index = argv.index("--policy") + 1
        argv[index] = str(self.root / "retained-policy.json")
        Path(argv[index]).write_bytes(selection.canonical_json_bytes(self.a.policy))
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
            selection.main(argv)
        self.assertEqual(2, failure.exception.code)
        self.assertEqual([], self.a.events)
        self.assertFalse(self.output.exists())

    def test_cli_rejects_late_caller_policy_mutation(self):
        argv, _, policy = self.cli()
        original = selection.write_selected_facade_metadata_policy

        def publish(*arguments, **kwargs):
            result = original(*arguments, **kwargs)
            policy.write_bytes(b"replaced after signed replay")
            return result

        with patch.object(selection, "write_selected_facade_metadata_policy", side_effect=publish), \
                redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
            selection.main(argv)
        self.assertEqual(2, failure.exception.code)
        self.assertEqual(["enter", "exit"], self.a.events)
        self.assertTrue(self.output.exists())

    def test_real_catalogs_select_all_originals_before_full_writer(self):
        raw = self.a.f.receipt_path.read_bytes()
        result = self.call()
        self.assertEqual(["enter", "exit"], self.a.events)
        self.assertEqual(selection.canonical_json_bytes(result), self.output.read_bytes())
        self.assertEqual(raw, self.a.f.receipt_path.read_bytes())
        self.assertNotEqual("c" * 40, self.a.envelope["receipt"]["producer"]["commit"])

    def test_missing_target_wrong_public_key_and_wrong_pr_reject_before_writer(self):
        policy = deepcopy(self.a.policy)
        del policy["validations"]["jvm"]
        with self.assertRaises(ValueError):
            self.call(policy=policy)
        _, wrong, _ = generate_development_key(self.root / "untrusted-catalog-key")
        with self.assertRaises(ValueError):
            self.call(catalog=replace(self.catalog, public_key=wrong))
        self.f.plan_check.return_value["pullRequest"] += 1
        with self.assertRaises(ValueError):
            self.call()
        self.assertEqual([], self.a.events)
        self.assertFalse(self.output.exists())

    def test_missing_object_and_substituted_original_never_fallback(self):
        key = next(value["receipt"]["buildKey"] for value in self.a.predecessors if value["receipt"]["target"] == "jvm")
        with self.assertRaisesRegex(ValueError, "absent or differs"):
            self.call(catalog=replace(self.catalog, objects={**self.catalog.objects, key: None}))
        with self.assertRaises(ValueError):
            self.call(catalog=replace(self.catalog, objects={**self.catalog.objects, key: self.a.f.receipt_path}))
        self.assertEqual([], self.a.events)
        self.assertFalse(self.output.exists())

    def test_catalog_mutation_at_final_publication_rejects_without_unsafe_rollback(self):
        real_link = selection.os.link

        def publish(source, destination, **kwargs):
            real_link(source, destination, **kwargs)
            if Path(destination) == self.output:
                self.assertEqual(["enter", "exit"], self.a.events)
                self.catalog.signature.write_bytes(b"changed after full replay")

        with patch.object(selection.os, "link", side_effect=publish), self.assertRaisesRegex(ValueError, "changed"):
            self.call()
        self.assertTrue(self.output.exists())
        self.assertEqual({"evidenceRoot", "records", "policy"},
                         set(selection.load_canonical_json_bytes(self.output.read_bytes())))

    def test_final_authority_check_cannot_accept_foreign_output_replacement(self):
        original_read = selection._read
        original_git = selection.product_reuse._git_value
        output_checked = False
        replaced = False

        def read(path):
            nonlocal output_checked
            raw = original_read(path)
            if Path(path) == self.output:
                output_checked = True
            return raw

        def git(*arguments):
            nonlocal replaced
            value = original_git(*arguments)
            # Replace only after the first published-byte check, during the
            # last authority check; all signed/original inputs stay unchanged.
            if output_checked and not replaced and arguments[-1] == "HEAD^{tree}":
                foreign = self.output.parent / "foreign-policy.json"
                foreign.write_bytes(b"independent caller replacement")
                foreign.replace(self.output)
                replaced = True
            return value

        with patch.object(selection, "_read", side_effect=read), \
                patch.object(selection.product_reuse, "_git_value", side_effect=git), \
                self.assertRaisesRegex(ValueError, "after final authority check"):
            self.call()
        self.assertTrue(replaced)
        self.assertEqual(b"independent caller replacement", self.output.read_bytes())

    def test_release_signed_catalog_does_not_upgrade_development_sdk_receipt(self):
        private, public, development = generate_development_key(self.root / "release-fixture-key")
        signing = {**development, "trustDomain": "release", "keyId": "release-test"}
        keys = self.root / "release-fixture-keys"
        keys.mkdir()
        (keys / "release-test.pub").write_bytes(public.read_bytes())
        keyring = self.root / "release-fixture-keyring.json"
        keyring.write_bytes(selection.canonical_json_bytes({"schemaVersion": 1,
            "namespace": signing["namespace"], "algorithm": signing["algorithm"], "trustDomain": "release",
            "activeKey": {"keyId": signing["keyId"], "fingerprint": signing["fingerprint"]}, "retiredKeys": []}))
        prior = self.catalog
        index = selection.load_canonical_json_bytes(prior.manifest.read_bytes())
        index["signing"], index["trustDomain"] = signing, "release"
        index["producer"].update(event="push", pullRequest=None)
        producer = index["producer"]
        index["context"] = {"kind": "promoted-main", "commit": producer["commit"], "tree": producer["tree"],
            "promotionRunId": producer["runId"], "promotionRunAttempt": producer["runAttempt"]}
        manifest = self.root / "promoted-fixture.json"
        manifest.write_bytes(selection.canonical_json_bytes(index))
        signature = sign_manifest(manifest, private, signing)
        catalog = selection.RemoteCatalog(manifest, signature, prior.objects, keyring=keyring, keys_directory=keys)
        with self.assertRaisesRegex(ValueError, "matching object or index entry is corrupt"):
            self.call(catalog=catalog, catalog_source="promoted-main")
        self.assertEqual([], self.a.events)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
