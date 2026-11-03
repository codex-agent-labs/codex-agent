"""Small archive fixtures exercise provisioning/guard, never product evidence."""
import copy
import io
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sdk_native_phase as worker
from products.inventory import canonical_json_bytes, sha256_file
from products.registry import PhaseInstanceId
from products.selection import _inventory_owners

ROOT = Path(__file__).resolve().parents[2]


class CppPackageToolchainTest(unittest.TestCase):
    def test_policy_is_canonical_and_owned_only_by_cpp_package(self):
        policy = worker.cpp_package_toolchain_policy(ROOT)
        name = 'codex-agent-bindings/cpp/package-toolchain.json'
        self.assertEqual(canonical_json_bytes(policy), (ROOT / name).read_bytes())
        self.assertEqual(frozenset({PhaseInstanceId('sdk', 'cpp', 'package', 'desktop')}),
                         _inventory_owners(name))
        self.assertEqual(frozenset(), _inventory_owners('ci/sdk_native_phase.py'))

    def test_provisioning_reuses_archive_and_guard_rejects_wrong_tools(self):
        policy = copy.deepcopy(worker.cpp_package_toolchain_policy(ROOT))
        action = (ROOT / '.github/actions/sdk-native-package-worker/action.yml').read_text()
        script = textwrap.dedent(action.split('from ci.sdk_native_phase import cpp_package_toolchain_policy', 1)[1]
                                 .split('\n        PY', 1)[0])
        script = ('import os, pathlib, tarfile, urllib.request\n'
                  'from ci.sdk_native_phase import cpp_package_toolchain_policy\n' + script.lstrip('\n'))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            base = root / 'cpp-package-toolchain'
            base.mkdir()
            archive = base / policy['archive']['name']
            files = {'bin/cmake': b'fixture executable\n',
                     'share/cmake-3.31/Modules/CMake.cmake': b'fixture module\n',
                     'share/cmake-3.31/Modules/IntelVSImplicitPath/hello.f': b'',
                     'doc/not-consumed': b'fixture documentation\n',
                     'bin/ctest': b'fixture unused executable\n'}
            with tarfile.open(archive, 'w:gz') as output:
                for name, data in files.items():
                    member = tarfile.TarInfo(policy['archiveRoot'] + '/' + name)
                    member.size = len(data)
                    member.mode = 0o755 if name.startswith('bin/') else 0o644
                    output.addfile(member, io.BytesIO(data))
            policy['archive'].update(bytes=archive.stat().st_size, sha256=sha256_file(archive))
            env = {'RUNNER_TEMP': str(root), 'GITHUB_WORKSPACE': str(ROOT),
                   'GITHUB_ENV': str(root / 'environment'), 'GITHUB_PATH': str(root / 'path')}
            # The action imports ci.sdk_native_phase; the worker guard above is
            # imported as sdk_native_phase, as in the existing test suite.
            with patch.dict(os.environ, env, clear=True), \
                 patch('ci.sdk_native_phase.cpp_package_toolchain_policy', return_value=policy), \
                 patch('urllib.request.urlopen', side_effect=AssertionError('No repeated transfer')):
                exec(compile(script, 'actual-cpp-provisioning-action', 'exec'), {})
                exec(compile(script, 'actual-cpp-provisioning-action-reuse', 'exec'), {})
            prefix = base / policy['archiveRoot']
            self.assertEqual({'bin/cmake', 'share/cmake-3.31/Modules/CMake.cmake',
                              'share/cmake-3.31/Modules/IntelVSImplicitPath/hello.f'},
                             {str(p.relative_to(prefix)) for p in prefix.rglob('*') if p.is_file()})
            environment = dict(line.split('=', 1) for line in (root / 'environment').read_text().splitlines())
            environment['PATH'] = str(prefix / 'bin')
            with patch.object(worker, 'cpp_package_toolchain_policy', return_value=policy), \
                 patch('products.sdk_dotnet_toolchain._host_identity', return_value=('Linux', 'X64', 'ubuntu-24.04')) as host, \
                 patch.object(worker.subprocess, 'run', return_value=SimpleNamespace(stdout='cmake version 3.31.6\n')) as version:
                worker.verify_cpp_package_toolchain(ROOT, environment)
                version.assert_called_once()
                module = prefix / 'share/cmake-3.31/Modules/CMake.cmake'
                module.write_bytes(b'changed module\n')
                with self.assertRaisesRegex(ValueError, 'Installed CMake inventory'):
                    worker.verify_cpp_package_toolchain(ROOT, environment)
                module.write_bytes(files['share/cmake-3.31/Modules/CMake.cmake'])
                extra = prefix / 'share/cmake-3.31/Modules/Unexpected.cmake'
                extra.write_bytes(b'additional executable code\n')
                with self.assertRaisesRegex(ValueError, 'Installed CMake inventory'):
                    worker.verify_cpp_package_toolchain(ROOT, environment)
                extra.unlink()
                host.return_value = ('Darwin', 'ARM64', '')
                with self.assertRaisesRegex(ValueError, 'host or selected CMake'):
                    worker.verify_cpp_package_toolchain(ROOT, environment)
                host.return_value = ('Linux', 'X64', 'ubuntu-24.04')
                with self.assertRaisesRegex(ValueError, 'host or selected CMake'):
                    worker.verify_cpp_package_toolchain(ROOT, environment | {'PATH': ''})
                archive.write_bytes(archive.read_bytes() + b'changed')
                with self.assertRaisesRegex(ValueError, 'official pin'):
                    worker.verify_cpp_package_toolchain(ROOT, environment)
                self.assertEqual(1, version.call_count, 'Never execute unauthenticated CMake')


if __name__ == '__main__':
    unittest.main()
