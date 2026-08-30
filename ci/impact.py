#!/usr/bin/env python3
"""Plan codex-agent CI work from Git-owned lane inputs."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path


LANES = (
    "contracts",
    "portable",
    "android",
    "node-js",
    "node-wasm",
    "desktop-macos-arm64",
    "desktop-macos-x64",
    "desktop-linux-arm64",
    "desktop-linux-x64",
    "desktop-windows-x64",
    "ios-native-tests",
    "ios-rust-device",
    "ios-rust-simulator",
    "ios-framework-device",
    "ios-framework-simulator",
    "ios-kotlin-tests",
    "ios-swift-build",
    "ios-swift-tests",
    "ios-package",
    "ios-privacy-metrics",
    "consumer-common",
    "consumer-android",
    "consumer-desktop",
    "consumer-ios-device",
    "consumer-ios-simulator",
    "consumer-node-js",
    "consumer-node-wasm",
)

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

HARMLESS_PATHS = ("README.md", "docs/**", ".gitignore", ".editorconfig")
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
        if require_oid(request.get("merge_commit_sha"), "pull-request merge commit") != validation_commit:
            raise ValueError("Pull-request merge commit does not match the validation commit")

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
        if github_ref not in {f"refs/heads/{dispatch_ref}", f"refs/tags/{dispatch_ref}"}:
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


def run_git(root: Path, *arguments: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout if binary else result.stdout.decode("utf-8")


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


@lru_cache(maxsize=8)
def tree_entries(root: Path, revision: str) -> tuple[tuple[str, str], ...]:
    raw = run_git(root, "ls-tree", "-r", "-z", revision, binary=True)
    entries: list[tuple[str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, path = record.split(b"\t", 1)
        mode, kind, object_id = metadata.decode("ascii").split(" ")
        decoded_path = path.decode("utf-8")
        entries.append((decoded_path, f"{mode}\t{kind}\t{object_id}\t{decoded_path}"))
    return tuple(entries)


def inventory(root: Path, revision: str, pathspecs: tuple[str, ...]) -> str:
    if not pathspecs:
        return ""
    entries = (
        record
        for path, record in tree_entries(root, revision)
        if any(fnmatch.fnmatchcase(path, pathspec) for pathspec in pathspecs)
    )
    return "".join(f"{entry}\n" for entry in sorted(entries))


def inventory_paths(contents: str) -> set[str]:
    return {line.split("\t", 3)[3] for line in contents.splitlines() if line}


@lru_cache(maxsize=8)
def historical_pathspecs(root: Path, revision: str) -> tuple[str, ...]:
    raw = str(run_git(root, "grep", "-h", "-e", ".", revision, "--", "ci/lanes/*.pathspec"))
    return tuple(
        line
        for raw_line in raw.splitlines()
        if (line := raw_line.strip()) and not line.startswith("#")
    )


def changed_paths(root: Path, base: str, target: str) -> tuple[set[str], set[str]]:
    raw = run_git(root, "diff", "--name-status", "-z", base, target, binary=True)
    tokens = raw.split(b"\0")
    result: set[str] = set()
    removals: set[str] = set()
    index = 0
    while index < len(tokens) and tokens[index]:
        status = tokens[index].decode("ascii")
        index += 1
        count = 2 if status.startswith(("R", "C")) else 1
        paths: list[str] = []
        for _ in range(count):
            if index >= len(tokens) or not tokens[index]:
                raise ValueError(f"Malformed git diff entry for {status}")
            paths.append(tokens[index].decode("utf-8"))
            index += 1
        if status.startswith("R"):
            result.update(paths)
            removals.add(paths[0])
        else:
            result.add(paths[-1])
            if status.startswith("D"):
                removals.add(paths[-1])
    return result, removals


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
    changes, removals = changed_paths(root, base_commit, target_commit)
    lanes: dict[str, dict[str, object]] = {}
    covered: set[str] = set()
    target_inventories: dict[tuple[str, str], str] = {}

    for lane in LANES:
        state = {
            "build": False,
            "test": False,
            "metadata": False,
            "reuseAllowed": True,
            "reasons": [],
        }
        lanes[lane] = state
        for category, action in (("production", "build"), ("test", "test"), ("metadata", "metadata")):
            specs = effective_pathspecs(root, lane, category)
            base_inventory = inventory(root, base_commit, specs)
            target_inventory = inventory(root, target_commit, specs)
            target_inventories[(lane, category)] = target_inventory
            covered.update(inventory_paths(base_inventory))
            covered.update(inventory_paths(target_inventory))
            if base_inventory != target_inventory:
                state[action] = True
                state["reasons"].append(f"{category}-input-changed")
        if state["build"]:
            if lane_action(root, lane, "test"):
                state["test"] = True
            if lane_action(root, lane, "metadata"):
                state["metadata"] = True

    harmless_base = inventory(root, base_commit, HARMLESS_PATHS)
    harmless_target = inventory(root, target_commit, HARMLESS_PATHS)
    covered.update(inventory_paths(harmless_base))
    covered.update(inventory_paths(harmless_target))
    prior_specs = historical_pathspecs(root, base_commit)
    covered.update(
        path
        for path in removals
        if any(fnmatch.fnmatchcase(path, spec) for spec in prior_specs)
    )
    unknown = sorted(changes - covered)
    core_change = any(
        path in FULL_VALIDATION_PATHS or path.startswith(FULL_VALIDATION_PREFIXES)
        for path in changes
    )
    full = force_full or bool(unknown) or core_change

    if full:
        reason = "ci-full-label" if force_full else "planner-core-changed" if core_change else "unknown-path"
        for lane in LANES:
            require_production(root, lanes, lane, reason)
            lanes[lane]["reuseAllowed"] = not bool(unknown)
    else:
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
                        propagated |= require_production(root, lanes, downstream, f"dependency:{upstream}")
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
        "full": full,
        "unknownPaths": unknown,
        "changedPaths": sorted(changes),
        "lanes": lanes,
    }
    validate_remote_build_authorization(result)
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
