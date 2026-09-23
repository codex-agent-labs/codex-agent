"""Produce Runtime Maven release sidecars from an authenticated aggregate handoff.

The protected workflow must pin the original upload ID/digest and expected
metadata receipt/build key independently. This local caller does not mint that
transport authority or make candidate/publication workflows build-free.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.inventory import (
    publish_regular_tree, regular_file_inventory,
    require_sha256, snapshot_regular_tree,
)
from products.registry import PhaseInstanceId
from products.runtime_aggregate_handoff import verified_runtime_aggregate_handoff
from products.runtime_phase10_maven import produce_runtime_phase10_maven_sidecars
from products.sdk_protected_runtime import _original_carrier


_METADATA = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")


def produce_authenticated_runtime_maven_sidecars(
    protected_output: Path,
    destination: Path,
    *,
    expected_metadata_receipt_sha256: str,
    expected_build_key: str,
    keyring: Path,
    keys_directory: Path,
    pgp_public_key: Path,
    expected_pgp_key_sha256: str,
    signing_home: Path,
    signing_fingerprint: str,
    passphrase: str,
) -> dict:
    """Verify fresh/retained original release bytes before using the PGP key."""
    protected_output, destination = Path(protected_output), Path(destination)
    expected_metadata_receipt_sha256 = require_sha256(
        expected_metadata_receipt_sha256, "Original Runtime metadata receipt",
    )
    expected_build_key = require_sha256(expected_build_key, "Original Runtime aggregate build key")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime Maven sidecar destination already exists")
    resolved_output = destination.resolve(strict=False)
    resolved_original = protected_output.resolve(strict=True)
    for source in (protected_output, keyring, keys_directory, pgp_public_key, signing_home):
        resolved = Path(source).resolve(strict=True)
        if resolved_output == resolved or resolved_output in resolved.parents or resolved in resolved_output.parents:
            raise ValueError("Runtime Maven sidecar output overlaps an input")
        if source != protected_output and (resolved == resolved_original
                                           or resolved in resolved_original.parents
                                           or resolved_original in resolved.parents):
            raise ValueError("Runtime verifier/signing policy must be external to transported output")
    before = regular_file_inventory(protected_output, allow_empty=True)
    with tempfile.TemporaryDirectory(prefix="rt-p10-caller-") as temporary:
        private = Path(temporary).resolve()
        captured = private / "protected-output"
        snapshot_regular_tree(protected_output, captured, allow_empty=True)
        if regular_file_inventory(captured, allow_empty=True) != before:
            raise ValueError("Runtime protected output changed during capture")
        carrier = _original_carrier(captured, expected_metadata_receipt_sha256, expected_build_key)
        with verified_runtime_aggregate_handoff(
            carrier, keyring=keyring, keys_directory=keys_directory,
        ) as verified:
            original = verified["originalPhases"][_METADATA]
            manifest = Path(verified["indexInputs"]["manifest"])
            payload = Path(original["stage"]) / "outputs"
            if manifest.parent != payload:
                raise ValueError("Runtime Maven payload is not the selected original aggregate stage")
            sidecars = private / "sidecars"
            result = produce_runtime_phase10_maven_sidecars(
                payload, manifest, sidecars, pgp_public_key, expected_pgp_key_sha256,
                signing_home, signing_fingerprint, passphrase,
            )
        if regular_file_inventory(protected_output, allow_empty=True) != before or \
                regular_file_inventory(captured, allow_empty=True) != before:
            raise ValueError("Runtime protected output changed during signing")
        if regular_file_inventory(sidecars) != result["sidecarFiles"]:
            raise ValueError("Runtime signed sidecars changed before publication")
        publish_regular_tree(sidecars, destination)
        if regular_file_inventory(destination) != result["sidecarFiles"] or \
                regular_file_inventory(protected_output, allow_empty=True) != before:
            raise ValueError("Runtime original or sidecars changed during publication")
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sign original Runtime aggregate Maven files externally; read PGP passphrase from stdin.",
    )
    for name in ("protected-output", "destination", "expected-metadata-receipt-sha256",
                 "expected-build-key", "keyring", "keys-directory", "pgp-public-key",
                 "expected-pgp-key-sha256", "signing-home", "signing-fingerprint"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args(argv)
    result = produce_authenticated_runtime_maven_sidecars(
        Path(args.protected_output), Path(args.destination),
        expected_metadata_receipt_sha256=args.expected_metadata_receipt_sha256,
        expected_build_key=args.expected_build_key,
        keyring=Path(args.keyring), keys_directory=Path(args.keys_directory),
        pgp_public_key=Path(args.pgp_public_key), expected_pgp_key_sha256=args.expected_pgp_key_sha256,
        signing_home=Path(args.signing_home), signing_fingerprint=args.signing_fingerprint,
        passphrase=sys.stdin.read(),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
