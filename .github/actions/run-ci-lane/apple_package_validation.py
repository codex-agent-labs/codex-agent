"""Ordinary retained Apple package controls; never public-release acceptance.

Call within the existing verified-state owner. Publish the detached result only
after every outer owner has exited successfully. No product bodies are read.
"""

from pathlib import Path

import product_reuse as products
from impact import validate_remote_build_authorization
from products.inventory import (canonical_json_bytes, git_regular_blob_bytes,
    load_canonical_json_bytes, load_json_bytes, read_regular_file_bytes, sha256_bytes, require_exact_keys, require_sha256)
from products.restore import _VERIFICATION_SESSION
from products.signing_isolation import require_no_signing_secret
from reuse_qualification import CompletedFrozenReuse
from sdk_android_evidence_capture import _retained_dependency_plan


_BINARY = products.PhaseInstanceId("sdk", "sdk-ios", "binary", "ios")
_PACKAGE = products.PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
_MANIFEST = "codex-agent-runtime-ios/apple/Package.swift"
_LEGAL = ("LICENSE", "THIRD_PARTY_NOTICES.md",
          "legal/openai-codex/openai-codex-LICENSE.txt",
          "legal/openai-codex/openai-codex-NOTICE.txt")
_SOURCE_PATHS = (_MANIFEST, *_LEGAL, "Package.swift")


def _package_controls(envelopes, sources):
    """Project already-authenticated receipts; this function grants no authority."""
    binary, package = (envelopes[i]["receipt"] for i in (_BINARY, _PACKAGE))
    if binary["productVersion"] != package["productVersion"]:
        raise ValueError("Apple binary/package version differs")
    source_rows = {}
    for name in _SOURCE_PATHS:
        receipt = binary if name == _MANIFEST else package
        row = {"relativePath": name, "bytes": len(sources[name]),
               "sha256": sha256_bytes(sources[name])}
        if [item for item in receipt["inputs"]["inventory"] if item["relativePath"] == name] != [row]:
            raise ValueError("Apple package source differs from its native original: " + name)
        source_rows[name] = row
    if b'.binaryTarget(name: "CodexAgent", path: "CodexAgent.xcframework")' not in sources[_MANIFEST]:
        raise ValueError("Apple package lacks its fixed local binary target")
    version = package["productVersion"]
    outputs = package["outputs"]
    selected = {}
    for key, path in (("xcframework", f"outputs/apple/CodexAgent-{version}.xcframework.zip"),
                      ("checksum", f"outputs/apple/CodexAgent-{version}.xcframework.zip.sha256"),
                      ("package", f"outputs/apple/CodexAgentPackage-{version}.zip")):
        rows = [row for row in outputs if row["relativePath"] == path and row["kind"] == "apple"]
        if len(rows) != 1:
            raise ValueError("Apple native package lacks its exact archive/checksum output")
        selected[key] = rows[0]
    checksum = (selected["xcframework"]["sha256"].removeprefix("sha256:") + "\n").encode("ascii")
    if selected["checksum"]["bytes"] != len(checksum) or selected["checksum"]["sha256"] != sha256_bytes(checksum):
        raise ValueError("Apple checksum output differs from the native archive digest")
    return {"sdkVersion": version, "outputs": selected,
            "localManifest": source_rows[_MANIFEST], "legalSources": [source_rows[p] for p in _LEGAL],
            "publicManifest": {"source": source_rows["Package.swift"], "result": "not-verified",
                               "purpose": "candidate-release-publication"}}


