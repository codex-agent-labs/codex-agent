"""Prepare pinned third-party inputs; the real installed consumer stays offline.

The caller owns native admission and the Maven directory's verified lifetime.
This source-free fixture resolves dependencies only and grants no acceptance.
"""

import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import time
import xml.etree.ElementTree as ET

from products.inventory import (
    canonical_json_bytes, git_regular_blob_bytes, read_regular_file_bytes,
    require_regular_directory, require_relative_path, require_semver,
    write_canonical_json,
)
from products.restore import memoized_file_inventory
from products.signing_isolation import require_no_signing_secret
from products.toolchain import _metadata_checksum


_POLICY = ".github/actions/sdk-ios-binary-worker/verification-metadata.xml"
_TEMPLATE = ".github/actions/run-ci-lane/installed-consumer/build.gradle.kts"
_BASE_TEMPLATE = "gradle/release/kmp-consumer-template/build.gradle.kts"
_SETTINGS = "gradle/release/kmp-consumer-template/settings.gradle.kts"
_NS = "https://schema.gradle.org/dependency-verification"
_COMMON = ("kotlinBuildToolsApiClasspath", "kotlinCompilerClasspath")
_JVM = ("kotlinCompilerPluginClasspathJvmMain", "jvmCompileClasspath", "jvmRuntimeClasspath")
_CONFIGURATIONS = {
    "common": _COMMON + _JVM[:-1],
    "android": _COMMON + ("kotlinCompilerPluginClasspathAndroidMain", "androidCompileClasspath"),
    "node-js": _COMMON + ("kotlinCompilerPluginClasspathJsMain", "jsCompileClasspath"),
    "node-wasm": _COMMON + ("kotlinCompilerPluginClasspathWasmJsMain", "wasmJsCompileClasspath"),
}
_NATIVE = {"ios-device": ("iosArm64",), "ios-simulator": ("iosSimulatorArm64",),
           "desktop": ("macosArm64", "macosX64", "linuxArm64", "linuxX64", "mingwX64")}
for _target, _prefixes in _NATIVE.items():
    _CONFIGURATIONS[_target] = (_COMMON + (_JVM if _target == "desktop" else ()) +
        ("kotlinNativeBundleConfiguration", "kotlinKlibCommonizerClasspath", "allSourceSetsCompileDependenciesMetadata") +
        tuple(prefix + suffix for prefix in _prefixes
              for suffix in ("CompileKlibraries", "CompilationDependenciesMetadata")))


