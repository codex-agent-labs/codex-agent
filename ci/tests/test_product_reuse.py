from __future__ import annotations

import copy
from dataclasses import replace
import functools
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile

import ci.products.contract_projection as contract_projection
import ci.products.index as product_index
import ci.products.reuse as product_reuse
from ci.products.contract import build_contract_bundle, capture_contract_execution_evidence, validate_contract_package_stage
from ci.products.contract_attestation import build_contract_attestation, capture_contract_execution_closure
from ci.products.inventory import canonical_json_bytes, sha256_bytes, write_canonical_json
from ci.products.plan import (
    NOT_APPLICABLE_FLAGS_DIGEST,
    NOT_APPLICABLE_TOOLCHAIN_DIGEST,
    VerifiedRuntimeValidationProjection,
    _VERIFIED_RUNTIME_VALIDATION_PROJECTION,
    plan_phase,
    runtime_validation_dependencies,
)
from ci.products.receipt import output_inventory_digest, validate_phase_receipt, write_output_manifest
from ci.products.registry import (
    NATIVE_TARGETS,
    PhaseInstanceId,
    phase_instance_dependencies,
    required_contract_components,
)
from ci.products.restore import CacheObjectError, object_relative_path, store_local_object, validate_transport
from ci.products.runtime_flags import load_runtime_binary_flags
from ci.products.selection import classify_paths, phase_git_inventory
from ci.products.toolchain import PROFILE_SHAPES, PROFILE_TOOL_NAMES
from ci.products.reuse import (
    LocalCandidate,
    LocalCatalog,
    LookupSession,
    RemoteCatalog,
    ReuseLookupError,
    advance_reuse as _advance_reuse,
    plan_reuse_wave,
)
from ci.products.signatures import generate_development_key, sign_manifest
from ci.tests import test_contract_bundle as contract_fixture


DIGEST_A = sha256_bytes(b"a")
DIGEST_B = sha256_bytes(b"b")
VERSIONS = {
    "contract": "1.2.3",
    "runtime-compatibility": "2.3.0",
    "runtime-release": "2.3.4",
    "sdk": "3.4.5",
}
REPOSITORY = "owner/repository"
CHECKOUT = Path(__file__).resolve().parents[2]
RUNTIME_FLAGS_DIGESTS = {
    target: record.digest
    for target, record in load_runtime_binary_flags(
        CHECKOUT / "codex-agent-runtime-desktop/native/c-api/binary-flags.json"
    ).items()
}
def test_toolchain_profile(target: str) -> dict[str, object]:
    return {
        "schemaVersion": 2,
        "id": target,
        "producers": [
            {
                "role": role,
                "runner": {"os": os_name, "arch": arch},
                "tools": [
                    {"name": name, "identity": f"fixture-{target}-{role}-{name}"}
                    for name in PROFILE_TOOL_NAMES[(target, role)]
                ],
            }
            for role, os_name, arch in PROFILE_SHAPES[target]
        ],
    }


TEST_TOOLCHAIN_PROFILE_BYTES = {
    target: canonical_json_bytes(test_toolchain_profile(target))
    for target in NATIVE_TARGETS
}
TEST_TOOLCHAIN_PROFILE_DIGESTS = {
    target: sha256_bytes(contents)
    for target, contents in TEST_TOOLCHAIN_PROFILE_BYTES.items()
}
PULL_REQUEST = 31
COMMIT = "a" * 40
TREE = "b" * 40
CONTRACT_BINARY = PhaseInstanceId("contract", "contract", "binary", "common")
CONTRACT_PACKAGE = PhaseInstanceId("contract", "contract", "package", "common")
CONTRACT_VALIDATION = PhaseInstanceId("contract", "contract", "validation", "common")
CONTRACT_METADATA = PhaseInstanceId("contract", "contract", "metadata", "common")
RUNTIME_BINARY = PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64")
RUNTIME_PACKAGE = PhaseInstanceId("runtime", "linux-x64", "package", "linux-x64")
RUNTIME_VALIDATION = PhaseInstanceId("runtime", "linux-x64", "validation", "linux-x64")
RUNTIME_JVM = PhaseInstanceId("runtime", "jvm", "binary", "jvm")
PYTHON_PACKAGE = PhaseInstanceId("sdk", "python", "package", "desktop")
PYTHON_METADATA = PhaseInstanceId("sdk", "python", "metadata", "desktop")


def dependency_closure(instance: PhaseInstanceId) -> tuple[PhaseInstanceId, ...]:
    values: set[PhaseInstanceId] = set()

    def add(value: PhaseInstanceId) -> None:
        if value in values:
            return
        values.add(value)
        for dependency in phase_instance_dependencies(value):
            add(dependency)

    add(instance)
    return tuple(sorted(values))


def phase_inputs(instance: PhaseInstanceId) -> dict[str, object]:
    inventory = [{
        "relativePath": f"inputs/{instance.component}-{instance.phase}-{instance.target}.txt",
        "bytes": 1,
        "sha256": DIGEST_A,
    }]
    return {
        "inventory": inventory,
        "versions": VERSIONS,
        "toolchain_profile_digest": (
            TEST_TOOLCHAIN_PROFILE_DIGESTS[instance.component]
            if instance.product == "runtime"
            and instance.component in NATIVE_TARGETS
            and instance.phase == "binary"
            else NOT_APPLICABLE_TOOLCHAIN_DIGEST
        ),
        "flags_digest": (
            RUNTIME_FLAGS_DIGESTS[instance.component]
            if instance.product == "runtime"
            and instance.component in NATIVE_TARGETS
            and instance.phase == "binary"
            else NOT_APPLICABLE_FLAGS_DIGEST
        ),
    }


def all_inputs(instance: PhaseInstanceId) -> dict[PhaseInstanceId, dict[str, object]]:
    return {value: phase_inputs(value) for value in dependency_closure(instance)}


def test_runtime_projection_provider(instance: PhaseInstanceId, _envelopes) -> object:
    dependencies = runtime_validation_dependencies(instance)
    return VerifiedRuntimeValidationProjection(
        instance.component,
        tuple(dependency.target for dependency in dependencies),
        DIGEST_A,
        _VERIFIED_RUNTIME_VALIDATION_PROJECTION,
    )


def product_version(product: str) -> str:
    return VERSIONS["runtime-release"] if product == "runtime" else VERSIONS[product]


@functools.cache
def binary_stage_files(version: str, target_hash_salt: bytes = b"", execution_context: bytes = b"first") -> dict[str, bytes]:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve()
        raw, classes, results = contract_fixture.ContractBundleTest()._execution_projection_fixture(
            root / "raw", contract_version=version, target_hash_salt=target_hash_salt,
        )
        report = results / "TEST-Contract.xml"
        report.write_bytes(report.read_bytes().replace(b"first", execution_context))
        contract_fixture.ContractBundleTest()._bind_execution_fixture(raw, classes, results)
        stage = root / "stage"
        shutil.copytree(raw, stage / "outputs")
        capture_contract_execution_evidence(stage / "outputs", classes, results)
        write_output_manifest(stage, "contract", "contract", "binary", "common", version, {
            "maven": "outputs/maven", "evidence": "outputs/evidence",
            "inventory": "outputs/inventories", "contract-execution": "outputs/execution",
        })
        return {path.relative_to(stage).as_posix(): path.read_bytes() for path in stage.rglob("*") if path.is_file()}


@functools.cache
def verified_execution_fixture(receipt_bytes: bytes):
    receipt = json.loads(receipt_bytes)
    with tempfile.TemporaryDirectory() as temporary:
        stage = Path(temporary).resolve()
        for name, data in binary_stage_files(receipt["productVersion"]).items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return contract_projection.verify_contract_execution_projection(
            stage, receipt_bytes, expected_receipt_sha256=sha256_bytes(receipt_bytes),
        )


def advance_reuse(*args, **kwargs):
    # Real verified fixture proof for tests supplying retained receipts without transported objects.
    kwargs.setdefault("contract_execution_projection_provider", lambda envelope: verified_execution_fixture(envelope["receiptBytes"]))
    from ci.tests.test_product_plan import verified_native_projections, verified_sdk_projections
    kwargs.setdefault("native_runtime_projection_provider", lambda instance, envelopes, projection:
                      verified_native_projections(instance, [item["receipt"] for item in envelopes], projection))
    # Planner fixtures only, not authenticated SDK execution/host acceptance.
    kwargs.setdefault("sdk_validation_projection_provider", lambda instance, envelopes, package:
                      verified_sdk_projections(instance, [package["receipt"], *[item["receipt"] for item in envelopes]]))
    return _advance_reuse(*args, **kwargs)


def envelope_for_plan(
    plan: dict[str, object],
    *,
    trust_domain: str = "development",
    release_version: str | None = None,
) -> dict[str, object]:
    name = f"outputs/{plan['component']}-{plan['phase']}-{plan['target']}.bin"
    payload = str(plan["buildKey"]).encode()
    receipt = validate_phase_receipt({
        "schemaVersion": 1,
        "product": plan["product"],
        "component": plan["component"],
        "phase": plan["phase"],
        "target": plan["target"],
        "productVersion": release_version or product_version(str(plan["product"])),
        "buildKey": plan["buildKey"],
        "inputs": plan["inputs"],
        "outputs": json.loads(binary_stage_files(release_version or VERSIONS["contract"])["output-manifest.json"])["outputs"]
        if (plan["product"], plan["phase"]) == ("contract", "binary") else [{
            "kind": "artifact",
            "relativePath": name,
            "bytes": len(payload),
            "sha256": sha256_bytes(payload),
        }],
        "producer": {
            "repository": REPOSITORY,
            "workflowPath": ".github/workflows/products.yml",
            "commit": COMMIT,
            "tree": TREE,
            "event": "push" if trust_domain == "release" else "pull_request",
            "runId": 7,
            "runAttempt": 1,
            "pullRequest": None if trust_domain == "release" else PULL_REQUEST,
        },
        "trustDomain": trust_domain,
        "result": "success",
    })
    contents = canonical_json_bytes(receipt)
    return {
        "receipt": receipt,
        "receiptBytes": contents,
        "receiptSha256": sha256_bytes(contents),
        "objectSha256": sha256_bytes(b"object:" + contents),
    }


def plan_for(
    instance: PhaseInstanceId,
    inputs: dict[PhaseInstanceId, dict[str, object]],
    resolved: dict[PhaseInstanceId, dict[str, object]],
) -> dict[str, object]:
    from ci.tests.test_product_plan import verified_native_projections, verified_sdk_projections
    semantic_dependencies = runtime_validation_dependencies(instance)
    return plan_phase(
        instance,
        upstream_receipts=[
            resolved[dependency]["receipt"]
            for dependency in phase_instance_dependencies(instance)
        ],
        runtime_validation_projection=(
            VerifiedRuntimeValidationProjection(
                instance.component,
                tuple(dependency.target for dependency in semantic_dependencies),
                DIGEST_A,
                _VERIFIED_RUNTIME_VALIDATION_PROJECTION,
            )
            if semantic_dependencies else None
        ),
        contract_execution_projection=(
            verified_execution_fixture(resolved[CONTRACT_BINARY]["receiptBytes"])
            if instance == CONTRACT_PACKAGE else None
        ),
        native_runtime_projections=verified_native_projections(
            instance, [resolved[dependency]["receipt"] for dependency in phase_instance_dependencies(instance)],
            inputs[instance].get("contract_projection"),
        ),
        sdk_validation_projections=verified_sdk_projections(
            instance, [resolved[dependency]["receipt"] for dependency in phase_instance_dependencies(instance)]),
        **inputs[instance],
    )


