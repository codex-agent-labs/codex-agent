"""Observed local tooling builds, never hosted/release provenance."""

import base64
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile

from .inventory import (
    canonical_json_bytes, git_file_inventory, git_inventory, git_inventory_paths,
    git_regular_blob_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_integer, require_sha256,
    require_string, run_git, sha256_bytes, write_canonical_json,
    snapshot_regular_tree, require_relative_path,
)
from .receipt import validate_producer


RECEIPT = "tooling-build-receipt.json"
SOURCES = "source-inputs.git-tree"
EXECUTIONS = ("java-execution.json", "gradle-execution.json", "build-execution.json")
TOOLCHAINS = ("java-inputs.json", "gradle-inputs.json", "dependency-inputs.json")
KOTLIN_HEAP = "-Dkotlin.daemon.jvm.options=-Xmx2g"
# Same source/resource boundary as the standalone build-logic build. Source tests
# are inventoried too, but no test or downstream product task is executed here.
PATHS = ("gradle/build-logic/**", "gradle/libs.versions.toml", "ci/**",
         "gradle/wrapper/gradle-wrapper.properties",
         "codex-agent-runtime-desktop/native/c-api/abi-contract.json",
         "codex-agent-runtime-desktop/native/c-api/exports/*",
         "codex-agent-bindings/cpp/tools/verify_imported_package.py")


def _source_inventory(repository, commit):
    return git_inventory(repository, commit, PATHS).encode("utf-8")


def _execution(path):
    value = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(path)),
                               {"command", "exitCode", "outputBase64", "schemaVersion"}, "local tooling execution")
    if require_integer(value["schemaVersion"], "execution schema", 1) != 1 or \
            require_integer(value["exitCode"], "execution exit") != 0:
        raise ValueError("Local tooling execution did not succeed")
    if type(value["command"]) is not list or not value["command"]:
        raise ValueError("Local tooling command is missing")
    for argument in value["command"]:
        require_string(argument, "local tooling argument")
    encoded = value["outputBase64"]
    if type(encoded) is not str:
        raise ValueError("Local tooling output is not Base64")
    output = base64.b64decode(encoded, validate=True)
    if base64.b64encode(output).decode("ascii") != encoded:
        raise ValueError("Local tooling output Base64 is noncanonical")
    return value, output


