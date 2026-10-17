"""Select one failed nested SDK child for same-run development caching only."""

from .products.inventory import require_object
from .sdk_native_continuation import _job, _locator


_CHILDREN = (
    "sdk-core-binary-wave", "sdk-core-package-wave", "sdk-core-validation-wave",
    "sdk-core-metadata-wave", "sdk-android-binary-result",
    "sdk-android-package-result",
)


def select_failed_nested_sdk_wave(needs):
    """Select the sole failed child after successful predecessors, never its bytes."""
    require_object(needs, "Nested SDK partial workflow needs")
    children = [_job(needs, name) for name in _CHILDREN]
    failed = [index for index, child in enumerate(children) if child["result"] == "failure"]
    if len(failed) != 1:
        raise ValueError("Nested SDK partial state requires exactly one failed child")
    chosen = failed[0]
    previous = None
    for index, child in enumerate(children):
        result, outputs = child["result"], child["outputs"]
        if index < chosen:
            state = _locator(outputs)
            wave = str(index + 11)
            if (result != "success" or not state["artifact_id"]
                    or state["sdk_state_wave"] and int(state["sdk_state_wave"]) > int(wave)
                    or previous is not None and state != previous
                    and (state["state_wave"], state["sdk_state_wave"]) != ("0", wave)):
                raise ValueError("Nested SDK partial state lacks a successful predecessor")
            previous = state
        elif index == chosen:
            if any(_locator(outputs).values()):
                raise ValueError("Failed nested SDK child cannot claim a completed state locator")
        elif result != "skipped" or outputs:
            raise ValueError("Nested SDK partial state has a successor after failure")
    return {"wave": chosen + 11}
