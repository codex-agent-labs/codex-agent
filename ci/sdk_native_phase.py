"""Run native-wrapper packages inside the caller's verified-input lifetime.

These are unadmitted outputs. The caller must exit all original-input contexts,
recheck both returned inventories, then verify its private candidate receipt with
verify_sdk_package_inputs before publishing a shard. Host validation and metadata
are separate phases; this leaf neither executes nor substitutes for them.
"""

from collections.abc import Callable, Mapping
from contextlib import nullcontext
import hashlib
import importlib.metadata
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import time
from typing import Any
import zipfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_exact_keys, require_integer, require_relative_path, require_semver, require_sha256, sha256_file,
    write_canonical_json,
)
from products.receipt import validate_phase_receipt, validate_producer, verify_output_manifest_identity
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PHASE_INSTANCE_IDS
from products.restore import PHASE_PLAN_KEYS
from products.sdk_native_metadata import _inventory
from products.sdk_package import _require_capability_output_separate
from products.sdk_validation_inputs import _request_inventory
from products.sdk_dotnet_toolchain import verify_sdk_dotnet_toolchain
from products.signing_isolation import require_no_signing_secret


_LIMIT = 16 * 1024 * 1024


def cpp_package_toolchain_policy(root):
    """Exact CMake bytes are an owning C++ package input, not run provenance."""
    raw = read_regular_file_bytes(Path(root) / "codex-agent-bindings/cpp/package-toolchain.json",
                                  max_bytes=8192, reject_symlink_parents=True)
    policy = require_exact_keys(load_canonical_json_bytes(raw), {
        "schemaVersion", "host", "cmakeVersion", "archiveRoot", "archive",
    }, "C++ package toolchain policy")
    if (type(policy["schemaVersion"]) is not int or policy["schemaVersion"] != 1
            or raw != canonical_json_bytes(policy)
            or policy["host"] != {"system": "Linux", "architecture": "X64", "distribution": "ubuntu-24.04"}
            or policy["cmakeVersion"] != "3.31.6"
            or policy["archiveRoot"] != "cmake-3.31.6-linux-x86_64"):
        raise ValueError("Unsupported C++ package toolchain policy")
    asset = require_exact_keys(policy["archive"], {
        "name", "bytes", "sha256", "url", "provenanceUrl", "provenanceSha256",
    }, "CMake official archive")
    origin = "https://github.com/Kitware/CMake/releases/download/v3.31.6/"
    if (asset["name"] != policy["archiveRoot"] + ".tar.gz"
            or asset["url"] != origin + asset["name"]
            or asset["provenanceUrl"] != origin + "cmake-3.31.6-SHA-256.txt"):
        raise ValueError("CMake requires exact official archive/checksum URLs")
    require_integer(asset["bytes"], "CMake archive length", 1)
    require_sha256(asset["sha256"], "CMake archive digest")
    require_sha256(asset["provenanceSha256"], "CMake official checksum metadata digest")
    return policy


def verify_cpp_package_toolchain(root, environ):
    """One full child-side check of provisioned tool bytes; never install here."""
    from products.sdk_dotnet_toolchain import _host_identity

    policy = cpp_package_toolchain_policy(root)
    prefix = Path(environ.get("CODEX_AGENT_CPP_TOOLCHAIN_ROOT", ""))
    archive_path = Path(environ.get("CODEX_AGENT_CPP_TOOLCHAIN_ARCHIVE", ""))
    if (_host_identity() != ("Linux", "X64", "ubuntu-24.04")
            or any(not path.is_absolute() or path.resolve(strict=True) != path
                   for path in (prefix, archive_path))
            or shutil.which("cmake", path=environ.get("PATH", "")) != str(prefix / "bin/cmake")):
        raise ValueError("C++ package host or selected CMake differs from its explicit installation")
    asset = policy["archive"]
    if (archive_path.stat().st_size != asset["bytes"]
            or sha256_file(archive_path, reject_symlink_parents=True) != asset["sha256"]):
        raise ValueError("CMake archive differs from its official pin")
    expected, seen = [], set()
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive:
            name = require_relative_path(member.name.rstrip("/"), "CMake archive member")
            if name in seen:
                raise ValueError("Duplicate CMake archive member")
            seen.add(name)
            if name == policy["archiveRoot"] and member.isdir():
                continue
            if not name.startswith(policy["archiveRoot"] + "/") or not (member.isdir() or member.isfile()):
                raise ValueError("Unsupported CMake archive member")
            if member.isdir():
                continue
            relative = name[len(policy["archiveRoot"]) + 1:]
            # Packaging consumes cmake and its module/template tree, not the GUI,
            # ctest/cpack executables or documentation shipped beside them.
            if relative != "bin/cmake" and not relative.startswith("share/cmake-3.31/"):
                continue
            with archive.extractfile(member) as original:
                digest = "sha256:" + hashlib.file_digest(original, "sha256").hexdigest()
            expected.append({"relativePath": relative, "bytes": member.size, "sha256": digest})
    if not {"bin/cmake", "share/cmake-3.31/Modules/CMake.cmake"} <= {row["relativePath"] for row in expected}:
        raise ValueError("CMake archive lacks its executable/module closure")
    if _inventory(prefix, allow_empty=True) != sorted(expected, key=lambda row: row["relativePath"]):
        raise ValueError("Installed CMake inventory differs from its official archive")
    observed = subprocess.run([str(prefix / "bin/cmake"), "--version"], env=dict(environ),
                              check=True, capture_output=True, text=True, timeout=10).stdout
    if observed.splitlines()[0] != "cmake version " + policy["cmakeVersion"]:
        raise ValueError("Installed CMake version differs from policy")


