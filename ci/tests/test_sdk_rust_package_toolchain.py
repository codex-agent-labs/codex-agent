"""Focused fixed-tool/offline-cache checks; fixtures are never product evidence."""
import copy
import hashlib
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


class RustPackageToolchainTest(unittest.TestCase):
    def test_policy_is_canonical_and_owned_only_by_rust_package(self):
        policy = worker.rust_package_toolchain_policy(ROOT)
        name = 'codex-agent-bindings/rust/package-toolchain.json'
        self.assertEqual(canonical_json_bytes(policy), (ROOT / name).read_bytes())
        self.assertEqual(frozenset({PhaseInstanceId('sdk', 'rust', 'package', 'desktop')}),
                         _inventory_owners(name))
        self.assertEqual(frozenset(), _inventory_owners('ci/sdk_native_phase.py'))
        self.assertEqual(16, len(worker.rust_locked_packages(ROOT)))

    def test_actual_provisioning_reuses_inputs_and_guard_rejects_mutation_and_injection(self):
        policy = copy.deepcopy(worker.rust_package_toolchain_policy(ROOT))
        action = (ROOT / '.github/actions/sdk-native-package-worker/action.yml').read_text()
        script = textwrap.dedent(action.split("python3 -B - <<'PYRUST'\n", 1)[1].split('\n        PYRUST', 1)[0])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            base = root / 'rust-package-toolchain'
            archives = base / 'archives'
            archives.mkdir(parents=True)
            expected = {}
            for component, asset in policy['archives'].items():
                path = archives / asset['name']
                with tarfile.open(path, 'w:xz') as archive:
                    for name in (*worker.RUST_PACKAGE_TOOL_FILES[component], 'share/doc/unused'):
                        data = (name + '\n').encode()
                        member = tarfile.TarInfo(asset['archiveRoot'] + '/' + component + '/' + name)
                        member.mode = 0o755 if name.startswith('bin/') else 0o644
                        member.size = len(data)
                        archive.addfile(member, io.BytesIO(data))
                        if name in worker.RUST_PACKAGE_TOOL_FILES[component]:
                            expected[name] = data
                asset.update(bytes=path.stat().st_size, sha256=sha256_file(path))
            crate = b'locked crate fixture\n'
            row = {'name': 'base64', 'version': '0.22.1', 'checksum': hashlib.sha256(crate).hexdigest(),
                   'indexPath': 'ba/se/base64'}
            (base / 'locked-index').mkdir()
            entry = {'name': row['name'], 'vers': row['version'], 'cksum': row['checksum'], 'deps': [], 'features': {}, 'yanked': False}
            policy['lockedIndexRecordsSha256'] = 'sha256:' + hashlib.sha256(canonical_json_bytes([entry])).hexdigest()
            (base / 'locked-index/base64').write_bytes(canonical_json_bytes(entry))
            crate_path = base / 'cargo-home/registry/cache/index.crates.io-1949cf8c6b5b557f/base64-0.22.1.crate'
            crate_path.parent.mkdir(parents=True)
            crate_path.write_bytes(crate)
            env = {'RUNNER_TEMP': str(root), 'GITHUB_WORKSPACE': str(ROOT),
                   'GITHUB_ENV': str(root / 'environment'), 'GITHUB_PATH': str(root / 'path')}
            with patch.dict(os.environ, env, clear=True), \
                 patch('ci.sdk_native_phase.rust_package_toolchain_policy', return_value=policy), \
                 patch('ci.sdk_native_phase.rust_locked_packages', return_value=[row]), \
                 patch('urllib.request.urlopen', side_effect=AssertionError('No repeated transfer')):
                exec(compile(script, 'actual-rust-provisioning-action', 'exec'), {})
                exec(compile(script, 'actual-rust-provisioning-action-reuse', 'exec'), {})
            prefix = base / 'toolchain'
            self.assertEqual(set(expected), {str(p.relative_to(prefix)) for p in prefix.rglob('*') if p.is_file()})
            environment = dict(line.split('=', 1) for line in (root / 'environment').read_text().splitlines())
            environment['PATH'] = str(prefix / 'bin')
            def version(command, **unused):
                name = Path(command[0]).name
                return SimpleNamespace(stdout=policy['versionIdentities'][name].replace(';', '\n') + '\n')
            with patch.object(worker, 'rust_package_toolchain_policy', return_value=policy), \
                 patch.object(worker, 'rust_locked_packages', return_value=[row]), \
                 patch('products.sdk_dotnet_toolchain._host_identity', return_value=('Linux', 'X64', 'ubuntu-24.04')), \
                 patch.object(worker.subprocess, 'run', side_effect=version) as versions:
                worker.verify_rust_package_toolchain(ROOT, environment)
                self.assertEqual(2, versions.call_count)
                for injected in ('RUSTC', 'RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER', 'CARGO_BUILD_RUSTC', 'CARGO_ENCODED_RUSTFLAGS'):
                    with self.subTest(injected=injected), self.assertRaisesRegex(ValueError, 'overrides'):
                        worker.verify_rust_package_toolchain(ROOT, environment | {injected: '/untrusted'})
                with self.assertRaisesRegex(ValueError, 'selected tools'):
                    worker.verify_rust_package_toolchain(ROOT, environment | {'PATH': ''})
                library = prefix / worker.RUST_PACKAGE_TOOL_FILES['rustc'][1]
                library.write_bytes(b'changed compiler library\n')
                with self.assertRaisesRegex(ValueError, 'Installed Rust inventory'):
                    worker.verify_rust_package_toolchain(ROOT, environment)
                library.write_bytes(expected[str(library.relative_to(prefix))])
                extra = prefix / 'bin/wrapper'
                extra.write_bytes(b'unexpected executable\n')
                with self.assertRaisesRegex(ValueError, 'Installed Rust inventory'):
                    worker.verify_rust_package_toolchain(ROOT, environment)
                extra.unlink()
                crate_path.write_bytes(b'changed crate\n')
                with self.assertRaisesRegex(ValueError, 'Cargo.lock'):
                    worker.verify_rust_package_toolchain(ROOT, environment)
                crate_path.write_bytes(crate)
                index_path = base / 'cargo-home/registry/index/index.crates.io-1949cf8c6b5b557f/.cache/ba/se/base64'
                index_bytes = index_path.read_bytes()
                changed = {**entry, 'yanked': True}
                index_path.write_bytes(worker.RUST_SPARSE_HEADER + row['version'].encode() + b'\0' + canonical_json_bytes(changed) + b'\0')
                with self.assertRaisesRegex(ValueError, 'metadata differs'):
                    worker.verify_rust_package_toolchain(ROOT, environment)
                index_path.write_bytes(index_bytes)
                config = base / 'cargo-home/config.toml'
                config.write_bytes(b'[build]\nrustc-wrapper = "/untrusted"\n')
                with self.assertRaisesRegex(ValueError, 'offline Cargo configuration'):
                    worker.verify_rust_package_toolchain(ROOT, environment)
                self.assertEqual(2, versions.call_count, 'Never execute unauthenticated Rust tools')


if __name__ == '__main__':
    unittest.main()
