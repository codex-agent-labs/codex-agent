"""Prepare an SDK release index without a key; sign only independently approved bytes.

The two functions belong in different processes. In particular, the protected
signer never receives a GitHub observation token or replays candidate tooling.
The expected index digest must come from protected approval, not this module's
preparation result or the development catalog.
"""

from collections.abc import Mapping
import os
from pathlib import Path
import tempfile

from products.aggregate import validate_product_index
from products.index import IndexEntrySource, _mint_release_admission, build_product_index
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, require_sha256, sha256_bytes,
)
from products.receipt import validate_phase_receipt, validate_producer
from products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from products.signatures import (
    load_keyring, public_key_for_metadata, require_active_release_key,
    sign_manifest, verify_manifest_signature,
)
from products.signing_isolation import require_no_signing_secret


_TOKEN_NAMES = frozenset({
    "GITHUB_TOKEN", "GH_TOKEN", "ACTIONS_RUNTIME_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
})
_CANDIDATE_OPTIONS = frozenset({
    "state_artifact_id", "state_artifact_sha256", "state_wave", "sdk_state_wave",
    "custody_catalogs", "sdk_validation_tooling", "sdk_apple_validation_policy",
    "sdk_facade_metadata_admission", "sdk_android_metadata_admission",
})
_REQUIRED_CANDIDATE_OPTIONS = frozenset({
    "state_artifact_id", "state_artifact_sha256", "state_wave", "sdk_state_wave",
})


def _release_key(keyring_path, keys_directory, expected_keyring_sha256):
    pinned = require_sha256(expected_keyring_sha256, "Protected SDK keyring digest")
    raw = read_regular_file_bytes(Path(keyring_path), max_bytes=64 * 1024,
        reject_symlink_parents=True)
    if sha256_bytes(raw) != pinned:
        raise ValueError("SDK signing keyring differs from protected pin")
    keyring = load_keyring(Path(keyring_path), Path(keys_directory))
    active, public_key = require_active_release_key(keyring, Path(keys_directory))
    signing = {name: keyring[name] for name in ("algorithm", "namespace", "trustDomain")}
    signing.update(active)
    return raw, signing, public_key


def prepare_sdk_release_index(plan_path, repository_root, *, authority_file,
        authority_artifact_id, authority_artifact_sha256, expected_authority_sha256,
        authority_workflow_sha, authority_workflow_path, authority_job_name,
        trusted_workflow_sha, election_files, semantic_files, token, environ,
        keyring_path, keys_directory, expected_keyring_sha256,
        repository, context, producer, **candidate_options):
    """Return unsigned canonical bytes only while the full official replay is held.

    Protected callers must supply the authority, keyring, workflow and policy
    pins independently of observed uploads. No raw receipt map is accepted.
    """
    require_no_signing_secret(environ)
    require_no_signing_secret(os.environ)
    if type(token) is not str or not token:
        raise ValueError("SDK release preparation requires an observation token")
    if set(candidate_options) - _CANDIDATE_OPTIONS or not _REQUIRED_CANDIDATE_OPTIONS <= set(candidate_options):
        raise ValueError("SDK release preparation accepts only its exact observation options")
    keyring_bytes, signing, _ = _release_key(
        keyring_path, keys_directory, expected_keyring_sha256)
    from ci.sdk_campaign_pinned_election import held_pinned_sdk_campaign_authority
    from ci.sdk_campaign_catalog_producer import held_sdk_campaign_candidate_from_official_authority

    with held_pinned_sdk_campaign_authority(Path(authority_file),
            expected_authority_sha256) as authority:
        with held_sdk_campaign_candidate_from_official_authority(plan_path,
                repository_root, authority_artifact_id=authority_artifact_id,
                authority_artifact_sha256=authority_artifact_sha256,
                expected_authority_sha256=expected_authority_sha256,
                authority_workflow_sha=authority_workflow_sha,
                authority_workflow_path=authority_workflow_path,
                authority_job_name=authority_job_name,
                trusted_workflow_sha=trusted_workflow_sha,
                election_files=election_files, semantic_files=semantic_files,
                token=token, environ=environ, **candidate_options) as (verified, _transport):
            receipts, _evidence = verified
            if not isinstance(receipts, Mapping) or set(receipts) != SDK_CAMPAIGN_INSTANCES:
                raise ValueError("Official SDK replay did not verify all 61 originals")
            current = validate_producer(producer)
            if (repository != current["repository"] or context.get("kind") != "pull-request"
                    or context.get("pullRequest") != current["pullRequest"]
                    or current != authority["completedCatalogPin"]["producer"]):
                raise ValueError("SDK release index differs from the approved PR producer")
            sources = []
            for instance in sorted(SDK_CAMPAIGN_INSTANCES):
                raw = receipts[instance]
                if type(raw) is not bytes:
                    raise ValueError("SDK replay returned a non-byte original receipt")
                receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
                original = receipt["producer"]
                if (receipt["productVersion"] != authority["sdkVersion"]
                        or original["repository"] != repository
                        or original["event"] not in {"push", "pull_request"}
                        or (original["event"] == "pull_request"
                            and original["pullRequest"] != current["pullRequest"])):
                    raise ValueError("SDK original differs from the protected campaign identity")
                path = authority["artifactPaths"][instance]
                source = IndexEntrySource(raw, path)
                admission = _mint_release_admission(source, receipt, raw,
                    (instance.product, instance.component, instance.phase, instance.target))
                sources.append(IndexEntrySource(raw, path, admission))
            index = build_product_index(sources, repository=repository,
                context=context, trust_domain="release", signing=signing,
                producer=current, stable_history=None)
            prepared = canonical_json_bytes(index)
        if read_regular_file_bytes(Path(keyring_path), max_bytes=64 * 1024,
                reject_symlink_parents=True) != keyring_bytes:
            raise ValueError("SDK signing keyring changed during preparation")
    return prepared


