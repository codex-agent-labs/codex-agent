"""Partial Kotlin artifact-pin comparison, never Core execution admission.

The caller independently authenticates policy_revision and the complete original
capture, then composes the existing original source/task/process replay. Only
observed compiler and compiler-plugin JARs are compared here with existing exact
Runtime verification metadata. This neither promotes Runtime producer profiles
to Core policy nor authenticates transformed KGP, AGP, JDK, Android SDK or native
installations. No local cache, submitted hash or current checkout supplies pins.
"""

from pathlib import Path, PureWindowsPath
import re
import tomllib

from .inventory import (
    git_regular_blob_bytes, load_json_bytes, read_regular_file_bytes,
    require_array, require_boolean, require_exact_keys, require_integer,
    require_regular_directory, require_semver, require_string, run_git, sha256_bytes,
)
from .sdk_facade_validation import FACADE_CONSUMER_TASKS, _original_path
from .toolchain import _metadata_checksum, _revision, RUNTIME_VERIFICATION_METADATA, VERSION_CATALOG


_LIMIT = 16 * 1024 * 1024
_TOP = {"schemaVersion", "target", "task", "taskClass", "family", "kotlinVersion", "agpVersion",
        "javaExecutable", "nativeHome", "arguments", "tools", "inputs", "outcome"}
_TOOLS = {"implementation", "compiler", "compilerPlugins", "java", "native", "android"}


def verify_facade_kotlin_compiler_artifacts(*, repository, policy_revision, compiler_inputs) -> None:
    """Compare the non-native Kotlin subset only; successful return grants no authority.

    Original absolute tool paths are identifiers, never opened on the replay
    host. Full observation/task validation and authenticated original execution
    remain mandatory outside this deliberately partial policy comparison.
    """
    revision = _revision(policy_revision)
    root = Path(repository)
    require_regular_directory(root, "Partial Kotlin policy repository")
    if not root.is_absolute() or root.resolve(strict=True) != root:
        raise ValueError("Partial Kotlin policy repository must be absolute and normalized")
    path = Path(compiler_inputs)
    raw = read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True)
    value = require_exact_keys(load_json_bytes(raw), _TOP, "Compiler observation")
    target = value["target"]
    if type(target) is not str or target not in {"jvm", "android", "node-js", "node-wasm"}:
        raise ValueError("Partial Kotlin policy does not support native compiler observations")
    family = "js" if target.startswith("node-") else "jvm"
    task_class = "Kotlin2JsCompile" if family == "js" else "KotlinCompile"
    if (require_integer(value["schemaVersion"], "Compiler schema") != 1
            or value["task"] != FACADE_CONSUMER_TASKS[target] or value["family"] != family
            or value["taskClass"] != f"org.jetbrains.kotlin.gradle.tasks.{task_class}"):
        raise ValueError("Partial Kotlin observation has the wrong task or family")
    observed = {}

    def inventory(item, *, empty=False):
        item = require_exact_keys(item, {"files", "sha256"}, "Compiler inventory")
        rows = require_array(item["files"], "Compiler inventory files")
        if not rows and not empty:
            raise ValueError("Compiler inventory must not be empty")
        paths, encoded = [], bytearray()
        for row in rows:
            row = require_exact_keys(row, {"path", "bytes", "sha256"}, "Compiler inventory row")
            name = _original_path(row["path"], "Original compiler input")
            size = require_integer(row["bytes"], "Compiler input size", 0)
            digest = row["sha256"]
            if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise ValueError("Compiler input digest must be lowercase SHA256")
            if name in observed and observed[name] != row:
                raise ValueError("Contradictory observed compiler inventories")
            observed[name] = row
            paths.append(name)
            encoded.extend(f"{name}\0{size}\0{digest}\n".encode("utf-8"))
        if paths != sorted(set(paths)) or item["sha256"] != sha256_bytes(bytes(encoded)).removeprefix("sha256:"):
            raise ValueError("Compiler inventory digest/order differs")
        return rows

    tools = require_exact_keys(value["tools"], _TOOLS, "Selected compiler tools")
    inventory(tools["implementation"])
    compiler = inventory(tools["compiler"])
    plugins = inventory(tools["compilerPlugins"], empty=True)
    java = inventory(tools["java"])
    if _original_path(value["javaExecutable"], "Selected Java") not in {row["path"] for row in java}:
        raise ValueError("Selected Java is absent from its observed inventory")
    if tools["native"] is not None or value["nativeHome"] is not None:
        raise ValueError("Partial Kotlin policy does not support native compiler observations")
    if target == "android":
        inventory(tools["android"])
        require_semver(value["agpVersion"], "Observed AGP version")
    elif tools["android"] is not None or value["agpVersion"] is not None:
        raise ValueError("Unexpected Android observation")
    inventory(value["inputs"])
    arguments = require_array(value["arguments"], "Compiler arguments")
    if not arguments or any(type(item) is not str or "\0" in item for item in arguments):
        raise ValueError("Compiler arguments are missing or malformed")
    outcome = require_exact_keys(value["outcome"],
        {"task", "didWork", "upToDate", "skipped", "skipMessage", "failure"}, "Compiler outcome")
    for name in ("didWork", "upToDate", "skipped"):
        require_boolean(outcome[name], f"Compiler outcome {name}")
    if (outcome["task"] != value["task"] or outcome["failure"] is not None
            or not (outcome["didWork"] or outcome["upToDate"])
            or (outcome["skipMessage"] is not None and type(outcome["skipMessage"]) is not str)):
        raise ValueError("Compiler task did not satisfy the existing successful outcome predicate")

    sources = {}
    try:
        if run_git(root, "rev-parse", f"{revision}^{{commit}}").strip() != revision:
            raise ValueError("Partial Kotlin policy revision is not the exact commit")
        for name in (VERSION_CATALOG, RUNTIME_VERIFICATION_METADATA):
            sources[name] = git_regular_blob_bytes(root, revision, name, max_bytes=4 * 1024 * 1024)
        catalog = tomllib.loads(sources[VERSION_CATALOG].decode("utf-8", errors="strict"))
        version = require_semver(catalog.get("versions", {}).get("kotlin"), "Pinned Kotlin version")
        if require_string(value["kotlinVersion"], "Observed Kotlin version") != version:
            raise ValueError("Observed Kotlin version differs from explicit policy source")
        names = {}
        for row in compiler + plugins:
            artifact = PureWindowsPath(row["path"]).name
            if not artifact.endswith(".jar"):
                raise ValueError("Partial Kotlin policy requires selected JAR artifacts")
            if artifact in names and names[artifact] != row:
                raise ValueError("Ambiguous observed compiler artifact name")
            names[artifact] = row
            expected = _metadata_checksum(sources[RUNTIME_VERIFICATION_METADATA], artifact)
            if expected != "sha256:" + row["sha256"]:
                raise ValueError(f"Selected Kotlin artifact differs from immutable pin: {artifact}")
        if f"kotlin-compiler-embeddable-{version}.jar" not in {
                PureWindowsPath(row["path"]).name for row in compiler}:
            raise ValueError("Observed compiler classpath lacks its exact pinned Kotlin compiler")
    finally:
        if (read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True) != raw
                or any(git_regular_blob_bytes(root, revision, name, max_bytes=4 * 1024 * 1024) != data
                       for name, data in sources.items())):
            raise ValueError("Partial Kotlin policy source or compiler observation changed")
