"""Locate one fresh SDK original upload; content and release admission stay separate."""

from collections.abc import Mapping
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci.sdk_campaign_observation import ObservedSdkOriginal
from sdk_apple_upload_locator import _locate
from sdk_facade_capture import _capture_route
import product_reuse as products
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_exact_keys, require_integer, require_relative_path, require_semver,
    require_sha256, regular_file_inventory, sha256_bytes,
    sha256_file, verified_zip_contents,
)
from products.index import SignedProductIndex, _verify_index_receipt, verify_signed_product_index
from products.receipt import validate_phase_receipt, validate_producer
from products.registry import PhaseInstanceId
from products.restore import verify_object, verify_phase_shard
from products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from products.signing_isolation import require_no_signing_secret


def fresh_sdk_worker_route(instance, receipt):
    """Return the fixed original workflow job and upload name for one phase."""
    if instance.component == "sdk-android":
        if instance.phase not in ("binary", "package", "validation", "metadata") or instance.target != "android":
            raise ValueError("SDK Android original route requires one exact worker phase")
        job = (f"product-validation / sdk-android-{instance.phase}-result / "
               f"sdk-android-{instance.phase}-android")
        producer = receipt["producer"]
        name = (f"codex-agent-sdk-worker-sdk-android-{instance.phase}-android-"
                f"{receipt['buildKey'].removeprefix('sha256:')}-{producer['tree']}-attempt-{producer['runAttempt']}")
        return job, name
    if instance.component == "sdk-core":
        routed, _, _, job, name, _ = _capture_route(receipt)
        if routed != instance:
            raise ValueError("SDK Core original route differs from selected phase")
        return job, name
    stem = f"{instance.component}-{instance.phase}-{instance.target}"
    producer = receipt["producer"]
    return (f"product-validation / sdk-{stem}",
            f"codex-agent-sdk-worker-{stem}-{receipt['buildKey'].removeprefix('sha256:')}-"
            f"{producer['tree']}-attempt-{producer['runAttempt']}")


def original_workflow_route(phase, default_job, sha, path=None, job=None):
    """Keep a caller-pinned child path and job paired at the original-run gate."""
    if (path is None) != (job is None):
        raise ValueError("SDK original workflow path and job must be pinned together")
    if path is None:
        return default_job, {"trusted_workflow_sha": sha}
    if type(job) is not str or not job:
        raise ValueError("SDK original workflow job must be caller-pinned text")
    return job, {"trusted_workflows_by_phase": {phase: {"path": path, "sha": sha}}}


def failed_sdk_partial_catalog_name(producer):
    """Keep failed-run cache artifacts outside the completed-catalog namespace."""
    producer = validate_producer(producer)
    if producer["event"] != "pull_request":
        raise ValueError("Partial SDK catalog requires a pull-request producer")
    return (f"codex-agent-sdk-partial-catalog-v1-pull-request-{producer['pullRequest']}-"
            f"{producer['tree']}-attempt-{producer['runAttempt']}")


_EARLY_JS_CATALOG_PATH = ".github/workflows/sdk-javascript-validation.yml"
_EARLY_JS_CATALOG_JOB = "product-validation / sdk-javascript-wave / sdk-partial-catalog"


def failed_sdk_early_js_partial_catalog_name(producer):
    """Reserve a distinct failed-attempt name for the future early JS child."""
    producer = validate_producer(producer)
    if producer["event"] != "pull_request":
        raise ValueError("Early JS partial SDK catalog requires a pull-request producer")
    return (f"codex-agent-sdk-early-js-partial-catalog-v1-pull-request-{producer['pullRequest']}-"
            f"{producer['tree']}-attempt-{producer['runAttempt']}")


def require_failed_sdk_partial_catalog_route(producer, artifact_name, workflow_path, job_name):
    """Bind the caller's name and workflow pair before retrieving catalog bytes."""
    if artifact_name == failed_sdk_partial_catalog_name(producer):
        return artifact_name
    if artifact_name == failed_sdk_early_js_partial_catalog_name(producer):
        if workflow_path != _EARLY_JS_CATALOG_PATH or job_name != _EARLY_JS_CATALOG_JOB:
            raise ValueError("Early JS partial SDK catalog requires its exact child workflow and job")
        return artifact_name
    raise ValueError("Partial SDK catalog differs from its caller-pinned namespace")


