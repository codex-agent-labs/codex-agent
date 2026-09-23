"""Pure native workflow routing, not state authentication or product admission.

Ready plans must come from the existing authenticated replay. Needs are workflow
job results; consumers must still recapture and authenticate returned locators.
This final gate never schedules or suppresses sibling-failure collection.
"""

from pathlib import Path
import re
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.inventory import (
    require_array, require_exact_keys, require_integer, require_object,
    require_sha256, require_string,
)
from products.receipt import compute_build_key, validate_receipt_inputs
from products.registry import NATIVE_BINDINGS, PHASE_INSTANCE_IDS, PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS
from sdk_native_prepare import validate_anchor


_IDENTITY = ("product", "component", "phase", "target")
_LOCATOR = ("artifact_id", "artifact_digest", "state_wave", "sdk_state_wave")
_STAGES = {
    "package": ("sdk-javascript", "sdk-native-plan", "sdk-native-workers", "sdk-collect-4", "4"),
    "ios-package": ("sdk-native-packages", "sdk-ios-package-plan", "sdk-ios-package", "sdk-collect-5", "5"),
    "javascript-metadata": ("sdk-ios-packages", "sdk-javascript-metadata-plan", "sdk-javascript-metadata", "sdk-collect-6", "6"),
    "validation": ("sdk-javascript-metadata-result", "sdk-native-validation-plan", "sdk-native-validation", "sdk-collect-7", "7"),
    "metadata": ("sdk-native-validation-result", "sdk-native-metadata-plan", "sdk-native-metadata", "sdk-collect-8", "8"),
    "ios-validation": ("sdk-native-result", "sdk-ios-validation-plan", "sdk-ios-validation", "sdk-collect-9", "9"),
    "ios-metadata": ("sdk-ios-validation-result", "sdk-ios-metadata-plan", "sdk-ios-metadata", "sdk-collect-10", "10"),
    "core-binary": ("sdk-ios-metadata-result", "sdk-core-binary-plan", "sdk-core-binary", "sdk-collect-11", "11"),
    "core-package": ("sdk-core-binary-result", "sdk-core-package-plan", "sdk-core-package", "sdk-collect-12", "12"),
    "core-validation": ("sdk-core-package-result", "sdk-core-validation-plan", "sdk-core-validation", "sdk-collect-13", "13"),
    "core-metadata": ("sdk-core-validation-result", "sdk-core-metadata-plan", "sdk-core-metadata", "sdk-collect-14", "14"),
    "android-binary": ("sdk-core-metadata-result", "sdk-android-binary-plan", "sdk-android-binary", "sdk-collect-15", "15"),
    "android-package": ("sdk-android-binary-result", "sdk-android-package-plan", "sdk-android-package", "sdk-collect-16", "16"),
    "android-validation": ("sdk-android-package-result", "sdk-android-validation-plan", "sdk-android-validation", "sdk-collect-17", "17"),
    "android-metadata": ("sdk-android-validation-result", "sdk-android-metadata-plan", "sdk-android-metadata", "sdk-collect-18", "18"),
}


def select_preparation_anchor(ready_plans):
    """Choose one unchanged native diagnostic anchor from verified ready plans."""
    seen, candidates = set(), []
    for plan in require_array(ready_plans, "Native continuation ready plans"):
        require_exact_keys(plan, PHASE_PLAN_KEYS, "Native continuation ready plan")
        if require_integer(plan["schemaVersion"], "Ready plan schema", 1) != 1:
            raise ValueError("Unsupported ready plan schema")
        identity = PhaseInstanceId(*(require_string(plan[name], "Ready plan " + name) for name in _IDENTITY))
        if identity not in PHASE_INSTANCE_IDS or identity in seen:
            raise ValueError("Unknown or duplicate ready plan identity")
        seen.add(identity)
        key = require_sha256(plan["buildKey"], "Ready plan build key")
        validate_receipt_inputs(plan["inputs"])
        if identity.product == "sdk" and identity.component in NATIVE_BINDINGS:
            validate_anchor(plan)
            candidates.append(plan)
        elif compute_build_key(**{name: plan[name] for name in (*_IDENTITY, "inputs")}) != key:
            raise ValueError("Ready plan identity or inputs differ from its build key")
    if not candidates:
        return dict(preparation_required=False, component="", phase="", target="", build_key="")
    priority = {"package": 0, "validation": 1, "metadata": 2}
    plan = min(candidates, key=lambda row: (priority[row["phase"]], *(row[name] for name in _IDENTITY)))
    return dict(preparation_required=True, component=plan["component"], phase=plan["phase"],
                target=plan["target"], build_key=plan["buildKey"])


