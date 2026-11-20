from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]


class ProductsCliTest(unittest.TestCase):
    def test_receipt_write_output_manifest_emits_canonical_verified_tree_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library = self.write(root, "outputs/library/libcodex_agent.so", b"library")
            evidence = self.write(root, "outputs/evidence/validation.json", b"evidence")

            result = self.run_cli(
                root,
                "--output-root", "runtime-library=outputs/library",
                "--output-root", "validation=outputs/evidence",
            )
            self.assertEqual(0, result.returncode, result.stderr)

            expected = {
                "schemaVersion": 1,
                "product": "runtime",
                "component": "linux-x64",
                "phase": "binary",
                "target": "linux-x64",
                "productVersion": "1.2.3",
                "outputs": [
                    self.record("validation", root, evidence),
                    self.record("runtime-library", root, library),
                ],
            }
            manifest = root / "output-manifest.json"
            canonical = (
                json.dumps(expected, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                + "\n"
            ).encode("utf-8")
            self.assertEqual(canonical, manifest.read_bytes())
            self.assertEqual(expected, json.loads(manifest.read_text(encoding="utf-8")))
            self.assertEqual(
                sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()),
                [
                    "output-manifest.json",
                    *[record["relativePath"] for record in expected["outputs"]],
                ],
            )

    def test_malformed_or_duplicate_output_root_fails_closed_and_removes_stale_manifest(self) -> None:
        cases = (
            (
                "malformed",
                ("--output-root", "not-a-kind-root"),
                ("outputs/value.bin",),
            ),
            (
                "duplicate-kind",
                (
                    "--output-root", "binary=outputs/first",
                    "--output-root", "binary=outputs/second",
                ),
                ("outputs/first/value.bin", "outputs/second/value.bin"),
            ),
            (
                "duplicate-root",
                (
                    "--output-root", "binary=outputs/shared",
                    "--output-root", "library=outputs/shared",
                ),
                ("outputs/shared/value.bin",),
            ),
        )
        for label, arguments, paths in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                for path in paths:
                    self.write(root, path, path.encode("utf-8"))
                manifest = root / "output-manifest.json"
                manifest.write_text('{"stale":true}\n', encoding="utf-8")

                result = self.run_cli(root, *arguments)

                self.assertNotEqual(0, result.returncode)
                self.assertFalse(manifest.exists(), result.stderr)

    def run_cli(self, root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "ci.products",
                "receipt",
                "write-output-manifest",
                "--root", str(root),
                "--product", "runtime",
                "--component", "linux-x64",
                "--phase", "binary",
                "--target", "linux-x64",
                "--product-version", "1.2.3",
                *arguments,
            ],
            cwd=REPOSITORY,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    @staticmethod
    def record(kind: str, root: Path, path: Path) -> dict[str, object]:
        contents = path.read_bytes()
        return {
            "kind": kind,
            "relativePath": path.relative_to(root).as_posix(),
            "bytes": len(contents),
            "sha256": f"sha256:{hashlib.sha256(contents).hexdigest()}",
        }

    @staticmethod
    def write(root: Path, relative: str, contents: bytes) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        return path


if __name__ == "__main__":
    unittest.main()
