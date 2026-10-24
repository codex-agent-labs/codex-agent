"""Bind a signed SDK campaign index to its exact selected originals.

This verifies index membership and original bytes, not semantic release admission.
The protected signer must establish every component's release proof before signing.
"""

from collections.abc import Mapping
from copy import deepcopy
import os
from pathlib import Path
import tempfile

from .index import (
    IndexEntrySource, SignedProductIndex, _verify_index_receipt,
    verify_release_product_index,
)
from . import aggregate, index
from .aggregate import validate_product_index
from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    sha256_bytes, _is_windows, _stat_identity,
)
from .registry import PhaseInstanceId
from .restore import verify_object, verification_scoped, _open_safe_regular, _VERIFICATION_SESSION


def verify_release_sdk_campaign_objects(index: dict, objects: Mapping[str, Path], *,
                                        repository: str) -> dict[PhaseInstanceId, dict]:
    """Bind a previously verified, release-signed promoted index to all 62 originals.

    The caller must authenticate the index signature and object transport first.
    Original development receipts remain unchanged; the release signature is the
    separate admission authority. Stable SDK catalogs are not yet produced.
    """
    from .sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES, verify_sdk_campaign_objects

    index = validate_product_index(index)
    if (index["repository"] != repository or index["trustDomain"] != "release"
            or index["context"]["kind"] != "promoted-main"):
        raise ValueError("SDK original catalog requires release-signed promoted-main authority")
    entries = {PhaseInstanceId(*(entry[field] for field in (
        "product", "component", "phase", "target"))): entry for entry in index["entries"]}
    if len(index["entries"]) != len(SDK_CAMPAIGN_INSTANCES) or set(entries) != SDK_CAMPAIGN_INSTANCES:
        raise ValueError("SDK release catalog must index every exact SDK campaign phase")
    if len({entry["productVersion"] for entry in index["entries"]}) != 1:
        raise ValueError("SDK release catalog phases must have one SDK version")
    if not isinstance(objects, Mapping) or set(objects) != {entry["buildKey"] for entry in entries.values()}:
        raise ValueError("SDK release catalog lacks the exact indexed original objects")

    def custody():
        result = []
        for key, path in sorted(objects.items()):
            descriptor, metadata = _open_safe_regular(Path(path), "SDK original object")
            os.close(descriptor)
            result.append((key, str(Path(path).absolute()), _stat_identity(metadata)))
        return tuple(result)

    session = None if _is_windows() else _VERIFICATION_SESSION.get()
    before = custody() if session is not None else None
    key = (canonical_json_bytes(index), before)
    if session is not None:
        with session["lock"]:
            cached = session.setdefault("sdkCampaigns", {}).get(key)
        if cached is not None:
            if custody() != before:
                raise ValueError("SDK campaign originals changed during reuse")
            return deepcopy(cached)

    sources, envelopes, archives = {}, {}, {}
    for instance, entry in entries.items():
        archive = Path(objects[entry["buildKey"]])
        verified = verify_object(archive, build_key=entry["buildKey"],
                                 receipt_sha256=entry["receiptSha256"])
        envelope = {name: verified[name] for name in (
            "receipt", "receiptBytes", "objectSha256")}
        envelope["receiptSha256"] = entry["receiptSha256"]
        receipt = envelope["receipt"]
        if (receipt["trustDomain"] != "development"
                or receipt["producer"]["repository"] != repository):
            raise ValueError("SDK release catalog original has incompatible provenance or trust")
        _verify_index_receipt(entry, envelope)
        artifacts = [output for output in receipt["outputs"]
                     if output["relativePath"] == entry["artifactName"]]
        if len(artifacts) != 1 or artifacts[0]["sha256"] != entry["artifactSha256"]:
            raise ValueError("SDK release catalog artifact differs from indexed original")
        sources[instance] = IndexEntrySource(envelope["receiptBytes"], entry["artifactName"])
        envelopes[instance] = envelope
        archives[instance] = archive
    verify_sdk_campaign_objects(sources, envelopes, archives)
    if session is not None:
        if custody() != before:
            raise ValueError("SDK campaign originals changed during verification")
        with session["lock"]:
            # Bound completed comparisons; signature and source admission stay with callers.
            if len(session["sdkCampaigns"]) < 8:
                session["sdkCampaigns"][key] = deepcopy(envelopes)
    return envelopes


