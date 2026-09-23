"""Execute elected Core/Android binaries with the original signed Contract."""

import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
import sdk_workflow
from products.contract_projection import verify_contract_component_projection
from products.inventory import (
    canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    write_canonical_json,
)
from products.receipt import verify_output_manifest_identity
from products.registry import PhaseInstanceId, required_contract_components
from products.restore import verify_phase_shard
from products.sdk_facade_validation import _inventory
from products.sdk_maven import verify_sdk_maven_binary_content
from products.sdk_package import _require_capability_output_separate
from products.signing_isolation import require_no_signing_secret
from sdk_ios_package import _record
from sdk_maven_phase import execute as execute_binary


_TARGETS = {"sdk-core": "common", "sdk-android": "android"}
_LIMIT = 512 * 1024 * 1024


def _read(path):
    return read_regular_file_bytes(Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)


def execute(plan, discovery, state, destination, *, component, expected_build_key,
            repository_root, environ, trusted_workflow_sha, android_runtime_archive=None,
            sdk_validation_tooling=None, sdk_apple_validation_policy=None,
            sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Finalize only after signed input replay and binary output/lifetime checks.

    The existing producer owns primary-inventory generation. This caller checks
    its exact inventory, stage layout and Maven repository semantics, not the
    later binary-to-package transformation. No hosted or reuse admission is
    granted by this controller. Captures and raw diagnostics stay outside stage.
    """
    require_no_signing_secret(environ)
    if (component not in _TARGETS or
            (android_runtime_archive is None) != (component == "sdk-core")):
        raise ValueError("Maven binary requires Core or Android with its exact archive inputs")
    target = _TARGETS[component]
    instance = PhaseInstanceId("sdk", component, "binary", target)
    root = Path(repository_root).resolve(strict=True)
    plan = Path(plan).absolute()
    discovery, state, destination = product_reuse._product_materialization_paths(root, discovery, state, destination)
    policies = sdk_workflow._caller_policies(sdk_validation_tooling, sdk_apple_validation_policy)
    policy_bytes = canonical_json_bytes(policies)
    trees, files = {"discovery": discovery, "state": state}, {"plan": plan}
    if android_runtime_archive is not None:
        files["androidArchive"] = Path(android_runtime_archive)
    for label, policy in policies.items():
        if type(policy) is not dict:
            raise ValueError("Caller replay policy must be an explicit mapping")
        for name, value in policy.items():
            if isinstance(value, (str, Path)) and Path(value).is_absolute():
                path = Path(value)
                (trees if path.is_dir() else files)[label + "/" + name] = path
    _require_capability_output_separate(destination, [*trees.values(), *files.values()])
    if (root not in destination.parents or destination.resolve(strict=False) != destination
            or destination.exists() or destination.is_symlink()):
        raise ValueError("Maven binary destination must be fresh and normalized inside checkout")
    before_trees = {name: _inventory(path, allow_empty=True) for name, path in trees.items()}
    before_files = {name: _read(path) for name, path in files.items()}
    retained, values = {}, []

    def unchanged():
        require_no_signing_secret(environ)
        if (canonical_json_bytes(policies) != policy_bytes
                or any(_inventory(path, allow_empty=True) != before_trees[name] for name, path in trees.items())
                or any(_read(path) != before_files[name] for name, path in files.items())
                or any(_inventory(path, allow_empty=True) != inventory for path, inventory in retained.items())
                or any(canonical_json_bytes(value) != raw for value, raw in values)):
            raise ValueError("Maven binary originals, selection or retained evidence changed")

    admissions = {name: value for name, value in (
        ("sdk_facade_metadata_admission", sdk_facade_metadata_admission),
        ("sdk_android_metadata_admission", sdk_android_metadata_admission)) if value is not None}
    try:
        verified = product_reuse._verified_product_state(plan, discovery, state, root, environ,
            sdk_validation_tooling, sdk_original_workflow_sha=trusted_workflow_sha,
            **sdk_workflow._caller_policies(None, sdk_apple_validation_policy), **admissions)
        elected = verified.prior_ready_plans.get(instance)
        if elected is None or elected["buildKey"] != expected_build_key:
            raise ValueError("Maven binary is not ready with the expected elected key")
        evidence = verified.rebased_request.get("contractEvidence")
        if evidence is None or evidence["expectedTrustDomain"] != "release":
            raise ValueError("Maven binary requires authenticated release Contract evidence")
        for value in (verified.plan, verified.producer, verified.expected_fixed, evidence, elected):
            values.append((value, canonical_json_bytes(value)))
        for name in ("attestation", "attestationSignature", "publicKey"):
            path = root / evidence[name]
            _require_capability_output_separate(destination, [path])
            files["contract/" + name] = path
            before_files["contract/" + name] = _read(path)
        closure = (root / evidence["attestation"]).parent / "execution-closure"
        _require_capability_output_separate(destination, [closure])
        trees["contractClosure"] = closure
        before_trees["contractClosure"] = _inventory(closure, allow_empty=True)
        unchanged()
        destination = product_reuse._prepare_destination(destination, root)
        prepared = destination / "inputs"
        prepared.mkdir()
        trust = product_reuse._release_trust(root, verified.plan["validationCommit"], prepared / "policy")
        if trust is None:
            raise ValueError("Maven binary requires Git-authoritative release policy")
        policy_inventory = _inventory(prepared / "policy", allow_empty=True)
        retained[prepared / "policy"] = policy_inventory
        predecessors = prepared / "predecessors"
        ready = product_reuse._materialize_product_predecessors(
            verified, instance, predecessors, expected_build_key, root)
        producer, version = verified.producer, verified.expected_fixed["versions"]["sdk"]
        if (ready != elected or _read(predecessors / "phase-plan.json") != canonical_json_bytes(ready)
                or _read(predecessors / "producer.json") != canonical_json_bytes(producer)):
            raise ValueError("Maven binary retained election differs from its original plan")
        values.append((ready, canonical_json_bytes(ready)))
        retained[predecessors] = _inventory(predecessors, allow_empty=True)

        def original(product, name, phase, source_target):
            if ((product, name, source_target) != ("contract", "contract", "common")
                    or phase not in ("binary", "package", "validation", "metadata")):
                raise ValueError("Maven binary requested an unrelated Contract predecessor")
            directory = predecessors / "-".join((product, name, phase, source_target))
            receipt = directory / "phase-receipt.json"
            return _record({"stage": directory / "stage", "receiptPath": receipt,
                "receipt": product_reuse._canonical_control(receipt, "Original Contract receipt")},
                (product, name, phase, source_target), "Elected Contract predecessor")[0]

        def one_output(record, kind):
            outputs = [row for row in record["receipt"]["outputs"] if row["kind"] == kind]
            if len(outputs) != 1:
                raise ValueError("Maven binary requires one original Contract payload")
            return record["stage"] / outputs[0]["relativePath"]

        contract, contract_version, handoff, _ = product_reuse._capture_runtime_contract(
            root, evidence, original, one_output, prepared, trust)
        retained[handoff] = _inventory(handoff, allow_empty=True)
        values.append((contract["receipt"], canonical_json_bytes(contract["receipt"])))
        stem = "codex-agent-contract-" + contract_version
        verify_contract_component_projection(contract["stage"], contract["receiptPath"],
            handoff / (stem + ".attestation.json"), handoff / (stem + ".attestation.sig"),
            handoff / "public-key.pub", expected_trust_domain="release",
            expected_contract_version=contract_version, required_components=required_contract_components(instance),
            keyring=trust.keyring, keys_directory=trust.keys)
        selected = destination / "selection"
        selected.mkdir()
        (selected / "impact-plan.json").write_bytes(before_files["plan"])
        write_canonical_json(selected / "phase-plan.json", ready)
        write_canonical_json(selected / "producer.json", producer)
        retained[selected] = _inventory(selected)
        archive = None
        if android_runtime_archive is not None:
            archive_root = destination / "android-original"
            archive_root.mkdir()
            archive = archive_root / Path(android_runtime_archive).name
            archive.write_bytes(before_files["androidArchive"])
            retained[archive_root] = _inventory(archive_root)
        unchanged()
        result = execute_binary(ready, producer=producer, sdk_version=version,
            contract_metadata=contract, verified_contract_handoff=handoff,
            repository_root=root, destination=destination / "worker", environ=environ,
            **({"android_runtime_archive": archive} if archive is not None else {}))
        stage = Path(result["stage"])
        stage_inventory = _inventory(stage)
        if stage_inventory != result["outputInventory"]:
            raise ValueError("Maven binary output differs from its worker inventory")
        retained[stage] = stage_inventory
        retained[destination / "worker"] = _inventory(destination / "worker", allow_empty=True)
        manifest = verify_output_manifest_identity(stage, "sdk", component, "binary", target, version)
        verify_sdk_maven_binary_content(stage, manifest)
        unchanged()
        product_reuse._runtime_worker_checkout(root, producer)
        unchanged()
        with tempfile.TemporaryDirectory(prefix="sdk-maven-binary-") as temporary:
            candidate = Path(temporary).resolve() / "shard"
            final = product_reuse.finalize_phase_object(stage_root=stage, phase_plan=ready,
                producer=producer, product_version=version,
                trust_domain="development" if producer["event"] == "pull_request" else "release",
                destination=candidate)
            unchanged()
            if verify_phase_shard(candidate, instance) != final:
                raise ValueError("Maven binary finalized shard differs from its selected phase")
            publish_regular_tree(candidate, destination / "shard")
            if verify_phase_shard(destination / "shard", instance) != final:
                raise ValueError("Maven binary published shard differs from its verified candidate")
        unchanged()
        return final
    finally:
        unchanged()


def main(argv=None):
    from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options

    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "destination", "repository-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--discovery-root", dest="discovery", type=Path, required=True)
    parser.add_argument("--state-root", dest="state", type=Path, required=True)
    parser.add_argument("--component", choices=tuple(_TARGETS), required=True)
    parser.add_argument("--expected-build-key", required=True)
    parser.add_argument("--trusted-workflow-sha", required=True)
    parser.add_argument("--android-runtime-archive", type=Path)
    for name in ("sdk-validation-tooling", "sdk-apple-validation-policy"):
        parser.add_argument("--" + name, type=Path)
    add_metadata_admission_arguments(parser)
    arguments = vars(parser.parse_args(argv))
    try:
        for name in ("sdk_validation_tooling", "sdk_apple_validation_policy"):
            path = arguments.pop(name)
            if path is not None:
                arguments[name] = product_reuse._canonical_control(path, "Caller " + name)
        with metadata_admission_options(arguments) as admissions:
            execute(**arguments, environ=os.environ, **admissions)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
