"""Hold all 61 authenticated SDK originals for a no-secret campaign replay.

The protected caller selects the pins independently of the captured state and
runs the full SDK semantic verifier inside this context. This is neither a
release admission nor a signed catalog producer.
"""

from collections import Counter
from collections.abc import Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
from types import MappingProxyType

from ci.sdk_campaign_observation import ObservedSdkOriginal, held_sdk_campaign_observation
from ci.sdk_campaign_original_locator import (
    CUSTODY_SELECTION_KEYS, discover_fresh_sdk_original_pin,
    discover_reused_sdk_original_pins, discover_reused_sdk_original_pins_from_custody,
)
from ci.sdk_campaign_original_worker import held_fresh_sdk_worker_upload
from ci.sdk_campaign_reused_original import (
    _held_reused_sdk_original, held_completed_sdk_catalog, held_reused_sdk_catalog,
    held_reused_sdk_original, verify_completed_sdk_catalog_originals,
)
from products.index import IndexEntrySource
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, require_exact_keys,
    require_integer, require_sha256,
)
from products.registry import PhaseInstanceId
from products.receipt import validate_phase_receipt, validate_producer
from products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES, held_sdk_campaign_selection
from products.sdk_campaign_semantics import verify_sdk_campaign_semantics
from products.signing_isolation import require_no_signing_secret


@dataclass(frozen=True, slots=True)
class FreshSdkOriginalPin:
    receipt_sha256: str
    artifact_id: int
    artifact_sha256: str
    workflow_path: str
    job_name: str


@dataclass(frozen=True, slots=True)
class ReusedSdkOriginalPin:
    receipt_sha256: str
    original_artifact_id: int
    original_artifact_sha256: str
    catalog_artifact_id: int
    catalog_artifact_sha256: str
    catalog_public_key: Path
    catalog_public_key_sha256: str
    pull_request: int
    worker_workflow_path: str
    worker_job_name: str
    catalog_workflow_path: str
    catalog_job_name: str
    failed_catalog_producer_bytes: bytes | None = None
    catalog_workflow_sha: str | None = None


_FRESH_SELECTION_KEYS = {
    "producer", "expected_build_key", "expected_product_version",
    "trusted_workflow_path", "trusted_job_name",
}
_REUSED_SELECTION_KEYS = {
    "expected_build_key", "expected_product_version", "pull_request", "repository",
    "catalog_artifact_name", "catalog_public_key", "expected_public_key_sha256",
    "trusted_worker_workflow_path", "trusted_worker_job_name",
    "trusted_catalog_workflow_path", "trusted_catalog_job_name",
}
_CUSTODY_REUSED_SELECTION_KEYS = {
    "expected_build_key", "expected_product_version", "pull_request", "repository",
    "trusted_worker_workflow_path", "trusted_worker_job_name",
    "failed_catalog_producer", "custody_ref",
}
_COMPLETED_CATALOG_PIN_KEYS = {
    "producer", "artifact_name", "artifact_id", "artifact_sha256",
    "index_sha256", "public_key_sha256", "trusted_workflow_path",
    "trusted_job_name",
}


