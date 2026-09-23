"""Bind a selected Core validation object to its retained original replay.

The original checkout/worker expectations must come from independent caller
policy, not the uploaded execution context. This is not hosted-toolchain or
release admission: the caller still has to authenticate those expectations.
"""

from pathlib import Path
import os
import tempfile

from .inventory import (canonical_json_bytes, load_canonical_json_bytes,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys, require_integer)
from .receipt import verify_output_manifest_identity
from .registry import SDK_FACADE_TARGETS
from .restore import verify_phase_shard
from .reuse import _validate_envelope
from .sdk_facade_validation import _original_path
from .sdk_package import _require_capability_output_separate
from .signing_isolation import require_no_signing_secret


def verify_campaign_core_validation(
    envelope, stage, capture_root, *, plan, facade_request, repository_root,
    original_context, original_worker_directory, tooling_evidence,
    tooling_public_key, java_executable, policy_revision, required_trust_domain,
    environ=None, tooling_keyring=None, tooling_keys_directory=None,
    native_compiler_archive=None,
) -> bytes:
    """Return exact original receipt bytes after all selected-original gates.

    The caller must independently authenticate the two original path pins and
    the tooling/Contract inputs. A matching uploaded path is only consistency.
    """
    if __package__ == "products":
        from sdk_facade_original_validation import verified_retained_sdk_facade_validation
    else:
        from ..sdk_facade_original_validation import verified_retained_sdk_facade_validation

    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if environment is not os.environ:
        require_no_signing_secret(os.environ)
    identity, selected = _validate_envelope(envelope)
    if (identity.product, identity.component, identity.phase) != ("sdk", "sdk-core", "validation") \
            or identity.target not in SDK_FACADE_TARGETS:
        raise ValueError("Campaign Core requires an exact validation envelope")
    context = require_exact_keys(original_context,
        {"repositoryRoot", "androidSdkDirectory"} |
        ({"javaExecutable"} if identity.target == "windows-x64" else set()),
        "Independent original Core context")
    _original_path(context["repositoryRoot"], "Independent original Core checkout")
    worker = _original_path(original_worker_directory, "Independent original Core worker")
    pins = canonical_json_bytes({"context": context, "worker": worker})
    stage, capture_root = Path(stage), Path(capture_root)
    before = regular_file_inventory(stage)
    manifest = verify_output_manifest_identity(stage, identity.product, identity.component,
        identity.phase, identity.target, selected["receipt"]["productVersion"])
    if manifest["outputs"] != selected["receipt"]["outputs"]:
        raise ValueError("Campaign Core stage differs from its selected receipt")

    def binding():
        _, value = _validate_envelope(envelope)
        return (value["receiptBytes"], value["receiptSha256"], value["objectSha256"],
                canonical_json_bytes(value["receipt"]))

    expected = binding()

    def unchanged():
        require_no_signing_secret(environment)
        if (binding() != expected or regular_file_inventory(stage) != before
                or canonical_json_bytes({"context": original_context,
                                         "worker": original_worker_directory}) != pins):
            raise ValueError("Campaign Core selection, stage or caller path pins changed")

    unchanged()
    try:
        with tempfile.TemporaryDirectory(prefix="campaign-core-original-") as temporary:
            receipt = Path(temporary).resolve() / "phase-receipt.json"
            _require_capability_output_separate(receipt, (stage, capture_root, plan, facade_request,
                repository_root, tooling_evidence, tooling_public_key, java_executable,
                *(path for path in (tooling_keyring, tooling_keys_directory,
                                   native_compiler_archive) if path is not None)))
            receipt.write_bytes(expected[0])
            with verified_retained_sdk_facade_validation(
                plan, receipt, capture_root=capture_root, facade_request=facade_request,
                repository_root=repository_root, environ=environment,
                tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key,
                java_executable=java_executable, policy_revision=policy_revision,
                required_trust_domain=required_trust_domain,
                tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory,
                native_compiler_archive=native_compiler_archive,
            ) as original:
                shard = verify_phase_shard(Path(original["original"]) / "shard", identity)
                record = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(
                    Path(original["original"]) / "context/execution-context.json",
                    max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)),
                    {"schemaVersion", "target", "buildKey", "producer", "originalContext",
                     "workerDirectory"}, "Selected original Core execution context")
                if (require_integer(record["schemaVersion"], "Selected original Core context schema", 1) != 1
                        or record["target"] != identity.target
                        or record["buildKey"] != selected["receipt"]["buildKey"]
                        or record["producer"] != selected["receipt"]["producer"]
                        or record["originalContext"] != context or record["workerDirectory"] != worker):
                    raise ValueError("Campaign Core original paths differ from independent caller pins")
                if (original["receiptBytes"] != expected[0]
                        or any(shard[name] != value for name, value in (
                            ("receiptBytes", expected[0]), ("receiptSha256", expected[1]),
                            ("objectSha256", expected[2]),
                            ("buildKey", selected["receipt"]["buildKey"])))
                        or regular_file_inventory(Path(original["stage"])) != before):
                    raise ValueError("Campaign Core original differs from selected object or stage")
                unchanged()
            unchanged()
            if receipt.read_bytes() != expected[0]:
                raise ValueError("Campaign Core private receipt changed during replay")
    finally:
        unchanged()
    return expected[0]