def _retained_apple_package_contribution(state, plan_path, *, repository_root, environ, trusted_workflow_sha=None):
    """Require current native B/P, exact source and one live verification session."""
    require_no_signing_secret(environ)
    reviewed = trusted_workflow_sha is not None
    session = _VERIFICATION_SESSION.get()
    if (session is None or type(state) is not products._VerifiedProductState
            or type(state.completed_frozen) is not CompletedFrozenReuse):
        raise ValueError("Apple contribution requires the concrete live native state")
    root, plan_path = Path(repository_root).resolve(strict=True), Path(plan_path).absolute()
    raw = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    if (load_json_bytes(raw) != state.plan or products._validate_plan(plan_path, root) != state.plan
            or not validate_remote_build_authorization(state.plan)[0]
            or not _selected_lanes(state.plan, reviewed)):

        raise ValueError("Apple contribution differs from its authorized ordinary package lane")
    native, consumer = state.completed_frozen, state.consumer
    revision = state.plan["validationCommit"]

    def controls():
        if (_VERIFICATION_SESSION.get() is not session
                or products._consumer(state.plan, environ) != consumer
                or products._git_value(root, "rev-parse", "HEAD^{commit}") != revision):
            raise ValueError("Apple contribution changed or outlived its current consumer")
        native.check_request(state.rebased_request)
        native.check_consumer(consumer)
        envelopes = {}
        records = []
        for identity in (_REVIEW_IDENTITIES if reviewed else (_BINARY, _PACKAGE)):
            record = state.prior_by_instance.get(identity)
            if identity not in state.closure or record is None or record["state"] not in {"retained", "reused"}:
                raise ValueError("Apple contribution lacks its selected native B/P")
            envelope = native.envelope(record)
            if envelope is None or envelope["receipt"]["productVersion"] != state.expected_fixed["versions"]["sdk"]:
                raise ValueError("Apple contribution lacks its exact current native original")
            _retained_dependency_plan(state, identity, envelope)
            envelopes[identity] = envelope
            records.append({**{key: record[key] for key in ("buildKey", "receiptSha256", "objectSha256")},
                            "receipt": envelope["receipt"]})
        return envelopes, canonical_json_bytes(records)

    envelopes, originals = controls()
    sources = {name: git_regular_blob_bytes(root, revision, name, max_bytes=1024 * 1024)
               for name in _SOURCE_PATHS}
    review_raw = None
    if reviewed:
        review_raw, review = _reviewed_controls(root, revision, trusted_workflow_sha, envelopes, sources)
    result = {"schemaVersion": 1, "kind": "current-apple-retained-package-controls",
              "result": "scoped-passed", "consumer": consumer["producer"], "planSha256": sha256_bytes(raw),
              "originals": load_canonical_json_bytes(originals), **_package_controls(envelopes, sources),
              "scope": ["native-package-identity", "declared-checksum-relation", "local-package-manifest",
                        "native-package-legal-source-identity"],
              "missingEvidence": ["deployment-targets", "privacy-binary-scan", "complete-release-budget-metrics"],
              "releaseAcceptance": False, "productBodiesRead": False}
    if reviewed:
        result.update(kind="current-reviewed-apple-controls", approvedReview=review,
            selectedLanes=_selected_lanes(state.plan, True),
            missingEvidence=["public-release-swift-manifest", "hosted-ordinary-lane-acceptance",
                             "full-tree-body-measurement-if-required"],
            scope=[*result["scope"], "reviewed-local-privacy", "reviewed-local-deployment",
                   "reviewed-original-artifact-size-metadata", "reviewed-local-kotlin-source-tests",
                   "qualified-original-native-rust-prerequisites"])
        if _reviewed_controls(root, revision, trusted_workflow_sha, envelopes, sources)[0] != review_raw:
            raise ValueError("Protected Apple review changed during consumption")
    if (controls()[1] != originals or read_regular_file_bytes(plan_path, reject_symlink_parents=True) != raw
            or load_json_bytes(raw) != state.plan):
        raise ValueError("Apple contribution inputs changed during consumption")
    return load_canonical_json_bytes(canonical_json_bytes(result))


_REVIEW_PATH = ".reuse/reviewed-apple-checks.json"
_REVIEW_LIMIT = 64 * 1024
_REVIEW_IDENTITIES = (_BINARY, _PACKAGE, *(
    products.PhaseInstanceId("sdk", "sdk-ios", "validation", target)
    for target in ("ios-arm64", "ios-simulator-arm64")))
