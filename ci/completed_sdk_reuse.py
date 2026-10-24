"""Validate incremental SDK completion controls after independent native admission.

These checks do not create semantic authority. The native issuer authenticates
the successful admission upload and each consumed original object. The consumer
authenticates its attestation before creating the sealed completed-reuse capability.
"""

from contextlib import contextmanager
from pathlib import Path

from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, load_json_bytes, require_exact_keys,
    require_relative_path, require_sha256, sha256_bytes, validate_file_record,
)
from products.receipt import validate_phase_receipt, validate_producer
from products.registry import PHASE_INSTANCE_IDS, PhaseInstanceId
from sdk_phase import CHECKPOINT_ROUTES, SDK_FAMILY_INSTANCES


IDENTITY = ("product", "component", "phase", "target")
OBJECT = ("buildKey", "receiptSha256", "objectSha256")
LIMIT = 16 * 1024 * 1024
IOS_PACKAGE = PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
COLLECTED_VALIDATION_JOB = "product-validation / sdk-collect-9"
_CORE_COLLECTOR = "product-validation / sdk-core-binary-wave / sdk-collect-11"
_CORE_PACKAGE_COLLECTOR = "product-validation / sdk-core-package-wave / sdk-collect-12"
# The legacy JavaScript frontend precedes family continuation routing, but its
# successful collector uses the same bounded, independently verified format.
_COLLECTED_WAVES = {"product-validation / sdk-collect-1": 1,
                    "product-validation / sdk-collect-19": 19,
                    # Package replay has its own reader; do not also register it
                    # as a generic compact replay through CHECKPOINT_ROUTES.
                    "product-validation / sdk-collect-5": 5,
                    **{job: row.wave for job, row in CHECKPOINT_ROUTES.items()}}
SOURCE_PLAN = "product-resume-inputs/plan/impact-plan.json"
_SOURCE_UPLOADS = {
    "product-validation / product-resume": "codex-agent-product-resume-",
    "product-validation / plan": "codex-agent-planned-product-resume-",
    **{job: f"codex-agent-sdk-wave-{wave}-state-" for job, wave in _COLLECTED_WAVES.items()},
}


def _identity(record):
    return PhaseInstanceId(*(record.get(field) for field in IDENTITY))


def original_worker_member(spec):
    """Compact states omit bodies; consumption uses exact original workers."""
    return spec["schemaVersion"] in (3, 4)


def source_predecessor_context(spec):
    return type(spec) is dict and type(spec.get("schemaVersion")) is int and spec["schemaVersion"] == 4


def source_predecessors(spec):
    """Observed source context, never additional native completion claims."""
    if not source_predecessor_context(spec):
        return {}
    rows = spec.get("sourcePredecessors")
    if type(rows) is not list or not rows or len(rows) > len(PHASE_INSTANCE_IDS):
        raise ValueError("Planned SDK completion requires bounded source predecessors")
    result = _records(rows, "Planned SDK source predecessors")
    for row in result.values():
        require_exact_keys(row, set(IDENTITY + OBJECT), "Planned SDK source predecessor")
        for field in OBJECT:
            require_sha256(row[field], "Planned SDK predecessor " + field)
    return result


def collected_validation(spec):
    return (type(spec) is dict and type(spec.get("source")) is dict
            and type(spec["source"].get("jobName")) is str
            and spec["source"]["jobName"] in _COLLECTED_WAVES)


def _records(rows, label):
    import reuse_qualification
    return reuse_qualification._phase_records(rows, label)


def _object_limit(instance):
    if instance == IOS_PACKAGE:
        return 8 * 1024**3
    if instance in (SDK_FAMILY_INSTANCES['android-binary'] | SDK_FAMILY_INSTANCES['android-package']
                    | SDK_FAMILY_INSTANCES['native-package'] | SDK_FAMILY_INSTANCES['native-validation']):
        # Packages and native validation's compiled test closures are bounded
        # object bodies, not JSON controls. Receipt/manifest JSON keeps LIMIT.
        return 512 * 1024 * 1024
    return LIMIT


def _receipt_objects(spec):
    """Only exact collected objects may supply their embedded receipt control."""
    from products.restore import object_relative_path
    objects = spec.get("receiptObjects", [])
    if type(objects) is not list or len(objects) > len(spec["completedPhases"]):
        raise ValueError("Collected receipt objects exceed their selected scope")
    selected = {row["receiptPath"]: row for row in spec["completedPhases"]}
    result = {}
    for row in objects:
        if type(row) is not dict:
            raise ValueError("Collected receipt object must be a record")
        has_hint, hint = "receipt" in row, row.get("receipt")
        row = {key: value for key, value in row.items() if key != "receipt"}
        validate_file_record(row, "Collected receipt object", with_kind=False)
        path = row["relativePath"] + "/phase-receipt.json"
        phase = selected.get(path)
        # Same hashed-body bound as original consumption; receipt JSON stays small.
        limit = _object_limit(_identity(phase)) if phase is not None else LIMIT
        if (path in result or phase is None or not 0 < row["bytes"] <= limit
                or row["sha256"] != phase["objectSha256"]
                or row["relativePath"] != spec["stateRoot"] + "/original-objects/"
                    + object_relative_path(phase["buildKey"], phase["receiptSha256"])):
            raise ValueError("Collected receipt object differs from its exact selected phase")
        if has_hint:
            raw = canonical_json_bytes(validate_phase_receipt(hint))
            if len(raw) > LIMIT or sha256_bytes(raw) != phase["receiptSha256"]:
                raise ValueError("Collected receipt hint differs from its pinned original")
        result[path] = (row, phase)
    return result


def validate_controls(spec, controls, base):
    """Bind every new SDK receipt to the exact successful state and native base."""
    selected = _records(spec["completedPhases"], "Incremental completed SDK phases")
    if (not selected or any(instance not in PHASE_INSTANCE_IDS or instance.product != "sdk"
                            for instance in selected)):
        raise ValueError("Incremental completion requires registered SDK phases")
    rows = spec["controls"]
    if (type(rows) is not list or not 3 <= len(rows) <= 128
            or type(controls) is not dict
            or len({row["relativePath"] for row in rows}) != len(rows)
            or set(controls) != {row["relativePath"] for row in rows}):
        raise ValueError("Incremental completion changes its fixed controls")
    for row in rows:
        validate_file_record(row, "Incremental SDK control", with_kind=False)
        value = controls[row["relativePath"]]
        if collected_validation(spec) and row["relativePath"] == SOURCE_PLAN:
            if type(value) is not str or value != spec["sourcePlan"]:
                raise ValueError("Collector source plan changes its exact original bytes")
            raw = value.encode("utf-8")
        else:
            raw = canonical_json_bytes(value)
        if len(raw) > LIMIT or len(raw) != row["bytes"] or sha256_bytes(raw) != row["sha256"]:
            raise ValueError("Incremental SDK control differs from its approved original")
    prefix = require_relative_path(spec["stateRoot"], "Incremental SDK state root") + "/"
    producer = validate_producer(spec["source"]["producer"])
    request = controls[prefix + "reuse-wave-request.json"]
    result = controls[prefix + "reuse-wave-result.json"]
    if collected_validation(spec):
        from product_reuse import _same_run_state_consumer
        _same_run_state_consumer({"producer": producer}, controls[prefix + "producer.json"])
    elif controls[prefix + "producer.json"] != producer:
        raise ValueError("Incremental SDK completion changes its original consumer or policy")
    if (request["repositoryRevision"] != producer["commit"]
            or any(request[field] != base["request"][field]
                   for field in ("repository", "pullRequest", "versions", "catalogs"))
            or request.get("sdkRuntimeSource") is not None):
        raise ValueError("Incremental SDK completion changes its original consumer or policy")
    phases = _records(result["phases"], "Incremental SDK result")
    available = _records(request["availableObjects"], "Incremental SDK available objects")
    frozen = _records(base["expectedResult"]["phases"], "Native completed predecessors")
    if set(selected) & set(frozen):
        raise ValueError("Incremental SDK completion replaces an existing native phase")
    context = source_predecessors(spec)
    if source_predecessor_context(spec) and set(context) & set(selected):
        raise ValueError("Planned SDK source context overlaps selected native claims")
    expected = {**(context if source_predecessor_context(spec) else frozen), **selected}
    if (set(available) != set(expected)
            or {instance for instance, row in phases.items() if row["state"] in {"retained", "reused"}}
            != set(expected) or result["matrices"]["contract"] or result["matrices"]["runtime"]):
        raise ValueError("Incremental SDK completion changes its successful original scope")
    authorities = _records(request["phaseAuthorities"], "Incremental SDK authorities")
    original_authorities = _records(base["request"]["phaseAuthorities"], "Native predecessor authorities")
    for instance, expected_phase in expected.items():
        if any(phases[instance].get(field) != expected_phase[field]
               or available[instance].get(field) != expected_phase[field] for field in OBJECT):
            raise ValueError("Incremental SDK completion changes an admitted original")
        if (instance in frozen and (not source_predecessor_context(spec)
                or all(context.get(instance, {}).get(field) == frozen[instance][field] for field in OBJECT))
                and authorities.get(instance) != original_authorities[instance]):
            raise ValueError("Incremental SDK completion changes a native predecessor authority")
    if source_predecessor_context(spec):
        from products.reuse import _dependency_closure
        if not set(_dependency_closure(tuple(selected))) <= set(expected):
            raise ValueError("Planned SDK source context lacks a selected dependency closure")
        if any(instance not in authorities for instance in expected):
            raise ValueError("Planned SDK source context lacks its phase authorities")
    receipts = []
    receipt_prefixes = (prefix, "product-resume-state/") if collected_validation(spec) else (prefix,)
    for instance, phase in selected.items():
        require_exact_keys(phase, set(IDENTITY + OBJECT) | {"receiptPath"}, "Incremental SDK phase")
        path = require_relative_path(phase["receiptPath"], "Incremental SDK receipt path")
        receipt = validate_phase_receipt(controls[path])
        if (not path.startswith(receipt_prefixes) or _identity(receipt) != instance
                or receipt["buildKey"] != phase["buildKey"]
                or sha256_bytes(canonical_json_bytes(receipt)) != phase["receiptSha256"]
                or any(receipt["producer"][field] != producer[field]
                       for field in ("repository", "event", "pullRequest"))
                or (receipt["producer"]["runId"], receipt["producer"]["runAttempt"])
                > (producer["runId"], producer["runAttempt"])):
            raise ValueError("Incremental SDK receipt differs from its admitted original")
        receipts.append(receipt)
    return request, [phases[instance] for instance in sorted(selected)], receipts


def validate_current(request, phases, receipts, *, root, revision, original_revision):
    """Reuse completion only for identical current owning inputs and authorities."""
    import product_reuse
    from products.inventory import tree_entries
    from products.selection import phase_inventory_paths
    from reuse_qualification import QualificationIncompatible, _changed_inventory_paths
    before, after = (dict(tree_entries(Path(root), commit)) for commit in (original_revision, revision))
    changed = _changed_inventory_paths(before, after)
    expected = _records(request["phaseAuthorities"], "Incremental SDK authorities")
    by_id = {_identity(receipt): receipt for receipt in receipts}
    for phase in phases:
        instance = _identity(phase)
        if phase_inventory_paths(changed, instance):
            raise QualificationIncompatible("Incremental SDK owning inputs changed")
        authorities, unavailable = product_reuse._authorities(root, revision, (instance,))
        if unavailable or authorities != [expected[instance]]:
            raise QualificationIncompatible("Incremental SDK current authority changed")
        if any(by_id[instance]["inputs"][field] != expected[instance][field]
               for field in ("toolchainProfileDigest", "flagsDigest", "outputSchemaVersion")):
            raise ValueError("Incremental SDK receipt changes its admitted phase authority")


def observe_original(original, receipt, token, *, native_locator=None, _fresh_observation=None):
    """Fresh original gates; native_locator requires an authenticated native subject."""
    import product_reuse as products
    receipt = validate_phase_receipt(receipt)
    producer = validate_producer(receipt["producer"])
    if (producer["repository"] != "codex-agent-labs/codex-agent" or producer["event"] != "pull_request"
            or producer["pullRequest"] != 31 or producer["workflowPath"] != ".github/workflows/ci.yml"):
        raise ValueError("Incremental original changes its approved repository or PR scope")
    instance = _identity(receipt)
    if instance.product != "sdk" or instance not in PHASE_INSTANCE_IDS:
        raise ValueError("Incremental original must be a registered SDK phase")
    base_job = f"product-validation / sdk-{instance.component}-{instance.phase}-{instance.target}"
    workflow = {"trusted_workflow_sha": original["workflowSha"]}
    child = next((row for row in CHECKPOINT_ROUTES.values()
                  if row.child and instance in SDK_FAMILY_INSTANCES[row.family]), None)
    if child is not None:
        from sdk_campaign_original_locator import fresh_sdk_worker_route
        base_job, _ = fresh_sdk_worker_route(instance, receipt)
        workflow = {"trusted_workflows_by_phase": {"original": {
            "path": child.workflow_path, "sha": original["workflowSha"]}}}
    if native_locator is not None and (type(native_locator) is not dict
            or type(native_locator.get("job")) is not dict or native_locator["job"].get("id") != original["jobId"]):
        raise ValueError("Native original locator changes its independently pinned job")
    observed = products._observe_ci_producer_jobs({"original": producer},
        jobs_by_phase={"original": base_job}, build_keys_by_phase={"original": receipt["buildKey"]},
        token=token, **workflow,
        **({"_fresh_observation": _fresh_observation} if _fresh_observation is not None else {}),
        **({"native_job_ids_by_phase": {"original": original["jobId"]}} if native_locator is not None else {}))
    matches = products._matching_ci_jobs(observed[0]["jobs"], base_job, expected_build_key=receipt["buildKey"])
    if len(matches) != 1 or matches[0].get("id") != original["jobId"]:
        raise ValueError("Incremental SDK original job is missing or ambiguous")
    name = (products._worker_artifact_prefix("sdk", instance) +
            f"{receipt['buildKey'][7:]}-{producer['tree']}-attempt-{producer['runAttempt']}")
    artifact = products._contract_ci_upload_metadata(original["artifactId"], original["artifactSha256"],
        name, producer, observed[0]["run"], token,
        **({"upload_limit": products._IOS_PACKAGE_UPLOAD_LIMIT} if instance in products._LARGE_SDK_UPLOADS else {}))
    products._require_artifact_job_window(observed[0], matches[0]["name"], artifact)
    locator = products._runtime_original_locator(
        artifact, original["workflowSha"], instance, matches[0])
    if native_locator is not None and locator != native_locator:
        raise ValueError("Fresh original differs from its authenticated native locator")
    return artifact, observed, locator


