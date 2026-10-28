"""Hold official original Core carriers while the existing strict selector replays them.

The caller independently authenticates the signed catalog, original receipt
digests and replay policy. This module neither elects product work nor turns
runner labels into native compiler/toolchain proof.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci import product_reuse
from ci.products.inventory import (canonical_json_bytes, git_regular_blob_bytes, load_canonical_json_bytes,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_sha256, sha256_bytes, sha256_file, write_canonical_json)
from ci.products.receipt import validate_phase_receipt
from products.registry import PhaseInstanceId, SDK_FACADE_CONTRACT_COMPONENTS, SDK_FACADE_TARGETS
from ci.products.sdk_facade_inputs import _path, _request, _sources
from ci.products.sdk_facade_metadata_admission import fresh_metadata_arguments
from ci.products.sdk_facade_validation import _inventory
from ci.products.sdk_facade_validation_admission import _NON_NATIVE_TARGETS, _native_archive_path, _native_archive_digest
from ci.products.sdk_validation_inputs import _request_paths
from ci.products.signing_isolation import require_no_signing_secret
from ci.sdk_facade_capture import (capture_sdk_facade_metadata_upload,
    capture_sdk_facade_validation_upload)
from ci.sdk_facade_metadata_inputs import _qualified_predecessors, verified_facade_metadata_inputs
from ci.sdk_facade_metadata_selection import write_selected_facade_metadata_policy
from ci.sdk_facade_upload_locator import locate_original_facade_upload
from sdk_phase import maven_consumed_predecessors
from products.restore import verification_session


_FRESH_INSTANCE = PhaseInstanceId("sdk", "sdk-core", "metadata", "common")


def _retained_validation_origin(raw, consumer):
    from sdk_campaign_original_locator import retained_core_origin
    receipt = load_canonical_json_bytes(raw)
    if tuple(receipt.get(name) for name in ("product", "component", "phase")) != ("sdk", "sdk-core", "validation"):
        return None
    if receipt["producer"] == consumer:
        return None
    origin = retained_core_origin("validation", receipt["buildKey"], consumer, target=receipt["target"])
    if origin is not None and origin["producer"] == receipt["producer"]:
        return origin
    producer = receipt["producer"]
    if (any(producer[name] != consumer[name] for name in
            ("repository", "workflowPath", "event", "pullRequest"))
            or (producer["runId"], producer["runAttempt"]) >= (consumer["runId"], consumer["runAttempt"])):
        return None
    # Reviewed selection only: use the consumer's immutable Git recipe, never
    # an uploaded workflow claim. Official capture and full replay still follow.
    spec = load_canonical_json_bytes(git_regular_blob_bytes(
        Path(__file__).resolve().parents[1], consumer["commit"],
        "ci/tests/data/requalified-sdk-completed-resume.json", max_bytes=16 * 1024 * 1024))
    if spec.get("schemaVersion") not in (2, 3):
        return None
    fields = ("product", "component", "phase", "target")
    matches = [row for row in spec["completedPhases"]
               if all(row[name] == receipt[name] for name in fields)
               and row["buildKey"] == receipt["buildKey"]]
    if not matches:
        return None
    if len(matches) != 1 or matches[0]["receiptSha256"] != sha256_bytes(raw):
        raise ValueError("Reviewed Core original differs from the exact selected receipt")
    pins = [row for row in spec["originals"] if all(row[name] == receipt[name] for name in fields)]
    if len(pins) != 1:
        raise ValueError("Reviewed Core original upload is missing or ambiguous")
    pin = pins[0]
    return {"producer": producer, "artifact_id": pin["artifactId"],
            "artifact_sha256": pin["artifactSha256"], "job_id": pin["jobId"],
            "workflow_sha": pin["workflowSha"]}


def _require_retained_upload(locator, origin):
    if origin is not None and locator != {name: origin[name] for name in ("artifact_id", "artifact_sha256")}:
        raise ValueError("Core validation metadata input differs from its reviewed original upload")


def _fresh_policy_sources(policy):
    """Pin typed caller inputs before any original-upload API observation."""
    require_exact_keys(policy, {"plan", "toolingEvidence", "toolingPublicKey", "javaExecutable",
        "toolingKeyring", "toolingKeysDirectory", "toolingTrustDomain", "validations",
        "contractDigest", "componentDigests"}, "Fresh Core metadata policy")
    require_sha256(policy["contractDigest"], "Fresh Core Contract digest")
    components = require_exact_keys(policy["componentDigests"],
        set(SDK_FACADE_CONTRACT_COMPONENTS.values()), "Fresh Core Contract component digests")
    for digest in components.values():
        require_sha256(digest, "Fresh Core Contract component digest")
    trust = policy["toolingTrustDomain"]
    if trust not in {"development", "release"} or any(
            (policy[name] is None) != (trust == "development")
            for name in ("toolingKeyring", "toolingKeysDirectory")):
        raise ValueError("Fresh Core tooling trust requires its exact caller keyring pair")
    validations = require_exact_keys(policy["validations"], SDK_FACADE_TARGETS,
                                     "Fresh Core validation locators")
    files = {_path(policy[name], name) for name in ("plan", "toolingPublicKey", "javaExecutable")}
    trees = {_path(policy["toolingEvidence"], "toolingEvidence")}
    archives = set()
    for name, collection in (("toolingKeyring", files), ("toolingKeysDirectory", trees)):
        if policy[name] is not None:
            collection.add(_path(policy[name], name))
    for target, record in validations.items():
        fields = {"validationReceipt", "facadeRequest"} | (
            {"nativeCompilerArchive"} if target not in _NON_NATIVE_TARGETS else set())
        require_exact_keys(record, fields, "Fresh Core validation caller locator")
        files.add(_path(record["validationReceipt"], "Fresh Core receipt"))
        request_path = _path(record["facadeRequest"], "Fresh Core facade request")
        files.add(request_path)
        archive = _native_archive_path(target, record.get("nativeCompilerArchive"))
        if archive is not None:
            files.add(archive)
            archives.add(archive)
        request, _ = _request(request_path)
        _, source_trees, source_files = _sources(request)
        trees.update(source_trees.values())
        files.update(source_files.values())
        files.update(_request_paths(Path(request["compatibilityRequest"])))
    return ({path: _native_archive_digest(path) if path in archives else
             sha256_file(path, reject_symlink_parents=True) for path in files},
            {path: _inventory(path, allow_empty=True) for path in trees})


@contextmanager
def held_fresh_facade_metadata_policy(plan, discovery, state, **arguments):
    """Hold verified fresh inputs, with no metadata reuse authority."""
    with verification_session(), _held_captured_facade_metadata_policy(plan, discovery, state, **arguments) as captured:
        descriptor, predecessors, elected = captured
        policy = load_canonical_json_bytes(read_regular_file_bytes(
            descriptor, reject_symlink_parents=True))["policy"]
        root = Path(arguments["repository_root"]).resolve(strict=True)
        environ, token = arguments["environ"], arguments["token"]
        trusted_workflow_sha = arguments["trusted_workflow_sha"]
        completed_frozen = arguments.get("completed_frozen")
        arguments = fresh_metadata_arguments(policy)
        with verified_facade_metadata_inputs(plan=Path(plan).absolute(), validations=arguments["validations"],
                contract_digest=arguments["contract_digest"], component_digests=arguments["component_digests"],
                repository_root=root, environ=environ, token=token,
                trusted_workflow_sha=trusted_workflow_sha, tooling_evidence=arguments["tooling_evidence"],
                tooling_public_key=arguments["tooling_public_key"], java_executable=arguments["java_executable"],
                policy_revision=elected.plan["validationCommit"],
                required_trust_domain=arguments["required_trust_domain"],
                tooling_keyring=arguments["tooling_keyring"],
                tooling_keys_directory=arguments["tooling_keys_directory"],
                completed_frozen=completed_frozen, elected=elected) as original:
            package = predecessors / "sdk-sdk-core-package-common"
            if (read_regular_file_bytes(package / "phase-receipt.json", reject_symlink_parents=True) !=
                    original["package"]["receiptBytes"]
                    or _inventory(package / "stage") != _inventory(original["package"]["stage"])):
                raise ValueError("Fresh Core original package differs from elected predecessor")
            for target in SDK_FACADE_TARGETS:
                selected = predecessors / f"sdk-sdk-core-validation-{target}"
                record = original["validations"][target]
                if (read_regular_file_bytes(selected / "phase-receipt.json", reject_symlink_parents=True) !=
                        record["receiptBytes"] or _inventory(selected / "stage") != _inventory(record["stage"])):
                    raise ValueError("Fresh Core original validation differs from elected predecessor")
            yield descriptor


@contextmanager
def held_captured_facade_metadata_policy(plan, discovery, state, **arguments):
    """Hold official captures or qualified locators for the consuming controller.

    This records=[] descriptor grants no semantic acceptance or reuse admission.
    Use it only around execute(), which independently verifies original inputs,
    checks elected package/validation bytes, and finalizes after clean reader exit.
    """
    with verification_session(), _held_captured_facade_metadata_policy(plan, discovery, state, **arguments) as captured:
        yield captured[0]


@contextmanager
def _held_captured_facade_metadata_policy(plan, discovery, state, *, expected_build_key,
        replay_policy, trusted_workflow_sha, repository_root, environ, token,
        sdk_apple_validation_policy=None, sdk_android_metadata_admission=None, completed_frozen=None):
    """Acquire exact elected originals and hold caller inputs through consumption."""
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    plan = _path(str(Path(plan).absolute()), "Fresh Core plan")
    discovery, state, _ = product_reuse._product_materialization_paths(
        root, discovery, state, root / "build/fresh-core-policy-unused")
    policy_bytes = canonical_json_bytes(replay_policy)
    policy = load_canonical_json_bytes(policy_bytes)
    if _path(policy["plan"], "Fresh Core replay plan") != plan:
        raise ValueError("Fresh Core replay policy refers to another current plan")
    file_digests, tree_inventories = _fresh_policy_sources(policy)
    archives = {Path(row["nativeCompilerArchive"]) for row in policy["validations"].values()
                if "nativeCompilerArchive" in row}
    file_digests[plan] = sha256_file(plan, reject_symlink_parents=True)
    tree_inventories.update({path: _inventory(path, allow_empty=True) for path in (discovery, state)})

    def unchanged():
        require_no_signing_secret(environ)
        if (canonical_json_bytes(replay_policy) != policy_bytes
                or any((_native_archive_digest(path) if path in archives else
                        sha256_file(path, reject_symlink_parents=True)) != digest
                       for path, digest in file_digests.items())
                or any(_inventory(path, allow_empty=True) != before
                       for path, before in tree_inventories.items())):
            raise ValueError("Fresh Core original election or caller policy changed")

    tooling = {"evidence": policy["toolingEvidence"], "publicKey": policy["toolingPublicKey"],
        "javaExecutable": policy["javaExecutable"], "requiredTrustDomain": policy["toolingTrustDomain"],
        "keyring": policy["toolingKeyring"], "keysDirectory": policy["toolingKeysDirectory"]}
    optional = ({"sdk_apple_validation_policy": sdk_apple_validation_policy}
                if sdk_apple_validation_policy is not None else {})
    if sdk_android_metadata_admission is not None:
        optional["sdk_android_metadata_admission"] = sdk_android_metadata_admission
    unchanged()
    elected = product_reuse._verified_product_state(plan, discovery, state, root, environ, tooling,
        sdk_original_workflow_sha=trusted_workflow_sha,
        **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}), **optional)
    ready = elected.prior_ready_plans.get(_FRESH_INSTANCE)
    if ready is None or ready["buildKey"] != expected_build_key:
        raise ValueError("Fresh Core metadata is not ready with the exact elected build key")
    unchanged()
    with tempfile.TemporaryDirectory(prefix="fresh-core-predecessors-", dir=root) as local_temp, \
            tempfile.TemporaryDirectory(prefix="fresh-core-originals-") as external_temp:
        predecessors = Path(local_temp).resolve() / "inputs"
        outside = Path(external_temp).resolve()
        if outside == root or root in outside.parents:
            raise ValueError("Fresh Core original scratch must be outside the source checkout")
        materialized = product_reuse.materialize_product_predecessors(plan, discovery, state,
            _FRESH_INSTANCE, predecessors, expected_build_key=expected_build_key,
            materialized_scope=maven_consumed_predecessors(_FRESH_INSTANCE),
            repository_root=root, environ=environ, sdk_validation_tooling=tooling,
            sdk_apple_validation_policy=sdk_apple_validation_policy,
            sdk_original_workflow_sha=trusted_workflow_sha,
            sdk_android_metadata_admission=sdk_android_metadata_admission,
            **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}))
        if materialized != ready:
            raise ValueError("Fresh Core predecessor election changed during materialization")
        receipts = {}
        for target in SDK_FACADE_TARGETS:
            selected = predecessors / f"sdk-sdk-core-validation-{target}/phase-receipt.json"
            raw = read_regular_file_bytes(selected, reject_symlink_parents=True)
            caller = Path(policy["validations"][target]["validationReceipt"])
            if raw != read_regular_file_bytes(caller, reject_symlink_parents=True):
                raise ValueError("Fresh Core original receipt differs from elected predecessor")
            receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
            if tuple(receipt[name] for name in ("product", "component", "phase", "target")) != (
                    "sdk", "sdk-core", "validation", target):
                raise ValueError("Fresh Core selected predecessor has the wrong target")
            receipts[target] = raw
        captures = outside / "evidence"
        captures.mkdir()
        native = _qualified_predecessors(completed_frozen, elected)
        for target in SDK_FACADE_TARGETS:
            unchanged()
            path = Path(policy["validations"][target]["validationReceipt"])
            if native is not None:
                identity = PhaseInstanceId("sdk", "sdk-core", "validation", target)
                if receipts[target] != native[identity]["receiptBytes"]:
                    raise ValueError("Fresh Core selected validation differs from native authority")
                _, artifact, _ = completed_frozen.observe_extended_sdk(elected.prior_by_instance[identity],
                    producer=elected.consumer["producer"], token=token)
                policy["validations"][target].update(artifactId=artifact["id"], artifactSha256=artifact["digest"])
                continue
            origin = _retained_validation_origin(receipts[target], elected.producer)
            workflow = trusted_workflow_sha if origin is None else origin["workflow_sha"]
            locator = locate_original_facade_upload(path, expected_receipt_sha256=sha256_bytes(receipts[target]),
                trusted_workflow_sha=workflow, token=token)
            _require_retained_upload(locator, origin)
            unchanged()
            capture = captures / target
            capture_sdk_facade_validation_upload(plan, capture, validation_receipt_path=path,
                artifact_id=locator["artifact_id"], artifact_sha256=locator["artifact_sha256"],
                trusted_workflow_sha=workflow, repository_root=root, environ=environ, token=token)
            policy["validations"][target]["captureRoot"] = str(capture)
        fresh_metadata_arguments(policy)
        before = _inventory(captures, allow_empty=True)
        unchanged()
        descriptor = outside / "policy.json"
        write_canonical_json(descriptor, {"evidenceRoot": str(captures), "records": [], "policy": policy})
        descriptor_bytes = read_regular_file_bytes(descriptor, reject_symlink_parents=True)
        unchanged()
        try:
            yield descriptor, predecessors, elected
        finally:
            unchanged()
            if (_inventory(captures, allow_empty=True) != before
                    or read_regular_file_bytes(descriptor, reject_symlink_parents=True) != descriptor_bytes):
                raise ValueError("Fresh Core original carriers or descriptor changed while held")
            if native is not None and _qualified_predecessors(completed_frozen, elected) != native:
                raise ValueError("Fresh Core predecessor authority changed while held")


@contextmanager
def held_original_facade_metadata_policy(plan, *, catalog, catalog_source,
        metadata_receipt_path, expected_receipt_sha256, replay_policy,
        trusted_workflow_sha, repository_root, token):
    """Yield a temporary descriptor after all twelve official captures and replay.

    `expected_receipt_sha256` is the caller-authenticated mapping for `common`
    plus all eleven targets. `replay_policy` is the independent Core metadata
    policy without captureRoot fields; this function fills only those paths.
    Consumers must use the descriptor inside the context and rerun the concrete
    metadata admission. Original producers remain exactly as in the receipts.
    """
    require_no_signing_secret(os.environ)
    root = Path(repository_root).resolve(strict=True)
    expected = require_exact_keys(expected_receipt_sha256,
        {"common", *SDK_FACADE_TARGETS}, "Caller-selected Core original receipts")
    for digest in expected.values():
        require_sha256(digest, "Caller-selected Core original receipt")
    policy_bytes = canonical_json_bytes(replay_policy)
    policy = load_canonical_json_bytes(policy_bytes)
    validations = require_exact_keys(policy["validations"], SDK_FACADE_TARGETS,
                                   "Core original validation policy")
    if any("captureRoot" in value for value in validations.values()):
        raise ValueError("Core original capture paths must come from official capture")
    paths = {"common": Path(metadata_receipt_path), **{
        target: Path(validations[target]["validationReceipt"]) for target in SDK_FACADE_TARGETS}}
    originals = {}
    for target, path in paths.items():
        raw = read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                                      reject_symlink_parents=True)
        if sha256_bytes(raw) != expected[target]:
            raise ValueError("Core original receipt differs from independent selection")
        originals[target] = raw
    expected_bytes = canonical_json_bytes(expected)

    def unchanged():
        require_no_signing_secret(os.environ)
        if (canonical_json_bytes(expected_receipt_sha256) != expected_bytes
                or canonical_json_bytes(replay_policy) != policy_bytes
                or any(read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                       reject_symlink_parents=True) != originals[target]
                       for target, path in paths.items())):
            raise ValueError("Core caller-selected originals or policy changed")

    unchanged()
    with tempfile.TemporaryDirectory(prefix="core-original-inputs-") as temporary:
        private = Path(temporary).resolve(strict=True)
        if private == root or root in private.parents:
            raise ValueError("Core original scratch must remain outside the source repository")
        evidence = private / "evidence"
        evidence.mkdir()
        for target in (*SDK_FACADE_TARGETS, "common"):
            unchanged()
            path = paths[target]
            origin = _retained_validation_origin(originals[target],
                load_canonical_json_bytes(originals["common"])["producer"])
            workflow = trusted_workflow_sha if origin is None else origin["workflow_sha"]
            locator = locate_original_facade_upload(path,
                expected_receipt_sha256=expected[target],
                trusted_workflow_sha=workflow, token=token)
            _require_retained_upload(locator, origin)
            unchanged()
            arguments = dict(artifact_id=locator["artifact_id"],
                artifact_sha256=locator["artifact_sha256"],
                trusted_workflow_sha=workflow,
                repository_root=root, token=token)
            capture = evidence / target
            if target == "common":
                capture_sdk_facade_metadata_upload(plan, capture,
                    metadata_receipt_path=path, **arguments)
            else:
                capture_sdk_facade_validation_upload(plan, capture,
                    validation_receipt_path=path, **arguments)
            unchanged()
            if target != "common":
                policy["validations"][target]["captureRoot"] = str(capture)
        records = sorted(({"receiptSha256": expected[target], "captureRoot": target}
                          for target in ("common", *SDK_FACADE_TARGETS)),
                         key=lambda record: record["receiptSha256"])
        descriptor = private / "policy.json"
        write_selected_facade_metadata_policy(plan, descriptor, catalog=catalog,
            catalog_source=catalog_source, metadata_receipt_path=paths["common"],
            evidence_root=evidence, records=records, policy=policy,
            repository_root=root)
        before = regular_file_inventory(evidence, allow_empty=True)
        descriptor_bytes = read_regular_file_bytes(descriptor, reject_symlink_parents=True)
        unchanged()
        try:
            yield descriptor
        finally:
            unchanged()
            if (regular_file_inventory(evidence, allow_empty=True) != before
                    or read_regular_file_bytes(descriptor, reject_symlink_parents=True) != descriptor_bytes):
                raise ValueError("Core original carriers or descriptor changed while held")
