"""Retained ordinary ios-package route: original frameworks into the unchanged hosted lane."""
from contextlib import ExitStack
import importlib.util
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ci.tests.test_runtime_reference_transport import RangeOpener

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'apple_package_inputs', ROOT / '.github/actions/run-ci-lane/apple_package_inputs.py')
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)
APPLE = (ROOT / '.github/workflows/apple-runtime-evidence.yml').read_text()
PRODUCT = (ROOT / '.github/workflows/product-validation.yml').read_text()


def _job(text, name):
    body = text.split('\n  ' + name + ':\n', 1)[1]
    end = [i for i, line in enumerate(body.splitlines()) if line and not line.startswith('    ') and line.startswith('  ')]
    return '\n'.join(body.splitlines()[:end[0]] if end else body.splitlines())


def _leaves():
    rows, data = [], {}
    for target in helper._TARGETS.values():
        for leaf in helper._LEAVES:
            path = helper._prefix(target) + leaf
            data[path] = (target + ':' + leaf).encode()
            rows.append({'relativePath': path, 'kind': 'apple-binary', 'bytes': len(data[path]),
                         'sha256': helper.sha256_bytes(data[path])})
    return rows, data


class SelectedActionsTest(unittest.TestCase):
    def plan(self, **actions):
        return {'lanes': {'ios-package': {'build': False, 'test': False, 'metadata': False, **actions}}}

    def test_serves_only_planned_build_and_metadata(self):
        self.assertEqual(['build', 'metadata'], helper.selected_actions(self.plan(build=True, metadata=True)))
        self.assertEqual(['metadata'], helper.selected_actions(self.plan(metadata=True)))
        for bad in (self.plan(), self.plan(test=True), self.plan(build=True, test=True), self.plan(build=1)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                helper.selected_actions(bad)


class _Native:
    pass


@patch.object(helper, 'CompletedFrozenReuse', _Native)
class ExpectedOriginalTest(unittest.TestCase):
    def native(self, outputs, record=None):
        record = record or {'product': 'sdk', 'component': 'sdk-ios', 'phase': 'binary', 'target': 'ios',
                            'buildKey': 'sha256:' + 'a' * 64, 'receiptSha256': 'sha256:' + 'b' * 64,
                            'objectSha256': 'sha256:' + 'c' * 64}
        native = _Native()
        native.check_consumer = lambda consumer: None
        native._values = lambda: (None, {helper._BINARY: record})
        native.envelope = lambda value: {'receipt': {'outputs': outputs}}
        return native, record

    def test_requires_exactly_four_original_leaves_per_framework(self):
        rows, _ = _leaves()
        native, record = self.native(rows + [{'relativePath': 'outputs/apple/other.zip', 'kind': 'apple', 'bytes': 1,
                                               'sha256': 'sha256:' + 'd' * 64}])
        expected = helper._expected(native, {})
        self.assertEqual({k: record[k] for k in helper._FIELDS}, expected['originalInput'])
        self.assertEqual({'device', 'simulator'}, set(expected['frameworks']))
        self.assertEqual(sorted(helper._LEAVES), [r['relativePath'] for r in helper._framework_inventory(expected, 'device')])
        for bad in (rows[1:], rows + [{**rows[0], 'relativePath': rows[0]['relativePath'] + '.extra'}],
                    [{**rows[0], 'kind': 'apple'}] + rows[1:]):
            with self.subTest(count=len(bad)), self.assertRaises(ValueError):
                helper._expected(self.native(bad)[0], {})
        with self.assertRaises(ValueError):
            helper._expected(object(), {})


class CopyFrameworksTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def transport(self):
        rows, data = _leaves()
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, 'w', compression=zipfile.ZIP_STORED) as z:
            z.writestr('stage/outputs/device/unconsumed.bin', b'x' * (2 * 1024 ** 2))
            for name, value in data.items():
                z.writestr('stage/' + name, value)
        member = {'relativePath': 'objects/b.zip', 'bytes': len(inner.getvalue()),
                  'sha256': helper.sha256_bytes(inner.getvalue())}
        outer = io.BytesIO()
        with zipfile.ZipFile(outer, 'w', compression=zipfile.ZIP_STORED) as z:
            z.writestr(member['relativePath'], inner.getvalue())
        artifact = {'id': 1, 'size_in_bytes': len(outer.getvalue()), 'digest': helper.sha256_bytes(outer.getvalue()),
                    'archive_download_url': 'https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/1/zip'}
        binary = dict(product='sdk', component='sdk-ios', phase='binary', target='ios')
        native = SimpleNamespace(envelope=lambda record: {'receipt': {}},
            sdk_extension=lambda: {'spec': {'schemaVersion': 4, 'completedPhases': [binary]}, 'proof': {'members': [member]}},
            sdk_original=lambda: {'proof': {'member': member}},
            observe_sdk=lambda **k: (artifact, {}, []),
            observe_extended_sdk=lambda *a, **k: ({}, artifact, []))
        expected = {'frameworks': {name: [r for r in rows if r['relativePath'].startswith(helper._prefix(target))]
                                   for name, target in helper._TARGETS.items()}}
        state = SimpleNamespace(completed_frozen=native, producer={}, plan={})
        return state, {'objectSha256': member['sha256']}, expected, RangeOpener({1: outer.getvalue()}), data

    def test_streams_only_the_eight_original_leaves_into_two_frameworks(self):
        import runtime_reference_archive as transport
        state, record, expected, opener, data = self.transport()
        with patch.object(transport.urllib.request, 'build_opener', return_value=opener), \
             patch.object(helper, 'original_worker_member', return_value=True), \
             patch.object(helper, '_retained_dependency_plan') as dependency, \
             patch.object(zipfile.ZipFile, 'read', side_effect=AssertionError('no read-all')), \
             patch.object(helper.products, '_restore_product_objects', side_effect=AssertionError('no whole object restore')):
            with ExitStack() as stack:
                helper._copy_frameworks(state, record, expected, self.root / 'frameworks', stack, 'fixture')
            dependency.assert_called_once()
        for name, target in helper._TARGETS.items():
            framework = self.root / 'frameworks' / name / 'CodexAgent.framework'
            self.assertEqual(set(helper._LEAVES),
                             {p.relative_to(framework).as_posix() for p in framework.rglob('*') if p.is_file()})
            for leaf in helper._LEAVES:
                self.assertEqual(data[helper._prefix(target) + leaf], (framework / leaf).read_bytes())
        self.assertLess(sum(b - a + 1 for _, a, b in opener.requests), 1024 ** 2)

    def test_wrong_digest_or_changed_authority_denies(self):
        import runtime_reference_archive as transport
        for mode in ('digest', 'late', 'parent'):
            state, record, expected, opener, _ = self.transport()
            if mode == 'digest':
                expected['frameworks']['device'][0]['sha256'] = 'sha256:' + '0' * 64
            if mode == 'parent':
                state.completed_frozen.sdk_extension = lambda: None
                record = {'objectSha256': 'sha256:' + '0' * 64}
            with self.subTest(mode=mode), \
                 patch.object(transport.urllib.request, 'build_opener', return_value=opener), \
                 patch.object(helper, 'original_worker_member', return_value=True), \
                 patch.object(helper, '_retained_dependency_plan'):
                with self.assertRaises(ValueError), ExitStack() as stack:
                    helper._copy_frameworks(state, record, expected, self.root / mode, stack, 'fixture')
                    state.completed_frozen.envelope = lambda record: {'changed': True}


