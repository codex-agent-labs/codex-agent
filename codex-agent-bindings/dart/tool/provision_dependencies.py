#!/usr/bin/env python3
"""Resolve locked, already-cached Dart dependencies outside the checkout.

This is tooling preparation, never SDK validation or source admission. The
caller supplies an installed Dart executable and an already-populated pub cache.
No downloads, source compilation, copied-source authority or lock updates are
allowed. The existing evidence producer still requires the actual binding ROOT.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import produce_sdk_validation_evidence as evidence


def prepare(*, dart_executable: Path, pub_cache: Path, output: Path) -> Path:
    """Return an external package_config.json accepted by the unchanged producer."""
    dart_executable, pub_cache, output = map(Path, (dart_executable, pub_cache, output))
    if any(not path.is_absolute() for path in (dart_executable, pub_cache, output)):
        raise ValueError("Dart provisioning requires explicit absolute paths")
    executable = evidence._required(dart_executable)
    if executable.name not in {"dart", "dart.exe"}:
        raise ValueError("Dart provisioning requires the fixed installed Dart executable")
    cache = evidence._required(pub_cache, directory=True)
    source = evidence._required(evidence.ROOT, directory=True)
    checkout = evidence._required(evidence.CHECKOUT, directory=True)
    if cache.is_relative_to(checkout) or checkout.is_relative_to(cache):
        raise ValueError("Dart pub cache must be outside and separate from the checkout")
    files = evidence._source_files()
    originals = {path: path.read_bytes() for path in files}
    manifests = {name: evidence._required(source / name).read_bytes() for name in ("pubspec.yaml", "pubspec.lock")}
    executable_bytes = executable.read_bytes()
    output = evidence._output_scope(output, (cache, executable, *files))
    if output.is_relative_to(checkout) or output.exists():
        raise ValueError("Dart provisioning requires a fresh output outside the checkout")
    output.mkdir(parents=True)
    project = output / "resolution"
    project.mkdir()
    for name, raw in manifests.items():
        (project / name).write_bytes(raw)

    def unchanged():
        current = evidence._source_files()
        if (set(current) != set(originals) or any(path.read_bytes() != raw for path, raw in originals.items())
                or evidence._required(executable).read_bytes() != executable_bytes
                or any(evidence._required(project / name).read_bytes() != raw for name, raw in manifests.items())):
            raise ValueError("Dart binding source, executable or exact resolution lock changed")

    environment = dict(os.environ)
    environment["PUB_CACHE"] = str(cache)
    command = [str(executable), "pub", "get", "--enforce-lockfile", "--offline"]
    started, return_code, launch_error = time.monotonic_ns(), None, None
    try:
        unchanged()
        with (output / "pub.log").open("xb") as log:
            return_code = subprocess.run(command, cwd=project, env=environment, stdout=log,
                stderr=subprocess.STDOUT, check=False).returncode
    except OSError as error:
        launch_error = str(error)
        raise
    finally:
        with (output / "execution.json").open("xb") as trace:
            trace.write((json.dumps({"schemaVersion": 1, "command": command, "workingDirectory": str(project),
                "returnCode": return_code, "launchError": launch_error, "elapsedNs": time.monotonic_ns() - started},
                sort_keys=True, separators=(",", ":")) + "\n").encode())
        unchanged()
    if return_code != 0:
        raise ValueError(f"Dart offline dependency resolution failed with exit code {return_code}; see {output / 'pub.log'}")

    original_config = evidence._required(project / ".dart_tool/package_config.json")
    original_config_bytes = original_config.read_bytes()
    configuration = json.loads(original_config_bytes)
    if (type(configuration) is not dict or configuration.get("configVersion") != 2
            or type(configuration.get("packages")) is not list):
        raise ValueError("Dart resolution did not produce package-config version 2")
    for package in configuration["packages"]:
        root = evidence._package_root(original_config, package["rootUri"])
        if package["name"] == "codex_agent":
            if root != project:
                raise ValueError("Dart resolution root differs from its exact isolated manifest")
            root = source
        elif not root.is_relative_to(cache):
            raise ValueError("Dart resolved dependency escapes the caller pub cache")
        package["rootUri"] = root.as_uri() + "/"
    candidate = output / "package_config.pending.json"
    normalized = (json.dumps(configuration, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with candidate.open("xb") as handle:
        handle.write(normalized)
    # Reuse the producer's exact runner/source check; never accept a copied
    # codex_agent root as authority. Original pub output is retained separately.
    evidence._resolved_runner(candidate)
    unchanged()
    if (evidence._required(original_config).read_bytes() != original_config_bytes
            or evidence._required(candidate).read_bytes() != normalized):
        raise ValueError("Dart original package configuration changed during normalization")
    final = output / "package_config.json"
    # A fresh hard link exposes the verified bytes without overwriting another
    # caller's file or making partially written configuration visible.
    os.link(candidate, final)
    candidate.unlink()
    return final


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("dart-executable", "pub-cache", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        result = prepare(dart_executable=arguments.dart_executable, pub_cache=arguments.pub_cache, output=arguments.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
