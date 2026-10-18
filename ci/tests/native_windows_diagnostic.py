"""Narrow hosted diagnostics, never a product producer or acceptance receipt."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
CHECKS = ("cpp", "csharp", "dart-identity", "dart-lifecycle")


def commands(check, scratch):
    include = ROOT / "codex-agent-runtime-desktop/native/c-api/include"
    if check == "cpp":
        if os.environ.get("VCToolsVersion", "").rstrip("/\\") != "14.51.36231":
            raise ValueError("Diagnostic requires the failing worker's MSVC 14.51.36231")
        cpp = ROOT / "codex-agent-bindings/cpp"
        return scratch, [["cl", "/nologo", "/Bv", "/std:c++20", "/Zs",
                          "/I" + str(cpp / "include"), "/I" + str(include),
                          str(cpp / "consumer/host_smoke.cpp")]]
    if check == "csharp":
        path = ROOT / "codex-agent-bindings/csharp/tools/produce_sdk_validation_evidence.py"
        spec = importlib.util.spec_from_file_location("csharp_producer", path)
        producer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(producer)
        fixture = producer.SUITE_ROOT / "native/fake_codex_agent.c"
        producer._copy_sources([fixture], scratch / "source")
        return scratch, [["clang", "--version"], [
            "clang", "-std=c11", "-Wall", "-Wextra", "-Werror", "-DCODEX_AGENT_BUILD",
            "-I" + str(include), "-c", str(scratch / "source" / fixture.relative_to(producer.ROOT)),
            "-o", str(scratch / "fixture.obj")]]
    test = {"dart-identity": "runtime_compatibility", "dart-lifecycle": "native_behavior"}[check]
    return ROOT / "codex-agent-bindings/dart", [
        ["dart", "--version"],
        ["dart", "test", "test/" + test + "_test.dart", "-r", "expanded"]]


def diagnose(check, output):
    output.mkdir(parents=True, exist_ok=False)
    report = {"diagnosticOnly": True, "productExecuted": False, "check": check,
              "source": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip(),
              "run": os.environ.get("GITHUB_RUN_ID"), "attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
              "vcToolsVersion": os.environ.get("VCToolsVersion"), "commands": [], "passed": False}
    start = time.monotonic_ns()
    try:
        if sys.platform != "win32":
            raise ValueError("Actual Windows execution is required")
        with tempfile.TemporaryDirectory(prefix="native-host-diagnostic-") as temporary:
            cwd, selected = commands(check, Path(temporary))
            for index, command in enumerate(selected):
                log = output / f"{index}.log"
                item = {"command": command, "cwd": str(cwd), "log": log.name}
                report["commands"].append(item)
                started = time.monotonic_ns()
                try:
                    with log.open("xb") as stream:
                        result = subprocess.run(command, cwd=cwd, stdout=stream,
                                                stderr=subprocess.STDOUT, timeout=600)
                    item["returnCode"] = result.returncode
                    result.check_returncode()
                finally:
                    item["elapsedNs"] = time.monotonic_ns() - started
                    if log.exists():
                        print(log.read_text(errors="replace"), flush=True)
        report["passed"] = True
    except Exception as error:
        report["error"] = type(error).__name__ + ": " + str(error)
    finally:
        report["elapsedNs"] = time.monotonic_ns() - start
        (output / "result.json").write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, sort_keys=True), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("check", choices=CHECKS)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    raise SystemExit(diagnose(args.check, args.output.resolve()))
