"""Non-secret CLI dispatch, not preparation transport or signing admission."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ci.tests import test_runtime_aggregate_tooling_cli as fixtures
from ci.products.signing_isolation import SIGNING_SECRET


release = fixtures.runtime_release


class RuntimePreparationCliTest(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.RuntimeAggregateToolingCliTest()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_native_and_aggregate_prepare_never_dispatch_signing(self):
        for target in ('linux-x64', 'aggregate'):
            with self.subTest(target=target):
                argv = self.case.argv.copy()
                argv[argv.index('--target') + 1] = target
                prepared = Mock()
                with patch.dict(release.os.environ, self.case.environment, clear=True), \
                        patch.dict('sys.modules', {'runtime_signing_preparation': SimpleNamespace(
                            prepare_runtime_signing_inputs=prepared)}), \
                        patch.object(release, 'attest_runtime_state_ci') as signer:
                    release.main(argv + ['--prepare-only', '--sdk-validation-tooling', str(self.case.policy_path)])
                    prepared.assert_called_once()
                    self.assertEqual(target, prepared.call_args.kwargs['target'])
                    self.assertEqual(self.case.policy, prepared.call_args.kwargs['sdk_validation_tooling'])
                    self.assertNotIn('release_handoffs', prepared.call_args.kwargs)
                    self.assertNotIn('variant_handoffs', prepared.call_args.kwargs)
                    signer.assert_not_called()

    def test_secret_is_rejected_before_reading_event_or_any_dispatch(self):
        for value in ('', 'synthetic'):
            with self.subTest(empty=not value), patch.dict(release.os.environ, {SIGNING_SECRET: value}, clear=True), \
                    patch.object(release, 'read_regular_file_bytes') as read:
                with self.assertRaisesRegex(ValueError, 'outside the product signing-secret context'):
                    release.main(self.case.argv + ['--prepare-only'])
                read.assert_not_called()

    def test_preparation_rejects_unbound_handoff_overrides_before_event_read(self):
        for option in (['--release-handoff', 'carrier'], ['--variant-handoff', 'linux-x64=carrier']):
            with self.subTest(option=option), patch.dict(release.os.environ, {}, clear=True), \
                    patch.object(release, 'read_regular_file_bytes') as read:
                with self.assertRaises(SystemExit) as error:
                    release.main(self.case.argv + ['--prepare-only', *option])
                self.assertEqual(2, error.exception.code)
                read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