def contract_execution_chain(root: Path, inputs):
    """Real four-phase fixture artifacts for admission tests, not hosted evidence."""
    resolved, objects, receipts = {}, {}, {}
    roots = {"maven": "outputs/maven", "evidence": "outputs/evidence", "inventory": "outputs/inventories"}
    for instance in (CONTRACT_BINARY, CONTRACT_PACKAGE, CONTRACT_VALIDATION, CONTRACT_METADATA):
        stage = root / instance.phase
        if instance == CONTRACT_BINARY:
            for name, contents in binary_stage_files(VERSIONS["contract"]).items():
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(contents)
            output_roots = {**roots, "contract-execution": "outputs/execution"}
        elif instance == CONTRACT_PACKAGE:
            shutil.copytree(root / "binary/outputs", stage / "outputs", ignore=shutil.ignore_patterns("execution"))
            output_roots = roots
        elif instance == CONTRACT_VALIDATION:
            shutil.copytree(root / "package/outputs", stage / "outputs")
            validate_contract_package_stage(
                root / "package", receipts["package"], resolved[CONTRACT_PACKAGE]["receiptSha256"],
                receipts["binary"], resolved[CONTRACT_BINARY]["receiptSha256"],
                stage / "outputs/validation", VERSIONS["contract"],
            )
            output_roots = {**roots, "validation": "outputs/validation"}
        else:
            payload = stage / "outputs" / f"codex-agent-contract-{VERSIONS['contract']}.zip"
            build_contract_bundle(root / "package/outputs", payload, VERSIONS["contract"])
            output_roots = {"contract-bundle": "outputs"}
        manifest = write_output_manifest(stage, "contract", "contract", instance.phase, "common", VERSIONS["contract"], output_roots)
        planned = plan_for(instance, inputs, resolved)
        envelope = envelope_for_plan(planned)
        envelope["receipt"]["outputs"] = manifest["outputs"]
        envelope["receiptBytes"] = canonical_json_bytes(validate_phase_receipt(envelope["receipt"]))
        envelope["receiptSha256"] = sha256_bytes(envelope["receiptBytes"])
        receipts[instance.phase] = root / f"{instance.phase}-receipt.json"
        receipts[instance.phase].write_bytes(envelope["receiptBytes"])
        stored = store_local_object(stage, receipts[instance.phase], root / "cache")
        envelope["objectSha256"] = stored["objectSha256"]
        resolved[instance] = envelope
        objects[instance] = (envelope, stored["path"])
    capture_contract_execution_closure(
        payload, receipts, root / "binary/outputs/execution/contract-execution.zip", root / "closure",
    )
    return resolved, objects, payload, receipts["metadata"], root / "closure"


def retained_chain(
    requested: PhaseInstanceId,
    inputs: dict[PhaseInstanceId, dict[str, object]],
) -> dict[PhaseInstanceId, dict[str, object]]:
    resolved: dict[PhaseInstanceId, dict[str, object]] = {}
    pending = set(dependency_closure(requested))
    while pending:
        ready = sorted(
            instance for instance in pending
            if all(dependency in resolved for dependency in phase_instance_dependencies(instance))
        )
        if not ready:
            raise AssertionError("fixture dependency cycle")
        for instance in ready:
            resolved[instance] = envelope_for_plan(plan_for(instance, inputs, resolved))
            pending.remove(instance)
    return resolved


