from __future__ import annotations

import copy
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile

from ci.products.c_abi import (
    C_ABI_CURRENT,
    C_ABI_ENCODED,
    C_ABI_FILE_MODE,
    C_ABI_MINIMUM,
    C_ABI_PACKAGE_MANIFEST,
    C_ABI_STAGED_EVIDENCE_PATH,
    C_ABI_SYMBOL_COUNT,
    C_ABI_ZIP_EPOCH,
    COMPILE_ONLY_CONSUMERS,
    GNU_CONSUMERS,
    STRICT_CONSUMERS,
    TARGET_SPECS,
    CAbiConsumerProof,
    CAbiEvidenceValues,
    CAbiPackageInput,
    build_c_abi_package_evidence,
    c_abi_archive_file_name,
    describe_c_abi,
    describe_c_abi_export_policy,
    c_abi_evidence_file_name,
    c_abi_expected_symbols,
    c_abi_host_target,
    c_abi_linux_symbol_versions,
    inspect_c_abi_package,
    main,
    package_c_abi_sdk,
    portable_verify_c_abi_package_evidence,
    verify_c_abi_package_evidence,
    write_c_abi_package_evidence,
)
from ci.products.inventory import canonical_json_bytes


class ProductCAbiTest(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="product-c-abi-")
        self.root = Path(self.temporary.name)
        self.symbols = tuple(f"codex_agent_symbol_{index:03d}" for index in range(C_ABI_SYMBOL_COUNT))
        self.header = self._write(
            "inputs/codex_agent.h",
            "".join(f"int {symbol}(void);\n" for symbol in self.symbols).encode(),
        )
        self.license = self._write("inputs/LICENSE.txt", b"license\n")
        self.notice = self._write("inputs/THIRD_PARTY_NOTICES.md", b"notice\n")
        self.consumer_root = self.root / "consumers"
        self.consumer_sources = [
            self._write(f"consumers/{name}", f"/* {name} */\n".encode())
            for name in sorted(STRICT_CONSUMERS)
        ]
        self.consumer_digests = {
            source.name: self._digest(source.read_bytes()) for source in self.consumer_sources
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_target_contract_host_mapping_and_names_are_exact(self) -> None:
        self.assertEqual(
            {"macosArm64", "macosX64", "linuxArm64", "linuxX64", "mingwX64"},
            set(TARGET_SPECS),
        )
        self.assertEqual("macosArm64", c_abi_host_target("Mac OS X", "aarch64"))
        self.assertEqual("macosX64", c_abi_host_target("macOS", "x86_64"))
        self.assertEqual("linuxArm64", c_abi_host_target("Linux", "arm64"))
        self.assertEqual("linuxX64", c_abi_host_target("linux", "amd64"))
        self.assertEqual("mingwX64", c_abi_host_target("Windows 11", "x86_64"))
        self.assertIsNone(c_abi_host_target("Plan9", "x86_64"))
        for target, spec in TARGET_SPECS.items():
            self.assertEqual(
                f"codex-agent-runtime-desktop-1.2.3-{spec.classifier}.zip",
                c_abi_archive_file_name("1.2.3", target),
            )
            self.assertEqual(f"{spec.proof_id}.json", c_abi_evidence_file_name(target))
            self.assertEqual(C_ABI_CURRENT, "1.12")
            self.assertEqual(C_ABI_MINIMUM, "1.0")
            self.assertEqual(C_ABI_ENCODED, "0x010c0000")

    def test_describe_and_specs_emit_the_complete_canonical_catalog(self) -> None:
        expected = describe_c_abi()
        self.assertEqual(
            {"schemaVersion", "abi", "paths", "consumers", "hostMappings", "targets"},
            set(expected),
        )
        self.assertEqual(
            {
                "current": C_ABI_CURRENT,
                "minimum": C_ABI_MINIMUM,
                "encoded": C_ABI_ENCODED,
                "publicSymbolCount": C_ABI_SYMBOL_COUNT,
            },
            expected["abi"],
        )
        self.assertEqual(
            {
                "header": "include/codex_agent.h",
                "packageManifest": C_ABI_PACKAGE_MANIFEST,
                "stagedEvidence": C_ABI_STAGED_EVIDENCE_PATH,
            },
            expected["paths"],
        )
        self.assertEqual(sorted(STRICT_CONSUMERS), expected["consumers"]["strict"])
        self.assertEqual(sorted(COMPILE_ONLY_CONSUMERS), expected["consumers"]["compileOnly"])
        self.assertEqual(sorted(GNU_CONSUMERS), expected["consumers"]["gnu"])
        self.assertEqual(
            [
                {"osContains": "mac", "architectures": ["aarch64", "arm64"], "target": "macosArm64"},
                {"osContains": "mac", "architectures": ["amd64", "x86_64"], "target": "macosX64"},
                {"osContains": "linux", "architectures": ["aarch64", "arm64"], "target": "linuxArm64"},
                {"osContains": "linux", "architectures": ["amd64", "x86_64"], "target": "linuxX64"},
                {"osContains": "windows", "architectures": ["amd64", "x86_64"], "target": "mingwX64"},
            ],
            expected["hostMappings"],
        )
        self.assertEqual(sorted(TARGET_SPECS), [record["target"] for record in expected["targets"]])
        by_target = {record["target"]: record for record in expected["targets"]}
        for target, spec in TARGET_SPECS.items():
            record = by_target[target]
            self.assertEqual(
                {
                    "target", "component", "classifier", "runnerOs", "runnerArch", "format",
                    "architecture", "libraryPath", "loaderIdentity", "importLibraryPaths", "proofId",
                    "evidenceFileName", "archiveFileNameTemplate", "versionIdentity", "requiredToolIds",
                },
                set(record),
            )
            self.assertEqual(spec.classifier.removeprefix("c-abi-"), record["component"])
            self.assertEqual(spec.classifier, record["classifier"])
            self.assertEqual(spec.library_path, record["libraryPath"])
            self.assertEqual(spec.proof_id, record["proofId"])
            self.assertEqual(sorted(spec.required_tool_ids), record["requiredToolIds"])
            self.assertEqual(
                c_abi_archive_file_name("7.8.9", target),
                record["archiveFileNameTemplate"].replace("{libraryVersion}", "7.8.9"),
            )

        outputs: list[str] = []
        for command in ("describe", "specs"):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(0, main([command]))
            self.assertEqual(expected, self._canonical_stdout(output.getvalue()))
            outputs.append(output.getvalue())
        self.assertEqual(outputs[0], outputs[1])

    def test_describe_export_policy_emits_exact_canonical_symbols_and_linux_versions(self) -> None:
        for target in ("macosArm64", "linuxX64", "mingwX64"):
            with self.subTest(target=target):
                spec = TARGET_SPECS[target]
                policy = self._export_policy(target)
                expected = describe_c_abi_export_policy(policy, spec.format)
                self.assertEqual(
                    {"schemaVersion", "format", "publicSymbols", "publicSymbolVersions"},
                    set(expected),
                )
                self.assertEqual(spec.format, expected["format"])
                self.assertEqual(list(self.symbols), expected["publicSymbols"])
                if spec.format == "elf":
                    self.assertEqual(
                        [
                            {"symbol": symbol, "version": version}
                            for symbol, version in c_abi_linux_symbol_versions(policy).items()
                        ],
                        expected["publicSymbolVersions"],
                    )
                else:
                    self.assertEqual([], expected["publicSymbolVersions"])
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(0, main([
                        "describe-export-policy",
                        "--export-policy", str(policy),
                        "--format", spec.format,
                    ]))
                self.assertEqual(expected, self._canonical_stdout(output.getvalue()))

    def test_describe_export_policy_rejects_missing_malformed_duplicate_and_wrong_node_inputs(self) -> None:
        missing = self.root / "missing.exports"
        with self.assertRaises(ValueError):
            describe_c_abi_export_policy(missing, "pe")

        malformed = self._write("bad/malformed.exports", b"\xff\xfe")
        with self.assertRaises(UnicodeDecodeError):
            describe_c_abi_export_policy(malformed, "mach-o")

        short = self._write(
            "bad/missing-symbol.exports",
            "".join(f"{symbol}\n" for symbol in self.symbols[:-1]).encode(),
        )
        with self.assertRaisesRegex(ValueError, "exactly 777 symbols"):
            describe_c_abi_export_policy(short, "pe")

        linux = self._export_policy("linuxX64")
        linux_contents = linux.read_text(encoding="utf-8")
        duplicate = self._write(
            "bad/duplicate.map",
            linux_contents.replace(
                f"        {self.symbols[0]};\n",
                f"        {self.symbols[0]};\n        {self.symbols[0]};\n",
                1,
            ).encode(),
        )
        with self.assertRaisesRegex(ValueError, "Duplicate C ABI Linux symbol assignment"):
            describe_c_abi_export_policy(duplicate, "elf")

        wrong_node = self._write(
            "bad/wrong-node.map",
            linux_contents.replace("CODEX_AGENT_1.12 {", "CODEX_AGENT_2.12 {", 1).encode(),
        )
        with self.assertRaisesRegex(ValueError, "outside a version node"):
            describe_c_abi_export_policy(wrong_node, "elf")

        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            self.assertEqual(1, main([
                "describe-export-policy",
                "--export-policy", str(duplicate),
                "--format", "elf",
            ]))
        self.assertIn("Duplicate C ABI Linux symbol assignment", error.getvalue())

    def test_all_five_packages_are_deterministic_and_exact(self) -> None:
        for target, spec in TARGET_SPECS.items():
            with self.subTest(target=target):
                package_input = self._package_input(target)
                first = self.root / f"first-{target}.zip"
                second = self.root / f"second-{target}.zip"
                first_snapshot = package_c_abi_sdk(package_input, first)
                second_snapshot = package_c_abi_sdk(package_input, second)
                self.assertEqual(first.read_bytes(), second.read_bytes())
                self.assertEqual(first_snapshot, second_snapshot)
                self.assertEqual(first_snapshot, inspect_c_abi_package(first, package_input))
                expected = {
                    "LICENSE.txt",
                    "THIRD_PARTY_NOTICES.md",
                    "include/codex_agent.h",
                    spec.library_path,
                }
                if spec.format == "elf":
                    expected.add(f"lib/{spec.loader_identity}")
                expected.update(spec.import_library_paths)
                self.assertEqual(expected, set(first_snapshot.members))
                with zipfile.ZipFile(first) as archive:
                    self.assertEqual(sorted(expected | {C_ABI_PACKAGE_MANIFEST}), archive.namelist())
                    for info in archive.infolist():
                        self.assertEqual(C_ABI_ZIP_EPOCH, info.date_time)
                        self.assertEqual(zipfile.ZIP_DEFLATED, info.compress_type)
                        self.assertEqual(3, info.create_system)
                        self.assertEqual(C_ABI_FILE_MODE, (info.external_attr >> 16) & 0xFFFF)
                    manifest = json.loads(archive.read(C_ABI_PACKAGE_MANIFEST))
                self.assertEqual(
                    {
                        "schemaVersion", "libraryVersion", "target", "classifier", "producerCommit",
                        "producerTree", "abiCurrent", "abiMinimum", "abiEncoded", "publicSymbolCount",
                        "publicSymbolsSha256", "exportPolicySha256", "members",
                    },
                    set(manifest),
                )
                self.assertEqual(C_ABI_SYMBOL_COUNT, manifest["publicSymbolCount"])

    def test_symbol_version_and_package_input_contracts_fail_closed(self) -> None:
        policy = self._export_policy("linuxX64")
        self.assertEqual(set(self.symbols), set(c_abi_expected_symbols(policy)))
        versions = c_abi_linux_symbol_versions(policy)
        self.assertEqual(set(self.symbols), set(versions))
        self.assertEqual({f"CODEX_AGENT_1.{minor}" for minor in range(13)}, set(versions.values()))

        short_policy = self._write("bad/short.map", b"codex_agent_only;\n")
        with self.assertRaisesRegex(ValueError, "exactly 777 symbols"):
            c_abi_expected_symbols(short_policy)
        outside = self._write(
            "bad/outside.map",
            "".join(f"{symbol};\n" for symbol in self.symbols).encode(),
        )
        with self.assertRaisesRegex(ValueError, "outside a version node"):
            c_abi_linux_symbol_versions(outside)

        package_input = self._package_input("macosArm64")
        bad_header = self._write("bad/header.h", self.header.read_bytes().replace(b"symbol_000", b"other_000", 1))
        with self.assertRaisesRegex(ValueError, "header/export policy symbol mismatch"):
            package_c_abi_sdk(self._replace_input(package_input, reviewed_header=bad_header), self.root / "bad.zip")
        with self.assertRaisesRegex(ValueError, "library version is invalid"):
            package_c_abi_sdk(self._replace_input(package_input, library_version="1.2"), self.root / "bad.zip")
        with self.assertRaisesRegex(ValueError, "producer commit is not immutable"):
            package_c_abi_sdk(self._replace_input(package_input, producer_commit="HEAD"), self.root / "bad.zip")
        with self.assertRaisesRegex(ValueError, "must not contain import libraries"):
            package_c_abi_sdk(
                self._replace_input(package_input, gnu_import_library=self._write("bad/lib.a", b"import")),
                self.root / "bad.zip",
            )
        windows = self._package_input("mingwX64")
        with self.assertRaisesRegex(ValueError, "requires a GNU and MSVC import library"):
            package_c_abi_sdk(self._replace_input(windows, msvc_import_library=None), self.root / "bad.zip")

    def test_evidence_round_trip_and_portable_verification_for_every_target(self) -> None:
        for target, spec in TARGET_SPECS.items():
            with self.subTest(target=target):
                package_input = self._package_input(target)
                archive = self.root / f"{target}.zip"
                snapshot = package_c_abi_sdk(package_input, archive)
                values = self._evidence_values(target, snapshot)
                evidence = self.root / f"{target}.json"
                report = write_c_abi_package_evidence(values, evidence)
                verify_c_abi_package_evidence(
                    report,
                    archive,
                    package_input,
                    spec.runner_os,
                    spec.runner_arch,
                    self.consumer_digests,
                )
                self.assertEqual(
                    report,
                    portable_verify_c_abi_package_evidence(
                        target,
                        "1.2.3",
                        "a" * 40,
                        "b" * 40,
                        archive,
                        evidence,
                        self.header,
                        self.license,
                        self.notice,
                        package_input.export_policy,
                        self.consumer_sources,
                    ),
                )
                self.assertEqual(sorted(STRICT_CONSUMERS), [item["source"] for item in report["consumers"]])
                self.assertEqual(sorted(GNU_CONSUMERS) if spec.format == "pe" else [], [
                    item["source"] for item in report["gnuConsumers"]
                ])

    def test_evidence_mutations_reject_schema_digest_tools_and_consumer_claims(self) -> None:
        package_input = self._package_input("mingwX64")
        archive = self.root / "windows.zip"
        snapshot = package_c_abi_sdk(package_input, archive)
        report = build_c_abi_package_evidence(self._evidence_values("mingwX64", snapshot))
        spec = TARGET_SPECS["mingwX64"]

        mutations: list[tuple[str, object]] = []
        unknown = copy.deepcopy(report)
        unknown["unknown"] = True
        mutations.append(("schema mismatch", unknown))
        wrong_digest = copy.deepcopy(report)
        wrong_digest["archiveSha256"] = "0" * 64
        mutations.append(("artifact digest mismatch", wrong_digest))
        missing_tool = copy.deepcopy(report)
        missing_tool["tools"] = missing_tool["tools"][1:]
        mutations.append(("tool evidence inventory mismatch", missing_tool))
        failed_consumer = copy.deepcopy(report)
        failed_consumer["consumers"][0]["exitCode"] = 1
        mutations.append(("strict consumer proof failed", failed_consumer))
        compile_only = copy.deepcopy(report)
        proof = next(item for item in compile_only["consumers"] if item["source"] in COMPILE_ONLY_CONSUMERS)
        proof["linked"] = True
        proof["executed"] = True
        mutations.append(("execution boundary mismatch", compile_only))
        bad_import = copy.deepcopy(report)
        bad_import["importLibraries"][0]["sha256"] = "f" * 64
        mutations.append(("import-library mismatch", bad_import))
        missing_gnu = copy.deepcopy(report)
        missing_gnu["gnuConsumers"] = []
        mutations.append(("GNU strict consumer evidence inventory mismatch", missing_gnu))

        for message, mutation in mutations:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                verify_c_abi_package_evidence(
                    mutation,
                    archive,
                    package_input,
                    spec.runner_os,
                    spec.runner_arch,
                    self.consumer_digests,
                )

        incomplete = dict(self.consumer_digests)
        incomplete.pop(next(iter(incomplete)))
        with self.assertRaisesRegex(ValueError, "source inventory is incomplete"):
            verify_c_abi_package_evidence(
                report, archive, package_input, spec.runner_os, spec.runner_arch, incomplete,
            )

    def test_archive_and_portable_input_mutations_are_rejected(self) -> None:
        package_input = self._package_input("linuxX64")
        archive = self.root / "linux.zip"
        snapshot = package_c_abi_sdk(package_input, archive)
        values = self._evidence_values("linuxX64", snapshot)
        evidence = self.root / "linux.json"
        write_c_abi_package_evidence(values, evidence)

        tampered = self.root / "tampered.zip"
        self._rewrite_zip(archive, tampered, mutate={TARGET_SPECS["linuxX64"].library_path: b"tampered"})
        with self.assertRaises(ValueError):
            inspect_c_abi_package(tampered, package_input)

        noncanonical = self.root / "noncanonical.zip"
        self._rewrite_zip(archive, noncanonical, timestamp=(2020, 1, 1, 0, 0, 0))
        with self.assertRaisesRegex(ValueError, "encoding is not canonical"):
            inspect_c_abi_package(noncanonical, package_input)

        traversal = self.root / "traversal.zip"
        self._rewrite_zip(archive, traversal, extra={"../escape": b"bad"})
        with self.assertRaises(ValueError):
            inspect_c_abi_package(traversal, package_input)

        duplicate = self.root / "duplicate.zip"
        self._rewrite_zip(archive, duplicate, duplicate=C_ABI_PACKAGE_MANIFEST)
        with self.assertRaises(ValueError):
            inspect_c_abi_package(duplicate, package_input)

        pretty_but_different = self.root / "noncanonical.json"
        pretty_but_different.write_text(json.dumps(json.loads(evidence.read_text())) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not canonically encoded"):
            portable_verify_c_abi_package_evidence(
                "linuxX64", "1.2.3", "a" * 40, "b" * 40, archive, pretty_but_different,
                self.header, self.license, self.notice, package_input.export_policy, self.consumer_sources,
            )

        duplicate_sources = list(self.consumer_sources)
        duplicate_sources[-1] = duplicate_sources[0]
        with self.assertRaisesRegex(ValueError, "sources are missing or duplicated"):
            portable_verify_c_abi_package_evidence(
                "linuxX64", "1.2.3", "a" * 40, "b" * 40, archive, evidence,
                self.header, self.license, self.notice, package_input.export_policy, duplicate_sources,
            )

        linked = self.root / "linked-evidence.json"
        try:
            linked.symlink_to(evidence)
        except (NotImplementedError, OSError):
            return
        with self.assertRaises(ValueError):
            portable_verify_c_abi_package_evidence(
                "linuxX64", "1.2.3", "a" * 40, "b" * 40, archive, linked,
                self.header, self.license, self.notice, package_input.export_policy, self.consumer_sources,
            )

    def test_cli_package_inspect_write_verify_and_portable_verify(self) -> None:
        package_input = self._package_input("macosArm64")
        archive = self.root / "cli-package.zip"
        package_arguments = self._package_cli_arguments(package_input)

        package_stdout = io.StringIO()
        with contextlib.redirect_stdout(package_stdout):
            self.assertEqual(0, main(["package", *package_arguments, "--output", str(archive)]))
        package_document = self._canonical_stdout(package_stdout.getvalue())
        self.assertEqual("macosArm64", package_document["target"])
        self.assertTrue(archive.is_file())

        inspect_stdout = io.StringIO()
        inspected_sdk = self.root / "inspected-sdk"
        with contextlib.redirect_stdout(inspect_stdout):
            self.assertEqual(0, main([
                "inspect", *self._package_cli_arguments(package_input, include_library=False),
                "--archive", str(archive),
                "--output-directory", str(inspected_sdk),
            ]))
        self.assertEqual(package_document, self._canonical_stdout(inspect_stdout.getvalue()))
        with zipfile.ZipFile(archive) as package:
            self.assertEqual(
                {name: package.read(name) for name in package.namelist()},
                {
                    path.relative_to(inspected_sdk).as_posix(): path.read_bytes()
                    for path in inspected_sdk.rglob("*")
                    if path.is_file()
                },
            )

        snapshot = inspect_c_abi_package(archive, package_input)
        values = self._evidence_values("macosArm64", snapshot)
        values_path = self.root / "values.json"
        values_path.write_bytes(canonical_json_bytes(self._values_document(values)))
        evidence = self.root / "evidence.json"
        verification_arguments = self._evidence_cli_arguments(package_input, archive)
        evidence_write_stdout = io.StringIO()
        with contextlib.redirect_stdout(evidence_write_stdout):
            self.assertEqual(0, main([
                "evidence-write", *verification_arguments,
                "--values", str(values_path), "--output", str(evidence),
            ]))
        self.assertTrue(evidence.is_file())
        self.assertEqual(
            json.loads(evidence.read_text()),
            self._canonical_stdout(evidence_write_stdout.getvalue()),
        )

        verify_stdout = io.StringIO()
        with contextlib.redirect_stdout(verify_stdout):
            self.assertEqual(0, main([
                "evidence-verify", *verification_arguments, "--evidence", str(evidence),
            ]))
        verified_report = self._canonical_stdout(verify_stdout.getvalue())
        self.assertEqual("passed", verified_report["result"])

        portable_stdout = io.StringIO()
        staged = self.root / "portable-staged"
        with contextlib.redirect_stdout(portable_stdout):
            self.assertEqual(0, main([
                "portable-verify",
                "--target", package_input.target,
                "--library-version", package_input.library_version,
                "--producer-commit", package_input.producer_commit,
                "--producer-tree", package_input.producer_tree,
                "--archive", str(archive),
                "--evidence", str(evidence),
                "--reviewed-header", str(package_input.reviewed_header),
                "--license", str(package_input.license),
                "--notice", str(package_input.notice),
                "--export-policy", str(package_input.export_policy),
                *self._consumer_cli_arguments(),
                "--output-directory", str(staged),
            ]))
        self.assertEqual(verified_report, self._canonical_stdout(portable_stdout.getvalue()))
        with zipfile.ZipFile(archive) as package:
            expected_staged = {name: package.read(name) for name in package.namelist()}
        expected_staged[C_ABI_STAGED_EVIDENCE_PATH] = evidence.read_bytes()
        self.assertEqual(
            expected_staged,
            {
                path.relative_to(staged).as_posix(): path.read_bytes()
                for path in staged.rglob("*")
                if path.is_file()
            },
        )

        process = subprocess.run(
            [sys.executable, "-m", "ci.products.c_abi", "inspect", *package_arguments,
             "--archive", str(archive)],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, process.returncode, process.stderr)
        self.assertEqual(package_document, self._canonical_stdout(process.stdout))

    def test_cli_rejects_noncanonical_unvalidated_and_tampered_evidence_inputs(self) -> None:
        package_input = self._package_input("linuxX64")
        archive = self.root / "cli-linux.zip"
        snapshot = package_c_abi_sdk(package_input, archive)
        values = self._evidence_values("linuxX64", snapshot)
        document = self._values_document(values)
        verification_arguments = self._evidence_cli_arguments(package_input, archive)

        noncanonical = self.root / "noncanonical-values.json"
        noncanonical.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        rejected_output = self.root / "rejected.json"
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            self.assertEqual(1, main([
                "evidence-write", *verification_arguments,
                "--values", str(noncanonical), "--output", str(rejected_output),
            ]))
        self.assertIn("Product JSON bytes are not canonical", error.getvalue())
        self.assertFalse(rejected_output.exists())

        unknown = copy.deepcopy(document)
        unknown["unexpected"] = True
        unknown_path = self.root / "unknown-values.json"
        unknown_path.write_bytes(canonical_json_bytes(unknown))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(1, main([
                "evidence-write", *verification_arguments,
                "--values", str(unknown_path), "--output", str(rejected_output),
            ]))
        self.assertFalse(rejected_output.exists())

        false_claim = copy.deepcopy(document)
        false_claim["archiveSha256"] = "0" * 64
        false_claim_path = self.root / "false-claim-values.json"
        false_claim_path.write_bytes(canonical_json_bytes(false_claim))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(1, main([
                "evidence-write", *verification_arguments,
                "--values", str(false_claim_path), "--output", str(rejected_output),
            ]))
        self.assertFalse(rejected_output.exists())

        valid_values = self.root / "valid-values.json"
        valid_values.write_bytes(canonical_json_bytes(document))
        evidence = self.root / "valid-evidence.json"
        self.assertEqual(0, main([
            "evidence-write", *verification_arguments,
            "--values", str(valid_values), "--output", str(evidence),
        ]))
        evidence.write_bytes(evidence.read_bytes().replace(b'"result": "passed"', b'"result": "failed"'))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(1, main([
                "evidence-verify", *verification_arguments, "--evidence", str(evidence),
            ]))

        process = subprocess.run(
            [sys.executable, "-m", "ci.products.c_abi", "package"],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, process.returncode)

    def test_portable_output_is_immutable_symlink_safe_and_absent_after_failure(self) -> None:
        package_input = self._package_input("macosArm64")
        archive = self.root / "portable.zip"
        snapshot = package_c_abi_sdk(package_input, archive)
        evidence = self.root / "portable-evidence.json"
        write_c_abi_package_evidence(self._evidence_values("macosArm64", snapshot), evidence)

        output = self.root / "sdk"
        portable_verify_c_abi_package_evidence(
            "macosArm64", "1.2.3", "a" * 40, "b" * 40, archive, evidence,
            self.header, self.license, self.notice, package_input.export_policy,
            self.consumer_sources, output,
        )
        before = {
            path.relative_to(output).as_posix(): path.read_bytes()
            for path in output.rglob("*")
            if path.is_file()
        }
        with self.assertRaisesRegex(ValueError, "already exists"):
            portable_verify_c_abi_package_evidence(
                "macosArm64", "1.2.3", "a" * 40, "b" * 40, archive, evidence,
                self.header, self.license, self.notice, package_input.export_policy,
                self.consumer_sources, output,
            )
        self.assertEqual(
            before,
            {
                path.relative_to(output).as_posix(): path.read_bytes()
                for path in output.rglob("*")
                if path.is_file()
            },
        )

        occupied_file = self.root / "occupied-sdk"
        occupied_file.write_text("preserve\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "already exists"):
            portable_verify_c_abi_package_evidence(
                "macosArm64", "1.2.3", "a" * 40, "b" * 40, archive, evidence,
                self.header, self.license, self.notice, package_input.export_policy,
                self.consumer_sources, occupied_file,
            )
        self.assertEqual("preserve\n", occupied_file.read_text(encoding="utf-8"))

        tampered_evidence = self.root / "tampered-portable-evidence.json"
        tampered_evidence.write_bytes(
            evidence.read_bytes().replace(b'"archiveSha256": "', b'"archiveSha256": "0', 1),
        )
        failed_output = self.root / "failed-sdk"
        with self.assertRaises(ValueError):
            portable_verify_c_abi_package_evidence(
                "macosArm64", "1.2.3", "a" * 40, "b" * 40, archive, tampered_evidence,
                self.header, self.license, self.notice, package_input.export_policy,
                self.consumer_sources, failed_output,
            )
        self.assertFalse(failed_output.exists())

        link = self.root / "linked-sdk"
        link_target = self.root / "missing-link-target"
        try:
            link.symlink_to(link_target, target_is_directory=True)
        except (NotImplementedError, OSError):
            return
        with self.assertRaisesRegex(ValueError, "already exists"):
            portable_verify_c_abi_package_evidence(
                "macosArm64", "1.2.3", "a" * 40, "b" * 40, archive, evidence,
                self.header, self.license, self.notice, package_input.export_policy,
                self.consumer_sources, link,
            )
        self.assertTrue(link.is_symlink())

    def test_inspect_output_is_immutable_symlink_safe_and_absent_after_failure(self) -> None:
        package_input = self._package_input("linuxX64")
        archive = self.root / "inspect-source.zip"
        package_c_abi_sdk(package_input, archive)

        output = self.root / "inspect-sdk"
        archive_only_input = self._replace_input(
            package_input,
            library=self.root / "missing-raw-library",
            gnu_import_library=None,
            msvc_import_library=None,
        )
        snapshot = inspect_c_abi_package(archive, archive_only_input, output)
        self.assertEqual(snapshot, inspect_c_abi_package(archive, package_input))
        with zipfile.ZipFile(archive) as package:
            expected = {name: package.read(name) for name in package.namelist()}
        self.assertEqual(
            expected,
            {
                path.relative_to(output).as_posix(): path.read_bytes()
                for path in output.rglob("*")
                if path.is_file()
            },
        )
        with self.assertRaisesRegex(ValueError, "already exists"):
            inspect_c_abi_package(archive, archive_only_input, output)

        occupied_file = self.root / "occupied-inspect"
        occupied_file.write_text("preserve\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "already exists"):
            inspect_c_abi_package(archive, archive_only_input, occupied_file)
        self.assertEqual("preserve\n", occupied_file.read_text(encoding="utf-8"))

        occupied_directory = self.root / "occupied-inspect-directory"
        occupied_directory.mkdir()
        marker = occupied_directory / "marker"
        marker.write_text("preserve\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "already exists"):
            inspect_c_abi_package(archive, archive_only_input, occupied_directory)
        self.assertEqual("preserve\n", marker.read_text(encoding="utf-8"))

        tampered = self.root / "inspect-tampered.zip"
        self._rewrite_zip(
            archive,
            tampered,
            mutate={TARGET_SPECS["linuxX64"].library_path: b"tampered"},
        )
        failed_output = self.root / "failed-inspect-sdk"
        with self.assertRaises(ValueError):
            inspect_c_abi_package(tampered, archive_only_input, failed_output)
        self.assertFalse(failed_output.exists())

        linked = self.root / "linked-inspect-sdk"
        try:
            linked.symlink_to(self.root / "missing-inspect-target", target_is_directory=True)
        except (NotImplementedError, OSError):
            return
        with self.assertRaisesRegex(ValueError, "already exists"):
            inspect_c_abi_package(archive, archive_only_input, linked)
        self.assertTrue(linked.is_symlink())

        windows_input = self._package_input("mingwX64")
        windows_archive = self.root / "inspect-windows.zip"
        package_c_abi_sdk(windows_input, windows_archive)
        windows_output = self.root / "inspect-windows-sdk"
        windows_snapshot = inspect_c_abi_package(
            windows_archive,
            self._replace_input(
                windows_input,
                library=self.root / "missing-windows-dll",
                gnu_import_library=None,
                msvc_import_library=None,
            ),
            windows_output,
        )
        self.assertEqual(
            set(TARGET_SPECS["mingwX64"].import_library_paths),
            set(TARGET_SPECS["mingwX64"].import_library_paths) & set(windows_snapshot.members),
        )

    def _package_input(self, target: str) -> CAbiPackageInput:
        spec = TARGET_SPECS[target]
        library = self._write(f"inputs/{target}/library", f"library:{target}\n".encode())
        export_policy = self._export_policy(target)
        gnu = self._write("inputs/mingwX64/libcodex_agent.dll.a", b"gnu import\n") if spec.format == "pe" else None
        msvc = self._write("inputs/mingwX64/codex_agent.lib", b"msvc import\n") if spec.format == "pe" else None
        return CAbiPackageInput(
            target=target,
            classifier=spec.classifier,
            library_version="1.2.3",
            producer_commit="a" * 40,
            producer_tree="b" * 40,
            reviewed_header=self.header,
            license=self.license,
            notice=self.notice,
            library=library,
            export_policy=export_policy,
            gnu_import_library=gnu,
            msvc_import_library=msvc,
        )

    def _evidence_values(self, target: str, snapshot: object) -> CAbiEvidenceValues:
        spec = TARGET_SPECS[target]
        export_policy = self._export_policy(target)
        symbols = c_abi_expected_symbols(export_policy)
        tools = {tool_id: self._digest(f"tool:{tool_id}".encode()) for tool_id in spec.required_tool_ids}

        def proof(name: str, *, gnu: bool = False) -> CAbiConsumerProof:
            language = "c++17" if name.endswith(".cpp") else "c11"
            compiler = ("gnuCpp" if language == "c++17" else "gnuC") if gnu else (
                "cpp" if language == "c++17" else "c"
            )
            compile_only = name in COMPILE_ONLY_CONSUMERS and not gnu
            return CAbiConsumerProof(
                name,
                self.consumer_digests[name],
                language,
                tools[compiler],
                self._digest(f"compile:{target}:{name}:{gnu}".encode()),
                self._digest(f"artifact:{target}:{name}:{gnu}".encode()),
                not compile_only,
                not compile_only,
                0,
            )

        return CAbiEvidenceValues(
            target=target,
            classifier=spec.classifier,
            library_version="1.2.3",
            producer_commit="a" * 40,
            producer_tree="b" * 40,
            runner_os=spec.runner_os,
            runner_arch=spec.runner_arch,
            archive_sha256=snapshot.archive_sha256,
            header_sha256=snapshot.header_sha256,
            library_sha256=snapshot.library_sha256,
            public_symbols=symbols,
            public_symbol_versions=c_abi_linux_symbol_versions(export_policy) if spec.format == "elf" else {},
            format=spec.format,
            architecture=spec.architecture,
            loader_identity=spec.loader_identity,
            version_identity=spec.version_identity,
            import_libraries={path: snapshot.members[path] for path in spec.import_library_paths},
            tool_proofs=tools,
            consumers=tuple(proof(name) for name in STRICT_CONSUMERS),
            gnu_consumers=tuple(proof(name, gnu=True) for name in GNU_CONSUMERS) if spec.format == "pe" else (),
        )

    def _export_policy(self, target: str) -> Path:
        destination = self.root / "inputs" / target / "exports"
        if destination.exists():
            return destination
        if TARGET_SPECS[target].format == "elf":
            lines: list[str] = []
            for minor in range(13):
                lines.append(f"CODEX_AGENT_1.{minor} {{\n    global:\n")
                lines.extend(
                    f"        {symbol};\n"
                    for index, symbol in enumerate(self.symbols)
                    if index % 13 == minor
                )
                lines.append("};\n")
            contents = "".join(lines).encode()
        else:
            prefix = "_" if TARGET_SPECS[target].format == "mach-o" else ""
            contents = "".join(f"{prefix}{symbol}\n" for symbol in self.symbols).encode()
        return self._write(destination.relative_to(self.root), contents)

    def _replace_input(self, value: CAbiPackageInput, **changes: object) -> CAbiPackageInput:
        fields = {name: getattr(value, name) for name in value.__dataclass_fields__}
        fields.update(changes)
        return CAbiPackageInput(**fields)

    def _package_cli_arguments(
        self,
        value: CAbiPackageInput,
        *,
        include_library: bool = True,
    ) -> list[str]:
        arguments = [
            "--target", value.target,
            "--classifier", value.classifier,
            "--library-version", value.library_version,
            "--producer-commit", value.producer_commit,
            "--producer-tree", value.producer_tree,
            "--reviewed-header", str(value.reviewed_header),
            "--license", str(value.license),
            "--notice", str(value.notice),
            "--export-policy", str(value.export_policy),
        ]
        if include_library:
            arguments.extend(("--library", str(value.library)))
            if value.gnu_import_library is not None:
                arguments.extend(("--gnu-import-library", str(value.gnu_import_library)))
            if value.msvc_import_library is not None:
                arguments.extend(("--msvc-import-library", str(value.msvc_import_library)))
        return arguments

    def _evidence_cli_arguments(self, value: CAbiPackageInput, archive: Path) -> list[str]:
        spec = TARGET_SPECS[value.target]
        return [
            *self._package_cli_arguments(value),
            "--archive", str(archive),
            "--expected-runner-os", spec.runner_os,
            "--expected-runner-arch", spec.runner_arch,
            *self._consumer_cli_arguments(),
        ]

    def _consumer_cli_arguments(self) -> list[str]:
        return [item for source in self.consumer_sources for item in ("--consumer-source", str(source))]

    @staticmethod
    def _values_document(values: CAbiEvidenceValues) -> dict[str, object]:
        report = build_c_abi_package_evidence(values)
        return {
            "schemaVersion": 1,
            "target": values.target,
            "classifier": values.classifier,
            "libraryVersion": values.library_version,
            "producerCommit": values.producer_commit,
            "producerTree": values.producer_tree,
            "runnerOs": values.runner_os,
            "runnerArch": values.runner_arch,
            "archiveSha256": values.archive_sha256,
            "headerSha256": values.header_sha256,
            "librarySha256": values.library_sha256,
            "publicSymbols": report["publicSymbols"],
            "publicSymbolVersions": report["publicSymbolVersions"],
            "format": values.format,
            "architecture": values.architecture,
            "loaderIdentity": values.loader_identity,
            "versionIdentity": values.version_identity,
            "importLibraries": report["importLibraries"],
            "toolProofs": report["tools"],
            "consumers": report["consumers"],
            "gnuConsumers": report["gnuConsumers"],
        }

    def _canonical_stdout(self, contents: str) -> dict[str, object]:
        document = json.loads(contents)
        self.assertEqual(canonical_json_bytes(document).decode(), contents)
        return document

    def _rewrite_zip(
        self,
        source: Path,
        destination: Path,
        *,
        mutate: dict[str, bytes] | None = None,
        extra: dict[str, bytes] | None = None,
        duplicate: str | None = None,
        timestamp: tuple[int, int, int, int, int, int] = C_ABI_ZIP_EPOCH,
    ) -> None:
        with zipfile.ZipFile(source) as archive:
            members = [(name, archive.read(name)) for name in archive.namelist()]
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, contents in members + sorted((extra or {}).items()):
                info = zipfile.ZipInfo(name, timestamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = C_ABI_FILE_MODE << 16
                archive.writestr(info, (mutate or {}).get(name, contents), compresslevel=9)
            if duplicate is not None:
                duplicate_contents = dict(members)[duplicate]
                info = zipfile.ZipInfo(duplicate, timestamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = C_ABI_FILE_MODE << 16
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    archive.writestr(info, duplicate_contents, compresslevel=9)

    def _write(self, relative: str | Path, contents: bytes) -> Path:
        destination = self.root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)
        return destination

    @staticmethod
    def _digest(contents: bytes) -> str:
        return hashlib.sha256(contents).hexdigest()


if __name__ == "__main__":
    unittest.main()