def observe_source(source, token, *, contract=False, native_locator=None, _fresh_observation=None):
    """Issuers select fully; native consumers bind the complete authenticated locator."""
    import product_reuse as products
    import reuse_qualification as native
    producer = validate_producer(source["producer"])
    if (producer["repository"] != native.REPOSITORY or producer["event"] != "pull_request"
            or producer["pullRequest"] != 31 or producer["workflowPath"] != ".github/workflows/ci.yml"):
        raise ValueError("Incremental source changes its approved producer scope")
    if contract:
        job, prefix = ("product-validation / contract-validation / contract-attestation",
                       "codex-agent-contract-release-controls-")
    else:
        job = source.get("jobName")
        if type(job) is not str or job not in _SOURCE_UPLOADS:
            raise ValueError("Incremental source requires a fixed native state producer")
        prefix = _SOURCE_UPLOADS[job]
    if native_locator is not None and (type(native_locator) is not dict
            or type(native_locator.get("job")) is not dict or native_locator["job"].get("id") != source["jobId"]):
        raise ValueError("Native source locator changes its independently pinned job")
    route = CHECKPOINT_ROUTES.get(job)
    child = route.workflow_path if route is not None and route.child else None
    workflow = ({"trusted_workflows_by_phase": {"source": {
        "path": child, "sha": source["workflowSha"]}}}
        if child is not None else {"trusted_workflow_sha": source["workflowSha"]})
    observed = products._observe_ci_producer_jobs({"source": producer}, jobs_by_phase={"source": job},
        token=token, **workflow,
        **({"_fresh_observation": _fresh_observation} if _fresh_observation is not None else {}),
        **({"native_job_ids_by_phase": {"source": source["jobId"]}} if native_locator is not None else {}))
    selected = products._matching_ci_jobs(observed[0]["jobs"], job)
    if len(selected) != 1 or selected[0]["id"] != source["jobId"]:
        raise ValueError("Incremental source differs from its approved successful job")
    suffix = f"-attempt-{producer['runAttempt']}" if job in _COLLECTED_WAVES else ""
    artifact = products._contract_ci_upload_metadata(source["artifactId"], source["artifactSha256"],
        prefix + producer["tree"] + suffix, producer, observed[0]["run"], token)
    if artifact["size_in_bytes"] != source["artifactBytes"]:
        raise ValueError("Incremental source size changed")
    products._require_artifact_job_window(observed[0], job, artifact)
    locator = products._runtime_original_locator(artifact, source["workflowSha"],
        PhaseInstanceId("contract", "contract", "metadata", "common") if contract else
        PhaseInstanceId("sdk", "javascript", "metadata", "node"), selected[0])
    if native_locator is not None and locator != native_locator:
        raise ValueError("Fresh source differs from its authenticated native locator")
    return artifact, observed, locator


def _base(frozen, sdk):
    import reuse_qualification as native
    base = load_canonical_json_bytes(canonical_json_bytes(frozen))
    request, phase, receipt, _ = native._completed_sdk_controls(
        sdk["spec"], sdk["proof"]["controls"], frozen, sdk["original"])
    instance = _identity(receipt)
    for field in ("availableObjects", "phaseAuthorities"):
        base["request"][field].append(_records(request[field], field)[instance])
    base["expectedResult"]["phases"].append(phase)
    return base


def _spec(spec):
    import reuse_qualification as native
    collected = collected_validation(spec)
    context = source_predecessor_context(spec)
    reuse = (collected or context) and "reuseCompletion" in spec
    require_exact_keys(spec, {"schemaVersion", "parent", "parentProofSha256", "source", "stateRoot",
        "controls", "completedPhases", "originals", "contractControls", "contractFiles"}
        | ({"sourcePlan"} if collected else set())
        | ({"receiptObjects"} if collected and "receiptObjects" in spec else set())
        | ({"sourcePredecessors"} if context else set())
        | ({"reuseCompletion", "reuseCompletionProofSha256"} if reuse else set()), "Incremental SDK spec")
    if type(spec["schemaVersion"]) is not int or spec["schemaVersion"] not in (2, 3, 4):
        raise ValueError("Unsupported incremental SDK spec")
    if context:
        source_predecessors(spec)
        if not collected and (spec["source"].get("jobName") != "product-validation / plan"
                or spec["stateRoot"] != "product-resume-state"):
            raise ValueError("SDK source context requires an exact successful plan or registered collector role")
    native._native_pin_arguments(spec["parent"])
    native.require_sha256(spec["parentProofSha256"], "Approved native parent subject")
    selected = _records(spec["completedPhases"], "Incremental SDK phases")
    originals = _records(spec["originals"], "Incremental SDK originals")
    if set(selected) != set(originals):
        raise ValueError("Incremental SDK original scope changed")
    for source, contract in ((spec["source"], False), (spec["contractControls"], True)):
        require_exact_keys(source, {"producer", "workflowSha", "jobId", "artifactId", "artifactSha256",
            "artifactBytes"} | (set() if contract else {"jobName", "inventoryCommit"})
            | ({"referenceControlSha256"} if collected and not contract else set()), "Incremental native source")
        validate_producer(source["producer"])
        native._commit(source["workflowSha"])
        native.require_sha256(source["artifactSha256"], "Incremental original upload")
        for field in ("jobId", "artifactId", "artifactBytes"):
            if type(source[field]) is not int or source[field] <= 0:
                raise ValueError("Incremental native source has invalid positive identity")
        bound = (64 * 1024**2 if context and not collected and not contract else
                 16 * 1024**3 if collected and not contract else LIMIT)
        if source["artifactBytes"] > bound:
            raise ValueError("Incremental controls exceed the bounded original upload")
    if (spec["stateRoot"] != ("runtime-state" if collected else "product-resume-state")
            or type(spec["source"]["jobName"]) is not str
            or spec["source"]["jobName"] not in _SOURCE_UPLOADS
            or collected and spec["schemaVersion"] not in (3, 4)):
        raise ValueError("Incremental native source changes its successful resume contract")
    if collected:
        _receipt_objects(spec)
        native.require_sha256(spec["source"]["referenceControlSha256"], "Approved collector reference control")
        if type(spec["sourcePlan"]) is not str:
            raise ValueError("Collector source plan must preserve its original JSON text")
        raw = spec["sourcePlan"].encode("utf-8")
        if len(raw) > LIMIT:
            raise ValueError("Collector source plan exceeds its bounded control size")
        plan, producer = load_json_bytes(raw), spec["source"]["producer"]
        if (type(plan) is not dict or plan.get("remoteBuildAuthorized") is not True
                or any(plan.get(field) != producer[field] for field in ("repository", "event", "pullRequest"))
                or plan.get("validationCommit") != producer["commit"]
                or plan.get("validationTree") != producer["tree"]):
            raise ValueError("Collector source plan differs from its exact authorized producer")
        expected = {"relativePath": SOURCE_PLAN, "bytes": len(raw), "sha256": sha256_bytes(raw)}
        if len(raw) > LIMIT or [row for row in spec["controls"] if row["relativePath"] == SOURCE_PLAN] != [expected]:
            raise ValueError("Collector source plan lacks its exact bounded control pin")
    if reuse:
        native._native_pin_arguments(spec["reuseCompletion"])
        native.require_sha256(spec["reuseCompletionProofSha256"], "Approved earlier native completion subject")
        earlier = spec["reuseCompletion"]
        producer = spec["source"]["producer"]
        if (earlier["runId"], earlier["runAttempt"]) >= (producer["runId"], producer["runAttempt"]):
            raise ValueError("Reused native completion must precede its collected source")
    native._commit(spec["source"]["inventoryCommit"])
    for row in originals.values():
        require_exact_keys(row, set(IDENTITY) | {"artifactId", "artifactSha256", "jobId", "workflowSha"},
                           "Incremental original")
        native._commit(row["workflowSha"])
        native.require_sha256(row["artifactSha256"], "Incremental original digest")
        if any(type(row[key]) is not int or row[key] <= 0 for key in ("artifactId", "jobId")):
            raise ValueError("Incremental original identity is invalid")
    return originals


def _inventory_revision(spec, root, *, token=None):
    from products.inventory import run_git
    revision = spec["source"]["inventoryCommit"]
    if token is not None:
        from sdk_handoff import _ensure_pinned_git_commit
        _ensure_pinned_git_commit(root, revision, spec["source"]["producer"]["tree"], token)
    if run_git(root, "rev-parse", revision + "^{tree}").strip() != spec["source"]["producer"]["tree"]:
        raise ValueError("Incremental inventory revision differs from the admitted producer tree")
    return revision


def _contract_files(spec, files, sdk):
    """Bind small signed controls to the unchanged, independently qualified handoff."""
    import reuse_qualification as native
    rows = spec["contractFiles"]
    if (type(files) is not dict or type(rows) is not list or len(rows) != 9
            or len({row["relativePath"] for row in rows}) != 9
            or set(files) != {row["relativePath"] for row in rows}):
        raise ValueError("Incremental Contract control inventory changed")
    qualified = {row["relativePath"]: row for row in native._sdk_input_members(sdk["proof"]["sdkInputs"])}
    for row in rows:
        validate_file_record(row, "Incremental Contract control", with_kind=False)
        raw = files[row["relativePath"]].encode("utf-8")
        if len(raw) != row["bytes"] or len(raw) > LIMIT or sha256_bytes(raw) != row["sha256"]:
            raise ValueError("Incremental Contract control differs from approved original")
        name = row["relativePath"].removeprefix("contract-input/")
        if name == "contract-manifest.json":
            continue  # Its original signature and frozen semantic projections are checked on use.
        matches = [value for path, value in qualified.items() if path.endswith("/" + name)
                   and any(path.startswith("sdk-inputs/inputs/" + prefix + "/") for prefix in
                           ("contractAttestation", "contractAttestationSignature", "contractPublicKey"))]
        if len(matches) != 1 or any(matches[0][field] != row[field] for field in ("bytes", "sha256")):
            raise ValueError("Incremental Contract control differs from native predecessor evidence")
    return files


def validate_extension(spec, proof, arguments, *, root, revision, frozen, token, consumer_revision=None,
                       _checkpoint=None):
    """The caller has authenticated this exact new native subject first."""
    import reuse_qualification as native
    originals = _spec(spec)
    if _checkpoint is not None:
        if type(_checkpoint) is not _CheckpointConsumer:
            raise ValueError("Checkpoint semantics require a private authenticated consumer witness")
        _checkpoint.match(spec, proof, arguments, consumer_revision, token)
    if source_predecessor_context(spec):
        if consumer_revision is None:
            raise ValueError("Planned SDK completion requires an explicit current consumer revision")
        native._commit(consumer_revision)
    require_exact_keys(proof, {"schemaVersion", "kind", "issuerCommit", "specSha256", "parentProof",
        "controls", "source", "originals", "members", "contractSource", "contractFiles"},
        "Incremental native completion")
    if (type(proof["schemaVersion"]) is not int or proof["schemaVersion"] != spec["schemaVersion"]
            or proof["kind"] != "completed-sdk-reuse" or proof["issuerCommit"] != arguments["signer_commit"]
            or proof["specSha256"] != sha256_bytes(canonical_json_bytes(spec))
            or sha256_bytes(canonical_json_bytes(proof["parentProof"])) != spec["parentProofSha256"]
            or proof["parentProof"].get("schemaVersion") != 1):
        raise ValueError("Incremental completion changes its approved native issuer or parent")
    # Body inheritance authenticates the old subject at its own pinned product
    # baseline, which may predate its signer. Explicit consumer revisions still
    # pass the unchanged current-input gate below.
    if revision is None:
        revision = _inventory_revision(spec, root, token=token)
    # The new native issuer authenticated this exact old native subject before
    # signing it. Its immutable SHA is independently pinned in the issuer Git spec.
    sdk = native._validate_completed_sdk(proof["parentProof"], native._native_pin_arguments(spec["parent"]),
        root=root, revision=revision, frozen=frozen, token=token)
    request, phases, receipts = validate_controls(spec, proof["controls"], _base(frozen, sdk))
    import product_reuse as products
    from products.restore import bounded_verify
    _contract_files(spec, proof["contractFiles"], sdk)
    if type(proof["originals"]) is not list or len(proof["originals"]) != len(receipts):
        raise ValueError("Incremental SDK native original scope changed")
    with products._ci_observation_batch():
        products._prime_runtime_artifact_metadata([
            {"receipt": receipt, "artifactId": originals[_identity(receipt)]["artifactId"]}
            for receipt in receipts if _checkpoint is None or receipt["producer"] != spec["source"]["producer"]], token)
        source, contract, *expected_locators = bounded_verify(lambda observe: observe()[2], (
            (lambda: observe_source(spec["source"], token, native_locator=proof["source"]))
            if _checkpoint is None else _checkpoint.source,
            lambda: observe_source(spec["contractControls"], token, contract=True, native_locator=proof["contractSource"]),
            *(lambda receipt=receipt, locator=locator: (
                observe_original(originals[_identity(receipt)], receipt, token, native_locator=locator)
                if _checkpoint is None else _checkpoint.original(originals[_identity(receipt)], receipt, locator, token))
              for receipt, locator in zip(receipts, proof["originals"]))))
    if source != proof["source"]:
        raise ValueError("Incremental completed source changed")
    if contract != proof["contractSource"]:
        raise ValueError("Incremental Contract source changed")
    if expected_locators != proof["originals"]:
        raise ValueError("Incremental SDK original native observations changed")
    # A fresh runner may lack the original PR merge even with full branch history.
    # Acquire only the exact native-pinned tree after its live source checks pass.
    validate_current(request, phases, receipts, root=root,
                     revision=consumer_revision if source_predecessor_context(spec) else revision,
                     original_revision=_inventory_revision(spec, root, token=token))
    available = _records(request["availableObjects"], "Incremental original objects")
    if type(proof["members"]) is not list or len(proof["members"]) != len(phases):
        raise ValueError("Incremental SDK object members changed")
    embedded_objects = {_identity(phase): row for row, phase in _receipt_objects(spec).values()}
    for phase, member in zip(phases, proof["members"]):
        validate_file_record(member, "Incremental SDK object", with_kind=False)
        expected = spec["stateRoot"] + "/" + available[_identity(phase)]["objectPath"]
        limit = LIMIT
        if original_worker_member(spec):
            from products.restore import object_relative_path
            expected = "shard/" + object_relative_path(phase["buildKey"], phase["receiptSha256"])
            limit = _object_limit(_identity(phase))
        if (member["relativePath"] != expected or member["sha256"] != phase["objectSha256"]
                or not 0 < member["bytes"] <= limit):
            raise ValueError("Incremental SDK consumed object changed")
        embedded = embedded_objects.get(_identity(phase))
        if embedded is not None and member["bytes"] != embedded["bytes"]:
            raise ValueError("Incremental original size differs from its collected declaration")
    if _checkpoint is not None:
        _checkpoint.match(spec, proof, arguments, consumer_revision, token)
    sdk["extension"] = {"spec": spec, "proof": proof}
    return sdk