def verify_local_original(root, repository):
    from .tooling import JAR
    receipt = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(root / RECEIPT)),
        {"schemaVersion", "kind", "producer", "sourceInventorySha256", "host", "java", "gradle",
         "executions", "outputs"}, "local tooling receipt")
    if require_integer(receipt["schemaVersion"], "local tooling schema", 1) != 1 or \
            receipt["kind"] != "release-tooling-local-build":
        raise ValueError("Unsupported local tooling receipt")
    producer = validate_producer(receipt["producer"])
    if producer["event"] != "local":
        raise ValueError("Local tooling must not claim a hosted producer")
    if run_git(repository, "rev-parse", f"{producer['commit']}^{{tree}}").strip() != producer["tree"]:
        raise ValueError("Local tooling source commit/tree mismatch")
    sources = read_regular_file_bytes(root / SOURCES)
    if sources != _source_inventory(repository, producer["commit"]) or \
            sha256_bytes(sources) != require_sha256(receipt["sourceInventorySha256"], "local source inventory"):
        raise ValueError("Local tooling original source inventory mismatch")
    host = require_exact_keys(receipt["host"], {"system", "machine"}, "local observed host")
    for value in host.values():
        require_string(value, "local observed host")
    toolchains = []
    for name in TOOLCHAINS:
        raw = read_regular_file_bytes(root / name)
        records = load_canonical_json_bytes(raw)
        if type(records) is not list or not records:
            raise ValueError("Local tooling input inventory must be nonempty")
        for record in records:
            require_exact_keys(record, {"relativePath", "bytes", "sha256"}, "local tooling input")
            require_relative_path(record["relativePath"], "local tooling input path")
            require_integer(record["bytes"], "local tooling input bytes")
            require_sha256(record["sha256"], "local tooling input digest")
        paths = [record["relativePath"] for record in records]
        if paths != sorted(set(paths)):
            raise ValueError("Local tooling inputs must be sorted and unique")
        toolchains.append((sha256_bytes(raw), records))
    java = require_exact_keys(receipt["java"], {"executable", "sha256", "installationDigest"}, "local Java")
    require_string(java["executable"], "local Java executable")
    require_sha256(java["sha256"], "local Java executable digest")
    gradle = require_exact_keys(receipt["gradle"],
        {"launcher", "version", "installationDigest", "userHome", "dependencyInputsDigest"}, "local Gradle")
    require_string(gradle["launcher"], "local Gradle launcher")
    require_sha256(gradle["installationDigest"], "local Gradle installation digest")
    if (java["installationDigest"], gradle["installationDigest"], gradle["dependencyInputsDigest"]) != \
            tuple(digest for digest, _ in toolchains):
        raise ValueError("Local tooling compiler/dependency inventory binding mismatch")
    java_records = {item["relativePath"]: item for item in toolchains[0][1]}
    java_name = "bin/" + java["executable"].replace("\\", "/").rsplit("/", 1)[-1]
    if java_records.get(java_name, {}).get("sha256") != java["sha256"]:
        raise ValueError("Local Java executable is absent from its exact installation")
    wrapper = git_regular_blob_bytes(repository, producer["commit"], PATHS[3], max_bytes=8192)
    match = re.search(rb"/gradle-([0-9.]+)-bin\.zip", wrapper)
    if match is None or gradle["version"] != match[1].decode():
        raise ValueError("Local Gradle version differs from source wrapper")
    execution_records = []
    values = []
    for name in EXECUTIONS:
        value, output = _execution(root / name)
        values.append(value)
        contents = read_regular_file_bytes(root / name)
        execution_records.append({"relativePath": name, "bytes": len(contents), "sha256": sha256_bytes(contents)})
        if name == "gradle-execution.json" and f"Gradle {gradle['version']}".encode() not in output.splitlines():
            raise ValueError("Observed local Gradle version is incorrect")
    prefix = [java["executable"], "-classpath", gradle["launcher"], "org.gradle.launcher.GradleMain"]
    if values[0]["command"] != [java["executable"], "-XshowSettings:properties", "-version"] or \
            values[1]["command"] != prefix + ["--version"]:
        raise ValueError("Local tooling observer command mismatch")
    command = values[2]["command"]
    if command[:4] != prefix or len(command) != 13 or command[4:6] != ["--offline", "--no-daemon"] or \
            command[6:8] != ["--no-configuration-cache", "--project-dir"] or \
            not command[8].replace("\\", "/").endswith("/gradle/build-logic") or \
            command[9:11] != ["--gradle-user-home", gradle["userHome"]] or command[11:] != [KOTLIN_HEAP, "releaseToolingJar"]:
        raise ValueError("Local tooling build command is not the fixed offline task")
    if receipt["executions"] != execution_records:
        raise ValueError("Local tooling execution inventory mismatch")
    jar = read_regular_file_bytes(root / JAR, reject_symlink_parents=True)
    if not jar or receipt["outputs"] != [{"relativePath": JAR, "bytes": len(jar), "sha256": sha256_bytes(jar)}]:
        raise ValueError("Local tooling original JAR inventory mismatch")
    inventory = regular_file_inventory(root, allow_empty=True)
    if {item["relativePath"] for item in inventory} != {RECEIPT, SOURCES, JAR, *EXECUTIONS, *TOOLCHAINS}:
        raise ValueError("Local tooling original closure is incomplete or unexpected")
    return inventory