_REVIEW_SOURCES = ('gradle/build-logic/src/main/kotlin/AppleReleaseCheckTasks.kt', 'gradle/build-logic/src/main/kotlin/IosAppleReleaseVerificationTasks.kt', 'gradle/build-logic/src/main/kotlin/IosPrivacyArchive.kt', 'gradle/build-logic/src/main/kotlin/IosPrivacyAuditVerification.kt', 'gradle/build-logic/src/main/kotlin/IosPrivacyEvidence.kt', 'gradle/build-logic/src/main/kotlin/IosPrivacyManifest.kt', 'gradle/build-logic/src/main/kotlin/IosPrivacyPolicy.kt', 'gradle/build-logic/src/main/kotlin/IosPrivacyReviewBinding.kt', 'gradle/build-logic/src/main/kotlin/IosPrivacyScanner.kt', 'gradle/build-logic/src/main/kotlin/ReleaseIo.kt', 'gradle/build-logic/src/main/kotlin/ReleaseToolingGradleTasks.kt', 'gradle/build-logic/src/main/kotlin/codexagent.ios-runtime.gradle.kts', 'gradle/release/ios-resource-policy.json', 'gradle/release/privacy-data-flow-review.json', 'gradle/release/privacy-required-reason-review.json')


def _selected_lanes(plan, reviewed):
    selected = {}
    allowed = {"ios-package": {"build", "metadata"}}
    if reviewed:
        allowed.update({"ios-privacy-metrics": {"test", "metadata"},
                        "ios-kotlin-tests": {"test", "metadata"},
                        "ios-native-tests": {"test", "metadata"},
                        "ios-rust-device": {"build", "metadata"},
                        "ios-rust-simulator": {"build", "metadata"}})
    for lane, actions in allowed.items():
        row = plan["lanes"].get(lane, {})
        actual = {key for key in ("build", "test", "metadata") if row.get(key) is True}
        if actual - actions:
            raise ValueError("Apple reviewed checks cannot substitute unmatched lane actions")
        if actual:
            selected[lane] = {key: row.get(key, False) for key in ("build", "test", "metadata")}
    return selected


def _reviewed_source_checks(root, revision, value, envelopes):
    """Protected review preserves local Kotlin and inherited B prerequisite attribution."""
    from products.inventory import git_file_inventory, git_inventory, git_inventory_paths
    from products.sdk_apple_native_source import _SINGLE_FILES, _SOURCE_TREES
    require_exact_keys(value, {"schemaVersion", "sourceTrees", "kotlin", "nativePrerequisites", "verifierSources"},
                       "Reviewed Apple source checks")
    if type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1:
        raise ValueError("Reviewed Apple source schema differs")
    trees = require_exact_keys(value["sourceTrees"],
        {"codex-agent-runtime-ios/src", "codex-agent-runtime-ios/native"}, "Apple source trees")
    kotlin = value["kotlin"]
    if (kotlin.get("result") != "passed" or kotlin.get("origin") != "local-retained-main-friend-source-tests"
            or kotlin.get("hostedExecution") is not False
            or canonical_json_bytes(kotlin.get("counts")) != canonical_json_bytes(
                {"tests": 27, "errors": 0, "failures": 0, "skipped": 0})):
        raise ValueError("Reviewed Kotlin source checks change their actual local scope")
    if products._OID.fullmatch(kotlin.get("source", "")) is None:
        raise ValueError("Reviewed Kotlin source revision is invalid")
    for path, oid in trees.items():
        if (products._OID.fullmatch(oid) is None
                or products._git_value(root, "rev-parse", revision + ":" + path) != oid
                or products._git_value(root, "rev-parse", kotlin["source"] + ":" + path) != oid):
            raise ValueError("Reviewed Apple source tree changed")
    test_paths = sorted(git_inventory_paths(git_inventory(root, revision, ("codex-agent-runtime-ios/src/iosTest/**",))))
    if len(test_paths) != 9 or kotlin.get("sourceFiles") != git_file_inventory(root, revision, test_paths):
        raise ValueError("Reviewed Kotlin test closure changed")
    require_sha256(kotlin["execution"]["sha256"], "Kotlin execution proof")
    require_sha256(kotlin["inputPreparation"]["sha256"], "Kotlin retained-input proof")
    if len(kotlin["junit"]) != 8:
        raise ValueError("Reviewed Kotlin XML closure changed")
    for row in kotlin["junit"]: require_sha256(row["sha256"], "Kotlin JUnit proof")
    original = envelopes[_BINARY]["receipt"]
    native = value["nativePrerequisites"]
    expected_tasks = {"ios-native-tests": ":codex-agent-runtime-ios:exportCodexAgentIosNativeTestsProof",
        "ios-rust-device": ":codex-agent-runtime-ios:exportCodexAgentIosArm64RustSlice",
        "ios-rust-simulator": ":codex-agent-runtime-ios:exportCodexAgentIosSimulatorArm64RustSlice"}
    if (native.get("result") != "inherited-passed"
            or native.get("origin") != "qualified-original-sdk-ios-binary-prerequisites"
            or native.get("originalBinaryProducer") != original["producer"]
            or native.get("originalBinaryReceiptSha256") != sha256_bytes(canonical_json_bytes(original))
            or native.get("lanes") != expected_tasks):
        raise ValueError("Reviewed native prerequisites substitute the qualified binary")
    patterns = (*_SINGLE_FILES, *(path + "/**" for path in _SOURCE_TREES))
    current = git_inventory(root, revision, patterns)
    if current != git_inventory(root, original["producer"]["commit"], patterns):
        raise ValueError("Reviewed native tests or producer source changed")
    rows = git_file_inventory(root, revision, sorted(git_inventory_paths(current)))
    by_path = {row["relativePath"]: row for row in original["inputs"]["inventory"]}
    covered = [row for row in rows if by_path.get(row["relativePath"]) == row]
    source_only = [row["relativePath"] for row in rows if row not in covered]
    if (native.get("sourceFiles") != rows or len(rows) != 21 or len(covered) != 16
            or native.get("receiptBoundFiles") != 16 or native.get("sourceOnlyTestFiles") != source_only
            or len(source_only) != 5 or any("/bridge/src/tests/" not in path for path in source_only)):
        raise ValueError("Reviewed native source closure changed")
    for key in ("nativeCompletion", "authentication"):
        require_sha256(native[key]["sha256"], "Original native prerequisite authority")
    verifier_paths = ("ci/sdk_ios_original_binary.py", "ci/sdk_apple_native.py",
        "ci/products/sdk_apple_native_replay.py", "ci/products/sdk_apple_native_source.py")
    if value["verifierSources"] != git_file_inventory(root, revision, verifier_paths):
        raise ValueError("Native prerequisite verifier source changed")


