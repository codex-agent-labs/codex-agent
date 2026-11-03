"""Retained facade execution consistency and deterministic content, NOT admission.

The caller must authenticate original execution/source/host (including the
template and outcome init-script bytes) and the expected inventories. In
particular it must prove the imported Maven repository is the
exact package/Contract binary union and bind that binary to Contract metadata.
Neither a successful report nor these ordinary dictionaries grants that proof.
No Maven verifier, compiler, signer or network operation runs here.
"""

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .inventory import (
    canonical_json_bytes, load_json_bytes, read_regular_file_bytes,
    regular_file_inventory, require_array, require_boolean, require_exact_keys,
    require_integer, require_regular_directory, require_semver, require_sha256,
    require_string,
)
from .receipt import output_inventory_digest, validate_contract_projection, verify_output_manifest_identity
from .registry import SDK_FACADE_CONTRACT_COMPONENTS, SDK_FACADE_TARGETS
from .sdk_maven import MAVEN_GROUPS


FACADE_CONSUMER_TASKS = {
    "android": "compileAndroidMain", "jvm": "compileKotlinJvm",
    "ios-arm64": "compileKotlinIosArm64", "ios-simulator-arm64": "compileKotlinIosSimulatorArm64",
    "macos-arm64": "compileKotlinMacosArm64", "macos-x64": "compileKotlinMacosX64",
    "linux-arm64": "compileKotlinLinuxArm64", "linux-x64": "compileKotlinLinuxX64",
    "windows-x64": "compileKotlinMingwX64", "node-js": "compileKotlinJs",
    "node-wasm": "compileKotlinWasmJs",
}
_OUTCOME_TASK = "verifyCodexStagedConsumerTaskOutcomes"
_FILES = {"report.json", "task-outcomes.json", "process/execution.json",
          "process/stdout.bin", "process/stderr.bin"}
_LIMIT = 16 * 1024 * 1024


def _inventory(root: Path, *, allow_empty: bool = False):
    for ancestor in (root, *root.parents):
        require_regular_directory(ancestor, "Facade input ancestry")
    return regular_file_inventory(root, allow_empty=allow_empty)


def _read(root: Path, name: str):
    return load_json_bytes(read_regular_file_bytes(root / name, max_bytes=_LIMIT,
                                                 reject_symlink_parents=True))


def _original_path(value: Any, label: str) -> str:
    value = require_string(value, label)
    # Original Windows paths remain Windows paths when replayed on another host.
    path = PureWindowsPath(value) if PureWindowsPath(value).drive else PurePosixPath(value)
    if (not path.is_absolute() or ".." in path.parts or str(path) != value
            or any(ord(character) < 32 or ord(character) == 127 for character in value)):
        raise ValueError(f"{label} must be an exact absolute original path")
    return value


def validate_facade_validation_content(value: Any) -> dict[str, Any]:
    """Validate content shape only; return an independent, authority-free value."""
    value = require_exact_keys(value, {
        "schemaVersion", "kind", "component", "target", "sdkVersion", "packageOutputsDigest",
        "contractDigest", "componentDigests", "tasks", "result",
    }, "Facade validation content")
    if (require_integer(value["schemaVersion"], "Facade content schema") != 1
            or value["kind"] != "sdk-facade-validation-content" or value["component"] != "sdk-core"
            or type(value["target"]) is not str or value["target"] not in SDK_FACADE_TARGETS
            or value["result"] != "passed"):
        raise ValueError("Facade validation content identity is invalid")
    require_semver(value["sdkVersion"], "Facade SDK version")
    for field in ("packageOutputsDigest", "contractDigest"):
        require_sha256(value[field], field)
    components = require_array(value["componentDigests"], "Facade Contract components")
    if len(components) != 1:
        raise ValueError("Facade content requires exactly its target Contract component")
    component = require_exact_keys(components[0], {"component", "sha256"}, "Facade Contract component")
    if component["component"] != SDK_FACADE_CONTRACT_COMPONENTS[value["target"]]:
        raise ValueError("Facade content Contract component differs from its target")
    require_sha256(component["sha256"], "Facade Contract component digest")
    if require_array(value["tasks"], "Facade tasks") != [FACADE_CONSUMER_TASKS[value["target"]]]:
        raise ValueError("Facade validation content task mapping differs from the fixed target")
    return load_json_bytes(canonical_json_bytes(value))