def materialize_failed_sdk_partial_catalog(artifact, destination, *, producer,
        repository, pull_request, public_key, public_key_sha256,
        trusted_workflow_sha, trusted_workflow_path, trusted_job_name, token):
    """Admit only a signed partial cache from a failed run's successful catalog job."""
    producer = validate_producer(producer)
    name = require_failed_sdk_partial_catalog_route(producer, artifact.get("name"),
        trusted_workflow_path, trusted_job_name)
    if (producer["repository"] != repository or producer["pullRequest"] != pull_request
            or not trusted_workflow_path or not trusted_job_name):
        raise ValueError("Partial SDK catalog differs from independent producer or route")
    artifact_id = require_integer(artifact.get("id"), "Partial SDK catalog artifact ID", 1)
    url = f"https://api.github.com/repos/{repository}/actions/artifacts/{artifact_id}"
    if (artifact.get("name") != name or artifact.get("expired") is not False
            or artifact.get("archive_download_url") != url + "/zip"
            or not isinstance(artifact.get("workflow_run"), dict)
            or artifact["workflow_run"].get("id") != producer["runId"]):
        raise ValueError("Partial SDK catalog differs from its exact failed attempt")
    digest = require_sha256(artifact.get("digest"), "Partial SDK catalog artifact digest")
    size = require_integer(artifact.get("size_in_bytes"), "Partial SDK catalog size", 1)
    if size > products._CATALOG_LIMIT:
        raise ValueError("Partial SDK catalog exceeds transport limit")
    key = read_regular_file_bytes(public_key, max_bytes=64 * 1024, reject_symlink_parents=True)
    if sha256_bytes(key) != require_sha256(public_key_sha256, "Partial SDK catalog key digest"):
        raise ValueError("Partial SDK catalog key differs from independent digest")
    catalog_root = destination / "catalogs/same-pr" / str(artifact_id)
    catalog_root.mkdir(parents=True)
    archive = catalog_root / "transport.zip"
    products.download_artifact_to_file(artifact, token, archive, max_bytes=products._CATALOG_LIMIT)
    if archive.stat().st_size != size or sha256_file(archive) != digest:
        raise ValueError("Partial SDK catalog differs from official artifact bytes")
    zipped, _, _ = verified_zip_contents(archive, retained_paths=(),
        allow_empty_members=True, **products._CATALOG_ZIP_LIMITS)
    extracted = catalog_root / "contents"
    products.safe_extract(archive, extracted)
    if regular_file_inventory(extracted) != zipped:
        raise ValueError("Partial SDK catalog extraction differs from official upload")
    if read_regular_file_bytes(extracted / "public-key.pub", max_bytes=64 * 1024,
            reject_symlink_parents=True) != key:
        raise ValueError("Partial SDK catalog embedded key differs from independent policy")
    index, _ = verify_signed_product_index(SignedProductIndex(
        extracted / "product-index.json", extracted / "product-index.sig"), Path(public_key))
    instances = [PhaseInstanceId(*(entry[field] for field in
        ("product", "component", "phase", "target"))) for entry in index["entries"]]
    if (index["producer"] != producer or index["repository"] != repository
            or index["trustDomain"] != "development"
            or not instances or len(instances) >= len(SDK_CAMPAIGN_INSTANCES)
            or len(set(instances)) != len(instances)
            or not set(instances) <= SDK_CAMPAIGN_INSTANCES):
        raise ValueError("Partial SDK catalog is not an exact incomplete SDK selection")
    job, policy = original_workflow_route("catalog", trusted_job_name,
        trusted_workflow_sha, trusted_workflow_path, trusted_job_name)
    observed = products._observe_ci_producer_jobs({"catalog": producer},
        jobs_by_phase={"catalog": job}, token=token, **policy)
    if (len(observed) != 1 or observed[0]["run"].get("status") != "completed"
            or observed[0]["run"].get("conclusion") != "failure"
            or artifact["workflow_run"].get("head_sha") != observed[0]["run"].get("head_sha")):
        raise ValueError("Partial SDK catalog lacks its failed run and successful original job")
    products._require_artifact_job_window(observed[0], job, artifact)
    catalog = products._read_catalog_directory("same-pr", extracted, destination, None,
        repository=repository, pull_request=pull_request, provenance_root=catalog_root,
        artifact=artifact, token=token, workflow_run={
            "run": observed[0]["run"], "testedCommit": observed[0]["testedCommit"]},
        api="https://api.github.com")
    if catalog.index != index:
        raise ValueError("Partial SDK catalog changed during verification")
    return catalog, observed[0]


