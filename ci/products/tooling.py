"""External original-tooling attestation; never a fourth product or SDK receipt."""

from contextlib import contextmanager
from pathlib import Path
import tempfile

from ..impact import effective_pathspecs
from ..receipt import INPUT_NAMES, parse_validation_actions, validate_receipt
from .inventory import (
    git_inventory, load_canonical_json_bytes, load_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys, require_integer,
    require_sha256, run_git, sha256_bytes, snapshot_regular_tree, write_canonical_json,
)
from .receipt import validate_producer
from .signatures import (
    load_keyring, public_key_for_metadata, sign_manifest, validate_signing_metadata,
    verify_manifest_signature,
)


ATTESTATION = "release-tooling.attestation.json"
SIGNATURE = "release-tooling.attestation.sig"
JAR = "payload/gradle/build-logic/build/libs/codex-agent-release-tooling.jar"
_LIMIT = 16 * 1024 * 1024


def _json(path):
    # Original legacy JSON is deliberately not rewritten to canonical product JSON.
    return load_json_bytes(read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True))


def _verify_original(root: Path, repository: Path):
    plan_path = root / "plan.json"
    plan = _json(plan_path)
    lane = root / "lane"
    receipt = _json(lane / "lane-receipt.json")
    if type(plan) is not dict or require_integer(plan.get("schemaVersion"), "tooling plan schema", 1) != 1:
        raise ValueError("Unsupported original tooling plan")
    # Strict parsing above rejects duplicate keys; the existing full lane gate owns semantics.
    receipt = validate_receipt(lane / "lane-receipt.json", plan_path, lane, "contracts",
                               repository_root=repository)
    producer = validate_producer({
        "repository": receipt["repository"], "workflowPath": receipt["workflowPath"],
        "commit": receipt["validationCommit"], "tree": receipt["validationTree"],
        "event": receipt["event"], "runId": receipt["runId"],
        "runAttempt": receipt["runAttempt"], "pullRequest": receipt["pullRequest"],
    }, "original tooling producer")
    if str(run_git(repository, "rev-parse", f"{producer['commit']}^{{tree}}")).strip() != producer["tree"]:
        raise ValueError("Original tooling source commit/tree mismatch")
    if "build" not in parse_validation_actions(receipt["toolchain"]):
        raise ValueError("Original tooling receipt does not prove its build action")
    artifacts = [item for item in receipt["artifacts"] if item["kind"] == "release-tooling"]
    if len(artifacts) != 1 or artifacts[0]["relativePath"] != JAR or \
            require_integer(artifacts[0]["bytes"], "tooling JAR bytes", 1) < 1:
        raise ValueError("Expected exactly one original release-tooling artifact")
    if any(item["kind"] == "transport-provenance" for item in receipt["evidence"]):
        raise ValueError("Reissued transport receipt is not an original tooling producer")
    for category, filename in INPUT_NAMES.items():
        expected = git_inventory(repository, producer["commit"],
                                 effective_pathspecs(repository, "contracts", category)).encode("utf-8")
        if read_regular_file_bytes(lane / filename, reject_symlink_parents=True) != expected:
            raise ValueError(f"Original tooling {category} source inventory mismatch")
    inventory = regular_file_inventory(root, allow_empty=True)
    expected_paths = {"plan.json", *(f"inventories/contracts/{name}" for name in INPUT_NAMES.values()),
                      *(f"lane/{item['relativePath']}" for item in regular_file_inventory(lane, allow_empty=True))}
    if {item["relativePath"] for item in inventory} != expected_paths:
        raise ValueError("Original tooling closure has unexpected files")
    return receipt, inventory


def _value(root: Path, signing, repository: Path):
    _, inventory = _verify_original(root, repository)
    return {"schemaVersion": 1, "kind": "release-tooling-attestation",
            "planSha256": sha256_bytes(read_regular_file_bytes(root / "plan.json")),
            "laneReceiptSha256": sha256_bytes(read_regular_file_bytes(root / "lane/lane-receipt.json")),
            "files": inventory, "signing": signing}


