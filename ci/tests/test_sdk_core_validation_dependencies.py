"""Caller binding for dependency preparation; no product admission is minted."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ci import sdk_core_validation_dependencies as dependencies


class CoreDependencyPreparationTest(unittest.TestCase):
    def test_selected_request_and_java_are_bound_before_seed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            java = root / 'jdk'
            java.mkdir()
            link = root / 'selected-java'
            link.symlink_to(java, target_is_directory=True)
            value = {'target': 'jvm', 'repository': str(root), 'contractVersion': '0.8.0',
                     'compatibilityRequest': str(root / 'compatibility.json')}
            compatibility = {key: root / key for key in ('contract_payload', 'contract_metadata_receipt',
                'contract_attestation', 'contract_attestation_signature', 'contract_public_key')}
            with patch.object(dependencies, '_request', return_value=(value, b'original')), \
                    patch.object(dependencies, 'load_sdk_compatibility_request', return_value=compatibility), \
                    patch.object(dependencies, 'git_regular_blob_bytes', return_value=b'exact wrapper'), \
                    patch.object(dependencies, 'require_preprovisioned_gradle') as wrapper, \
                    patch.object(dependencies, 'seed_sdk_maven_binary_dependencies') as seed:
                arguments = dict(repository=root, revision='a' * 40, target='jvm',
                    destination=root / 'seed', native_archive=None, environment={'JAVA_HOME': str(link)})
                dependencies.prepare(root / 'request.json', **arguments)
                self.assertEqual(str(java), wrapper.call_args.args[1]['JAVA_HOME'])
                self.assertEqual('jvm', seed.call_args.kwargs['consumer_target'])
                self.assertEqual(str(compatibility['contract_payload']),
                    seed.call_args.args[5]['codexAgent.contractPayload'])
                seed.reset_mock()
                with self.assertRaisesRegex(ValueError, 'elected Core consumer'):
                    dependencies.prepare(root / 'request.json', **dict(arguments, target='node-js'))
                seed.assert_not_called()


if __name__ == '__main__':
    unittest.main()
