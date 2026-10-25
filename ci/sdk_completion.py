"""Require completion of every selected SDK phase in authenticated replay."""

import argparse
from contextlib import ExitStack
from dataclasses import replace
import os
from pathlib import Path
import subprocess
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options
from reuse_qualification import add_completed_frozen_argument, completed_frozen_options
from products.inventory import (
    canonical_json_bytes, require_array, require_boolean, require_exact_keys,
    require_integer, require_object, require_sha256, require_string, read_regular_file_bytes,
    load_canonical_json_bytes, sha256_bytes, git_inventory, verified_zip_contents,
)
from reuse import github_output
from products.restore import verification_scoped


LOCAL_REPOSITORY_INIT = """\
gradle.projectsEvaluated {
    def root = rootProject
    if (root.findProject(':codex-agent-core') == null) return
    def policy = System.getProperty('codexAgent.completedRepositoryPolicy')
    def python = System.getProperty('codexAgent.repositoryPython')
    if (!policy || !python) throw new GradleException('Repository verification requires explicit caller inputs')
    def report = root.layout.buildDirectory.file('reports/repository/imported-product-evidence.json').get().asFile
    def captured = new ByteArrayOutputStream()
    def authenticated = root.tasks.register('verifyCompletedRepositoryEvidence', org.gradle.api.tasks.Exec) {
        group = 'verification'
        description = 'Authenticates original completed products against current repository inputs.'
        dependsOn root.tasks.named('invalidateImportedRepositoryEvidenceOutput')
        workingDir root.projectDir
        environment 'PYTHONDONTWRITEBYTECODE', '1'
        commandLine python, '-B', '-m', 'ci.sdk_completion', '--repository', '--local',
            '--repository-root', root.projectDir.absolutePath, '--completed-frozen-policy', policy
        standardOutput = captured
        outputs.upToDateWhen { false }
        doLast {
            report.parentFile.mkdirs()
            report.bytes = captured.toByteArray()
        }
    }
    root.tasks.named('verifyRepository').configure {
        dependsOn authenticated
        // The legacy direct-terminal reader cannot read genuine transitive receipts.
        // Its explicit replacement authenticates the complete DAG, not rewritten receipts.
        setOnlyIf('Replaced by authenticated completed-product verification') { false }
    }
}
"""


# Same task-time execution pattern as VerifyImportedRepositoryEvidenceTask; no
# Project/script/stream object is captured in a cached task action.
LOCAL_CACHE_TASK = """\
abstract class VerifyCompletedEvidence extends org.gradle.api.DefaultTask {
    @org.gradle.api.tasks.Internal
    abstract org.gradle.api.file.DirectoryProperty getRepositoryDirectory()
    @org.gradle.api.tasks.Input
    abstract org.gradle.api.provider.ListProperty<String> getArguments()
    @org.gradle.api.tasks.OutputFile
    abstract org.gradle.api.file.RegularFileProperty getResultFile()
    @javax.inject.Inject
    abstract org.gradle.process.ExecOperations getProcesses()

    @org.gradle.api.tasks.TaskAction
    void verify() {
        def report = resultFile.get().asFile
        java.nio.file.Files.deleteIfExists(report.toPath())
        def captured = new ByteArrayOutputStream()
        processes.exec {
            workingDir repositoryDirectory.get().asFile
            environment 'PYTHONDONTWRITEBYTECODE', '1'
            commandLine arguments.get()
            standardOutput = captured
        }.assertNormalExitValue()
        report.parentFile.mkdirs()
        report.bytes = captured.toByteArray()
    }
}
"""


def _runtime_contract_policy(path):
    raw = read_regular_file_bytes(path, max_bytes=8192, reject_symlink_parents=True)
    value = require_exact_keys(load_canonical_json_bytes(raw), {
        "schemaVersion", "contractVersion", "runtimeVersion", "target", "contractPayload",
        "contractMetadataReceipt", "contractAttestation", "contractAttestationSignature", "contractPublicKey",
    }, "Standalone acceptance Contract inputs")
    if require_integer(value["schemaVersion"], "Contract inputs schema", 1) != 1 or value["target"] != "jvm":
        raise ValueError("Standalone acceptance uses JVM configuration and the complete authenticated Runtime closure")
    for name in ("contractVersion", "runtimeVersion"):
        products.require_semver(value[name], name)
    for name in ("contractPayload", "contractMetadataReceipt", "contractAttestation",
                 "contractAttestationSignature", "contractPublicKey"):
        path = Path(require_string(value[name], name))
        if not path.is_absolute() or path.resolve(strict=True) != path or not path.is_file():
            raise ValueError("Standalone Contract inputs require absolute non-symbolic paths")
    return raw, value