def verify_signed_sdk_campaign_originals(
    index_source: SignedProductIndex, *, repository: str, context: dict,
    keyring_path: Path, keys_directory: Path,
    sources: Mapping[PhaseInstanceId, IndexEntrySource],
    envelopes: Mapping[PhaseInstanceId, dict],
    archives: Mapping[PhaseInstanceId, Path],
    stages: Mapping[PhaseInstanceId, Path],
) -> tuple[dict, bytes]:
    """Authenticate the release-signed PR index and all 62 original phase objects."""
    from .sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES, held_sdk_campaign_selection

    index, raw = verify_release_product_index(
        index_source, keyring_path=keyring_path, keys_directory=keys_directory,
    )
    if (index["repository"] != repository or index["context"] != context
            or index["context"]["kind"] != "pull-request"
            or index["trustDomain"] != "release"):
        raise ValueError("SDK campaign index has the wrong release context")
    with held_sdk_campaign_selection(sources, envelopes, archives, stages) as (
        originals, held_envelopes, _, receipts,
    ):
        entries = {
            PhaseInstanceId(*(entry[field] for field in (
                "product", "component", "phase", "target",
            ))): entry for entry in index["entries"]
        }
        if len(index["entries"]) != len(SDK_CAMPAIGN_INSTANCES) or set(entries) != SDK_CAMPAIGN_INSTANCES:
            raise ValueError("SDK campaign index does not contain every exact phase")
        for instance, entry in entries.items():
            original = originals[instance]
            receipt = receipts[instance]
            if receipt["trustDomain"] != "development":
                raise ValueError("SDK campaign original receipt must retain development trust")
            if receipt["producer"]["repository"] != repository:
                raise ValueError("SDK campaign original receipt belongs to another repository")
            producer = receipt["producer"]
            if producer["event"] != "push" and not (
                producer["event"] == "pull_request"
                and producer["pullRequest"] == context["pullRequest"]
            ):
                raise ValueError("SDK campaign original receipt belongs to another producer context")
            _verify_index_receipt(entry, held_envelopes[instance])
            artifact = next(
                (output for output in receipt["outputs"]
                 if output["relativePath"] == original.artifact_path), None,
            )
            if (entry["receiptSha256"] != sha256_bytes(original.receipt_bytes)
                    or artifact is None or entry["artifactName"] != original.artifact_path
                    or entry["artifactSha256"] != artifact["sha256"]):
                raise ValueError("SDK campaign index differs from the selected original artifact")
    return index, raw


def is_javascript_validation(entry):
    return tuple(entry.get(field) for field in ("product", "component", "phase", "target")) == (
        "sdk", "javascript", "validation", "node")


def _javascript_inventory(proof, entry):
    from .sdk_javascript_validation_phase import VerifiedJavaScriptValidationProjection

    if type(proof) is not VerifiedJavaScriptValidationProjection:
        raise ValueError("Verified JavaScript validation projection is required for index consistency")
    return proof.output_inventory(entry["receiptSha256"], entry["outputs"], identity=entry)


@verification_scoped
def verify_sdk_validation_index_object(entry, archive, projection_provider):
    """Bind the full proof to the actual original object, never an index assertion."""
    if not is_javascript_validation(entry):
        return index.verify_sdk_validation_index_object(entry, archive, projection_provider)
    if not callable(projection_provider):
        raise ValueError("JavaScript comparison requires authenticated original evidence")
    verified = verify_object(archive, build_key=entry["buildKey"], receipt_sha256=entry["receiptSha256"])
    _verify_index_receipt(entry, {**verified, "receiptSha256": sha256_bytes(verified["receiptBytes"])})
    proof = projection_provider(entry, archive)
    _javascript_inventory(proof, entry)
    return proof


