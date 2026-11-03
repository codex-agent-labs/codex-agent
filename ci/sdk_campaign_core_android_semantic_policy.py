"""Decode independently pinned Core/Android semantic controls before observation.

This reader snapshots caller authority. It does not authenticate the policy's
origin, inspect captured originals, run a verifier, or grant release admission.
"""

import re
from pathlib import Path
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, require_exact_keys,
    require_sha256, require_string,
)
from products.registry import (
    PhaseInstanceId, SDK_FACADE_CONTRACT_COMPONENTS, SDK_FACADE_TARGETS,
)
from products.sdk_facade_inputs import _EVIDENCE_FIELDS
from products.sdk_facade_validation import _original_path
from products.sdk_facade_validation_admission import _NON_NATIVE_TARGETS


_MAVEN = {PhaseInstanceId("sdk", component, phase, target)
          for component, target in (("sdk-core", "common"), ("sdk-android", "android"))
          for phase in ("binary", "package")}
_OID = re.compile(r"[0-9a-f]{40}")
_MAVEN_KEYS = {"capture_root", "plan", "repository_root", "binary_contract_evidence",
               "original_context", "keyring", "keys_directory", "android_runtime_archive",
               "binary_original_context"}
_CORE_VALIDATION_KEYS = {"captureRoot", "plan", "facadeRequest", "originalContext",
                         "originalWorkerDirectory", "nativeCompilerArchive"}
_CORE_POLICY_KEYS = {"repository_root", "tooling_evidence", "tooling_public_key",
                     "java_executable", "policy_revision", "required_trust_domain",
                     "tooling_keyring", "tooling_keys_directory"}
_CORE_METADATA_KEYS = {"root", "records", "repository", "policy_revision", "policy"}
_CORE_METADATA_POLICY_PATHS = {"plan", "toolingEvidence", "toolingPublicKey",
                               "javaExecutable", "toolingKeyring", "toolingKeysDirectory"}
_CORE_METADATA_POLICY_KEYS = _CORE_METADATA_POLICY_PATHS | {"validations", "contractDigest",
    "componentDigests", "toolingTrustDomain", "originalContext"}
_ANDROID_KEYS = {"receipts", "plan", "repository", "original_validation",
                 "metadata_evidence_root", "metadata_evidence_records", "metadata_policy",
                 "policy_revision"}
_ANDROID_ORIGINAL_KEYS = {"validation_artifact_id", "validation_artifact_sha256",
                          "trusted_workflow_sha", "trusted_android_workflow_sha",
                          "expected_original_run_id", "expected_original_run_attempt",
                          "compatibility_request", "binary_contract_evidence",
                          "trusted_source_commit", "trusted_source_tree", "tooling_evidence",
                          "tooling_public_key", "java_executable", "apkanalyzer_executable",
                          "required_trust_domain", "tooling_keyring", "tooling_keys_directory"}
_ANDROID_METADATA_KEYS = {"plan", "validationCapture", "packageStage", "packageReceipt",
                          "binaryStage", "binaryReceipt", "compatibilityRequest",
                          "toolingEvidence", "toolingPublicKey", "javaExecutable",
                          "apkanalyzerExecutable", "toolingKeyring", "toolingKeysDirectory",
                          "binaryContractEvidence", "trustedSourceCommit", "trustedSourceTree",
                          "originalContext", "toolingTrustDomain"}


def _path(value, label, *, optional=False):
    if optional and value is None:
        return None
    path = Path(require_string(value, label))
    if not path.is_absolute() or str(path) != value or ".." in path.parts:
        raise ValueError(f"{label} must be an absolute normalized path")
    return path


def _paths(control, fields, label, *, optional=()):
    for field in fields:
        control[field] = _path(control[field], f"{label} {field}", optional=field in optional)


def _trust(value, label):
    if type(value) is not str or value not in {"development", "release"}:
        raise ValueError(f"{label} must be development or release")


def _oid(value, label):
    if type(value) is not str or _OID.fullmatch(value) is None:
        raise ValueError(f"{label} must be a Git object ID")


def _evidence(value, label):
    value = require_exact_keys(value, _EVIDENCE_FIELDS, label)
    _trust(value["expectedTrustDomain"], label)
    if (value["keyring"] is None) != (value["keysDirectory"] is None):
        raise ValueError(f"{label} keyring pair differs")
    for field in _EVIDENCE_FIELDS - {"expectedTrustDomain"}:
        _path(value[field], f"{label} {field}", optional=field in {"keyring", "keysDirectory"})
    return value