def run_local_repository_gradle(repository_root, policy_path, *, parity_policy=None, parity_archive=None,
                               runtime_contract_policy=None, configuration_cache=False):
    """Use the root verification entry point without changing product/toolkit inputs."""
    root = Path(repository_root).resolve(strict=True)
    policy = Path(policy_path).absolute()
    read_regular_file_bytes(policy, max_bytes=4096, reject_symlink_parents=True)
    sdk = parity_policy is not None or parity_archive is not None
    runtime = runtime_contract_policy is not None
    if configuration_cache and not sdk:
        raise ValueError("Configuration-cache lifecycle requires local SDK Gradle acceptance")
    if runtime and sdk:
        raise ValueError("Standalone Runtime acceptance does not consume SDK parity")
    if sdk and (parity_policy is None or parity_archive is None):
        raise ValueError("SDK acceptance requires both original parity policy and archive")
    report = root / ("runtime/build/reports/runtime/completed-runtime-evidence.json" if runtime else
                     "build/reports/sdk/completed-sdk-evidence.json" if sdk else
                     "build/reports/repository/imported-product-evidence.json")
    from products.sdk_package import _require_capability_output_separate
    protected = [policy, *((parity_policy, parity_archive) if sdk else ())]
    if runtime:
        contract_raw, contract = _runtime_contract_policy(runtime_contract_policy)
        protected.extend([runtime_contract_policy, *(Path(value) for name, value in contract.items()
            if name.startswith("contract") and name != "contractVersion")])
    _require_capability_output_separate(report, protected)
    # Reject linked output ancestors before the legacy invalidation task can delete anything.
    for path in (report, *report.parents):
        if path.is_symlink():
            raise ValueError("Repository acceptance output must not traverse symbolic links")
    report.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="repository-gradle-adapter-") as temporary:
        script = Path(temporary) / "repository.init.gradle"
        init = LOCAL_REPOSITORY_INIT
        if configuration_cache:
            init = LOCAL_CACHE_TASK + init.replace(
                "    def captured = new ByteArrayOutputStream()\n", "").replace(
                "org.gradle.api.tasks.Exec", "VerifyCompletedEvidence").replace(
                "workingDir root.projectDir", "repositoryDirectory.set(root.projectDir)").replace(
                "        environment 'PYTHONDONTWRITEBYTECODE', '1'\n", "").replace(
                "commandLine python,", "arguments.set([python,").replace(
                "'--completed-frozen-policy', policy\n", "'--completed-frozen-policy', policy])\n").replace(
                "        standardOutput = captured\n", "").replace(
                "        doLast {\n            report.parentFile.mkdirs()\n"
                "            report.bytes = captured.toByteArray()\n        }", "        resultFile.set(report)")
        extra = []
        if runtime:
            init = init.replace("':codex-agent-core'", "':codex-agent-runtime-desktop'")
            init = init.replace("reports/repository/imported-product-evidence.json",
                                "reports/runtime/completed-runtime-evidence.json")
            init = init.replace("verifyCompletedRepositoryEvidence", "verifyCompletedRuntimeEvidence")
            init = init.replace("dependsOn root.tasks.named('invalidateImportedRepositoryEvidenceOutput')", "")
            init = init.replace("'--repository', '--local',", "'--runtime', '--local',")
            init = init.replace("root.projectDir", "root.projectDir.parentFile")
            init = init.replace("'--completed-frozen-policy', policy",
                "'--completed-frozen-policy', policy,\n"
                "            '--runtime-contract-policy', System.getProperty('codexAgent.runtimeContractPolicy'),\n"
                "            '--runtime-contract-manifest', root.extensions.extraProperties"
                ".get('codexAgent.verifiedContractManifest').absolutePath")
            init = init[:init.index("    root.tasks.named('verifyRepository')")] + """\
    root.tasks.named('verifyRuntime').configure {
        // Settings retain their complete Contract authentication/materialization.
        // Reuse qualified metadata instead of invoking its successful producer.
        setDependsOn([authenticated])
    }
}
"""
            extra = ["--project-dir", str(root / "runtime"),
                     "-DcodexAgent.runtimeContractPolicy=" + str(Path(runtime_contract_policy).absolute()),
                     *("-PcodexAgent." + name + "=" + value for name, value in contract.items()
                       if name != "schemaVersion")]
        if sdk:
            # The qualified core P/V/M closure already includes the publication
            # verifier and all eleven isolated facade consumers. Replace their
            # source-building graph explicitly, not just their task actions.
            init = init.replace("reports/repository/imported-product-evidence.json",
                                "reports/sdk/completed-sdk-evidence.json")
            init = init.replace("verifyCompletedRepositoryEvidence", "verifyCompletedSdkEvidence")
            init = init.replace("dependsOn root.tasks.named('invalidateImportedRepositoryEvidenceOutput')", "")
            init = init.replace("'--repository', '--local',", "'--sdk', '--local',")
            init = init.replace("'--completed-frozen-policy', policy",
                "'--completed-frozen-policy', policy,\n"
                "            '--parity-policy', System.getProperty('codexAgent.parityPolicy'),\n"
                "            '--parity-archive', System.getProperty('codexAgent.parityArchive')")
            init = init[:init.index("    root.tasks.named('verifyRepository')")] + """\
    root.tasks.named('verifySdk').configure {
        setDependsOn([authenticated])
    }
}
"""
            extra = ["-DcodexAgent.parityPolicy=" + str(Path(parity_policy).absolute()),
                     "-DcodexAgent.parityArchive=" + str(Path(parity_archive).absolute())]
        script.write_text(init, encoding="utf-8")
        command = [str(root / "gradlew"), "--offline",
            *(["--configuration-cache", "--configuration-cache-problems=fail"] if configuration_cache
              else ["--no-configuration-cache"]), "--no-build-cache",
            "--max-workers=4", "--console=plain", "--init-script",
            str(root / ".github/actions/run-ci-lane/release_tooling.init.gradle"),
            "--init-script", str(script), "-DcodexAgent.completedRepositoryPolicy=" + str(policy),
            "-DcodexAgent.repositoryPython=" + sys.executable, *extra,
            ":verifyRuntime" if runtime else ":verifySdk" if sdk else ":verifyRepository"]
        # Both cache-lifecycle passes use this one private init path. Each executes
        # fresh authentication; Gradle's actual store/reuse log remains the proof.
        for _ in range(2 if configuration_cache else 1):
            report.unlink(missing_ok=True)
            try:
                subprocess.run(command, cwd=root, stdout=sys.stderr, check=True)
            except BaseException:
                report.unlink(missing_ok=True)
                raise
    if runtime and read_regular_file_bytes(runtime_contract_policy, max_bytes=8192,
                                          reject_symlink_parents=True) != contract_raw:
        raise ValueError("Standalone Contract caller policy changed during verification")
    return load_canonical_json_bytes(read_regular_file_bytes(
        report, max_bytes=1024 * 1024, reject_symlink_parents=True))