def verified_index_content(entry, contract_execution_projection=None, native_runtime_projection=None,
                           adapter_runtime_projection=None, sdk_validation_projection=None):
    """Consumer comparison only; preserve frozen producer code and original bytes."""
    from .receipt import output_inventory_digest

    if sdk_validation_projection is not None and is_javascript_validation(entry):
        outputs = _javascript_inventory(sdk_validation_projection(entry), entry)
        return {**entry, "outputs": outputs, "outputInventoryDigest": output_inventory_digest(outputs),
                "artifactName": None, "artifactSha256": None}
    return aggregate.verified_index_content(entry, contract_execution_projection,
        native_runtime_projection, adapter_runtime_projection, sdk_validation_projection)


def verify_immutable_product_indexes(existing, candidate, *, contract_execution_projection=None,
                                     native_runtime_projection=None, adapter_runtime_projection=None,
                                     sdk_validation_projection=None):
    prior = validate_product_index(existing)["entries"]
    proposed = validate_product_index(candidate)["entries"]
    providers = (contract_execution_projection, native_runtime_projection,
                 adapter_runtime_projection, sdk_validation_projection)
    # Views are not signed indexes or receipts. Derive only actual conflicts,
    # at most once per original entry; never serialize or transport these views.
    views = {}

    def content(entry):
        key = id(entry)
        if key not in views:
            views[key] = verified_index_content(entry, *providers)
        return views[key]

    by_key = {entry["buildKey"]: entry for entry in prior}
    for entry in proposed:
        previous = by_key.get(entry["buildKey"])
        if previous is not None and previous["outputs"] != entry["outputs"]:
            if content(previous)["outputs"] != content(entry)["outputs"]:
                raise ValueError("Identical product build key has a conflicting output inventory")
    prior_releases, proposed_releases = {}, {}
    for entries, releases in ((prior, prior_releases), (proposed, proposed_releases)):
        for entry in entries:
            releases.setdefault(aggregate._release_identity(entry), []).append(entry)
    for identity in prior_releases.keys() & proposed_releases.keys():
        left, right = prior_releases[identity], proposed_releases[identity]
        if aggregate._release_output_projection(left) != aggregate._release_output_projection(right):
            if aggregate._release_output_projection([content(entry) for entry in left]) != \
                    aggregate._release_output_projection([content(entry) for entry in right]):
                raise ValueError("Stable product identity has different asset names or output bytes")


def verify_build_key_output_consistency(receipts, *, sdk_javascript_validation_projection=None, **providers):
    """Extend the frozen receipt verifier without rewriting any original receipt."""
    from .plan import verify_build_key_output_consistency as verify_other_receipts

    if sdk_javascript_validation_projection is None:
        return verify_other_receipts(receipts, **providers)
    from .receipt import validate_phase_receipt
    from .inventory import require_array

    remaining, javascript = [], {}
    for value in require_array(receipts, "phase receipts"):
        receipt = validate_phase_receipt(value)
        if sdk_javascript_validation_projection is not None and is_javascript_validation(receipt):
            previous = javascript.setdefault(receipt["buildKey"], receipt)
            if previous["outputs"] != receipt["outputs"]:
                views = [_javascript_inventory(sdk_javascript_validation_projection(member),
                    {**member, "receiptSha256": sha256_bytes(canonical_json_bytes(member))})
                    for member in (previous, receipt)]
                if views[0] != views[1]:
                    raise ValueError(f"Build key has conflicting output inventories: {receipt['buildKey']}")
            if previous is not receipt:
                continue  # Already compared, not deleted from the caller's evidence.
        remaining.append(receipt)
    verify_other_receipts(remaining, **providers)


