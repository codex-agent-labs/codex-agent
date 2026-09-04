from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout

from ci.products.inventory import canonical_json_bytes, load_json, sha256_bytes, write_canonical_json
from ci.products.receipt import compute_build_key
from ci.products.runtime_evidence import (
    DESKTOP_RUNTIME_TEST_CLASS,
    DESKTOP_RUNTIME_TEST_METHODS,
    IMPORTED_JVM_RUNTIME_EVIDENCE_TASK,
    JVM_RUNTIME_RUNNER_ARCHIVE,
    JVM_RUNTIME_RUNNER_ENTRYPOINT,
    NODE_RUNTIME_JS_BACKEND,
    NODE_RUNTIME_RUNNER_ARCHIVE,
    NODE_RUNTIME_RUNNER_ENTRY,
    NODE_RUNTIME_WASM_BACKEND,
    NODE_WASM_RUNTIME_RUNNER_ARCHIVE,
    NODE_WASM_RUNTIME_RUNNER_ENTRIES,
    RUNTIME_TARGETS,
    build_desktop_evidence,
    build_jvm_evidence,
    build_node_evidence,
    derive_authenticated_runtime_validation_projection,
    derive_runtime_adapter_projection,
    desktop_evidence_filename,
    inspect_classifier,
    inspect_jvm_runner,
    inspect_node_runner,
    jvm_evidence_filename,
    node_evidence_filename,
    read_canonical_test_results,
    read_distribution_manifest,
    main,
    validate_desktop_evidence,
    validate_jvm_evidence,
    validate_node_evidence,
    validate_runtime_adapter_projection,
    verify_desktop_test_report,
    write_evidence,
)


