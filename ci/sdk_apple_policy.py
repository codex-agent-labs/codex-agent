"""Construct invocation-only Apple release policy from caller-owned inputs.

The tooling policy must already come from caller-authenticated capture. This
helper neither executes tooling nor authenticates evidence or signatures; all
original semantic gates remain mandatory on use. No retained state supplies
policy, and no product signing secret may be present.
"""

import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_regular_directory, write_canonical_json,
)
from products.sdk_apple_validation_admission import apple_validation_policy_arguments
from products.sdk_package import _require_capability_output_separate
from products.signing_isolation import require_no_signing_secret
from reuse import github_output


_LIMIT = 16 * 1024 * 1024
POLICY_NAME = "apple-validation-policy.json"
_TOOLING_FIELDS = {
    "evidence": "toolingEvidence", "publicKey": "toolingPublicKey", "javaExecutable": "javaExecutable",
    "requiredTrustDomain": "toolingTrustDomain", "keyring": "toolingKeyring", "keysDirectory": "toolingKeysDirectory",
}


def create_apple_validation_policy(plan_path, tooling_policy_path, destination, *, repository_root, environ=None):
    """Publish current Git public keys plus the existing canonical policy schema."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    repository = Path(repository_root).resolve(strict=True)
    plan_path, tooling_policy_path = Path(plan_path).absolute(), Path(tooling_policy_path).absolute()
    output = Path(destination).absolute()
    originals = {"plan": read_regular_file_bytes(plan_path, max_bytes=_LIMIT, reject_symlink_parents=True),
                 "tooling-policy": read_regular_file_bytes(tooling_policy_path, max_bytes=_LIMIT, reject_symlink_parents=True)}
    tooling = require_exact_keys(load_canonical_json_bytes(originals["tooling-policy"]),
                                 set(_TOOLING_FIELDS), "Caller SDK tooling policy")
    if tooling["requiredTrustDomain"] != "release":
        raise ValueError("Apple policy construction requires release tooling trust")
    policy = {"plan": str(plan_path), "attestationPublicKey": None, "attestationTrustDomain": "release",
              "keyring": str(output / "trust/product-signing-keys.json"), "keysDirectory": str(output / "trust/keys"),
              **{target: tooling[source] for source, target in _TOOLING_FIELDS.items()}}
    arguments = apple_validation_policy_arguments(policy)
    files = {"plan": plan_path, "tooling-policy": tooling_policy_path,
             "tooling-public-key": arguments["tooling_public_key"], "java": arguments["java_executable"],
             "tooling-keyring": arguments["tooling_keyring"]}
    directories = {"tooling-evidence": arguments["tooling_evidence"], "tooling-keys": arguments["tooling_keys_directory"]}

    def output_safe():
        _require_capability_output_separate(output, [repository, *files.values(), *directories.values()])
        if output.exists() or output.is_symlink():
            raise ValueError("Apple policy destination must not exist")
        if output != output.resolve(strict=False):
            raise ValueError("Apple policy destination must use its real absolute path")
        for ancestor in output.parents:
            if ancestor.exists() or ancestor.is_symlink():
                require_regular_directory(ancestor, "Apple policy output ancestry")

    output_safe()
    before_files = {name: (originals[name] if name in originals else read_regular_file_bytes(
        path, max_bytes=128 * 1024 * 1024, reject_symlink_parents=True)) for name, path in files.items()}
    for path in directories.values():
        require_regular_directory(path, "Caller tooling directory")
    before_dirs = {name: regular_file_inventory(path, allow_empty=True) for name, path in directories.items()}
    with tempfile.TemporaryDirectory(prefix="apple-caller-policy-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, [output, repository, *files.values(), *directories.values()])
        captured_plan = private / "impact-plan.json"
        captured_plan.write_bytes(originals["plan"])
        plan = products._validate_plan(captured_plan, repository)
        revision, tree = plan["validationCommit"], plan["validationTree"]
        prepared = private / "prepared"
        trust = products._release_trust(repository, revision, prepared)
        if trust is None:
            raise ValueError("Apple policy requires current Git-owned release keys")
        trust_inventory = regular_file_inventory(prepared / "trust")

        def unchanged():
            require_no_signing_secret(environment)
            if (any(read_regular_file_bytes(path, max_bytes=128 * 1024 * 1024,
                    reject_symlink_parents=True) != before_files[name] for name, path in files.items())
                    or any(regular_file_inventory(path, allow_empty=True) != before_dirs[name]
                           for name, path in directories.items())
                    or read_regular_file_bytes(captured_plan) != originals["plan"]
                    or regular_file_inventory(prepared / "trust") != trust_inventory
                    or products._git_value(repository, "rev-parse", "HEAD^{commit}") != revision
                    or products._git_value(repository, "rev-parse", "HEAD^{tree}") != tree):
                raise ValueError("Apple caller policy inputs changed during construction")

        unchanged()
        write_canonical_json(prepared / POLICY_NAME, policy)
        unchanged()
        if read_regular_file_bytes(prepared / POLICY_NAME) != canonical_json_bytes(policy):
            raise ValueError("Apple invocation policy changed before publication")
        output_safe()
        publish_regular_tree(prepared, output)
    return policy


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "tooling-policy", "destination", "repository-root"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    try:
        create_apple_validation_policy(args.plan, args.tooling_policy, args.destination,
                                      repository_root=args.repository_root, environ=os.environ)
        result = {"policy_path": str(args.destination.absolute() / POLICY_NAME)}
        if args.github_output is None:
            print(canonical_json_bytes(result).decode().strip())
        else:
            github_output(args.github_output, result)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
