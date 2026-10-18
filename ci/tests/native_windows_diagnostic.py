"""Narrow hosted diagnostics, never a product producer or acceptance receipt."""

import argparse
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile


ROOT = Path(__file__).resolve().parents[2]
CONTROL_CHECKS = ("signing-acl", "catalog-newlines", "native-signature", "runtime-exit")
FOLLOWUP_CHECKS = ("signing-workspace", "runtime-host-exit")
CHECKS = ("cpp", "csharp", "dart-identity", "dart-lifecycle", *CONTROL_CHECKS, *FOLLOWUP_CHECKS)


def observed(command, *, check=True):
    started = time.monotonic_ns()
    result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    print(json.dumps({"command": command, "returnCode": result.returncode,
                      "elapsedNs": time.monotonic_ns() - started}), flush=True)
    print(result.stdout.decode(errors="replace"), flush=True)
    if check:
        result.check_returncode()
    return result


def pinned_windows_library(scratch):
    """One small original package, existing source/transport/object authentication.

    Diagnostic execution only: this does not grant current-plan phase admission.
    """
    import product_reuse as reuse
    from products.inventory import sha256_bytes, verified_zip_contents
    from products.restore import _verified_object_snapshot

    token = os.environ["GITHUB_TOKEN"]
    key = "f102a9e45b4aadab1e296870e0d03bb76845a8ee73353d266771c00ddb8ce95b"
    receipt = "fcb9899c9a7f324065a1fe8ddd519f415d707218c61eb4845a9a241f5149962e"
    producer = dict(commit="cc7dd57e0e069d610f93488b29923762cdfa2d44",
        tree="be87ed630f7b844312dbfa34884e9ef10896aee5", runId=39130038248, runAttempt=1,
        event="pull_request", repository="codex-agent-labs/codex-agent", pullRequest=31,
        workflowPath=".github/workflows/ci.yml")
    job = "product-validation / sdk-rust-package-desktop"
    observation, = reuse._observe_ci_producer_jobs({"package": producer},
        jobs_by_phase={"package": job}, token=token,
        trusted_workflow_sha="c89bb8510208a6560a80a4984be6b1a26e72654b",
        build_keys_by_phase={"package": "sha256:" + key})
    selected, = reuse._matching_ci_jobs(observation["jobs"], job, expected_build_key="sha256:" + key)
    if selected["id"] != 117685954378:
        raise ValueError("Diagnostic original job differs from reviewed custody")
    digest = "sha256:bb36797686c89ec49acb2433f7a7fd427905d3adbb0573384eff69b7026d4e0f"
    name = f"codex-agent-sdk-worker-rust-package-desktop-{key}-{producer['tree']}-attempt-1"
    artifact = reuse._contract_ci_upload_metadata(12138113349, digest, name, producer, observation["run"], token)
    reuse._require_artifact_job_window(observation, job, artifact)
    archive = scratch / "original.zip"
    reuse._reuse_contract_ci_upload(artifact, producer, observation["run"], token,
        destination=archive, limit=32 * 1024**2, artifact_sha256=digest, size=artifact["size_in_bytes"])
    object_path = f"shard/v1/objects/sha256/{key}/{receipt}.zip"
    _, contents, _ = verified_zip_contents(archive, retained_paths=(object_path,),
        max_archive_bytes=32 * 1024**2, max_total_bytes=32 * 1024**2,
        max_retained_bytes=32 * 1024**2, require_sorted=False, allow_empty_members=True)
    original = scratch / "object.zip"
    original.write_bytes(contents[object_path])
    with _verified_object_snapshot(original, build_key="sha256:" + key, receipt_sha256="sha256:" + receipt,
            object_sha256="sha256:9a4fadd2804ad1929f8242396ca56548dbb0e35c24eb9e718e5c9346068d3d75") as (snapshot, verified):
        if verified["receipt"]["producer"] != producer:
            raise ValueError("Diagnostic package producer differs from its observed original")
        with zipfile.ZipFile(snapshot) as stage:
            crate = stage.read("stage/outputs/rust/codex-agent-0.8.0.crate")
            compatibility = json.loads(stage.read("stage/outputs/evidence/sdk-compatibility.json"))
    library = windows_library_bytes(crate, compatibility)
    destination = scratch / "codex_agent.dll"
    destination.write_bytes(library)
    print(json.dumps({"originalArtifactId": artifact["id"], "originalSha256": digest,
        "downloadedBytes": artifact["size_in_bytes"], "librarySha256": sha256_bytes(library),
        "phaseAdmissionGranted": False}), flush=True)
    return destination


