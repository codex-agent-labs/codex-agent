"""Six fixed ordinary duties from live native originals and protected review.

Only the existing merge observer calls this. It emits no file, fetches no body,
and does not convert local source tests into hosted execution or phase receipts.
The outer observer must exit all owners before publishing its aggregate.
"""
from pathlib import Path

import product_reuse as products
from impact import validate_remote_build_authorization
from products.inventory import (canonical_json_bytes, git_regular_blob_bytes,
    load_canonical_json_bytes, require_exact_keys, require_sha256, sha256_bytes)
from products.restore import _VERIFICATION_SESSION
from products.signing_isolation import require_no_signing_secret
from reuse_qualification import CompletedFrozenReuse

_POLICY = ".reuse/reviewed-runtime-source-checks.json"
_LIMIT = 128 * 1024
_FIELDS = (*products._IDENTITY_KEYS, "buildKey", "receiptSha256", "objectSha256")
_HOSTS = ("linux-arm64", "linux-x64", "macos-arm64", "macos-x64", "windows-x64")
_SOURCES = ("codex-agent-runtime-desktop/src", "runtime/build-logic", "runtime/build.gradle.kts",
    "runtime/settings.gradle.kts", "codex-agent-runtime-desktop/build.gradle.kts", "runtime/gradle",
    "gradle/libs.versions.toml", "gradle/build-logic", "settings.gradle.kts",
    ".github/actions/run-ci-lane/build-logic-tests.py", "ci/run-lane.sh", "ci/receipt.py",
    "codex-agent-runtime-android", "tooling/protocol-generator",
    "codex-agent-core/build.gradle.kts", "build.gradle.kts", "gradle.properties",
    "gradlew", "gradle/wrapper", ".github/actions/sdk-ios-binary-worker/verification-metadata.xml")

def _phase(component, phase, target):
    return products.PhaseInstanceId("runtime", component, phase, target)

_CONTRACT = tuple(products.PhaseInstanceId("contract", "contract", p, "common")
                  for p in ("binary", "package", "validation", "metadata"))
_LANES = {
    "android": (*_CONTRACT, *(products.PhaseInstanceId("sdk", "sdk-android", p, "android")
                             for p in ("binary", "package", "validation", "metadata"))),
    "contracts": _CONTRACT,
    "portable": tuple(_phase(c, p, c) for c in ("jvm", "node-js", "node-wasm")
                      for p in ("binary", "package", "metadata")),
    "node-wasm": (*(_phase("node-wasm", p, "node-wasm") for p in ("binary", "package", "metadata")),
                  *(_phase("node-wasm", "validation", host) for host in _HOSTS)),
    **{"desktop-" + host: (*(_phase(host, p, host) for p in ("binary", "package", "validation", "metadata")),
                          *(_phase(c, "validation", host) for c in ("jvm", "node-js", "node-wasm")))
       for host in ("macos-arm64", "linux-arm64")},
}
_CHECKS = {"android": ("androidHost", "androidLint"), "contracts": ("contractGenerator",),
           "portable": ("jvm", "portableFixtures"), "node-wasm": ("wasm",),
           "desktop-macos-arm64": ("nativeMacArm",), "desktop-linux-arm64": ()}
_EXPECTED = {"androidHost": ("local-test-only-compile-and-run", 21),
             "androidLint": ("local-retained-input-lint", None),
             "contractGenerator": ("local-tool-test-compile-and-run", 3),
             "jvm": ("local-retained-executable", 33),
             "wasm": ("local-test-only-compile-and-run", 21),
             "nativeMacArm": ("local-retained-executable", 244),
             "portableFixtures": ("historical-hosted-full-suite-subset", None)}

class _ReviewedSourceChanged(ValueError):
    pass


def select_reviewed_runtime_routing(plan, *, root, trusted_workflow_sha, enabled, tooling_miss=True):
    """Planner hint only. Merge independently verifies the live native envelopes."""
    if type(enabled) is not bool:
        raise ValueError("Reviewed Runtime routing must be an explicit boolean")
    if not enabled:
        return {}
    if not any(plan["lanes"].get(lane, {}).get(action, False)
               for lane in _LANES for action in ("build", "test", "metadata")):
        return {}
    if type(tooling_miss) is not bool:
        raise ValueError("Reviewed Contract tooling miss must be an explicit boolean")
    selected = selected_reviewed_runtime_lanes(plan, True)
    if tooling_miss:
        selected.pop("contracts", None)
    if not selected:
        return {}
    try:
        _policy(Path(root), plan["validationCommit"], trusted_workflow_sha)
    except _ReviewedSourceChanged:
        return {}
    return selected


