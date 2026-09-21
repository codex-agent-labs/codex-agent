"""Capture immutable facade consumer inputs and generator sources, not admission."""

import os
from pathlib import Path
import tempfile

from .inventory import (
    git_file_inventory, git_regular_blob_bytes, publish_regular_tree,
    regular_file_inventory, require_regular_directory, tree_entries,
)
from .sdk_apple_package_source import _immutable_tree


_TEMPLATE = "gradle/release/sdk-facade-consumer-template"
_REQUIRED_TEMPLATE_FILES = (
    "build.gradle.kts", "settings.gradle.kts", "src/commonMain/kotlin/Consumer.kt",
)
_FILES = (
    "gradlew", "gradlew.bat", "gradle/wrapper/gradle-wrapper.jar", "gradle/wrapper/gradle-wrapper.properties",
    "gradle/build-logic/src/main/kotlin/KmpConsumerVerificationTask.kt",
    "gradle/build-logic/src/main/kotlin/ReleaseToolingGradleTasks.kt",
    "gradle/build-logic/src/main/kotlin/SdkFacadeValidationTasks.kt",
    "gradle/build-logic/src/main/kotlin/SdkFacadeCompilerCapture.kt",
    "gradle/build-logic/build.gradle.kts", "gradle/build-logic/settings.gradle.kts", "gradle/libs.versions.toml",
)


def capture_facade_validation_sources(repository: Path, revision: str, output: Path) -> dict:
    """Preserve selected regular Git blobs and modes without reading the checkout.

    The caller MUST independently authenticate the original validation receipt
    and bind revision to its exact producer commit/tree. Accepting a caller's Git
    object ID here grants no receipt, source-policy, execution or host authority.

    The generated init script is not a tracked input. Its base/outcome-check
    generator lives in KmpConsumerVerificationTask.kt, while the appended raw
    TaskState recorder and composition live in ReleaseToolingGradleTasks.kt.
    Both are retained verbatim, alongside registration, wrapper and dependency
    declarations. This function neither interprets those sources nor fabricates
    generated init/local.properties bytes. Replay must still bind those bytes to
    the original task list, capture path and Android SDK context, using the
    existing generators. Host Java/Gradle caches are deliberately not captured.
    """
    repository = Path(repository).resolve(strict=True)
    require_regular_directory(repository, "Facade source repository")
    output = Path(output)
    if not output.is_absolute() or output.resolve(strict=False) != output:
        raise ValueError("Facade source output must be an absolute normalized non-symbolic path")
    if output.exists() or output.is_symlink():
        raise ValueError("Facade source output already exists")
    if output == repository or output in repository.parents or repository in output.parents:
        raise ValueError("Facade source output overlaps the repository")
    for parent in output.parents:
        if parent.exists() or parent.is_symlink():
            require_regular_directory(parent, "Facade source output ancestry")

    tree = _immutable_tree(repository, revision)
    entries = {path: record.split("\t", 3) for path, record in tree_entries(repository, tree)}
    paths = sorted({*_FILES, *(f"{_TEMPLATE}/{name}" for name in _REQUIRED_TEMPLATE_FILES),
                    *(path for path in entries if path.startswith(_TEMPLATE + "/"))})
    # Existing inventory validation rejects absent, unsafe, symbolic and submodule
    # entries. The full template tree is copied, just as prepareStagedConsumer does.
    inventory = git_file_inventory(repository, tree, paths)
    if any(record["bytes"] == 0 for record in inventory):
        raise ValueError("Facade source capture contains an empty blob")
    with tempfile.TemporaryDirectory(prefix="sdk-facade-source-") as temporary:
        captured = Path(temporary).resolve() / "source"
        captured.mkdir()
        for record in inventory:
            relative = record["relativePath"]
            contents = git_regular_blob_bytes(repository, tree, relative, max_bytes=record["bytes"])
            destination = captured / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(contents)
            os.chmod(destination, 0o755 if entries[relative][0] == "100755" else 0o644)
        if regular_file_inventory(captured) != inventory or git_file_inventory(repository, tree, paths) != inventory:
            raise ValueError("Facade immutable source bytes changed during capture")
        publish_regular_tree(captured, output)
    if regular_file_inventory(output) != inventory:
        raise ValueError("Facade captured source bytes changed during publication")
    return {"tree": tree, "files": inventory}
