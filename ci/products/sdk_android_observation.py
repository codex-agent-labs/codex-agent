"""Bind protected Firebase submission inputs; never attest Firebase success."""

import argparse
from pathlib import Path
import re
import tempfile

if __package__ == "products":  # Script entry points in ci/ use this namespace.
    from receipt import validate_receipt
else:
    from ..receipt import validate_receipt
from .inventory import (
    canonical_json_bytes, publish_regular_tree, read_regular_file_bytes, run_git,
    sha256_bytes,
)
from .sdk_package import _require_capability_output_separate


SUBMISSION_FILES = {
    "application.apk": "payload/tooling/android-runtime-evidence/build/outputs/apk/debug/android-runtime-evidence-debug.apk",
    "test.apk": "payload/tooling/android-runtime-evidence/build/outputs/apk/androidTest/debug/android-runtime-evidence-debug-androidTest.apk",
    "runtime.aar": "payload/codex-agent-runtime-android/build/outputs/aar/codex-agent-runtime-android-release.aar",
    "lane-receipt.json": "lane-receipt.json",
}


def bind_submission(*, repository: Path, lane: Path, plan: Path, observation: Path,
                    candidate_commit: str, candidate_tree: str,
                    trusted_source_commit: str, trusted_source_tree: str, create: bool) -> None:
    """Create once before submission, or compare exact originals afterward.

    The protected workflow selects main's immutable source identity before any
    checkout code runs. Supplied identities are policy, not authority from data.
    The original lane checker remains mandatory and no receipt is rewritten.
    """
    identities = (candidate_commit, candidate_tree, trusted_source_commit, trusted_source_tree)
    if any(type(value) is not str or re.fullmatch(r"[0-9a-f]{40}", value) is None for value in identities):
        raise ValueError("Firebase submission requires exact Git identities")
    paths = [Path(value).absolute() for value in (repository, lane, plan, observation)]
    if any(path.resolve(strict=False) != path for path in paths):
        raise ValueError("Firebase submission paths must be normalized and non-symbolic")
    repository, lane, plan, observation = paths
    _require_capability_output_separate(observation, (lane, plan))

    def source_identity():
        if (run_git(repository, "rev-parse", "HEAD").strip() != trusted_source_commit or
                run_git(repository, "rev-parse", "HEAD^{tree}").strip() != trusted_source_tree):
            raise ValueError("Firebase checked-out source differs from the protected selection")
        run_git(repository, "diff", "--quiet", "HEAD", "--")

    def inputs():
        source_identity()
        raw = {name: read_regular_file_bytes(lane / relative, max_bytes=512 * 1024 * 1024,
                                           reject_symlink_parents=True)
               for name, relative in SUBMISSION_FILES.items()}
        if any(not value for value in raw.values()):
            raise ValueError("Firebase submission input is empty")
        receipt = validate_receipt(lane / "lane-receipt.json", plan, lane, "android")
        if receipt["validationCommit"] != candidate_commit or receipt["validationTree"] != candidate_tree:
            raise ValueError("Firebase submission differs from the selected candidate")
        return raw

    plan_bytes = read_regular_file_bytes(plan, reject_symlink_parents=True)
    original = inputs()
    binding = canonical_json_bytes({
        "schemaVersion": 1, "kind": "firebase-android-input-binding",
        "candidateCommit": candidate_commit, "candidateTree": candidate_tree,
        "trustedSourceCommit": trusted_source_commit, "trustedSourceTree": trusted_source_tree,
        "files": [{"relativePath": name, "bytes": len(raw), "sha256": sha256_bytes(raw)}
                  for name, raw in sorted(original.items())],
    })

    def unchanged():
        if inputs() != original or read_regular_file_bytes(plan, reject_symlink_parents=True) != plan_bytes:
            raise ValueError("Firebase submission inputs changed during binding")

    if create:
        with tempfile.TemporaryDirectory(prefix="firebase-submission-") as temporary:
            staged = Path(temporary).resolve() / "observation"
            staged.mkdir()
            (staged / "input-binding.json").write_bytes(binding)
            (staged / "lane-receipt.json").write_bytes(original["lane-receipt.json"])
            unchanged()
            publish_regular_tree(staged, observation)
    try:
        if (read_regular_file_bytes(observation / "input-binding.json", reject_symlink_parents=True) != binding or
                read_regular_file_bytes(observation / "lane-receipt.json", reject_symlink_parents=True)
                != original["lane-receipt.json"]):
            raise ValueError("Firebase submission differs from its protected original binding")
    finally:
        unchanged()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("create", "verify"))
    for field in ("repository", "lane", "plan", "observation"):
        parser.add_argument("--" + field, type=Path, required=True)
    for field in ("candidate-commit", "candidate-tree", "trusted-source-commit", "trusted-source-tree"):
        parser.add_argument("--" + field, required=True)
    values = vars(parser.parse_args())
    values["create"] = values.pop("mode") == "create"
    bind_submission(**values)


if __name__ == "__main__":
    main()
