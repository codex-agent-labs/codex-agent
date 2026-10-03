"""External original K/R evidence transport; never a product or trust authority."""

from pathlib import Path
import argparse
import tempfile

from .contract_attestation import CONTRACT_EXECUTION_CLOSURE_DIRECTORY
from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, require_relative_path, snapshot_regular_tree,
    regular_file_inventory,
)
from .reuse import _native_comparison_provider, _native_comparison_records
from .sdk_inputs import _copy_file
from .signatures import load_keyring, public_key_path


REQUEST_NAME = "native-runtime-evidence.json"


def load_native_runtime_evidence(root: Path) -> list[dict]:
    records = load_canonical_json_bytes(read_regular_file_bytes(
        root / REQUEST_NAME, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
    decoded = _native_comparison_records(root, records)
    expected = {REQUEST_NAME}

    def tree(source):
        path = Path(source)
        expected.update((path / item["relativePath"]).relative_to(root).as_posix()
                        for item in regular_file_inventory(path))

    for contract, runtime in decoded.values():
        for value in (contract, runtime):
            for field in ("attestation", "attestationSignature", "publicKey", "keyring", "phaseReceipt", "payload"):
                if value.get(field) is not None:
                    expected.add(Path(value[field]).relative_to(root).as_posix())
            if value.get("keysDirectory") is not None:
                keys = Path(value["keysDirectory"])
                keyring = load_keyring(Path(value["keyring"]), keys)
                for key in ([keyring["activeKey"]] if keyring["activeKey"] else []) + keyring["retiredKeys"]:
                    expected.add(public_key_path(keys, key["keyId"]).relative_to(root).as_posix())
        tree(contract["stageRoot"])
        tree(Path(contract["attestation"]).parent / CONTRACT_EXECUTION_CLOSURE_DIRECTORY)
        for phase in ("package", "validation"):
            tree(Path(runtime["stageRoot"]) / runtime["target"] / phase)
        expected.update(Path(path).relative_to(root).as_posix() for path in runtime["phaseReceipts"].values())
    if expected != {item["relativePath"] for item in regular_file_inventory(root)}:
        raise ValueError("Native Runtime handoff contains missing or unexpected files")
    return records


def stage_native_runtime_evidence(records, source_root: Path, destination: Path, *,
                                  keyring: Path | None = None, keys_directory: Path | None = None) -> list[dict]:
    """Capture declared original bytes, verify the capture, then publish once.

    Path relocation is transport only. Original receipts and attestations are
    never rewritten, and no private signing key is copied. Reusing an existing
    handoff should rebase its records, not call this producer again.
    """
    decoded = _native_comparison_records(source_root, records)
    destination = Path(destination).absolute()
    for contract, runtime in decoded.values():
        for source in (Path(contract["stageRoot"]), Path(contract["attestation"]).parent,
                       Path(runtime["stageRoot"]), Path(runtime["attestation"]).parent):
            if destination == source or source in destination.parents or destination in source.parents:
                raise ValueError("Native evidence destination overlaps original inputs")
    with tempfile.TemporaryDirectory(prefix="native-runtime-inputs-") as temporary:
        root = Path(temporary).resolve() / "handoff"
        root.mkdir()
        relocated = []
        contracts = {}
        for digest, (contract, runtime) in decoded.items():
            if contract["expectedTrustDomain"] == "release":
                if keyring is None or keys_directory is None:
                    raise ValueError("Release native handoff requires a caller-pinned product keyring")
                pinned = {"keyring": str(keyring), "keysDirectory": str(keys_directory)}
                contract, runtime = {**contract, **pinned}, {**runtime, **pinned}
            prefix = Path("originals") / digest.removeprefix("sha256:")

            def file(value, relative):
                if value is None:
                    return None
                source = Path(value)
                path = relative / require_relative_path(source.name, "Native evidence basename")
                _copy_file(source, root / path, max_bytes=1024 * 1024 * 1024)
                return path.as_posix()

            def directory(value, relative):
                snapshot_regular_tree(Path(value), root / relative)
                return relative.as_posix()

            def trust(value, relative):
                result = {name: file(value[name], relative / name) for name in
                          ("attestation", "attestationSignature", "publicKey", "keyring")}
                result["keysDirectory"] = None
                if value["keysDirectory"] is not None:
                    keys = Path(value["keysDirectory"])
                    keyring = load_keyring(root / result["keyring"], keys)
                    path = relative / "keysDirectory"
                    (root / path).mkdir(parents=True)
                    for key in ([keyring["activeKey"]] if keyring["activeKey"] else []) + keyring["retiredKeys"]:
                        _copy_file(public_key_path(keys, key["keyId"]), root / path / f"{key['keyId']}.pub")
                    result["keysDirectory"] = path.as_posix()
                return result

            kroot, rroot = prefix / "contract", prefix / "runtime"
            contract_key = canonical_json_bytes(contract)
            if contract_key not in contracts:
                captured_contract = {
                    **trust(contract, kroot),
                    "stageRoot": directory(contract["stageRoot"], kroot / "stage"),
                    "phaseReceipt": file(contract["phaseReceipt"], kroot / "receipt"),
                    "expectedTrustDomain": contract["expectedTrustDomain"],
                }
                closure = CONTRACT_EXECUTION_CLOSURE_DIRECTORY
                directory(Path(contract["attestation"]).parent / closure,
                          Path(captured_contract["attestation"]).parent / closure)
                contracts[contract_key] = captured_contract
            captured_contract = contracts[contract_key]
            stage = rroot / "stages"
            for phase in ("package", "validation"):
                directory(Path(runtime["stageRoot"]) / runtime["target"] / phase,
                          stage / runtime["target"] / phase)
            captured_runtime = {
                **trust(runtime, rroot), "target": runtime["target"], "stageRoot": stage.as_posix(),
                "payload": file(runtime["payload"], rroot / "payload"),
                "phaseReceipts": {phase: file(path, rroot / "receipts" / phase)
                                  for phase, path in runtime["phaseReceipts"].items()},
            }
            relocated.append({"receiptSha256": digest, "contractEvidence": captured_contract,
                              "runtimeEvidence": captured_runtime})
        provider = _native_comparison_provider(root, relocated, keyring=keyring, keys_directory=keys_directory)
        for record in relocated:
            # This authenticates complete original K/R content. Indexed-object
            # admission separately checks the selected original carrier object.
            provider({"receiptSha256": record["receiptSha256"],
                      "target": record["runtimeEvidence"]["target"]}, None).output_inventory(
                record["receiptSha256"], load_canonical_json_bytes(read_regular_file_bytes(
                    root / record["runtimeEvidence"]["phaseReceipts"]["validation"],
                    max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))["outputs"])
        (root / REQUEST_NAME).write_bytes(canonical_json_bytes(relocated))
        publish_regular_tree(root, destination)
    return relocated


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--keyring", type=Path)
    parser.add_argument("--keys-directory", type=Path)
    args = parser.parse_args(argv)
    try:
        records = load_canonical_json_bytes(read_regular_file_bytes(
            args.request, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
        stage_native_runtime_evidence(records, args.source_root, args.output,
                                      keyring=args.keyring, keys_directory=args.keys_directory)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