def digest(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def write_zip(path: Path, entries: dict[str, bytes], *, symlinks: set[str] = frozenset()) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, contents in entries.items():
            info = zipfile.ZipInfo(name)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            if name in symlinks:
                info.create_system = 3
                info.external_attr = (0o120777 << 16)
            archive.writestr(info, contents)


class RuntimeEvidenceFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.app_server = b"official app server"
        self.supervisor = b"process supervisor"
        self.commits = {target: f"{index + 1:040x}" for index, target in enumerate(RUNTIME_TARGETS)}
        self.manifest_path = root / "distributions.json"
        distributions = []
        for target, expected in RUNTIME_TARGETS.items():
            windows = target == "mingwX64"
            distributions.append(
                {
                    "target": target,
                    "classifier": expected.classifier,
                    "asset": f"{target}.tar.gz",
                    "archiveSha256": "a" * 64,
                    "archiveEntry": "codex-app-server.exe" if windows else "codex-app-server",
                    "binarySha256": digest(self.app_server),
                    "executableName": "codex-app-server.exe" if windows else "codex-app-server",
                    "supervisorExecutableName": (
                        "codex-process-supervisor.exe" if windows else "codex-process-supervisor"
                    ),
                }
            )
        write_canonical_json(
            self.manifest_path,
            {"version": "0.145.0", "releaseTag": "rust-v0.145.0", "distributions": distributions},
        )
        self.manifest = read_distribution_manifest(self.manifest_path)
        self.classifiers: dict[str, Path] = {}
        self.proofs = {}
        for distribution in self.manifest.distributions:
            archive = root / f"codex-agent-runtime-desktop-0.2.0-{distribution.classifier}.zip"
            payload = {
                distribution.executable_name: self.app_server,
                distribution.supervisor_executable_name: self.supervisor,
                "openai-codex-LICENSE.txt": b"license",
                "openai-codex-NOTICE.txt": b"notice",
            }
            members = [
                {
                    "name": name,
                    "size": len(contents),
                    "sha256": digest(contents),
                    "executable": name
                    in {distribution.executable_name, distribution.supervisor_executable_name},
                }
                for name, contents in payload.items()
            ]
            runtime_manifest = canonical_json_bytes(
                {
                    "schemaVersion": 1,
                    "libraryVersion": "0.2.0",
                    "appServerVersion": "0.145.0",
                    "target": distribution.target,
                    "classifier": distribution.classifier,
                    "members": members,
                }
            )
            write_zip(archive, payload | {"codex-runtime-manifest.json": runtime_manifest})
            self.classifiers[distribution.target] = archive
            self.proofs[distribution.target] = inspect_classifier(distribution.target, self.manifest, archive)
        self.jvm_runner = root / JVM_RUNTIME_RUNNER_ARCHIVE
        write_zip(
            self.jvm_runner,
            {
                f"classes/{JVM_RUNTIME_RUNNER_ENTRYPOINT.replace('.', '/')}.class": b"main",
                "lib/kotlin-stdlib.jar": b"stdlib",
            },
        )
        self.node_runner = root / NODE_RUNTIME_RUNNER_ARCHIVE
        write_zip(self.node_runner, {NODE_RUNTIME_RUNNER_ENTRY: b"main", "kotlin-stdlib.js": b"stdlib"})
        self.wasm_runner = root / NODE_WASM_RUNTIME_RUNNER_ARCHIVE
        write_zip(self.wasm_runner, {name: f"compiled {name}".encode() for name in NODE_WASM_RUNTIME_RUNNER_ENTRIES})

    @property
    def classifier_files(self) -> list[Path]:
        return list(self.classifiers.values())

    def write_desktop(self) -> list[Path]:
        paths = []
        for target, proof in self.proofs.items():
            path = self.root / desktop_evidence_filename(target)
            write_evidence(
                path,
                build_desktop_evidence(
                    self.commits[target], target, proof.binary_sha256, proof.supervisor_sha256,
                    proof.archive_sha256,
                ),
            )
            paths.append(path)
        return paths

    def write_jvm(self) -> list[Path]:
        paths = []
        for target, proof in self.proofs.items():
            path = self.root / jvm_evidence_filename(target)
            write_evidence(path, build_jvm_evidence(self.commits[target], target, proof, self.jvm_runner))
            paths.append(path)
        return paths

    def write_node(self, backend: str) -> list[Path]:
        runner = self.node_runner if backend == NODE_RUNTIME_JS_BACKEND else self.wasm_runner
        paths = []
        for target, proof in self.proofs.items():
            path = self.root / node_evidence_filename(target, backend)
            write_evidence(path, build_node_evidence(self.commits[target], target, backend, proof, runner))
            paths.append(path)
        return paths


class RuntimeEvidenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.temporary.name)
        self.fixture = RuntimeEvidenceFixture(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _adapter_reports(self, component: str) -> list[dict[str, object]]:
        if component == "jvm":
            paths = self.fixture.write_jvm()
        else:
            backend = (
                NODE_RUNTIME_JS_BACKEND
                if component == "node-js"
                else NODE_RUNTIME_WASM_BACKEND
            )
            paths = self.fixture.write_node(backend)
        return [load_json(path) for path in paths]

    def _validation_receipt(
        self,
        component: str,
        target: str,
        report: Path,
        commit: str,
        *,
        run_id: int = 1,
    ) -> dict[str, object]:
        contents = report.read_bytes()
        inputs = {
            "inventory": [],
            "phaseInputDigest": sha256_bytes(canonical_json_bytes([])),
            "versionIdentity": "0.2.0",
            "upstreamArtifacts": [],
            "toolchainProfileDigest": sha256_bytes(b"toolchain"),
            "flagsDigest": sha256_bytes(b"flags"),
            "outputSchemaVersion": 1,
        }
        return {
            "schemaVersion": 1,
            "product": "runtime",
            "component": component,
            "phase": "validation",
            "target": target,
            "productVersion": "0.2.0",
            "buildKey": compute_build_key(
                product="runtime", component=component, phase="validation",
                target=target, inputs=inputs,
            ),
            "inputs": inputs,
            "outputs": [{
                "kind": "runtime-validation-evidence",
                "relativePath": f"outputs/{report.name}",
                "bytes": len(contents),
                "sha256": sha256_bytes(contents),
            }],
            "producer": {
                "repository": "owner/repository",
                "workflowPath": ".github/workflows/runtime.yml",
                "commit": commit,
                "tree": "f" * 40,
                "event": "pull_request",
                "runId": run_id,
                "runAttempt": 1,
                "pullRequest": 31,
            },
            "trustDomain": "development",
            "result": "success",
        }

    def _authenticated_adapter_inputs(
        self, component: str,
    ) -> tuple[list[Path], list[dict[str, object]]]:
        paths = (
            self.fixture.write_jvm()
            if component == "jvm"
            else self.fixture.write_node(
                NODE_RUNTIME_JS_BACKEND if component == "node-js" else NODE_RUNTIME_WASM_BACKEND
            )
        )
        product_targets = (
            "macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64",
        )
        receipts = [
            self._validation_receipt(
                component, product_target, path, self.fixture.commits[evidence_target],
            )
            for evidence_target, product_target, path in zip(
                RUNTIME_TARGETS, product_targets, paths, strict=True,
            )
        ]
        return paths, receipts

    def test_authenticated_projection_binds_raw_reports_receipts_and_provenance(self) -> None:
        paths, receipts = self._authenticated_adapter_inputs("jvm")
        original = derive_authenticated_runtime_validation_projection("jvm", paths, receipts)

        rerun = copy.deepcopy(receipts)
        for receipt in rerun:
            receipt["producer"]["tree"] = "e" * 40
            receipt["producer"]["runId"] = 99
        self.assertEqual(
            original,
            derive_authenticated_runtime_validation_projection("jvm", paths, rerun),
        )

        changed_paths, changed_receipts = self._authenticated_adapter_inputs("jvm")
        report = load_json(changed_paths[0])
        report["candidateCommit"] = "d" * 40
        write_canonical_json(changed_paths[0], report)
        changed_receipts[0] = self._validation_receipt(
            "jvm", "macos-arm64", changed_paths[0], "d" * 40,
        )
        self.assertEqual(
            original,
            derive_authenticated_runtime_validation_projection(
                "jvm", changed_paths, changed_receipts,
            ),
        )

        report["compiledJvmTestRuntimeBytes"] += 1
        write_canonical_json(changed_paths[0], report)
        changed_receipts[0] = self._validation_receipt(
            "jvm", "macos-arm64", changed_paths[0], "d" * 40,
        )
        self.assertNotEqual(
            original,
            derive_authenticated_runtime_validation_projection(
                "jvm", changed_paths, changed_receipts,
            ),
        )

    def test_authenticated_projection_rejects_none_forgery_and_cross_pair(self) -> None:
        paths, receipts = self._authenticated_adapter_inputs("node-js")
        with self.assertRaises(ValueError):
            derive_authenticated_runtime_validation_projection("node-js", None, receipts)
        forged = copy.deepcopy(receipts)
        forged[0]["outputs"][0]["sha256"] = sha256_bytes(b"forged")
        with self.assertRaisesRegex(ValueError, "exact receipt output"):
            derive_authenticated_runtime_validation_projection("node-js", paths, forged)
        crossed = copy.deepcopy(receipts)
        crossed[0]["outputs"], crossed[1]["outputs"] = (
            crossed[1]["outputs"], crossed[0]["outputs"],
        )
        with self.assertRaisesRegex(ValueError, "exact receipt output"):
            derive_authenticated_runtime_validation_projection("node-js", paths, crossed)

    def test_authenticated_native_projection_uses_exact_receipt_commit(self) -> None:
        path = self.fixture.write_desktop()[3]
        receipt = self._validation_receipt(
            "linux-x64", "linux-x64", path, self.fixture.commits["linuxX64"],
        )
        projection = derive_authenticated_runtime_validation_projection(
            "linux-x64", [path], [receipt],
        )
        self.assertEqual("linux-x64", projection["target"])
        receipt["producer"]["commit"] = "e" * 40
        with self.assertRaisesRegex(ValueError, "identity"):
            derive_authenticated_runtime_validation_projection(
                "linux-x64", [path], [receipt],
            )

    def test_adapter_projection_is_exact_and_execution_identity_independent(self) -> None:
        projections = {}
        for component in ("jvm", "node-js", "node-wasm"):
            reports = self._adapter_reports(component)
            projection = derive_runtime_adapter_projection(
                component, reports, self.fixture.commits,
            )
            self.assertEqual(
                {"schemaVersion", "component", "reports"}, set(projection),
            )
            self.assertEqual(list(RUNTIME_TARGETS), [
                report["target"] for report in projection["reports"]
            ])
            self.assertTrue(all(
                "candidateCommit" not in report and "testTask" not in report
                for report in projection["reports"]
            ))
            self.assertIs(projection, validate_runtime_adapter_projection(projection))
            projections[component] = canonical_json_bytes(projection)

            changed = copy.deepcopy(reports)
            changed_commits = {
                target: f"{index + 20:040x}"
                for index, target in enumerate(RUNTIME_TARGETS)
            }
            for report in changed:
                report["candidateCommit"] = changed_commits[report["target"]]
                if component == "jvm":
                    report["testTask"] = IMPORTED_JVM_RUNTIME_EVIDENCE_TASK
            self.assertEqual(
                projections[component],
                canonical_json_bytes(derive_runtime_adapter_projection(
                    component, changed, changed_commits,
                )),
            )

        self.assertEqual(
            {"jvm", "node-js", "node-wasm"}, set(projections),
        )
        with self.assertRaisesRegex(ValueError, "unsupported"):
            derive_runtime_adapter_projection(
                "node-js-binding", self._adapter_reports("node-js"), self.fixture.commits,
            )

    def test_adapter_projection_rejects_set_schema_authority_and_cross_component(self) -> None:
        reports = self._adapter_reports("jvm")

        def rejected(candidate: object, commits: object = None) -> None:
            with self.assertRaises(ValueError):
                derive_runtime_adapter_projection(
                    "jvm", candidate, self.fixture.commits if commits is None else commits,
                )

        rejected(reports[:-1])
        rejected([reports[1], reports[0], *reports[2:]])
        rejected([reports[0], reports[0], *reports[2:]])
        crossed = copy.deepcopy(reports)
        crossed[0] = self._adapter_reports("node-js")[0]
        rejected(crossed)
        node_js = self._adapter_reports("node-js")
        node_js[0] = self._adapter_reports("node-wasm")[0]
        with self.assertRaises(ValueError):
            derive_runtime_adapter_projection(
                "node-js", node_js, self.fixture.commits,
            )
        unknown = copy.deepcopy(reports)
        unknown[0]["unknown"] = True
        rejected(unknown)
        missing = copy.deepcopy(reports)
        missing[0].pop("result")
        rejected(missing)
        wrong_commit = copy.deepcopy(reports)
        wrong_commit[0]["candidateCommit"] = "f" * 40
        rejected(wrong_commit)
        wrong_task = copy.deepcopy(reports)
        wrong_task[0]["testTask"] = ":unowned"
        rejected(wrong_task)
        rejected({"not": "a report list"})
        rejected(1)
        rejected(reports, {target: "f" * 40 for target in tuple(RUNTIME_TARGETS)[:-1]})

        projection = derive_runtime_adapter_projection(
            "jvm", reports, self.fixture.commits,
        )
        for mutation in (
            {**projection, "unknown": True},
            {**projection, "schemaVersion": 2},
            {**projection, "component": "node-js-binding"},
            {**projection, "reports": list(reversed(projection["reports"]))},
            {**projection, "reports": [projection["reports"][0]] * 5},
        ):
            with self.assertRaises(ValueError):
                validate_runtime_adapter_projection(mutation)
        transient = copy.deepcopy(projection)
        transient["reports"][0]["candidateCommit"] = self.fixture.commits["macosArm64"]
        with self.assertRaises(ValueError):
            validate_runtime_adapter_projection(transient)

    def test_adapter_projection_preserves_every_other_semantic_field(self) -> None:
        for component in ("jvm", "node-js", "node-wasm"):
            reports = self._adapter_reports(component)
            original = canonical_json_bytes(derive_runtime_adapter_projection(
                component, reports, self.fixture.commits,
            ))
            for field, value in reports[0].items():
                if field in {"candidateCommit", "testTask"}:
                    continue
                changed = copy.deepcopy(reports)
                if type(value) is int:
                    changed[0][field] = value + 1
                elif type(value) is list:
                    changed[0][field] = list(reversed(value))
                elif field.endswith("Sha256"):
                    changed[0][field] = "f" * 64
                else:
                    changed[0][field] = f"{value}-changed"
                try:
                    mutated = canonical_json_bytes(derive_runtime_adapter_projection(
                        component, changed, self.fixture.commits,
                    ))
                except ValueError:
                    continue
                self.assertNotEqual(original, mutated, f"{component}.{field}")

    def test_classifier_and_runner_inspection(self) -> None:
        self.assertEqual(5, len(self.fixture.proofs))
        self.assertIn("classes/", inspect_jvm_runner(self.fixture.jvm_runner)[0])
        self.assertEqual(
            {NODE_RUNTIME_RUNNER_ENTRY, "kotlin-stdlib.js"},
            set(inspect_node_runner(self.fixture.node_runner, NODE_RUNTIME_JS_BACKEND)),
        )
        self.assertEqual(
            set(NODE_WASM_RUNTIME_RUNNER_ENTRIES),
            set(inspect_node_runner(self.fixture.wasm_runner, NODE_RUNTIME_WASM_BACKEND)),
        )

    def test_desktop_mixed_producer_evidence_and_maven_binding(self) -> None:
        files = self.fixture.write_desktop()
        inventory = self.root / "maven-inventory.json"
        write_canonical_json(
            inventory,
            {
                "files": [
                    {
                        "path": (
                            "io/github/codex-agent-labs/codex-agent-runtime-desktop/0.2.0/"
                            f"codex-agent-runtime-desktop-0.2.0-{RUNTIME_TARGETS[target].classifier}.zip"
                        ),
                        "sha256": self.fixture.proofs[target].archive_sha256,
                    }
                    for target in RUNTIME_TARGETS
                ]
            },
        )
        self.assertEqual(
            [],
            validate_desktop_evidence(
                files,
                self.fixture.commits,
                version="0.2.0",
                maven_inventory=inventory,
                distribution_manifest=self.fixture.manifest_path,
                classifier_archives=self.fixture.classifier_files,
            ),
        )
        self.assertTrue(validate_desktop_evidence(files, {target: "f" * 40 for target in RUNTIME_TARGETS}))

    def test_desktop_schema_hash_and_file_set_mutations_fail(self) -> None:
        files = self.fixture.write_desktop()
        victim = files[0]
        report = load_json(victim)
        report["unexpected"] = True
        write_evidence(victim, report)
        self.assertTrue(validate_desktop_evidence(files, self.fixture.commits))
        files = self.fixture.write_desktop()
        report = load_json(files[0])
        report["binarySha256"] = "f" * 64
        write_evidence(files[0], report)
        self.assertTrue(
            validate_desktop_evidence(
                files,
                self.fixture.commits,
                distribution_manifest=self.fixture.manifest_path,
                classifier_archives=self.fixture.classifier_files,
            )
        )
        self.assertTrue(validate_desktop_evidence(files[:-1], self.fixture.commits))

    def test_jvm_evidence_binds_classifier_runner_and_mixed_commits(self) -> None:
        files = self.fixture.write_jvm()
        self.assertEqual(
            [],
            validate_jvm_evidence(
                files, self.fixture.commits, self.fixture.manifest_path,
                self.fixture.classifier_files, self.fixture.jvm_runner,
            ),
        )
        report = load_json(files[-1])
        report["compiledJvmTestRuntimeSha256"] = "f" * 64
        write_evidence(files[-1], report)
        self.assertTrue(
            validate_jvm_evidence(
                files, self.fixture.commits, self.fixture.manifest_path,
                self.fixture.classifier_files, self.fixture.jvm_runner,
            )
        )

    def test_node_js_and_wasm_evidence_and_mutations(self) -> None:
        for backend, runner in (
            (NODE_RUNTIME_JS_BACKEND, self.fixture.node_runner),
            (NODE_RUNTIME_WASM_BACKEND, self.fixture.wasm_runner),
        ):
            files = self.fixture.write_node(backend)
            self.assertEqual(
                [],
                validate_node_evidence(
                    files, self.fixture.commits, backend, self.fixture.manifest_path,
                    self.fixture.classifier_files, runner,
                ),
            )
            report = load_json(files[0])
            report["nodeVersion"] = "24.18.1"
            write_evidence(files[0], report)
            self.assertTrue(
                validate_node_evidence(
                    files, self.fixture.commits, backend, self.fixture.manifest_path,
                    self.fixture.classifier_files, runner,
                )
            )

    def test_node_rejects_every_bound_field_and_unknown_field_mutation(self) -> None:
        backend = NODE_RUNTIME_WASM_BACKEND
        files = self.fixture.write_node(backend)
        victim = files[0]
        original = victim.read_bytes()
        mutations = {
            "schemaVersion": 1,
            "candidateCommit": "f" * 40,
            "target": "linuxX64",
            "runtimeBackend": NODE_RUNTIME_JS_BACKEND,
            "classifier": "wrong",
            "runnerOs": "Linux",
            "runnerArch": "X64",
            "nodeVersion": "24.18.1",
            "testTask": ":wrong",
            "testClass": "wrong",
            "testMethods": [],
            "tests": 3,
            "skipped": 1,
            "failures": 1,
            "errors": 1,
            "classifierArchiveFileName": "../unsafe.zip",
            "classifierArchiveBytes": 1,
            "classifierArchiveSha256": "f" * 64,
            "appServerBinarySha256": "f" * 64,
            "processSupervisorSha256": "f" * 64,
            "compiledNodeTestRuntimeFileName": "../unsafe.zip",
            "compiledNodeTestRuntimeBytes": 1,
            "compiledNodeTestRuntimeSha256": "f" * 64,
            "result": "failed",
        }
        for field, value in mutations.items():
            report = json.loads(original)
            report[field] = value
            write_evidence(victim, report)
            self.assertTrue(
                validate_node_evidence(
                    files,
                    self.fixture.commits,
                    backend,
                    self.fixture.manifest_path,
                    self.fixture.classifier_files,
                    self.fixture.wasm_runner,
                ),
                field,
            )
        report = json.loads(original)
        report["unexpected"] = True
        write_evidence(victim, report)
        self.assertTrue(
            validate_node_evidence(
                files,
                self.fixture.commits,
                backend,
                self.fixture.manifest_path,
                self.fixture.classifier_files,
                self.fixture.wasm_runner,
            )
        )

    def test_archive_paths_symlinks_members_and_distribution_schema_fail_closed(self) -> None:
        target = "linuxX64"
        expected = RUNTIME_TARGETS[target]
        unsafe = self.root / f"unsafe-{expected.classifier}.zip"
        write_zip(unsafe, {"../escape": b"payload"})
        with self.assertRaisesRegex(ValueError, "unsafe"):
            inspect_classifier(target, self.fixture.manifest, unsafe)

        symlink = self.root / NODE_RUNTIME_RUNNER_ARCHIVE
        write_zip(symlink, {NODE_RUNTIME_RUNNER_ENTRY: b"target"}, symlinks={NODE_RUNTIME_RUNNER_ENTRY})
        with self.assertRaisesRegex(ValueError, "unsafe"):
            inspect_node_runner(symlink, NODE_RUNTIME_JS_BACKEND)

        manifest = load_json(self.fixture.manifest_path)
        manifest["unexpected"] = True
        write_canonical_json(self.fixture.manifest_path, manifest)
        with self.assertRaisesRegex(ValueError, "schema"):
            read_distribution_manifest(self.fixture.manifest_path)

    def test_tampered_classifier_and_symlinked_evidence_fail_closed(self) -> None:
        files = self.fixture.write_desktop()
        classifier = self.fixture.classifiers["linuxX64"]
        classifier.write_bytes(classifier.read_bytes() + b"tampered")
        self.assertTrue(
            validate_desktop_evidence(
                files,
                self.fixture.commits,
                distribution_manifest=self.fixture.manifest_path,
                classifier_archives=self.fixture.classifier_files,
            )
        )

        files = self.fixture.write_desktop()
        victim = files[0]
        target = self.root / "real-evidence.json"
        target.write_bytes(victim.read_bytes())
        victim.unlink()
        victim.symlink_to(target)
        self.assertTrue(validate_desktop_evidence(files, self.fixture.commits))

    def test_junit_exactness_security_and_duplicate_identity(self) -> None:
        report = self.root / "TEST-desktop.xml"
        class_name = f"linuxX64Test.{DESKTOP_RUNTIME_TEST_CLASS}"
        cases = "".join(
            f'<testcase classname="{class_name}" name="{method}[linuxX64]"/>'
            for method in DESKTOP_RUNTIME_TEST_METHODS
        )
        report.write_text(
            f'<testsuite tests="4" skipped="0" failures="0" errors="0">{cases}</testsuite>',
            encoding="utf-8",
        )
        verify_desktop_test_report(report, "linuxX64")
        self.assertEqual(4, len(read_canonical_test_results(self.root)))

        duplicate = self.root / "nested" / "TEST-duplicate.xml"
        duplicate.parent.mkdir()
        duplicate.write_text(
            f'<testsuite><testcase classname="{class_name}" name="{DESKTOP_RUNTIME_TEST_METHODS[0]}[linuxX64]"/></testsuite>',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            read_canonical_test_results(self.root)

        report.write_text('<!DOCTYPE testsuite [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><testsuite/>')
        with self.assertRaisesRegex(ValueError, "forbidden"):
            verify_desktop_test_report(report, "linuxX64")

    def test_writer_emits_canonical_bytes(self) -> None:
        path = self.root / "evidence.json"
        evidence = build_desktop_evidence(
            self.fixture.commits["macosArm64"],
            "macosArm64",
            "a" * 64,
            "b" * 64,
            "c" * 64,
        )
        write_evidence(path, evidence)
        self.assertEqual(canonical_json_bytes(evidence), path.read_bytes())

    def test_cli_inspection_build_validation_and_report_commands(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                0,
                main(["inspect-manifest", "--manifest", str(self.fixture.manifest_path)]),
            )
        projection = json.loads(output.getvalue())
        self.assertEqual(1, projection["schemaVersion"])
        self.assertEqual(list(RUNTIME_TARGETS), [item["target"] for item in projection["distributions"]])
        self.assertEqual(output.getvalue(), output.getvalue().strip() + "\n")

        target = "macosArm64"
        proof = self.fixture.proofs[target]
        desktop_output = self.root / desktop_evidence_filename(target)
        self.assertEqual(
            0,
            main(
                [
                    "build-desktop",
                    "--candidate-commit", self.fixture.commits[target],
                    "--target", target,
                    "--binary-sha256", proof.binary_sha256,
                    "--supervisor-sha256", proof.supervisor_sha256,
                    "--classifier-archive-sha256", proof.archive_sha256,
                    "--output", str(desktop_output),
                ]
            ),
        )
        self.assertEqual(3, load_json(desktop_output)["schemaVersion"])

        jvm_output = self.root / jvm_evidence_filename(target)
        self.assertEqual(
            0,
            main(
                [
                    "build-jvm",
                    "--candidate-commit", self.fixture.commits[target],
                    "--target", target,
                    "--manifest", str(self.fixture.manifest_path),
                    "--classifier", str(self.fixture.classifiers[target]),
                    "--runner", str(self.fixture.jvm_runner),
                    "--output", str(jvm_output),
                ]
            ),
        )
        self.assertEqual(1, load_json(jvm_output)["schemaVersion"])

        node_output = self.root / node_evidence_filename(target, NODE_RUNTIME_WASM_BACKEND)
        self.assertEqual(
            0,
            main(
                [
                    "build-node",
                    "--candidate-commit", self.fixture.commits[target],
                    "--target", target,
                    "--backend", NODE_RUNTIME_WASM_BACKEND,
                    "--manifest", str(self.fixture.manifest_path),
                    "--classifier", str(self.fixture.classifiers[target]),
                    "--runner", str(self.fixture.wasm_runner),
                    "--output", str(node_output),
                ]
            ),
        )
        self.assertEqual(2, load_json(node_output)["schemaVersion"])

        commit_arguments = [
            argument
            for target_name, commit in self.fixture.commits.items()
            for argument in ("--expected-commit", f"{target_name}={commit}")
        ]
        classifier_arguments = [
            argument
            for path in self.fixture.classifier_files
            for argument in ("--classifier", str(path))
        ]
        desktop_files = self.fixture.write_desktop()
        jvm_files = self.fixture.write_jvm()
        node_files = self.fixture.write_node(NODE_RUNTIME_JS_BACKEND)
        for command, files, extra in (
            (
                "validate-desktop",
                desktop_files,
                ["--manifest", str(self.fixture.manifest_path), *classifier_arguments],
            ),
            (
                "validate-jvm",
                jvm_files,
                [
                    "--manifest", str(self.fixture.manifest_path),
                    *classifier_arguments,
                    "--runner", str(self.fixture.jvm_runner),
                ],
            ),
            (
                "validate-node",
                node_files,
                [
                    "--backend", NODE_RUNTIME_JS_BACKEND,
                    "--manifest", str(self.fixture.manifest_path),
                    *classifier_arguments,
                    "--runner", str(self.fixture.node_runner),
                ],
            ),
        ):
            evidence_arguments = [
                argument for path in files for argument in ("--evidence", str(path))
            ]
            command_output = io.StringIO()
            with redirect_stdout(command_output):
                self.assertEqual(0, main([command, *commit_arguments, *evidence_arguments, *extra]))
            self.assertEqual("passed", json.loads(command_output.getvalue())["result"])

        report = self.root / "desktop-report.xml"
        class_name = f"{target}Test.{DESKTOP_RUNTIME_TEST_CLASS}"
        cases = "".join(
            f'<testcase classname="{class_name}" name="{method}[{target}]"/>'
            for method in DESKTOP_RUNTIME_TEST_METHODS
        )
        report.write_text(
            f'<testsuite tests="4" skipped="0" failures="0" errors="0">{cases}</testsuite>',
            encoding="utf-8",
        )
        report_result = io.StringIO()
        with redirect_stdout(report_result):
            self.assertEqual(
                0,
                main(
                    [
                        "verify-desktop-test-report",
                        "--report", str(report),
                        "--target", target,
                    ]
                ),
            )
        self.assertEqual("passed", json.loads(report_result.getvalue())["result"])

    def test_direct_module_cli_and_validator_failure_are_nonzero(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "ci.products.runtime_evidence",
                "inspect-manifest",
                "--manifest",
                str(self.fixture.manifest_path),
            ],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(1, json.loads(completed.stdout)["schemaVersion"])

        files = self.fixture.write_desktop()
        report = load_json(files[0])
        report["result"] = "failed"
        write_evidence(files[0], report)
        commits = [
            argument
            for target, commit in self.fixture.commits.items()
            for argument in ("--expected-commit", f"{target}={commit}")
        ]
        evidence = [argument for path in files for argument in ("--evidence", str(path))]
        failed = subprocess.run(
            [
                sys.executable,
                "-m",
                "ci.products.runtime_evidence",
                "validate-desktop",
                *commits,
                *evidence,
            ],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, failed.returncode)
        self.assertIn("test result mismatch", failed.stderr)


if __name__ == "__main__":
    unittest.main()