def _reviewed_controls(root, revision, publisher, envelopes, package_sources):
    # The caller/observer supplies its independently authenticated current publisher.
    # A PR file, arbitrary policy path or an environment variable is never read here.
    if type(publisher) is not str or products._OID.fullmatch(publisher) is None or publisher == revision:
        raise ValueError("Apple review requires its distinct immutable protected publisher")
    raw = git_regular_blob_bytes(root, publisher, _REVIEW_PATH, max_bytes=_REVIEW_LIMIT)
    value = require_exact_keys(load_canonical_json_bytes(raw),
        {"schemaVersion", "kind", "sdkVersion", "originals", "sources", "checks", "limits"}, "Protected Apple review")
    if (type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1
            or value["kind"] != "reviewed-original-apple-checks"
            or value["sdkVersion"] != envelopes[_PACKAGE]["receipt"]["productVersion"]):
        raise ValueError("Protected Apple review has different kind/version")
    expected = []
    for identity in _REVIEW_IDENTITIES:
        row = envelopes[identity]
        expected.append({**{k: row["receipt"][k] for k in products._IDENTITY_KEYS},
            "buildKey": row["receipt"]["buildKey"], "receiptSha256": sha256_bytes(canonical_json_bytes(row["receipt"])),
            "objectSha256": row["objectSha256"]})
    if value["originals"] != expected:
        raise ValueError("Protected Apple review is for different native originals")
    expected_sources = []
    source_bytes = {}
    for name in _REVIEW_SOURCES:
        source_bytes[name] = git_regular_blob_bytes(root, revision, name, max_bytes=1024 * 1024)
        expected_sources.append({"relativePath": name, "bytes": len(source_bytes[name]), "sha256": sha256_bytes(source_bytes[name])})
    if value["sources"] != expected_sources:
        raise ValueError("Apple verifier or policy differs from the reviewed source")
    checks = require_exact_keys(value["checks"],
        {"privacy", "deployment", "artifactSizeMetadata", "publicSwiftManifest", "sourceChecks"}, "Reviewed Apple checks")
    _reviewed_source_checks(root, revision, checks["sourceChecks"], envelopes)
    if (checks["privacy"].get("result") != "passed" or checks["privacy"].get("origin") != "local-genuine-original"
            or checks["deployment"].get("result") != "passed"
            or checks["deployment"].get("origin") != "local-genuine-original-composed"):
        raise ValueError("Protected Apple review lacks its local privacy/deployment checks")
    sizes = checks["artifactSizeMetadata"]
    if (sizes.get("result") != "passed" or sizes.get("origin") != "native-output-and-original-zip-metadata"
            or sizes.get("fullTreeBodyMeasurement") is not False):
        raise ValueError("Protected Apple size review changes its measurement scope")
    metrics = require_exact_keys(sizes["metrics"],
        {"compressedXcframeworkBytes", "deviceFrameworkBytes", "sampleAppInstallBytes"}, "Reviewed Apple sizes")
    rows = sizes["sampleAppFiles"]
    if (type(rows) is not list or not rows or any(type(r) is not dict or set(r) != {"relativePath", "bytes"}
            or type(r["relativePath"]) is not str or not r["relativePath"] or r["relativePath"].startswith("/")
            or ".." in r["relativePath"].split("/") or type(r["bytes"]) is not int or r["bytes"] < 0 for r in rows)
            or len({r["relativePath"] for r in rows}) != len(rows)
            or sum(r["bytes"] for r in rows) != metrics["sampleAppInstallBytes"]):
        raise ValueError("Reviewed Apple application inventory is inconsistent")
    limits = load_json_bytes(source_bytes["gradle/release/ios-resource-policy.json"])["artifactBytes"]
    for metric, limit in (("compressedXcframeworkBytes", "compressedXcframeworkMaximum"),
                          ("deviceFrameworkBytes", "deviceFrameworkMaximum"),
                          ("sampleAppInstallBytes", "sampleAppInstallMaximum")):
        if type(metrics[metric]) is not int or not 0 < metrics[metric] <= limits[limit]:
            raise ValueError("Reviewed Apple size exceeds the current budget")
    package = _package_controls(envelopes, package_sources)
    if metrics["compressedXcframeworkBytes"] != package["outputs"]["xcframework"]["bytes"]:
        raise ValueError("Reviewed Apple archive size differs from its native output")
    public = checks["publicSwiftManifest"]
    if (public.get("result") != "not-passed" or public.get("purpose") != "public-release-url-and-checksum"
            or public.get("source") != package["publicManifest"]["source"]):
        raise ValueError("Apple review must preserve the current public manifest limitation")
    for check, field in (("privacy", "completion"), ("privacy", "audit"), ("deployment", "completion"),
                         ("artifactSizeMetadata", "index"), ("artifactSizeMetadata", "custody"),
                         ("artifactSizeMetadata", "priorWholeNestedZip"), ("artifactSizeMetadata", "verifier"),
                         ("publicSwiftManifest", "verification")):
        require_sha256(checks[check][field]["sha256"], "Apple reviewed evidence digest")
    return raw, {"publisher": publisher, "path": _REVIEW_PATH, "sha256": sha256_bytes(raw),
                 "checks": checks, "limits": value["limits"]}


