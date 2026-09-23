"""Locate original Core uploads; this grants neither capture nor content admission."""

import argparse
import os
from pathlib import Path
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from products.inventory import (canonical_json_bytes, load_canonical_json_bytes,
    read_regular_file_bytes, require_sha256, sha256_bytes)
from products.registry import SDK_FACADE_TARGETS
from products.signing_isolation import require_no_signing_secret
from reuse import github_output
from sdk_apple_upload_locator import _locate
from sdk_facade_capture import _capture_route


def locate_original_facade_upload(receipt_path, *, expected_receipt_sha256,
        trusted_workflow_sha, token, environ=None):
    """Return an official ID/digest for a caller-authenticated original receipt.

    The caller selects and authenticates the receipt independently. Its original
    producer, never the current run or a retained descriptor, fixes the route.
    Consumption must still capture and replay the complete original upload.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if type(token) is not str or not token:
        raise ValueError("Core upload locator requires an observation token")
    require_sha256(expected_receipt_sha256, "Caller-selected Core receipt")
    path = Path(receipt_path).absolute()
    raw = read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    if sha256_bytes(raw) != expected_receipt_sha256:
        raise ValueError("Core receipt differs from independent caller selection")
    receipt = products.validate_phase_receipt(load_canonical_json_bytes(raw))
    identity = tuple(receipt[field] for field in ("product", "component", "phase", "target"))
    if identity not in ({("sdk", "sdk-core", "validation", target) for target in SDK_FACADE_TARGETS}
            | {("sdk", "sdk-core", "metadata", "common")}):
        raise ValueError("Core upload locator requires an exact validation or metadata receipt")
    _, _, _, job, name, phase = _capture_route(receipt)
    result = _locate(receipt["producer"], phase=phase, job=job, name=name,
                     trusted_workflow_sha=trusted_workflow_sha, token=token)
    require_no_signing_secret(environment)
    if (read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != raw
            or canonical_json_bytes(receipt) != raw):
        raise ValueError("Original Core receipt changed during observation")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--expected-receipt-sha256", required=True)
    parser.add_argument("--trusted-workflow-sha", required=True)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    try:
        value = locate_original_facade_upload(args.receipt,
            expected_receipt_sha256=args.expected_receipt_sha256,
            trusted_workflow_sha=args.trusted_workflow_sha, token=os.environ["GITHUB_TOKEN"])
        if args.github_output is None:
            print(canonical_json_bytes(value).decode().strip())
        else:
            github_output(args.github_output, value)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
