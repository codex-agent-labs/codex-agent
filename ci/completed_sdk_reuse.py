"""Validate incremental SDK completion controls after independent native admission.

These checks do not create semantic authority. The native issuer authenticates
the successful admission upload and each consumed original object. The consumer
authenticates its attestation before creating the sealed completed-reuse capability.
"""

from pathlib import Path

from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, load_json_bytes, require_exact_keys,
    require_relative_path, sha256_bytes, validate_file_record,
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
    """V3 compact states omit bodies; consumption uses exact original workers."""
    return spec["schemaVersion"] == 3


def collected_validation(spec):
    return (type(spec) is dict and type(spec.get("source")) is dict
            and type(spec["source"].get("jobName")) is str
            and spec["source"]["jobName"] in _COLLECTED_WAVES)


def _records(rows, label):
    import reuse_qualification
    return reuse_qualification._phase_records(rows, label)


def _receipt_objects(spec):
    """Only exact collected objects may supply their embedded receipt control."""
    from products.restore import object_relative_path
    objects = spec.get("receiptObjects", [])
    if type(objects) is not list or len(objects) > len(spec["completedPhases"]):
        raise ValueError("Collected receipt objects exceed their selected scope")
    selected = {row["receiptPath"]: row for row in spec["completedPhases"]}
    result = {}
    for row in objects:
        validate_file_record(row, "Collected receipt object", with_kind=False)
        path = row["relativePath"] + "/phase-receipt.json"
        phase = selected.get(path)
        if (path in result or phase is None or not 0 < row["bytes"] <= LIMIT
                or row["sha256"] != phase["objectSha256"]
                or row["relativePath"] != spec["stateRoot"] + "/original-objects/"
                    + object_relative_path(phase["buildKey"], phase["receiptSha256"])):
            raise ValueError("Collected receipt object differs from its exact selected phase")
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
    if (controls[prefix + "producer.json"] != producer
            or request["repositoryRevision"] != producer["commit"]
            or any(request[field] != base["request"][field]
                   for field in ("repository", "pullRequest", "versions", "catalogs"))
            or request.get("sdkRuntimeSource") is not None):
        raise ValueError("Incremental SDK completion changes its original consumer or policy")
    phases = _records(result["phases"], "Incremental SDK result")
    available = _records(request["availableObjects"], "Incremental SDK available objects")
    frozen = _records(base["expectedResult"]["phases"], "Native completed predecessors")
    if set(selected) & set(frozen):
        raise ValueError("Incremental SDK completion replaces an existing native phase")
    expected = {**frozen, **selected}
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
        if instance in frozen and authorities.get(instance) != original_authorities[instance]:
            raise ValueError("Incremental SDK completion changes a native predecessor authority")
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


def observe_original(original, receipt, token, *, native_locator=None):
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
        **({"native_job_ids_by_phase": {"original": original["jobId"]}} if native_locator is not None else {}))
    matches = products._matching_ci_jobs(observed[0]["jobs"], base_job, expected_build_key=receipt["buildKey"])
    if len(matches) != 1 or matches[0].get("id") != original["jobId"]:
        raise ValueError("Incremental SDK original job is missing or ambiguous")
    name = (products._worker_artifact_prefix("sdk", instance) +
            f"{receipt['buildKey'][7:]}-{producer['tree']}-attempt-{producer['runAttempt']}")
    artifact = products._contract_ci_upload_metadata(original["artifactId"], original["artifactSha256"],
        name, producer, observed[0]["run"], token,
        **({"upload_limit": products._IOS_PACKAGE_UPLOAD_LIMIT} if instance == IOS_PACKAGE else {}))
    products._require_artifact_job_window(observed[0], matches[0]["name"], artifact)
    locator = products._runtime_original_locator(
        artifact, original["workflowSha"], instance, matches[0])
    if native_locator is not None and locator != native_locator:
        raise ValueError("Fresh original differs from its authenticated native locator")
    return artifact, observed, locator