def verify_facade_consumer_evidence(
    *, evidence_directory: Path, target: str, sdk_version: str, runtime_version: str,
    contract_version: str, package_stage: Path, contract_stage: Path,
    imported_repository: Path, expected_package_inventory: list,
    expected_contract_inventory: list, expected_repository_inventory: list,
    expected_contract_projection: dict[str, Any], original_context: dict[str, Any],
) -> dict[str, Any]:
    """Check retained observations against independent caller inputs, not trust.

    Contract stage is the deterministic contract/contract/metadata/common payload,
    not raw validation evidence. Original context contains gradleWrapper,
    consumerDirectory, repositoryDirectory, outcomeInitScript and environment.
    Its paths describe the original process, never the current replay machine.
    The returned content deliberately excludes logs, paths, Runtime version and
    execution/cache distinctions. Full source/receipt/host admission is external.
    The caller supplies the full projection from existing Contract verification;
    only its key-bound contractDigest and target componentDigests enter content.
    Whole ZIP/repository inventories remain external, since unrelated Contract
    bytes are deliberately not part of this target's build key.
    """
    if type(target) is not str or target not in SDK_FACADE_TARGETS:
        raise ValueError("Unsupported facade target")
    for value, label in ((sdk_version, "SDK"), (runtime_version, "Runtime"), (contract_version, "Contract")):
        require_semver(value, f"{label} version")
    authority = {"context": original_context, "package": expected_package_inventory,
                 "contract": expected_contract_inventory, "repository": expected_repository_inventory,
                 "projection": expected_contract_projection}
    authority_bytes = canonical_json_bytes(authority)
    expected = load_json_bytes(authority_bytes)
    raw_context = expected["context"]
    if type(raw_context) is not dict:
        raise ValueError("Original facade context must be an object")
    wrapper_value = _original_path(raw_context.get("gradleWrapper"), "gradleWrapper")
    windows = bool(PureWindowsPath(wrapper_value).drive)
    context = require_exact_keys(raw_context, {
        "gradleWrapper", "consumerDirectory", "repositoryDirectory", "outcomeInitScript", "environment",
    } | ({"javaExecutable"} if windows else set()), "Original facade context")
    for field in ("gradleWrapper", "consumerDirectory", "repositoryDirectory", "outcomeInitScript"):
        _original_path(context[field], field)
    launcher = [context["gradleWrapper"]]
    if windows:
        java = PureWindowsPath(_original_path(context["javaExecutable"], "javaExecutable"))
        wrapper = PureWindowsPath(wrapper_value)
        if wrapper.name != "gradlew.bat" or java.name != "java.exe" or not java.is_absolute():
            raise ValueError("Windows facade requires its explicit Java wrapper launcher")
        launcher = [str(java), "-Xmx64m", "-Xms64m", "-Dorg.gradle.appname=gradlew", "-jar",
                    str(wrapper.parent / "gradle/wrapper/gradle-wrapper.jar")]
    if require_exact_keys(context["environment"], set(), "Facade environment") != {}:
        raise ValueError("Facade process requires unchanged empty environment overrides")
    paths = {"evidence": Path(evidence_directory).absolute(), "package": Path(package_stage).absolute(),
             "contract": Path(contract_stage).absolute(), "repository": Path(imported_repository).absolute()}
    before = {name: _inventory(path, allow_empty=name == "evidence") for name, path in paths.items()}

    def unchanged():
        if canonical_json_bytes(authority) != authority_bytes or any(
                _inventory(path, allow_empty=name == "evidence") != before[name]
                for name, path in paths.items()):
            raise ValueError("Facade original inputs or caller expectations changed during verification")

    try:
        for name in ("package", "contract", "repository"):
            if not before[name] or canonical_json_bytes(before[name]) != canonical_json_bytes(expected[name]):
                raise ValueError(f"Facade {name} differs from the caller-owned exact inventory")
        evidence = paths["evidence"]
        if ({row["relativePath"] for row in before["evidence"]} != _FILES
                or {path.name for path in evidence.iterdir()} != {"report.json", "task-outcomes.json", "process"}
                or {path.name for path in (evidence / "process").iterdir()} !=
                {"execution.json", "stdout.bin", "stderr.bin"}):
            raise ValueError("Facade execution capture has an unexpected layout")
        package = verify_output_manifest_identity(paths["package"], "sdk", "sdk-core", "package", "common", sdk_version)
        contract = verify_output_manifest_identity(paths["contract"], "contract", "contract", "metadata", "common", contract_version)
        projection = validate_contract_projection(expected["projection"], "Facade selected Contract projection")
        if (projection["schemaVersion"] != 1 or projection["contractVersion"] != contract_version
                or [row["component"] for row in projection["componentDigests"]] !=
                [SDK_FACADE_CONTRACT_COMPONENTS[target]]
                or len(contract["outputs"]) != 1
                or contract["outputs"][0]["kind"] != "contract-bundle"
                or contract["outputs"][0]["relativePath"] != projection["bundlePath"]
                or contract["outputs"][0]["sha256"] != projection["bundleSha256"]):
            raise ValueError("Facade selected Contract projection differs from the exact target and metadata stage")
        tasks = [FACADE_CONSUMER_TASKS[target]]
        report = require_exact_keys(_read(evidence, "report.json"), {
            "schemaVersion", "result", "sdkVersion", "runtimeVersion", "repository", "mavenGroup", "target", "tasks",
        }, "Facade consumer report")
        if (require_integer(report["schemaVersion"], "Facade report schema") != 6
                or report != {"schemaVersion": 6, "result": "passed", "sdkVersion": sdk_version,
                    "runtimeVersion": runtime_version, "repository": "CENTRAL_STAGING-only",
                    "mavenGroup": MAVEN_GROUPS["sdk-core"], "target": target, "tasks": tasks}):
            raise ValueError("Facade consumer report does not match its original inputs and fixed task")
        command = [*launcher, "-p", context["consumerDirectory"], "--offline", "--no-daemon",
            "--no-configuration-cache", "-PCENTRAL_STAGING=" + context["repositoryDirectory"],
            "-PcodexAgent.sdkVersion=" + sdk_version, "-PcodexAgent.runtimeVersion=" + runtime_version,
            "-PcodexAgent.consumerTarget=" + target, "--init-script", context["outcomeInitScript"],
            *tasks, _OUTCOME_TASK]
        execution = require_exact_keys(_read(evidence, "process/execution.json"), {
            "schemaVersion", "command", "workingDirectory", "environment", "exitCode",
        }, "Facade process")
        if (require_integer(execution["schemaVersion"], "Facade process schema") != 1
                or require_integer(execution["exitCode"], "Facade process exit") != 0
                or execution["command"] != command or execution["workingDirectory"] != context["consumerDirectory"]
                or execution["environment"] != context["environment"]):
            raise ValueError("Facade process is not the exact successful caller-bound invocation")
        outcomes = require_exact_keys(_read(evidence, "task-outcomes.json"), {"schemaVersion", "tasks"}, "Facade outcomes")
        if require_integer(outcomes["schemaVersion"], "Facade outcomes schema") != 1:
            raise ValueError("Unsupported facade outcomes schema")
        rows = [require_exact_keys(row, {"task", "didWork", "upToDate", "skipped", "skipMessage", "failure"},
                                   "Facade task outcome") for row in require_array(outcomes["tasks"], "Facade outcomes")]
        if [row["task"] for row in rows] != tasks:
            raise ValueError("Facade task outcomes do not cover the exact requested tasks")
        for row in rows:
            for field in ("didWork", "upToDate", "skipped"):
                require_boolean(row[field], f"Facade outcome {field}")
            if row["skipMessage"] is not None:
                require_string(row["skipMessage"], "Facade skip message")
            # Keep the original init script predicate, including real UP-TO-DATE
            # and FROM-CACHE observations. Do not replace it with !skipped.
            if row["failure"] is not None or not (row["didWork"] or row["upToDate"]):
                raise ValueError("Facade requested compilation has no successful task outcome")
        return validate_facade_validation_content({
            "schemaVersion": 1, "kind": "sdk-facade-validation-content", "component": "sdk-core",
            "target": target, "sdkVersion": sdk_version,
            "packageOutputsDigest": output_inventory_digest(package["outputs"]),
            "contractDigest": projection["contractDigest"],
            "componentDigests": projection["componentDigests"],
            "tasks": tasks, "result": "passed",
        })
    finally:
        unchanged()
