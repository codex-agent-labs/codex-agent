"""Reject missing wrapper installations before offline workers can bootstrap online.

This checks Gradle's installed-cache fast path, not distribution authenticity or
network isolation. Toolchain admission must independently authenticate tool bytes.
"""

import hashlib
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

from .inventory import git_regular_blob_bytes, read_regular_file_bytes, require_regular_directory
from .toolchain import _properties


def require_preprovisioned_gradle(properties_bytes: bytes, environment) -> Path:
    properties = _properties(properties_bytes, "Original Gradle wrapper properties")
    for key, expected in {
        "distributionBase": "GRADLE_USER_HOME", "distributionPath": "wrapper/dists",
        "zipStoreBase": "GRADLE_USER_HOME", "zipStorePath": "wrapper/dists",
    }.items():
        if properties.get(key) != expected:
            raise ValueError("Offline worker requires the declared Gradle user-home wrapper layout")
    url = properties.get("distributionUrl", "").replace("\\:", ":")
    match = re.fullmatch(r"https://services\.gradle\.org/distributions/(gradle-([0-9]+(?:\.[0-9]+)+)-(?:bin|all)\.zip)", url)
    if match is None or re.fullmatch(r"[0-9a-f]{64}", properties.get("distributionSha256Sum", "")) is None:
        raise ValueError("Offline worker requires an exact pinned Gradle distribution")
    home = Path(environment.get("GRADLE_USER_HOME", str(Path.home() / ".gradle")))
    if not home.is_absolute() or home.resolve(strict=False) != home:
        raise ValueError("Offline Gradle user home must be absolute and non-symbolic")
    # This MD5 is Gradle PathAssembler's cache locator, never a security digest.
    number = int.from_bytes(hashlib.md5(url.encode("ascii"), usedforsecurity=False).digest(), "big")
    cache_key = ""
    while number:
        number, digit = divmod(number, 36)
        cache_key = "0123456789abcdefghijklmnopqrstuvwxyz"[digit] + cache_key
    archive, version = match.groups()
    cache = home / "wrapper/dists" / archive.removesuffix(".zip") / (cache_key or "0")
    require_regular_directory(cache, "Preprovisioned Gradle wrapper cache")
    marker = cache / (archive + ".ok")
    read_regular_file_bytes(marker, max_bytes=1024, reject_symlink_parents=True)
    directories = []
    for child in cache.iterdir():
        if child.is_symlink():
            raise ValueError("Offline Gradle cache contains a symbolic entry")
        if child.is_dir():
            directories.append(child)
    installation = cache / f"gradle-{version}"
    if directories != [installation]:
        raise ValueError("Offline Gradle cache must contain exactly its selected distribution")
    lib = installation / "lib"
    require_regular_directory(lib, "Preprovisioned Gradle libraries")
    launchers = list(lib.glob("gradle-launcher-*.jar"))
    if launchers != [lib / f"gradle-launcher-{version}.jar"]:
        raise ValueError("Offline Gradle distribution must contain its exact launcher")
    if not read_regular_file_bytes(launchers[0], max_bytes=128 * 1024 * 1024, reject_symlink_parents=True):
        raise ValueError("Offline Gradle launcher is empty")
    return installation


_SDK_SEED_SCRIPT = """gradle.projectsEvaluated {
    def catalog = rootProject.extensions.getByType(org.gradle.api.artifacts.VersionCatalogsExtension).named('libs')
    def markers = rootProject.configurations.create('sdkPluginMarkers') {
        canBeResolved = true
        canBeConsumed = false
    }
    catalog.pluginAliases.each { alias ->
        def plugin = catalog.findPlugin(alias).get().get()
        rootProject.dependencies.add(markers.name,
            plugin.pluginId + ':' + plugin.pluginId + '.gradle.plugin:' + plugin.version.requiredVersion)
    }
    rootProject.tasks.register('resolveSdkBuildDependencies') {
        doLast {
            ['sdkPluginMarkers', 'compileClasspath', 'runtimeClasspath', 'embeddedKotlin',
             'kotlinBuildToolsApiClasspath', 'kotlinCompilerClasspath', 'kotlinCompilerPluginClasspathMain',
             'compilePluginsBlocksPluginClasspathElements'].each { name ->
                rootProject.configurations.getByName(name).files.each { file ->
                    println('SDK_DEPENDENCY ' + file.name)
                }
            }
        }
    }
}
"""