def stage_prepared_sdk_release_index(prepared: bytes, destination: Path):
    """Retain one exact no-secret candidate for later, independently approved signing.

    This does not return an approval digest or grant admission.
    """
    require_no_signing_secret(os.environ)
    if type(prepared) is not bytes or len(prepared) > 16 * 1024 * 1024:
        raise ValueError("Prepared SDK index bytes are missing or oversized")
    index = validate_product_index(load_canonical_json_bytes(prepared))
    if (canonical_json_bytes(index) != prepared or index["trustDomain"] != "release"
            or index["context"]["kind"] != "pull-request"
            or len(index["entries"]) != len(SDK_CAMPAIGN_INSTANCES)):
        raise ValueError("Prepared SDK index is not the exact release campaign candidate")
    digest = sha256_bytes(prepared)
    with tempfile.TemporaryDirectory(prefix="sdk-release-prepare-") as temporary:
        staged = Path(temporary).resolve() / "index"
        staged.mkdir()
        (staged / "product-index.json").write_bytes(prepared)
        publish_regular_tree(staged, Path(destination), expected_inventory=[{
            "relativePath": "product-index.json", "bytes": len(prepared), "sha256": digest,
        }])
    return Path(destination) / "product-index.json"


def sign_approved_sdk_release_index(prepared_index: Path, *, expected_index_sha256,
        keyring_path: Path, keys_directory: Path, expected_keyring_sha256,
        private_key: Path, environ: Mapping[str, str]):
    """Sign exactly an independently approved all-61 index, without observation.

    The protected caller must obtain ``expected_index_sha256`` independently
    from its approval authority; deriving it from ``prepared_index`` here would
    make this a self-certifying development-catalog signer.
    """
    if _TOKEN_NAMES & (set(environ) | set(os.environ)):
        raise ValueError("SDK signing process must not have an observation token")
    approved = require_sha256(expected_index_sha256, "Protected SDK index digest")
    keyring_bytes, signing, public_key = _release_key(
        keyring_path, keys_directory, expected_keyring_sha256)
    path = Path(prepared_index)
    raw = read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
        reject_symlink_parents=True)
    if sha256_bytes(raw) != approved:
        raise ValueError("SDK index differs from independent protected approval")
    index = validate_product_index(load_canonical_json_bytes(raw))
    if (index["trustDomain"] != "release" or index["context"]["kind"] != "pull-request"
            or index["signing"] != signing
            or len(index["entries"]) != len(SDK_CAMPAIGN_INSTANCES)):
        raise ValueError("Protected SDK signing requires the exact release campaign index")
    public_key_for_metadata(signing, load_keyring(keyring_path, keys_directory),
        keys_directory, allow_retired=False)
    with tempfile.TemporaryDirectory(prefix="sdk-release-sign-") as temporary:
        candidate = Path(temporary).resolve() / "product-index.json"
        candidate.write_bytes(raw)
        detached = sign_manifest(candidate, Path(private_key), signing)
        verify_manifest_signature(candidate, detached, public_key, signing)
        signature = read_regular_file_bytes(detached, max_bytes=1024 * 1024,
            reject_symlink_parents=True)
    if (read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
            reject_symlink_parents=True) != raw
            or read_regular_file_bytes(keyring_path, max_bytes=64 * 1024,
                reject_symlink_parents=True) != keyring_bytes):
        raise ValueError("Protected SDK signing input changed after verification")
    return signature
