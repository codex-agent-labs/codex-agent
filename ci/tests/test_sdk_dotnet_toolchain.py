"""C# binary and NuGet package share one immutable .NET SDK identity."""

import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci.products.sdk_dotnet_toolchain import (
    load_sdk_dotnet_profile_bytes, verify_sdk_dotnet_toolchain,
)


PROFILE = Path(__file__).resolve().parents[2] / "gradle/release/toolchains/sdk/csharp.json"


class SdkDotnetToolchainTest(unittest.TestCase):
    def test_tracked_profile_is_exact_and_content_addressed(self) -> None:
        raw = PROFILE.read_bytes()
        profile = load_sdk_dotnet_profile_bytes(raw)
        self.assertEqual("8.0.419", profile.dotnet_sdk)
        self.assertEqual("sha256:" + hashlib.sha256(raw).hexdigest(), profile.digest)
        with self.assertRaises(ValueError):
            load_sdk_dotnet_profile_bytes(raw[:-1] + b" ")
        with self.assertRaises(ValueError):
            load_sdk_dotnet_profile_bytes(raw.replace(b'"8.0.419"', b'"10.0.102"'))

    def test_preflight_checks_host_and_actual_dotnet_before_build_or_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / "csharp.json"
            path.write_bytes(PROFILE.read_bytes())
            with patch("ci.products.sdk_dotnet_toolchain._host_identity", return_value=(
                    "Linux", "X64", "ubuntu-24.04")), patch(
                    "ci.products.sdk_dotnet_toolchain.subprocess.run", return_value=subprocess.CompletedProcess(
                        ["dotnet", "--version"], 0, stdout="8.0.419\n")) as observed:
                self.assertEqual("8.0.419", verify_sdk_dotnet_toolchain(path).dotnet_sdk)
                observed.assert_called_once()
            with patch("ci.products.sdk_dotnet_toolchain._host_identity", return_value=(
                    "Linux", "X64", "ubuntu-24.04")), patch(
                    "ci.products.sdk_dotnet_toolchain.subprocess.run", return_value=subprocess.CompletedProcess(
                        ["dotnet", "--version"], 0, stdout="10.0.102\n")):
                with self.assertRaisesRegex(ValueError, "differs from pinned"):
                    verify_sdk_dotnet_toolchain(path)
            with patch("ci.products.sdk_dotnet_toolchain._host_identity", return_value=(
                    "Darwin", "arm64", "")), patch(
                    "ci.products.sdk_dotnet_toolchain.subprocess.run") as observed:
                with self.assertRaisesRegex(ValueError, "host differs"):
                    verify_sdk_dotnet_toolchain(path)
                observed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