def observe_source(source, token, *, contract=False, native_locator=None):
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
    reuse = collected and "reuseCompletion" in spec
    require_exact_keys(spec, {"schemaVersion", "parent", "parentProofSha256", "source", "stateRoot",
        "controls", "completedPhases", "originals", "contractControls", "contractFiles"}
        | ({"sourcePlan"} if collected else set())
        | ({"receiptObjects"} if collected and "receiptObjects" in spec else set())
        | ({"reuseCompletion", "reuseCompletionProofSha256"} if reuse else set()), "Incremental SDK spec")
    if type(spec["schemaVersion"]) is not int or spec["schemaVersion"] not in (2, 3):
        raise ValueError("Unsupported incremental SDK spec")
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
        if source["artifactBytes"] > (16 * 1024**3 if collected and not contract else LIMIT):
            raise ValueError("Incremental controls exceed the bounded original upload")
    if (spec["stateRoot"] != ("runtime-state" if collected else "product-resume-state")
            or type(spec["source"]["jobName"]) is not str
            or spec["source"]["jobName"] not in _SOURCE_UPLOADS
            or collected and spec["schemaVersion"] != 3):
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


def validate_extension(spec, proof, arguments, *, root, revision, frozen, token):
    """The caller has authenticated this exact new native subject first."""
    import reuse_qualification as native
    originals = _spec(spec)
    require_exact_keys(proof, {"schemaVersion", "kind", "issuerCommit", "specSha256", "parentProof",
        "controls", "source", "originals", "members", "contractSource", "contractFiles"},
        "Incremental native completion")
    if (type(proof["schemaVersion"]) is not int or proof["schemaVersion"] != spec["schemaVersion"]
            or proof["kind"] != "completed-sdk-reuse" or proof["issuerCommit"] != arguments["signer_commit"]
            or proof["specSha256"] != sha256_bytes(canonical_json_bytes(spec))
            or sha256_bytes(canonical_json_bytes(proof["parentProof"])) != spec["parentProofSha256"]
            or proof["parentProof"].get("schemaVersion") != 1):
        raise ValueError("Incremental completion changes its approved native issuer or parent")
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
        source, contract, *expected_locators = bounded_verify(lambda observe: observe()[2], (
            lambda: observe_source(spec["source"], token, native_locator=proof["source"]),
            lambda: observe_source(spec["contractControls"], token, contract=True, native_locator=proof["contractSource"]),
            *(lambda receipt=receipt, locator=locator: observe_original(
                originals[_identity(receipt)], receipt, token, native_locator=locator)
              for receipt, locator in zip(receipts, proof["originals"]))))
    if source != proof["source"]:
        raise ValueError("Incremental completed source changed")
    if contract != proof["contractSource"]:
        raise ValueError("Incremental Contract source changed")
    if expected_locators != proof["originals"]:
        raise ValueError("Incremental SDK original native observations changed")
    # A fresh runner may lack the original PR merge even with full branch history.
    # Acquire only the exact native-pinned tree after its live source checks pass.
    validate_current(request, phases, receipts, root=root, revision=revision,
                     original_revision=_inventory_revision(spec, root, token=token))
    available = _records(request["availableObjects"], "Incremental original objects")
    if type(proof["members"]) is not list or len(proof["members"]) != len(phases):
        raise ValueError("Incremental SDK object members changed")
    for phase, member in zip(phases, proof["members"]):
        validate_file_record(member, "Incremental SDK object", with_kind=False)
        expected = spec["stateRoot"] + "/" + available[_identity(phase)]["objectPath"]
        limit = LIMIT
        if original_worker_member(spec):
            from products.restore import object_relative_path
            expected = "shard/" + object_relative_path(phase["buildKey"], phase["receiptSha256"])
            if _identity(phase) == IOS_PACKAGE:
                limit = 8 * 1024**3
        if (member["relativePath"] != expected or member["sha256"] != phase["objectSha256"]
                or not 0 < member["bytes"] <= limit):
            raise ValueError("Incremental SDK consumed object changed")
    sdk["extension"] = {"spec": spec, "proof": proof}
    return sdk


