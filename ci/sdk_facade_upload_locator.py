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


_FACADE = ({("sdk", "sdk-core", "validation", target) for target in SDK_FACADE_TARGETS}
           | {("sdk", "sdk-core", "metadata", "common")})
_MAVEN = {("sdk", component, phase, target)
          for component, target in (("sdk-core", "common"), ("sdk-android", "android"))
          for phase in ("binary", "package")}


def locate_original_facade_upload(receipt_path, *, expected_receipt_sha256,
        trusted_workflow_sha, token, environ=None):
    """Locate an independently selected Core validation/metadata upload."""
    return _locate_selected(receipt_path, _FACADE, expected_receipt_sha256,
                            trusted_workflow_sha, token, environ)


def locate_original_maven_upload(receipt_path, *, expected_receipt_sha256,
        trusted_workflow_sha, token, environ=None):
    """Locate an independently selected Core/Android binary/package upload."""
    return _locate_selected(receipt_path, _MAVEN, expected_receipt_sha256,
                            trusted_workflow_sha, token, environ)


def _locate_selected(receipt_path, allowed, expected_receipt_sha256,
        trusted_workflow_sha, token, environ):
    """Official routing only; full original capture and semantic replay follow."""
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
    if identity not in allowed:
        raise ValueError("SDK upload locator requires an exact selected phase receipt")
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
    parser.add_argument("--maven", action="store_true", help="Locate a Core/Android binary or package upload")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    try:
        locator = locate_original_maven_upload if args.maven else locate_original_facade_upload
        value = locator(args.receipt,
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
