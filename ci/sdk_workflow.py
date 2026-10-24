"""Compose SDK handoff routes from the existing authenticated product replay."""

from __future__ import annotations

import argparse
import json
from contextlib import contextmanager, ExitStack
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
from sdk_phase import NATIVE_RUNTIME_PREDECESSORS
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options
from runtime_reference_transport import count, measured

from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    regular_file_inventory, sha256_bytes, snapshot_regular_tree, publish_regular_tree,
    verified_zip_contents,
    _stat_identity,
)
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PHASE_INSTANCE_IDS, PhaseInstanceId
from products.restore import verification_scoped, verification_session, memoized_file_inventory
from products.sdk_apple_original_inputs import verified_apple_original_inputs
from products.sdk_inputs import REQUEST_NAME
from reuse import github_output
from products.contract_model import _execution_tree_digest
from products.signing_isolation import require_no_signing_secret
from products.sdk_validation import decode_sdk_validation_records
from products.sdk_validation_inputs import collection_admission_scope
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
    def loader = sdk.tasks.named('verifyCppBindingParity').get().class.classLoader
    def modelClass = { name -> loader.loadClass(name) }
    def m11 = modelClass('CrossLanguageBindingPhase').enumConstants.find { it.name() == 'M11' }
    def nativeModels = [:]
    def freshSeparateFile = { destination, sources ->
        def path = destination.canonicalFile.toPath()
        if (java.nio.file.Files.exists(destination.toPath(), java.nio.file.LinkOption.NOFOLLOW_LINKS) ||
            sources.any { source ->
                def originalPath = file(source).canonicalFile.toPath()
                path == originalPath || path.startsWith(originalPath) || originalPath.startsWith(path)
            })
            throw new GradleException('Parity output must be fresh and separate from original inputs')
    }
    // These are newly derived aggregate receipts, never original phase receipts.
    // All original host fields survive; schema6 removes only single-run assumptions.
    def nativeDocument = { r ->
        [schema:6, result:'passed', phase:r.phase.name(), language:r.language.id,
         canonical:[apiReportSha256:r.canonical.apiReportSha256,
                    coverageReceiptSha256:r.canonical.coverageReceiptSha256],
         artifacts:r.artifacts.sort(false) { it.id }.collect { [id:it.id, sha256:it.sha256] },
         hostConsumerProofs:r.hostConsumerProofs.sort(false) { it.classifier }.collect { proof ->
             def row = ['classifier', 'runnerOs', 'runnerArch', 'toolchainIdentitySha256',
                 'packageArtifactId', 'packageSha256', 'nativeLibrarySha256', 'testId',
                 'candidateCommit', 'candidateTree'].collectEntries { [(it):proof."$it"] }
             row.status = proof.status.name().toLowerCase(java.util.Locale.ROOT)
             row
         },
         testProgramSha256:r.testProgramSha256, testResultsSha256:r.testResultsSha256,
         publicSymbols:r.publicSymbols.sort(false),
         tests:r.bindingTests.sort(false) { it.testId }.collect {
             [id:it.testId, status:it.status.name().toLowerCase(java.util.Locale.ROOT)] },
         scenarios:r.scenarioEvidence.sort(false) { it.scenario.id }.collect {
             [id:it.scenario.id, testIds:it.testIds.sort(false)] },
         claims:r.projectionClaims.sort(false) { it.capabilityKey }.collect {
             [capabilityKey:it.capabilityKey, publicSymbols:it.publicSymbols.sort(false),
              executedTests:it.executedTests.sort(false),
              sharedScenarios:it.sharedScenarios.collect { it.id }.sort(false)] },
         exclusions:r.applicabilityExclusions.sort(false) { it.capabilityKey }.collect {
             [capabilityKey:it.capabilityKey, reason:it.reason] }]
    }
    def canonicalBytes = { value ->
        // Use the one repository canonical writer; this caller has no second codec.
        def process = new ProcessBuilder('python3', '-B', '-c',
            'import json,sys; from ci.products.inventory import canonical_json_bytes; ' +
            'sys.stdout.buffer.write(canonical_json_bytes(json.load(sys.stdin)))')
            .directory(rootProject.projectDir).start()
        process.outputStream.withWriter('UTF-8') { it.write(groovy.json.JsonOutput.toJson(value)) }
        def bytes = process.inputStream.bytes
        def error = process.errorStream.getText('UTF-8')
        if (process.waitFor() != 0) throw new GradleException('Parity canonical writer failed: ' + error)
        bytes
    }
    def writeCanonical = { destination, value ->
        def bytes = canonicalBytes(value)
        destination.parentFile.mkdirs()
        destination.bytes = bytes
        bytes
    }
    ['python':'Python', 'csharp':'CSharp', 'rust':'Rust', 'cpp':'Cpp', 'dart':'Dart'].each { language, title ->
        def original = config.native[language]
        freshSeparateFile(file(original.output), [config.api, config.coverage, original.bootstrap,
            original.claims, original.capability, original.packageStage, original.packageReceipt,
            original.request, original.runtime, original.validationStages, original.validationReceipts, original.sdks])
        sdk.tasks.named("verify${title}BindingParity").configure {
            setDependsOn([])
            phase.set('M11')
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
            actions.clear()
            doLast {
                def evidence = modelClass('CrossLanguageNativeWrapperBindingEvidenceKt')
                def binding = modelClass('CrossLanguageBinding').enumConstants.find { it.id == language }
                def packages = evidence.nativeWrapperPackageArtifacts(binding, packageArtifacts.get().asFile)
                def imported = modelClass('ImportedNativeWrapperParityHosts').newInstance(
                    rootProject.projectDir, importedPackageStage.get().asFile,
                    importedPackageReceipt.get().asFile, importedCompatibilityRequest.get().asFile,
                    importedRuntimeStages.get().asFile, importedValidationStages.get().asFile,
                    importedValidationReceipts.get().asFile)
                def input = modelClass('CrossLanguageNativeWrapperEvidenceInput').newInstance(
                    m11, binding, apiReport.get().asFile, canonicalCoverageReceipt.get().asFile,
                    getCAbiBootstrapEvidence().get().asFile, claims.get().asFile,
                    compilerEvidence.get().asFile, testProgram.get().asFile, testResults.get().asFile,
                    packages, hostEvidenceDirectory.get().asFile, stagedCAbiSdks.get().asFile, imported)
                // Unchanged full five-host installed-package and capability gates.
                def derived = evidence.deriveCrossLanguageNativeWrapperBindingReceipt(input)
                def document = nativeDocument(derived)
                if (document.hostConsumerProofs.size() != 5 ||
                    document.hostConsumerProofs.collect { it.classifier }.toSet().size() != 5 ||
                    document.artifacts.collect { it.id }.toSet().size() != document.artifacts.size()) {
                    throw new GradleException('Derived native parity has duplicate or missing identities')
                }
                nativeModels[binding] = derived
                writeCanonical(receipt.get().asFile, document)
            }
        }
    }
    rootProject.tasks.register('verifyImportedCAbiBindingParity') {
        def original = config.native.cpp
        def directory = file(config.cabiOutput)
        // Reject prior contents before Gradle's stale-output cleanup can touch them.
        if (java.nio.file.Files.exists(directory.toPath(), java.nio.file.LinkOption.NOFOLLOW_LINKS)) {
            throw new GradleException('C ABI parity output must be fresh')
        }
        def outputPath = directory.canonicalFile.toPath()
        if ([original.packageStage, original.packageReceipt, original.request, original.runtime,
             original.sdks, original.bootstrap, rootProject.file('ci').path].any { value ->
                def source = file(value).canonicalFile.toPath()
                outputPath.startsWith(source) || source.startsWith(outputPath)
            }) {
            throw new GradleException('C ABI parity output overlaps an original input')
        }
        outputs.dir(directory)
        outputs.upToDateWhen { false }
        doFirst {
            // Gradle creates output directories before task actions.
            // This caller owns a new private tree; remove only an empty real directory.
            def output = directory.toPath()
            def noFollow = java.nio.file.LinkOption.NOFOLLOW_LINKS
            if (java.nio.file.Files.exists(output, noFollow)) {
                if (!java.nio.file.Files.isDirectory(output, noFollow)) {
                    throw new GradleException('C ABI parity output is not a regular directory')
                }
                java.nio.file.Files.delete(output)
            }
        }
        doLast {
            java.nio.file.Files.createDirectory(directory.toPath())
            // The enclosing Python transaction has already fully authenticated these
            // originals. Reuse its bootstrap and the existing frozen receipt builders;
            // no second package snapshot, semantic verification or serializer.
            def evidence = loader.loadClass('CrossLanguageCAbiBindingEvidenceKt')
            def client = loader.loadClass('CrossLanguageCAbiClientKt')
            def identity = loader.loadClass('CrossLanguageBindingArtifactIdentity')
            def input = loader.loadClass('CrossLanguageCAbiBindingEvidenceInput')
            def io = loader.loadClass('ReleaseIoKt')
            def bootstrap = file(original.bootstrap)
            def scenarioFile = new File(directory, 'c-abi-scenarios.json')
            def count = evidence.C_ABI_BINDING_CAPABILITY_COUNT
            def symbols = evidence.getC_ABI_BINDING_PUBLIC_SYMBOL_COUNT()
            def digest = evidence.C_ABI_BINDING_CAPABILITY_SHA256
            def scenario = evidence.writeCrossLanguageCAbiScenarioProof(scenarioFile, bootstrap,
                evidence.productionCrossLanguageCAbiScenarioMappings(), count, symbols, digest)
            def artifact = { name, path ->
                identity.newInstance(name, io.releaseDigest(path, 'SHA-256'))
            }
            def artifacts = [artifact('c-abi-bootstrap', bootstrap),
                artifact(evidence.C_ABI_SCENARIO_PROOF_ARTIFACT_ID, scenarioFile)]
            client.getCrossLanguageCAbiTargetSpecs().sort().each { target, spec ->
                def component = spec.classifier.substring('c-abi-'.length())
                def proof = new File(original.runtime, component + '/validation/outputs/c-abi/' +
                    client.crossLanguageCAbiPackageEvidenceFileName(target))
                artifacts.add(artifact(client.getCrossLanguageCAbiPackageProofIds().get(target), proof))
            }
            evidence.writeCrossLanguageCAbiBindingReceipt(new File(directory, 'c-abi-parity.json'),
                input.newInstance(bootstrap, scenario.mappings, artifacts,
                    scenario.testProgramSha256, scenario.testResultsSha256, count, symbols, digest))
        }
    }
    rootProject.tasks.named('verifyImportedSdkBindingParity').configure {
        def inputs = [config.api, config.coverage] + config.nonNative.values() +
            config.native.values().collectMany { original ->
                [original.packageStage, original.packageReceipt, original.validationStages,
                 original.validationReceipts, original.bootstrap, original.claims, original.capability]
            }
        freshSeparateFile(file(config.finalOutput), inputs + [config.finalEvidence])
        freshSeparateFile(file(config.finalEvidence), inputs)
        setDependsOn(['verifyImportedCAbiBindingParity'] +
            ['Python', 'CSharp', 'Rust', 'Cpp', 'Dart'].collect { ':codex-agent-sdk:verify' + it + 'BindingParity' })
        canonicalApiReport.set(file(config.api))
        canonicalCoverageReceipt.set(file(config.coverage))
        // This adapter consumes originals, then emits the new aggregate directory.
        // Do not declare that not-yet-created output as a required Gradle input.
        evidenceDirectory.set(file(config.api).parentFile)
        resultFile.set(file(config.finalOutput))
        outputs.upToDateWhen { false }
        actions.clear()
        doLast {
            def receiptIo = modelClass('CrossLanguageBindingReceiptKt')
            def canonical = modelClass('CrossLanguageApiEvidenceKt')
                .readCrossLanguageCanonicalApiEvidence(file(config.api), file(config.coverage))
            def originals = new LinkedHashMap(nativeModels)
            ['kotlin', 'java', 'javascript-typescript', 'swift', 'objective-c', 'c-abi'].each { name ->
                def source = name == 'c-abi' ? new File(config.cabiOutput, 'c-abi-parity.json') :
                    file(config.nonNative[name])
                def r = receiptIo.readCrossLanguageBindingReceipt(source)
                // Advance derived phase only. Every original file stays untouched.
                originals[r.language] = r.copy(m11, r.language, r.canonical, r.artifacts,
                    r.testProgramSha256, r.testResultsSha256, r.publicSymbols, r.bindingTests,
                    r.scenarioEvidence, r.projectionClaims, r.applicabilityExclusions, r.hostConsumerProofs)
            }
            def languages = modelClass('CrossLanguageBinding').enumConstants.toList()
            if (originals.keySet() != languages.toSet()) throw new GradleException('Parity lacks exactly eleven languages')
            originals.each { language, r ->
                if (r.language != language || r.phase != m11 || r.canonical != canonical.canonical)
                    throw new GradleException('Parity receipt identity does not match current Contract')
            }
            def kotlin = originals.find { key, value -> key.id == 'kotlin' }.value
            if (kotlin.testProgramSha256 != canonical.compiledTestsSha256 ||
                kotlin.testResultsSha256 != canonical.testResultsSha256 ||
                kotlin.publicSymbols.sort(false) != canonical.memberKeys.sort(false))
                throw new GradleException('Canonical Kotlin proof differs from executed Contract evidence')
            def receipts = originals.values().toList()
            def input = modelClass('CrossLanguageBindingParityInput').newInstance(
                m11, canonical.memberKeys, canonical.memberKeys,
                receipts.collectMany { it.projectionClaims }, receipts.collectMany { it.applicabilityExclusions },
                originals.collectEntries { key, value -> [(key):value.publicSymbols] },
                receipts.collectMany { it.bindingTests }, receipts.collectMany { it.scenarioEvidence })
            def evaluated = modelClass('CrossLanguageBindingParityKt').verifyCrossLanguageBindingParity(input)
            def counts = evaluated.obligations.countBy { it.status.name() }
            if (canonical.memberKeys.size() != 556 || evaluated.obligations.size() != 6116 ||
                counts != [SATISFIED:6104, EXCLUDED:12])
                throw new GradleException('Parity obligation matrix is not complete')
            def output = file(config.finalEvidence)
            output.mkdirs()
            def expected = [:]
            originals.each { language, r ->
                def path = new File(output, language.id + '-parity.json')
                if (nativeModels.containsKey(language)) {
                    expected[path.name] = writeCanonical(path, nativeDocument(r))
                } else {
                    receiptIo.writeCrossLanguageBindingReceipt(path, r)
                    expected[path.name] = path.bytes
                }
            }
            ['canonical-api.json':config.api, 'canonical-coverage.json':config.coverage].each { name, source ->
                expected[name] = file(source).bytes
                new File(output, name).bytes = expected[name]
            }
            def digest = { bytes -> java.security.MessageDigest.getInstance('SHA-256')
                .digest(bytes).encodeHex().toString() }
            def exclusions = receipts.collectMany { it.applicabilityExclusions }
            def audit = [schema:4, result:'complete', phase:'M11',
                apiReportSha256:canonical.canonical.apiReportSha256,
                canonicalCoverageSha256:canonical.canonical.coverageReceiptSha256,
                languageReceiptSha256:originals.collectEntries { language, r ->
                    [(language.id):digest(expected[language.id + '-parity.json'])] },
                summary:[total:6116, active:6104, pending:0, excluded:12, satisfied:6104, missing:0],
                obligations:evaluated.obligations.collect { row ->
                    def record = [capabilityKey:row.capabilityKey, language:row.language.id,
                        applicable:row.applicable, obligationState:row.applicable ? 'active' : 'excluded',
                        parityStatus:row.status.name().toLowerCase(java.util.Locale.ROOT)]
                    def exclusion = exclusions.find { it.capabilityKey == row.capabilityKey && it.language == row.language }
                    if (exclusion != null) record.exclusionReason = exclusion.reason
                    record
                }, errors:[]]
            def auditName = 'binding-obligations-m11.json'
            expected[auditName] = writeCanonical(new File(output, auditName), audit)
            if (output.list().toList().toSet() != expected.keySet() ||
                expected.any { name, bytes -> !java.util.Arrays.equals(new File(output, name).bytes, bytes) })
                throw new GradleException('Derived parity evidence changed before verification')
            writeCanonical(file(config.finalOutput), [schemaVersion:2, result:'passed', phase:'M11',
                capabilityCount:556, languageCount:11, scenarioCount:14,
                canonicalApiSha256:audit.apiReportSha256, canonicalCoverageSha256:audit.canonicalCoverageSha256,
                active:6104, pending:0, excluded:12, satisfied:6104, missing:0,
                evidenceFiles:expected.sort().collect { name, bytes -> [path:name, bytes:bytes.length, sha256:digest(bytes)] }])
        }
    }
}
"""


@contextmanager
def verified_java_parity_inputs(plan, discovery, state, *, repository_root, environ,
                                sdk_validation_tooling=None, sdk_original_workflow_sha=None,
                                sdk_apple_validation_policy=None,
                                sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None, completed_frozen=None):
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
            sdk_android_metadata_admission=sdk_android_metadata_admission),
                **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}))
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
                           sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None, completed_frozen=None):
    # Keep private recovered categories alive through consumption and exit checks.
    with verification_session(), _verified_parity_inputs(plan, discovery, state,
            repository_root=repository_root, environ=environ,
            sdk_validation_tooling=sdk_validation_tooling,
            sdk_original_workflow_sha=sdk_original_workflow_sha,
            sdk_apple_validation_policy=sdk_apple_validation_policy,
            sdk_facade_metadata_admission=sdk_facade_metadata_admission,
            sdk_android_metadata_admission=sdk_android_metadata_admission,
            completed_frozen=completed_frozen) as inputs:
        yield inputs


def _completed_apple_parity_files(verified, destination, *, token):
    """Recover genuine raw receipts, after native admission and fresh observation."""
    from reuse_qualification import CompletedFrozenReuse
    from sdk_apple_upload_locator import (
        RETAINED_PARITY_SOURCE, RETAINED_PARITY_ARCHIVE_BYTES, RETAINED_PARITY_REPORTS,
    )
    from runtime_reference_archive import (
        open_reference_archive, open_stored_reference_archive, copy_reference_member,
    )
    from runtime_reference_transport import count
    completed = verified.completed_frozen
    if type(completed) is not CompletedFrozenReuse:
        raise ValueError("Compact Apple parity requires concrete native completion")
    completed.check_request(verified.rebased_request)
    completed.check_consumer(verified.consumer)
    identity = PhaseInstanceId("sdk", "sdk-ios", "validation", "ios-arm64")
    row = verified.prior_by_instance[identity]
    envelope = completed.envelope(row)
    if envelope is None:
        raise ValueError("Compact Apple parity lacks its exact qualified original")
    if any(row[field] != RETAINED_PARITY_SOURCE[field] for field in ("buildKey", "receiptSha256")):
        raise ValueError("Compact Apple parity differs from its reviewed original")
    _, artifact, observed = completed.observe_extended_sdk(row, producer=verified.producer, token=token)
    if ((artifact["id"], artifact["digest"]) != (RETAINED_PARITY_SOURCE["artifactId"], RETAINED_PARITY_SOURCE["artifactSha256"])
            or not any(job["id"] == RETAINED_PARITY_SOURCE["jobId"]
                       for observation in observed for job in observation["jobs"])):
        raise ValueError("Compact Apple parity changes its independently qualified upload")
    files = {}
    with open_reference_archive(artifact, token) as (archive, stream), \
            open_stored_reference_archive(archive, "execution/apple-validation-evidence.zip",
                expected_bytes=RETAINED_PARITY_ARCHIVE_BYTES) as reports:
        for record in RETAINED_PARITY_REPORTS:
            name = Path(record["relativePath"]).name
            destination_file = destination / name
            copy_reference_member(reports, record["relativePath"], destination_file, record)
            files[name] = destination_file
        if stream is not None:
            count("appleParityOriginalRangeBytes", stream.transferred)
    if completed.envelope(row) != envelope:
        raise ValueError("Compact Apple parity authority changed during recovery")
    return files


@contextmanager
def _verified_parity_inputs(plan, discovery, state, *, repository_root, environ,
                           sdk_validation_tooling, sdk_original_workflow_sha,
                           sdk_apple_validation_policy, sdk_facade_metadata_admission,
                           sdk_android_metadata_admission, completed_frozen):
    """Borrow completed immutable evidence after one full authenticated replay."""
    root = Path(repository_root).resolve(strict=True)
    plan_bytes = read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    verified = product_reuse._verified_product_state(plan, discovery, state, root, environ,
        sdk_validation_tooling, sdk_original_workflow_sha=sdk_original_workflow_sha,
        **_caller_policies(None, sdk_apple_validation_policy,
            sdk_facade_metadata_admission=sdk_facade_metadata_admission,
            sdk_android_metadata_admission=sdk_android_metadata_admission),
                **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}))
    phases = {product_reuse._identity(row): row for row in verified.prior["phases"]}
    required = {identity for identity in PHASE_INSTANCE_IDS if identity.product == "sdk"}
    if any(identity not in verified.sources or phases.get(identity, {}).get("state") not in {"retained", "reused"}
           for identity in required):
        raise ValueError("Full parity requires every selected SDK phase completed and authenticated")
    records = {"sdkValidationEvidence": list(verified.rebased_request.get("sdkValidationEvidence", []))}
    product_reuse._merge_native_comparison_records(records,
        product_reuse._retained_sdk_handoffs(Path(state), root), key="sdkValidationEvidence")
    native = decode_sdk_validation_records(root, records["sdkValidationEvidence"])
    recovery = None
    if any(phases[PhaseInstanceId("sdk", language, "validation", target)]["receiptSha256"] not in native
           for language in NATIVE_BINDINGS for target in NATIVE_TARGETS):
        from sdk_native_metadata_workflow import completed_validation_recovery
        recovery = completed_validation_recovery(verified.completed_frozen,
            {**verified.rebased_request, **records}, sdk_validation_tooling,
            product_reuse._apple_package_origin(plan, root, sdk_original_workflow_sha, environ))
        if recovery is None:
            raise ValueError("Parity lacks authenticated native recovery authority")
        from products.plan import sdk_validation_dependencies
        for language in NATIVE_BINDINGS:
            instance = PhaseInstanceId("sdk", language, "metadata", "desktop")
            identities = sdk_validation_dependencies(instance)
            if all(phases[identity]["receiptSha256"] in native for identity in identities):
                continue
            package = PhaseInstanceId("sdk", language, "package", "desktop")
            def envelope(identity):
                row = phases[identity]
                qualified = verified.completed_frozen.envelope(row)
                if qualified is not None:
                    return qualified
                record = native.get(row["receiptSha256"])
                if record is None:
                    raise ValueError("Parity lacks an authenticated selected native host")
                raw = read_regular_file_bytes(record["validationReceipt"], reject_symlink_parents=True)
                if sha256_bytes(raw) != row["receiptSha256"]:
                    raise ValueError("Parity native receipt differs from its selected original")
                return dict(receipt=product_reuse.validate_phase_receipt(load_canonical_json_bytes(raw)),
                    receiptBytes=raw, receiptSha256=row["receiptSha256"], objectSha256=row["objectSha256"])
            recovered = recovery["records"](instance,
                tuple(envelope(identity) for identity in identities),
                verified.completed_frozen.envelope(phases[package]))
            if recovered is None:
                raise ValueError("Parity lacks complete qualified native originals")
            native.update(recovered[1])
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
            protected.add(Path(record["compatibilityRequest"]).parent)
            protected.update(Path(record[name]) for name in (
                "packageStage", "packageReceipt", "compatibilityRequest", "runtimeStages", "stagedSdks",
                "validationStage", "validationReceipt", "runtimeAuthorization",
                *(("binaryStage", "binaryReceipt") if language == "csharp" else ())))
        selected[language] = hosts
    before = {path: (memoized_file_inventory(path, allow_empty=True) if path.is_dir()
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
        archive, archive_identity = None, None
        if not apple_rows and verified.completed_frozen is not None:
            files.update(_completed_apple_parity_files(verified, private,
                token=environ.get("GITHUB_TOKEN", "")))
        elif len(apple_rows) != 1:
            raise ValueError("Parity lacks the selected authenticated Apple validation original")
        else:
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
                if ((archive is not None and _stat_identity(archive.stat()) != archive_identity) or
                        regular_file_inventory(private) != imported_inventory or
                        any((memoized_file_inventory(path, allow_empty=True) if path.is_dir()
                            else read_regular_file_bytes(path, reject_symlink_parents=True)) != old
                            for path, old in before.items())):
                    raise ValueError("Original parity inputs changed during use")
                if recovery is not None:
                    recovery["check"]()


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


@measured
def _parity_package_receipts(native, directory):
    """Adapt borrowed categories to the existing verifier's sibling layout once.

    Only external authorization, original receipts and the C# binary context are
    copied. Product packages, Runtime bodies and compatibility inputs stay borrowed.
    """
    contexts, receipts = {}, {}
    for language, hosts in native.items():
        inventories = {target: memoized_file_inventory(record["runtimeAuthorization"])
                       for target, record in hosts.items()}
        key = canonical_json_bytes(inventories)
        if key not in contexts:
            context = directory / str(len(contexts))
            for target, record in hosts.items():
                captured = context / "runtime-authorization" / target
                snapshot_regular_tree(record["runtimeAuthorization"], captured)
                if memoized_file_inventory(captured) != inventories[target]:
                    raise ValueError("Parity Runtime authorization changed during capture")
                count("parityContextCopiedBytes", sum(row["bytes"] for row in inventories[target]))
            contexts[key] = context
            count("parityAuthorizationCaptures")
        else:
            count("parityAuthorizationReuses")
        context = contexts[key]
        primary = hosts["linux-x64"]
        if language == "csharp":
            binary = context / "csharp-binary"
            inventory = memoized_file_inventory(primary["binaryStage"])
            snapshot_regular_tree(primary["binaryStage"], binary / "stage")
            if memoized_file_inventory(binary / "stage") != inventory:
                raise ValueError("Parity C# binary changed during capture")
            raw = read_regular_file_bytes(primary["binaryReceipt"], reject_symlink_parents=True)
            (binary / "phase-receipt.json").write_bytes(raw)
            count("parityContextCopiedBytes", sum(row["bytes"] for row in inventory) + len(raw))
        receipt = context / (language + ".json")
        raw = read_regular_file_bytes(primary["packageReceipt"], reject_symlink_parents=True)
        receipt.write_bytes(raw)
        count("parityContextCopiedBytes", len(raw))
        receipts[language] = receipt
    return receipts


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
                    policy_revision=revision), (result / "consumer.log").open("w+b") as log:
            def run(command):
                start = log.tell()
                try:
                    subprocess.run(command, cwd=root, env=dict(environ), check=True,
                        stdout=log, stderr=subprocess.STDOUT)
                except subprocess.CalledProcessError:
                    log.flush()
                    log.seek(max(start, log.tell() - 65536))
                    print("Parity consumer diagnostics (last 64 KiB):\n" +
                          log.read().decode("utf-8", errors="replace"), file=sys.stderr)
                    raise

            def copy(source, target):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(read_regular_file_bytes(source, reject_symlink_parents=True))

            files = inputs["files"]
            contexts = private / "package-contexts"
            package_receipts = _parity_package_receipts(inputs["native"], contexts)
            context_inventory = memoized_file_inventory(contexts)
            config = {"api": str(files["canonical-api.json"]), "coverage": str(files["canonical-coverage.json"]),
                "native": {}, "cabiOutput": str(private / "cabi"),
                "finalEvidence": str(result / "m11"), "finalOutput": str(result / "sdk-parity.json"),
                "nonNative": {
                    name: str(files[name + "-parity.json"])
                    for name in ("kotlin", "javascript-typescript", "swift", "objective-c")
                } | {"java": str(private / "java/java-parity.json")}}
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
                command.extend(("--receipt", str(package_receipts[language])))
                for option, key in (("stage", "packageStage"),
                        ("compatibility-request", "compatibilityRequest"), ("runtime-stages", "runtimeStages"),
                        ("staged-sdks", "stagedSdks"), ("validation-stage", "validationStage"),
                        ("validation-receipt", "validationReceipt")):
                    command.extend(("--" + option, str(primary[key])))
                run(command)
                config["native"][language] = {"packageStage": str(primary["packageStage"]),
                    "packageReceipt": str(package_receipts[language]), "request": str(primary["compatibilityRequest"]),
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
            gradle = [str(root / "gradlew"),
                "--init-script", str(root / ".github/actions/run-ci-lane/release_tooling.init.gradle"),
                "--no-configuration-cache",
                "--no-build-cache", "--max-workers=4", "--console=plain"]
            native_options = ["--init-script", str(native_script),
                "-DcodexAgent.importedNativeParityInputs=" + str(config_path)]
            run(gradle + ["--init-script", str(java_script),
                "-DcodexAgent.importedJavaParityInputs=" + str(inputs["java"]),
                "-DcodexAgent.importedJavaParityOutput=" + str(private / "java/java-parity.json"),
                ":codex-agent-core:verifyJavaBindingParity"])
            run(gradle + native_options + [":verifyImportedSdkBindingParity"])
            if product_reuse.load_json_bytes(read_regular_file_bytes(result / "sdk-parity.json"))["result"] != "passed":
                raise ValueError("Full imported SDK parity did not pass")
            if memoized_file_inventory(contexts) != context_inventory:
                raise ValueError("Parity package context changed during consumption")
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
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None, requested_scope=None,
    completed_frozen=None, _product_state_consumer=None):
    plan_bytes = read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    validated = product_reuse._validate_plan(plan, repository_root)
    inspected = product_reuse.inspect_products(plan, discovery, state,
        repository_root=repository_root, environ=environ, include_sdk_selection=True,
        **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}),
        **({"requested_scope": requested_scope} if requested_scope is not None else {}),
        **({"_verified_state_consumer": _product_state_consumer} if _product_state_consumer is not None else {}),
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


def _routed_selection(plan, repository_root, environ, trusted_workflow_sha, routing_state):
    """A successful current transition may route to the signed Runtime bridge.

    The bridge still authenticates the selected aggregate, Contract digest and
    current Git compatibility policy. This hint never admits a product phase.
    """
    from sdk_native_continuation import select
    validated = product_reuse._validate_plan(plan, repository_root)
    value, locator, plan_id = routing_state
    expected = {**product_reuse._consumer(validated, environ)["producer"],
                "workflowSha": trusted_workflow_sha, "planId": plan_id}
    outputs = select(value, locator, expected, family="runtime")
    selection = json.loads(outputs["sdk_input_selection"])
    if outputs["sdk_handoff_required"] != "true" or not isinstance(selection, dict):
        raise ValueError("Routing has no selected SDK consumers")
    return validated, selection


# Reviewed transport locators only; the ordinary capture below authenticates
# the complete original upload and current Runtime/SDK compatibility afresh.
_RETAINED_SDK_INPUT_RECOVERY = {'historicalSource': {'artifactId': 12020869488,
                      'artifactSha256': 'sha256:6d01390908eccb403a068ef4717d6d3f9a3a68dea07bea7a252877c159d89f27',
                      'producer': {'commit': 'b1f647efebe105abba89bcb31de3a8d25b580406',
                                   'event': 'pull_request',
                                   'pullRequest': 31,
                                   'repository': 'codex-agent-labs/codex-agent',
                                   'runAttempt': 1,
                                   'runId': 38835706077,
                                   'tree': '3fe366739c0dbf3c11f305d77609e9509262093d',
                                   'workflowPath': '.github/workflows/ci.yml'},
                      'workflowSha': 'b0947995481dec088fce8e9490a17a3399e9dc2b'},
 'runtimeSource': {'artifactId': 12433452038,
                   'artifactSha256': 'sha256:a51cad9fe390a6579b6ce40f1245f5020730db5b44c44ff2a2453472982ab225',
                   'buildKey': 'sha256:38f5f548b4fc926e8be981bc5df81569e3422820c37a83b024f2772b46da6a45',
                   'metadataReceiptSha256': 'sha256:eb826c1b4634c5ba010e3fec385f27393310af5252ccb98ab6aaff644dfb3a26',
                   'producer': {'commit': 'c8400811dca2e4f8c23f7c459b1abe6ad78d5348',
                                'event': 'pull_request',
                                'pullRequest': 31,
                                'repository': 'codex-agent-labs/codex-agent',
                                'runAttempt': 1,
                                'runId': 39745656910,
                                'tree': 'e2c1b2686acbd4471f9f5d3ef7a78df3e9a505c7',
                                'workflowPath': '.github/workflows/ci.yml'},
                   'workflowSha': 'd2243aac89368df2776b6617fd5a623bd6754cb2'},
 'compatibleSource': {'artifactId': 12521408629,
                      'artifactSha256': 'sha256:824a00f4f54cbd37103031c8d0ef5a2ff7a82bdd57cf4e748ba2d4be2e2368d6',
                      'producer': {'commit': 'fc5b6c5ad9d4912d27b9c63e5a1627d4a13bef1b',
                                   'event': 'pull_request',
                                   'pullRequest': 31,
                                   'repository': 'codex-agent-labs/codex-agent',
                                   'runAttempt': 1,
                                   'runId': 39995416657,
                                   'tree': 'c04648a952d38c9fc2d67c2cfc4ae1e5d3591e26',
                                   'workflowPath': '.github/workflows/ci.yml'},
                      'workflowSha': '4552e2da1684d5af0b86386bf94e5113326761c5'}}


def retained_sdk_input_source(source, runtime_source):
    """Select the reviewed compatible transport; ordinary capture still grants trust."""
    if (source == _RETAINED_SDK_INPUT_RECOVERY["historicalSource"]
            and runtime_source == _RETAINED_SDK_INPUT_RECOVERY["runtimeSource"]):
        return _RETAINED_SDK_INPUT_RECOVERY["compatibleSource"]
    return source


@measured
def stage(plan, discovery, state, destination, *, keyring, keys_directory,
          repository_root, environ, token, trusted_workflow_sha=None, artifact_id=None,
          artifact_sha256=None, expected_build_key=None, expected_metadata_receipt_sha256=None,
          sdk_validation_tooling=None, sdk_apple_validation_policy=None,
          runtime_original_producer=None, runtime_original_workflow_sha=None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None, routing_state=None,
    retained_sdk_inputs_source=None, reference_sdk_inputs=False, completed_frozen=None):
    """Delegate source selection and both destination policies, never grant trust."""
    if (runtime_original_producer is None) != (runtime_original_workflow_sha is None):
        raise ValueError("Retained Runtime producer and original workflow pin must be paired")
    if reference_sdk_inputs and (retained_sdk_inputs_source is None or runtime_original_producer is None):
        raise ValueError('SDK input routing requires independently selected original SDK and Runtime sources')
    tooling = _caller_policies(sdk_validation_tooling, sdk_apple_validation_policy,
        sdk_facade_metadata_admission=sdk_facade_metadata_admission,
        sdk_android_metadata_admission=sdk_android_metadata_admission)
    if routing_state is None:
        validated, selection, _ = _selection(plan, discovery, state, repository_root, environ,
                                             trusted_workflow_sha=trusted_workflow_sha,
                                            **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}), **tooling)
    else:
        validated, selection = _routed_selection(plan, repository_root, environ, trusted_workflow_sha, routing_state)
    if selection.get("source") == "released-default":
        if retained_sdk_inputs_source is not None:
            raise ValueError("Retained current Runtime SDK inputs cannot replace a released-default selection")
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
    if reference_sdk_inputs:
        runtime_source = dict(artifactId=artifact_id, artifactSha256=artifact_sha256,
            producer=runtime_original_producer, workflowSha=runtime_original_workflow_sha,
            buildKey=expected_build_key, metadataReceiptSha256=expected_metadata_receipt_sha256)
        selected_source = retained_sdk_input_source(retained_sdk_inputs_source, runtime_source)
        if selected_source != retained_sdk_inputs_source:
            # SDK8 keeps its historical member authority. This newer input upload
            # takes the existing full-authentication route, never that shortcut.
            retained_sdk_inputs_source = selected_source
        else:
            return sdk_handoff.stage_sdk_input_binding(plan, destination,
                sdk_inputs_source=retained_sdk_inputs_source, runtime_source=runtime_source,
                repository_root=repository_root, environ=environ)
    capture = (sdk_handoff.capture_sdk_handoff if retained_sdk_inputs_source is None
               else sdk_handoff.capture_reused_sdk_handoff)
    retained_arguments = ({} if retained_sdk_inputs_source is None
                          else {"sdk_inputs_source": retained_sdk_inputs_source})
    return capture(plan, destination,
        artifact_id=artifact_id, artifact_sha256=artifact_sha256,
        trusted_workflow_sha=runtime_original_workflow_sha or trusted_workflow_sha,
        expected_build_key=expected_build_key, expected_metadata_receipt_sha256=expected_metadata_receipt_sha256,
        sdk_version=selection["sdkVersion"], compatible_release_range=selection["compatibleReleaseRange"],
        compatible_runtime_compatibility_range=selection["compatibleRuntimeCompatibilityRange"],
        expected_contract_payload_sha256=selection["contractPayloadSha256"],
        reference_runtime=True,
        keyring=keyring, keys_directory=keys_directory, selection_repository_root=repository_root,
        selection_revision=validated["validationCommit"], repository_root=repository_root, environ=environ, token=token,
        **({"original_producer": runtime_original_producer} if runtime_original_producer is not None else {}),
        **retained_arguments)


@contextmanager
def _completed_sdk_inputs(capture, *, completed_frozen, **policy):
    """Keep signed SDK policy/content gates, joining exact completed Runtime controls."""
    from reuse_qualification import CompletedFrozenReuse
    from products.sdk_inputs_verification import _borrow_private_sdk_inputs, verified_sdk_inputs
    if type(completed_frozen) is not CompletedFrozenReuse:
        raise ValueError("SDK completed input join requires native semantic authority")
    sdk_root = capture / "original/sdk-inputs"
    with _borrow_private_sdk_inputs(sdk_root), verified_sdk_inputs(sdk_root, **policy) as sdk:
        receipts = completed_frozen.sdk_receipts(sdk["arguments"])
        yield {"sdk": sdk, "runtime": {"receiptBytes": receipts}}
        # The dictionaries exposed to a worker never become authority on exit.
        completed_frozen.sdk_receipts(sdk["arguments"])


@contextmanager
def verified_inputs(plan, discovery, state, *, artifact_id, artifact_sha256,
                    trusted_workflow_sha, keyring, keys_directory, repository_root, environ, token,
                    sdk_validation_tooling=None, sdk_apple_validation_policy=None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None, requested_scope=None,
    retained_sdk_inputs_source=None, completed_frozen=None, _product_state_consumer=None):
    """Keep upload, SDK policy and raw Runtime originals verified through consumer use.

    Returned paths expire on exit. Consumers must finish using them inside the
    context and admit their outputs only after its final checks succeed. The
    Runtime carrier's Contract receipts remain its originals, not replacements
    for the current candidate's independently selected Contract predecessors.
    """
    validated, selection, plan_bytes = _selection(plan, discovery, state, repository_root, environ,
                                                sdk_validation_tooling=sdk_validation_tooling,
                                                requested_scope=requested_scope,
                                                **({"_product_state_consumer": _product_state_consumer}
                                                   if _product_state_consumer is not None else {}),
                                                **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}),
                                                trusted_workflow_sha=trusted_workflow_sha,
                                                **_caller_policies(None, sdk_apple_validation_policy,
                                                    sdk_facade_metadata_admission=sdk_facade_metadata_admission,
                                                    sdk_android_metadata_admission=sdk_android_metadata_admission))
    with tempfile.TemporaryDirectory(prefix="sdk-consumer-inputs-") as temporary:
        capture = Path(temporary).resolve() / "capture"
        # A requalified aggregate needs ordinary admission until a new native
        # checkpoint proves it; unchanged predecessor proofs cannot replace it.
        input_completion = completed_frozen
        if (input_completion is not None and PhaseInstanceId(
                "runtime", "runtime-aggregate", "metadata", "aggregate")
                not in input_completion.completed_phases()):
            input_completion = None
        product_reuse.capture_sdk_inputs_upload(plan, capture, artifact_id=artifact_id,
            artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
            expected_source=selection["source"], repository_root=repository_root, environ=environ, token=token,
            **({"completed_frozen": input_completion} if input_completion is not None else {}),
            **({'retained_sdk_inputs_source': retained_sdk_inputs_source} if retained_sdk_inputs_source is not None else {}))
        inventory = memoized_file_inventory(capture, allow_empty=True)

        def unchanged():
            if (memoized_file_inventory(capture, allow_empty=True) != inventory
                    or read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes):
                raise ValueError("SDK consumer original plan or captured upload changed during use")

        verifier = verified_apple_original_inputs if input_completion is None else _completed_sdk_inputs
        options = ({"expected_source": selection["source"]} if input_completion is None else
                   {"completed_frozen": input_completion})
        with verifier(capture, **options,
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
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None, completed_frozen=None):
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
            sdk_android_metadata_admission=sdk_android_metadata_admission),
                **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}))
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
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None, completed_frozen=None):
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
            trusted_workflow_sha=trusted_workflow_sha, repository_root=root, environ=environ, token=token, **tooling,
            **({"completed_frozen": completed_frozen} if completed_frozen is not None else {})) as inputs:
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


def _matrix_from_plans(ready_plans, *, ios_binary=False, family=None):
    """Route a caller-authenticated election; never load a transported matrix."""
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
    rows = [{**{field: ready[field] for field in ("product", "component", "phase", "target", "buildKey")},
             **worker_route(ready)}
            for ready in ready_plans
            if selected(product_reuse._identity(ready))]
    return {"include": rows}


def _write_matrix(ready_plans, github_output_path, *, ios_binary=False, family=None):
    value = _matrix_from_plans(ready_plans, ios_binary=ios_binary, family=family)
    github_output(github_output_path, {"sdk_matrix": canonical_json_bytes(value).decode().strip(),
                                      "sdk_workers_required": bool(value["include"])})
    return value


def _read_scope(ios_binary, family):
    selected = tuple(instance for instance in product_reuse.PHASE_INSTANCE_IDS
        if (product_reuse._sdk_family_worker_instance(instance, family) if family is not None else
            (product_reuse._sdk_ios_binary_worker_instance if ios_binary else
             product_reuse._sdk_javascript_worker_instance)(instance)))
    if family == "native-package":
        selected = tuple(instance for instance in product_reuse.PHASE_INSTANCE_IDS
            if instance.product == "sdk" and instance.component in NATIVE_BINDINGS)
    return selected


def matrix(plan, discovery, state, github_output_path, *, repository_root=None, environ=None, ios_binary=False, family=None,
           trusted_workflow_sha=None,
           sdk_validation_tooling=None, sdk_apple_validation_policy=None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None, completed_frozen=None):
    """Expose only the fixed replay-elected SDK family before platform setup."""
    if type(ios_binary) is not bool:
        raise ValueError("SDK binary projection must be boolean")
    if family is not None:
        product_reuse._sdk_family_worker_instance(None, family)
        if ios_binary:
            raise ValueError("SDK family and binary projection are mutually exclusive")
    selected = _read_scope(ios_binary, family)
    inspected = product_reuse.inspect_products(plan, discovery, state,
        repository_root=repository_root, environ=environ,
        **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}),
        requested_scope=selected,
        **({"sdk_original_workflow_sha": trusted_workflow_sha} if trusted_workflow_sha is not None else {}),
        **_caller_policies(sdk_validation_tooling, sdk_apple_validation_policy,
            sdk_facade_metadata_admission=sdk_facade_metadata_admission,
            sdk_android_metadata_admission=sdk_android_metadata_admission))
    if family == "native-package":
        from sdk_native_continuation import select_preparation_anchor
        anchor = select_preparation_anchor(inspected["readyPlans"])
        github_output(github_output_path, {"native_preparation_" + name.removeprefix("preparation_"): value for name, value in anchor.items()})
    return _write_matrix(inspected["readyPlans"], github_output_path,
                         ios_binary=ios_binary, family=family)


@verification_scoped
@measured
def capture(plan, destination, github_output_path, *, artifact_id, artifact_sha256,
            trusted_workflow_sha, state_wave=0, sdk_state_wave=None,
            repository_root=None, environ=None, token, ios_binary=False, family=None, sdk_validation_tooling=None,
            sdk_apple_validation_policy=None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None, scope_inputs=False,
    completed_frozen=None):
    """Capture exact original state, then replay SDK readiness independently."""
    if type(ios_binary) is not bool:
        raise ValueError("SDK binary projection must be boolean")
    if family is not None:
        product_reuse._sdk_family_worker_instance(None, family)
        if ios_binary:
            raise ValueError("SDK family and binary projection are mutually exclusive")
    if type(scope_inputs) is not bool or scope_inputs and (ios_binary or family not in
            {None, 'javascript-metadata', 'native-package', 'native-validation', 'native-metadata',
             'csharp-binary', 'core-binary', 'android-binary'}):
        raise ValueError('SDK capture scope requires a worker with independent scoped admission')
    product_reuse.capture_runtime_resume_upload(plan, destination, artifact_id=artifact_id,
        artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
        state_wave=state_wave, **({"sdk_state_wave": sdk_state_wave} if sdk_state_wave is not None else {}),
        repository_root=repository_root, environ=environ, token=token, allow_earlier_attempt=True,
        **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}),
        **({'requested_scope': _read_scope(ios_binary, family)} if scope_inputs else {}))
    original = destination / "original"
    paths = {"input_root": original,
        "plan_path": original / "product-resume-inputs/plan/impact-plan.json",
        "discovery_root": original / "product-resume-state",
        "state_root": original / ("runtime-state" if state_wave or sdk_state_wave is not None else "product-resume-state")}
    value = matrix(paths["plan_path"], paths["discovery_root"], paths["state_root"], github_output_path,
                   repository_root=repository_root, environ=environ,
                **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}),
                   trusted_workflow_sha=trusted_workflow_sha, **({"ios_binary": True} if ios_binary else {}),
                   **_caller_policies(sdk_validation_tooling, sdk_apple_validation_policy,
                       sdk_facade_metadata_admission=sdk_facade_metadata_admission,
                       sdk_android_metadata_admission=sdk_android_metadata_admission),
                   **({"family": family} if family is not None else {}))
    github_output(github_output_path, {name: str(path) for name, path in paths.items()})
    return {**paths, "matrix": value}


def capture_transport(plan, destination, github_output_path, *, artifact_id,
        artifact_sha256, trusted_workflow_sha, sdk_state_wave=None, state_wave=0, repository_root,
        environ, token, completed_frozen=None):
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
            environ=environ, token=token, allow_earlier_attempt=True,
            **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}))
        original = destination / "original"
        # Capture binds these exact caller plan bytes to the original upload.
        # Keep its lane inventories: compact native carriers omit those files.
        paths = {"input_root": original,
            "plan_path": plan,
            "discovery_root": original / "product-resume-state",
            "state_root": original / ("runtime-state" if state_wave or sdk_state_wave is not None
                                      else "product-resume-state")}
        for name, path in paths.items():
            if "\n" in str(path) or "\r" in str(path):
                raise ValueError("SDK transport output path contains a line break")
            held_output.write(f"{name}={path}\n")
    return paths


@verification_scoped
@measured
@collection_admission_scope
def collect(input_root, destination, github_output_path, *, wave, trusted_workflow_sha,
            repository_root=None, environ=None, token, ios_binary=False, family=None, sdk_validation_tooling=None,
            sdk_apple_validation_policy=None,
            sdk_worker_workflow_path=None, sdk_worker_job_name=None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None, completed_frozen=None,
    core_metadata_caller=None):
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
    if core_metadata_caller is not None and (family != "core-metadata" or sdk_facade_metadata_admission is not None):
        raise ValueError("Core collection caller requires its exact family and one admission policy")
    scope = ({"sdk_family": family} if family is not None else
             {"sdk_ios_binary_only": True} if ios_binary else {"sdk_javascript_only": True})
    tooling = _caller_policies(sdk_validation_tooling, sdk_apple_validation_policy,
        sdk_facade_metadata_admission=sdk_facade_metadata_admission,
        sdk_android_metadata_admission=sdk_android_metadata_admission)
    if completed_frozen is not None:
        tooling["completed_frozen"] = completed_frozen
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
    evidence = tuple(dict.fromkeys(destination / "collection" / row["sdkValidationEvidenceDirectory"]
                     for row in collection["rows"] if row["result"] == "success")) if family == "native-validation" else ()
    apple_evidence = tuple(destination / "collection" / row["sdkAppleValidationEvidenceDirectory"]
                           for row in collection["rows"] if row["result"] == "success") if family == "ios-validation" else ()
    handoff = destination / "handoff"
    with ExitStack() as held:
        if family == "android-metadata" and shards and sdk_android_metadata_admission is None:
            if len(shards) != 1 or failed:
                raise ValueError("Android metadata collection requires one exact successful original")
            from products.sdk_android_metadata_admission import AndroidMetadataAdmission
            tooling["sdk_android_metadata_admission"] = AndroidMetadataAdmission.from_completed_predecessors(
                completed_frozen=completed_frozen, plan=plan, discovery=discovery, state=state,
                artifact=collection["rows"][0]["artifact"], trusted_workflow_sha=trusted_workflow_sha,
                repository_root=root, environ=os.environ if environ is None else environ, token=token,
                sdk_validation_tooling=sdk_validation_tooling, sdk_apple_validation_policy=sdk_apple_validation_policy)
        if core_metadata_caller is not None and shards:
            if len(shards) != 1 or failed:
                raise ValueError("Core metadata collection requires one exact successful original")
            from sdk_core_metadata_same_campaign import held_collection_admission
            tooling["sdk_facade_metadata_admission"] = held.enter_context(held_collection_admission(
                core_metadata_caller, plan, discovery, state, shards[0], trusted_workflow_sha=trusted_workflow_sha,
                repository_root=root, environ=os.environ if environ is None else environ, token=token,
                sdk_validation_tooling=sdk_validation_tooling, sdk_apple_validation_policy=sdk_apple_validation_policy,
                completed_frozen=completed_frozen))
        advanced = product_reuse.advance_products(plan, discovery, state, shards, handoff / "runtime-state",
            github_output_path, repository_root=root, environ=environ, failed_instances=failed, **scope, **tooling,
            routing_output=True,
            sdk_original_workflow_sha=trusted_workflow_sha,
            **({"sdk_evidence_roots": evidence} if family == "native-validation" else {}),
            **({"sdk_apple_evidence_roots": apple_evidence} if family == "ios-validation" else {}))
    for name in ("product-resume-inputs", "product-resume-state"):
        snapshot_regular_tree(input_root / name, handoff / name, allow_empty=True)
    if failed:
        github_output(github_output_path, {"sdk_matrix": '{"include":[]}', "sdk_workers_required": False})
    else:
        ready = _write_matrix(advanced["matrices"]["sdk"], github_output_path,
                              ios_binary=ios_binary, family=family)
        if wave >= 2 and ready["include"]:
            raise ValueError("SDK workers remain after their final collection wave")
    return advanced


def prepare_native(plan, discovery, state, destination, *, component, expected_build_key,
                   artifact_id, artifact_sha256, trusted_workflow_sha, keyring, keys_directory,
                   repository_root, environ, token, sdk_validation_tooling=None, sdk_apple_validation_policy=None,
                   preparation_phase="package", preparation_target="desktop",
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None, retained_sdk_inputs_source=None, completed_frozen=None):
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
            **({"retained_sdk_inputs_source": retained_sdk_inputs_source} if retained_sdk_inputs_source is not None else {}),
            requested_scope=(instance,),
            trusted_workflow_sha=trusted_workflow_sha, keyring=keyring, keys_directory=keys_directory,
            repository_root=root, environ=environ, token=token, **tooling,
            **({"completed_frozen": completed_frozen} if completed_frozen is not None else {})) as inputs:
        selection = inputs["selection"]
        if fields not in selection["consumers"]:
            raise ValueError("SDK native preparation consumer is not selected")
        prepared = destination / "inputs"
        ready = product_reuse.materialize_product_predecessors(plan, discovery, state, instance, prepared,
            expected_build_key=expected_build_key, repository_root=root, environ=environ,
            materialized_scope=NATIVE_RUNTIME_PREDECESSORS,
            sdk_original_workflow_sha=trusted_workflow_sha, **tooling,
                **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}))
        producer = product_reuse.validate_producer(product_reuse._canonical_control(
            prepared / "producer.json", "Elected native SDK producer"))
        contract = product_reuse.validate_phase_receipt(product_reuse._canonical_control(
            prepared / "contract-contract-metadata-common/phase-receipt.json", "Current Contract metadata"))
        bundles = [row for row in contract["outputs"] if row["kind"] == "contract-bundle"]
        if (tuple(contract[name] for name in ("product", "component", "phase", "target")) !=
                ("contract", "contract", "metadata", "common") or len(bundles) != 1
                or bundles[0]["sha256"] != selection["contractPayloadSha256"]):
            raise ValueError("Elected current Contract differs from verified native SDK inputs")
        before = memoized_file_inventory(prepared, allow_empty=True)

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
        runtime_before = memoized_file_inventory(runtime_stages)

        def unchanged():
            if (memoized_file_inventory(prepared, allow_empty=True) != before
                    or memoized_file_inventory(runtime_stages) != runtime_before):
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
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None, retained_sdk_inputs_source=None, completed_frozen=None):
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
    consumed = [PhaseInstanceId("contract", "contract", item, "common") for item in ("binary", "metadata")]
    consumed.append(PhaseInstanceId("runtime", "node-js", phase,
                                   "node-js" if phase == "package" else "node-js-binding"))
    if phase == "validation":
        consumed.append(PhaseInstanceId("sdk", "javascript", "package", "node"))
    fields = {"product": "sdk", "component": "javascript", "phase": phase, "target": "node"}
    tooling = _caller_policies(sdk_validation_tooling, sdk_apple_validation_policy,
        sdk_facade_metadata_admission=sdk_facade_metadata_admission,
        sdk_android_metadata_admission=sdk_android_metadata_admission)
    with verified_inputs(plan, discovery, state, artifact_id=artifact_id, artifact_sha256=artifact_sha256,
            **({"retained_sdk_inputs_source": retained_sdk_inputs_source} if retained_sdk_inputs_source is not None else {}),
            requested_scope=(instance,),
            trusted_workflow_sha=trusted_workflow_sha, keyring=keyring, keys_directory=keys_directory,
            repository_root=root, environ=environ, token=token, **tooling,
            **({"completed_frozen": completed_frozen} if completed_frozen is not None else {})) as inputs:
        selection = inputs["selection"]
        if fields not in selection["consumers"]:
            raise ValueError("SDK JavaScript worker is not selected")
        prepared = destination / "inputs"
        ready = product_reuse.materialize_product_predecessors(plan, discovery, state, instance, prepared,
            expected_build_key=expected_build_key, repository_root=root, environ=environ,
            materialized_scope=tuple(consumed),
            sdk_original_workflow_sha=trusted_workflow_sha, **tooling,
                **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}))
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


@verification_scoped
@product_reuse._fresh_ci_observations(share_nested=True)
def _workflow_main(argv, *, _continuation=None):
    from reuse_qualification import add_completed_frozen_argument, completed_frozen_options
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
    captured.add_argument("--scope-inputs", action="store_true")
    captured.add_argument("--preparation-destination", type=Path)
    captured.add_argument("--preparation-artifact-id", type=int)
    captured.add_argument("--preparation-artifact-sha256")
    captured.add_argument("--preparation-phase", choices=("package", "validation", "metadata"))
    captured.add_argument("--preparation-state-wave", type=int)
    captured.add_argument("--preparation-sdk-state-wave", type=int)
    parsers["collect"].add_argument("--input-root", type=Path, required=True)
    parsers["collect"].add_argument("--wave", type=int, choices=range(1, 20), required=True)
    parsers["collect"].add_argument("--sdk-worker-workflow-path")
    parsers["collect"].add_argument("--sdk-worker-job-name")
    parsers["collect"].add_argument("--core-metadata-caller", type=Path)
    for name in ("matrix", "capture", "collect"):
        add_completed_frozen_argument(parsers[name])
    arguments = vars(parser.parse_args(argv))
    command = arguments.pop("command")
    try:
        preparation = {name: arguments.pop("preparation_" + name, None) for name in
            ("destination", "artifact_id", "artifact_sha256", "phase", "state_wave", "sdk_state_wave")}
        paired = any(value is not None for value in preparation.values())
        if _continuation is not None and not paired:
            raise ValueError("Native worker continuation requires paired scoped captures")
        output = arguments["github_output_path"]
        if paired:
            if (command != "capture" or arguments.get("family") != "native-validation"
                    or not arguments.get("scope_inputs") or any(preparation[name] is None for name in
                        ("destination", "artifact_id", "artifact_sha256", "phase"))):
                raise ValueError("Paired preparation requires complete scoped native validation capture controls")
            current, previous = (arguments["destination"].resolve(), preparation["destination"].resolve())
            if current == previous or current in previous.parents or previous in current.parents:
                raise ValueError("Paired native capture destinations overlap")
            preparation["family"] = "native-" + preparation.pop("phase")
            preparation["state_wave"] = preparation["state_wave"] or 0
            # Withhold caller outputs until both captures, the optional execution
            # continuation, and policy exit checks pass.
            arguments["github_output_path"] = None
        with metadata_admission_options(arguments) as admissions, completed_frozen_options(arguments) as semantic:
            policy = arguments.pop("sdk_validation_tooling")
            if policy is not None:
                arguments["sdk_validation_tooling"] = product_reuse._canonical_control(policy, "Caller SDK tooling policy")
            apple_policy = arguments.pop("sdk_apple_validation_policy")
            if apple_policy is not None:
                arguments["sdk_apple_validation_policy"] = product_reuse._canonical_control(apple_policy, "Caller Apple validation policy")
            result = {"matrix": matrix, "capture": capture, "collect": collect}[command](**arguments, **admissions, **semantic,
                environ=os.environ, **({"token": os.environ.get("GITHUB_TOKEN", "")} if command != "matrix" else {}))
            if paired:
                prepared = capture(**{**arguments, **preparation, "plan": result["plan_path"]},
                    **admissions, **semantic, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""))
                if _continuation is not None:
                    # The capability never crosses a process or serialized boundary.
                    # Both captures and execution remain inside its lifetime checks.
                    _continuation(result, prepared, semantic)
        if paired:
            github_output(output, {**{name: str(value) for name, value in result.items() if name != "matrix"},
                "sdk_matrix": canonical_json_bytes(result["matrix"]).decode().strip(),
                "sdk_workers_required": bool(result["matrix"]["include"]),
                "preparation_state_root": str(prepared["state_root"]),
                "preparation_sdk_matrix": canonical_json_bytes(prepared["matrix"]).decode().strip()})
        return result
    except (OSError, ValueError) as error:
        parser.error(str(error))


def _capture_transport_main(argv):
    from reuse_qualification import add_completed_frozen_argument, completed_frozen_options
    parser = argparse.ArgumentParser(description="Capture exact official SDK state transport before caller policy selection",
                                     allow_abbrev=False)
    for name in ("plan", "destination", "github-output", "repository-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("trusted-workflow-sha", "artifact-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--state-wave", type=int, choices=range(6), default=0)
    parser.add_argument("--sdk-state-wave", type=int, choices=range(1, 20))
    add_completed_frozen_argument(parser)
    arguments = vars(parser.parse_args(argv))
    arguments["github_output_path"] = arguments.pop("github_output")
    try:
        # The parent directory is runner-owned; O_NOFOLLOW protects the final file.
        runner_output = os.environ.get("GITHUB_OUTPUT")
        if not runner_output or Path(runner_output).absolute() != arguments["github_output_path"].absolute():
            raise ValueError("SDK transport output must be the runner-provided GITHUB_OUTPUT")
        with completed_frozen_options(arguments) as semantic:
            capture_transport(**arguments, **semantic, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


def _ios_binary_main(argv):
    from reuse_qualification import add_completed_frozen_argument, completed_frozen_options
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
    add_completed_frozen_argument(parser)
    arguments = vars(parser.parse_args(argv))
    uploads = {f"ios-{lane}": {
        "artifactId": arguments.pop(lane.replace("-", "_") + "_artifact_id"),
        "artifactSha256": arguments.pop(lane.replace("-", "_") + "_artifact_sha256"),
    } for lane in lanes}
    try:
        with metadata_admission_options(arguments) as admissions, completed_frozen_options(arguments) as semantic:
            plan, discovery, state, destination = (arguments.pop(name) for name in (
                "plan", "discovery_root", "state_root", "destination"))
            policy = arguments.pop("sdk_validation_tooling")
            if policy is not None:
                arguments["sdk_validation_tooling"] = product_reuse._canonical_control(policy, "Caller SDK tooling policy")
            apple_policy = arguments.pop("sdk_apple_validation_policy")
            if apple_policy is not None:
                arguments["sdk_apple_validation_policy"] = product_reuse._canonical_control(apple_policy, "Caller Apple validation policy")
            execute_ios_binary(plan, discovery, state, destination, **arguments, **admissions, **semantic,
                native_uploads=uploads, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


def _parity_main(argv, *, full=False):
    from reuse_qualification import add_completed_frozen_argument, completed_frozen_options
    parser = argparse.ArgumentParser(description="Verify parity against authenticated immutable products", allow_abbrev=False)
    for name in ("plan", "discovery-root", "state-root", "destination", "repository-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("sdk-validation-tooling", "sdk-apple-validation-policy"):
        parser.add_argument("--" + name, type=Path, required=full and name == "sdk-validation-tooling")
    parser.add_argument("--sdk-original-workflow-sha", required=True)
    add_metadata_admission_arguments(parser)
    add_completed_frozen_argument(parser)
    arguments = vars(parser.parse_args(argv))
    try:
        with metadata_admission_options(arguments) as admissions, completed_frozen_options(arguments) as semantic:
            for name in ("sdk_validation_tooling", "sdk_apple_validation_policy"):
                if arguments[name] is not None:
                    arguments[name] = product_reuse._canonical_control(arguments[name], "Caller Java parity " + name)
            plan, discovery, state, destination = (arguments.pop(name) for name in
                ("plan", "discovery_root", "state_root", "destination"))
            execute = execute_parity if full else execute_java_parity
            execute(plan, discovery, state, destination, **arguments, **admissions, **semantic, environ=os.environ)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    return 0


@verification_scoped
def main(argv=None):
    from reuse_qualification import add_completed_frozen_argument, completed_frozen_options
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
    parser.add_argument("--retained-sdk-inputs-source", type=Path, default=argparse.SUPPRESS)
    if not worker and not native_prepare:
        parser.add_argument("--routing-json")
        parser.add_argument("--reference-sdk-inputs", action='store_true', default=argparse.SUPPRESS)
        parser.add_argument("--plan-id")
        parser.add_argument("--runtime-original-producer", type=Path, default=argparse.SUPPRESS)
        parser.add_argument("--runtime-original-workflow-sha", default=argparse.SUPPRESS)
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    add_metadata_admission_arguments(parser)
    add_completed_frozen_argument(parser)
    arguments = vars(parser.parse_args(argv))
    try:
        with metadata_admission_options(arguments) as admissions, completed_frozen_options(arguments) as semantic:
            if ("runtime_original_producer" in arguments) != ("runtime_original_workflow_sha" in arguments):
                raise ValueError("Retained Runtime producer and original workflow pin must be paired")
            if "runtime_original_producer" in arguments:
                arguments["runtime_original_producer"] = product_reuse._canonical_control(
                    arguments["runtime_original_producer"], "Original retained Runtime producer")
            if "retained_sdk_inputs_source" in arguments:
                arguments["retained_sdk_inputs_source"] = product_reuse._canonical_control(
                    arguments["retained_sdk_inputs_source"], "Original retained SDK input source")
            plan, discovery, state, destination = (arguments.pop(name) for name in ("plan", "discovery_root", "state_root", "destination"))
            state_locator = [arguments.pop(name) for name in ("state_artifact_id", "state_artifact_sha256", "state_capture_root")]
            state_wave = arguments.pop("state_wave")
            routing_json = arguments.pop("routing_json", None)
            plan_id = arguments.pop("plan_id", None)
            if (routing_json is None) != (plan_id is None):
                raise ValueError("SDK routing requires its current plan upload identity")
            if any(value is not None for value in state_locator):
                if worker or any(value is None for value in state_locator) or arguments["trusted_workflow_sha"] is None:
                    raise ValueError("SDK input staging requires the complete caller-owned Runtime state locator")
                identifier, digest, capture_root = state_locator
                expected_discovery = capture_root / "original/product-resume-state"
                expected_state = capture_root / ("original/runtime-state" if state_wave else "original/product-resume-state")
                if discovery != expected_discovery or state != expected_state:
                    raise ValueError("SDK input staging paths differ from the caller-selected Runtime capture")
                routed = None
                if routing_json is not None:
                    if len(routing_json.encode()) > 128 * 1024:
                        raise ValueError("SDK routing control exceeds its bound")
                    routing_state = (json.loads(routing_json), dict(artifact_id=str(identifier),
                        artifact_digest=digest, state_wave=str(state_wave), sdk_state_wave=""), plan_id)
                    _, routed = _routed_selection(plan, arguments["repository_root"], os.environ,
                                                  arguments["trusted_workflow_sha"], routing_state)
                if routed is not None and routed.get("source") == "current-runtime":
                    arguments["routing_state"] = routing_state
                else:
                    product_reuse.capture_runtime_resume_upload(plan, capture_root,
                        artifact_id=identifier, artifact_sha256=digest, state_wave=state_wave,
                        trusted_workflow_sha=arguments["trusted_workflow_sha"], repository_root=arguments["repository_root"],
                        environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""))
            elif routing_json is not None:
                raise ValueError("SDK routing requires its exact state locator")
            elif state_wave:
                raise ValueError("SDK input staging state wave requires its complete capture locator")
            action = prepare_native if native_prepare else execute_javascript if javascript else stage
            policy = arguments.pop("sdk_validation_tooling")
            if policy is not None:
                arguments["sdk_validation_tooling"] = product_reuse._canonical_control(policy, "Caller SDK tooling policy")
            apple_policy = arguments.pop("sdk_apple_validation_policy")
            if apple_policy is not None:
                arguments["sdk_apple_validation_policy"] = product_reuse._canonical_control(apple_policy, "Caller Apple validation policy")
            action(plan, discovery, state, destination, **arguments, **admissions, **semantic,
                environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