class RecordTest(unittest.TestCase):
    def test_record_names_the_unchanged_lane_and_never_a_waiver(self):
        expected = {'originalInput': {'buildKey': 'sha256:' + 'a' * 64}, 'frameworks': {'device': [], 'simulator': []}}
        producer, digest = {'commit': 'a' * 40}, 'sha256:' + 'b' * 64
        record = {'schemaVersion': 1, 'kind': 'retained-apple-package-inputs', 'lane': 'ios-package',
                  'actions': ['build', 'metadata'], 'producer': producer, 'planSha256': digest, **expected,
                  'laneReceipt': 'unchanged-hosted-ios-package-lane', 'productBodiesCompiled': False}
        self.assertEqual(record, helper.validate_record(record, producer, digest, expected))
        for field, value in (('lane', 'ios-swift-tests'), ('actions', ['test']), ('actions', []),
                             ('actions', ['metadata', 'build']), ('laneReceipt', 'waived'),
                             ('productBodiesCompiled', True), ('originalInput', {})):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                helper.validate_record({**record, field: value}, producer, digest, expected)
        with self.assertRaises(ValueError):
            helper.validate_record(record, producer, 'sha256:' + 'c' * 64, expected)

    def test_stage_requires_live_session_and_fixed_host_before_any_transfer(self):
        with patch.object(helper, '_copy_frameworks', side_effect=AssertionError('no transfer')):
            with self.assertRaisesRegex(ValueError, 'live verified state'):
                helper.stage_retained_package_inputs(object(), plan_path='p', repository_root=ROOT,
                                                     environ={}, staging=ROOT / 'never')


