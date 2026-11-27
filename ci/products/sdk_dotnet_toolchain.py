"""Exact .NET SDK identity shared by C# binary and NuGet package phases."""

from dataclasses import dataclass
from pathlib import Path
import platform
import subprocess

from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_exact_keys, sha256_bytes,
)


@dataclass(frozen=True)
class SdkDotnetProfile:
    dotnet_sdk: str
    digest: str


def load_sdk_dotnet_profile_bytes(raw: bytes) -> SdkDotnetProfile:
    value = require_exact_keys(load_canonical_json_bytes(raw), {
        "schemaVersion", "runner", "runnerOs", "runnerArch", "dotnetSdk",
    }, "C# .NET toolchain profile")
    if value != {"schemaVersion": 1, "runner": "ubuntu-24.04", "runnerOs": "Linux",
                 "runnerArch": "X64", "dotnetSdk": "8.0.419"} or raw != canonical_json_bytes(value):
        raise ValueError("Unsupported or noncanonical C# .NET toolchain profile")
    return SdkDotnetProfile(dotnet_sdk=value["dotnetSdk"], digest=sha256_bytes(raw))


def _host_identity() -> tuple[str, str, str]:
    system = platform.system()
    machine = platform.machine().lower()
    if system != "Linux" or machine not in {"x86_64", "amd64"}:
        return system, machine, ""
    release = platform.freedesktop_os_release()
    return system, "X64", f"{release.get('ID', '')}-{release.get('VERSION_ID', '')}"


def verify_sdk_dotnet_toolchain(profile_path: Path) -> SdkDotnetProfile:
    profile = load_sdk_dotnet_profile_bytes(read_regular_file_bytes(
        Path(profile_path), max_bytes=4096, reject_symlink_parents=True,
    ))
    if _host_identity() != ("Linux", "X64", "ubuntu-24.04"):
        raise ValueError("C# .NET toolchain host differs from pinned ubuntu-24.04/Linux/X64")
    try:
        observed = subprocess.run(["dotnet", "--version"], capture_output=True, text=True,
                                  check=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError("C# .NET SDK identity could not be observed") from error
    if observed != profile.dotnet_sdk + "\n":
        raise ValueError(f"C# .NET SDK differs from pinned {profile.dotnet_sdk}")
    return profile
