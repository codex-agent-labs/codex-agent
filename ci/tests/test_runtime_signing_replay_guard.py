"""Legacy combined entry points must not replay tooling with a signing secret."""

import os
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_workflow as fixture
from ci import runtime_release, runtime_aggregate_release
from ci.products.signing_isolation import SIGNING_SECRET


class RuntimeSigningReplayGuardTest(unittest.TestCase):
    def test_both_entry_points_reject_secret_before_context_transport_or_replay(self):
        for module, name, specific in (
            (runtime_release, 'attest_runtime_state_ci', {'target': 'linux-x64'}),
            (runtime_aggregate_release, 'attest_runtime_aggregate_state_ci', {'variant_handoffs': {}}),
        ):
            for live in (False, True):
                for value in ('', 'synthetic private material'):
                    supplied = {} if live else {SIGNING_SECRET: value}
                    environment = {SIGNING_SECRET: value} if live else {}
                    with self.subTest(entry=name, live=live, empty=not value), \
                            patch.dict(os.environ, environment, clear=True), \
                            patch.object(module, 'verify_product_release_context') as context, \
                            patch.object(module, 'capture_runtime_resume_upload') as capture, \
                            patch.object(module, 'materialize_runtime_attestation_inputs') as replay:
                        with self.assertRaisesRegex(ValueError, 'outside the product signing-secret context'):
                            getattr(module, name)(None, None, None, None, **specific,
                                expected_build_key=fixture.KEY, artifact_id=1, artifact_sha256=fixture.KEY,
                                state_wave=0, trusted_source_sha='a' * 40, trusted_workflow_sha='b' * 40,
                                transport_producer={}, event_payload={}, environment=supplied,
                                token='synthetic', sdk_validation_tooling={})
                        context.assert_not_called()
                        capture.assert_not_called()
                        replay.assert_not_called()

    def test_omitted_tooling_keeps_existing_context_gate(self):
        for module, name, specific in (
            (runtime_release, 'attest_runtime_state_ci', {'target': 'linux-x64'}),
            (runtime_aggregate_release, 'attest_runtime_aggregate_state_ci', {'variant_handoffs': {}}),
        ):
            with self.subTest(entry=name), patch.dict(os.environ, {SIGNING_SECRET: ''}, clear=True), \
                    patch.object(module, 'verify_product_release_context', side_effect=ValueError('context sentinel')):
                with self.assertRaisesRegex(ValueError, 'context sentinel'):
                    getattr(module, name)(None, None, None, None, **specific,
                        expected_build_key=fixture.KEY, artifact_id=1, artifact_sha256=fixture.KEY,
                        state_wave=0, trusted_source_sha='a' * 40, trusted_workflow_sha='b' * 40,
                        transport_producer={}, event_payload={}, environment={}, token='synthetic')


if __name__ == '__main__':
    unittest.main()
