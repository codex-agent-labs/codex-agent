"""Run the fixed imported Core consumer producer; never finalize or admit it.

The outer controller owns election, original receipts, source/host authority and
full original replay. Retained requests and successful task reports are evidence,
not admission. All compiler caches/toolchains must already be provisioned.
"""

from collections.abc import Mapping
from pathlib import Path
import subprocess
import sys
import tempfile
import time

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from native_wrappers import host_classifier
from product_reuse import (
    _prepare_destination, _runtime_worker_checkout, _runtime_worker_command,
    _runtime_worker_environment,
)
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    require_exact_keys, require_integer, require_sha256, sha256_file, write_canonical_json,
)
from products.receipt import validate_producer, verify_output_manifest_identity
from products.registry import PHASE_INSTANCE_IDS, SDK_FACADE_TARGETS, PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS
from products.sdk_facade_inputs import OUTPUT_KIND, OUTPUT_PATH, _request, _sources
from products.sdk_facade_source import capture_facade_validation_sources
from products.sdk_facade_validation import _FILES, _inventory, validate_facade_validation_content
from products.sdk_package import _require_capability_output_separate
from products.sdk_validation_inputs import _request_inventory
from products.signing_isolation import require_no_signing_secret
from runtime_native_phase import _HOSTS
from sdk_phase import route


_LIMIT = 16 * 1024 * 1024


def _read(path):
    return read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True)


