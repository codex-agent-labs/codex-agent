"""Observe the Core worker host and launchers, never grant execution admission.

These fixed version probes do not prove which Kotlin/AGP/Konan compiler artifacts
executed consumer tasks. Their original output must remain inside the observed
worker upload; neither this record nor caller dictionaries grant hosted trust.
"""

import base64
from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath
import platform
import re
import subprocess

from .inventory import (
    canonical_json_bytes, git_regular_blob_bytes, load_canonical_json_bytes,
    read_regular_file_bytes, require_exact_keys, require_integer, require_regular_directory,
    require_sha256, require_string, run_git, sha256_bytes, write_canonical_json,
)
from .receipt import validate_producer
from .sdk_facade_validation import _inventory, _original_path
from .sdk_package import _require_capability_output_separate
from .signing_isolation import require_no_signing_secret
from .toolchain import _authority, _match, _properties, WRAPPER_PROPERTIES
from .tooling_local import _execution
from .gradle_bootstrap import require_preprovisioned_gradle


@contextmanager
def capture_facade_execution_observation(*, repository, producer, target, environment, destination):
    """Hold exact original source/launcher bytes around the caller's worker.

    JAVA_HOME is mandatory so the probe and Gradle wrapper use one actual
    launcher. Version records use the existing local-tooling raw execution
    schema. Failed/launch-failed probes leave diagnostics, never a success record.
    No product task, signer or Runtime profile is selected here. The wrapper
    distribution must already be provisioned: Gradle's --offline flag does not
    itself prevent the wrapper bootstrap from downloading a missing distribution.
    """
    from native_wrappers import HOSTS, host_classifier
    from product_reuse import _runtime_worker_command
    from sdk_phase import route

    require_no_signing_secret(environment)
    root, output = Path(repository).resolve(strict=True), Path(destination).absolute()
    selected = validate_producer(producer)
    producer_bytes = canonical_json_bytes(producer)
    topology = route({"product": "sdk", "component": "sdk-core", "phase": "validation", "target": target})
    host = {"system": platform.system(), "machine": platform.machine(), "classifier": host_classifier()}
    if HOSTS[host["classifier"]][2:4] != (topology["runnerOs"], topology["runnerArch"]):
        raise ValueError("Core launcher observation differs from the elected actual host")
    for key, value in environment.items():
        if value and (key.startswith("ORG_GRADLE_PROJECT_") or key in {
                "JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "JAVA_OPTS", "GRADLE_OPTS"}):
            raise ValueError("Core launcher observation rejects injected JVM/Gradle options")
    java_home_value = environment.get("JAVA_HOME")
    if type(java_home_value) is not str or not java_home_value:
        raise ValueError("Core launcher observation requires explicit JAVA_HOME")
    java_home = Path(java_home_value)
    if not java_home.is_absolute() or java_home.resolve(strict=True) != java_home:
        raise ValueError("Core JAVA_HOME must be normalized and non-symbolic")
    windows = topology["runnerOs"] == "Windows"
    java = java_home / "bin" / ("java.exe" if windows else "java")
    wrapper = root / ("gradlew.bat" if windows else "gradlew")
    sources = {name: _authority(root, selected["commit"], name) for name in
               (wrapper.name, "gradle/wrapper/gradle-wrapper.jar", WRAPPER_PROPERTIES)}
    properties = _properties(sources[WRAPPER_PROPERTIES], "Core original wrapper properties")
    version = re.search(r"/gradle-([^/]+)-(?:bin|all)\.zip$", properties.get("distributionUrl", ""))
    if version is None or re.fullmatch(r"[0-9a-f]{64}", properties.get("distributionSha256Sum", "")) is None:
        raise ValueError("Core source wrapper lacks an exact version/distribution digest")
    version = version[1]
    java_bytes = read_regular_file_bytes(java, max_bytes=128 * 1024 * 1024, reject_symlink_parents=True)
    if not java_bytes:
        raise ValueError("Core Java launcher is empty")
    if (run_git(root, "rev-parse", f"{selected['commit']}^{{commit}}").strip() != selected["commit"]
            or run_git(root, "rev-parse", f"{selected['commit']}^{{tree}}").strip() != selected["tree"]):
        raise ValueError("Core launcher source differs from its original producer")
    _require_capability_output_separate(output, [root / name for name in sources] + [java_home])
    if output.resolve(strict=False) != output or output.exists() or output.is_symlink():
        raise ValueError("Core launcher observation output must be fresh and normalized")
    for parent in output.parents:
        if parent.exists() or parent.is_symlink():
            require_regular_directory(parent, "Core observation output ancestry")
    before_environment = dict(environment)
    captured = None
    value = value_bytes = None

    def unchanged():
        require_no_signing_secret(environment)
        if (dict(environment) != before_environment or canonical_json_bytes(producer) != producer_bytes
                or platform.system() != host["system"] or platform.machine() != host["machine"]
                or host_classifier() != host["classifier"]
                or read_regular_file_bytes(java, reject_symlink_parents=True) != java_bytes
                or any(_authority(root, selected["commit"], name) != raw for name, raw in sources.items())
                or (captured is not None and _inventory(output, allow_empty=True) != captured)
                or (value is not None and canonical_json_bytes(value) != value_bytes)):
            raise ValueError("Core original launcher/source observation changed")

    unchanged()
    require_preprovisioned_gradle(sources[WRAPPER_PROPERTIES], environment)
    output.mkdir(parents=True)
    prefix = _runtime_worker_command(wrapper, {}, environment, build_directory=".", platform_name="nt" if windows else "posix")
    prefix = prefix[:prefix.index("--offline")]
    commands = {"java-execution.json": [str(java), "-XshowSettings:properties", "-version"],
                "gradle-execution.json": prefix + ["--offline", "--no-daemon", "--version"]}
    outputs = {}
    try:
        for name, command in commands.items():
            try:
                process = subprocess.run(command, cwd=root, env=dict(environment), stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            except OSError as error:
                write_canonical_json(output / "launch-failure.json", {"schemaVersion": 1, "command": command,
                    "error": str(error)})
                raise
            write_canonical_json(output / name, {"schemaVersion": 1, "command": command,
                "exitCode": process.returncode, "outputBase64": base64.b64encode(process.stdout).decode("ascii")})
            _, outputs[name] = _execution(output / name)
            unchanged()
        java_text = outputs["java-execution.json"].decode("utf-8", errors="strict")
        gradle_text = outputs["gradle-execution.json"].decode("utf-8", errors="strict")
        java_arch = _match(r"^\s*os\.arch = (.+)$", java_text, "Core Java architecture")
        if java_arch.lower() not in HOSTS[host["classifier"]][1]:
            raise ValueError("Core Java launcher architecture differs from actual elected host")
        if _match(r"^Gradle ([^\s]+)$", gradle_text, "Core Gradle version") != version:
            raise ValueError("Core observed Gradle version differs from immutable wrapper source")
        value = {"schemaVersion": 1, "kind": "sdk-facade-launcher-observation", "target": target,
            "producer": dict(selected), "host": host,
            "java": {"executable": str(java), "sha256": sha256_bytes(java_bytes), "arch": java_arch,
                "runtimeVersion": _match(r"^\s*java\.runtime\.version = (.+)$", java_text, "Core Java runtime")},
            "gradle": {"wrapper": str(wrapper), "version": version,
                "sourceFiles": [{"relativePath": name, "bytes": len(raw), "sha256": sha256_bytes(raw)}
                                for name, raw in sorted(sources.items())]},
            "executions": _inventory(output)}
        value_bytes = canonical_json_bytes(value)
        write_canonical_json(output / "observation.json", value)
        captured = _inventory(output)
        unchanged()
        yield value
    finally:
        unchanged()


def verify_facade_execution_observation(directory, *, repository, producer, target,
        original_repository_root, original_java_executable=None):
    """Replay captured probe consistency and source identity without running tools.

    The enclosing original upload must already be independently authenticated.
    An observed Java locator/digest is NOT a pinned installation or evidence of
    compiler-task execution. A supplied independent Java locator is compared,
    never replaced. No original machine path is dereferenced on the replay host.
    """
    from native_wrappers import HOSTS
    from product_reuse import _runtime_worker_command
    from sdk_phase import route

    directory, repository = Path(directory), Path(repository)
    before = _inventory(directory)
    if {row["relativePath"] for row in before} != {"observation.json", "java-execution.json", "gradle-execution.json"}:
        raise ValueError("Core launcher observation requires its exact successful capture")
    producer = validate_producer(producer)
    producer_bytes = canonical_json_bytes(producer)
    root_value = _original_path(original_repository_root, "Caller original Core repository")
    path_type = PureWindowsPath if PureWindowsPath(root_value).drive else PurePosixPath
    root = path_type(root_value)
    value = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(directory / "observation.json",
        reject_symlink_parents=True)), {"schemaVersion", "kind", "target", "producer", "host", "java", "gradle", "executions"},
        "Core launcher observation")
    if (require_integer(value["schemaVersion"], "Core launcher schema", 1) != 1
            or value["kind"] != "sdk-facade-launcher-observation" or value["target"] != target
            or value["producer"] != producer):
        raise ValueError("Core launcher observation differs from its original receipt")
    topology = route({"product": "sdk", "component": "sdk-core", "phase": "validation", "target": target})
    host = require_exact_keys(value["host"], {"system", "machine", "classifier"}, "Core observed host")
    matches = [name for name, spec in HOSTS.items() if host["system"] == spec[0]
        and require_string(host["machine"], "Core observed architecture").lower() in spec[1]]
    if matches != [host["classifier"]] or HOSTS[matches[0]][2:4] != (topology["runnerOs"], topology["runnerArch"]):
        raise ValueError("Core observed host differs from the exact target route")
    windows = topology["runnerOs"] == "Windows"
    if bool(PureWindowsPath(root_value).drive) != windows:
        raise ValueError("Core original repository path platform differs from its target")
    java = require_exact_keys(value["java"], {"executable", "sha256", "arch", "runtimeVersion"}, "Core observed Java")
    java_value = _original_path(java["executable"], "Core original Java launcher")
    if bool(PureWindowsPath(java_value).drive) != windows:
        raise ValueError("Core original Java path platform differs from its target")
    java_path_type = PureWindowsPath if PureWindowsPath(java_value).drive else PurePosixPath
    java_path = java_path_type(java_value)
    if (java_path.name != ("java.exe" if windows else "java") or java_path.parent.name != "bin"
            or (original_java_executable is not None and java_value !=
                _original_path(original_java_executable, "Caller original Java launcher"))):
        raise ValueError("Core observed Java differs from its exact original launcher")
    require_sha256(java["sha256"], "Observed original Java bytes")
    gradle = require_exact_keys(value["gradle"], {"wrapper", "version", "sourceFiles"}, "Core observed Gradle")
    wrapper = root / ("gradlew.bat" if windows else "gradlew")
    if gradle["wrapper"] != str(wrapper):
        raise ValueError("Core observed wrapper differs from caller original repository")
    commit = producer["commit"]
    if (run_git(repository, "rev-parse", f"{commit}^{{commit}}").strip() != commit
            or run_git(repository, "rev-parse", f"{commit}^{{tree}}").strip() != producer["tree"]):
        raise ValueError("Core observed source differs from original Git")
    sources = {name: git_regular_blob_bytes(repository, commit, name, max_bytes=4 * 1024 * 1024)
        for name in (wrapper.name, "gradle/wrapper/gradle-wrapper.jar", WRAPPER_PROPERTIES)}
    expected_sources = [{"relativePath": name, "bytes": len(raw), "sha256": sha256_bytes(raw)} for name, raw in sorted(sources.items())]
    if gradle["sourceFiles"] != expected_sources:
        raise ValueError("Core launcher bytes differ from immutable original source")
    properties = _properties(sources[WRAPPER_PROPERTIES], "Original Core wrapper properties")
    version = re.search(r"/gradle-([^/]+)-(?:bin|all)\.zip$", properties.get("distributionUrl", ""))
    if (version is None or version[1] != gradle["version"]
            or re.fullmatch(r"[0-9a-f]{64}", properties.get("distributionSha256Sum", "")) is None):
        raise ValueError("Core observed version differs from immutable wrapper source")
    raw_java, java_output = _execution(directory / "java-execution.json")
    raw_gradle, gradle_output = _execution(directory / "gradle-execution.json")
    prefix = _runtime_worker_command(str(wrapper), {}, {"JAVA_HOME": str(java_path.parent.parent)},
        build_directory=".", platform_name="nt" if windows else "posix")
    prefix = prefix[:prefix.index("--offline")]
    if (raw_java["command"] != [java_value, "-XshowSettings:properties", "-version"]
            or raw_gradle["command"] != prefix + ["--offline", "--no-daemon", "--version"]):
        raise ValueError("Core original probe command differs from fixed launcher policy")
    text = java_output.decode("utf-8", errors="strict")
    if (java["arch"] != _match(r"^\s*os\.arch = (.+)$", text, "Core original Java architecture")
            or java["arch"].lower() not in HOSTS[matches[0]][1]
            or java["runtimeVersion"] != _match(r"^\s*java\.runtime\.version = (.+)$", text, "Core original Java version")
            or gradle["version"] != _match(r"^Gradle ([^\s]+)$", gradle_output.decode("utf-8", errors="strict"), "Core original Gradle")):
        raise ValueError("Core original probe output differs from retained observation")
    if value["executions"] != [row for row in before if row["relativePath"] != "observation.json"]:
        raise ValueError("Core original raw probe bytes differ from retained hashes")
    if _inventory(directory) != before or canonical_json_bytes(producer) != producer_bytes:
        raise ValueError("Core original observation changed during replay")