def produce_local_tooling_attestation(repository, java_home, gradle_installation, gradle_user_home,
                                     signing_metadata, private_key, public_key, output):
    """Execute the fixed local task and attest what was actually observed.

    Java, installed Gradle and its dependency cache are explicit trusted local
    toolchain inputs. This API cannot import a success log or a caller-built JAR.
    """
    from .signatures import sign_manifest, validate_signing_metadata
    from .tooling import ATTESTATION, JAR, _verify_capture
    from .inventory import publish_regular_tree
    signing = validate_signing_metadata(signing_metadata, trust_domain="development")
    repository, java_home, gradle_installation, gradle_user_home, output = map(Path,
        (repository, java_home, gradle_installation, gradle_user_home, output))
    if output.exists() or output.is_symlink():
        raise ValueError("Local tooling destination already exists")
    for source in (repository, java_home, gradle_installation, gradle_user_home, Path(private_key), Path(public_key)):
        left, right = source.resolve(), output.resolve()
        if left == right or left in right.parents or right in left.parents:
            raise ValueError("Local tooling destination overlaps an original input")
    for name in ("init.gradle", "init.gradle.kts", "init.d", "gradle.properties"):
        if (gradle_user_home / name).exists() or (gradle_user_home / name).is_symlink():
            raise ValueError("Local tooling rejects external Gradle initialization/properties")
    commit = run_git(repository, "rev-parse", "HEAD").strip()
    tree = run_git(repository, "rev-parse", f"{commit}^{{tree}}").strip()
    sources = _source_inventory(repository, commit)
    source_paths = git_inventory_paths(sources.decode())
    source_records = git_file_inventory(repository, commit, source_paths)
    wrapper = git_regular_blob_bytes(repository, commit, PATHS[3], max_bytes=8192)
    version_match = re.search(rb"/gradle-([0-9.]+)-bin\.zip", wrapper)
    if version_match is None:
        raise ValueError("Local tooling source wrapper version is absent")
    version = version_match[1].decode()
    java = java_home / "bin" / ("java.exe" if os.name == "nt" else "java")
    java_files = regular_file_inventory(java_home, allow_empty=True)
    java_digest = sha256_bytes(read_regular_file_bytes(java, reject_symlink_parents=True))
    launcher = gradle_installation / "lib" / f"gradle-gradle-cli-main-{version}.jar"
    read_regular_file_bytes(launcher, reject_symlink_parents=True)
    gradle_files = regular_file_inventory(gradle_installation, allow_empty=True)
    dependency_source = gradle_user_home / "caches/modules-2"
    dependency_files = regular_file_inventory(dependency_source, allow_empty=True)
    if not dependency_files:
        raise ValueError("Local tooling requires an existing offline dependency cache")
    environment = {key: value for key, value in os.environ.items() if key in {
        "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL",
    }}
    with tempfile.TemporaryDirectory(prefix="local-tooling-producer-") as temporary:
        work = Path(temporary).resolve()
        source = work / "source"
        original = work / "evidence/original"
        original.mkdir(parents=True)
        private_java = work / "jdk"
        private_gradle = work / "gradle"
        private_cache = work / "cache"
        snapshot_regular_tree(java_home, private_java, allow_empty=True)
        snapshot_regular_tree(gradle_installation, private_gradle, allow_empty=True)
        snapshot_regular_tree(dependency_source, private_cache / "caches/modules-2", allow_empty=True)
        if (java_files != regular_file_inventory(private_java, allow_empty=True) or
                gradle_files != regular_file_inventory(private_gradle, allow_empty=True) or
                dependency_files != regular_file_inventory(private_cache / "caches/modules-2", allow_empty=True)):
            raise ValueError("Local tooling inputs changed during private capture")
        java = private_java / "bin" / java.name
        launcher = private_gradle / "lib" / launcher.name
        prefix = [str(java), "-classpath", str(launcher), "org.gradle.launcher.GradleMain"]
        environment.update(JAVA_HOME=str(private_java), GRADLE_USER_HOME=str(private_cache))
        for name, records in zip(TOOLCHAINS, (java_files, gradle_files, dependency_files)):
            write_canonical_json(original / name, records)
        for record in source_records:
            path = source / record["relativePath"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(git_regular_blob_bytes(repository, commit, record["relativePath"], max_bytes=record["bytes"]))
        (original / SOURCES).write_bytes(sources)
        commands = ([str(java), "-XshowSettings:properties", "-version"], prefix + ["--version"],
                    prefix + ["--offline", "--no-daemon", "--no-configuration-cache", "--project-dir",
                              str(source / "gradle/build-logic"), "--gradle-user-home", str(private_cache),
                              KOTLIN_HEAP, "releaseToolingJar"])
        for name, command in zip(EXECUTIONS, commands):
            result = subprocess.run(command, cwd=source, env=environment, check=False,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            write_canonical_json(original / name, {"schemaVersion": 1, "command": command,
                "exitCode": result.returncode, "outputBase64": base64.b64encode(result.stdout).decode("ascii")})
            if result.returncode:
                # Keep original bytes visible even though no success attestation is emitted.
                import sys
                sys.stderr.buffer.write(result.stdout)
                raise ValueError(f"Local tooling command failed: {name}")
        for record in source_records:
            if sha256_bytes(read_regular_file_bytes(source / record["relativePath"], reject_symlink_parents=True)) != record["sha256"]:
                raise ValueError("Local tooling source changed during build")
        jar = read_regular_file_bytes(source / JAR.removeprefix("payload/"), reject_symlink_parents=True)
        (original / JAR).parent.mkdir(parents=True)
        (original / JAR).write_bytes(jar)
        receipts = [{"relativePath": name, "bytes": (original / name).stat().st_size,
                     "sha256": sha256_bytes((original / name).read_bytes())} for name in EXECUTIONS]
        receipt = {"schemaVersion": 1, "kind": "release-tooling-local-build",
            "producer": {"repository": "codex-agent-labs/codex-agent", "commit": commit, "tree": tree,
                         "event": "local", "workflowPath": None, "runId": None, "runAttempt": None, "pullRequest": None},
            "sourceInventorySha256": sha256_bytes(sources),
            "host": {"system": platform.system(), "machine": platform.machine()},
            "java": {"executable": str(java), "sha256": java_digest,
                     "installationDigest": sha256_bytes(canonical_json_bytes(java_files))},
            "gradle": {"launcher": str(launcher), "version": version,
                       "installationDigest": sha256_bytes(canonical_json_bytes(gradle_files)),
                       "userHome": str(private_cache),
                       "dependencyInputsDigest": sha256_bytes(canonical_json_bytes(dependency_files))},
            "executions": receipts, "outputs": [{"relativePath": JAR, "bytes": len(jar), "sha256": sha256_bytes(jar)}]}
        write_canonical_json(original / RECEIPT, receipt)
        value = {"schemaVersion": 2, "kind": "release-tooling-attestation",
                 "localReceiptSha256": sha256_bytes((original / RECEIPT).read_bytes()),
                 "files": verify_local_original(original, repository), "signing": signing}
        write_canonical_json(original.parent / ATTESTATION, value)
        sign_manifest(original.parent / ATTESTATION, private_key, signing)
        _verify_capture(original.parent, repository, public_key, "development", None, None)
        immutable_dependencies = lambda records: [item for item in records
                                                 if item["relativePath"].startswith("files-2.1/")]
        if (java_files != regular_file_inventory(java_home, allow_empty=True) or
                java_files != regular_file_inventory(private_java, allow_empty=True) or
                gradle_files != regular_file_inventory(gradle_installation, allow_empty=True) or
                gradle_files != regular_file_inventory(private_gradle, allow_empty=True) or
                dependency_files != regular_file_inventory(dependency_source, allow_empty=True) or
                immutable_dependencies(dependency_files) != immutable_dependencies(
                    regular_file_inventory(private_cache / "caches/modules-2", allow_empty=True))):
            raise ValueError("Local tooling compiler installation changed during execution")
        publish_regular_tree(original.parent, output, allow_empty=True)
    return value
