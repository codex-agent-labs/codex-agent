"""Exercise the real producer's path checks; no native execution claim."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch


path = Path(__file__).resolve().parents[2] / "codex-agent-bindings/dart/tool/tests/test_sdk_validation_evidence_producer.py"
spec = importlib.util.spec_from_file_location("dart_producer_checks", path)
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)
producer = checks.producer


class DartNativeCommandIdentityTest(unittest.TestCase):
    def test_windows_slash_spellings_preserve_raw_evidence_and_exact_arguments(self):
        for mutation in (None, "wrong-source", "wrong-executable", "extra-argument", "wrong-import", "no-warning"):
            with self.subTest(mutation=mutation), checks.Fixture() as fixture:
                retained = {}

                def run(command, **options):
                    result = fixture.run(command, **options)
                    native = options["cwd"] / "build/parity"
                    for name in (*producer.NATIVE_RECEIPTS, "host-classifier.txt"):
                        file = native / name
                        file.write_bytes(file.read_bytes().replace(b"macos-arm64", b"windows-x64"))
                    leaf = native / producer.LEAF_EVIDENCE
                    for name in ("compiler-execution.json", "boundary-execution.json"):
                        file = leaf / name
                        value = json.loads(file.read_bytes())
                        value["classifier"] = "windows-x64"
                        if name.startswith("compiler"):
                            value["command"] = [r"C:\Program Files\LLVM\bin\clang.exe",
                                str(leaf / "real-leaf-boundary.c").replace("/", "\\"),
                                str(fixture.sdk / "lib/codex_agent.lib"), "-Werror"]
                            if mutation == "wrong-source": value["command"][1] += ".other"
                            if mutation == "wrong-import": value["command"][2] += ".other"
                            if mutation == "no-warning": value["command"].pop()
                        else:
                            value["command"] = [str(leaf / producer.LEAF_EXECUTABLE).replace("/", "\\")]
                            if mutation == "wrong-executable": value["command"][0] += ".other"
                            if mutation == "extra-argument": value["command"].append("unexpected")
                        raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
                        file.write_bytes(raw)
                        retained[name] = raw
                    return result

                with patch.object(producer.subprocess, "run", side_effect=run):
                    if mutation:
                        with self.assertRaises(ValueError): fixture.produce()
                    else:
                        fixture.produce()
                        for name, raw in retained.items():
                            self.assertEqual(raw, (fixture.output / "native-evidence" / producer.LEAF_EVIDENCE / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
