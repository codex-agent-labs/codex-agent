"""Original synthetic K/R objects planned from a real isolated Git inventory.

No product compiler or hosted runner executes here. Synthetic profiles and
outcomes are fixture data, never eligible for release/host acceptance.
"""

from pathlib import Path
import shutil
import subprocess

from ci.products.contract_projection import verify_contract_component_projection
from ci.products.inventory import write_canonical_json
from ci.products.plan import (
    attach_runtime_binary_identity, plan_phase, runtime_validation_dependencies,
    verify_runtime_validation_projection,
)
from ci.products.registry import NATIVE_TARGETS, PhaseInstanceId, required_contract_components
from ci.products.selection import phase_git_inventory
from ci.products.signatures import generate_development_key
from ci.tests.product_chain_variants import _write_runtime_inputs
from ci.tests.test_product_native_chain import build_chain
from ci.tests.test_product_plan import toolchain_profile
from ci.tests.test_product_reuse_adapter import product_reuse as adapter


VERSIONS = {"contract": "0.2.0", "runtime-release": "0.2.7",
            "runtime-compatibility": "0.2.0", "sdk": "0.2.9"}


def planned_chain(root: Path) -> dict:
    repository = root / "repository"
    repository.mkdir(parents=True)
    source = Path(__file__).resolve().parents[2]
    abi = "codex-agent-runtime-desktop/native/c-api"
    for relative in (f"{abi}/abi-contract.json", f"{abi}/binary-flags.json",
                     f"{abi}/include/codex_agent.h", f"{abi}/exports/macos.exports",
                     f"{abi}/exports/linux.map", f"{abi}/exports/windows.def"):
        destination = repository / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, destination)
    inputs = root / "app-inputs"
    inputs.mkdir()
    manifest, _, _ = _write_runtime_inputs(inputs)
    shutil.copyfile(manifest, repository / "codex-agent-runtime-desktop/codex-app-server-distributions.json")
    for target in NATIVE_TARGETS:
        write_canonical_json(repository / f"gradle/release/toolchains/runtime/{target}.json", toolchain_profile(target))
    for product, version in (("contract", "0.2.0"), ("runtime", "0.2.7"), ("sdk", "0.2.9")):
        path = repository / f"gradle/release/versions/{product}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(version + "\n", encoding="utf-8")
    for relative in ("codex-agent-core/src/commonMain/kotlin/Fixture.kt",
                     "codex-agent-bindings/python/fixture.py"):
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"Explicit synthetic planner fixture input\n")

    def git(*args):
        return subprocess.run(("git", *args), cwd=repository, check=True,
                              capture_output=True, text=True).stdout.strip()

    git("init", "-q")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "user.name", "Synthetic planner fixture")
    git("add", ".")
    git("commit", "-qm", "synthetic planner inputs, not product execution")
    commit, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
    private_key, public_key, signing = generate_development_key(root / "keys")
    context = {
        "private_key": private_key, "public_key": public_key, "signing": signing,
        "producer": {"repository": "codex-agent-labs/codex-agent",
                     "workflowPath": ".github/workflows/product-validation.yml",
                     "commit": commit, "tree": tree, "event": "pull_request",
                     "runId": 201, "runAttempt": 1, "pullRequest": 31},
        "planned_receipts": {}, "receipt_paths": {}, "phase_stages": {}, "plans": {},
    }
    authority_cache = {}
    projection = None

    def factory(instance, upstream=None, **arguments):
        nonlocal projection
        if upstream is not None:
            arguments = {"upstream_receipts": [context["planned_receipts"][PhaseInstanceId(
                *(record[key] for key in ("product", "component", "phase", "target")))] for record in upstream]}
        if instance not in authority_cache:
            # Reuse the workflow authority reader; no fixture implementation of
            # toolchain/flags policy or planner keys.
            outer = adapter.PhaseInstanceId(instance.product, instance.component, instance.phase, instance.target)
            authorities, unavailable = adapter._authorities(repository, commit, (outer,))
            if authorities is None:
                raise AssertionError(unavailable)
            authority_cache[instance] = authorities[0]
        authority = authority_cache[instance]
        arguments.update(inventory=phase_git_inventory(repository, commit, instance), versions=VERSIONS,
                         toolchain_profile_digest=authority["toolchainProfileDigest"],
                         flags_digest=authority["flagsDigest"], output_schema_version=1)
        components = required_contract_components(instance)
        if components:
            contract = context["contract"]
            if projection is None:
                projection = verify_contract_component_projection(
                    contract["payload"].parent.parent, contract["receipt"].read_bytes(),
                    contract["attestation"], contract["signature"], public_key,
                    expected_trust_domain="development", expected_contract_version="0.2.0",
                    required_components=tuple(sorted(contract["manifest"]["components"])),
                )
            arguments["contract_projection"] = projection.restrict(components)
        dependencies = runtime_validation_dependencies(instance)
        if dependencies:
            reports = {dependency.target: adapter._runtime_report_output(
                instance, dependency, context["phase_stages"][dependency],
                context["planned_receipts"][dependency]) for dependency in dependencies}
            order = adapter.RUNTIME_TARGETS if instance.component in {"jvm", "node-js", "node-wasm"} else (instance.target,)
            arguments["runtime_validation_projection"] = verify_runtime_validation_projection(
                instance, [reports[target] for target in order],
                [context["planned_receipts"][dependency] for dependency in dependencies])
        plan = plan_phase(instance, **arguments)
        if instance.product == "runtime" and instance.component in NATIVE_TARGETS and instance.phase == "binary":
            plan = attach_runtime_binary_identity(repository, commit, instance, plan, arguments["contract_projection"])
        context["plans"][instance] = plan
        return {key: value for key, value in plan.items() if key != "runtimeBinaryIdentity"}

    context["plan_factory"] = factory
    chain = build_chain(repository / "originals", 201, include_bootstrap=True, context=context)
    chain.update(repository=repository, commit=commit, tree=tree)
    return chain
