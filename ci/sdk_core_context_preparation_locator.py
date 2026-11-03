"""Locate the unsigned Core-14 replay upload; do not grant release trust."""

import argparse
import os
from pathlib import Path
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from .products.inventory import (canonical_json_bytes, load_canonical_json_bytes,
    read_regular_file_bytes, require_integer, require_sha256, sha256_bytes)
from .products.receipt import validate_phase_receipt
from .products.signing_isolation import require_no_signing_secret
from .reuse import github_output
from .sdk_apple_upload_locator import _locate


def locate_core_context_preparation(metadata_receipt, *, expected_receipt_sha256,
        preparation_artifact_id, preparation_artifact_sha256, trusted_workflow_sha,
        token, environ=None):
    """Observe the fixed successful Core-14 job and exact caller-pinned upload.

    The receipt digest and preparation ID/digest must be independent worker
    outputs. The returned locator is not evidence that its bytes or replay are
    valid; a protected consumer must capture and verify them before signing.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_sha256(expected_receipt_sha256, "Selected Core metadata receipt")
    require_integer(preparation_artifact_id, "Selected Core preparation upload ID", 1)
    require_sha256(preparation_artifact_sha256, "Selected Core preparation upload digest")
    if type(token) is not str or not token:
        raise ValueError("Core preparation locator requires an observation token")
    path = Path(metadata_receipt).absolute()
    raw = read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    if sha256_bytes(raw) != expected_receipt_sha256:
        raise ValueError("Core metadata receipt differs from independent caller selection")
    receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
    if tuple(receipt[field] for field in ("product", "component", "phase", "target")) != \
            ("sdk", "sdk-core", "metadata", "common"):
        raise ValueError("Core preparation requires an exact selected metadata receipt")
    producer = receipt["producer"]
    name = ("codex-agent-sdk-core-context-preparation-"
            f"{receipt['buildKey'].removeprefix('sha256:')}-{producer['tree']}-"
            f"attempt-{producer['runAttempt']}")
    observed = _locate(producer, phase="preparation",
        job="product-validation / sdk-core-metadata-common", name=name,
        trusted_workflow_sha=trusted_workflow_sha, token=token)
    require_no_signing_secret(environment)
    if (observed != {"artifact_id": preparation_artifact_id,
                     "artifact_sha256": preparation_artifact_sha256}
            or read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                reject_symlink_parents=True) != raw
            or canonical_json_bytes(receipt) != raw):
        raise ValueError("Core preparation upload or selected receipt changed")
    return observed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--metadata-receipt", type=Path, required=True)
    parser.add_argument("--expected-receipt-sha256", required=True)
    parser.add_argument("--preparation-artifact-id", type=int, required=True)
    parser.add_argument("--preparation-artifact-sha256", required=True)
    parser.add_argument("--trusted-workflow-sha", required=True)
    parser.add_argument("--github-output", type=Path)
    args = vars(parser.parse_args(argv))
    try:
        output = args.pop("github_output")
        value = locate_core_context_preparation(**args, token=os.environ["GITHUB_TOKEN"])
        if output is None:
            print(canonical_json_bytes(value).decode().strip())
        else:
            github_output(output, value)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