def _qualified_members(spec, prior, phases, receipts, *, root=None, _checkpoint=None):
    """Join only after _fetch_completed_sdk freshly authenticates the native subject.

    The new issuer reuses exact byte qualification; current source admission,
    owning inputs, receipts and fresh original locators remain mandatory.
    """
    extension = prior.get("extension")
    if extension is None:
        raise ValueError("Object reuse requires an earlier incremental native completion")
    old, proof = extension["spec"], extension["proof"]
    if _checkpoint is not None:
        if type(_checkpoint) is not _CheckpointConsumer:
            raise ValueError("Checkpoint inheritance requires a private authenticated predecessor")
        _checkpoint.inherit(spec, prior)
    if (old["schemaVersion"] not in (3, 4) or old["parent"] != spec["parent"]
            or sha256_bytes(canonical_json_bytes(prior["proof"])) != spec["parentProofSha256"]
            or _checkpoint is None and sha256_bytes(canonical_json_bytes(proof)) != spec["reuseCompletionProofSha256"]):
        raise ValueError("Reused native completion differs from its pinned subject or parent")
    selected = _records(phases, "Current admitted SDK phases")
    earlier = _records(old["completedPhases"], "Previously native-qualified SDK phases")
    current_receipts = {_identity(receipt): canonical_json_bytes(receipt) for receipt in receipts}
    omitted = set(earlier) - set(selected)
    if omitted:
        if root is None:
            raise ValueError("Reused native completion drops a previously admitted SDK phase")
        from products.inventory import tree_entries
        from products.selection import phase_inventory_paths
        from reuse_qualification import _changed_inventory_paths
        before, after = (dict(tree_entries(root, _inventory_revision(subject, root)))
                         for subject in (old, spec))
        changed = _changed_inventory_paths(before, after)
        from products.reuse import _dependency_closure
        if any(not any(phase_inventory_paths(changed, dependency) for dependency in
                       (_dependency_closure((instance,)) if source_predecessor_context(spec) else (instance,)))
               for instance in omitted):
            raise ValueError("Reused native completion drops an unchanged SDK phase")
    qualified = {}
    for instance, member, locator in zip(sorted(earlier), proof["members"], proof["originals"], strict=True):
        phase = earlier[instance]
        if instance in omitted:
            # Its old proof/receipt remains immutable in reuseCompletion. Changed
            # inputs invalidate this key; no replacement receives body authority.
            continue
        if source_predecessor_context(spec) and not collected_validation(spec) and instance not in (
                PhaseInstanceId("sdk", "sdk-core", "binary", "common"),
                PhaseInstanceId("sdk", "sdk-android", "binary", "android")):
            continue  # Only these unchanged SDK bodies are inherited by this source checkpoint.
        if phase['buildKey'] != selected[instance]['buildKey']:
            # A changed key inherits no qualification: the issuer below verifies
            # its new successful original and complete object independently.
            continue
        if (any(phase[field] != selected[instance][field] for field in OBJECT)
                or canonical_json_bytes(proof["controls"][phase["receiptPath"]]) != current_receipts[instance]):
            raise ValueError("Reused native completion changes an original SDK object or receipt")
        qualified[instance] = member, locator
    return qualified


def _observe_incremental_originals(originals, receipts, qualified, token, *, _checkpoint=None):
    """Fresh bounded provenance; only authenticated inherited objects pin jobs."""
    import product_reuse as products
    from products.restore import bounded_verify

    def observe(receipt):
        instance = _identity(receipt)
        fresh = _checkpoint is not None and receipt["producer"] == _checkpoint.producer
        if instance in qualified and _checkpoint is not None and _checkpoint.previous is not None:
            return _checkpoint.previous.original(originals[instance], receipt, qualified[instance][1], token)
        result = observe_original(originals[instance], receipt, token,
            **({"_fresh_observation": _checkpoint.observation}
               if fresh else {}),
            **({"native_locator": qualified[instance][1]} if instance in qualified and not fresh else {}))
        return result

    batch = ({"current_attempt": tuple(str(_checkpoint.producer[key]) for key in ("runId", "runAttempt")),
              "share_nested": True} if _checkpoint is not None else {})
    with products._ci_observation_batch(**batch):
        products._prime_runtime_artifact_metadata([
            {"receipt": receipt, "artifactId": originals[_identity(receipt)]["artifactId"]}
            for receipt in receipts if _checkpoint is None
            or _checkpoint.previous is None and _identity(receipt) in qualified], token)
        return bounded_verify(observe, receipts)


_CHECKPOINT_INPUTS = object()


class _CheckpointIssueInputs:
    """Authenticated in this issuer invocation, never decoded from retained JSON."""
    __slots__ = ("spec_sha", "revision", "controls", "controls_sha", "source", "parent_frozen",
                 "sdk", "prior", "observation", "producer", "token", "authority_sha", "previous")

    def __init__(self, spec, revision, controls, source, parent_frozen, sdk, prior, observation, token, seal,
                 previous=None):
        if seal is not _CHECKPOINT_INPUTS:
            raise ValueError("Checkpoint issuance requires authenticated private inputs")
        self.spec_sha, self.revision = sha256_bytes(canonical_json_bytes(spec)), revision
        self.controls, self.controls_sha = controls, sha256_bytes(canonical_json_bytes(controls))
        self.source, self.parent_frozen, self.sdk, self.prior = source, parent_frozen, sdk, prior
        self.observation, self.producer, self.token = observation, spec["source"]["producer"], token
        self.previous = previous
        self.authority_sha = sha256_bytes(canonical_json_bytes([source, parent_frozen, sdk, prior]))

    def check(self, spec, revision, token):
        import product_reuse as products
        if (revision != self.revision or sha256_bytes(canonical_json_bytes(spec)) != self.spec_sha
                or sha256_bytes(canonical_json_bytes(self.controls)) != self.controls_sha
                or sha256_bytes(canonical_json_bytes([self.source, self.parent_frozen, self.sdk, self.prior]))
                   != self.authority_sha):
            raise ValueError("Checkpoint issuer controls changed during use")
        products._fresh_ci_observation_values(self.observation, self.producer, token)
        if self.previous is not None:
            self.previous.check(token=token)
            self.previous.inherit(spec, self.prior)


def _checkpoint_originals(controls, prior, base, source, observation, token):
    """Keep qualified pins; resolve new originals at their own reviewed source."""
    import product_reuse as products
    from sdk_campaign_original_locator import fresh_sdk_worker_route, retained_core_origin
    from products.inventory import require_integer
    available = _records(controls["runtime-state/reuse-wave-request.json"]["availableObjects"], "Checkpoint available")
    inherited = _records(base["expectedResult"]["phases"], "Checkpoint native base")
    selected = {instance: row for instance, row in available.items()
                if instance.product == "sdk" and instance not in inherited}
    old = prior["extension"]
    phases = _records(old["spec"]["completedPhases"], "Checkpoint previous phases")
    originals = _records(old["spec"]["originals"], "Checkpoint previous originals")
    result, pending = {}, []
    for instance, phase in sorted(selected.items()):
        receipts = [row for row in controls.values() if type(row) is dict and _identity(row) == instance
                    and sha256_bytes(canonical_json_bytes(row)) == phase["receiptSha256"]]
        if not receipts:
            raise ValueError("Checkpoint phase lacks its exact authenticated receipt")
        receipt = validate_phase_receipt(receipts[0])
        previous = phases.get(instance)
        if previous is not None and previous["buildKey"] == phase["buildKey"]:
            if (any(previous[field] != phase[field] for field in OBJECT)
                    or old["proof"]["controls"][previous["receiptPath"]] != receipt):
                raise ValueError("Checkpoint changes a native-qualified original tuple")
            result[instance] = originals[instance]
        else:
            producer, current = receipt["producer"], source["producer"]
            if (any(producer[key] != current[key] for key in ("repository", "workflowPath", "event", "pullRequest"))
                    or producer["runId"] > current["runId"]):
                raise ValueError("New checkpoint original changes its source scope or chronology")
            if producer["runId"] == current["runId"]:
                products._same_run_state_consumer({"producer": current}, producer)
            pending.append((instance, phase, receipt))
    artifacts_by_run = {}
    for instance, phase, receipt in pending:
        producer = receipt["producer"]
        current = producer == source["producer"]
        job, name = fresh_sdk_worker_route(instance, receipt)
        child = next((row for row in CHECKPOINT_ROUTES.values()
                      if row.child and instance in SDK_FAMILY_INSTANCES[row.family]), None)
        path = child.workflow_path if child is not None else ".github/workflows/product-validation.yml"
        retained = None
        if not current:
            if instance.component == "sdk-ios" and instance.phase == "validation":
                from sdk_apple_upload_locator import retained_validation_origin
                retained = retained_validation_origin(instance.target, phase["buildKey"], source["producer"])
            else:
                retained = retained_core_origin(instance.phase, phase["buildKey"], source["producer"],
                    target=instance.target, component=instance.component)
            if retained is not None and retained["producer"] != producer:
                retained = None  # A same-key locator for another producer cannot replace this receipt.
        if retained is not None:
            if (any(retained[key] != phase[field] for key, field in (
                    ("receipt_sha256", "receiptSha256"), ("object_sha256", "objectSha256")) if key in retained)
                    or (retained.get("workflow_path", path), retained.get("job_name", job)) != (path, job)):
                raise ValueError("Checkpoint retained original changes its reviewed tuple or registered route")
            workflow_sha = retained["workflow_sha"]
        else:
            workflow_sha = (source["workflowSha"] if current else products._runtime_prior_workflow_sha(
                products._original_ci_run(producer, token), source["workflowSha"]))
        if workflow_sha is None:
            raise ValueError("New checkpoint original lacks its reviewed original workflow")
        observed = products._observe_ci_producer_jobs({"original": receipt["producer"]},
            jobs_by_phase={"original": job}, build_keys_by_phase={"original": receipt["buildKey"]},
            trusted_workflows_by_phase={"original": {"path": path, "sha": workflow_sha}},
            token=token, **({"_fresh_observation": observation} if current else {}))[0]
        jobs = products._matching_ci_jobs(observed["jobs"], job, expected_build_key=receipt["buildKey"])
        if retained is not None:
            if jobs[0]["id"] != retained["job_id"]:
                raise ValueError("Checkpoint retained original changes its reviewed successful job")
            result[instance] = {**{key: phase[key] for key in IDENTITY},
                "artifactId": require_integer(retained["artifact_id"], "Reviewed original upload", 1),
                "artifactSha256": require_sha256(retained["artifact_sha256"], "Reviewed original upload digest"),
                "jobId": jobs[0]["id"], "workflowSha": workflow_sha}
            continue  # observe_original still checks this exact upload before any new object is opened.
        run = producer["repository"], producer["runId"]
        if run not in artifacts_by_run:
            artifacts_by_run[run] = products.paginated_items(
                f"https://api.github.com/repos/{run[0]}/actions/runs/{run[1]}/artifacts", "artifacts", token)
        matches = [row for row in artifacts_by_run[run] if type(row) is dict and row.get("name") == name
                   and row.get("expired") is False]
        if len(matches) != 1:
            raise ValueError("Checkpoint original upload is missing or ambiguous")
        record = matches[0]
        identity = require_integer(record.get("id"), "Checkpoint original upload", 1)
        digest = require_sha256(record.get("digest"), "Checkpoint original upload digest")
        # Discovery selects untrusted pins. observe_original performs the one full
        # upload/name/run/size/window check before issue_extension opens any body.
        result[instance] = {**{key: phase[key] for key in IDENTITY}, "artifactId": identity,
            "artifactSha256": digest, "jobId": jobs[0]["id"], "workflowSha": workflow_sha}
    return [result[instance] for instance in sorted(result)]


def issue_checkpoint(policy, source, control_selector, work, *, root, revision, frozen, token, previous=None):
    """Prepare one flat completion envelope for the existing protected signer.

    This core operation does not sign, upload or provision its caller-owned policy.
    It authenticates the whole small controls and one bootstrap native proof, then
    uses the existing issuer to fully verify only previously unqualified objects.
    """
    import time
    from contextlib import ExitStack
    import product_reuse as products
    import reuse_qualification as native
    from products.inventory import read_regular_file_bytes, write_canonical_json
    from sdk_handoff import _ensure_observed_sdk_commit
    started = time.perf_counter()
    policy, source, control_selector = (load_canonical_json_bytes(canonical_json_bytes(value))
                                        for value in (policy, source, control_selector))
    previous = (load_canonical_json_bytes(canonical_json_bytes(previous)) if previous is not None else
        {"kind": "existing-sdk-completion", "native": policy["bootstrap"],
         "subjectSha256": policy["bootstrapProofSha256"]})
    checkpoint_selection(policy, previous)
    identity = checkpoint_archive_identity(policy, source, signer_commit=revision,
        source_commit=source["producer"]["commit"], run_id=source["producer"]["runId"],
        run_attempt=source["producer"]["runAttempt"])
    work = Path(work).resolve()
    work.mkdir(exist_ok=False)
    with ExitStack() as lifetime, products._fresh_ci_observation(source["producer"], token) as observation, products._ci_observation_batch(
            tuple(str(source["producer"][key]) for key in ("runId", "runAttempt")), share_nested=True):
        collected = fetch_collector_controls(source, control_selector, work / "controls",
            producer=source["producer"], job_name=source["jobName"], workflow_sha=policy["collectorWorkflowSha"],
            token=token, _fresh_observation=observation)
        _ensure_observed_sdk_commit(root, source["producer"], token)
        plan_path = work / "source-plan.json"
        plan_path.write_bytes(collected["controls"][SOURCE_PLAN].encode("utf-8"))
        products._validate_plan(plan_path, root, expected_revision=source["producer"]["commit"])
        parent_frozen = native._sdk_parent_frozen_spec(root, policy["bootstrap"], frozen, token)
        predecessor = None
        if previous["kind"] == "sdk-checkpoint":
            predecessor = lifetime.enter_context(checkpoint_consumer(policy, previous, work / "previous",
                root=root, consumer={"kind": "ci", "producer": source["producer"]},
                job="sdk-checkpoint-" + str(_COLLECTED_WAVES[source["jobName"]]), token=token,
                _next_source=source, _observation=observation))
            prior = predecessor.validate(root=root, revision=None, frozen=parent_frozen,
                consumer_revision=source["inventoryCommit"], token=token)
        else:
            prior = native._fetch_completed_sdk(work / "previous", policy["bootstrap"], root=root, revision=None,
                frozen=parent_frozen, token=token, consumer_revision=source["inventoryCommit"])
        old = prior.get("extension")
        if (old is None or old["spec"]["parent"] != policy["parent"]
                or sha256_bytes(canonical_json_bytes(prior["proof"])) != policy["parentProofSha256"]
                or predecessor is None and sha256_bytes(canonical_json_bytes(old["proof"])) != policy["bootstrapProofSha256"]):
            raise ValueError("Checkpoint bootstrap differs from its approved native subjects")
        # The validated flat bootstrap already carries its exact authenticated
        # schema-one parent. Fetching/authenticating that parent again adds no gate.
        sdk = {key: value for key, value in prior.items() if key != "extension"}
        originals = _checkpoint_originals(collected["controls"], prior, _base(parent_frozen, sdk),
                                          source, observation, token)
        recipe_policy = {"parent": policy["parent"], "parentProofSha256": policy["parentProofSha256"],
            "contractControls": old["spec"]["contractControls"], "contractFiles": old["spec"]["contractFiles"]}
        if predecessor is None:
            recipe_policy.update(reuseCompletion=policy["bootstrap"], reuseCompletionProofSha256=policy["bootstrapProofSha256"])
        recipe, controls, preparation = prepare_collected_extension(recipe_policy, source, collected["references"],
            collected["controls"], originals, root=root, frozen=parent_frozen, parent_sdk=sdk, previous_sdk=prior,
            _checkpoint=predecessor)
        if (preparation["newSdkObjectsRequiringQualification"] == 0
                and preparation["selectedSdkPhases"] == len(old["spec"]["completedPhases"])):
            return {"reusedCheckpoint": previous["native"], "reusedCheckpointOutput": previous,
                "reusedCheckpointSubjectSha256": previous["subjectSha256"],
                "checkpointControlUploadBytes": collected["controlArchive"]["bytes"],
                "checkpointPreparation": preparation, "verifiedObjectBytes": 0,
                "originalMemberRangeBytes": 0, "productPhasesExecuted": 0,
                "checkpointSeconds": str(time.perf_counter() - started), "nativeAttestationIssued": False}
        inputs = _CheckpointIssueInputs(recipe, revision, controls, collected["stateLocator"],
            parent_frozen, sdk, prior, observation, token, _CHECKPOINT_INPUTS, previous=predecessor)
        inner = work / "inner"
        inner.mkdir()
        report = issue_extension(recipe, inner, root=root, revision=revision, frozen=frozen,
                                 token=token, _checkpoint=inputs)
        inputs.check(recipe, revision, token)
        completion = load_canonical_json_bytes(read_regular_file_bytes(inner / "completion.json", max_bytes=LIMIT,
                                                                      reject_symlink_parents=True))
        envelope = {"schemaVersion": 1, "kind": "completed-sdk-checkpoint", "issuerCommit": revision,
            "ownerPolicySha256": sha256_bytes(canonical_json_bytes(policy)), "recipe": recipe,
            "completion": completion, "sourceCheckpoint": {"source": source, "controlArtifact": control_selector},
            "precedingCheckpoint": {"native": previous["native"], "subjectSha256": previous["subjectSha256"]}}
        if len(canonical_json_bytes(envelope)) > LIMIT:
            raise ValueError("Checkpoint completion exceeds its bounded native subject")
        write_canonical_json(work / "completion.json", envelope)
    report.update(checkpointControlUploadBytes=collected["controlArchive"]["bytes"],
        checkpointPreparation=preparation, checkpointArtifactName=identity["artifactName"],
        checkpointSeconds=str(time.perf_counter() - started), nativeAttestationIssued=False)
    return report


