"""Prepare an SDK release index without a key; sign only independently approved bytes.

The two functions belong in different processes. In particular, the protected
signer never receives a GitHub observation token or replays candidate tooling.
The expected index digest must come from protected approval, not this module's
preparation result or the development catalog.
"""

import argparse
from collections.abc import Mapping
import json
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from products.aggregate import validate_product_index
from products.index import (
    IndexEntrySource, SignedProductIndex, _mint_release_admission,
    build_product_index, verify_release_product_index,
)
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, require_exact_keys, require_sha256, sha256_bytes,
)
from products.receipt import validate_phase_receipt, validate_producer
from products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from products.signatures import (
    load_keyring, public_key_for_metadata, require_active_release_key,
    sign_manifest, verify_manifest_signature,
)
from products.signing_isolation import SIGNING_SECRET, require_no_signing_secret


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
_FAMILIES = ("core-android", "native", "apple-js")
_APPROVED_AUTHORITY = "CODEX_AGENT_SDK_AUTHORITY_APPROVED_SHA256"
_APPROVED_KEYRING = "CODEX_AGENT_PRODUCT_KEYRING_APPROVED_SHA256"
_APPROVED_INDEX = "CODEX_AGENT_SDK_INDEX_APPROVED_SHA256"
_APPROVED_SIGNATURE = "CODEX_AGENT_SDK_SIGNATURE_APPROVED_SHA256"
_CONTROL_APPROVAL_ENV = {
    "sdk_validation_tooling": "CODEX_AGENT_SDK_VALIDATION_TOOLING_APPROVED_SHA256",
    "sdk_apple_validation_policy": "CODEX_AGENT_SDK_APPLE_POLICY_APPROVED_SHA256",
    "sdk_facade_metadata_policy": "CODEX_AGENT_SDK_FACADE_POLICY_APPROVED_SHA256",
    "sdk_android_metadata_policy": "CODEX_AGENT_SDK_ANDROID_POLICY_APPROVED_SHA256",
    "custody_catalogs": "CODEX_AGENT_SDK_CUSTODY_APPROVED_SHA256",
}


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


def verify_signed_sdk_release_index_against_official_replay(
        signed: SignedProductIndex, plan_path, repository_root, *,
        expected_index_sha256, expected_signature_sha256,
        keyring_path, keys_directory, expected_keyring_sha256, **replay_options):
    """Recheck signed bytes against the full official all-61 replay without a key.

    The three expected digests must come from protected caller approval, not
    from the signed files or a development catalog. This grants no approval by
    itself; the caller retains the verified bytes and replay result externally.
    """
    require_no_signing_secret(os.environ)
    require_no_signing_secret(replay_options.get("environ", {}))
    if not isinstance(signed, SignedProductIndex):
        raise ValueError("Signed SDK campaign index source is invalid")
    index_pin = require_sha256(expected_index_sha256, "Protected SDK index digest")
    signature_pin = require_sha256(expected_signature_sha256, "Protected SDK signature digest")
    keyring_bytes, _, _ = _release_key(
        keyring_path, keys_directory, expected_keyring_sha256)
    index_bytes = read_regular_file_bytes(signed.manifest, max_bytes=16 * 1024 * 1024,
        reject_symlink_parents=True)
    signature_bytes = read_regular_file_bytes(signed.signature, max_bytes=1024 * 1024,
        reject_symlink_parents=True)
    if sha256_bytes(index_bytes) != index_pin or sha256_bytes(signature_bytes) != signature_pin:
        raise ValueError("Signed SDK index differs from independent protected approval")
    index, verified_bytes = verify_release_product_index(signed,
        keyring_path=keyring_path, keys_directory=keys_directory)
    if verified_bytes != index_bytes:
        raise ValueError("Signed SDK index changed during signature verification")
    replayed = prepare_sdk_release_index(plan_path, repository_root,
        keyring_path=keyring_path, keys_directory=keys_directory,
        expected_keyring_sha256=expected_keyring_sha256, **replay_options)
    if replayed != index_bytes:
        raise ValueError("Signed SDK index differs from full official campaign replay")
    if (read_regular_file_bytes(signed.manifest, max_bytes=16 * 1024 * 1024,
            reject_symlink_parents=True) != index_bytes
            or read_regular_file_bytes(signed.signature, max_bytes=1024 * 1024,
                reject_symlink_parents=True) != signature_bytes
            or read_regular_file_bytes(keyring_path, max_bytes=64 * 1024,
                reject_symlink_parents=True) != keyring_bytes):
        raise ValueError("Signed SDK verification inputs changed during replay")
    return index, index_bytes


