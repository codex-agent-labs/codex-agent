"""Select final SDK replay transport; no planning or evidence authentication."""

from .sdk_native_continuation import _job, _locator
from .products.inventory import require_object


_JOBS = (
    "product-resume", "runtime-continuation", "runtime-aggregate-continuation",
    "sdk-ios-binary-plan", "sdk-ios-binary", "sdk-collect-3", "sdk-plan", "sdk-native-result",
    "sdk-ios-validation-result", "sdk-ios-metadata-result", "sdk-core-binary-wave",
    "sdk-core-package-wave", "sdk-core-validation-result", "sdk-core-metadata-result",
    "sdk-android-binary-result", "sdk-android-package-result",
    "sdk-android-validation-result", "sdk-android-metadata-result",
)


def _state(outputs, *, runtime_wave=None, sdk_wave=None):
    values = dict(outputs)
    for field, fixed in (("state_wave", runtime_wave), ("sdk_state_wave", sdk_wave)):
        if fixed is not None:
            if field in values and values[field] != fixed:
                raise ValueError("Final SDK state contradicts its original collection wave")
            values[field] = fixed
    result = _locator(values)
    if not result["artifact_id"]:
        raise ValueError("Final SDK state requires a complete original upload locator")
    return result


def select_sdk_completion_state(needs):
    """Choose one exact successful original state, never fall back past failure.

    Caller supplies these terminal workflow jobs. Their outputs select
    transport only: the caller must recapture the upload and run sdk_completion
    against its full authenticated requested SDK closure before acceptance.
    """
    require_object(needs, "SDK completion workflow needs")
    jobs = {name: _job(needs, name) for name in _JOBS}
    for name, job in jobs.items():
        if job["result"] in {"failure", "cancelled"}:
            raise ValueError("SDK completion cannot bypass failed branch: " + name)
        if job["result"] == "skipped" and any(_locator(job["outputs"]).values()):
            raise ValueError("Skipped SDK completion branch contains a state locator: " + name)
    resume = jobs["product-resume"]
    if (resume["result"] != "success" or resume["outputs"].get("wave_failed") != "false"
            or resume["outputs"].get("full_reuse") not in ("true", "false")):
        raise ValueError("SDK completion requires successful original product resume")
    initial = _state(resume["outputs"], runtime_wave="0", sdk_wave="")
    if all(jobs[name]["result"] == "skipped" for name in _JOBS[1:]):
        if resume["outputs"]["full_reuse"] != "true":
            raise ValueError("Skipped continuations require explicit original full reuse")
        return initial

    runtime, aggregate = jobs["runtime-continuation"], jobs["runtime-aggregate-continuation"]
    if runtime["result"] != "success":
        raise ValueError("SDK completion Runtime continuation did not succeed")
    parent = _state(runtime["outputs"], sdk_wave="")
    if parent["state_wave"] == "5" or (parent["state_wave"] == "0" and parent != initial):
        raise ValueError("SDK completion Runtime continuation differs from its original wave")
    handoff = runtime["outputs"].get("sdk_handoff_required")
    aggregate_state = runtime["outputs"].get("aggregate_state")
    if handoff not in ("true", "false") or aggregate_state not in ("not-selected", "ready", "completed"):
        raise ValueError("SDK completion Runtime election is incomplete")
    expected_required = "true" if aggregate_state == "ready" else "false"
    if runtime["outputs"].get("aggregate_required") != expected_required:
        raise ValueError("Runtime aggregate election contradicts its state")
    if aggregate_state == "not-selected":
        if aggregate["result"] != "skipped":
            raise ValueError("Unelected Runtime aggregate continuation executed")
    else:
        if (aggregate["result"] != "success"
                or aggregate["outputs"].get("aggregate_payload_complete") != "true"):
            raise ValueError("Selected Runtime aggregate continuation is incomplete")
        aggregate_parent = _state(aggregate["outputs"], sdk_wave="")
        if (aggregate_state == "ready" and aggregate_parent["state_wave"] != "5"
                or aggregate_state == "completed" and aggregate_parent != parent):
            raise ValueError("Runtime aggregate continuation differs from its elected parent")
        parent = aggregate_parent

    binary_plan, binary, collected = (jobs[name] for name in
        ("sdk-ios-binary-plan", "sdk-ios-binary", "sdk-collect-3"))
    required = binary_plan["outputs"].get("sdk_workers_required")
    if binary_plan["result"] != "success" or required not in ("true", "false"):
        raise ValueError("SDK completion iOS binary election is incomplete")
    expected = "success" if required == "true" else "skipped"
    if binary["result"] != expected or collected["result"] != expected:
        raise ValueError("SDK completion iOS binary work differs from its election")
    if required == "true":
        if collected["outputs"].get("wave_failed") != "false":
            raise ValueError("SDK completion iOS binary collection retained failures")
        parent = _state(collected["outputs"], runtime_wave="0", sdk_wave="3")

    planned, native, validation, final, core_binary, core_package, core_validation, core_metadata = (jobs[name] for name in
        ("sdk-plan", "sdk-native-result", "sdk-ios-validation-result", "sdk-ios-metadata-result",
         "sdk-core-binary-wave", "sdk-core-package-wave", "sdk-core-validation-result",
         "sdk-core-metadata-result"))
    if native["result"] != "success":
        raise ValueError("SDK completion final native gate did not succeed")
    if validation["result"] != "success":
        raise ValueError("SDK completion final iOS validation gate did not succeed")
    if final["result"] != "success":
        raise ValueError("SDK completion final iOS metadata gate did not succeed")
    if handoff == "true":
        if (planned["result"] != "success"
                or planned["outputs"].get("sdk_workers_required") not in ("true", "false")):
            raise ValueError("Required SDK handoff planning did not succeed")
        _state(planned["outputs"])
        native_state = _state(native["outputs"])
        validation_state = _state(validation["outputs"])
        final_state = _state(final["outputs"])
        if (native_state["sdk_state_wave"] in ("9", "10")
                or validation_state["sdk_state_wave"] == "10"
                or (validation_state != native_state and validation_state["sdk_state_wave"] != "9")):
            raise ValueError("Final iOS validation state differs from its original native parent or wave")
        if final_state != validation_state and final_state["sdk_state_wave"] != "10":
            raise ValueError("Final iOS metadata state differs from its original validation parent or wave")
        if core_binary["result"] != "success":
            raise ValueError("SDK completion Core binary gate did not succeed")
        core_state = _state(core_binary["outputs"])
        if core_state != final_state and core_state["sdk_state_wave"] != "11":
            raise ValueError("Core binary state differs from its original iOS metadata parent or wave")
        if core_package["result"] != "success":
            raise ValueError("SDK completion Core package gate did not succeed")
        package_state = _state(core_package["outputs"])
        if package_state != core_state and package_state["sdk_state_wave"] != "12":
            raise ValueError("Core package state differs from its original binary parent or wave")
        if core_validation["result"] != "success":
            raise ValueError("SDK completion Core validation gate did not succeed")
        validation_state = _state(core_validation["outputs"])
        if validation_state != package_state and validation_state["sdk_state_wave"] != "13":
            raise ValueError("Core validation state differs from its original package parent or wave")
        if core_metadata["result"] != "success":
            raise ValueError("SDK completion Core metadata gate did not succeed")
        metadata_state = _state(core_metadata["outputs"])
        if metadata_state != validation_state and metadata_state["sdk_state_wave"] != "14":
            raise ValueError("Core metadata state differs from its original validation parent or wave")
        parent = metadata_state
        for name, wave in (("sdk-android-binary-result", "15"),
                           ("sdk-android-package-result", "16"),
                           ("sdk-android-validation-result", "17"),
                           ("sdk-android-metadata-result", "18")):
            android = jobs[name]
            if android["result"] != "success":
                raise ValueError("SDK completion Android gate did not succeed: " + name)
            current = _state(android["outputs"])
            if current != parent and current["sdk_state_wave"] != wave:
                raise ValueError("Android state differs from its original predecessor or wave: " + name)
            parent = current
        return parent
    if (planned["result"] != "skipped" or any(_locator(native["outputs"]).values())
            or any(_locator(validation["outputs"]).values())
            or any(_locator(final["outputs"]).values())
            or core_binary["result"] != "skipped" or any(_locator(core_binary["outputs"]).values())
            or core_package["result"] != "skipped" or any(_locator(core_package["outputs"]).values())
            or core_validation["result"] != "skipped" or any(_locator(core_validation["outputs"]).values())
            or core_metadata["result"] != "skipped" or any(_locator(core_metadata["outputs"]).values())
            or any(jobs[name]["result"] != "skipped" or any(_locator(jobs[name]["outputs"]).values())
                   for name in ("sdk-android-binary-result", "sdk-android-package-result",
                                "sdk-android-validation-result", "sdk-android-metadata-result"))):
        raise ValueError("Unexpected SDK handoff state without its election")
    return parent
