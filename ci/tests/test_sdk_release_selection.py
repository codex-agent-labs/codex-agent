"""Real synthetic Git policy checks, not Runtime authentication or host evidence."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from ci.products.inventory import canonical_json_bytes
from ci.products.registry import PhaseInstanceId
from ci.products.sdk_release_selection import (
    read_sdk_release_selection, require_sdk_release_selection,
    read_sdk_runtime_compatibility_policy, require_sdk_runtime_compatibility_policy,
    sdk_runtime_source, require_sdk_contract_version,
)


class SdkReleaseSelectionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-release-selection-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.sdk = self.root / "gradle/release/versions/sdk.txt"
        self.default = self.root / "gradle/release/sdk-default-runtime.txt"
        self.sdk.parent.mkdir(parents=True)
        self.sdk.write_bytes(b"0.3.0-rc.1\n")
        self.default.write_bytes(b"0.2.0\n")
        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic SDK Policy")
        self.git("config", "user.email", "sdk-policy@example.invalid")
        self.revision = self.commit()

    def git(self, *arguments):
        return subprocess.run(["git", *arguments], cwd=self.root, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "synthetic policy")
        return self.git("rev-parse", "HEAD")

    def test_exact_original_selection_ignores_checkout_and_unrelated_runtime_version(self):
        self.sdk.write_bytes(b"9.0.0\n")
        self.default.write_bytes(b"9.1.0\n")
        (self.sdk.parent / "runtime.txt").write_bytes(b"99.0.0\n")
        expected = {"sdkVersion": "0.3.0-rc.1", "defaultRuntimeVersion": "0.2.0"}
        self.assertEqual(expected, require_sdk_release_selection(self.root, self.revision,
                         sdk_version="0.3.0-rc.1", runtime_version="0.2.0"))
        self.assertEqual(b"9.0.0\n", self.sdk.read_bytes())
        self.assertEqual(b"9.1.0\n", self.default.read_bytes())
        later = self.commit()
        self.assertEqual(expected, read_sdk_release_selection(self.root, self.revision))
        self.assertEqual({"sdkVersion": "9.0.0", "defaultRuntimeVersion": "9.1.0"},
                         read_sdk_release_selection(self.root, later))

    def test_mismatched_sdk_or_authenticated_runtime_is_rejected(self):
        for sdk, runtime in (("0.3.0", "0.2.0"), ("0.3.0-rc.1", "0.2.1"),
                             (None, "0.2.0"), ("0.3.0-rc.1", "0.2.0+build")):
            with self.subTest(sdk=sdk, runtime=runtime), self.assertRaises(ValueError):
                require_sdk_release_selection(self.root, self.revision, sdk_version=sdk, runtime_version=runtime)

    def test_only_exact_revisions_are_accepted(self):
        for revision in (None, "HEAD", self.revision[:12], self.revision.upper(), self.revision + "^{tree}"):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                read_sdk_release_selection(self.root, revision)

    def test_each_authority_rejects_malformed_bytes(self):
        invalid = (b"", b"0.2.0", b"0.2.0\r\n", b"0.2.0\n\n", b" 0.2.0\n",
                   b"0.2.0 \n", b"0.2.0+build\n", b"00.2.0\n", b"\xff\n", b"0.2.0\x00\n", b"1" * 257 + b"\n")
        for path in (self.sdk, self.default):
            for raw in invalid:
                with self.subTest(path=path.name, raw=raw):
                    self.sdk.write_bytes(b"0.3.0-rc.1\n")
                    self.default.write_bytes(b"0.2.0\n")
                    path.write_bytes(raw)
                    revision = self.commit()
                    with self.assertRaises(ValueError):
                        read_sdk_release_selection(self.root, revision)

    def test_default_requires_stable_release_but_sdk_may_be_prerelease(self):
        self.default.write_bytes(b"0.2.0-rc.1\n")
        revision = self.commit()
        with self.assertRaisesRegex(ValueError, "stable release"):
            read_sdk_release_selection(self.root, revision)

    def test_missing_and_symbolic_git_authorities_are_rejected(self):
        for path in (self.sdk, self.default):
            relative = path.relative_to(self.root).as_posix()
            self.git("read-tree", self.revision)
            self.git("update-index", "--force-remove", relative)
            tree = self.git("write-tree")
            with self.subTest(path=relative, mode="missing"), self.assertRaisesRegex(ValueError, "absent"):
                read_sdk_release_selection(self.root, tree)
            self.git("read-tree", self.revision)
            blob = self.git("rev-parse", f"{self.revision}:{relative}")
            self.git("update-index", "--cacheinfo", "120000", blob, relative)
            tree = self.git("write-tree")
            with self.subTest(path=relative, mode="symbolic"), self.assertRaisesRegex(ValueError, "not a regular"):
                read_sdk_release_selection(self.root, tree)

    def range_policy(self, default="0.8.0", **changes):
        policy = {"compatibleReleaseRange": ">=0.8.0 <0.9.0",
                  "compatibleRuntimeCompatibilityRange": ">=0.8.0 <0.9.0", **changes}
        self.default.write_text(default + "\n", encoding="ascii")
        path = self.root / "gradle/release/sdk-runtime-compatibility.json"
        path.write_bytes(canonical_json_bytes(policy))
        return path, policy, self.commit()

    def test_original_range_policy_accepts_stable_patch_defaults_and_ignores_checkout(self):
        for default in ("0.8.0", "0.8.1"):
            path, policy, revision = self.range_policy(default)
            path.write_bytes(b"mutable checkout is not policy\n")
            self.default.write_bytes(b"0.9.0\n")
            with self.subTest(default=default):
                self.assertEqual(policy, require_sdk_runtime_compatibility_policy(self.root, revision,
                    compatible_release_range=policy["compatibleReleaseRange"],
                    compatible_runtime_compatibility_range=policy["compatibleRuntimeCompatibilityRange"]))

    def test_default_and_derived_compatibility_must_be_inside_original_ranges(self):
        for default, changes in (("0.9.0", {}), ("0.8.0-rc.1", {}),
                ("0.8.1", {"compatibleRuntimeCompatibilityRange": ">=0.8.1 <0.9.0"}),
                ("0.8.1", {"compatibleRuntimeCompatibilityRange": ">=0.8.0 <0.8.1"})):
            _, _, revision = self.range_policy(default, **changes)
            with self.subTest(default=default, changes=changes), self.assertRaises(ValueError):
                read_sdk_runtime_compatibility_policy(self.root, revision)

    def test_ranges_cannot_be_overridden_by_the_caller(self):
        _, policy, revision = self.range_policy()
        for release, compatibility in ((">=0.8.0 <1.0.0", policy["compatibleRuntimeCompatibilityRange"]),
                (policy["compatibleReleaseRange"], ">=0.8.0 <1.0.0"), (None, None)):
            with self.subTest(release=release, compatibility=compatibility), self.assertRaisesRegex(ValueError, "differ"):
                require_sdk_runtime_compatibility_policy(self.root, revision,
                    compatible_release_range=release, compatible_runtime_compatibility_range=compatibility)

    def test_range_policy_requires_exact_canonical_fields_and_range_grammar(self):
        path, policy, _ = self.range_policy()
        invalid = [b"{}\n", canonical_json_bytes({**policy, "extra": True}),
                   canonical_json_bytes(policy) + b"\n", b'{"compatibleReleaseRange":"x","compatibleReleaseRange":"y"}\n']
        for field in policy:
            for value in (None, ">=0.8.0 <0.8.0", ">=0.9.0 <0.8.0", ">=0.8.0  <0.9.0",
                          ">=0.8.0-rc.1 <0.9.0", "^0.8.0", ">=00.8.0 <0.9.0"):
                invalid.append(canonical_json_bytes({**policy, field: value}))
        for raw in invalid:
            path.write_bytes(raw)
            revision = self.commit()
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                read_sdk_runtime_compatibility_policy(self.root, revision)

    def test_range_policy_missing_symbolic_or_nonexact_revision_fails_without_fallback(self):
        with self.assertRaisesRegex(ValueError, "absent"):
            read_sdk_runtime_compatibility_policy(self.root, self.revision)
        path, _, revision = self.range_policy()
        for value in ("HEAD", revision[:12], None):
            with self.subTest(revision=value), self.assertRaisesRegex(ValueError, "exact Git revision"):
                read_sdk_runtime_compatibility_policy(self.root, value)
        relative = path.relative_to(self.root).as_posix()
        blob = self.git("rev-parse", f"{revision}:{relative}")
        self.git("update-index", "--cacheinfo", "120000", blob, relative)
        with self.assertRaisesRegex(ValueError, "not a regular"):
            read_sdk_runtime_compatibility_policy(self.root, self.git("write-tree"))

    def test_source_route_uses_original_default_not_current_runtime_or_dirty_policy(self):
        path, _, revision = self.range_policy("0.8.0")
        self.sdk.write_bytes(b"9.0.0\n")
        self.default.write_bytes(b"0.8.1\n")
        path.write_bytes(b"not authoritative checkout policy\n")
        (self.sdk.parent / "runtime.txt").write_bytes(b"99.0.0\n")
        for instance in (PhaseInstanceId("sdk", "sdk-core", "package", "common"),
                         PhaseInstanceId("sdk", "python", "package", "desktop"),
                         PhaseInstanceId("sdk", "python", "validation", "linux-x64")):
            for current, expected in (("0.8.0", None), ("0.8.1", "released-default")):
                with self.subTest(instance=instance, current=current):
                    self.assertEqual(expected, sdk_runtime_source(self.root, revision, instances=(instance,),
                        runtime_version=current, sdk_version="0.3.0-rc.1"))
        self.assertEqual(b"not authoritative checkout policy\n", path.read_bytes())

    def test_source_route_nonconsuming_closure_needs_no_sdk_policy(self):
        for instances in ((), (PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate"),),
                (PhaseInstanceId("contract", "contract", "binary", "common"),
                 PhaseInstanceId("sdk", "sdk-core", "binary", "common"))):
            with self.subTest(instances=instances):
                self.assertIsNone(sdk_runtime_source(self.root / "absent", "not-a-revision", instances=instances,
                                                    runtime_version=None, sdk_version=None))

    def test_source_route_consumers_require_valid_exact_policy_and_versions(self):
        instances = (PhaseInstanceId("sdk", "python", "package", "desktop"),)
        def route(revision, **changes):
            return sdk_runtime_source(self.root, revision, instances=instances,
                **{"runtime_version": "0.8.1", "sdk_version": "0.3.0-rc.1", **changes})
        with self.assertRaisesRegex(ValueError, "absent"):
            route(self.revision)
        path, _, revision = self.range_policy()
        with self.assertRaisesRegex(ValueError, "original SDK release selection"):
            route(revision, sdk_version="0.3.0")
        for current in (None, "latest", "00.8.1", "0.8.1+build"):
            with self.subTest(current=current), self.assertRaisesRegex(ValueError, "SemVer"):
                route(revision, runtime_version=current)
        with self.assertRaisesRegex(ValueError, "exact Git revision"):
            route("HEAD")
        path.write_bytes(b"{}\n")
        with self.assertRaises(ValueError):
            route(self.commit())
        _, _, outside = self.range_policy("0.9.0")
        with self.assertRaisesRegex(ValueError, "outside"):
            route(outside)

    def test_contract_version_check_reads_exact_original_not_dirty_checkout(self):
        contract = self.sdk.parent / "contract.txt"
        contract.write_bytes(b"0.8.0\n")
        revision = self.commit()
        contract.write_bytes(b"0.8.1\n")
        self.assertEqual("0.8.0", require_sdk_contract_version(self.root, revision, contract_version="0.8.0"))
        with self.assertRaisesRegex(ValueError, "original SDK Contract version"):
            require_sdk_contract_version(self.root, revision, contract_version="0.8.1")
        self.assertEqual(b"0.8.1\n", contract.read_bytes())
        later = self.commit()
        self.assertEqual("0.8.1", require_sdk_contract_version(self.root, later, contract_version="0.8.1"))
        # The existing SDK/default public schema has not gained another required authority.
        self.assertEqual({"sdkVersion": "0.3.0-rc.1", "defaultRuntimeVersion": "0.2.0"},
                         read_sdk_release_selection(self.root, self.revision))

    def test_contract_version_check_rejects_missing_symbolic_and_malformed_authority(self):
        with self.assertRaisesRegex(ValueError, "absent"):
            require_sdk_contract_version(self.root, self.revision, contract_version="0.8.0")
        contract = self.sdk.parent / "contract.txt"
        for raw in (b"0.8.0", b"0.8.0\r\n", b"0.8.0\n\n", b" 0.8.0\n", b"0.8.0+build\n", b"\xff\n"):
            contract.write_bytes(raw)
            revision = self.commit()
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                require_sdk_contract_version(self.root, revision, contract_version="0.8.0")
        contract.write_bytes(b"0.8.0\n")
        revision = self.commit()
        for value in (None, "0.8", "0.8.0+build"):
            with self.subTest(version=value), self.assertRaisesRegex(ValueError, "SemVer"):
                require_sdk_contract_version(self.root, revision, contract_version=value)
        with self.assertRaisesRegex(ValueError, "exact Git revision"):
            require_sdk_contract_version(self.root, "HEAD", contract_version="0.8.0")
        relative = contract.relative_to(self.root).as_posix()
        blob = self.git("rev-parse", f"{revision}:{relative}")
        self.git("update-index", "--cacheinfo", "120000", blob, relative)
        with self.assertRaisesRegex(ValueError, "not a regular"):
            require_sdk_contract_version(self.root, self.git("write-tree"), contract_version="0.8.0")


if __name__ == "__main__":
    unittest.main()