def _approved_environment_digest(name):
    value = os.environ.get(name)
    if type(value) is not str or not value:
        raise ValueError(f"Protected SDK caller is missing {name}")
    return require_sha256(value, name)


def _optional_pinned_file(path, digest, label):
    if (path is None) != (digest is None):
        raise ValueError(f"{label} requires both its file and independent digest")
    if path is None:
        return None
    raw = read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
        reject_symlink_parents=True)
    if sha256_bytes(raw) != require_sha256(digest, f"{label} digest"):
        raise ValueError(f"{label} differs from its independent digest")
    return raw


def _prepare_or_verify_cli(args):
    require_no_signing_secret(os.environ)
    authority_pin = _approved_environment_digest(_APPROVED_AUTHORITY)
    keyring_pin = _approved_environment_digest(_APPROVED_KEYRING)
    index_pin = _approved_environment_digest(_APPROVED_INDEX) if args.mode == "verify" else None
    signature_pin = _approved_environment_digest(_APPROVED_SIGNATURE) if args.mode == "verify" else None
    from ci.sdk_campaign_pinned_election import held_pinned_sdk_campaign_authority
    from sdk_metadata_policy import metadata_admission_options

    controlled = {}
    for name, approved_name in _CONTROL_APPROVAL_ENV.items():
        controlled[name] = _optional_pinned_file(
            getattr(args, name),
            _approved_environment_digest(approved_name) if getattr(args, name) is not None else None,
            name)
    custody = {}
    if controlled["custody_catalogs"] is not None:
        raw_catalogs = load_canonical_json_bytes(controlled["custody_catalogs"])
        if type(raw_catalogs) is not dict:
            raise ValueError("SDK custody descriptors must be a canonical object")
        for ref, row in raw_catalogs.items():
            row = require_exact_keys(row, {"selection", "destination"},
                "SDK custody descriptor")
            if type(row["destination"]) is not str or not Path(row["destination"]).is_absolute():
                raise ValueError("SDK custody destination must be an absolute path")
            custody[ref] = {"selection": row["selection"],
                            "destination": Path(row["destination"])}
    metadata = {"repository_root": args.repository_root, "plan": args.plan,
                "expected_policy_bytes": {}}
    for name in ("sdk_facade_metadata_policy", "sdk_android_metadata_policy"):
        if controlled[name] is not None:
            metadata[name] = getattr(args, name)
            metadata["expected_policy_bytes"][name] = controlled[name]

    with held_pinned_sdk_campaign_authority(args.authority_file, authority_pin) as authority:
        producer = authority["completedCatalogPin"]["producer"]
        context = {"kind": "pull-request", "pullRequest": producer["pullRequest"],
                   **{name: producer[name] for name in (
                       "commit", "tree", "runId", "runAttempt")}}
        with metadata_admission_options(metadata) as admissions:
            options = dict(
                authority_file=args.authority_file,
                authority_artifact_id=args.authority_artifact_id,
                authority_artifact_sha256=args.authority_artifact_sha256,
                expected_authority_sha256=authority_pin,
                authority_workflow_sha=args.authority_workflow_sha,
                authority_workflow_path=args.authority_workflow_path,
                authority_job_name=args.authority_job_name,
                trusted_workflow_sha=args.trusted_workflow_sha,
                election_files={family: getattr(args, "election_" + family.replace("-", "_"))
                                for family in _FAMILIES},
                semantic_files={family: getattr(args, "semantic_" + family.replace("-", "_"))
                                for family in _FAMILIES},
                token=os.environ["GITHUB_TOKEN"], environ=os.environ,
                keyring_path=args.keyring_path, keys_directory=args.keys_directory,
                expected_keyring_sha256=keyring_pin,
                repository=producer["repository"], context=context, producer=producer,
                state_artifact_id=args.state_artifact_id,
                state_artifact_sha256=args.state_artifact_sha256,
                state_wave=args.state_wave, sdk_state_wave=args.sdk_state_wave,
                custody_catalogs=custody,
                sdk_validation_tooling=(None if controlled["sdk_validation_tooling"] is None
                    else load_canonical_json_bytes(controlled["sdk_validation_tooling"])),
                sdk_apple_validation_policy=(None if controlled["sdk_apple_validation_policy"] is None
                    else load_canonical_json_bytes(controlled["sdk_apple_validation_policy"])),
                **admissions)
            if args.mode == "verify":
                _, prepared = verify_signed_sdk_release_index_against_official_replay(
                    SignedProductIndex(args.signed_index, args.signature),
                    args.plan, args.repository_root,
                    expected_index_sha256=index_pin,
                    expected_signature_sha256=signature_pin, **options)
            else:
                prepared = prepare_sdk_release_index(args.plan, args.repository_root,
                    **options)
            for name, raw in controlled.items():
                if raw is not None and read_regular_file_bytes(getattr(args, name),
                        max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != raw:
                    raise ValueError(f"{name} changed during SDK release preparation")
        if args.mode == "verify":
            return {"verifiedIndexSha256": index_pin,
                    "verifiedSignatureSha256": signature_pin}
        result = stage_prepared_sdk_release_index(prepared, args.destination)
    return {"preparedIndex": str(result)}


def _sign_cli(args):
    if _TOKEN_NAMES & set(os.environ):
        raise ValueError("SDK signing process must not have an observation token")
    approved_index = _approved_environment_digest(_APPROVED_INDEX)
    approved_keyring = _approved_environment_digest(_APPROVED_KEYRING)
    destination = Path(args.destination).resolve(strict=False)
    inputs = (Path(args.prepared_index).resolve(strict=True).parent,
              Path(args.keyring_path).resolve(strict=True),
              Path(args.keys_directory).resolve(strict=True))
    if any(destination == source or destination in source.parents
           or source in destination.parents for source in inputs):
        raise ValueError("Signed SDK index destination overlaps an input")
    raw = read_regular_file_bytes(args.prepared_index, max_bytes=16 * 1024 * 1024,
        reject_symlink_parents=True)
    if sha256_bytes(raw) != approved_index:
        raise ValueError("Prepared SDK index differs from independent protected approval")
    secret = os.environ.get(SIGNING_SECRET)
    if type(secret) is not str or not secret:
        raise ValueError("Protected SDK release signing key is unavailable")
    with tempfile.TemporaryDirectory(prefix="sdk-release-key-") as temporary:
        private_key = Path(temporary).resolve() / "release-ed25519"
        descriptor = os.open(private_key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(secret.encode("utf-8"))
        signature = sign_approved_sdk_release_index(args.prepared_index,
            expected_index_sha256=approved_index, keyring_path=args.keyring_path,
            keys_directory=args.keys_directory, expected_keyring_sha256=approved_keyring,
            private_key=private_key, environ=os.environ)
    if read_regular_file_bytes(args.prepared_index, max_bytes=16 * 1024 * 1024,
            reject_symlink_parents=True) != raw:
        raise ValueError("Prepared SDK index changed before signed publication")
    with tempfile.TemporaryDirectory(prefix="sdk-release-pair-") as temporary:
        staged = Path(temporary).resolve() / "signed"
        staged.mkdir()
        (staged / "product-index.json").write_bytes(raw)
        (staged / "product-index.sig").write_bytes(signature)
        publish_regular_tree(staged, args.destination, expected_inventory=[
            {"relativePath": "product-index.json", "bytes": len(raw), "sha256": approved_index},
            {"relativePath": "product-index.sig", "bytes": len(signature),
             "sha256": sha256_bytes(signature)},
        ])
    return {"signedIndex": str(args.destination / "product-index.json"),
            "signature": str(args.destination / "product-index.sig")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    modes = parser.add_subparsers(dest="mode", required=True)
    for mode in ("prepare", "verify"):
        command = modes.add_parser(mode, allow_abbrev=False)
        for name in ("plan", "repository-root", "authority-file", "keyring-path",
                     "keys-directory"):
            command.add_argument("--" + name, type=Path, required=True)
        if mode == "prepare":
            command.add_argument("--destination", type=Path, required=True)
        else:
            for name in ("signed-index", "signature"):
                command.add_argument("--" + name, type=Path, required=True)
        for name in ("authority-artifact-id", "state-artifact-id", "state-wave"):
            command.add_argument("--" + name, type=int, required=True)
        command.add_argument("--sdk-state-wave", type=int)
        for name in ("authority-artifact-sha256", "authority-workflow-sha",
                     "authority-workflow-path", "authority-job-name", "trusted-workflow-sha",
                     "state-artifact-sha256"):
            command.add_argument("--" + name, required=True)
        for family in _FAMILIES:
            for kind in ("election", "semantic"):
                command.add_argument(f"--{kind}-{family}", type=Path, required=True)
        for name in ("sdk-validation-tooling", "sdk-apple-validation-policy",
                     "sdk-facade-metadata-policy", "sdk-android-metadata-policy",
                     "custody-catalogs"):
            command.add_argument("--" + name, type=Path)
    sign = modes.add_parser("sign", allow_abbrev=False)
    for name in ("prepared-index", "destination", "keyring-path", "keys-directory"):
        sign.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = _sign_cli(args) if args.mode == "sign" else _prepare_or_verify_cli(args)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
