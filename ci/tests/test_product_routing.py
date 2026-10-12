"""Routing hints from workflow outputs cannot become product admission."""
from copy import deepcopy
from contextlib import ExitStack
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from ci import sdk_native_continuation as routing


class ProductRoutingTest(unittest.TestCase):
    def setUp(self):
        self.locator = dict(artifact_id='42', artifact_digest='sha256:' + 'a' * 64,
                            state_wave='0', sdk_state_wave='')
        self.producer = dict(repository='codex-agent-labs/codex-agent', workflowPath='.github/workflows/ci.yml',
            commit='a' * 40, tree='b' * 40, event='pull_request', runId=7, runAttempt=1, pullRequest=31)
        self.expected = {**self.producer, 'workflowSha': 'c' * 40, 'planId': '41'}
        self.decisions = dict(schemaVersion=1, producer=self.producer, workflowSha='c' * 40,
            ready=[dict(product='sdk', component='javascript', phase='validation', target='node',
                        buildKey='sha256:' + 'd' * 64)],
            preparation=dict(preparation_required=False, component='', phase='', target='', build_key=''),
            runtime={'aggregate_state': 'completed'})

    def test_all_families_route_without_product_capture_replay_or_cache(self):
        import product_reuse
        value = routing.bind(self.decisions, self.locator, self.expected)
        with ExitStack() as stack:
            for name in ('inspect_products', 'capture_runtime_resume_upload', 'regular_file_inventory',
                         'verified_zip_contents', '_prior_failed_pr_attempts', 'api_json', 'publish_regular_tree'):
                stack.enter_context(patch.object(product_reuse, name, side_effect=AssertionError(name)))
            for family in ('javascript', 'ios-binary', *product_reuse.SDK_WORKER_FAMILIES):
                result = routing.select(value, self.locator, self.expected, family=family)
                self.assertEqual(family == 'javascript', result['sdk_workers_required'])
            self.assertEqual({'aggregate_state': 'completed'},
                routing.select(value, self.locator, self.expected, family='runtime'))

    def test_every_registered_sdk_frontier_is_emitted_and_routed_without_body_io(self):
        from ci.tests.test_sdk_native_continuation import ready
        from products.registry import PHASE_INSTANCE_IDS
        import product_reuse
        plan = dict(repository=self.producer['repository'], event='pull_request', pullRequest=31,
                    validationCommit=self.producer['commit'], validationTree=self.producer['tree'])
        env = dict(GITHUB_RUN_ID='7', GITHUB_RUN_ATTEMPT='1')
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'output'
            for identity in PHASE_INSTANCE_IDS:
                if identity.product != 'sdk':
                    continue
                phase = ready(identity.component, identity.phase, identity.target)
                if output.exists():
                    output.unlink()
                routing.emit(plan, {'phases': []}, [phase], {}, {'versions': {}},
                             Path(temporary), env, self.expected['workflowSha'], output)
                rows = dict(line.split('=', 1) for line in output.read_text().splitlines())
                value = routing.bind(json.loads(rows['routing_decisions']), self.locator, self.expected)
                elected = []
                with patch.object(product_reuse, 'inspect_products', side_effect=AssertionError('replay')), \
                        patch.object(product_reuse, 'capture_runtime_resume_upload', side_effect=AssertionError('download')):
                    for family in ('javascript', 'ios-binary', *product_reuse.SDK_WORKER_FAMILIES):
                        decision = routing.select(value, self.locator, self.expected, family=family)
                        elected.extend(json.loads(decision['sdk_matrix'])['include'])
                self.assertEqual([phase['buildKey']], [row['buildKey'] for row in elected], identity)

    def test_forwarding_checks_locator_and_terminal_gates(self):
        from ci.tests.test_sdk_native_continuation import needs_for
        encoded = json.dumps(routing.bind(self.decisions, self.locator, self.expected), separators=(',', ':'))
        needs = needs_for('metadata', state={**self.locator, 'routing': encoded})
        self.assertEqual(encoded, routing.select_native_state(needs, stage='metadata')['routing'])
        changed = deepcopy(needs)
        changed['sdk-native-validation-result']['outputs']['artifact_id'] = '43'
        with self.assertRaises(ValueError):
            routing.select_native_state(changed, stage='metadata')
        for status in ('failure', 'cancelled', 'in_progress'):
            changed = deepcopy(needs)
            changed['sdk-native-metadata']['result'] = status
            with self.assertRaises(ValueError):
                routing.select_native_state(changed, stage='metadata')

    def test_changed_locator_context_identity_and_preparation_reject(self):
        value = routing.bind(self.decisions, self.locator, self.expected)
        for field in self.locator:
            changed = {**self.locator, field: {'artifact_id': '43', 'artifact_digest': 'sha256:' + 'b' * 64,
                'state_wave': '1', 'sdk_state_wave': '3'}[field]}
            with self.subTest(locator=field), self.assertRaises(ValueError):
                routing.select(value, changed, self.expected, family='javascript')
        for field in ('commit', 'tree', 'repository', 'runId', 'runAttempt', 'planId', 'workflowSha'):
            with self.subTest(context=field), self.assertRaises(ValueError):
                routing.select(value, self.locator, {**self.expected, field: 'different'}, family='javascript')
        for kind in ('duplicate', 'unknown', 'key', 'preparation', 'output-key', 'output-value'):
            changed = deepcopy(self.decisions)
            if kind == 'duplicate': changed['ready'] *= 2
            elif kind == 'unknown': changed['ready'][0]['component'] = 'unknown'
            elif kind == 'key': changed['ready'][0]['buildKey'] = 'invalid'
            elif kind == 'output-key': changed['runtime']['aggregate_state\nother_output'] = 'bad'
            elif kind == 'output-value': changed['runtime']['aggregate_state'] = 'bad\nother_output=true'
            else: changed['preparation']['preparation_required'] = True
            with self.subTest(changed=kind), self.assertRaises(ValueError):
                routing.bind(changed, self.locator, self.expected)


if __name__ == '__main__':
    unittest.main()