def windows_library_bytes(crate, compatibility):
    from products.inventory import sha256_bytes
    # Read only the consumed regular member; never extract paths from a tarball.
    with tarfile.open(fileobj=io.BytesIO(crate), mode="r:gz") as archive:
        member, = [row for row in archive.getmembers()
                   if row.name == "codex-agent-0.8.0/native/win-x64/codex_agent.dll"]
        if not member.isfile() or not 0 < member.size <= 64 * 1024**2:
            raise ValueError("Diagnostic Windows library is not a bounded regular member")
        library = archive.extractfile(member).read(member.size + 1)
    variant, = [row for row in compatibility["runtime"]["embeddedVariants"] if row["target"] == "windows-x64"]
    if len(library) != member.size or sha256_bytes(library) != variant["runtimeLibrarySha256"]:
        raise ValueError("Diagnostic library differs from authenticated SDK compatibility")
    return library


RUNTIME_EXIT_PROBE = r'''
import atexit, ctypes, sys
library = ctypes.CDLL(sys.argv[1])
library.codex_agent_abi_version.restype = ctypes.c_uint32
assert library.codex_agent_abi_version() == 0x010d0000
context = ctypes.c_void_p()
for name in ('codex_agent_context_create', 'codex_agent_context_destroy'):
    method = getattr(library, name)
    method.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    method.restype = ctypes.c_int
    assert method(ctypes.byref(context)) == 0, name
assert context.value is None
print('Context create/destroy completed; exit mode=' + sys.argv[2], flush=True)
if sys.argv[3] == 'host':
    import asyncio
    from pathlib import Path
    sys.path.insert(0, str(Path.cwd() / 'codex-agent-bindings/python/src'))
    from codex_agent import ClientInfo, CodexHost, HostStateKind
    from codex_agent._ffi import NativeLibrary
    # Original DLL authenticated by the parent; this is an ABI lifecycle probe,
    # not Python package acceptance or external-library loader authorization.
    async def lifecycle():
        host = CodexHost('unused-unprepared-bundle', 'unused-host-consumer-data',
            ClientInfo('installed-host-smoke', 'Installed Host smoke', '1.0.0'),
            _native=NativeLibrary(library))
        assert host.state.current.kind == HostStateKind.NEW
        await host._void_operation('codex_agent_host_close')
        await host._void_operation('codex_agent_host_close')
        assert host.state.current.kind == HostStateKind.CLOSED
        await host.aclose()
        print('Host create/state/close twice/release/context destroy completed', flush=True)
    asyncio.run(lifecycle())
if sys.argv[2] == 'unload':
    free = ctypes.WinDLL('kernel32', use_last_error=True).FreeLibrary
    free.argtypes = [ctypes.c_void_p]
    free.restype = ctypes.c_int
    def unload():
        print('FreeLibrary entering', flush=True)
        assert free(library._handle)
        print('FreeLibrary returned', flush=True)
    atexit.register(unload)
'''


