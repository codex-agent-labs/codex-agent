"""Recover a current target's exact worker receipt before preparation/signing.

This transport bootstrap grants no semantic or release admission. Both subsequent
controllers independently recapture and verify the selected original upload.
"""

import argparse
import os
from pathlib import Path
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from sdk_apple_upload_locator import locate_apple_upload
from products.inventory import canonical_json_bytes, require_sha256
from products.signing_isolation import require_no_signing_secret
from reuse import github_output


def capture_worker(plan, candidate_root, destination, *, target, expected_build_key,
                   trusted_workflow_sha, environ=None, token):
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    destination = Path(destination).absolute()
    if any(character in str(destination) for character in "\r\n"):
        raise ValueError("Apple receipt output path must occupy one line")
    locator = locate_apple_upload(plan, candidate_root, mode="validation", target=target,
        expected_build_key=expected_build_key, trusted_workflow_sha=trusted_workflow_sha,
        environ=environment, token=token)
    captured = products.capture_elected_sdk_ios_validation_upload(plan, destination,
        target=target, expected_build_key=expected_build_key, **locator,
        trusted_workflow_sha=trusted_workflow_sha, repository_root=candidate_root,
        environ=environment, token=token)
    require_no_signing_secret(environment)
    return {**locator, "receipt_path": str(destination / "original/shard/phase-receipt.json"),
            "receipt_sha256": require_sha256(captured["validationReceiptSha256"], "Captured Apple receipt digest")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "candidate-root", "destination"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--target", choices=("ios-arm64", "ios-simulator-arm64"), required=True)
    parser.add_argument("--expected-build-key", required=True)
    parser.add_argument("--trusted-workflow-sha", required=True)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    try:
        value = capture_worker(args.plan, args.candidate_root, args.destination, target=args.target,
            expected_build_key=args.expected_build_key, trusted_workflow_sha=args.trusted_workflow_sha,
            environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""))
        if args.github_output is None:
            print(canonical_json_bytes(value).decode().strip())
        else:
            github_output(args.github_output, value)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
