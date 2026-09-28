"""Prepare exact original SDK Maven packages with a token; sign them offline.

The protected caller must independently pin the canonical control JSON and
download the signed index, original plan, and three original receipts. This
module neither elects originals nor repeats the all-61 semantic campaign.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci import product_reuse
from ci.products.index import SignedProductIndex, _verify_index_receipt, verify_release_product_index
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_sha256, sha256_bytes, snapshot_regular_tree, write_canonical_json,
)
from ci.products.receipt import validate_producer
from ci.products.registry import PhaseInstanceId
from ci.products.restore import restore_object, verify_phase_shard
from ci.products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from ci.products.sdk_phase10_maven import produce_sdk_phase10_maven_sidecars
from ci.sdk_phase10_maven_campaign import capture_sdk_phase10_maven_campaign
from ci.sdk_facade_capture import verify_retained_sdk_phase_upload


_TARGETS = {"sdk-core": "common", "sdk-android": "android", "sdk-ios": "ios"}
_CONTROL = {"schemaVersion", "signedIndexSha256", "signatureSha256",
            "keyringSha256", "keysInventorySha256", "planSha256",
            "pgpPublicKeySha256", "packages"}
_PACKAGE = {"component", "target", "receiptSha256", "producer",
            "producerSha256", "artifactId", "artifactSha256", "trustedWorkflowSha"}
_TOKENS = {"GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_TOKEN",
           "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN"}
_SECRETS = {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", "SIGNING_IN_MEMORY_KEY",
            "SIGNING_IN_MEMORY_KEY_PASSWORD"}


def _read(path: Path, limit: int = 16 * 1024 * 1024) -> bytes:
    return read_regular_file_bytes(Path(path), max_bytes=limit, reject_symlink_parents=True)


def _selection(raw: bytes, approved_sha256: str) -> dict:
    if sha256_bytes(raw) != require_sha256(approved_sha256, "SDK Maven protected control"):
        raise ValueError("SDK Maven control differs from independent approval")
    control = require_exact_keys(load_canonical_json_bytes(raw), _CONTROL, "SDK Maven control")
    if control["schemaVersion"] != 1 or type(control["packages"]) is not list or len(control["packages"]) != 3:
        raise ValueError("SDK Maven control requires exactly three packages")
    for field in ("signedIndexSha256", "signatureSha256", "keyringSha256",
                  "keysInventorySha256", "planSha256", "pgpPublicKeySha256"):
        require_sha256(control[field], f"SDK Maven {field}")
    seen = set()
    for row in control["packages"]:
        require_exact_keys(row, _PACKAGE, "SDK Maven package selection")
        component = row["component"]
        if component not in _TARGETS or row["target"] != _TARGETS[component] or component in seen:
            raise ValueError("SDK Maven selection has duplicate or wrong package identity")
        seen.add(component)
        validate_producer(row["producer"])
        for field in ("receiptSha256", "producerSha256", "artifactSha256"):
            require_sha256(row[field], f"SDK Maven {field}")
    if seen != set(_TARGETS):
        raise ValueError("SDK Maven control does not cover exact package set")
    return control


def _no_overlap(destination: Path, *sources: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK Maven handoff destination already exists")
    output = destination.resolve(strict=False)
    for source in sources:
        resolved = Path(source).resolve(strict=True)
        if output == resolved or output in resolved.parents or resolved in output.parents:
            raise ValueError("SDK Maven handoff output overlaps an input")


def prepare_sdk_phase10_maven_handoff(
    control_path: Path, destination: Path, *, approved_control_sha256: str,
    signed_index: SignedProductIndex, keyring: Path, keys_directory: Path,
    original_plan: Path, original_root: Path, receipts_directory: Path,
    pgp_public_key: Path, token: str,
) -> dict:
    """Capture only independently approved, original SDK package objects."""
    if _SECRETS & set(os.environ):
        raise ValueError("SDK Maven observation process must not receive signing secrets")
    paths = (control_path, signed_index.manifest, signed_index.signature, keyring,
             keys_directory, original_plan, original_root, receipts_directory, pgp_public_key)
    _no_overlap(Path(destination), *(Path(path) for path in paths))
    raw_control = _read(control_path)
    control = _selection(raw_control, approved_control_sha256)
    raw_plan = _read(original_plan)
    public_key = _read(pgp_public_key, 1024 * 1024)
    if (sha256_bytes(raw_plan) != control["planSha256"]
            or not public_key or sha256_bytes(public_key) != control["pgpPublicKeySha256"]):
        raise ValueError("SDK Maven plan or PGP public key differs from protected control")
    receipts = {row["component"]: _read(Path(receipts_directory) / (row["component"] + ".json"))
                for row in control["packages"]}
    selections = {
        PhaseInstanceId("sdk", row["component"], "package", row["target"]): {
            "plan": str(original_plan), "repositoryRoot": str(original_root),
            "receipt": str(Path(receipts_directory) / (row["component"] + ".json")),
            **{name: row[name] for name in _PACKAGE - {"component", "target"}},
        } for row in control["packages"]
    }
    with tempfile.TemporaryDirectory(prefix="sdk-p10-maven-prepare-") as temporary:
        root = Path(temporary).resolve()
        prepared = root / "prepared"
        prepared.mkdir()
        capture_sdk_phase10_maven_campaign(
            signed_index, prepared / "custody",
            expected_index_sha256=control["signedIndexSha256"],
            expected_signature_sha256=control["signatureSha256"],
            keyring_path=keyring, keys_directory=keys_directory,
            expected_keyring_sha256=control["keyringSha256"],
            expected_keys_inventory_sha256=control["keysInventorySha256"],
            selections=selections, token=token,
        )
        (prepared / "control.json").write_bytes(raw_control)
        (prepared / "publication-pgp-public-key.asc").write_bytes(public_key)
        inventory = regular_file_inventory(prepared, allow_empty=True)
        write_canonical_json(prepared / "preparation.json", {
            "schemaVersion": 1, "approvedControlSha256": approved_control_sha256,
            "preparedFiles": inventory,
        })
        if (_read(control_path) != raw_control or _read(original_plan) != raw_plan
                or _read(pgp_public_key, 1024 * 1024) != public_key
                or any(_read(Path(receipts_directory) / (name + ".json")) != value
                       for name, value in receipts.items())):
            raise ValueError("SDK Maven protected inputs changed during observation")
        expected = regular_file_inventory(prepared, allow_empty=True)
        if _SECRETS & set(os.environ):
            raise ValueError("SDK Maven observation gained signing secrets")
        publish_regular_tree(prepared, Path(destination), allow_empty=True,
                             expected_inventory=expected)
    return {"preparationSha256": sha256_bytes(_read(Path(destination) / "preparation.json")),
            "files": expected}


def sign_sdk_phase10_maven_handoff(
    prepared: Path, destination: Path, *, expected_preparation_sha256: str,
    expected_control_sha256: str,
    expected_pgp_key_sha256: str, signing_home: Path,
    signing_fingerprint: str, passphrase: str,
) -> dict:
    """Sign only a verified local preparation, with no observation token."""
    if _TOKENS & set(os.environ):
        raise ValueError("SDK Maven signer must not receive an observation token")
    _no_overlap(Path(destination), Path(prepared), Path(signing_home))
    original_inventory = regular_file_inventory(prepared, allow_empty=True)
    with tempfile.TemporaryDirectory(prefix="sdk-p10-maven-sign-") as temporary:
        root = Path(temporary).resolve()
        held = root / "prepared"
        snapshot_regular_tree(prepared, held, allow_empty=True)
        if regular_file_inventory(held, allow_empty=True) != original_inventory:
            raise ValueError("SDK Maven preparation changed while being held")
        raw = _read(held / "preparation.json")
        if sha256_bytes(raw) != require_sha256(expected_preparation_sha256, "SDK preparation digest"):
            raise ValueError("SDK Maven preparation differs from approved digest")
        prep = require_exact_keys(load_canonical_json_bytes(raw),
            {"schemaVersion", "approvedControlSha256", "preparedFiles"}, "SDK Maven preparation")
        if (prep["schemaVersion"] != 1 or
                prep["approvedControlSha256"] != require_sha256(
                    expected_control_sha256, "SDK independent control digest") or
                prep["preparedFiles"] != [
                    entry for entry in original_inventory
                    if entry["relativePath"] != "preparation.json"]):
            raise ValueError("SDK Maven preparation inventory differs from its pin")
        control = _selection(_read(held / "control.json"), prep["approvedControlSha256"])
        if control["pgpPublicKeySha256"] != require_sha256(
                expected_pgp_key_sha256, "SDK PGP protected key digest"):
            raise ValueError("SDK Maven signer PGP key differs from protected authority")
        public_key = held / "publication-pgp-public-key.asc"
        if sha256_bytes(_read(public_key, 1024 * 1024)) != expected_pgp_key_sha256:
            raise ValueError("SDK Maven held public key differs from protected authority")
        custody = held / "custody"
        campaign = custody / "campaign"
        index, raw_index = verify_release_product_index(
            SignedProductIndex(campaign / "product-index.json", campaign / "product-index.sig"),
            keyring_path=campaign / "product-signing-keys.json",
            keys_directory=campaign / "keys")
        entries = {PhaseInstanceId(*(entry[field] for field in
            ("product", "component", "phase", "target"))): entry for entry in index["entries"]}
        if (sha256_bytes(raw_index) != control["signedIndexSha256"]
                or sha256_bytes(_read(campaign / "product-index.sig")) != control["signatureSha256"]
                or sha256_bytes(_read(campaign / "product-signing-keys.json")) != control["keyringSha256"]
                or sha256_bytes(canonical_json_bytes(regular_file_inventory(campaign / "keys"))) !=
                    control["keysInventorySha256"]
                or index["repository"] != "codex-agent-labs/codex-agent"
                or index["trustDomain"] != "release"
                or index["context"]["kind"] != "pull-request"
                or any(row["producer"]["repository"] != index["repository"]
                       or row["producer"]["pullRequest"] != index["context"]["pullRequest"]
                       for row in control["packages"])
                or len(index["entries"]) != len(SDK_CAMPAIGN_INSTANCES)
                or len({entry["productVersion"] for entry in index["entries"]}) != 1
                or set(entries) != SDK_CAMPAIGN_INSTANCES):
            raise ValueError("SDK Maven held campaign differs from approved signature and policy")
        records = require_exact_keys(load_canonical_json_bytes(_read(custody / "custody.json")),
            {"schemaVersion", "product", "signedIndexSha256", "signedIndexSignatureSha256", "packages"},
            "SDK Maven custody")
        if (records["schemaVersion"] != 1 or records["product"] != "sdk"
                or records["signedIndexSha256"] != control["signedIndexSha256"]
                or records["signedIndexSignatureSha256"] != control["signatureSha256"]
                or len(records["packages"]) != 3):
            raise ValueError("SDK Maven held custody differs from approved packages")
        # Authenticate every retained original before first use of the PGP secret.
        selected = []
        for row in control["packages"]:
            component = row["component"]
            instance = PhaseInstanceId("sdk", component, "package", row["target"])
            matched = [item for item in records["packages"] if item["component"] == component]
            if len(matched) != 1 or matched[0]["target"] != row["target"] or \
                    matched[0]["receiptSha256"] != row["receiptSha256"] or \
                    matched[0]["producerSha256"] != row["producerSha256"] or \
                    matched[0]["artifactId"] != row["artifactId"] or \
                    matched[0]["artifactSha256"] != row["artifactSha256"]:
                raise ValueError("SDK Maven held package differs from approved original")
            stage = custody / component / "stage"
            receipt = custody / component / "phase-receipt.json"
            receipt_bytes = _read(receipt)
            if (regular_file_inventory(stage) != matched[0]["stageFiles"]
                    or sha256_bytes(receipt_bytes) != row["receiptSha256"]):
                raise ValueError("SDK Maven held stage differs from original custody")
            capture = custody / component / "capture"
            transport = require_exact_keys(load_canonical_json_bytes(
                _read(capture / "capture-transport.json")),
                {"artifact", "captureProducer", "observed", "packageReceiptSha256"},
                "SDK Maven retained transport")
            if (transport["artifact"]["id"] != row["artifactId"]
                    or transport["artifact"]["digest"] != row["artifactSha256"]
                    or transport["captureProducer"] != row["producer"]
                    or transport["packageReceiptSha256"] != row["receiptSha256"]):
                raise ValueError("SDK Maven retained transport differs from protected approval")
            if component == "sdk-ios":
                product_reuse.verify_retained_sdk_ios_upload(capture, receipt_bytes)
            else:
                verify_retained_sdk_phase_upload(capture, receipt_bytes)
            shard = verify_phase_shard(capture / "original/shard", instance)
            _verify_index_receipt(entries[instance], {
                "receipt": shard["receipt"], "receiptSha256": shard["receiptSha256"]})
            if (shard["receiptBytes"] != receipt_bytes
                    or shard["objectSha256"] != matched[0]["objectSha256"]):
                raise ValueError("SDK Maven retained object differs from approved custody")
            restored = root / "replayed" / component
            restored.parent.mkdir(exist_ok=True)
            object_result = restore_object(capture / "original/shard" / shard["objectPath"],
                restored, build_key=shard["buildKey"],
                receipt_sha256=shard["receiptSha256"], object_sha256=shard["objectSha256"])
            if (object_result["receiptBytes"] != receipt_bytes
                    or regular_file_inventory(restored) != matched[0]["stageFiles"]
                    or regular_file_inventory(restored) != regular_file_inventory(stage)):
                raise ValueError("SDK Maven retained stage differs from restored original object")
            selected.append((component, stage, receipt))
        published = root / "published"
        published.mkdir()
        snapshot_regular_tree(custody, published / "custody", allow_empty=True)
        (published / "publication-pgp-public-key.asc").write_bytes(_read(public_key, 1024 * 1024))
        (published / "maven-sidecars").mkdir()
        results = []
        for component, stage, receipt in selected:
            result = produce_sdk_phase10_maven_sidecars(
                stage, receipt, published / "maven-sidecars" / component,
                public_key, expected_pgp_key_sha256,
                signing_home, signing_fingerprint, passphrase)
            results.append(result)
        write_canonical_json(published / "sidecar-selection.json", {
            "schemaVersion": 1, "product": "sdk", "approvedControlSha256": prep["approvedControlSha256"],
            "preparationSha256": expected_preparation_sha256, "packages": results,
        })
        output = regular_file_inventory(published, allow_empty=True)
        if (regular_file_inventory(held, allow_empty=True) != original_inventory
                or regular_file_inventory(prepared, allow_empty=True) != original_inventory
                or _TOKENS & set(os.environ)):
            raise ValueError("SDK Maven prepared bytes or signing isolation changed")
        publish_regular_tree(published, Path(destination), allow_empty=True,
                             expected_inventory=output)
    return {"packages": results, "files": output}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="mode", required=True)
    prepare = commands.add_parser("prepare")
    for name in ("control", "destination", "approved-control-sha256", "signed-index",
                 "signature", "keyring", "keys-directory", "original-plan",
                 "original-root", "receipts-directory", "pgp-public-key"):
        prepare.add_argument("--" + name, required=True)
    sign = commands.add_parser("sign")
    for name in ("prepared", "destination", "expected-preparation-sha256",
                 "expected-control-sha256", "expected-pgp-key-sha256",
                 "signing-home", "signing-fingerprint"):
        sign.add_argument("--" + name, required=True)
    arguments = parser.parse_args(argv)
    try:
        if arguments.mode == "prepare":
            result = prepare_sdk_phase10_maven_handoff(
                Path(arguments.control), Path(arguments.destination),
                approved_control_sha256=arguments.approved_control_sha256,
                signed_index=SignedProductIndex(Path(arguments.signed_index), Path(arguments.signature)),
                keyring=Path(arguments.keyring), keys_directory=Path(arguments.keys_directory),
                original_plan=Path(arguments.original_plan), original_root=Path(arguments.original_root),
                receipts_directory=Path(arguments.receipts_directory),
                pgp_public_key=Path(arguments.pgp_public_key), token=os.environ.get("GITHUB_TOKEN", ""))
        else:
            result = sign_sdk_phase10_maven_handoff(
                Path(arguments.prepared), Path(arguments.destination),
                expected_preparation_sha256=arguments.expected_preparation_sha256,
                expected_control_sha256=arguments.expected_control_sha256,
                expected_pgp_key_sha256=arguments.expected_pgp_key_sha256,
                signing_home=Path(arguments.signing_home),
                signing_fingerprint=arguments.signing_fingerprint, passphrase=sys.stdin.read())
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