def control_probe(check, scratch):
    sys.path[:0] = [str(ROOT / "ci"), str(ROOT)]
    scratch.mkdir(exist_ok=False)
    if check in ("signing-acl", "signing-workspace"):
        fixture = ROOT / "codex-agent-bindings/csharp/tests/CodexAgent.Tests/fixtures/sdk-runtime-root-test-only"
        key, payload = scratch / "test-only-key", scratch / "payload"
        shutil.copyfile(fixture, key)
        shutil.copyfile(fixture.with_name(fixture.name + ".pub"), key.with_name(key.name + ".pub"))
        payload.write_bytes(b"Windows test-only signing diagnostic\n")
        signer = str(Path(os.environ["SystemRoot"]) / "System32/OpenSSH/ssh-keygen.exe")
        command = [signer, "-Y", "sign", "-f", str(key), "-n", "codex-agent-sdk-runtime-root-v1", str(payload)]
        observed(["icacls", str(key)])
        observed(command, check=False)
        payload.with_name(payload.name + ".sig").unlink(missing_ok=True)
        user = subprocess.check_output(["whoami"], text=True).strip()
        observed(["icacls", str(key), "/inheritance:r", "/grant:r", user + ":F"])
        observed(command)
    elif check == "catalog-newlines":
        from products.c_abi import describe_c_abi
        from products.inventory import canonical_json_bytes, sha256_bytes
        result = subprocess.run([sys.executable, "-m", "ci.products.c_abi", "describe"],
                                cwd=ROOT, capture_output=True, check=True, timeout=60)
        expected = canonical_json_bytes(describe_c_abi())
        print(json.dumps({"canonical": result.stdout == expected, "tailHex": result.stdout[-4:].hex(),
            "stdoutSha256": sha256_bytes(result.stdout), "expectedSha256": sha256_bytes(expected),
            "crlfOnlyDifference": result.stdout == expected[:-1] + b"\r\n"}), flush=True)
        if result.stdout not in (expected, expected[:-1] + b"\r\n"):
            raise ValueError("Catalog difference is not only final newline translation")
    elif check == "native-signature":
        import reuse_qualification as qualification
        observed(["gh", "--version"])
        commit = "cc7dd57e0e069d610f93488b29923762cdfa2d44"
        report, captured = qualification._fetch_qualification_archive(scratch / "qualification",
            artifact_id=12137458247, artifact_sha256="sha256:614273eea4c84c50c8c41a45d2d82c7467659cfb4a1605608e3e67de49091e5c",
            run_id=39129485152, run_attempt=1, signer_commit=commit, source_commit=commit,
            token=os.environ["GITHUB_TOKEN"], _completed_sdk=True)
        qualification._authenticate_native_subject(captured["completion.json"], captured["bundle.jsonl"],
            "completion.json", signer_commit=commit, source_commit=commit)
        print(json.dumps({"signatureAuthenticated": True, "downloadedBytes": report["downloadedQualificationBytes"],
                          "qualificationIssued": False, "phaseAdmissionGranted": False}), flush=True)
    elif check in ("runtime-exit", "runtime-host-exit"):
        library = pinned_windows_library(scratch)
        # Same authenticated DLL, isolated processes; preserve BOTH outcomes.
        for mode in ("retain", "unload"):
            observed([sys.executable, "-c", RUNTIME_EXIT_PROBE, str(library), mode,
                      "host" if check == "runtime-host-exit" else "context"], check=False)
    else:
        raise ValueError("Unknown control diagnostic")


def commands(check, scratch):
    if check in (*CONTROL_CHECKS, *FOLLOWUP_CHECKS):
        return ROOT, [[sys.executable, str(Path(__file__).resolve()), check, str(scratch / "probe"), "--probe"]]
    include = ROOT / "codex-agent-runtime-desktop/native/c-api/include"
    if check == "cpp":
        if os.environ.get("VCToolsVersion", "").rstrip("/\\") != "14.51.36231":
            raise ValueError("Diagnostic requires the failing worker's MSVC 14.51.36231")
        cpp = ROOT / "codex-agent-bindings/cpp"
        # Exercise Release code generation as well as parsing, without linking.
        return scratch, [["cl", "/nologo", "/Bv", "/std:c++20", "/c",
                          "/O2", "/Ob2", "/MD", "/EHsc", "/W4", "/WX", "/DNDEBUG",
                          "/Fo" + str(scratch / "host_smoke.obj"),
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
    report = {"diagnosticOnly": True, "productPhasesProduced": 0,
              "existingRuntimeExecutionRequested": check in ("runtime-exit", "runtime-host-exit"), "check": check,
              "source": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip(),
              "run": os.environ.get("GITHUB_RUN_ID"), "attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
              "vcToolsVersion": os.environ.get("VCToolsVersion"), "commands": [], "passed": False}
    start = time.monotonic_ns()
    try:
        if sys.platform != "win32":
            raise ValueError("Actual Windows execution is required")
        # Match the C# producer's workspace/build TemporaryDirectory location;
        # user Temp has different inherited ACLs and already passed signing.
        parent = ROOT / "build" if check == "signing-workspace" else None
        if parent is not None:
            parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="native-host-diagnostic-", dir=parent) as temporary:
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
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    if args.probe:
        if sys.platform != "win32":
            raise ValueError("Actual Windows execution is required")
        control_probe(args.check, args.output.resolve())
        raise SystemExit(0)
    raise SystemExit(diagnose(args.check, args.output.resolve()))