def discover_fresh_sdk_original_pin(instance, *, producer, expected_build_key,
        expected_product_version, trusted_workflow_sha, trusted_workflow_path,
        trusted_job_name, token, environ=None):
    """Derive a fresh receipt pin from its official upload, never campaign state.

    The caller supplies the exact phase, build key, version, current producer and
    reviewed workflow route independently. This is a non-secret locator only;
    the 61-original holder still re-downloads and verifies the complete shard.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if not isinstance(instance, PhaseInstanceId) or instance not in SDK_CAMPAIGN_INSTANCES:
        raise ValueError("Fresh SDK pin discovery requires one registered SDK phase")
    producer = validate_producer(producer)
    require_sha256(expected_build_key, "Independent SDK build key")
    if (type(expected_product_version) is not str or not expected_product_version
            or type(token) is not str or not token
            or type(trusted_workflow_path) is not str or not trusted_workflow_path
            or type(trusted_job_name) is not str or not trusted_job_name):
        raise ValueError("Fresh SDK pin discovery requires independent version, token and workflow route")
    _, name = fresh_sdk_worker_route(instance, {
        **{field: getattr(instance, field) for field in ("product", "component", "phase", "target")},
        "buildKey": expected_build_key, "producer": producer,
    })
    job, policy = original_workflow_route("worker", trusted_job_name,
        trusted_workflow_sha, trusted_workflow_path, trusted_job_name)
    pin = _locate(producer, phase="worker", job=job, name=name, token=token,
                  trusted_workflows_by_phase=policy["trusted_workflows_by_phase"])
    observed = products._observe_ci_producer_jobs(
        {"worker": producer}, jobs_by_phase={"worker": job}, token=token, **policy)[0]
    with tempfile.TemporaryDirectory(prefix="sdk-original-pin-") as temporary:
        archive = Path(temporary) / "original-upload.zip"
        artifact, _ = products._download_contract_ci_upload(
            pin["artifact_id"], pin["artifact_sha256"], name, producer,
            observed["run"], token, destination=archive)
        products._require_artifact_job_window(observed, job, artifact)
        _, retained, _ = verified_zip_contents(
            archive, retained_paths=("shard/phase-receipt.json",),
            max_retained_bytes=16 * 1024 * 1024, allow_empty_members=True,
            **products._CATALOG_ZIP_LIMITS)
        receipt_bytes = retained.get("shard/phase-receipt.json")
        if receipt_bytes is None:
            raise ValueError("Fresh SDK original upload lacks its phase receipt")
        receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
        if (tuple(receipt[field] for field in ("product", "component", "phase", "target"))
                != tuple(getattr(instance, field) for field in ("product", "component", "phase", "target"))
                or receipt["buildKey"] != expected_build_key
                or receipt["productVersion"] != expected_product_version
                or receipt["producer"] != producer
                or receipt["trustDomain"] != "development"):
            raise ValueError("Fresh SDK original upload differs from independent phase identity")
    require_no_signing_secret(environment)
    return {"receipt_sha256": sha256_bytes(receipt_bytes),
            "artifact_id": pin["artifact_id"], "artifact_sha256": pin["artifact_sha256"],
            "workflow_path": trusted_workflow_path, "job_name": trusted_job_name}


def discover_reused_sdk_original_pins(selections, *, pull_request, repository,
        catalog_artifact_name, catalog_public_key,
        expected_public_key_sha256, trusted_workflow_sha,
        trusted_catalog_workflow_path, trusted_catalog_job_name,
        token, environ=None, failed_catalog_producer=None):
    """Select same-PR originals from one held authenticated catalog snapshot.

    Every phase key/version/worker route and the shared catalog/key/PR policy
    come from the caller, never from the current campaign's replay state.
    Failed-run partial catalogs require a separate caller-pinned producer.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    if not isinstance(selections, Mapping) or not selections:
        raise ValueError("Reused SDK pin discovery requires selected phases")
    for instance, selection in selections.items():
        if not isinstance(instance, PhaseInstanceId) or instance not in SDK_CAMPAIGN_INSTANCES:
            raise ValueError("Reused SDK pin discovery requires registered phases")
        selection = require_exact_keys(selection, {
            "expected_build_key", "expected_product_version",
            "trusted_worker_workflow_path", "trusted_worker_job_name",
        }, "Reused SDK phase selection")
        require_sha256(selection["expected_build_key"], "Independent SDK build key")
        require_semver(selection["expected_product_version"], "Independent SDK version")
        if not selection["trusted_worker_workflow_path"] or not selection["trusted_worker_job_name"]:
            raise ValueError("Reused SDK pin discovery requires reviewed worker route")
    require_sha256(expected_public_key_sha256, "Independent catalog public key")
    require_integer(pull_request, "Independent pull request", 1)
    if type(token) is not str or not token:
        raise ValueError("Reused SDK pin discovery requires an observation token")
    require_relative_path(repository, "Independent repository")
    if repository.count("/") != 1:
        raise ValueError("Independent repository must be an owner/repository pair")
    prefix = f"{products._CATALOG_PREFIX}pull-request-{pull_request}-"
    failed = (None if failed_catalog_producer is None else
              validate_producer(failed_catalog_producer))
    if type(catalog_artifact_name) is not str:
        raise ValueError("Reused SDK catalog requires a caller-pinned same-PR artifact name")
    if failed is not None:
        require_failed_sdk_partial_catalog_route(failed, catalog_artifact_name,
            trusted_catalog_workflow_path, trusted_catalog_job_name)
    elif not catalog_artifact_name.startswith(prefix) or not catalog_artifact_name[len(prefix):]:
        raise ValueError("Reused SDK catalog requires a caller-pinned same-PR artifact name")
    catalog_job, catalog_policy = original_workflow_route("catalog", trusted_catalog_job_name,
        trusted_workflow_sha, trusted_catalog_workflow_path, trusted_catalog_job_name)
    if not all((trusted_catalog_workflow_path, trusted_catalog_job_name)):
        raise ValueError("Reused SDK pin discovery requires reviewed catalog route")
    pinned_key = read_regular_file_bytes(Path(catalog_public_key), max_bytes=64 * 1024,
        reject_symlink_parents=True)
    if sha256_bytes(pinned_key) != expected_public_key_sha256:
        raise ValueError("Reused SDK catalog key differs from independent digest")
    api = "https://api.github.com"
    listed = products.paginated_items(f"{api}/repos/{repository}/actions/artifacts", "artifacts", token)
    candidates = [row for row in listed if isinstance(row, dict)
                  and row.get("name") == catalog_artifact_name
                  and row.get("expired") is False]
    if not candidates:
        raise ValueError("Reused SDK has no exact same-PR catalog")
    if failed is not None and len(candidates) != 1:
        raise ValueError("Partial SDK catalog official listing is ambiguous")
    candidates.sort(key=lambda row: require_integer(row.get("id"), "Catalog artifact ID", 1),
                    reverse=True)
    if len(candidates) > 1 and candidates[0]["id"] == candidates[1]["id"]:
        raise ValueError("Reused SDK catalog listing has duplicate latest ID")
    listed_artifact = candidates[0]
    artifact_id = listed_artifact["id"]
    detail_url = f"{api}/repos/{repository}/actions/artifacts/{artifact_id}"
    detail = products.api_json(detail_url, token)
    if (not isinstance(detail, dict) or detail.get("id") != artifact_id
            or detail.get("name") != catalog_artifact_name or detail.get("expired") is not False
            or detail.get("digest") != listed_artifact.get("digest")
            or detail.get("archive_download_url") != f"{detail_url}/zip"):
        raise ValueError("Reused SDK catalog detail differs from official listing")
    catalog_sha = require_sha256(detail["digest"], "Official SDK catalog digest")
    with tempfile.TemporaryDirectory(prefix="sdk-reused-pin-") as temporary:
        root = Path(temporary).resolve()
        if failed is None:
            catalog = products._materialize_catalog("same-pr", detail, token, root,
                repository, pull_request, None, api=api)
        else:
            catalog, _ = materialize_failed_sdk_partial_catalog(detail, root,
                producer=failed, repository=repository, pull_request=pull_request,
                public_key=catalog_public_key, public_key_sha256=expected_public_key_sha256,
                trusted_workflow_sha=trusted_workflow_sha,
                trusted_workflow_path=trusted_catalog_workflow_path,
                trusted_job_name=trusted_catalog_job_name, token=token)
        extracted = root / "catalogs" / "same-pr" / str(artifact_id) / "contents"
        if read_regular_file_bytes(extracted / "public-key.pub", max_bytes=64 * 1024,
                reject_symlink_parents=True) != pinned_key:
            raise ValueError("Reused SDK catalog key differs from independent policy")
        index, index_bytes = verify_signed_product_index(SignedProductIndex(
            extracted / "product-index.json", extracted / "product-index.sig"), Path(catalog_public_key))
        if index != catalog.index:
            raise ValueError("Reused SDK catalog changed during signed verification")
        if failed is None:
            observed_catalog = products._observe_ci_producer_jobs(
                {"catalog": index["producer"]}, jobs_by_phase={"catalog": catalog_job},
                token=token, **catalog_policy)
            products._require_artifact_job_window(observed_catalog[0], catalog_job, detail)
        pins = {}
        for position, instance in enumerate(sorted(selections)):
            selection = selections[instance]
            expected_build_key = selection["expected_build_key"]
            expected_product_version = selection["expected_product_version"]
            worker_job, worker_policy = original_workflow_route("worker",
                selection["trusted_worker_job_name"], trusted_workflow_sha,
                selection["trusted_worker_workflow_path"], selection["trusted_worker_job_name"])
            entries = [entry for entry in index["entries"]
                       if (entry["product"], entry["component"], entry["phase"], entry["target"])
                       == (instance.product, instance.component, instance.phase, instance.target)
                       and entry["buildKey"] == expected_build_key
                       and entry["productVersion"] == expected_product_version]
            if len(entries) != 1:
                raise ValueError("Reused SDK catalog lacks one exact phase entry")
            entry = entries[0]
            original_object = catalog.objects.get(expected_build_key)
            if original_object is None:
                raise ValueError("Reused SDK catalog lacks original object")
            selected = verify_object(original_object, build_key=expected_build_key,
                receipt_sha256=entry["receiptSha256"])
            _verify_index_receipt(entry, {**selected, "receiptSha256": entry["receiptSha256"]})
            receipt = validate_phase_receipt(load_canonical_json_bytes(selected["receiptBytes"]))
            producer = receipt["producer"]
            if producer["repository"] != repository or producer["pullRequest"] != pull_request:
                raise ValueError("Reused SDK receipt differs from independent PR/repository")
            _, worker_name = fresh_sdk_worker_route(instance, receipt)
            worker_pin = _locate(producer, phase="worker", job=worker_job, name=worker_name,
                token=token, **worker_policy)
            observed_worker = products._observe_ci_producer_jobs(
                {"worker": producer}, jobs_by_phase={"worker": worker_job},
                token=token, **worker_policy)
            with tempfile.TemporaryDirectory(prefix=f"original-worker-{position}-", dir=root) as worker_temp:
                worker_temp = Path(worker_temp)
                worker_archive = worker_temp / "transport.zip"
                worker_artifact, _ = products._download_contract_ci_upload(
                    worker_pin["artifact_id"], worker_pin["artifact_sha256"], worker_name,
                    producer, observed_worker[0]["run"], token, destination=worker_archive)
                products._require_artifact_job_window(observed_worker[0], worker_job, worker_artifact)
                verified_zip_contents(worker_archive, retained_paths=(), allow_empty_members=True,
                    **products._CATALOG_ZIP_LIMITS)
                worker_root = worker_temp / "original"
                products.safe_extract(worker_archive, worker_root)
                shard = verify_phase_shard(worker_root / "shard", instance)
                if (shard["receiptBytes"] != selected["receiptBytes"]
                        or sha256_file(worker_root / "shard" / shard["objectPath"])
                        != sha256_file(original_object)):
                    raise ValueError("Reused SDK worker upload differs from signed catalog original")
            pins[instance] = {"receipt_sha256": entry["receiptSha256"],
                "original_artifact_id": worker_pin["artifact_id"],
                "original_artifact_sha256": worker_pin["artifact_sha256"],
                "catalog_artifact_id": artifact_id, "catalog_artifact_sha256": catalog_sha,
                "catalog_public_key": Path(catalog_public_key),
                "catalog_public_key_sha256": expected_public_key_sha256,
                "pull_request": pull_request,
                "worker_workflow_path": selection["trusted_worker_workflow_path"],
                "worker_job_name": worker_job,
                "catalog_workflow_path": trusted_catalog_workflow_path,
                "catalog_job_name": catalog_job}
    require_no_signing_secret(environment)
    return pins


