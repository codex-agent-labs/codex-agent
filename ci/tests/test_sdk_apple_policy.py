"""Caller-policy construction controls; existing plan/Git trust authority mocked.

Real canonical parsers, inventories and publication run. Synthetic tooling is
never executed, and this fixture makes no signature or source admission claim.
"""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci import sdk_apple_policy as policy
from products.inventory import canonical_json_bytes, regular_file_inventory, write_canonical_json
from products.sdk_apple_validation_admission import apple_validation_policy_arguments


class ApplePolicyTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="apple-policy-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.plan = self.root / "impact-plan.json"
        self.plan.write_bytes(b'{"synthetic":"exact original plan bytes"}\n')
        self.tooling = self.root / "tooling"
        self.tooling.mkdir()
        for name in ("evidence", "keys"):
            (self.tooling / name).mkdir()
            (self.tooling / name / "original.bin").write_bytes(b"opaque original\x00\xff")
        for name in ("public-key", "java", "keyring"):
            (self.tooling / name).write_bytes(b"caller-owned fixture; not executable\n")
        self.value = {"evidence": str(self.tooling / "evidence"), "publicKey": str(self.tooling / "public-key"),
                      "javaExecutable": str(self.tooling / "java"), "requiredTrustDomain": "release",
                      "keyring": str(self.tooling / "keyring"), "keysDirectory": str(self.tooling / "keys")}
        self.tooling_policy = self.root / "tooling-policy.json"
        write_canonical_json(self.tooling_policy, self.value)
        self.destination = self.root / "apple-policy"
        self.commit, self.tree = "a" * 40, "b" * 40
        self.environment = {}
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.validate = self.enterContext(patch.object(policy.products, "_validate_plan", side_effect=self.validated))
        self.trust = self.enterContext(patch.object(policy.products, "_release_trust", side_effect=self.git_trust))
        self.git = self.enterContext(patch.object(policy.products, "_git_value", side_effect=lambda root, *args:
            self.commit if args[-1] == "HEAD^{commit}" else self.tree))

    def validated(self, path, repository):
        self.assertEqual(self.repository, repository)
        self.assertEqual(self.plan.read_bytes(), path.read_bytes())
        self.assertNotEqual(self.plan, path)
        return {"validationCommit": self.commit, "validationTree": self.tree}

    def git_trust(self, repository, revision, destination):
        self.assertEqual(self.repository, repository)
        self.assertEqual(self.commit, revision)
        trust = destination / "trust"
        (trust / "keys").mkdir(parents=True)
        (trust / "product-signing-keys.json").write_bytes(b"current Git-owned ring fixture\n")
        for name in ("active", "retired"):
            (trust / "keys" / f"{name}.pub").write_bytes(name.encode())
        return SimpleNamespace(keyring=trust / "product-signing-keys.json", keys=trust / "keys")

    def call(self):
        return policy.create_apple_validation_policy(self.plan, self.tooling_policy, self.destination,
            repository_root=self.repository, environ=self.environment)

    def test_exact_release_schema_final_paths_and_originals_preserved_without_execution(self):
        original = regular_file_inventory(self.tooling)
        plan_bytes, tooling_bytes = self.plan.read_bytes(), self.tooling_policy.read_bytes()
        with patch("subprocess.run", side_effect=AssertionError("policy construction must not execute tooling")), \
                patch.object(policy, "caller_apple_validation_policy", wraps=policy.caller_apple_validation_policy) as mapping:
            result = self.call()
        mapping.assert_called_once_with(self.plan, self.value,
            keyring=self.destination / "trust/product-signing-keys.json",
            keys_directory=self.destination / "trust/keys", environ=self.environment)
        self.assertEqual({"plan": str(self.plan), "attestationPublicKey": None, "attestationTrustDomain": "release",
            "keyring": str(self.destination / "trust/product-signing-keys.json"),
            "keysDirectory": str(self.destination / "trust/keys"),
            "toolingEvidence": self.value["evidence"], "toolingPublicKey": self.value["publicKey"],
            "javaExecutable": self.value["javaExecutable"], "toolingTrustDomain": "release",
            "toolingKeyring": self.value["keyring"], "toolingKeysDirectory": self.value["keysDirectory"]}, result)
        self.assertEqual(canonical_json_bytes(result), (self.destination / policy.POLICY_NAME).read_bytes())
        self.assertEqual({"trust", policy.POLICY_NAME}, {path.name for path in self.destination.iterdir()})
        self.assertEqual({"active.pub", "retired.pub"}, {path.name for path in (self.destination / "trust/keys").iterdir()})
        self.assertIsNone(apple_validation_policy_arguments(result)["attestation_public_key"])
        self.assertEqual(original, regular_file_inventory(self.tooling))
        self.assertEqual(plan_bytes, self.plan.read_bytes())
        self.assertEqual(tooling_bytes, self.tooling_policy.read_bytes())
        self.validate.assert_called_once()
        self.trust.assert_called_once()
        before = regular_file_inventory(self.destination)
        with self.assertRaisesRegex(ValueError, "must not exist"):
            self.call()
        self.assertEqual(before, regular_file_inventory(self.destination))

    def test_pure_mapping_uses_explicit_paths_without_io_and_detaches_caller_dictionary(self):
        tooling = dict(self.value)
        with patch("builtins.open", side_effect=AssertionError("mapping must not read or write")), \
                patch.object(policy, "read_regular_file_bytes", side_effect=AssertionError("mapping must not read")), \
                patch.object(policy, "regular_file_inventory", side_effect=AssertionError("mapping must not inventory")), \
                patch("subprocess.run", side_effect=AssertionError("mapping must not execute")):
            result = policy.caller_apple_validation_policy("/absent/original-plan.json", tooling,
                keyring=Path("/absent/current-policy.json"), keys_directory=Path("/absent/current-keys"), environ={})
        self.validate.assert_not_called()
        self.trust.assert_not_called()
        self.git.assert_not_called()
        arguments = apple_validation_policy_arguments(result)
        self.assertEqual(Path("/absent/original-plan.json"), arguments["plan"])
        self.assertEqual(Path("/absent/current-policy.json"), arguments["keyring"])
        self.assertEqual(Path("/absent/current-keys"), arguments["keys_directory"])
        self.assertIsNone(arguments["attestation_public_key"])
        self.assertEqual("release", arguments["attestation_trust_domain"])
        self.assertEqual("release", arguments["required_trust_domain"])
        self.assertEqual(self.value["evidence"], result["toolingEvidence"])
        original_result = canonical_json_bytes(result)
        tooling.update(evidence="/changed/caller/evidence", extra={"untrusted": "state"})
        self.assertEqual(original_result, canonical_json_bytes(result))
        result["toolingEvidence"] = "/changed/result"
        self.assertEqual("/changed/caller/evidence", tooling["evidence"])

    def test_pure_mapping_rejects_nonrelease_wrong_shape_paths_and_any_signing_secret(self):
        arguments = {"plan_path": self.plan, "tooling": self.value,
                     "keyring": self.root / "current-policy.json", "keys_directory": self.root / "current-keys",
                     "environ": self.environment}
        invalid = [None, [], {**self.value, "extra": "retained authority"},
                   {name: value for name, value in self.value.items() if name != "keyring"},
                   {**self.value, "requiredTrustDomain": "development"}]
        invalid += [{**self.value, name: value} for name in self.value if name != "requiredTrustDomain"
                    for value in (None, "relative", 1)]
        for value in invalid:
            with self.subTest(tooling=value), self.assertRaises(ValueError):
                policy.caller_apple_validation_policy(**{**arguments, "tooling": value})
        for name in ("plan_path", "keyring", "keys_directory"):
            with self.subTest(path=name), self.assertRaises(ValueError):
                policy.caller_apple_validation_policy(**{**arguments, name: Path("relative")})
        for live in (False, True):
            selected = os.environ if live else self.environment
            selected["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"] = ""
            try:
                with self.subTest(live=live), patch.object(policy, "require_exact_keys") as parse, \
                        self.assertRaisesRegex(ValueError, "signing-secret context"):
                    policy.caller_apple_validation_policy(**arguments)
                parse.assert_not_called()
            finally:
                del selected["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"]

    def test_malformed_nonrelease_null_relative_and_noncanonical_tooling_fail_before_git(self):
        mutations = [lambda value: value.update(extra="state-selected policy"), lambda value: value.pop("keyring"),
                     lambda value: value.update(requiredTrustDomain="development")]
        mutations += [lambda value, name=name: value.update({name: None}) for name in self.value if name != "requiredTrustDomain"]
        mutations += [lambda value, name=name: value.update({name: "relative"}) for name in self.value if name != "requiredTrustDomain"]
        for index, mutate in enumerate(mutations):
            value = dict(self.value)
            mutate(value)
            write_canonical_json(self.tooling_policy, value)
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.call()
        self.tooling_policy.write_bytes(json.dumps(self.value, indent=2).encode())
        with self.assertRaises(ValueError):
            self.call()
        self.validate.assert_not_called()
        self.trust.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_missing_git_authority_and_noncurrent_plan_never_publish(self):
        self.validate.side_effect = ValueError("Checkout commit does not match the impact plan")
        with self.assertRaisesRegex(ValueError, "Checkout commit"):
            self.call()
        self.trust.assert_not_called()
        self.validate.side_effect = self.validated
        self.trust.side_effect = None
        self.trust.return_value = None
        with self.assertRaisesRegex(ValueError, "Git-owned release keys"):
            self.call()
        self.assertFalse(self.destination.exists())

    def test_secret_presence_in_supplied_or_live_environment_fails_before_reads(self):
        for live in (False, True):
            for value in ("", "opaque signing value"):
                selected = os.environ if live else self.environment
                selected["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"] = value
                try:
                    with self.subTest(live=live, empty=not value), patch.object(policy, "read_regular_file_bytes") as read, \
                            self.assertRaisesRegex(ValueError, "signing-secret context"):
                        self.call()
                    read.assert_not_called()
                finally:
                    del selected["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"]
        self.validate.assert_not_called()

    def test_overlap_symlink_and_occupied_outputs_fail_without_replacing_inputs(self):
        alias = self.root / "alias"
        alias.symlink_to(self.tooling, target_is_directory=True)
        occupied = self.root / "occupied"
        occupied.mkdir()
        (occupied / "sentinel").write_bytes(b"keep")
        before = regular_file_inventory(self.tooling)
        for destination in (self.repository / "output", self.plan, self.tooling / "evidence/output", alias / "output", occupied):
            self.destination = destination
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                self.call()
        self.validate.assert_not_called()
        self.assertEqual(before, regular_file_inventory(self.tooling))
        self.assertEqual(b"keep", (occupied / "sentinel").read_bytes())

    def test_distinct_sibling_output_preserves_all_declared_tooling_inputs(self):
        before = regular_file_inventory(self.tooling)
        plan_bytes, tooling_bytes = self.plan.read_bytes(), self.tooling_policy.read_bytes()
        self.destination = self.tooling / "output"
        result = self.call()
        self.assertEqual(canonical_json_bytes(result), (self.destination / policy.POLICY_NAME).read_bytes())
        self.assertEqual(str(self.destination / "trust/product-signing-keys.json"), result["keyring"])
        self.assertEqual(before, [record for record in regular_file_inventory(self.tooling)
                                  if not record["relativePath"].startswith("output/")])
        self.assertEqual(plan_bytes, self.plan.read_bytes())
        self.assertEqual(tooling_bytes, self.tooling_policy.read_bytes())

    def test_late_original_snapshot_head_and_secret_mutations_fail_before_publication(self):
        write = policy.write_canonical_json
        paths = (self.plan, self.tooling_policy, self.tooling / "evidence/original.bin", self.tooling / "public-key")
        original = {path: path.read_bytes() for path in paths}
        for selected in (*paths, "trust", "head", "secret"):
            for path, raw in original.items(): path.write_bytes(raw)
            self.git.side_effect = lambda root, *args: self.commit if args[-1] == "HEAD^{commit}" else self.tree
            self.environment.clear()
            def mutate(path, value):
                write(path, value)
                if isinstance(selected, Path): selected.write_bytes(b"late mutation")
                elif selected == "trust": (path.parent / "trust/keys/retired.pub").write_bytes(b"changed key")
                elif selected == "head": self.git.side_effect = lambda *args: "c" * 40
                else: self.environment["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"] = ""
            with self.subTest(selected=selected), patch.object(policy, "write_canonical_json", side_effect=mutate), \
                    self.assertRaises(ValueError):
                self.call()
            self.assertFalse(self.destination.exists())

    def test_cli_strict_forwarding_output_and_errors(self):
        argv = ["--plan", str(self.plan), "--tooling-policy", str(self.tooling_policy),
                "--destination", str(self.destination), "--repository-root", str(self.repository)]
        with patch.object(policy, "create_apple_validation_policy") as create, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, policy.main(argv))
        create.assert_called_once_with(self.plan, self.tooling_policy, self.destination,
                                       repository_root=self.repository, environ=os.environ)
        self.assertEqual({"policy_path": str(self.destination / policy.POLICY_NAME)}, json.loads(output.getvalue()))
        for extra in (("--command", "anything"), ("--tooling-pol", str(self.tooling_policy)), ("--keyring", "retained")):
            with patch.object(policy, "create_apple_validation_policy") as create, redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as error:
                policy.main([*argv, *extra])
            self.assertEqual(2, error.exception.code)
            create.assert_not_called()
        with patch.object(policy, "create_apple_validation_policy", side_effect=ValueError("rejected")), \
                redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            policy.main(argv)
        self.assertEqual(2, error.exception.code)


if __name__ == "__main__":
    unittest.main()
