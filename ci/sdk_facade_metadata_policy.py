"""Produce an external Core caller descriptor after complete retained replay.

The caller independently authenticates selected envelopes and enclosing captures,
and supplies original invocation, Contract, tooling and native archive policy.
Nothing is elected from a transported carrier. This leaf performs the existing
semantic/source/key checks; it does not manufacture hardware or missing compiler
pins. Unsupported native policy remains a failure, not a partial descriptor.
"""

import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes, sha256_file
from products.reuse import _validate_envelope
from products.sdk_facade_inputs import _fresh, _path, _request, _sources
from products.sdk_facade_metadata_admission import FacadeMetadataAdmission, _arguments
from products.sdk_facade_validation import _inventory
from products.sdk_package import _require_capability_output_separate
from products.sdk_validation_inputs import _request_inventory
from products.signing_isolation import require_no_signing_secret


def _read(path):
    return read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)


def _digest(path):
    # Keep archive hashing streaming, with the same normalized ancestry guards
    # as the original readers. sha256_file also checks the opened file identity.
    _path(str(path), "Core policy input")
    digest = sha256_file(path, reject_symlink_parents=True)
    _path(str(path), "Core policy input")
    return digest


def write_facade_metadata_policy(plan, destination, *, evidence_root, records, policy,
                                 metadata_envelope, validation_envelopes, repository_root):
    """Write one fresh canonical descriptor only after every replay context exits.

    Inputs are independently selected caller authority, not a metadata carrier
    parser. Returned descriptor data is not an admission token: consumers must
    rerun the concrete adapter and retain its existing policy limitations.
    Destination must be outside the repository and all protected inputs (for
    example a fresh file below RUNNER_TEMP). This is not a preplanner selector:
    independently selected envelopes must already be available to the caller.
    """
    require_no_signing_secret(os.environ)
    repository = _path(str(repository_root), "Core policy repository")
    evidence = _path(str(evidence_root), "Core policy evidence root")
    plan = _path(str(plan), "Core policy current plan")
    output = Path(destination).absolute()
    descriptor_bytes = canonical_json_bytes({"evidenceRoot": str(evidence), "records": records, "policy": policy})
    descriptor = load_canonical_json_bytes(descriptor_bytes)
    arguments = _arguments(policy)
    plan_bytes = _read(plan)
    if _read(arguments["plan"]) != plan_bytes:
        raise ValueError("Core caller policy plan differs from the current invocation")
    if not isinstance(validation_envelopes, (tuple, list)):
        raise ValueError("Core policy requires independently selected validation envelopes")

    def envelopes():
        return tuple((value["receiptBytes"], value["receiptSha256"], value["objectSha256"],
                      canonical_json_bytes(value["receipt"]))
                     for _, value in map(_validate_envelope, (metadata_envelope, *validation_envelopes)))

    selected = envelopes()
    trees = {evidence, arguments["tooling_evidence"]}
    files = {plan, arguments["plan"], arguments["tooling_public_key"], arguments["java_executable"]}
    if arguments["tooling_keyring"] is not None:
        files.add(arguments["tooling_keyring"])
        trees.add(arguments["tooling_keys_directory"])
    compatibility, request_bytes = {}, {}
    for record in arguments["validations"].values():
        trees.add(Path(record["captureRoot"]))
        files.update(Path(record[name]) for name in ("facadeRequest", "validationReceipt"))
        if "nativeCompilerArchive" in record:
            files.add(Path(record["nativeCompilerArchive"]))
        request_path = Path(record["facadeRequest"])
        request, request_bytes[request_path] = _request(request_path)
        _, request_trees, request_files = _sources(request)
        trees.update(request_trees.values())
        files.update(request_files.values())
        path = Path(request["compatibilityRequest"])
        compatibility[path] = _request_inventory(path)
    protected = [repository, *trees, *files, *(path for inventory in compatibility.values() for path in inventory)]
    _fresh(output, protected)
    before_trees = {path: _inventory(path, allow_empty=True) for path in trees}
    # Native archives and Java may exceed the small control-file bound.
    before_files = {path: _digest(path) for path in files}
    validated = product_reuse._validate_plan(plan, repository)
    revision, tree = validated["validationCommit"], validated["validationTree"]

    def unchanged():
        require_no_signing_secret(os.environ)
        if (_read(plan) != plan_bytes or envelopes() != selected
                or canonical_json_bytes({"evidenceRoot": str(evidence), "records": records, "policy": policy}) != descriptor_bytes
                or any(_read(path) != raw for path, raw in request_bytes.items())
                or any(_digest(path) != digest for path, digest in before_files.items())
                or any(_inventory(path, allow_empty=True) != inventory for path, inventory in before_trees.items())
                or any(_request_inventory(path) != inventory for path, inventory in compatibility.items())
                or product_reuse._git_value(repository, "rev-parse", "HEAD^{commit}") != revision
                or product_reuse._git_value(repository, "rev-parse", "HEAD^{tree}") != tree):
            raise ValueError("Core caller policy originals or independent authority changed")

    published = None

    def remove_own_output():
        if published is not None:
            try:
                current = output.lstat()
            except FileNotFoundError:
                return
            if (current.st_dev, current.st_ino) == published:
                output.unlink()

    try:
        unchanged()
        admission = FacadeMetadataAdmission(evidence, records, repository=repository,
                                             policy_revision=revision, policy=policy)
        admission.verify_metadata(metadata_envelope, validation_envelopes)
        unchanged()
        _fresh(output, protected)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".core-metadata-policy-", dir=output.parent) as temporary:
            staged = Path(temporary) / "policy.json"
            _require_capability_output_separate(staged, protected)
            staged.write_bytes(descriptor_bytes)
            unchanged()
            if _read(staged) != descriptor_bytes:
                raise ValueError("Core caller descriptor changed before publication")
            _fresh(output, protected)
            original = staged.stat()
            os.link(staged, output, follow_symlinks=False)
            published = original.st_dev, original.st_ino
            unchanged()
            if _read(output) != descriptor_bytes:
                raise ValueError("Core caller descriptor changed during publication")
        return descriptor
    except BaseException:
        remove_own_output()
        raise
    finally:
        try:
            unchanged()
        except BaseException:
            remove_own_output()
            raise
