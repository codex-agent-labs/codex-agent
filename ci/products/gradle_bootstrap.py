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
    def compilerPlugins = rootProject.configurations.create('sdkProjectCompilerPlugins') {
        canBeResolved = true
        canBeConsumed = false
    }
    rootProject.dependencies.add(compilerPlugins.name,
        'org.jetbrains.kotlin:kotlin-serialization-compiler-plugin-embeddable:' +
        catalog.findVersion('kotlin').get().requiredVersion)
    rootProject.tasks.register('resolveSdkBuildDependencies') {
        doLast {
            ['sdkPluginMarkers', 'sdkProjectCompilerPlugins', 'compileClasspath', 'runtimeClasspath', 'embeddedKotlin',
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


def seed_sdk_android_dependencies(root: Path, revision: str, wrapper: Path,
                                  environment, destination: Path, properties) -> None:
    """Resolve the locked Android producer tools against authenticated Contract bytes."""
    import json
    import tomllib
    from .contract_attestation import materialize_contract_payload
    from .inventory import require_semver, require_relative_path
    from ci.product_reuse import _runtime_worker_command

    if destination.exists() or destination.is_symlink():
        raise ValueError('Android dependency seed requires a fresh destination')
    require_regular_directory(destination.parent, 'Android dependency seed parent')
    destination.mkdir()
    (destination / 'gradle').mkdir()
    catalog = git_regular_blob_bytes(root, revision, 'gradle/libs.versions.toml', max_bytes=4 * 1024**2)
    versions = tomllib.loads(catalog.decode())['versions']
    if versions['kotlin'] != '2.3.10' or versions['agp'] != '9.2.1':
        raise ValueError('Android seed requires the reviewed Kotlin/AGP tool routing')
    (destination / 'gradle/libs.versions.toml').write_bytes(catalog)
    (destination / 'gradle.lockfile').write_bytes(git_regular_blob_bytes(root, revision,
        'codex-agent-runtime-android/gradle-authenticated-contract.lockfile', max_bytes=4 * 1024**2))
    version = require_semver(properties['codexAgent.contractVersion'], 'Android seed Contract version')
    release = environment.get('GITHUB_ACTIONS') == 'true'
    manifest = materialize_contract_payload(
        *(Path(properties['codexAgent.' + name]) for name in
          ('contractPayload', 'contractMetadataReceipt', 'contractAttestation',
           'contractAttestationSignature', 'contractPublicKey')),
        destination / 'contract', required_trust_domain='release' if release else 'development',
        expected_contract_version=version, required_components=('android',),
        keyring=root / 'gradle/release/product-signing-keys.json' if release else None,
        keys_directory=root / 'gradle/release/keys' if release else None,
    )
    metadata = ET.fromstring(git_regular_blob_bytes(root, revision,
        '.github/actions/sdk-ios-binary-worker/verification-metadata.xml', max_bytes=4 * 1024**2))
    namespace = 'https://schema.gradle.org/dependency-verification'
    if metadata.findtext('{' + namespace + '}configuration/{' + namespace + '}verify-metadata') != 'true':
        raise ValueError('Android dependency seed requires metadata verification')
    components = metadata.find('{' + namespace + '}components')
    if components is None:
        raise ValueError('Android dependency seed lacks pinned components')
    by_id = {tuple(component.get(key) for key in ('group', 'name', 'version')): component
             for component in components}

    def pin(parts, filename, digest):
        identity = ('.'.join(parts[:-3]), parts[-3], parts[-2])
        component = by_id.get(identity)
        if component is None:
            component = ET.SubElement(components, '{' + namespace + '}component',
                dict(zip(('group', 'name', 'version'), identity)))
            by_id[identity] = component
        known = [artifact for artifact in component if artifact.get('name') == filename]
        if known:
            if not any(value.get('value') == digest for artifact in known
                       for value in artifact.findall('{' + namespace + '}sha256')):
                raise ValueError('Android seed Contract pin conflicts with its verified payload')
            return
        artifact = ET.SubElement(component, '{' + namespace + '}artifact', {'name': filename})
        ET.SubElement(artifact, '{' + namespace + '}sha256', {'value': digest,
            'origin': 'Transient seed pin from authenticated Contract Maven allow-list'})

    for record in manifest['mavenFiles']:
        parts = Path(record['path']).parts[1:]
        pin(parts, parts[-1], record['sha256'].removeprefix('sha256:'))
        if parts[-1].endswith('.module'):
            module = destination / 'contract' / record['path']
            for variant in json.loads(module.read_bytes()).get('variants', []):
                for artifact in variant.get('files', []):
                    name = require_relative_path(artifact['name'], 'Contract module artifact alias')
                    url = require_relative_path(artifact['url'], 'Contract module artifact URL')
                    if '/' in name or '/' in url:
                        raise ValueError('Contract module seed alias must be a sibling file')
                    body = read_regular_file_bytes(module.parent / url, reject_symlink_parents=True)
                    pin(parts, name, hashlib.sha256(body).hexdigest())
    ET.register_namespace('', namespace)
    ET.register_namespace('xsi', 'http://www.w3.org/2001/XMLSchema-instance')
    (destination / 'gradle/verification-metadata.xml').write_bytes(
        ET.tostring(metadata, encoding='utf-8', xml_declaration=True))
    (destination / 'settings.gradle.kts').write_text(
        'pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }\n'
        'dependencyResolutionManagement {\n'
        '    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)\n'
        '    repositories {\n'
        '        exclusiveContent {\n'
        '            forRepository { maven { url = uri(layout.settingsDirectory.dir("contract/maven")) } }\n'
        '            filter { includeGroup("io.github.codex-agent-labs") }\n'
        '        }\n'
        '        google(); mavenCentral()\n'
        '    }\n'
        '}\n', encoding='utf-8')
    (destination / 'build.gradle.kts').write_text(
        'import com.android.build.gradle.internal.res.Aapt2FromMaven\n'
        'plugins { alias(libs.plugins.android.library); alias(libs.plugins.kotlin.jvm) apply false }\n'
        'android { namespace = "io.github.codex_agent_labs.dependencyseed"; compileSdk = 37\n'
        '    defaultConfig { minSdk = 26 }\n'
        '    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }\n'
        '}\n'
        f'dependencies {{ api("io.github.codex-agent-labs:codex-agent-core:{version}")\n'
        '    implementation(libs.androidx.browser); implementation(libs.androidx.sqlite)\n'
        '    implementation(libs.androidx.sqlite.framework); implementation(libs.kotlinx.coroutines.core); implementation(libs.okio)\n'
        '}\n'
        'dependencyLocking { lockAllConfigurations() }\n'
        'val aapt2 = Aapt2FromMaven.create(project) { null }\n'
        'tasks.register("resolveSdkAndroidDependencies") { doLast {\n'
        '    listOf("kotlinCompilerClasspath", "kotlinBuildToolsApiClasspath", "releaseCompileClasspath", "releaseRuntimeClasspath", "androidLintTool").forEach { name ->\n'
        '        configurations.getByName(name).files.forEach { println("SDK_DEPENDENCY ${it.name}") }\n'
        '    }\n'
        '    aapt2.aapt2Directory.files.forEach { println("SDK_AAPT2 ${it}") }\n'
        '} }\n', encoding='utf-8')
    original = _runtime_worker_command(wrapper, {}, environment, build_directory='.')
    command = [*original[:original.index('--offline')], '-p', str(destination),
        'resolveSdkAndroidDependencies', '--dependency-verification=strict',
        '--no-daemon', '--no-configuration-cache', '--console=plain']
    with (destination / 'gradle.log').open('xb') as log:
        result = subprocess.run(command, cwd=root, env=dict(environment), stdout=log,
            stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise ValueError(f'Pinned Android dependency seed failed; see {destination / "gradle.log"}')


def seed_sdk_ios_native_distribution(root: Path, revision: str, wrapper: Path,
                                     environment, destination: Path) -> None:
    """Seed pinned iOS dependencies and KGP's prebuilt tools, never product tasks.

    Gradle pins authenticate the distribution archive. Konan's own downloader
    handles its declared dependencies; its direct downloads are not Gradle inputs.
    """
    import tomllib
    from ci.product_reuse import _runtime_worker_command
    catalog = git_regular_blob_bytes(root, revision,
        'gradle/libs.versions.toml', max_bytes=4 * 1024**2)
    version = tomllib.loads(catalog.decode())['versions']['kotlin']
    if version != '2.3.10':
        raise ValueError('SDK native setup requires reviewed Kotlin 2.3.10 routing')
    if destination.exists() or destination.is_symlink():
        raise ValueError('SDK native setup requires a fresh diagnostic destination')
    require_regular_directory(destination.parent, 'SDK native setup parent')
    destination.mkdir()
    (destination / 'gradle').mkdir()
    (destination / 'gradle/libs.versions.toml').write_bytes(catalog)
    (destination / 'gradle/verification-metadata.xml').write_bytes(git_regular_blob_bytes(root, revision,
        '.github/actions/sdk-ios-binary-worker/verification-metadata.xml', max_bytes=4 * 1024**2))
    (destination / 'settings.gradle.kts').write_text(
        'pluginManagement { repositories { mavenCentral(); gradlePluginPortal() } }\n', encoding='utf-8')
    (destination / 'build.gradle.kts').write_text(
        f'plugins {{ kotlin("multiplatform") version "{version}" }}\n'
        'repositories { mavenCentral() }\n'
        'kotlin {\n'
        '    iosArm64(); iosSimulatorArm64()\n'
        '    sourceSets.commonMain.dependencies {\n'
        '        implementation(libs.kotlinx.coroutines.core)\n'
        '        implementation(libs.kotlinx.serialization.json)\n'
        '        implementation(libs.okio)\n'
        '    }\n'
        '}\n'
        'tasks.register("resolveSdkIosDependencies") {\n'
        '    doLast {\n'
        '        listOf("iosArm64CompileKlibraries", "iosSimulatorArm64CompileKlibraries", "kotlinCompilerClasspath", "kotlinKlibCommonizerClasspath", "allSourceSetsCompileDependenciesMetadata", "iosArm64CompilationDependenciesMetadata", "iosSimulatorArm64CompilationDependenciesMetadata").forEach { name ->\n'
        '            configurations.getByName(name).files.forEach { println("SDK_DEPENDENCY ${it.name}") }\n'
        '        }\n'
        '    }\n'
        '}\n', encoding='utf-8')
    original = _runtime_worker_command(wrapper, {}, environment, build_directory='.')
    command = [*original[:original.index('--offline')], '-p', str(destination),
        'downloadKotlinNativeDistribution', 'resolveSdkIosDependencies',
        '--dependency-verification=strict', '--no-daemon',
        '--no-configuration-cache', '--console=plain', '-Pkotlin.native.distribution.type=prebuilt']
    with (destination / 'gradle.log').open('xb') as log:
        result = subprocess.run(command, cwd=root, env=dict(environment), stdout=log,
            stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise ValueError(f'SDK native tool setup failed; see {destination / "gradle.log"}')
    from .inventory import load_canonical_json_bytes, require_array, require_exact_keys, require_integer, require_sha256
    from .toolchain import _tree_digest
    policy = require_exact_keys(load_canonical_json_bytes(git_regular_blob_bytes(root, revision,
        '.github/actions/sdk-ios-binary-worker/native-dependencies.json', max_bytes=64 * 1024)),
        {'schemaVersion', 'kotlinVersion', 'host', 'dependencies'}, 'SDK native dependency policy')
    if (require_integer(policy['schemaVersion'], 'SDK native dependency policy schema', 1) != 1 or
            policy['kotlinVersion'] != version or policy['host'] != 'macos_arm64'):
        raise ValueError('SDK native dependency policy differs from its fixed compiler/host')
    konan = Path(environment.get('KONAN_DATA_DIR', str(Path.home() / '.konan')))
    if not konan.is_absolute() or konan.resolve(strict=True) != konan:
        raise ValueError('SDK Konan data directory must be normalized')
    names = []
    for record in require_array(policy['dependencies'], 'SDK native dependencies'):
        require_exact_keys(record, {'name', 'treeSha256'}, 'SDK native dependency')
        name = record['name']
        if name not in {'libffi-3.3-1-macos-arm64', 'llvm-19-aarch64-macos-essentials-79'}:
            raise ValueError('Unsupported SDK native dependency')
        names.append(name)
        expected = require_sha256(record['treeSha256'], 'SDK native dependency tree')
        if _tree_digest(konan / 'dependencies' / name, 'SDK native dependency') != expected:
            raise ValueError('SDK native dependency differs from its approved immutable tree')
    if sorted(names) != ['libffi-3.3-1-macos-arm64', 'llvm-19-aarch64-macos-essentials-79']:
        raise ValueError('SDK native dependency policy must contain exactly the required two trees')
