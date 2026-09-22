"""Require completion of every selected SDK phase in authenticated replay."""

import argparse
import os
from pathlib import Path
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from products.inventory import (
    canonical_json_bytes, require_array, require_boolean, require_exact_keys,
    require_integer, require_object, require_sha256, require_string,
)
from reuse import github_output


def require_sdk_completion(plan_path, discovery_root, state_root=None, *,
                           repository_root=None, environ=None, sdk_validation_tooling=None,
                           sdk_apple_validation_policy=None,
                           sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Check the full replayed SDK closure, not a family matrix or new election.

    Existing inspection authenticates the exact result schema, requested closure,
    original receipts and phase states. Global ``result`` may be build-required
    for unrelated products; SDK completion stays scoped while fullReuse forwards
    the same authenticated replay's global result for the final merge gate.
    No SDK selection is a successful no-op, not evidence of a produced SDK.
    """
    inspected = products.inspect_products(plan_path, discovery_root, state_root,
        repository_root=repository_root, environ=environ,
        **({"sdk_validation_tooling": sdk_validation_tooling} if sdk_validation_tooling is not None else {}),
        **({"sdk_apple_validation_policy": sdk_apple_validation_policy}
           if sdk_apple_validation_policy is not None else {}),
        **products._metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
    result = require_exact_keys(require_object(inspected, "SDK completion inspection").get("result"),
                                products._REUSE_RESULT_KEYS, "SDK completion replay result")
    if (require_integer(result["schemaVersion"], "SDK completion result schema", 1) != 1
            or require_string(result["result"], "SDK completion result status") not in {"complete", "build-required"}
            or require_boolean(result["fullReuse"], "SDK completion full reuse") != (result["result"] == "complete")):
        raise ValueError("Invalid SDK completion replay status")
    unresolved, seen, count = [], set(), 0
    for value in require_array(result["phases"], "SDK completion phases"):
        phase = require_exact_keys(value, products._REUSE_PHASE_KEYS, "SDK completion phase")
        for field in (*products._IDENTITY_KEYS, "state"):
            require_string(phase[field], "SDK completion phase " + field)
        identity = products._identity(phase)
        if identity in seen or phase["state"] not in {"retained", "reused", "build", "waiting"}:
            raise ValueError("Duplicate or unsupported SDK completion phase")
        seen.add(identity)
        if identity.product != "sdk":
            continue
        count += 1
        if phase["state"] not in {"retained", "reused"}:
            unresolved.append(f"{identity.component}/{identity.phase}/{identity.target}: {phase['state']}")
        else:
            for field in ("buildKey", "receiptSha256", "objectSha256"):
                require_sha256(phase[field], "Completed SDK phase " + field)
    if unresolved:
        raise ValueError("Selected SDK phases remain unresolved: " + ", ".join(unresolved))
    return {"complete": True, "phaseCount": count, "fullReuse": result["fullReuse"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "discovery-root", "repository-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("state-root", "sdk-validation-tooling", "sdk-apple-validation-policy", "github-output"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args(argv)
    try:
        tooling = {} if args.sdk_validation_tooling is None else {"sdk_validation_tooling":
            products._canonical_control(args.sdk_validation_tooling, "Caller SDK tooling policy")}
        apple = {} if args.sdk_apple_validation_policy is None else {"sdk_apple_validation_policy":
            products._canonical_control(args.sdk_apple_validation_policy, "Caller Apple validation policy")}
        result = require_sdk_completion(args.plan, args.discovery_root, args.state_root,
            repository_root=args.repository_root, environ=os.environ, **tooling, **apple)
        if args.github_output is None:
            print(canonical_json_bytes(result).decode().strip())
        else:
            github_output(args.github_output, result)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
