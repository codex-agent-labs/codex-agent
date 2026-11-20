#!/usr/bin/env python3
"""Test current build logic using an authenticated original standalone toolkit."""

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ci.products.inventory import load_canonical_json_bytes, read_regular_file_bytes, require_exact_keys
from ci.products.tooling import verified_tooling_capture


_INIT = """def jar = System.getProperty('codexAgent.verifiedTestTooling')
gradle.projectsEvaluated {
    gradle.rootProject.allprojects { project ->
        project.tasks.withType(org.gradle.api.tasks.testing.Test).configureEach { test ->
            test.systemProperty('codexAgent.releaseToolingJar', jar)
            test.classpath = test.classpath + project.files(jar)
        }
    }
}
"""
_PATHS = {"evidence", "publicKey", "javaExecutable", "keyring", "keysDirectory"}


def run(*, repository_root: Path, tooling_policy: Path, policy_revision: str, tests=()) -> int:
    if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", policy_revision) is None:
        raise ValueError("An exact tooling policy revision is required")
    if any(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", name) is None
           for name in tests):
        raise ValueError("Test selectors must be exact class names")
    if tests and os.environ.get("GITHUB_ACTIONS") == "true":
        raise ValueError("Focused test selectors are local-only")
    repository = Path(repository_root).resolve(strict=True)
    policy = load_canonical_json_bytes(read_regular_file_bytes(tooling_policy, max_bytes=65536,
                                                               reject_symlink_parents=True))
    require_exact_keys(policy, _PATHS | {"requiredTrustDomain"}, "build-logic tooling policy")
    if policy["requiredTrustDomain"] != "release":
        raise ValueError("Build-logic tests require release tooling")
    for name in _PATHS:
        if type(policy[name]) is not str or not Path(policy[name]).is_absolute():
            raise ValueError(f"Tooling policy {name} must be an absolute path")

    failure = None
    with verified_tooling_capture(Path(policy["evidence"]), repository, Path(policy["publicKey"]),
            required_trust_domain="release", keyring=Path(policy["keyring"]),
            keys_directory=Path(policy["keysDirectory"]), policy_revision=policy_revision,
            use="full") as jar:
        with tempfile.TemporaryDirectory(prefix="build-logic-tests-") as temporary:
            init = Path(temporary) / "verified-tooling.init.gradle"
            init.write_text(_INIT, encoding="utf-8")
            command = [str(repository / "gradlew"), "-p", "gradle/build-logic", "test",
                "-Pkotlin.daemon.jvmargs=-Xmx2g", "--configuration-cache",
                "--configuration-cache-problems=fail", "--no-build-cache",
                "-x", "releaseToolingJar", "--init-script", str(init),
                f"-DcodexAgent.verifiedTestTooling={jar}"]
            for selector in tests:
                command.extend(("--tests", selector))
            try:
                result = subprocess.run(command, cwd=repository, check=False)
            except BaseException as error:
                # Exit the owning capture normally so its lifetime checks also run
                # after launch failures or interruption; then preserve the error.
                failure = error
    if failure is not None:
        raise failure
    return result.returncode


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--tooling-policy", type=Path, required=True)
    parser.add_argument("--policy-revision", required=True)
    parser.add_argument("--tests", action="append", default=[])
    args = parser.parse_args(argv)
    return run(repository_root=args.repository_root, tooling_policy=args.tooling_policy,
               policy_revision=args.policy_revision, tests=args.tests)


if __name__ == "__main__":
    raise SystemExit(main())