def execute(plan: Mapping, *, producer: Mapping, repository_root: Path,
            destination: Path, facade_request: Path, environ: Mapping[str, str]) -> dict:
    """Retain actual fixed-command outputs, with no receipt or hosted proof."""
    require_no_signing_secret(environ)
    selected = require_exact_keys(plan, PHASE_PLAN_KEYS, "Core validation phase plan")
    target = selected["target"]
    if (require_integer(selected["schemaVersion"], "Core validation schema", 1) != 1
            or type(target) is not str or target not in SDK_FACADE_TARGETS
            or tuple(selected[key] for key in ("product", "component", "phase")) !=
            ("sdk", "sdk-core", "validation")
            or PhaseInstanceId("sdk", "sdk-core", "validation", target) not in PHASE_INSTANCE_IDS
            or type(selected["inputs"]) is not dict):
        raise ValueError("Unsupported Core validation phase identity")
    require_sha256(selected["buildKey"], "Core validation build key")
    current = validate_producer(producer, "Core validation producer")
    selected_bytes, producer_bytes = canonical_json_bytes(plan), canonical_json_bytes(producer)
    root = Path(repository_root).resolve(strict=True)
    request = Path(facade_request).absolute()
    if request.resolve(strict=True) != request:
        raise ValueError("Core validation request must be normalized and non-symbolic")
    value, request_bytes = _request(request)
    if value["target"] != target or Path(value["repository"]) != root:
        raise ValueError("Core validation request differs from the elected target or repository")
    topology = route(selected)
    actual_host = host_classifier()
    if actual_host not in _HOSTS or _HOSTS[actual_host][1:] != (topology["runnerOs"], topology["runnerArch"]):
        raise ValueError("Core validation requires its actual elected host")

    _, trees, files = _sources(value)
    tree_before = {name: _inventory(path, allow_empty=True) for name, path in trees.items()}
    file_before = {name: _read(path) for name, path in files.items()}
    compatibility_before = _request_inventory(Path(value["compatibilityRequest"]))
    destination = Path(destination).absolute()
    stage = root / f"build/product-stage/sdk/sdk-core/validation/{target}"
    work = root / f"build/imported-sdk-facade-validation/{current['tree']}/{target}"
    sources = [request, *trees.values(), *files.values(), *compatibility_before]
    outputs = (destination, stage, work)
    for index, output in enumerate(outputs):
        _require_capability_output_separate(output, sources)
        if any(output == other or output in other.parents or other in output.parents
               for other in outputs[index + 1:]):
            raise ValueError("Core validation task-owned outputs overlap")
        if output.resolve(strict=False) != output or root not in output.parents:
            raise ValueError("Core validation output must be normalized inside the repository")
        if output.exists() or output.is_symlink():
            raise ValueError("Core validation requires fresh diagnostic and task-owned outputs")

    def originals_unchanged():
        require_no_signing_secret(environ)
        if (canonical_json_bytes(plan) != selected_bytes or canonical_json_bytes(producer) != producer_bytes
                or _read(request) != request_bytes
                or any(_inventory(path, allow_empty=True) != tree_before[name] for name, path in trees.items())
                or any(_read(path) != file_before[name] for name, path in files.items())
                or _request_inventory(Path(value["compatibilityRequest"])) != compatibility_before):
            raise ValueError("Core validation original input changed during execution")

    originals_unchanged()
    environment, wrapper = _runtime_worker_environment(root, current, destination, environ)
    destination = _prepare_destination(destination, root)
    retained_request = destination / "facade-request.json"
    with retained_request.open("xb") as stream:
        stream.write(request_bytes)
    source = destination / "source"
    with tempfile.TemporaryDirectory(prefix="sdk-facade-worker-source-") as temporary:
        private_source = Path(temporary).resolve() / "source"
        source_record = capture_facade_validation_sources(root, current["commit"], private_source)
        if source_record["tree"] != current["tree"] or _inventory(private_source) != source_record["files"]:
            raise ValueError("Core validation captured source differs from its producer tree or inventory")
        publish_regular_tree(private_source, source)
        if _inventory(private_source) != source_record["files"] or _inventory(source) != source_record["files"]:
            raise ValueError("Core validation source changed during retention")
    source_before = _inventory(source)
    fields = {
        "codexAgent.product": "sdk", "codexAgent.component": "sdk-core",
        "codexAgent.phase": "validation", "codexAgent.target": target,
        "codexAgent.sdkVersion": value["sdkVersion"],
        "codexAgent.candidateCommit": current["commit"], "codexAgent.candidateTree": current["tree"],
        "codexAgent.sdkFacadeValidationRequest": str(retained_request),
    }

    def unchanged():
        originals_unchanged()
        _runtime_worker_checkout(root, current)
        if _read(retained_request) != request_bytes:
            raise ValueError("Core validation retained request changed during execution")
        if _inventory(source) != source_before:
            raise ValueError("Core validation retained source changed during execution")
        bytecode = destination / "python-bytecode"
        if bytecode.exists() or bytecode.is_symlink():
            raise ValueError("Core validation private bytecode namespace was modified")

    command = _runtime_worker_command(wrapper, fields, environment, build_directory=".")
    if command.count("ciProductPhase") != 1:
        raise ValueError("Core validation requires the fixed phase task")
    unchanged()
    if any(path.exists() or path.is_symlink() for path in (stage, work)):
        raise ValueError("Core validation output appeared before execution")
    started = time.monotonic_ns()
    return_code, launch_error = None, None
    try:
        with (destination / "gradle.log").open("xb") as log:
            process = subprocess.run(command, cwd=root, env=environment, stdout=log,
                                     stderr=subprocess.STDOUT, check=False)
            return_code = process.returncode
    except OSError as error:
        launch_error = str(error)
        raise
    finally:
        write_canonical_json(destination / "execution.json", {
            "schemaVersion": 1, "producer": dict(current), "buildKey": selected["buildKey"],
            "command": command, "returnCode": return_code, "launchError": launch_error,
            "elapsedNs": time.monotonic_ns() - started,
        })
        unchanged()
    if return_code != 0:
        raise ValueError(f"Core validation failed with exit code {return_code}; see {destination / 'gradle.log'}")

    manifest = verify_output_manifest_identity(stage, "sdk", "sdk-core", "validation", target, value["sdkVersion"])
    if (len(manifest["outputs"]) != 1 or manifest["outputs"][0]["kind"] != OUTPUT_KIND
            or manifest["outputs"][0]["relativePath"] != OUTPUT_PATH):
        raise ValueError("Core validation canonical output is missing or ambiguous")
    content = validate_facade_validation_content(load_canonical_json_bytes(_read(stage / OUTPUT_PATH)))
    if content["target"] != target or content["sdkVersion"] != value["sdkVersion"]:
        raise ValueError("Core validation content differs from its elected identity")
    evidence = work / "execution"
    if {row["relativePath"] for row in _inventory(evidence, allow_empty=True)} != _FILES:
        raise ValueError("Core validation raw execution evidence is incomplete")
    for name in ("inputs", "consumer"):
        _inventory(work / name, allow_empty=True)
    consumer_inputs = work / "consumer-inputs"
    captured_inputs = _inventory(consumer_inputs, allow_empty=True)
    expected_names = {row["relativePath"] for row in
                      _inventory(source / "gradle/release/sdk-facade-consumer-template")}
    expected_names.update({"local.properties", ".codex-consumer-task-outcomes.init.gradle.kts"})
    if {row["relativePath"] for row in captured_inputs} != expected_names:
        raise ValueError("Core validation consumer input capture is incomplete")
    if any(sha256_file(work / "consumer" / row["relativePath"]) != row["sha256"] for row in captured_inputs):
        raise ValueError("Core validation consumer inputs changed after their capture")
    for name in ("inputs/inputs.json", "inputs/maven-inventory.json", "publication-metadata.json", "report.json"):
        if not _read(work / name):
            raise ValueError("Core validation retained input or report is empty")
    if _read(work / "report.json") != _read(evidence / "report.json"):
        raise ValueError("Core validation retained reports differ")
    inventories = {"stage": _inventory(stage), "work": _inventory(work, allow_empty=True),
                   "diagnostics": _inventory(destination, allow_empty=True)}
    unchanged()
    if any(_inventory(path, allow_empty=name != "stage") != inventories[name] for name, path in
           (("stage", stage), ("work", work), ("diagnostics", destination))):
        raise ValueError("Core validation output changed during verification")
    return {"stage": stage, "diagnostics": destination, "outputInventory": inventories["stage"],
            "work": work, "workInventory": inventories["work"], "request": retained_request,
            "source": source, "consumerInputs": consumer_inputs,
            "inputs": work / "inputs", "execution": evidence, "consumer": work / "consumer",
            "report": work / "report.json", "publicationMetadata": work / "publication-metadata.json"}