def discover_sdk_campaign_original_pins(fresh, reused, *, trusted_workflow_sha,
        token, environ, custody_catalogs=None):
    """Resolve caller-selected 61-phase authorities without campaign observations.

    The caller owns each build key/version/producer/catalog/key/workflow route.
    This is a no-secret transport locator, not SDK release admission.
    """
    require_no_signing_secret(environ)
    require_no_signing_secret(os.environ)
    if (not isinstance(fresh, Mapping) or not isinstance(reused, Mapping)
            or set(fresh) & set(reused)
            or set(fresh) | set(reused) != SDK_CAMPAIGN_INSTANCES):
        raise ValueError("SDK original pin discovery requires exactly 61 disjoint phase selections")
    custody_catalogs = {} if custody_catalogs is None else custody_catalogs
    if not isinstance(custody_catalogs, Mapping):
        raise ValueError("SDK custody catalogs require caller-owned selections")
    custody_refs = set()
    for request in reused.values():
        if isinstance(request, Mapping) and "custody_ref" in request:
            ref = request["custody_ref"]
            if type(ref) is not str or not ref:
                raise ValueError("SDK custody reference must be nonempty caller-owned text")
            custody_refs.add(ref)
    if set(custody_catalogs) != custody_refs:
        raise ValueError("SDK custody references must match exact caller-owned descriptors")
    custody_by_ref = {}
    custody_identities, destinations = set(), set()
    for ref, descriptor in custody_catalogs.items():
        descriptor = require_exact_keys(descriptor, {"selection", "destination"},
            "SDK custody descriptor")
        selection = dict(require_exact_keys(descriptor["selection"], CUSTODY_SELECTION_KEYS,
            "SDK custody selection"))
        destination = descriptor["destination"]
        if not isinstance(destination, Path):
            raise ValueError("SDK custody destination must be a caller-owned path")
        catalog_producer = validate_producer(selection["catalog_producer"])
        custody_producer = validate_producer(selection["custody_producer"])
        selection["catalog_producer"] = dict(catalog_producer)
        selection["custody_producer"] = dict(custody_producer)
        catalog_id = require_integer(selection["catalog_artifact_id"],
            "SDK custody catalog artifact ID", 1)
        custody_id = require_integer(selection["custody_artifact_id"],
            "SDK custody upload artifact ID", 1)
        require_sha256(selection["catalog_artifact_sha256"], "SDK custody catalog digest")
        require_sha256(selection["custody_artifact_sha256"], "SDK custody upload digest")
        identity = (canonical_json_bytes(catalog_producer), catalog_id,
            canonical_json_bytes(custody_producer), custody_id)
        if identity in custody_identities or destination in destinations:
            raise ValueError("SDK custody descriptor is duplicated")
        custody_identities.add(identity)
        destinations.add(destination)
        custody_by_ref[ref] = (selection, destination, catalog_producer)
    for instance, request in fresh.items():
        if not isinstance(instance, PhaseInstanceId):
            raise ValueError("Fresh SDK selection has invalid phase identity")
        require_exact_keys(request, _FRESH_SELECTION_KEYS, "Fresh SDK original selection")
    custody_requests = {}
    for instance, request in reused.items():
        if not isinstance(instance, PhaseInstanceId):
            raise ValueError("Reused SDK selection has invalid phase identity")
        if "custody_ref" in request:
            require_exact_keys(request, _CUSTODY_REUSED_SELECTION_KEYS,
                "Custody-backed SDK original selection")
            selection, _, producer = custody_by_ref[request["custody_ref"]]
            if (validate_producer(request["failed_catalog_producer"]) != producer
                    or request["repository"] != producer["repository"]
                    or request["pull_request"] != producer["pullRequest"]):
                raise ValueError("SDK custody phase differs from its caller-owned descriptor")
            custody_requests[instance] = {field: request[field]
                for field in _CUSTODY_REUSED_SELECTION_KEYS if field != "failed_catalog_producer"}
        else:
            require_exact_keys(request, _REUSED_SELECTION_KEYS |
                ({"failed_catalog_producer"} if "failed_catalog_producer" in request else set()),
                "Reused SDK original selection")
    pins = {instance: FreshSdkOriginalPin(**discover_fresh_sdk_original_pin(
        instance, **fresh[instance], trusted_workflow_sha=trusted_workflow_sha,
        token=token, environ=environ)) for instance in sorted(fresh)}
    shared_fields = ("pull_request", "repository", "catalog_artifact_name", "catalog_public_key",
        "expected_public_key_sha256", "trusted_catalog_workflow_path", "trusted_catalog_job_name")
    worker_fields = ("expected_build_key", "expected_product_version",
        "trusted_worker_workflow_path", "trusted_worker_job_name")
    groups = {}
    custody_groups = {}
    for instance in sorted(reused):
        request = custody_requests.get(instance, reused[instance])
        if instance in custody_requests:
            custody_groups.setdefault(request["custody_ref"], {})[instance] = {
                field: request[field] for field in worker_fields}
            continue
        failed = request.get("failed_catalog_producer")
        failed_bytes = (None if failed is None else
            canonical_json_bytes(validate_producer(failed)))
        common = tuple(request[field] for field in shared_fields) + (failed_bytes,)
        groups.setdefault(common, {})[instance] = {field: request[field] for field in worker_fields}
    for common, selections in groups.items():
        found = discover_reused_sdk_original_pins(selections,
            **dict(zip(shared_fields, common[:-1])),
            failed_catalog_producer=(None if common[-1] is None else
                validate_producer(load_canonical_json_bytes(common[-1]))),
            trusted_workflow_sha=trusted_workflow_sha,
            token=token, environ=environ)
        if set(found) != set(selections):
            raise ValueError("Reused SDK catalog discovery returned incomplete phases")
        pins.update({instance: ReusedSdkOriginalPin(**{
            **found[instance], "failed_catalog_producer_bytes": common[-1],
        }) for instance in selections})
    for ref, selections in custody_groups.items():
        selection, destination, producer = custody_by_ref[ref]
        found = discover_reused_sdk_original_pins_from_custody(selections,
            repository=producer["repository"], pull_request=producer["pullRequest"],
            trusted_workflow_sha=trusted_workflow_sha,
            custody_selection=selection, custody_destination=destination,
            token=token, environ=environ)
        if set(found) != set(selections):
            raise ValueError("Custody-backed SDK discovery returned incomplete phases")
        failed_bytes = canonical_json_bytes(producer)
        pins.update({instance: ReusedSdkOriginalPin(**{
            **found[instance], "failed_catalog_producer_bytes": failed_bytes,
            "catalog_workflow_sha": selection["catalog_workflow_sha"],
        }) for instance in selections})
    require_no_signing_secret(environ)
    return MappingProxyType(pins)


