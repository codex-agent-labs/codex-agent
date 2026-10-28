"""Real concrete admission/shards; deep original replay and Git are mocked.

Fixtures do not establish hosted compilation, reviewed tool pins or signatures.
"""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_facade_metadata_policy as producer
from ci.tests import test_sdk_facade_metadata_admission as fixtures
import sdk_facade_metadata_original as original


class FacadeMetadataPolicyTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.FacadeMetadataAdmissionTest(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        temporary = self.enterContext(tempfile.TemporaryDirectory(prefix="core-caller-policy-"))
        self.output = Path(temporary).resolve() / "caller.json"
        self.plan = Path(self.f.policy["plan"])
        self.enterContext(patch.object(original, "verified_retained_sdk_facade_metadata", side_effect=self.f.replay))
        self.enterContext(patch.object(producer, "_request_inventory",
            side_effect=lambda path: {path: producer.sha256_file(path)}))
        self.plan_check = self.enterContext(patch.object(producer.product_reuse, "_validate_plan",
            return_value={"validationCommit": "c" * 40, "validationTree": "d" * 40}))
        self.enterContext(patch.object(producer.product_reuse, "_git_value",
            side_effect=lambda root, op, value: ("d" if value.endswith("{tree}") else "c") * 40))

    def call(self, **changes):
        arguments = dict(evidence_root=self.f.root, records=self.f.records, policy=self.f.policy,
            metadata_envelope=self.f.envelope, validation_envelopes=self.f.predecessors,
            repository_root=self.f.root)
        arguments.update(changes)
        return producer.write_facade_metadata_policy(self.plan, self.output, **arguments)

    def test_full_adapter_exits_before_fresh_external_canonical_publication(self):
        before = deepcopy(self.f.envelope)
        real_link = producer.os.link

        def publish(*args, **kwargs):
            self.assertEqual(["enter", "exit"], self.f.events)
            return real_link(*args, **kwargs)

        with patch.object(producer.os, "link", side_effect=publish):
            result = self.call()
        self.assertEqual({"evidenceRoot": str(self.f.root), "records": self.f.records,
                          "policy": self.f.policy}, result)
        self.assertEqual(producer.canonical_json_bytes(result), self.output.read_bytes())
        self.assertEqual(before, self.f.envelope)
        self.assertNotEqual("c" * 40, before["receipt"]["producer"]["commit"])
        self.plan_check.assert_called_once_with(self.plan, self.f.root)

    def test_original_reader_failure_and_exit_mutation_publish_nothing(self):
        baseline = deepcopy(self.f.policy)
        for mode in ("enter", "exit", "policy"):
            self.f.policy = deepcopy(baseline)

            def mutate(phase, value, arguments):
                if phase == mode:
                    raise ValueError("original replay rejected")
                if phase == "exit" and mode == "policy":
                    self.f.policy["originalContext"]["repositoryRoot"] = "/changed"

            self.f.mutation = mutate
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(self.output.exists())

    def test_wrong_selected_object_and_malformed_policy_fail_closed(self):
        selected = deepcopy(self.f.predecessors)
        selected[0]["objectSha256"] = "sha256:" + "e" * 64
        with self.assertRaisesRegex(ValueError, "predecessor object differs"):
            self.call(validation_envelopes=selected)
        policy = {**self.f.policy, "trusted": True}
        with self.assertRaises(ValueError):
            self.call(policy=policy)
        self.assertFalse(self.output.exists())
        self.assertEqual([], self.f.events)

    def test_fresh_external_output_and_non_symbolic_inputs_required(self):
        external = self.output
        for destination in (self.f.root / "build/caller-policy.json", self.f.f.retained / "caller.json"):
            self.output = destination
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(destination.exists())
        self.output = external
        self.output.write_bytes(b"owned by caller")
        with self.assertRaises(ValueError):
            self.call()
        self.assertEqual(b"owned by caller", self.output.read_bytes())
        link = self.output.parent / "linked"
        link.symlink_to(self.f.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            producer._digest(link / self.plan.relative_to(self.f.root))
        self.assertEqual([], self.f.events)

    def test_late_publication_failure_removes_only_own_inode(self):
        raw = self.plan.read_bytes()
        real_link = producer.os.link
        for replace in (False, True):
            self.plan.write_bytes(raw)

            def publish(source, destination, **kwargs):
                real_link(source, destination, **kwargs)
                if replace:
                    replacement = self.output.parent / "replacement"
                    replacement.write_bytes(b"independent replacement")
                    replacement.replace(destination)
                self.plan.write_bytes(b"changed after publication")

            with self.subTest(replace=replace), patch.object(producer.os, "link", side_effect=publish), \
                    self.assertRaises(ValueError):
                self.call()
            if replace:
                self.assertEqual(b"independent replacement", self.output.read_bytes())
            else:
                self.assertFalse(self.output.exists())

    def test_streaming_archive_guard_and_request_setup_mutation(self):
        archive = Path(next(row["nativeCompilerArchive"] for row in self.f.policy["validations"].values()
                            if "nativeCompilerArchive" in row))
        with archive.open("wb") as stream:
            for _ in range(17):
                stream.write(b"x" * (1024 * 1024))
        self.assertEqual(producer.sha256_file(archive), producer._digest(archive))
        request_path = Path(self.f.policy["validations"]["jvm"]["facadeRequest"])
        raw = request_path.read_bytes()
        real_sources = producer._sources

        def sources(request):
            result = real_sources(request)
            if request["target"] == "jvm":
                request_path.write_bytes(raw + b" ")
            return result

        with patch.object(producer, "_sources", side_effect=sources), self.assertRaises(ValueError):
            self.call()
        self.assertFalse(self.output.exists())

    def test_streaming_digest_rejects_parent_swap_during_open(self):
        with tempfile.TemporaryDirectory(prefix="core-digest-parent-") as temporary:
            root = Path(temporary).resolve()
            parent, backup, alternate = (root / name for name in ("source", "backup", "alternate"))
            parent.mkdir()
            alternate.mkdir()
            (parent / "archive.zip").write_bytes(b"original")
            (alternate / "archive.zip").write_bytes(b"substituted")
            real_hash = producer.sha256_file

            hash_opened = []

            def swap_during_hash(path, **kwargs):
                hash_opened.append(True)
                parent.rename(backup)
                parent.symlink_to(alternate, target_is_directory=True)
                try:
                    return real_hash(path, **kwargs)
                finally:
                    parent.unlink()
                    backup.rename(parent)

            with patch.object(producer, "sha256_file", side_effect=swap_during_hash), \
                    self.assertRaises(ValueError):
                producer._digest(parent / "archive.zip")
            self.assertEqual([True], hash_opened)
            self.assertEqual(b"original", (parent / "archive.zip").read_bytes())


if __name__ == "__main__":
    unittest.main()
