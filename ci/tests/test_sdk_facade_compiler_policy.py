"""Real checked-in pin parsing; immutable Git reads mocked, no compiler/host proof."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from products import sdk_facade_compiler_policy as policy
from products.inventory import sha256_bytes


class FacadePartialCompilerPolicyTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.capture = self.root / "compiler-inputs.json"
        self.revision = "a" * 40
        repository = Path(__file__).resolve().parents[2]
        self.sources = {name: (repository / name).read_bytes() for name in
                        (policy.VERSION_CATALOG, policy.RUNTIME_VERIFICATION_METADATA)}
        self.git = self.enterContext(patch.object(policy, "run_git", side_effect=self.git_read))
        self.blobs = self.enterContext(patch.object(policy, "git_regular_blob_bytes", side_effect=self.blob))
        self.compiler_name = "kotlin-compiler-embeddable-2.3.10.jar"
        self.plugin_name = "kotlin-scripting-compiler-embeddable-2.3.10.jar"
        self.value = self.observation()
        self.save()

    def git_read(self, root, command, argument):
        self.assertEqual((self.root, "rev-parse", self.revision + "^{commit}"), (root, command, argument))
        return self.revision + "\n"

    def blob(self, root, revision, name, *, max_bytes):
        self.assertEqual((self.root, self.revision, 4 * 1024 * 1024), (root, revision, max_bytes))
        return self.sources[name]

    def row(self, path, *, pinned=False):
        digest = (policy._metadata_checksum(self.sources[policy.RUNTIME_VERIFICATION_METADATA], path.rsplit("/", 1)[-1])
                  .removeprefix("sha256:") if pinned else "b" * 64)
        return {"path": path, "bytes": 123, "sha256": digest}

    def inventory(self, *rows):
        rows = sorted(rows, key=lambda row: row["path"])
        encoded = "".join(f"{row['path']}\0{row['bytes']}\0{row['sha256']}\n" for row in rows).encode()
        return {"files": rows, "sha256": sha256_bytes(encoded).removeprefix("sha256:")}

    def observation(self, target="jvm"):
        family = "js" if target.startswith("node-") else "jvm"
        task = policy.FACADE_CONSUMER_TASKS[target]
        return {"schemaVersion": 1, "target": target, "task": task,
            "taskClass": "org.jetbrains.kotlin.gradle.tasks." + ("Kotlin2JsCompile" if family == "js" else "KotlinCompile"),
            "family": family, "kotlinVersion": "2.3.10", "agpVersion": "9.2.1" if target == "android" else None,
            "javaExecutable": "/original/jdk/bin/java", "nativeHome": None, "arguments": ["-Xmulti-platform"],
            "tools": {"implementation": self.inventory(self.row("/transformed/kotlin-gradle-plugin.jar")),
                "compiler": self.inventory(self.row("/cache/" + self.compiler_name, pinned=True)),
                "compilerPlugins": self.inventory(self.row("/cache/" + self.plugin_name, pinned=True)),
                "java": self.inventory(self.row("/original/jdk/bin/java")), "native": None,
                "android": self.inventory(self.row("/transformed/gradle-9.2.1.jar")) if target == "android" else None},
            "inputs": self.inventory(self.row("/original/consumer/Consumer.kt")),
            "outcome": {"task": task, "didWork": True, "upToDate": False, "skipped": False,
                        "skipMessage": None, "failure": None}}

    def save(self):
        # Original producer uses ordinary pretty/compact JSON, not canonical product JSON.
        self.capture.write_text(json.dumps(self.value, indent=2) + "\n")

    def call(self, **changes):
        return policy.verify_facade_kotlin_compiler_artifacts(**{
            "repository": self.root, "policy_revision": self.revision,
            "compiler_inputs": self.capture, **changes})

    def test_known_compiler_and_plugin_pins_ignore_dirty_checkout_and_do_not_admit_other_tools(self):
        for name in self.sources:
            output = self.root / name
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"dirty checkout is not policy")
        for target in ("jvm", "android", "node-js", "node-wasm"):
            self.value = self.observation(target)
            self.save()
            self.assertIsNone(self.call())
        # Unpinned AGP/JDK/implementation fixture hashes were intentionally not authenticated.
        self.assertTrue(self.blobs.called)

    def test_native_and_wrong_explicit_policy_revision_reject(self):
        self.revision = "a" * 64
        self.assertIsNone(self.call())
        for revision in ("HEAD", "A" * 40, "a" * 39, None):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                self.call(policy_revision=revision)
        self.value["target"] = "ios-arm64"
        self.save()
        with self.assertRaisesRegex(ValueError, "does not support native"):
            self.call()
        self.value = self.observation()
        self.save()
        self.git.side_effect = None
        self.git.return_value = "c" * 40
        with self.assertRaisesRegex(ValueError, "exact commit"):
            self.call()

    def test_unknown_wrong_pin_and_ambiguous_observed_artifacts_reject(self):
        original = deepcopy(self.value)
        for kind in ("unknown", "wrong", "ambiguous"):
            self.value = deepcopy(original)
            row = self.value["tools"]["compiler"]["files"][0]
            if kind == "unknown": row["path"] = "/cache/unreviewed.jar"
            elif kind == "wrong": row["sha256"] = "d" * 64
            else:
                other = {**row, "path": "/another/" + self.compiler_name}
                self.value["tools"]["compilerPlugins"] = self.inventory(other)
            self.value["tools"]["compiler"] = self.inventory(row)
            self.save()
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.call()

    def test_inventory_unknown_fields_contradictions_and_duplicate_json_reject(self):
        original = deepcopy(self.value)
        for kind in ("digest", "extra", "missing", "contradiction", "duplicate", "path"):
            self.value = deepcopy(original)
            if kind == "digest": self.value["tools"]["compiler"]["sha256"] = "c" * 64
            elif kind == "extra": self.value["tools"]["newFamily"] = None
            elif kind == "missing": del self.value["tools"]["compiler"]
            elif kind == "path":
                row = self.value["tools"]["compiler"]["files"][0]
                row["path"] = "/original/../cache/" + self.compiler_name
                self.value["tools"]["compiler"] = self.inventory(row)
            elif kind == "contradiction":
                row = {**self.value["tools"]["compiler"]["files"][0], "bytes": 124}
                self.value["inputs"] = self.inventory(row)
            self.save()
            if kind == "duplicate":
                self.capture.write_text(self.capture.read_text().replace('"schemaVersion": 1', '"schemaVersion": 1, "schemaVersion": 1'))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.call()

    def test_failed_task_and_foreign_source_version_reject(self):
        for field, changed in (("outcome", {**self.value["outcome"], "didWork": False}),
                               ("kotlinVersion", "2.3.0"), ("task", "help")):
            self.value = self.observation()
            self.value[field] = changed
            self.save()
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.call()

    def test_observation_and_policy_mutation_during_comparison_reject(self):
        checksum = policy._metadata_checksum
        original_sources = dict(self.sources)
        for changed in ("observation", "policy"):
            self.sources = dict(original_sources)
            self.value = self.observation()
            self.save()
            def mutate(contents, artifact):
                if changed == "observation": self.capture.write_bytes(b"{}\n")
                else: self.sources[policy.RUNTIME_VERIFICATION_METADATA] = contents + b"\n"
                return checksum(contents, artifact)
            with self.subTest(changed=changed), patch.object(policy, "_metadata_checksum", side_effect=mutate):
                with self.assertRaisesRegex(ValueError, "changed"):
                    self.call()

    def test_symbolic_capture_is_rejected(self):
        symbolic = self.root / "symbolic.json"
        symbolic.symlink_to(self.capture)
        with self.assertRaises(ValueError):
            self.call(compiler_inputs=symbolic)