def python_package_toolchain_policy(root):
    """Python package source input, bound by phaseInputDigest (not a new profile)."""
    raw = read_regular_file_bytes(Path(root) / "codex-agent-bindings/python/package-toolchain.json",
                                  max_bytes=16384, reject_symlink_parents=True)
    policy = require_exact_keys(load_canonical_json_bytes(raw), {
        "schemaVersion", "host", "pythonVersion", "prefix", "interpreter", "wheels",
    }, "Python package toolchain policy")
    if (policy["schemaVersion"] != 1 or raw != canonical_json_bytes(policy)
            or policy["host"] != {"system": "Linux", "architecture": "X64", "distribution": "ubuntu-24.04"}
            or policy["pythonVersion"] != "3.11.17"
            or policy["prefix"] != "/opt/hostedtoolcache/Python/3.11.17/x64"):
        raise ValueError("Unsupported Python package toolchain policy")
    wheels = policy["wheels"]
    expected = {"build": "1.3.0", "packaging": "25.0", "pyproject-hooks": "1.2.0",
                "setuptools": "80.9.0", "wheel": "0.45.1"}
    if (not isinstance(wheels, list) or len(wheels) != len(expected)
            or {w.get("distribution"): w.get("version") for w in wheels} != expected):
        raise ValueError("Python package tool dependency closure differs from policy")
    for asset in (policy["interpreter"], *wheels):
        require_exact_keys(asset, {"name", "bytes", "sha256", "url", "provenanceUrl", "provenanceSha256"}
                           | ({"distribution", "version", "module"} if asset in wheels else set()),
                           "Python package tool artifact")
        name = require_relative_path(asset["name"], "Python tool artifact filename")
        if "/" in name or not asset["url"].startswith(("https://files.pythonhosted.org/", "https://github.com/actions/python-versions/")):
            raise ValueError("Python package tools require exact official artifact URLs")
        require_integer(asset["bytes"], "Python tool artifact length", 1)
        require_sha256(asset["sha256"], "Python tool artifact digest")
        require_sha256(asset["provenanceSha256"], "Python tool official metadata digest")
    return policy


def verify_python_package_identity(root, environ):
    """Cheap parent preflight; the child must still authenticate all tool bytes."""
    from products.sdk_dotnet_toolchain import _host_identity

    policy = python_package_toolchain_policy(root)
    prefix = Path(policy["prefix"])
    executable = prefix / "bin/python3.11"
    selected = shutil.which("python3", path=environ.get("PATH", ""))
    if (_host_identity() != ("Linux", "X64", "ubuntu-24.04")
            or sys.version_info[:3] != tuple(map(int, policy["pythonVersion"].split(".")))
            or Path(sys.prefix) != prefix or Path(sys.base_prefix) != prefix
            or Path(sys.executable).resolve() != executable
            or selected is None or Path(selected).resolve() != executable):
        raise ValueError("Python package interpreter, prefix or actual host differs from policy")
    return policy


