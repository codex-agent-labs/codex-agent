"""Compose SDK handoff routes from the existing authenticated product replay."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
import sdk_handoff
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    regular_file_inventory, sha256_bytes, snapshot_regular_tree, publish_regular_tree,
    verified_zip_contents,
    _stat_identity,
)
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PHASE_INSTANCE_IDS, PhaseInstanceId
from products.restore import verification_scoped
from products.sdk_apple_original_inputs import verified_apple_original_inputs
from products.sdk_inputs import REQUEST_NAME
from reuse import github_output
from products.contract_model import _execution_tree_digest
from products.signing_isolation import require_no_signing_secret
from products.sdk_validation import decode_sdk_validation_records
from products.sdk_maven import _zip_members
from products.tooling import verified_tooling_capture


IMPORTED_JAVA_PARITY_INIT = """\
gradle.projectsEvaluated {
    def core = rootProject.findProject(':codex-agent-core')
    if (core == null) return
    def inputs = System.getProperty('codexAgent.importedJavaParityInputs')
    def output = System.getProperty('codexAgent.importedJavaParityOutput')
    if (!inputs || !output) {
        throw new GradleException('Imported Java parity requires explicit input and output paths')
    }
    def originals = new File(inputs).canonicalFile
    def result = new File(output).canonicalFile
    def consumerRoot = result.parentFile.toPath()
    if (consumerRoot.startsWith(originals.toPath()) || originals.toPath().startsWith(consumerRoot)) {
        throw new GradleException('Java consumer outputs must be separate from original inputs')
    }
    def externalModules = { name ->
        // Configuration file dependencies include this project's producer
        // outputs. Use only resolved external modules, with no builtBy edges.
        core.files(core.configurations.getByName(name).incoming.artifacts.artifacts.findAll {
            it.id.componentIdentifier instanceof org.gradle.api.artifacts.component.ModuleComponentIdentifier
        }.collect { it.file })
    }
    def compileTests = core.tasks.register('compileImportedJavaParityTests', org.gradle.api.tasks.compile.JavaCompile) {
        setDependsOn([])
        source core.fileTree('src/jvmTest/java') { include '**/*.java' }
        classpath = core.files(new File(originals, 'core-jvm.jar'), new File(originals, 'fixture-classes')) +
            externalModules('jvmTestCompileClasspath')
        destinationDirectory.set(new File(result.parentFile, 'compiled-java-tests'))
        options.release.set(17)
        outputs.upToDateWhen { false }
    }
    def runTests = core.tasks.register('runImportedJavaParityTests', org.gradle.api.tasks.testing.Test) {
        setDependsOn([compileTests])
        testClassesDirs = core.files(compileTests.flatMap { it.destinationDirectory })
        classpath = testClassesDirs + core.files(new File(originals, 'core-jvm.jar'),
            new File(originals, 'fixture-classes')) + externalModules('jvmTestRuntimeClasspath')
        useJUnitPlatform()
        filter { includeTestsMatching 'io.github.codex_agent_labs.codexagent.agent.CodexJavaApiTest' }
        reports.junitXml.outputLocation.set(new File(result.parentFile, 'test-results'))
        reports.html.required.set(false)
        binaryResultsDirectory.set(new File(result.parentFile, 'binary-results'))
        outputs.upToDateWhen { false }
    }
    core.tasks.named('verifyJavaBindingParity').configure {
        useImportedInputs(originals)
        compiledJavaTests.set(compileTests.flatMap { it.destinationDirectory })
        testResults.set(new File(result.parentFile, 'test-results'))
        receiptFile.set(result)
        dependsOn runTests
        outputs.upToDateWhen { false }
    }
}
"""

IMPORTED_NATIVE_PARITY_INIT = """\
gradle.projectsEvaluated {
    def sdk = rootProject.findProject(':codex-agent-sdk')
    if (sdk == null) return
    def config = new groovy.json.JsonSlurper().parse(new File(System.getProperty('codexAgent.importedNativeParityInputs')))
    def file = { value -> new File(value) }
    ['python':'Python', 'csharp':'CSharp', 'rust':'Rust', 'cpp':'Cpp', 'dart':'Dart'].each { language, title ->
        def original = config.native[language]
        sdk.tasks.named("verify${title}BindingParity").configure {
            setDependsOn([])
            apiReport.set(file(config.api))
            canonicalCoverageReceipt.set(file(config.coverage))
            getCAbiBootstrapEvidence().set(file(original.bootstrap))
            claims.set(file(original.claims))
            compilerEvidence.set(file(original.capability + '/compiler-evidence.tsv'))
            testProgram.set(file(original.capability + '/test-program'))
            testResults.set(file(original.capability + '/executed-tests.tsv'))
            packageArtifacts.set(file(original.packageStage + '/outputs/' + language))
            hostEvidenceDirectory.set(file(original.validationStages))
            stagedCAbiSdks.set(file(original.sdks))
            importedPackageStage.set(file(original.packageStage))
            importedPackageReceipt.set(file(original.packageReceipt))
            importedCompatibilityRequest.set(file(original.request))
            importedRuntimeStages.set(file(original.runtime))
            importedValidationStages.set(file(original.validationStages))
            importedValidationReceipts.set(file(original.validationReceipts))
            importedRepository.set(rootProject.layout.projectDirectory)
            receipt.set(file(original.output))
            outputs.upToDateWhen { false }
        }
    }
    def type = sdk.tasks.named('verifyCppBindingParity').get().class.classLoader
        .loadClass('VerifyImportedCAbiBindingParityTask')
    rootProject.tasks.register('verifyImportedCAbiBindingParity', type) {
        def original = config.native.cpp
        language.set('cpp')
        packageStage.set(file(original.packageStage))
        packageReceipt.set(file(original.packageReceipt))
        compatibilityRequest.set(file(original.request))
        runtimeStages.set(file(original.runtime))
        stagedSdks.set(file(original.sdks))
        repositoryRoot.set(rootProject.layout.projectDirectory)
        evidenceDirectory.set(file(config.cabiOutput))
    }
    rootProject.tasks.named('verifyImportedSdkBindingParity').configure {
        setDependsOn([])
        canonicalApiReport.set(file(config.api))
        canonicalCoverageReceipt.set(file(config.coverage))
        evidenceDirectory.set(file(config.finalEvidence))
        resultFile.set(file(config.finalOutput))
        outputs.upToDateWhen { false }
    }
}
"""


@contextmanager
def verified_java_parity_inputs(plan, discovery, state, *, repository_root, environ,
                                sdk_validation_tooling=None, sdk_original_workflow_sha=None,
                                sdk_apple_validation_policy=None,
                                sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Import unchanged products after the existing full original-source replay.

    Paths grant no authority. Receipts, objects, keys and original producers are
    authenticated by the existing replay before extraction. Derived class trees
    are consumer inputs only; no product archive or receipt is rewritten.
    """
    root = Path(repository_root).resolve(strict=True)
    plan_bytes = read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    verified = product_reuse._verified_product_state(
        plan, discovery, state, root, environ, sdk_validation_tooling,
        sdk_original_workflow_sha=sdk_original_workflow_sha,
        **_caller_policies(None, sdk_apple_validation_policy,
            sdk_facade_metadata_admission=sdk_facade_metadata_admission,
            sdk_android_metadata_admission=sdk_android_metadata_admission))
    with _java_parity_inputs(verified, plan, plan_bytes) as inputs:
        yield inputs


