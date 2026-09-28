"""Token-only custody of a protected, independently elected SDK catalog.

The resulting files are evidence, not a caller-controlled trust token. The
separate signer must recheck them against the same protected pins and the
official Phase-10 signed-index capture before composing a promoted catalog.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from ci.receipt import safe_extract
from ci.product_reuse import _CATALOG_ZIP_LIMITS, _require_artifact_job_window
from ci.sdk_campaign_pinned_election import held_pinned_sdk_campaign_authority
from ci.sdk_campaign_reused_original import held_completed_sdk_catalog
from ci.sdk_phase11_bytes import forward_verified_sdk_phase10_bytes
from ci.products.index import SignedProductIndex, _verify_index_receipt, verify_signed_product_index
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_integer, require_sha256, sha256_bytes, sha256_file,
    verified_zip_contents, write_canonical_json,
)
from ci.products.registry import PhaseInstanceId
from ci.products.receipt import validate_producer
from ci.products.restore import object_relative_path, verify_object
from ci.products.sdk_catalog_promotion import stage_promoted_sdk_catalog
from ci.products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from ci.products.signing_isolation import require_no_signing_secret


_OBJECT_PIN_KEYS = {"product", "component", "phase", "target", "buildKey",
                    "receiptSha256", "objectSha256", "relativePath"}
_WORKFLOW = ".github/workflows/product-validation.yml"
_JOB = "product-validation / sdk-catalog"


def _landed_commit(repository: Path) -> str:
    root = Path(repository).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("SDK landed checkout must be a directory")
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel", "HEAD"],
        capture_output=True, text=True, timeout=30)
    lines = result.stdout.splitlines()
    if (result.returncode or len(lines) != 2 or Path(lines[0]).resolve(strict=True) != root
            or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", lines[1]) is None):
        raise ValueError("SDK landed checkout is not the exact Git root and HEAD")
    return lines[1]


def _require_phase10_signing_policy(keyring: Path, keys_directory: Path, pins: dict) -> None:
    if (sha256_file(keyring, reject_symlink_parents=True) != require_sha256(
            pins["expected_keyring_sha256"], "SDK Phase-10 keyring digest")
            or sha256_bytes(canonical_json_bytes(regular_file_inventory(keys_directory)))
            != require_sha256(pins["expected_keys_inventory_sha256"],
                              "SDK Phase-10 public-key inventory digest")):
        raise ValueError("SDK catalog signer policy differs from pinned Phase-10 policy")


def _object_pins(path: Path, expected_digest: str, expected_index_digest: str) -> tuple[bytes, dict]:
    raw = read_regular_file_bytes(path, max_bytes=64 * 1024, reject_symlink_parents=True)
    if sha256_bytes(raw) != require_sha256(expected_digest, "SDK object pin file"):
        raise ValueError("SDK object pins differ from independent S1048 approval")
    document = require_exact_keys(load_canonical_json_bytes(raw),
        {"schemaVersion", "signedIndexSha256", "objects"}, "SDK object pins")
    if (document["schemaVersion"] != 1 or type(document["schemaVersion"]) is not int
            or document["signedIndexSha256"] != require_sha256(
                expected_index_digest, "SDK Phase-10 signed index digest")
            or type(document["objects"]) is not list
            or len(document["objects"]) != len(SDK_CAMPAIGN_INSTANCES)):
        raise ValueError("SDK object pins lack exact Phase-10 index and 62 objects")
    selected = {}
    order = []
    for row in document["objects"]:
        pin = require_exact_keys(row, _OBJECT_PIN_KEYS, "SDK object pin")
        instance = PhaseInstanceId(*(pin[field] for field in (
            "product", "component", "phase", "target")))
        if instance not in SDK_CAMPAIGN_INSTANCES or instance in selected:
            raise ValueError("SDK object pins contain an unknown or duplicate phase")
        for field in ("buildKey", "receiptSha256", "objectSha256"):
            require_sha256(pin[field], "SDK object " + field)
        if pin["relativePath"] != object_relative_path(pin["buildKey"], pin["receiptSha256"]):
            raise ValueError("SDK object pin path differs from its immutable identity")
        selected[instance] = pin
        order.append(instance)
    if order != sorted(SDK_CAMPAIGN_INSTANCES):
        raise ValueError("SDK object pins are not in canonical phase order")
    return raw, selected


def capture_promotable_sdk_original_catalog(
    authority_file: Path, object_pins_file: Path, destination: Path, *,
    expected_authority_sha256: str, expected_object_pins_sha256: str,
    expected_signed_index_sha256: str, expected_catalog_artifact_size: int,
    trusted_workflow_sha: str, token: str, environ: dict[str, str],
) -> dict:
    """Capture exact official SDK dev catalog ZIP after protected pin election.

    No product bytes are built or signed here. Phase-10 signed-index transport
    and landed-tree authority are *not* established by this function.
    """
    require_no_signing_secret(environ)
    require_no_signing_secret(os.environ)
    if type(token) is not str or not token:
        raise ValueError("SDK catalog capture requires an observation token")
    if type(trusted_workflow_sha) is not str or re.fullmatch(r"[0-9a-f]{40}", trusted_workflow_sha) is None:
        raise ValueError("SDK catalog requires a pinned workflow commit")
    size = require_integer(expected_catalog_artifact_size,
                           "SDK catalog protected artifact size", 1)
    if Path(destination).exists() or Path(destination).is_symlink():
        raise ValueError("SDK catalog capture destination already exists")
    selected_raw, object_pins = _object_pins(
        object_pins_file, expected_object_pins_sha256, expected_signed_index_sha256)
    with held_pinned_sdk_campaign_authority(
            Path(authority_file), expected_authority_sha256) as authority:
        pin = authority["completedCatalogPin"]
        if (pin["trusted_workflow_path"] != _WORKFLOW
                or pin["trusted_job_name"] != _JOB
                or pin["producer"]["workflowPath"] != ".github/workflows/ci.yml"
                or pin["producer"]["repository"] != "codex-agent-labs/codex-agent"):
            raise ValueError("SDK catalog pin does not name the fixed original CI job")
        with held_completed_sdk_catalog(**pin, trusted_workflow_sha=trusted_workflow_sha,
                token=token, environ=environ) as held:
            values = held.values
            artifact_paths = {tuple(getattr(instance, field) for field in (
                "product", "component", "phase", "target")): path
                for instance, path in authority["artifactPaths"].items()}
            if values["artifact"].get("size_in_bytes") != size:
                raise ValueError("SDK official catalog size differs from protected pin")
            entries = {PhaseInstanceId(*(entry[field] for field in (
                "product", "component", "phase", "target"))): entry
                for entry in values["index"]["entries"]}
            if len(values["index"]["entries"]) != len(SDK_CAMPAIGN_INSTANCES) \
                    or set(entries) != SDK_CAMPAIGN_INSTANCES:
                raise ValueError("SDK official catalog lacks exact 62-phase membership")
            for instance in sorted(SDK_CAMPAIGN_INSTANCES):
                row, entry = object_pins[instance], entries[instance]
                if (any(row[field] != entry[field] for field in (
                        "product", "component", "phase", "target", "buildKey", "receiptSha256"))
                        or entry["artifactName"] != artifact_paths[(instance.product,
                            instance.component, instance.phase, instance.target)]):
                    raise ValueError("SDK object pins differ from approved catalog entry")
                archive = values["catalog"].objects.get(entry["buildKey"])
                if archive is None or archive.relative_to(values["root"]).as_posix() != \
                        (f"catalogs/same-pr/{pin['artifact_id']}/contents/{row['relativePath']}"):
                    raise ValueError("SDK catalog object is absent from official upload")
                verified = verify_object(archive, build_key=row["buildKey"],
                    receipt_sha256=row["receiptSha256"], object_sha256=row["objectSha256"])
                _verify_index_receipt(entry, {**verified, "receiptSha256": row["receiptSha256"]})
            source = values["root"] / "catalogs" / "same-pr" / str(pin["artifact_id"]) / "transport.zip"
            if source.stat().st_size != size or sha256_file(source) != pin["artifact_sha256"]:
                raise ValueError("SDK official catalog ZIP differs from protected upload pin")
            destination = Path(destination)
            output = destination.resolve(strict=False)
            originals = [Path(authority_file).resolve(strict=True),
                         Path(object_pins_file).resolve(strict=True), source.resolve(strict=True)]
            if any(output == path or output in path.parents or path in output.parents
                   for path in originals):
                raise ValueError("SDK catalog capture output overlaps original input")
            with tempfile.TemporaryDirectory(prefix="sdk-promotable-catalog-") as temporary:
                prepared = Path(temporary).resolve() / "capture"
                prepared.mkdir()
                target = prepared / "official-catalog.zip"
                shutil.copyfile(source, target)
                if target.stat().st_size != size or sha256_file(target) != pin["artifact_sha256"]:
                    raise ValueError("SDK official catalog changed while captured")
                (prepared / "authority.json").write_bytes(read_regular_file_bytes(
                    authority_file, max_bytes=1024 * 1024, reject_symlink_parents=True))
                (prepared / "object-pins.json").write_bytes(selected_raw)
                write_canonical_json(prepared / "transport.json", {
                    "schemaVersion": 1, "artifact": values["artifact"],
                    "observed": values["producer"],
                    "indexSha256": values["indexSha256"],
                    "publicKeySha256": values["keySha256"],
                    "trustedWorkflowSha": trusted_workflow_sha,
                })
                inventory = regular_file_inventory(prepared)
                if (sha256_file(source) != pin["artifact_sha256"]
                        or read_regular_file_bytes(object_pins_file, max_bytes=64 * 1024,
                            reject_symlink_parents=True) != selected_raw):
                    raise ValueError("SDK protected catalog inputs changed during capture")
                require_no_signing_secret(environ)
                require_no_signing_secret(os.environ)
                publish_regular_tree(prepared, destination, expected_inventory=inventory)
    return {"inventorySha256": sha256_bytes(canonical_json_bytes(inventory)),
            "artifactId": pin["artifact_id"], "artifactSha256": pin["artifact_sha256"],
            "signedIndexSha256": expected_signed_index_sha256}


def sign_promoted_sdk_catalog(
    protected_catalog_capture: Path, protected_index_capture: Path,
    authority_file: Path, object_pins_file: Path, landed_repository: Path,
    destination: Path, *, expected_catalog_capture_inventory_sha256: str,
    expected_authority_sha256: str, expected_object_pins_sha256: str,
    expected_catalog_artifact_size: int, trusted_workflow_sha: str,
    index_handoff_pins: dict, repository: str, context: dict, producer: dict,
    keyring: Path, keys_directory: Path, private_key: Path,
    environ: dict[str, str],
) -> dict:
    """Token-free recheck of protected captures, then sign one new index only.

    The caller must independently pin the capture inventory and Phase-10 index
    handoff. The local landed Git tree must equal Phase-10 validation's tree.
    """
    tokens = {"GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_TOKEN",
              "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN"}
    if tokens & set(environ) or tokens & set(os.environ):
        raise ValueError("SDK promoted catalog signer must not receive an observation token")
    if type(index_handoff_pins) is not dict:
        raise ValueError("SDK signed-index handoff requires exact protected pins")
    handoff_keys = {"expected_inventory_sha256", "expected_index_sha256",
        "expected_signature_sha256", "expected_authority_sha256",
        "expected_signed_upload_sha256", "expected_authority_upload_sha256",
        "expected_authority_transport_sha256", "expected_keyring_sha256",
        "expected_keys_inventory_sha256", "expected_sdk_version",
        "expected_source_commit", "expected_source_tree", "expected_validation_tree"}
    require_exact_keys(index_handoff_pins, handoff_keys, "SDK Phase-10 index handoff pins")
    promoted_producer = validate_producer(producer)
    landed_tree = index_handoff_pins["expected_validation_tree"]
    if (promoted_producer["event"] != "push"
            or promoted_producer["tree"] != landed_tree
            or not isinstance(context, dict)
            or context.get("kind") != "promoted-main"
            or context.get("tree") != landed_tree):
        raise ValueError("SDK promoted producer and context must name the Phase-10 landed tree")
    landed_commit = _landed_commit(landed_repository)
    if promoted_producer["commit"] != landed_commit or context.get("commit") != landed_commit:
        raise ValueError("SDK promoted producer and context must name landed checkout HEAD")
    _require_phase10_signing_policy(keyring, keys_directory, index_handoff_pins)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK promoted catalog destination already exists")
    source_paths = [protected_catalog_capture, protected_index_capture, authority_file,
                    object_pins_file, landed_repository, keyring, keys_directory, private_key]
    output = destination.resolve(strict=False)
    for path in source_paths:
        source = Path(path).resolve(strict=True)
        if output == source or output in source.parents or source in output.parents:
            raise ValueError("SDK promoted catalog output overlaps a protected input")
    capture_inventory = regular_file_inventory(protected_catalog_capture)
    if sha256_bytes(canonical_json_bytes(capture_inventory)) != require_sha256(
            expected_catalog_capture_inventory_sha256, "SDK protected catalog capture inventory"):
        raise ValueError("SDK official catalog capture differs from independent inventory pin")
    if {row["relativePath"] for row in capture_inventory} != {
            "authority.json", "object-pins.json", "official-catalog.zip", "transport.json"}:
        raise ValueError("SDK catalog capture has unexpected or missing files")
    pins_raw, object_pins = _object_pins(object_pins_file,
        expected_object_pins_sha256, index_handoff_pins["expected_index_sha256"])
    if (read_regular_file_bytes(Path(protected_catalog_capture) / "authority.json",
            max_bytes=1024 * 1024, reject_symlink_parents=True) !=
            read_regular_file_bytes(authority_file, max_bytes=1024 * 1024,
                                    reject_symlink_parents=True)
            or read_regular_file_bytes(Path(protected_catalog_capture) / "object-pins.json",
                max_bytes=64 * 1024, reject_symlink_parents=True) != pins_raw):
        raise ValueError("SDK captured authority or object pins differ from protected inputs")
    with held_pinned_sdk_campaign_authority(Path(authority_file),
            expected_authority_sha256) as authority:
        pin = authority["completedCatalogPin"]
        if (pin["trusted_workflow_path"] != _WORKFLOW or pin["trusted_job_name"] != _JOB
                or pin["producer"]["repository"] != repository
                or index_handoff_pins["expected_authority_sha256"] != expected_authority_sha256
                or index_handoff_pins["expected_source_commit"] != pin["producer"]["commit"]
                or index_handoff_pins["expected_source_tree"] != pin["producer"]["tree"]
                or index_handoff_pins["expected_sdk_version"] != authority["sdkVersion"]):
            raise ValueError("SDK Phase-10 handoff and original catalog authority differ")
        transport = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(
            Path(protected_catalog_capture) / "transport.json", max_bytes=1024 * 1024,
            reject_symlink_parents=True)),
            {"schemaVersion", "artifact", "observed", "indexSha256",
             "publicKeySha256", "trustedWorkflowSha"}, "SDK catalog capture transport")
        size = require_integer(expected_catalog_artifact_size,
                               "SDK catalog protected artifact size", 1)
        if (transport["schemaVersion"] != 1 or type(transport["schemaVersion"]) is not int
                or transport["trustedWorkflowSha"] != trusted_workflow_sha
                or transport["artifact"].get("id") != pin["artifact_id"]
                or transport["artifact"].get("digest") != pin["artifact_sha256"]
                or transport["artifact"].get("size_in_bytes") != size
                or transport["indexSha256"] != pin["index_sha256"]
                or transport["publicKeySha256"] != pin["public_key_sha256"]):
            raise ValueError("SDK captured official upload differs from protected selection")
        observed = transport["observed"]
        if (type(observed) is not list or len(observed) != 1
                or type(observed[0]) is not dict):
            raise ValueError("SDK captured original producer observation is incomplete")
        observation = observed[0]
        run = observation.get("run")
        tested = observation.get("testedCommit")
        if (not isinstance(run, dict) or not isinstance(tested, dict)
                or run.get("id") != pin["producer"]["runId"]
                or run.get("run_attempt") != pin["producer"]["runAttempt"]
                or run.get("path") != pin["producer"]["workflowPath"]
                or tested.get("sha") != pin["producer"]["commit"]
                or not isinstance(tested.get("tree"), dict)
                or tested["tree"].get("sha") != pin["producer"]["tree"]):
            raise ValueError("SDK captured producer observation differs from protected selection")
        _require_artifact_job_window(observation, _JOB, transport["artifact"])
        archive = Path(protected_catalog_capture) / "official-catalog.zip"
        if archive.stat().st_size != size or sha256_file(archive) != pin["artifact_sha256"]:
            raise ValueError("SDK captured official catalog ZIP differs from protected digest")
        with tempfile.TemporaryDirectory(prefix="sdk-promoted-catalog-sign-") as temporary:
            root = Path(temporary).resolve()
            forwarded = root / "phase10"
            forward_verified_sdk_phase10_bytes(protected_index_capture, forwarded,
                landed_repository=landed_repository, **index_handoff_pins)
            _require_phase10_signing_policy(
                forwarded / "replay-evidence/product-signing-keys.json",
                forwarded / "replay-evidence/keys", index_handoff_pins)
            listing, _, _ = verified_zip_contents(archive, retained_paths=(),
                allow_empty_members=True, **_CATALOG_ZIP_LIMITS)
            original = root / "original"
            safe_extract(archive, original)
            if regular_file_inventory(original) != listing:
                raise ValueError("SDK official catalog ZIP changed during extraction")
            if (sha256_file(original / "product-index.json") != pin["index_sha256"]
                    or sha256_file(original / "public-key.pub") != pin["public_key_sha256"]):
                raise ValueError("SDK original catalog index or key differs from protected pin")
            dev_index, _ = verify_signed_product_index(SignedProductIndex(
                original / "product-index.json", original / "product-index.sig"),
                original / "public-key.pub")
            if (dev_index["repository"] != repository or dev_index["producer"] != pin["producer"]
                    or dev_index["trustDomain"] != "development"):
                raise ValueError("SDK original catalog differs from approved producer")
            phase_pins = {}
            objects = {}
            entries = {PhaseInstanceId(*(entry[field] for field in (
                "product", "component", "phase", "target"))): entry
                for entry in dev_index["entries"]}
            if len(dev_index["entries"]) != len(SDK_CAMPAIGN_INSTANCES) \
                    or set(entries) != SDK_CAMPAIGN_INSTANCES:
                raise ValueError("SDK original catalog lacks exact 62-phase membership")
            artifact_paths = {tuple(getattr(instance, field) for field in (
                "product", "component", "phase", "target")): path
                for instance, path in authority["artifactPaths"].items()}
            for instance in sorted(SDK_CAMPAIGN_INSTANCES):
                row, entry = object_pins[instance], entries[instance]
                if (entry["buildKey"] != row["buildKey"]
                        or entry["receiptSha256"] != row["receiptSha256"]
                        or entry["artifactName"] != artifact_paths[(instance.product,
                            instance.component, instance.phase, instance.target)]):
                    raise ValueError("SDK original catalog differs from protected phase pin")
                objects[instance] = original / row["relativePath"]
                phase_pins[instance] = {"buildKey": row["buildKey"],
                    "receiptSha256": row["receiptSha256"],
                    "objectSha256": row["objectSha256"],
                    "artifactPath": entry["artifactName"],
                    "producer": verify_object(objects[instance], build_key=row["buildKey"],
                        receipt_sha256=row["receiptSha256"],
                        object_sha256=row["objectSha256"])["receipt"]["producer"]}
            pair = forwarded / "signed-pair"
            promoted = root / "promoted"
            index = stage_promoted_sdk_catalog(objects, phase_pins,
                SignedProductIndex(pair / "product-index.json", pair / "product-index.sig"),
                promoted, repository=repository,
                campaign_context={"kind": "pull-request",
                    "pullRequest": pin["producer"]["pullRequest"],
                    **{field: pin["producer"][field] for field in (
                        "commit", "tree", "runId", "runAttempt")}},
                expected_index_sha256=index_handoff_pins["expected_index_sha256"],
                expected_signature_sha256=index_handoff_pins["expected_signature_sha256"],
                context=context, producer=producer, keyring=keyring,
                keys_directory=keys_directory, private_key=private_key)
            if (regular_file_inventory(protected_catalog_capture) != capture_inventory
                    or sha256_file(archive) != pin["artifact_sha256"]
                    or read_regular_file_bytes(object_pins_file, max_bytes=64 * 1024,
                        reject_symlink_parents=True) != pins_raw):
                raise ValueError("SDK protected capture changed during catalog signing")
            if _landed_commit(landed_repository) != landed_commit:
                raise ValueError("SDK landed checkout HEAD changed during catalog signing")
            _require_phase10_signing_policy(keyring, keys_directory, index_handoff_pins)
            publish_regular_tree(promoted, destination,
                expected_inventory=regular_file_inventory(promoted))
    return index
