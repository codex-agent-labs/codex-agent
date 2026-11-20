"""Tiny ZIP fixtures cover Dart provisioning/guard, not product acceptance."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sdk_native_phase as worker
from products.inventory import canonical_json_bytes, sha256_file
from products.registry import PhaseInstanceId
from products.selection import _inventory_owners

ROOT = Path(__file__).resolve().parents[2]


class DartPackageToolchainTest(unittest.TestCase):
    def test_policy_is_canonical_and_owned_only_by_dart_package(self):
        policy = worker.dart_package_toolchain_policy(ROOT)
        name = 'codex-agent-bindings/dart/package-toolchain.json'
        self.assertEqual(canonical_json_bytes(policy), (ROOT / name).read_bytes())
        self.assertEqual(frozenset({PhaseInstanceId('sdk', 'dart', 'package', 'desktop')}),
                         _inventory_owners(name))
        self.assertEqual(frozenset(), _inventory_owners('ci/sdk_native_phase.py'))

    def test_scoped_provisioning_reuses_archive_and_guard_rejects_changed_tools(self):
        policy = copy.deepcopy(worker.dart_package_toolchain_policy(ROOT))
        action = (ROOT / '.github/actions/sdk-native-package-worker/action.yml').read_text()
        block = action.split("    - if: inputs.component == 'dart'\n", 1)[1]
        script = textwrap.dedent(block.split("        python3 -B - <<'PY'\n", 1)[1].split('\n        PY', 1)[0])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            base = root / 'dart-package-toolchain'
            base.mkdir()
            archive = base / policy['archive']['name']
            files = {'bin/dart': b'fixture executable\n',
                     'version': (policy['dartVersion'] + '\n').encode(),
                     'revision': (policy['revision'] + '\n').encode(),
                     'bin/snapshots/unused.snapshot': b'fixture unconsumed compiler\n'}
            with zipfile.ZipFile(archive, 'w') as output:
                for name, data in files.items():
                    member = zipfile.ZipInfo(policy['archiveRoot'] + '/' + name)
                    member.external_attr = (0o100755 if name == 'bin/dart' else 0o100644) << 16
                    output.writestr(member, data)
            policy['archive'].update(bytes=archive.stat().st_size, sha256=sha256_file(archive))
            env = {'RUNNER_TEMP': str(root), 'GITHUB_WORKSPACE': str(ROOT),
                   'GITHUB_ENV': str(root / 'environment'), 'GITHUB_PATH': str(root / 'path')}
            with patch.dict(os.environ, env, clear=True), \
                 patch('ci.sdk_native_phase.dart_package_toolchain_policy', return_value=policy), \
                 patch('urllib.request.urlopen', side_effect=AssertionError('No repeated transfer')):
                exec(compile(script, 'actual-dart-provisioning-action', 'exec'), {})
                exec(compile(script, 'actual-dart-provisioning-action-reuse', 'exec'), {})
            prefix = base / policy['archiveRoot']
            self.assertEqual(set(worker.DART_PACKAGE_TOOL_FILES),
                             {str(p.relative_to(prefix)) for p in prefix.rglob('*') if p.is_file()})
            environment = dict(line.split('=', 1) for line in (root / 'environment').read_text().splitlines())
            environment['PATH'] = str(prefix / 'bin')
            with patch.object(worker, 'dart_package_toolchain_policy', return_value=policy), \
                 patch('products.sdk_dotnet_toolchain._host_identity', return_value=('Linux', 'X64', 'ubuntu-24.04')) as host, \
                 patch.object(worker.subprocess, 'run', return_value=SimpleNamespace(stdout=policy['versionIdentity'] + '\n')) as version:
                worker.verify_dart_package_toolchain(ROOT, environment)
                version.assert_called_once()
                binary = prefix / 'bin/dart'
                binary.write_bytes(b'changed executable\n')
                with self.assertRaisesRegex(ValueError, 'Installed Dart inventory'):
                    worker.verify_dart_package_toolchain(ROOT, environment)
                binary.write_bytes(files['bin/dart'])
                extra = prefix / 'bin/extra.snapshot'
                extra.write_bytes(b'additional executable code\n')
                with self.assertRaisesRegex(ValueError, 'Installed Dart inventory'):
                    worker.verify_dart_package_toolchain(ROOT, environment)
                extra.unlink()
                revision = prefix / 'revision'
                revision.unlink()
                revision.symlink_to(archive)
                with self.assertRaises(ValueError):
                    worker.verify_dart_package_toolchain(ROOT, environment)
                revision.unlink()
                revision.write_bytes(files['revision'])
                host.return_value = ('Darwin', 'ARM64', '')
                with self.assertRaisesRegex(ValueError, 'host or selected executable'):
                    worker.verify_dart_package_toolchain(ROOT, environment)
                host.return_value = ('Linux', 'X64', 'ubuntu-24.04')
                with self.assertRaisesRegex(ValueError, 'host or selected executable'):
                    worker.verify_dart_package_toolchain(ROOT, environment | {'PATH': ''})
                archive.write_bytes(archive.read_bytes() + b'changed')
                with self.assertRaisesRegex(ValueError, 'official pin'):
                    worker.verify_dart_package_toolchain(ROOT, environment)
                self.assertEqual(1, version.call_count, 'Never execute unauthenticated Dart')


if __name__ == '__main__':
    unittest.main()