def require_sdk_completion(plan_path, discovery_root, state_root=None, *,
                           repository_root=None, environ=None, sdk_validation_tooling=None,
                           sdk_apple_validation_policy=None, sdk_original_workflow_sha=None,
                           sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
                           completed_frozen=None):
    """Check the full replayed SDK closure, not a family matrix or new election.

    Existing inspection authenticates the exact result schema, requested closure,
    original receipts and phase states. Global ``result`` may be build-required
    for unrelated products; SDK completion stays scoped while fullReuse forwards
    the same authenticated replay's global result for the final merge gate.
    No SDK selection is a successful no-op, not evidence of a produced SDK.
    """
    inspected = products.inspect_products(plan_path, discovery_root, state_root,
        repository_root=repository_root, environ=environ,
        **({"sdk_validation_tooling": sdk_validation_tooling} if sdk_validation_tooling is not None else {}),
        **({"sdk_apple_validation_policy": sdk_apple_validation_policy}
           if sdk_apple_validation_policy is not None else {}),
        **({"sdk_original_workflow_sha": sdk_original_workflow_sha}
           if sdk_original_workflow_sha is not None else {}),
        **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}),
        **products._metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
    result = require_exact_keys(require_object(inspected, "SDK completion inspection").get("result"),
                                products._REUSE_RESULT_KEYS, "SDK completion replay result")
    if (require_integer(result["schemaVersion"], "SDK completion result schema", 1) != 1
            or require_string(result["result"], "SDK completion result status") not in {"complete", "build-required"}
            or require_boolean(result["fullReuse"], "SDK completion full reuse") != (result["result"] == "complete")):
        raise ValueError("Invalid SDK completion replay status")
    unresolved, seen, count = [], set(), 0
    for value in require_array(result["phases"], "SDK completion phases"):
        phase = require_exact_keys(value, products._REUSE_PHASE_KEYS, "SDK completion phase")
        for field in (*products._IDENTITY_KEYS, "state"):
            require_string(phase[field], "SDK completion phase " + field)
        identity = products._identity(phase)
        if identity in seen or phase["state"] not in {"retained", "reused", "build", "waiting"}:
            raise ValueError("Duplicate or unsupported SDK completion phase")
        seen.add(identity)
        if identity.product != "sdk":
            continue
        count += 1
        if phase["state"] not in {"retained", "reused"}:
            unresolved.append(f"{identity.component}/{identity.phase}/{identity.target}: {phase['state']}")
        else:
            for field in ("buildKey", "receiptSha256", "objectSha256"):
                require_sha256(phase[field], "Completed SDK phase " + field)
    if unresolved:
        raise ValueError("Selected SDK phases remain unresolved: " + ", ".join(unresolved))
    return {"complete": True, "phaseCount": count, "fullReuse": result["fullReuse"]}


def require_repository_completion(plan_path, discovery_root, state_root=None, **options):
    """Report the full authenticated phase DAG, not invented terminal-receipt edges.

    Inspection owns original object/receipt/provenance, semantic projections and
    current-key verification. This report is external evidence, never reuse authority.
    """
    inspected = products.inspect_products(plan_path, discovery_root, state_root, **options)
    return _repository_report(inspected["result"])


def _repository_report(result, *, runtime_only=False):
    from products.aggregate import REPOSITORY_EDGES, REPOSITORY_EVIDENCE_IDENTITIES

    owners = ("contract", "runtime") if runtime_only else ("contract", "runtime", "sdk")
    _, selected, records = products._validate_reuse_result(result, tuple(sorted(
        item for item in products.PHASE_INSTANCE_IDS if item.product in owners)), require_complete=True)
    phases = {products._identity(row): row for row in records}
    terminals = {name: products.PhaseInstanceId(name, *identity)
                 for name, identity in REPOSITORY_EVIDENCE_IDENTITIES.items()}
    edges = []
    for producer, consumer in REPOSITORY_EDGES:
        if producer not in owners or consumer not in owners:
            continue
        if terminals[producer] not in products._dependency_closure((terminals[consumer],)):
            raise ValueError("Repository terminal phases lack their required dependency path")
        edges.append({
            "producerProduct": producer, "consumerProduct": consumer,
            "producerReceiptSha256": phases[terminals[producer]]["receiptSha256"],
            "consumerReceiptSha256": phases[terminals[consumer]]["receiptSha256"],
        })
    return {"schemaVersion": 1, "result": "passed", "phaseCount": len(selected),
            "products": [phases[terminals[name]] for name in owners],
            "edges": edges, "originalPhases": records}


