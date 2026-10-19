"""Narrow hosted diagnostics, never a product producer or acceptance receipt."""

import argparse
from concurrent.futures import ThreadPoolExecutor
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
REMAINING_CHECKS = ("signing-private-parent", "rust-host-exit", "signature-initialization", "csharp-loader-security",
                    "cpp-leaf-preprocessor", "rust-fixture-compiler")
CHECKS = ("cpp", "csharp", "dart-identity", "dart-lifecycle", *CONTROL_CHECKS, *FOLLOWUP_CHECKS, *REMAINING_CHECKS)


def observed(command, *, check=True, cwd=ROOT, env=None, input=None):
    started = time.monotonic_ns()
    result = subprocess.run(command, cwd=cwd, env=env, input=input,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    print(json.dumps({"command": command, "returnCode": result.returncode,
                      "elapsedNs": time.monotonic_ns() - started}), flush=True)
    print(result.stdout.decode(errors="replace"), flush=True)
    if check:
        result.check_returncode()
    return result


def pinned_windows_library(scratch, *, crate_path=None):
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
    if crate_path is not None:
        crate_path.write_bytes(crate)
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


RUST_EXIT_PIN_PROBE = r'''
    if std::env::var_os("CODEX_AGENT_DIAGNOSTIC_PIN").is_some() {
        #[link(name = "kernel32")]
        unsafe extern "system" {
            fn GetModuleHandleExW(flags: u32, name: *const u16, module: *mut *mut std::ffi::c_void) -> i32;
        }
        let name: Vec<u16> = "codex_agent.dll".encode_utf16().chain([0]).collect();
        let mut module = std::ptr::null_mut();
        // Diagnostic only: keep the already-loaded module mapped until OS exit,
        // isolating early unloading from the unchanged package's atexit cleanup.
        let pinned = unsafe { GetModuleHandleExW(1, name.as_ptr(), &mut module) };
        assert_ne!(pinned, 0, "pin loaded Runtime: {}", std::io::Error::last_os_error());
        println!("diagnostic Runtime module pinned until process termination");
    }
'''


CSHARP_SIGNING_PROBE = r'''
param([string]$fixture, [string]$root, [string]$signer)
$ErrorActionPreference = 'Stop'
$key = [IO.Path]::Combine($root, 'root-key')
$payload = [IO.Path]::Combine($root, 'root-delegation.json')
[IO.File]::Copy($fixture, $key)
[IO.File]::WriteAllBytes($payload, [Text.Encoding]::UTF8.GetBytes("{} `n"))
& "$env:SystemRoot/System32/icacls.exe" $key
$start = [Diagnostics.ProcessStartInfo]::new($signer)
$start.UseShellExecute = $false
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
foreach ($argument in @('-Y', 'sign', '-f', $key, '-n', 'codex-agent-sdk-runtime-root-v1', $payload)) {
    $start.ArgumentList.Add($argument)
}
$process = [Diagnostics.Process]::Start($start)
$output = $process.StandardOutput.ReadToEnd()
$errorOutput = $process.StandardError.ReadToEnd()
$process.WaitForExit()
@{dotnetRuntime = [Environment]::Version.ToString(); keyPathLength = $key.Length;
  payloadPathLength = $payload.Length; returnCode = $process.ExitCode;
  stdout = $output; stderr = $errorOutput} | ConvertTo-Json -Compress
exit $process.ExitCode
'''


SIGNATURE_INITIALIZATION_PROBE = '''
import sys
from pathlib import Path
sys.path[:0] = [str(Path.cwd() / "ci"), str(Path.cwd())]
from reuse_qualification import _authenticate_native_subject
subject, bundle, commit = sys.argv[1:]
_authenticate_native_subject(Path(subject).read_bytes(), Path(bundle).read_bytes(),
    Path(subject).name.removesuffix(".subject"), signer_commit=commit, source_commit=commit)
print("Production native verification passed; no qualification issued or phase admitted")
'''


def rust_host_probe(scratch):
    from native_wrappers import safe_extract_tar
    crate = scratch / "original.crate"
    pinned_windows_library(scratch, crate_path=crate)
    safe_extract_tar(crate, scratch / "package")
    package = scratch / "package/codex-agent-0.8.0"
    consumer = scratch / "consumer"
    # The same installed consumer as production, no test fixture library.
    shutil.copytree(ROOT / "codex-agent-bindings/rust/consumer", consumer,
                    ignore=shutil.ignore_patterns("target"))
    manifest = consumer / "Cargo.toml"
    raw = manifest.read_text(encoding="utf-8")
    if raw.count('path = ".."') != 1:
        raise ValueError("Rust diagnostic consumer dependency changed")
    manifest.write_text(raw.replace('path = ".."', f'path = "{package.as_posix()}"'), encoding="utf-8")
    host = consumer / "src/bin/host_smoke.rs"
    raw = host.read_text(encoding="utf-8")
    marker = '    println!("installed-crate Host smoke passed with {source}");'
    if raw.count(marker) != 1:
        raise ValueError("Rust diagnostic Host lifecycle changed")
    environment = dict(os.environ, CARGO_TARGET_DIR=str(scratch / "target"))
    for name in ("CODEX_AGENT_LIBRARY", "CODEX_AGENT_DIAGNOSTIC_PIN", "GITHUB_TOKEN", "GH_TOKEN"):
        environment.pop(name, None)
    observed(["rustc", "--version", "--verbose"])
    observed(["cargo", "fetch", "--manifest-path", str(manifest), "--locked"], cwd=scratch, env=environment)
    build = ["cargo", "build", "--manifest-path", str(manifest), "--release", "--locked", "--offline",
             "--bin", "codex-agent-rust-host-smoke"]
    observed(build, cwd=scratch, env=environment)
    executable = str(scratch / "target/release/codex-agent-rust-host-smoke.exe")
    # The earlier instrumented-only single trial could hide an exit race. Keep
    # the actual consumer as the baseline; rebuild only this small test binary.
    for instrumented in (False, True):
        if instrumented:
            host.write_text(raw.replace(marker, marker + "\n" + RUST_EXIT_PIN_PROBE), encoding="utf-8")
            observed(build, cwd=scratch, env=environment)
        for pin in ((False, True) if instrumented else (False,)):
            for trial in range(5):
                print(json.dumps({"rustExitPin": pin, "instrumentedConsumer": instrumented,
                                  "trial": trial, "originalPackageUnchanged": True}), flush=True)
                observed([executable], check=False, cwd=scratch,
                         env=environment | ({"CODEX_AGENT_DIAGNOSTIC_PIN": "1"} if pin else {}))


def csharp_signing_probe(scratch):
    """Compile only the actual suite's signing methods under its .NET 8 SDK."""
    test = ROOT / "codex-agent-bindings/csharp/tests/CodexAgent.Tests"
    raw = (test / "RuntimeLoaderSecurity.cs").read_text(encoding="utf-8")
    keygen = raw.split("            static void Keygen(", 1)[1].split("            static byte[] PublicKey(", 1)[0]
    sign = raw.split("            static void Sign(", 1)[1].split("            var rootKey =", 1)[0]
    # Preserve process arguments/copy behavior; expose stderr discarded by the
    # suite. This is a diagnostic consumer, never package or phase evidence.
    sign = sign.replace("_ = process.StandardError.ReadToEnd();", "Console.WriteLine(process.StandardError.ReadToEnd());")
    source = '''using System;
using System.IO;
using System.Diagnostics;
Console.WriteLine("dotnetRuntime=" + Environment.Version);
var root = Path.Combine(AppContext.BaseDirectory, "runtime-loader-signed");
Directory.CreateDirectory(root);
var key = Path.Combine(root, "root-key");
File.Copy(args[0], key);
if (!OperatingSystem.IsWindows()) File.SetUnixFileMode(key, UnixFileMode.UserRead | UnixFileMode.UserWrite);
Keygen(Path.Combine(root, "release-key"));
var evidence = Path.Combine(root, "codex_agent.dll.evidence");
Directory.CreateDirectory(evidence);
var payload = Path.Combine(evidence, "root-delegation.json");
File.WriteAllBytes(payload, System.Text.Encoding.UTF8.GetBytes("{}\\n"));
Console.WriteLine("keyPathLength=" + key.Length + ";payloadPathLength=" + payload.Length);
Sign(payload, key, "codex-agent-sdk-runtime-root-v1", Path.Combine(evidence, "root-delegation.sig"));
''' + "static void Keygen(" + keygen + "static void Sign(" + sign
    project = scratch / "dotnet8-signing"
    project.mkdir()
    (project / "Program.cs").write_text(source, encoding="utf-8")
    (project / "probe.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net8.0</TargetFramework><OutputType>Exe</OutputType></PropertyGroup></Project>\n', encoding="utf-8")
    (project / "global.json").write_text('{"sdk":{"version":"8.0.419","rollForward":"disable"}}\n', encoding="utf-8")
    (project / "NuGet.Config").write_text('<configuration><packageSources><clear /></packageSources></configuration>\n', encoding="utf-8")
    observed(["dotnet", "--version"], cwd=project)
    observed(["dotnet", "build", "probe.csproj", "--configuration", "Release", "--nologo"], cwd=project)
    observed(["dotnet", str(project / "bin/Release/net8.0/probe.dll"), str(test / "fixtures/sdk-runtime-root-test-only")],
             cwd=project, check=False)


def csharp_security_probe(scratch):
    """Actual loader-security suite composition, not product/capability evidence."""
    import xml.etree.ElementTree as ET
    path = ROOT / "codex-agent-bindings/csharp/tools/produce_sdk_validation_evidence.py"
    spec = importlib.util.spec_from_file_location("csharp_security_producer", path)
    producer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(producer)
    if sys.platform == "win32":
        from ci.sdk_native_validation_workflow import _private_windows_validation_parent
        _private_windows_validation_parent(scratch)
    # Match the producer's nested workspace layout, not the shorter probe that
    # passed while the real worker still failed. This remains diagnostic-only.
    parent = scratch / "validation/outputs"
    parent.mkdir(parents=True)
    # The enclosing diagnostic owns/cleans this tree. Use Python's actual
    # mode-0700 temporary allocation; ordinary mkdir misses the failing ACL.
    scratch = Path(tempfile.mkdtemp(prefix=".csharp-binding-evidence-", dir=parent))
    if sys.platform == "win32":
        observed([str(Path(os.environ["SystemRoot"]) / "System32/icacls.exe"), str(scratch)])
        producer._private_windows_workspace(scratch)
        observed([str(Path(os.environ["SystemRoot"]) / "System32/icacls.exe"), str(scratch)])
    source, program = scratch / "source", scratch / "program"
    producer._copy_sources(producer._source_files(), source)
    project = source / producer.PROJECT.relative_to(producer.ROOT)
    # This diagnostic runs no capability/parity reports and uses only the
    # existing unit fixtures. Do not invent Contract reports to satisfy their
    # unrelated presence guard; remove that guard ONLY from this private copy.
    document = ET.parse(project)
    guard, = [node for node in document.getroot().findall("Target")
              if node.get("Name") == "ValidateDeclaredArtifactInputs"]
    document.getroot().remove(guard)
    document.write(project, encoding="utf-8")
    security = project.parent / "RuntimeLoaderSecurity.cs"
    raw = security.read_text(encoding="utf-8")
    assert raw.count("Console.Error.Write(process.StandardError.ReadToEnd());") == 2
    sign = '                foreach (var argument in new[] { "-Y", "sign",'
    assert raw.count(sign) == 1
    diagnostic = '''                Console.WriteLine("fixtureKeyPath=" + privateKey + ";payloadPath=" + path);
                Console.WriteLine("fixtureKeySha256=" + Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(privateKey))));
'''
    security.write_text(raw.replace(sign, diagnostic + sign), encoding="utf-8")
    entry = project.parent / "Program.cs"
    raw = entry.read_text(encoding="utf-8")
    marker = "var capabilityClaims = ReadCapabilityClaims();"
    assert raw.count(marker) == 1
    entry.write_text(raw.replace(marker, '''if (args is ["--runtime-loader-signed-fixture"])
{
    RuntimeLoaderSecurity.LoadFakeNativeForTests();
    return;
}

''' + marker), encoding="utf-8")
    config = scratch / "NuGet.Config"
    config.write_bytes(producer.RESTORE_CONFIG)
    (source / "global.json").write_text('{"sdk":{"version":"8.0.419","rollForward":"disable"}}\n', encoding="utf-8")
    compatibility = producer.ROOT / "native/sdk-compatibility.json"
    temporary = scratch / "scratch"
    temporary.mkdir()
    environment = dict(os.environ, **producer._fixture_environment(compatibility),
        DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1", DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1",
        DOTNET_CLI_HOME=str(scratch / "dotnet-home"), NUGET_PACKAGES=str(scratch / "packages"),
        NUGET_HTTP_CACHE_PATH=str(scratch / "nuget-http-cache"),
        NUGET_PLUGINS_CACHE_PATH=str(scratch / "nuget-plugins-cache"),
        TMPDIR=str(temporary), TMP=str(temporary), TEMP=str(temporary))
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        environment.pop(name, None)
    observed(["dotnet", "restore", str(project), "--configfile", str(config),
              "--packages", str(scratch / "packages"), "-p:NuGetAudit=false"], cwd=source, env=environment)
    observed(["dotnet", "build", str(project), "--configuration", "Release", "--no-restore",
              "-p:UseSharedCompilation=false",
              "--output", str(program), f"-p:CodexAgentSdkCompatibility={compatibility}",
              f"-p:CodexAgentCSdkRoot={ROOT / 'codex-agent-runtime-desktop/native/c-api'}"], cwd=source, env=environment)
    # The ordinary suite enters here directly, unlike Verify() which first runs
    # snapshot/path tests. Observe that exact startup without repeating Verify().
    observed(["dotnet", str(program / producer.TEST_PROGRAM), "--runtime-loader-signed-fixture"],
             cwd=source, env=environment)


def compiler_probe(check, scratch):
    """Compile only the failing test source, never a product or acceptance receipt."""
    if check == "cpp-leaf-preprocessor":
        if os.environ.get("VCToolsVersion", "").rstrip("/\\") != "14.51.36231":
            raise ValueError("Diagnostic requires the failing worker's MSVC 14.51.36231")
        cpp = ROOT / "codex-agent-bindings/cpp"
        observed(["cl", "/nologo", "/Bv", "/std:c++20", "/c", "/O2", "/Ob2", "/MD",
                  "/EHsc", "/W4", "/WX", "/DNDEBUG", "/Fo" + str(scratch / "leaf.obj"),
                  "/I" + str(cpp / "include"),
                  "/I" + str(ROOT / "codex-agent-runtime-desktop/native/c-api/include"),
                  str(cpp / "tests/leaf_behavior_test.cpp")],
                 cwd=scratch, env=dict(os.environ, CL="/Zc:preprocessor"))
        return
    from ci.sdk_native_validation_workflow import _windows_rust_fixture_compiler
    environment = dict(os.environ)
    adapter = _windows_rust_fixture_compiler(scratch, environment)
    crate = ROOT / "codex-agent-bindings/rust"
    raw = (crate / "tests/lifecycle.rs").read_text()
    start, end = "fn compile_fixture_with_defines(", "\nstruct ThreadWake"
    assert raw.count(start) == raw.count(end) == 1
    function = start + raw.split(start, 1)[1].split(end, 1)[0]
    # Execute the exact source function with std only, including quoted -D
    # arguments and paths containing spaces. No Cargo/dependency/package build.
    source = scratch / "probe.rs"
    source.write_text("use std::path::{Path, PathBuf};\nuse std::process::Command;\n" + function +
        '\nfn main() { for definitions in [&[][..], &["CODEX_AGENT_TEST_OMIT_IDENTITY"][..]] {\n'
        'assert!(compile_fixture_with_defines("mock_codex_agent.c", "diagnostic", definitions).is_file());\n'
        '} }\n', encoding="utf-8")
    temporary = scratch / "fixture temporary with spaces"
    temporary.mkdir()
    environment.update(CARGO_MANIFEST_DIR=str(crate), TMP=str(temporary), TEMP=str(temporary),
                       CODEX_AGENT_TEST_CONTRACT_DIGEST="sha256:" + "a" * 64)
    observed(["rustc", "--version"])
    observed(["clang", "--version"])
    executable = scratch / "probe.exe"
    observed(["rustc", "--edition=2021", str(source), "-o", str(executable)], cwd=scratch, env=environment)
    observed([str(executable)], cwd=scratch, env=environment)
    if any(path.read_bytes() != contents for path, contents in adapter.items()):
        raise ValueError("Diagnostic compiler adapter changed during execution")


def control_probe(check, scratch):
    sys.path[:0] = [str(ROOT / "ci"), str(ROOT)]
    scratch.mkdir(exist_ok=False)
    if check == "csharp-loader-security":
        csharp_security_probe(scratch)
    elif check in ("cpp-leaf-preprocessor", "rust-fixture-compiler"):
        compiler_probe(check, scratch)
    elif check in ("signing-acl", "signing-workspace", "signing-private-parent"):
        if check == "signing-private-parent":
            from ci.sdk_native_validation_workflow import _private_windows_validation_parent
            _private_windows_validation_parent(scratch)
            private_parent = scratch
            scratch = scratch / "validation/outputs/private-test/program/runtime-loader-signed"
            scratch.mkdir(parents=True)
        fixture = ROOT / "codex-agent-bindings/csharp/tests/CodexAgent.Tests/fixtures/sdk-runtime-root-test-only"
        key, payload = scratch / "test-only-key", scratch / "payload"
        shutil.copyfile(fixture, key)
        shutil.copyfile(fixture.with_name(fixture.name + ".pub"), key.with_name(key.name + ".pub"))
        payload.write_bytes(b"Windows test-only signing diagnostic\n")
        signer = str(Path(os.environ["SystemRoot"]) / "System32/OpenSSH/ssh-keygen.exe")
        command = [signer, "-Y", "sign", "-f", str(key), "-n", "codex-agent-sdk-runtime-root-v1", str(payload)]
        observed(["icacls", str(key)])
        observed(command, check=check == "signing-private-parent")
        if check == "signing-private-parent":
            # The Python worker passed Gradle but failed the final verifier's
            # OpenSSH call under its reduced environment. Reuse this signature.
            allowed = scratch / "allowed-signers"
            allowed.write_bytes(b"diagnostic " + key.with_name(key.name + ".pub").read_bytes())
            verify = [signer, "-Y", "verify", "-f", str(allowed), "-I", "diagnostic",
                      "-n", "codex-agent-sdk-runtime-root-v1", "-s", str(payload) + ".sig"]
            names = {"PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL"}
            for reduced in (False, True):
                environment = {k: v for k, v in os.environ.items() if not reduced or k in names}
                environment.update(LC_ALL="C", LANG="C")
                print(json.dumps({"reducedVerifierEnvironment": reduced}), flush=True)
                observed(verify, env=environment, input=payload.read_bytes(), check=False)
            # Win32 OpenSSH init_prog_paths requires ProgramData before its
            # normal stderr initialization. Add only that one missing OS path.
            environment = {**environment, "PROGRAMDATA": os.environ["PROGRAMDATA"]}
            print(json.dumps({"reducedVerifierEnvironment": True, "programDataRestored": True}), flush=True)
            observed(verify, env=environment, input=payload.read_bytes(), check=False)
            # Match the suite's .NET File.Copy and ProcessStartInfo instead of
            # treating the Python-copy/direct-sign probe as equivalent evidence.
            script = scratch / "signing-copy.ps1"
            script.write_text(CSHARP_SIGNING_PROBE, encoding="utf-8")
            observed(["pwsh", "-NoProfile", "-NonInteractive", "-File", str(script),
                      str(key), str(scratch), signer], check=False)
            csharp_signing_probe(private_parent)
            return
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
    elif check == "signature-initialization":
        import reuse_qualification as qualification
        observed(["gh", "--version"])
        subjects = []
        # These are the two already-signed controls used by the failing worker.
        # Only their small original uploads are fetched, once each; no issuer runs.
        for name, artifact, digest, run, commit, completed in (
            ("qualification.json", 12023034412, "3c31cfd94a21ed031716454de44ebf9fbc0069001c6e844e6c212dd87be30af8",
             38846309757, "92793307c0044fdfca6352b26babe2e4bb873bd6", False),
            ("completion.json", 12137458247, "614273eea4c84c50c8c41a45d2d82c7467659cfb4a1605608e3e67de49091e5c",
             39129485152, "cc7dd57e0e069d610f93488b29923762cdfa2d44", True),
        ):
            _, captured = qualification._fetch_qualification_archive(scratch / name,
                artifact_id=artifact, artifact_sha256="sha256:" + digest,
                run_id=run, run_attempt=1, signer_commit=commit, source_commit=commit,
                token=os.environ["GITHUB_TOKEN"], _completed_sdk=completed)
            subject, bundle = scratch / (name + ".subject"), scratch / (name + ".bundle.jsonl")
            subject.write_bytes(captured[name])
            bundle.write_bytes(captured["bundle.jsonl"])
            subjects.append((subject, bundle, commit))
        def verify(item, environment):
            subject, bundle, commit = item
            # Exercise the production verifier, including its bounded startup
            # retry, in separate processes sharing only this trial's trust cache.
            return observed([sys.executable, "-c", SIGNATURE_INITIALIZATION_PROBE,
                str(subject), str(bundle), commit], env=environment, check=False).returncode
        for trial in range(3):
            environment = dict(os.environ, GH_CACHE_DIR=str(scratch / f"trust-cache-{trial}"))
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(lambda item: verify(item, environment), subjects))
            print(json.dumps({"signatureInitializationTrial": trial, "returnCodes": outcomes,
                              "qualificationIssued": False, "phaseAdmissionGranted": False}), flush=True)
    elif check in ("runtime-exit", "runtime-host-exit"):
        library = pinned_windows_library(scratch)
        # Same authenticated DLL, isolated processes; preserve BOTH outcomes.
        for mode in ("retain", "unload"):
            observed([sys.executable, "-c", RUNTIME_EXIT_PROBE, str(library), mode,
                      "host" if check == "runtime-host-exit" else "context"], check=False)
    elif check == "rust-host-exit":
        rust_host_probe(scratch)
    else:
        raise ValueError("Unknown control diagnostic")


def commands(check, scratch):
    if check in (*CONTROL_CHECKS, *FOLLOWUP_CHECKS, *REMAINING_CHECKS):
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


def require_diagnostic_host(check):
    if sys.platform != "win32" and not (sys.platform == "darwin" and check == "signature-initialization"):
        raise ValueError("Actual Windows execution or macOS signature diagnostic is required")


def diagnose(check, output):
    output.mkdir(parents=True, exist_ok=False)
    report = {"diagnosticOnly": True, "productPhasesProduced": 0,
              "existingRuntimeExecutionRequested": check in ("runtime-exit", "runtime-host-exit", "rust-host-exit"), "check": check,
              "source": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip(),
              "run": os.environ.get("GITHUB_RUN_ID"), "attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
              "vcToolsVersion": os.environ.get("VCToolsVersion"), "commands": [], "passed": False}
    start = time.monotonic_ns()
    try:
        require_diagnostic_host(check)
        # Match the C# producer's workspace/build TemporaryDirectory location;
        # user Temp has different inherited ACLs and already passed signing.
        parent = ROOT / "build" if check in ("signing-workspace", "signing-private-parent", "csharp-loader-security") else None
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
        require_diagnostic_host(args.check)
        control_probe(args.check, args.output.resolve())
        raise SystemExit(0)
    raise SystemExit(diagnose(args.check, args.output.resolve()))