def _parse(raw):
    policy = require_exact_keys(load_canonical_json_bytes(raw),
                                {"schemaVersion", "family", "controls"},
                                "Core/Android semantic policy")
    if type(policy["schemaVersion"]) is not int or policy["schemaVersion"] != 1 \
            or policy["family"] != "core-android":
        raise ValueError("Core/Android semantic policy schema or family differs")
    controls = require_exact_keys(policy["controls"],
        {"maven_controls", "core_validation_controls", "core_validation_policy",
         "core_metadata_control", "android_control"}, "Core/Android semantic controls")

    rows = controls["maven_controls"]
    if type(rows) is not list or len(rows) != len(_MAVEN):
        raise ValueError("Core/Android semantic policy requires four Maven rows")
    maven = {}
    for row in rows:
        row = require_exact_keys(row, {"identity", "control"}, "Maven semantic row")
        identity = require_exact_keys(row["identity"],
                                      {"product", "component", "phase", "target"},
                                      "Maven semantic identity")
        instance = PhaseInstanceId(*(require_string(identity[field], field) for field in
                                     ("product", "component", "phase", "target")))
        if instance not in _MAVEN or instance in maven:
            raise ValueError("Maven semantic identity is unknown or duplicated")
        control = dict(require_exact_keys(row["control"], _MAVEN_KEYS, "Maven semantic control"))
        _paths(control, {"capture_root", "plan", "repository_root", "keyring",
                         "keys_directory", "android_runtime_archive"}, "Maven",
               optional={"keyring", "keys_directory", "android_runtime_archive"})
        _evidence(control["binary_contract_evidence"], "Maven binary Contract")
        context_keys = {"repositoryRoot", "workerRoot"} | \
            ({"compatibilityRequest"} if instance.phase == "package" else set())
        context = require_exact_keys(control["original_context"], context_keys, "Maven original context")
        for field in context_keys:
            _path(context[field], "Maven original context " + field)
        binary_context = control["binary_original_context"]
        if instance.phase == "package":
            binary_context = require_exact_keys(binary_context,
                {"repositoryRoot", "workerRoot"}, "Maven binary original context")
            for field in binary_context:
                _path(binary_context[field], "Maven binary original context " + field)
        elif binary_context is not None:
            raise ValueError("Maven binary original context belongs only to package")
        if instance.component == "sdk-core" and control["android_runtime_archive"] is not None:
            raise ValueError("Core Maven cannot select an Android runtime archive")
        maven[instance] = control

    validations = require_exact_keys(controls["core_validation_controls"],
        set(SDK_FACADE_TARGETS), "Core validation semantic controls")
    core_validations = {}
    for target, value in validations.items():
        control = dict(require_exact_keys(value, _CORE_VALIDATION_KEYS,
                                          f"Core {target} semantic control"))
        _paths(control, {"captureRoot", "plan", "facadeRequest", "nativeCompilerArchive"},
               f"Core {target}", optional={"nativeCompilerArchive"})
        context = require_exact_keys(control["originalContext"],
            {"repositoryRoot", "androidSdkDirectory"} |
            ({"javaExecutable"} if target == "windows-x64" else set()),
            f"Core {target} original context")
        for field in context:
            _original_path(context[field], f"Core {target} original context {field}")
        _original_path(control["originalWorkerDirectory"], f"Core {target} original worker")
        core_validations[target] = control

    core_policy = dict(require_exact_keys(controls["core_validation_policy"],
                                          _CORE_POLICY_KEYS, "Core validation policy"))
    _paths(core_policy, {"repository_root", "tooling_evidence", "tooling_public_key",
                         "java_executable", "tooling_keyring", "tooling_keys_directory"},
           "Core validation", optional={"tooling_keyring", "tooling_keys_directory"})
    _oid(core_policy["policy_revision"], "Core policy revision")
    _trust(core_policy["required_trust_domain"], "Core validation trust domain")
    if (core_policy["tooling_keyring"] is None) != (core_policy["tooling_keys_directory"] is None):
        raise ValueError("Core validation tooling keyring pair differs")

    metadata = dict(require_exact_keys(controls["core_metadata_control"],
                                       _CORE_METADATA_KEYS, "Core metadata control"))
    _paths(metadata, {"root", "repository"}, "Core metadata")
    _oid(metadata["policy_revision"], "Core metadata policy revision")
    if type(metadata["records"]) is not list:
        raise ValueError("Core metadata records must be a list")
    for record in metadata["records"]:
        require_exact_keys(record, {"receiptSha256", "captureRoot"}, "Core metadata record")
        require_sha256(record["receiptSha256"], "Core metadata receipt")
        require_string(record["captureRoot"], "Core metadata capture")
    metadata_policy = require_exact_keys(metadata["policy"], _CORE_METADATA_POLICY_KEYS,
                                         "Core metadata policy")
    for field in _CORE_METADATA_POLICY_PATHS:
        _path(metadata_policy[field], f"Core metadata {field}",
              optional=field in {"toolingKeyring", "toolingKeysDirectory"})
    _trust(metadata_policy["toolingTrustDomain"], "Core metadata trust domain")
    if (metadata_policy["toolingTrustDomain"] == "release") != \
            (metadata_policy["toolingKeyring"] is not None and
             metadata_policy["toolingKeysDirectory"] is not None):
        raise ValueError("Core metadata tooling keyring pair differs from trust domain")
    require_sha256(metadata_policy["contractDigest"], "Core metadata Contract digest")
    components = require_exact_keys(metadata_policy["componentDigests"],
        set(SDK_FACADE_CONTRACT_COMPONENTS.values()), "Core metadata components")
    for digest in components.values():
        require_sha256(digest, "Core metadata component digest")
    context = require_exact_keys(metadata_policy["originalContext"],
        {"repositoryRoot", "metadataRequest"}, "Core metadata original context")
    for field in context:
        _path(context[field], f"Core metadata original context {field}")
    records = require_exact_keys(metadata_policy["validations"], set(SDK_FACADE_TARGETS),
                                 "Core metadata validations")
    for target, record in records.items():
        fields = {"validationReceipt", "facadeRequest", "captureRoot"} | \
            ({"nativeCompilerArchive"} if target not in _NON_NATIVE_TARGETS else set())
        record = require_exact_keys(record, fields, f"Core metadata {target} validation")
        for field in fields:
            _path(record[field], f"Core metadata {target} {field}")

    android = dict(require_exact_keys(controls["android_control"],
                                      _ANDROID_KEYS, "Android semantic control"))
    _paths(android, {"plan", "repository", "metadata_evidence_root"}, "Android")
    receipts = require_exact_keys(android["receipts"], {"binary", "package"},
                                  "Android predecessor receipts")
    android["receipts"] = {key: _path(value, f"Android {key} receipt")
                           for key, value in receipts.items()}
    original = require_exact_keys(android["original_validation"], _ANDROID_ORIGINAL_KEYS,
                                  "Android original validation")
    for field in ("validation_artifact_id", "expected_original_run_id",
                  "expected_original_run_attempt"):
        if type(original[field]) is not int or original[field] < 1:
            raise ValueError(f"Android {field} must be a positive integer")
    require_sha256(original["validation_artifact_sha256"], "Android validation artifact digest")
    for field in ("trusted_workflow_sha", "trusted_android_workflow_sha"):
        _oid(original[field], f"Android {field}")
    for field in ("compatibility_request", "tooling_evidence", "tooling_public_key",
                  "java_executable", "apkanalyzer_executable", "tooling_keyring",
                  "tooling_keys_directory"):
        _path(original[field], f"Android original {field}",
              optional=field in {"tooling_keyring", "tooling_keys_directory"})
    _evidence(original["binary_contract_evidence"], "Android binary Contract")
    for field in ("trusted_source_commit", "trusted_source_tree"):
        _oid(original[field], f"Android {field}")
    _trust(original["required_trust_domain"], "Android original trust domain")
    if type(android["metadata_evidence_records"]) is not list or len(android["metadata_evidence_records"]) != 1:
        raise ValueError("Android metadata requires one evidence record")
    for record in android["metadata_evidence_records"]:
        require_exact_keys(record, {"receiptSha256", "captureRoot"}, "Android metadata record")
        require_sha256(record["receiptSha256"], "Android metadata receipt")
        require_string(record["captureRoot"], "Android metadata capture")
    metadata_policy = require_exact_keys(android["metadata_policy"], _ANDROID_METADATA_KEYS,
                                         "Android metadata policy")
    for field in _ANDROID_METADATA_KEYS - {"binaryContractEvidence", "trustedSourceCommit",
                                             "trustedSourceTree", "originalContext", "toolingTrustDomain"}:
        _path(metadata_policy[field], f"Android metadata {field}",
              optional=field in {"toolingKeyring", "toolingKeysDirectory"})
    _evidence(metadata_policy["binaryContractEvidence"], "Android metadata binary Contract")
    for field in ("trustedSourceCommit", "trustedSourceTree"):
        _oid(metadata_policy[field], f"Android metadata {field}")
    context = require_exact_keys(metadata_policy["originalContext"],
        {"repositoryRoot", "metadataRequest"}, "Android metadata original context")
    for field in context:
        _path(context[field], f"Android metadata original context {field}")
    _trust(metadata_policy["toolingTrustDomain"], "Android metadata trust domain")
    _oid(android["policy_revision"], "Android policy revision")
    return maven, core_validations, core_policy, metadata, android


def load_core_android_semantic_policy(path: Path):
    """Return five verifier controls and exact bytes for independent pinning."""
    raw = read_regular_file_bytes(Path(path), max_bytes=1024 * 1024,
                                  reject_symlink_parents=True)
    return *_parse(raw), raw