def _verification_metadata(raw, maven, rows):
    """Add only the caller's exact native-bound Maven files, including module aliases."""
    document = ET.fromstring(raw)
    if document.findtext(f"{{{_NS}}}configuration/{{{_NS}}}verify-metadata") != "true":
        raise ValueError("Installed dependency preparation requires metadata verification")
    components = document.find(f"{{{_NS}}}components")
    if components is None:
        raise ValueError("Installed dependency preparation lacks immutable component pins")
    by_id = {tuple(item.get(key) for key in ("group", "name", "version")): item for item in components}

    def pin(parts, name, digest):
        identity = (".".join(parts[:-3]), parts[-3], parts[-2])
        if identity[0] != "io.github.codex-agent-labs":
            raise ValueError("Installed Maven pins must belong to the authenticated product group")
        component = by_id.get(identity)
        if component is None:
            component = ET.SubElement(components, f"{{{_NS}}}component",
                dict(zip(("group", "name", "version"), identity)))
            by_id[identity] = component
        known = [item for item in component if item.get("name") == name]
        if known:
            if any({value.get("value") for value in item.findall(f"{{{_NS}}}sha256")} != {digest} for item in known):
                raise ValueError("Installed Maven pin conflicts with the native-bound inventory")
        else:
            artifact = ET.SubElement(component, f"{{{_NS}}}artifact", {"name": name})
            ET.SubElement(artifact, f"{{{_NS}}}sha256", {"value": digest,
                "origin": "Current private native-bound installed Maven inventory"})

    inventory = {row["relativePath"]: row for row in rows}
    for row in rows:
        relative = require_relative_path(row["relativePath"], "Installed Maven dependency path")
        parts = Path(relative).parts
        if len(parts) < 4:
            raise ValueError("Installed Maven dependency path lacks its coordinate")
        pin(parts, parts[-1], row["sha256"].removeprefix("sha256:"))
        if relative.endswith(".module"):
            raw_module = read_regular_file_bytes(maven / relative, max_bytes=4 * 1024**2, reject_symlink_parents=True)
            if "sha256:" + hashlib.sha256(raw_module).hexdigest() != row["sha256"]:
                raise ValueError("Installed Maven module changed during dependency preparation")
            for variant in json.loads(raw_module).get("variants", []):
                for artifact in variant.get("files", []):
                    name = require_relative_path(artifact["name"], "Installed module alias")
                    url = require_relative_path(artifact["url"], "Installed module URL")
                    if "/" in name or "/" in url:
                        raise ValueError("Installed module aliases must remain siblings")
                    original = inventory.get((Path(relative).parent / url).as_posix())
                    if original is None:
                        raise ValueError("Installed module alias lacks an exact native-bound file")
                    pin(parts, name, original["sha256"].removeprefix("sha256:"))
    ET.register_namespace("", _NS)
    return ET.tostring(document, encoding="utf-8", xml_declaration=True)


