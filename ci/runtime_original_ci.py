"""Original CI capture for aggregate metadata and its 25 adapter receipts.

This fixed naming policy is a provisioning prerequisite, not evidence that the
aggregate workflow has been wired or run. Retained aggregate release admission
and full semantic verification remain separate protected-caller requirements.
"""

from datetime import datetime, timedelta
from contextlib import nullcontext
from pathlib import Path
import tempfile
from typing import Any

from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory,
    require_array, require_exact_keys, require_regular_directory, require_string,
    sha256_bytes, verified_zip_contents, write_canonical_json,
    snapshot_regular_tree,
)
from products.receipt import validate_phase_receipt
from products.registry import PhaseInstanceId
from products.restore import verify_phase_shard
from products.runtime_aggregate import _adapter_receipt_identities
from products.signatures import require_release_signing_metadata


def capture_runtime_aggregate_original_ci(
    aggregate_receipt: Path, adapter_receipts: list[dict[str, Any]], destination: Path,
    *, trusted_workflow_sha: str, token: str, signing_metadata: dict[str, Any] | None = None,
    selected_contract_receipt_sha256: str | None = None,
) -> dict[str, Any]:
    """Capture exact original attempts/uploads; never sign or admit semantics."""
    # Share the established observer, official downloader and safe extractor;
    # no caller may select a job name, artifact name or verification callback.
    from product_reuse import (
        _CATALOG_ZIP_LIMITS, _download_contract_ci_upload, _observe_ci_producer_jobs,
        _runtime_prior_workflow_sha, api_json, paginated_items, safe_extract,
    )

    if type(token) is not str or not token:
        raise ValueError("Original Runtime aggregate CI capture requires an observation token")
    signing = None if signing_metadata is None else require_release_signing_metadata(signing_metadata)
    inputs = []
    for value in require_array(adapter_receipts, "Runtime aggregate adapter receipt inputs"):
        record = require_exact_keys(value, {"component", "phase", "target", "receipt"},
                                    "Runtime aggregate adapter receipt input")
        inputs.append((tuple(record[key] for key in ("component", "phase", "target")), Path(record["receipt"])))
    if [identity for identity, _ in inputs] != _adapter_receipt_identities():
        raise ValueError("Runtime aggregate source capture requires the exact sorted 25 adapter receipts")
    inputs.append((("runtime-aggregate", "metadata", "aggregate"), Path(aggregate_receipt)))
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Original Runtime aggregate CI destination must not exist")
    ancestor = destination.parent
    while not ancestor.exists() and not ancestor.is_symlink():
        ancestor = ancestor.parent
    for directory in (ancestor, *ancestor.parents):
        require_regular_directory(directory, "Runtime aggregate CI destination ancestor")
    originals, receipts, sources, identities = {}, {}, {}, {}
    for identity, source in inputs:
        for left, right in ((source.absolute(), destination), (source.resolve(), destination.resolve())):
            if left == right or left in right.parents or right in left.parents:
                raise ValueError("Runtime aggregate CI destination overlaps an original receipt")
        raw = read_regular_file_bytes(source, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
        receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
        if tuple(receipt[key] for key in ("product", "component", "phase", "target")) != ("runtime", *identity):
            raise ValueError("Runtime aggregate original receipt has the wrong phase identity")
        name = "-".join(identity)
        originals[name], receipts[name], sources[name] = raw, receipt, source
        identities[name] = PhaseInstanceId("runtime", *identity)
    jobs = {name: f"product-validation / runtime-{name}" for name in receipts}
    original_workflows, workflow_policies = {}, {}
    for name, receipt in receipts.items():
        producer = receipt["producer"]
        identity = producer["runId"], producer["runAttempt"]
        if identity not in original_workflows:
            original_run = api_json(
                f"https://api.github.com/repos/codex-agent-labs/codex-agent/actions/runs/"
                f"{identity[0]}/attempts/{identity[1]}", token)
            original_workflows[identity] = _runtime_prior_workflow_sha(original_run, trusted_workflow_sha)
        original_sha = original_workflows[identity]
        if original_sha is None:
            raise ValueError("Original Runtime aggregate phase lacks a reviewed producer workflow")
        workflow_policies[name] = {"path": ".github/workflows/product-validation.yml", "sha": original_sha}
    observed = _observe_ci_producer_jobs(
        {name: receipt["producer"] for name, receipt in receipts.items()},
        jobs_by_phase=jobs, trusted_workflows_by_phase=workflow_policies, token=token,
    )
    attempts = {(value["run"]["id"], value["run"]["run_attempt"]): value for value in observed}
    with tempfile.TemporaryDirectory(prefix="runtime-aggregate-original-ci-") as temporary:
        prepared = Path(temporary).resolve() / "captured"
        inventories, artifacts, expected_files = {}, {}, []
        for name, receipt in receipts.items():
            producer = receipt["producer"]
            run_id = producer["runId"]
            if run_id not in inventories:
                inventories[run_id] = paginated_items(
                    f"https://api.github.com/repos/codex-agent-labs/codex-agent/actions/runs/{run_id}/artifacts",
                    "artifacts", token)
            expected_name = (f"codex-agent-runtime-worker-{name}-{receipt['buildKey'][7:]}-"
                             f"{producer['tree']}-attempt-{producer['runAttempt']}")
            candidates = [item for item in inventories[run_id]
                          if isinstance(item, dict) and item.get("name") == expected_name]
            if len(candidates) != 1:
                raise ValueError("Original Runtime aggregate upload is missing or ambiguous")
            observation = attempts[(run_id, producer["runAttempt"])]
            candidate = candidates[0]
            # New release proofs retain immutable upload identities, not 26 raw
            # archives plus their full extractions. Authenticate one at a time.
            scratch = tempfile.TemporaryDirectory(prefix="original-phase-", dir=temporary) if signing else nullcontext(None)
            with scratch as private:
                retained = Path(private).resolve() if signing else prepared / "phases" / name
                retained.mkdir(parents=True, exist_ok=signing is not None)
                archive = retained / "transport.zip"
                artifact, raw = _download_contract_ci_upload(
                    candidate.get("id"), candidate.get("digest"), expected_name,
                    producer, observation["run"], token,
                    **({"destination": archive} if signing else {}),
                )
                job = next(value for value in observation["jobs"] if value.get("name") == jobs[name])
                timestamps = [datetime.fromisoformat(require_string(value, "Original Runtime upload timestamp").replace("Z", "+00:00"))
                              for value in (job.get("started_at"), artifact.get("created_at"), job.get("completed_at"))]
                if any(value.utcoffset() != timedelta(0) for value in timestamps) or not timestamps[0] <= timestamps[1] <= timestamps[2]:
                    raise ValueError("Original Runtime aggregate upload is outside its original job-attempt window")
                if signing is None:
                    archive.write_bytes(raw)
                archive_files, _, archive_record = verified_zip_contents(
                    archive, retained_paths=(), allow_empty_members=True, **_CATALOG_ZIP_LIMITS,
                )
                safe_extract(archive, retained / "original")
                if regular_file_inventory(retained / "original", allow_empty=True) != archive_files:
                    raise ValueError("Original Runtime aggregate extraction differs from verified upload")
                verified = verify_phase_shard(retained / "original/shard", identities[name])
                if verified["receiptBytes"] != originals[name]:
                    raise ValueError("Original Runtime aggregate upload differs from its requested original receipt")
                if selected_contract_receipt_sha256 is not None and receipt["phase"] == "binary":
                    upstreams = receipt["inputs"]["upstreamArtifacts"]
                    if len(upstreams) != 1 or "contractProjection" not in upstreams[0]:
                        raise ValueError("Original adapter binary lacks its Contract predecessor")
                    digest = upstreams[0]["contractProjection"]["receiptSha256"]
                    if digest != selected_contract_receipt_sha256:
                        from products.inventory import require_sha256
                        require_sha256(digest, "Original adapter Contract receipt digest")
                        handoff = retained / "original/inputs/contract-input"
                        if sha256_bytes(read_regular_file_bytes(handoff / "execution-closure/receipts/metadata.json",
                                max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)) != digest:
                            raise ValueError("Original adapter upload changes its Contract receipt")
                        target = prepared / "adapter-contracts" / digest[7:]
                        if not target.exists():
                            snapshot_regular_tree(handoff, target)
                            expected_files.extend({**record, "relativePath": f"adapter-contracts/{digest[7:]}/{record['relativePath']}"}
                                                  for record in regular_file_inventory(target))
                if signing is None:
                    expected_files.append({**archive_record, "relativePath": f"phases/{name}/transport.zip"})
                    expected_files.extend({**record, "relativePath": f"phases/{name}/original/{record['relativePath']}"}
                                          for record in archive_files)
            artifacts[name] = artifact
        if any(read_regular_file_bytes(sources[name], max_bytes=16 * 1024 * 1024,
                                       reject_symlink_parents=True) != raw for name, raw in originals.items()):
            raise ValueError("Original Runtime aggregate receipts changed during capture")
        evidence = {"target": "aggregate", "observed": observed, "artifacts": artifacts,
                    "receiptSha256s": {name: sha256_bytes(raw) for name, raw in originals.items()}}
        if signing is not None:
            evidence["signing"] = signing
        write_canonical_json(prepared / "transport/original-ci-phases.json", evidence)
        evidence_bytes = canonical_json_bytes(evidence)
        expected_files.append({"relativePath": "transport/original-ci-phases.json",
                               "bytes": len(evidence_bytes), "sha256": sha256_bytes(evidence_bytes)})
        expected_files.sort(key=lambda record: record["relativePath"])
        if regular_file_inventory(prepared, allow_empty=True) != expected_files:
            raise ValueError("Original Runtime aggregate evidence changed before publication")
        publish_regular_tree(prepared, destination, allow_empty=True,
                             expected_inventory=expected_files)
    return evidence
