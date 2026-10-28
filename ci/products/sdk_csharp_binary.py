"""Pure receipt and byte check for the reusable C# assembly stage."""

from pathlib import Path

from .inventory import read_regular_file_bytes, regular_file_inventory
from .receipt import validate_phase_receipt, verify_output_manifest_identity


FILES = frozenset({
    "CodexAgent.dll", "CodexAgent.pdb", "CodexAgent.xml", "CodexAgent.deps.json",
    "sdk-compatibility.json", "sdk-runtime-root.pub",
})


def verify_csharp_binary_stage(stage: Path, receipt: dict, compatibility_file: Path,
                               root_key: Path) -> dict:
    """Bind six binary outputs to one receipt and the exact embedded SDK policy."""
    value = validate_phase_receipt(receipt)
    if tuple(value[name] for name in ("product", "component", "phase", "target")) != (
            "sdk", "csharp", "binary", "desktop"):
        raise ValueError("C# binary stage has the wrong product identity")
    stage = Path(stage)
    before = regular_file_inventory(stage)
    manifest = verify_output_manifest_identity(stage, "sdk", "csharp", "binary", "desktop",
                                               value["productVersion"])
    expected = {f"outputs/csharp/{name}" for name in FILES}
    if (manifest["outputs"] != value["outputs"] or
            {item["relativePath"] for item in manifest["outputs"]} != expected or
            {item["kind"] for item in manifest["outputs"]} != {"csharp-binary"} or
            any(item["bytes"] == 0 for item in manifest["outputs"])):
        raise ValueError("C# binary stage has an unexpected output inventory")
    for name, original in (("sdk-compatibility.json", compatibility_file),
                           ("sdk-runtime-root.pub", root_key)):
        if read_regular_file_bytes(stage / "outputs/csharp" / name, reject_symlink_parents=True) != \
                read_regular_file_bytes(Path(original), reject_symlink_parents=True):
            raise ValueError("C# binary stage embeds a different SDK policy")
    if regular_file_inventory(stage) != before:
        raise ValueError("C# binary stage changed during verification")
    return manifest