def prepare_dependencies(*, repository, revision, target, maven, maven_inventory,
                         sdk_version, runtime_version, destination, environment):
    """Resolve one fixed target against existing inputs; never compile or copy products."""
    if target not in _CONFIGURATIONS or re.fullmatch(r"[0-9a-f]{40}", revision or "") is None:
        raise ValueError("Installed dependency preparation requires an exact target and source")
    require_semver(sdk_version, "Installed SDK version")
    require_semver(runtime_version, "Installed Runtime version")
    require_no_signing_secret(environment)
    root, maven, destination = Path(repository), Path(maven), Path(destination)
    for path in (root, maven, destination.parent):
        require_regular_directory(path, "Installed dependency preparation directory")
        if not path.is_absolute() or path.resolve(strict=True) != path:
            raise ValueError("Installed dependency preparation paths must be absolute and normalized")
    if (destination.exists() or destination.is_symlink() or destination.is_relative_to(maven)
            or maven.is_relative_to(destination)):
        raise ValueError("Installed dependency preparation requires a fresh independent directory")
    rows = json.loads(canonical_json_bytes(maven_inventory))
    if not rows or memoized_file_inventory(maven) != rows:
        raise ValueError("Installed dependency preparation differs from its native-bound Maven inventory")
    template = _TEMPLATE if target in {"desktop", "node-js", "node-wasm"} else _BASE_TEMPLATE
    inputs = {name: git_regular_blob_bytes(root, revision, name, max_bytes=4 * 1024**2)
              for name in (_POLICY, template, _SETTINGS, "gradlew", "gradle/wrapper/gradle-wrapper.properties")}
    if read_regular_file_bytes(root / "gradlew", reject_symlink_parents=True) != inputs["gradlew"] or \
            read_regular_file_bytes(root / "gradle/wrapper/gradle-wrapper.properties", reject_symlink_parents=True) != inputs["gradle/wrapper/gradle-wrapper.properties"]:
        raise ValueError("Installed dependency wrapper differs from its exact source")
    native_pin = None
    if target in _NATIVE:
        if platform.system() != "Darwin" or platform.machine() not in {"arm64", "aarch64"}:
            raise ValueError("Installed native preparation requires its elected macOS ARM64 host")
        name = "kotlin-native-prebuilt-2.3.10-macos-aarch64.tar.gz"
        native_pin = _metadata_checksum(inputs[_POLICY], name)
        if native_pin != _metadata_checksum(git_regular_blob_bytes(root, revision,
                "runtime/gradle/verification-metadata.xml", max_bytes=4 * 1024**2), name):
            raise ValueError("Installed native compiler archive differs between immutable policies")
    metadata = _verification_metadata(inputs[_POLICY], maven, rows)
    environment = dict(environment)
    java = Path(environment.get("JAVA_HOME", ""))
    if not java.is_absolute():
        raise ValueError("Installed dependency preparation requires absolute JAVA_HOME")
    environment["JAVA_HOME"] = str(java.resolve(strict=True))
    destination.mkdir(mode=0o700)
    fixture = destination / "consumer"
    (fixture / "gradle").mkdir(parents=True)
    (fixture / "settings.gradle.kts").write_bytes(inputs[_SETTINGS])
    (fixture / "build.gradle.kts").write_bytes(inputs[template])
    (fixture / "gradle/verification-metadata.xml").write_bytes(metadata)
    script = fixture / "resolve.gradle"
    script.write_text("gradle.projectsEvaluated {\n"
        "    rootProject.tasks.register('resolveInstalledConsumerDependencies') {\n"
        "        doLast {\n"
        "            " + json.dumps(_CONFIGURATIONS[target]) + ".each { name ->\n"
        "                rootProject.configurations.getByName(name).files.each { file ->\n"
        "                    println('INSTALLED_DEPENDENCY ' + name + ' ' + file.name)\n"
        "                }\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "}\n", encoding="utf-8")
    from product_reuse import _runtime_worker_command
    wrapper = root / "gradlew"
    original = _runtime_worker_command(wrapper, {}, environment, build_directory=".")
    command = [*original[:original.index("--offline")], "-p", str(fixture), "-I", str(script),
        "resolveInstalledConsumerDependencies", "--dependency-verification=strict",
        "--no-daemon", "--no-configuration-cache", "--console=plain",
        "-PCENTRAL_STAGING=" + str(maven), "-PcodexAgent.sdkVersion=" + sdk_version,
        "-PcodexAgent.runtimeVersion=" + runtime_version, "-PcodexAgent.consumerTarget=" + target]
    if native_pin is not None:
        command.append("-Pkotlin.native.distribution.type=prebuilt")
    controls = {path: read_regular_file_bytes(path, max_bytes=4 * 1024**2, reject_symlink_parents=True)
                for path in (fixture / "settings.gradle.kts", fixture / "build.gradle.kts",
                             fixture / "gradle/verification-metadata.xml", script)}

    def unchanged():
        require_no_signing_secret(environment)
        if memoized_file_inventory(maven) != rows:
            raise ValueError("Installed Maven inputs changed during dependency preparation")
        if any(git_regular_blob_bytes(root, revision, name, max_bytes=4 * 1024**2) != raw for name, raw in inputs.items()):
            raise ValueError("Installed dependency source changed during preparation")
        if any(read_regular_file_bytes(path, max_bytes=4 * 1024**2, reject_symlink_parents=True) != raw
               for path, raw in controls.items()) or any(
                read_regular_file_bytes(root / name, reject_symlink_parents=True) != inputs[name]
                for name in ("gradlew", "gradle/wrapper/gradle-wrapper.properties")):
            raise ValueError("Installed dependency execution controls changed during preparation")

    started = time.monotonic_ns()
    try:
        unchanged()
        with (destination / "gradle.log").open("xb") as log:
            result = subprocess.run(command, cwd=root, env=environment, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, check=False)
        if result.returncode:
            raise ValueError(f"Pinned installed dependency preparation failed; see {destination / 'gradle.log'}")
    finally:
        unchanged()
    write_canonical_json(destination / "result.json", {"schemaVersion": 1, "target": target,
        "elapsedNs": time.monotonic_ns() - started, "configurations": list(_CONFIGURATIONS[target]),
        "nativeArchiveSha256": native_pin, "consumerCompiled": False, "productFilesCopied": 0})
