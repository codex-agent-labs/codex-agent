from __future__ import annotations

import copy
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
from ci.products.inventory import canonical_json_bytes, sha256_bytes, write_canonical_json
from ci.products.plan import plan_phase
from ci.products.receipt import output_inventory_digest, validate_phase_receipt, write_output_manifest
from ci.products.registry import (
    NATIVE_TARGETS,
    PhaseInstanceId,
    phase_instance_dependencies,
    required_contract_components,
)
from ci.products.restore import object_relative_path, store_local_object, validate_transport
from ci.products.runtime_flags import load_runtime_binary_flags
from ci.products.selection import classify_paths, phase_git_inventory
from ci.products.toolchain import PROFILE_SHAPES, PROFILE_TOOL_NAMES
from ci.products.reuse import (
    LocalCandidate,
    LocalCatalog,
    LookupSession,
    RemoteCatalog,
    ReuseLookupError,
    advance_reuse,
)
from ci.products.signatures import generate_development_key, sign_manifest


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
            else DIGEST_A
        ),
        "flags_digest": (
            RUNTIME_FLAGS_DIGESTS[instance.component]
            if instance.product == "runtime"
            and instance.component in NATIVE_TARGETS
            and instance.phase == "binary"
            else DIGEST_B
        ),
    }


def all_inputs(instance: PhaseInstanceId) -> dict[PhaseInstanceId, dict[str, object]]:
    return {value: phase_inputs(value) for value in dependency_closure(instance)}


def product_version(product: str) -> str:
    return VERSIONS["runtime-release"] if product == "runtime" else VERSIONS[product]


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
        "outputs": [{
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
    return plan_phase(
        instance,
        upstream_receipts=[
            resolved[dependency]["receipt"]
            for dependency in phase_instance_dependencies(instance)
        ],
        **inputs[instance],
    )


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
            }, contract_projection._VERIFIED)

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
    ) -> tuple[dict[str, object], Path]:
        self.counter += 1
        root = self.root / f"object-{self.counter}"
        stage = root / "stage"
        name = f"{plan['component']}-{plan['phase']}-{plan['target']}.bin"
        payload = stage / "outputs" / name
        payload.parent.mkdir(parents=True)
        payload.write_bytes(str(plan["buildKey"]).encode())
        version = release_version or product_version(str(plan["product"]))
        manifest = write_output_manifest(
            stage,
            plan["product"],
            plan["component"],
            plan["phase"],
            plan["target"],
            version,
            {"artifact": "outputs"},
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

    def test_development_signed_stable_index_is_rejected(self) -> None:
        inputs = all_inputs(CONTRACT_BINARY)
        plan = plan_for(CONTRACT_BINARY, inputs, {})
        envelope, path = self.object_for_plan(plan, trust_domain="development")
        catalog = self.catalog("stable", [(envelope, path)], trust_domain="development")

        with self.assertRaisesRegex(ValueError, "release trust"):
            self.session(stable=[catalog])

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
            "bundlePath": "outputs/repackaged-contract.zip",
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
        verified.assert_called_once()

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

        result, _ = advance_reuse(
            [PYTHON_PACKAGE],
            inputs,
            dependencies,
            self.session(),
            repository_root=flags_repository,
            repository_revision=flags_revision,
        )

        self.assertFalse(result["fullReuse"])
        self.assertEqual([], result["matrices"]["runtime"])
        self.assertEqual([], result["matrices"]["contract"])
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
        second, second_path = self.object_for_plan(second_plan, trust_domain="release")
        self.assertNotEqual(first_plan["buildKey"], second_plan["buildKey"])

        with self.assertRaisesRegex(ValueError, "Stable product identity"):
            self.session(stable=[
                self.catalog("stable", [(first, first_path)]),
                self.catalog("stable", [(second, second_path)]),
            ])

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
