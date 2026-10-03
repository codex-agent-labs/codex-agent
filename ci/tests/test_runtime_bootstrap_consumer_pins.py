import hashlib
from pathlib import Path
import re
import unittest


class RuntimeBootstrapConsumerPinsTest(unittest.TestCase):
    def test_reviewed_consumer_hashes_match_exact_sources(self):
        root = Path(__file__).resolve().parents[2]
        kotlin = root / "runtime/build-logic/src/main/kotlin"
        evidence = (kotlin / "CrossLanguageCAbiBootstrapEvidence.kt").read_text()
        plugin = (kotlin / "codexagent.desktop-runtime.gradle.kts").read_text()
        guards = re.findall(
            r"val \w+ = (\w+Consumer)\.get\(\)\.asFile\.also \{\s*"
            r"check\(it.releaseDigest\(\) == (\w+)\)", evidence,
        )
        self.assertTrue(guards)
        for prop, constant in guards:
            with self.subTest(consumer=prop):
                path = re.search(
                    re.escape(prop) + r'\.set\(\s*layout\.projectDirectory\.file\(\s*"([^"\n]+)"',
                    plugin,
                )
                pin = re.search(
                    r'private const val ' + constant + r'\s*=\s*"([a-f0-9]{64})"', evidence,
                )
                self.assertIsNotNone(path)
                self.assertIsNotNone(pin)
                source = root / "codex-agent-runtime-desktop" / path[1]
                self.assertEqual(pin[1], hashlib.sha256(source.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