def issue_extension(spec, work, *, root, revision, frozen, token, _checkpoint=None):
    """Authenticate resumed admission, then hash only each consumed object."""
    import stat
    import time
    import zipfile
    import product_reuse as products
    import reuse_qualification as native
    from products.inventory import write_canonical_json
    from products.restore import verify_object, object_relative_path
    from runtime_reference_archive import open_reference_archive, copy_reference_member
    started = time.perf_counter()
    originals = _spec(spec)
    if _checkpoint is not None:
        if type(_checkpoint) is not _CheckpointIssueInputs:
            raise ValueError("Checkpoint issuance requires private authenticated inputs")
        _checkpoint.check(spec, revision, token)
    # Qualify the pinned successful producer's bytes, not the issuer's newer
    # product source. validate_extension still gates each consumer's inputs.
    inventory_revision = _inventory_revision(spec, root, token=token)
    if _checkpoint is None:
        parent_frozen = native._sdk_parent_frozen_spec(root, spec["parent"], frozen, token)
        sdk = native._fetch_completed_sdk(work / "parent", spec["parent"],
            root=root, revision=inventory_revision, frozen=parent_frozen, token=token)
    else:
        parent_frozen, sdk = _checkpoint.parent_frozen, _checkpoint.sdk
    if sha256_bytes(canonical_json_bytes(sdk["proof"])) != spec["parentProofSha256"]:
        raise ValueError("Incremental issuer parent differs from its fixed subject")

    def download(source, path, *, contract=False):
        artifact, observed, locator = observe_source(source, token, contract=contract)
        products._download_contract_ci_upload(source["artifactId"], source["artifactSha256"], artifact["name"],
            source["producer"], observed[0]["run"], token, destination=path, max_bytes=source["artifactBytes"])
        return locator

    def directory(archive):
        rows = archive.infolist()
        if len(rows) > 16384 or len({row.filename for row in rows}) != len(rows):
            raise ValueError("Incremental original ZIP directory is ambiguous or oversized")

    def read(archive, path, limit=LIMIT):
        entry = archive.getinfo(path)
        if (entry.is_dir() or entry.flag_bits & 1 or not 0 <= entry.file_size <= limit
                or stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG)
                or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
            raise ValueError("Incremental original member is not bounded regular evidence")
        return archive.read(entry)

    from contextlib import nullcontext
    source_range_bytes = 0
    if _checkpoint is not None:
        controls, source = _checkpoint.controls, _checkpoint.source
        source_archive = nullcontext(None)
    elif collected_validation(spec):
        from sdk_handoff import _ensure_observed_sdk_commit
        from products.inventory import read_regular_file_bytes
        artifact, _, source = observe_source(spec["source"], token)
        producer = spec["source"]["producer"]
        _ensure_observed_sdk_commit(root, producer, token)
        plan_path = work / "source-plan.json"
        raw_plan = spec["sourcePlan"].encode("utf-8")
        plan_path.write_bytes(raw_plan)
        plan = products._validate_plan(plan_path, root, expected_revision=producer["commit"])
        destination = work / "source-controls"
        # Reviewed issuer Git independently pins this reference control and all
        # requested members. No whole-archive hash or body-admission claim here.
        base = {key: spec["source"][key] for key in
                ("artifactId", "artifactSha256", "referenceControlSha256")}
        base.update(stateWave=0, sdkStateWave=_COLLECTED_WAVES[spec["source"]["jobName"]],
                    runAttempt=producer["runAttempt"])
        receipt_objects = _receipt_objects(spec)
        # Reviewed Git may carry the exact small receipt, never body authority.
        # Bind its containing object to the authenticated collector inventory;
        # fresh original/job/upload and full object gates below remain mandatory.
        hints = {row["relativePath"] + "/phase-receipt.json": row["receipt"]
                 for row in spec.get("receiptObjects", []) if "receipt" in row}
        declared = {row["relativePath"]: row for path, (row, _) in receipt_objects.items() if path in hints}
        wanted = {row["relativePath"]: row for row in spec["controls"]
                  if row["relativePath"] not in receipt_objects}
        wanted.update((row["relativePath"], row) for path, (row, _) in receipt_objects.items() if path not in hints)
        transport = products._capture_runtime_reference_members(plan, raw_plan, producer, base, destination,
            trusted_workflow_sha=spec["source"]["workflowSha"], token=token,
            wanted=wanted, **({"inventory_only": declared} if declared else {}))
        if transport["artifact"] != artifact:
            raise ValueError("Collector control intake changes its observed source upload")
        controls = {}
        for row in spec["controls"]:
            embedded = receipt_objects.get(row["relativePath"])
            if row["relativePath"] in hints:
                raw = canonical_json_bytes(validate_phase_receipt(hints[row["relativePath"]]))
            elif embedded is not None:
                obj, phase = embedded
                verified = verify_object(destination / obj["relativePath"], build_key=phase["buildKey"],
                    receipt_sha256=phase["receiptSha256"], object_sha256=phase["objectSha256"])
                raw = verified["receiptBytes"]
            else:
                raw = read_regular_file_bytes(destination / row["relativePath"], max_bytes=LIMIT, reject_symlink_parents=True)
            controls[row["relativePath"]] = (raw.decode("utf-8") if row["relativePath"] == SOURCE_PLAN
                                             else load_canonical_json_bytes(raw))
        pending = [transport]
        while pending:
            current = pending.pop()
            source_range_bytes += current.get("rangeBytes", 0)
            pending.extend(current.get("originalReferenceSources", []))
            if current.get("referenceBase") is not None:
                pending.append(current["referenceBase"])
        source_archive = nullcontext(None)
    else:
        path = work / "completed-state.zip"
        source = download(spec["source"], path)
        source_archive = zipfile.ZipFile(path)
    with source_archive as archive:
        if archive is not None:
            directory(archive)
            from runtime_reference_transport import validate_original_references
            references = validate_original_references(load_canonical_json_bytes(read(archive, "runtime-original-references.json")))
            inventory = {row["relativePath"]: row for row in references["inventory"]}
            aliases = {row["relativePath"]: row for row in references["references"]}
            sources = {row["relativePath"]: row for row in references["sources"]}

            def retained(name):
                row = inventory[name]
                alias = aliases.get(name, {})
                if alias.get("source") is not None:
                    source = sources[alias["source"]]
                    receipt = source["receipt"]
                    original = originals.get(_identity(receipt))
                    if (not original_worker_member(spec) or _identity(receipt) != IOS_PACKAGE
                            or source["kind"] != "sdk-package"
                            or alias["sourcePath"] != "shard/phase-receipt.json" or original is None
                            or any(source[field] != original[field] for field in ("artifactId", "artifactSha256"))):
                        raise ValueError("Incremental external control is outside its approved package receipt")
                    # This exact receipt is inside the whole-authenticated successful
                    # resume. Its native Git pin and fresh original provenance remain mandatory.
                    raw = canonical_json_bytes(receipt)
                else:
                    raw = read(archive, alias.get("sourcePath", name))
                if len(raw) != row["bytes"] or sha256_bytes(raw) != row["sha256"]:
                    raise ValueError("Incremental retained control differs from its exact archive member")
                return raw

            controls = {row["relativePath"]: load_canonical_json_bytes(retained(row["relativePath"]))
                        for row in spec["controls"]}
        request, phases, receipts = validate_controls(spec, controls, _base(parent_frozen, sdk))
        validate_current(request, phases, receipts, root=root, revision=inventory_revision,
                         original_revision=inventory_revision)
        qualified = {}
        if "reuseCompletion" in spec or _checkpoint is not None and _checkpoint.previous is not None:
            if _checkpoint is None:
                previous_frozen = native._sdk_parent_frozen_spec(root, spec["reuseCompletion"], frozen, token)
                prior = native._fetch_completed_sdk(work / "previous", spec["reuseCompletion"],
                    root=root, revision=None, frozen=previous_frozen, token=token,
                    consumer_revision=inventory_revision)
            else:
                prior = _checkpoint.prior
            # Both subjects bind their original product source; only exact
            # matching keys/receipts/objects inherit body qualification.
            qualified = _qualified_members(spec, prior, phases, receipts, root=root,
                _checkpoint=_checkpoint.previous if _checkpoint is not None else None)
        available = _records(request["availableObjects"], "Incremental original objects")
        observation_started = time.perf_counter()
        observations = _observe_incremental_originals(originals, receipts, qualified, token,
            **({"_checkpoint": _checkpoint} if _checkpoint is not None else {}))
        observation_seconds = time.perf_counter() - observation_started
        members, locators, transferred, reused_bytes = [], [], 0, 0
        for number, phase in enumerate(phases):
            artifact, _, locator = observations[number]
            locators.append(locator)
            if _identity(phase) in qualified:
                member, previous_locator = qualified[_identity(phase)]
                if locator != previous_locator:
                    raise ValueError("Reused native object changes its freshly observed original locator")
                members.append(member)
                reused_bytes += member["bytes"]
                continue
            obj = work / f"object-{number}.zip"
            if original_worker_member(spec):
                name = "shard/" + object_relative_path(phase["buildKey"], phase["receiptSha256"])
                bounds = products._worker_upload_reference_limits(_identity(phase))
                with open_reference_archive(artifact, token, **bounds) as (original, stream):
                    member = {"relativePath": name, "bytes": original.getinfo(name).file_size,
                              "sha256": phase["objectSha256"]}
                    if not 0 < member["bytes"] <= _object_limit(_identity(phase)):
                        raise ValueError("Incremental original member exceeds its fixed bound")
                    copy_reference_member(original, name, obj, member)
                    transferred += stream.transferred
            else:
                name = spec["stateRoot"] + "/" + available[_identity(phase)]["objectPath"]
                raw = read(archive, name)
                member = {"relativePath": name, "bytes": len(raw), "sha256": sha256_bytes(raw)}
                obj.write_bytes(raw)
            verified = verify_object(obj, build_key=phase["buildKey"], receipt_sha256=phase["receiptSha256"],
                                     object_sha256=phase["objectSha256"])
            if verified["receiptBytes"] != canonical_json_bytes(receipts[number]):
                raise ValueError("Incremental SDK object changes its admitted receipt")
            members.append(member)
        embedded_objects = {_identity(phase): row for row, phase in _receipt_objects(spec).values()}
        for phase, member in zip(phases, members, strict=True):
            embedded = embedded_objects.get(_identity(phase))
            if embedded is not None and member["bytes"] != embedded["bytes"]:
                raise ValueError("Incremental original size differs from its collected declaration")
    contract_path = work / "contract-controls.zip"
    contract_source = download(spec["contractControls"], contract_path, contract=True)
    with zipfile.ZipFile(contract_path) as archive:
        directory(archive)
        if set(archive.namelist()) != {row["relativePath"] for row in spec["contractFiles"]}:
            raise ValueError("Incremental signed Contract upload changes its exact control inventory")
        files = {name: read(archive, name).decode("utf-8") for name in archive.namelist()}
    _contract_files(spec, files, sdk)
    proof = {"schemaVersion": spec["schemaVersion"], "kind": "completed-sdk-reuse", "issuerCommit": revision,
        "specSha256": sha256_bytes(canonical_json_bytes(spec)), "parentProof": sdk["proof"],
        "source": source, "controls": controls, "originals": locators, "members": members,
        "contractSource": contract_source, "contractFiles": files}
    if _checkpoint is not None:
        _checkpoint.check(spec, revision, token)
    write_canonical_json(work / "completion.json", proof)
    report = {"downloadedOriginalBytes": spec["contractControls"]["artifactBytes"] + (
        0 if collected_validation(spec) else spec["source"]["artifactBytes"]),
        "sourceControlRangeBytes": source_range_bytes, "originalMemberRangeBytes": transferred,
        "nativePinnedOriginalObservations": len(qualified),
        "discoveredOriginalObservations": len(phases) - len(qualified),
        "originalObservationSeconds": str(observation_seconds),
        "verifiedObjectBytes": sum(row["bytes"] for row in members) - reused_bytes,
        "reusedObjectBytes": reused_bytes, "completedSdkPhases": len(phases) + 1,
        "seconds": str(time.perf_counter() - started), "productPhasesExecuted": 0}
    import json
    print(json.dumps(report), flush=True)
    return report


