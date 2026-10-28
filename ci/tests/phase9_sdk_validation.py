"""Narrow hosted SDK validation carrier; transported flags never grant admission.

The caller pins the selection independently. Original bytes/receipts survive intact;
only request paths are rebound. Fixed product executors retain their own full checks.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ci'))
sys.path.insert(0, str(ROOT))
from ci.tests import phase9_ios_mutation as transport
from ci.tests.phase9_ios_package_check import receive
from native_wrappers import host_classifier
from products.inventory import (canonical_json_bytes, git_product_versions,
    load_canonical_json_bytes, read_regular_file_bytes, require_exact_keys,
    require_relative_path, require_sha256, sha256_bytes, write_canonical_json)
from products.plan import (NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST,
    native_runtime_validation_dependencies, plan_phase)
from products.receipt import compute_build_key, validate_phase_receipt, validate_producer
from products.registry import PhaseInstanceId, phase_instance_dependencies, required_contract_components
from products.restore import verification_session
from products.selection import phase_git_inventory
from products.signing_isolation import require_no_signing_secret

PURPOSE = 'phase9-sdk-missing-host-validation'
LABEL = 'ci:phase9-sdk-host-validation'
HOSTS = {'linux-arm64': ('Linux', 'ARM64'), 'macos-x64': ('macOS', 'X64'),
         'windows-x64': ('Windows', 'X64')}
LANGUAGES = frozenset(('python', 'csharp', 'cpp', 'rust', 'dart'))
EXCLUDED = (':codex-agent-sdk:invalidateNativeWrapperProductPhaseOutputs',
            ':codex-agent-sdk:snapshotImportedNativeWrapperRuntimeStages')
FUNCTION_SHA = '2392f89e01a9647797042882d576f8d3dadc04216d2ff72173b86df70985f11b'


def read(path):
    return load_canonical_json_bytes(read_regular_file_bytes(Path(path),
        max_bytes=16 * 1024**2, reject_symlink_parents=True))


def ref(path):
    path = Path(path)
    return {'path': str(path), 'sha256': sha256_bytes(read_regular_file_bytes(path,
        max_bytes=16 * 1024**2, reject_symlink_parents=True))}


def member(root, relative):
    path = root / require_relative_path(relative, 'SDK carrier member')
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('SDK carrier members cannot traverse symbolic links')
    return path


def selection(path, expected, target):
    raw = read_regular_file_bytes(path, max_bytes=16 * 1024**2, reject_symlink_parents=True)
    if sha256_bytes(raw) != require_sha256(expected, 'Independent SDK selection pin'):
        raise ValueError('SDK selection changed')
    spec = require_exact_keys(load_canonical_json_bytes(raw),
        {'schemaVersion', 'purpose', 'source', 'checkpoint', 'hosts'}, 'SDK selection')
    if type(spec['schemaVersion']) is not int or spec['schemaVersion'] != 1 or spec['purpose'] != PURPOSE or target not in HOSTS:
        raise ValueError('Unsupported SDK carrier purpose or host')
    source = require_exact_keys(spec['source'], {'commit', 'tree', 'bundles'}, 'SDK source')
    if any(len(source[k]) != 40 or any(c not in '0123456789abcdef' for c in source[k])
           for k in ('commit', 'tree')) or not source['bundles']:
        raise ValueError('Exact SDK source and bundles required')
    checkpoint = require_exact_keys(spec['checkpoint'], {'sha256', 'retainedKeys'}, 'SDK checkpoint')
    require_sha256(checkpoint['sha256'], 'Original checkpoint')
    keys = checkpoint['retainedKeys']
    if not isinstance(keys, list) or keys != sorted(set(keys)):
        raise ValueError('Retained keys must be unique and sorted')
    for key in keys:
        require_sha256(key, 'Original retained key')
    host = require_exact_keys(spec['hosts'][target],
        {'files', 'bindings', 'requests', 'paths', 'originals', 'plans'}, 'SDK host selection')
    names, digests = [], {}
    for row in host['files']:
        require_exact_keys(row, {'relativePath', 'sha256', 'bytes'}, 'SDK transported member')
        names.append(require_relative_path(row['relativePath'], 'SDK transported member'))
        require_sha256(row['sha256'], 'SDK transported digest')
        if type(row['bytes']) is not int or row['bytes'] < 0:
            raise ValueError('Invalid transported byte length')
        if row['sha256'] in digests and digests[row['sha256']] != row['bytes']:
            raise ValueError('One digest cannot have conflicting lengths')
        digests[row['sha256']] = row['bytes']
    if names != sorted(set(names)):
        raise ValueError('SDK input inventory must be unique and sorted')
    if not host['plans']:
        raise ValueError('No missing SDK phase selected')
    for component, plan in host['plans'].items():
        if (component not in LANGUAGES | {'sdk-core'} or
                (component == 'sdk-core' and target == 'linux-arm64') or
                tuple(plan[k] for k in ('product', 'component', 'phase', 'target')) !=
                ('sdk', component, 'validation', target)):
            raise ValueError('Only the selected missing native/Core validations may execute')
        if (compute_build_key(product='sdk', component=component, phase='validation',
                target=target, inputs=plan['inputs']) != plan['buildKey'] or
                plan['buildKey'] in keys):
            raise ValueError('Invalid or already-retained SDK key; reuse it instead')
    for name, value in host['requests'].items():
        if name not in {'compatibility', 'facade'} or value not in names:
            raise ValueError('Original SDK request must be an exact transported member')
    for value in host['bindings'].values():
        relative = require_relative_path(value, 'SDK path binding')
        if relative.split('/')[0] not in {'source', 'inputs', 'rebased'}:
            raise ValueError('SDK path binding escapes the prepared carrier')
    for bundle in source['bundles']:
        require_exact_keys(bundle, {'relativePath', 'head'}, 'SDK source bundle')
        if bundle['relativePath'] not in names or len(bundle['head']) != 40:
            raise ValueError('SDK source bundle must be selected explicitly')
    return spec, host, raw


def hosted_context(target):
    require_no_signing_secret(os.environ)
    if any(os.environ.get(key) for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE',
            'GIT_OBJECT_DIRECTORY', 'GIT_COMMON_DIR', 'GIT_ALTERNATE_OBJECT_DIRECTORIES')):
        raise ValueError('Hosted controller must use its ordinary exact checkout')
    revision = transport.git('rev-parse', 'HEAD')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    pr = event.get('pull_request', {}); head = pr.get('head', {})
    repository = 'codex-agent-labs/codex-agent'
    if (os.environ.get('GITHUB_ACTIONS') != 'true' or
            os.environ.get('GITHUB_EVENT_NAME') != 'pull_request' or
            os.environ.get('GITHUB_REPOSITORY') != repository or pr.get('number') != 31 or
            head.get('repo', {}).get('full_name') != repository or
            head.get('repo', {}).get('fork') is not False or head.get('sha') != revision or
            event.get('label', {}).get('name') != LABEL or transport.git('diff', 'HEAD', '--') or
            host_classifier() != target or
            (os.environ.get('RUNNER_OS'), os.environ.get('RUNNER_ARCH')) != HOSTS[target]):
        raise ValueError('Exact labeled PR source and actual native host required before acquisition')
    if target == 'macos-x64' and subprocess.run(
            ['sysctl', '-in', 'sysctl.proc_translated'], capture_output=True, text=True).stdout.strip() == '1':
        raise ValueError('SDK x64 validation requires a real Intel host')
    producer = validate_producer(dict(commit=revision, tree=transport.git('rev-parse', 'HEAD^{tree}'),
        repository=repository, event='pull_request', pullRequest=31,
        workflowPath='.github/workflows/portable-reuse-proof.yml',
        runId=int(os.environ['GITHUB_RUN_ID']), runAttempt=int(os.environ['GITHUB_RUN_ATTEMPT'])))
    return {'producer': producer, 'workflowEventCommit': os.environ['GITHUB_SHA'],
            'target': target, 'runnerOS': HOSTS[target][0], 'runnerArch': HOSTS[target][1]}


def source_fixture(destination, inputs, spec):
    """Existing detached bundle checkout category, with explicit SDK source pins."""
    source, gitdir = destination / 'source', destination / 'git'
    source.mkdir(); transport.git('init', '--bare', str(gitdir))
    transport.git('--git-dir', str(gitdir), 'config', 'core.bare', 'false')
    transport.git('--git-dir', str(gitdir), 'config', 'core.worktree', str(source))
    transport.git('--git-dir', str(gitdir), 'config', 'core.autocrlf', 'false')
    environment = dict(os.environ, GIT_DIR=str(gitdir), GIT_WORK_TREE=str(source),
        GIT_ALTERNATE_OBJECT_DIRECTORIES=str(Path(transport.git('rev-parse', '--git-path', 'objects')).resolve()))
    environment.pop('GIT_INDEX_FILE', None)
    for row in spec['source']['bundles']:
        bundle = member(inputs, row['relativePath'])
        transport.git('bundle', 'verify', str(bundle), environment=environment)
        if transport.git('bundle', 'list-heads', str(bundle), environment=environment) != row['head'] + ' HEAD':
            raise ValueError('SDK bundle heads differ from the exact selection')
        transport.git('bundle', 'unbundle', str(bundle), environment=environment)
    commit = spec['source']['commit']
    if transport.git('rev-parse', commit + '^{tree}', environment=environment) != spec['source']['tree']:
        raise ValueError('SDK source tree differs')
    transport.git('read-tree', commit, environment=environment)
    transport.git('update-ref', '--no-deref', 'HEAD', commit, environment=environment)
    transport.git('checkout-index', '--all', '--prefix=' + str(source) + '/', environment=environment)
    if (transport.git('diff', 'HEAD', '--', cwd=source, environment=environment) or
            transport.git('for-each-ref', environment=environment)):
        raise ValueError('SDK source must remain the exact detached checkout')
    return {key: environment[key] for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_ALTERNATE_OBJECT_DIRECTORIES')}


def rebase(value, bindings):
    if isinstance(value, dict):
        return {key: rebase(item, bindings) for key, item in value.items()}
    if isinstance(value, list):
        return [rebase(item, bindings) for item in value]
    return bindings.get(value, value) if isinstance(value, str) else value


def selected_json(destination, host, relative):
    relative = require_relative_path(relative, 'Original SDK control')
    if not relative.startswith('inputs/'):
        raise ValueError('Original SDK control must come from the pinned intake')
    rows = [row for row in host['files'] if row['relativePath'] == relative.removeprefix('inputs/')]
    if len(rows) != 1:
        raise ValueError('Original control is not uniquely selected')
    raw = read_regular_file_bytes(member(destination, relative), max_bytes=16 * 1024**2,
                                  reject_symlink_parents=True)
    if len(raw) != rows[0]['bytes'] or sha256_bytes(raw) != rows[0]['sha256']:
        raise ValueError('Original control changed after intake')
    return load_canonical_json_bytes(raw)


def confined_request(value, destination):
    if isinstance(value, dict):
        for item in value.values():
            confined_request(item, destination)
    elif isinstance(value, list):
        for item in value:
            confined_request(item, destination)
    elif isinstance(value, str) and (Path(value).is_absolute() or PureWindowsPath(value).is_absolute()):
        path = Path(value)
        if not path.is_absolute() or not path.is_relative_to(destination):
            raise ValueError('Unbound original path escaped SDK carrier')
        member(destination, path.relative_to(destination).as_posix())


def originals(destination, host):
    result = {}
    for row in host['originals']:
        require_exact_keys(row, {'stage', 'receipt'}, 'Original SDK predecessor')
        stage, receipt_path = member(destination, row['stage']), member(destination, row['receipt'])
        receipt = validate_phase_receipt(selected_json(destination, host, row['receipt']))
        identity = tuple(receipt[k] for k in ('product', 'component', 'phase', 'target'))
        if identity in result or receipt['result'] != 'success':
            raise ValueError('Duplicate or unsuccessful predecessor')
        manifest = selected_json(destination, host, row['stage'] + '/output-manifest.json')
        if (tuple(manifest[k] for k in ('product', 'component', 'phase', 'target', 'productVersion')) !=
                tuple(receipt[k] for k in ('product', 'component', 'phase', 'target', 'productVersion')) or
                manifest['outputs'] != receipt['outputs']):
            raise ValueError('Original manifest/receipt inventory differs')
        result[identity] = {'stage': stage, 'receiptPath': receipt_path, 'receipt': receipt}
    return result


def elect(destination, spec, host, component, target):
    """Live scoped Contract/Runtime capabilities; a serialized plan grants no trust."""
    from products.contract_projection import verify_contract_component_projection
    from products.sdk_runtime_content import verify_native_runtime_projection
    source = destination / 'source'; instance = PhaseInstanceId('sdk', component, 'validation', target)
    original = originals(destination, host)
    dependencies = phase_instance_dependencies(instance)
    predecessors = [original[tuple((i.product, i.component, i.phase, i.target))]['receipt'] for i in dependencies]
    if any(r['buildKey'] not in spec['checkpoint']['retainedKeys'] for r in predecessors):
        raise ValueError('Original predecessor is missing from the retained checkpoint')
    request = read(destination / 'rebased' / ('facade.json' if component == 'sdk-core' else 'compatibility.json'))
    if component == 'sdk-core':
        evidence = request['validationContractEvidence']
        contract = verify_contract_component_projection(Path(evidence['stageRoot']), Path(evidence['phaseReceipt']),
            Path(evidence['attestation']), Path(evidence['attestationSignature']), Path(evidence['publicKey']),
            expected_trust_domain='development', expected_contract_version='0.8.0',
            required_components=required_contract_components(instance))
        native = None
    else:
        contract = verify_contract_component_projection(member(destination, host['paths']['contractStage']),
            Path(request['contractMetadataReceipt']), Path(request['contractAttestation']),
            Path(request['contractAttestationSignature']), Path(request['contractPublicKey']),
            expected_trust_domain='development', expected_contract_version='0.8.0',
            required_components=required_contract_components(instance))
        native = tuple(verify_native_runtime_projection(target=dependency.target,
            runtime_stage_root=member(destination, host['paths']['runtimeStages']),
            phase_receipts={k: Path(v) for k, v in request['variantPhaseReceipts'][dependency.target].items()},
            variant_payload=Path(request['variantBundles'][dependency.target]),
            attestation=Path(request['variantAttestations'][dependency.target]),
            signature=Path(request['variantAttestationSignatures'][dependency.target]),
            public_key=Path(request['variantPublicKeys'][dependency.target]),
            contract_projection=contract, contract_payload=Path(request['contractPayload']),
            required_trust_domain='development') for dependency in native_runtime_validation_dependencies(instance))
    plan = plan_phase(instance, inventory=phase_git_inventory(source, spec['source']['commit'], instance),
        versions=git_product_versions(source, spec['source']['commit']), upstream_receipts=predecessors,
        toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST, flags_digest=NOT_APPLICABLE_FLAGS_DIGEST,
        contract_projection=contract, native_runtime_projections=native)
    if plan != host['plans'][component] or plan['buildKey'] in spec['checkpoint']['retainedKeys']:
        raise ValueError('SDK exact key changed or is already retained; do not rebuild')
    return plan, original


def prepare(selection_path, selection_sha256, target, destination, storage):
    controller = hosted_context(target)
    spec, host, raw = selection(selection_path, selection_sha256, target)
    started = time.monotonic_ns(); destination.mkdir(); storage.mkdir(exist_ok=True)
    write_canonical_json(destination / 'selection.json', spec)
    intake = receive(host['files'], destination / 'inputs', storage)
    environment = source_fixture(destination, destination / 'inputs', spec)
    bindings = {key: str(member(destination, value)) for key, value in host['bindings'].items()}
    (destination / 'rebased').mkdir()
    for name, relative in host['requests'].items():
        rebound = rebase(selected_json(destination, host, 'inputs/' + relative), bindings)
        confined_request(rebound, destination)
        write_canonical_json(destination / 'rebased' / (name + '.json'), rebound)
    with transport.fixture_environment(environment), verification_session():
        plans = {component: elect(destination, spec, host, component, target)[0] for component in host['plans']}
    result = {'schemaVersion': 1, 'passed': True, 'selectionSha256': sha256_bytes(raw),
        'controller': controller, 'environment': environment, 'plans': plans, 'intake': intake,
        'requestBindings': bindings, 'elapsedNs': time.monotonic_ns() - started,
        'originalReceiptBytesRewritten': 0, 'productExecutions': 0, 'phaseAdmitted': False,
        'releaseAdmission': False}
    write_canonical_json(destination / 'preparation.json', result)
    return result


def same_definitions(current, original, names):
    def definitions(raw):
        return {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(raw).body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    left, right = definitions(current), definitions(original)
    if any(name not in left or left[name] != right.get(name) for name in names):
        raise ValueError('Fixed dispatcher helper differs from the elected product source')


def bind_dispatcher(source, component):
    """Bind byte-affecting dispatch helpers; keep reviewed current control readers.

    Current acquisition/admission helpers intentionally come from the actual
    reviewed controller commit. They are not relabeled as old product source.
    """
    whole = ('ci/products/inventory.py', 'ci/products/receipt.py', 'ci/products/registry.py',
             'ci/products/gradle_bootstrap.py', 'ci/products/sdk_inputs.py', 'ci/products/signing_isolation.py')
    functions = {'ci/product_reuse.py': ('_runtime_worker_checkout', '_worker_process_environment',
        '_runtime_worker_environment', '_runtime_worker_command', '_prepare_destination', '_git_value'),
        'ci/products/sdk_package.py': ('_require_capability_output_separate',),
        'ci/products/sdk_validation_inputs.py': ('_request_inventory', '_request_paths'),
        'ci/native_wrappers.py': ('host_classifier',)}
    if component == 'sdk-core':
        whole += ('ci/sdk_facade_validation_phase.py', 'ci/products/sdk_facade_inputs.py',
            'ci/products/sdk_facade_source.py', 'ci/products/sdk_facade_execution_observation.py',
            'ci/products/sdk_facade_validation.py', 'ci/products/sdk_apple_package_source.py',
            'ci/runtime_native_phase.py')
        functions['ci/sdk_phase.py'] = ('route', '_identity')
    else:
        whole += ('ci/products/sdk_native_metadata.py', 'ci/sdk_native_phase.py', 'ci/sdk_cpp_windows_policy.py')
        functions.update({
            'ci/sdk_native_validation_workflow.py': ('_execute_validation', '_private_windows_validation_parent',
                                                    '_windows_rust_fixture_compiler')})
    records = []
    for name in (*whole, *functions):
        current = read_regular_file_bytes(ROOT / name, max_bytes=4 * 1024**2, reject_symlink_parents=True)
        original = read_regular_file_bytes(source / name, max_bytes=4 * 1024**2, reject_symlink_parents=True)
        if name in functions:
            same_definitions(current, original, functions[name])
        elif current != original:
            raise ValueError('Fixed dispatcher dependency differs from selected source: ' + name)
        records.append({'path': name, 'controllerSha256': sha256_bytes(current),
            'productSourceSha256': sha256_bytes(original),
            'equivalence': list(functions[name]) if name in functions else 'whole-file bytes'})
    for name in ('ci/products/restore.py', 'ci/runtime_reference_transport.py'):
        records.append({'path': name, 'controllerSha256': sha256_bytes(read_regular_file_bytes(ROOT / name)),
            'productSourceSha256': sha256_bytes(read_regular_file_bytes(source / name)),
            'equivalence': 'Explicit current controller authentication/reuse reader; no product-command equivalence claim'})
    return records


def native_projection(source_bytes):
    """The existing two-site retained Runtime projection; all verifiers remain."""
    text = source_bytes.decode('utf-8'); module = ast.parse(text)
    matches = [node for node in module.body if isinstance(node, ast.FunctionDef)
               and node.name == '_execute_validation']
    if len(matches) != 1 or hashlib.sha256(ast.get_source_segment(text, matches[0]).encode()).hexdigest() != FUNCTION_SHA:
        raise ValueError('Exact reviewed native execution function required')
    function, = matches
    owned, = [n for n in function.body if isinstance(n, ast.Assign) and len(n.targets) == 1
              and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'owned']
    expected = ast.parse('build / f"imported-native-wrapper-runtime-stages/{tree}"', mode='eval').body
    indexes = [i for i, node in enumerate(owned.value.elts) if ast.dump(node) == ast.dump(expected)]
    if len(owned.value.elts) != 6 or len(indexes) != 1:
        raise ValueError('Only the original Runtime snapshot may become an input')
    del owned.value.elts[indexes[0]]
    command, = [n for n in function.body if isinstance(n, ast.Assign) and len(n.targets) == 1
                and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'command']
    expected_command = ast.parse('command = product_reuse._runtime_worker_command(wrapper, fields, environment, build_directory=".")').body[0]
    if ast.dump(command) != ast.dump(expected_command):
        raise ValueError('Original fixed command construction changed')
    function.body.insert(function.body.index(command) + 1, ast.AugAssign(
        target=ast.Name(id='command', ctx=ast.Store()), op=ast.Add(),
        value=ast.List(elts=[ast.Constant(value=value) for task in EXCLUDED for value in ('-x', task)], ctx=ast.Load())))
    return ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))


def native_execute(workflow, plan, arguments, destination, out, controller):
    source = arguments['repository_root']; tree = arguments['producer']['tree']
    private_bytes = read_regular_file_bytes(source / 'ci/sdk_native_validation_workflow.py')
    # Both the actual dispatcher and private source must have the exact fixed
    # function. Unrelated current-campaign control improvements remain intact.
    projected = native_projection(private_bytes)
    native_projection(read_regular_file_bytes(Path(workflow.__file__)))
    retained = source / 'codex-agent-sdk/build/imported-native-wrapper-runtime-stages' / tree
    if not retained.exists():
        return workflow._execute_validation(plan, **arguments)
    prior = []
    for component in sorted(LANGUAGES - {plan['component']}):
        path = destination / 'results' / component / 'raw-result.json'
        if path.exists():
            raw = read(path)
            if (raw['consumerSuccess'] and raw['controller'] == controller and
                    raw['producer'] == arguments['producer']):
                prior.append(ref(path))
    # A later language failure does not invalidate a complete earlier Runtime
    # snapshot. Authenticate all ten exact originals before routing it; this is
    # integrity evidence only, and the full fixed verifier still runs afterward.
    tick = time.monotonic_ns()
    workflow._runtime_originals(retained, workflow._inventory(retained), arguments['predecessor'])
    retained_integrity_ns = time.monotonic_ns() - tick
    qualification = source / 'build/phase9-sdk-host-validation' / tree / plan['target'] / 'runtime-reuse-qualification'
    if not qualification.exists():
        from product_reuse import _runtime_worker_command, _worker_process_environment
        from products.gradle_bootstrap import require_preprovisioned_gradle
        qualification.mkdir(parents=True)
        environment = _worker_process_environment(source, arguments['producer'],
            qualification / 'diagnostics', arguments['environ'])
        wrapper = source / ('gradlew.bat' if os.name == 'nt' else 'gradlew')
        require_preprovisioned_gradle(read_regular_file_bytes(source / 'gradle/wrapper/gradle-wrapper.properties'), environment)
        fields = {'codexAgent.product': 'sdk', 'codexAgent.component': plan['component'],
            'codexAgent.phase': 'validation', 'codexAgent.target': plan['target'],
            'codexAgent.candidateCommit': arguments['producer']['commit'], 'codexAgent.candidateTree': tree,
            'codexAgent.nativeWrapperRuntimeStageRoot': str(retained),
            'codexAgent.nativeWrapperStagedSdkRoot': str(arguments['staged_sdks']),
            'codexAgent.sdkPackageStageRoot': str(arguments['package']['stage']),
            'codexAgent.sdkPackageReceipt': str(arguments['package']['receiptPath']),
            'codexAgent.sdkCompatibilityRequest': str(arguments['compatibility_request'])}
        for name, key in (('dotnetExecutable', 'dotnet_executable'), ('dartExecutable', 'dart_executable'),
                          ('dartPackageConfig', 'dart_package_config')):
            if arguments[key] is not None:
                fields['codexAgent.' + name] = str(arguments[key])
        command = _runtime_worker_command(wrapper, fields, environment, build_directory='.')
        command += [value for task in EXCLUDED for value in ('-x', task)] + ['--dry-run']
        tick = time.monotonic_ns()
        with (qualification / 'gradle.log').open('xb') as log:
            process = subprocess.run(command, cwd=source, env=environment,
                stdout=log, stderr=subprocess.STDOUT, check=False)
        log_bytes = read_regular_file_bytes(qualification / 'gradle.log', max_bytes=16 * 1024**2)
        title = {'csharp': 'CSharp', 'cpp': 'Cpp', 'python': 'Python', 'dart': 'Dart', 'rust': 'Rust'}[plan['component']]
        required = [':codex-agent-sdk:' + value for value in (
            f'invalidate{title}NativeWrapperInstalledConsumer', f'snapshotImported{title}NativeWrapperSdkPackage',
            f'verifyImported{title}NativeWrapperSdkPackage', f'verify{title}NativeWrapperInstalledConsumer',
            f'verify{title}NativeWrapperCapabilityEvidence', f'write{title}NativeWrapperSdkValidationOutputManifest')]
        required += [':sdkProductPhase', ':ciProductPhase']
        tasks = [line.decode().split() for line in log_bytes.splitlines() if line.startswith(b':')]
        passed = process.returncode == 0 and tasks == [[task, 'SKIPPED'] for task in required]
        write_canonical_json(qualification / 'result.json', {'passed': passed, 'controller': controller,
            'sourceCommit': arguments['producer']['commit'], 'sourceTree': tree, 'target': plan['target'],
            'observedComponent': plan['component'], 'functionSha256': 'sha256:' + FUNCTION_SHA,
            'excludedTasks': list(EXCLUDED), 'requiredTasks': required, 'tasks': tasks, 'command': command,
            'priorRawResults': prior, 'log': ref(qualification / 'gradle.log'),
            'elapsedNs': time.monotonic_ns() - tick, 'productExecutions': 0,
            'runtimeBodiesAuthenticated': False, 'qualificationOnly': True})
        if not passed:
            raise ValueError('Warm retained-Runtime routing qualification failed; preserve its diagnostics')
    proof = read(qualification / 'result.json')
    if (not proof['passed'] or proof['controller'] != controller or
            proof['sourceCommit'] != arguments['producer']['commit'] or proof['sourceTree'] != tree or
            proof['target'] != plan['target'] or proof['functionSha256'] != 'sha256:' + FUNCTION_SHA or
            proof['excludedTasks'] != list(EXCLUDED) or not proof['qualificationOnly']):
        raise ValueError('Exact same-host/source warm routing qualification required')
    selected = dict(arguments, runtime_stages=retained,
        protected_inputs=[*arguments['protected_inputs'], arguments['runtime_stages']])
    namespace = dict(workflow.__dict__)
    exec(compile(projected, str(source / 'ci/sdk_native_validation_workflow.py'), 'exec'), namespace)
    qualification_ref = ref(qualification / 'result.json')
    result = namespace['_execute_validation'](plan, **selected)
    result['runtimeSnapshotReuse'] = {'qualification': qualification_ref,
        'runtimeStagesConsumed': str(retained), 'originalRuntimeStages': str(arguments['runtime_stages']),
        'excludedTaskPaths': list(EXCLUDED), 'originalExecutionFunctionSha256': 'sha256:' + FUNCTION_SHA,
        'retainedOriginalIntegrityNs': retained_integrity_ns,
        'semanticAdmissionPending': True}
    return result


def execute(destination, selection_sha256, target, component, *, dotnet=None, dart=None, dart_config=None):
    controller = hosted_context(target)
    spec, host, _ = selection(destination / 'selection.json', selection_sha256, target)
    prepared = read(destination / 'preparation.json')
    if prepared['controller'] != controller or prepared['selectionSha256'] != selection_sha256 or not prepared['passed']:
        raise ValueError('Exact successful same-run shared SDK intake required')
    expected_environment = dict(GIT_DIR=str(destination / 'git'), GIT_WORK_TREE=str(destination / 'source'),
        GIT_ALTERNATE_OBJECT_DIRECTORIES=str(Path(transport.git('rev-parse', '--git-path', 'objects')).resolve()))
    if prepared['environment'] != expected_environment:
        raise ValueError('Prepared SDK Git environment differs from this exact carrier')
    if component not in host['plans']:
        raise ValueError('SDK component was not elected')
    out = destination / 'results' / component; out.mkdir(parents=True)
    producer = dict(controller['producer'], commit=spec['source']['commit'], tree=spec['source']['tree'])
    started = time.monotonic_ns(); started_wall = time.time_ns(); source = destination / 'source'
    with transport.fixture_environment(prepared['environment']), verification_session():
        tick = time.monotonic_ns()
        plan, original = elect(destination, spec, host, component, target)
        routing_ns = time.monotonic_ns() - tick
        product_environment = dict(os.environ, GH_TOKEN='', GITHUB_TOKEN='')
        if plan != prepared['plans'][component]:
            raise ValueError('Prepared SDK election changed')
        dispatcher_binding = bind_dispatcher(source, component)
        write_canonical_json(out / 'election.json', {'plan': plan, 'controller': controller,
            'fixtureExecution': producer, 'preparation': ref(destination / 'preparation.json'),
            'dispatcherBinding': dispatcher_binding})
        worker = source / 'build/phase9-sdk-host-validation' / producer['tree'] / target / component
        dispatch_started = time.time_ns()
        if component == 'sdk-core':
            import sdk_facade_validation_phase as workflow
            if read_regular_file_bytes(Path(workflow.__file__)) != read_regular_file_bytes(source / 'ci/sdk_facade_validation_phase.py'):
                raise ValueError('Core fixed executor differs from the exact selected source')
            result = workflow.execute(plan, producer=producer, repository_root=source,
                destination=worker, facade_request=destination / 'rebased/facade.json', environ=product_environment)
        else:
            import sdk_native_validation_workflow as workflow
            package = original[('sdk', component, 'package', 'desktop')]
            def predecessor(product, name, phase, original_target):
                return original[(product, name, phase, original_target)]
            arguments = dict(producer=producer, sdk_version='0.8.0',
                repository_root=source, destination=worker,
                runtime_stages=member(destination, host['paths']['runtimeStages']),
                staged_sdks=member(destination, host['paths']['stagedSdks']),
                compatibility_request=destination / 'rebased/compatibility.json', package=package,
                predecessor=predecessor, environ=product_environment, dotnet_executable=dotnet,
                dart_executable=dart, dart_package_config=dart_config,
                protected_inputs=[destination / 'inputs', destination / 'rebased'])
            result = native_execute(workflow, plan, arguments, destination, out, controller)
        # The existing fixed executor returned its original checks. Preserve this
        # before any outer bookkeeping; semantic admission remains a separate gate.
        raw = {'schemaVersion': 1, 'consumerSuccess': True, 'semanticAdmissionPending': True,
            'plan': plan, 'producer': producer, 'controller': controller,
            'result': {k: str(v) if isinstance(v, Path) else v for k, v in result.items()},
            'authenticationAndPlanningNs': routing_ns, 'startedUnixNs': started_wall,
            'fixedExecutorDispatchStartedUnixNs': dispatch_started, 'fixedExecutorReturnedUnixNs': time.time_ns(),
            'dispatchIntervalIncludesWarmRoutingQualification': component != 'sdk-core',
            'elapsedNs': time.monotonic_ns() - started, 'phaseAdmitted': False, 'releaseAdmission': False}
        write_canonical_json(out / 'raw-result.json', raw)
    return raw


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('operation', choices=('prepare', 'execute'))
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--selection-sha256', required=True)
    parser.add_argument('--target', required=True, choices=tuple(HOSTS))
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--storage', type=Path)
    parser.add_argument('--component', choices=tuple(sorted(LANGUAGES | {'sdk-core'})))
    parser.add_argument('--dotnet', type=Path); parser.add_argument('--dart', type=Path)
    parser.add_argument('--dart-package-config', type=Path)
    args = parser.parse_args()
    if args.operation == 'prepare':
        if args.selection is None or args.storage is None or args.component is not None:
            parser.error('Prepare requires a pinned selection and storage, without a component')
        result = prepare(args.selection.resolve(strict=True), args.selection_sha256, args.target,
            args.destination.absolute(), args.storage.absolute())
    else:
        if args.component is None or args.selection is not None or args.storage is not None:
            parser.error('Execute consumes an existing preparation and one elected component')
        result = execute(args.destination.resolve(strict=True), args.selection_sha256, args.target,
            args.component, dotnet=args.dotnet, dart=args.dart, dart_config=args.dart_package_config)
    print(json.dumps({'passed': result.get('passed', result.get('consumerSuccess')),
                      'elapsedNs': result['elapsedNs']}), flush=True)


if __name__ == '__main__':
    main()