def verify_python_package_toolchain(root, environ):
    """Authenticate the actual interpreter/tool code before any product output.

    No downloads, installation or self-issued trust receipts. The full check is
    owned by the package child (including direct CLI use), not repeated by its
    diagnostic-only parent. Retained official archives are never extracted here.
    """
    policy = verify_python_package_identity(root, environ)
    prefix = Path(policy["prefix"])
    cache = Path(environ.get("PYTHONPYCACHEPREFIX", ""))
    if (not cache.is_absolute() or cache.resolve(strict=False) != cache
            or cache.exists() or cache.is_symlink() or sys.pycache_prefix != str(cache)
            or not sys.dont_write_bytecode or environ.get("PYTHONDONTWRITEBYTECODE") != "1"):
        raise ValueError("Python package requires the existing fresh bytecode-cache startup envelope")
    archives = Path(environ.get("CODEX_AGENT_PYTHON_TOOLCHAIN_ARCHIVES", ""))
    if not archives.is_absolute() or archives.resolve(strict=True) != archives:
        raise ValueError("Python package requires an explicit immutable tool archive directory")
    for asset in (policy["interpreter"], *policy["wheels"]):
        path = archives / asset["name"]
        if path.stat().st_size != asset["bytes"] or sha256_file(path, reject_symlink_parents=True) != asset["sha256"]:
            raise ValueError(f"Python tool artifact differs from its official pin: {asset['name']}")

    # The official Actions archive is rooted at the installation prefix. Compare
    # executable/runtime/stdlib bytes, never extract or trust a local stamp.
    runtime_files = set()
    with tarfile.open(archives / policy["interpreter"]["name"], "r:gz") as archive:
        for member in archive:
            name = member.name.removeprefix("./")
            if not name or member.isdir():
                continue
            require_relative_path(name, "Python interpreter archive member")
            selected_runtime = (name == "bin/python3.11" or name.startswith("lib/libpython3.11.")
                                or name.startswith("lib/python3.11/"))
            if (not selected_runtime or "/site-packages/" in name or "/__pycache__/" in name
                    or name.endswith((".pyc", ".pyo"))):
                continue
            if member.issym():
                installed = prefix / name
                if not installed.is_symlink() or os.readlink(installed) != member.linkname:
                    raise ValueError(f"Python runtime link differs from official archive: {name}")
                continue
            if not member.isfile() or name in runtime_files:
                raise ValueError("Python runtime archive contains an unsupported or duplicate member")
            runtime_files.add(name)
            with archive.extractfile(member) as original:
                expected = "sha256:" + hashlib.file_digest(original, "sha256").hexdigest()
            if sha256_file(prefix / name, reject_symlink_parents=True) != expected:
                raise ValueError(f"Installed Python runtime differs from official archive: {name}")
    if not {"bin/python3.11", "lib/libpython3.11.so.1.0", "lib/python3.11/os.py"} <= runtime_files:
        raise ValueError("Official Python archive lacks the required executable/runtime closure")
    _require_python_code_inventory(prefix / "lib/python3.11", {prefix / name for name in runtime_files},
                                   skip={"site-packages", "__pycache__"})

    site = prefix / "lib/python3.11/site-packages"
    for wheel in policy["wheels"]:
        distribution = importlib.metadata.distribution(wheel["distribution"])
        module = importlib.util.find_spec(wheel["module"])
        if (distribution.version != wheel["version"] or Path(distribution.locate_file("")) != site
                or module is None or module.origin != str(site / wheel["module"] / "__init__.py")):
            raise ValueError(f"Python package tool identity differs from policy: {wheel['distribution']}")
        with zipfile.ZipFile(archives / wheel["name"]) as archive:
            seen = set()
            for member in archive.infolist():
                if member.is_dir():
                    continue
                name = require_relative_path(member.filename, "Python tool wheel member")
                if name in seen or (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Python tool wheel contains duplicate or symbolic members")
                seen.add(name)
                # pip rewrites RECORD and adds installer metadata; neither is tool code.
                if name.endswith(".dist-info/RECORD"):
                    continue
                with archive.open(member) as original:
                    expected = "sha256:" + hashlib.file_digest(original, "sha256").hexdigest()
                if sha256_file(site / name, reject_symlink_parents=True) != expected:
                    raise ValueError(f"Installed Python tool differs from official wheel: {name}")
            for name in {name.split("/")[0] for name in seen if "/" in name}:
                _require_python_code_inventory(site / name, {site / name for name in seen},
                                               skip={"__pycache__"})


def _require_python_code_inventory(root, expected, *, skip):
    """Directory entries only: an extra extension may shadow authenticated source."""
    for directory, children, files in os.walk(root):
        children[:] = [name for name in children if name not in skip]
        if any((Path(directory) / name).is_symlink() for name in children):
            raise ValueError("Python tool code directory is symbolic")
        for name in files:
            if name.endswith((".py", ".so", ".pyc", ".pyo")) and Path(directory) / name not in expected:
                raise ValueError(f"Unexpected importable Python tool code: {Path(directory) / name}")


def route(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Fixed portable package host; not a toolchain or execution observation."""
    identity = tuple(plan.get(name) for name in ("product", "component", "phase", "target"))
    if (identity[0] != "sdk" or identity[1] not in NATIVE_BINDINGS
            or identity[2:] != ("package", "desktop") or not any(
                identity == (item.product, item.component, item.phase, item.target)
                for item in PHASE_INSTANCE_IDS)):
        raise ValueError("Only native-wrapper SDK package phases have an implemented worker")
    return {"runner": "ubuntu-24.04", "runnerOs": "Linux", "runnerArch": "X64",
            "toolchainProfile": "sdk-csharp" if identity[1] == "csharp" else None,
            "producerRole": None, "supervisor": None}


def _runtime_originals(runtime_stages, runtime_inventory, predecessor):
    """Check the exact ten supplied originals; return integrity records, not trust."""
    originals, expected_runtime_files = [], set()
    for target in NATIVE_TARGETS:
        for phase in ("package", "validation"):
            identity = ("runtime", target, phase, target)
            value = predecessor(*identity)
            receipt_path = Path(value["receiptPath"])
            raw = read_regular_file_bytes(receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True)
            receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
            if receipt != value["receipt"] or tuple(receipt[name] for name in (
                    "product", "component", "phase", "target")) != identity:
                raise ValueError("Native SDK Runtime predecessor differs from its original receipt")
            original = Path(value["stage"])
            original_inventory = _inventory(original)
            manifest = verify_output_manifest_identity(original, *identity, receipt["productVersion"])
            imported = runtime_stages / target / phase
            if manifest["outputs"] != receipt["outputs"] or _inventory(imported) != original_inventory:
                raise ValueError("Native SDK Runtime stage differs from its original receipt or bytes")
            expected_runtime_files.update(f"{target}/{phase}/{item['relativePath']}"
                                          for item in original_inventory)
            originals.append((original, original_inventory, receipt_path, raw))
    if {item["relativePath"] for item in runtime_inventory} != expected_runtime_files:
        raise ValueError("Native SDK Runtime tree must contain exactly five original package/validation pairs")
    return originals


def _runtime_originals_unchanged(runtime_stages, runtime_inventory, originals):
    if (_inventory(runtime_stages) != runtime_inventory or any(
            _inventory(original) != inventory or read_regular_file_bytes(
                receipt, max_bytes=_LIMIT, reject_symlink_parents=True) != raw
            for original, inventory, receipt, raw in originals)):
        raise ValueError("Original native SDK Runtime inputs changed")


def execute(
    plan: Mapping[str, Any], *, producer: Mapping[str, Any], sdk_version: str,
    repository_root: Path, destination: Path, runtime_stages: Path,
    prepared_sources: Path, staged_sdks: Path,
    compatibility_request: Path,
    predecessor: Callable[[str, str, str, str], Mapping[str, Any]],
    environ: Mapping[str, str],
    csharp_binary_stage: Path | None = None,
    csharp_inspector=None,
) -> dict[str, Any]:
    """Run the fixed package recipe; never finalize or publish evidence.

    The caller authenticates S858/current Contract, the original Runtime source,
    and the single prepared-source/SDK upload bound to its original source plan
    before entering this leaf. Prepared sources are executable package inputs;
    inventory checks cannot grant them source authority. The callback supplies
    original Runtime records, not a replacement for election or trust gates.
    External package-manager dependencies must already be provisioned by the job.
    """
    from native_wrappers import HOSTS, host_classifier
    from product_reuse import (
        _prepare_destination, _runtime_worker_checkout, _worker_process_environment,
    )

    require_no_signing_secret(environ)
    require_exact_keys(plan, PHASE_PLAN_KEYS, "Native SDK package plan")
    if require_integer(plan["schemaVersion"], "Native SDK plan schema", 1) != 1:
        raise ValueError("Unsupported native SDK package plan schema")
    elected_route = route(plan)
    require_sha256(plan["buildKey"], "Elected native SDK build key")
    validate_producer(producer, "Elected native SDK producer")
    require_semver(sdk_version, "Elected SDK version")
    if HOSTS[host_classifier()][2:4] != (elected_route["runnerOs"], elected_route["runnerArch"]):
        raise ValueError("Native SDK package actual host differs from its elected route")
    root = Path(repository_root).resolve(strict=True)
    if plan["component"] == "python":
        verify_python_package_identity(root, environ)
    dotnet_profile = root / "gradle/release/toolchains/sdk/csharp.json" if plan["component"] == "csharp" else None
    if dotnet_profile is not None:
        verify_sdk_dotnet_toolchain(dotnet_profile)
    destination = Path(destination).absolute()
    runtime_stages = Path(runtime_stages)
    prepared_sources, sdks = Path(prepared_sources), Path(staged_sdks)
    request = Path(compatibility_request)
    binary = Path(csharp_binary_stage) if csharp_binary_stage is not None else None
    if (component := plan["component"]) == "csharp" and binary is None:
        raise ValueError("C# package requires an authenticated binary predecessor")
    if component != "csharp" and binary is not None:
        raise ValueError("Only C# may import the C# binary predecessor")
    if component == "csharp":
        from tooling_inspector import require_inspector
        require_inspector(csharp_inspector)
        inspector_directory, inspector_digest = csharp_inspector.handoff()
    elif csharp_inspector is not None:
        raise ValueError("Only C# may use the private inspector")
    if any(not path.is_absolute() for path in (runtime_stages, prepared_sources, sdks, request)):
        raise ValueError("Native SDK inputs must be explicit absolute paths")
    if binary is not None and not binary.is_absolute():
        raise ValueError("C# binary predecessor must be an explicit absolute path")
    runtime_inventory = _inventory(runtime_stages)
    source_inventory, sdk_inventory = _inventory(prepared_sources), _inventory(sdks)
    request_bytes = read_regular_file_bytes(request, max_bytes=_LIMIT, reject_symlink_parents=True)
    request_inventory = _request_inventory(request)
    plan_bytes, producer_bytes = canonical_json_bytes(plan), canonical_json_bytes(producer)
    component, tree = plan["component"], producer["tree"]
    binary_inventory = _inventory(binary) if binary is not None else None
    if binary is not None:
        verify_output_manifest_identity(binary, "sdk", "csharp", "binary", "desktop", sdk_version)
    build = root / "codex-agent-sdk/build"
    stage = build / f"product-stage/sdk/{component}/package"
    # Both supplied trees were produced once by the separately authenticated
    # preparation job. This package worker must never clean or regenerate them.
    _inventory(prepared_sources / component)
    owned = (stage,)
    if any(path.exists() or path.is_symlink() for path in (*owned, destination)):
        raise ValueError("Native SDK worker requires fresh diagnostic and package outputs")

    originals = _runtime_originals(runtime_stages, runtime_inventory, predecessor)
    inputs = [runtime_stages, prepared_sources, sdks, request, *request_inventory,
              *(path for original, _, receipt, _ in originals for path in (original, receipt))]
    if binary is not None:
        inputs.append(binary)
        inputs.append(inspector_directory)
    _require_capability_output_separate(destination, [*owned, *inputs])
    for output in owned:
        _require_capability_output_separate(output, inputs)
    if environ.get("CODEX_AGENT_VERIFIED_DEPENDENCY_FETCH", ""):
        raise ValueError("SDK product commands remain offline after verified dependency seeding")
    environment = _worker_process_environment(root, producer, destination, environ)

    def unchanged():
        require_no_signing_secret(environ)
        _runtime_worker_checkout(root, producer)
        bytecode = destination / "python-bytecode"
        if bytecode.exists() or bytecode.is_symlink():
            raise ValueError("Native SDK private bytecode namespace was modified")
        if canonical_json_bytes(plan) != plan_bytes or canonical_json_bytes(producer) != producer_bytes:
            raise ValueError("Native SDK elected plan or producer changed")
        _runtime_originals_unchanged(runtime_stages, runtime_inventory, originals)
        if _inventory(prepared_sources) != source_inventory or _inventory(sdks) != sdk_inventory:
            raise ValueError("Original prepared native SDK source or staging inputs changed")
        if binary is not None and _inventory(binary) != binary_inventory:
            raise ValueError("Original C# binary predecessor changed")
        if csharp_inspector is not None:
            require_inspector(csharp_inspector)
        if (read_regular_file_bytes(request, max_bytes=_LIMIT, reject_symlink_parents=True) != request_bytes
                or _request_inventory(request) != request_inventory):
            raise ValueError("Original SDK compatibility request or inputs changed")

    unchanged()
    # These exact task-owned paths may be cleaned by Gradle; never reuse one.
    for output in owned:
        _prepare_destination(output, root).rmdir()
    destination = _prepare_destination(destination, root)
    fields = {
        "codexAgent.product": "sdk", "codexAgent.component": component,
        "codexAgent.phase": "package", "codexAgent.target": "desktop",
        "codexAgent.candidateCommit": producer["commit"], "codexAgent.candidateTree": tree,
        "codexAgent.nativeWrapperRuntimeStageRoot": str(runtime_stages),
        "codexAgent.nativeWrapperPackageSourcesRoot": str(prepared_sources),
        "codexAgent.nativeWrapperPackageSdksRoot": str(sdks),
        "codexAgent.sdkCompatibilityRequest": str(request),
        "codexAgent.sdkVersion": sdk_version,
    }
    if binary is not None:
        fields["codexAgent.csharpBinaryStageRoot"] = str(binary)
        fields["codexAgent.csharpDotnetProfile"] = str(dotnet_profile)
        fields["codexAgent.csharpInspectorRoot"] = str(inspector_directory)
        fields["codexAgent.csharpInspectorManifestSha256"] = inspector_digest
    command = _package_command(root, fields)
    unchanged()
    if any(path.exists() or path.is_symlink() for path in owned):
        raise ValueError("Native SDK task output appeared before execution")
    started = time.monotonic_ns()
    return_code, launch_error = None, None
    try:
        with (destination / "gradle.log").open("xb") as log:
            process = subprocess.run(command, cwd=root, env=environment, stdout=log,
                                     stderr=subprocess.STDOUT, check=False)
            return_code = process.returncode
    except OSError as error:
        launch_error = str(error)
        raise
    finally:
        write_canonical_json(destination / "execution.json", {
            "schemaVersion": 1, "producer": dict(producer), "buildKey": plan["buildKey"],
            "command": command, "returnCode": return_code, "launchError": launch_error,
            "elapsedNs": time.monotonic_ns() - started,
        })
        unchanged()
    if return_code != 0:
        raise ValueError(f"Native SDK package failed with exit code {return_code}; see {destination / 'gradle.log'}")
    verify_output_manifest_identity(stage, "sdk", component, "package", "desktop", sdk_version)
    output_inventory = _inventory(stage)
    unchanged()
    return {"stage": stage, "diagnostics": destination, "outputInventory": output_inventory,
            "stagedSdks": sdks, "stagedSdkInventory": sdk_inventory}


def _package_command(root, properties):
    """The exact fixed Python recipe recorded in execution diagnostics."""
    return ["python3", "-B", "-m", "ci.sdk_native_phase", "package", str(root),
            *(f"-P{key}={value}" for key, value in sorted(properties.items()))]


def _package_only(root, fields, environ):
    """Compose unchanged producers; execute owns original-input authentication/lifetimes."""
    from native_wrappers import host_classifier, package_all, require_sdk_version_file
    from product_reuse import _runtime_worker_checkout
    from products.receipt import write_output_manifest
    from sdk_ios_binary import _directory, _file

    require_no_signing_secret(environ)
    if environ.get("CODEX_AGENT_VERIFIED_DEPENDENCY_FETCH", ""):
        raise ValueError("SDK product commands remain offline after verified dependency seeding")
    component = fields.get("codexAgent.component")
    if component not in NATIVE_BINDINGS or host_classifier() != "linux-x64":
        raise ValueError("Python native package requires a native binding on Linux x64")
    csharp_fields = {"codexAgent." + name for name in (
        "csharpBinaryStageRoot", "csharpDotnetProfile", "csharpInspectorRoot",
        "csharpInspectorManifestSha256")} if component == "csharp" else set()
    require_exact_keys(fields, {"codexAgent." + name for name in (
        "product", "component", "phase", "target", "sdkVersion", "candidateCommit", "candidateTree",
        "nativeWrapperRuntimeStageRoot", "nativeWrapperPackageSourcesRoot",
        "nativeWrapperPackageSdksRoot", "sdkCompatibilityRequest")} | csharp_fields,
        "Fixed Python native package properties")
    if (fields["codexAgent.product"], fields["codexAgent.phase"], fields["codexAgent.target"]) != (
            "sdk", "package", "desktop"):
        raise ValueError("Python native package identity differs from the fixed recipe")
    version = require_semver(fields["codexAgent.sdkVersion"], "Python native package version")
    producer = {name: fields["codexAgent.candidate" + name.title()] for name in ("commit", "tree")}
    if any(re.fullmatch("[0-9a-f]{40}", value) is None for value in producer.values()):
        raise ValueError("Python native package source identity is malformed")
    root = Path(root)
    if root.resolve(strict=True) != root:
        raise ValueError("Python native package checkout must be normalized and absolute")
    runtime, sources, sdks = (_directory(Path(fields["codexAgent." + name]), "Original native package input")
                             for name in ("nativeWrapperRuntimeStageRoot", "nativeWrapperPackageSourcesRoot",
                                          "nativeWrapperPackageSdksRoot"))
    request = Path(fields["codexAgent.sdkCompatibilityRequest"])
    if not request.is_absolute() or request.resolve(strict=True) != request:
        raise ValueError("Python native package request must be normalized and absolute")
    version_file = _file(root / "gradle/release/versions/sdk.txt", "Tracked SDK version")
    if require_sdk_version_file(version_file) != version:
        raise ValueError("Python native package differs from the tracked SDK version")
    stage = root / f"codex-agent-sdk/build/product-stage/sdk/{component}/package"
    _require_capability_output_separate(stage, [runtime, sources, sdks, request, version_file])
    if stage.resolve(strict=False) != stage or stage.exists() or stage.is_symlink():
        raise ValueError("Python native package requires fresh normalized outputs")
    package_arguments = {}
    inspector_context = nullcontext()
    if component == "csharp":
        from tooling_inspector import borrowed_inspector
        binary = _directory(Path(fields["codexAgent.csharpBinaryStageRoot"]), "Original C# binary")
        profile = _file(root / "gradle/release/toolchains/sdk/csharp.json", "Tracked .NET profile")
        if str(profile) != fields["codexAgent.csharpDotnetProfile"]:
            raise ValueError("C# package profile differs from the tracked policy")
        inspector = _directory(Path(fields["codexAgent.csharpInspectorRoot"]), "Private C# inspector")
        _require_capability_output_separate(stage, [binary, profile, inspector])
        package_arguments = {"csharp_binary": binary / "outputs/csharp", "dotnet_profile": profile}
        inspector_context = borrowed_inspector(inspector, fields["codexAgent.csharpInspectorManifestSha256"])

    def unchanged():
        require_no_signing_secret(environ)
        _runtime_worker_checkout(root, producer)

    unchanged()
    if component == "python":
        verify_python_package_toolchain(root, environ)
    elif component == "cpp":
        verify_cpp_package_toolchain(root, environ)
    try:
        with inspector_context as capability:
            if capability is not None:
                package_arguments["csharp_inspector"] = capability
            package_all(sources, sdks, stage / "outputs", version, (component,), **package_arguments)
        evidence = stage / "outputs/evidence"
        evidence.mkdir()
        for name in ("sdk-compatibility.json", "sdk-runtime-root.pub"):
            with (evidence / name).open("xb") as output:
                output.write(read_regular_file_bytes(sdks / name, max_bytes=_LIMIT, reject_symlink_parents=True))
        write_output_manifest(stage, "sdk", component, "package", "desktop", version,
                              {"evidence": "outputs/evidence", "package": f"outputs/{component}"})
    finally:
        unchanged()


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) < 2 or arguments[0] != "package":
        raise ValueError("Only the fixed native package recipe is available")
    fields = {}
    for argument in arguments[2:]:
        if not argument.startswith("-P") or "=" not in argument[2:]:
            raise ValueError("Malformed native package property")
        key, value = argument[2:].split("=", 1)
        if key in fields:
            raise ValueError("Duplicate native package property")
        fields[key] = value
    if arguments != _package_command(arguments[1], fields)[4:]:
        raise ValueError("Native package command is not canonical")
    _package_only(arguments[1], fields, os.environ)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
