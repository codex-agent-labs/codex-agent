"""Original CI capture for aggregate metadata and its 25 adapter receipts.

This fixed naming policy is a provisioning prerequisite, not evidence that the
aggregate workflow has been wired or run. Retained aggregate release admission
and full semantic verification remain separate protected-caller requirements.
"""

from datetime import datetime, timedelta
from pathlib import Path
import tempfile
from typing import Any

from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory,
    require_array, require_exact_keys, require_regular_directory, require_string,
    sha256_bytes, verified_zip_contents, write_canonical_json,
)
from products.receipt import validate_phase_receipt
from products.registry import PhaseInstanceId
from products.restore import verify_phase_shard
from products.runtime_aggregate import _adapter_receipt_identities


def capture_runtime_aggregate_original_ci(
    aggregate_receipt: Path, adapter_receipts: list[dict[str, Any]], destination: Path,
    *, trusted_workflow_sha: str, token: str,
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
            artifact, raw = _download_contract_ci_upload(
                candidate.get("id"), candidate.get("digest"), expected_name,
                producer, observation["run"], token,
            )
            job = next(value for value in observation["jobs"] if value.get("name") == jobs[name])
            timestamps = [datetime.fromisoformat(require_string(value, "Original Runtime upload timestamp").replace("Z", "+00:00"))
                          for value in (job.get("started_at"), artifact.get("created_at"), job.get("completed_at"))]
            if any(value.utcoffset() != timedelta(0) for value in timestamps) or not timestamps[0] <= timestamps[1] <= timestamps[2]:
                raise ValueError("Original Runtime aggregate upload is outside its original job-attempt window")
            retained = prepared / "phases" / name
            retained.mkdir(parents=True)
            archive = retained / "transport.zip"
            archive.write_bytes(raw)
            archive_files, _, _ = verified_zip_contents(
                archive, retained_paths=(), allow_empty_members=True, **_CATALOG_ZIP_LIMITS,
            )
            safe_extract(archive, retained / "original")
            if regular_file_inventory(retained / "original", allow_empty=True) != archive_files:
                raise ValueError("Original Runtime aggregate extraction differs from verified upload")
            verified = verify_phase_shard(retained / "original/shard", identities[name])
            if verified["receiptBytes"] != originals[name]:
                raise ValueError("Original Runtime aggregate upload differs from its requested original receipt")
            expected_files.append({"relativePath": f"phases/{name}/transport.zip",
                                   "bytes": len(raw), "sha256": sha256_bytes(raw)})
            expected_files.extend({**record, "relativePath": f"phases/{name}/original/{record['relativePath']}"}
                                  for record in archive_files)
            artifacts[name] = artifact
        if any(read_regular_file_bytes(sources[name], max_bytes=16 * 1024 * 1024,
                                       reject_symlink_parents=True) != raw for name, raw in originals.items()):
            raise ValueError("Original Runtime aggregate receipts changed during capture")
        evidence = {"target": "aggregate", "observed": observed, "artifacts": artifacts,
                    "receiptSha256s": {name: sha256_bytes(raw) for name, raw in originals.items()}}
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
