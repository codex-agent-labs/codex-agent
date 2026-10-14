"""Validate incremental SDK completion controls after independent native admission.

These checks do not create semantic authority. The native issuer authenticates
the successful admission upload and each consumed original object. The consumer
authenticates its attestation before creating the sealed completed-reuse capability.
"""

from pathlib import Path

from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, require_exact_keys,
    require_relative_path, sha256_bytes, validate_file_record,
)
from products.receipt import validate_phase_receipt, validate_producer
from products.registry import PHASE_INSTANCE_IDS, PhaseInstanceId


IDENTITY = ("product", "component", "phase", "target")
OBJECT = ("buildKey", "receiptSha256", "objectSha256")
LIMIT = 16 * 1024 * 1024
IOS_PACKAGE = PhaseInstanceId("sdk", "sdk-ios", "package", "ios")


def _identity(record):
    return PhaseInstanceId(*(record.get(field) for field in IDENTITY))


def original_worker_member(spec):
    """V3 compact states omit bodies; consumption uses exact original workers."""
    return spec["schemaVersion"] == 3


def _records(rows, label):
    import reuse_qualification
    return reuse_qualification._phase_records(rows, label)


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
        raw = canonical_json_bytes(controls[row["relativePath"]])
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
    for instance, phase in selected.items():
        require_exact_keys(phase, set(IDENTITY + OBJECT) | {"receiptPath"}, "Incremental SDK phase")
        path = require_relative_path(phase["receiptPath"], "Incremental SDK receipt path")
        receipt = validate_phase_receipt(controls[path])
        if (not path.startswith(prefix) or _identity(receipt) != instance
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


def observe_original(original, receipt, token):
    """Fresh official original job/upload gates; a native member digest is separate."""
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
    observed = products._observe_ci_producer_jobs({"original": producer},
        jobs_by_phase={"original": base_job}, build_keys_by_phase={"original": receipt["buildKey"]},
        trusted_workflow_sha=original["workflowSha"], token=token)
    matches = products._matching_ci_jobs(observed[0]["jobs"], base_job, expected_build_key=receipt["buildKey"])
    if len(matches) != 1 or matches[0].get("id") != original["jobId"]:
        raise ValueError("Incremental SDK original job is missing or ambiguous")
    name = (products._worker_artifact_prefix("sdk", instance) +
            f"{receipt['buildKey'][7:]}-{producer['tree']}-attempt-{producer['runAttempt']}")
    artifact = products._contract_ci_upload_metadata(original["artifactId"], original["artifactSha256"],
        name, producer, observed[0]["run"], token,
        **({"upload_limit": products._IOS_PACKAGE_UPLOAD_LIMIT} if instance == IOS_PACKAGE else {}))
    products._require_artifact_job_window(observed[0], matches[0]["name"], artifact)
    return artifact, observed, products._runtime_original_locator(
        artifact, original["workflowSha"], instance, matches[0])


def observe_source(source, token, *, contract=False):
    import product_reuse as products
    import reuse_qualification as native
    producer = validate_producer(source["producer"])
    if (producer["repository"] != native.REPOSITORY or producer["event"] != "pull_request"
            or producer["pullRequest"] != 31 or producer["workflowPath"] != ".github/workflows/ci.yml"):
        raise ValueError("Incremental source changes its approved producer scope")
    job = ("product-validation / contract-validation / contract-attestation" if contract
           else "product-validation / product-resume")
    prefix = "codex-agent-contract-release-controls-" if contract else "codex-agent-product-resume-"
    observed = products._observe_ci_producer_jobs({"source": producer}, jobs_by_phase={"source": job},
        trusted_workflow_sha=source["workflowSha"], token=token)
    selected = products._matching_ci_jobs(observed[0]["jobs"], job)
    if len(selected) != 1 or selected[0]["id"] != source["jobId"]:
        raise ValueError("Incremental source differs from its approved successful job")
    artifact = products._contract_ci_upload_metadata(source["artifactId"], source["artifactSha256"],
        prefix + producer["tree"], producer, observed[0]["run"], token)
    if artifact["size_in_bytes"] != source["artifactBytes"]:
        raise ValueError("Incremental source size changed")
    products._require_artifact_job_window(observed[0], job, artifact)
    locator = products._runtime_original_locator(artifact, source["workflowSha"],
        PhaseInstanceId("contract", "contract", "metadata", "common") if contract else
        PhaseInstanceId("sdk", "javascript", "metadata", "node"), selected[0])
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
    require_exact_keys(spec, {"schemaVersion", "parent", "parentProofSha256", "source", "stateRoot",
        "controls", "completedPhases", "originals", "contractControls", "contractFiles"}, "Incremental SDK spec")
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
            "artifactBytes"} | (set() if contract else {"jobName", "inventoryCommit"}), "Incremental native source")
        validate_producer(source["producer"])
        native._commit(source["workflowSha"])
        native.require_sha256(source["artifactSha256"], "Incremental original upload")
        for field in ("jobId", "artifactId", "artifactBytes"):
            if type(source[field]) is not int or source[field] <= 0:
                raise ValueError("Incremental native source has invalid positive identity")
        if source["artifactBytes"] > LIMIT:
            raise ValueError("Incremental controls exceed the bounded original upload")
    if (spec["stateRoot"] != "product-resume-state"
            or spec["source"]["jobName"] != "product-validation / product-resume"):
        raise ValueError("Incremental native source changes its successful resume contract")
    native._commit(spec["source"]["inventoryCommit"])
    for row in originals.values():
        require_exact_keys(row, set(IDENTITY) | {"artifactId", "artifactSha256", "jobId", "workflowSha"},
                           "Incremental original")
        native._commit(row["workflowSha"])
        native.require_sha256(row["artifactSha256"], "Incremental original digest")
        if any(type(row[key]) is not int or row[key] <= 0 for key in ("artifactId", "jobId")):
            raise ValueError("Incremental original identity is invalid")
    return originals


