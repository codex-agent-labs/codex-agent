"""Bind a selected iOS package object to its full original execution replay.

The caller authenticates the retained uploads and selected phase object.  This
context adds no transport or host authority; it holds the existing semantic
gate and checks that the exact selected package bytes are the ones it replayed.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import re

from .inventory import (canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
                        regular_file_inventory, require_exact_keys, require_sha256)
from .receipt import validate_phase_receipt, verify_output_manifest_identity
from .registry import PhaseInstanceId
from .restore import verify_phase_shard
from .signing_isolation import require_no_signing_secret


_INSTANCE = PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
_RECORD_KEYS = {"receiptSha256", "selectedStage", "selectedReceipt", "plan",
                "packageCapture", "sdkCapture"}


@contextmanager
def verified_selected_ios_package(selected_stage, selected_receipt, *, plan,
        package_capture, sdk_capture, keyring, keys_directory, repository_root,
        tooling_evidence, tooling_public_key, java_executable, policy_revision,
        required_trust_domain, tooling_keyring=None, tooling_keys_directory=None):
    """Yield only while original package semantics and selected bytes agree.

    The enclosing upload/catalog and caller tooling policy must already be
    authenticated.  The original context replays source, Contract, S858,
    execution events and package semantics; this wrapper never substitutes a
    receipt or content-inventory check for that gate.
    """
    from ci.sdk_ios_original_package import verified_retained_ios_package

    stage = Path(selected_stage)
    receipt_path = Path(selected_receipt)
    raw = read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024,
                                  reject_symlink_parents=True)
    receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
    identity = tuple(receipt[field] for field in ("product", "component", "phase", "target"))
    if identity != ("sdk", "sdk-ios", "package", "ios"):
        raise ValueError("Selected Apple package has the wrong phase identity")
    manifest = verify_output_manifest_identity(stage, *identity, receipt["productVersion"])
    if manifest["outputs"] != receipt["outputs"]:
        raise ValueError("Selected Apple package manifest differs from its receipt")
    selected_inventory = regular_file_inventory(stage)

    def unchanged():
        if (read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024,
                                    reject_symlink_parents=True) != raw
                or regular_file_inventory(stage) != selected_inventory):
            raise ValueError("Selected Apple package changed during original replay")

    with verified_retained_ios_package(plan, receipt_path,
            package_capture=package_capture, sdk_capture=sdk_capture,
            keyring=keyring, keys_directory=keys_directory,
            repository_root=repository_root, tooling_evidence=tooling_evidence,
            tooling_public_key=tooling_public_key, java_executable=java_executable,
            policy_revision=policy_revision, required_trust_domain=required_trust_domain,
            tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory) as original:
        if (original["receiptBytes"] != raw or original["receipt"] != receipt
                or regular_file_inventory(original["stage"]) != selected_inventory):
            raise ValueError("Original Apple replay differs from the exact selected package")
        unchanged()
        try:
            yield original
        finally:
            unchanged()
    unchanged()


class ApplePackageAdmission:
    """Admit only the selected original shard after its complete package replay.

    The caller independently authenticates and restores each selected stage,
    receipt, package capture and SDK capture before supplying these paths.
    Neither the envelope nor an untrusted transport descriptor can supply them.
    """

    def __init__(self, records, *, repository_root, keyring, keys_directory,
            tooling_evidence, tooling_public_key, java_executable, policy_revision,
            required_trust_domain, tooling_keyring=None, tooling_keys_directory=None):
        if type(policy_revision) is not str or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", policy_revision) is None:
            raise ValueError("Apple package admission requires an exact caller policy revision")
        if required_trust_domain not in {"development", "release"}:
            raise ValueError("Apple package admission requires an exact caller trust domain")
        if type(records) not in (list, tuple):
            raise ValueError("Apple package admission requires selected original records")
        self._records = {}
        for value in records:
            record = require_exact_keys(value, _RECORD_KEYS, "Apple package admission record")
            digest = require_sha256(record["receiptSha256"], "Apple package original receipt")
            if digest in self._records:
                raise ValueError("Apple package original receipt is duplicated")
            paths = {name: Path(record[name]) for name in _RECORD_KEYS - {"receiptSha256"}}
            if any(not path.is_absolute() or path.resolve(strict=True) != path for path in paths.values()):
                raise ValueError("Apple package original paths must be absolute and non-symbolic")
            self._records[digest] = paths
        self._policy = dict(repository_root=Path(repository_root), keyring=Path(keyring),
            keys_directory=Path(keys_directory), tooling_evidence=Path(tooling_evidence),
            tooling_public_key=Path(tooling_public_key), java_executable=Path(java_executable),
            policy_revision=policy_revision, required_trust_domain=required_trust_domain,
            tooling_keyring=None if tooling_keyring is None else Path(tooling_keyring),
            tooling_keys_directory=None if tooling_keys_directory is None else Path(tooling_keys_directory))

    def verify(self, envelope):
        """Return only after original capture, content and selected object agree."""
        from .reuse import _validate_envelope

        require_no_signing_secret(os.environ)
        instance, selected = _validate_envelope(envelope)
        if instance != _INSTANCE:
            raise ValueError("Apple package admission requires the exact iOS package envelope")
        record = self._records.get(selected["receiptSha256"])
        if record is None:
            raise ValueError("Apple package admission lacks authenticated original evidence")
        binding = (selected["receiptBytes"], selected["receiptSha256"],
                   selected["objectSha256"], canonical_json_bytes(selected["receipt"]))
        with verified_selected_ios_package(record["selectedStage"], record["selectedReceipt"],
                plan=record["plan"], package_capture=record["packageCapture"],
                sdk_capture=record["sdkCapture"], **self._policy) as original:
            shard = verify_phase_shard(original["original"] / "shard", _INSTANCE)
            if (shard["receiptBytes"] != binding[0]
                    or shard["receiptSha256"] != binding[1]
                    or shard["objectSha256"] != binding[2]):
                raise ValueError("Original Apple package shard differs from the selected envelope")
        require_no_signing_secret(os.environ)
        if (selected["receiptBytes"], selected["receiptSha256"], selected["objectSha256"],
                canonical_json_bytes(selected["receipt"])) != binding:
            raise ValueError("Selected Apple package envelope changed during admission")
