from __future__ import annotations

import copy
from pathlib import Path
import subprocess
import tempfile
import unittest

import ci.products.contract_projection as contract_projection
from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, sha256_bytes, write_canonical_json
from ci.products.plan import (
    plan_phase,
    verified_phase_flags_digest,
    verified_phase_toolchain_digest,
    verify_build_key_output_consistency,
)
from ci.products.receipt import compute_build_key, output_inventory_digest
from ci.products.registry import (
    NATIVE_TARGETS,
    RUNTIME_ADAPTERS,
    PhaseInstanceId,
    phase_instance_dependencies,
    required_contract_components,
)
from ci.products.runtime_flags import load_runtime_binary_flags
from ci.products.selection import phase_git_inventory
from ci.products.toolchain import PROFILE_SHAPES, PROFILE_TOOL_NAMES


DIGEST_A = sha256_bytes(b"a")
DIGEST_B = sha256_bytes(b"b")
DIGEST_C = sha256_bytes(b"c")
VERSIONS = {
    "contract": "1.2.3",
    "runtime-compatibility": "2.3.0",
    "runtime-release": "2.3.4",
    "sdk": "3.4.5",
}
PRODUCER = {
    "repository": "owner/repository",
    "workflowPath": ".github/workflows/products.yml",
    "commit": "a" * 40,
    "tree": "b" * 40,
    "event": "pull_request",
    "runId": 1,
    "runAttempt": 1,
    "pullRequest": 2,
}


def file_record(name: str = "input.txt", digest: str = DIGEST_A) -> dict[str, object]:
    return {"relativePath": name, "bytes": 1, "sha256": digest}


def receipt(
    instance: PhaseInstanceId,
    *,
    output_digest: str = DIGEST_B,
    producer: dict[str, object] = PRODUCER,
) -> dict[str, object]:
    inputs = {
        "inventory": [file_record()],
        "phaseInputDigest": sha256_bytes(canonical_json_bytes([file_record()])),
        "versionIdentity": (
            VERSIONS["runtime-compatibility"]
            if instance.product == "runtime" and instance.component != "runtime-aggregate"
            else VERSIONS["runtime-release"]
            if instance.product == "runtime"
            else VERSIONS[instance.product]
        ),
        "upstreamArtifacts": [],
        "toolchainProfileDigest": DIGEST_A,
        "flagsDigest": DIGEST_B,
        "outputSchemaVersion": 1,
    }
    return {
        "schemaVersion": 1,
        "product": instance.product,
        "component": instance.component,
        "phase": instance.phase,
        "target": instance.target,
        "productVersion": (
            VERSIONS["runtime-release"] if instance.product == "runtime" else VERSIONS[instance.product]
        ),
        "buildKey": compute_build_key(
            product=instance.product,
            component=instance.component,
            phase=instance.phase,
            target=instance.target,
            inputs=inputs,
        ),
        "inputs": inputs,
        "outputs": [{
            "kind": "contract-bundle" if instance == PhaseInstanceId(
                "contract", "contract", "metadata", "common"
            ) else "artifact",
            "relativePath": f"outputs/codex-agent-contract-{VERSIONS['contract']}.zip"
            if instance == PhaseInstanceId("contract", "contract", "metadata", "common")
            else "outputs/artifact.bin",
            "bytes": 1,
            "sha256": output_digest,
        }],
        "producer": producer,
        "trustDomain": "development",
        "result": "success",
    }


def upstreams(instance: PhaseInstanceId) -> list[dict[str, object]]:
    return [receipt(dependency) for dependency in phase_instance_dependencies(instance)]