def discover_reused_sdk_original_pin(instance, *, expected_build_key,
        expected_product_version, pull_request, repository, catalog_artifact_name,
        catalog_public_key, expected_public_key_sha256, trusted_workflow_sha,
        trusted_worker_workflow_path, trusted_worker_job_name,
        trusted_catalog_workflow_path, trusted_catalog_job_name,
        token, environ=None):
    """Single-phase convenience route; campaign callers use the batched route."""
    return discover_reused_sdk_original_pins({instance: {
        "expected_build_key": expected_build_key,
        "expected_product_version": expected_product_version,
        "trusted_worker_workflow_path": trusted_worker_workflow_path,
        "trusted_worker_job_name": trusted_worker_job_name,
    }}, pull_request=pull_request, repository=repository,
        catalog_artifact_name=catalog_artifact_name,
        catalog_public_key=catalog_public_key,
        expected_public_key_sha256=expected_public_key_sha256,
        trusted_workflow_sha=trusted_workflow_sha,
        trusted_catalog_workflow_path=trusted_catalog_workflow_path,
        trusted_catalog_job_name=trusted_catalog_job_name,
        token=token, environ=environ)[instance]


def locate_fresh_sdk_original_upload(instance, original, *, expected_receipt_sha256,
        trusted_workflow_sha, token, environ=None,
        trusted_workflow_path=None, trusted_job_name=None):
    """Return an official ID/digest for an independently selected retained receipt.

    The caller supplies the original receipt digest independently of the held
    state. This locator never accepts a claimed artifact ID, name, or path from
    that state. The consumer must still download and verify the exact upload.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if environment is not os.environ:
        require_no_signing_secret(os.environ)
    if type(token) is not str or not token:
        raise ValueError("SDK original locator requires an observation token")
    require_sha256(expected_receipt_sha256, "Caller-selected SDK receipt")
    if not isinstance(instance, PhaseInstanceId) or instance not in SDK_CAMPAIGN_INSTANCES:
        raise ValueError("SDK original locator requires one registered phase")
    if not isinstance(original, ObservedSdkOriginal):
        raise ValueError("SDK original locator requires one held original")
    receipt_bytes = original.receipt_bytes
    replay_bytes = original.replay_record_canonical
    if sha256_bytes(receipt_bytes) != expected_receipt_sha256:
        raise ValueError("SDK original receipt differs from independent caller selection")
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    replay = require_exact_keys(load_canonical_json_bytes(replay_bytes),
        products._REUSE_PHASE_KEYS, "SDK original replay phase")
    identity = tuple(getattr(instance, field) for field in ("product", "component", "phase", "target"))
    if (canonical_json_bytes(receipt) != receipt_bytes
            or canonical_json_bytes(replay) != replay_bytes
            or tuple(receipt[field] for field in ("product", "component", "phase", "target")) != identity
            or tuple(replay[field] for field in ("product", "component", "phase", "target")) != identity
            or replay["state"] != "retained" or replay["source"] is not None
            or replay["transportSource"] is not None or replay["misses"]
            or replay["buildKey"] != receipt["buildKey"]
            or replay["receiptSha256"] != expected_receipt_sha256):
        raise ValueError("SDK original locator requires the exact retained phase")
    producer = receipt["producer"]
    default_job, name = fresh_sdk_worker_route(instance, receipt)
    job, policy = original_workflow_route("worker", default_job, trusted_workflow_sha,
        trusted_workflow_path, trusted_job_name)
    result = _locate(producer, phase="worker", job=job, name=name,
        token=token, **policy)
    require_no_signing_secret(environment)
    if (original.receipt_bytes != receipt_bytes or original.replay_record_canonical != replay_bytes
            or sha256_bytes(receipt_bytes) != expected_receipt_sha256):
        raise ValueError("SDK original receipt changed during lookup")
    return result
