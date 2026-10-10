"""Build a development SDK cache catalog from authenticated completed state."""

import argparse
import os
from pathlib import Path
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options
from products.index import IndexEntrySource
from products.inventory import canonical_json_bytes, require_sha256, sha256_bytes, sha256_file
from products.restore import verify_object
from products.sdk_campaign_dev_catalog import stage_sdk_same_pr_catalog
from products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from products.sdk_package import _require_capability_output_separate
from products.signing_isolation import require_no_signing_secret
from reuse import github_output


def stage_completed_sdk_catalog(state, destination: Path) -> dict:
    """Consume only the private replay state; never infer release trust from it."""
    require_no_signing_secret(os.environ)
    selected = {instance for instance in state.prior_by_instance if instance.product == "sdk"}
    if selected != SDK_CAMPAIGN_INSTANCES or state.producer["event"] != "pull_request":
        raise ValueError("SDK catalog requires a completed exact-62 PR selection")
    if any(instance not in state.sources for instance in selected):
        raise ValueError("SDK catalog lacks an original object for a selected phase")
    sources, envelopes, archives = {}, {}, {}
    for instance in sorted(SDK_CAMPAIGN_INSTANCES):
        record = state.prior_by_instance[instance]
        if record["state"] not in {"retained", "reused"}:
            raise ValueError("SDK catalog contains an unresolved phase")
        for field in ("buildKey", "receiptSha256", "objectSha256"):
            require_sha256(record[field], "SDK catalog selected " + field)
        archive = Path(state.sources[instance])
        original = verify_object(archive, build_key=record["buildKey"],
            receipt_sha256=record["receiptSha256"], object_sha256=record["objectSha256"])
        receipt = original["receipt"]
        if (tuple(receipt[field] for field in ("product", "component", "phase", "target"))
                != (instance.product, instance.component, instance.phase, instance.target)
                or receipt["productVersion"] != state.expected_fixed["versions"]["sdk"]
                or not receipt["outputs"] or sha256_bytes(original["receiptBytes"]) != record["receiptSha256"]):
            raise ValueError("SDK catalog original differs from its elected phase/version")
        sources[instance] = IndexEntrySource(original["receiptBytes"],
            min(output["relativePath"] for output in receipt["outputs"]))
        envelopes[instance] = {field: original[field] for field in (
            "receipt", "receiptBytes", "objectSha256")}
        envelopes[instance]["receiptSha256"] = record["receiptSha256"]
        archives[instance] = archive
    object_bytes = sum(archive.stat().st_size for archive in archives.values())
    # The outer transport is stored, with a bounded index/signature/ZIP header allowance.
    if object_bytes > products._CATALOG_LIMIT - 32 * 1024 * 1024:
        raise ValueError("SDK catalog original objects exceed bounded transport capacity")
    index = stage_sdk_same_pr_catalog(sources, envelopes, archives,
        producer=state.producer, destination=destination)
    result = {"phaseCount": len(index["entries"]),
              "objectBytes": object_bytes,
              "indexSha256": sha256_file(Path(destination) / "product-index.json",
                  reject_symlink_parents=True),
              "publicKeySha256": sha256_file(Path(destination) / "public-key.pub",
                  reject_symlink_parents=True)}
    require_no_signing_secret(os.environ)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "discovery-root", "state-root", "repository-root", "destination"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("sdk-validation-tooling", "sdk-apple-validation-policy"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--sdk-original-workflow-sha", required=True)
    parser.add_argument("--github-output", type=Path)
    add_metadata_admission_arguments(parser)
    args = parser.parse_args(argv)
    try:
        require_no_signing_secret(os.environ)
        root = args.repository_root.resolve(strict=True)
        paths = [Path(os.path.abspath(path)) for path in (args.discovery_root, args.state_root)]
        if any(path == root or root not in path.parents for path in paths):
            raise ValueError("SDK catalog state roots must remain inside the repository")
        _require_capability_output_separate(args.destination, [args.plan, *paths])
        if args.github_output is not None:
            _require_capability_output_separate(args.github_output,
                [args.plan, *paths, args.destination])
        with metadata_admission_options(args) as admissions:
            tooling = None if args.sdk_validation_tooling is None else products._canonical_control(
                args.sdk_validation_tooling, "Caller SDK tooling policy")
            apple = None if args.sdk_apple_validation_policy is None else products._canonical_control(
                args.sdk_apple_validation_policy, "Caller Apple validation policy")
            state = products._verified_product_state(args.plan, *paths, root, os.environ,
                tooling, sdk_original_workflow_sha=args.sdk_original_workflow_sha,
                sdk_apple_validation_policy=apple, **admissions)
            result = stage_completed_sdk_catalog(state, args.destination)
        require_no_signing_secret(os.environ)
        github_output(args.github_output, result)
        print(canonical_json_bytes(result).decode().strip())
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
