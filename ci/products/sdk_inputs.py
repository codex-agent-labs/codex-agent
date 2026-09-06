"""Stage exact, authenticated SDK inputs once for independent package consumers.

This is transport, not a product or a release admission. The caller must select
the request/trust roots from its authorized plan and bind the emitted inventory
through receipt-qualified transport; a self-supplied inventory is not trust.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile
from typing import Any

from .contract_attestation import CONTRACT_EXECUTION_CLOSURE_DIRECTORY
from .inventory import (
    _open_regular_file,
    _stat_identity,
    canonical_json_bytes,
    publish_regular_tree,
    regular_file_inventory,
    require_relative_path,
    sha256_bytes,
    snapshot_regular_tree,
)
from .sdk_compatibility import load_sdk_compatibility_request, produce_sdk_compatibility
from .signatures import load_keyring, public_key_path


REQUEST_NAME = "sdk-compatibility-request.json"
COMPATIBILITY_NAME = "sdk-compatibility.json"
INVENTORY_NAME = "sdk-inputs-inventory.json"
_FILE_LIMIT = 512 * 1024 * 1024


def _copy_file(source: Path, destination: Path, *, max_bytes: int | None = None) -> None:
    """Bounded regular-file snapshot; never follow a source symlink or load a ZIP into RAM."""
    descriptor, before = _open_regular_file(source, "SDK input", reject_symlink_parents=True)
    try:
        if not 0 < before.st_size <= (_FILE_LIMIT if max_bytes is None else max_bytes):
            raise ValueError(f"SDK input size is invalid: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        remaining = before.st_size
        with os.fdopen(descriptor, "rb", closefd=False) as incoming, destination.open("xb") as outgoing:
            while remaining:
                chunk = incoming.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                outgoing.write(chunk)
                remaining -= len(chunk)
            if remaining or incoming.read(1) or _stat_identity(before) != _stat_identity(os.fstat(descriptor)):
                raise ValueError(f"SDK input changed during snapshot: {source}")
    finally:
        os.close(descriptor)


def stage_sdk_inputs(request: Path, output: Path, *, request_directory: Path | None = None) -> dict[str, Any]:
    """Authenticate a private snapshot, then publish without rewriting any evidence.

    Only the request's path strings are relocated. Original receipts, payloads,
    external attestations, signatures and public keys remain byte-identical.
    No private keys or unrelated source-directory files are transported.
    """
    arguments = load_sdk_compatibility_request(Path(request), request_directory=request_directory)
    with tempfile.TemporaryDirectory(prefix="sdk-inputs-") as temporary:
        root = Path(temporary).resolve() / "handoff"
        root.mkdir()

        def stage(value: Any, relative: Path) -> Any:
            if isinstance(value, Path):
                name = require_relative_path(value.name, "SDK input basename")
                destination = relative / name
                _copy_file(value, root / destination)
                return destination.as_posix()
            if isinstance(value, dict):
                return {key: stage(member, relative / key) for key, member in sorted(value.items())}
            return value

        relocated = {"schemaVersion": 1}
        for key, value in arguments.items():
            if value is None or key.endswith("_keys_directory"):
                continue
            head, *tail = key.split("_")
            field = head + "".join(part.title() for part in tail)
            relocated[field] = stage(value, Path("inputs") / field)

        # Contract authentication requires the complete original raw execution
        # closure beside its attestation, not just the attestation's digest.
        closure = CONTRACT_EXECUTION_CLOSURE_DIRECTORY
        snapshot_regular_tree(
            arguments["contract_attestation"].parent / closure,
            (root / relocated["contractAttestation"]).parent / closure,
        )
        for product in ("contract", "runtime"):
            directory = arguments[f"{product}_keys_directory"]
            if directory is None:
                continue
            keyring_path = root / relocated[f"{product}Keyring"]
            keyring = load_keyring(keyring_path, directory)
            relative = Path("inputs") / f"{product}KeysDirectory"
            (root / relative).mkdir()
            records = ([keyring["activeKey"]] if keyring["activeKey"] else []) + keyring["retiredKeys"]
            for record in records:
                source = public_key_path(directory, record["keyId"])
                _copy_file(source, root / relative / source.name)
            relocated[f"{product}KeysDirectory"] = relative.as_posix()

        staged_request = root / REQUEST_NAME
        staged_request.write_bytes(canonical_json_bytes(relocated))
        staged_arguments = load_sdk_compatibility_request(staged_request)
        produce_sdk_compatibility(output=root / COMPATIBILITY_NAME, **staged_arguments)
        inventory = {"schemaVersion": 1, "kind": "sdk-inputs", "files": regular_file_inventory(root)}
        inventory_bytes = canonical_json_bytes(inventory)
        (root / INVENTORY_NAME).write_bytes(inventory_bytes)
        publish_regular_tree(root, Path(output))
    return {"inventorySha256": sha256_bytes(inventory_bytes), "inventory": inventory}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args(argv)
    try:
        stage_sdk_inputs(Path(arguments.request), Path(arguments.output))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