@contextmanager
def held_sdk_campaign_original_uploads(observations, current_transport_bytes, pins, *,
        trusted_workflow_sha, token, environ):
    """Hold exact original uploads across the caller's all-family semantic replay.

    The 61 pins must come from protected, independent policy/official discovery;
    deriving them from observations or replay records defeats this boundary.
    """
    require_no_signing_secret(environ)
    if (not isinstance(observations, Mapping) or not isinstance(pins, Mapping)
            or set(observations) != SDK_CAMPAIGN_INSTANCES
            or set(pins) != SDK_CAMPAIGN_INSTANCES
            or type(current_transport_bytes) is not bytes):
        raise ValueError("SDK original uploads require the exact 61 observed phases and pins")
    for instance in SDK_CAMPAIGN_INSTANCES:
        original, pin = observations[instance], pins[instance]
        if not isinstance(instance, PhaseInstanceId) or not isinstance(original, ObservedSdkOriginal):
            raise ValueError("SDK original upload has an invalid phase or observation")
        replay = load_canonical_json_bytes(original.replay_record_canonical)
        if not isinstance(replay, dict):
            raise ValueError("SDK original replay record is invalid")
        if replay.get("state") == "retained" and replay.get("source") is None:
            if type(pin) is not FreshSdkOriginalPin:
                raise ValueError("Retained SDK original requires a fresh upload pin")
            require_sha256(pin.receipt_sha256, "Fresh SDK receipt pin")
            require_sha256(pin.artifact_sha256, "Fresh SDK artifact pin")
            require_integer(pin.artifact_id, "Fresh SDK artifact ID", 1)
            if any(type(value) is not str or not value for value in (pin.workflow_path, pin.job_name)):
                raise ValueError("Fresh SDK workflow path and job must both be pinned")
        elif replay.get("state") == "reused" and replay.get("source") == "same-pr":
            if type(pin) is not ReusedSdkOriginalPin:
                raise ValueError("Reused SDK original requires a same-PR catalog pin")
            for label, digest in (("Reused SDK receipt", pin.receipt_sha256),
                                  ("Reused SDK original artifact", pin.original_artifact_sha256),
                                  ("Reused SDK catalog artifact", pin.catalog_artifact_sha256),
                                  ("Reused SDK catalog key", pin.catalog_public_key_sha256)):
                require_sha256(digest, label)
            for label, value in (("Reused SDK original artifact ID", pin.original_artifact_id),
                                 ("Reused SDK catalog artifact ID", pin.catalog_artifact_id),
                                 ("Reused SDK pull request", pin.pull_request)):
                require_integer(value, label, 1)
            if not isinstance(pin.catalog_public_key, Path):
                raise ValueError("Reused SDK catalog key requires an independent path")
            if any(type(value) is not str or not value for value in (
                    pin.worker_workflow_path, pin.worker_job_name,
                    pin.catalog_workflow_path, pin.catalog_job_name)):
                raise ValueError("Reused SDK worker and catalog workflow paths and jobs must be pinned")
            if pin.failed_catalog_producer_bytes is not None:
                if type(pin.failed_catalog_producer_bytes) is not bytes:
                    raise ValueError("Failed SDK catalog producer must be immutable canonical bytes")
                failed = validate_producer(load_canonical_json_bytes(pin.failed_catalog_producer_bytes))
                if canonical_json_bytes(failed) != pin.failed_catalog_producer_bytes or \
                        failed["event"] != "pull_request" or failed["pullRequest"] != pin.pull_request:
                    raise ValueError("Failed SDK catalog producer differs from pinned PR")
        else:
            raise ValueError("SDK original upload has no authenticated retained/same-PR route")

    catalog_fields = ("catalog_artifact_id", "catalog_artifact_sha256", "catalog_public_key",
        "catalog_public_key_sha256", "pull_request", "catalog_workflow_path", "catalog_job_name",
        "failed_catalog_producer_bytes", "catalog_workflow_sha")
    groups = Counter(tuple(getattr(pin, field) for field in catalog_fields)
        for pin in pins.values() if type(pin) is ReusedSdkOriginalPin)
    held, catalogs = {}, {}
    with ExitStack() as stack:
        for instance in sorted(SDK_CAMPAIGN_INSTANCES):
            original, pin = observations[instance], pins[instance]
            if type(pin) is FreshSdkOriginalPin:
                evidence, _ = stack.enter_context(held_fresh_sdk_worker_upload(
                    instance, original, current_transport_bytes,
                    expected_receipt_sha256=pin.receipt_sha256,
                    artifact_id=pin.artifact_id, artifact_sha256=pin.artifact_sha256,
                    trusted_workflow_sha=trusted_workflow_sha, token=token, environ=environ,
                    trusted_workflow_path=pin.workflow_path, trusted_job_name=pin.job_name))
            else:
                group = tuple(getattr(pin, field) for field in catalog_fields)
                shared = None
                if groups[group] > 1:
                    if group not in catalogs:
                        receipt = validate_phase_receipt(load_canonical_json_bytes(original.receipt_bytes))
                        catalogs[group] = stack.enter_context(held_reused_sdk_catalog(
                            repository=receipt["producer"]["repository"],
                            pull_request=pin.pull_request,
                            artifact_id=pin.catalog_artifact_id,
                            artifact_sha256=pin.catalog_artifact_sha256,
                            public_key=pin.catalog_public_key,
                            public_key_sha256=pin.catalog_public_key_sha256,
                            trusted_workflow_sha=pin.catalog_workflow_sha or trusted_workflow_sha,
                            trusted_workflow_path=pin.catalog_workflow_path,
                            trusted_job_name=pin.catalog_job_name,
                            failed_catalog_producer=(None if pin.failed_catalog_producer_bytes is None else
                                validate_producer(load_canonical_json_bytes(pin.failed_catalog_producer_bytes))),
                            token=token, environ=environ))
                    shared = catalogs[group]
                holder = _held_reused_sdk_original if shared is not None else held_reused_sdk_original
                shared_arg = {"_shared_catalog": shared} if shared is not None else {}
                evidence, _ = stack.enter_context(holder(
                    instance, original, current_transport_bytes,
                    expected_receipt_sha256=pin.receipt_sha256,
                    original_artifact_id=pin.original_artifact_id,
                    original_artifact_sha256=pin.original_artifact_sha256,
                    catalog_artifact_id=pin.catalog_artifact_id,
                    catalog_artifact_sha256=pin.catalog_artifact_sha256,
                    catalog_public_key=pin.catalog_public_key,
                    expected_public_key_sha256=pin.catalog_public_key_sha256,
                    pull_request=pin.pull_request,
                    trusted_workflow_sha=trusted_workflow_sha, token=token, environ=environ,
                    trusted_worker_workflow_path=pin.worker_workflow_path,
                    trusted_worker_job_name=pin.worker_job_name,
                    trusted_catalog_workflow_path=pin.catalog_workflow_path,
                    trusted_catalog_job_name=pin.catalog_job_name,
                    catalog_workflow_sha=pin.catalog_workflow_sha,
                    failed_catalog_producer=(None if pin.failed_catalog_producer_bytes is None else
                        validate_producer(load_canonical_json_bytes(pin.failed_catalog_producer_bytes))),
                    **shared_arg))
            held[instance] = evidence
        require_no_signing_secret(environ)
        try:
            yield MappingProxyType(held)
        finally:
            require_no_signing_secret(environ)