def _qualified_members(spec, prior, phases, receipts):
    """Join only after _fetch_completed_sdk freshly authenticates the native subject.

    The new issuer reuses exact byte qualification; current source admission,
    owning inputs, receipts and fresh original locators remain mandatory.
    """
    extension = prior.get("extension")
    if extension is None:
        raise ValueError("Object reuse requires an earlier incremental native completion")
    old, proof = extension["spec"], extension["proof"]
    if (old["schemaVersion"] != 3 or old["parent"] != spec["parent"]
            or sha256_bytes(canonical_json_bytes(prior["proof"])) != spec["parentProofSha256"]
            or sha256_bytes(canonical_json_bytes(proof)) != spec["reuseCompletionProofSha256"]):
        raise ValueError("Reused native completion differs from its pinned subject or parent")
    selected = _records(phases, "Current admitted SDK phases")
    earlier = _records(old["completedPhases"], "Previously native-qualified SDK phases")
    current_receipts = {_identity(receipt): canonical_json_bytes(receipt) for receipt in receipts}
    if not set(earlier) <= set(selected):
        raise ValueError("Reused native completion drops a previously admitted SDK phase")
    qualified = {}
    for instance, member, locator in zip(sorted(earlier), proof["members"], proof["originals"], strict=True):
        phase = earlier[instance]
        if (any(phase[field] != selected[instance][field] for field in OBJECT)
                or canonical_json_bytes(proof["controls"][phase["receiptPath"]]) != current_receipts[instance]):
            raise ValueError("Reused native completion changes an original SDK object or receipt")
        qualified[instance] = member, locator
    return qualified


def issue_extension(spec, work, *, root, revision, frozen, token):
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
    sdk = native._fetch_completed_sdk(work / "parent", spec["parent"],
        root=root, revision=revision, frozen=frozen, token=token)
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
    if collected_validation(spec):
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
        wanted = {row["relativePath"]: row for row in spec["controls"]
                  if row["relativePath"] not in receipt_objects}
        wanted.update((row["relativePath"], row) for row, _ in receipt_objects.values())
        transport = products._capture_runtime_reference_members(plan, raw_plan, producer, base, destination,
            trusted_workflow_sha=spec["source"]["workflowSha"], token=token,
            wanted=wanted)
        if transport["artifact"] != artifact:
            raise ValueError("Collector control intake changes its observed source upload")
        controls = {}
        for row in spec["controls"]:
            embedded = receipt_objects.get(row["relativePath"])
            if embedded is not None:
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
        request, phases, receipts = validate_controls(spec, controls, _base(frozen, sdk))
        validate_current(request, phases, receipts, root=root, revision=revision,
                         original_revision=_inventory_revision(spec, root, token=token))
        qualified = {}
        if "reuseCompletion" in spec:
            prior = native._fetch_completed_sdk(work / "previous", spec["reuseCompletion"],
                root=root, revision=revision, frozen=frozen, token=token)
            qualified = _qualified_members(spec, prior, phases, receipts)
        available = _records(request["availableObjects"], "Incremental original objects")
        members, locators, transferred, reused_bytes = [], [], 0, 0
        for number, phase in enumerate(phases):
            artifact, _, locator = observe_original(originals[_identity(phase)], receipts[number], token)
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
                package = _identity(phase) == IOS_PACKAGE
                bounds = {"max_bytes": products._IOS_PACKAGE_UPLOAD_LIMIT} if package else {}
                with open_reference_archive(artifact, token, **bounds) as (original, stream):
                    member = {"relativePath": name, "bytes": original.getinfo(name).file_size,
                              "sha256": phase["objectSha256"]}
                    if not 0 < member["bytes"] <= (8 * 1024**3 if package else LIMIT):
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
    write_canonical_json(work / "completion.json", proof)
    report = {"downloadedOriginalBytes": spec["contractControls"]["artifactBytes"] + (
        0 if collected_validation(spec) else spec["source"]["artifactBytes"]),
        "sourceControlRangeBytes": source_range_bytes, "originalMemberRangeBytes": transferred,
        "verifiedObjectBytes": sum(row["bytes"] for row in members) - reused_bytes,
        "reusedObjectBytes": reused_bytes, "completedSdkPhases": len(phases) + 1,
        "seconds": str(time.perf_counter() - started), "productPhasesExecuted": 0}
    import json
    print(json.dumps(report), flush=True)
    return report