@products.measured
def _completed_parity(root, revision, result, policy_path, archive, token):
    """Consume original hosted parity, never a serialized success-marker authority.

    Called only after current-key replay inside the live native capability scope.
    The successful original verifier supplies semantics; current content and
    unchanged verifier inputs establish applicability without re-running it.
    """
    from products.tooling import _COMPILER_INPUTS
    policy_path = Path(policy_path).absolute()
    raw = read_regular_file_bytes(policy_path, max_bytes=4096, reject_symlink_parents=True)
    policy = require_exact_keys(load_canonical_json_bytes(raw), {
        "schemaVersion", "kind", "producer", "workflowSha", "jobId", "artifactId", "artifactSha256",
    }, "Original SDK parity policy")
    if (require_integer(policy["schemaVersion"], "Parity policy schema", 1) != 1
            or policy["kind"] != "completed-sdk-parity"):
        raise ValueError("Unsupported original SDK parity policy")
    producer = products.validate_producer(policy["producer"], "Original SDK parity producer")
    if producer["event"] != "pull_request" or producer["pullRequest"] != 31:
        raise ValueError("Original SDK parity requires its authorized PR scope")
    job_name = "product-validation / sdk-parity / sdk-parity"
    observation, = products._observe_ci_producer_jobs(
        {"parity": producer}, jobs_by_phase={"parity": job_name}, token=token,
        trusted_workflows_by_phase={"parity": {
            "path": ".github/workflows/sdk-binding-parity.yml", "sha": policy["workflowSha"]}})
    job, = products._matching_ci_jobs(observation["jobs"], job_name)
    if job["id"] != require_integer(policy["jobId"], "Original parity job ID", 1):
        raise ValueError("Original SDK parity job differs from caller policy")
    artifact = products._contract_ci_upload_metadata(
        policy["artifactId"], policy["artifactSha256"],
        "codex-agent-sdk-binding-parity-" + producer["tree"], producer, observation["run"], token)
    products._require_artifact_job_window(observation, job_name, artifact)
    recipe = (*_COMPILER_INPUTS, "ci/sdk_workflow.py", "ci/products/sdk_package.py")
    # Official observation binds the tested commit to this exact tree. The tree
    # may already be held even when GitHub's ephemeral PR merge commit is not.
    original_recipe = git_inventory(root, producer["tree"], recipe)
    if not original_recipe or original_recipe != git_inventory(root, revision, recipe):
        raise ValueError("Original SDK parity verifier recipe differs from current inputs")
    with ExitStack() as held:
        if archive is None:
            # Reuse this fresh official observation; do not query metadata again.
            limit = 32 * 1024 * 1024
            size = require_integer(artifact["size_in_bytes"], "Original parity archive bytes", 1)
            if size > limit:
                raise ValueError("Original parity archive exceeds its transport bound")
            private = Path(held.enter_context(tempfile.TemporaryDirectory(prefix="sdk-parity-original-")))
            _, archive = products._reuse_contract_ci_upload(artifact, producer, observation["run"], token,
                destination=private / "parity.zip", limit=limit,
                artifact_sha256=policy["artifactSha256"], size=size)
        content = verify_completed_parity_archive(archive, expected_phases=result["phases"],
            expected_bytes=artifact["size_in_bytes"], expected_sha256=policy["artifactSha256"])
    if read_regular_file_bytes(policy_path, max_bytes=4096, reject_symlink_parents=True) != raw:
        raise ValueError("Original SDK parity caller policy changed during verification")
    return dict(content, producer=producer, jobId=job["id"],
        artifactId=policy["artifactId"], artifactSha256=policy["artifactSha256"],
        policySha256=sha256_bytes(raw), verifierInputsSha256=sha256_bytes(original_recipe.encode()))



