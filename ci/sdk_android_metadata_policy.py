"""Build caller-owned Android metadata replay policy from verified originals.

The metadata carrier is checked only as lossless transport.  Authority comes
from the existing official Android/Firebase validation reader plus explicit
caller Contract, source and tooling inputs.  Full metadata admission still
runs later in :class:`AndroidMetadataAdmission`.
"""

import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (
    _directory_inventory, _open_directory, _stat_identity,
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_regular_directory,
    write_canonical_json,
)
from products.sdk_android_metadata_admission import AndroidMetadataAdmission
from products.sdk_package import _require_capability_output_separate
from products.sdk_validation_inputs import _request_inventory
from products.signing_isolation import require_no_signing_secret
from products import sdk_android_validation_phase as validation_phase
from sdk_android_firebase_original import verified_original_android_firebase_validation
from sdk_android_metadata_original import _context
from sdk_metadata_evidence import load_sdk_metadata_evidence
from reuse import github_output


POLICY_NAME = "android-metadata-policy.json"
_LIMIT = 16 * 1024 * 1024


def _read(path):
    return read_regular_file_bytes(
        Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)


def _path(value, label, *, directory=False):
    path = Path(value).absolute()
    if path.resolve(strict=True) != path:
        raise ValueError(f"Android metadata {label} must be normalized and non-symbolic")
    if directory:
        require_regular_directory(path, f"Android metadata {label}")
    return path