def _job(needs, name):
    job = require_object(needs.get(name), "Native continuation job " + name)
    if job.get("result") not in ("success", "failure", "cancelled", "skipped"):
        raise ValueError("Native continuation job is missing or still running: " + name)
    require_object(job.get("outputs"), "Native continuation job outputs " + name)
    return job


def _locator(outputs):
    result = {name: outputs.get(name, "") for name in _LOCATOR}
    if any(type(value) is not str for value in result.values()):
        raise ValueError("Native state locator fields must be strings")
    if not any(result.values()):
        return result
    if (not re.fullmatch(r"[1-9][0-9]*", result["artifact_id"])
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", result["artifact_digest"])
            or result["state_wave"] not in ("0", "1", "2", "3", "4", "5")
            or result["sdk_state_wave"] not in ("", *(str(wave) for wave in range(1, 19)))
            or (result["sdk_state_wave"] and result["state_wave"] != "0")):
        raise ValueError("Invalid native state artifact identity or wave")
    return result


def select_native_state(needs, *, stage):
    """Return a collected locator or the exact unchanged parent after final gates.

    Preparation is independent of package misses. Its original locator tuple is
    forwarded separately by the workflow and is never reconstructed here.
    """
    if type(stage) is not str or stage not in _STAGES:
        raise ValueError("Unknown native continuation stage")
    require_object(needs, "Native continuation needs")
    parent_name, election_name, workers_name, collector_name, wave = _STAGES[stage]
    parent, election, workers, collector = (_job(needs, name) for name in
        (parent_name, election_name, workers_name, collector_name))
    if parent["result"] != "success":
        raise ValueError("Native predecessor gate failed")
    state = _locator(parent["outputs"])
    preparation = _job(needs, "sdk-native-prepare") if stage == "package" else None
    apple_signing = tuple(_job(needs, name) for name in
        ("sdk-apple-signing-prepare", "sdk-apple-validation-attestation")) if stage == "ios-validation" else ()
    if not state["artifact_id"]:
        if any(job["result"] != "skipped" for job in
               (election, workers, collector, *apple_signing, *((preparation,) if preparation is not None else ()))):
            raise ValueError("Unexpected native jobs without parent state")
        return state
    if election["result"] != "success":
        raise ValueError("Native election did not complete")
    required = election["outputs"].get("sdk_workers_required")
    if required not in ("true", "false"):
        raise ValueError("Native worker election is incomplete")
    if preparation is not None:
        prepare = election["outputs"].get("preparation_required")
        if prepare not in ("true", "false") or (required == "true" and prepare != "true"):
            raise ValueError("Native preparation election is incomplete or inconsistent")
        if preparation["result"] != ("success" if prepare == "true" else "skipped"):
            raise ValueError("Native preparation did not match its election")
    expected = "success" if required == "true" else "skipped"
    if any(job["result"] != expected for job in apple_signing):
        raise ValueError("Apple preparation or attestation failed or differed from election")
    if workers["result"] != expected or collector["result"] != expected:
        raise ValueError("Native workers or collection failed or differed from election")
    if required == "false":
        return state
    if collector["outputs"].get("wave_failed") != "false":
        raise ValueError("Native collection retained failed or incomplete siblings")
    return _locator({**collector["outputs"], "state_wave": "0", "sdk_state_wave": wave})