def _inventory_revision(spec, root):
    from products.inventory import run_git
    revision = spec["source"]["inventoryCommit"]
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
    validate_current(request, phases, receipts, root=root, revision=revision,
                     original_revision=_inventory_revision(spec, root))
    import product_reuse as products
    from products.restore import bounded_verify
    _contract_files(spec, proof["contractFiles"], sdk)
    with products._ci_observation_batch():
        source, contract, *expected_locators = bounded_verify(lambda observe: observe()[2], (
            lambda: observe_source(spec["source"], token),
            lambda: observe_source(spec["contractControls"], token, contract=True),
            *(lambda receipt=receipt: observe_original(originals[_identity(receipt)], receipt, token)
              for receipt in receipts)))
    if source != proof["source"]:
        raise ValueError("Incremental completed source changed")
    if contract != proof["contractSource"]:
        raise ValueError("Incremental Contract source changed")
    if expected_locators != proof["originals"]:
        raise ValueError("Incremental SDK original native observations changed")
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

    path = work / "completed-state.zip"
    source = download(spec["source"], path)
    with zipfile.ZipFile(path) as archive:
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
                         original_revision=_inventory_revision(spec, root))
        available = _records(request["availableObjects"], "Incremental original objects")
        members, locators, transferred = [], [], 0
        for number, phase in enumerate(phases):
            artifact, _, locator = observe_original(originals[_identity(phase)], receipts[number], token)
            locators.append(locator)
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
    report = {"downloadedOriginalBytes": spec["source"]["artifactBytes"] + spec["contractControls"]["artifactBytes"],
        "originalMemberRangeBytes": transferred,
        "verifiedObjectBytes": sum(row["bytes"] for row in members), "completedSdkPhases": len(phases) + 1,
        "seconds": str(time.perf_counter() - started), "productPhasesExecuted": 0}
    import json
    print(json.dumps(report), flush=True)
    return report