def require_hosted_sdk_parity(plan_path, discovery_root, state_root, *, repository_root,
                              parity_policy, environ=None, completed_frozen=None, **options):
    """Reuse an independently approved original policy inside current hosted replay.

    The policy is caller-owned authority, never selected from transported parity
    reports. Future workflow wiring must provision it from protected review.
    This verifies reuse; it does not claim a newly executed M11 consumer.
    """
    from products.signing_isolation import require_no_signing_secret
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if (environment.get("GITHUB_ACTIONS") != "true" or environment.get("GITHUB_JOB") != "sdk-parity"
            or not environment.get("GITHUB_TOKEN") or completed_frozen is None):
        raise ValueError("Hosted parity reuse requires its actual job and native authority")
    root = Path(repository_root).resolve(strict=True)
    reports = []

    def consume(state):
        if state.completed_frozen is not completed_frozen:
            raise ValueError("Hosted parity replay changed its native authority")
        completed_frozen.check_consumer(state.consumer)
        report = _repository_report(state.prior)
        report["sdkParity"] = _completed_parity(root, state.plan["validationCommit"],
            state.prior, parity_policy, None, environment["GITHUB_TOKEN"])
        report["verificationContext"] = {"kind": "hosted-original-parity-reuse", "producer": state.producer}
        reports.append(report)

    products.inspect_products(plan_path, discovery_root, state_root, repository_root=root,
        environ=environment, completed_frozen=completed_frozen,
        _verified_state_consumer=consume, **options)
    if len(reports) != 1:
        raise ValueError("Hosted parity requires one authenticated selected-state continuation")
    if products._git_value(root, "rev-parse", "HEAD^{commit}") != reports[0]["verificationContext"]["producer"]["commit"]:
        raise ValueError("Hosted parity source changed during verification")
    return reports[0]

def verify_completed_parity_archive(archive, *, expected_phases, expected_bytes, expected_sha256):
    """Read exact prevalidated parity bytes, NOT grant transport/release authority.

    The caller must independently authenticate the archive identity and phase
    selection. No original receipt is decoded through a different schema or
    rewritten: the successful original verifier supplies its semantics.
    One bounded ZIP pass checks all members without extracting product bodies.
    """
    from products.registry import NATIVE_BINDINGS
    require_integer(expected_bytes, "Original parity archive bytes", 1)
    require_sha256(expected_sha256, "Original parity archive digest")
    inventory, retained, transport = verified_zip_contents(Path(archive),
        max_archive_bytes=32 * 1024 * 1024, max_members=32,
        max_entry_bytes=16 * 1024 * 1024, max_total_bytes=32 * 1024 * 1024,
        retained_paths=("sdk-parity.json", "original-phase-identities.json"),
        max_retained_bytes=1024 * 1024, require_sorted=False)
    if transport != {"bytes": expected_bytes, "sha256": expected_sha256}:
        raise ValueError("Held SDK parity archive differs from authenticated original upload")
    if set(retained) != {"sdk-parity.json", "original-phase-identities.json"}:
        raise ValueError("Original SDK parity archive lacks its report or phase identities")
    originals = require_array(load_canonical_json_bytes(retained["original-phase-identities.json"]),
                              "Original SDK parity phases")
    # Compatibility excludes retrieval/reuse state; original receipts remain exact.
    fields = (*products._IDENTITY_KEYS, "buildKey", "receiptSha256", "objectSha256")
    expected = {tuple(row[key] for key in fields) for row in expected_phases}
    actual = {tuple(require_string(require_exact_keys(row, products._REUSE_PHASE_KEYS,
              "Original SDK parity phase")[key], "Parity original " + key) for key in fields) for row in originals}
    if len(expected_phases) != len(expected) or len(originals) != len(expected) or actual != expected:
        raise ValueError("Original SDK parity does not cover the current exact phase identities")
    report = require_exact_keys(load_canonical_json_bytes(retained["sdk-parity.json"]), {
        "schemaVersion", "phase", "result", "capabilityCount", "languageCount", "scenarioCount",
        "active", "pending", "excluded", "satisfied", "missing", "canonicalApiSha256",
        "canonicalCoverageSha256", "evidenceFiles"}, "Original SDK parity report")
    counts = dict(schemaVersion=2, capabilityCount=556, languageCount=11, scenarioCount=14,
                  active=6104, pending=0, excluded=12, satisfied=6104, missing=0)
    if (any(require_integer(report[key], "Parity " + key, 0) != value for key, value in counts.items())
            or report["phase"] != "M11" or report["result"] != "passed"):
        raise ValueError("Original SDK parity did not pass the complete M11 gate")
    languages = (*NATIVE_BINDINGS, "kotlin", "java", "javascript-typescript", "swift", "objective-c", "c-abi")
    names = {"binding-obligations-m11.json", "canonical-api.json", "canonical-coverage.json",
             *(name + "-parity.json" for name in languages)}
    files = {}
    for row in require_array(report["evidenceFiles"], "Parity evidence inventory"):
        row = require_exact_keys(row, {"path", "bytes", "sha256"}, "Parity evidence file")
        if row["path"] not in names or row["path"] in files:
            raise ValueError("Unexpected or duplicate SDK parity evidence")
        files[row["path"]] = dict(relativePath="m11/" + row["path"],
            bytes=require_integer(row["bytes"], "Parity evidence bytes", 1),
            sha256=require_sha256("sha256:" + require_string(row["sha256"], "Parity evidence SHA"),
                                  "Parity evidence digest"))
    archived = {row["relativePath"]: row for row in inventory}
    if (set(files) != names or set(archived) != {
            "consumer.log", "sdk-parity.json", "original-phase-identities.json",
            *("m11/" + name for name in names)}
            or any(archived["m11/" + name] != row for name, row in files.items())
            or any(report[field] != files[name]["sha256"].removeprefix("sha256:") for field, name in (
                ("canonicalApiSha256", "canonical-api.json"),
                ("canonicalCoverageSha256", "canonical-coverage.json")))):
        raise ValueError("SDK parity evidence differs from the original exact report inventory")
    return dict(result="passed",
        reportSha256=sha256_bytes(retained["sdk-parity.json"]), phaseCount=len(originals),
        languageCount=11, satisfied=6104, excluded=12, scenarioCount=14)


