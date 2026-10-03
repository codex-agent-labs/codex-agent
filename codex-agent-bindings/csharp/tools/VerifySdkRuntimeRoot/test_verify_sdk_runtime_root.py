"""Offline self-check against a compiled test-root CodexAgent assembly."""

from pathlib import Path
import subprocess
import sys
import tempfile


def main() -> None:
    if len(sys.argv) != 5:
        raise SystemExit("usage: test_verify_sdk_runtime_root.py TOOL_DLL FIXTURE_DLL TEST_ROOT_PUB COMPATIBILITY_JSON")
    tool, fixture, public, compatibility = map(Path, sys.argv[1:])

    def verify(expected_root: Path, expected_compatibility: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["dotnet", str(tool), str(fixture), str(expected_root), str(expected_compatibility)],
            capture_output=True,
            text=True,
            check=False,
        )

    matched = verify(public, compatibility)
    if matched.returncode != 0:
        raise AssertionError(f"matching embedded resources were rejected: {matched.stderr}")

    with tempfile.TemporaryDirectory(prefix="codex-agent-root-check-") as temporary:
        wrong = Path(temporary) / "wrong-root.pub"
        data = bytearray(public.read_bytes())
        if not data:
            raise AssertionError("test root is empty")
        data[-2] = ord("A") if data[-2] != ord("A") else ord("B")
        wrong.write_bytes(data)
        mismatched = verify(wrong, compatibility)
        if mismatched.returncode != 1 or "differs" not in mismatched.stderr:
            raise AssertionError("mismatched embedded root was not rejected")
        wrong_compatibility = Path(temporary) / "wrong-compatibility.json"
        wrong_compatibility.write_bytes(compatibility.read_bytes() + b" ")
        mismatched = verify(public, wrong_compatibility)
        if mismatched.returncode != 1 or "SDK compatibility differs" not in mismatched.stderr:
            raise AssertionError("mismatched embedded compatibility was not rejected")
        oversized = Path(temporary) / "oversized-compatibility.json"
        with oversized.open("wb") as stream:
            stream.truncate(65537)
        rejected = verify(public, oversized)
        if rejected.returncode != 1 or "Expected SDK compatibility has invalid size" not in rejected.stderr:
            raise AssertionError("oversized expected compatibility was not rejected")
        oversized_root = Path(temporary) / "oversized-root.pub"
        with oversized_root.open("wb") as stream:
            stream.truncate(4097)
        rejected = verify(oversized_root, compatibility)
        if rejected.returncode != 1 or "Expected SDK root has invalid size" not in rejected.stderr:
            raise AssertionError("oversized expected root was not rejected")

    print("PEReader SDK-root and compatibility resource self-check passed")


if __name__ == "__main__":
    main()