def verified_projection(
    instance: PhaseInstanceId,
    *,
    bundle_digest: str = DIGEST_B,
    component_digest: str = DIGEST_C,
    contract_receipt: dict[str, object] | None = None,
) -> contract_projection.VerifiedContractProjection | None:
    components = required_contract_components(instance)
    if not components:
        return None
    if contract_receipt is None:
        contract_receipt = receipt(
            PhaseInstanceId("contract", "contract", "metadata", "common"),
            output_digest=bundle_digest,
        )
    return contract_projection.VerifiedContractProjection({
        "schemaVersion": 1,
        "receiptSha256": sha256_bytes(canonical_json_bytes(contract_receipt)),
        "bundlePath": f"outputs/codex-agent-contract-{VERSIONS['contract']}.zip",
        "bundleSha256": bundle_digest,
        "manifestSha256": DIGEST_A,
        "contractVersion": VERSIONS["contract"],
        "contractDigest": DIGEST_A,
        "componentDigests": [
            {"component": component, "sha256": component_digest}
            for component in components
        ],
    }, contract_projection._VERIFIED)


def plan(
    instance: PhaseInstanceId,
    *,
    versions: dict[str, str] = VERSIONS,
    upstream_receipts: list[dict[str, object]] | None = None,
    inventory: list[dict[str, object]] | None = None,
    projection: contract_projection.VerifiedContractProjection | None = None,
    flags_digest: str = DIGEST_B,
) -> dict[str, object]:
    selected_upstreams = upstreams(instance) if upstream_receipts is None else upstream_receipts
    if projection is None:
        contract_receipt = next((
            value for value in selected_upstreams
            if (
                value["product"], value["component"], value["phase"], value["target"]
            ) == ("contract", "contract", "metadata", "common")
        ), None)
        projection = verified_projection(instance, contract_receipt=contract_receipt)
    return plan_phase(
        instance,
        inventory=[file_record()] if inventory is None else inventory,
        versions=versions,
        upstream_receipts=selected_upstreams,
        toolchain_profile_digest=DIGEST_A,
        flags_digest=flags_digest,
        contract_projection=projection,
    )


def toolchain_profile(profile_id: str) -> dict[str, object]:
    return {
        "schemaVersion": 2,
        "id": profile_id,
        "producers": [
            {
                "role": role,
                "runner": {"os": os_name, "arch": arch},
                "tools": [
                    {"name": name, "identity": f"fixture-{profile_id}-{role}-{name}"}
                    for name in PROFILE_TOOL_NAMES[(profile_id, role)]
                ],
            }
            for role, os_name, arch in PROFILE_SHAPES[profile_id]
        ],
    }


