"""The Core14 composite must reject missing reused authority before capture."""

import os
from pathlib import Path
import subprocess
import textwrap
import unittest


ACTION = Path(__file__).resolve().parents[2] / ".github/actions/sdk-android-core14-caller/action.yml"


class AndroidCore14ActionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ACTION.read_text(encoding="utf-8")
        cls.route = textwrap.dedent(source.split("    - id: route\n", 1)[1]
            .split("    - id: before\n", 1)[0].split("      run: |\n", 1)[1])
        cls.source = source

    def run_route(self, **overrides):
        names = ("FRESH_ARTIFACT_ID FRESH_ARTIFACT_SHA256 FRESH_CONTEXT "
            "FRESH_SDK_INPUTS_ID FRESH_SDK_INPUTS_SHA256 REUSED_CATALOG "
            "REUSED_CATALOG_ROOT REUSED_CATALOG_SOURCE REUSED_RECEIPTS REUSED_POLICY "
            "REUSED_CONTEXT REUSED_CONTEXT_MANIFEST REUSED_CONTEXT_SIGNATURE "
            "REUSED_CONTEXT_KEYRING REUSED_CONTEXT_KEYS_DIRECTORY "
            "REUSED_METADATA_RECEIPT REUSED_AFTER_STATE ANDROID_ARCHIVE "
            "BEFORE_STATE_WAVE BEFORE_SDK_STATE_WAVE "
            "REUSED_PUBLIC_KEY REUSED_KEYRING REUSED_KEYS_DIRECTORY "
            "IOS_ARM64_ARCHIVE IOS_SIMULATOR_ARM64_ARCHIVE LINUX_ARM64_ARCHIVE "
            "LINUX_X64_ARCHIVE MACOS_ARM64_ARCHIVE MACOS_X64_ARCHIVE WINDOWS_X64_ARCHIVE").split()
        values = {name: "" for name in names}
        values.update(overrides)
        return subprocess.run(["bash", "-c", self.route], env={**os.environ, **values},
            capture_output=True, text=True, check=False)

    def test_fresh_and_reused_routes_are_mutually_exclusive(self):
        fresh = dict(FRESH_ARTIFACT_ID="1", FRESH_ARTIFACT_SHA256="digest",
            FRESH_CONTEXT="context", FRESH_SDK_INPUTS_ID="2", FRESH_SDK_INPUTS_SHA256="digest",
            BEFORE_STATE_WAVE="0", BEFORE_SDK_STATE_WAVE="13",
            IOS_ARM64_ARCHIVE="archive", IOS_SIMULATOR_ARM64_ARCHIVE="archive",
            LINUX_ARM64_ARCHIVE="archive", LINUX_X64_ARCHIVE="archive",
            MACOS_ARM64_ARCHIVE="archive", MACOS_X64_ARCHIVE="archive",
            WINDOWS_X64_ARCHIVE="archive")
        reused = dict(REUSED_CATALOG="catalog", REUSED_CATALOG_ROOT="carrier",
            BEFORE_STATE_WAVE="0", BEFORE_SDK_STATE_WAVE="12",
            REUSED_CATALOG_SOURCE="same-pr", REUSED_RECEIPTS="twelve-pins",
            REUSED_POLICY="policy", REUSED_CONTEXT="context",
            REUSED_CONTEXT_MANIFEST="signed-context", REUSED_CONTEXT_SIGNATURE="signature",
            REUSED_CONTEXT_KEYRING="keyring", REUSED_CONTEXT_KEYS_DIRECTORY="keys",
            REUSED_METADATA_RECEIPT="receipt", REUSED_AFTER_STATE="state",
            ANDROID_ARCHIVE="archive", REUSED_PUBLIC_KEY="public-key")
        self.assertEqual(0, self.run_route(**fresh).returncode)
        self.assertEqual(0, self.run_route(**reused).returncode)
        self.assertEqual(0, self.run_route(**{**reused, "BEFORE_STATE_WAVE": "5",
            "BEFORE_SDK_STATE_WAVE": ""}).returncode)
        self.assertNotEqual(0, self.run_route(**{**reused, "REUSED_CONTEXT_SIGNATURE": ""}).returncode)
        self.assertNotEqual(0, self.run_route(**{**reused, "FRESH_ARTIFACT_ID": "1"}).returncode)
        self.assertNotEqual(0, self.run_route(**{**reused, "LINUX_X64_ARCHIVE": "fresh"}).returncode)
        self.assertNotEqual(0, self.run_route(**{**reused, "BEFORE_STATE_WAVE": "13"}).returncode)
        self.assertNotEqual(0, self.run_route(**{**reused, "BEFORE_SDK_STATE_WAVE": "14"}).returncode)
        self.assertNotEqual(0, self.run_route(**{**fresh, "REUSED_CONTEXT": "unsigned"}).returncode)

    def test_reused_route_replays_signed_context_and_catalog_before_outputs(self):
        reused = self.source.split("    - id: reused\n", 1)[1]
        before = self.source.split("    - id: before\n", 1)[1].split("    - uses: actions/download-artifact", 1)[0]
        self.assertIn("state-wave: ${{ inputs.before-state-wave }}", before)
        self.assertIn("sdk-state-wave: ${{ inputs.before-sdk-state-wave }}", before)
        self.assertIn("--reused-context-manifest \"$CONTEXT_MANIFEST\"", reused)
        self.assertIn("--reused-context-signature \"$CONTEXT_SIGNATURE\"", reused)
        self.assertIn("--reused-receipt-sha256 \"$RECEIPT_SHA256\"", reused)
        self.assertLess(reused.index("python3 -B -m ci.sdk_android_core14_caller elect"),
                        reused.index('echo "metadata_receipt=$METADATA_RECEIPT"'))


if __name__ == "__main__":
    unittest.main()