def retained_product_closure(
    requested: PhaseInstanceId,
    inventory_overrides: dict[PhaseInstanceId, list[dict[str, object]]] | None = None,
    *,
    repository_root: Path | None = None,
    repository_revision: str | None = None,
) -> tuple[
    dict[PhaseInstanceId, dict[str, object]],
    dict[PhaseInstanceId, dict[str, object]],
]:
    inputs = all_inputs(requested)
    if (repository_root is None) != (repository_revision is None):
        raise AssertionError("fixture repository root and revision must be paired")
    if repository_root is not None:
        for instance in inputs:
            if (
                instance.product == "runtime"
                and instance.component in NATIVE_TARGETS
                and instance.phase == "binary"
            ):
                inputs[instance]["inventory"] = phase_git_inventory(
                    repository_root, repository_revision, instance,
                )
    for instance, inventory in (inventory_overrides or {}).items():
        inputs[instance]["inventory"] = inventory
    resolved = retained_chain(CONTRACT_METADATA, inputs)
    contract = resolved[CONTRACT_METADATA]
    bundle_path = f"outputs/codex-agent-contract-{VERSIONS['contract']}.zip"
    contract["receipt"]["outputs"] = [{
        "kind": "contract-bundle",
        "relativePath": bundle_path,
        "bytes": 1,
        "sha256": DIGEST_B,
    }]
    contract["receiptBytes"] = canonical_json_bytes(contract["receipt"])
    contract["receiptSha256"] = sha256_bytes(contract["receiptBytes"])

    for instance in dependency_closure(requested):
        components = required_contract_components(instance)
        if components:
            inputs[instance]["contract_projection"] = contract_projection.VerifiedContractProjection({
                "schemaVersion": 1,
                "receiptSha256": contract["receiptSha256"],
                "bundlePath": bundle_path,
                "bundleSha256": DIGEST_B,
                "manifestSha256": DIGEST_A,
                "contractVersion": VERSIONS["contract"],
                "contractDigest": DIGEST_A,
                "componentDigests": [
                    {"component": component, "sha256": DIGEST_B}
                    for component in components
                ],
            }, contract_projection._VERIFIED, DIGEST_B)

    pending = set(dependency_closure(requested)) - set(resolved)
    while pending:
        ready = sorted(
            instance for instance in pending
            if all(dependency in resolved for dependency in phase_instance_dependencies(instance))
        )
        if not ready:
            raise AssertionError("fixture dependency cycle")
        for instance in ready:
            resolved[instance] = envelope_for_plan(plan_for(instance, inputs, resolved))
            pending.remove(instance)
    return inputs, resolved


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class ProductReuseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.keys = tempfile.TemporaryDirectory()
        cls.private_key, cls.public_key, cls.development_signing = generate_development_key(
            Path(cls.keys.name).resolve() / "keys"
        )
        cls.release_signing = {
            **cls.development_signing,
            "trustDomain": "release",
            "keyId": "release-test",
        }
        cls.release_keys = Path(cls.keys.name).resolve() / "release-keys"
        cls.release_keys.mkdir()
        (cls.release_keys / "release-test.pub").write_bytes(cls.public_key.read_bytes())
        cls.release_keyring = Path(cls.keys.name).resolve() / "release-keyring.json"
        write_canonical_json(cls.release_keyring, {
            "schemaVersion": 1,
            "namespace": cls.release_signing["namespace"],
            "algorithm": cls.release_signing["algorithm"],
            "trustDomain": "release",
            "activeKey": {
                "keyId": "release-test",
                "fingerprint": cls.release_signing["fingerprint"],
            },
            "retiredKeys": [],
        })

    @classmethod
    def tearDownClass(cls) -> None:
        cls.keys.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.counter = 0

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def object_for_plan(
        self,
        plan: dict[str, object],
        *,
        trust_domain: str,
        release_version: str | None = None,
        cache_root: Path | None = None,
        producer_commit: str = COMMIT,
        producer_tree: str = TREE,
        binary_salt: bytes = b"",
        execution_context: bytes = b"first",
    ) -> tuple[dict[str, object], Path]:
        self.counter += 1
        root = self.root / f"object-{self.counter}"
        stage = root / "stage"
        name = f"{plan['component']}-{plan['phase']}-{plan['target']}.bin"
        payload = stage / "outputs" / name
        version = release_version or product_version(str(plan["product"]))
        binary = (plan["product"], plan["phase"]) == ("contract", "binary")
        if binary:
            for relative, data in binary_stage_files(version, binary_salt, execution_context).items():
                path = stage / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        else:
            payload.parent.mkdir(parents=True)
            payload.write_bytes(str(plan["buildKey"]).encode())
        manifest = write_output_manifest(
            stage,
            plan["product"],
            plan["component"],
            plan["phase"],
            plan["target"],
            version,
            {"maven": "outputs/maven", "evidence": "outputs/evidence", "inventory": "outputs/inventories",
             "contract-execution": "outputs/execution"} if binary else {"artifact": "outputs"},
        )
        envelope = envelope_for_plan(
            plan,
            trust_domain=trust_domain,
            release_version=version,
        )
        envelope["receipt"]["outputs"] = manifest["outputs"]
        envelope["receipt"]["producer"]["commit"] = producer_commit
        envelope["receipt"]["producer"]["tree"] = producer_tree
        envelope["receiptBytes"] = canonical_json_bytes(envelope["receipt"])
        envelope["receiptSha256"] = sha256_bytes(envelope["receiptBytes"])
        receipt_path = root / "phase-receipt.json"
        write_canonical_json(receipt_path, envelope["receipt"])
        stored = store_local_object(stage, receipt_path, cache_root or root / "cache")
        envelope["objectSha256"] = stored["objectSha256"]
        return envelope, stored["path"]

    @staticmethod
    def entry(envelope: dict[str, object]) -> dict[str, object]:
        receipt = envelope["receipt"]
        artifact = receipt["outputs"][0]
        return {
            "buildKey": receipt["buildKey"],
            "product": receipt["product"],
            "component": receipt["component"],
            "phase": receipt["phase"],
            "target": receipt["target"],
            "productVersion": receipt["productVersion"],
            "coordinate": f"test:{receipt['component']}",
            "outputInventoryDigest": output_inventory_digest(receipt["outputs"]),
            "outputs": receipt["outputs"],
            "artifactName": artifact["relativePath"],
            "artifactSha256": artifact["sha256"],
            "receiptSha256": envelope["receiptSha256"],
        }

    def catalog(
        self,
        source: str,
        values: list[tuple[dict[str, object], Path | None]],
        *,
        trust_domain: str | None = None,
        pull_request: int = PULL_REQUEST,
        execution_artifact: bool = False,
    ) -> RemoteCatalog:
        self.counter += 1
        root = self.root / f"catalog-{self.counter}"
        root.mkdir()
        trust = trust_domain or ("development" if source == "same-pr" else "release")
        signing = self.development_signing if trust == "development" else self.release_signing
        if source == "stable":
            receipt = values[0][0]["receipt"]
            context = {
                "kind": "stable",
                "tag": f"{receipt['product']}/v{receipt['productVersion']}",
            }
        elif source == "promoted-main":
            context = {
                "kind": "promoted-main",
                "commit": COMMIT,
                "tree": TREE,
                "promotionRunId": 7,
                "promotionRunAttempt": 1,
            }
        elif source == "same-pr":
            context = {
                "kind": "pull-request",
                "pullRequest": pull_request,
                "commit": COMMIT,
                "tree": TREE,
                "runId": 7,
                "runAttempt": 1,
            }
        else:
            raise AssertionError(source)
        producer = {
            "repository": REPOSITORY,
            "workflowPath": ".github/workflows/products.yml",
            "commit": COMMIT,
            "tree": TREE,
            "event": "pull_request" if source == "same-pr" else "push",
            "runId": 7,
            "runAttempt": 1,
            "pullRequest": pull_request if source == "same-pr" else None,
        }
        index = {
            "schemaVersion": 1,
            "repository": REPOSITORY,
            "context": context,
            "entries": sorted((self.entry(envelope) for envelope, _ in values), key=lambda item: item["buildKey"]),
            "trustDomain": trust,
            "signing": signing,
            "producer": producer,
        }
        if execution_artifact:
            for entry in index["entries"]:
                archive = next(output for output in entry["outputs"] if output["kind"] == "contract-execution")
                entry.update(artifactName=archive["relativePath"], artifactSha256=archive["sha256"])
        manifest = root / "product-index.json"
        write_canonical_json(manifest, index)
        signature = sign_manifest(
            manifest,
            self.private_key,
            signing,
        )
        return RemoteCatalog(
            manifest,
            signature,
            {envelope["receipt"]["buildKey"]: path for envelope, path in values},
            public_key=self.public_key if trust == "development" else None,
            keyring=self.release_keyring if trust == "release" else None,
            keys_directory=self.release_keys if trust == "release" else None,
        )

    @staticmethod
    def session(**values: object) -> LookupSession:
        return LookupSession(repository=REPOSITORY, pull_request=PULL_REQUEST, **values)

    def runtime_flags_revision(self) -> tuple[Path, str, str]:
        repository = self.root / "runtime-flags-repository"
        authority = repository / "codex-agent-runtime-desktop/native/c-api/binary-flags.json"
        authority.parent.mkdir(parents=True)
        authority.write_bytes((CHECKOUT / authority.relative_to(repository)).read_bytes())
        for relative in (
            "codex-agent-runtime-desktop/native/c-api/abi-contract.json",
            "codex-agent-runtime-desktop/native/c-api/include/codex_agent.h",
            "codex-agent-runtime-desktop/native/c-api/exports/macos.exports",
            "codex-agent-runtime-desktop/native/c-api/exports/linux.map",
            "codex-agent-runtime-desktop/native/c-api/exports/windows.def",
            "codex-agent-runtime-desktop/codex-app-server-distributions.json",
        ):
            destination = repository / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((CHECKOUT / relative).read_bytes())
        profiles = repository / "gradle/release/toolchains/runtime"
        profiles.mkdir(parents=True)
        for target, contents in TEST_TOOLCHAIN_PROFILE_BYTES.items():
            (profiles / f"{target}.json").write_bytes(contents)
        subprocess.run(("git", "init", "-q"), cwd=repository, check=True)
        subprocess.run(("git", "config", "user.email", "fixture@example.invalid"), cwd=repository, check=True)
        subprocess.run(("git", "config", "user.name", "Fixture"), cwd=repository, check=True)
        subprocess.run(("git", "add", "."), cwd=repository, check=True)
        subprocess.run(("git", "commit", "-qm", "flags"), cwd=repository, check=True)
        revision = subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=repository, check=True, capture_output=True, text=True,
        ).stdout.strip()
        return repository, revision, load_runtime_binary_flags(authority)["linux-x64"].digest

    def reuse_wave_repository(self) -> tuple[Path, str]:
        repository = self.root / "reuse-wave-repository"
        source = repository / "codex-agent-core/src/commonMain/kotlin/example.kt"
        source.parent.mkdir(parents=True)
        source.write_text("package example\n", encoding="utf-8")
        subprocess.run(("git", "init", "-q"), cwd=repository, check=True)
        subprocess.run(("git", "config", "user.email", "fixture@example.invalid"), cwd=repository, check=True)
        subprocess.run(("git", "config", "user.name", "Fixture"), cwd=repository, check=True)
        subprocess.run(("git", "add", "."), cwd=repository, check=True)
        subprocess.run(("git", "commit", "-qm", "fixture"), cwd=repository, check=True)
        revision = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return repository, revision

    def reuse_wave_request(self, repository: Path, revision: str) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "requestType": "reuse-wave",
            "repository": REPOSITORY,
            "pullRequest": PULL_REQUEST,
            "repositoryRoot": str(repository),
            "repositoryRevision": revision,
            "artifactRoot": str(self.root),
            "requested": [{
                "product": CONTRACT_BINARY.product,
                "component": CONTRACT_BINARY.component,
                "phase": CONTRACT_BINARY.phase,
                "target": CONTRACT_BINARY.target,
            }],
            "versions": VERSIONS,
            "phaseAuthorities": [{
                "product": CONTRACT_BINARY.product,
                "component": CONTRACT_BINARY.component,
                "phase": CONTRACT_BINARY.phase,
                "target": CONTRACT_BINARY.target,
                "toolchainProfileDigest": NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                "flagsDigest": NOT_APPLICABLE_FLAGS_DIGEST,
                "outputSchemaVersion": 1,
            }],
            "contractEvidence": None,
            "runtimeValidationEvidence": [],
            "availableObjects": [],
            "catalogs": {
                "stable": [],
                "promotedMain": None,
                "samePr": None,
                "local": None,
            },
        }

    def test_metadata_admission_is_explicit_invocation_authority_not_transport(self) -> None:
        from ci.products.reuse import FacadeMetadataAdmission, AndroidMetadataAdmission
        repository, revision = self.reuse_wave_repository()
        request = self.reuse_wave_request(repository, revision)
        core = object.__new__(FacadeMetadataAdmission)
        android = object.__new__(AndroidMetadataAdmission)
        with mock.patch("ci.products.reuse.advance_reuse", return_value=({"ok": True}, ())) as delegated:
            self.assertEqual({"ok": True}, plan_reuse_wave(request,
                sdk_facade_metadata_admission=core, sdk_android_metadata_admission=android))
        self.assertIs(core, delegated.call_args.kwargs["sdk_facade_metadata_admission"])
        self.assertIs(android, delegated.call_args.kwargs["sdk_android_metadata_admission"])
        for name in ("sdkFacadeMetadataAdmission", "sdkAndroidMetadataAdmission",
                     "sdk_facade_metadata_admission", "sdk_android_metadata_admission"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                plan_reuse_wave({**request, name: {"transported": "not authority"}})

    def test_aggregate_external_transport_never_changes_product_plan_identity(self) -> None:
        repository, revision = self.reuse_wave_repository()
        request = self.reuse_wave_request(repository, revision)
        expected = plan_reuse_wave(request)
        for digest, path in ((DIGEST_A, "producer-one/original"), (DIGEST_B, "another-run/retained")):
            request["runtimeAggregateReleaseEvidence"] = [{"receiptSha256": digest, "handoffRoot": path}]
            self.assertEqual(expected, plan_reuse_wave(request))
        request["runtimeAggregateReleaseEvidence"][0]["handoffRoot"] = "../escape"
        with self.assertRaises(ValueError):
            plan_reuse_wave(request)

    def test_reuse_wave_derives_git_inventory_and_returns_advance_result_unchanged(self) -> None:
        repository, revision = self.reuse_wave_repository()
        request = self.reuse_wave_request(repository, revision)
        request["nativeRuntimeComparisonEvidence"] = []
        request["adapterRuntimeComparisonEvidence"] = []
        request["sdkValidationEvidence"] = []
        request["sdkAppleValidationEvidence"] = []
        request["sdkAppleValidationPolicy"] = {"fixture": "explicit caller policy"}
        request["runtimeAggregateReleaseEvidence"] = [{"receiptSha256": DIGEST_A, "handoffRoot": "original-aggregate"}]
        comparison_provider = mock.Mock()
        adapter_provider = mock.Mock()
        sdk_provider = mock.Mock()
        (repository / "codex-agent-core/src/commonMain/kotlin/example.kt").write_text(
            "package dirty\n",
            encoding="utf-8",
        )
        expected = {
            "schemaVersion": 1,
            "result": "distinctive",
            "fullReuse": False,
            "phases": [],
            "matrices": {"contract": [], "runtime": [], "sdk": []},
        }
        with mock.patch("ci.products.reuse.advance_reuse", return_value=(expected, ())) as delegated, \
                mock.patch("ci.products.reuse._native_comparison_provider", return_value=comparison_provider) as proof_factory, \
                mock.patch("ci.products.reuse.adapter_comparison_provider", return_value=adapter_provider) as adapter_factory, \
                mock.patch("ci.products.reuse.sdk_validation_provider", return_value=sdk_provider) as sdk_factory, \
                mock.patch("ci.products.reuse.AppleValidationAdmission") as apple_factory:
            result = plan_reuse_wave(request)
        self.assertIs(expected, result)
        args, kwargs = delegated.call_args
        self.assertEqual((CONTRACT_BINARY,), args[0])
        self.assertEqual({CONTRACT_BINARY}, set(args[1]))
        self.assertEqual(
            phase_git_inventory(repository, revision, CONTRACT_BINARY),
            args[1][CONTRACT_BINARY]["inventory"],
        )
        self.assertEqual(repository, kwargs["repository_root"])
        self.assertEqual(revision, kwargs["repository_revision"])
        self.assertIsInstance(args[3], LookupSession)
        self.assertIs(comparison_provider, args[3]._native_runtime_projection)
        self.assertIs(adapter_provider, args[3]._adapter_runtime_projection)
        self.assertIs(sdk_provider, args[3]._sdk_validation_projection)
        self.assertTrue(callable(kwargs["sdk_validation_projection_provider"]))
        self.assertIs(apple_factory.return_value, kwargs["sdk_apple_validation_admission"])
        apple_factory.assert_called_once_with(Path(request["artifactRoot"]), [], repository=repository,
            policy_revision=revision, policy=request["sdkAppleValidationPolicy"])
        proof_factory.assert_called_once_with(Path(request["artifactRoot"]), [])
        adapter_factory.assert_called_once_with(Path(request["artifactRoot"]), [])
        sdk_factory.assert_called_once_with(Path(request["artifactRoot"]), [], repository=repository,
                                            policy_revision=revision, tooling=None)

    def test_reuse_wave_rejects_unpaired_apple_evidence_and_caller_policy(self) -> None:
        repository, revision = self.reuse_wave_repository()
        for field, value in (("sdkAppleValidationEvidence", []), ("sdkAppleValidationPolicy", {})):
            request = self.reuse_wave_request(repository, revision)
            request[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "explicit caller policy"):
                plan_reuse_wave(request)

    def test_reuse_wave_rejects_nonexact_authorities_and_unsafe_paths_before_planning(self) -> None:
        repository, revision = self.reuse_wave_repository()
        base = self.reuse_wave_request(repository, revision)
        outside = {
            **base["phaseAuthorities"][0],
            "phase": "package",
        }
        invalid = {
            "missing": lambda value: value.update(phaseAuthorities=[]),
            "duplicate": lambda value: value.update(
                phaseAuthorities=[*value["phaseAuthorities"], *value["phaseAuthorities"]],
            ),
            "outside": lambda value: value.update(
                phaseAuthorities=[*value["phaseAuthorities"], outside],
            ),
            "caller inventory": lambda value: value["phaseAuthorities"][0].update(inventory=[]),
            "symbolic revision": lambda value: value.update(repositoryRevision="HEAD"),
            "claimed semantic digest": lambda value: value.update(
                runtimeValidationEvidence=[{
                    **value["requested"][0],
                    "reports": [],
                    "sha256": DIGEST_A,
                }],
            ),
        }
        for name, mutate in invalid.items():
            with self.subTest(name=name), mock.patch("ci.products.reuse.advance_reuse") as delegated:
                request = copy.deepcopy(base)
                mutate(request)
                with self.assertRaises(ValueError):
                    plan_reuse_wave(request)
                delegated.assert_not_called()

        for path in ("../escape.zip", "nested\\escape.zip", "/absolute/object.zip"):
            with self.subTest(path=path), mock.patch("ci.products.reuse.advance_reuse") as delegated:
                request = copy.deepcopy(base)
                request["availableObjects"] = [{
                    **request["requested"][0],
                    "buildKey": DIGEST_A,
                    "receiptSha256": DIGEST_B,
                    "objectSha256": DIGEST_A,
                    "objectPath": path,
                }]
                with self.assertRaises(ValueError):
                    plan_reuse_wave(request)
                delegated.assert_not_called()

        for path in ("../contract.pub", "/absolute/contract.pub", "nested\\contract.pub"):
            with self.subTest(contract_path=path), mock.patch("ci.products.reuse.advance_reuse") as delegated:
                request = copy.deepcopy(base)
                request["contractEvidence"] = {
                    "attestation": "contract.attestation.json",
                    "attestationSignature": "contract.attestation.sig",
                    "publicKey": path,
                    "expectedTrustDomain": "development",
                    "keyring": None,
                    "keysDirectory": None,
                }
                with self.assertRaises(ValueError):
                    plan_reuse_wave(request)
                delegated.assert_not_called()

        duplicate_object = {
            **base["requested"][0],
            "buildKey": DIGEST_A,
            "receiptSha256": DIGEST_B,
            "objectSha256": DIGEST_A,
            "objectPath": "object.zip",
        }
        duplicate_request = copy.deepcopy(base)
        duplicate_request["availableObjects"] = [
            duplicate_object,
            {**duplicate_object, "buildKey": DIGEST_B, "receiptSha256": DIGEST_A},
        ]
        duplicate_request["catalogs"]["stable"] = [{
            "manifest": "indexes/product-index.json",
            "signature": "indexes/product-index.json.sig",
            "publicKey": None,
            "keyring": "keys/keyring.json",
            "keysDirectory": "keys",
            "contractAttestation": None,
            "contractAttestationSignature": None,
            "contractPublicKey": None,
            "objects": [],
        }]
        with mock.patch("ci.products.reuse.LookupSession._load_catalog") as catalog_io, \
                mock.patch("ci.products.reuse.verify_object") as verified:
            with self.assertRaisesRegex(ValueError, "unique by phase identity"):
                plan_reuse_wave(duplicate_request)
            catalog_io.assert_not_called()
            verified.assert_not_called()

        catalog = {
            "manifest": "indexes/product-index.json",
            "signature": "indexes/product-index.json.sig",
            "publicKey": None,
            "keyring": "keys/keyring.json",
            "keysDirectory": "keys",
            "contractAttestation": None,
            "contractAttestationSignature": None,
            "contractPublicKey": None,
            "objects": [],
        }
        duplicate_catalog = copy.deepcopy(base)
        duplicate_catalog["catalogs"]["stable"] = [catalog, catalog]
        with mock.patch("ci.products.reuse._remote_catalog") as decoded:
            with self.assertRaisesRegex(ValueError, "sorted and unique"):
                plan_reuse_wave(duplicate_catalog)
            decoded.assert_not_called()

        local_escape = copy.deepcopy(base)
        local_escape["catalogs"]["local"] = {
            "cacheRoot": str(self.root / "cache"),
            "restoreRoot": str(self.root.parent),
            "candidates": [],
        }
        with self.assertRaisesRegex(ValueError, "fields are invalid"):
            plan_reuse_wave(local_escape)

        external = self.root / "external"
        external.mkdir()
        (external / "object.zip").write_bytes(b"not-an-object")
        linked = self.root / "linked"
        try:
            linked.symlink_to(external, target_is_directory=True)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"symbolic links are unavailable: {error}")
        symlink_request = copy.deepcopy(base)
        symlink_request["availableObjects"] = [{
            **duplicate_object,
            "objectPath": "linked/object.zip",
        }]
        with self.assertRaises((CacheObjectError, ValueError)):
            plan_reuse_wave(symlink_request)

    def test_reuse_wave_decodes_only_raw_runtime_validation_report_paths(self) -> None:
        repository, revision = self.reuse_wave_repository()
        metadata = PhaseInstanceId("runtime", "jvm", "metadata", "jvm")
        request = self.reuse_wave_request(repository, revision)
        request["requested"] = [{
            "product": metadata.product,
            "component": metadata.component,
            "phase": metadata.phase,
            "target": metadata.target,
        }]
        request["phaseAuthorities"] = [{
            **request["requested"][0],
            "toolchainProfileDigest": NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            "flagsDigest": NOT_APPLICABLE_FLAGS_DIGEST,
            "outputSchemaVersion": 1,
        }]
        request["runtimeValidationEvidence"] = [{
            **request["requested"][0],
            "reports": [f"reports/{target}.json" for target in (
                "macosArm64", "macosX64", "linuxArm64", "linuxX64", "mingwX64",
            )],
        }]
        envelopes = tuple({"receipt": {"target": target}} for target in range(5))

        def delegated_advance(*_args, **kwargs):
            kwargs["runtime_validation_projection_provider"](metadata, envelopes)
            return {"ok": True}, ()

        with (
            mock.patch("ci.products.reuse._dependency_closure", return_value=(metadata,)),
            mock.patch("ci.products.reuse.phase_git_inventory", return_value=[]),
            mock.patch("ci.products.reuse.advance_reuse", side_effect=delegated_advance) as delegated,
            mock.patch(
                "ci.products.reuse.verify_runtime_validation_projection", return_value=object(),
            ) as verified,
        ):
            self.assertEqual({"ok": True}, plan_reuse_wave(request))
        provider = delegated.call_args.kwargs["runtime_validation_projection_provider"]
        self.assertTrue(callable(provider))
        self.assertEqual(
            tuple(self.root / f"reports/{target}.json" for target in (
                "macosArm64", "macosX64", "linuxArm64", "linuxX64", "mingwX64",
            )),
            tuple(verified.call_args.args[1]),
        )
        self.assertEqual([envelope["receipt"] for envelope in envelopes], verified.call_args.args[2])

        early = copy.deepcopy(request)
        with (
            mock.patch("ci.products.reuse._dependency_closure", return_value=(metadata,)),
            mock.patch("ci.products.reuse.phase_git_inventory", return_value=[]),
            mock.patch("ci.products.reuse.advance_reuse", return_value=({"ok": True}, ())),
        ):
            with self.assertRaisesRegex(ValueError, "before its metadata phase was ready"):
                plan_reuse_wave(early)

        future = copy.deepcopy(request)
        future["runtimeValidationEvidence"] = []
        continuation = {"continuationRequirements": [{"kind": "runtime-validation-evidence"}]}
        with (
            mock.patch("ci.products.reuse._dependency_closure", return_value=(metadata,)),
            mock.patch("ci.products.reuse.phase_git_inventory", return_value=[]),
            mock.patch("ci.products.reuse.advance_reuse", return_value=(continuation, ())),
        ):
            self.assertIs(continuation, plan_reuse_wave(future))

        with (
            mock.patch("ci.products.reuse._dependency_closure", return_value=(metadata,)),
            mock.patch("ci.products.reuse.phase_git_inventory", return_value=[]),
            mock.patch("ci.products.reuse.advance_reuse", side_effect=delegated_advance),
            mock.patch(
                "ci.products.reuse.verify_runtime_validation_projection",
                side_effect=ValueError("cross-paired Runtime validation evidence"),
            ),
        ):
            with self.assertRaisesRegex(ValueError, "cross-paired"):
                plan_reuse_wave(request)

    def test_advance_reuse_requires_internal_authenticated_runtime_projection(self) -> None:
        metadata = PhaseInstanceId("runtime", "jvm", "metadata", "jvm")
        early, _ = advance_reuse(
            [metadata], all_inputs(metadata), [], self.session(),
        )
        self.assertEqual([], early["continuationRequirements"])
        self.assertEqual(
            ["binary"], [entry["phase"] for entry in early["matrices"]["contract"]],
        )

        dependencies = tuple(
            dependency for dependency in phase_instance_dependencies(metadata)
            if dependency.phase == "validation" and dependency.target != "node-js-binding"
        )
        closure = tuple(sorted((*dependencies, metadata)))
        inputs = {instance: phase_inputs(instance) for instance in closure}
        envelopes = [{
            "receipt": {
                "product": instance.product,
                "component": instance.component,
                "phase": instance.phase,
                "target": instance.target,
            },
            "receiptBytes": b"receipt",
            "receiptSha256": DIGEST_A,
            "objectSha256": DIGEST_B,
        } for instance in dependencies]

        def validate(value: dict[str, object], **_: object):
            receipt = value["receipt"]
            return PhaseInstanceId(
                receipt["product"], receipt["component"], receipt["phase"], receipt["target"],
            ), value

        capability = object()

        def planned(instance: PhaseInstanceId, values, *_args):
            if instance == metadata:
                self.assertIs(capability, values[metadata]["runtime_validation_projection"])
            return {
                "product": instance.product,
                "component": instance.component,
                "phase": instance.phase,
                "target": instance.target,
                "buildKey": DIGEST_A,
                "inputs": {},
            }

        patches = (
            mock.patch("ci.products.reuse._dependency_closure", return_value=closure),
            mock.patch(
                "ci.products.reuse.phase_instance_dependencies",
                side_effect=lambda instance: dependencies if instance == metadata else (),
            ),
            mock.patch("ci.products.reuse._validate_envelope", side_effect=validate),
            mock.patch("ci.products.reuse.verify_build_key_output_consistency"),
            mock.patch("ci.products.reuse._plan", side_effect=planned),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            waiting, _ = advance_reuse([metadata], inputs, envelopes, self.session())
            self.assertEqual([{
                "kind": "runtime-validation-evidence",
                "product": "runtime",
                "component": "jvm",
                "phase": "metadata",
                "target": "jvm",
                "dependencies": [{
                    "product": dependency.product,
                    "component": dependency.component,
                    "phase": dependency.phase,
                    "target": dependency.target,
                } for dependency in dependencies],
            }], waiting["continuationRequirements"])
            metadata_phase = next(
                phase for phase in waiting["phases"]
                if (phase["product"], phase["component"], phase["phase"], phase["target"])
                == (metadata.product, metadata.component, metadata.phase, metadata.target)
            )
            self.assertEqual("waiting", metadata_phase["state"])
            self.assertIsNone(metadata_phase["buildKey"])
            provider = mock.Mock(return_value=capability)
            result, _ = advance_reuse(
                [metadata], inputs, envelopes, self.session(),
                runtime_validation_projection_provider=provider,
            )
            self.assertEqual("build-required", result["result"])
            self.assertEqual([], result["continuationRequirements"])
            provider.assert_called_once()
            self.assertEqual(metadata, provider.call_args.args[0])
            self.assertEqual(tuple(envelopes), provider.call_args.args[1])

            metadata_envelope = {
                "receipt": {
                    "product": metadata.product,
                    "component": metadata.component,
                    "phase": metadata.phase,
                    "target": metadata.target,
                },
                "receiptBytes": b"metadata receipt",
                "receiptSha256": DIGEST_A,
                "objectSha256": DIGEST_B,
            }
            complete, _ = advance_reuse(
                [metadata], inputs, [*envelopes, metadata_envelope], self.session(),
                runtime_validation_projection_provider=provider,
            )
            self.assertTrue(complete["fullReuse"])
            self.assertEqual([], complete["continuationRequirements"])

        forged = copy.deepcopy(inputs)
        forged[metadata]["runtime_validation_projection"] = capability
        with mock.patch("ci.products.reuse._dependency_closure", return_value=closure):
            with self.assertRaisesRegex(ValueError, "Callers cannot supply"):
                advance_reuse([metadata], forged, [], self.session())

    def test_reuse_wave_loads_available_object_with_existing_verifier(self) -> None:
        repository, revision = self.reuse_wave_repository()
        request = self.reuse_wave_request(repository, revision)
        inputs = {
            "inventory": phase_git_inventory(repository, revision, CONTRACT_BINARY),
            "versions": VERSIONS,
            "toolchain_profile_digest": NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            "flags_digest": NOT_APPLICABLE_FLAGS_DIGEST,
        }
        planned = plan_phase(CONTRACT_BINARY, upstream_receipts=[], **inputs)
        envelope, object_path = self.object_for_plan(planned, trust_domain="development")
        request["availableObjects"] = [{
            **request["requested"][0],
            "buildKey": envelope["receipt"]["buildKey"],
            "receiptSha256": envelope["receiptSha256"],
            "objectSha256": envelope["objectSha256"],
            "objectPath": object_path.relative_to(self.root).as_posix(),
        }]
        with mock.patch("ci.products.reuse.verify_object", wraps=product_reuse.verify_object) as verified:
            result = plan_reuse_wave(request)
        self.assertTrue(result["fullReuse"])
        self.assertEqual("retained", result["phases"][0]["state"])
        self.assertEqual({"contract": [], "runtime": [], "sdk": []}, result["matrices"])
        self.assertEqual(envelope["receiptSha256"], result["phases"][0]["receiptSha256"])
        self.assertEqual(envelope["objectSha256"], result["phases"][0]["objectSha256"])
        verified.assert_called_once_with(
            object_path,
            build_key=envelope["receipt"]["buildKey"],
            receipt_sha256=envelope["receiptSha256"],
            object_sha256=envelope["objectSha256"],
        )

        request["availableObjects"][0]["objectSha256"] = DIGEST_A
        with self.assertRaises((CacheObjectError, ValueError)):
            plan_reuse_wave(request)

    @unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
    def test_reuse_wave_restores_and_authenticates_contract_metadata_repeatably(self) -> None:
        repository, revision = self.reuse_wave_repository()
        runtime_source = repository / "codex-agent-runtime-desktop/src/jvmMain/kotlin/example.kt"
        runtime_source.parent.mkdir(parents=True)
        runtime_source.write_text("package example\n", encoding="utf-8")
        subprocess.run(("git", "add", "."), cwd=repository, check=True)
        subprocess.run(("git", "commit", "-qm", "runtime"), cwd=repository, check=True)
        revision = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        closure = dependency_closure(RUNTIME_JVM)
        inputs = {
            instance: {
                "inventory": phase_git_inventory(repository, revision, instance),
                "versions": VERSIONS,
                "toolchain_profile_digest": NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                "flags_digest": NOT_APPLICABLE_FLAGS_DIGEST,
            }
            for instance in closure
        }
        resolved, objects, bundle, receipt_path, execution_closure = contract_execution_chain(self.root / "contract-chain", inputs)
        metadata_stage = bundle.parent.parent
        attestation_directory = self.root / "contract-attestation"
        build_contract_attestation(
            bundle, receipt_path, self.development_signing, self.private_key,
            self.public_key, attestation_directory, execution_closure=execution_closure,
        )
        attestation = attestation_directory / f"codex-agent-contract-{VERSIONS['contract']}.attestation.json"
        attestation_signature = attestation.with_suffix(".sig")

        projection = contract_projection.verify_contract_component_projection(
            metadata_stage,
            resolved[CONTRACT_METADATA]["receiptBytes"],
            attestation,
            attestation_signature,
            self.public_key,
            expected_trust_domain="development",
            expected_contract_version=VERSIONS["contract"],
            required_components=("jvm",),
        )
        inputs[RUNTIME_JVM]["contract_projection"] = projection
        runtime_plan = plan_for(RUNTIME_JVM, inputs, resolved)
        runtime_envelope, runtime_object = self.object_for_plan(
            runtime_plan,
            trust_domain="development",
        )
        objects[RUNTIME_JVM] = (runtime_envelope, runtime_object)

        public_key = self.root / "keys/development.pub"
        public_key.parent.mkdir()
        shutil.copyfile(self.public_key, public_key)
        request = {
            "schemaVersion": 1,
            "requestType": "reuse-wave",
            "repository": REPOSITORY,
            "pullRequest": PULL_REQUEST,
            "repositoryRoot": str(repository),
            "repositoryRevision": revision,
            "artifactRoot": str(self.root),
            "requested": [{
                "product": RUNTIME_JVM.product,
                "component": RUNTIME_JVM.component,
                "phase": RUNTIME_JVM.phase,
                "target": RUNTIME_JVM.target,
            }],
            "versions": VERSIONS,
            "phaseAuthorities": [{
                "product": instance.product,
                "component": instance.component,
                "phase": instance.phase,
                "target": instance.target,
                "toolchainProfileDigest": NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                "flagsDigest": NOT_APPLICABLE_FLAGS_DIGEST,
                "outputSchemaVersion": 1,
            } for instance in closure],
            "contractEvidence": {
                "attestation": attestation.relative_to(self.root).as_posix(),
                "attestationSignature": attestation_signature.relative_to(self.root).as_posix(),
                "publicKey": public_key.relative_to(self.root).as_posix(),
                "expectedTrustDomain": "development",
                "keyring": None,
                "keysDirectory": None,
            },
            "runtimeValidationEvidence": [],
            "availableObjects": [{
                "product": instance.product,
                "component": instance.component,
                "phase": instance.phase,
                "target": instance.target,
                "buildKey": envelope["receipt"]["buildKey"],
                "receiptSha256": envelope["receiptSha256"],
                "objectSha256": envelope["objectSha256"],
                "objectPath": object_path.relative_to(self.root).as_posix(),
            } for instance, (envelope, object_path) in sorted(objects.items())],
            "catalogs": {
                "stable": [],
                "promotedMain": None,
                "samePr": None,
                "local": None,
            },
        }

        first = plan_reuse_wave(request)
        second = plan_reuse_wave(request)

        self.assertTrue(first["fullReuse"])
        self.assertEqual(first, second)
        self.assertEqual({"contract": [], "runtime": [], "sdk": []}, first["matrices"])
        self.assertFalse((self.root / "restored").exists())

    def test_reuse_resolution_bootstraps_contract_projection_after_metadata_restore(self) -> None:
        instance = PhaseInstanceId("runtime", "jvm", "binary", "jvm")
        inputs = all_inputs(instance)
        resolved = retained_chain(CONTRACT_METADATA, inputs)
        contract = resolved[CONTRACT_METADATA]
        bundle_path = f"outputs/codex-agent-contract-{VERSIONS['contract']}.zip"
        contract["receipt"]["outputs"] = [{
            "kind": "contract-bundle",
            "relativePath": bundle_path,
            "bytes": 1,
            "sha256": DIGEST_B,
        }]
        contract["receiptBytes"] = canonical_json_bytes(contract["receipt"])
        contract["receiptSha256"] = sha256_bytes(contract["receiptBytes"])
        projection = contract_projection.VerifiedContractProjection({
            "schemaVersion": 1,
            "receiptSha256": contract["receiptSha256"],
            "bundlePath": bundle_path,
            "bundleSha256": DIGEST_B,
            "manifestSha256": DIGEST_A,
            "contractVersion": VERSIONS["contract"],
            "contractDigest": DIGEST_A,
            "componentDigests": [{"component": "jvm", "sha256": DIGEST_B}],
        }, contract_projection._VERIFIED)
        inputs[instance]["contract_projection"] = projection
        runtime = envelope_for_plan(plan_for(instance, inputs, resolved))
        del inputs[instance]["contract_projection"]
        provider = mock.Mock(return_value=projection)

        result, _ = advance_reuse(
            [instance],
            inputs,
            [*resolved.values(), runtime],
            self.session(),
            contract_projection_provider=provider,
        )

        self.assertTrue(result["fullReuse"])
        provider.assert_called_once_with(instance, contract)

    def test_advance_reuse_rejects_invalid_inputs_at_its_public_boundary(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be a mapping"):
            advance_reuse(
                [CONTRACT_BINARY],
                {CONTRACT_BINARY: object()},
                [],
                self.session(),
            )
        with self.assertRaisesRegex(ValueError, "provider must be callable"):
            advance_reuse(
                [CONTRACT_BINARY],
                {CONTRACT_BINARY: phase_inputs(CONTRACT_BINARY)},
                [],
                self.session(),
                contract_projection_provider=object(),
            )

    def test_development_signed_stable_index_is_rejected(self) -> None:
        inputs = all_inputs(CONTRACT_BINARY)
        plan = plan_for(CONTRACT_BINARY, inputs, {})
        envelope, path = self.object_for_plan(plan, trust_domain="development")
        catalog = self.catalog("stable", [(envelope, path)], trust_domain="development")

        with self.assertRaisesRegex(ValueError, "release trust"):
            self.session(stable=[catalog])

    def test_release_attestation_authenticates_all_original_contract_phase_receipts(self) -> None:
        inputs = all_inputs(CONTRACT_METADATA)
        resolved, objects, payload, receipt, execution_closure = contract_execution_chain(self.root / "release-contract-chain", inputs)
        plan = plan_for(CONTRACT_METADATA, inputs, resolved)

        attestation_root = self.root / "release-attestation"
        build_contract_attestation(
            payload,
            receipt,
            self.release_signing,
            self.private_key,
            self.public_key,
            attestation_root,
            execution_closure=execution_closure,
            keyring=self.release_keyring,
            keys_directory=self.release_keys,
        )
        stem = f"codex-agent-contract-{VERSIONS['contract']}.attestation"
        attestation = attestation_root / f"{stem}.json"
        attestation_signature = attestation_root / f"{stem}.sig"
        indexed = self.catalog("promoted-main", [objects[CONTRACT_METADATA]])
        template = json.loads(indexed.manifest.read_bytes())
        sources = []
        for original, _ in objects.values():
            kind = {"binary": "contract-execution", "package": "maven", "validation": "validation", "metadata": "contract-bundle"}[
                original["receipt"]["phase"]]
            source = product_index.IndexEntrySource(
                original["receiptBytes"], next(output["relativePath"] for output in original["receipt"]["outputs"] if output["kind"] == kind))
            admission = product_index.release_attested_contract_admission(
                source, payload=payload, metadata_receipt=receipt,
                attestation=attestation, signature=attestation_signature,
                public_key=self.public_key, keyring=self.release_keyring,
                keys_directory=self.release_keys,
            )
            sources.append(product_index.IndexEntrySource(source.receipt_bytes, source.artifact_path, admission))
        index = product_index.build_product_index(
            sources, repository=REPOSITORY, context=template["context"],
            trust_domain="release", signing=self.release_signing,
            producer=template["producer"], stable_history=None,
        )
        manifest = self.root / "admitted-product-index.json"
        write_canonical_json(manifest, index)
        signature = sign_manifest(manifest, self.private_key, self.release_signing)
        catalog = RemoteCatalog(
            manifest,
            signature,
            {original["receipt"]["buildKey"]: path for original, path in objects.values()},
            keyring=indexed.keyring,
            keys_directory=indexed.keys_directory,
            contract_attestation=attestation,
            contract_attestation_signature=attestation_signature,
            contract_public_key=self.release_keys / "release-test.pub",
        )
        session = self.session(
            promoted_main=catalog,
            restore_root=self.root / "release-attested-restore",
        )
        for instance, (original, _) in objects.items():
            with self.subTest(phase=instance.phase):
                result = session.lookup("promoted-main", plan_for(instance, inputs, resolved))
                self.assertEqual(original["receiptBytes"], result.envelope["receiptBytes"])
                self.assertEqual(original["receiptSha256"], result.envelope["receiptSha256"])
                self.assertEqual(original["receipt"]["producer"], result.envelope["receipt"]["producer"])
                self.assertEqual("development", result.envelope["receipt"]["trustDomain"])

        missing_metadata = replace(catalog, objects={
            original["receipt"]["buildKey"]: path for instance, (original, path) in objects.items()
            if instance != CONTRACT_METADATA
        })
        with self.assertRaisesRegex(ReuseLookupError, "corrupt"):
            self.session(promoted_main=missing_metadata).lookup("promoted-main", plan_for(CONTRACT_BINARY, inputs, resolved))
        index_bytes = manifest.read_bytes()
        try:
            manifest.write_bytes(index_bytes + b" ")
            with self.assertRaisesRegex(ReuseLookupError, "corrupt"):
                session.lookup("promoted-main", plan_for(CONTRACT_BINARY, inputs, resolved))
        finally:
            manifest.write_bytes(index_bytes)

        # A signed index alone cannot substitute another same-key original producer.
        original, _ = objects[CONTRACT_BINARY]
        unrelated = copy.deepcopy(original)
        unrelated["receipt"]["producer"]["commit"] = "e" * 40
        unrelated["receiptBytes"] = canonical_json_bytes(unrelated["receipt"])
        unrelated["receiptSha256"] = sha256_bytes(unrelated["receiptBytes"])
        unrelated_receipt = self.root / "unrelated-receipt.json"
        unrelated_receipt.write_bytes(unrelated["receiptBytes"])
        stored = store_local_object(payload.parents[2] / "binary", unrelated_receipt, self.root / "unrelated-cache")
        unrelated["objectSha256"] = stored["objectSha256"]
        forged = self.catalog("promoted-main", [(unrelated, stored["path"]), objects[CONTRACT_METADATA]])
        forged_catalog = RemoteCatalog(
            forged.manifest, forged.signature, forged.objects,
            keyring=forged.keyring, keys_directory=forged.keys_directory,
            contract_attestation=attestation, contract_attestation_signature=attestation_signature,
            contract_public_key=self.public_key,
        )
        with self.assertRaisesRegex(ReuseLookupError, "corrupt"):
            self.session(promoted_main=forged_catalog).lookup("promoted-main", plan_for(CONTRACT_BINARY, inputs, resolved))

        # Even a correct selected receipt needs every original sibling in the signed closure.
        sibling = attestation_root / "execution-closure/receipts/validation.json"
        original_bytes = sibling.read_bytes()
        try:
            sibling.write_bytes(original_bytes + b" ")
            with self.assertRaisesRegex(ReuseLookupError, "corrupt"):
                session.lookup("promoted-main", plan_for(CONTRACT_BINARY, inputs, resolved))
        finally:
            sibling.write_bytes(original_bytes)

        missing = RemoteCatalog(
            catalog.manifest,
            catalog.signature,
            catalog.objects,
            keyring=indexed.keyring,
            keys_directory=indexed.keys_directory,
        )
        with self.assertRaisesRegex(ReuseLookupError, "corrupt"):
            self.session(promoted_main=missing).lookup("promoted-main", plan)

        binary_plan = plan_for(CONTRACT_BINARY, all_inputs(CONTRACT_BINARY), {})
        binary_envelope, binary_path = self.object_for_plan(
            binary_plan, trust_domain="development",
        )
        binary_catalog = self.catalog("promoted-main", [(binary_envelope, binary_path)])
        with self.assertRaisesRegex(ReuseLookupError, "corrupt"):
            self.session(promoted_main=binary_catalog).lookup("promoted-main", binary_plan)

    def test_release_signed_prerelease_index_is_not_a_stable_source(self) -> None:
        inputs = all_inputs(CONTRACT_BINARY)
        plan = plan_for(CONTRACT_BINARY, inputs, {})
        envelope, path = self.object_for_plan(plan, trust_domain="release")
        envelope["receipt"]["productVersion"] = "1.2.3-rc.1"
        catalog = self.catalog("stable", [(envelope, path)])

        with self.assertRaisesRegex(ValueError, "stable product identity"):
            self.session(stable=[catalog])

    def test_release_catalog_rejects_an_untracked_explicit_key(self) -> None:
        inputs = all_inputs(CONTRACT_BINARY)
        plan = plan_for(CONTRACT_BINARY, inputs, {})
        envelope, path = self.object_for_plan(plan, trust_domain="release")
        catalog = self.catalog("stable", [(envelope, path)])
        untracked = RemoteCatalog(
            catalog.manifest,
            catalog.signature,
            catalog.objects,
            public_key=self.public_key,
        )
        with self.assertRaisesRegex(ValueError, "tracked release key"):
            self.session(stable=[untracked])

    def test_same_pr_index_must_match_current_pr(self) -> None:
        inputs = all_inputs(CONTRACT_BINARY)
        plan = plan_for(CONTRACT_BINARY, inputs, {})
        envelope, path = self.object_for_plan(plan, trust_domain="development")
        catalog = self.catalog("same-pr", [(envelope, path)], pull_request=99)

        with self.assertRaisesRegex(ValueError, "current PR"):
            self.session(same_pr=catalog)

    def test_unavailable_stable_object_safely_falls_through_to_promoted(self) -> None:
        inputs = all_inputs(CONTRACT_BINARY)
        plan = plan_for(CONTRACT_BINARY, inputs, {})
        envelope, path = self.object_for_plan(plan, trust_domain="release")
        stable = self.catalog("stable", [(envelope, self.root / "not-downloaded.zip")])
        promoted = self.catalog("promoted-main", [(envelope, path)])

        result, receipts = advance_reuse(
            [CONTRACT_BINARY], inputs, [], self.session(stable=[stable], promoted_main=promoted)
        )

        phase = result["phases"][0]
        self.assertEqual("promoted-main", phase["source"])
        self.assertEqual({
            "kind": "promoted-main",
            "indexSha256": sha256_bytes(promoted.manifest.read_bytes()),
            "artifactName": self.entry(envelope)["artifactName"],
            "artifactSha256": self.entry(envelope)["artifactSha256"],
        }, phase["transportSource"])
        validate_transport({
            "schemaVersion": 1,
            "buildKey": phase["buildKey"],
            "receiptSha256": phase["receiptSha256"],
            "objectSha256": phase["objectSha256"],
            "source": phase["transportSource"],
            "consumer": {
                "kind": "local",
                "repository": REPOSITORY,
                "commit": COMMIT,
                "tree": TREE,
            },
        })
        self.assertEqual(
            [{"source": "stable", "reason": "artifact-unavailable"}],
            phase["misses"],
        )
        self.assertEqual(envelope["receiptBytes"], receipts[0]["receiptBytes"])

    def test_identical_inputs_reuse_across_commits_without_rewriting_producer(self) -> None:
        repository = self.root / "repository"
        repository.mkdir()

        def git(*arguments: str) -> str:
            return subprocess.run(
                ("git", *arguments),
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

        git("init", "-q")
        git("config", "user.email", "fixture@example.invalid")
        git("config", "user.name", "Fixture")
        direct = repository / "codex-agent-core/src/jvmMain/kotlin/example/Value.kt"
        direct.parent.mkdir(parents=True)
        direct.write_bytes(b"same direct input")
        (repository / "README.md").write_bytes(b"first unrelated byte")
        git("add", ".")
        git("commit", "-qm", "producer")
        producer_commit = git("rev-parse", "HEAD")
        producer_tree = git("rev-parse", "HEAD^{tree}")
        first_inventory = phase_git_inventory(repository, producer_commit, CONTRACT_BINARY)

        (repository / "README.md").write_bytes(b"second unrelated byte")
        git("add", "README.md")
        git("commit", "-qm", "consumer")
        consumer_commit = git("rev-parse", "HEAD")
        consumer_tree = git("rev-parse", "HEAD^{tree}")
        second_inventory = phase_git_inventory(repository, consumer_commit, CONTRACT_BINARY)
        self.assertNotEqual((producer_commit, producer_tree), (consumer_commit, consumer_tree))
        self.assertEqual(first_inventory, second_inventory)

        producer_inputs = all_inputs(CONTRACT_BINARY)
        producer_inputs[CONTRACT_BINARY]["inventory"] = first_inventory
        consumer_inputs = all_inputs(CONTRACT_BINARY)
        consumer_inputs[CONTRACT_BINARY]["inventory"] = second_inventory
        produced_plan = plan_for(CONTRACT_BINARY, producer_inputs, {})
        current_plan = plan_for(CONTRACT_BINARY, consumer_inputs, {})
        self.assertEqual(produced_plan, current_plan)
        produced, path = self.object_for_plan(
            produced_plan,
            trust_domain="release",
            producer_commit=producer_commit,
            producer_tree=producer_tree,
        )
        original_bytes = produced["receiptBytes"]
        catalog = self.catalog("stable", [(produced, path)])

        result, receipts = advance_reuse(
            [CONTRACT_BINARY],
            consumer_inputs,
            [],
            self.session(stable=[catalog]),
        )

        self.assertTrue(result["fullReuse"])
        self.assertEqual("stable", result["phases"][0]["source"])
        self.assertEqual(current_plan["buildKey"], result["phases"][0]["buildKey"])
        self.assertEqual(original_bytes, receipts[0]["receiptBytes"])
        self.assertEqual(producer_commit, receipts[0]["receipt"]["producer"]["commit"])
        self.assertEqual(producer_tree, receipts[0]["receipt"]["producer"]["tree"])
        self.assertNotIn(consumer_commit, receipts[0]["receiptBytes"].decode())
        self.assertNotIn(consumer_tree, receipts[0]["receiptBytes"].decode())
        validate_transport({
            "schemaVersion": 1,
            "buildKey": current_plan["buildKey"],
            "receiptSha256": receipts[0]["receiptSha256"],
            "objectSha256": receipts[0]["objectSha256"],
            "source": result["phases"][0]["transportSource"],
            "consumer": {
                "kind": "local",
                "repository": REPOSITORY,
                "commit": consumer_commit,
                "tree": consumer_tree,
            },
        })

    def test_corrupt_matching_remote_object_is_hard_without_fallback(self) -> None:
        inputs = all_inputs(CONTRACT_BINARY)
        plan = plan_for(CONTRACT_BINARY, inputs, {})
        envelope, valid = self.object_for_plan(plan, trust_domain="release")
        corrupt = self.root / "corrupt.zip"
        with zipfile.ZipFile(valid) as source:
            members = {member.filename: source.read(member) for member in source.infolist()}
        members["phase-receipt.json"] += b" "
        with warnings.catch_warnings(), zipfile.ZipFile(corrupt, "w") as target:
            warnings.simplefilter("ignore")
            for name, contents in sorted(members.items()):
                target.writestr(name, contents)
        stable = self.catalog("stable", [(envelope, corrupt)])
        promoted = self.catalog("promoted-main", [(envelope, valid)])
        session = self.session(stable=[stable], promoted_main=promoted)

        with mock.patch.object(product_reuse, "restore_local_object") as local_restore:
            with self.assertRaisesRegex(ReuseLookupError, "corrupt"):
                advance_reuse([CONTRACT_BINARY], inputs, [], session)
            local_restore.assert_not_called()

    def test_local_lookup_uses_restore_outcomes_without_reason_input(self) -> None:
        inputs = all_inputs(CONTRACT_BINARY)
        plan = plan_for(CONTRACT_BINARY, inputs, {})
        envelope, archive = self.object_for_plan(plan, trust_domain="development")
        cache = archive.parents[4]
        local = LocalCatalog(
            cache,
            {
                plan["buildKey"]: (
                    LocalCandidate(envelope["receiptSha256"], self.root / "restored"),
                ),
            },
        )

        result, receipts = advance_reuse(
            [CONTRACT_BINARY], inputs, [], self.session(local=local)
        )

        phase = result["phases"][0]
        self.assertEqual("local", phase["source"])
        self.assertEqual({
            "kind": "local",
            "cacheRelativePath": object_relative_path(
                plan["buildKey"], envelope["receiptSha256"],
            ),
        }, phase["transportSource"])
        self.assertEqual(
            [
                {"source": "stable", "reason": "no-index"},
                {"source": "promoted-main", "reason": "no-index"},
                {"source": "same-pr", "reason": "no-index"},
            ],
            phase["misses"],
        )
        self.assertEqual(envelope["receiptBytes"], receipts[0]["receiptBytes"])

    def test_local_corruption_is_a_safe_restore_outcome(self) -> None:
        inputs = all_inputs(CONTRACT_BINARY)
        plan = plan_for(CONTRACT_BINARY, inputs, {})
        envelope, archive = self.object_for_plan(plan, trust_domain="development")
        cache = archive.parents[4]
        archive.chmod(0o644)
        archive.write_bytes(b"not a product object")
        local = LocalCatalog(
            cache,
            {
                plan["buildKey"]: (
                    LocalCandidate(envelope["receiptSha256"], self.root / "not-restored"),
                ),
            },
        )

        result, receipts = advance_reuse(
            [CONTRACT_BINARY], inputs, [], self.session(local=local)
        )

        phase = result["phases"][0]
        self.assertEqual("build", phase["state"])
        self.assertEqual("local-corrupt", phase["misses"][-1]["reason"])
        self.assertEqual((), receipts)
        self.assertFalse((self.root / "not-restored").exists())

    def test_incompatible_runtime_release_line_is_rejected(self) -> None:
        inputs = all_inputs(RUNTIME_BINARY)
        flags_repository, flags_revision, flags_digest = self.runtime_flags_revision()
        inputs[RUNTIME_BINARY]["flags_digest"] = flags_digest
        inputs[RUNTIME_BINARY]["inventory"] = phase_git_inventory(
            flags_repository, flags_revision, RUNTIME_BINARY,
        )
        retained = retained_chain(CONTRACT_METADATA, inputs)
        contract = retained[CONTRACT_METADATA]
        bundle_path = f"outputs/codex-agent-contract-{VERSIONS['contract']}.zip"
        contract["receipt"]["outputs"] = [{
            "kind": "contract-bundle",
            "relativePath": bundle_path,
            "bytes": 1,
            "sha256": DIGEST_B,
        }]
        contract["receiptBytes"] = canonical_json_bytes(contract["receipt"])
        contract["receiptSha256"] = sha256_bytes(contract["receiptBytes"])
        inputs[RUNTIME_BINARY]["contract_projection"] = contract_projection.VerifiedContractProjection({
            "schemaVersion": 1,
            "receiptSha256": sha256_bytes(canonical_json_bytes(contract["receipt"])),
            "bundlePath": bundle_path,
            "bundleSha256": DIGEST_B,
            "manifestSha256": DIGEST_A,
            "contractVersion": VERSIONS["contract"],
            "contractDigest": DIGEST_A,
            "componentDigests": [{"component": "linux-x64", "sha256": DIGEST_B}],
        }, contract_projection._VERIFIED)
        plan = plan_for(RUNTIME_BINARY, inputs, retained)
        incompatible, path = self.object_for_plan(
            plan,
            trust_domain="release",
            release_version="9.9.9",
        )
        stable = self.catalog("stable", [(incompatible, path)])

        repackaged_plan = copy.deepcopy(plan)
        contract_upstream = repackaged_plan["inputs"]["upstreamArtifacts"][0]
        contract_upstream["contractProjection"].update({
            "contractVersion": "1.2.4",
            "receiptSha256": DIGEST_B,
            "bundlePath": "outputs/codex-agent-contract-1.2.4.zip",
            "bundleSha256": DIGEST_A,
            "manifestSha256": DIGEST_B,
        })
        self.assertEqual(plan["buildKey"], repackaged_plan["buildKey"])
        compatible = envelope_for_plan(plan)
        product_reuse._validate_envelope(compatible, expected_plan=repackaged_plan)
        incompatible_projection = copy.deepcopy(repackaged_plan)
        incompatible_projection["inputs"]["upstreamArtifacts"][0]["contractProjection"][
            "contractDigest"
        ] = DIGEST_B
        with self.assertRaisesRegex(ValueError, "build-key inputs"):
            product_reuse._validate_envelope(compatible, expected_plan=incompatible_projection)

        with self.assertRaisesRegex(ReuseLookupError, "corrupt"):
            advance_reuse(
                [RUNTIME_BINARY],
                inputs,
                list(retained.values()),
                self.session(stable=[stable]),
                repository_root=flags_repository,
                repository_revision=flags_revision,
            )

        forged = {instance: dict(values) for instance, values in inputs.items()}
        forged[RUNTIME_BINARY]["flags_digest"] = sha256_bytes(b"forged")
        with self.assertRaisesRegex(ValueError, "does not match"):
            advance_reuse(
                [RUNTIME_BINARY],
                forged,
                list(retained.values()),
                self.session(),
                repository_root=flags_repository,
                repository_revision=flags_revision,
            )

        forged = {instance: dict(values) for instance, values in inputs.items()}
        forged[RUNTIME_BINARY]["toolchain_profile_digest"] = sha256_bytes(b"forged")
        with self.assertRaisesRegex(ValueError, "toolchainProfileDigest does not match"):
            advance_reuse(
                [RUNTIME_BINARY],
                forged,
                list(retained.values()),
                self.session(),
                repository_root=flags_repository,
                repository_revision=flags_revision,
            )

        with (
            mock.patch.object(
                product_reuse,
                "verified_phase_toolchain_digest",
                wraps=product_reuse.verified_phase_toolchain_digest,
            ) as verified,
            self.assertRaisesRegex(ValueError, "exact lowercase Git object ID"),
        ):
            advance_reuse(
                [RUNTIME_BINARY],
                inputs,
                list(retained.values()),
                self.session(),
                repository_root=flags_repository,
                repository_revision="HEAD",
            )
        self.assertEqual(5, verified.call_count)
        verified.assert_called_with(
            flags_repository,
            "HEAD",
            RUNTIME_BINARY,
            inputs[RUNTIME_BINARY]["toolchain_profile_digest"],
        )

    def test_catalog_is_loaded_validated_and_verified_only_once_per_session(self) -> None:
        inputs = all_inputs(CONTRACT_METADATA)
        resolved: dict[PhaseInstanceId, dict[str, object]] = {}
        values = []
        for instance in (CONTRACT_BINARY, CONTRACT_PACKAGE, CONTRACT_VALIDATION, CONTRACT_METADATA):
            plan = plan_for(instance, inputs, resolved)
            envelope, path = self.object_for_plan(plan, trust_domain="release")
            resolved[instance] = envelope
            values.append((envelope, path))
        catalog = self.catalog("stable", values)

        with (
            mock.patch.object(
                product_index,
                "load_canonical_json_bytes",
                wraps=product_index.load_canonical_json_bytes,
            ) as load,
            mock.patch.object(
                product_index,
                "validate_product_index",
                wraps=product_index.validate_product_index,
            ) as validate,
            mock.patch.object(
                product_index,
                "_verify_signed_bytes",
                wraps=product_index._verify_signed_bytes,
            ) as verify,
        ):
            session = self.session(stable=[catalog])
            self.assertEqual(1, load.call_count)
            self.assertEqual(1, validate.call_count)
            self.assertEqual(1, verify.call_count)
            first, _ = advance_reuse([CONTRACT_METADATA], inputs, [], session)
            second, _ = advance_reuse([CONTRACT_METADATA], inputs, [], session)

        self.assertTrue(first["fullReuse"])
        self.assertEqual({"contract": [], "runtime": [], "sdk": []}, first["matrices"])
        self.assertEqual(first, second)
        self.assertEqual(1, validate.call_count)
        self.assertEqual(1, verify.call_count)

    def test_identical_local_restore_reuses_every_phase_and_emits_empty_matrices(self) -> None:
        inputs = all_inputs(CONTRACT_METADATA)
        resolved: dict[PhaseInstanceId, dict[str, object]] = {}
        candidates: dict[str, tuple[LocalCandidate, ...]] = {}
        cache = self.root / "shared-cache"
        pending = set(dependency_closure(CONTRACT_METADATA))
        while pending:
            ready = sorted(
                instance for instance in pending
                if all(dependency in resolved for dependency in phase_instance_dependencies(instance))
            )
            self.assertTrue(ready)
            for instance in ready:
                phase_plan = plan_for(instance, inputs, resolved)
                envelope, _ = self.object_for_plan(
                    phase_plan,
                    trust_domain="development",
                    cache_root=cache,
                )
                resolved[instance] = envelope
                candidates[phase_plan["buildKey"]] = (
                    LocalCandidate(
                        envelope["receiptSha256"],
                        self.root / "restored" / instance.phase,
                    ),
                )
                pending.remove(instance)

        result, receipts = advance_reuse(
            [CONTRACT_METADATA],
            inputs,
            [],
            self.session(local=LocalCatalog(cache, candidates)),
        )

        self.assertTrue(result["fullReuse"])
        self.assertEqual("complete", result["result"])
        self.assertEqual({"contract": [], "runtime": [], "sdk": []}, result["matrices"])
        self.assertEqual(
            {("reused", "local")},
            {(phase["state"], phase["source"]) for phase in result["phases"]},
        )
        self.assertEqual(len(dependency_closure(CONTRACT_METADATA)), len(receipts))

    def test_wrapper_only_wave_reuses_runtime_and_schedules_only_the_sdk_package(self) -> None:
        flags_repository, flags_revision, _ = self.runtime_flags_revision()
        inputs, resolved = retained_product_closure(
            PYTHON_PACKAGE,
            repository_root=flags_repository,
            repository_revision=flags_revision,
        )
        dependencies = [
            envelope for instance, envelope in resolved.items()
            if instance != PYTHON_PACKAGE
        ]

        ready_plans = []
        waiting, _ = advance_reuse(
            [PYTHON_PACKAGE], inputs, dependencies, self.session(),
            repository_root=flags_repository, repository_revision=flags_revision,
            runtime_validation_projection_provider=test_runtime_projection_provider,
            native_runtime_projection_provider=None,
            build_plan_consumer=lambda instance, plan: ready_plans.append((instance, plan)),
        )
        self.assertEqual([], ready_plans)
        self.assertEqual({"contract": [], "runtime": [], "sdk": []}, waiting["matrices"])
        self.assertEqual(["native-runtime-validation-evidence"],
                         [entry["kind"] for entry in waiting["continuationRequirements"]])
        self.assertEqual(5, len(waiting["continuationRequirements"][0]["dependencies"]))
        result, _ = advance_reuse(
            [PYTHON_PACKAGE],
            inputs,
            dependencies,
            self.session(),
            repository_root=flags_repository,
            repository_revision=flags_revision,
            runtime_validation_projection_provider=test_runtime_projection_provider,
            build_plan_consumer=lambda instance, plan: ready_plans.append((instance, plan)),
        )

        self.assertFalse(result["fullReuse"])
        self.assertEqual([], result["matrices"]["runtime"])
        self.assertEqual([], result["matrices"]["contract"])
        self.assertEqual(
            [(PYTHON_PACKAGE, plan_for(
                PYTHON_PACKAGE,
                inputs,
                {instance: envelope for instance, envelope in resolved.items() if instance != PYTHON_PACKAGE},
            ))],
            ready_plans,
        )
        self.assertEqual(
            [{
                "product": "sdk",
                "component": "python",
                "phase": "package",
                "target": "desktop",
                "buildKey": next(
                    phase["buildKey"] for phase in result["phases"]
                    if phase["product"] == "sdk" and phase["component"] == "python"
                ),
            }],
            result["matrices"]["sdk"],
        )

    def _external_sdk_runtime_fixture(self):
        # Planner envelopes only: the production caller must authenticate these
        # original objects/carriers before passing them to advance_reuse.
        repository, revision, _ = self.runtime_flags_revision()
        inputs, originals = retained_product_closure(
            PYTHON_PACKAGE, repository_root=repository, repository_revision=revision)
        dependencies = {instance for instance in phase_instance_dependencies(PYTHON_PACKAGE)
                        if instance.product == "runtime"}
        external = [originals[instance] for instance in sorted(dependencies)]
        current_versions = {**VERSIONS, "runtime-release": "2.3.5"}
        current_inputs = {instance: {**values, "versions": current_versions} for instance, values in inputs.items()}
        options = dict(repository_root=repository, repository_revision=revision,
                       sdk_runtime_receipts=external, sdk_default_runtime_version=VERSIONS["runtime-release"],
                       runtime_validation_projection_provider=test_runtime_projection_provider)
        return current_inputs, originals, options

    def test_sdk_pinned_old_default_does_not_schedule_current_runtime_after_patch_bump(self) -> None:
        inputs, originals, options = self._external_sdk_runtime_fixture()
        before = copy.deepcopy(originals)
        inputs = {instance: values for instance, values in inputs.items() if instance.product != "runtime"}
        available = [envelope for instance, envelope in originals.items() if instance.product == "contract"]
        plans = []
        result, retained = advance_reuse([PYTHON_PACKAGE], inputs, available, self.session(), **options,
            build_plan_consumer=lambda instance, plan: plans.append((instance, plan)))
        self.assertEqual([], result["matrices"]["runtime"])
        self.assertEqual([], result["matrices"]["contract"])
        self.assertEqual([PYTHON_PACKAGE], [instance for instance, _ in plans])
        self.assertFalse(any(phase["product"] == "runtime" for phase in result["phases"]))
        self.assertEqual(plan_for(PYTHON_PACKAGE, inputs, originals), plans[0][1])
        self.assertEqual({item["receiptSha256"] for item in available},
                         {item["receiptSha256"] for item in retained})
        # The unchanged SDK package is a full no-op when its original envelope
        # is also supplied; external Runtime dependencies are not new work.
        complete, returned = advance_reuse([PYTHON_PACKAGE], inputs,
            [*available, originals[PYTHON_PACKAGE]], self.session(), **options)
        self.assertTrue(complete["fullReuse"])
        self.assertEqual({"contract": [], "runtime": [], "sdk": []}, complete["matrices"])
        self.assertIn(originals[PYTHON_PACKAGE], returned)
        self.assertEqual(before, originals)

    def test_current_runtime_aggregate_and_sdk_old_default_remain_separate_selections(self) -> None:
        inputs, originals, options = self._external_sdk_runtime_fixture()
        before = copy.deepcopy(originals)
        aggregate = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
        available = [envelope for instance, envelope in originals.items()
                     if instance not in {aggregate, PYTHON_PACKAGE}]
        plans = {}
        result, retained = advance_reuse([aggregate, PYTHON_PACKAGE], inputs, available, self.session(), **options,
            build_plan_consumer=lambda instance, plan: plans.__setitem__(instance, plan))
        self.assertEqual({aggregate, PYTHON_PACKAGE}, set(plans))
        self.assertEqual("2.3.5", plans[aggregate]["inputs"]["versionIdentity"])
        self.assertNotEqual(originals[aggregate]["receipt"]["buildKey"], plans[aggregate]["buildKey"])
        embedded = [record for record in plans[PYTHON_PACKAGE]["inputs"]["upstreamArtifacts"]
                    if record["product"] == "runtime" and record["component"] == "runtime-aggregate"]
        self.assertEqual(1, len(embedded))
        self.assertEqual(originals[aggregate]["receipt"]["buildKey"], embedded[0]["buildKey"])
        self.assertEqual(output_inventory_digest(originals[aggregate]["receipt"]["outputs"]),
                         embedded[0]["outputsDigest"])
        self.assertEqual(["runtime-aggregate"], [row["component"] for row in result["matrices"]["runtime"]])
        self.assertEqual(["python"], [row["component"] for row in result["matrices"]["sdk"]])
        self.assertEqual({item["receiptSha256"] for item in available},
                         {item["receiptSha256"] for item in retained})
        self.assertEqual(before, originals)

    def test_sdk_external_runtime_missing_duplicate_wrong_default_and_unpaired_inputs_reject(self) -> None:
        inputs, originals, options = self._external_sdk_runtime_fixture()
        before = copy.deepcopy(originals)
        inputs = {instance: values for instance, values in inputs.items() if instance.product != "runtime"}
        available = [envelope for instance, envelope in originals.items() if instance.product == "contract"]
        external = options["sdk_runtime_receipts"]
        cases = (
            {"sdk_runtime_receipts": external[:-1]},
            {"sdk_runtime_receipts": [*external, external[0]]},
            {"sdk_runtime_receipts": [*external, originals[CONTRACT_METADATA]]},
            {"sdk_default_runtime_version": "2.3.5"},
            {"sdk_default_runtime_version": "2.3.4-rc.1"},
            {"sdk_default_runtime_version": None},
            {"sdk_runtime_receipts": None},
        )
        for changes in cases:
            with self.subTest(changes=tuple(changes)), self.assertRaises(ValueError):
                advance_reuse([PYTHON_PACKAGE], inputs, available, self.session(), **{**options, **changes})
        self.assertEqual(before, originals)

    def test_package_and_validation_only_waves_do_not_schedule_binary_work(self) -> None:
        flags_repository, flags_revision, _ = self.runtime_flags_revision()
        for requested in (RUNTIME_PACKAGE, RUNTIME_VALIDATION):
            inputs, resolved = retained_product_closure(
                requested,
                repository_root=flags_repository,
                repository_revision=flags_revision,
            )
            dependencies = [
                envelope for instance, envelope in resolved.items()
                if instance != requested
            ]
            with self.subTest(phase=requested.phase):
                result, _ = advance_reuse(
                    [requested],
                    inputs,
                    dependencies,
                    self.session(),
                    repository_root=flags_repository,
                    repository_revision=flags_revision,
                )
                self.assertEqual([], result["matrices"]["contract"])
                self.assertEqual([], result["matrices"]["sdk"])
                self.assertEqual(
                    [requested.phase],
                    [entry["phase"] for entry in result["matrices"]["runtime"]],
                )
                self.assertFalse(any(
                    phase["state"] == "build" and phase["phase"] == "binary"
                    for phase in result["phases"]
                ))

    def test_native_sdk_metadata_waits_for_exact_five_host_proofs_without_scheduling_work(self) -> None:
        from ci.tests.test_product_plan import verified_sdk_projections
        repository, revision, _ = self.runtime_flags_revision()
        inputs, retained = retained_product_closure(PYTHON_METADATA, repository_root=repository, repository_revision=revision)
        options = dict(repository_root=repository, repository_revision=revision,
                       runtime_validation_projection_provider=test_runtime_projection_provider)
        waiting, originals = advance_reuse([PYTHON_METADATA], inputs, list(retained.values()), self.session(),
                                           **options, sdk_validation_projection_provider=None)
        self.assertFalse(waiting["fullReuse"])
        self.assertTrue(all(not values for values in waiting["matrices"].values()))
        self.assertEqual("sdk-validation-evidence", waiting["continuationRequirements"][0]["kind"])
        self.assertEqual(5, len(waiting["continuationRequirements"][0]["dependencies"]))
        def provider(instance, envelopes, package):
            self.assertEqual(PYTHON_METADATA, instance)
            self.assertEqual(retained[PYTHON_PACKAGE], package)
            self.assertEqual(5, len(envelopes))
            return verified_sdk_projections(instance, [package["receipt"], *[value["receipt"] for value in envelopes]])
        complete, after = advance_reuse([PYTHON_METADATA], inputs, list(retained.values()), self.session(),
                                       **options, sdk_validation_projection_provider=provider)
        self.assertTrue(complete["fullReuse"])
        self.assertEqual([], complete["continuationRequirements"])
        self.assertTrue(all(not values for values in complete["matrices"].values()))
        self.assertEqual({entry["receiptSha256"] for entry in retained.values()}, {entry["receiptSha256"] for entry in after})
        forged = {identity: dict(value) for identity, value in inputs.items()}
        forged[PYTHON_METADATA]["sdk_validation_projections"] = ()
        with self.assertRaisesRegex(ValueError, "Callers cannot supply"):
            advance_reuse([PYTHON_METADATA], forged, [], self.session(), **options)

    def test_one_byte_direct_input_mutation_invalidates_only_the_first_owner_wave(self) -> None:
        flags_repository, flags_revision, _ = self.runtime_flags_revision()
        relative = "codex-agent-bindings/python/src/codex_agent/_ffi.py"
        source = self.root / relative
        source.parent.mkdir(parents=True)
        source.write_bytes(b"a")
        subprocess.run(("git", "init", "-q"), cwd=self.root, check=True)
        subprocess.run(("git", "config", "user.email", "fixture@example.invalid"), cwd=self.root, check=True)
        subprocess.run(("git", "config", "user.name", "Fixture"), cwd=self.root, check=True)
        subprocess.run(("git", "add", relative), cwd=self.root, check=True)
        subprocess.run(("git", "commit", "-qm", "first"), cwd=self.root, check=True)
        first_revision = subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=self.root, check=True, capture_output=True, text=True,
        ).stdout.strip()
        first_inventory = phase_git_inventory(self.root, first_revision, PYTHON_PACKAGE)
        selected = classify_paths((relative,)).instances
        self.assertEqual(
            {PYTHON_PACKAGE, PYTHON_METADATA, *(
                PhaseInstanceId("sdk", "python", "validation", target)
                for target in ("linux-arm64", "linux-x64", "macos-arm64", "macos-x64", "windows-x64")
            )},
            set(selected),
        )
        first_inputs, first_resolved = retained_product_closure(
            PYTHON_METADATA,
            {PYTHON_PACKAGE: first_inventory},
            repository_root=flags_repository,
            repository_revision=flags_revision,
        )
        first_plan = plan_for(PYTHON_PACKAGE, first_inputs, first_resolved)

        source.write_bytes(b"b")
        subprocess.run(("git", "add", relative), cwd=self.root, check=True)
        subprocess.run(("git", "commit", "-qm", "second"), cwd=self.root, check=True)
        second_revision = subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=self.root, check=True, capture_output=True, text=True,
        ).stdout.strip()
        second_inputs = {
            instance: dict(values) for instance, values in first_inputs.items()
        }
        second_inputs[PYTHON_PACKAGE]["inventory"] = phase_git_inventory(
            self.root, second_revision, PYTHON_PACKAGE,
        )
        dependencies = [
            envelope for instance, envelope in first_resolved.items()
            if instance != PYTHON_PACKAGE
        ]
        result, retained = advance_reuse(
            selected,
            second_inputs,
            dependencies,
            self.session(),
            repository_root=flags_repository,
            repository_revision=flags_revision,
            runtime_validation_projection_provider=test_runtime_projection_provider,
        )

        owner = next(
            phase for phase in result["phases"]
            if (phase["product"], phase["component"], phase["phase"], phase["target"])
            == ("sdk", "python", "package", "desktop")
        )
        self.assertNotEqual(first_plan["buildKey"], owner["buildKey"])
        self.assertEqual("build", owner["state"])
        self.assertEqual(1, sum(phase["state"] == "build" for phase in result["phases"]))
        self.assertTrue(all(
            phase["state"] == "retained"
            for phase in result["phases"]
            if phase is not owner and phase["phase"] not in {"validation", "metadata"}
        ))
        self.assertTrue(all(
            phase["state"] == "waiting"
            for phase in result["phases"]
            if phase["product"] == "sdk"
            and phase["component"] == "python"
            and phase["phase"] in {"validation", "metadata"}
        ))
        self.assertEqual([], result["matrices"]["contract"])
        self.assertEqual([], result["matrices"]["runtime"])
        self.assertEqual(["package"], [entry["phase"] for entry in result["matrices"]["sdk"]])

        rebuilt_package = envelope_for_plan(
            plan_for(PYTHON_PACKAGE, second_inputs, first_resolved)
        )
        successor_result, _ = advance_reuse(
            selected,
            second_inputs,
            [*retained, rebuilt_package],
            self.session(),
            repository_root=flags_repository,
            repository_revision=flags_revision,
            runtime_validation_projection_provider=test_runtime_projection_provider,
        )
        self.assertEqual(
            ["validation"] * 5,
            [entry["phase"] for entry in successor_result["matrices"]["sdk"]],
        )
        self.assertEqual(
            "waiting",
            next(
                phase["state"] for phase in successor_result["phases"]
                if phase["product"] == "sdk"
                and phase["component"] == "python"
                and phase["phase"] == "metadata"
            ),
        )

    def test_stable_catalogs_cannot_redefine_one_product_version(self) -> None:
        first_inputs = all_inputs(CONTRACT_BINARY)
        first_plan = plan_for(CONTRACT_BINARY, first_inputs, {})
        first, first_path = self.object_for_plan(first_plan, trust_domain="release")

        second_inputs = copy.deepcopy(first_inputs)
        second_inputs[CONTRACT_BINARY]["inventory"][0]["sha256"] = DIGEST_B
        second_plan = plan_for(CONTRACT_BINARY, second_inputs, {})
        second, second_path = self.object_for_plan(second_plan, trust_domain="release", binary_salt=b"changed contract")
        self.assertNotEqual(first_plan["buildKey"], second_plan["buildKey"])

        with self.assertRaisesRegex(ValueError, "Stable product identity"):
            self.session(stable=[
                self.catalog("stable", [(first, first_path)]),
                self.catalog("stable", [(second, second_path)]),
            ])

    def test_contract_catalog_consistency_authenticates_both_execution_objects(self) -> None:
        inputs = all_inputs(CONTRACT_BINARY)
        plan = plan_for(CONTRACT_BINARY, inputs, {})
        first, first_path = self.object_for_plan(plan, trust_domain="release")
        second, second_path = self.object_for_plan(
            plan, trust_domain="release", execution_context=b"another-run",
            producer_commit="c" * 40, producer_tree="d" * 40,
        )
        self.assertNotEqual(first["receipt"]["outputs"], second["receipt"]["outputs"])
        originals = (first_path.read_bytes(), second_path.read_bytes(), first["receiptBytes"], second["receiptBytes"])
        stable = self.catalog("stable", [(first, first_path)])
        for source in ("stable", "promoted-main"):
            with self.subTest(source=source):
                other = self.catalog(source, [(second, second_path)])
                arguments = {"stable": [stable, other]} if source == "stable" else {"stable": [stable], "promoted_main": other}
                session = self.session(**arguments)
                hit = session.lookup(source, plan)
                self.assertEqual(first["receiptBytes"] if source == "stable" else second["receiptBytes"], hit.envelope["receiptBytes"])
        self.assertEqual(originals, (first_path.read_bytes(), second_path.read_bytes(), first["receiptBytes"], second["receiptBytes"]))
        self.session(stable=[
            self.catalog("stable", [(first, first_path)], execution_artifact=True),
            self.catalog("stable", [(second, second_path)], execution_artifact=True),
        ])
        for path in (None, first_path):
            with self.subTest(invalid_object=path), self.assertRaises((ValueError, CacheObjectError)):
                self.session(stable=[stable], promoted_main=self.catalog("promoted-main", [(second, path)]))
        changed, changed_path = self.object_for_plan(plan, trust_domain="release", binary_salt=b"changed-product")
        with self.assertRaisesRegex(ValueError, "conflict"):
            self.session(stable=[stable], promoted_main=self.catalog("promoted-main", [(changed, changed_path)]))

    def test_safe_misses_emit_only_the_ready_wave_and_preserve_predecessors(self) -> None:
        inputs = all_inputs(CONTRACT_METADATA)
        session = self.session()
        first, receipts = advance_reuse([CONTRACT_METADATA], inputs, [], session)
        self.assertEqual("build", next(
            phase["state"] for phase in first["phases"] if phase["phase"] == "binary"
        ))
        self.assertEqual(
            ["no-index", "no-index", "no-index", "local-missing"],
            [miss["reason"] for miss in next(
                phase["misses"] for phase in first["phases"] if phase["phase"] == "binary"
            )],
        )
        self.assertEqual((), receipts)

        binary = envelope_for_plan(plan_for(CONTRACT_BINARY, inputs, {}))
        second, receipts = advance_reuse([CONTRACT_METADATA], inputs, [binary], session)
        self.assertEqual("build", next(
            phase["state"] for phase in second["phases"] if phase["phase"] == "package"
        ))
        self.assertIs(binary, receipts[0])
        self.assertIs(binary["receiptBytes"], receipts[0]["receiptBytes"])


if __name__ == "__main__":
    unittest.main()