@contextmanager
def _java_parity_inputs(verified, plan, plan_bytes):
    identities = (
        PhaseInstanceId("contract", "contract", "binary", "common"),
        PhaseInstanceId("runtime", "jvm", "binary", "jvm"),
        PhaseInstanceId("sdk", "sdk-android", "package", "android"),
    )
    phases = {product_reuse._identity(row): row for row in verified.prior["phases"]}
    if any(identity not in verified.sources or phases.get(identity, {}).get("state") not in {"retained", "reused"}
           for identity in identities):
        raise ValueError("Java parity requires completed authenticated Contract, JVM Runtime and Android SDK inputs")
    with tempfile.TemporaryDirectory(prefix="sdk-java-parity-inputs-") as temporary:
        private = Path(temporary).resolve()
        originals = private / "originals"
        originals.mkdir()
        restored = product_reuse._restore_product_objects(verified, identities, originals)
        inputs = private / "consumer-inputs"
        inputs.mkdir()

        def stage(identity):
            return originals / "-".join(getattr(identity, field) for field in product_reuse._IDENTITY_KEYS) / "stage"

        contract, runtime, android = (stage(identity) for identity in identities)
        contract_version, runtime_version, sdk_version = (
            restored[identity]["receipt"]["productVersion"] for identity in identities)
        group = "io/github/codex-agent-labs"
        files = {
            "core-jvm.jar": contract / f"outputs/maven/{group}/codex-agent-core-jvm/{contract_version}/codex-agent-core-jvm-{contract_version}.jar",
            "core-android.aar": contract / f"outputs/maven/{group}/codex-agent-core-android/{contract_version}/codex-agent-core-android-{contract_version}.aar",
            "desktop-runtime.jar": runtime / f"outputs/adapter/codex-agent-runtime-desktop-jvm-{runtime_version}.jar",
            "android-runtime.aar": android / f"outputs/maven/{group}/codex-agent-runtime-android/{sdk_version}/codex-agent-runtime-android-{sdk_version}.aar",
            "canonical-api.json": contract / "outputs/evidence/canonical-api.json",
            "canonical-coverage.json": contract / "outputs/evidence/canonical-coverage.json",
        }
        for name, source in files.items():
            (inputs / name).write_bytes(read_regular_file_bytes(source, reject_symlink_parents=True))
        # JARs legitimately include directory entries. Reuse the existing
        # Maven archive checker; product-object ZIP rules remain unchanged.
        classes = _zip_members(read_regular_file_bytes(inputs / "core-jvm.jar"), "preserved Core JAR")
        for name, (data, _, _) in classes.items():
            if name != "META-INF/MANIFEST.MF":
                target = inputs / "kotlin-classes" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        api = product_reuse.load_json_bytes((inputs / "canonical-api.json").read_bytes())
        target_digest = [row["sha256"] for row in api["targets"] if row["kind"] == "jvm-classes"]
        if target_digest != [_execution_tree_digest(inputs / "kotlin-classes")]:
            raise ValueError("Imported JVM classes differ from the original canonical compiler identity")
        _, execution, _ = verified_zip_contents(contract / "outputs/execution/contract-execution.zip", allow_empty_members=True)
        for name, data in execution.items():
            if name.startswith("compiled-tests/"):
                target = inputs / "fixture-classes" / name.removeprefix("compiled-tests/")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        inventory = regular_file_inventory(private)
        try:
            yield inputs
        finally:
            if (regular_file_inventory(private) != inventory or
                    read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024,
                        reject_symlink_parents=True) != plan_bytes):
                raise ValueError("Original Java parity inputs changed during consumer use")