class RetainedPackageWorkflowTest(unittest.TestCase):
    def test_retained_package_job_runs_the_unchanged_lane_from_original_frameworks(self):
        job = _job(APPLE, 'retained-package')
        self.assertIn('if: inputs.retainedPackageOnly && !inputs.retainedSwiftSourceOnly && !inputs.sdkBinaryOnly', job)
        self.assertNotIn('needs:', job)
        self.assertNotIn('framework-device', job)
        self.assertNotIn('framework-simulator', job)
        steps = [job.index(token) for token in (
            'restore-reuse-qualification@reuse-authority', 'cmp build/ci-retained-package/impact-plan.json build/ci/impact-plan.json',
            "outputs.get('full_reuse') != 'true'", '.github/actions/run-ci-lane/apple_package_inputs.py',
            'IOS_DEVICE_FRAMEWORK=', 'uses: ./.github/actions/run-ci-lane', 'lane: ios-package')]
        self.assertEqual(sorted(steps), steps)
        self.assertNotIn('force-build', job)
        self.assertNotIn('reuse-disabled', job)
        self.assertEqual(1, job.count('uses: ./.github/actions/run-ci-lane'))

    def test_broad_select_and_swift_source_never_run_in_the_package_caller(self):
        self.assertIn("if: ${{ !inputs.retainedSwiftSourceOnly && !inputs.retainedPackageOnly }}", _job(APPLE, 'select'))
        self.assertIn('if: inputs.retainedSwiftSourceOnly && !inputs.retainedPackageOnly && !inputs.sdkBinaryOnly',
                      _job(APPLE, 'retained-swift-source'))
        self.assertIn("Retained Apple package checks require retained Apple mode", _job(APPLE, 'select'))

    def test_product_caller_and_merge_gate_require_the_route_exactly_when_selected(self):
        caller = _job(PRODUCT, 'retained-apple-package')
        for token in ("needs.plan.outputs.retained_apple == 'true' && needs.plan.outputs.retained_apple_package == 'true'",
                      "needs.product-resume.outputs.full_reuse == 'true'", '!inputs.sdkRecoveryOnly',
                      'retainedPackageOnly: true', 'resumeOutputs: ${{ toJSON(needs.product-resume.outputs) }}',
                      'authority_read_token: ${{ secrets.REUSE_AUTHORITY_READ_TOKEN }}'):
            self.assertIn(token, caller)
        self.assertNotIn('retainedAppleChecks', caller)
        self.assertIn("retainedPackageChecks: ${{ needs.plan.outputs.retained_apple_package == 'true' }}",
                      _job(PRODUCT, 'apple'))
        gate = _job(PRODUCT, 'merge-gate')
        self.assertIn(' retained-apple-package,', [l for l in gate.splitlines() if l.startswith('    needs:')][0])
        self.assertIn('if [ "$RETAINED_APPLE" = true ] && [ "$RETAINED_APPLE_PACKAGE" = true ]; then\n'
                      '            test "$RETAINED_APPLE_PACKAGE_RESULT" = success || exit 1\n'
                      '          fi', gate)

    def test_retained_select_schedules_the_route_instead_of_raising(self):
        script = APPLE.split('              # Remaining duties', 1)[1]
        script = script.split("python3 -B - <<'PYCODE'\n", 1)[1].split('          PYCODE', 1)[0]
        script = '\n'.join(line[10:] for line in script.splitlines())
        lanes = {lane: {'build': False, 'test': False, 'metadata': False} for lane in (
            'ios-native-tests', 'ios-rust-device', 'ios-rust-simulator', 'ios-kotlin-tests', 'ios-swift-build', 'ios-package')}
        lanes['ios-package'].update(build=True, metadata=True)
        lanes['ios-kotlin-tests']['test'] = True
        lanes['ios-swift-build'].update(build=True, test=True)
        environment = {'RETAINED_APPLE_REVIEWED': 'true', 'RETAINED_SWIFT_SOURCE': 'true'}
        for package in ('true', 'false'):
            with patch.dict(os.environ, {**environment, 'RETAINED_PACKAGE': package}, clear=True), \
                 patch.object(Path, 'read_text', return_value=json.dumps({'lanes': lanes})):
                if package == 'true':
                    exec(compile(script, 'retained-package-guard', 'exec'), {})
                else:
                    with self.assertRaisesRegex(ValueError, 'retained-input checks: ios-package$'):
                        exec(compile(script, 'retained-package-guard', 'exec'), {})


if __name__ == '__main__':
    unittest.main()
