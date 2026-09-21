"""Hold eleven original Core validation replays for deterministic metadata.

This context preserves the existing observed-upload/source/semantic gates. It
does not turn runner labels or ordinary dictionaries into hardware/toolchain
authority, mint receipts, or independently admit metadata to a catalog.
"""

from contextlib import ExitStack, contextmanager
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_exact_keys, require_integer, require_regular_directory, require_sha256, snapshot_regular_tree,
    write_canonical_json,
)
from products.receipt import validate_phase_receipt
from products.registry import SDK_FACADE_CONTRACT_COMPONENTS, SDK_FACADE_TARGETS
from products.sdk_facade_inputs import _request
from products.sdk_facade_validation import _inventory
from products.sdk_facade_validation_admission import _native_archive_path, _native_archive_digest, _NON_NATIVE_TARGETS
from products.sdk_package import _require_capability_output_separate
from products.sdk_platform_metadata import write_facade_metadata_content
from products.signing_isolation import require_no_signing_secret
from sdk_facade_original_validation import (
    verified_original_sdk_facade_validation, verified_retained_sdk_facade_validation,
)


def _read(path):
    return read_regular_file_bytes(Path(path), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)


def _records(validations):
    result = {}
    for target, value in require_exact_keys(validations, SDK_FACADE_TARGETS, "Core metadata original validations").items():
        retained = type(value) is dict and "captureRoot" in value
        fields = {"validationReceipt", "facadeRequest"} | (
            {"nativeCompilerArchive"} if target not in _NON_NATIVE_TARGETS else set())
        record = require_exact_keys(value, fields | ({"captureRoot"} if retained else {"artifactId", "artifactSha256"}),
                                    "Core metadata original validation locator")
        result[target] = {} if retained else {
            "artifactId": require_integer(record["artifactId"], "Core validation artifact ID", 1),
            "artifactSha256": require_sha256(record["artifactSha256"], "Core validation artifact digest")}
        archive = _native_archive_path(target, record.get("nativeCompilerArchive"))
        if archive is not None:
            result[target]["nativeCompilerArchive"] = str(archive)
        for field in ("validationReceipt", "facadeRequest", *(("captureRoot",) if retained else ())):
            path = Path(record[field])
            if not path.is_absolute() or path.resolve(strict=True) != path:
                raise ValueError("Core metadata caller paths must be absolute, normalized and non-symbolic")
            if field == "captureRoot":
                require_regular_directory(path, "Caller-authenticated Core capture")
            result[target][field] = str(path)
    return result


def _native_archives(records):
    """Stream each distinct caller archive once per held-boundary check."""
    return {path: _native_archive_digest(path) for path in
            {Path(record["nativeCompilerArchive"]) for record in records.values() if "nativeCompilerArchive" in record}}


def _view(record):
    return canonical_json_bytes({name: str(value) if isinstance(value, Path) else
        value.hex() if isinstance(value, bytes) else value for name, value in record.items()})


