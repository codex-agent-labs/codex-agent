"""Real signed tooling callback ordering; source fetching and hosted CI are not claimed.

The existing release/capture fixture supplies synthetic Git and real signatures,
with its HTTP transport mocked. No verifier or signature acceptance is mocked.
"""

import json
import shutil
import unittest
from unittest.mock import Mock

from ci.products import tooling
from ci.products.inventory import canonical_json_bytes, regular_file_inventory
from ci.tests import test_tooling_capture as capture_fixture


@unittest.skipUnless(shutil.which('ssh-keygen'), 'OpenSSH signing tool unavailable')
class ToolingSourceAuthenticationTest(unittest.TestCase):
    def setUp(self):
        fixture = capture_fixture.ToolingCaptureTest(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.source = fixture.source
        self.evidence = self.source.destination / 'tooling-evidence'

    def capture(self, callback, **overrides):
        arguments = dict(evidence=self.evidence, repository=self.source.repository,
            public_key=self.source.public_key, required_trust_domain='release',
            keyring=self.source.keyring, keys_directory=self.source.keys,
            policy_revision=self.source.source_sha, ensure_original_source=callback)
        arguments.update(overrides)
        return tooling.verified_tooling_capture(**arguments)

    def test_callback_receives_signed_original_not_outer_transport_then_yields_private_jar(self):
        caller_path = self.source.destination / 'caller.json'
        caller = json.loads(caller_path.read_bytes())
        caller['transportProducer'] = {**self.source.producer, 'runId': self.source.producer['runId'] + 100}
        caller_path.write_bytes(canonical_json_bytes(caller))
        before = regular_file_inventory(self.evidence, allow_empty=True)
        original_receipt = (self.evidence / 'original/lane/lane-receipt.json').read_bytes()
        callback = Mock()
        with self.capture(callback) as jar:
            callback.assert_called_once_with(self.source.producer)
            self.assertNotEqual(caller['transportProducer'], callback.call_args.args[0])
            self.assertEqual((self.source.lane / tooling.JAR).read_bytes(), jar.read_bytes())
            self.assertNotEqual(self.source.lane / tooling.JAR, jar)
        self.assertFalse(jar.exists())
        self.assertEqual(before, regular_file_inventory(self.evidence, allow_empty=True))
        self.assertEqual(original_receipt, (self.evidence / 'original/lane/lane-receipt.json').read_bytes())

    def test_bad_signature_and_receipt_not_matching_signed_digest_never_invoke_callback(self):
        for relative in (tooling.SIGNATURE, 'original/lane/lane-receipt.json'):
            with self.subTest(relative=relative):
                path = self.evidence / relative
                original = path.read_bytes()
                if relative == tooling.SIGNATURE:
                    path.write_bytes(b'invalid signature\n')
                else:
                    receipt = json.loads(original)
                    receipt['runId'] += 1
                    path.write_bytes(canonical_json_bytes(receipt))
                callback = Mock()
                try:
                    with self.assertRaises(ValueError), self.capture(callback):
                        self.fail('Unauthenticated original reached JAR use')
                    callback.assert_not_called()
                finally:
                    path.write_bytes(original)

    def test_callback_failure_cannot_yield_an_authenticated_jar(self):
        callback = Mock(side_effect=ValueError('original source unavailable'))
        before = regular_file_inventory(self.evidence, allow_empty=True)
        with self.assertRaisesRegex(ValueError, 'original source unavailable'), self.capture(callback):
            self.fail('Failed original-source import reached JAR use')
        callback.assert_called_once_with(self.source.producer)
        self.assertEqual(before, regular_file_inventory(self.evidence, allow_empty=True))

    def test_full_original_receipt_payload_gate_still_runs_after_successful_callback(self):
        jar = self.evidence / 'original/lane' / tooling.JAR
        jar.write_bytes(jar.read_bytes() + b'tampered original payload')
        callback = Mock()
        with self.assertRaisesRegex(ValueError, 'integrity-mismatched'), self.capture(callback):
            self.fail('Source callback bypassed original JAR receipt binding')
        callback.assert_called_once_with(self.source.producer)

    def test_current_git_tooling_policy_still_runs_after_successful_callback(self):
        # A real new compiler-input revision is incompatible with this otherwise
        # valid original signed JAR; importing its old source cannot override it.
        revision = self.source.fixture.commit('gradle/build-logic/src/main/kotlin/ChangedTooling.kt',
                                              '// different caller compiler policy\n')
        callback = Mock()
        with self.assertRaisesRegex(ValueError, 'compiler/build inputs differ'), \
                self.capture(callback, policy_revision=revision):
            self.fail('Source callback bypassed current tooling policy')
        callback.assert_called_once_with(self.source.producer)


if __name__ == '__main__':
    unittest.main()
