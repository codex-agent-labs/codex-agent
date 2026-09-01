#!/usr/bin/env python3
"""Plan codex-agent CI work from Git-owned lane inputs."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

if __package__:
    from .legacy_lanes import LANES
    from .product_legacy import project_legacy_lanes
    from .products.inventory import (
        changed_git_paths as changed_paths,
        git_inventory as inventory,
        run_git,
    )
    from .products.registry import PHASE_INSTANCE_IDS
    from .products.selection import classify_paths
else:
    from legacy_lanes import LANES
    from product_legacy import project_legacy_lanes
    from products.inventory import (  # type: ignore[no-redef]
        changed_git_paths as changed_paths,
        git_inventory as inventory,
        run_git,
    )
    from products.registry import PHASE_INSTANCE_IDS
    from products.selection import classify_paths


CATEGORIES = ("production", "test", "metadata")

M8_OWNER_LANES = frozenset((
    "contracts",
    "node-js",
    "desktop-macos-arm64",
    "desktop-macos-x64",
    "desktop-linux-arm64",
    "desktop-linux-x64",
    "desktop-windows-x64",
    "ios-swift-tests",
))

DEPENDENCIES = {
    "android": ("consumer-android",),
    "node-js": ("contracts", "consumer-node-js"),
    "node-wasm": ("consumer-node-wasm",),
    "desktop-macos-arm64": ("consumer-desktop",),
    "desktop-macos-x64": ("consumer-desktop",),
    "desktop-linux-arm64": ("consumer-desktop",),
    "desktop-linux-x64": ("consumer-desktop",),
    "desktop-windows-x64": ("consumer-desktop",),
    "ios-rust-device": ("ios-framework-device",),
    "ios-rust-simulator": ("ios-framework-simulator",),
    "ios-framework-device": ("ios-swift-tests", "ios-package", "consumer-ios-device"),
    "ios-framework-simulator": (
        "ios-kotlin-tests",
        "ios-swift-build",
        "ios-package",
        "consumer-ios-simulator",
    ),
    "ios-swift-build": ("ios-swift-tests",),
    "ios-swift-tests": ("ios-privacy-metrics",),
    "ios-package": ("ios-privacy-metrics",),
}

SUPPORT_DEPENDENCIES = {
    **{
        lane: (("portable", "build"),)
        for lane in LANES
        if lane.startswith("desktop-")
    },
    **{
        consumer: tuple(
            (lane, action)
            for lane in LANES if lane.startswith("desktop-")
            for action in ("build", "test")
        )
        for consumer in ("consumer-desktop", "consumer-node-js", "consumer-node-wasm")
    },
    "consumer-android": (("android", "build"),),
    "consumer-ios-device": (("ios-rust-device", "build"), ("ios-rust-simulator", "build")),
    "consumer-ios-simulator": (("ios-rust-device", "build"), ("ios-rust-simulator", "build")),
    "ios-framework-device": (
        ("ios-rust-device", "build"),
    ),
    "ios-framework-simulator": (
        ("ios-rust-simulator", "build"),
    ),
    "ios-kotlin-tests": (("ios-rust-simulator", "build"),),
    "ios-swift-build": (("ios-framework-simulator", "build"),),
    "ios-swift-tests": (
        ("ios-framework-device", "build"),
        ("ios-framework-simulator", "build"),
        ("ios-swift-build", "build"),
        ("contracts", "build"),
        ("contracts", "test"),
        ("node-js", "test"),
        ("desktop-macos-arm64", "build"),
        ("desktop-macos-arm64", "test"),
        ("desktop-macos-x64", "build"),
        ("desktop-macos-x64", "test"),
        ("desktop-linux-arm64", "build"),
        ("desktop-linux-arm64", "test"),
        ("desktop-linux-x64", "build"),
        ("desktop-linux-x64", "test"),
        ("desktop-windows-x64", "build"),
        ("desktop-windows-x64", "test"),
    ),
    "ios-package": (("ios-framework-device", "build"), ("ios-framework-simulator", "build")),
    "ios-privacy-metrics": (
        ("ios-framework-device", "build"),
        ("ios-framework-simulator", "build"),
    ),
}

SUPPORT_TRIGGER_ACTIONS = {
    **{lane: ("test",) for lane in LANES if lane.startswith("desktop-")},
    "ios-framework-device": ("build",),
    "ios-framework-simulator": ("build",),
    "ios-package": ("build", "test"),
}

FULL_VALIDATION_PATHS = {
    ".github/workflows/ci.yml",
    ".github/workflows/product-validation.yml",
    ".github/workflows/android-runtime-evidence.yml",
    ".github/workflows/apple-runtime-evidence.yml",
    ".github/workflows/desktop-runtime-evidence.yml",
    "ci/impact.py",
    "ci/receipt.py",
    "ci/reuse.py",
    "ci/validation_reuse.py",
}
FULL_VALIDATION_PREFIXES = (
    "ci/",
    ".github/actions/run-ci-lane/",
    ".github/actions/setup-kmp/",
    ".github/actions/setup-sccache/",
)

PRODUCT_MATRIX_LANES = ("contracts", "portable", "node-js", "node-wasm")
CONSUMER_MATRIX_LANES = (
    "consumer-android", "consumer-desktop", "consumer-node-js", "consumer-node-wasm",
)
CONSUMER_RUNNERS = {
    lane: "macos-26" if lane == "consumer-desktop" else "ubuntu-24.04"
    for lane in CONSUMER_MATRIX_LANES
}
DESKTOP_LANES = tuple(lane for lane in LANES if lane.startswith("desktop-")) + ("consumer-desktop",)
APPLE_LANES = tuple(lane for lane in LANES if lane.startswith("ios-")) + (
    "consumer-common", "consumer-ios-device", "consumer-ios-simulator",
)
DESKTOP_RUNNERS = {
    "desktop-macos-arm64": "macos-26",
    "desktop-macos-x64": "macos-26-intel",
    "desktop-linux-x64": "ubuntu-24.04",
    "desktop-windows-x64": "windows-2025",
}
NATIVE_WRAPPER_LANES = tuple(lane for lane in LANES if lane.startswith("desktop-"))

OID = re.compile(r"[0-9a-f]{40}")
AUTHORIZED_REMOTE_BUILD_REASONS = frozenset((
    "merge-group",
    "protected-dispatch",
    "pull-request-final",
))
DENIED_REMOTE_BUILD_REASONS = frozenset((
    "dispatch-approval-required",
    "draft-pull-request",
    "merge-group-event-required",
    "merge-ready-required",
    "remote-final-event-required",
    "remote-final-required",
    "unsupported-event",
    "untrusted-pull-request",
))
REMOTE_BUILD_AUTHORIZATION_REASONS = (
    AUTHORIZED_REMOTE_BUILD_REASONS | DENIED_REMOTE_BUILD_REASONS
)
AUTHORIZED_REMOTE_REASON_BY_EVENT = {
    "merge_group": "merge-group",
    "pull_request": "pull-request-final",
    "workflow_dispatch": "protected-dispatch",
}
DENIED_REMOTE_REASONS_BY_EVENT = {
    "merge_group": frozenset(("merge-group-event-required",)),
    "pull_request": frozenset((
        "draft-pull-request",
        "merge-ready-required",
        "remote-final-event-required",
        "remote-final-required",
        "untrusted-pull-request",
    )),
    "workflow_dispatch": frozenset(("dispatch-approval-required",)),
}


def require_object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Malformed {label}")
    return value


def require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Malformed {label}")
    return value


def require_oid(value: object, label: str) -> str:
    if not isinstance(value, str) or not OID.fullmatch(value):
        raise ValueError(f"Malformed {label}")
    return value


def require_positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"Malformed {label}")
    return value


def validate_remote_build_authorization(plan: dict[str, object]) -> tuple[bool, str]:
    authorized = plan.get("remoteBuildAuthorized")
    reason = plan.get("remoteBuildAuthorizationReason")
    event = plan.get("event")
    merge_ready = plan.get("mergeReady")
    if (
        type(authorized) is not bool
        or not isinstance(reason, str)
        or not isinstance(event, str)
        or type(merge_ready) is not bool
    ):
        raise ValueError("Impact plan remote-build authorization fields have invalid types")
    if reason not in REMOTE_BUILD_AUTHORIZATION_REASONS:
        raise ValueError("Impact plan remote-build authorization reason is unsupported")
    if authorized != (reason in AUTHORIZED_REMOTE_BUILD_REASONS):
        raise ValueError("Impact plan remote-build authorization fields are contradictory")
    expected = AUTHORIZED_REMOTE_REASON_BY_EVENT.get(event)
    if authorized and (not merge_ready or reason != expected):
        raise ValueError("Impact plan remote-build authorization does not match its event")
    if not authorized:
        denied = DENIED_REMOTE_REASONS_BY_EVENT.get(event, frozenset(("unsupported-event",)))
        if reason not in denied:
            raise ValueError("Impact plan remote-build denial does not match its event")
    return authorized, reason


def evaluate_remote_build_authorization(
    *,
    event: str,
    event_payload: dict[str, object],
    repository: str,
    pull_request: int | None,
    base_commit: str,
    head_commit: str,
    validation_commit: str,
    validation_tree: str,
    github_ref: str,
    github_sha: str,
    dispatch_approved: bool,
) -> tuple[bool, str, bool]:
    if type(dispatch_approved) is not bool:
        raise ValueError("Dispatch approval must be a Boolean")
    if event != "workflow_dispatch" and dispatch_approved:
        raise ValueError("Dispatch approval is invalid for this event")
    payload = require_object(event_payload, "event payload")
    event_repository = require_object(payload.get("repository"), "event repository")
    if require_string(event_repository.get("full_name"), "event repository identity") != repository:
        raise ValueError("Event repository does not match the planned repository")
    if require_oid(github_sha, "GitHub SHA") != validation_commit:
        raise ValueError("GitHub SHA does not match the validation commit")
    require_oid(validation_tree, "validation tree")
    require_string(github_ref, "GitHub ref")

    if event == "pull_request":
        number = require_positive_int(pull_request, "pull-request number")
        if require_positive_int(payload.get("number"), "event pull-request number") != number:
            raise ValueError("Pull-request number does not match the event payload")
        request = require_object(payload.get("pull_request"), "pull request")
        if require_positive_int(
            request.get("number"), "embedded pull-request number",
        ) != number:
            raise ValueError("Embedded pull-request number does not match the event payload")
        action = require_string(payload.get("action"), "pull-request action")
        draft = request.get("draft")
        if type(draft) is not bool:
            raise ValueError("Malformed pull-request draft state")
        if github_ref != f"refs/pull/{number}/merge":
            raise ValueError("Pull-request ref does not match its number")

        base = require_object(request.get("base"), "pull-request base")
        head = require_object(request.get("head"), "pull-request head")
        base_repository = require_object(base.get("repo"), "pull-request base repository")
        head_repository = require_object(head.get("repo"), "pull-request head repository")
        if require_oid(base.get("sha"), "pull-request base SHA") != base_commit:
            raise ValueError("Pull-request base SHA does not match the planned base")
        if require_oid(head.get("sha"), "pull-request head SHA") != head_commit:
            raise ValueError("Pull-request head SHA does not match the planned head")
        base_repository_name = require_string(
            base_repository.get("full_name"), "pull-request base repository identity",
        )
        head_repository_name = require_string(
            head_repository.get("full_name"), "pull-request head repository identity",
        )
        head_is_fork = head_repository.get("fork")
        if type(head_is_fork) is not bool:
            raise ValueError("Malformed pull-request fork state")

        raw_labels = request.get("labels")
        if not isinstance(raw_labels, list):
            raise ValueError("Malformed pull-request label state")
        labels = [
            require_string(require_object(item, "pull-request label").get("name"), "label name")
            for item in raw_labels
        ]
        if len(labels) != len(set(labels)):
            raise ValueError("Duplicate pull-request label state")
        event_label: str | None = None
        if action in {"labeled", "unlabeled"}:
            event_label = require_string(
                require_object(payload.get("label"), "event label").get("name"),
                "event label name",
            )
            if (action == "labeled") != (event_label in labels):
                raise ValueError("Event label contradicts the current pull-request labels")
        elif "label" in payload:
            raise ValueError("Unexpected event label for pull-request action")

        merge_ready = not draft and "merge-ready" in labels
        if (
            base_repository_name != repository
            or head_repository_name != repository
            or head_is_fork
        ):
            return False, "untrusted-pull-request", merge_ready
        if draft:
            return False, "draft-pull-request", False
        if "merge-ready" not in labels:
            return False, "merge-ready-required", False
        if "ci:remote-final" not in labels:
            return False, "remote-final-required", True
        if action != "labeled" or event_label != "ci:remote-final":
            return False, "remote-final-event-required", True
        return True, "pull-request-final", True

    if event == "merge_group":
        number = require_positive_int(pull_request, "merge-group pull-request number")
        group = require_object(payload.get("merge_group"), "merge group")
        head_ref = require_string(group.get("head_ref"), "merge-group head ref")
        match = re.search(r"(?:^|/)pr-(\d+)-", head_ref)
        if match is None or int(match.group(1)) != number:
            raise ValueError("Merge-group ref does not identify the planned pull request")
        if require_oid(group.get("base_sha"), "merge-group base SHA") != base_commit:
            raise ValueError("Merge-group base SHA does not match the planned base")
        if require_oid(group.get("head_sha"), "merge-group head SHA") != validation_commit:
            raise ValueError("Merge-group head SHA does not match the validation commit")
        if head_commit != validation_commit or github_ref != head_ref:
            raise ValueError("Merge-group runner identity does not match the planned candidate")
        if require_string(payload.get("action"), "merge-group action") != "checks_requested":
            return False, "merge-group-event-required", True
        return True, "merge-group", True

    if event == "workflow_dispatch":
        if pull_request is not None:
            raise ValueError("Workflow dispatch must not claim a pull-request number")
        inputs = require_object(payload.get("inputs"), "workflow-dispatch inputs")
        dispatch_ref = require_string(payload.get("ref"), "workflow-dispatch ref")
        if (
            dispatch_ref != github_ref
            or not github_ref.startswith(("refs/heads/", "refs/tags/"))
        ):
            raise ValueError("Workflow-dispatch ref does not match the runner ref")
        expected_base = require_oid(inputs.get("baseCommit"), "dispatch base commit")
        expected_commit = require_oid(inputs.get("validationCommit"), "dispatch validation commit")
        expected_tree = require_oid(inputs.get("validationTree"), "dispatch validation tree")
        if (
            expected_base != base_commit
            or expected_commit != validation_commit
            or expected_commit != head_commit
            or expected_tree != validation_tree
        ):
            raise ValueError("Workflow-dispatch identity does not match the checked-out candidate")
        if not dispatch_approved:
            return False, "dispatch-approval-required", False
        return True, "protected-dispatch", True

    return False, "unsupported-event", False


def read_pathspecs(root: Path, lane: str, category: str) -> tuple[str, ...]:
    path = root / "ci" / "lanes" / f"{lane}.{category}.pathspec"
    if not path.exists():
        return ()
    return tuple(
        line
        for raw in path.read_text(encoding="utf-8").splitlines()
        if (line := raw.strip()) and not line.startswith("#")
    )


def effective_pathspecs(root: Path, lane: str, category: str) -> tuple[str, ...]:
    specs = set(read_pathspecs(root, lane, category))
    if category == "production":
        specs.update(read_pathspecs(root, "shared", category))
        specs.update(FULL_VALIDATION_PATHS)
        specs.update(f"{prefix}**" for prefix in FULL_VALIDATION_PREFIXES)
        pending = [upstream for upstream, downstreams in DEPENDENCIES.items() if lane in downstreams]
        seen: set[str] = set()
        while pending:
            upstream = pending.pop()
            if upstream in seen:
                continue
            seen.add(upstream)
            specs.update(read_pathspecs(root, upstream, category))
            pending.extend(
                candidate
                for candidate, downstreams in DEPENDENCIES.items()
                if upstream in downstreams
            )
    return tuple(sorted(specs))


def lane_action(root: Path, lane: str, category: str) -> bool:
    return bool(read_pathspecs(root, lane, category))


def require_production(root: Path, lanes: dict[str, dict[str, object]], lane: str, reason: str) -> bool:
    state = lanes[lane]
    changed = False
    for key, category in (("build", "production"), ("test", "test"), ("metadata", "metadata")):
        if lane_action(root, lane, category) and not state[key]:
            state[key] = True
            changed = True
    reasons = state["reasons"]
    if reason not in reasons:
        reasons.append(reason)
    return changed


def require_action(
    root: Path,
    lanes: dict[str, dict[str, object]],
    lane: str,
    action: str,
    reason: str,
) -> bool:
    category = {"build": "production", "test": "test", "metadata": "metadata"}[action]
    state = lanes[lane]
    changed = lane_action(root, lane, category) and not state[action]
    if changed:
        state[action] = True
    if reason not in state["reasons"]:
        state["reasons"].append(reason)
    return changed


def _legacy_lane_states(
    root: Path,
    changes: list[str] | tuple[str, ...],
    *,
    force_full: bool,
    remote_authorized: bool,
    remote_reason: str,
) -> tuple[dict[str, dict[str, object]], bool, list[str]]:
    selection = classify_paths(changes)
    unresolved = PHASE_INSTANCE_IDS if force_full else selection.instances
    projection = project_legacy_lanes(unresolved)
    lanes: dict[str, dict[str, object]] = {
        lane: {
            "build": False,
            "test": False,
            "metadata": False,
            "reuseAllowed": True,
            "reasons": [],
        }
        for lane in LANES
    }
    unknown = list(selection.unknown_paths)
    full = force_full or bool(unknown) or projection.full

    if full:
        reason = (
            "ci-full-label" if force_full else
            "unknown-path" if unknown else
            "legacy-projection-fallback"
        )
        for lane in LANES:
            require_production(root, lanes, lane, reason)
            lanes[lane]["reuseAllowed"] = selection.reuse_allowed
    else:
        for lane, action in projection.actions:
            require_action(root, lanes, lane, action, "selected-product-phase")
        propagated = True
        while propagated:
            propagated = False
            if any(
                lanes[lane][action]
                for lane in M8_OWNER_LANES
                for action in ("build", "test", "metadata")
            ):
                propagated |= require_action(
                    root,
                    lanes,
                    "ios-swift-tests",
                    "test",
                    "required-by:cross-language-m8",
                )
            for upstream, downstreams in DEPENDENCIES.items():
                if lanes[upstream]["build"] and any(
                    not reason.startswith("required-by:")
                    for reason in lanes[upstream]["reasons"]
                ):
                    for downstream in downstreams:
                        propagated |= require_production(
                            root, lanes, downstream, f"dependency:{upstream}",
                        )
            for downstream, upstreams in SUPPORT_DEPENDENCIES.items():
                if any(lanes[downstream][action] for action in SUPPORT_TRIGGER_ACTIONS.get(
                    downstream, ("build", "test", "metadata"),
                )):
                    for upstream, action in upstreams:
                        propagated |= require_action(
                            root, lanes, upstream, action, f"required-by:{downstream}",
                        )

    if not remote_authorized:
        for state in lanes.values():
            state.update(build=False, test=False, metadata=False, reuseAllowed=False)
            state["reasons"] = [remote_reason]
    return lanes, full, unknown


def _plan_repository_root(plan_path: Path | None = None) -> Path:
    if plan_path is not None:
        for candidate in plan_path.resolve().parents:
            if (candidate / ".git").exists() and (candidate / "ci/lanes").is_dir():
                return candidate
    return Path(__file__).resolve().parents[1]


def validate_legacy_lane_projection(
    plan: dict[str, object],
    repository_root: Path | None = None,
    plan_path: Path | None = None,
) -> None:
    changes = plan.get("changedPaths")
    if (
        not isinstance(changes, list)
        or any(type(path) is not str for path in changes)
        or changes != sorted(set(changes))
    ):
        raise ValueError("Impact plan changed paths are malformed")
    remote_authorized, remote_reason = validate_remote_build_authorization(plan)
    force_full = plan.get("fullRequested")
    if type(force_full) is not bool:
        raise ValueError("Impact plan full-request flag is malformed")
    root = repository_root or _plan_repository_root(plan_path)
    lanes, full, unknown = _legacy_lane_states(
        root,
        changes,
        force_full=force_full,
        remote_authorized=remote_authorized,
        remote_reason=remote_reason,
    )
    if not (
        plan.get("lanes") == lanes
        and plan.get("full") == full
        and plan.get("unknownPaths") == unknown
    ):
        raise ValueError("Impact plan is not the authoritative product-to-legacy projection")
    android_evidence = plan.get("androidEvidenceRequired")
    if type(android_evidence) is not bool:
        raise ValueError("Impact plan Android evidence flag is malformed")
    android = plan["lanes"]["android"]
    if android_evidence and not any(android[action] for action in ("build", "test", "metadata")):
        raise ValueError("Impact plan requires Android evidence without Android work")


def plan(
    root: Path,
    base: str,
    target: str,
    head: str,
    event: str,
    pull_request: int | None,
    force_full: bool,
    repository: str,
    output: Path,
    event_payload: dict[str, object],
    github_ref: str,
    github_sha: str,
    dispatch_approved: bool,
    require_android_evidence: bool = False,
) -> dict[str, object]:
    if type(force_full) is not bool or type(require_android_evidence) is not bool:
        raise ValueError("Planner flags must be Booleans")
    base_commit = str(run_git(root, "rev-parse", f"{base}^{{commit}}")).strip()
    target_commit = str(run_git(root, "rev-parse", f"{target}^{{commit}}")).strip()
    head_commit = str(run_git(root, "rev-parse", f"{head}^{{commit}}")).strip()
    validation_tree = str(run_git(root, "rev-parse", f"{target}^{{tree}}")).strip()
    remote_authorized, remote_reason, ready = evaluate_remote_build_authorization(
        event=event,
        event_payload=event_payload,
        repository=repository,
        pull_request=pull_request,
        base_commit=base_commit,
        head_commit=head_commit,
        validation_commit=target_commit,
        validation_tree=validation_tree,
        github_ref=github_ref,
        github_sha=github_sha,
        dispatch_approved=dispatch_approved,
    )
    changes, _ = changed_paths(root, base_commit, target_commit)
    lanes, full, unknown = _legacy_lane_states(
        root,
        changes,
        force_full=force_full,
        remote_authorized=remote_authorized,
        remote_reason=remote_reason,
    )
    target_inventories: dict[tuple[str, str], str] = {}

    for lane in LANES:
        for category in CATEGORIES:
            target_inventories[(lane, category)] = inventory(
                root, target_commit, effective_pathspecs(root, lane, category),
            )

    result: dict[str, object] = {
        "schemaVersion": 1,
        "event": event,
        "repository": repository,
        "pullRequest": pull_request,
        "baseCommit": base_commit,
        "headCommit": head_commit,
        "validationCommit": target_commit,
        "validationTree": validation_tree,
        "mergeReady": ready,
        "remoteBuildAuthorized": remote_authorized,
        "remoteBuildAuthorizationReason": remote_reason,
        "androidEvidenceRequired": require_android_evidence and any(
            lanes["android"][action] for action in ("build", "test", "metadata")
        ),
        "fullRequested": force_full,
        "full": full,
        "unknownPaths": unknown,
        "changedPaths": sorted(changes),
        "lanes": lanes,
    }
    validate_remote_build_authorization(result)
    validate_legacy_lane_projection(result, root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    inventory_root = output.parent / "inventories"
    for (lane, category), contents in target_inventories.items():
        path = inventory_root / lane / f"{category}-inputs.git-tree"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    return result


def write_github_outputs(path: Path, result: dict[str, object]) -> None:
    validate_remote_build_authorization(result)
    lines = [
        f"merge_ready={str(result['mergeReady']).lower()}",
        f"remote_build_authorized={str(result['remoteBuildAuthorized']).lower()}",
        f"remote_build_authorization_reason={result['remoteBuildAuthorizationReason']}",
        f"full={str(result['full']).lower()}",
        f"validation_tree={result['validationTree']}",
        f"validation_commit={result['validationCommit']}",
        f"android_evidence_required={str(result['androidEvidenceRequired']).lower()}",
    ]
    for lane, state in result["lanes"].items():
        run_lane = state["build"] or state["test"] or state["metadata"]
        output_lane = lane.replace("-", "_")
        lines.append(f"lane_{output_lane}={str(run_lane).lower()}")
        for action in ("build", "test", "metadata"):
            lines.append(f"lane_{output_lane}_{action}={str(state[action]).lower()}")
    for name, selected in (
        ("product_matrix", PRODUCT_MATRIX_LANES),
        ("consumer_matrix", CONSUMER_MATRIX_LANES),
    ):
        matrix = [
            {
                "lane": lane,
                **({"runner": CONSUMER_RUNNERS[lane]} if name == "consumer_matrix" else {}),
                **{action: bool(result["lanes"][lane][action]) for action in ("build", "test", "metadata")},
            }
            for lane in selected
            if any(result["lanes"][lane][action] for action in ("build", "test", "metadata"))
        ]
        lines.append(f"{name}={json.dumps(matrix, separators=(',', ':'))}")
    desktop_matrix = [
        {
            "lane": lane,
            "runner": runner,
            **{action: bool(result["lanes"][lane][action]) for action in ("build", "test", "metadata")},
        }
        for lane, runner in DESKTOP_RUNNERS.items()
        if any(result["lanes"][lane][action] for action in ("build", "test", "metadata"))
    ]
    lines.append(f"desktop_matrix={json.dumps(desktop_matrix, separators=(',', ':'))}")
    lines.append(f"any_desktop={str(any(any(result['lanes'][lane][action] for action in ('build', 'test', 'metadata')) for lane in DESKTOP_LANES)).lower()}")
    lines.append(f"native_wrappers={str(all(result['lanes'][lane]['build'] and result['lanes'][lane]['test'] for lane in NATIVE_WRAPPER_LANES)).lower()}")
    lines.append(f"any_apple={str(any(any(result['lanes'][lane][action] for action in ('build', 'test', 'metadata')) for lane in APPLE_LANES)).lower()}")
    with path.open("a", encoding="utf-8") as output:
        output.write("\n".join(lines) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--base", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--head")
    parser.add_argument("--event", required=True)
    parser.add_argument("--event-payload", type=Path, required=True)
    parser.add_argument("--github-ref", required=True)
    parser.add_argument("--github-sha", required=True)
    parser.add_argument("--pull-request", type=int)
    parser.add_argument("--dispatch-approved", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--require-android-evidence", action="store_true")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "codex-agent-labs/codex-agent"))
    parser.add_argument("--output", type=Path, default=Path("build/ci/impact-plan.json"))
    parser.add_argument("--github-output", type=Path)
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    root = arguments.repo.resolve()
    output = arguments.output if arguments.output.is_absolute() else root / arguments.output
    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"Duplicate event-payload key: {key}")
            value[key] = item
        return value

    event_payload = json.loads(
        arguments.event_payload.read_text(encoding="utf-8"),
        object_pairs_hook=unique_object,
    )
    if not isinstance(event_payload, dict):
        raise ValueError("GitHub event payload must be an object")
    result = plan(
        root=root,
        base=arguments.base,
        target=arguments.target,
        head=arguments.head or arguments.target,
        event=arguments.event,
        pull_request=arguments.pull_request,
        force_full=arguments.full,
        require_android_evidence=arguments.require_android_evidence,
        repository=arguments.repository,
        output=output,
        event_payload=event_payload,
        github_ref=arguments.github_ref,
        github_sha=arguments.github_sha,
        dispatch_approved=arguments.dispatch_approved,
    )
    if arguments.github_output:
        write_github_outputs(arguments.github_output, result)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
