"""Cold admission reclaims only unused hosted tools, before artifact transfer."""
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci.tests import test_sdk_ios_package_upload as uploads


capture = uploads.capture
HOSTED = {
    "CODEX_AGENT_COLD_APPLE_WORKSPACE": "true", "GITHUB_ACTIONS": "true",
    "RUNNER_OS": "Linux", "RUNNER_ENVIRONMENT": "github-hosted", "GITHUB_JOB": "product-resume",
}


class ColdAppleWorkspaceTest(unittest.TestCase):
    def test_insufficient_capacity_stops_before_package_transfer(self):
        fixture = uploads.SdkIosPackageUploadTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with patch.object(capture, "_prepare_cold_apple_workspace",
                          side_effect=ValueError("cold Apple workspace capacity")) as capacity, \
                patch.object(capture, "_reuse_contract_ci_upload", side_effect=AssertionError("body acquired")) as body:
            with self.assertRaisesRegex(ValueError, "cold Apple workspace capacity"):
                fixture.call(compact_recovery=True, environ=HOSTED)
            capacity.assert_called_once()
            body.assert_not_called()
        self.assertFalse(fixture.output.exists())

    def test_no_opt_in_has_no_disk_or_cleanup_cost(self):
        with patch.object(capture.shutil, "disk_usage", side_effect=AssertionError("disk")), \
                patch.object(capture.subprocess, "run", side_effect=AssertionError("cleanup")):
            capture._prepare_cold_apple_workspace(Path("unused"), {}, 1)

    def test_reclaim_refuses_local_self_hosted_or_other_jobs(self):
        for field in ("GITHUB_ACTIONS", "RUNNER_OS", "RUNNER_ENVIRONMENT", "GITHUB_JOB"):
            with self.subTest(field=field), patch.object(capture.subprocess, "run") as cleanup:
                with self.assertRaisesRegex(ValueError, "hosted product-resume"):
                    capture._prepare_cold_apple_workspace(Path("unused"), {**HOSTED, field: "wrong"}, 1)
                cleanup.assert_not_called()

    def test_existing_capacity_skips_cleanup_and_reclaim_failure_stops(self):
        required = 4 * 22_117_834_439 + 8 * 1024**3
        for before, after, cleans, passes in (
            (required, required, False, True),
            (required - 1, required, True, True),
            (required - 1, required - 1, True, False),
        ):
            with self.subTest(before=before, after=after), \
                    patch.object(capture.shutil, "disk_usage", side_effect=[
                        SimpleNamespace(free=before), SimpleNamespace(free=after)]), \
                    patch.object(capture.subprocess, "run") as cleanup, \
                    patch("sys.stdout", new=io.StringIO()) as output:
                if passes:
                    capture._prepare_cold_apple_workspace(Path("workspace"), HOSTED, 22_117_834_439)
                else:
                    with self.assertRaisesRegex(ValueError, "cold Apple workspace capacity"):
                        capture._prepare_cold_apple_workspace(Path("workspace"), HOSTED, 22_117_834_439)
                self.assertEqual(int(cleans), cleanup.call_count)
                self.assertIn('"requiredFreeBytes":' + str(required), output.getvalue())
                if cleans:
                    command = cleanup.call_args.args[0]
                    self.assertEqual(["sudo", "-n", "rm", "-rf", "--"], command[:5])
                    self.assertEqual({"/usr/local/lib/android", "/usr/share/dotnet", "/opt/ghc",
                                      "/usr/local/.ghcup", "/opt/hostedtoolcache/CodeQL"}, set(command[5:]))
                    self.assertTrue(cleanup.call_args.kwargs["check"])


if __name__ == "__main__":
    unittest.main()
