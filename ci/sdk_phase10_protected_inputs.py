"""Stage independently approved SDK Phase-10 replay inputs without observation.

The control digest, source revision, authority digest and key pins must come
from protected approval, not from files this command observes or produces.
The signed-index approval is intentionally absent: it belongs to a later run.
"""

import argparse
from collections.abc import Mapping
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci import product_reuse as products
from ci.sdk_campaign_pinned_election import held_pinned_sdk_campaign_authority
from ci.sdk_campaign_release_issuer import _release_key
from ci.sdk_phase10_original_plan import require_original_lane_policy
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_integer, require_sha256, sha256_bytes, snapshot_regular_tree,
)
from products.receipt import validate_producer
from products.signing_isolation import require_no_signing_secret


_FAMILIES = ("core-android", "native", "apple-js")
_REPLAY_CONTROLS = ("sdk_validation_tooling", "sdk_apple_validation_policy",
    "sdk_facade_metadata_policy", "sdk_android_metadata_policy", "custody_catalogs")
_CONTROL_KEYS = {"schemaVersion", "product", "trustedSourceCommit",
    "originalProducer", "originalProducerSha256", "planArtifactId",
    "planArtifactSha256", "planSha256", "authorityProducer",
    "authorityProducerSha256", "authorityArtifactId", "authorityArtifactSha256",
    "authorityWorkflowSha", "trustedWorkflowSha", "stateArtifactId",
    "stateArtifactSha256", "stateWave", "sdkStateWave", "authoritySha256",
    "keyringSha256", "keysInventorySha256", "replayControlSha256"}
_OID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def _source_file(path, label, limit):
    path = Path(path)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError(f"{label} must be a canonical absolute file")
    return read_regular_file_bytes(path, max_bytes=limit,
        reject_symlink_parents=True)


def _checkout_identity(path, label):
    root = Path(path)
    if not root.is_absolute() or root.resolve(strict=True) != root or not root.is_dir():
        raise ValueError(f"{label} must be a canonical absolute checkout")
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel",
        "HEAD^{commit}", "HEAD^{tree}"], capture_output=True, text=True,
        timeout=30)
    lines = result.stdout.splitlines()
    if (result.returncode or len(lines) != 3
            or Path(lines[0]).resolve(strict=True) != root
            or any(_OID.fullmatch(value) is None for value in lines[1:])):
        raise ValueError(f"{label} is not an exact Git checkout root")
    return lines[1], lines[2]


def _control(raw):
    document = require_exact_keys(load_canonical_json_bytes(raw), _CONTROL_KEYS,
        "SDK Phase-10 protected control")
    if (type(document["schemaVersion"]) is not int or document["schemaVersion"] != 1
            or document["product"] != "sdk"):
        raise ValueError("SDK Phase-10 control has wrong schema or product")
    controls = require_exact_keys(document["replayControlSha256"],
        _REPLAY_CONTROLS, "SDK Phase-10 replay control pins")
    for name, digest in controls.items():
        if digest is not None:
            require_sha256(digest, f"SDK Phase-10 {name} digest")
    for field in ("trustedSourceCommit",):
        if type(document[field]) is not str or _OID.fullmatch(document[field]) is None:
            raise ValueError(f"SDK Phase-10 {field} must be a full Git object ID")
    for field in ("authorityWorkflowSha", "trustedWorkflowSha"):
        if (type(document[field]) is not str
                or re.fullmatch(r"[0-9a-f]{40}", document[field]) is None):
            raise ValueError(f"SDK Phase-10 {field} must be a 40-character workflow commit")
    for field in ("originalProducerSha256", "planArtifactSha256", "planSha256",
            "authorityProducerSha256", "authorityArtifactSha256", "stateArtifactSha256",
            "authoritySha256", "keyringSha256", "keysInventorySha256"):
        require_sha256(document[field], f"SDK Phase-10 {field}")
    for field in ("planArtifactId", "authorityArtifactId", "stateArtifactId"):
        require_integer(document[field], f"SDK Phase-10 {field}", 1)
    sdk_wave = document["sdkStateWave"]
    if (type(document["stateWave"]) is not int or document["stateWave"] != 0
            or (sdk_wave is not None and
                (type(sdk_wave) is not int or sdk_wave not in range(1, 20)))):
        raise ValueError("SDK Phase-10 control has an invalid exact SDK state wave")
    original = validate_producer(document["originalProducer"])
    authority = validate_producer(document["authorityProducer"])
    if (sha256_bytes(canonical_json_bytes(original)) != document["originalProducerSha256"]
            or sha256_bytes(canonical_json_bytes(authority)) !=
                document["authorityProducerSha256"]):
        raise ValueError("SDK Phase-10 control producer differs from its approved digest")
    if (original["repository"] != "codex-agent-labs/codex-agent"
            or original["workflowPath"] != ".github/workflows/ci.yml"
            or original["event"] != "pull_request"
            or authority["repository"] != original["repository"]
            or authority["workflowPath"] != original["workflowPath"]
            or authority["event"] != "workflow_dispatch"
            or authority["runId"] == original["runId"]):
        raise ValueError("SDK Phase-10 control requires distinct approved PR and authority producers")
    return document, original, authority