def prepare_collected_extension(policy, source, references, controls, originals, *,
                                root, frozen, parent_sdk, previous_sdk, _checkpoint=None):
    """Derive selected/context/receipt inventories without fixed phase counts.

    Policy and original locators are explicit review inputs, never inferred trust.
    No source discovery, artifact download, proof signing or policy update occurs.
    """
    from products.restore import object_relative_path
    from runtime_reference_transport import validate_references
    require_exact_keys(policy, {"parent", "parentProofSha256", "contractControls", "contractFiles"}
        | ({"reuseCompletion", "reuseCompletionProofSha256"} if _checkpoint is None else set()),
        "Recipe preparation policy")
    if (parent_sdk["spec"].get("schemaVersion") != 1
            or sha256_bytes(canonical_json_bytes(parent_sdk["proof"])) != policy["parentProofSha256"]):
        raise ValueError("Recipe preparation changes its exact schema-one parent")
    wave = _COLLECTED_WAVES.get(source.get("jobName"))
    if wave is None:
        raise ValueError("Recipe preparation requires a registered collector")
    references = validate_references(references, 0, sdk_state_wave=wave)
    if sha256_bytes(canonical_json_bytes(references)) != source.get("referenceControlSha256"):
        raise ValueError("Recipe preparation changes its pinned reference control")
    if type(controls) is not dict or not 4 <= len(controls) <= 128:
        raise ValueError("Recipe preparation requires bounded held controls")
    for path, value in controls.items():
        require_relative_path(path, "Held collector control")
        raw = value.encode("utf-8") if path == SOURCE_PLAN and type(value) is str else canonical_json_bytes(value)
        if len(raw) > LIMIT:
            raise ValueError("Held collector control exceeds its byte bound")
    base = _base(frozen, parent_sdk)
    inherited = _records(base["expectedResult"]["phases"], "Native base phases")
    prefix = "runtime-state/"
    available = _records(controls[prefix + "reuse-wave-request.json"]["availableObjects"],
                                   "Collected available phases")
    selected = {instance: row for instance, row in available.items()
                if instance.product == "sdk" and instance not in inherited}
    inventory = {row["relativePath"]: row for row in references["inventory"]}
    retained = {path: controls[path] for path in (SOURCE_PLAN,
        *(prefix + name for name in ("producer.json", "reuse-wave-request.json", "reuse-wave-result.json")))}
    phases, objects = [], []
    for instance, phase in sorted(selected.items()):
        matches = [(path, value) for path, value in controls.items()
                   if type(value) is dict and _identity(value) == instance
                   and sha256_bytes(canonical_json_bytes(value)) == phase["receiptSha256"]]
        if not matches:
            raise ValueError("Collected phase lacks its exact held receipt: " + str(instance))
        direct = [(path, receipt) for path, receipt in matches if path in inventory
                  and inventory[path]["sha256"] == phase["receiptSha256"]]
        if direct:
            path, receipt = min(direct, key=lambda item: item[0])
        else:
            receipt = matches[0][1]
            obj = prefix + "original-objects/" + object_relative_path(phase["buildKey"], phase["receiptSha256"])
            if obj not in inventory or inventory[obj]["sha256"] != phase["objectSha256"]:
                raise ValueError("Collected receipt lacks its exact inventoried object")
            path = obj + "/phase-receipt.json"
            objects.append({**inventory[obj], "receipt": receipt})
        retained[path] = receipt
        phases.append({**{key: phase[key] for key in IDENTITY + OBJECT}, "receiptPath": path})
    pins = []
    for path, value in sorted(retained.items()):
        raw = value.encode("utf-8") if path == SOURCE_PLAN else canonical_json_bytes(value)
        record = {"relativePath": path, "bytes": len(raw), "sha256": sha256_bytes(raw)}
        if path not in {row["relativePath"] + "/phase-receipt.json" for row in objects} and inventory.get(path) != record:
            raise ValueError("Held control differs from the exact collector inventory: " + path)
        pins.append(record)
    spec = {**policy, "schemaVersion": 4, "source": source, "stateRoot": "runtime-state",
        "sourcePlan": retained[SOURCE_PLAN], "controls": pins, "completedPhases": phases,
        "sourcePredecessors": [{key: row[key] for key in IDENTITY + OBJECT}
                               for instance, row in sorted(available.items()) if instance not in selected],
        "originals": sorted(originals, key=_identity), "receiptObjects": objects}
    _spec(spec)
    request, admitted, receipts = validate_controls(spec, retained, base)
    revision = _inventory_revision(spec, root)
    validate_current(request, admitted, receipts, root=root, revision=revision, original_revision=revision)
    qualified = _qualified_members(spec, previous_sdk, admitted, receipts, root=root, _checkpoint=_checkpoint)
    # Detach review outputs from caller-owned dictionaries; no live capability is returned.
    spec, retained = (load_canonical_json_bytes(canonical_json_bytes(value)) for value in (spec, retained))
    report = {"preparationOnly": True, "qualificationIssued": False,
        "retainedPhases": len(available), "selectedSdkPhases": len(selected),
        "sourceContextPhases": len(spec["sourcePredecessors"]), "inheritedSdkObjects": len(qualified),
        "newSdkObjectsRequiringQualification": len(selected) - len(qualified),
        "recipeSha256": sha256_bytes(canonical_json_bytes(spec)),
        "controlsSha256": sha256_bytes(canonical_json_bytes(retained)),
        "networkCalls": 0, "productBodiesRead": 0, "productExecutions": 0}
    return spec, retained, report


COLLECTOR_CONTROL_NAME = "collector-controls.json"


def validate_checkpoint_owner(policy):
    """Shape of independently provisioned policy, never read from a proof."""
    import reuse_qualification as native
    require_exact_keys(policy, {"schemaVersion", "kind", "issuerCommit", "collectorWorkflowSha",
        "parent", "parentProofSha256", "bootstrap", "bootstrapProofSha256", "collectors"},
        "Checkpoint owner policy")
    if (type(policy["schemaVersion"]) is not int or policy["schemaVersion"] != 1
            or policy["kind"] != "sdk-checkpoint-owner"):
        raise ValueError("Unsupported checkpoint owner policy")
    for field in ("issuerCommit", "collectorWorkflowSha"):
        native._commit(policy[field])
    from products.inventory import require_integer
    for field in ("parent", "bootstrap"):
        pins = native._native_pin_arguments(policy[field])
        for name in ("signer_commit", "source_commit"):
            native._commit(pins[name])
        for name in ("artifact_id", "run_id", "run_attempt"):
            require_integer(pins[name], "Checkpoint " + field + " " + name, 1)
        require_sha256(pins["artifact_sha256"], "Checkpoint " + field + " upload")
        require_sha256(policy[field + "ProofSha256"], "Checkpoint " + field + " subject")
    collectors = policy["collectors"]
    if (type(collectors) is not list or not collectors or len(collectors) > len(_COLLECTED_WAVES)
            or any(type(job) is not str or job not in _COLLECTED_WAVES for job in collectors)
            or collectors != sorted(set(collectors))):
        raise ValueError("Checkpoint owner must register exact unique collector roles")
    return policy


def checkpoint_archive_identity(policy, source, *, signer_commit, source_commit, run_id, run_attempt):
    """A distinct CI job/upload role; legacy portable issuer names stay fixed."""
    import reuse_qualification as native
    validate_checkpoint_owner(policy)
    _collector_control_source(source)
    producer = source["producer"]
    if (source["jobName"] not in policy["collectors"]
            or source["workflowSha"] != policy["collectorWorkflowSha"]
            or signer_commit != policy["issuerCommit"]
            or (source_commit, run_id, run_attempt) !=
               (producer["commit"], producer["runId"], producer["runAttempt"])):
        raise ValueError("Checkpoint selectors differ from the approved issuer/collector source")
    wave = _COLLECTED_WAVES[source["jobName"]]
    route = CHECKPOINT_ROUTES.get(source["jobName"])
    workflow = route.workflow_path if route is not None else ".github/workflows/product-validation.yml"
    return {"producer": producer,
        "jobName": source["jobName"].rsplit(" / ", 1)[0] + f" / sdk-checkpoint-{wave} / completed-sdk-checkpoint",
        "artifactName": f"sdk-completed-checkpoint-{wave}-{run_id}-{run_attempt}-state-{source['artifactId']}",
        "collectorWorkflow": f"{native.REPOSITORY}/{workflow}@{source['workflowSha']}",
        "collectorWorkflowSha": source["workflowSha"]}


def fetch_checkpoint_envelope(policy, source, selector, work, *, token):
    """Native envelope custody only; this never constructs CompletedFrozenReuse.

    Policy is independently supplied by the protected caller. The selector and
    source are untrusted output locators. Current semantic admission, registered
    dependency ordering and actual consumer binding remain separate gates.
    """
    import reuse_qualification as native
    import product_reuse as products
    # Detach caller dictionaries before concurrent official reads or verification.
    policy, source, selector = (load_canonical_json_bytes(canonical_json_bytes(value))
                                for value in (policy, source, selector))
    arguments = native._native_pin_arguments(selector)
    identity = checkpoint_archive_identity(policy, source, **{name: arguments[name]
        for name in ("signer_commit", "source_commit", "run_id", "run_attempt")})
    with products._fresh_ci_observation(source["producer"], token) as observation:
        return _fetch_checkpoint_envelope(policy, source, arguments, identity, work, token, observation)


