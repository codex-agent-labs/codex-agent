"""Caller-owned Core/Android semantic controls remain exact and typed."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ci.sdk_campaign_core_android_semantic_policy import load_core_android_semantic_policy
from products.inventory import canonical_json_bytes
from products.registry import SDK_FACADE_CONTRACT_COMPONENTS, SDK_FACADE_TARGETS


_SHA = "sha256:" + "a" * 64
_PATH = "/var/tmp/sdk-policy-input"
_EVIDENCE = {"stageRoot": _PATH, "phaseReceipt": _PATH, "attestation": _PATH,
             "attestationSignature": _PATH, "publicKey": _PATH,
             "expectedTrustDomain": "development", "keyring": None, "keysDirectory": None}


def _policy():
    maven = []
    for component, target in (("sdk-core", "common"), ("sdk-android", "android")):
        for phase in ("binary", "package"):
            maven.append({"identity": {"product": "sdk", "component": component,
                                       "phase": phase, "target": target},
                          "control": {"capture_root": _PATH, "plan": _PATH,
                                      "repository_root": _PATH,
                                      "binary_contract_evidence": deepcopy(_EVIDENCE),
                                      "original_context": {"repositoryRoot": _PATH,
                                                           "workerRoot": _PATH,
                                                           **({"compatibilityRequest": _PATH}
                                                              if phase == "package" else {})},
                                      "keyring": None, "keys_directory": None,
                                      "android_runtime_archive": None,
                                      "binary_original_context":
                                          {"repositoryRoot": _PATH, "workerRoot": _PATH}
                                          if phase == "package" else None}})
    validations = {target: {"captureRoot": _PATH, "plan": _PATH,
                            "facadeRequest": _PATH,
                            "originalContext": {"repositoryRoot": _PATH,
                                                "androidSdkDirectory": _PATH,
                                                **({"javaExecutable": _PATH}
                                                   if target == "windows-x64" else {})},
                            "originalWorkerDirectory": _PATH,
                            "nativeCompilerArchive": None}
                   for target in SDK_FACADE_TARGETS}
    from products.sdk_facade_validation_admission import _NON_NATIVE_TARGETS
    metadata_validations = {target: {"validationReceipt": _PATH, "facadeRequest": _PATH,
                                      "captureRoot": _PATH,
                                      **({"nativeCompilerArchive": _PATH}
                                         if target not in _NON_NATIVE_TARGETS else {})}
                            for target in SDK_FACADE_TARGETS}
    android_original = {"validation_artifact_id": 7,
                        "validation_artifact_sha256": _SHA,
                        "trusted_workflow_sha": "a" * 40,
                        "trusted_android_workflow_sha": "a" * 40,
                        "expected_original_run_id": 8,
                        "expected_original_run_attempt": 1,
                        "compatibility_request": _PATH,
                        "binary_contract_evidence": deepcopy(_EVIDENCE),
                        "trusted_source_commit": "a" * 40,
                        "trusted_source_tree": "a" * 40,
                        "tooling_evidence": _PATH,
                        "tooling_public_key": _PATH,
                        "java_executable": _PATH,
                        "apkanalyzer_executable": _PATH,
                        "required_trust_domain": "development",
                        "tooling_keyring": None,
                        "tooling_keys_directory": None}
    android_metadata = {name: _PATH for name in
        ("plan", "validationCapture", "packageStage", "packageReceipt", "binaryStage",
         "binaryReceipt", "compatibilityRequest", "toolingEvidence", "toolingPublicKey",
         "javaExecutable", "apkanalyzerExecutable")}
    android_metadata.update({"toolingKeyring": None, "toolingKeysDirectory": None,
                             "binaryContractEvidence": deepcopy(_EVIDENCE),
                             "trustedSourceCommit": "a" * 40,
                             "trustedSourceTree": "a" * 40,
                             "originalContext": {"repositoryRoot": _PATH,
                                                 "metadataRequest": _PATH},
                             "toolingTrustDomain": "development"})
    return {"schemaVersion": 1, "family": "core-android", "controls": {
        "maven_controls": maven,
        "core_validation_controls": validations,
        "core_validation_policy": {"repository_root": _PATH,
            "tooling_evidence": _PATH, "tooling_public_key": _PATH,
            "java_executable": _PATH, "policy_revision": "a" * 40,
            "required_trust_domain": "development", "tooling_keyring": None,
            "tooling_keys_directory": None},
        "core_metadata_control": {"root": _PATH, "repository": _PATH,
            "policy_revision": "a" * 40, "records": [],
            "policy": {"plan": _PATH, "toolingEvidence": _PATH,
                "toolingPublicKey": _PATH, "javaExecutable": _PATH,
                "toolingKeyring": None, "toolingKeysDirectory": None,
                "validations": metadata_validations, "contractDigest": _SHA,
                "componentDigests": {component: _SHA for component in
                                     SDK_FACADE_CONTRACT_COMPONENTS.values()},
                "toolingTrustDomain": "development",
                "originalContext": {"repositoryRoot": _PATH, "metadataRequest": _PATH}}},
        "android_control": {"receipts": {"binary": _PATH, "package": _PATH},
            "plan": _PATH, "repository": _PATH,
            "original_validation": android_original,
            "metadata_evidence_root": _PATH,
            "metadata_evidence_records": [{"receiptSha256": _SHA,
                                           "captureRoot": "original"}],
            "metadata_policy": android_metadata, "policy_revision": "a" * 40}}}


class CoreAndroidSemanticPolicyTest(TestCase):
    def read(self, policy):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as temporary:
            path = Path(temporary) / "semantic.json"
            raw = canonical_json_bytes(policy)
            path.write_bytes(raw)
            return load_core_android_semantic_policy(path), raw

    def test_exact_controls_and_raw_snapshot(self):
        (maven, validations, core, metadata, android, captured), raw = self.read(_policy())
        self.assertEqual(raw, captured)
        self.assertEqual(4, len(maven))
        self.assertEqual(set(SDK_FACADE_TARGETS), set(validations))
        self.assertEqual(Path(_PATH), core["repository_root"])
        self.assertEqual(Path(_PATH), metadata["root"])
        self.assertEqual(Path(_PATH), android["receipts"]["binary"])
        self.assertNotIn("token", android)

    def test_missing_unknown_duplicate_and_wrong_type_reject(self):
        for change in (lambda p: p["controls"].pop("android_control"),
                       lambda p: p["controls"]["android_control"].update(token="secret"),
                       lambda p: p["controls"]["maven_controls"].__setitem__(1,
                           deepcopy(p["controls"]["maven_controls"][0])),
                       lambda p: p["controls"]["android_control"].update(plan=7),
                       lambda p: p["controls"]["android_control"]["original_validation"].update(
                           trusted_workflow_sha=_SHA),
                       lambda p: p["controls"]["android_control"]["original_validation"].update(
                           trusted_source_tree="Z" * 40),
                       lambda p: p["controls"]["core_validation_controls"].pop(
                           next(iter(SDK_FACADE_TARGETS))),
                       lambda p: p["controls"]["core_metadata_control"]["policy"].update(
                           observedReceipt=_SHA)):
            policy = _policy()
            change(policy)
            with self.assertRaises((ValueError, TypeError)):
                self.read(policy)

    def test_noncanonical_and_duplicate_json_keys_reject(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as temporary:
            path = Path(temporary) / "semantic.json"
            path.write_bytes(canonical_json_bytes(_policy()) + b" ")
            with self.assertRaises(ValueError):
                load_core_android_semantic_policy(path)
            path.write_bytes(b'{"family":"core-android","family":"core-android"}\n')
            with self.assertRaises(ValueError):
                load_core_android_semantic_policy(path)
