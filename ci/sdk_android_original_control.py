"""Compose fresh Android metadata control from independent caller policy.

The successful validation worker outputs are locator/equality constraints, not
authority over the Contract, S858, tooling, source, or original Firebase work.
Those remain caller-owned and are replayed by the metadata reader.
"""

import argparse
import os
from pathlib import Path
import re
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, require_exact_keys,
    require_integer, require_sha256, write_canonical_json,
)
from products.signing_isolation import require_no_signing_secret


_BASE = {
    "compatibilityRequest", "binaryContractEvidence", "trustedSourceCommit",
    "trustedSourceTree", "toolingEvidence", "toolingPublicKey",
    "javaExecutable", "apkanalyzerExecutable", "toolingTrustDomain",
    "toolingKeyring", "toolingKeysDirectory", "trustedAndroidWorkflowSha",
}
_VALIDATION = {
    "validationReceiptSha256", "validationArtifactId",
    "validationArtifactSha256", "validationRunId", "validationRunAttempt",
}
_OID = re.compile(r"[0-9a-f]{40}")


def compose(base, validation, *, expected_run_id, expected_run_attempt,
            repository_root):
    """Return exact metadata original policy, never selecting inputs from state."""
    require_no_signing_secret(os.environ)
    repository = Path(repository_root).resolve(strict=True)
    if not repository.is_dir():
        raise ValueError("Android original repository root is not a directory")
    base = require_exact_keys(base, _BASE, "Independent Android original policy")
    validation = require_exact_keys(
        validation, _VALIDATION, "Successful Android validation outputs")
    for name in ("trustedSourceCommit", "trustedSourceTree", "trustedAndroidWorkflowSha"):
        if type(base[name]) is not str or _OID.fullmatch(base[name]) is None:
            raise ValueError(f"Android original {name} is not an exact Git SHA")
    for name in ("validationReceiptSha256", "validationArtifactSha256"):
        require_sha256(validation[name], f"Successful Android {name}")
    for name in ("validationArtifactId", "validationRunId", "validationRunAttempt"):
        require_integer(validation[name], f"Successful Android {name}", 1)
    if (validation["validationRunId"] != require_integer(
            expected_run_id, "Current Android run ID", 1)
            or validation["validationRunAttempt"] != require_integer(
                expected_run_attempt, "Current Android run attempt", 1)):
        raise ValueError("Android validation outputs differ from the selected campaign attempt")
    if base["toolingTrustDomain"] not in ("development", "release"):
        raise ValueError("Android original tooling trust domain is invalid")
    if ((base["toolingKeyring"] is None) != (base["toolingKeysDirectory"] is None)
            or (base["toolingTrustDomain"] == "release") !=
               (base["toolingKeyring"] is not None)):
        raise ValueError("Android original tooling trust policy is incomplete")
    for name in _BASE - {
            "trustedSourceCommit", "trustedSourceTree", "trustedAndroidWorkflowSha",
            "toolingTrustDomain", "toolingKeyring", "toolingKeysDirectory",
            "toolingEvidence"}:
        _external(_source_path(base[name], name), repository, name)
    if base["toolingKeyring"] is not None:
        _external(_source_path(base["toolingKeyring"], "toolingKeyring"), repository,
                  "toolingKeyring")
        _external(_source_path(base["toolingKeysDirectory"], "toolingKeysDirectory",
                               directory=True), repository, "toolingKeysDirectory")
    _external(_source_path(base["toolingEvidence"], "toolingEvidence", directory=True),
              repository, "toolingEvidence")
    return {
        "schemaVersion": 1, **base,
        "validationReceiptSha256": validation["validationReceiptSha256"],
        "validationArtifactId": validation["validationArtifactId"],
        "validationArtifactSha256": validation["validationArtifactSha256"],
        "expectedOriginalRunId": validation["validationRunId"],
        "expectedOriginalRunAttempt": validation["validationRunAttempt"],
    }


def _source_path(value, label, *, directory=False):
    path = Path(value) if type(value) is str and value else None
    if (path is None or not path.is_absolute() or path.resolve(strict=True) != path
            or (not path.is_dir() if directory else not path.is_file())):
        raise ValueError(f"Android original {label} must be an absolute non-symbolic source")
    return path


def _external(path, repository, label):
    if path == repository or repository in path.parents:
        raise ValueError(f"Android original {label} cannot come from the source checkout")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--base-policy", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    for name in ("validation-receipt-sha256", "validation-artifact-id",
                 "validation-artifact-sha256", "validation-run-id",
                 "validation-run-attempt", "expected-run-id", "expected-run-attempt"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    try:
        repository = Path(args.repository_root).resolve(strict=True)
        base_path = _external(_source_path(str(args.base_policy), "basePolicy"),
                              repository, "basePolicy")
        base = load_canonical_json_bytes(read_regular_file_bytes(
            base_path, reject_symlink_parents=True))
        validation = {
            "validationReceiptSha256": args.validation_receipt_sha256,
            "validationArtifactId": int(args.validation_artifact_id),
            "validationArtifactSha256": args.validation_artifact_sha256,
            "validationRunId": int(args.validation_run_id),
            "validationRunAttempt": int(args.validation_run_attempt),
        }
        value = compose(base, validation, expected_run_id=int(args.expected_run_id),
                        expected_run_attempt=int(args.expected_run_attempt),
                        repository_root=repository)
        destination = Path(args.destination).absolute()
        if destination.exists() or destination.is_symlink() or destination.resolve(strict=False) != destination:
            raise ValueError("Android original control destination must be fresh and non-symbolic")
        _external(destination, repository, "control destination")
        if destination == base_path or base_path in destination.parents or destination in base_path.parents:
            raise ValueError("Android original control must not overwrite its source policy")
        destination.parent.mkdir(parents=True, exist_ok=True)
        write_canonical_json(destination, value)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
