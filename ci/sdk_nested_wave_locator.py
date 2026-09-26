"""Locate one failed-run nested SDK collection; never admit its state."""

import os

from .sdk_apple_upload_locator import _locate
from .products.receipt import validate_producer
from .products.signing_isolation import require_no_signing_secret
from . import product_reuse as products


_COLLECTORS = {
    11: ("sdk-core-binary-validation", "sdk-core-binary-wave"),
    12: ("sdk-core-package-validation", "sdk-core-package-wave"),
    13: ("sdk-core-validation", "sdk-core-validation-wave"),
    14: ("sdk-core-metadata-validation", "sdk-core-metadata-wave"),
    15: ("sdk-android-binary-validation", "sdk-android-binary-result"),
    16: ("sdk-android-package-validation", "sdk-android-package-result"),
    17: ("sdk-android-validation", "sdk-android-validation-result"),
    18: ("sdk-android-metadata-validation", "sdk-android-metadata-result"),
}


def locate_failed_nested_sdk_wave(producer, *, wave, trusted_workflow_sha,
                                  token, environ=None):
    """Return the exact original state upload ID/digest for a caller-chosen wave.

    A later consumer must recapture and authenticate the state, including the
    failed-wave evidence; this locator does not turn it into successful work.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    if type(wave) is not int or wave not in _COLLECTORS:
        raise ValueError("Unknown nested SDK collection wave")
    producer = dict(validate_producer(producer))
    if producer["event"] != "pull_request" or type(token) is not str or not token:
        raise ValueError("Nested SDK failed-run locator requires a PR producer and token")
    workflow_name, parent = _COLLECTORS[wave]
    workflow = f".github/workflows/{workflow_name}.yml"
    job = f"product-validation / {parent} / sdk-collect-{wave}"
    policy = {"collector": {"path": workflow, "sha": trusted_workflow_sha}}
    observed = products._observe_ci_producer_jobs(
        {"collector": producer}, jobs_by_phase={"collector": job},
        trusted_workflows_by_phase=policy, token=token)[0]
    if (observed["run"].get("status") != "completed"
            or observed["run"].get("conclusion") != "failure"):
        raise ValueError("Nested SDK collection requires a completed failed original run")
    name = (f"codex-agent-sdk-wave-{wave}-state-{producer['tree']}-"
            f"attempt-{producer['runAttempt']}")
    result = _locate(producer, phase="collector", job=job, name=name,
                     token=token, trusted_workflows_by_phase=policy)
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    return result
