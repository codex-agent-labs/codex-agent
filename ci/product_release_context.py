"""Shared protected caller preflight; context checks are not self-authentication.

Only independently pinned executable code may call this gate. Environment
approval remains workflow-owned; transported inputs cannot select trust roots.
"""

from collections.abc import Mapping
from pathlib import Path
import re
from typing import Any

from impact import evaluate_remote_build_authorization, require_object, require_oid
from product_reuse import _git_value
from products.receipt import validate_producer


def verify_product_release_context(
    repository_root: Path, *, trusted_source_sha: str, trusted_workflow_sha: str,
    transport_producer: Mapping[str, Any], event_payload: dict[str, Any],
    environment: Mapping[str, str],
) -> tuple[Path, dict[str, Any], str, dict[str, str], str]:
    require_oid(trusted_source_sha, "trusted source commit pin")
    require_oid(trusted_workflow_sha, "trusted workflow SHA pin")
    repository_root = Path(repository_root).resolve(strict=True)
    if _git_value(repository_root, "rev-parse", "HEAD") != trusted_source_sha:
        raise ValueError("Trusted source commit does not match its reviewed pin")
    if _git_value(repository_root, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Trusted source checkout must have clean tracked files")
    source_tree = _git_value(repository_root, "rev-parse", "HEAD^{tree}")
    producer = validate_producer(dict(transport_producer))
    if producer["repository"] != "codex-agent-labs/codex-agent" or \
            producer["workflowPath"] != ".github/workflows/ci.yml":
        raise ValueError("Product caller producer repository/workflow is not supported")
    event = producer["event"]
    if event not in {"pull_request", "merge_group"}:
        raise ValueError("Product original CI signing supports PR/merge_group events only")
    expected_environment = {
        "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": producer["repository"],
        "GITHUB_EVENT_NAME": event, "GITHUB_SHA": producer["commit"],
        "GITHUB_RUN_ID": str(producer["runId"]),
        "GITHUB_RUN_ATTEMPT": str(producer["runAttempt"]),
    }
    for name, expected in expected_environment.items():
        if environment.get(name) != expected:
            raise ValueError(f"Product caller Actions context mismatch: {name}")
    payload = require_object(event_payload, "Product caller event")
    if event == "pull_request":
        request = require_object(payload.get("pull_request"), "Product caller pull request")
        base = require_object(request.get("base"), "Product caller base").get("sha")
        head = require_object(request.get("head"), "Product caller head").get("sha")
        number = producer["pullRequest"]
    else:
        group = require_object(payload.get("merge_group"), "Product caller merge group")
        base, head = group.get("base_sha"), group.get("head_sha")
        ref = group.get("head_ref")
        match = re.search(r"(?:^|/)pr-(\d+)-", ref) if type(ref) is str else None
        number = int(match.group(1)) if match else None
    authorized, reason, _ = evaluate_remote_build_authorization(
        event=event, event_payload=payload, repository=producer["repository"],
        pull_request=number, base_commit=base, head_commit=head,
        validation_commit=producer["commit"], validation_tree=producer["tree"],
        github_ref=environment.get("GITHUB_REF"), github_sha=environment.get("GITHUB_SHA"),
        dispatch_approved=False,
    )
    if not authorized:
        raise ValueError(f"Product caller event is not authorized: {reason}")
    return repository_root, producer, source_tree, expected_environment, reason
