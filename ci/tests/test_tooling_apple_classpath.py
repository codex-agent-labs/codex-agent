"""Local emitted-JAR smoke, not genuine Apple or hosted acceptance evidence."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
JAR = ROOT / 'gradle/build-logic/build/libs/codex-agent-release-tooling.jar'


class AppleToolingClasspathTest(unittest.TestCase):
    @unittest.skipUnless(JAR.is_file() and shutil.which('java'), 'requires the emitted tooling JAR and Java')
    def test_validation_binding_cli_reaches_input_validation_without_gradle(self):
        with tempfile.TemporaryDirectory(prefix='apple-validation-classpath-') as temporary:
            root = Path(temporary).resolve()
            options = {name: root / name for name in (
                'evidence-directory', 'product-directory', 'sdk-compatibility', 'canonical-api',
                'canonical-coverage', 'consumer-source-directory', 'work-directory')}
            command = [shutil.which('java'), '-jar', str(JAR),
                       'verify-apple-validation-binding-content', '--version', '0.8.0']
            command += [part for name, value in options.items() for part in ('--' + name, str(value))]
            result = subprocess.run(command, capture_output=True, timeout=30)
            self.assertNotEqual(0, result.returncode)
            self.assertNotIn(b'NoClassDefFoundError', result.stderr)
            self.assertIn(b'Apple validation binding replay input is missing or unsafe', result.stderr)
            self.assertEqual([], list(root.iterdir()))

    @unittest.skipUnless(JAR.is_file() and shutil.which('java'), 'requires the emitted tooling JAR and Java')
    def test_capture_cli_reaches_input_validation_with_complete_helper_closure(self):
        classes = json.loads((ROOT / '.github/actions/run-ci-lane/release_tooling_classes.json').read_bytes())
        with zipfile.ZipFile(JAR) as archive:
            self.assertTrue(all(name + '.class' in archive.namelist() for name in classes))
        with tempfile.TemporaryDirectory(prefix='apple-tooling-classpath-') as temporary:
            root = Path(temporary).resolve()
            for name in ('product', 'binary', 'source', 'Developer', 'capture'):
                (root / name).mkdir()
            (root / 'compatibility.json').write_bytes(b'{}\n')
            options = {
                'product-directory': root / 'product', 'version': '0.8.0',
                'binary-frameworks': root / 'binary', 'source-snapshot': root / 'source',
                'sdk-compatibility': root / 'compatibility.json', 'work-directory': root / 'work',
                'developer-directory': root / 'Developer', 'xcode-version': '26.6',
                'xcode-build': '17F113', 'swift-version': '6.3.3',
                'execution-evidence-directory': root / 'capture/events',
                'execution-binding-file': root / 'capture/input-binding.json',
            }
            command = [shutil.which('java'), '-jar', str(JAR), 'capture-apple-binary-package-evidence']
            command += [part for name, value in options.items() for part in ('--' + name, str(value))]
            result = subprocess.run(command, capture_output=True, timeout=30)
            self.assertNotEqual(0, result.returncode)
            self.assertNotIn(b'NoClassDefFoundError', result.stderr)
            self.assertIn(b'Apple package execution binding input is empty', result.stderr)
