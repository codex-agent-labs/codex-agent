"""Synthetic archives and Git blobs; real pin/parser checks, no native execution.

Fixture checksums stand in for caller-reviewed immutable Git policy; they are not
claimed as genuine Kotlin distributions, hosted observations or tool authority.
"""

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from ci.products import sdk_facade_native_policy as policy


class FacadeNativePolicyTest(unittest.TestCase):
    def test_v2_fingerprint_and_selection_are_bound_without_admitting_dependency_bytes(self):
        self.value = self.observation_v2()
        self.save()
        self.assertIsNone(self.call())
        original = deepcopy(self.value)
        for change in ("digest", "path", "host", "target", "missing", "extra"):
            self.value = deepcopy(original)
            selected = self.value["nativeSelection"]
            if change == "digest":
                selected["fingerprint"] = self.inventory({"konan/compiler.fingerprint": b"wrong fingerprint"})
            elif change == "path":
                selected["fingerprint"] = self.inventory({"other/compiler.fingerprint": b"not yet captured by Core"})
            elif change in {"host", "target"}:
                selected[change] = "linux_x64"
            elif change == "missing":
                del selected["fingerprint"]
            else:
                selected["unexpected"] = True
            self.save()
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.call()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.archive = self.root / "caller-preprovisioned.tar.gz"
        self.capture = self.root / "compiler-inputs.json"
        self.revision = "a" * 40
        self.version = "2.3.10"
        self.home = "/original/selected/kotlin-native"
        self.host = "macos-arm64"
        self.host_name = "macos_arm64"
        self.classifier = "macos-aarch64"
        self.target_name = "macos_arm64"
        self.prefix = "kotlin-native-prebuilt-macos-aarch64-" + self.version
        self.selected = {"konan/konan.properties": (
                            b"llvmHome.macos_arm64 = $llvm.macos_arm64.user\n"
                            b"llvm.macos_arm64.user = llvm-reviewed\n"
                            b"libffiDir.macos_arm64 = libffi-reviewed\n"
                            b"dependencies.macos_arm64 = lldb-reviewed\n"),
                         "konan/lib/kotlin-native-compiler-embeddable.jar": b"selected-compiler",
                         "konan/lib/empty-resource": b""}
        self.sources = {policy.VERSION_CATALOG: b'[versions]\nkotlin="2.3.10"\n'}
        self.write_archive()
        self.value = self.observation()
        self.save()
        self.git = self.enterContext(patch.object(policy, "run_git", side_effect=self.git_read))
        self.blobs = self.enterContext(patch.object(policy, "git_regular_blob_bytes", side_effect=self.blob))

    def git_read(self, root, command, argument):
        self.assertEqual((self.root, "rev-parse", self.revision + "^{commit}"), (root, command, argument))
        return self.revision + "\n"

    def blob(self, root, revision, name, *, max_bytes):
        self.assertEqual((self.root, self.revision, 4 * 1024 * 1024), (root, revision, max_bytes))
        return self.sources[name]

    def write_archive(self, extra=(), *, omitted=()):
        entries = [(self.prefix + "/" + name, data, tarfile.REGTYPE, "")
                   for name, data in self.selected.items() if name not in omitted]
        entries += [(self.prefix + "/konan/compiler.fingerprint", b"not yet captured by Core", tarfile.REGTYPE, ""),
                    (self.prefix + "/bin/konanc", b"not part of this partial byte comparison", tarfile.REGTYPE, "")]
        with tarfile.open(self.archive, "w:gz", format=tarfile.GNU_FORMAT) as archive:
            directory = tarfile.TarInfo(self.prefix + "/")
            directory.type = tarfile.DIRTYPE
            archive.addfile(directory)
            for name, data, kind, link in [*entries, *extra]:
                member = tarfile.TarInfo(name)
                member.type, member.linkname = kind, link
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        artifact = f"kotlin-native-prebuilt-{self.version}-{self.classifier}.tar.gz"
        self.sources[policy.RUNTIME_VERIFICATION_METADATA] = (
            f'<verification-metadata><components><component group="org.jetbrains.kotlin" '
            f'name="kotlin-native-prebuilt" version="{self.version}"><artifact name="{artifact}">'
            f'<sha256 value="{digest}"/></artifact></component></components></verification-metadata>').encode()

    def inventory(self, values, *, root=None):
        base = self.home if root is None else root
        parent = PureWindowsPath(base) if PureWindowsPath(base).drive else PurePosixPath(base)
        rows = [{"path": str(parent / name), "bytes": len(contents),
                 "sha256": hashlib.sha256(contents).hexdigest()} for name, contents in values.items()]
        rows.sort(key=lambda row: row["path"])
        encoded = "".join(f"{row['path']}\0{row['bytes']}\0{row['sha256']}\n" for row in rows).encode()
        return {"files": rows, "sha256": hashlib.sha256(encoded).hexdigest()}

    def observation(self, target="macos-arm64"):
        task = policy.FACADE_CONSUMER_TASKS[target]
        return {"schemaVersion": 1, "target": target, "task": task,
            "taskClass": "org.jetbrains.kotlin.gradle.tasks.KotlinNativeCompile", "family": "native",
            "kotlinVersion": self.version, "agpVersion": None,
            "javaExecutable": "/original/jdk/bin/java", "nativeHome": self.home,
            "arguments": ["-produce", "library"], "tools": {
                "native": self.inventory(self.selected),
                "compiler": self.inventory({name: data for name, data in self.selected.items()
                                             if name.endswith("kotlin-native-compiler-embeddable.jar")}),
                "implementation": {"intentionally": "not authenticated by this partial leaf"},
                "compilerPlugins": {"intentionally": "left to the full original gate"},
                "java": {"intentionally": "not a reviewed JDK pin"}, "android": None},
            "inputs": {"intentionally": "left to the full original gate"},
            "outcome": {"task": task, "didWork": True, "upToDate": False,
                        "skipped": False, "skipMessage": None, "failure": None}}

    def observation_v2(self, target="macos-arm64"):
        value = self.observation(target)
        value["schemaVersion"] = 2
        names = ["libffi-reviewed", "llvm-reviewed"]
        if target == "macos-arm64" or self.host != "macos-arm64":
            names.append("lldb-reviewed")
        data = "C:\\original\\konan" if self.host == "windows-x64" else "/original/konan"
        separator = "\\" if self.host == "windows-x64" else "/"
        directory = data + separator + "dependencies"
        value["nativeSelection"] = {
            "dataDirectory": data, "dependenciesDirectory": directory,
            "host": self.host_name, "target": self.target_name if target == "windows-x64" else target.replace("-", "_"),
            "fingerprint": self.inventory({"konan/compiler.fingerprint": b"not yet captured by Core"}),
            "dependencies": [{"name": name, "root": directory + separator + name,
                "inventory": self.inventory({"bin/tool": b"unreviewed dependency bytes"}, root=directory + separator + name),
                "symlinks": []} for name in sorted(names)],
        }
        return value

    def test_v2_exact_target_dependencies_come_from_the_same_pinned_archive(self):
        for target in ("macos-arm64", "ios-arm64", "ios-simulator-arm64"):
            self.value = self.observation_v2(target)
            self.save()
            before = self.capture.read_bytes(), self.archive.read_bytes()
            with self.subTest(target=target):
                self.assertIsNone(self.call())
                self.assertEqual(before, (self.capture.read_bytes(), self.archive.read_bytes()))
        # Changing dependency bytes consistently is NOT rejected as a pin
        # mismatch: this leaf authenticates names, not LLVM/libffi file bytes.
        record = self.value["nativeSelection"]["dependencies"][0]
        record["inventory"] = self.inventory({"bin/tool": b"different unreviewed content"}, root=record["root"])
        self.save()
        self.assertIsNone(self.call())

    def test_v2_dependency_names_roots_inventory_and_order_cannot_be_self_selected(self):
        for change in ("missing", "extra", "duplicate", "reordered", "root", "data", "directory", "escape", "shape"):
            self.value = self.observation_v2()
            selection = self.value["nativeSelection"]
            records = selection["dependencies"]
            if change == "missing": records.pop()
            elif change == "extra": records.append({**records[0], "name": "unselected-cache"})
            elif change == "duplicate": records.append(deepcopy(records[0]))
            elif change == "reordered": records.reverse()
            elif change == "root": records[0]["root"] = "/another/data/dependencies/libffi-reviewed"
            elif change == "data": selection["dataDirectory"] = "/unselected"
            elif change == "directory": selection["dependenciesDirectory"] = "/original/konan/../dependencies"
            elif change == "escape": records[0]["inventory"] = self.inventory({"bin/tool": b"outside"})
            else: records[0]["unknown"] = True
            self.save()
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.call()

    def test_v2_property_selection_is_not_inferred_from_installed_files_or_observation(self):
        self.value = self.observation_v2()
        self.save()
        # Replace the reviewed synthetic archive's LLVM selection and re-pin it,
        # then update observed property bytes too: the OLD dependency names must
        # still fail, even though observed and pinned property hashes agree.
        self.selected["konan/konan.properties"] = self.selected["konan/konan.properties"].replace(
            b"llvm-reviewed", b"different-reviewed-llvm")
        self.write_archive()
        self.value["tools"]["native"] = self.inventory(self.selected)
        self.save()
        with self.assertRaisesRegex(ValueError, "pinned property selection"):
            self.call()

    def test_v2_unsupported_or_malformed_property_selection_fails_closed(self):
        baseline = self.selected["konan/konan.properties"]
        for suffix in (b"dependencies = ignored-fallback\n", b"llvmHome.macos_arm64 = duplicate\n"):
            self.selected["konan/konan.properties"] = baseline + suffix
            self.write_archive()
            self.value = self.observation_v2()
            self.save()
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                self.call()
        for value in (b"/outside/custom-llvm", b"$llvm.macos_arm64.user", b"../escape"):
            self.selected["konan/konan.properties"] = baseline.replace(b"llvm-reviewed", value)
            self.write_archive()
            self.value = self.observation_v2()
            self.save()
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.call()

    def test_properties_capture_is_bounded_and_does_not_retain_other_members(self):
        retained = bytearray()
        with self.archive.open("rb") as stream:
            policy._archive_subset(stream, self.version, include_fingerprint=True, properties=retained)
        self.assertEqual(self.selected["konan/konan.properties"], bytes(retained))
        with self.archive.open("rb") as stream, patch.object(policy, "_LIMIT", 1), \
                self.assertRaisesRegex(ValueError, "properties exceed the control limit"):
            policy._archive_subset(stream, self.version, include_fingerprint=True, properties=bytearray())

    def save(self):
        self.capture.write_text(json.dumps(self.value, indent=2) + "\n")

    def call(self, **changes):
        return policy.verify_facade_native_compiler_artifacts(**{
            "repository": self.root, "policy_revision": self.revision, "compiler_inputs": self.capture,
            "native_archive": self.archive, "expected_host": self.host, **changes})

    def test_three_supported_target_routes_compare_exact_subset_without_replay_or_extraction(self):
        before = {path: path.read_bytes() for path in (self.capture, self.archive)}
        for target in ("macos-arm64", "ios-arm64", "ios-simulator-arm64"):
            self.value = self.observation(target)
            self.save()
            raw = self.capture.read_bytes()
            with self.subTest(target=target):
                self.assertIsNone(self.call())
                self.assertEqual(raw, self.capture.read_bytes())
        self.assertEqual(before[self.archive], self.archive.read_bytes())
        self.assertEqual({self.capture, self.archive}, set(self.root.iterdir()))

    def test_four_additional_host_routes_bind_archive_selection_and_original_paths(self):
        routes = {
            "macos-x64": ("macos_x64", "macos-x86_64"),
            "linux-arm64": ("linux_arm64", "linux-aarch64"),
            "linux-x64": ("linux_x64", "linux-x86_64"),
            "windows-x64": ("mingw_x64", "windows-x86_64"),
        }
        for target, (host_name, classifier) in routes.items():
            with self.subTest(target=target):
                self.host, self.host_name, self.classifier = target, host_name, classifier
                self.target_name = "mingw_x64" if target == "windows-x64" else host_name
                self.home = (r"C:\original\selected\kotlin-native" if target == "windows-x64"
                             else "/original/selected/kotlin-native")
                self.prefix = f"kotlin-native-prebuilt-{classifier}-{self.version}"
                self.selected["konan/konan.properties"] = (
                    f"llvmHome.{host_name} = llvm-reviewed\n"
                    f"libffiDir.{host_name} = libffi-reviewed\n"
                    f"dependencies.{host_name} = lldb-reviewed\n").encode()
                self.write_archive()
                self.value = self.observation_v2(target)
                self.save()
                self.assertIsNone(self.call())
                with self.assertRaisesRegex(ValueError, "supported host route"):
                    self.call(expected_host="macos-arm64")
                self.sources[policy.RUNTIME_VERIFICATION_METADATA] = b"<verification-metadata/>"
                with self.assertRaisesRegex(ValueError, "one exact checksum"):
                    self.call()

    def test_host_target_and_revision_are_independent_and_fail_closed(self):
        for host in ("macos-x64", "linux-x64", "windows-x64", "macos-aarch64", None):
            with self.subTest(host=host), self.assertRaisesRegex(ValueError, "native host|supported host route"):
                self.call(expected_host=host)
        for revision in ("HEAD", "A" * 40, None):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                self.call(policy_revision=revision)
        for target in ("macos-x64", "linux-arm64", "jvm"):
            self.value["target"] = target
            self.save()
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "supported host route"):
                self.call()
        self.git.assert_not_called()

    def test_missing_extra_or_mutated_observed_native_files_reject(self):
        for kind in ("missing", "extra", "bytes", "digest", "escape", "main"):
            self.value = self.observation()
            values = dict(self.selected)
            if kind == "missing": del values["konan/konan.properties"]
            elif kind == "extra": values["konan/compiler.fingerprint"] = b"outside current capture subset"
            elif kind in ("bytes", "digest"): values["konan/konan.properties"] = b"different"
            self.value["tools"]["native"] = self.inventory(values)
            if kind == "escape":
                self.value["nativeHome"] = "/different/selected/distribution"
            if kind == "main":
                self.value["tools"]["compiler"] = self.inventory({"foreign.jar": b"unrelated"})
            self.save()
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.call()

    def test_caller_archive_and_observed_version_must_match_exact_git_pin(self):
        archive = self.archive.read_bytes()
        self.archive.write_bytes(archive + b"different bytes")
        with self.assertRaisesRegex(ValueError, "immutable artifact pin"):
            self.call()
        self.archive.write_bytes(archive)
        self.value["kotlinVersion"] = "2.3.0"
        self.save()
        with self.assertRaisesRegex(ValueError, "immutable policy"):
            self.call()
        self.value = self.observation()
        self.save()
        self.sources[policy.RUNTIME_VERIFICATION_METADATA] = b"<verification-metadata/>"
        with self.assertRaisesRegex(ValueError, "one exact checksum"):
            self.call()

    def test_unsafe_and_duplicate_tar_members_reject_even_under_fixture_pin(self):
        for name, kind, link in ((self.prefix + "/konan/konan.properties", tarfile.REGTYPE, ""),
                ("../outside", tarfile.REGTYPE, ""), ("/absolute", tarfile.REGTYPE, ""),
                (self.prefix + "/bad\\name", tarfile.REGTYPE, ""),
                (self.prefix + "/symbolic", tarfile.SYMTYPE, "konan/konan.properties"),
                (self.prefix + "/hard", tarfile.LNKTYPE, self.prefix + "/konan/konan.properties"),
                (self.prefix + "/fifo", tarfile.FIFOTYPE, "")):
            data = b"bad" if kind == tarfile.REGTYPE else b""
            self.write_archive([(name, data, kind, link)])
            with self.subTest(name=name, kind=kind), self.assertRaises(ValueError):
                self.call()

    def test_missing_archive_subset_and_finite_quotas_reject(self):
        self.write_archive(omitted=("konan/konan.properties",))
        with self.assertRaisesRegex(ValueError, "lacks the selected compiler subset"):
            self.call()
        self.write_archive()
        for name in ("max_archive_bytes", "max_members", "max_headers", "max_entry_bytes", "max_total_bytes"):
            with self.subTest(limit=name), patch.dict(policy._LIMITS, {name: 1}), \
                    self.assertRaisesRegex(ValueError, "bounded archive limits"):
                self.call()
        with patch.dict(policy._LIMITS, {"max_compression_ratio": 0}), \
                self.assertRaisesRegex(ValueError, "bounded archive limits"):
            self.call()

    def test_native_member_bound_is_separate_from_product_transport(self):
        self.assertEqual(65_536, policy._LIMITS["max_members"])
        self.assertEqual(131_072, policy._LIMITS["max_headers"])
        self.assertEqual(4096, policy.OBJECT_ZIP_LIMITS["max_members"])
        self.assertIsNot(policy._LIMITS, policy.OBJECT_ZIP_LIMITS)

    def test_gnu_longname_counts_separately_from_logical_members(self):
        self.write_archive([(self.prefix + "/" + "long-name-" * 20,
                             b"unselected payload", tarfile.REGTYPE, "")])
        # Root directory + three selected files + two other files + long name:
        # seven logical entries, with an eighth physical GNU extension header.
        with patch.dict(policy._LIMITS, {"max_members": 7, "max_headers": 8}):
            self.call()
        for bounds in ({"max_members": 6, "max_headers": 8},
                       {"max_members": 7, "max_headers": 7}):
            with self.subTest(bounds=bounds), patch.dict(policy._LIMITS, bounds), \
                    self.assertRaisesRegex(ValueError, "bounded archive limits"):
                self.call()

    def test_extended_header_limit_applies_before_metadata_payload_parsing(self):
        self.write_archive([("././@LongLink", b"extended-control-name\0", tarfile.GNUTYPE_LONGNAME, "")])
        with patch.dict(policy._LIMITS, {"max_central_directory_bytes": 1}), \
                self.assertRaisesRegex(ValueError, "control metadata exceeds inherited limits"):
            self.call()

    def test_archive_observation_and_git_policy_lifetimes_are_guarded(self):
        inspect = policy._archive_subset
        for changed in ("archive", "observation", "policy"):
            self.write_archive()
            self.save()
            def mutate(stream, version):
                value = inspect(stream, version)
                if changed == "archive":
                    with self.archive.open("ab") as archive: archive.write(b"late change")
                elif changed == "observation": self.capture.write_bytes(b"{}\n")
                else: self.sources[policy.RUNTIME_VERIFICATION_METADATA] += b"\n"
                return value
            with self.subTest(changed=changed), patch.object(policy, "_archive_subset", side_effect=mutate), \
                    self.assertRaisesRegex(ValueError, "changed"):
                self.call()

    def test_symbolic_archive_or_capture_reject_and_no_old_absolute_paths_are_opened(self):
        link = self.root / "symbolic"
        link.symlink_to(self.archive)
        with self.assertRaises(ValueError):
            self.call(native_archive=link)
        link.unlink()
        link.symlink_to(self.capture)
        with self.assertRaises(ValueError):
            self.call(compiler_inputs=link)
        self.assertFalse(Path(self.home).exists())
        self.assertIsNone(self.call())


if __name__ == "__main__":
    unittest.main()
