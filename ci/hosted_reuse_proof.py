"""Frozen Phase-9 reuse only: no discovery, producers, signing or acceptance jobs."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import product_reuse as products
import hydrated_evidence as cache
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    regular_file_inventory, sha256_bytes, sha256_file, tree_entries,
    verified_zip_contents, write_canonical_json,
)
from products.registry import PHASE_INSTANCE_IDS
from products.restore import verification_session
from products.reuse import plan_reuse_wave
from products.selection import phase_inventory_paths
from products.signatures import load_keyring, public_key_for_metadata, verify_manifest_signature
from runtime_reference_transport import validate_original_references, _copy_exact


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "ci/tests/data/hosted-frozen-reuse.json"
PRODUCER = {
    "commit": "e84323e74c07f220ffe35ddda77dab3fe8b00e40",
    "tree": "30a022336b6e09028040d037b4c19c4cf3a95a0f",
    "runId": 37229320159, "runAttempt": 1, "event": "pull_request",
    "repository": "codex-agent-labs/codex-agent", "pullRequest": 31,
    "workflowPath": ".github/workflows/ci.yml",
}


def authenticate(spec, token):
    observed = products._observe_ci_producer_jobs({"resume": PRODUCER},
        jobs_by_phase={"resume": "product-validation / product-resume"},
        trusted_workflow_sha=spec["carrier"]["workflowSha"], token=token)
    artifact = products._contract_ci_upload_metadata(spec["carrier"]["id"],
        spec["carrier"]["sha256"], f"codex-agent-product-resume-{PRODUCER['tree']}",
        PRODUCER, observed[0]["run"], token)
    products._require_artifact_job_window(observed[0], "product-validation / product-resume", artifact)
    return artifact


def prepare(spec, work, token, retained=None):
    started = time.perf_counter()
    artifact = authenticate(spec, token)
    archive = work / "carrier.zip"
    if retained is None:
        products._download_contract_ci_upload(artifact["id"], artifact["digest"], artifact["name"],
            PRODUCER, products.api_json(f"https://api.github.com/repos/{PRODUCER['repository']}/actions/runs/{PRODUCER['runId']}/attempts/1", token),
            token, destination=archive)
    else:
        _copy_exact(retained, archive, {"bytes": artifact["size_in_bytes"], "sha256": artifact["digest"]})
    physical, _, verified = verified_zip_contents(archive, retained_paths=(), allow_empty_members=True,
                                           **products._CATALOG_ZIP_LIMITS)
    if verified != {"bytes": artifact["size_in_bytes"], "sha256": artifact["digest"]}:
        raise ValueError("Frozen reference carrier differs from official original bytes")
    original = work / "original"
    products.safe_extract(archive, original)
    if regular_file_inventory(original, allow_empty=True) != physical:
        raise ValueError("Frozen reference carrier extraction changed")
    refs = validate_original_references(load_canonical_json_bytes(
        read_regular_file_bytes(original / "runtime-original-references.json", reject_symlink_parents=True)))
    expected = {row["relativePath"]: row for row in refs["inventory"]}
    for row in [*spec["files"], *spec["signedCheckpoint"]]:
        name = row.get("sourcePath", row["relativePath"])
        if expected.get(name) != {"relativePath": name, "bytes": row["bytes"], "sha256": row["sha256"]}:
            raise ValueError("Frozen proof changes an authenticated file identity")
    bodies = [row for row in refs["references"] if row["source"] and
              next(source["kind"] for source in refs["sources"] if source["relativePath"] == row["source"]) == "phase"
              and row["relativePath"].startswith(row["source"] + "/")]
    manifest = [{"sha256": row["sha256"], "bytes": row["bytes"]}
                for row in [*bodies, *spec["files"], *spec["signedCheckpoint"]]]
    write_canonical_json(work / "cache-manifest.json", manifest)
    write_canonical_json(work / "prepare.json", {"seconds": str(time.perf_counter() - started),
        "carrierBytes": artifact["size_in_bytes"], "downloadedCarrierBytes": artifact["size_in_bytes"] if retained is None else 0,
        "logicalProjectionBytes": sum(row["bytes"] for row in bodies),
        "uniqueHydratedBytes": sum({row["sha256"]: row["bytes"] for row in manifest}.values())})


def verify_frozen_inventories(baseline, phases):
    """Protect retained phases, while reporting legitimate unrelated SDK changes."""
    frozen = {products._identity(row) for row in phases}
    old = tuple(path for path, _ in tree_entries(ROOT, baseline))
    new = tuple(path for path, _ in tree_entries(ROOT, "HEAD"))
    changed = set(subprocess.check_output(
        ["git", "-C", str(ROOT), "diff", baseline, "HEAD", "--name-only"], text=True).splitlines())
    affected = []
    for instance in PHASE_INSTANCE_IDS:
        before, after = phase_inventory_paths(old, instance), phase_inventory_paths(new, instance)
        if before != after or set(after) & changed:
            if instance in frozen:
                raise ValueError(f"Frozen product inventory changed: {instance}")
            affected.append(products._identity_record(instance))
    return affected


def verify(spec, work, token):
    from reuse_qualification import process_read_bytes
    read_before = process_read_bytes()
    started = time.perf_counter()
    artifact = authenticate(spec, token)  # Restore never carries authentication.
    physical, _, verified = verified_zip_contents(work / "carrier.zip", retained_paths=(),
        allow_empty_members=True, **products._CATALOG_ZIP_LIMITS)
    if verified != {"bytes": artifact["size_in_bytes"], "sha256": artifact["digest"]}:
        raise ValueError("Authenticated reference carrier changed during cache retrieval")
    original = work / "original"
    if regular_file_inventory(original, allow_empty=True) != physical:
        raise ValueError("Authenticated reference extraction changed during cache retrieval")
    refs = validate_original_references(load_canonical_json_bytes(
        read_regular_file_bytes(original / "runtime-original-references.json", reject_symlink_parents=True)))
    plan = {"event": "pull_request", "pullRequest": 31, "repository": PRODUCER["repository"]}
    projections = [source for source in refs["sources"] if source["kind"] == "phase"]
    if len(projections) != 46:
        raise ValueError("Frozen proof has a different original phase closure")
    transports = []
    with verification_session() as session:
        initial_cold_bytes = session.get("runtimeColdArchiveBytes", 0)
        for source in projections:
            records = [row for row in refs["references"] if row["source"] == source["relativePath"]
                       and row["relativePath"].startswith(source["relativePath"] + "/")]
            transport = products._capture_runtime_original_reference_members(plan, PRODUCER,
                source, records, original, trusted_workflow_sha=spec["carrier"]["workflowSha"], token=token)
            transports.append(transport)
        if not session.get("portableQualificationInputs"):
            products._register_qualified_original_projections(original, {**refs, "sources": projections},
                transports, trusted_workflow_sha=spec["carrier"]["workflowSha"])
        # Original admission is still performed by the existing real verifier.
        phases = []
        for source in projections:
            receipt = source["receipt"]
            instance = products._identity(receipt)
            destination = work / "verified" / instance.component / instance.phase / instance.target
            products.capture_runtime_original_ci_phases(
                {instance.phase: original / source["relativePath"] / "shard/phase-receipt.json"},
                destination, target=instance.component, original_instance=instance,
                trusted_workflow_sha=spec["carrier"]["workflowSha"], token=token, recovery_projection=True)
            phases.append({**products._identity_record(instance),
                           "receiptSha256": sha256_bytes(canonical_json_bytes(receipt))})
            shutil.rmtree(destination)
            print(json.dumps({"verifiedOriginalPhase": len(phases), "of": len(projections),
                              "component": instance.component, "phase": instance.phase}), flush=True)
        # A few signed reports live in aggregate predecessor inputs. Retrieve
        # only these qualified members, never their enclosing cold archives.
        additional = {}
        mappings = {row["relativePath"]: row for row in refs["references"]}
        sources = {source["relativePath"]: source for source in refs["sources"]}
        for row in [*spec["files"], *spec["signedCheckpoint"]]:
            name = row.get("sourcePath", row["relativePath"])
            target = original / name
            if target.exists():
                continue
            if cache.copy(row, target):
                continue
            mapping = mappings[name]
            if mapping["source"] is None:
                _copy_exact(original / mapping["sourcePath"], target, row)
                cache.retain(row, target)
            else:
                additional.setdefault(mapping["source"], []).append(mapping)
        additional_transports = []
        for prefix, records in additional.items():
            additional_transports.append(products._capture_runtime_original_reference_members(plan, PRODUCER,
                sources[prefix], records, original, trusted_workflow_sha=spec["carrier"]["workflowSha"], token=token))
        frozen = work / "frozen"
        for row in spec["files"]:
            destination = frozen / row["relativePath"]
            if not cache.copy(row, destination):
                _copy_exact(original / row["sourcePath"], destination, row)
                cache.retain(row, destination)
        aggregate = next(source for source in refs["sources"] if source["kind"] == "aggregate")
        # Reauthenticate the signing origin even when all its bodies are hits.
        records = [row for row in refs["references"] if row["relativePath"] in
                   {item["relativePath"] for item in spec["signedCheckpoint"]}]
        import tempfile
        with tempfile.TemporaryDirectory(prefix="frozen-signing-origin-") as temporary:
            signed_transport = products._capture_runtime_original_reference_members(plan, PRODUCER,
                aggregate, records, Path(temporary).resolve(),
                trusted_workflow_sha=spec["carrier"]["workflowSha"], token=token)
        signed = original / aggregate["relativePath"] / "aggregate-input"
        attestation_path = signed / "codex-agent-runtime-0.8.0.attestation.json"
        attestation = load_canonical_json_bytes(read_regular_file_bytes(attestation_path, reject_symlink_parents=True))
        keyring_path = ROOT / "gradle/release/product-signing-keys.json"
        keys = ROOT / "gradle/release/keys"
        public_key = public_key_for_metadata(attestation["signing"], load_keyring(keyring_path, keys),
                                             keys, allow_retired=True)
        verify_manifest_signature(attestation_path, signed / "codex-agent-runtime-0.8.0.attestation.sig",
                                  public_key, attestation["signing"])
        payload = attestation["payload"]
        manifest = signed / payload["fileName"]
        if manifest.stat().st_size != payload["bytes"] or sha256_file(manifest, reject_symlink_parents=True) != payload["sha256"]:
            raise ValueError("Signed Runtime payload commitment differs from its preserved manifest")
        if attestation["metadataReceiptSha256"] != next(row["receiptSha256"] for row in
                spec["request"]["availableObjects"] if row["component"] == "runtime-aggregate"):
            raise ValueError("Signed Runtime checkpoint changes its aggregate receipt")
        (frozen / "policy").mkdir(parents=True)
        shutil.copyfile(keyring_path, frozen / "policy/product-signing-keys.json")
        shutil.copytree(keys, frozen / "policy/keys")
        request = {**copy.deepcopy(spec["request"]), "artifactRoot": str(frozen), "repositoryRoot": str(ROOT)}
        result = plan_reuse_wave(request)
        if result != spec["expectedResult"] or not result["fullReuse"] or any(result["matrices"].values()):
            raise ValueError("Frozen fifty-phase full reuse differs or selects a product phase")
        cold_archive_bytes = session.get("runtimeColdArchiveBytes", 0) - initial_cold_bytes
        if cold_archive_bytes:
            raise ValueError("Frozen cache proof unexpectedly consumed cold original archives")
        from products.verified_evidence import _source_identity
        verification_policy = _source_identity()
    changed_inventories = verify_frozen_inventories(spec["inventoryBaseline"], result["phases"])
    report = {"seconds": str(time.perf_counter() - started), "frozenPhases": len(result["phases"]),
        "selectedProductPhases": 0, "productInventories": len(PHASE_INSTANCE_IDS),
        "changedProductInventories": len(changed_inventories), "changedProductInstances": changed_inventories,
        "changedFrozenInventories": 0,
        "resultSha256": sha256_bytes(canonical_json_bytes(result)), "freshOriginalPhases": phases,
        "originalRangeBytes": sum(item["rangeBytes"] for item in [*transports, *additional_transports, signed_transport]),
        "originalColdArchiveBytes": cold_archive_bytes, "verificationPolicySha256": verification_policy,
        "rootProcessReadBytes": process_read_bytes() - read_before if read_before is not None else None,
        "portableQualification": {key: str(session.get(key, 0)) if key == "qualificationVerificationSeconds"
                                  else session.get(key, 0) for key in (
            "qualificationHits", "qualificationMisses", "qualificationBodyReadBytes",
            "qualificationVerificationSeconds", "downloadedArtifactCount", "downloadedArtifactBytes")},
        "checkpoint": spec["signedCheckpoint"], "prepare": json.loads((work / "prepare.json").read_bytes())}
    write_canonical_json(work / "proof.json", report)
    print(json.dumps(report), flush=True)


def qualify_checkpoint(plan, work, token, *, trusted_workflow_sha):
    """Qualify preserved originals for discovery; never adopt the historical plan."""
    from products.restore import _VERIFICATION_SESSION
    from products.verified_evidence import _source_identity
    if plan["repository"] != PRODUCER["repository"] or plan["pullRequest"] != PRODUCER["pullRequest"]:
        return
    spec = load_canonical_json_bytes(SPEC.read_bytes())
    work.mkdir()
    prepare(spec, work, token)
    original = work / "original"
    refs = validate_original_references(load_canonical_json_bytes(
        read_regular_file_bytes(original / "runtime-original-references.json", reject_symlink_parents=True)))
    cache.hosted("restore", refs, work)
    transports = []
    for source in refs["sources"]:
        if source["kind"] != "phase":
            continue
        rows = [row for row in refs["references"] if row["source"] == source["relativePath"]
                and row["relativePath"].startswith(source["relativePath"] + "/")]
        transports.append(products._capture_runtime_original_reference_members(plan, PRODUCER,
            source, rows, original, trusted_workflow_sha=trusted_workflow_sha, token=token))
    products._register_qualified_original_projections(original,
        {**refs, "sources": [source for source in refs["sources"] if source["kind"] == "phase"]},
        transports, trusted_workflow_sha=trusted_workflow_sha)
    session = _VERIFICATION_SESSION.get()
    if session is None:
        raise ValueError("Original checkpoint qualification requires private verification custody")
    session["referenceCheckpoint"] = original, refs, _source_identity()
    cache.hosted("save", refs, work)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "verify"))
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--retained-carrier", type=Path)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    spec = load_canonical_json_bytes(SPEC.read_bytes())
    token = os.environ["GITHUB_TOKEN"]
    if args.mode == "prepare":
        prepare(spec, work, token, args.retained_carrier)
    else:
        verify(spec, work, token)
