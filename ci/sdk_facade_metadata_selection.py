"""Select original Core receipts from a caller-pinned signed local catalog.

This is not current-key election or hosted/toolchain authority. Catalog lookup
authenticates original object identity; the existing full policy writer must
still replay all eleven originals. No policy is recovered from carrier bytes.
Release catalogs containing development SDK receipts remain rejected by the
existing lookup policy; no SDK release-attestation exception is added here.
"""

import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, sha256_bytes
from products.receipt import validate_phase_receipt
from products.registry import SDK_FACADE_TARGETS
from products.restore import PHASE_PLAN_KEYS
from products.reuse import LookupSession, RemoteCatalog
from products.sdk_facade_inputs import _fresh, _path, _request, _sources
from products.sdk_facade_metadata_admission import _arguments
from products.sdk_facade_validation import _inventory
from products.sdk_validation_inputs import _request_inventory
from products.signing_isolation import require_no_signing_secret
from sdk_facade_metadata_policy import _digest, _read, write_facade_metadata_policy


def write_selected_facade_metadata_policy(plan, destination, *, catalog, catalog_source,
        metadata_receipt_path, evidence_root, records, policy, repository_root):
    """Authenticate explicitly selected originals, then publish external policy.

    Catalog/public keys and every replay input are independent caller inputs.
    The current plan selects repository/PR and current policy revision only;
    original receipts retain their historical commits and keys unchanged.
    Destination must be fresh and outside the repository and every input.
    A post-publication failure may leave the output for caller cleanup; this
    function never risks unlinking a concurrently replaced caller-owned path.
    """
    require_no_signing_secret(os.environ)
    if type(catalog) is not RemoteCatalog or catalog_source not in {"same-pr", "stable", "promoted-main"}:
        raise ValueError("Core selection requires an explicit signed RemoteCatalog source")
    objects = dict(catalog.objects)
    repository = _path(str(repository_root), "Core selection repository")
    plan = _path(str(plan), "Core selection current plan")
    metadata = _path(str(metadata_receipt_path), "Core selection metadata receipt")
    evidence = _path(str(evidence_root), "Core selection evidence")
    output = Path(destination).absolute()
    arguments = _arguments(policy)
    authority = canonical_json_bytes({"records": records, "policy": policy})
    files = {plan, metadata}
    files.update(Path(path) for path in (arguments["plan"], arguments["tooling_public_key"], arguments["java_executable"],
        arguments["tooling_keyring"]) if path is not None)
    trees = {evidence, arguments["tooling_evidence"]}
    trees.update(Path(path) for path in (arguments["tooling_keys_directory"],)
                 if path is not None)
    files.update((Path(catalog.manifest), Path(catalog.signature)))
    files.update(Path(path) for path in (*objects.values(), catalog.public_key, catalog.keyring) if path is not None)
    if catalog.keys_directory is not None:
        trees.add(Path(catalog.keys_directory))
    requests = {}
    selected_paths = {"common": metadata}
    for target, record in arguments["validations"].items():
        selected_paths[target] = Path(record["validationReceipt"])
        files.update((Path(record["validationReceipt"]), Path(record["facadeRequest"])))
        trees.add(Path(record["captureRoot"]))
        if "nativeCompilerArchive" in record:
            files.add(Path(record["nativeCompilerArchive"]))
        request, raw = _request(Path(record["facadeRequest"]))
        requests[Path(record["facadeRequest"])] = raw
        _, source_trees, source_files = _sources(request)
        trees.update(source_trees.values())
        files.update(source_files.values())
    compatibility = {Path(load_canonical_json_bytes(raw)["compatibilityRequest"]): None
                     for raw in requests.values()}
    compatibility = {path: _request_inventory(path) for path in compatibility}
    files.update(path for inventory in compatibility.values() for path in inventory)
    protected = [repository, *trees, *files]
    _fresh(output, protected)
    before_files = {path: _digest(path) for path in files}
    before_trees = {path: _inventory(path, allow_empty=True) for path in trees}
    raw_receipts = {target: _read(path) for target, path in selected_paths.items()}
    if len({sha256_bytes(raw) for raw in raw_receipts.values()}) != len(raw_receipts):
        raise ValueError("Core original receipts must be distinct")
    current = product_reuse._validate_plan(plan, repository)
    if current["remoteBuildAuthorized"] is not True or current["event"] == "workflow_dispatch":
        raise ValueError("Core catalog selection requires an authorized current plan")

    def unchanged():
        require_no_signing_secret(os.environ)
        if (dict(catalog.objects) != objects
                or canonical_json_bytes({"records": records, "policy": policy}) != authority
                or any(_read(path) != raw for path, raw in requests.items())
                or any(_digest(path) != value for path, value in before_files.items())
                or any(_inventory(path, allow_empty=True) != value for path, value in before_trees.items())
                or any(_request_inventory(path) != value for path, value in compatibility.items())
                or product_reuse._git_value(repository, "rev-parse", "HEAD^{commit}") != current["validationCommit"]
                or product_reuse._git_value(repository, "rev-parse", "HEAD^{tree}") != current["validationTree"]):
            raise ValueError("Core signed selection or caller authority changed")

    published = None
    try:
        unchanged()
        envelopes = {}
        session = LookupSession(repository=current["repository"], pull_request=current["pullRequest"],
            **{catalog_source.replace("-", "_"): (catalog,) if catalog_source == "stable" else catalog})
        for target, raw in raw_receipts.items():
            receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
            expected = ("sdk", "sdk-core", "metadata" if target == "common" else "validation", target)
            if tuple(receipt[key] for key in ("product", "component", "phase", "target")) != expected:
                raise ValueError("Core selection requires exact metadata and eleven validation identities")
            result = session.lookup(catalog_source, {key: receipt[key] for key in PHASE_PLAN_KEYS})
            if (result.envelope is None or result.envelope["receiptBytes"] != raw
                    or result.envelope["receiptSha256"] != sha256_bytes(raw)):
                raise ValueError("Core selected original is absent or differs from its signed catalog")
            envelopes[target] = result.envelope
        unchanged()
        with tempfile.TemporaryDirectory(prefix="core-selected-policy-") as temporary:
            staged = Path(temporary).resolve() / "policy.json"
            _fresh(staged, [output, *protected])
            result = write_facade_metadata_policy(plan, staged, evidence_root=evidence, records=records,
                policy=policy, metadata_envelope=envelopes["common"],
                validation_envelopes=[envelopes[target] for target in SDK_FACADE_TARGETS], repository_root=repository)
            raw = canonical_json_bytes(result)
            if _read(staged) != raw:
                raise ValueError("Core selected descriptor differs from complete replay")
            unchanged()
            _fresh(output, protected)
            output.parent.mkdir(parents=True, exist_ok=True)
            identity = staged.stat()
            os.link(staged, output, follow_symlinks=False)
            published = identity.st_dev, identity.st_ino
            unchanged()
            if _read(output) != raw:
                raise ValueError("Core selected descriptor changed during publication")
        unchanged()
        identity = output.lstat()
        if (identity.st_dev, identity.st_ino) != published or _read(output) != raw:
            raise ValueError("Core selected descriptor changed after final authority check")
        return result
    except BaseException:
        # There is no atomic compare-inode-and-unlink primitive here. Retain a
        # failed publication instead of racing deletion of a foreign inode.
        raise
