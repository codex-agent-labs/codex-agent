"""Bind a selected iOS package object to its full original execution replay.

The caller authenticates the retained uploads and selected phase object.  This
context adds no transport or host authority; it holds the existing semantic
gate and checks that the exact selected package bytes are the ones it replayed.
"""

from contextlib import ExitStack, contextmanager, nullcontext
from contextvars import ContextVar
import os
from pathlib import Path
import re

from .inventory import (canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
                        regular_file_inventory, require_exact_keys, require_sha256, sha256_bytes)
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
    if __package__ == "ci.products":
        from ..sdk_ios_original_package import verified_retained_ios_package
    else:
        from sdk_ios_original_package import verified_retained_ios_package

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


_HOLD = ContextVar("held_original_apple_packages", default=None)


@contextmanager
def holding_original_packages():
    """Consumer-owned, in-process custody of complete original package gates.

    Inside this scope an original admission runs its complete gate once and keeps
    the yielded private capture open until the scope exits; a later consumer in
    the same process may use it only on an exact receipt/upload/policy match.
    Nothing is serialized; every inventory/unchanged check runs at scope exit.
    """
    if _HOLD.get() is not None:
        raise ValueError("Original Apple package custody cannot be nested")
    with ExitStack() as stack:
        registry = {"stack": stack, "held": {}}
        token = _HOLD.set(registry)
        try:
            yield registry
        finally:
            _HOLD.reset(token)


def active_package_hold():
    return _HOLD.get()


def _file_identity(path):
    if path is None:
        return None
    return sha256_bytes(read_regular_file_bytes(Path(path), max_bytes=128 * 1024 * 1024,
                                                reject_symlink_parents=True))


def _tree_identity(path):
    if path is None:
        return None
    return sha256_bytes(canonical_json_bytes(regular_file_inventory(Path(path), allow_empty=True)))


def package_policy_identity(*, keyring, keys_directory, tooling_evidence, tooling_public_key,
        java_executable, policy_revision, required_trust_domain, tooling_keyring=None,
        tooling_keys_directory=None, retained_sdk_inputs_source=None, repository_root=None):
    """Exact caller policy by content, so equal authority in different paths matches."""
    return canonical_json_bytes({
        "keyring": _file_identity(keyring), "keysDirectory": _tree_identity(keys_directory),
        "toolingEvidence": _tree_identity(tooling_evidence),
        "toolingPublicKey": _file_identity(tooling_public_key),
        "javaExecutable": str(Path(java_executable).resolve(strict=True)),
        "policyRevision": policy_revision, "requiredTrustDomain": required_trust_domain,
        "toolingKeyring": _file_identity(tooling_keyring),
        "toolingKeysDirectory": _tree_identity(tooling_keys_directory),
        "retainedSdkInputsSource": retained_sdk_inputs_source,
        "repositoryRoot": None if repository_root is None else str(Path(repository_root).resolve(strict=True)),
    })


