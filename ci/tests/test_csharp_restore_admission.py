"""Fixed C# private-restore admission checks; not host execution evidence."""

import base64
import copy
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import tempfile
import unittest

from ci.products.inventory import canonical_json_bytes
from ci.products.receipt import write_output_manifest
from ci.products.sdk_package import _verify_csharp_restore_execution, _verify_native_validation_stage


CONFIG = (b'<?xml version="1.0" encoding="utf-8"?>\n<configuration><packageSources><clear />'
          b'</packageSources><fallbackPackageFolders><clear /></fallbackPackageFolders></configuration>\n')


def execution(target: str) -> dict:
    if target == "windows-x64":
        path_type = PureWindowsPath
        working = path_type(r"C:\worker\.csharp-binding-evidence-fixture\source")
        executable = r"C:\Program Files\dotnet\dotnet.exe"
    else:
        path_type = PurePosixPath
        working = path_type("/private/tmp/.csharp-binding-evidence-fixture/source")
        executable = "/opt/dotnet/dotnet"
    parent = working.parent
    return {
        "schemaVersion": 1,
        "command": [
            executable, "restore", str(working / "tests/CodexAgent.Tests/CodexAgent.Tests.csproj"),
            "--configfile", str(parent / "NuGet.Config"), "--packages", str(parent / "packages"),
            "--force", "--no-cache", "-p:RestoreSources=", "-p:RestoreAdditionalProjectSources=",
            "-p:RestoreFallbackFolders=", "-p:NuGetAudit=false",
        ],
        "workingDirectory": str(working),
        "exitCode": 0,
        "launchError": None,
        "stdoutBase64": base64.b64encode(b"restore completed\n").decode("ascii"),
        "stderrBase64": "",
        "configBase64": base64.b64encode(CONFIG).decode("ascii"),
    }


class CsharpRestoreAdmissionTest(unittest.TestCase):
    def verify(self, value: dict, target: str = "linux-x64") -> None:
        with tempfile.TemporaryDirectory(prefix="csharp-restore-") as temporary:
            path = Path(temporary).resolve() / "execution.json"
            path.write_bytes(canonical_json_bytes(value))
            _verify_csharp_restore_execution(path, target)

    def test_exact_posix_and_windows_recipes_are_accepted(self):
        for target in ("linux-x64", "macos-arm64", "windows-x64"):
            with self.subTest(target=target):
                self.verify(execution(target), target)

    def test_missing_malformed_and_noncanonical_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="csharp-restore-") as temporary:
            path = Path(temporary).resolve() / "execution.json"
            with self.assertRaises(ValueError):
                _verify_csharp_restore_execution(path, "linux-x64")
            for name, contents in (
                ("malformed-json", b"{\n"),
                ("noncanonical-json", json.dumps(execution("linux-x64")).encode("utf-8")),
            ):
                with self.subTest(name=name):
                    path.write_bytes(contents)
                    with self.assertRaises(ValueError):
                        _verify_csharp_restore_execution(path, "linux-x64")

        changed = execution("linux-x64")
        changed["stdoutBase64"] = "YR=="
        with self.assertRaisesRegex(ValueError, "canonical Base64"):
            self.verify(changed)
        changed = execution("linux-x64")
        changed.pop("workingDirectory")
        with self.assertRaises(ValueError):
            self.verify(changed)

    def test_schema_exit_config_command_feed_and_private_source_are_rejected(self):
        baseline = execution("linux-x64")
        cases = []
        for field, value in (("schemaVersion", 2), ("schemaVersion", True),
                             ("exitCode", 1), ("exitCode", True), ("launchError", "failed")):
            changed = copy.deepcopy(baseline)
            changed[field] = value
            cases.append((field, changed, "did not complete successfully"))

        changed = copy.deepcopy(baseline)
        changed["configBase64"] = base64.b64encode(
            b'<configuration><packageSources><add key="public" value="https://example.invalid" />'
            b'</packageSources></configuration>').decode("ascii")
        cases.append(("config", changed, "exact empty-source configuration"))

        changed = copy.deepcopy(baseline)
        changed["command"].remove("--no-cache")
        cases.append(("argv", changed, "fixed offline private recipe"))

        changed = copy.deepcopy(baseline)
        changed["command"][changed["command"].index("-p:RestoreSources=")] = \
            "-p:RestoreSources=https://example.invalid/feed"
        cases.append(("feed", changed, "fixed offline private recipe"))

        changed = copy.deepcopy(baseline)
        source = PurePosixPath("/private/tmp/source")
        changed["workingDirectory"] = str(source)
        changed["command"][2] = str(source / "tests/CodexAgent.Tests/CodexAgent.Tests.csproj")
        changed["command"][4] = str(source.parent / "NuGet.Config")
        changed["command"][6] = str(source.parent / "packages")
        cases.append(("private-source", changed, "private exact-source snapshot"))

        for name, value, message in cases:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, message):
                self.verify(value)

    def test_csharp_validation_stage_requires_the_restore_record(self):
        with tempfile.TemporaryDirectory(prefix="csharp-stage-") as temporary:
            stage = Path(temporary).resolve()
            for relative, contents in (
                ("outputs/installed/evidence.tsv", b"installed\n"),
                ("outputs/capability/test-program", b"compiled fixture\n"),
                ("outputs/capability/dotnet-restore-execution.json",
                 canonical_json_bytes(execution("linux-x64"))),
            ):
                path = stage / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(contents)
            manifest = write_output_manifest(
                stage, "sdk", "csharp", "validation", "linux-x64", "0.2.9",
                {"native-wrapper-installed": "outputs/installed",
                 "native-wrapper-capability": "outputs/capability"},
            )
            receipt = {
                "product": "sdk", "component": "csharp", "phase": "validation",
                "target": "linux-x64", "productVersion": "0.2.9", "outputs": manifest["outputs"],
            }
            _verify_native_validation_stage(stage, receipt, "linux-x64")
            restore = stage / "outputs/capability/dotnet-restore-execution.json"
            restore.write_bytes(canonical_json_bytes({**execution("linux-x64"), "exitCode": 1}))
            receipt["outputs"] = write_output_manifest(
                stage, "sdk", "csharp", "validation", "linux-x64", "0.2.9",
                {"native-wrapper-installed": "outputs/installed",
                 "native-wrapper-capability": "outputs/capability"},
            )["outputs"]
            with self.assertRaisesRegex(ValueError, "did not complete successfully"):
                _verify_native_validation_stage(stage, receipt, "linux-x64")
            restore.unlink()
            receipt["outputs"] = write_output_manifest(
                stage, "sdk", "csharp", "validation", "linux-x64", "0.2.9",
                {"native-wrapper-installed": "outputs/installed",
                 "native-wrapper-capability": "outputs/capability"},
            )["outputs"]
            with self.assertRaises(ValueError):
                _verify_native_validation_stage(stage, receipt, "linux-x64")


if __name__ == "__main__":
    unittest.main()