def _fetch_checkpoint_envelope(policy, source, arguments, identity, work, token, observation):
    import reuse_qualification as native
    import product_reuse as products
    from datetime import datetime
    from products.inventory import require_integer
    report, captured = native._fetch_qualification_archive(work, **arguments, token=token,
        _completed_sdk=True, _checkpoint=(policy, source), _fresh_observation=observation)
    # No recipe, policy or predecessor identity is accepted from JSON until the
    # entire artifact and this exact subject pass the existing native verifier.
    native._authenticate_native_subject(captured["completion.json"], captured["bundle.jsonl"],
        "completion.json", signer_commit=policy["issuerCommit"], source_commit=source["producer"]["commit"])
    envelope = require_exact_keys(load_canonical_json_bytes(captured["completion.json"]),
        {"schemaVersion", "kind", "issuerCommit", "ownerPolicySha256", "recipe", "completion",
         "sourceCheckpoint", "precedingCheckpoint"}, "Native SDK checkpoint envelope")
    if (type(envelope["schemaVersion"]) is not int or envelope["schemaVersion"] != 1
            or envelope["kind"] != "completed-sdk-checkpoint"
            or envelope["issuerCommit"] != policy["issuerCommit"]
            or envelope["ownerPolicySha256"] != sha256_bytes(canonical_json_bytes(policy))):
        raise ValueError("Native checkpoint differs from its independent owner policy")
    preceding = require_exact_keys(envelope["precedingCheckpoint"], {"native", "subjectSha256"},
                                   "Preceding native checkpoint")
    bootstrap = preceding == {"native": policy["bootstrap"], "subjectSha256": policy["bootstrapProofSha256"]}
    if not bootstrap:
        # Signed custody history, not a recursive instruction to fetch old proofs.
        # Issuance admits this exact predecessor through its live private witness.
        pins = native._native_pin_arguments(preceding["native"])
        require_sha256(preceding["subjectSha256"], "Preceding native checkpoint subject")
        for name in ("artifact_id", "run_id", "run_attempt"):
            require_integer(pins[name], "Preceding native checkpoint " + name, 1)
        require_sha256(pins["artifact_sha256"], "Preceding native checkpoint digest")
        if (any(pins[name] != arguments[name] for name in
                ("signer_commit", "source_commit", "run_id", "run_attempt"))
                or pins["artifact_id"] in (arguments["artifact_id"], source["artifactId"])):
            raise ValueError("Native checkpoint changes its approved preceding campaign")
    source_checkpoint = require_exact_keys(envelope["sourceCheckpoint"], {"source", "controlArtifact"},
                                           "Native collector checkpoint")
    control = require_exact_keys(source_checkpoint["controlArtifact"], {"artifactId", "artifactSha256"},
                                 "Native collector control upload")
    require_integer(control["artifactId"], "Native collector control ID", 1)
    require_sha256(control["artifactSha256"], "Native collector control digest")
    spec, proof = envelope["recipe"], envelope["completion"]
    if (type(spec) is not dict or type(proof) is not dict
            or spec.get("schemaVersion") != 4 or spec.get("source") != source
            or source_checkpoint["source"] != source
            or spec.get("parent") != policy["parent"]
            or spec.get("parentProofSha256") != policy["parentProofSha256"]
            or bootstrap and (spec.get("reuseCompletion") != preceding["native"]
                              or spec.get("reuseCompletionProofSha256") != preceding["subjectSha256"])
            or not bootstrap and ("reuseCompletion" in spec or "reuseCompletionProofSha256" in spec)
            or proof.get("schemaVersion") != 4 or type(proof.get("schemaVersion")) is not int
            or proof.get("kind") != "completed-sdk-reuse"
            or proof.get("issuerCommit") != policy["issuerCommit"]
            or proof.get("specSha256") != sha256_bytes(canonical_json_bytes(spec))):
        raise ValueError("Native checkpoint changes its complete recipe/proof/source join")
    _spec(spec)  # Preserve the existing strict earlier-run gate, without a bypass.
    state, observed, locator = observe_source(source, token, _fresh_observation=observation)
    artifact = products._contract_ci_upload_metadata(control["artifactId"], control["artifactSha256"],
        collector_control_artifact_name(source), source["producer"], observed[0]["run"], token)
    products._require_artifact_job_window(observed[0], source["jobName"], artifact)
    source_job = products._matching_ci_jobs(observed[0]["jobs"], source["jobName"])[0]
    def when(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    if (proof.get("source") != locator or artifact["id"] == state["id"]
            or artifact["size_in_bytes"] > 2 * LIMIT
            or when(artifact["created_at"]) < when(state["created_at"])
            or when(source_job["completed_at"]) > when(report["checkpointIssuerJob"]["started_at"])):
        raise ValueError("Native checkpoint source/control upload does not precede its issuer")
    # Timing supplements exact approved roles; it grants no needs-edge capability.
    return {"envelope": envelope, "subjectSha256": sha256_bytes(captured["completion.json"]),
        "issuer": identity, "transport": report, "sourceArtifact": state, "semanticAuthority": False}


def _checkpoint_workflow_control(raw):
    """Read bounded literal workflow jobs; this data grants no authority.

    Unsupported structural/scalar forms fail rather than approximating YAML.
    Block scalar content cannot contribute job or dependency fields.
    """
    import re
    if type(raw) is not bytes or len(raw) > 1024 * 1024:
        raise ValueError("Checkpoint workflow exceeds its fixed control bound")
    identifier = r"[A-Za-z_][A-Za-z0-9_-]*"
    roots, jobs, fields = set(), {}, None
    in_jobs, scalar_indent, section = False, None, None
    in_on, event, call_section, output = False, None, None, None
    events, call_fields, call_outputs = set(), set(), {}
    for line in raw.decode("utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if scalar_indent is not None and indent > scalar_indent:
            continue
        scalar_indent = None
        if line[indent:indent + 1] == "\t":
            raise ValueError("Checkpoint workflow cannot use structural tabs")
        value_match = re.match(r"(?:- )?[^:\s][^:]*:[ \t]*(.*)$", line[indent:])
        value = value_match[1] if value_match else None
        if value is not None:
            if value.startswith(("|", ">")):
                if not re.fullmatch(r"[|>](?:[+-][1-9]?|[1-9][+-]?)?(?:[ \t]+#.*)?[ \t]*", value):
                    raise ValueError("Unsupported checkpoint workflow block scalar")
                scalar_indent = indent + (2 if line[indent:].startswith("- ") else 0)
            elif value.startswith(("'", '"')):
                quoted = r"'(?:[^']|'')*'" if value[0] == "'" else r'"(?:[^"\\]|\\.)*"'
                if not re.fullmatch(quoted + r"(?:[ \t]+#.*)?[ \t]*", value):
                    raise ValueError("Checkpoint workflow multiline quoted scalars are unsupported")
            elif value.startswith(("!", "&", "*")):
                key = line[indent:].split(":", 1)[0]
                if (indent <= 2 or key in {"needs", "uses"}
                        or not re.fullmatch(r"[&*][A-Za-z_][A-Za-z0-9_-]*", value)):
                    raise ValueError("Checkpoint workflow structural tags or aliases are unsupported")
            elif value.startswith(("[", "{")):
                if value != "{}" and not re.fullmatch(r"\[[ \t]*(?:" + identifier +
                        r"(?:[ \t]*,[ \t]*" + identifier + r")*)?[ \t]*\]", value):
                    raise ValueError("Checkpoint workflow flow values must be literal single-line lists")
        if indent == 0:
            root = re.fullmatch(r"(" + identifier + r"):[ \t]*(.*)", line)
            if root is None or root[1] in roots:
                raise ValueError("Checkpoint workflow requires unique literal root keys")
            roots.add(root[1]); in_jobs = root[1] == "jobs"; in_on = root[1] == "on"; fields = None
            if (in_jobs or in_on) and root[2]:
                raise ValueError("Checkpoint requires literal jobs and event mappings")
        elif in_on and indent == 2:
            field = re.fullmatch(r"(" + identifier + r"):[ \t]*(.*)", line[2:])
            if field is None or field[1] in events:
                raise ValueError("Checkpoint workflow events require unique literal keys")
            event = field[1]; events.add(event)
            if event == "workflow_call" and field[2]:
                raise ValueError("Checkpoint reusable workflow requires a literal call mapping")
        elif in_on and event == "workflow_call" and indent == 4:
            field = re.fullmatch(r"(" + identifier + r"):[ \t]*(.*)", line[4:])
            if field is None or field[1] in call_fields:
                raise ValueError("Checkpoint workflow call fields must be unique")
            call_section = field[1]; call_fields.add(call_section)
            if call_section == "outputs" and field[2]:
                raise ValueError("Checkpoint reusable outputs require a literal mapping")
        elif in_on and event == "workflow_call" and call_section == "outputs" and indent == 6:
            field = re.fullmatch(r"(" + identifier + r"):[ \t]*", line[6:])
            if field is None or field[1] in call_outputs:
                raise ValueError("Checkpoint reusable outputs require unique literal names")
            output = call_outputs[field[1]] = {}
        elif in_on and event == "workflow_call" and call_section == "outputs" and indent == 8:
            field = re.fullmatch(r"(" + identifier + r"):[ \t]*(.*)", line[8:])
            if output is None or field is None or field[1] in output:
                raise ValueError("Checkpoint reusable output fields must be unique")
            output[field[1]] = field[2]
        elif in_on and event == "workflow_call" and call_section == "outputs" and indent < 8:
            raise ValueError("Checkpoint reusable output indentation is unsupported")
        elif in_jobs and indent == 2:
            job = re.fullmatch(r"(" + identifier + r"):[ \t]*", line[2:])
            if job is None or job[1] in jobs:
                raise ValueError("Checkpoint jobs require unique literal mapping keys")
            fields = jobs[job[1]] = {}
            section = None
        elif in_jobs and indent == 4:
            field = re.fullmatch(r"(" + identifier + r"):[ \t]*(.*)", line[4:])
            if fields is None or field is None or field[1] in fields:
                raise ValueError("Checkpoint job fields require unique literal keys")
            section = field[1]
            fields[section] = {} if section in {"with", "env", "outputs"} and not field[2] else field[2]
        elif in_jobs and indent == 6 and fields is not None and type(fields.get(section)) is dict:
            field = re.fullmatch(r"(" + identifier + r"):[ \t]*(.*)", line[6:])
            if field is None or field[1] in fields[section]:
                raise ValueError("Checkpoint job inputs/environment require unique literal keys")
            fields[section][field[1]] = field[2]
        elif in_jobs and (indent < 4 or fields is None):
            raise ValueError("Checkpoint workflow job indentation is unsupported")
    if "jobs" not in roots:
        raise ValueError("Checkpoint workflow has no literal jobs mapping")
    return jobs, call_outputs


def _checkpoint_workflow_jobs(raw):
    return _checkpoint_workflow_control(raw)[0]


def _checkpoint_needs(jobs, name):
    import re
    identifier = r"[A-Za-z_][A-Za-z0-9_-]*"
    value = jobs[name].get("needs", "")
    if type(value) is not str or not re.fullmatch(r"\[" + identifier + r"(?:, " + identifier + r")*\]", value):
        raise ValueError("Selected checkpoint edges require canonical literal needs arrays")
    result = value[1:-1].split(", ")
    if len(set(result)) != len(result) or name in result:
        raise ValueError("Checkpoint needs repeats a dependency or itself")
    return result


def _checkpoint_edges(jobs, collector, issuer, consumer, *, next_collector=None):
    if len({collector, issuer, consumer}) != 3 or any(
            name not in jobs for name in (collector, issuer, consumer)):
        raise ValueError("Checkpoint selected workflow jobs are missing or conflicting")
    preceding, following = _checkpoint_needs(jobs, issuer), _checkpoint_needs(jobs, consumer)
    if collector not in preceding or issuer not in following or consumer in preceding:
        raise ValueError("Checkpoint lacks its actual collector-to-issuer-to-consumer needs edges")
    expected = "codex-agent-labs/codex-agent/.github/workflows/reuse-qualification.yml@reuse-authority"
    if jobs[issuer].get("uses") != expected:
        raise ValueError("Checkpoint edge must invoke its existing protected native issuer")
    if next_collector is not None and (next_collector not in jobs or next_collector not in following
            or next_collector in {collector, issuer, consumer} or jobs[consumer].get("uses") != expected):
        raise ValueError("Next checkpoint must depend on its own collector and prior protected issuer")



def _checkpoint_workflow_edges(raw, collector, issuer, consumer, *, next_collector=None):
    _checkpoint_edges(_checkpoint_workflow_jobs(raw), collector, issuer, consumer, next_collector=next_collector)
    return sha256_bytes(raw)


def _checkpoint_core_workflow_edges(raw, child_raw, collector, issuer, *, consumer="sdk-core-binary"):
    jobs, child = _checkpoint_workflow_jobs(raw), _checkpoint_workflow_jobs(child_raw)
    caller = "sdk-core-binary-wave"
    if issuer == "sdk-checkpoint-9":
        _checkpoint_edges(jobs, collector, issuer, "sdk-checkpoint-10", next_collector="sdk-collect-10")
    elif (collector, issuer) != ("sdk-collect-10", "sdk-checkpoint-10"):
        raise ValueError("Core checkpoint is outside its registered signing or forwarding route")
    _checkpoint_edges(jobs, "sdk-collect-10", "sdk-checkpoint-10", caller)
    if (jobs[caller].get("uses") != "./.github/workflows/sdk-core-binary-validation.yml"
            or type(jobs[caller].get("with")) is not dict
            or jobs[caller]["with"].get("sdkCheckpoint") != "${{ needs.sdk-checkpoint-10.outputs.checkpoint }}"):
        raise ValueError("Core checkpoint changes its exact caller selector path")
    if consumer == "sdk-core-binary":
        if (child.get("sdk-core-binary", {}).get("name") != "sdk-core-binary-common"
            or child["sdk-core-binary"].get("needs") != "[sdk-core-binary-plan]"
            or "sdk-core-binary-plan" not in child
            or type(child["sdk-core-binary"].get("env")) is not dict
            or child["sdk-core-binary"]["env"].get("CODEX_AGENT_SDK_CHECKPOINT") != "${{ inputs.sdkCheckpoint }}"):
            raise ValueError("Core checkpoint changes its exact child selector path")
    elif consumer == "sdk-collect-11":
        if (consumer not in child or child[consumer].get("name", consumer) != consumer
                or _checkpoint_needs(child, consumer) != ["sdk-core-binary-plan", "sdk-core-binary"]
                or type(child[consumer].get("env")) is not dict
                or child[consumer]["env"].get("CODEX_AGENT_SDK_CHECKPOINT") != "${{ inputs.sdkCheckpoint }}"):
            raise ValueError("Core collector changes its exact child selector or worker needs")
    elif consumer == "sdk-checkpoint-11":
        _checkpoint_edges(child, "sdk-collect-11", consumer, "sdk-core-binary-result")
        if (type(child[consumer].get("with")) is not dict
                or child[consumer]["with"].get("sdk-preceding-checkpoint") != "${{ inputs.sdkCheckpoint }}"
                or child[consumer]["with"].get("sdk-checkpoint") != "${{ needs.sdk-collect-11.outputs.checkpoint_inputs || '{}' }}"
                or _checkpoint_needs(child, "sdk-core-binary-result") !=
                   ["sdk-core-binary-plan", "sdk-core-binary", "sdk-collect-11", "sdk-checkpoint-11"]):
            raise ValueError("Nested checkpoint changes its exact collector or preceding selector")
    else:
        raise ValueError("Unregistered Core checkpoint consumer")
    return sha256_bytes(raw), sha256_bytes(child_raw)


def _checkpoint_core_package_edges(raw, binary_raw, package_raw, source_job, *, consumer="sdk-core-package"):
    if source_job not in {"product-validation / sdk-collect-9", "product-validation / sdk-collect-10",
                         "product-validation / sdk-core-binary-wave / sdk-collect-11"}:
        raise ValueError("Core package checkpoint is outside its registered preceding routes")
    collector = "sdk-collect-9" if source_job == "product-validation / sdk-collect-9" else "sdk-collect-10"
    issuer = "sdk-checkpoint-9" if collector == "sdk-collect-9" else "sdk-checkpoint-10"
    parent_sha, binary_sha = _checkpoint_core_workflow_edges(raw, binary_raw, collector, issuer,
                                                            consumer="sdk-checkpoint-11")
    jobs = _checkpoint_workflow_jobs(raw)
    binary, outputs = _checkpoint_workflow_control(binary_raw)
    package = _checkpoint_workflow_jobs(package_raw)
    caller, result = "sdk-core-package-wave", "sdk-core-binary-result"
    if (caller not in jobs or "sdk-core-binary-wave" not in _checkpoint_needs(jobs, caller)
            or jobs[caller].get("uses") != "./.github/workflows/sdk-core-package-validation.yml"
            or type(jobs[caller].get("with")) is not dict
            or jobs[caller]["with"].get("binaryWave") != "${{ toJSON(needs.sdk-core-binary-wave) }}"
            or outputs.get("checkpoint", {}).get("value") != "${{ jobs.sdk-core-binary-result.outputs.checkpoint }}"
            or type(binary[result].get("outputs")) is not dict
            or binary[result]["outputs"].get("checkpoint") != "${{ steps.result.outputs.checkpoint }}"
            or package.get("sdk-core-package", {}).get("name") != "sdk-core-package-common"
            or type(package["sdk-core-package"].get("env")) is not dict
            or package["sdk-core-package"]["env"].get("CODEX_AGENT_SDK_CHECKPOINT") !=
               "${{ fromJSON(inputs.binaryWave).outputs.checkpoint }}"):
        raise ValueError("Core package changes its exact reusable result/consumer selector path")
    if consumer == "sdk-collect-12":
        fields = package.get(consumer, {})
        if (fields.get("name", consumer) != consumer
                or consumer not in package or _checkpoint_needs(package, consumer) != ["sdk-core-package"]
                or type(fields.get("env")) is not dict
                or fields["env"].get("CODEX_AGENT_SDK_CHECKPOINT") !=
                   "${{ fromJSON(inputs.binaryWave).outputs.checkpoint }}"):
            raise ValueError("Core package collector changes its exact child selector or worker needs")
    elif consumer != "sdk-core-package":
        raise ValueError("Unregistered Core package checkpoint consumer")
    return parent_sha, binary_sha, sha256_bytes(package_raw)


_CHECKPOINT_CONSUMER = object()


class _CheckpointConsumer:
    """One authenticated subject and actual next-job witness, scoped to this CLI."""
    __slots__ = ("_active", "_consumer", "_subject", "_source_artifact", "observation", "_token", "_originals",
                 "_workflow", "_bootstrap", "_next_source", "_validated")

    def __init__(self, consumer, custody, observation, token, workflow, seal, *, bootstrap=None, next_source=None):
        if seal is not _CHECKPOINT_CONSUMER:
            raise ValueError("Checkpoint consumer requires private native and needs authentication")
        self._active, self._consumer = True, canonical_json_bytes(consumer)
        self._subject = canonical_json_bytes(custody["envelope"])
        self._source_artifact = canonical_json_bytes(custody["sourceArtifact"])
        self.observation, self._token, self._originals = observation, token, {}
        self._workflow = workflow
        self._bootstrap, self._next_source = canonical_json_bytes(bootstrap), canonical_json_bytes(next_source)
        self._validated = None

    def check(self, *, consumer=None, token=None):
        if not self._active or self.observation._raw is None:
            raise ValueError("Checkpoint consumer witness is closed")
        if consumer is not None and canonical_json_bytes(consumer) != self._consumer:
            raise ValueError("Checkpoint witness belongs to another consumer")
        if token is not None and token != self._token:
            raise ValueError("Checkpoint witness belongs to another observation token")

    def match(self, spec, proof, arguments, consumer_revision, token):
        self.check(token=token)
        envelope = load_canonical_json_bytes(self._subject)
        consumer = load_canonical_json_bytes(self._consumer)
        if (spec != envelope["recipe"] or proof != envelope["completion"]
                or arguments["signer_commit"] != envelope["issuerCommit"]
                or consumer_revision != consumer["producer"]["commit"]):
            raise ValueError("Checkpoint semantics differ from its exact authenticated subject/consumer")

    def bootstrap(self):
        self.check()
        return load_canonical_json_bytes(self._bootstrap)

    def inherit(self, spec, prior):
        self.check()
        envelope = load_canonical_json_bytes(self._subject)
        source = load_canonical_json_bytes(self._next_source)
        if (self._validated != sha256_bytes(canonical_json_bytes(prior))
                or source is None or spec["source"] != source or "reuseCompletion" in spec
                or "reuseCompletionProofSha256" in spec
                or spec["parent"] != envelope["recipe"]["parent"]
                or spec["parentProofSha256"] != envelope["recipe"]["parentProofSha256"]
                or prior.get("extension") != {"spec": envelope["recipe"], "proof": envelope["completion"]}):
            raise ValueError("Checkpoint inheritance changes its authenticated inner proof or next source")

    def validate(self, *, root, revision, frozen, consumer_revision, token):
        self.check(token=token)
        envelope = load_canonical_json_bytes(self._subject)
        result = validate_extension(envelope["recipe"], envelope["completion"],
            {"signer_commit": envelope["issuerCommit"]}, root=root, revision=revision,
            frozen=frozen, consumer_revision=consumer_revision, token=token, _checkpoint=self)
        self._validated = sha256_bytes(canonical_json_bytes(result))
        return result

    def source(self):
        self.check()
        envelope = load_canonical_json_bytes(self._subject)
        return load_canonical_json_bytes(self._source_artifact), [], envelope["completion"]["source"]

    def original(self, original, receipt, locator, token):
        self.check(token=token)
        key = canonical_json_bytes([original, receipt, locator])
        if key not in self._originals:
            consumer = load_canonical_json_bytes(self._consumer)
            fresh = receipt["producer"] == consumer["producer"]
            result = observe_original(original, receipt, token,
                **({"_fresh_observation": self.observation} if fresh else {"native_locator": locator}))
            if result[2] != locator:
                raise ValueError("Checkpoint original differs from its exact native locator")
            self._originals[key] = canonical_json_bytes(list(result))
        return load_canonical_json_bytes(self._originals[key])


def checkpoint_selection(policy, output):
    """A no-op may name only the exact declared bootstrap; every other value fails."""
    import reuse_qualification as native
    validate_checkpoint_owner(policy)
    if type(output) is not dict:
        raise ValueError("Checkpoint output must be an explicit selector")
    if output.get("kind") == "existing-sdk-completion":
        if output != {"kind": "existing-sdk-completion", "native": policy["bootstrap"],
                      "subjectSha256": policy["bootstrapProofSha256"]}:
            raise ValueError("Unchanged checkpoint selector changes its approved bootstrap")
        return None
    require_exact_keys(output, {"kind", "source", "native", "subjectSha256"}, "Checkpoint consumer selector")
    if output["kind"] != "sdk-checkpoint":
        raise ValueError("Unsupported explicit checkpoint selector")
    require_sha256(output["subjectSha256"], "Expected native checkpoint subject")
    arguments = native._native_pin_arguments(output["native"])
    identity = checkpoint_archive_identity(policy, output["source"], **{name: arguments[name]
        for name in ("signer_commit", "source_commit", "run_id", "run_attempt")})
    return arguments, identity


@contextmanager
def checkpoint_consumer(policy, output, work, *, root, consumer, job, token, _next_source=None, _observation=None):
    """Native custody plus actual approved workflow edges; semantic gates follow."""
    import product_reuse as products
    import reuse_qualification as native
    from contextlib import nullcontext
    from datetime import datetime
    from products.inventory import git_regular_blob_bytes, require_integer
    policy, output, consumer = (load_canonical_json_bytes(canonical_json_bytes(value))
                               for value in (policy, output, consumer))
    selection = checkpoint_selection(policy, output)
    if selection is None:
        yield None
        return
    arguments, identity = selection
    source = output["source"]
    # ponytail: register actual wired edges only; cross-workflow forwarding follows
    # its own literal caller/child evidence, never numeric wave ordering.
    next_collector = None
    current_name = "product-validation / sdk-sdk-ios-metadata-ios"
    package = job in {"sdk-core-package", "sdk-collect-12"} and _next_source is None
    nested = job == "sdk-checkpoint-11" and _next_source is not None
    collecting = job in {"sdk-collect-10", "sdk-collect-11", "sdk-collect-12"} and _next_source is None
    core = job in {"sdk-core-binary", "sdk-collect-11"} and _next_source is None or nested or package
    binary_collector = "product-validation / sdk-core-binary-wave / sdk-collect-11"
    if core:
        allowed = {"product-validation / sdk-collect-9", "product-validation / sdk-collect-10"}
        if package:
            allowed.add(binary_collector)
        if (source["jobName"] not in allowed
                or "product-validation / sdk-collect-10" not in policy["collectors"]
                or (nested or package or collecting) and binary_collector not in policy["collectors"]
                or package and collecting and _CORE_PACKAGE_COLLECTOR not in policy["collectors"]):
            raise ValueError("Core checkpoint requires its registered signer/forwarder")
        current_name = ("product-validation / sdk-core-package-wave / sdk-core-package-common" if package
                        else "product-validation / sdk-core-binary-wave / sdk-core-binary-common")
        if collecting:
            current_name = _CORE_PACKAGE_COLLECTOR if package else binary_collector
    elif collecting:
        if "product-validation / sdk-collect-10" not in policy["collectors"]:
            raise ValueError("Checkpoint requires its registered following collector")
        current_name = "product-validation / sdk-collect-10"
    if _next_source is not None:
        _next_source = load_canonical_json_bytes(canonical_json_bytes(_next_source))
        next_identity = checkpoint_archive_identity(policy, _next_source,
            signer_commit=policy["issuerCommit"], source_commit=source["producer"]["commit"],
            run_id=source["producer"]["runId"], run_attempt=source["producer"]["runAttempt"])
        expected_source = binary_collector if nested else "product-validation / sdk-collect-10"
        if (job not in {"sdk-checkpoint-10", "sdk-checkpoint-11"} or _next_source["jobName"] != expected_source
                or _next_source["producer"] != source["producer"]):
            raise ValueError("Checkpoint predecessor is outside its registered next issuer edge")
        next_collector, current_name = expected_source.rsplit(" / ", 1)[1], next_identity["jobName"]
    if (not core and (source["jobName"] != "product-validation / sdk-collect-9"
            or next_collector is None and job not in {"sdk-ios-metadata", "sdk-collect-10"})
            or consumer != {"kind": "ci", "producer": source["producer"]}):
        raise ValueError("Checkpoint is outside its registered current consumer edge")
    native._ensure_native_issuer_commit(root, policy["collectorWorkflowSha"], token)
    workflow = git_regular_blob_bytes(root, policy["collectorWorkflowSha"],
        ".github/workflows/product-validation.yml", max_bytes=1024 * 1024)
    child_paths = []
    if core:
        child_path = ".github/workflows/sdk-core-binary-validation.yml"
        child = git_regular_blob_bytes(root, policy["collectorWorkflowSha"], child_path, max_bytes=1024 * 1024)
        child_paths.append(child_path)
        if package:
            package_path = ".github/workflows/sdk-core-package-validation.yml"
            package_child = git_regular_blob_bytes(root, policy["collectorWorkflowSha"], package_path, max_bytes=1024 * 1024)
            child_paths.append(package_path)
            workflow_sha = _checkpoint_core_package_edges(workflow, child, package_child, source["jobName"], consumer=job)
        else:
            collector_job = source["jobName"].rsplit(" / ", 1)[1]
            workflow_sha = _checkpoint_core_workflow_edges(workflow, child, collector_job,
                "sdk-checkpoint-" + str(_COLLECTED_WAVES[source["jobName"]]), consumer=job)
    else:
        workflow_sha = _checkpoint_workflow_edges(workflow, "sdk-collect-9", "sdk-checkpoint-9", job,
                                                   next_collector=next_collector)
        if collecting:
            fields = _checkpoint_workflow_jobs(workflow)[job]
            if (fields.get("name", job) != job or type(fields.get("env")) is not dict
                    or fields["env"].get("CODEX_AGENT_SDK_CHECKPOINT") != "${{ needs.sdk-checkpoint-9.outputs.checkpoint }}"):
                raise ValueError("Collector checkpoint changes its exact preceding selector")
    if _observation is not None:
        products._fresh_ci_observation_values(_observation, source["producer"], token)
    with (products._fresh_ci_observation(source["producer"], token) if _observation is None
          else nullcontext(_observation)) as observation:
        custody = _fetch_checkpoint_envelope(policy, source, arguments, identity, work, token, observation)
        if custody["subjectSha256"] != output["subjectSha256"]:
            raise ValueError("Checkpoint selector changes its exact native subject")
        fresh = products._fresh_ci_observation_values(observation, source["producer"], token)
        for child_path in child_paths:
            products._require_ci_workflow_reference(fresh["run"],
                f"{native.REPOSITORY}/{child_path}@{policy['collectorWorkflowSha']}", policy["collectorWorkflowSha"])
        matches = products._matching_ci_jobs(fresh["jobs"], current_name)
        if len(matches) != 1:
            raise ValueError("Checkpoint consumer job is missing or ambiguous")
        current, issuer = matches[0], custody["transport"]["checkpointIssuerJob"]
        require_integer(current.get("id"), "Checkpoint consumer job ID", 1)
        if (current["id"] in (issuer["id"], source["jobId"])
                or current.get("run_id") != source["producer"]["runId"]
                or current.get("head_sha") != fresh["run"]["head_sha"]
                or (current.get("status"), current.get("conclusion")) != ("in_progress", None)
                or datetime.fromisoformat(current["started_at"].replace("Z", "+00:00"))
                   < datetime.fromisoformat(issuer["completed_at"].replace("Z", "+00:00"))):
            raise ValueError("Checkpoint consumer is not the actual later current job")
        def when(value):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))

        used_ids = {issuer["id"], current["id"], source["jobId"]}
        previous = issuer

        def successful(name, workflow_path, workflow_commit):
            observed = products._observe_ci_producer_jobs({"forwarder": source["producer"]},
                jobs_by_phase={"forwarder": name}, token=token, _fresh_observation=observation,
                trusted_workflows_by_phase={"forwarder": {"path": workflow_path, "sha": workflow_commit}})
            matches = products._matching_ci_jobs(observed[0]["jobs"], name)
            if len(matches) != 1:
                raise ValueError("Core checkpoint forwarder is missing or ambiguous")
            result = matches[0]
            require_integer(result.get("id"), "Checkpoint forwarder ID", 1)
            if (result["id"] in used_ids or when(result["started_at"]) < when(previous["completed_at"])
                    or when(current["started_at"]) < when(result["completed_at"])):
                raise ValueError("Core checkpoint forwarder does not join the actual signer and consumer")
            used_ids.add(result["id"])
            return result

        if core and source["jobName"] == "product-validation / sdk-collect-9":
            name = "product-validation / sdk-checkpoint-10 / completed-sdk-checkpoint"
            previous = successful(name, native.ISSUER_WORKFLOW, policy["issuerCommit"])
        if package:
            if source["jobName"] != binary_collector:
                matches = products._matching_ci_jobs(fresh["jobs"], binary_collector)
                if len(matches) != 1:
                    raise ValueError("Core checkpoint collection is missing or ambiguous")
                collected = matches[0]
                if (collected.get("status"), collected.get("conclusion")) == ("completed", "skipped"):
                    # The approved result step also checks the exact no-work needs
                    # and forwards its input unchanged; absence alone grants nothing.
                    for name in (binary_collector, "product-validation / sdk-core-binary-wave / sdk-core-binary-common"):
                        matches = products._matching_ci_jobs(fresh["jobs"], name)
                        if len(matches) != 1:
                            raise ValueError("Core no-work role is missing or ambiguous")
                        skipped = matches[0]
                        require_integer(skipped.get("id"), "Core skipped job ID", 1)
                        if (skipped["id"] in used_ids or skipped.get("run_id") != source["producer"]["runId"]
                                or skipped.get("head_sha") != fresh["run"]["head_sha"]
                                or (skipped.get("status"), skipped.get("conclusion")) != ("completed", "skipped")):
                            raise ValueError("Core no-work branch requires its exact skipped roles")
                        used_ids.add(skipped["id"])
                    previous = successful("product-validation / sdk-core-binary-wave / sdk-core-binary-plan",
                        ".github/workflows/sdk-core-binary-validation.yml", policy["collectorWorkflowSha"])
                else:
                    previous = successful(binary_collector, ".github/workflows/sdk-core-binary-validation.yml",
                                          policy["collectorWorkflowSha"])
                    previous = successful("product-validation / sdk-core-binary-wave / sdk-checkpoint-11 / completed-sdk-checkpoint",
                                          native.ISSUER_WORKFLOW, policy["issuerCommit"])
            successful("product-validation / sdk-core-binary-wave / sdk-core-binary-result",
                       ".github/workflows/sdk-core-binary-validation.yml", policy["collectorWorkflowSha"])
        if _next_source is not None:
            _, _, next_locator = observe_source(_next_source, token, _fresh_observation=observation)
            if (next_locator["job"]["id"] in used_ids
                    or datetime.fromisoformat(next_locator["job"]["completed_at"].replace("Z", "+00:00"))
                       > datetime.fromisoformat(current["started_at"].replace("Z", "+00:00"))):
                raise ValueError("Next checkpoint collector must finish before its actual issuer")
        witness = _CheckpointConsumer(consumer, custody, observation, token,
            (policy["collectorWorkflowSha"], ".github/workflows/product-validation.yml", workflow_sha),
            _CHECKPOINT_CONSUMER, bootstrap=policy["bootstrap"], next_source=_next_source)
        try:
            yield witness
        finally:
            witness._active = False
            witness._originals.clear()