def held_original_package(registry, receipt_bytes, *, artifact_id, artifact_sha256, policy):
    """Return an already fully verified original only on an exact identity match."""
    if registry is None:
        return None
    entry = registry["held"].get(sha256_bytes(receipt_bytes))
    if entry is None:
        return None
    key, value = entry
    # ``policy`` is computed only for a candidate: absent custody reads nothing.
    if key != (receipt_bytes, artifact_id, artifact_sha256, policy() if callable(policy) else policy):
        return None
    shard = verify_phase_shard(value["original"] / "shard", _INSTANCE)
    if (shard["receiptBytes"] != receipt_bytes or value["receiptBytes"] != receipt_bytes
            or canonical_json_bytes(value["receipt"]) != receipt_bytes):
        raise ValueError("Held original Apple package differs from its exact receipt")
    try:
        from runtime_reference_transport import count
    except ImportError:  # pragma: no cover - isolated script namespace without transport
        pass
    else:
        count("applePackageHeldReuses")
    return value


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
        self._original = None
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

    @classmethod
    def from_original(cls, envelope, *, plan, selected_receipt, artifact_id, artifact_sha256,
            trusted_workflow_sha, environ, token, retained_sdk_inputs_source=None, **policy):
        """Keep caller-owned original selection; run its full gate only in verify()."""
        from .reuse import _validate_envelope

        instance, selected = _validate_envelope(envelope)
        if instance != _INSTANCE:
            raise ValueError("Original Apple admission requires the selected package")
        plan, receipt = Path(plan).resolve(strict=True), Path(selected_receipt).resolve(strict=True)
        if read_regular_file_bytes(receipt, reject_symlink_parents=True) != selected["receiptBytes"]:
            raise ValueError("Original Apple admission differs from its selected receipt")
        result = cls([], **policy)
        result._original = (plan, receipt, selected["receiptSha256"], dict(
            artifact_id=artifact_id, artifact_sha256=artifact_sha256,
            trusted_workflow_sha=trusted_workflow_sha, environ=dict(environ), token=token,
            ephemeral_capture=True, expected_plan_revision=selected["receipt"]["producer"]["commit"],
            **({"retained_sdk_inputs_source": load_canonical_json_bytes(
                canonical_json_bytes(retained_sdk_inputs_source))} if retained_sdk_inputs_source is not None else {})))
        return result

    def verify(self, envelope):
        """Return only after original capture, content and selected object agree."""
        from .reuse import _validate_envelope

        require_no_signing_secret(os.environ)
        instance, selected = _validate_envelope(envelope)
        if instance != _INSTANCE:
            raise ValueError("Apple package admission requires the exact iOS package envelope")
        binding = (selected["receiptBytes"], selected["receiptSha256"],
                   selected["objectSha256"], canonical_json_bytes(selected["receipt"]))
        if self._original is not None:
            if __package__ == "ci.products":
                from ..sdk_ios_original_package import verified_original_ios_package
            else:
                from sdk_ios_original_package import verified_original_ios_package
            plan, receipt, digest, options = self._original
            if digest != binding[1]:
                raise ValueError("Apple package admission changes its selected original")
            registry = _HOLD.get()
            if registry is not None:
                # Same complete gate, kept open for this process's consumer.
                held = dict(options, ephemeral_capture=False)
                key = (binding[0], held["artifact_id"], held["artifact_sha256"], package_policy_identity(
                    **{name: self._policy[name] for name in ("keyring", "keys_directory", "tooling_evidence",
                        "tooling_public_key", "java_executable", "policy_revision", "required_trust_domain",
                        "tooling_keyring", "tooling_keys_directory", "repository_root")},
                    retained_sdk_inputs_source=held.get("retained_sdk_inputs_source")))
                entry = registry["held"].get(digest)
                if entry is None:
                    value = registry["stack"].enter_context(
                        verified_original_ios_package(plan, receipt, **held, **self._policy))
                    registry["held"][digest] = (key, value)
                elif entry[0] != key:
                    raise ValueError("Held original Apple package has a different upload or policy")
                context = nullcontext(registry["held"][digest][1])
            else:
                context = verified_original_ios_package(plan, receipt, **options, **self._policy)
        else:
            record = self._records.get(selected["receiptSha256"])
            if record is None:
                raise ValueError("Apple package admission lacks authenticated original evidence")
            context = verified_selected_ios_package(record["selectedStage"], record["selectedReceipt"],
                plan=record["plan"], package_capture=record["packageCapture"],
                sdk_capture=record["sdkCapture"], **self._policy)
        with context as original:
            shard = verify_phase_shard(original["original"] / "shard", _INSTANCE)
            if (shard["receiptBytes"] != binding[0]
                    or shard["receiptSha256"] != binding[1]
                    or shard["objectSha256"] != binding[2]):
                raise ValueError("Original Apple package shard differs from the selected envelope")
        require_no_signing_secret(os.environ)
        if (selected["receiptBytes"], selected["receiptSha256"], selected["objectSha256"],
                canonical_json_bytes(selected["receipt"])) != binding:
            raise ValueError("Selected Apple package envelope changed during admission")