def create_sdk_android_metadata_policy(
        plan, evidence_root, validation_receipt_path, validation_capture,
        destination, *, validation_artifact_id, validation_artifact_sha256,
        trusted_workflow_sha, trusted_android_workflow_sha,
        expected_original_run_id, expected_original_run_attempt,
        package_stage, package_receipt, binary_stage, binary_receipt,
        compatibility_request, binary_contract_evidence,
        trusted_source_commit, trusted_source_tree, original_context,
        tooling_evidence, tooling_public_key, java_executable,
        apkanalyzer_executable, required_trust_domain, repository_root,
        environ=None, token, tooling_keyring=None, tooling_keys_directory=None):
    """Publish one canonical descriptor after authenticating its validation.

    The current plan supplies only the current tooling-policy revision.  It is
    intentionally not required to equal the retained metadata producer commit.
    The returned descriptor is invocation policy, never product or hosted
    authority, and its metadata carrier is replayed in full only on later use.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if environment is not os.environ:
        require_no_signing_secret(os.environ)
    if (tooling_keyring is None) != (tooling_keys_directory is None):
        raise ValueError("Android metadata tooling keyring and directory must be paired")

    repository = _path(repository_root, "repository", directory=True)
    plan = _path(plan, "plan")
    evidence_root = _path(evidence_root, "evidence root", directory=True)
    validation_receipt_path = _path(validation_receipt_path, "validation receipt")
    validation_capture = _path(validation_capture, "validation capture", directory=True)
    trees = {
        "packageStage": _path(package_stage, "package stage", directory=True),
        "binaryStage": _path(binary_stage, "binary stage", directory=True),
        "toolingEvidence": _path(tooling_evidence, "tooling evidence", directory=True),
    }
    files = {
        "packageReceipt": _path(package_receipt, "package receipt"),
        "binaryReceipt": _path(binary_receipt, "binary receipt"),
        "compatibilityRequest": _path(compatibility_request, "compatibility request"),
        "toolingPublicKey": _path(tooling_public_key, "tooling public key"),
        "javaExecutable": _path(java_executable, "Java executable"),
        "apkanalyzerExecutable": _path(apkanalyzer_executable, "apkanalyzer executable"),
    }
    if tooling_keyring is not None:
        files["toolingKeyring"] = _path(tooling_keyring, "tooling keyring")
        trees["toolingKeysDirectory"] = _path(
            tooling_keys_directory, "tooling keys directory", directory=True)

    contract = load_canonical_json_bytes(canonical_json_bytes(binary_contract_evidence))
    context = _context(load_canonical_json_bytes(canonical_json_bytes(original_context)))
    contract_trees, contract_files = validation_phase._contract_sources(contract)
    trees.update({"contract:" + name: _path(path, name, directory=True)
                  for name, path in contract_trees.items()})
    files.update({"contract:" + name: _path(path, name)
                  for name, path in contract_files.items()})
    request_inputs = tuple(_request_inventory(files["compatibilityRequest"]))
    files.update({f"compatibility:{index}": path
                  for index, path in enumerate(request_inputs)})
    output = Path(destination).absolute()
    protected = [repository, plan, evidence_root, validation_receipt_path,
                 validation_capture, *trees.values(), *files.values()]

    def output_safe():
        _require_capability_output_separate(output, protected)
        if (output.exists() or output.is_symlink()
                or output.resolve(strict=False) != output):
            raise ValueError("Android metadata policy destination must be fresh and normalized")
        for ancestor in output.parents:
            if ancestor.exists() or ancestor.is_symlink():
                require_regular_directory(ancestor, "Android metadata policy output ancestry")

    output_safe()
    plan_bytes = _read(plan)
    validation_receipt_bytes = _read(validation_receipt_path)
    tree_before = {name: regular_file_inventory(path, allow_empty=True)
                   for name, path in {**trees, "evidenceRoot": evidence_root,
                                      "validationCapture": validation_capture}.items()}
    file_before = {name: _read(path) for name, path in files.items()}
    authority_bytes = canonical_json_bytes({
        "binaryContractEvidence": contract,
        "trustedSourceCommit": trusted_source_commit,
        "trustedSourceTree": trusted_source_tree,
        "originalContext": context,
        "requiredTrustDomain": required_trust_domain,
    })

    with tempfile.TemporaryDirectory(prefix="android-metadata-policy-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, [output, *protected])
        captured_plan = private / "impact-plan.json"
        captured_plan.write_bytes(plan_bytes)
        current_plan = product_reuse._validate_plan(captured_plan, repository)
        policy_revision = current_plan["validationCommit"]
        records = [
            {"receiptSha256": record["receiptSha256"], "captureRoot": record["capture"]}
            for record in load_sdk_metadata_evidence(evidence_root)
            if (record["component"], record["phase"], record["target"])
            == ("sdk-android", "metadata", "android")
        ]
        if not records:
            raise ValueError("Android metadata policy requires retained Android metadata evidence")
        policy = {
            "plan": str(plan), "validationCapture": str(validation_capture),
            "packageStage": str(trees["packageStage"]),
            "packageReceipt": str(files["packageReceipt"]),
            "binaryStage": str(trees["binaryStage"]),
            "binaryReceipt": str(files["binaryReceipt"]),
            "compatibilityRequest": str(files["compatibilityRequest"]),
            "binaryContractEvidence": contract,
            "trustedSourceCommit": trusted_source_commit,
            "trustedSourceTree": trusted_source_tree,
            "originalContext": context,
            "toolingEvidence": str(trees["toolingEvidence"]),
            "toolingPublicKey": str(files["toolingPublicKey"]),
            "javaExecutable": str(files["javaExecutable"]),
            "apkanalyzerExecutable": str(files["apkanalyzerExecutable"]),
            "toolingTrustDomain": required_trust_domain,
            "toolingKeyring": (None if tooling_keyring is None
                               else str(files["toolingKeyring"])),
            "toolingKeysDirectory": (None if tooling_keys_directory is None
                                     else str(trees["toolingKeysDirectory"])),
        }
        descriptor = {"evidenceRoot": str(evidence_root),
                      "records": records, "policy": policy}
        descriptor_bytes = canonical_json_bytes(descriptor)

        def unchanged():
            require_no_signing_secret(environment)
            if environment is not os.environ:
                require_no_signing_secret(os.environ)
            if (_read(plan) != plan_bytes
                    or _read(captured_plan) != plan_bytes
                    or _read(validation_receipt_path) != validation_receipt_bytes
                    or canonical_json_bytes({
                        "binaryContractEvidence": binary_contract_evidence,
                        "trustedSourceCommit": trusted_source_commit,
                        "trustedSourceTree": trusted_source_tree,
                        "originalContext": original_context,
                        "requiredTrustDomain": required_trust_domain,
                    }) != authority_bytes
                    or any(regular_file_inventory(path, allow_empty=True) != tree_before[name]
                           for name, path in {**trees, "evidenceRoot": evidence_root,
                                             "validationCapture": validation_capture}.items())
                    or any(_read(path) != file_before[name] for name, path in files.items())):
                raise ValueError("Android metadata caller policy inputs changed during construction")

        reader = dict(
            validation_artifact_id=validation_artifact_id,
            validation_artifact_sha256=validation_artifact_sha256,
            trusted_workflow_sha=trusted_workflow_sha,
            trusted_android_workflow_sha=trusted_android_workflow_sha,
            expected_original_run_id=expected_original_run_id,
            expected_original_run_attempt=expected_original_run_attempt,
            package_stage=trees["packageStage"], package_receipt=files["packageReceipt"],
            binary_stage=trees["binaryStage"], binary_receipt=files["binaryReceipt"],
            compatibility_request=files["compatibilityRequest"],
            binary_contract_evidence=contract,
            trusted_source_commit=trusted_source_commit,
            trusted_source_tree=trusted_source_tree,
            tooling_evidence=trees["toolingEvidence"],
            tooling_public_key=files["toolingPublicKey"],
            java_executable=files["javaExecutable"],
            apkanalyzer_executable=files["apkanalyzerExecutable"],
            policy_revision=policy_revision,
            required_trust_domain=required_trust_domain,
            repository_root=repository, environ=environment, token=token,
            tooling_keyring=(None if tooling_keyring is None else files["toolingKeyring"]),
            tooling_keys_directory=(None if tooling_keys_directory is None
                                    else trees["toolingKeysDirectory"]),
        )
        prepared = private / "prepared"
        published_inventory = published_identity = published_descriptor_inventory = None
        try:
            unchanged()
            with verified_original_android_firebase_validation(
                    captured_plan, validation_receipt_path, **reader) as verified:
                if (verified["receiptBytes"] != validation_receipt_bytes
                        or regular_file_inventory(verified["capture"], allow_empty=True) !=
                           tree_before["validationCapture"]):
                    raise ValueError(
                        "Android metadata validation capture differs from its authenticated original")
                # Constructor validation keeps this producer aligned with the
                # exact later CLI adapter without pretending to admit metadata.
                AndroidMetadataAdmission(
                    evidence_root, records, repository=repository,
                    policy_revision=policy_revision, policy=policy)
                prepared.mkdir()
                write_canonical_json(prepared / POLICY_NAME, descriptor)
                if _read(prepared / POLICY_NAME) != descriptor_bytes:
                    raise ValueError("Android metadata policy descriptor changed before publication")
                unchanged()
                output_safe()
                publish_regular_tree(prepared, output)
                published_inventory = regular_file_inventory(output)
                published_identity = _stat_identity(os.stat(output, follow_symlinks=False))
                published_descriptor = _open_directory(output, "Published Android metadata policy")
                try:
                    published_descriptor_inventory = _directory_inventory(published_descriptor)
                finally:
                    os.close(published_descriptor)
                if (_read(output / POLICY_NAME) != descriptor_bytes
                        or published_inventory != regular_file_inventory(prepared)):
                    raise ValueError("Published Android metadata policy differs from its private candidate")
                unchanged()
            unchanged()
            published_descriptor = _open_directory(output, "Published Android metadata policy final check")
            try:
                if (_stat_identity(os.fstat(published_descriptor)) != published_identity
                        or _directory_inventory(published_descriptor) != published_descriptor_inventory
                        or _read(output / POLICY_NAME) != descriptor_bytes):
                    raise ValueError("Published Android metadata policy changed after validation")
            finally:
                os.close(published_descriptor)
        except BaseException as error:
            # No atomic compare-and-rmdir exists here. A rejected publication
            # stays as diagnostics; consumers must use only a successful return.
            try:
                unchanged()
            except BaseException as mutation:
                raise mutation from error
            raise
    return descriptor


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in (
            "plan", "evidence-root", "validation-receipt", "validation-capture",
            "destination", "package-stage", "package-receipt", "binary-stage",
            "binary-receipt", "compatibility-request", "binary-contract-evidence",
            "original-context", "tooling-evidence", "tooling-public-key",
            "java-executable", "apkanalyzer-executable", "repository-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in (
            "validation-artifact-sha256", "trusted-workflow-sha",
            "trusted-android-workflow-sha", "trusted-source-commit",
            "trusted-source-tree"):
        parser.add_argument("--" + name, required=True)
    for name in ("validation-artifact-id", "expected-original-run-id",
                 "expected-original-run-attempt"):
        parser.add_argument("--" + name, type=int, required=True)
    parser.add_argument("--required-trust-domain", choices=("development", "release"), required=True)
    parser.add_argument("--tooling-keyring", type=Path)
    parser.add_argument("--tooling-keys-directory", type=Path)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    if (args.tooling_keyring is None) != (args.tooling_keys_directory is None):
        parser.error("Android metadata tooling keyring and directory must be paired")
    try:
        descriptor = create_sdk_android_metadata_policy(
            args.plan, args.evidence_root, args.validation_receipt,
            args.validation_capture, args.destination,
            validation_artifact_id=args.validation_artifact_id,
            validation_artifact_sha256=args.validation_artifact_sha256,
            trusted_workflow_sha=args.trusted_workflow_sha,
            trusted_android_workflow_sha=args.trusted_android_workflow_sha,
            expected_original_run_id=args.expected_original_run_id,
            expected_original_run_attempt=args.expected_original_run_attempt,
            package_stage=args.package_stage, package_receipt=args.package_receipt,
            binary_stage=args.binary_stage, binary_receipt=args.binary_receipt,
            compatibility_request=args.compatibility_request,
            binary_contract_evidence=product_reuse._canonical_control(
                args.binary_contract_evidence, "Caller Android binary Contract evidence"),
            trusted_source_commit=args.trusted_source_commit,
            trusted_source_tree=args.trusted_source_tree,
            original_context=product_reuse._canonical_control(
                args.original_context, "Caller original Android metadata context"),
            tooling_evidence=args.tooling_evidence,
            tooling_public_key=args.tooling_public_key,
            java_executable=args.java_executable,
            apkanalyzer_executable=args.apkanalyzer_executable,
            required_trust_domain=args.required_trust_domain,
            repository_root=args.repository_root, environ=os.environ,
            token=os.environ.get("GITHUB_TOKEN", ""),
            tooling_keyring=args.tooling_keyring,
            tooling_keys_directory=args.tooling_keys_directory)
        if set(descriptor) != {"evidenceRoot", "records", "policy"}:
            raise ValueError("Android metadata policy descriptor shape changed")
        result = {"policy_path": str(args.destination.absolute() / POLICY_NAME)}
        if args.github_output is None:
            print(canonical_json_bytes(result).decode().strip())
        else:
            github_output(args.github_output, result)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
