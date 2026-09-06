"""Receipt-bound adapter comparison content from the original signed K/R closure."""

from pathlib import Path
import tempfile
from typing import Any

from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, load_json_bytes, read_regular_file_bytes,
    regular_file_inventory, require_array, require_exact_keys, require_object, require_relative_path,
    require_sha256, sha256_bytes, snapshot_regular_tree,
)
from .receipt import validate_phase_receipt, verify_output_manifest_identity
from .runtime_adapter_validation import _verify_adapter_host_snapshot
from .runtime_evidence import JVM_RUNTIME_RUNNER_ARCHIVE, NODE_RUNTIME_RUNNER_ARCHIVE, NODE_WASM_RUNTIME_RUNNER_ARCHIVE


_VERIFIED = object()
_IDENTITY = ("product", "component", "phase", "target", "productVersion", "buildKey")
_SOURCE = "codex-agent-runtime-desktop/codex-app-server-distributions.json"
_FILES = {
    "aggregate_metadata_receipt", "aggregate_attestation", "aggregate_attestation_signature", "aggregate_public_key",
    "contract_payload", "contract_metadata_receipt", "contract_attestation", "contract_attestation_signature",
    "contract_public_key",
}
_MAPS = {"variant_bundles", "variant_attestations", "variant_attestation_signatures", "variant_public_keys",
         "variant_validation_evidence", "adapter_evidence"}
_NESTED = {"variant_phase_receipts", "adapter_report_files"}
_TRUST = {f"{product}_{suffix}" for product in ("contract", "aggregate", "variant")
          for suffix in ("keyring", "keys_directory")}
_RECORD_PATHS = {"aggregateManifest": "aggregate_manifest", "adapterPackageStage": "adapter_package_stage",
                 "nativePackageStage": "native_package_stage", "validationStage": "validation_stage",
                 "distributionManifest": "distribution_manifest"}


def map_adapter_comparison_record(record, path):
    """Map declared filesystem paths only; never transform content or identity."""
    record = require_exact_keys(record, {"receiptSha256", "component", "target", "aggregateInputs", *_RECORD_PATHS},
                                "adapter comparison record")
    require_sha256(record["receiptSha256"], "adapter comparison receipt")
    from .aggregate import RUNTIME_ADAPTERS, RUNTIME_EVIDENCE_TARGETS
    if record["component"] not in RUNTIME_ADAPTERS or record["target"] not in RUNTIME_EVIDENCE_TARGETS:
        raise ValueError("Adapter comparison component/target mismatch")
    inputs = require_object(record["aggregateInputs"], "adapter aggregate inputs")
    required = _FILES | _MAPS | _NESTED | {"adapter_receipts", "runtime_maven_files", "required_trust_domain"}
    if not required <= inputs.keys() or inputs.keys() - required - _TRUST:
        raise ValueError("Adapter comparison requires exact aggregate input fields")
    if inputs["required_trust_domain"] not in {"development", "release"}:
        raise ValueError("Adapter comparison trust domain is invalid")
    mapped = {name: path(inputs[name]) for name in _FILES}
    for name in _MAPS:
        mapped[name] = {key: path(value) for key, value in require_object(inputs[name], name).items()}
    for name in _NESTED:
        mapped[name] = {key: {part: path(value) for part, value in require_object(member, name).items()}
                        for key, member in require_object(inputs[name], name).items()}
    mapped["adapter_receipts"] = [{**require_exact_keys(member, {"component", "phase", "target", "receipt"},
                                                       "adapter receipt reference"), "receipt": path(member["receipt"])}
                                  for member in require_array(inputs["adapter_receipts"], "adapter receipts")]
    mapped["runtime_maven_files"] = [{**require_object(member, "Runtime Maven reference"), "file": path(member["file"])}
                                     for member in require_array(inputs["runtime_maven_files"], "Runtime Maven files")]
    mapped["required_trust_domain"] = inputs["required_trust_domain"]
    mapped.update({name: None if inputs[name] is None else path(inputs[name]) for name in _TRUST if name in inputs})
    return {**record, "aggregateInputs": mapped, **{name: path(record[name]) for name in _RECORD_PATHS}}