@contextmanager
def verified_facade_metadata_inputs(*, plan, validations, contract_digest, component_digests,
        repository_root, environ, token, trusted_workflow_sha, tooling_evidence, tooling_public_key,
        java_executable, policy_revision, required_trust_domain,
        tooling_keyring=None, tooling_keys_directory=None):
    """Yield private package/validation paths and expected content until clean exit.

    Caller-owned facade requests supply replay policy. Retained request paths
    never replace it. Distinct validation producers are permitted, but all must
    consume exactly the same original package receipt and SDK version.
    Each retained capture requires independently authenticated enclosing carrier
    bytes; stored transport records never replace that caller obligation.
    Every native target record requires nativeCompilerArchive from independent
    caller policy, in either acquisition mode. This path is not retained in the
    metadata request/payload; unsupported host archive policies remain failures.
    """
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    records = _records(validations)
    record_bytes = canonical_json_bytes(records)
    archives = _native_archives(records)
    retained_sources = {Path(record["captureRoot"]): _inventory(Path(record["captureRoot"]), allow_empty=True)
                        for record in records.values() if "captureRoot" in record}
    require_sha256(contract_digest, "Core metadata expected Contract digest")
    components = require_exact_keys(component_digests, set(SDK_FACADE_CONTRACT_COMPONENTS.values()),
                                    "Core metadata expected Contract components")
    for digest in components.values():
        require_sha256(digest, "Core metadata expected component digest")
    component_bytes = canonical_json_bytes(component_digests)
    request_values, original_files, selected_receipts = {}, {}, {}
    package_bytes = None
    for target in SDK_FACADE_TARGETS:
        record = records[target]
        request, raw_request = _request(Path(record["facadeRequest"]))
        raw_receipt = _read(record["validationReceipt"])
        receipt = validate_phase_receipt(load_canonical_json_bytes(raw_receipt))
        raw_package = _read(request["packageReceipt"])
        if (tuple(receipt[name] for name in ("product", "component", "phase", "target")) !=
                ("sdk", "sdk-core", "validation", target) or request["target"] != target
                or request["sdkVersion"] != receipt["productVersion"] or Path(request["repository"]) != root):
            raise ValueError("Core metadata original validation/request identity differs")
        if package_bytes is None:
            package_bytes = raw_package
        elif raw_package != package_bytes:
            raise ValueError("Core metadata validations have different original package receipts")
        original_files.update({Path(record["facadeRequest"]): raw_request,
            Path(record["validationReceipt"]): raw_receipt, Path(request["packageReceipt"]): raw_package})
        request_values[target], selected_receipts[target] = request, raw_receipt

    held, held_before, trees = {}, {}, {}
    package, package_before, content, content_bytes = None, None, None, None

    def unchanged():
        require_no_signing_secret(environ)
        if (set(held) != set(held_before)
                or canonical_json_bytes(_records(validations)) != record_bytes
                or _native_archives(records) != archives
                or canonical_json_bytes(component_digests) != component_bytes
                or any(_read(path) != raw for path, raw in original_files.items())
                or any(_inventory(path, allow_empty=True) != before for path, before in retained_sources.items())
                or any(_inventory(path, allow_empty=True) != before for path, before in trees.items())
                or any(_view(held[target]) != before for target, before in held_before.items())
                or (package is not None and _view(package) != package_before)
                or (content is not None and canonical_json_bytes(content) != content_bytes)):
            raise ValueError("Core metadata original inputs, private evidence or caller policy changed")

    with tempfile.TemporaryDirectory(prefix="core-metadata-inputs-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, [root, *original_files, *retained_sources, *archives,
            *(Path(value["packageStage"]) for value in request_values.values())])
        try:
            with ExitStack() as stack:
                for target in SDK_FACADE_TARGETS:
                    record = records[target]
                    arguments = dict(facade_request=Path(record["facadeRequest"]), repository_root=root, environ=environ,
                        tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key,
                        java_executable=java_executable, policy_revision=policy_revision,
                        required_trust_domain=required_trust_domain, tooling_keyring=tooling_keyring,
                        tooling_keys_directory=tooling_keys_directory)
                    if "nativeCompilerArchive" in record:
                        arguments["native_compiler_archive"] = Path(record["nativeCompilerArchive"])
                    if "captureRoot" in record:
                        context = verified_retained_sdk_facade_validation(plan, Path(record["validationReceipt"]),
                            capture_root=Path(record["captureRoot"]), **arguments)
                    else:
                        context = verified_original_sdk_facade_validation(plan, Path(record["validationReceipt"]),
                            artifact_id=record["artifactId"], artifact_sha256=record["artifactSha256"],
                            trusted_workflow_sha=trusted_workflow_sha, token=token, **arguments)
                    verified = stack.enter_context(context)
                    if (verified["receiptBytes"] != selected_receipts[target]
                            or canonical_json_bytes(verified["receipt"]) != selected_receipts[target]
                            or _read(verified["receiptPath"]) != selected_receipts[target]):
                        raise ValueError("Core metadata original reader returned a different selected receipt")
                    held[target], held_before[target] = verified, _view(verified)
                    for name in ("stage", "capture"):
                        path = Path(verified[name])
                        trees[path] = _inventory(path, allow_empty=True)
                    unchanged()

                first = request_values[SDK_FACADE_TARGETS[0]]
                package_stage = private / "package/stage"
                package_path = private / "package/phase-receipt.json"
                snapshot_regular_tree(Path(first["packageStage"]), package_stage)
                package_path.write_bytes(package_bytes)
                package = {"stage": package_stage, "receiptPath": package_path, "receiptBytes": package_bytes,
                           "receipt": validate_phase_receipt(load_canonical_json_bytes(package_bytes))}
                package_before = _view(package)
                invocation = private / "metadata-request.json"
                write_canonical_json(invocation, {
                    "sdkVersion": package["receipt"]["productVersion"], "packageStage": str(package_stage),
                    "packageReceipt": str(package_path), "contractDigest": contract_digest,
                    "componentDigests": load_canonical_json_bytes(component_bytes),
                    "validations": {target: {"stageRoot": str(held[target]["stage"]),
                        "phaseReceipt": str(held[target]["receiptPath"])} for target in SDK_FACADE_TARGETS},
                })
                content = write_facade_metadata_content(invocation, private / "expected-content.json")
                content_bytes = canonical_json_bytes(content)
                trees[private] = _inventory(private)
                unchanged()
                try:
                    yield {"package": package, "validations": held, "request": invocation,
                           "expectedContent": content, "expectedContentBytes": content_bytes}
                finally:
                    unchanged()
            # Reader exit failures propagate; original caller inputs are rechecked
            # after all contexts close, without accessing their deleted private paths.
            trees = {path: before for path, before in trees.items() if path == private}
            unchanged()
        finally:
            # Any remaining reader-owned paths may already have been cleaned up.
            trees = {path: before for path, before in trees.items() if path == private}
            unchanged()