def selected_reviewed_runtime_lanes(plan, enabled):
    if type(enabled) is not bool:
        raise ValueError("Reviewed Runtime routing must be an explicit boolean")
    if not enabled:
        return {}
    selected = {}
    for lane in _LANES:
        row = plan["lanes"].get(lane, {})
        actions = {key: row.get(key, False) for key in ("build", "test", "metadata")}
        if any(type(flag) is not bool for flag in actions.values()):
            raise ValueError("Reviewed Runtime lane selection must be boolean")
        if lane not in {"node-wasm", "android", "contracts"} and actions["metadata"]:
            raise ValueError("Reviewed Runtime lane has an unmatched metadata duty")
        if any(actions.values()):
            selected[lane] = actions
    if not selected:
        raise ValueError("Reviewed Runtime routing requires a selected fixed lane")
    return selected


def _policy(root, revision, publisher):
    if (type(publisher) is not str or products._OID.fullmatch(publisher) is None
            or publisher == revision):
        raise ValueError("Reviewed Runtime requires its independently trusted protected publisher")
    raw = git_regular_blob_bytes(root, publisher, _POLICY, max_bytes=_LIMIT)
    value = require_exact_keys(load_canonical_json_bytes(raw),
        {"schemaVersion", "kind", "runtimeVersion", "originals", "sourceObjects", "checks", "limits"},
        "Protected Runtime review")
    if (type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1
            or value["kind"] != "reviewed-runtime-source-checks"):
        raise ValueError("Protected Runtime review has an unsupported schema")
    entries = {}
    for line in products._git_value(root, "ls-tree", revision, "--", *_SOURCES).splitlines():
        metadata, path = line.split("\t", 1)
        mode, kind, oid = metadata.split()
        entries[path] = {"path": path, "mode": mode, "kind": kind, "gitObject": oid}
    expected = [entries.get(path) for path in _SOURCES]
    if value["sourceObjects"] != expected:
        raise _ReviewedSourceChanged("Reviewed Runtime source or verification scope changed")
    checks = require_exact_keys(value["checks"], set(_EXPECTED), "Reviewed Runtime checks")
    for name, (origin, count) in _EXPECTED.items():
        check = require_exact_keys(checks[name],
            {"origin", "source", "host", "result", "tests", "reportSha256", "detail"}, "Reviewed Runtime check")
        if (check["origin"] != origin or check["result"] != "passed" or check["tests"] != count
                or type(check["tests"]) is not (type(None) if count is None else int)
                or type(check["source"]) is not str or products._OID.fullmatch(check["source"]) is None
                or check["host"] != ("historical-ci" if name == "portableFixtures" else "macos-arm64")):
            raise ValueError("Protected Runtime check changes its original execution scope")
        require_sha256(check["reportSha256"], "Reviewed Runtime report")
        if type(check["detail"]) is not dict:
            raise ValueError("Reviewed Runtime attribution must be explicit")
        zeros = (("failures", "skipped") if name in {"androidHost", "contractGenerator"}
                 else ("errors",) if name == "androidLint" else ())
        if any(type(check["detail"].get(key)) is not int or check["detail"][key] != 0 for key in zeros):
            raise ValueError("Reviewed source duty includes failed or skipped work")
    if value["limits"] != ["local-results-are-not-current-hosted-execution",
                           "native-original-producers-and-receipts-unchanged",
                           "no-phase10-or-phase11-acceptance"]:
        raise ValueError("Reviewed Runtime limits must remain explicit")
    return raw, value


