"""Small tool-archive fixtures, never production tool or product evidence."""
from contextlib import ExitStack
import copy
import hashlib
import io
from pathlib import Path
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sdk_native_phase as worker
from products.inventory import canonical_json_bytes
from products.registry import PhaseInstanceId
from products.selection import _inventory_owners


class PythonPackageToolchainTest(unittest.TestCase):
    def test_policy_is_canonical_and_owned_only_by_python_package(self):
        root = Path(__file__).resolve().parents[2]
        policy = worker.python_package_toolchain_policy(root)
        self.assertEqual(5, len(policy['wheels']))
        path = 'codex-agent-bindings/python/package-toolchain.json'
        self.assertEqual((root / path).read_bytes(), canonical_json_bytes(policy))
        self.assertEqual(frozenset({PhaseInstanceId('sdk', 'python', 'package', 'desktop')}),
                         _inventory_owners(path))
        for control in ('ci/sdk_native_phase.py', '.github/actions/sdk-native-package-worker/action.yml'):
            self.assertEqual(frozenset(), _inventory_owners(control))

    def test_real_archive_comparison_rejects_changed_tools_and_wrong_interpreter(self):
        policy = copy.deepcopy(worker.python_package_toolchain_policy(Path(__file__).resolve().parents[2]))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            prefix, archives = root / 'prefix', root / 'archives'
            archives.mkdir()
            policy['prefix'] = str(prefix)
            runtime = {'bin/python3.11': b'fixture interpreter\n',
                       'lib/libpython3.11.so.1.0': b'fixture runtime\n',
                       'lib/python3.11/os.py': b'fixture stdlib\n'}
            for name, data in runtime.items():
                target = prefix / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            archive_path = archives / policy['interpreter']['name']
            with tarfile.open(archive_path, 'w:gz') as archive:
                for name, data in runtime.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))
            site = prefix / 'lib/python3.11/site-packages'
            versions = {}
            for wheel in policy['wheels']:
                versions[wheel['distribution']] = wheel['version']
                name, data = wheel['module'] + '/__init__.py', b'fixture tool code\n'
                installed = site / name
                installed.parent.mkdir(parents=True)
                installed.write_bytes(data)
                with zipfile.ZipFile(archives / wheel['name'], 'w') as archive:
                    archive.writestr(name, data)
            for asset in (policy['interpreter'], *policy['wheels']):
                data = (archives / asset['name']).read_bytes()
                asset.update(bytes=len(data), sha256='sha256:' + hashlib.sha256(data).hexdigest())
            environment = {'PATH': str(prefix / 'bin'), 'CODEX_AGENT_PYTHON_TOOLCHAIN_ARCHIVES': str(archives),
                           'PYTHONPYCACHEPREFIX': str(root / 'fresh-bytecode'), 'PYTHONDONTWRITEBYTECODE': '1'}
            with ExitStack() as stack:
                stack.enter_context(patch.object(worker, 'python_package_toolchain_policy', return_value=policy))
                stack.enter_context(patch('products.sdk_dotnet_toolchain._host_identity',
                                          return_value=('Linux', 'X64', 'ubuntu-24.04')))
                stack.enter_context(patch.object(sys, 'prefix', str(prefix)))
                stack.enter_context(patch.object(sys, 'base_prefix', str(prefix)))
                stack.enter_context(patch.object(sys, 'executable', str(prefix / 'bin/python3.11')))
                stack.enter_context(patch.object(sys, 'version_info', (3, 11, 17)))
                stack.enter_context(patch.object(sys, 'pycache_prefix', environment['PYTHONPYCACHEPREFIX']))
                stack.enter_context(patch.object(sys, 'dont_write_bytecode', True))
                stack.enter_context(patch.object(worker.shutil, 'which', return_value=str(prefix / 'bin/python3.11')))
                stack.enter_context(patch.object(worker.importlib.metadata, 'distribution', side_effect=lambda name:
                    SimpleNamespace(version=versions[name], locate_file=lambda _: site)))
                stack.enter_context(patch.object(worker.importlib.util, 'find_spec', side_effect=lambda name:
                    SimpleNamespace(origin=str(site / name / '__init__.py'))))
                worker.verify_python_package_toolchain(root, environment)
                with patch.object(sys, 'pycache_prefix', None), self.assertRaisesRegex(ValueError, 'startup envelope'):
                    worker.verify_python_package_toolchain(root, environment)
                for extra in (site / 'build/__init__.so', prefix / 'lib/python3.11/os.so'):
                    extra.write_bytes(b'fixture import shadow\n')
                    with self.assertRaisesRegex(ValueError, 'Unexpected importable'):
                        worker.verify_python_package_toolchain(root, environment)
                    extra.unlink()
                with patch.object(sys, 'version_info', (3, 12, 3)), self.assertRaisesRegex(ValueError, 'interpreter'):
                    worker.verify_python_package_toolchain(root, environment)
                installed = site / 'build/__init__.py'
                installed.write_bytes(b'changed fixture code\n')
                with self.assertRaisesRegex(ValueError, 'Installed Python tool'):
                    worker.verify_python_package_toolchain(root, environment)
                installed.write_bytes(b'fixture tool code\n')
                (prefix / 'lib/python3.11/os.py').write_bytes(b'changed stdlib\n')
                with self.assertRaisesRegex(ValueError, 'Installed Python runtime'):
                    worker.verify_python_package_toolchain(root, environment)
                (prefix / 'lib/python3.11/os.py').write_bytes(runtime['lib/python3.11/os.py'])
                archive_path.write_bytes(b'changed retained archive\n')
                with self.assertRaisesRegex(ValueError, 'official pin'):
                    worker.verify_python_package_toolchain(root, environment)

    def test_wrong_tool_identity_precedes_any_output_or_input_scan(self):
        from ci.tests.test_sdk_native_phase import SdkNativePhaseTest
        fixture = SdkNativePhaseTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with patch('native_wrappers.host_classifier', return_value='linux-x64'), \
             patch.object(worker, 'verify_python_package_identity', side_effect=ValueError('wrong tool identity')), \
             patch.object(worker, '_inventory', side_effect=AssertionError('guard must precede input scan')):
            with self.assertRaisesRegex(ValueError, 'wrong tool identity'):
                worker.execute(fixture.plan, producer=fixture.producer, sdk_version='0.3.0',
                    repository_root=fixture.root, destination=fixture.destination,
                    runtime_stages=fixture.runtime, prepared_sources=fixture.sources,
                    staged_sdks=fixture.sdks, compatibility_request=fixture.request,
                    predecessor=fixture.predecessor, environ={})
        self.assertFalse(fixture.destination.exists())
        self.assertFalse(fixture.stage.exists())

    def test_parent_does_not_repeat_full_child_tool_authentication(self):
        from ci.tests.test_sdk_native_phase import SdkNativePhaseTest
        fixture = SdkNativePhaseTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with patch.object(worker, 'verify_python_package_toolchain',
                          side_effect=AssertionError('Only the actual package child scans tool bytes')):
            fixture.invoke()
        self.assertEqual(1, len(fixture.calls))


if __name__ == '__main__':
    unittest.main()
