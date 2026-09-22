"""CLI construction checks; mocked adapters do not prove hosted admission."""

import argparse
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_metadata_policy as policy
import product_reuse
from products.inventory import canonical_json_bytes


class MetadataPolicyTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="metadata-policy-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(b'{}\n')
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        self.paths = {}
        self.descriptor = {"evidenceRoot": str(self.evidence), "records": [], "policy": {}}
        for name in policy._OPTIONS:
            path = self.root / (name + ".json")
            path.write_bytes(canonical_json_bytes(self.descriptor))
            self.paths[name] = path
        self.stack = self.enterContext(ExitStack())
        self.validate = self.stack.enter_context(patch.object(product_reuse, "_validate_plan",
            return_value={"validationCommit": "a" * 40}))
        self.adapters = [self.stack.enter_context(patch(target)) for target in (
            "products.sdk_facade_metadata_admission.FacadeMetadataAdmission",
            "products.sdk_android_metadata_admission.AndroidMetadataAdmission")]

    def args(self, **options):
        return argparse.Namespace(plan=self.plan, repository_root=self.root, **options)

    def test_omission_does_not_read_or_validate_anything(self):
        with policy.metadata_admission_options(argparse.Namespace()) as value:
            self.assertEqual({}, value)
        self.validate.assert_not_called()

    def test_independent_flags_bind_concrete_adapters_to_current_plan(self):
        for names in ((policy._OPTIONS[0],), (policy._OPTIONS[1],), policy._OPTIONS):
            for adapter in self.adapters:
                adapter.reset_mock()
            args = self.args(**{name: self.paths[name] for name in names})
            before = dict(vars(args))
            with policy.metadata_admission_options(args) as value:
                self.assertEqual({name.replace("_policy", "_admission") for name in names}, set(value))
                for name, adapter in zip(policy._OPTIONS, self.adapters):
                    if name not in names:
                        adapter.assert_not_called()
                        continue
                    self.assertIs(adapter.return_value, value[name.replace("_policy", "_admission")])
                    adapter.assert_called_once_with(str(self.evidence), [], repository=self.root,
                        policy_revision="a" * 40, policy={})
            self.assertEqual(before, vars(args))

    def test_dict_consumes_only_policy_switches(self):
        args = vars(self.args(**self.paths))
        with policy.metadata_admission_options(args):
            self.assertEqual({"plan": self.plan, "repository_root": self.root}, args)

    def test_collector_uses_exact_original_plan_location(self):
        original = self.root / "product-resume-inputs/plan/impact-plan.json"
        original.parent.mkdir(parents=True)
        original.write_bytes(self.plan.read_bytes())
        args = argparse.Namespace(input_root=self.root, repository_root=self.root, **self.paths)
        with policy.metadata_admission_options(args):
            self.validate.assert_called_once_with(original, self.root)

    def test_malformed_noncanonical_and_unknown_descriptor_fields_reject(self):
        for raw in (b'{', b'{}', b'[]\n', canonical_json_bytes({**self.descriptor, "repository": str(self.root)})):
            self.paths[policy._OPTIONS[0]].write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises((ValueError, TypeError)):
                with policy.metadata_admission_options(self.args(**self.paths)):
                    self.fail("Malformed policy reached execution")
        for adapter in self.adapters:
            adapter.assert_not_called()

    def test_policy_inside_evidence_and_symlinked_policy_reject(self):
        inside = self.evidence / "policy.json"
        inside.write_bytes(canonical_json_bytes(self.descriptor))
        symbolic = self.root / "symbolic.json"
        symbolic.symlink_to(self.paths[policy._OPTIONS[0]])
        outside = self.root / "outside"
        outside.mkdir()
        alias = outside / ".." / "evidence" / "policy.json"
        for path in (inside, symbolic, alias):
            with self.subTest(path=path), self.assertRaises((ValueError, OSError)):
                with policy.metadata_admission_options(self.args(**{policy._OPTIONS[0]: path})):
                    self.fail("Unsafe policy reached execution")

    def test_plan_and_descriptor_mutation_reject_on_context_exit(self):
        for path in (self.plan, self.paths[policy._OPTIONS[0]]):
            before = path.read_bytes()
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "changed during execution"):
                with policy.metadata_admission_options(self.args(**self.paths)):
                    path.write_bytes(b'{"changed":true}\n')
            path.write_bytes(before)

    def test_adapter_rejection_cannot_be_replaced_by_success(self):
        self.adapters[0].side_effect = ValueError("complete replay policy rejected")
        with self.assertRaisesRegex(ValueError, "complete replay policy rejected"):
            with policy.metadata_admission_options(self.args(**self.paths)):
                self.fail("Rejected policy reached execution")

    def test_parser_has_only_explicit_policy_paths(self):
        parser = argparse.ArgumentParser(allow_abbrev=False)
        policy.add_metadata_admission_arguments(parser)
        args = parser.parse_args(["--sdk-facade-metadata-policy", str(self.paths[policy._OPTIONS[0]])])
        self.assertEqual(self.paths[policy._OPTIONS[0]], args.sdk_facade_metadata_policy)
        self.assertIsNone(args.sdk_android_metadata_policy)


if __name__ == "__main__":
    unittest.main()