def _collector_control_source(source):
    """Validate selectors only; official source/upload observations grant custody."""
    import reuse_qualification as native
    from products.inventory import require_integer
    require_exact_keys(source, {"producer", "workflowSha", "jobName", "jobId", "artifactId",
        "artifactSha256", "artifactBytes", "inventoryCommit", "referenceControlSha256"}, "Collector control source")
    producer = validate_producer(source["producer"])
    if (producer["repository"] != native.REPOSITORY or producer["event"] != "pull_request"
            or producer["pullRequest"] != 31 or producer["workflowPath"] != ".github/workflows/ci.yml"
            or type(source["jobName"]) is not str or source["jobName"] not in _COLLECTED_WAVES
            or source["inventoryCommit"] != producer["commit"]):
        raise ValueError("Collector controls require their exact registered source")
    native._commit(source["workflowSha"])
    for field in ("artifactSha256", "referenceControlSha256"):
        require_sha256(source[field], "Collector control " + field)
    for field in ("jobId", "artifactId", "artifactBytes"):
        require_integer(source[field], "Collector control " + field, 1)
    if source["artifactBytes"] > 16 * 1024**3:
        raise ValueError("Collector state exceeds its existing upload bound")
    return source


def collector_control_artifact_name(source):
    source = _collector_control_source(source)
    producer = source["producer"]
    return (f"codex-agent-sdk-wave-{_COLLECTED_WAVES[source['jobName']]}-controls-{producer['tree']}"
            f"-run-{producer['runId']}-attempt-{producer['runAttempt']}-state-{source['artifactId']}")