@contextmanager
def held_sdk_campaign_semantic_replay(observations, current_transport_bytes, pins,
        artifact_paths, semantic_controls, *, trusted_workflow_sha, token, environ):
    """Run all 61 existing family gates while exact original uploads remain held.

    This non-secret boundary grants neither release admission nor a signed index.
    Artifact paths and all producer/upload pins are caller-owned inputs.
    """
    if (not isinstance(artifact_paths, Mapping) or set(artifact_paths) != SDK_CAMPAIGN_INSTANCES
            or not isinstance(semantic_controls, Mapping)):
        raise ValueError("SDK semantic replay requires 61 caller-selected artifacts and controls")
    with held_sdk_campaign_original_uploads(observations, current_transport_bytes, pins,
            trusted_workflow_sha=trusted_workflow_sha, token=token, environ=environ) as evidence:
        sources, envelopes, archives, stages = {}, {}, {}, {}
        for instance in SDK_CAMPAIGN_INSTANCES:
            original = observations[instance]
            replay = load_canonical_json_bytes(original.replay_record_canonical)
            sources[instance] = IndexEntrySource(original.receipt_bytes, artifact_paths[instance])
            envelopes[instance] = {
                "receipt": load_canonical_json_bytes(original.receipt_bytes),
                "receiptBytes": original.receipt_bytes,
                "receiptSha256": replay["receiptSha256"],
                "objectSha256": replay["objectSha256"],
            }
            archives[instance], stages[instance] = original.object_path, original.stage_path
        with held_sdk_campaign_selection(sources, envelopes, archives, stages) as (
                held_sources, held_envelopes, held_stages, held_receipts):
            verified = verify_sdk_campaign_semantics(sources=held_sources,
                envelopes=held_envelopes, stages=held_stages, **semantic_controls)
            if verified != {instance: sources[instance].receipt_bytes for instance in SDK_CAMPAIGN_INSTANCES}:
                raise ValueError("SDK semantic replay changed an original receipt")
            require_no_signing_secret(environ)
            yield MappingProxyType(verified), evidence


