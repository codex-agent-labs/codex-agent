"""Require completion of every selected SDK phase in authenticated replay."""

import argparse
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
    load_canonical_json_bytes, sha256_bytes,
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


def run_local_repository_gradle(repository_root, policy_path):
    """Use the root verification entry point without changing product/toolkit inputs."""
    root = Path(repository_root).resolve(strict=True)
    policy = Path(policy_path).absolute()
    read_regular_file_bytes(policy, max_bytes=4096, reject_symlink_parents=True)
    report = root / "build/reports/repository/imported-product-evidence.json"
    from products.sdk_package import _require_capability_output_separate
    _require_capability_output_separate(report, [policy])
    # Reject linked output ancestors before the legacy invalidation task can delete anything.
    for path in (report, *report.parents):
        if path.is_symlink():
            raise ValueError("Repository acceptance output must not traverse symbolic links")
    report.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="repository-gradle-adapter-") as temporary:
        script = Path(temporary) / "repository.init.gradle"
        script.write_text(LOCAL_REPOSITORY_INIT, encoding="utf-8")
        subprocess.run([str(root / "gradlew"), "--offline", "--no-configuration-cache", "--no-build-cache",
            "--max-workers=4", "--console=plain", "--init-script",
            str(root / ".github/actions/run-ci-lane/release_tooling.init.gradle"),
            "--init-script", str(script), "-DcodexAgent.completedRepositoryPolicy=" + str(policy),
            "-DcodexAgent.repositoryPython=" + sys.executable, ":verifyRepository"],
            cwd=root, stdout=sys.stderr, check=True)
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


def _repository_report(result):
    from products.aggregate import REPOSITORY_EDGES, REPOSITORY_EVIDENCE_IDENTITIES

    _, selected, records = products._validate_reuse_result(
        result, tuple(sorted(products.PHASE_INSTANCE_IDS)), require_complete=True)
    phases = {products._identity(row): row for row in records}
    terminals = {name: products.PhaseInstanceId(name, *identity)
                 for name, identity in REPOSITORY_EVIDENCE_IDENTITIES.items()}
    edges = []
    for producer, consumer in REPOSITORY_EDGES:
        if terminals[producer] not in products._dependency_closure((terminals[consumer],)):
            raise ValueError("Repository terminal phases lack their required dependency path")
        edges.append({
            "producerProduct": producer, "consumerProduct": consumer,
            "producerReceiptSha256": phases[terminals[producer]]["receiptSha256"],
            "consumerReceiptSha256": phases[terminals[consumer]]["receiptSha256"],
        })
    return {"schemaVersion": 1, "result": "passed", "phaseCount": len(selected),
            "products": [phases[terminals[name]] for name in ("contract", "runtime", "sdk")],
            "edges": edges, "originalPhases": records}


def require_local_repository_completion(repository_root, policy_path, *, environ=None):
    """Verify actual current inputs through native original evidence, without a CI identity.

    This is a read-only local acceptance report, never a new phase receipt,
    hosted execution claim, or permission to skip the protected workflow.
    """
    import reuse_qualification as native
    from products.registry import PhaseInstanceId
    from products.reuse import LookupSession, advance_reuse, _phase_git_inventories

    environment = os.environ if environ is None else environ
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
    instances = tuple(sorted(products.PHASE_INSTANCE_IDS))
    with tempfile.TemporaryDirectory(prefix="repository-original-evidence-") as temporary, \
            products._ci_observation_batch():
        capability, _ = native.fetch_completed_frozen(
            Path(temporary).resolve() / "native", consumer_commit=revision,
            verifier_policy_sha256=policy["verifierPolicySha256"], repository_root=root,
            revision=revision, token=token,
            **({"sdk_completion": policy["sdkCompletion"]} if "sdkCompletion" in policy else {}),
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
        report = _repository_report(result)
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
    parser.add_argument("--local", action="store_true",
                        help="Verify current local repository inputs through completed original evidence; no CI identity")
    parser.add_argument("--gradle", action="store_true",
                        help="Run --repository --local through root :verifyRepository (offline, warm build)")
    add_metadata_admission_arguments(parser)
    add_completed_frozen_argument(parser)
    args = parser.parse_args(argv)
    if args.repository and (args.partial_catalog_destination is not None or args.github_output is not None):
        parser.error("Repository verification requires its standalone report, not catalog or routing outputs")
    if args.gradle and not args.local:
        parser.error("--gradle requires --repository --local")
    if args.local:
        if (not args.repository or args.completed_frozen_policy is None or any(value is not None for name, value in
                vars(args).items() if name not in {"repository_root", "completed_frozen_policy", "repository", "local", "gradle"})):
            parser.error("Local repository verification accepts only its current source and explicit completed policy")
    elif args.plan is None or args.discovery_root is None:
        parser.error("Hosted replay requires --plan and --discovery-root")
    try:
        if args.local:
            gate = run_local_repository_gradle if args.gradle else require_local_repository_completion
            result = gate(args.repository_root, args.completed_frozen_policy)
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
            if args.repository:
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