def seed_sdk_gradle_dependencies(root: Path, revision: str, wrapper: Path,
                                 environment, destination: Path, *, platform_name=None) -> None:
    """Resolve only pinned build dependencies; the product command stays offline.

    The private fixture uses exact Git build/catalog bytes, never SDK sources or
    product tasks. Generated seed files and logs are external execution evidence.
    """
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK dependency seed requires a fresh destination")
    require_regular_directory(destination.parent, "SDK dependency seed parent")
    if destination.parent.resolve(strict=True) != destination.parent:
        raise ValueError("SDK dependency seed parent must be normalized")
    destination.mkdir()
    for relative in ("gradle/build-logic/build.gradle.kts",
                     "gradle/build-logic/settings.gradle.kts", "gradle/libs.versions.toml"):
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(git_regular_blob_bytes(root, revision, relative, max_bytes=4 * 1024**2))

    namespace = {"v": "https://schema.gradle.org/dependency-verification"}
    merged = None
    components = {}
    for relative in (".github/actions/sdk-ios-binary-worker/verification-metadata.xml",):
        document = ET.fromstring(git_regular_blob_bytes(root, revision, relative, max_bytes=4 * 1024**2))
        configuration = document.find("v:configuration", namespace)
        if ((configuration is None and merged is None) or
                configuration is not None and configuration.findtext("v:verify-metadata", namespaces=namespace) != "true"):
            raise ValueError("SDK seed requires metadata verification")
        children = document.find("v:components", namespace)
        if children is None:
            raise ValueError("SDK seed lacks pinned components")
        incoming = list(children)
        if merged is None:
            merged = document
            merged.find("v:components", namespace).clear()
        for component in incoming:
            key = tuple(component.get(field) for field in ("group", "name", "version"))
            if key not in components:
                components[key] = component
                continue
            known = {artifact.get("name"): artifact for artifact in components[key]}
            for artifact in component:
                name = artifact.get("name")
                if name not in known:
                    components[key].append(artifact)
                    known[name] = artifact
                elif {item.get("value") for item in artifact.findall("v:sha256", namespace)} != {
                        item.get("value") for item in known[name].findall("v:sha256", namespace)}:
                    raise ValueError("SDK seed policies contain conflicting checksums")
    merged.find("v:components", namespace).extend(components[key] for key in sorted(components))
    metadata = destination / "gradle/build-logic/gradle/verification-metadata.xml"
    metadata.parent.mkdir()
    ET.register_namespace("", namespace["v"])
    ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")
    metadata.write_bytes(ET.tostring(merged, encoding="utf-8", xml_declaration=True))
    script = destination / "resolve-dependencies.gradle"
    script.write_text(_SDK_SEED_SCRIPT, encoding="utf-8")
    from ci.product_reuse import _runtime_worker_command
    product_command = _runtime_worker_command(wrapper, {}, environment,
        build_directory=".", platform_name=platform_name)
    command = [*product_command[:product_command.index("--offline")],
               "-p", str(destination / "gradle/build-logic"), "-I", str(script),
               "resolveSdkBuildDependencies", "--dependency-verification=strict",
               "--no-daemon", "--no-configuration-cache", "--console=plain"]
    with (destination / "gradle.log").open("xb") as log:
        result = subprocess.run(command, cwd=root, env=dict(environment), stdout=log,
                                stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise ValueError(f"Pinned SDK dependency seeding failed; see {destination / 'gradle.log'}")