class ProductPlanTest(unittest.TestCase):
    def test_native_toolchain_is_derived_from_the_exact_target_profile_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            profiles = root / "gradle/release/toolchains/runtime"
            profiles.mkdir(parents=True)
            for target in NATIVE_TARGETS:
                write_canonical_json(profiles / f"{target}.json", toolchain_profile(target))
            subprocess.run(("git", "init", "-q"), cwd=root, check=True)
            subprocess.run(("git", "config", "user.email", "fixture@example.invalid"), cwd=root, check=True)
            subprocess.run(("git", "config", "user.name", "Fixture"), cwd=root, check=True)
            subprocess.run(("git", "add", "."), cwd=root, check=True)
            subprocess.run(("git", "commit", "-qm", "profiles"), cwd=root, check=True)
            revision = subprocess.run(
                ("git", "rev-parse", "HEAD"), cwd=root, check=True, capture_output=True, text=True,
            ).stdout.strip()

            changed = []
            before = {}
            for target in NATIVE_TARGETS:
                instance = PhaseInstanceId("runtime", target, "binary", target)
                digest = sha256_bytes((profiles / f"{target}.json").read_bytes())
                before[target] = verified_phase_toolchain_digest(root, revision, instance, digest)
                self.assertNotIn(
                    f"gradle/release/toolchains/runtime/{target}.json",
                    {record["relativePath"] for record in phase_git_inventory(root, revision, instance)},
                )

            value = toolchain_profile("linux-x64")
            value["producers"][0]["tools"][0]["identity"] += "-changed"
            write_canonical_json(profiles / "linux-x64.json", value)
            subprocess.run(("git", "add", "."), cwd=root, check=True)
            subprocess.run(("git", "commit", "-qm", "one profile"), cwd=root, check=True)
            next_revision = subprocess.run(
                ("git", "rev-parse", "HEAD"), cwd=root, check=True, capture_output=True, text=True,
            ).stdout.strip()
            for target in NATIVE_TARGETS:
                instance = PhaseInstanceId("runtime", target, "binary", target)
                digest = sha256_bytes((profiles / f"{target}.json").read_bytes())
                after = verified_phase_toolchain_digest(root, next_revision, instance, digest)
                if after != before[target]:
                    changed.append(target)
            self.assertEqual(["linux-x64"], changed)
            with self.assertRaisesRegex(ValueError, "does not match"):
                verified_phase_toolchain_digest(
                    root,
                    next_revision,
                    PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64"),
                    DIGEST_A,
                )
            with self.assertRaisesRegex(ValueError, "exact lowercase Git object ID"):
                verified_phase_toolchain_digest(
                    root,
                    "HEAD",
                    PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64"),
                    sha256_bytes((profiles / "linux-x64.json").read_bytes()),
                )

    def test_native_flags_are_derived_from_the_exact_revision_and_invalidate_one_target(self) -> None:
        authority = Path(__file__).resolve().parents[2] / (
            "codex-agent-runtime-desktop/native/c-api/binary-flags.json"
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            path = root / "codex-agent-runtime-desktop/native/c-api/binary-flags.json"
            path.parent.mkdir(parents=True)
            path.write_bytes(authority.read_bytes())
            subprocess.run(("git", "init", "-q"), cwd=root, check=True)
            subprocess.run(("git", "config", "user.email", "fixture@example.invalid"), cwd=root, check=True)
            subprocess.run(("git", "config", "user.name", "Fixture"), cwd=root, check=True)
            subprocess.run(("git", "add", "."), cwd=root, check=True)
            subprocess.run(("git", "commit", "-qm", "first"), cwd=root, check=True)
            first_revision = subprocess.run(
                ("git", "rev-parse", "HEAD"), cwd=root, check=True, capture_output=True, text=True,
            ).stdout.strip()
            first = load_runtime_binary_flags(path)

            value = load_canonical_json_bytes(path.read_bytes())
            next(record for record in value["targets"] if record["target"] == "linux-x64")[
                "linkerArguments"
            ].append("-Wl,--gc-sections")
            write_canonical_json(path, value)
            subprocess.run(("git", "add", "."), cwd=root, check=True)
            subprocess.run(("git", "commit", "-qm", "second"), cwd=root, check=True)
            second_revision = subprocess.run(
                ("git", "rev-parse", "HEAD"), cwd=root, check=True, capture_output=True, text=True,
            ).stdout.strip()
            second = load_runtime_binary_flags(path)

            changed = []
            for target in NATIVE_TARGETS:
                instance = PhaseInstanceId("runtime", target, "binary", target)
                first_digest = verified_phase_flags_digest(
                    root, first_revision, instance, first[target].digest,
                )
                second_digest = verified_phase_flags_digest(
                    root, second_revision, instance, second[target].digest,
                )
                self.assertNotIn(
                    "codex-agent-runtime-desktop/native/c-api/binary-flags.json",
                    {record["relativePath"] for record in phase_git_inventory(root, second_revision, instance)},
                )
                first_plan = plan(instance, flags_digest=first_digest)
                second_plan = plan(instance, flags_digest=second_digest)
                if first_plan["buildKey"] != second_plan["buildKey"]:
                    changed.append(target)
            self.assertEqual(["linux-x64"], changed)
            with self.assertRaisesRegex(ValueError, "does not match"):
                verified_phase_flags_digest(
                    root,
                    second_revision,
                    PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64"),
                    DIGEST_A,
                )
            with self.assertRaisesRegex(ValueError, "exact lowercase Git object ID"):
                verified_phase_flags_digest(
                    root,
                    "HEAD",
                    PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64"),
                    second["linux-x64"].digest,
                )

    def test_plan_binds_canonical_inventory_and_exact_sorted_upstreams(self) -> None:
        instance = PhaseInstanceId("runtime", "jvm", "validation", "linux-x64")
        supplied = list(reversed(upstreams(instance)))

        result = plan(instance, upstream_receipts=supplied)

        self.assertEqual(
            {
                "schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs",
            },
            set(result),
        )
        self.assertEqual(
            sha256_bytes(canonical_json_bytes([file_record()])),
            result["inputs"]["phaseInputDigest"],
        )
        self.assertEqual(
            [
                ("jvm", "package", "jvm"),
                ("linux-x64", "package", "linux-x64"),
            ],
            [
                (value["component"], value["phase"], value["target"])
                for value in result["inputs"]["upstreamArtifacts"]
            ],
        )
        self.assertEqual(
            result["buildKey"],
            compute_build_key(
                product="runtime",
                component="jvm",
                phase="validation",
                target="linux-x64",
                inputs=result["inputs"],
            ),
        )

    def test_version_identity_is_conditional_and_selected_by_product_owner(self) -> None:
        contract = PhaseInstanceId("contract", "contract", "binary", "common")
        runtime = PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64")
        sdk = PhaseInstanceId("sdk", "sdk-core", "binary", "common")
        aggregate = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")

        self.assertEqual(VERSIONS["contract"], plan(contract)["inputs"]["versionIdentity"])
        self.assertEqual(
            VERSIONS["runtime-compatibility"],
            plan(runtime)["inputs"]["versionIdentity"],
        )
        self.assertEqual(VERSIONS["sdk"], plan(sdk)["inputs"]["versionIdentity"])
        self.assertEqual(
            VERSIONS["runtime-release"],
            plan(aggregate)["inputs"]["versionIdentity"],
        )

    def test_runtime_compatibility_is_derived_from_release(self) -> None:
        instance = PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64")
        prerelease = {**VERSIONS, "runtime-release": "2.3.5-rc.1"}
        self.assertEqual(
            "2.3.0",
            plan(instance, versions=prerelease)["inputs"]["versionIdentity"],
        )
        for incompatible in ("2.3.1", "9.9.0"):
            with self.subTest(incompatible=incompatible):
                with self.assertRaisesRegex(ValueError, "compatibility identity"):
                    plan(instance, versions={**VERSIONS, "runtime-compatibility": incompatible})

    def test_native_sdk_keeps_an_explicit_compatible_embedded_runtime(self) -> None:
        instance = PhaseInstanceId("sdk", "rust", "package", "desktop")

        def runtime_inputs(version: str, *, changed: bool = False) -> list[dict[str, object]]:
            values = upstreams(instance)
            for value in values:
                if value["product"] != "runtime":
                    continue
                value["productVersion"] = version
                if value["component"] == "runtime-aggregate":
                    value["inputs"]["versionIdentity"] = version
                if changed:
                    value["inputs"]["inventory"] = [file_record(digest=DIGEST_C)]
                    value["inputs"]["phaseInputDigest"] = sha256_bytes(
                        canonical_json_bytes(value["inputs"]["inventory"]),
                    )
                    value["outputs"][0]["sha256"] = DIGEST_C
                value["buildKey"] = compute_build_key(
                    product=value["product"],
                    component=value["component"],
                    phase=value["phase"],
                    target=value["target"],
                    inputs=value["inputs"],
                )
            return values

        embedded = runtime_inputs("2.3.3")
        before = plan(instance, upstream_receipts=embedded)
        after_external_release = plan(
            instance,
            upstream_receipts=embedded,
            versions={
                **VERSIONS,
                "runtime-release": "2.4.0",
                "runtime-compatibility": "2.4.0",
            },
        )
        next_default = plan(
            instance,
            upstream_receipts=runtime_inputs("2.3.4", changed=True),
        )

        self.assertEqual(before, after_external_release)
        self.assertNotEqual(before["buildKey"], next_default["buildKey"])

        validation = PhaseInstanceId("sdk", "rust", "validation", "linux-x64")
        package_receipt = receipt(instance)
        package_receipt["inputs"] = before["inputs"]
        package_receipt["buildKey"] = before["buildKey"]
        runtime_receipt = next(
            value for value in embedded
            if (value["product"], value["component"], value["phase"], value["target"])
            == ("runtime", "linux-x64", "validation", "linux-x64")
        )
        plan(validation, upstream_receipts=[package_receipt, runtime_receipt])
        substituted = copy.deepcopy(runtime_receipt)
        substituted["outputs"][0]["sha256"] = DIGEST_C
        with self.assertRaisesRegex(ValueError, "differs from its embedded package input"):
            plan(validation, upstream_receipts=[package_receipt, substituted])

        mixed = runtime_inputs("2.3.3")
        changed_runtime = next(
            value for value in mixed
            if value["product"] == "runtime" and value["component"] != "runtime-aggregate"
        )
        changed_runtime["productVersion"] = "2.4.0"
        changed_runtime["inputs"]["versionIdentity"] = "2.4.0"
        changed_runtime["buildKey"] = compute_build_key(
            product=changed_runtime["product"],
            component=changed_runtime["component"],
            phase=changed_runtime["phase"],
            target=changed_runtime["target"],
            inputs=changed_runtime["inputs"],
        )
        with self.assertRaisesRegex(ValueError, "span incompatible release lines"):
            plan(instance, upstream_receipts=mixed)

    def test_every_sdk_package_keeps_its_selected_older_runtime_metadata(self) -> None:
        for component, target in (
            ("sdk-core", "common"),
            ("sdk-android", "android"),
            ("sdk-ios", "ios"),
            ("javascript", "node"),
        ):
            instance = PhaseInstanceId("sdk", component, "package", target)
            embedded = upstreams(instance)
            for value in embedded:
                if value["product"] != "runtime":
                    continue
                value["productVersion"] = "2.3.3"
                value["inputs"]["versionIdentity"] = (
                    "2.3.3" if value["component"] == "runtime-aggregate" else "2.3.0"
                )
                value["buildKey"] = compute_build_key(
                    product=value["product"],
                    component=value["component"],
                    phase=value["phase"],
                    target=value["target"],
                    inputs=value["inputs"],
                )
            with self.subTest(component=component):
                baseline = plan(instance, upstream_receipts=embedded)
                current_runtime_advanced = plan(
                    instance,
                    upstream_receipts=embedded,
                    versions={
                        **VERSIONS,
                        "runtime-release": "2.4.0",
                        "runtime-compatibility": "2.4.0",
                    },
                )
                self.assertEqual(baseline, current_runtime_advanced)

    def test_unrelated_versions_and_provenance_do_not_change_the_key(self) -> None:
        instance = PhaseInstanceId("runtime", "jvm", "validation", "linux-x64")
        original = upstreams(instance)
        changed = copy.deepcopy(original)
        for value in changed:
            value["producer"] = {
                **value["producer"],
                "commit": "c" * 40,
                "tree": "d" * 40,
                "runId": 99,
                "runAttempt": 7,
                "pullRequest": 88,
            }
        unrelated = {**VERSIONS, "contract": "9.0.0", "runtime-release": "2.3.9", "sdk": "9.0.2"}

        first = plan(instance, upstream_receipts=original)
        second = plan(instance, upstream_receipts=changed, versions=unrelated)

        self.assertEqual(first, second)
        self.assertNotIn("producer", first)
        self.assertNotIn("commit", canonical_json_bytes(first).decode())

    def test_authenticated_contract_projection_is_preserved_but_only_compatibility_changes_key(self) -> None:
        instance = PhaseInstanceId("runtime", "jvm", "binary", "jvm")
        original_upstreams = upstreams(instance)
        first = plan(instance, upstream_receipts=original_upstreams)
        contract_input = first["inputs"]["upstreamArtifacts"][0]
        self.assertEqual(original_upstreams[0]["buildKey"], contract_input["buildKey"])
        self.assertIn("contractProjection", contract_input)

        repackaged_upstreams = copy.deepcopy(original_upstreams)
        repackaged_upstreams[0]["inputs"]["inventory"] = [file_record(digest=DIGEST_C)]
        repackaged_upstreams[0]["inputs"]["phaseInputDigest"] = sha256_bytes(
            canonical_json_bytes(repackaged_upstreams[0]["inputs"]["inventory"]),
        )
        repackaged_upstreams[0]["outputs"][0]["sha256"] = DIGEST_C
        repackaged_upstreams[0]["buildKey"] = compute_build_key(
            product="contract",
            component="contract",
            phase="metadata",
            target="common",
            inputs=repackaged_upstreams[0]["inputs"],
        )
        repackaged = plan(
            instance,
            upstream_receipts=repackaged_upstreams,
            projection=verified_projection(
                instance,
                bundle_digest=DIGEST_C,
                contract_receipt=repackaged_upstreams[0],
            ),
        )
        self.assertEqual(first["buildKey"], repackaged["buildKey"])
        self.assertNotEqual(
            first["inputs"]["upstreamArtifacts"],
            repackaged["inputs"]["upstreamArtifacts"],
        )

        changed_component = plan(
            instance,
            upstream_receipts=original_upstreams,
            projection=verified_projection(instance, component_digest=DIGEST_B),
        )
        self.assertNotEqual(first["buildKey"], changed_component["buildKey"])

    def test_contract_projection_must_be_authenticated_exact_and_receipt_linked(self) -> None:
        instance = PhaseInstanceId("sdk", "sdk-ios", "binary", "ios")
        with self.assertRaisesRegex(ValueError, "Authenticated Contract projection"):
            plan_phase(
                instance,
                inventory=[file_record()],
                versions=VERSIONS,
                upstream_receipts=upstreams(instance),
                toolchain_profile_digest=DIGEST_A,
                flags_digest=DIGEST_B,
                contract_projection=verified_projection(instance).receipt_value(),
            )
        with self.assertRaisesRegex(ValueError, "exact required components"):
            plan(instance, projection=verified_projection(
                PhaseInstanceId("sdk", "sdk-core", "binary", "common"),
            ))
        with self.assertRaisesRegex(ValueError, "Bundle differ"):
            actual = upstreams(instance)
            plan(instance, upstream_receipts=actual, projection=verified_projection(
                instance,
                bundle_digest=DIGEST_C,
                contract_receipt=actual[0],
            ))

        paired = upstreams(instance)
        altered = copy.deepcopy(paired)
        altered[0]["producer"] = {**altered[0]["producer"], "runId": 99}
        with self.assertRaisesRegex(ValueError, "receipt bytes differ"):
            plan(
                instance,
                upstream_receipts=altered,
                projection=verified_projection(instance, contract_receipt=paired[0]),
            )

    def test_inventory_mutation_changes_only_the_derived_key_input(self) -> None:
        instance = PhaseInstanceId("contract", "contract", "binary", "common")
        first = plan(instance)
        second = plan(instance, inventory=[file_record(digest=DIGEST_C)])

        self.assertNotEqual(first["inputs"]["phaseInputDigest"], second["inputs"]["phaseInputDigest"])
        self.assertNotEqual(first["buildKey"], second["buildKey"])

    def test_versions_are_exact_and_valid_and_flags_are_schema_checked(self) -> None:
        instance = PhaseInstanceId("contract", "contract", "binary", "common")
        mutations = (
            {key: value for key, value in VERSIONS.items() if key != "sdk"},
            {**VERSIONS, "extra": "1.0.0"},
            {**VERSIONS, "contract": "latest"},
        )
        for versions in mutations:
            with self.subTest(versions=versions):
                with self.assertRaises(ValueError):
                    plan(instance, versions=versions)

    def test_upstreams_must_match_the_registry_exactly(self) -> None:
        instance = PhaseInstanceId("runtime", "jvm", "validation", "linux-x64")
        exact = upstreams(instance)
        cases = {
            "missing": exact[:-1],
            "duplicate": [*exact, exact[0]],
            "unexpected": [*exact, receipt(PhaseInstanceId("contract", "contract", "binary", "common"))],
        }
        failed = copy.deepcopy(exact)
        failed[0]["result"] = "failure"
        cases["failed"] = failed

        for name, values in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    plan(instance, upstream_receipts=values)

    def test_upstreams_must_match_current_product_and_compatibility_versions(self) -> None:
        cases = (
            (PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64"), "9.9.9", "9.9.9"),
            (PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate"), "9.9.9", "9.9.0"),
            (PhaseInstanceId("sdk", "sdk-core", "package", "common"), "9.9.9", "9.9.9"),
        )
        for instance, product_version, version_identity in cases:
            incompatible = upstreams(instance)
            incompatible[0]["productVersion"] = product_version
            incompatible[0]["inputs"]["versionIdentity"] = version_identity
            incompatible[0]["buildKey"] = compute_build_key(
                product=incompatible[0]["product"],
                component=incompatible[0]["component"],
                phase=incompatible[0]["phase"],
                target=incompatible[0]["target"],
                inputs=incompatible[0]["inputs"],
            )
            with self.subTest(instance=instance):
                with self.assertRaisesRegex(ValueError, "Incompatible upstream"):
                    plan(instance, upstream_receipts=incompatible)

    def test_compatible_older_runtime_patch_receipt_is_reusable(self) -> None:
        instance = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
        compatible = upstreams(instance)
        compatible[0]["productVersion"] = "2.3.1"
        compatible[0]["buildKey"] = compute_build_key(
            product=compatible[0]["product"],
            component=compatible[0]["component"],
            phase=compatible[0]["phase"],
            target=compatible[0]["target"],
            inputs=compatible[0]["inputs"],
        )
        plan(instance, upstream_receipts=compatible)

    def test_every_runtime_adapter_host_plan_keeps_both_required_packages(self) -> None:
        for adapter in RUNTIME_ADAPTERS:
            for target in NATIVE_TARGETS:
                instance = PhaseInstanceId("runtime", adapter, "validation", target)
                expected = {
                    PhaseInstanceId("runtime", adapter, "package", adapter),
                    PhaseInstanceId("runtime", target, "package", target),
                }
                with self.subTest(adapter=adapter, target=target):
                    self.assertEqual(
                        expected,
                        {
                            PhaseInstanceId(
                                value["product"], value["component"], value["phase"], value["target"],
                            )
                            for value in plan(instance)["inputs"]["upstreamArtifacts"]
                        },
                    )

    def test_javascript_plan_requires_the_distinct_node_binding_receipt(self) -> None:
        instance = PhaseInstanceId("sdk", "javascript", "validation", "node")
        result = plan(instance)
        identities = {
            (value["product"], value["component"], value["phase"], value["target"])
            for value in result["inputs"]["upstreamArtifacts"]
        }
        self.assertIn(("runtime", "node-js", "validation", "node-js-binding"), identities)
        self.assertNotIn(("runtime", "node-js", "validation", "node-js"), identities)

    def test_unknown_instance_and_unsupported_output_schema_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown product phase instance"):
            plan_phase(
                PhaseInstanceId("runtime", "jvm", "validation", "jvm"),
                inventory=[file_record()],
                versions=VERSIONS,
                upstream_receipts=[],
                toolchain_profile_digest=DIGEST_A,
                flags_digest=DIGEST_B,
            )
        with self.assertRaisesRegex(ValueError, "output schema version"):
            plan_phase(
                PhaseInstanceId("contract", "contract", "binary", "common"),
                inventory=[file_record()],
                versions=VERSIONS,
                upstream_receipts=[],
                toolchain_profile_digest=DIGEST_A,
                flags_digest=DIGEST_B,
                output_schema_version=2,
            )

    def test_identical_build_key_cannot_claim_conflicting_outputs(self) -> None:
        instance = PhaseInstanceId("contract", "contract", "binary", "common")
        first = receipt(instance)
        same = copy.deepcopy(first)
        same["producer"] = {**same["producer"], "runId": 2}
        verify_build_key_output_consistency([first, same])

        conflicting = copy.deepcopy(first)
        conflicting["outputs"][0]["sha256"] = DIGEST_C
        self.assertNotEqual(
            output_inventory_digest(first["outputs"]),
            output_inventory_digest(conflicting["outputs"]),
        )
        with self.assertRaisesRegex(ValueError, "conflicting output inventories"):
            verify_build_key_output_consistency([first, conflicting])


if __name__ == "__main__":
    unittest.main()