def retained_apple_package_contribution(state, plan_path, *, repository_root, environ):
    """Compatibility entry: unchanged retained package scope and honest missing checks."""
    return _retained_apple_package_contribution(state, plan_path, repository_root=repository_root, environ=environ)


def reviewed_apple_contribution(state, plan_path, *, repository_root, environ, trusted_workflow_sha):
    """Scoped Phase9 join. No full lane waiver, hosted result or release acceptance.

    Use only inside the existing live verified-state callback. Supply the publisher
    already authenticated by that caller; the transport observer must independently
    reload this fixed protected leaf using its own trusted publisher pin. Publish
    only after every outer owner exits. This function does not write or fetch.
    """
    if trusted_workflow_sha is None:
        raise ValueError("Reviewed Apple checks require the protected publisher")
    return _retained_apple_package_contribution(state, plan_path, repository_root=repository_root,
        environ=environ, trusted_workflow_sha=trusted_workflow_sha)


def validate_reviewed_apple_contribution(value, plan_path, *, repository_root, environ, trusted_workflow_sha):
    """Check detached controls AFTER the existing observer authenticates their job/upload.

    This is the fixed record validator, not a transport/signature/native authority
    API. Its caller retains the existing observation/session and publication exits.
    It grants no whole-lane exemption: public Swift/full-tree/hosted duties remain.
    """
    from products.receipt import validate_phase_receipt
    require_no_signing_secret(environ)
    session = _VERIFICATION_SESSION.get()
    if (session is None or environ.get("GITHUB_ACTIONS") != "true"
            or environ.get("GITHUB_JOB") != "merge-gate"):
        raise ValueError("Reviewed Apple controls require the live merge-gate observer")
    root, path = Path(repository_root).resolve(strict=True), Path(plan_path).absolute()
    raw = read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    plan = products._validate_plan(path, root)
    if (load_json_bytes(raw) != plan or not validate_remote_build_authorization(plan)[0]
            or not _selected_lanes(plan, True)):
        raise ValueError("Reviewed Apple controls require the authorized current plan")
    consumer = products._consumer(plan, environ)["producer"]
    value = require_exact_keys(value, {"schemaVersion", "kind", "result", "consumer", "planSha256", "originals",
        "sdkVersion", "outputs", "localManifest", "legalSources", "publicManifest", "scope", "missingEvidence",
        "releaseAcceptance", "productBodiesRead", "approvedReview", "selectedLanes"}, "Reviewed Apple contribution")
    if (type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1
            or value["kind"] != "current-reviewed-apple-controls" or value["result"] != "scoped-passed"
            or value["consumer"] != consumer or value["planSha256"] != sha256_bytes(raw)
            or value["releaseAcceptance"] is not False or value["productBodiesRead"] is not False
            or value["selectedLanes"] != _selected_lanes(plan, True)):
        raise ValueError("Reviewed Apple controls change their current consumer or scope")
    if type(value["originals"]) is not list or len(value["originals"]) != 4:
        raise ValueError("Reviewed Apple controls require exactly four original envelopes")
    envelopes = {}
    for identity, original in zip(_REVIEW_IDENTITIES, value["originals"]):
        row = require_exact_keys(original, {"buildKey", "receiptSha256", "objectSha256", "receipt"}, "Apple original")
        receipt = validate_phase_receipt(row["receipt"])
        if (products._identity(receipt) != identity or row["buildKey"] != receipt["buildKey"]
                or row["receiptSha256"] != sha256_bytes(canonical_json_bytes(receipt))):
            raise ValueError("Reviewed Apple controls substitute an original receipt")
        require_sha256(row["objectSha256"], "Apple object digest")
        envelopes[identity] = row
    revision = plan["validationCommit"]
    if products._git_value(root, "rev-parse", "HEAD^{commit}") != revision:
        raise ValueError("Apple observer is not at the current plan source")
    sources = {name: git_regular_blob_bytes(root, revision, name, max_bytes=1024 * 1024) for name in _SOURCE_PATHS}
    package = _package_controls(envelopes, sources)
    review_raw, review = _reviewed_controls(root, revision, trusted_workflow_sha, envelopes, sources)
    if (any(value[k] != v for k, v in package.items()) or value["approvedReview"] != review
            or value["scope"] != ["native-package-identity", "declared-checksum-relation", "local-package-manifest",
                "native-package-legal-source-identity", "reviewed-local-privacy", "reviewed-local-deployment",
                "reviewed-original-artifact-size-metadata", "reviewed-local-kotlin-source-tests",
                   "qualified-original-native-rust-prerequisites"]
            or value["missingEvidence"] != ["public-release-swift-manifest", "hosted-ordinary-lane-acceptance",
                                           "full-tree-body-measurement-if-required"]):
        raise ValueError("Apple contribution differs from the protected reviewed checks")
    if (_VERIFICATION_SESSION.get() is not session or read_regular_file_bytes(path, reject_symlink_parents=True) != raw
            or products._consumer(plan, environ)["producer"] != consumer
            or products._git_value(root, "rev-parse", "HEAD^{commit}") != revision
            or git_regular_blob_bytes(root, trusted_workflow_sha, _REVIEW_PATH, max_bytes=_REVIEW_LIMIT) != review_raw):
        raise ValueError("Apple observer controls changed during consumption")
    return load_canonical_json_bytes(canonical_json_bytes(value))