@contextmanager
def verified_parity_inputs(plan, discovery, state, *, repository_root, environ,
                           sdk_validation_tooling=None, sdk_original_workflow_sha=None,
                           sdk_apple_validation_policy=None,
                           sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Borrow completed immutable evidence after one full authenticated replay."""
    root = Path(repository_root).resolve(strict=True)
    plan_bytes = read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    verified = product_reuse._verified_product_state(plan, discovery, state, root, environ,
        sdk_validation_tooling, sdk_original_workflow_sha=sdk_original_workflow_sha,
        **_caller_policies(None, sdk_apple_validation_policy,
            sdk_facade_metadata_admission=sdk_facade_metadata_admission,
            sdk_android_metadata_admission=sdk_android_metadata_admission))
    phases = {product_reuse._identity(row): row for row in verified.prior["phases"]}
    required = {identity for identity in PHASE_INSTANCE_IDS if identity.product == "sdk"}
    if any(identity not in verified.sources or phases.get(identity, {}).get("state") not in {"retained", "reused"}
           for identity in required):
        raise ValueError("Full parity requires every selected SDK phase completed and authenticated")
    records = {"sdkValidationEvidence": list(verified.rebased_request.get("sdkValidationEvidence", []))}
    product_reuse._merge_native_comparison_records(records,
        product_reuse._retained_sdk_handoffs(Path(state), root), key="sdkValidationEvidence")
    native = decode_sdk_validation_records(root, records["sdkValidationEvidence"])
    selected = {}
    protected = set()
    for language in NATIVE_BINDINGS:
        hosts = {}
        for target in NATIVE_TARGETS:
            identity = PhaseInstanceId("sdk", language, "validation", target)
            digest = phases[identity]["receiptSha256"]
            record = native.get(digest)
            if record is None or (record["component"], record["target"]) != (language, target):
                raise ValueError("Parity lacks the exact authenticated native validation receipt")
            if sha256_bytes(read_regular_file_bytes(record["validationReceipt"], reject_symlink_parents=True)) != digest:
                raise ValueError("Parity native receipt differs from the selected immutable phase")
            hosts[target] = record
            protected.update(Path(record[name]) for name in (
                "packageStage", "packageReceipt", "compatibilityRequest", "runtimeStages", "stagedSdks",
                "validationStage", "validationReceipt"))
        selected[language] = hosts
    before = {path: (regular_file_inventory(path, allow_empty=True) if path.is_dir()
        else read_regular_file_bytes(path, reject_symlink_parents=True)) for path in protected}
    with tempfile.TemporaryDirectory(prefix="sdk-parity-originals-") as temporary:
        private = Path(temporary).resolve()
        originals = private / "objects"
        originals.mkdir()
        javascript = PhaseInstanceId("sdk", "javascript", "metadata", "node")
        contract = PhaseInstanceId("contract", "contract", "binary", "common")
        product_reuse._restore_product_objects(verified, (contract, javascript), originals)
        files = {
            "canonical-api.json": originals / "contract-contract-binary-common/stage/outputs/evidence/canonical-api.json",
            "canonical-coverage.json": originals / "contract-contract-binary-common/stage/outputs/evidence/canonical-coverage.json",
            "kotlin-parity.json": originals / "contract-contract-binary-common/stage/outputs/evidence/kotlin-parity.json",
            "javascript-typescript-parity.json": originals / "sdk-javascript-metadata-node/stage/outputs/binding-evidence/javascript-typescript-parity.json",
        }
        apple = {"sdkAppleValidationEvidence": list(verified.rebased_request.get("sdkAppleValidationEvidence", []))}
        product_reuse._merge_native_comparison_records(apple,
            product_reuse._retained_apple_handoffs(Path(state), root), key="sdkAppleValidationEvidence")
        apple_rows = [row for row in apple["sdkAppleValidationEvidence"]
            if row["target"] == "ios-arm64" and row["receiptSha256"] ==
                phases[PhaseInstanceId("sdk", "sdk-ios", "validation", "ios-arm64")]["receiptSha256"]]
        if len(apple_rows) != 1:
            raise ValueError("Parity lacks the selected authenticated Apple validation original")
        archive = root / apple_rows[0]["evidenceRoot"] / "capture/original/execution/apple-validation-evidence.zip"
        archive_identity = _stat_identity(archive.stat())
        reports = {name: "reports/" + name
            for name in ("swift-parity.json", "objective-c-parity.json")}
        _, extracted, _ = verified_zip_contents(archive, allow_empty_members=True,
            retained_paths=reports.values(), max_retained_bytes=16 * 1024 * 1024)
        for name, path in reports.items():
            destination = private / name
            destination.write_bytes(extracted[path])
            files[name] = destination
        imported_inventory = regular_file_inventory(private)
        with _java_parity_inputs(verified, plan, plan_bytes) as java:
            try:
                yield {"java": java, "native": selected, "files": files, "phases": phases}
            finally:
                if (_stat_identity(archive.stat()) != archive_identity or
                        regular_file_inventory(private) != imported_inventory or
                        any((regular_file_inventory(path, allow_empty=True) if path.is_dir()
                            else read_regular_file_bytes(path, reject_symlink_parents=True)) != old
                            for path, old in before.items())):
                    raise ValueError("Original parity inputs changed during use")


def execute_java_parity(plan, discovery, state, destination, *, repository_root, environ, **policies):
    """Run the fixed consumer and full Java gate; publish after input exit checks.

    This produces semantic parity evidence only, never a product phase receipt
    or hosted-provenance claim. Missing authenticated products fail before Gradle.
    """
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    discovery, state, destination = product_reuse._product_materialization_paths(root, discovery, state, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Java parity destination must be fresh")
    with tempfile.TemporaryDirectory(prefix="sdk-java-parity-execution-") as temporary:
        private = Path(temporary).resolve()
        result = private / "evidence"
        result.mkdir()
        script = private / "parity.init.gradle"
        script.write_text(IMPORTED_JAVA_PARITY_INIT)
        with verified_java_parity_inputs(plan, discovery, state, repository_root=root,
                environ=environ, **policies) as inputs:
            command = [str(root / "gradlew"), ":codex-agent-core:verifyJavaBindingParity",
                "--init-script", str(script), "-DcodexAgent.importedJavaParityInputs=" + str(inputs),
                "-DcodexAgent.importedJavaParityOutput=" + str(result / "java-parity.json"),
                "--offline", "--no-configuration-cache", "--no-build-cache", "--console=plain"]
            with (result / "consumer.log").open("wb") as log:
                subprocess.run(command, cwd=root, env=dict(environ), check=True, stdout=log, stderr=subprocess.STDOUT)
            read_regular_file_bytes(result / "java-parity.json", reject_symlink_parents=True)
        publish_regular_tree(result, destination)
    return {"evidence": destination / "java-parity.json"}


def execute_parity(plan, discovery, state, destination, *, repository_root, environ,
                   sdk_validation_tooling, **policies):
    """Full consumer parity over authenticated originals; no product execution."""
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    discovery, state, destination = product_reuse._product_materialization_paths(root, discovery, state, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Parity destination must be fresh")
    tooling = sdk_validation_tooling
    revision = product_reuse.load_json_bytes(read_regular_file_bytes(plan))["validationCommit"]
    with tempfile.TemporaryDirectory(prefix="sdk-parity-execution-") as temporary:
        private = Path(temporary).resolve()
        result = private / "evidence"
        result.mkdir()
        with verified_parity_inputs(plan, discovery, state, repository_root=root,
                environ=environ, sdk_validation_tooling=tooling, **policies) as inputs, \
                verified_tooling_capture(Path(tooling["evidence"]), root, Path(tooling["publicKey"]),
                    required_trust_domain=tooling["requiredTrustDomain"],
                    keyring=Path(tooling["keyring"]) if tooling["keyring"] else None,
                    keys_directory=Path(tooling["keysDirectory"]) if tooling["keysDirectory"] else None,
                    policy_revision=revision) as jar, (result / "consumer.log").open("wb") as log:
            def run(command):
                subprocess.run(command, cwd=root, env=dict(environ), check=True,
                    stdout=log, stderr=subprocess.STDOUT)

            def copy(source, target):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(read_regular_file_bytes(source, reject_symlink_parents=True))

            files = inputs["files"]
            config = {"api": str(files["canonical-api.json"]), "coverage": str(files["canonical-coverage.json"]),
                "native": {}, "cabiOutput": str(private / "cabi"),
                "finalEvidence": str(result / "m11"), "finalOutput": str(result / "sdk-parity.json")}
            titles = {"python": "Python", "csharp": "CSharp", "rust": "Rust", "cpp": "Cpp", "dart": "Dart"}
            for language, hosts in inputs["native"].items():
                lane = private / language
                primary = hosts["linux-x64"]
                for target, record in hosts.items():
                    snapshot_regular_tree(record["validationStage"], lane / "hosts" / target)
                    copy(record["validationReceipt"], lane / "receipts" / (target + ".json"))
                # Existing verifier stages the original producer's source,
                # canonical inputs, bootstrap and raw compiler/test evidence.
                handoff = lane / "inputs"
                command = [sys.executable, "-m", "ci.products.sdk_package", "verify-native",
                    "--repository", str(root), "--component", language,
                    "--validation-target", "linux-x64", "--validation-inputs-output", str(handoff)]
                for option, key in (("stage", "packageStage"), ("receipt", "packageReceipt"),
                        ("compatibility-request", "compatibilityRequest"), ("runtime-stages", "runtimeStages"),
                        ("staged-sdks", "stagedSdks"), ("validation-stage", "validationStage"),
                        ("validation-receipt", "validationReceipt")):
                    command.extend(("--" + option, str(primary[key])))
                run(command)
                config["native"][language] = {"packageStage": str(primary["packageStage"]),
                    "packageReceipt": str(primary["packageReceipt"]), "request": str(primary["compatibilityRequest"]),
                    "runtime": str(primary["runtimeStages"]), "sdks": str(primary["stagedSdks"]),
                    "validationStages": str(lane / "hosts"), "validationReceipts": str(lane / "receipts"),
                    "bootstrap": str(handoff / "bootstrap/bootstrap-evidence.json"),
                    "claims": str(handoff / "validation-source/capability-claims.tsv"),
                    "capability": str(handoff / "validation/outputs/capability"),
                    "output": str(private / (language + "-parity.json"))}
            native_script = private / "native.init.gradle"
            native_script.write_text(IMPORTED_NATIVE_PARITY_INIT)
            java_script = private / "java.init.gradle"
            java_script.write_text(IMPORTED_JAVA_PARITY_INIT)
            config_path = private / "native.json"
            config_path.write_bytes(canonical_json_bytes(config))
            gradle = [str(root / "gradlew"), "--no-configuration-cache",
                "--no-build-cache", "--max-workers=4", "--console=plain"]
            native_options = ["--init-script", str(native_script),
                "-DcodexAgent.importedNativeParityInputs=" + str(config_path)]
            run(gradle + native_options + [":codex-agent-sdk:verify" + titles[name] + "BindingParity"
                for name in titles] + [":verifyImportedCAbiBindingParity"])
            run(gradle + ["--init-script", str(java_script),
                "-DcodexAgent.importedJavaParityInputs=" + str(inputs["java"]),
                "-DcodexAgent.importedJavaParityOutput=" + str(private / "java/java-parity.json"),
                ":codex-agent-core:verifyJavaBindingParity"])
            receipts = private / "m8-receipts"
            for name in ("kotlin-parity.json", "javascript-typescript-parity.json", "swift-parity.json", "objective-c-parity.json"):
                copy(files[name], receipts / name)
            copy(private / "java/java-parity.json", receipts / "java-parity.json")
            copy(private / "cabi/c-abi-parity.json", receipts / "c-abi-parity.json")

            def tool(command, **options):
                run([str(tooling["javaExecutable"]), "-jar", str(jar), command] +
                    [item for key, value in options.items() for item in ("--" + key.replace("_", "-"), str(value))])

            def audit(phase, directory, destination):
                tool("audit-cross-language-bindings", phase=phase, api_report=files["canonical-api.json"],
                    coverage_receipt=files["canonical-coverage.json"], receipts=directory, output=destination)

            audit("M8", receipts, result / "binding-obligations-m8.json")
            for language in titles:
                phase = "M9_" + language.upper()
                next_receipts = private / (phase + "-receipts")
                next_receipts.mkdir()
                for source in receipts.glob("*-parity.json"):
                    tool("advance-cross-language-binding-receipt", phase=phase, source=source,
                        output=next_receipts / source.name)
                copy(private / (language + "-parity.json"), next_receipts / (language + "-parity.json"))
                audit(phase, next_receipts, result / ("binding-obligations-" + phase.lower() + ".json"))
                receipts = next_receipts
            final = result / "m11"
            final.mkdir()
            for source in receipts.glob("*-parity.json"):
                tool("advance-cross-language-binding-receipt", phase="M11", source=source, output=final / source.name)
            for name in ("canonical-api.json", "canonical-coverage.json"):
                copy(files[name], final / name)
            audit("M11", final, final / "binding-obligations-m11.json")
            run(gradle + native_options + [":verifyImportedSdkBindingParity"])
            if product_reuse.load_json_bytes(read_regular_file_bytes(result / "sdk-parity.json"))["result"] != "passed":
                raise ValueError("Full imported SDK parity did not pass")
            (result / "original-phase-identities.json").write_bytes(canonical_json_bytes(list(inputs["phases"].values())))
        # Every original lifetime and tooling authentication check must finish
        # successfully before a report can become available to another caller.
        publish_regular_tree(result, destination)
    return {"evidence": destination / "sdk-parity.json"}


def _caller_policies(sdk_validation_tooling, sdk_apple_validation_policy, *,
                     sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    return {name: value for name, value in (
        ("sdk_validation_tooling", sdk_validation_tooling),
        ("sdk_apple_validation_policy", sdk_apple_validation_policy),
        ("sdk_facade_metadata_admission", sdk_facade_metadata_admission),
        ("sdk_android_metadata_admission", sdk_android_metadata_admission)) if value is not None}


def _selection(plan, discovery, state, repository_root, environ, sdk_validation_tooling=None,
               sdk_apple_validation_policy=None, *, trusted_workflow_sha=None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    plan_bytes = read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    validated = product_reuse._validate_plan(plan, repository_root)
    inspected = product_reuse.inspect_products(plan, discovery, state,
        repository_root=repository_root, environ=environ, include_sdk_selection=True,
        **({"sdk_original_workflow_sha": trusted_workflow_sha} if trusted_workflow_sha is not None else {}),
        **_caller_policies(sdk_validation_tooling, sdk_apple_validation_policy,
            sdk_facade_metadata_admission=sdk_facade_metadata_admission,
            sdk_android_metadata_admission=sdk_android_metadata_admission))
    selection = inspected.get("sdkInputSelection")
    if not isinstance(selection, dict):
        raise ValueError("SDK workflow requires selected SDK consumer work")
    if read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes:
        raise ValueError("SDK workflow plan changed during inspection")
    return validated, selection, plan_bytes


def stage(plan, discovery, state, destination, *, keyring, keys_directory,
          repository_root, environ, token, trusted_workflow_sha=None, artifact_id=None,
          artifact_sha256=None, expected_build_key=None, expected_metadata_receipt_sha256=None,
          sdk_validation_tooling=None, sdk_apple_validation_policy=None,
          runtime_original_producer=None, runtime_original_workflow_sha=None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Delegate source selection and both destination policies, never grant trust."""
    if (runtime_original_producer is None) != (runtime_original_workflow_sha is None):
        raise ValueError("Retained Runtime producer and original workflow pin must be paired")
    tooling = _caller_policies(sdk_validation_tooling, sdk_apple_validation_policy,
        sdk_facade_metadata_admission=sdk_facade_metadata_admission,
        sdk_android_metadata_admission=sdk_android_metadata_admission)
    validated, selection, _ = _selection(plan, discovery, state, repository_root, environ,
                                         trusted_workflow_sha=trusted_workflow_sha, **tooling)
    if selection.get("source") == "released-default":
        if runtime_original_producer is not None:
            raise ValueError("Retained current Runtime identity cannot override a released default")
        return product_reuse.materialize_sdk_default_inputs(plan, discovery, state, destination,
            keyring=keyring, keys_directory=keys_directory, repository_root=repository_root, environ=environ,
            **({"sdk_original_workflow_sha": trusted_workflow_sha} if trusted_workflow_sha is not None else {}),
            **tooling)
    if selection.get("source") != "current-runtime":
        raise ValueError("SDK workflow has an unsupported replayed Runtime source")
    if any(value is None for value in (trusted_workflow_sha, artifact_id, artifact_sha256,
                                      expected_build_key, expected_metadata_receipt_sha256)):
        raise ValueError("Current Runtime SDK handoff requires complete authenticated upload identity")
    return sdk_handoff.capture_sdk_handoff(plan, destination,
        artifact_id=artifact_id, artifact_sha256=artifact_sha256,
        trusted_workflow_sha=runtime_original_workflow_sha or trusted_workflow_sha,
        expected_build_key=expected_build_key, expected_metadata_receipt_sha256=expected_metadata_receipt_sha256,
        sdk_version=selection["sdkVersion"], compatible_release_range=selection["compatibleReleaseRange"],
        compatible_runtime_compatibility_range=selection["compatibleRuntimeCompatibilityRange"],
        expected_contract_payload_sha256=selection["contractPayloadSha256"],
        keyring=keyring, keys_directory=keys_directory, selection_repository_root=repository_root,
        selection_revision=validated["validationCommit"], repository_root=repository_root, environ=environ, token=token,
        **({"original_producer": runtime_original_producer} if runtime_original_producer is not None else {}))


@contextmanager
def verified_inputs(plan, discovery, state, *, artifact_id, artifact_sha256,
                    trusted_workflow_sha, keyring, keys_directory, repository_root, environ, token,
                    sdk_validation_tooling=None, sdk_apple_validation_policy=None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Keep upload, SDK policy and raw Runtime originals verified through consumer use.

    Returned paths expire on exit. Consumers must finish using them inside the
    context and admit their outputs only after its final checks succeed. The
    Runtime carrier's Contract receipts remain its originals, not replacements
    for the current candidate's independently selected Contract predecessors.
    """
    validated, selection, plan_bytes = _selection(plan, discovery, state, repository_root, environ,
                                                sdk_validation_tooling=sdk_validation_tooling,
                                                trusted_workflow_sha=trusted_workflow_sha,
                                                **_caller_policies(None, sdk_apple_validation_policy,
                                                    sdk_facade_metadata_admission=sdk_facade_metadata_admission,
                                                    sdk_android_metadata_admission=sdk_android_metadata_admission))
    with tempfile.TemporaryDirectory(prefix="sdk-consumer-inputs-") as temporary:
        capture = Path(temporary).resolve() / "capture"
        product_reuse.capture_sdk_inputs_upload(plan, capture, artifact_id=artifact_id,
            artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
            expected_source=selection["source"], repository_root=repository_root, environ=environ, token=token)
        inventory = regular_file_inventory(capture, allow_empty=True)

        def unchanged():
            if (regular_file_inventory(capture, allow_empty=True) != inventory
                    or read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes):
                raise ValueError("SDK consumer original plan or captured upload changed during use")

        with verified_apple_original_inputs(capture, expected_source=selection["source"],
                keyring=keyring, keys_directory=keys_directory,
                selection_repository_root=repository_root, selection_revision=validated["validationCommit"],
                expected_contract_payload_sha256=selection["contractPayloadSha256"]) as original:
            unchanged()
            yield {"selection": selection, "capture": capture, **original}
        unchanged()


@contextmanager
def verified_ios_binary_inputs(plan, discovery, state, destination, *, expected_build_key,
                               native_uploads, trusted_workflow_sha, repository_root, environ, token,
                               sdk_validation_tooling=None, sdk_apple_validation_policy=None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Keep elected iOS binary Contract/native originals verified through use.

    This is not package readiness or output admission. The caller must execute
    the binary phase inside this lifetime and finalize only after successful exit.
    """
    from products.contract_projection import verify_contract_component_projection
    from sdk_apple_native import verified_sdk_apple_native_inputs

    root = Path(repository_root).resolve(strict=True)
    discovery, state, destination = product_reuse._product_materialization_paths(root, discovery, state, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK iOS binary inputs require a fresh destination")
    plan_bytes = read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    verified = product_reuse._verified_product_state(plan, discovery, state, root, environ, sdk_validation_tooling,
        sdk_original_workflow_sha=trusted_workflow_sha,
        **_caller_policies(None, sdk_apple_validation_policy,
            sdk_facade_metadata_admission=sdk_facade_metadata_admission,
            sdk_android_metadata_admission=sdk_android_metadata_admission))
    instance = PhaseInstanceId("sdk", "sdk-ios", "binary", "ios")
    elected = verified.prior_ready_plans.get(instance)
    if elected is None or elected["buildKey"] != expected_build_key:
        raise ValueError("SDK iOS binary is not ready with the expected elected key")
    evidence = verified.rebased_request.get("contractEvidence")
    if evidence is None or evidence["expectedTrustDomain"] != "release":
        raise ValueError("SDK iOS binary requires authenticated release Contract evidence")
    destination = product_reuse._prepare_destination(destination, root)
    trust = product_reuse._release_trust(root, verified.plan["validationCommit"], destination / "policy")
    if trust is None:
        raise ValueError("SDK iOS binary requires Git-authoritative release policy")
    predecessors = destination / "predecessors"
    ready = product_reuse._materialize_product_predecessors(
        verified, instance, predecessors, expected_build_key, root)

    def original(product, component, phase, target):
        if (product, component, target) != ("contract", "contract", "common"):
            raise ValueError("SDK iOS binary requested an unrelated Contract predecessor")
        directory = predecessors / "-".join((product, component, phase, target))
        receipt_path = directory / "phase-receipt.json"
        receipt = product_reuse.validate_phase_receipt(product_reuse._canonical_control(receipt_path, "Original Contract receipt"))
        manifest = product_reuse.verify_output_manifest_identity(
            directory / "stage", product, component, phase, target, receipt["productVersion"])
        if manifest["outputs"] != receipt["outputs"]:
            raise ValueError("SDK iOS Contract stage differs from its original receipt")
        return {"stage": directory / "stage", "receiptPath": receipt_path, "receipt": receipt}

    def one_output(record, kind):
        outputs = [row for row in record["receipt"]["outputs"] if row["kind"] == kind]
        if len(outputs) != 1:
            raise ValueError("SDK iOS binary requires one original Contract payload")
        return record["stage"] / outputs[0]["relativePath"]

    contract, version, handoff, _, handoff_files = product_reuse._capture_runtime_contract(
        root, evidence, original, one_output, destination, trust)
    stem = f"codex-agent-contract-{version}"
    before = regular_file_inventory(destination, allow_empty=True)
    verify_contract_component_projection(contract["stage"], contract["receiptPath"],
        handoff / f"{stem}.attestation.json", handoff / f"{stem}.attestation.sig", handoff / "public-key.pub",
        expected_trust_domain="release", expected_contract_version=version,
        required_components=("ios-arm64", "ios-simulator-arm64"), keyring=trust.keyring, keys_directory=trust.keys)

    def unchanged():
        if (regular_file_inventory(handoff) != handoff_files or
                regular_file_inventory(destination, allow_empty=True) != before or
                read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes):
            raise ValueError("SDK iOS binary original inputs changed during use")

    unchanged()
    with verified_sdk_apple_native_inputs(plan, uploads=native_uploads,
            trusted_workflow_sha=trusted_workflow_sha, repository_root=root, environ=environ, token=token) as native:
        if native["producer"] != verified.producer:
            raise ValueError("SDK iOS native evidence differs from the elected producer")
        unchanged()
        try:
            yield {"ready": ready, "producer": verified.producer,
                   "sdkVersion": verified.expected_fixed["versions"]["sdk"], "contract": contract,
                   "contractHandoff": handoff, "native": native["directory"],
                   "nativeCaptureRoot": native["captureRoot"], "inputs": destination}
        finally:
            unchanged()
    unchanged()


def execute_ios_binary(plan, discovery, state, destination, *, expected_build_key,
                       native_uploads, trusted_workflow_sha, repository_root, environ, token,
                       sdk_validation_tooling=None, sdk_apple_validation_policy=None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Execute an elected binary; receipt creation follows every input exit check."""
    from sdk_ios_binary import execute

    root = Path(repository_root).resolve(strict=True)
    discovery, state, destination = product_reuse._product_materialization_paths(root, discovery, state, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK iOS binary worker requires a fresh destination")
    tooling = _caller_policies(sdk_validation_tooling, sdk_apple_validation_policy,
        sdk_facade_metadata_admission=sdk_facade_metadata_admission,
        sdk_android_metadata_admission=sdk_android_metadata_admission)
    with verified_ios_binary_inputs(plan, discovery, state, destination / "inputs",
            expected_build_key=expected_build_key, native_uploads=native_uploads,
            trusted_workflow_sha=trusted_workflow_sha, repository_root=root, environ=environ, token=token, **tooling) as inputs:
        ready, producer, version = inputs["ready"], inputs["producer"], inputs["sdkVersion"]
        # External original evidence, never part of the reusable binary stage.
        retained_native = destination / "native-original"
        native_inventory = regular_file_inventory(inputs["nativeCaptureRoot"], allow_empty=True)
        snapshot_regular_tree(inputs["nativeCaptureRoot"], retained_native, allow_empty=True)
        if regular_file_inventory(retained_native, allow_empty=True) != native_inventory:
            raise ValueError("SDK iOS binary retained native evidence differs from its original capture")
        result = execute(ready, producer=producer, sdk_version=version,
            contract_metadata=inputs["contract"], verified_contract_handoff=inputs["contractHandoff"],
            native_evidence=inputs["native"], repository_root=root, destination=destination / "worker", environ=environ)
        if (regular_file_inventory(inputs["nativeCaptureRoot"], allow_empty=True) != native_inventory
                or regular_file_inventory(retained_native, allow_empty=True) != native_inventory):
            raise ValueError("SDK iOS binary native evidence changed during execution")
    if regular_file_inventory(retained_native, allow_empty=True) != native_inventory:
        raise ValueError("SDK iOS binary native evidence changed during context exit")
    if regular_file_inventory(result["stage"]) != result["outputInventory"]:
        raise ValueError("SDK iOS binary output changed before finalization")
    trust = "development" if producer["event"] == "pull_request" else "release"
    return product_reuse.finalize_phase_object(stage_root=result["stage"], phase_plan=ready,
        producer=producer, product_version=version, trust_domain=trust, destination=destination / "shard")


def matrix(plan, discovery, state, github_output_path, *, repository_root=None, environ=None, ios_binary=False, family=None,
           trusted_workflow_sha=None,
           sdk_validation_tooling=None, sdk_apple_validation_policy=None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Expose only the fixed replay-elected SDK family before platform setup."""
    from sdk_phase import route

    if type(ios_binary) is not bool:
        raise ValueError("SDK binary projection must be boolean")
    if family is not None:
        product_reuse._sdk_family_worker_instance(None, family)
        if ios_binary:
            raise ValueError("SDK family and binary projection are mutually exclusive")
    def selected(instance):
        if family is not None:
            return product_reuse._sdk_family_worker_instance(instance, family)
        return (product_reuse._sdk_ios_binary_worker_instance if ios_binary else
                product_reuse._sdk_javascript_worker_instance)(instance)

    def worker_route(ready):
        if family in ("native-validation", "native-metadata"):
            from runtime_native_phase import _HOSTS
            host = ready["target"] if family == "native-validation" else "linux-x64"
            label, os_name, arch = _HOSTS[host]
            return {"runner": label, "runnerOs": os_name, "runnerArch": arch}
        if family == "native-package":
            from sdk_native_phase import route as native_route
            return native_route(ready)
        if ios_binary or family in ("ios-package", "ios-validation", "ios-metadata", "core-binary"):
            return {"runner": "macos-26", "runnerOs": "macOS", "runnerArch": "ARM64"}
        if family in ("csharp-binary", "javascript-metadata", "core-package", "core-metadata",
                      "android-binary", "android-package", "android-validation", "android-metadata"):
            return {"runner": "ubuntu-24.04", "runnerOs": "Linux", "runnerArch": "X64"}
        return route(ready)
    inspected = product_reuse.inspect_products(plan, discovery, state,
        repository_root=repository_root, environ=environ,
        **({"sdk_original_workflow_sha": trusted_workflow_sha} if trusted_workflow_sha is not None else {}),
        **_caller_policies(sdk_validation_tooling, sdk_apple_validation_policy,
            sdk_facade_metadata_admission=sdk_facade_metadata_admission,
            sdk_android_metadata_admission=sdk_android_metadata_admission))
    rows = [{**{field: ready[field] for field in ("product", "component", "phase", "target", "buildKey")},
             **worker_route(ready)}
            for ready in inspected["readyPlans"]
            if selected(product_reuse._identity(ready))]
    value = {"include": rows}
    github_output(github_output_path, {"sdk_matrix": canonical_json_bytes(value).decode().strip(),
                                      "sdk_workers_required": bool(rows)})
    return value


def capture(plan, destination, github_output_path, *, artifact_id, artifact_sha256,
            trusted_workflow_sha, state_wave=0, sdk_state_wave=None,
            repository_root=None, environ=None, token, ios_binary=False, family=None, sdk_validation_tooling=None,
            sdk_apple_validation_policy=None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Capture exact original state, then replay SDK readiness independently."""
    if type(ios_binary) is not bool:
        raise ValueError("SDK binary projection must be boolean")
    if family is not None:
        product_reuse._sdk_family_worker_instance(None, family)
        if ios_binary:
            raise ValueError("SDK family and binary projection are mutually exclusive")
    product_reuse.capture_runtime_resume_upload(plan, destination, artifact_id=artifact_id,
        artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
        state_wave=state_wave, **({"sdk_state_wave": sdk_state_wave} if sdk_state_wave is not None else {}),
        repository_root=repository_root, environ=environ, token=token)
    original = destination / "original"
    paths = {"input_root": original,
        "plan_path": original / "product-resume-inputs/plan/impact-plan.json",
        "discovery_root": original / "product-resume-state",
        "state_root": original / ("runtime-state" if state_wave or sdk_state_wave is not None else "product-resume-state")}
    value = matrix(paths["plan_path"], paths["discovery_root"], paths["state_root"], github_output_path,
                   repository_root=repository_root, environ=environ,
                   trusted_workflow_sha=trusted_workflow_sha, **({"ios_binary": True} if ios_binary else {}),
                   **_caller_policies(sdk_validation_tooling, sdk_apple_validation_policy,
                       sdk_facade_metadata_admission=sdk_facade_metadata_admission,
                       sdk_android_metadata_admission=sdk_android_metadata_admission),
                   **({"family": family} if family is not None else {}))
    github_output(github_output_path, {name: str(path) for name, path in paths.items()})
    return {**paths, "matrix": value}


def capture_transport(plan, destination, github_output_path, *, artifact_id,
        artifact_sha256, trusted_workflow_sha, sdk_state_wave=None, state_wave=0, repository_root,
        environ, token):
    """Authenticate only the current original state upload before policy election.

    The caller must separately pin its elected receipt/object identities, build
    current policy, and replay the state. Transport capture alone grants no
    metadata or phase authority and deliberately emits no worker matrix.
    """
    if (type(state_wave) is not int or state_wave not in range(6)
            or (sdk_state_wave is not None and (type(sdk_state_wave) is not int
                or sdk_state_wave not in range(1, 20) or state_wave != 0))):
        raise ValueError("SDK transport requires one exact current state wave")
    root = Path(repository_root).resolve(strict=True)
    plan, _, destination = product_reuse._product_materialization_paths(root, plan, plan, destination)
    output = Path(github_output_path).absolute()
    if (output.resolve(strict=False) != output or output == root or root in output.parents
            or output == destination or destination in output.parents):
        raise ValueError("SDK transport output must be outside source and captured state")
    descriptor = os.open(output, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "a", encoding="utf-8") as held_output:
        identity = os.fstat(held_output.fileno())
        if not stat.S_ISREG(identity.st_mode) or identity.st_nlink != 1:
            raise ValueError("SDK transport output must be a singly linked regular runner file")
        product_reuse.capture_runtime_resume_upload(plan, destination, artifact_id=artifact_id,
            artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
            sdk_state_wave=sdk_state_wave, state_wave=state_wave, repository_root=root,
            environ=environ, token=token)
        original = destination / "original"
        paths = {"input_root": original,
            "plan_path": original / "product-resume-inputs/plan/impact-plan.json",
            "discovery_root": original / "product-resume-state",
            "state_root": original / ("runtime-state" if state_wave or sdk_state_wave is not None
                                      else "product-resume-state")}
        for name, path in paths.items():
            if "\n" in str(path) or "\r" in str(path):
                raise ValueError("SDK transport output path contains a line break")
            held_output.write(f"{name}={path}\n")
    return paths


def collect(input_root, destination, github_output_path, *, wave, trusted_workflow_sha,
            repository_root=None, environ=None, token, ios_binary=False, family=None, sdk_validation_tooling=None,
            sdk_apple_validation_policy=None,
            sdk_worker_workflow_path=None, sdk_worker_job_name=None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Advance only the exact elected SDK partition using the shared collector."""
    family_waves = {"csharp-binary": 19, "native-package": 4, "ios-package": 5, "javascript-metadata": 6,
                    "native-validation": 7, "native-metadata": 8, "ios-validation": 9, "ios-metadata": 10,
                    "core-binary": 11, "core-package": 12, "core-validation": 13, "core-metadata": 14,
                    "android-binary": 15, "android-package": 16, "android-validation": 17,
                    "android-metadata": 18}
    if family is not None:
        product_reuse._sdk_family_worker_instance(None, family)
    allowed = (family_waves[family],) if family is not None else (3,) if ios_binary else (1, 2)
    if type(ios_binary) is not bool or (ios_binary and family is not None) or type(wave) is not int or wave not in allowed:
        raise ValueError("SDK collection requires the exact wave for its elected family")
    scope = ({"sdk_family": family} if family is not None else
             {"sdk_ios_binary_only": True} if ios_binary else {"sdk_javascript_only": True})
    tooling = _caller_policies(sdk_validation_tooling, sdk_apple_validation_policy,
        sdk_facade_metadata_admission=sdk_facade_metadata_admission,
        sdk_android_metadata_admission=sdk_android_metadata_admission)
    root = Path(repository_root or Path(__file__).resolve().parents[1]).resolve()
    input_root, _, destination = product_reuse._product_materialization_paths(root, input_root, input_root, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK collection destination must not exist")
    plan = input_root / "product-resume-inputs/plan/impact-plan.json"
    discovery = input_root / "product-resume-state"
    state = input_root / "runtime-state" if (input_root / "runtime-state").exists() else discovery
    collection = product_reuse.collect_runtime_workers(plan, discovery, state, destination / "collection",
        trusted_workflow_sha=trusted_workflow_sha, repository_root=root, environ=environ, token=token,
        sdk_worker_workflow_path=sdk_worker_workflow_path, sdk_worker_job_name=sdk_worker_job_name,
        **scope, **tooling)
    shards = [destination / "collection" / row["shardDirectory"]
              for row in collection["rows"] if row["result"] == "success"]
    failed = tuple(product_reuse._identity(row) for row in collection["rows"] if row["result"] != "success")
    evidence = tuple(destination / "collection" / row["sdkValidationEvidenceDirectory"]
                     for row in collection["rows"] if row["result"] == "success") if family == "native-validation" else ()
    apple_evidence = tuple(destination / "collection" / row["sdkAppleValidationEvidenceDirectory"]
                           for row in collection["rows"] if row["result"] == "success") if family == "ios-validation" else ()
    handoff = destination / "handoff"
    advanced = product_reuse.advance_products(plan, discovery, state, shards, handoff / "runtime-state",
        github_output_path, repository_root=root, environ=environ, failed_instances=failed, **scope, **tooling,
        sdk_original_workflow_sha=trusted_workflow_sha,
        **({"sdk_evidence_roots": evidence} if family == "native-validation" else {}),
        **({"sdk_apple_evidence_roots": apple_evidence} if family == "ios-validation" else {}))
    for name in ("product-resume-inputs", "product-resume-state"):
        snapshot_regular_tree(input_root / name, handoff / name, allow_empty=True)
    if failed:
        github_output(github_output_path, {"sdk_matrix": '{"include":[]}', "sdk_workers_required": False})
    else:
        ready = matrix(handoff / "product-resume-inputs/plan/impact-plan.json", handoff / "product-resume-state",
                       handoff / "runtime-state", github_output_path, repository_root=root, environ=environ,
                       trusted_workflow_sha=trusted_workflow_sha, **tooling,
                       **({"ios_binary": True} if ios_binary else {}),
                       **({"family": family} if family is not None else {}))
        if wave >= 2 and ready["include"]:
            raise ValueError("SDK workers remain after their final collection wave")
    return advanced


def prepare_native(plan, discovery, state, destination, *, component, expected_build_key,
                   artifact_id, artifact_sha256, trusted_workflow_sha, keyring, keys_directory,
                   repository_root, environ, token, sdk_validation_tooling=None, sdk_apple_validation_policy=None,
                   preparation_phase="package", preparation_target="desktop",
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Prepare once from elected original inputs; this does not admit an upload.

    The transport caller must bind these outputs and the retained original plan
    to the observed preparation producer before any independent language job.
    No new product phase or receipt is manufactured for shared preparation.
    """
    from sdk_native_prepare import execute

    if component not in NATIVE_BINDINGS:
        raise ValueError("Unsupported native SDK preparation component")
    root = Path(repository_root).resolve(strict=True)
    discovery, state, destination = product_reuse._product_materialization_paths(
        root, discovery, state, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK native preparation destination must not exist")
    plan_bytes = read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    instance = PhaseInstanceId("sdk", component, preparation_phase, preparation_target)
    if (preparation_phase not in {"package", "validation", "metadata"}
            or not product_reuse._sdk_family_worker_instance(instance, "native-" + preparation_phase)):
        raise ValueError("Native preparation requires an exact native consumer anchor")
    fields = {"product": "sdk", "component": component, "phase": preparation_phase, "target": preparation_target}
    tooling = _caller_policies(sdk_validation_tooling, sdk_apple_validation_policy,
        sdk_facade_metadata_admission=sdk_facade_metadata_admission,
        sdk_android_metadata_admission=sdk_android_metadata_admission)
    with verified_inputs(plan, discovery, state, artifact_id=artifact_id, artifact_sha256=artifact_sha256,
            trusted_workflow_sha=trusted_workflow_sha, keyring=keyring, keys_directory=keys_directory,
            repository_root=root, environ=environ, token=token, **tooling) as inputs:
        selection = inputs["selection"]
        if fields not in selection["consumers"]:
            raise ValueError("SDK native preparation consumer is not selected")
        prepared = destination / "inputs"
        ready = product_reuse.materialize_product_predecessors(plan, discovery, state, instance, prepared,
            expected_build_key=expected_build_key, repository_root=root, environ=environ,
            sdk_original_workflow_sha=trusted_workflow_sha, **tooling)
        producer = product_reuse.validate_producer(product_reuse._canonical_control(
            prepared / "producer.json", "Elected native SDK producer"))
        contract = product_reuse.validate_phase_receipt(product_reuse._canonical_control(
            prepared / "contract-contract-metadata-common/phase-receipt.json", "Current Contract metadata"))
        bundles = [row for row in contract["outputs"] if row["kind"] == "contract-bundle"]
        if (tuple(contract[name] for name in ("product", "component", "phase", "target")) !=
                ("contract", "contract", "metadata", "common") or len(bundles) != 1
                or bundles[0]["sha256"] != selection["contractPayloadSha256"]):
            raise ValueError("Elected current Contract differs from verified native SDK inputs")
        before = regular_file_inventory(prepared, allow_empty=True)

        def original(product, runtime_component, phase, target):
            identity = PhaseInstanceId(product, runtime_component, phase, target)
            directory = prepared / "-".join((product, runtime_component, phase, target))
            receipt_path = directory / "phase-receipt.json"
            raw = read_regular_file_bytes(receipt_path)
            receipt = product_reuse.validate_phase_receipt(load_canonical_json_bytes(raw))
            if (product != "runtime" or runtime_component not in NATIVE_TARGETS or target != runtime_component
                    or phase not in {"package", "validation"}
                    or raw != inputs["runtime"]["receiptBytes"].get(identity)
                    or tuple(receipt[name] for name in ("product", "component", "phase", "target")) !=
                    (product, runtime_component, phase, target)):
                raise ValueError("Native preparation predecessor differs from its verified original")
            manifest = product_reuse.verify_output_manifest_identity(
                directory / "stage", product, runtime_component, phase, target, receipt["productVersion"])
            if manifest["outputs"] != receipt["outputs"]:
                raise ValueError("Native preparation stage differs from its original receipt")
            return {"stage": directory / "stage", "receiptPath": receipt_path, "receipt": receipt}

        runtime_stages = destination / "runtime-stages"
        for target in NATIVE_TARGETS:
            for phase in ("package", "validation"):
                record = original("runtime", target, phase, target)
                snapshot_regular_tree(record["stage"], runtime_stages / target / phase)
        runtime_before = regular_file_inventory(runtime_stages)

        def unchanged():
            if (regular_file_inventory(prepared, allow_empty=True) != before
                    or regular_file_inventory(runtime_stages) != runtime_before):
                raise ValueError("Native preparation original predecessor inputs changed")

        unchanged()
        result = execute(ready, producer=producer, sdk_version=selection["sdkVersion"],
            repository_root=root, destination=destination / "worker", runtime_stages=runtime_stages,
            compatibility_request=inputs["sdk"]["directory"] / REQUEST_NAME,
            predecessor=original, environ=environ)
        unchanged()
    unchanged()
    def outputs_unchanged():
        if (regular_file_inventory(result["preparedSources"]) != result["preparedSourcesInventory"]
                or regular_file_inventory(result["stagedSdks"]) != result["stagedSdkInventory"]
                or read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024,
                                           reject_symlink_parents=True) != plan_bytes):
            raise ValueError("Native SDK preparation outputs or original plan changed before handoff")

    outputs_unchanged()
    diagnostics = {name: read_regular_file_bytes(result["diagnostics"] / name,
                   reject_symlink_parents=True) for name in ("gradle.log", "execution.json")}
    # This is an external transport envelope, not a product phase or receipt.
    # The receiving worker must authenticate its upload owner and original plan.
    with tempfile.TemporaryDirectory(prefix="sdk-native-prepared-") as temporary:
        upload = Path(temporary).resolve() / "upload"
        (upload / "original-plan").mkdir(parents=True)
        (upload / "original-plan/impact-plan.json").write_bytes(plan_bytes)
        phase_bytes = read_regular_file_bytes(prepared / "phase-plan.json", reject_symlink_parents=True)
        if phase_bytes != canonical_json_bytes(ready):
            raise ValueError("Native preparation elected phase plan changed before handoff")
        (upload / "original-plan/phase-plan.json").write_bytes(phase_bytes)
        for name, source, inventory in (
                ("prepared-sources", result["preparedSources"], result["preparedSourcesInventory"]),
                ("staged-sdks", result["stagedSdks"], result["stagedSdkInventory"])):
            snapshot_regular_tree(source, upload / name)
            if regular_file_inventory(upload / name) != inventory:
                raise ValueError("Native preparation output changed during transport capture")
        (upload / "diagnostics").mkdir()
        for name, raw in diagnostics.items():
            (upload / "diagnostics" / name).write_bytes(raw)
        unchanged()
        outputs_unchanged()
        if any(read_regular_file_bytes(result["diagnostics"] / name, reject_symlink_parents=True) != raw
               for name, raw in diagnostics.items()):
            raise ValueError("Native preparation diagnostics changed during transport capture")
        publish_regular_tree(upload, destination / "upload", allow_empty=True)
    return result


def execute_javascript(plan, discovery, state, destination, *, phase, expected_build_key,
                       artifact_id, artifact_sha256, trusted_workflow_sha, keyring, keys_directory,
                       repository_root, environ, token, sdk_validation_tooling=None, sdk_apple_validation_policy=None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Execute elected SDK work; finalize only after original input contexts close."""
    from sdk_javascript_phase import execute

    if phase not in {"package", "validation"}:
        raise ValueError("Unsupported SDK JavaScript worker phase")
    root = Path(repository_root).resolve(strict=True)
    discovery, state, destination = product_reuse._product_materialization_paths(
        root, discovery, state, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK JavaScript worker destination must not exist")
    instance = PhaseInstanceId("sdk", "javascript", phase, "node")
    fields = {"product": "sdk", "component": "javascript", "phase": phase, "target": "node"}
    tooling = _caller_policies(sdk_validation_tooling, sdk_apple_validation_policy,
        sdk_facade_metadata_admission=sdk_facade_metadata_admission,
        sdk_android_metadata_admission=sdk_android_metadata_admission)
    with verified_inputs(plan, discovery, state, artifact_id=artifact_id, artifact_sha256=artifact_sha256,
            trusted_workflow_sha=trusted_workflow_sha, keyring=keyring, keys_directory=keys_directory,
            repository_root=root, environ=environ, token=token, **tooling) as inputs:
        selection = inputs["selection"]
        if fields not in selection["consumers"]:
            raise ValueError("SDK JavaScript worker is not selected")
        prepared = destination / "inputs"
        ready = product_reuse.materialize_product_predecessors(plan, discovery, state, instance, prepared,
            expected_build_key=expected_build_key, repository_root=root, environ=environ,
            sdk_original_workflow_sha=trusted_workflow_sha, **tooling)
        producer = product_reuse.validate_producer(product_reuse._canonical_control(
            prepared / "producer.json", "Elected SDK producer"))
        contract = product_reuse.validate_phase_receipt(product_reuse._canonical_control(
            prepared / "contract-contract-metadata-common/phase-receipt.json", "Current Contract metadata"))
        bundles = [row for row in contract["outputs"] if row["kind"] == "contract-bundle"]
        if len(bundles) != 1 or bundles[0]["sha256"] != selection["contractPayloadSha256"]:
            raise ValueError("Elected current Contract differs from verified SDK inputs")
        before = regular_file_inventory(prepared, allow_empty=True)

        def original(product, component, source_phase, target):
            identity = PhaseInstanceId(product, component, source_phase, target)
            directory = prepared / "-".join((product, component, source_phase, target))
            receipt_path = directory / "phase-receipt.json"
            raw = read_regular_file_bytes(receipt_path)
            receipt = product_reuse.validate_phase_receipt(load_canonical_json_bytes(raw))
            if product == "runtime" and raw != inputs["runtime"]["receiptBytes"].get(identity):
                raise ValueError("Elected SDK Runtime predecessor differs from the verified original")
            return {"stage": directory / "stage", "receiptPath": receipt_path, "receipt": receipt}

        trust = "development" if producer["event"] == "pull_request" else "release"
        result = execute(ready, producer=producer, sdk_version=selection["sdkVersion"], trust_domain=trust,
            repository_root=root, destination=destination / "worker", predecessor=original, environ=environ,
            compatibility_request=inputs["sdk"]["directory"] / REQUEST_NAME if phase == "package" else None)
        if regular_file_inventory(prepared, allow_empty=True) != before:
            raise ValueError("Elected SDK predecessor inputs changed during execution")
    if regular_file_inventory(prepared, allow_empty=True) != before:
        raise ValueError("Elected SDK predecessor inputs changed before finalization")
    if regular_file_inventory(result["stage"]) != result["outputInventory"]:
        raise ValueError("SDK JavaScript output changed before finalization")
    return product_reuse.finalize_phase_object(stage_root=result["stage"], phase_plan=ready,
        producer=producer, product_version=selection["sdkVersion"], trust_domain=trust,
        destination=destination / "shard")


def _workflow_main(argv):
    parser = argparse.ArgumentParser(description="Replay, capture and collect exact SDK phase work", allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    parsers = {name: commands.add_parser(name, allow_abbrev=False) for name in ("matrix", "capture", "collect")}
    for name, command in parsers.items():
        scope = command.add_mutually_exclusive_group()
        scope.add_argument("--ios-binary", action="store_true")
        scope.add_argument("--family", choices=product_reuse.SDK_WORKER_FAMILIES)
        command.add_argument("--github-output", dest="github_output_path", type=Path, required=True)
        command.add_argument("--repository-root", type=Path)
        command.add_argument("--sdk-validation-tooling", type=Path)
        command.add_argument("--sdk-apple-validation-policy", type=Path)
        add_metadata_admission_arguments(command)
        if name == "matrix":
            for flag, dest in (("plan", "plan"), ("discovery-root", "discovery"), ("state-root", "state")):
                command.add_argument(f"--{flag}", dest=dest, type=Path, required=True)
            command.add_argument("--trusted-workflow-sha")
        else:
            command.add_argument("--destination", type=Path, required=True)
            command.add_argument("--trusted-workflow-sha", required=True)
    captured = parsers["capture"]
    captured.add_argument("--plan", type=Path, required=True)
    captured.add_argument("--artifact-id", type=int, required=True)
    captured.add_argument("--artifact-sha256", required=True)
    captured.add_argument("--state-wave", type=int, default=0)
    captured.add_argument("--sdk-state-wave", type=int)
    parsers["collect"].add_argument("--input-root", type=Path, required=True)
    parsers["collect"].add_argument("--wave", type=int, choices=range(1, 20), required=True)
    parsers["collect"].add_argument("--sdk-worker-workflow-path")
    parsers["collect"].add_argument("--sdk-worker-job-name")
    arguments = vars(parser.parse_args(argv))
    command = arguments.pop("command")
    try:
        with metadata_admission_options(arguments) as admissions:
            policy = arguments.pop("sdk_validation_tooling")
            if policy is not None:
                arguments["sdk_validation_tooling"] = product_reuse._canonical_control(policy, "Caller SDK tooling policy")
            apple_policy = arguments.pop("sdk_apple_validation_policy")
            if apple_policy is not None:
                arguments["sdk_apple_validation_policy"] = product_reuse._canonical_control(apple_policy, "Caller Apple validation policy")
            return {"matrix": matrix, "capture": capture, "collect": collect}[command](**arguments, **admissions,
                environ=os.environ, **({"token": os.environ.get("GITHUB_TOKEN", "")} if command != "matrix" else {}))
    except (OSError, ValueError) as error:
        parser.error(str(error))


def _capture_transport_main(argv):
    parser = argparse.ArgumentParser(description="Capture exact official SDK state transport before caller policy selection",
                                     allow_abbrev=False)
    for name in ("plan", "destination", "github-output", "repository-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("trusted-workflow-sha", "artifact-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--state-wave", type=int, choices=range(6), default=0)
    parser.add_argument("--sdk-state-wave", type=int, choices=range(1, 20))
    arguments = vars(parser.parse_args(argv))
    arguments["github_output_path"] = arguments.pop("github_output")
    try:
        # The parent directory is runner-owned; O_NOFOLLOW protects the final file.
        runner_output = os.environ.get("GITHUB_OUTPUT")
        if not runner_output or Path(runner_output).absolute() != arguments["github_output_path"].absolute():
            raise ValueError("SDK transport output must be the runner-provided GITHUB_OUTPUT")
        capture_transport(**arguments, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


def _ios_binary_main(argv):
    parser = argparse.ArgumentParser(description="Execute only the elected SDK iOS binary phase")
    for name in ("plan", "discovery-root", "state-root", "destination", "repository-root"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("trusted-workflow-sha", "expected-build-key"):
        parser.add_argument(f"--{name}", required=True)
    lanes = ("native-tests", "rust-device", "rust-simulator")
    for lane in lanes:
        parser.add_argument(f"--{lane}-artifact-id", type=int, required=True)
        parser.add_argument(f"--{lane}-artifact-sha256", required=True)
    parser.add_argument("--sdk-validation-tooling", type=Path)
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    add_metadata_admission_arguments(parser)
    arguments = vars(parser.parse_args(argv))
    uploads = {f"ios-{lane}": {
        "artifactId": arguments.pop(lane.replace("-", "_") + "_artifact_id"),
        "artifactSha256": arguments.pop(lane.replace("-", "_") + "_artifact_sha256"),
    } for lane in lanes}
    try:
        with metadata_admission_options(arguments) as admissions:
            plan, discovery, state, destination = (arguments.pop(name) for name in (
                "plan", "discovery_root", "state_root", "destination"))
            policy = arguments.pop("sdk_validation_tooling")
            if policy is not None:
                arguments["sdk_validation_tooling"] = product_reuse._canonical_control(policy, "Caller SDK tooling policy")
            apple_policy = arguments.pop("sdk_apple_validation_policy")
            if apple_policy is not None:
                arguments["sdk_apple_validation_policy"] = product_reuse._canonical_control(apple_policy, "Caller Apple validation policy")
            execute_ios_binary(plan, discovery, state, destination, **arguments, **admissions,
                native_uploads=uploads, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


def _parity_main(argv, *, full=False):
    parser = argparse.ArgumentParser(description="Verify parity against authenticated immutable products", allow_abbrev=False)
    for name in ("plan", "discovery-root", "state-root", "destination", "repository-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("sdk-validation-tooling", "sdk-apple-validation-policy"):
        parser.add_argument("--" + name, type=Path, required=full and name == "sdk-validation-tooling")
    parser.add_argument("--sdk-original-workflow-sha", required=True)
    add_metadata_admission_arguments(parser)
    arguments = vars(parser.parse_args(argv))
    try:
        with metadata_admission_options(arguments) as admissions:
            for name in ("sdk_validation_tooling", "sdk_apple_validation_policy"):
                if arguments[name] is not None:
                    arguments[name] = product_reuse._canonical_control(arguments[name], "Caller Java parity " + name)
            plan, discovery, state, destination = (arguments.pop(name) for name in
                ("plan", "discovery_root", "state_root", "destination"))
            execute = execute_parity if full else execute_java_parity
            execute(plan, discovery, state, destination, **arguments, **admissions, environ=os.environ)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    return 0


@verification_scoped
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "parity":
        return _parity_main(argv[1:], full=True)
    if argv and argv[0] == "java-parity":
        return _parity_main(argv[1:])
    if argv and argv[0] == "capture-transport":
        return _capture_transport_main(argv[1:])
    if argv and argv[0] == "maven-binary":
        from sdk_maven_binary_workflow import main as maven_binary_main
        return maven_binary_main(argv[1:])
    if argv and argv[0] == "android-metadata":
        from sdk_android_metadata_workflow import main as android_metadata_main
        return android_metadata_main(argv[1:])
    if argv and argv[0] == "core-metadata":
        from sdk_facade_metadata_workflow import main as facade_metadata_main
        return facade_metadata_main(argv[1:])
    if argv and argv[0] == "android-validation":
        from sdk_android_validation_workflow import main as android_validation_main
        return android_validation_main(argv[1:])
    if argv and argv[0] == "maven-package":
        from sdk_maven_package_workflow import main as maven_package_main
        return maven_package_main(argv[1:])
    if argv and argv[0] == "core-validation":
        from sdk_facade_workflow import main as facade_main
        return facade_main(argv[1:])
    if argv and argv[0] == "ios-metadata":
        from sdk_ios_metadata_workflow import main as ios_metadata_main
        return ios_metadata_main(argv[1:])
    if argv and argv[0] == "ios-validation":
        from sdk_ios_validation_workflow import main as ios_validation_main
        return ios_validation_main(argv[1:])
    if argv and argv[0] == "native-validation":
        from sdk_native_validation_workflow import main as validation_main
        return validation_main(argv[1:])
    if argv and argv[0] == "native-metadata":
        from sdk_native_metadata_workflow import main as metadata_main
        return metadata_main(argv[1:])
    if argv and argv[0] == "javascript-metadata":
        from sdk_javascript_metadata_workflow import main as metadata_main
        return metadata_main(argv[1:])
    if argv and argv[0] == "ios-package":
        from sdk_ios_package_workflow import main as ios_package_main
        return ios_package_main(argv[1:])
    if argv and argv[0] == "native-package":
        from sdk_native_package_workflow import main as native_package_main
        return native_package_main(argv[1:])
    if argv and argv[0] == "ios-binary":
        return _ios_binary_main(argv[1:])
    if argv and argv[0] in {"matrix", "capture", "collect"}:
        _workflow_main(argv)
        return 0
    javascript = bool(argv and argv[0] == "javascript")
    native_prepare = bool(argv and argv[0] == "native-prepare")
    worker = javascript or native_prepare
    if worker:
        argv.pop(0)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "discovery-root", "state-root", "destination", "keyring", "keys-directory", "repository-root"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--artifact-id", type=int, required=worker)
    for name in ("trusted-workflow-sha", "artifact-sha256", "expected-build-key"):
        parser.add_argument(f"--{name}", required=worker)
    if javascript:
        parser.add_argument("--phase", choices=("package", "validation"), required=True)
    elif native_prepare:
        parser.add_argument("--component", choices=NATIVE_BINDINGS, required=True)
        parser.add_argument("--preparation-phase", choices=("package", "validation", "metadata"), default="package")
        parser.add_argument("--preparation-target", default="desktop")
    else:
        parser.add_argument("--expected-metadata-receipt-sha256")
    parser.add_argument("--sdk-validation-tooling", type=Path)
    parser.add_argument("--state-artifact-id", type=int)
    parser.add_argument("--state-artifact-sha256")
    parser.add_argument("--state-capture-root", type=Path)
    parser.add_argument("--state-wave", type=int, default=0)
    if not worker and not native_prepare:
        parser.add_argument("--runtime-original-producer", type=Path, default=argparse.SUPPRESS)
        parser.add_argument("--runtime-original-workflow-sha", default=argparse.SUPPRESS)
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    add_metadata_admission_arguments(parser)
    arguments = vars(parser.parse_args(argv))
    try:
        with metadata_admission_options(arguments) as admissions:
            if ("runtime_original_producer" in arguments) != ("runtime_original_workflow_sha" in arguments):
                raise ValueError("Retained Runtime producer and original workflow pin must be paired")
            if "runtime_original_producer" in arguments:
                arguments["runtime_original_producer"] = product_reuse._canonical_control(
                    arguments["runtime_original_producer"], "Original retained Runtime producer")
            plan, discovery, state, destination = (arguments.pop(name) for name in ("plan", "discovery_root", "state_root", "destination"))
            state_locator = [arguments.pop(name) for name in ("state_artifact_id", "state_artifact_sha256", "state_capture_root")]
            state_wave = arguments.pop("state_wave")
            if any(value is not None for value in state_locator):
                if worker or any(value is None for value in state_locator) or arguments["trusted_workflow_sha"] is None:
                    raise ValueError("SDK input staging requires the complete caller-owned Runtime state locator")
                identifier, digest, capture_root = state_locator
                expected_discovery = capture_root / "original/product-resume-state"
                expected_state = capture_root / ("original/runtime-state" if state_wave else "original/product-resume-state")
                if discovery != expected_discovery or state != expected_state:
                    raise ValueError("SDK input staging paths differ from the caller-selected Runtime capture")
                product_reuse.capture_runtime_resume_upload(plan, capture_root,
                    artifact_id=identifier, artifact_sha256=digest, state_wave=state_wave,
                    trusted_workflow_sha=arguments["trusted_workflow_sha"], repository_root=arguments["repository_root"],
                    environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""))
            elif state_wave:
                raise ValueError("SDK input staging state wave requires its complete capture locator")
            action = prepare_native if native_prepare else execute_javascript if javascript else stage
            policy = arguments.pop("sdk_validation_tooling")
            if policy is not None:
                arguments["sdk_validation_tooling"] = product_reuse._canonical_control(policy, "Caller SDK tooling policy")
            apple_policy = arguments.pop("sdk_apple_validation_policy")
            if apple_policy is not None:
                arguments["sdk_apple_validation_policy"] = product_reuse._canonical_control(apple_policy, "Caller Apple validation policy")
            action(plan, discovery, state, destination, **arguments, **admissions,
                environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
