"""Observe the fixed protected-dispatch Android job chain.

The reviewed product and Android workflow pins define the environment-gated
jobs. Their exact-attempt success is GitHub's external evidence that those jobs
were released to run; this helper grants no artifact, Firebase, or product
content authority.
"""

from datetime import datetime, timedelta
from pathlib import Path
import re
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
import sdk_android_upload_locator as upload_locator
from products.inventory import canonical_json_bytes, require_array, require_string
from products.receipt import validate_producer


DISPATCH_JOB = "product-validation / dispatch-authorization"
_OID = re.compile(r"[0-9a-f]{40}")


def _utc(value, label):
    parsed = datetime.fromisoformat(require_string(value, label).replace("Z", "+00:00"))
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("Android protected-dispatch job timestamps must be UTC")
    return parsed


def _job(observation, name):
    selected = [job for job in observation["jobs"] if job.get("name") == name]
    if len(selected) != 1:
        raise ValueError("Android protected-dispatch job is missing or ambiguous")
    return selected[0]


def observe_android_protected_dispatch(
        producer, *, trusted_workflow_sha, trusted_android_workflow_sha, token):
    """Return external exact-attempt observation for one protected dispatch.

    Caller-selected pins are authority; neither the returned API response nor a
    transported Android artifact may select them. The pinned jobs themselves
    contain the protected-environment configuration checks.
    """
    selected = validate_producer(producer, "Android protected-dispatch producer")
    if selected["event"] != "workflow_dispatch" or selected["pullRequest"] is not None:
        raise ValueError("Android protected-dispatch observation requires workflow_dispatch")
    if (type(trusted_android_workflow_sha) is not str
            or _OID.fullmatch(trusted_android_workflow_sha) is None):
        raise ValueError("Android protected-dispatch requires a caller-pinned Android workflow SHA")
    if type(token) is not str or not token:
        raise ValueError("Android protected-dispatch observation requires a token")
    authority = canonical_json_bytes({
        "producer": selected,
        "trustedWorkflowSha": trusted_workflow_sha,
        "trustedAndroidWorkflowSha": trusted_android_workflow_sha,
    })
    observation, = products._observe_ci_producer_jobs(
        {"firebase": selected, "attach": selected},
        jobs_by_phase={
            "firebase": upload_locator.FIREBASE_JOB,
            "attach": upload_locator.ATTACH_JOB,
        },
        trusted_workflow_sha=trusted_workflow_sha,
        token=token,
        allow_protected_dispatch=True,
    )
    references = require_array(
        observation["run"].get("referenced_workflows"),
        "Android protected-dispatch workflow references",
    )
    expected = f"{upload_locator.REPOSITORY}/{upload_locator.ANDROID_WORKFLOW}@main"
    android = [value for value in references if type(value) is dict
               and isinstance(value.get("path"), str)
               and value["path"].split("@", 1)[0] == expected.split("@", 1)[0]]
    if (len(android) != 1 or android[0].get("path") != expected
            or android[0].get("sha") != trusted_android_workflow_sha):
        raise ValueError("Android protected dispatch lacks its caller-pinned reusable workflow")
    dispatch = _job(observation, DISPATCH_JOB)
    firebase = _job(observation, upload_locator.FIREBASE_JOB)
    attach = _job(observation, upload_locator.ATTACH_JOB)
    if (_utc(dispatch.get("completed_at"), "Dispatch approval completion") >
            _utc(firebase.get("started_at"), "Firebase start")
            or _utc(firebase.get("completed_at"), "Firebase completion") >
            _utc(attach.get("started_at"), "Android attach start")):
        raise ValueError("Android protected-dispatch jobs ran out of order")
    if canonical_json_bytes({
            "producer": producer,
            "trustedWorkflowSha": trusted_workflow_sha,
            "trustedAndroidWorkflowSha": trusted_android_workflow_sha,
            }) != authority:
        raise ValueError("Android protected-dispatch caller policy changed during observation")
    return observation
