"""Dependency-seed control checks, not genuine Gradle/product acceptance."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from ci.products import gradle_bootstrap as bootstrap


class SdkDependencySeedTest(unittest.TestCase):
    def test_exact_git_fixture_merges_all_pins_and_only_resolves_dependencies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            documents = iter((self.metadata('first'), self.metadata('second'),
                self.metadata('sdk').replace(
                    b'<configuration><verify-metadata>true</verify-metadata></configuration>', b'')))

            def blob(repository, revision, relative, **limits):
                self.assertEqual((root, 'a' * 40), (repository, revision))
                return next(documents) if relative.endswith('.xml') else b'// exact Git build input\n'

            with patch.object(bootstrap, 'git_regular_blob_bytes', side_effect=blob), \
                    patch.object(bootstrap.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
                destination = root / 'seed'
                bootstrap.seed_sdk_gradle_dependencies(root, 'a' * 40, root / 'gradlew', {}, destination)
            metadata = ET.parse(destination / 'gradle/build-logic/gradle/verification-metadata.xml')
            self.assertIn(b'<verification-metadata xmlns=',
                (destination / 'gradle/build-logic/gradle/verification-metadata.xml').read_bytes())
            namespace = {'v': 'https://schema.gradle.org/dependency-verification'}
            self.assertEqual(['first', 'sdk', 'second'], [item.get('name') for item in
                metadata.findall('v:components/v:component', namespace)])
            command = run.call_args.args[0]
            self.assertIn('--dependency-verification=strict', command)
            self.assertIn('resolveSdkBuildDependencies', command)
            self.assertNotIn('ciProductPhase', command)
            self.assertNotIn('compileKotlin', command)
            self.assertIn("'kotlinCompilerClasspath'", bootstrap._SDK_SEED_SCRIPT)
            self.assertNotIn("kotlinAbiValidationCompatClasspath", bootstrap._SDK_SEED_SCRIPT)
            self.assertNotIn("findAll", bootstrap._SDK_SEED_SCRIPT)

    @staticmethod
    def metadata(name, digest='a' * 64):
        return (f'<verification-metadata xmlns="https://schema.gradle.org/dependency-verification">'
                f'<configuration><verify-metadata>true</verify-metadata></configuration><components>'
                f'<component group="example" name="{name}" version="1.0.0"><artifact name="{name}.jar">'
                f'<sha256 value="{digest}"/></artifact></component></components></verification-metadata>').encode()

    def test_conflicting_pins_fail_before_gradle_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            documents = iter((self.metadata('same'), self.metadata('same', 'b' * 64)))
            with patch.object(bootstrap, 'git_regular_blob_bytes', side_effect=lambda *a, **k:
                    next(documents) if a[2].endswith('.xml') else b'// Git input\n'), \
                    patch.object(bootstrap.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'conflicting checksums'):
                    bootstrap.seed_sdk_gradle_dependencies(root, 'a' * 40, root / 'gradlew', {}, root / 'seed')
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