def _bind_runtime_contract(root, result, policy_path, manifest_path, versions):
    """Bind the configured Contract to current native-qualified original bytes."""
    raw, policy = _runtime_contract_policy(policy_path)
    if (policy["contractVersion"] != versions["contract"]
            or policy["runtimeVersion"] != versions["runtime-release"]):
        raise ValueError("Standalone Contract/Runtime versions differ from current authority")
    original = next(row for row in result["phases"] if (
        row["product"], row["component"], row["phase"], row["target"]) ==
        ("contract", "contract", "metadata", "common"))
    receipt_raw = read_regular_file_bytes(policy["contractMetadataReceipt"],
        max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    if sha256_bytes(receipt_raw) != original["receiptSha256"]:
        raise ValueError("Configured Contract is not the current authenticated metadata receipt")
    receipt = products.validate_phase_receipt(load_canonical_json_bytes(receipt_raw))
    manifest_path = Path(manifest_path).absolute()
    if (root / "runtime/.gradle/verified-contracts" not in manifest_path.parents
            or manifest_path.name != "contract-manifest.json"):
        raise ValueError("Runtime acceptance requires its settings-authenticated Contract manifest")
    # One bounded read of the consumed archive; no copying/extracting Maven bodies.
    _, retained, payload = verified_zip_contents(Path(policy["contractPayload"]),
        max_archive_bytes=512 * 1024 * 1024, max_members=4096,
        max_total_bytes=1024 * 1024 * 1024, retained_paths=("contract-manifest.json",),
        max_retained_bytes=16 * 1024 * 1024)
    if (len(receipt["outputs"]) != 1
            or any(receipt["outputs"][0][name] != value for name, value in payload.items())
            or read_regular_file_bytes(manifest_path, max_bytes=16 * 1024 * 1024,
                reject_symlink_parents=True) != retained.get("contract-manifest.json")
            or receipt["productVersion"] != policy["contractVersion"]):
        raise ValueError("Configured Contract manifest/payload differs from the current original")
    if read_regular_file_bytes(policy_path, max_bytes=8192, reject_symlink_parents=True) != raw:
        raise ValueError("Runtime Contract caller policy changed during verification")
    return dict(payloadSha256=payload["sha256"], metadataReceiptSha256=original["receiptSha256"],
        manifestSha256=sha256_bytes(retained["contract-manifest.json"]), policySha256=sha256_bytes(raw),
        configurationTarget=policy["target"])


@products.measured
def require_local_repository_completion(repository_root, policy_path, *, environ=None,
                                       parity_policy=None, parity_archive=None, runtime_only=False,
                                       runtime_contract_policy=None, runtime_contract_manifest=None):
    """Verify actual current inputs through native original evidence, without a CI identity.

    This is a read-only local acceptance report, never a new phase receipt,
    hosted execution claim, or permission to skip the protected workflow.
    """
    import reuse_qualification as native
    from products.registry import PhaseInstanceId
    from products.reuse import LookupSession, advance_reuse, _phase_git_inventories

    environment = os.environ if environ is None else environ
    require_boolean(runtime_only, "Runtime-only acceptance")
    if ((runtime_contract_policy is None) != (runtime_contract_manifest is None)
            or runtime_contract_policy is not None and not runtime_only
            or runtime_only and parity_policy is not None):
        raise ValueError("Standalone Runtime acceptance requires its own complete Contract inputs")
    if (parity_policy is None) != (parity_archive is None):
        raise ValueError("SDK acceptance requires both original parity policy and archive")
    if environment.get("GITHUB_ACTIONS") or environment.get("GITHUB_RUN_ID"):
        raise ValueError("Local repository verification cannot claim a hosted execution identity")
    root = Path(repository_root).resolve(strict=True)
    policy_path = Path(policy_path).absolute()
    raw = read_regular_file_bytes(policy_path, max_bytes=4096, reject_symlink_parents=True)
    policy = load_canonical_json_bytes(raw)
    native.validate_completed_reuse_policy(policy)
    revision = products._git_value(root, "rev-parse", "HEAD^{commit}")
    if policy["consumerCommit"] != revision:
        raise ValueError("Local repository policy must pin the actual current source")
    token = environment.get("GH_TOKEN") or environment.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("Local repository verification requires an original-evidence observation token")
    instances = tuple(sorted(item for item in products.PHASE_INSTANCE_IDS
                             if not runtime_only or item.product in {"contract", "runtime"}))
    with tempfile.TemporaryDirectory(prefix="repository-original-evidence-") as temporary, \
            products._ci_observation_batch():
        capability, _ = native.fetch_completed_frozen(
            Path(temporary).resolve() / "native", consumer_commit=revision,
            verifier_policy_sha256=policy["verifierPolicySha256"], repository_root=root,
            revision=revision, token=token,
            **({"sdk_completion": policy["sdkCompletion"]}
               if not runtime_only and "sdkCompletion" in policy else {}),
            **({"requalification_baseline": policy["requalificationBaseline"]}
               if "requalificationBaseline" in policy else {}),
            **native._native_pin_arguments({key: policy[key] for key in (
                "artifactId", "artifactSha256", "runId", "runAttempt", "signerCommit", "sourceCommit")}))
        if set(capability.completed_phases()) != set(instances):
            raise ValueError("Local repository acceptance requires every current completed phase")
        authorities, unavailable = products._authorities(root, revision, instances)
        if authorities is None or unavailable:
            raise ValueError(unavailable or "Current repository phase authorities are unavailable")
        versions = products._versions(root, revision)
        inventories = _phase_git_inventories(root, revision, instances)
        values = {}
        for row in authorities:
            instance = PhaseInstanceId(*(row[key] for key in products._IDENTITY_KEYS))
            values[instance] = dict(inventory=inventories[instance],
                versions=versions, flags_digest=row["flagsDigest"],
                toolchain_profile_digest=row["toolchainProfileDigest"],
                output_schema_version=row["outputSchemaVersion"])
        _, phases = capability._values()
        envelopes = [capability.envelope(phases[instance]) for instance in instances]
        result, _ = advance_reuse(instances, values, envelopes,
            LookupSession(repository=native.REPOSITORY, pull_request=31),
            repository_root=root, repository_revision=revision, completed_frozen=capability)
        report = _repository_report(result, runtime_only=runtime_only)
        if runtime_contract_policy is not None:
            report["runtimeContract"] = _bind_runtime_contract(
                root, result, runtime_contract_policy, runtime_contract_manifest, versions)
        if parity_policy is not None:
            report["sdkParity"] = _completed_parity(
                root, revision, result, parity_policy, parity_archive, token)
        if read_regular_file_bytes(policy_path, max_bytes=4096, reject_symlink_parents=True) != raw:
            raise ValueError("Local repository caller policy changed during verification")
        if products._git_value(root, "rev-parse", "HEAD^{commit}") != revision:
            raise ValueError("Local repository source changed during verification")
    return {**report, "verificationContext": {
        "kind": "local", "commit": revision, "completedPolicySha256": sha256_bytes(raw)}}


def stage_partial_catalog(state, destination):
    """Preserve new originals; independently qualified objects need no second catalog.

    Full state replay precedes this selection. A qualified envelope is authority
    to omit its body, never an absent-file heuristic or a changed producer receipt.
    The existing development catalog writer still authenticates every new object.
    """
    from sdk_campaign_partial_catalog_caller import stage_partial_sdk_catalog
    from products.signing_isolation import require_no_signing_secret
    require_no_signing_secret(os.environ)
    if state.producer["event"] != "pull_request":
        raise ValueError("Partial SDK catalog requires a current PR")
    selected = {instance: record for instance, record in state.prior_by_instance.items()
                if instance.product == "sdk" and record["state"] in {"retained", "reused"}
                and record.get("source") not in {"stable", "promoted-main"}
                and (state.completed_frozen is None or state.completed_frozen.envelope(record) is None)}
    if not selected:
        return {"phaseCount": 0, "objectBytes": 0}
    return stage_partial_sdk_catalog(replace(state, prior_by_instance=selected), destination)


@verification_scoped
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--repository-root", type=Path, required=True)
    for name in ("plan", "discovery-root"):
        parser.add_argument("--" + name, type=Path)
    for name in ("state-root", "sdk-validation-tooling", "sdk-apple-validation-policy", "github-output"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--sdk-original-workflow-sha")
    parser.add_argument("--partial-catalog-destination", type=Path)
    parser.add_argument("--repository", action="store_true",
                        help="Require the complete authenticated Contract/Runtime/SDK phase DAG")
    parser.add_argument("--sdk", action="store_true",
                        help="Require local current SDK closure and authenticated original full parity")
    parser.add_argument("--hosted-parity", action="store_true",
                        help="Verify an approved original parity upload against current hosted native state")
    parser.add_argument("--runtime", action="store_true",
                        help="Require only current Contract/Runtime originals, without SDK acquisition")
    parser.add_argument("--runtime-contract-policy", type=Path)
    parser.add_argument("--runtime-contract-manifest", type=Path)
    parser.add_argument("--parity-policy", type=Path)
    parser.add_argument("--parity-archive", type=Path)
    parser.add_argument("--local", action="store_true",
                        help="Verify current local repository inputs through completed original evidence; no CI identity")
    parser.add_argument("--gradle", action="store_true",
                        help="Run local repository, SDK or standalone Runtime acceptance through Gradle (offline)")
    parser.add_argument("--configuration-cache", action="store_true",
                        help="Run two local SDK Gradle passes with one private init path; inspect actual store/reuse logs")
    add_metadata_admission_arguments(parser)
    add_completed_frozen_argument(parser)
    args = parser.parse_args(argv)
    if args.configuration_cache and not (args.local and args.gradle and args.sdk):
        parser.error("--configuration-cache requires --sdk --local --gradle")
    if args.runtime:
        if not args.local or args.repository or args.sdk:
            parser.error("--runtime requires --local without --repository or --sdk")
        if args.gradle:
            if args.runtime_contract_policy is None or args.runtime_contract_manifest is not None:
                parser.error("Standalone Gradle requires Contract policy; settings supplies its verified manifest")
        elif (args.runtime_contract_policy is None) != (args.runtime_contract_manifest is None):
            parser.error("Runtime Contract binding requires both policy and settings-verified manifest")
    elif args.runtime_contract_policy is not None or args.runtime_contract_manifest is not None:
        parser.error("Standalone Contract inputs require --runtime --local")
    if args.sdk and (not args.local or args.repository or args.parity_policy is None or args.parity_archive is None):
        parser.error("--sdk requires --local and both original parity inputs, without --repository")
    if args.hosted_parity:
        if (args.local or args.sdk or args.repository or args.runtime or args.gradle
                or args.parity_policy is None or args.parity_archive is not None
                or args.completed_frozen_policy is None or args.state_root is None
                or args.partial_catalog_destination is not None or args.github_output is not None):
            parser.error("Hosted parity requires current state, native policy and original parity policy only")
    elif not args.sdk and (args.parity_policy is not None or args.parity_archive is not None):
        parser.error("Original parity inputs require --sdk --local")
    if args.repository and (args.partial_catalog_destination is not None or args.github_output is not None):
        parser.error("Repository verification requires its standalone report, not catalog or routing outputs")
    if args.gradle and not args.local:
        parser.error("--gradle requires local repository or SDK verification")
    if args.local:
        if (not (args.repository or args.sdk or args.runtime) or args.completed_frozen_policy is None or any(
                value is not None for name, value in vars(args).items() if name not in {
                    "repository_root", "completed_frozen_policy", "repository", "local", "gradle", "configuration_cache",
                    "sdk", "parity_policy", "parity_archive", "runtime", "hosted_parity",
                    "runtime_contract_policy", "runtime_contract_manifest"})):
            parser.error("Local repository verification accepts only its current source and explicit completed policy")
    elif args.plan is None or args.discovery_root is None:
        parser.error("Hosted replay requires --plan and --discovery-root")
    try:
        if args.local:
            gate = run_local_repository_gradle if args.gradle else require_local_repository_completion
            options = dict(parity_policy=args.parity_policy, parity_archive=args.parity_archive) if args.sdk else {}
            if args.runtime:
                options = {} if args.gradle else dict(runtime_only=True)
                if args.runtime_contract_policy is not None:
                    options["runtime_contract_policy"] = args.runtime_contract_policy
                if args.runtime_contract_manifest is not None:
                    options["runtime_contract_manifest"] = args.runtime_contract_manifest
            if args.configuration_cache:
                options["configuration_cache"] = True
            result = gate(args.repository_root, args.completed_frozen_policy, **options)
            print(canonical_json_bytes(result).decode().strip())
            return 0
        with metadata_admission_options(args) as admissions, completed_frozen_options(args) as completed:
            tooling = {} if args.sdk_validation_tooling is None else {"sdk_validation_tooling":
                products._canonical_control(args.sdk_validation_tooling, "Caller SDK tooling policy")}
            apple = {} if args.sdk_apple_validation_policy is None else {"sdk_apple_validation_policy":
                products._canonical_control(args.sdk_apple_validation_policy, "Caller Apple validation policy")}
            options = {**tooling, **apple, **admissions, **completed,
                **({"sdk_original_workflow_sha": args.sdk_original_workflow_sha}
                   if args.sdk_original_workflow_sha is not None else {})}
            if args.hosted_parity:
                result = require_hosted_sdk_parity(args.plan, args.discovery_root, args.state_root,
                    repository_root=args.repository_root, environ=os.environ,
                    parity_policy=args.parity_policy, **options)
            elif args.repository:
                result = require_repository_completion(args.plan, args.discovery_root, args.state_root,
                    repository_root=args.repository_root, environ=os.environ, **options)
            elif args.partial_catalog_destination is None:
                result = require_sdk_completion(args.plan, args.discovery_root, args.state_root,
                    repository_root=args.repository_root, environ=os.environ, **options)
            else:
                from products.sdk_package import _require_capability_output_separate
                from products.signing_isolation import require_no_signing_secret
                require_no_signing_secret(os.environ)
                root = args.repository_root.resolve(strict=True)
                paths = [Path(os.path.abspath(path)) for path in (args.discovery_root, args.state_root)
                         if path is not None]
                if (len(paths) != 2 or not args.sdk_original_workflow_sha
                        or any(path == root or root not in path.parents for path in paths)):
                    raise ValueError("Partial SDK catalog requires original workflow and in-repository state roots")
                _require_capability_output_separate(args.partial_catalog_destination, [args.plan, *paths])
                if args.github_output is not None:
                    _require_capability_output_separate(args.github_output,
                        [args.plan, *paths, args.partial_catalog_destination])
                options.setdefault("sdk_validation_tooling", None)
                state = products._verified_product_state(args.plan, *paths, root, os.environ, **options)
                result = stage_partial_catalog(state, args.partial_catalog_destination)
                require_no_signing_secret(os.environ)
        # Policy lifetime checks must succeed before advertising any result.
        if args.github_output is None:
            print(canonical_json_bytes(result).decode().strip())
        else:
            github_output(args.github_output, result)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
