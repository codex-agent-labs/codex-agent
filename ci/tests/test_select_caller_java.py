import os
from pathlib import Path
import subprocess
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "select_caller_java.sh"


class SelectCallerJavaTest(unittest.TestCase):
    def test_exact_hosted_aliases_and_missing_java(self):
        cases = (
            ("macOS", "ARM64", "JAVA_HOME_17_arm64"),
            ("Linux", "ARM64", "JAVA_HOME_17_X64"),
            ("Linux", "X64", "JAVA_HOME_17_X64"),
            ("Windows", "X64", "JAVA_HOME_17_X64"),
        )
        for system, arch, alias in cases:
            with self.subTest(system=system, arch=arch):
                environment = {**os.environ, "RUNNER_OS": system, "RUNNER_ARCH": arch,
                               alias: "/verified/java17"}
                result = subprocess.run(["bash", "-c", 'source "$1"; printf "%s" "$selected_java_home"',
                                         "bash", str(SCRIPT)], env=environment,
                                        capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "/verified/java17")
                environment.pop(alias)
                result = subprocess.run(["bash", "-c", 'source "$1"', "bash", str(SCRIPT)],
                                        env=environment, capture_output=True, text=True, check=False)
                self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