def decode_adapter_comparison_records(root: Path, records) -> dict[str, dict[str, Any]]:
    result = {}
    for record in require_array(records, "adapter comparison records"):
        mapped = map_adapter_comparison_record(record, lambda value: root / require_relative_path(value, "adapter evidence path"))
        digest = mapped["receiptSha256"]
        if digest in result:
            raise ValueError("Duplicate adapter comparison receipt")
        result[digest] = {"component": mapped["component"], "target": mapped["target"],
                          "aggregate_inputs": mapped["aggregateInputs"],
                          **{dest: mapped[src] for src, dest in _RECORD_PATHS.items()}}
    if list(result) != sorted(result):
        raise ValueError("Adapter comparison records must be sorted by original receipt")
    return result


def rebase_adapter_comparison_records(records, source_root: Path, destination_root: Path):
    decode_adapter_comparison_records(source_root, records)
    return [map_adapter_comparison_record(record, lambda value:
            (source_root / require_relative_path(value, "adapter evidence path")).relative_to(destination_root).as_posix())
            for record in records]


def adapter_comparison_provider(root: Path, records, *, keyring=None, keys_directory=None):
    originals = decode_adapter_comparison_records(root, records)
    if (keyring is None) != (keys_directory is None):
        raise ValueError("Adapter release comparison requires both caller-pinned trust paths")

    def verify(entry, _verified_object):
        arguments = originals.get(entry["receiptSha256"])
        if arguments is None:
            raise ValueError("Adapter comparison lacks original signed K/R evidence")
        if (entry["component"], entry["target"]) != (arguments["component"], arguments["target"]):
            raise ValueError("Adapter comparison differs from original component/host")
        inputs = arguments["aggregate_inputs"]
        if inputs["required_trust_domain"] == "release":
            if keyring is None:
                raise ValueError("Release adapter comparison requires caller-pinned product keys")
            inputs = {**inputs, **{f"{product}_{suffix}": Path(value)
                      for product in ("contract", "aggregate", "variant")
                      for suffix, value in (("keyring", keyring), ("keys_directory", keys_directory))}}
        proof = verify_runtime_adapter_projection(**{**arguments, "aggregate_inputs": inputs})
        path = next(member["receipt"] for member in inputs["adapter_receipts"] if
                    (member["component"], member["phase"], member["target"]) ==
                    (entry["component"], "validation", entry["target"]))
        receipt = _receipt(path)
        proof.output_inventory(entry["receiptSha256"], receipt["outputs"], identity=receipt)
        return proof

    return verify if originals else None


