"""S808 fixture identities, never evidence of a real compiler or hosted runner."""

from pathlib import Path
from typing import Any
import zipfile

from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, sha256_bytes, sha256_file,
    require_exact_keys, require_integer, write_canonical_json,
)
from ci.products.receipt import compute_build_key, output_inventory_digest, validate_phase_receipt
from ci.products.registry import PhaseInstanceId


TOOLCHAIN = sha256_bytes(b"S808 synthetic fixture profile; not hosted execution")


def output(kind: str, path: str, contents: bytes) -> dict[str, Any]:
    return {"kind": kind, "relativePath": path, "bytes": len(contents), "sha256": sha256_bytes(contents)}


def reference(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        **{name: receipt[name] for name in ("product", "component", "phase", "target", "buildKey")},
        "outputsDigest": output_inventory_digest(receipt["outputs"]),
    }


def contract_reference(contract: dict[str, Any], component: str) -> dict[str, Any]:
    receipt = load_canonical_json_bytes(contract["receipt"].read_bytes())
    with zipfile.ZipFile(contract["payload"]) as archive:
        manifest_digest = sha256_bytes(archive.read("contract-manifest.json"))
    manifest = contract["manifest"]
    return {
        **reference(receipt),
        "contractProjection": {
            "schemaVersion": 1,
            "receiptSha256": sha256_file(contract["receipt"]),
            "bundlePath": receipt["outputs"][0]["relativePath"],
            "bundleSha256": sha256_file(contract["payload"]),
            "manifestSha256": manifest_digest,
            "contractVersion": manifest["contractVersion"],
            "contractDigest": manifest["contractDigest"],
            "componentDigests": [{"component": component, "sha256": manifest["components"][component]["sha256"]}],
        },
    }


def write_receipt(
    path: Path, *, component: str, phase: str, target: str,
    outputs: list[dict[str, Any]], upstream: list[dict[str, Any]],
    context: dict[str, Any], product: str = "runtime", version: str = "0.2.7",
    version_identity: str = "0.2.0", toolchain: str = TOOLCHAIN,
    inventory: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    marker = f"S808 synthetic input:{product}:{component}:{phase}:{target}".encode()
    if inventory is None:
        inventory = [{"relativePath": "fixture/input.txt", "bytes": len(marker), "sha256": sha256_bytes(marker)}]
    inputs = {
        "inventory": inventory,
        "phaseInputDigest": sha256_bytes(canonical_json_bytes(inventory)),
        "versionIdentity": version_identity,
        "upstreamArtifacts": sorted(upstream, key=lambda item: tuple(
            item[name] for name in ("product", "component", "phase", "target", "buildKey")
        )),
        "toolchainProfileDigest": toolchain,
        "flagsDigest": sha256_bytes(b"S808 synthetic flags"),
        "outputSchemaVersion": 1,
    }
    identity = PhaseInstanceId(product, component, phase, target)
    planned = None
    if "plan_factory" in context:
        if not callable(context["plan_factory"]):
            raise ValueError("Fixture plan factory must be callable")
        planned = require_exact_keys(context["plan_factory"](identity, upstream), {
            "schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs",
        }, "Synthetic fixture original plan")
        if require_integer(planned["schemaVersion"], "Fixture plan schema", 1) != 1 or any(
            planned[key] != getattr(identity, key) for key in ("product", "component", "phase", "target")
        ):
            raise ValueError("Fixture plan identity differs from the original phase")
        if identity in context.setdefault("planned_receipts", {}):
            raise ValueError("Fixture must not rewrite an already registered original receipt")
        inputs = planned["inputs"]
    receipt = validate_phase_receipt({
        "schemaVersion": 1, "product": product, "component": component,
        "phase": phase, "target": target, "productVersion": version,
        "buildKey": planned["buildKey"] if planned is not None else compute_build_key(
            product=product, component=component, phase=phase, target=target, inputs=inputs,
        ),
        "inputs": inputs,
        "outputs": sorted(outputs, key=lambda item: item["relativePath"]),
        "producer": dict(context["producer"]),
        "trustDomain": "development", "result": "success",
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    write_canonical_json(path, receipt)
    if planned is not None:
        context["planned_receipts"][identity] = receipt
        context.setdefault("receipt_paths", {})[identity] = path
    return receipt