def _history_comparisons(options, history=None):
    """Reuse receipt-qualified readers; each exact conflicting original is read once."""
    references, projections = {}, {}
    for family, label, verifier in (
        ("contract", "Contract", None),
        ("native_runtime", "Native Runtime", index.verify_native_runtime_index_object),
        ("adapter_runtime", "Adapter Runtime", index.verify_adapter_runtime_index_object),
        ("sdk_validation", "SDK validation", verify_sdk_validation_index_object),
    ):
        name = family + "_objects"
        references[family] = {
            **(dict(getattr(history, "_" + name)) if history is not None else {}),
            **index._contract_object_references(options.get(name), label),
        }
        if family == "contract":
            projections["contract_execution_projection"] = index._contract_object_projection(references[family])
        else:
            projections[family + "_projection"] = index._validation_object_projection(
                references[family], options.get(family + "_projection"), verifier)
    return references, projections


@verification_scoped
def verify_stable_index_history(sources, *, repository, keyring_path, keys_directory, **options):
    """Authenticate original signed history with the SDK consumer comparison rules.

    No normalized index or empty-history alias is manufactured. The existing
    history capability retains the exact signed bytes and original object paths.
    """
    unknown = set(options) - {
        "contract_objects", "native_runtime_objects", "native_runtime_projection",
        "adapter_runtime_objects", "adapter_runtime_projection",
        "sdk_validation_objects", "sdk_validation_projection",
    }
    if unknown:
        raise TypeError(f"Unknown index history options: {sorted(unknown)}")
    references, projections = _history_comparisons(options)
    keyring = index.load_keyring(Path(keyring_path), Path(keys_directory))
    authoritative_refs = index._authoritative_stable_refs(repository)
    originals, indexes, tags = [], [], []
    for source in sources:
        value, raw, _ = index._verify_release_product_index_with_keyring(
            source, keyring, Path(keys_directory))
        if value["repository"] != repository:
            raise ValueError("Stable product-index history repository mismatch")
        index.stable_index_identity(value)
        tags.append(value["context"]["tag"])
        for prior in indexes:
            verify_immutable_product_indexes(prior, value, **projections)
        indexes.append(value)
        originals.append(raw)
    if len(tags) != len(set(tags)) or set(tags) != set(authoritative_refs):
        raise ValueError("Stable product-index sources do not match the current protected stable-tag inventory")
    return index.VerifiedStableIndexHistory(repository, tuple(originals), index._HISTORY_TOKEN,
        *(tuple(references[family].items()) for family in (
            "contract", "native_runtime", "adapter_runtime", "sdk_validation")))


@verification_scoped
def build_product_index(sources, *, repository, context, trust_domain, signing, producer,
                        stable_history, **options):
    """Keep ordinary construction unchanged; compare stable originals as consumers."""
    arguments = dict(repository=repository, context=context, trust_domain=trust_domain,
                     signing=signing, producer=producer, stable_history=stable_history, **options)
    if context.get("kind") != "stable":
        return index.build_product_index(sources, **arguments)
    unknown = set(options) - {
        "contract_objects", "native_runtime_objects", "native_runtime_projection",
        "adapter_runtime_objects", "adapter_runtime_projection",
        "sdk_validation_objects", "sdk_validation_projection",
    }
    if unknown:
        raise TypeError(f"Unknown index construction options: {sorted(unknown)}")
    pairs = sorted((index._entry(source, repository=repository, trust_domain=trust_domain)
                    for source in sources), key=lambda pair: pair[0]["buildKey"])
    entries = [entry for entry, _, _ in pairs]
    if len({entry["buildKey"] for entry in entries}) != len(entries):
        raise ValueError("Product index entry build keys must be unique")
    value = validate_product_index(dict(schemaVersion=1, repository=repository,
        context=context, entries=entries, trustDomain=trust_domain, signing=signing, producer=producer))
    if any(receipt["producer"]["event"] != "push" and not admitted for _, receipt, admitted in pairs):
        raise ValueError("Release product index contains a non-push receipt")
    index.stable_index_identity(value)
    if (not isinstance(stable_history, index.VerifiedStableIndexHistory)
            or stable_history._token is not index._HISTORY_TOKEN
            or stable_history._repository != repository):
        raise ValueError("Stable product index requires explicit authenticated history")
    _, projections = _history_comparisons(options, stable_history)
    for raw in stable_history._index_bytes:
        verify_immutable_product_indexes(load_canonical_json_bytes(raw), value, **projections)
    return value


