"""Probe routing tests only, never hosted toolchain authentication evidence."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci.tests import phase9_xcode_probe as probe
from ci.products.registry import PHASE_INSTANCE_IDS
from ci.products.selection import phase_inventory_paths


class XcodeProbeTest(unittest.TestCase):
    def test_signature_failure_is_retained_and_never_treated_as_provisioned(self):
        for signature_status in (0, 1):
            with self.subTest(signature_status=signature_status), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                event = root / 'event.json'
                event.write_text(json.dumps(dict(pull_request=dict(number=31, head=dict(sha='a'*40,
                    repo=dict(full_name='codex-agent-labs/codex-agent', fork=False))),
                    label=dict(name='ci:phase9-xcode-probe'))))
                environment = dict(GITHUB_EVENT_PATH=str(event), GITHUB_ACTIONS='true',
                    GITHUB_EVENT_NAME='pull_request', GITHUB_REPOSITORY='codex-agent-labs/codex-agent',
                    GITHUB_SHA='b'*40, GITHUB_RUN_ID='1', GITHUB_RUN_ATTEMPT='1',
                    DEVELOPER_DIR='/Applications/Xcode_26.6.app/Contents/Developer', RUNNER_OS='macOS', RUNNER_ARCH='ARM64')
                def run(command, **kwargs):
                    stdout = ('Xcode 26.6\nBuild version 17F113\n' if command[0].endswith('xcodebuild') else
                              'Apple Swift version 6.3.3\n' if command[1:2] == ['swift'] else 'fixture observation\n')
                    return SimpleNamespace(returncode=signature_status if '--verify' in command else 0,
                                           stdout=stdout, stderr='')
                with patch.dict(os.environ, environment), \
                        patch.object(probe.subprocess, 'check_output', side_effect=['a'*40, b'']), \
                        patch.object(probe, 'git_regular_blob_bytes', return_value=b'fixture'), \
                        patch.object(probe, '_toolchain_expectations', return_value=dict(
                            xcodeVersion='26.6', xcodeBuild='17F113', swiftVersion='6.3.3')), \
                        patch.object(Path, 'is_dir', return_value=True), patch.object(Path, 'is_symlink', return_value=False), \
                        patch.object(probe.subprocess, 'run', side_effect=run) as observed:
                    if signature_status:
                        with self.assertRaisesRegex(ValueError, 'probe failed'):
                            probe.probe(root / 'output')
                    else:
                        probe.probe(root / 'output')
                record = json.loads((root / 'output/observations.json').read_bytes())
                self.assertFalse(record['toolchainExported'])
                self.assertFalse(record['releaseAdmission'])
                self.assertEqual(record['productExecutions'], 0)
                self.assertEqual(record['observations']['signature']['returnCode'], signature_status)
                self.assertIn('-R=anchor apple', record['observations']['signature']['command'])
                self.assertEqual(10, observed.call_count)

    def test_wrong_event_stops_before_toolchain_observation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            event = root / 'event.json'
            event.write_text('{}')
            with patch.dict(os.environ, GITHUB_EVENT_PATH=str(event), GITHUB_ACTIONS='false'), \
                    patch.object(probe.subprocess, 'check_output', return_value='a'*40), \
                    patch.object(probe.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'same-repository'):
                    probe.probe(root / 'output')
            run.assert_not_called()
            self.assertFalse((root / 'output').exists())

    def test_narrow_read_only_workflow_and_zero_product_input_ownership(self):
        workflow = '.github/workflows/portable-reuse-proof.yml'
        block = (probe.ROOT / workflow).read_text().split('  phase9-xcode-probe:\n', 1)[1].split('  phase9-ios-mutation:\n', 1)[0]
        self.assertIn("github.event.label.name == 'ci:phase9-xcode-probe'", block)
        self.assertIn('github.event.pull_request.head.repo.fork == false', block)
        self.assertIn('persist-credentials: false', block)
        self.assertIn('retention-days: 90', block)
        for forbidden in ('setup-kmp', 'rust-toolchain', 'gradlew', 'cargo', 'secrets.', 'GITHUB_TOKEN'):
            self.assertNotIn(forbidden, block)
        self.assertIn("if: success() && github.event.label.name == 'ci:phase9-xcode-provision'", block)
        self.assertIn('path: ${{ runner.temp }}/phase9-xcode-probe/xcode-26.6.dmg.cms', block)
        self.assertNotIn('path: ${{ runner.temp }}/xcode-26.6.dmg', block)
        paths = (workflow, 'ci/tests/phase9_xcode_probe.py', 'ci/tests/test_phase9_xcode_probe.py',
                 'ci/tests/fixtures/phase9-xcode-recipient.pem')
        self.assertTrue(all(not phase_inventory_paths(paths, phase) for phase in PHASE_INSTANCE_IDS))

    def test_private_transport_rejects_identity_changes_and_never_publishes_partial_encryption(self):
        details = {'signature-details': {'stderr': 'CandidateCDHashFull sha256=' +
            '502eca5e95e1b8eaaf52e9b38617e8e7d23f46db1d7122169443c05837c40cff'}}
        with patch.object(probe.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'Apple code identity'):
                probe.export_private_image(Path('/unused'), Path('/unused.app'),
                    {'signature-details': {'stderr': 'wrong identity'}})
            with patch.object(probe, 'sha256_file', return_value='sha256:' + '0'*64):
                with self.assertRaisesRegex(ValueError, 'recipient'):
                    probe.export_private_image(Path('/unused'), Path('/unused.app'), details)
            run.assert_not_called()
        for failed in (False, True):
            with self.subTest(encryption_failed=failed), tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary) / 'observations'
                destination.mkdir()
                (destination / 'observations.json').write_text('{}\n')
                def run(command, **kwargs):
                    if command[0].endswith('hdiutil'):
                        Path(command[-1]).write_bytes(b'fixture image, not a toolchain')
                    else:
                        self.assertIn('-aes256', command)
                        self.assertIn('-stream', command)
                        self.assertNotIn('-inkey', command)
                        Path(command[command.index('-out') + 1]).write_bytes(b'fixture cipher')
                        if failed:
                            raise subprocess.CalledProcessError(1, command)
                with patch.object(probe.subprocess, 'run', side_effect=run):
                    if failed:
                        with self.assertRaises(subprocess.CalledProcessError):
                            probe.export_private_image(destination, Path('/Applications/Xcode_26.6.app'), details)
                    else:
                        probe.export_private_image(destination, Path('/Applications/Xcode_26.6.app'), details)
                self.assertEqual((destination / 'xcode-26.6.dmg.cms').exists(), not failed)
                self.assertEqual((destination / 'provisioning.json').exists(), not failed)
                if not failed:
                    evidence = json.loads((destination / 'provisioning.json').read_bytes())
                    self.assertFalse(evidence['privateKeyTransferred'])
                    self.assertFalse(evidence['plaintextUploaded'])
                    self.assertEqual(evidence['productExecutions'], 0)


if __name__ == '__main__':
    unittest.main()
