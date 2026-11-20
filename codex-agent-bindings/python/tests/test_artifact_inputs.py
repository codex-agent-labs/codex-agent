from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from artifact_inputs import (
    canonical_api_report,
    c_abi_bootstrap_evidence,
    c_header,
    real_library,
)


class ArtifactInputTests(unittest.TestCase):
    def test_missing_inputs_fail_closed(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeError):
                canonical_api_report()
            with self.assertRaises(RuntimeError):
                c_abi_bootstrap_evidence()
            with self.assertRaises(RuntimeError):
                c_header()
            with self.assertRaises(RuntimeError):
                real_library()

    def test_declared_files_are_resolved_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = root / "canonical-api.json"
            bootstrap = root / "bootstrap-evidence.json"
            library = root / "libcodex_agent.dylib"
            header = root / "c-sdk" / "include" / "codex_agent.h"
            header.parent.mkdir(parents=True)
            for path in (canonical, bootstrap, library, header):
                path.touch()
            with mock.patch.dict(
                "os.environ",
                {
                    "CODEX_AGENT_CANONICAL_API_REPORT": str(canonical),
                    "CODEX_AGENT_C_ABI_BOOTSTRAP_EVIDENCE": str(bootstrap),
                    "CODEX_AGENT_C_SDK_ROOT": str(root / "c-sdk"),
                    "CODEX_AGENT_LIBRARY": str(library),
                },
                clear=True,
            ):
                self.assertEqual(canonical_api_report(), canonical.resolve())
                self.assertEqual(c_abi_bootstrap_evidence(), bootstrap.resolve())
                self.assertEqual(c_header(), header.resolve())
                self.assertEqual(real_library(), library.resolve())


if __name__ == "__main__":
    unittest.main()