def stage_sdk_phase10_protected_inputs(control_file, *,
        expected_control_sha256, trusted_source, trusted_source_commit,
        original_checkout, plan_file, authority_file,
        expected_authority_sha256, election_files, semantic_files,
        keyring_file, keys_directory, expected_keyring_sha256,
        expected_keys_inventory_sha256, replay_control_files=None,
        destination):
    """Publish exact reviewed input files; never query hosted state or mint trust."""
    require_no_signing_secret(os.environ)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK protected input destination already exists")
    if Path(trusted_source) == Path(original_checkout):
        raise ValueError("SDK original validation checkout must be separate from trusted source")
    output = destination.resolve(strict=False)
    if any(output == path or output in path.parents or path in output.parents
            for path in (Path(trusted_source), Path(original_checkout),
                         Path(keys_directory))):
        raise ValueError("SDK protected input destination overlaps a reviewed source")
    raw = _source_file(control_file, "SDK protected control", 1024 * 1024)
    if sha256_bytes(raw) != require_sha256(expected_control_sha256,
            "Protected SDK control digest"):
        raise ValueError("SDK control differs from independent protected approval")
    control, original, authority_producer = _control(raw)
    if (control["trustedSourceCommit"] != trusted_source_commit
            or _checkout_identity(trusted_source, "Trusted SDK source")[0] !=
                trusted_source_commit):
        raise ValueError("SDK verifier source differs from protected reviewed commit")
    if _checkout_identity(original_checkout, "Original SDK validation") != (
            original["commit"], original["tree"]):
        raise ValueError("SDK original checkout differs from approved PR commit/tree")
    plan = _source_file(plan_file, "SDK original plan", 16 * 1024 * 1024)
    if sha256_bytes(plan) != control["planSha256"]:
        raise ValueError("SDK original plan differs from independently approved digest")
    with tempfile.TemporaryDirectory(prefix="sdk-protected-inputs-") as temporary:
        private = Path(temporary).resolve()
        plan_copy = private / "impact-plan.json"
        plan_copy.write_bytes(plan)
        lane_policy = require_original_lane_policy(original_checkout,
            original["commit"])
        validated = products._validate_plan(plan_copy, Path(original_checkout))
        if require_original_lane_policy(original_checkout,
                original["commit"]) != lane_policy:
            raise ValueError("SDK original lane policy changed during plan validation")
        if (validated["remoteBuildAuthorized"] is not True
                or validated["event"] != "pull_request"
                or validate_producer(products._consumer(validated, {},
                    original_run_id=original["runId"],
                    original_run_attempt=original["runAttempt"])["producer"])
                    != original):
            raise ValueError("SDK original plan differs from approved PR producer")
        authority_raw = _source_file(authority_file, "SDK campaign authority", 1024 * 1024)
        if (sha256_bytes(authority_raw) != require_sha256(
                    expected_authority_sha256, "Protected SDK authority digest")
                or control["authoritySha256"] != expected_authority_sha256):
            raise ValueError("SDK authority differs from independent protected approval")
        if set(election_files) != set(_FAMILIES) or set(semantic_files) != set(_FAMILIES):
            raise ValueError("SDK protected inputs require six exact policy files")
        policy = {}
        with held_pinned_sdk_campaign_authority(Path(authority_file),
                expected_authority_sha256) as authority:
            if authority["completedCatalogPin"]["producer"] != original:
                raise ValueError("SDK authority differs from approved original producer")
            for kind, paths in (("election", election_files), ("semantic", semantic_files)):
                for family in _FAMILIES:
                    payload = _source_file(paths[family], f"SDK {kind} {family}",
                        1024 * 1024)
                    if (sha256_bytes(payload) != authority[f"{kind}Sha256"][family]
                            or canonical_json_bytes(load_canonical_json_bytes(payload)) != payload):
                        raise ValueError(f"SDK {kind} {family} differs from approved authority")
                    policy[f"{kind}-{family}.json"] = payload
        replay_control_files = {} if replay_control_files is None else replay_control_files
        if not isinstance(replay_control_files, Mapping) or set(replay_control_files) - set(_REPLAY_CONTROLS):
            raise ValueError("SDK protected inputs contain an unknown replay control")
        controlled = {}
        for name in _REPLAY_CONTROLS:
            expected = control["replayControlSha256"][name]
            path = replay_control_files.get(name)
            if (expected is None) != (path is None):
                raise ValueError(f"SDK {name} requires its exact approved file and digest")
            if path is not None:
                payload = _source_file(path, f"SDK {name}", 16 * 1024 * 1024)
                if (sha256_bytes(payload) != expected
                        or canonical_json_bytes(load_canonical_json_bytes(payload)) != payload):
                    raise ValueError(f"SDK {name} differs from independent protected control")
                controlled[f"{name}.json"] = payload
        keyring_raw, _, _ = _release_key(keyring_file, keys_directory,
            expected_keyring_sha256, expected_keys_inventory_sha256)
        if (control["keyringSha256"] != expected_keyring_sha256
                or control["keysInventorySha256"] != expected_keys_inventory_sha256):
            raise ValueError("SDK signing keys differ from protected control")
        keys_before = regular_file_inventory(Path(keys_directory))
        staged = private / "staged"
        staged.mkdir()
        fixed = {"control.json": raw,
            "sdk-campaign-authority.json": authority_raw,
            "original-producer.json": canonical_json_bytes(original),
            "authority-producer.json": canonical_json_bytes(authority_producer),
            "plan/impact-plan.json": plan,
            "product-signing-keys.json": keyring_raw, **policy, **controlled}
        for name, data in fixed.items():
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        snapshot_regular_tree(Path(keys_directory), staged / "keys")
        if (regular_file_inventory(staged / "keys") != keys_before
                or _checkout_identity(trusted_source, "Trusted SDK source")[0] !=
                    trusted_source_commit
                or _checkout_identity(original_checkout, "Original SDK validation") !=
                    (original["commit"], original["tree"])
                or require_original_lane_policy(original_checkout,
                    original["commit"]) != lane_policy
                or _source_file(control_file, "SDK protected control", 1024 * 1024) != raw
                or _source_file(plan_file, "SDK original plan", 16 * 1024 * 1024) != plan
                or _source_file(authority_file, "SDK campaign authority", 1024 * 1024)
                    != authority_raw
                or _source_file(keyring_file, "SDK signing keyring", 64 * 1024)
                    != keyring_raw
                or any(_source_file(paths[family], f"SDK {kind} {family}",
                    1024 * 1024) != policy[f"{kind}-{family}.json"]
                    for kind, paths in (("election", election_files),
                                        ("semantic", semantic_files))
                    for family in _FAMILIES)
                or any(_source_file(replay_control_files[name], f"SDK {name}",
                    16 * 1024 * 1024) != controlled[f"{name}.json"]
                    for name in replay_control_files)):
            raise ValueError("SDK protected inputs changed during staging")
        inventory = regular_file_inventory(staged)
        require_no_signing_secret(os.environ)
        publish_regular_tree(staged, destination, expected_inventory=inventory)
    return {"destination": str(destination), "files": inventory}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    command = parser.add_subparsers(dest="mode", required=True).add_parser(
        "stage", allow_abbrev=False)
    for name in ("control", "trusted-source", "original-checkout", "plan",
                 "authority", "keyring", "keys-directory", "destination"):
        command.add_argument("--" + name, type=Path, required=True)
    for name in ("approved-control-sha256", "trusted-source-commit",
                 "approved-authority-sha256", "approved-keyring-sha256",
                 "approved-keys-inventory-sha256"):
        command.add_argument("--" + name, required=True)
    for kind in ("election", "semantic"):
        for family in _FAMILIES:
            command.add_argument(f"--{kind}-{family}", type=Path, required=True)
    for name in _REPLAY_CONTROLS:
        command.add_argument("--" + name.replace("_", "-"), type=Path)
    args = parser.parse_args(argv)
    try:
        result = stage_sdk_phase10_protected_inputs(
            args.control, expected_control_sha256=args.approved_control_sha256,
            trusted_source=args.trusted_source,
            trusted_source_commit=args.trusted_source_commit,
            original_checkout=args.original_checkout, plan_file=args.plan,
            authority_file=args.authority,
            expected_authority_sha256=args.approved_authority_sha256,
            election_files={family: getattr(args, "election_" + family.replace("-", "_"))
                for family in _FAMILIES},
            semantic_files={family: getattr(args, "semantic_" + family.replace("-", "_"))
                for family in _FAMILIES}, keyring_file=args.keyring,
            keys_directory=args.keys_directory,
            expected_keyring_sha256=args.approved_keyring_sha256,
            expected_keys_inventory_sha256=args.approved_keys_inventory_sha256,
            replay_control_files={name: getattr(args, name) for name in _REPLAY_CONTROLS
                if getattr(args, name) is not None},
            destination=args.destination)
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        parser.error(str(error))
    print(json.dumps({"destination": result["destination"]},
        sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
