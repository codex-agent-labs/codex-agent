"""Select an uploaded failed SDK wave for development-only partial caching.

Only top-level collectors expose their original upload locator after a failed
wave. Nested waves 11–18 require separate official-upload observation.
"""

from .sdk_native_continuation import _job, _locator
from .products.inventory import require_object


_WAVES = (3, 1, 2, 4, 5, 6, 7, 8, 9, 10)


def select_failed_sdk_wave_state(needs):
    """Return one successful collector's failed-wave upload, never accept it."""
    require_object(needs, "Partial SDK workflow needs")
    jobs = tuple(_job(needs, f"sdk-collect-{wave}") for wave in _WAVES)
    candidates = [index for index, job in enumerate(jobs)
                  if job["result"] == "success" and job["outputs"].get("wave_failed") == "true"]
    if len(candidates) != 1:
        raise ValueError("Partial SDK state requires one failed top-level collection")
    chosen = candidates[0]
    for index, job in enumerate(jobs):
        result = job["result"]
        if index < chosen and (result not in {"success", "skipped"}
                or result == "success" and job["outputs"].get("wave_failed") != "false"):
            raise ValueError("Partial SDK state has a failed or incomplete predecessor")
        if index > chosen and result != "skipped":
            raise ValueError("Partial SDK state has a successor after failed collection")
        if result == "skipped" and job["outputs"]:
            raise ValueError("Skipped SDK collection claims output")
        if result == "success" and index < chosen:
            previous_wave = _WAVES[index]
            for field, expected in (("state_wave", "0"), ("sdk_state_wave", str(previous_wave))):
                if field in job["outputs"] and job["outputs"][field] != expected:
                    raise ValueError("SDK predecessor contradicts its original wave")
            previous = _locator({**job["outputs"], "state_wave": "0",
                                 "sdk_state_wave": str(previous_wave)})
            if not previous["artifact_id"]:
                raise ValueError("Successful SDK predecessor lacks its upload locator")
    wave = _WAVES[chosen]
    outputs = jobs[chosen]["outputs"]
    for field, expected in (("state_wave", "0"), ("sdk_state_wave", str(wave))):
        if field in outputs and outputs[field] != expected:
            raise ValueError("Failed SDK collection contradicts its original wave")
    selected = _locator({**outputs, "state_wave": "0", "sdk_state_wave": str(wave)})
    if not selected["artifact_id"]:
        raise ValueError("Failed SDK collection lacks its original upload locator")
    return selected
