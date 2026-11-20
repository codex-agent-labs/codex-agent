"""Real immutable control blobs; no shared repository mutations."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ci.reuse_qualification import read_blobs


class ControlGitTest(unittest.TestCase):
    def test_large_batch_uses_seekable_input_and_returns_exact_originals(self):
        import hashlib
        import zlib
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            expected = {}
            for number in range(2048):
                body = ('original control ' + str(number)).encode()
                raw = f'blob {len(body)}\0'.encode() + body
                oid = hashlib.sha1(raw).hexdigest()
                path = root / '.git/objects' / oid[:2] / oid[2:]
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(zlib.compress(raw))
                expected[oid] = body
            run = subprocess.run
            def checked(*args, **kwargs):
                self.assertTrue(kwargs['stdin'].seekable())
                self.assertEqual(0, kwargs['stdin'].tell())
                self.assertNotIn('input', kwargs)
                return run(*args, **kwargs)
            with patch('ci.reuse_qualification.subprocess.run', side_effect=checked) as calls:
                self.assertEqual(expected, read_blobs(root, expected, max_bytes=100, total_bytes=100_000))
                self.assertEqual(2, calls.call_count)

    def test_batch_bounds_identity_and_framing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def git(*arguments, data=b""):
                return subprocess.run(["git", "-C", str(root), *arguments], input=data,
                                      capture_output=True, check=True).stdout
            git("init", "-q")
            bodies = (b"first\x00body\n", b"second")
            ids = [git("hash-object", "-w", "--stdin", data=body).decode().strip() for body in bodies]
            run = subprocess.run
            with patch("ci.reuse_qualification.subprocess.run", wraps=run) as calls:
                self.assertEqual(dict(zip(ids, bodies)), read_blobs(root, ids + ids,
                    max_bytes=100, total_bytes=100))
                self.assertEqual(2, calls.call_count)
            for options in ({"max_bytes": 2, "total_bytes": 100},
                            {"max_bytes": 100, "total_bytes": 2}):
                with patch("ci.reuse_qualification.subprocess.run", wraps=run) as calls:
                    with self.assertRaisesRegex(ValueError, "byte bound"):
                        read_blobs(root, ids, **options)
                    self.assertEqual(1, calls.call_count)  # No body fetched on a bound failure.
            tree = git("mktree").decode().strip()
            for invalid in ("HEAD", "f" * 40, tree):
                with self.assertRaises(ValueError):
                    read_blobs(root, [invalid], max_bytes=100, total_bytes=100)
            metadata = run(["git", "-C", str(root), "cat-file", "--batch-check"],
                           input=(ids[0] + "\n").encode(), capture_output=True, check=True)
            correct = f"{ids[0]} blob {len(bodies[0])}\n".encode() + bodies[0] + b"\n"
            for changed in (correct[:-1], correct + b"extra", correct.replace(b"blob", b"tree", 1)):
                with patch("ci.reuse_qualification.subprocess.run", side_effect=[metadata,
                        subprocess.CompletedProcess([], 0, changed)]):
                    with self.assertRaises(ValueError):
                        read_blobs(root, ids[:1], max_bytes=100, total_bytes=100)


if __name__ == "__main__":
    unittest.main()
