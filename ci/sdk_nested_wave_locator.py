"""Locate one failed-run nested SDK collection; never admit its state."""

import os
from pathlib import Path
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from sdk_apple_upload_locator import _locate
from products.receipt import validate_producer
from products.signing_isolation import require_no_signing_secret
import product_reuse as products


from sdk_phase import SDK_FAMILY_ROUTES

_COLLECTORS = {row.wave: (row.child, row.parent) for row in SDK_FAMILY_ROUTES if row.child}


def locate_failed_nested_sdk_wave(producer, *, wave, trusted_workflow_sha,
                                  token, environ=None):
    """Return the exact original state upload ID/digest for a caller-chosen wave.

    A later consumer must recapture and authenticate the state, including the
    failed-wave evidence; this locator does not turn it into successful work.
    """
    if type(wave) is not int or wave not in _COLLECTORS:
        raise ValueError("Unknown nested SDK collection wave")
    return locate_failed_sdk_wave(producer, wave=wave, trusted_workflow_sha=trusted_workflow_sha,
                                  token=token, environ=environ)


def locate_failed_sdk_wave(producer, *, wave, trusted_workflow_sha, token, environ=None):
    """Locate an exact successful checkpoint of a failed/cancelled SDK attempt."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    if type(wave) is not int or wave not in range(1, 20):
        raise ValueError("Unknown SDK collection wave")
    producer = dict(validate_producer(producer))
    if producer["event"] != "pull_request" or type(token) is not str or not token:
        raise ValueError("Nested SDK failed-run locator requires a PR producer and token")
    workflow = ".github/workflows/product-validation.yml"
    job = f"product-validation / sdk-collect-{wave}"
    if wave in _COLLECTORS:
        workflow_name, parent = _COLLECTORS[wave]
        workflow = f".github/workflows/{workflow_name}.yml"
        job = f"product-validation / {parent} / sdk-collect-{wave}"
    policy = {"collector": {"path": workflow, "sha": trusted_workflow_sha}}
    observed = products._observe_ci_producer_jobs(
        {"collector": producer}, jobs_by_phase={"collector": job},
        trusted_workflows_by_phase=policy, token=token)[0]
    if (observed["run"].get("status") != "completed"
            or observed["run"].get("conclusion") not in {"failure", "cancelled"}):
        raise ValueError("Nested SDK collection requires a completed failed original run")
    name = (f"codex-agent-sdk-wave-{wave}-state-{producer['tree']}-"
            f"attempt-{producer['runAttempt']}")
    result = _locate(producer, phase="collector", job=job, name=name,
                     token=token, trusted_workflows_by_phase=policy)
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    return result


def locate_current_failed_nested_sdk_wave(producer, *, wave,
        trusted_workflow_sha, token, environ=None):
    """Locate this run's successful child collector after one child failed.

    The parent run may still be in progress. This is upload transport only;
    the caller must recapture its bytes and verify completed phase objects.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    if type(wave) is not int or wave not in range(11, 17):
        raise ValueError("Unknown current nested SDK collection wave")
    current = dict(validate_producer(producer))
    if (current["event"] != "pull_request" or type(token) is not str or not token
            or environment.get("GITHUB_REPOSITORY") != current["repository"]
            or environment.get("GITHUB_RUN_ID") != str(current["runId"])
            or environment.get("GITHUB_RUN_ATTEMPT") != str(current["runAttempt"])):
        raise ValueError("Current nested SDK locator requires this PR run and token")
    workflow_name, parent = _COLLECTORS[wave]
    workflow = f".github/workflows/{workflow_name}.yml"
    job = f"product-validation / {parent} / sdk-collect-{wave}"
    policy = {"collector": {"path": workflow, "sha": trusted_workflow_sha}}
    observed = products._observe_ci_producer_jobs(
        {"collector": current}, jobs_by_phase={"collector": job},
        trusted_workflows_by_phase=policy, token=token)[0]
    run = observed["run"]
    if (run.get("status") not in {"in_progress", "completed"}
            or run.get("status") == "in_progress" and run.get("conclusion") is not None
            or run.get("status") == "completed" and run.get("conclusion") not in {"failure", "cancelled"}):
        raise ValueError("Current nested SDK collector requires an active or failed run")
    name = (f"codex-agent-sdk-wave-{wave}-state-{current['tree']}-"
            f"attempt-{current['runAttempt']}")
    result = _locate(current, phase="collector", job=job, name=name,
                     token=token, trusted_workflows_by_phase=policy)
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    return result