def reviewed_runtime_contribution(native, *, plan, plan_sha256, root, consumer,
                                  environ, trusted_workflow_sha):
    """Validate directly in the existing live merge scope; no second capture/auth.

    trusted_workflow_sha is the publisher independently authenticated by the outer
    observer. A source policy, arbitrary path, environment override or serialized
    verdict is never accepted. Publish the returned record only after owner exits.
    """
    require_no_signing_secret(environ)
    session = _VERIFICATION_SESSION.get()
    root = Path(root).resolve(strict=True)
    revision = plan["validationCommit"]
    if (session is None or type(native) is not CompletedFrozenReuse
            or native._revision != revision or native._eligible is None or native._checkpoint is not None
            or environ.get("GITHUB_ACTIONS") != "true" or environ.get("GITHUB_JOB") != "merge-gate"
            or not validate_remote_build_authorization(plan)[0] or plan["mergeReady"] is not True):
        raise ValueError("Reviewed Runtime requires the live current ordinary merge capability")
    require_sha256(plan_sha256, "Current reviewed plan")
    controls_raw = canonical_json_bytes({"plan": plan, "consumer": consumer})
    selected = selected_reviewed_runtime_lanes(plan, True)
    tooling_miss = environ.get("TOOLING_MISS")
    if "contracts" in selected:
        if tooling_miss not in {"true", "false"}:
            raise ValueError("Reviewed Contract requires the actual current tooling-miss result")
        if tooling_miss == "true":
            selected.pop("contracts")
    if not selected:
        raise ValueError("Reviewed contribution cannot replace a required tooling receipt")
    identities = sorted({identity for lane in selected for identity in _LANES[lane]})

    def observe():
        if (_VERIFICATION_SESSION.get() is not session or native._revision != revision
                or native._eligible is None or native._checkpoint is not None
                or canonical_json_bytes({"plan": plan, "consumer": consumer}) != controls_raw
                or environ.get("TOOLING_MISS") != tooling_miss
                or products._consumer(plan, environ) != consumer
                or products._git_value(root, "rev-parse", "HEAD^{commit}") != revision
                or products._git_value(root, "rev-parse", "HEAD^{tree}") != plan["validationTree"]):
            raise ValueError("Reviewed Runtime source or consumer changed or outlived its owner")
        native.check_consumer(consumer)
        _, records = native._values()
        originals = []
        for identity in identities:
            record = records.get(identity)
            envelope = None if record is None else native.envelope(record)
            if envelope is None:
                raise ValueError("Reviewed Runtime lacks an exact current-eligible original")
            receipt = envelope["receipt"]
            if (products._identity(receipt) != identity
                    or receipt["buildKey"] != record["buildKey"]
                    or sha256_bytes(envelope["receiptBytes"]) != record["receiptSha256"]):
                raise ValueError("Reviewed Runtime original receipt differs")
            originals.append({**{key: record[key] for key in _FIELDS},
                              "originalProducer": receipt["producer"]})
        raw, policy = _policy(root, revision, trusted_workflow_sha)
        expected = [{key: row[key] for key in _FIELDS} for row in originals]
        all_identities = sorted({identity for values in _LANES.values() for identity in values})
        if (type(policy["originals"]) is not list or len(policy["originals"]) != len(all_identities)
                or [products._identity(row) for row in policy["originals"]] != all_identities):
            raise ValueError("Protected Runtime review must name exactly its fixed original union")
        for row in policy["originals"]:
            require_exact_keys(row, set(_FIELDS), "Protected Runtime original")
        if [row for row in policy["originals"] if products._identity(row) in identities] != expected:
            raise ValueError("Protected Runtime review substitutes a native original")
        versions = products._versions(root, revision)
        # The Runtime product release version (gradle/release/versions/runtime.txt).
        if policy["runtimeVersion"] != versions["runtime-release"]:
            raise ValueError("Reviewed Runtime version differs from current source")
        return raw, policy, originals

    raw, policy, originals = observe()
    duties = {lane: {"actions": actions, "checks": {key: policy["checks"][key] for key in _CHECKS[lane]},
                    "originals": [row for row in originals if products._identity(row) in _LANES[lane]]}
              for lane, actions in selected.items()}
    result = {"schemaVersion": 1, "kind": "current-reviewed-runtime-duties", "result": "passed",
              "consumer": consumer["producer"], "planSha256": plan_sha256, "lanes": duties,
              "protectedReview": {"publisher": trusted_workflow_sha, "path": _POLICY, "sha256": sha256_bytes(raw)},
              "sourceObjects": policy["sourceObjects"], "limits": policy["limits"],
              "currentHostedTestExecution": False, "productBodiesRead": False}
    if observe() != (raw, policy, originals):
        raise ValueError("Reviewed Runtime controls changed during consumption")
    native.check_consumer(consumer)
    if (_VERIFICATION_SESSION.get() is not session
            or environ.get("TOOLING_MISS") != tooling_miss
            or canonical_json_bytes({"plan": plan, "consumer": consumer}) != controls_raw):
        raise ValueError("Reviewed Runtime owner or caller controls exited during consumption")
    return load_canonical_json_bytes(canonical_json_bytes(result))