@verification_scoped
def write_signed_product_index(sources, *, private_key, public_key, manifest_path, **arguments):
    """Publish exact raw stable entries, using the frozen writer's atomic primitives."""
    if arguments["context"].get("kind") != "stable":
        return index.write_signed_product_index(sources, private_key=private_key,
            public_key=public_key, manifest_path=manifest_path, **arguments)
    value = build_product_index(sources, **arguments)
    manifest = Path(os.path.abspath(manifest_path))
    signature = manifest.with_suffix(".sig")
    if signature == manifest or manifest.parent != signature.parent:
        raise ValueError("Product index manifest and signature paths must differ in one directory")
    signing = arguments["signing"]
    with tempfile.TemporaryDirectory(prefix="sdk-product-index-") as temporary:
        root = Path(temporary).resolve()
        key = root / "public-key.pub"
        key.write_bytes(read_regular_file_bytes(Path(public_key),
            max_bytes=index._SIGNATURE_LIMIT, reject_symlink_parents=True))
        candidate = root / manifest.name
        candidate.write_bytes(canonical_json_bytes(value))
        detached = index.sign_manifest(candidate, Path(private_key), signing)
        index.verify_manifest_signature(candidate, detached, key, signing)
        raw = read_regular_file_bytes(candidate, max_bytes=index._INDEX_LIMIT)
        sig = read_regular_file_bytes(detached, max_bytes=index._SIGNATURE_LIMIT)
        if raw != canonical_json_bytes(value):
            raise ValueError("Signed product index differs from the verified candidate")
        with index._held_output_parent(manifest.parent) as (descriptor, parent):
            leaves = ((manifest.name, raw, index._INDEX_LIMIT), (signature.name, sig, index._SIGNATURE_LIMIT))
            for name, expected, limit in leaves:
                if index._read_parent_file(descriptor, parent, name, max_bytes=limit) not in (None, expected):
                    raise ValueError("Immutable product index output conflicts with existing bytes")
            published = [index._publish_output(expected, descriptor, parent, name, max_bytes=limit)
                         for name, expected, limit in leaves]
            with (
                index._held_parent_file(descriptor, parent, manifest.name) as (raw_fd, raw_stat),
                index._held_parent_file(descriptor, parent, signature.name) as (sig_fd, sig_stat),
            ):
                def unchanged():
                    if (index._read_held_file(raw_fd, raw_stat, index._INDEX_LIMIT) != raw
                            or index._read_held_file(sig_fd, sig_stat, index._SIGNATURE_LIMIT) != sig):
                        raise ValueError("Published product index pair changed during final verification")
                    index._require_held_leaf_identity(descriptor, parent, manifest.name, raw_fd, raw_stat)
                    index._require_held_leaf_identity(descriptor, parent, signature.name, sig_fd, sig_stat)

                unchanged()
                final_manifest, final_signature = root / "published.json", root / "published.sig"
                final_manifest.write_bytes(raw)
                final_signature.write_bytes(sig)
                index.verify_manifest_signature(final_manifest, final_signature, key, signing)
                unchanged()
    return dict(status="published" if any(published) else "existing", index=value,
        manifestPath=manifest, signaturePath=signature,
        manifestSha256=sha256_bytes(raw), signatureSha256=sha256_bytes(sig))