def _verify_capture(root: Path, repository: Path, public_key: Path, required_trust_domain: str,
                    keyring: Path | None, keys_directory: Path | None):
    value = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(root / ATTESTATION)),
                               {"schemaVersion", "kind", "planSha256", "laneReceiptSha256", "files", "signing"},
                               "tooling attestation")
    if require_integer(value["schemaVersion"], "tooling attestation schema", 1) != 1 or \
            value["kind"] != "release-tooling-attestation":
        raise ValueError("Unsupported tooling attestation")
    for name in ("planSha256", "laneReceiptSha256"):
        require_sha256(value[name], f"tooling {name}")
    if required_trust_domain not in {"development", "release"}:
        raise ValueError("Expected tooling trust domain is invalid")
    signing = validate_signing_metadata(value["signing"], trust_domain=required_trust_domain)
    if required_trust_domain == "release":
        if keyring is None or keys_directory is None:
            raise ValueError("Release tooling requires caller-pinned release keys")
        trusted = public_key_for_metadata(signing, load_keyring(keyring, keys_directory), keys_directory,
                                          allow_retired=True)
        if read_regular_file_bytes(trusted, reject_symlink_parents=True) != read_regular_file_bytes(public_key):
            raise ValueError("Tooling public key differs from pinned release policy")
    elif keyring is not None or keys_directory is not None:
        raise ValueError("Development tooling rejects release keyring inputs")
    verify_manifest_signature(root / ATTESTATION, root / SIGNATURE, public_key, signing)
    # Authenticate before inspecting original executable/source inventories. Never execute the JAR here.
    original = root / "original"
    expected = _value(original, signing, repository)
    if value != expected:
        raise ValueError("Tooling attestation differs from exact original closure")
    actual_paths = {item["relativePath"] for item in regular_file_inventory(root, allow_empty=True)}
    if actual_paths != {ATTESTATION, SIGNATURE, *(f"original/{item['relativePath']}" for item in value["files"])}:
        raise ValueError("Tooling evidence object contains unexpected files")
    return original / "lane" / JAR


@contextmanager
def verified_tooling_capture(evidence: Path, repository: Path, public_key: Path, *,
                             required_trust_domain: str, keyring: Path | None = None,
                             keys_directory: Path | None = None):
    """Yield only an authenticated private JAR, invalid after this context exits.

    The repository is the invoking trusted policy/Git context, never selected by
    placement of an imported plan. This does not grant SDK/host receipt admission.
    """
    evidence, repository, public_key = Path(evidence), Path(repository), Path(public_key)
    before = regular_file_inventory(evidence, allow_empty=True)
    with tempfile.TemporaryDirectory(prefix="verified-tooling-") as temporary:
        root = Path(temporary).resolve()
        captured = root / "evidence"
        snapshot_regular_tree(evidence, captured, allow_empty=True)
        key = root / "pinned.pub"
        key.write_bytes(read_regular_file_bytes(public_key, max_bytes=_LIMIT, reject_symlink_parents=True))
        jar = _verify_capture(captured, repository, key, required_trust_domain, keyring, keys_directory)
        checked = regular_file_inventory(captured, allow_empty=True)
        yield jar
        if checked != regular_file_inventory(captured, allow_empty=True) or \
                before != regular_file_inventory(evidence, allow_empty=True):
            raise ValueError("Original or captured tooling evidence changed during use")


def build_development_tooling_attestation(plan: Path, lane: Path, repository: Path,
                                         signing_metadata, private_key: Path, public_key: Path,
                                         output: Path):
    """Local development only. Protected release-provenance signing is a later gate."""
    signing = validate_signing_metadata(signing_metadata, trust_domain="development")
    plan, lane, repository, output = map(Path, (plan, lane, repository, output))
    if any(left == right or left in right.parents or right in left.parents
           for source in (plan, lane) for left, right in
           ((source.absolute(), output.absolute()), (source.resolve(), output.resolve()))):
        raise ValueError("Tooling evidence output overlaps an original input")
    before = regular_file_inventory(lane, allow_empty=True)
    plan_bytes = read_regular_file_bytes(plan, max_bytes=_LIMIT, reject_symlink_parents=True)
    inventories = {name: read_regular_file_bytes(plan.parent / "inventories/contracts" / name,
                                               reject_symlink_parents=True)
                   for name in INPUT_NAMES.values()}
    with tempfile.TemporaryDirectory(prefix="development-tooling-") as temporary:
        prepared = Path(temporary).resolve() / "evidence"
        original = prepared / "original"
        (original / "inventories/contracts").mkdir(parents=True)
        (original / "plan.json").write_bytes(plan_bytes)
        for name, contents in inventories.items():
            (original / "inventories/contracts" / name).write_bytes(contents)
        snapshot_regular_tree(lane, original / "lane", allow_empty=True)
        value = _value(original, signing, repository)
        write_canonical_json(prepared / ATTESTATION, value)
        sign_manifest(prepared / ATTESTATION, private_key, signing)
        _verify_capture(prepared, repository, public_key, "development", None, None)
        if before != regular_file_inventory(lane, allow_empty=True) or plan_bytes != read_regular_file_bytes(plan) or \
                any(contents != read_regular_file_bytes(plan.parent / "inventories/contracts" / name,
                                                        reject_symlink_parents=True)
                    for name, contents in inventories.items()):
            raise ValueError("Original tooling input changed during development attestation")
        publish_regular_tree(prepared, output, allow_empty=True)
    return value
