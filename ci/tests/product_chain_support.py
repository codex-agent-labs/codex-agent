"""S808 fixture identities, never evidence of a real compiler or hosted runner."""

from pathlib import Path
from typing import Any
import zipfile

from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, sha256_bytes, sha256_file,
    write_canonical_json,
)
from ci.products.receipt import compute_build_key, output_inventory_digest, validate_phase_receipt


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
) -> dict[str, Any]:
    marker = f"S808 synthetic input:{product}:{component}:{phase}:{target}".encode()
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
    receipt = validate_phase_receipt({
        "schemaVersion": 1, "product": product, "component": component,
        "phase": phase, "target": target, "productVersion": version,
        "buildKey": compute_build_key(
            product=product, component=component, phase=phase, target=target, inputs=inputs,
        ),
        "inputs": inputs,
        "outputs": sorted(outputs, key=lambda item: item["relativePath"]),
        "producer": dict(context["producer"]),
        "trustDomain": "development", "result": "success",
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    write_canonical_json(path, receipt)
    return receipt
