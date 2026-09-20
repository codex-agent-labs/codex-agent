"""Real content/byte consistency checks; no compiler or hosted trust assertion."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products import sdk_facade_validation as facade
from ci.products.inventory import canonical_json_bytes, regular_file_inventory
from ci.products.receipt import output_inventory_digest, write_output_manifest
from ci.products.registry import SDK_FACADE_TARGETS


class FacadeValidationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-facade-content-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.package = self.root / "package"
        self.contract = self.root / "contract"
        self.repository = self.root / "repository"
        self.evidence = self.root / "evidence"
        for stage in (self.package, self.contract):
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/payload.bin").write_bytes(stage.name.encode())
        self.package_manifest = write_output_manifest(self.package, "sdk", "sdk-core", "package", "common", "0.8.7",
                                                       {"maven": "outputs"})
        write_output_manifest(self.contract, "contract", "contract", "metadata", "common", "0.8.2",
                              {"contract-bundle": "outputs"})
        self.repository.mkdir()
        (self.repository / "fixture.jar").write_bytes(b"caller-admitted repository fixture; not real Maven")
        (self.evidence / "process").mkdir(parents=True)
        (self.evidence / "process/stdout.bin").write_bytes(b"arbitrary lossless output\xff")
        (self.evidence / "process/stderr.bin").write_bytes(b"")
        self.context = {"gradleWrapper": "/original checkout/gradlew",
            "consumerDirectory": "/original work/consumer", "repositoryDirectory": "/original work/maven",
            "outcomeInitScript": "/original work/consumer/.codex-consumer-task-outcomes.init.gradle.kts",
            "environment": {}}
        self.arguments = dict(evidence_directory=self.evidence, target="jvm", sdk_version="0.8.7",
            runtime_version="0.8.9", contract_version="0.8.2", package_stage=self.package,
            contract_stage=self.contract, imported_repository=self.repository,
            expected_package_inventory=regular_file_inventory(self.package),
            expected_contract_inventory=regular_file_inventory(self.contract),
            expected_repository_inventory=regular_file_inventory(self.repository), original_context=self.context)
        self.capture("jvm")

    def write(self, name, value):
        # Gradle atomicWriteJson is not the canonical Python encoder.
        (self.evidence / name).write_text(json.dumps(value, indent=2) + "\n")

    def capture(self, target):
        self.arguments["target"] = target
        task = facade.FACADE_CONSUMER_TASKS[target]
        self.report = {"schemaVersion": 6, "result": "passed", "sdkVersion": "0.8.7",
            "runtimeVersion": "0.8.9", "repository": "CENTRAL_STAGING-only",
            "mavenGroup": "io.github.codex-agent-labs", "target": target, "tasks": [task]}
        self.execution = {"schemaVersion": 1, "command": [self.context["gradleWrapper"], "-p",
            self.context["consumerDirectory"], "--no-daemon", "--no-configuration-cache",
            "-PCENTRAL_STAGING=" + self.context["repositoryDirectory"], "-PcodexAgent.sdkVersion=0.8.7",
            "-PcodexAgent.runtimeVersion=0.8.9", "-PcodexAgent.consumerTarget=" + target,
            "--init-script", self.context["outcomeInitScript"], task, "verifyCodexStagedConsumerTaskOutcomes"],
            "workingDirectory": self.context["consumerDirectory"], "environment": {}, "exitCode": 0}
        self.outcomes = {"schemaVersion": 1, "tasks": [{"task": task, "didWork": True,
            "upToDate": False, "skipped": False, "skipMessage": None, "failure": None}]}
        self.write("report.json", self.report)
        self.write("process/execution.json", self.execution)
        self.write("task-outcomes.json", self.outcomes)

    def test_all_registry_targets_and_exact_content_without_execution_identity(self):
        self.assertEqual(set(SDK_FACADE_TARGETS), set(facade.FACADE_CONSUMER_TASKS))
        for target in SDK_FACADE_TARGETS:
            with self.subTest(target=target):
                self.capture(target)
                before = regular_file_inventory(self.root, allow_empty=True)
                content = facade.verify_facade_consumer_evidence(**self.arguments)
                self.assertEqual(target, content["target"])
                self.assertEqual([facade.FACADE_CONSUMER_TASKS[target]], content["tasks"])
                self.assertEqual(output_inventory_digest(self.package_manifest["outputs"]), content["packageOutputsDigest"])
                self.assertEqual(content, facade.validate_facade_validation_content(content))
                self.assertNotIn("original", canonical_json_bytes(content).decode())
                self.assertNotIn("runtimeVersion", content)
                self.assertEqual(before, regular_file_inventory(self.root, allow_empty=True))

    def test_cache_and_log_differences_do_not_change_canonical_content(self):
        baseline = canonical_json_bytes(facade.verify_facade_consumer_evidence(**self.arguments))
        for message in ("UP-TO-DATE", "FROM-CACHE"):
            self.outcomes["tasks"][0].update(didWork=False, upToDate=True, skipped=True, skipMessage=message)
            self.write("task-outcomes.json", self.outcomes)
            (self.evidence / "process/stdout.bin").write_bytes(message.encode())
            self.assertEqual(baseline, canonical_json_bytes(facade.verify_facade_consumer_evidence(**self.arguments)))

    def test_report_process_and_outcome_failures_are_not_success(self):
        cases = [
            ("report.json", lambda v: v.update(target="desktop")),
            ("report.json", lambda v: v.update(tasks=["compileOther"])),
            ("report.json", lambda v: v.update(runtimeVersion="0.2.0")),
            ("report.json", lambda v: v.update(unexpected=True)),
            ("process/execution.json", lambda v: v.update(exitCode=None)),
            ("process/execution.json", lambda v: v.update(exitCode=1)),
            ("process/execution.json", lambda v: v.update(exitCode=False)),
            ("process/execution.json", lambda v: v["command"].append("--offline")),
            ("process/execution.json", lambda v: v.update(workingDirectory="/other")),
            ("process/execution.json", lambda v: v.update(environment={"JAVA_HOME": "/other"})),
            ("task-outcomes.json", lambda v: v.update(tasks=[])),
            ("task-outcomes.json", lambda v: v["tasks"].append(deepcopy(v["tasks"][0]))),
            ("task-outcomes.json", lambda v: v["tasks"][0].update(didWork=False, skipped=True, skipMessage="NO-SOURCE")),
            ("task-outcomes.json", lambda v: v["tasks"][0].update(failure="compiler failed")),
            ("task-outcomes.json", lambda v: v["tasks"][0].update(didWork=1)),
        ]
        for name, mutate in cases:
            with self.subTest(file=name, mutation=cases.index((name, mutate))):
                self.capture("jvm")
                value = json.loads((self.evidence / name).read_bytes())
                mutate(value)
                self.write(name, value)
                with self.assertRaises(ValueError):
                    facade.verify_facade_consumer_evidence(**self.arguments)

    def test_exact_caller_inventories_manifest_identities_and_repository_digest(self):
        baseline = facade.verify_facade_consumer_evidence(**self.arguments)
        for name in ("expected_package_inventory", "expected_contract_inventory", "expected_repository_inventory"):
            arguments = {**self.arguments, name: []}
            with self.subTest(inventory=name), self.assertRaises(ValueError):
                facade.verify_facade_consumer_evidence(**arguments)
        for field in ("sdk_version", "contract_version"):
            with self.subTest(version=field), self.assertRaises(ValueError):
                facade.verify_facade_consumer_evidence(**{**self.arguments, field: "0.8.99"})
        (self.repository / "fixture.jar").write_bytes(b"different independently admitted fixture bytes")
        with self.assertRaises(ValueError):
            facade.verify_facade_consumer_evidence(**self.arguments)
        self.arguments["expected_repository_inventory"] = regular_file_inventory(self.repository)
        changed = facade.verify_facade_consumer_evidence(**self.arguments)
        self.assertNotEqual(baseline["importedRepositoryDigest"], changed["importedRepositoryDigest"])

    def test_missing_extra_symlink_and_duplicate_raw_json_reject(self):
        path = self.evidence / "process/stderr.bin"
        path.unlink()
        with self.assertRaises(ValueError): facade.verify_facade_consumer_evidence(**self.arguments)
        path.write_bytes(b"")
        extra = self.evidence / "extra"
        extra.mkdir()
        with self.assertRaises(ValueError): facade.verify_facade_consumer_evidence(**self.arguments)
        extra.rmdir()
        path.unlink()
        path.symlink_to(self.repository / "fixture.jar")
        with self.assertRaises(ValueError): facade.verify_facade_consumer_evidence(**self.arguments)
        path.unlink()
        path.write_bytes(b"")
        (self.evidence / "report.json").write_text('{"schemaVersion":6,"schemaVersion":6}')
        with self.assertRaises(ValueError): facade.verify_facade_consumer_evidence(**self.arguments)

    def test_late_mutations_of_originals_or_caller_expectations_reject(self):
        project = facade.validate_facade_validation_content
        for kind in ("log", "repository", "context", "inventory"):
            with self.subTest(kind=kind):
                self.capture("jvm")
                old_repository = (self.repository / "fixture.jar").read_bytes()
                old_context = deepcopy(self.context)
                old_inventory = deepcopy(self.arguments["expected_package_inventory"])

                def mutate(value):
                    result = project(value)
                    if kind == "log": (self.evidence / "process/stderr.bin").write_bytes(b"late mutation")
                    elif kind == "repository": (self.repository / "fixture.jar").write_bytes(b"late mutation")
                    elif kind == "context": self.context["consumerDirectory"] = "/late"
                    else: self.arguments["expected_package_inventory"].clear()
                    return result

                with patch.object(facade, "validate_facade_validation_content", side_effect=mutate), self.assertRaisesRegex(ValueError, "changed"):
                    facade.verify_facade_consumer_evidence(**self.arguments)
                (self.repository / "fixture.jar").write_bytes(old_repository)
                self.context.clear()
                self.context.update(old_context)
                self.arguments["expected_package_inventory"] = old_inventory

    def test_content_rejects_foreign_fields_targets_and_tasks(self):
        content = facade.verify_facade_consumer_evidence(**self.arguments)
        for field, value in (("producer", {}), ("target", "desktop"), ("schemaVersion", True),
                             ("tasks", []), ("result", "failed"), ("packageOutputsDigest", "bad")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                facade.validate_facade_validation_content({**content, field: value})


if __name__ == "__main__":
    unittest.main()
