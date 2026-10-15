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
                        if family == 'javascript':
                            self.assertEqual(identity.component == 'sdk-ios' and identity.phase in {'validation', 'metadata'},
                                             decision['ios_validation_direct'], identity)
                self.assertEqual([phase['buildKey']], [row['buildKey'] for row in elected], identity)

    def test_ready_ios_prefix_never_bypasses_earlier_work_or_an_executed_job(self):
        from ci.tests.test_sdk_native_continuation import ready, needs_for
        from products.registry import PHASE_INSTANCE_IDS
        import product_reuse
        ios = ready('sdk-ios', 'validation', 'ios-simulator-arm64')
        ios = {k: ios[k] for k in (*routing._IDENTITY, 'buildKey')}
        decisions = {**deepcopy(self.decisions), 'ready': [ios]}
        bound = routing.bind(decisions, self.locator, self.expected)
        decision = routing.select(bound, self.locator, self.expected, family='javascript')
        self.assertTrue(decision['ios_validation_direct'])
        prefix = (*routing._IOS_PREFIX_RESULTS, 'sdk-native-metadata-plan',
                  'sdk-native-metadata', 'sdk-collect-8')
        needs = {name: {'result': 'skipped', 'outputs': {}} for name in prefix}
        planned = {**self.locator, 'routing': json.dumps(bound, separators=(',', ':')),
                   'sdk_workers_required': 'false', 'ios_validation_direct': 'true'}
        needs['sdk-plan'] = {'result': 'success', 'outputs': planned}
        before = deepcopy(needs)
        self.assertEqual(routing.forward_routing(self.locator, planned), routing.select_ios_ready_prefix(needs))
        self.assertEqual(before, needs)
        for name in ('sdk-plan', *prefix):
            for status in ('success', 'failure', 'cancelled', 'in_progress'):
                if name == 'sdk-plan' and status == 'success':
                    continue
                changed = deepcopy(needs)
                changed[name]['result'] = status
                with self.subTest(name=name, status=status), self.assertRaises(ValueError):
                    routing.select_ios_ready_prefix(changed)
        for changes in ({'sdk_workers_required': 'true'}, {'artifact_id': '43'}, {'routing': ''}):
            changed = deepcopy(needs)
            changed['sdk-plan']['outputs'].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                routing.select_ios_ready_prefix(changed)
        for name in prefix:
            changed = deepcopy(needs)
            changed[name]['outputs'] = dict(self.locator)
            with self.subTest(unexpected_state=name), self.assertRaises(ValueError):
                routing.select_ios_ready_prefix(changed)

        earlier = ('csharp-binary', 'native-package', 'ios-package', 'javascript-metadata',
                   'native-validation', 'native-metadata')
        for identity in PHASE_INSTANCE_IDS:
            if identity.product != 'sdk' or not (product_reuse._sdk_javascript_worker_instance(identity)
                    or any(product_reuse._sdk_family_worker_instance(identity, family) for family in earlier)):
                continue
            extra = ready(identity.component, identity.phase, identity.target)
            changed = {**deepcopy(decisions), 'ready': [ios, {k: extra[k] for k in (*routing._IDENTITY, 'buildKey')}],
                       'preparation': routing.select_preparation_anchor([extra] if extra['phase'] != 'binary' else [])}
            candidate = routing.bind(changed, self.locator, self.expected)
            with self.subTest(earlier=identity):
                self.assertFalse(routing.select(candidate, self.locator, self.expected,
                                                family='javascript')['ios_validation_direct'])
        legacy = needs_for('metadata', state=self.locator)
        legacy['sdk-plan'] = {'result': 'success', 'outputs': {'ios_validation_direct': 'false'}}
        self.assertEqual(self.locator, routing.select_ios_ready_prefix(legacy))

    def test_native_resume_shortcut_requires_completed_runtime_and_ready_ios_frontier(self):
        from ci.tests.test_sdk_native_continuation import ready
        ios = ready('sdk-ios', 'validation', 'ios-simulator-arm64')
        decisions = {**deepcopy(self.decisions),
            'ready': [{k: ios[k] for k in (*routing._IDENTITY, 'buildKey')}],
            'runtime': dict(aggregate_state='completed', aggregate_required='false',
                aggregate_payload_complete='true', sdk_handoff_required='true',
                aggregate_key='sha256:' + '1' * 64, aggregate_receipt_sha256='sha256:' + '2' * 64,
                sdk_input_selection=json.dumps({'source': 'current-runtime'}))}
        arguments = dict(sdk_recovery_only=True, runtime_workers_required='false', supervisor_key='')
        result = routing.native_sdk_resume(decisions, self.locator, self.expected, **arguments)
        self.assertTrue(result['native_sdk_direct'])
        bound = routing.bind(decisions, self.locator, self.expected)
        self.assertEqual(routing.select(bound, self.locator, self.expected, family='ios-validation')['sdk_matrix'],
                         result['sdk_matrix'])
        self.assertEqual(decisions['runtime']['aggregate_key'], result['aggregate_key'])
        metadata = deepcopy(decisions)
        metadata['ready'] = [{key: phase[key] for key in (*routing._IDENTITY, 'buildKey')}
            for phase in (ready('sdk-ios', 'metadata', 'ios'), ready('sdk-core', 'binary', 'common'),
                          ready('sdk-android', 'binary', 'android'))]
        direct_metadata = routing.native_sdk_resume(metadata, self.locator, self.expected, **arguments)
        self.assertTrue(direct_metadata['native_sdk_direct'])
        self.assertEqual({'include': []}, json.loads(direct_metadata['sdk_matrix']))
        metadata_bound = routing.bind(metadata, self.locator, self.expected)
        self.assertTrue(routing.select(metadata_bound, self.locator, self.expected,
                                       family='javascript')['ios_validation_direct'])
        self.assertTrue(routing.select(metadata_bound, self.locator, self.expected,
                                       family='ios-metadata')['sdk_workers_required'])
        for changes in ({'sdk_recovery_only': False}, {'runtime_workers_required': 'true'},
                        {'supervisor_key': 'sha256:' + '3' * 64}):
            with self.subTest(changes=changes):
                self.assertEqual({'native_sdk_direct': False}, routing.native_sdk_resume(
                    decisions, self.locator, self.expected, **{**arguments, **changes}))
        for field, value in (('aggregate_state', 'ready'), ('aggregate_required', 'true'),
                ('aggregate_payload_complete', 'false'), ('sdk_handoff_required', 'false'),
                ('sdk_input_selection', json.dumps({'source': 'released-default'}))):
            changed = deepcopy(decisions)
            changed['runtime'][field] = value
            with self.subTest(field=field):
                self.assertEqual({'native_sdk_direct': False}, routing.native_sdk_resume(
                    changed, self.locator, self.expected, **arguments))
        for component, phase, target in (('sdk-ios', 'binary', 'ios'),
                ('javascript', 'validation', 'node'), ('sdk-ios', 'package', 'ios')):
            extra = ready(component, phase, target)
            changed = deepcopy(decisions)
            changed['ready'].append({k: extra[k] for k in (*routing._IDENTITY, 'buildKey')})
            self.assertFalse(routing.native_sdk_resume(changed, self.locator, self.expected,
                                                      **arguments)['native_sdk_direct'])
        for changed in ({**self.expected, 'runId': 99}, {**self.expected, 'workflowSha': 'd' * 40}):
            with self.assertRaises(ValueError):
                routing.native_sdk_resume(decisions, self.locator, changed, **arguments)
        with self.assertRaises(ValueError):
            routing.native_sdk_resume(decisions, self.locator, self.expected,
                                     **{**arguments, 'sdk_recovery_only': 'true'})

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