@contextmanager
def held_completed_sdk_campaign_replay(observations, current_transport_bytes, pins,
        artifact_paths, semantic_controls, *, completed_catalog_pin,
        trusted_workflow_sha, token, environ):
    """Join the current signed catalog to all original-worker and family gates.

    The caller must select the catalog and every worker pin independently. This
    no-secret replay does not mint release admission.
    """
    pin = require_exact_keys(completed_catalog_pin, _COMPLETED_CATALOG_PIN_KEYS,
        "Completed SDK catalog pin")
    with held_completed_sdk_catalog(**pin, trusted_workflow_sha=trusted_workflow_sha,
            token=token, environ=environ) as catalog:
        verify_completed_sdk_catalog_originals(catalog, observations, artifact_paths)
        with held_sdk_campaign_semantic_replay(observations, current_transport_bytes,
                pins, artifact_paths, semantic_controls,
                trusted_workflow_sha=trusted_workflow_sha,
                token=token, environ=environ) as verified:
            yield verified


@contextmanager
def held_sdk_campaign_candidate(plan_path, *, state_artifact_id,
        state_artifact_sha256, state_wave, sdk_state_wave, repository_root,
        fresh_selections, reused_selections, artifact_paths, semantic_controls,
        completed_catalog_pin, trusted_workflow_sha, token, environ,
        custody_catalogs=None,
        sdk_validation_tooling=None, sdk_apple_validation_policy=None,
        sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Replay caller-selected current state and 61 originals without release trust."""
    require_no_signing_secret(environ)
    require_no_signing_secret(os.environ)
    selected_catalog = require_exact_keys(completed_catalog_pin,
        _COMPLETED_CATALOG_PIN_KEYS, "Completed SDK catalog pin")
    selected_producer = validate_producer(selected_catalog["producer"])
    with held_sdk_campaign_observation(plan_path, artifact_id=state_artifact_id,
            artifact_sha256=state_artifact_sha256,
            state_wave=state_wave, sdk_state_wave=sdk_state_wave,
            repository_root=repository_root, environ=environ, token=token,
            sdk_validation_tooling=sdk_validation_tooling,
            sdk_apple_validation_policy=sdk_apple_validation_policy,
            sdk_facade_metadata_admission=sdk_facade_metadata_admission,
            sdk_android_metadata_admission=sdk_android_metadata_admission,
            trusted_workflow_sha=trusted_workflow_sha) as (transport, observations):
        current = load_canonical_json_bytes(transport)
        if (not isinstance(current, dict) or "captureProducer" not in current
                or validate_producer(current["captureProducer"]) != selected_producer):
            raise ValueError("SDK campaign state differs from independently selected producer")
        pins = discover_sdk_campaign_original_pins(fresh_selections, reused_selections,
            trusted_workflow_sha=trusted_workflow_sha, token=token, environ=environ,
            custody_catalogs=custody_catalogs)
        with held_completed_sdk_campaign_replay(observations, transport, pins,
                artifact_paths, semantic_controls,
                completed_catalog_pin=selected_catalog,
                trusted_workflow_sha=trusted_workflow_sha,
                token=token, environ=environ) as verified:
            yield verified


@contextmanager
def held_sdk_campaign_candidate_from_election(plan_path, *, policy_files,
        expected_election_sha256, **candidate_options):
    """Pin all 61 caller elections before the first state observation.

    The caller must source the three digests independently from protected
    policy. Original uploads, semantic controls and release trust remain the
    existing downstream gates; this wrapper grants none of them by itself.
    """
    if {"fresh_selections", "reused_selections"} & set(candidate_options):
        raise ValueError("Pinned SDK election cannot be replaced by caller selections")
    from ci.sdk_campaign_pinned_election import held_pinned_sdk_campaign_election
    with held_pinned_sdk_campaign_election(policy_files, expected_election_sha256) as (
            fresh, reused):
        with held_sdk_campaign_candidate(plan_path, fresh_selections=fresh,
                reused_selections=reused, **candidate_options) as verified:
            yield verified


@contextmanager
def held_sdk_campaign_candidate_from_policies(plan_path, *, election_files,
        expected_election_sha256, semantic_files, expected_semantic_sha256,
        **candidate_options):
    """Pin exact original elections and typed semantics before observation."""
    if {"fresh_selections", "reused_selections", "semantic_controls"} & set(candidate_options):
        raise ValueError("Pinned SDK campaign policies cannot be replaced by caller controls")
    from ci.sdk_campaign_pinned_election import (
        held_pinned_sdk_campaign_election, held_pinned_sdk_campaign_semantics,
    )
    with held_pinned_sdk_campaign_election(election_files, expected_election_sha256) as (
            fresh, reused), held_pinned_sdk_campaign_semantics(
            semantic_files, expected_semantic_sha256) as controls:
        semantics = dict(controls)
        semantics["android_control"] = {**controls["android_control"],
            "token": candidate_options["token"], "environ": candidate_options["environ"]}
        with held_sdk_campaign_candidate(plan_path, fresh_selections=fresh,
                reused_selections=reused, semantic_controls=semantics,
                **candidate_options) as verified:
            yield verified