def prepare_collector_controls(source, reference_bytes, controls):
    """Project staged controls only. This is neither object nor native admission.

    The separate upload binds the actual state upload to its reference manifest;
    its consumer authenticates the whole small ZIP before using these pins.
    """
    from products.restore import object_relative_path
    from product_reuse import _same_run_state_consumer
    from runtime_reference_transport import REFERENCE_NAME, validate_references
    source = _collector_control_source(source)
    if (type(reference_bytes) is not bytes or len(reference_bytes) > LIMIT
            or sha256_bytes(reference_bytes) != source["referenceControlSha256"]):
        raise ValueError("Collector reference bytes differ from their declared control")
    references = validate_references(load_canonical_json_bytes(reference_bytes), 0,
        sdk_state_wave=_COLLECTED_WAVES[source["jobName"]])
    inventory = {row["relativePath"]: row for row in references["inventory"]}
    prefix = "runtime-state/"
    required = {SOURCE_PLAN, *(prefix + name for name in
        ("producer.json", "reuse-wave-request.json", "reuse-wave-result.json"))}
    if type(controls) is not dict or not required <= controls.keys() or not 4 <= len(controls) <= 128:
        raise ValueError("Collector controls lack their bounded source plan and state")
    producer = source["producer"]
    if type(controls[SOURCE_PLAN]) is not str:
        raise ValueError("Collector controls must preserve the exact source plan text")
    plan = load_json_bytes(controls[SOURCE_PLAN].encode("utf-8"))
    _same_run_state_consumer({"producer": producer}, controls[prefix + "producer.json"])
    if (type(plan) is not dict or plan.get("remoteBuildAuthorized") is not True
            or any(plan.get(key) != producer[key] for key in ("repository", "event", "pullRequest"))
            or plan.get("validationCommit") != producer["commit"] or plan.get("validationTree") != producer["tree"]):
        raise ValueError("Collector control plan or state changes its original producer")
    request = controls[prefix + "reuse-wave-request.json"]
    if (type(request) is not dict or request.get("repositoryRevision") != producer["commit"]
            or any(request.get(key) != producer[key] for key in ("repository", "pullRequest"))):
        raise ValueError("Collector control request changes its original source")
    available = _records(request.get("availableObjects"), "Collected control objects")
    pins, seen = [], set()
    for path, value in sorted(controls.items()):
        require_relative_path(path, "Collector control path")
        raw = value.encode("utf-8") if path == SOURCE_PLAN else canonical_json_bytes(value)
        pin = {"relativePath": path, "bytes": len(raw), "sha256": sha256_bytes(raw)}
        if not 0 < len(raw) <= LIMIT:
            raise ValueError("Collector control exceeds its existing member bound")
        if path in required:
            if inventory.get(path) != pin:
                raise ValueError("Collector control differs from its exact state inventory")
        else:
            receipt = validate_phase_receipt(value)
            instance = _identity(receipt)
            phase = available.get(instance)
            if (instance not in PHASE_INSTANCE_IDS or instance.product != "sdk" or instance in seen
                    or phase is None or receipt["buildKey"] != phase.get("buildKey")
                    or pin["sha256"] != phase.get("receiptSha256")
                    or any(receipt["producer"][key] != producer[key] for key in ("repository", "event", "pullRequest"))
                    or (receipt["producer"]["runId"], receipt["producer"]["runAttempt"])
                    > (producer["runId"], producer["runAttempt"])):
                raise ValueError("Collector receipt changes its exact available SDK original")
            seen.add(instance)
            if inventory.get(path) != pin:
                obj = prefix + "original-objects/" + object_relative_path(phase["buildKey"], phase["receiptSha256"])
                record = inventory.get(obj)
                if (path != obj + "/phase-receipt.json" or record is None
                        or record["sha256"] != phase.get("objectSha256")
                        or not 0 < record["bytes"] <= _object_limit(instance)):
                    raise ValueError("Collector receipt lacks its exact inventoried object")
        pins.append(pin)
    # Missing receipt scope and semantic admission remain the existing recipe
    # validators' responsibility; this projection grants only source custody.
    envelope = canonical_json_bytes({"schemaVersion": 1, "kind": "sdk-collector-controls",
        "source": source, "controlPins": pins, "controls": controls})
    if len(envelope) > LIMIT or len(envelope) + len(reference_bytes) > 2 * LIMIT:
        raise ValueError("Collector controls exceed the existing compact archive bounds")
    return {COLLECTOR_CONTROL_NAME: envelope, REFERENCE_NAME: reference_bytes}


def stage_collector_controls(source, reference_path, controls, destination):
    """Publish two small files from staged bytes, without walking product roots."""
    import tempfile
    from products.inventory import publish_regular_tree, read_regular_file_bytes
    reference = read_regular_file_bytes(reference_path, max_bytes=LIMIT, reject_symlink_parents=True)
    files = prepare_collector_controls(source, reference, controls)
    with tempfile.TemporaryDirectory(prefix="sdk-collector-controls-") as temporary:
        prepared = Path(temporary).resolve() / "controls"
        prepared.mkdir()
        for name, raw in files.items():
            (prepared / name).write_bytes(raw)
        publish_regular_tree(prepared, destination)


def fetch_collector_controls(source, selector, work, *, producer, job_name, workflow_sha, token,
                             _fresh_observation=None):
    """Authenticate whole small control upload before exposing any manifest pins.

    Producer, registered role and workflow SHA come from the independently
    approved caller policy/plan, never from this artifact or its selector.
    Returned controls still require all existing recipe and new-object gates.
    """
    from datetime import datetime
    import product_reuse as products
    from products.inventory import require_integer, verified_zip_contents
    from runtime_reference_transport import REFERENCE_NAME
    source = _collector_control_source(source)
    if (source["producer"] != producer or source["jobName"] != job_name
            or source["workflowSha"] != workflow_sha):
        raise ValueError("Collector selectors differ from the independent caller policy")
    require_exact_keys(selector, {"artifactId", "artifactSha256"}, "Collector control selector")
    require_integer(selector["artifactId"], "Collector control upload", 1)
    require_sha256(selector["artifactSha256"], "Collector control upload digest")
    state, observed, locator = observe_source(source, token,
        **({"_fresh_observation": _fresh_observation} if _fresh_observation is not None else {}))
    name = collector_control_artifact_name(source)
    artifact = products._contract_ci_upload_metadata(selector["artifactId"], selector["artifactSha256"],
        name, producer, observed[0]["run"], token)
    products._require_artifact_job_window(observed[0], job_name, artifact)
    if (artifact["size_in_bytes"] > 2 * LIMIT or artifact["id"] == state["id"]
            or datetime.fromisoformat(artifact["created_at"].replace("Z", "+00:00"))
            < datetime.fromisoformat(state["created_at"].replace("Z", "+00:00"))):
        raise ValueError("Collector control upload must be small and follow its exact state upload")
    work = Path(work)
    work.mkdir(parents=True, exist_ok=False)
    archive = work / "collector-controls.zip"
    downloaded, _ = products._reuse_contract_ci_upload(artifact, producer, observed[0]["run"], token,
        destination=archive, limit=2 * LIMIT, artifact_sha256=selector["artifactSha256"],
        size=artifact["size_in_bytes"])
    if downloaded != artifact:
        raise ValueError("Collector control upload changed during acquisition")
    _, retained, identity = verified_zip_contents(archive, max_archive_bytes=2 * LIMIT,
        max_central_directory_bytes=64 * 1024, max_members=2, max_entry_bytes=LIMIT,
        max_total_bytes=2 * LIMIT, max_retained_bytes=2 * LIMIT, require_sorted=False)
    if (identity != {"bytes": artifact["size_in_bytes"], "sha256": artifact["digest"]}
            or set(retained) != {COLLECTOR_CONTROL_NAME, REFERENCE_NAME}):
        raise ValueError("Collector control ZIP differs from its whole authenticated upload")
    envelope = require_exact_keys(load_canonical_json_bytes(retained[COLLECTOR_CONTROL_NAME]),
        {"schemaVersion", "kind", "source", "controlPins", "controls"}, "Collector control envelope")
    if (type(envelope["schemaVersion"]) is not int or envelope["schemaVersion"] != 1
            or envelope["kind"] != "sdk-collector-controls" or envelope["source"] != source
            or prepare_collector_controls(source, retained[REFERENCE_NAME], envelope["controls"]) != retained):
        raise ValueError("Collector control envelope changes its source or exact pins")
    return {"source": source, "references": load_canonical_json_bytes(retained[REFERENCE_NAME]),
        "controls": envelope["controls"], "controlPins": envelope["controlPins"],
        "stateLocator": locator, "controlArtifact": artifact, "controlArchive": identity}


COLLECTOR_RECEIPTS = "collector-receipts"


def write_collector_receipts(carrier, result, destination):
    """Retain receipts already returned by write_carrier, never reopen objects.

    These are transport controls. Native admission still requires independently
    authenticated source custody, complete receipt joins and object verification.
    """
    import tempfile
    from products.inventory import publish_regular_tree
    selected = {identity: row for identity, row in _records(result["phases"], "Collector result").items()
                if identity.product == "sdk" and row["state"] in {"reused", "retained"}}
    objects = {identity: row for identity, row in _records(carrier["objects"], "Verified carrier objects").items()
               if identity.product == "sdk"}
    if set(objects) != set(selected) or len(objects) > len(PHASE_INSTANCE_IDS):
        raise ValueError("Collector receipt controls change the exact successful SDK scope")
    if not selected:
        return
    files = {}
    for identity, phase in selected.items():
        original = objects[identity]
        receipt = validate_phase_receipt(original["receipt"])
        raw = canonical_json_bytes(receipt)
        if (identity not in PHASE_INSTANCE_IDS or _identity(receipt) != identity
                or receipt["buildKey"] != phase["buildKey"] or original["receiptBytes"] != raw
                or sha256_bytes(raw) != phase["receiptSha256"] or len(raw) > LIMIT
                or any(original[field] != phase[field] for field in OBJECT)):
            raise ValueError("Collector receipt differs from the verified original tuple")
        files[phase["receiptSha256"][7:] + ".json"] = raw
    if sum(map(len, files.values())) > LIMIT:
        raise ValueError("Collector receipt controls exceed the compact member budget")
    with tempfile.TemporaryDirectory(prefix="sdk-collector-receipts-") as temporary:
        prepared = Path(temporary).resolve() / "receipts"
        prepared.mkdir()
        for name, raw in files.items():
            (prepared / name).write_bytes(raw)
        publish_regular_tree(prepared, destination)


def collected_control_inputs(handoff, references):
    """Read fixed controls and receipt files from the existing reference inventory.

    The caller supplies the just-staged inventory, not authority. Publication
    binds these bytes through prepare_collector_controls and the actual upload.
    """
    from products.inventory import read_regular_file_bytes
    prefix = "runtime-state/"
    required = {SOURCE_PLAN, *(prefix + name for name in
        ("producer.json", "reuse-wave-request.json", "reuse-wave-result.json"))}
    inventory = {row["relativePath"]: row for row in references["inventory"]}
    receipts = {path for path in inventory if path.startswith(prefix + COLLECTOR_RECEIPTS + "/")}
    names = required | receipts
    if not required <= inventory.keys() or not 4 <= len(names) <= 128:
        raise ValueError("Collector input controls are missing or exceed their fixed bound")
    controls = {}
    for path in sorted(names):
        require_relative_path(path, "Collector staged control")
        raw = read_regular_file_bytes(Path(handoff) / path, max_bytes=LIMIT, reject_symlink_parents=True)
        if inventory[path] != {"relativePath": path, "bytes": len(raw), "sha256": sha256_bytes(raw)}:
            raise ValueError("Collector staged control changed after reference export")
        controls[path] = raw.decode("utf-8") if path == SOURCE_PLAN else load_canonical_json_bytes(raw)
        if path in receipts and path != prefix + COLLECTOR_RECEIPTS + "/" + sha256_bytes(raw)[7:] + ".json":
            raise ValueError("Collector receipt control path differs from its original digest")
    available = _records(controls[prefix + "reuse-wave-request.json"]["availableObjects"], "Collector available SDK objects")
    selected = {identity: row for identity, row in available.items() if identity.product == "sdk"}
    captured = _records([controls[path] for path in receipts], "Collector staged receipts")
    if set(captured) != set(selected):
        raise ValueError("Collector receipt controls omit or add an available SDK original")
    for identity, receipt in captured.items():
        validate_phase_receipt(receipt)
        if (receipt["buildKey"] != selected[identity]["buildKey"]
                or sha256_bytes(canonical_json_bytes(receipt)) != selected[identity]["receiptSha256"]):
            raise ValueError("Collector receipt controls change an available SDK original")
    return controls


def publish_current_collector_controls(handoff, reference_path, destination, *, wave,
        artifact_id, artifact_sha256, workflow_sha, token, environ, github_output_path=None):
    """Stage selectors after the actual upload; the next job authenticates custody.

    This job is still running. Its own output cannot establish successful CI or
    native authority; fetch_collector_controls requires that later, independently.
    """
    import product_reuse as products
    from products.inventory import read_regular_file_bytes, require_integer
    from runtime_reference_transport import validate_references
    from reuse import github_output
    require_integer(wave, "Collector control wave", 1)
    roles = [job for job, number in _COLLECTED_WAVES.items() if number == wave]
    if len(roles) != 1:
        raise ValueError("Collector controls require one registered role for their wave")
    job_name = roles[0]
    reference = read_regular_file_bytes(reference_path, max_bytes=LIMIT, reject_symlink_parents=True)
    references = validate_references(load_canonical_json_bytes(reference), 0, sdk_state_wave=wave)
    controls = collected_control_inputs(handoff, references)
    plan = load_json_bytes(controls[SOURCE_PLAN].encode("utf-8"))
    # Upload identity belongs to this collector; retained replay context and
    # original receipt producers keep their exact earlier-attempt identities.
    consumer = products._consumer(plan, environ)
    products._same_run_state_consumer(consumer, controls["runtime-state/producer.json"])
    producer = consumer["producer"]
    run = products._original_ci_run(producer, token)
    if run.get("id") != producer["runId"] or run.get("run_attempt") != producer["runAttempt"]:
        raise ValueError("Collector control output run differs from its current attempt")
    jobs = products.paginated_items(f"https://api.github.com/repos/{producer['repository']}/actions/runs/"
        f"{producer['runId']}/attempts/{producer['runAttempt']}/jobs", "jobs", token)
    selected = products._matching_ci_jobs(jobs, job_name)
    if (len(selected) != 1 or selected[0].get("run_id") != producer["runId"]
            or selected[0].get("head_sha") != run.get("head_sha")
            or (selected[0].get("status"), selected[0].get("conclusion"))
            not in (("in_progress", None), ("completed", "success"))):
        raise ValueError("Collector control output lacks its unique current job")
    artifact = products._contract_ci_upload_metadata(artifact_id, artifact_sha256,
        _SOURCE_UPLOADS[job_name] + producer["tree"] + f"-attempt-{producer['runAttempt']}",
        producer, run, token)
    source = _collector_control_source({"producer": producer, "workflowSha": workflow_sha,
        "jobName": job_name, "jobId": selected[0]["id"], "artifactId": artifact_id,
        "artifactSha256": artifact_sha256, "artifactBytes": artifact["size_in_bytes"],
        "inventoryCommit": producer["commit"], "referenceControlSha256": sha256_bytes(reference)})
    # Re-read through the existing guarded publisher. A changed reference cannot
    # pass its original hash; only bounded JSON controls are touched here.
    stage_collector_controls(source, reference_path, controls, destination)
    github_output(github_output_path, {"artifact_name": collector_control_artifact_name(source),
        "source": canonical_json_bytes(source).decode("utf-8").rstrip("\n")})
    return source


def _publish_main():
    import argparse
    import os
    parser = argparse.ArgumentParser(description="Stage current collector control output", allow_abbrev=False)
    for name in ("handoff", "reference-path", "destination"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--github-output", dest="github_output_path", type=Path, required=True)
    parser.add_argument("--wave", type=int, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--workflow-sha", required=True)
    args = parser.parse_args()
    publish_current_collector_controls(**vars(args), token=os.environ.get("GITHUB_TOKEN"), environ=os.environ)


def _prepare_main():
    import argparse
    from products.inventory import read_regular_file_bytes, write_canonical_json
    import json
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    values = load_canonical_json_bytes(read_regular_file_bytes(args.inputs,
        reject_symlink_parents=True, max_bytes=LIMIT))
    require_exact_keys(values, {"policy", "source", "references", "controls", "originals",
                               "frozen", "parent_sdk", "previous_sdk"}, "Held recipe inputs")
    spec, controls, report = prepare_collected_extension(**values, root=args.repository_root.resolve(strict=True))
    if args.output is not None:
        args.output.mkdir(exist_ok=False)
        for name, value in (("recipe.json", spec), ("controls.json", controls), ("prepared.json", report)):
            write_canonical_json(args.output / name, value)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "stage-collector-controls":
        del sys.argv[1]
        _publish_main()
    else:
        _prepare_main()
