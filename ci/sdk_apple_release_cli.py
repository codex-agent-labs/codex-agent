"""Separate non-secret Apple preparation from protected, replay-free signing."""

import argparse
import os
from pathlib import Path
import re
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.inventory import load_json_bytes, read_regular_file_bytes, require_sha256
from products.signing_isolation import require_no_signing_secret


def _digest(value):
    try:
        return require_sha256(value, "Selected digest")
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _revision(value):
    if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value) is None:
        raise argparse.ArgumentTypeError("Git identity must be a full lowercase object ID")
    return value


def _artifact_id(value):
    if re.fullmatch(r"[1-9][0-9]*", value) is None:
        raise argparse.ArgumentTypeError("Artifact ID must be a positive decimal integer")
    return int(value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    modes = parser.add_subparsers(dest="mode", required=True)
    for mode in ("prepare", "sign"):
        command = modes.add_parser(mode, allow_abbrev=False)
        for name in ("plan", "validation-receipt", "destination", "repository-root"):
            command.add_argument(f"--{name}", type=Path, required=True)
        command.add_argument("--target", choices=("ios-arm64", "ios-simulator-arm64"), required=True)
        for name in ("expected-receipt-sha256", "artifact-sha256"):
            command.add_argument(f"--{name}", type=_digest, required=True)
        command.add_argument("--artifact-id", type=_artifact_id, required=True)
        command.add_argument("--trusted-workflow-sha", type=_revision, required=True)
        if mode == "prepare":
            for name in ("keyring", "keys-directory", "tooling-evidence", "tooling-public-key",
                         "java-executable", "tooling-keyring", "tooling-keys-directory"):
                command.add_argument(f"--{name}", type=Path, required=True)
            command.add_argument("--policy-revision", type=_revision, required=True)
        else:
            command.add_argument("--candidate-root", type=Path, required=True)
            command.add_argument("--preparation-artifact-id", type=_artifact_id, required=True)
            command.add_argument("--preparation-artifact-sha256", type=_digest, required=True)
            for name in ("trusted-source-sha", "validation-tree"):
                command.add_argument(f"--{name}", type=_revision, required=True)
    args = parser.parse_args(argv)
    common = dict(target=args.target, expected_receipt_sha256=args.expected_receipt_sha256,
        artifact_id=args.artifact_id, artifact_sha256=args.artifact_sha256,
        trusted_workflow_sha=args.trusted_workflow_sha, token=os.environ.get("GITHUB_TOKEN", ""))
    try:
        if args.mode == "prepare":
            # Import replay code only after confirming this process has no signing secret.
            require_no_signing_secret(os.environ)
            from sdk_ios_original_validation import prepare_ios_validation_signing_inputs
            prepare_ios_validation_signing_inputs(args.plan, args.validation_receipt, args.destination,
                **common, repository_root=args.repository_root, environ=os.environ,
                keyring=args.keyring, keys_directory=args.keys_directory,
                tooling_evidence=args.tooling_evidence, tooling_public_key=args.tooling_public_key,
                java_executable=args.java_executable, policy_revision=args.policy_revision,
                tooling_keyring=args.tooling_keyring, tooling_keys_directory=args.tooling_keys_directory,
                required_trust_domain="release")
        else:
            event_payload = load_json_bytes(read_regular_file_bytes(Path(os.environ["GITHUB_EVENT_PATH"]),
                max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
            if not isinstance(event_payload, dict):
                raise ValueError("GitHub event must be an object")
            event = os.environ.get("GITHUB_EVENT_NAME")
            producer = {
                "repository": os.environ.get("GITHUB_REPOSITORY"), "workflowPath": ".github/workflows/ci.yml",
                "commit": os.environ.get("GITHUB_SHA"), "tree": args.validation_tree, "event": event,
                "runId": int(os.environ["GITHUB_RUN_ID"]), "runAttempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
                "pullRequest": event_payload.get("number") if event == "pull_request" else None,
            }
            from sdk_apple_prepared_release import attest_prepared_apple_validation_ci
            attest_prepared_apple_validation_ci(args.repository_root, args.candidate_root, args.plan,
                args.validation_receipt, args.destination, **common,
                preparation_artifact_id=args.preparation_artifact_id,
                preparation_artifact_sha256=args.preparation_artifact_sha256,
                trusted_source_sha=args.trusted_source_sha, transport_producer=producer,
                event_payload=event_payload, environment=os.environ)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