class VerifiedAdapterRuntimeProjection:
    """Comparison-only proof bound to one byte-identical original validation receipt."""

    __slots__ = ("_receipt", "_content", "_verified")

    def __init__(self, receipt: bytes, content: bytes, verified: object):
        if verified is not _VERIFIED:
            raise TypeError("Adapter projection requires original signed K/R verification")
        self._receipt, self._content, self._verified = receipt, content, verified

    def output_inventory(self, receipt_sha256: str, outputs: list[dict[str, Any]], *,
                         identity: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        receipt = load_canonical_json_bytes(self._receipt)
        if (self._verified is not _VERIFIED or receipt_sha256 != sha256_bytes(self._receipt)
                or outputs != receipt["outputs"] or identity is None
                or any(identity.get(field) != receipt[field] for field in _IDENTITY)):
            raise ValueError("Adapter comparison differs from its exact original receipt/identity/outputs")
        return [{"kind": "runtime-adapter-validation-content",
                 "relativePath": "outputs/runtime-adapter-validation-content.json",
                 "bytes": len(self._content), "sha256": sha256_bytes(self._content)}]


def verify_runtime_adapter_projection(
    component: str, target: str, *, aggregate_manifest: Path, aggregate_inputs: dict[str, Any],
    adapter_package_stage: Path, native_package_stage: Path, validation_stage: Path,
    distribution_manifest: Path,
) -> VerifiedAdapterRuntimeProjection:
    """Authenticate and interpret the same private originals, never a supplied digest."""
    from .aggregate import RUNTIME_ADAPTERS, RUNTIME_EVIDENCE_TARGETS, verify_runtime_aggregate_artifacts

    if component not in RUNTIME_ADAPTERS or target not in RUNTIME_EVIDENCE_TARGETS:
        raise ValueError("Adapter comparison requires one exact adapter and native host")
    required = _FILES | _MAPS | _NESTED | {"adapter_receipts", "runtime_maven_files", "required_trust_domain"}
    if type(aggregate_inputs) is not dict or not required <= set(aggregate_inputs) or set(aggregate_inputs) - required - _TRUST:
        raise ValueError("Adapter comparison requires the exact original aggregate input closure")
    with tempfile.TemporaryDirectory(prefix="runtime-adapter-content-") as temporary:
        root = Path(temporary).resolve()
        originals: dict[Path, tuple[Path, str]] = {}

        def capture(path: Path) -> Path:
            if not isinstance(path, Path):
                raise ValueError("Adapter original evidence paths must be explicit Paths")
            source = path.absolute()
            if source not in originals:
                contents = read_regular_file_bytes(source, max_bytes=1024 * 1024 * 1024, reject_symlink_parents=True)
                destination = root / "files" / str(len(originals)) / source.name
                destination.parent.mkdir(parents=True)
                destination.write_bytes(contents)
                originals[source] = destination, sha256_bytes(contents)
            return originals[source][0]

        inputs = {name: capture(aggregate_inputs[name]) for name in _FILES}
        # Contract attestation authenticates this original sibling tree as well as its JSON.
        from .contract_attestation import CONTRACT_EXECUTION_CLOSURE_DIRECTORY
        closure = aggregate_inputs["contract_attestation"].parent / CONTRACT_EXECUTION_CLOSURE_DIRECTORY
        closure_inventory = regular_file_inventory(closure, allow_empty=True)
        captured_closure = inputs["contract_attestation"].parent / CONTRACT_EXECUTION_CLOSURE_DIRECTORY
        snapshot_regular_tree(closure, captured_closure)
        if regular_file_inventory(captured_closure, allow_empty=True) != closure_inventory:
            raise ValueError("Adapter original Contract closure changed during capture")
        for name in _MAPS:
            inputs[name] = {key: capture(path) for key, path in require_object(aggregate_inputs[name], name).items()}
        for name in _NESTED:
            inputs[name] = {key: {part: capture(path) for part, path in require_object(value, name).items()}
                            for key, value in require_object(aggregate_inputs[name], name).items()}
        inputs["adapter_receipts"] = [{**require_exact_keys(record, {"component", "phase", "target", "receipt"},
                                                            "Adapter original receipt"),
                                       "receipt": capture(record["receipt"])}
                                      for record in require_array(aggregate_inputs["adapter_receipts"], "adapter_receipts")]
        inputs["runtime_maven_files"] = [{**require_object(record, "Runtime Maven file"), "file": capture(record["file"])}
                                          for record in require_array(aggregate_inputs["runtime_maven_files"], "runtime_maven_files")]
        inputs["required_trust_domain"] = aggregate_inputs["required_trust_domain"]
        for name in _TRUST:
            if aggregate_inputs.get(name) is not None:
                if name.endswith("keys_directory"):
                    destination = root / name
                    snapshot_regular_tree(aggregate_inputs[name], destination)
                    inputs[name] = destination
                else:
                    inputs[name] = capture(aggregate_inputs[name])
        manifest = capture(aggregate_manifest)
        distributions = capture(distribution_manifest)
        stages = {}
        stage_originals = {}
        for name, path in (("adapter", adapter_package_stage), ("native", native_package_stage),
                           ("validation", validation_stage)):
            stage_originals[name] = regular_file_inventory(path)
            stages[name] = root / name
            snapshot_regular_tree(path, stages[name])
            if regular_file_inventory(stages[name]) != stage_originals[name]:
                raise ValueError("Adapter original stage changed during capture")
        aggregate = verify_runtime_aggregate_artifacts(manifest, **inputs)
        receipt_paths = {(record["component"], record["phase"], record["target"]): record["receipt"]
                         for record in inputs["adapter_receipts"]}
        binary = _receipt(receipt_paths[(component, "binary", component)])
        package = _receipt(receipt_paths[(component, "package", component)])
        original = read_regular_file_bytes(receipt_paths[(component, "validation", target)], reject_symlink_parents=True)
        validation = validate_phase_receipt(load_canonical_json_bytes(original))
        native = _receipt(inputs["variant_phase_receipts"][target]["package"])
        for name, receipt in (("adapter", package), ("native", native), ("validation", validation)):
            stage = verify_output_manifest_identity(stages[name], *(receipt[field] for field in
                                                    ("product", "component", "phase", "target", "productVersion")))
            if stage["outputs"] != receipt["outputs"]:
                raise ValueError("Adapter original stage differs from its authenticated receipt")
        source = read_regular_file_bytes(distributions)
        if {"relativePath": _SOURCE, "bytes": len(source), "sha256": sha256_bytes(source)} not in validation["inputs"]["inventory"]:
            raise ValueError("Adapter original distribution manifest lacks its exact validation source inventory")
        evidence_target = RUNTIME_EVIDENCE_TARGETS[target]
        report_kind = "jvm-evidence" if component == "jvm" else "node-evidence"
        expected_report = inputs["adapter_report_files"][component][target]
        report = stages["validation"] / "outputs" / report_kind / expected_report.name
        if read_regular_file_bytes(report) != read_regular_file_bytes(expected_report):
            raise ValueError("Adapter staged report differs from its authenticated aggregate report")
        raw = load_json_bytes(read_regular_file_bytes(report))
        runner_name = {"jvm": JVM_RUNTIME_RUNNER_ARCHIVE, "node-js": NODE_RUNTIME_RUNNER_ARCHIVE,
                       "node-wasm": NODE_WASM_RUNTIME_RUNNER_ARCHIVE}[component]
        runner_path = f"outputs/validation-runner/{runner_name}"
        runner_output = _output(package, "validation-runner", runner_path)
        if runner_output != _output(binary, "validation-runner", runner_path):
            raise ValueError("Adapter package runner differs from its original binary output")
        classifier_path = f"outputs/app-server/{raw['classifierArchiveFileName']}"
        _output(native, "app-server", classifier_path)
        execution_path = f"outputs/execution/{report.stem}-execution.json"
        test_class = raw["testClass"]
        prefix = "nodeRuntime" if component == "node-js" else "nodeWasmRuntime"
        junit_name = (f"TEST-jvm-runtime-{evidence_target}.xml" if component == "jvm" else
                      f"TEST-{prefix}{evidence_target[0].upper() + evidence_target[1:]}Test.{test_class}.xml")
        junit_path = f"outputs/test-report/{junit_name}"
        expected_outputs = {f"outputs/{report_kind}/{report.name}": report_kind,
                            execution_path: "execution", junit_path: "test-report"}
        if {item["relativePath"]: item["kind"] for item in validation["outputs"]} != expected_outputs:
            raise ValueError("Adapter validation has missing or unprojected original outputs")
        host = _verify_adapter_host_snapshot(component, evidence_target, validation["producer"]["commit"],
            report=report, execution=stages["validation"] / execution_path,
            junit=stages["validation"] / junit_path, distribution_manifest=distributions,
            classifier=stages["native"] / classifier_path, runner=stages["adapter"] / runner_path)
        contract = binary["inputs"]["upstreamArtifacts"][0]["contractProjection"]
        content = canonical_json_bytes({"schemaVersion": 1, "component": component, "target": target,
            "contract": {key: contract[key] for key in ("contractDigest", "componentDigests")},
            "runtimeCompatibilityVersion": aggregate["runtimeCompatibilityVersion"],
            "adapterPackageOutputs": package["outputs"], "host": host})
        for source_path, (_, digest) in originals.items():
            if sha256_bytes(read_regular_file_bytes(source_path, max_bytes=1024 * 1024 * 1024,
                                                   reject_symlink_parents=True)) != digest:
                raise ValueError("Adapter original evidence changed during verification")
        if regular_file_inventory(closure, allow_empty=True) != closure_inventory:
            raise ValueError("Adapter original Contract closure changed during verification")
        for name, path in (("adapter", adapter_package_stage), ("native", native_package_stage),
                           ("validation", validation_stage)):
            if regular_file_inventory(path) != stage_originals[name]:
                raise ValueError("Adapter original stage changed during verification")
        return VerifiedAdapterRuntimeProjection(original, content, _VERIFIED)


def _receipt(path: Path) -> dict[str, Any]:
    return validate_phase_receipt(load_canonical_json_bytes(read_regular_file_bytes(path, reject_symlink_parents=True)))


def _output(receipt: dict[str, Any], kind: str, path: str) -> dict[str, Any]:
    matches = [item for item in receipt["outputs"] if item["kind"] == kind and item["relativePath"] == path]
    if len(matches) != 1:
        raise ValueError("Adapter input is not one exact original receipt output")
    return matches[0]
