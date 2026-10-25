"""Six missing development adapter host validations, using original packages only.

Prepare shared source/intake once; invoke each component separately so its raw
success survives sibling failure. JVM semantic admission remains a separate
S1253 consumer step after capture. This helper never grants release authority.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'ci')]
from ci.tests import phase9_ios_mutation as mutation
from ci.tests.phase9_ios_package_check import receive
from ci.tests.phase9_runtime_mutation import prepare_windows_source
from products.inventory import (canonical_json_bytes, git_product_versions, load_canonical_json_bytes,
    read_regular_file_bytes, require_relative_path, sha256_bytes, sha256_file, write_canonical_json)
from products.plan import NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST, plan_phase
from products.receipt import validate_phase_receipt, validate_producer, verify_output_manifest_identity, write_phase_receipt
from products.registry import PhaseInstanceId, required_contract_components
from products.selection import phase_git_inventory

FIXTURES = Path(__file__).with_name('fixtures') / 'phase9-adapter-validation'
SELECTION_SHA256 = 'sha256:f88f59e6256b15c33feb90d19458fd458c924728b5b2bbb61a5913ec51ac5640'
LABEL = 'ci:phase9-adapter-artifact-validation'
COMPONENTS = ('jvm', 'node-js', 'node-wasm')
TARGETS = ('windows-x64', 'macos-x64')
TASK = ':codex-agent-runtime-desktop:writeAdapterRuntimeValidationOutputManifest'


def specification():
    raw = read_regular_file_bytes(FIXTURES / 'selection.json', max_bytes=128*1024, reject_symlink_parents=True)
    if sha256_bytes(raw) != SELECTION_SHA256:
        raise ValueError('Adapter selection differs from reviewed original pins')
    spec = load_canonical_json_bytes(raw)
    if (spec['purpose'] != 'phase9-adapter-artifact-validation' or set(spec['hosts']) != set(TARGETS)
            or set(spec['plans']) != {c+':'+t for c in COMPONENTS for t in TARGETS}
            or len(set(spec['retainedKeys'])) != spec['retainedKeyCount']):
        raise ValueError('Adapter selection is not the exact six missing identities')
    for host in spec['hosts'].values():
        paths = [require_relative_path(r['relativePath'], 'Adapter input') for r in host['files']]
        if paths != sorted(set(paths)) or len(paths) != 11:
            raise ValueError('Exact eleven consumed files per host required')
    return spec


def hosted_context(target):
    from native_wrappers import host_classifier
    from products.signing_isolation import require_no_signing_secret
    require_no_signing_secret(os.environ)
    spec = specification(); host = spec['hosts'][target]
    revision = mutation.git('rev-parse', 'HEAD')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    pr = event.get('pull_request', {}); head = pr.get('head', {})
    repository = 'codex-agent-labs/codex-agent'
    if (not __debug__ or os.environ.get('PYTHONOPTIMIZE') or os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('GITHUB_EVENT_NAME') != 'pull_request' or os.environ.get('GITHUB_REPOSITORY') != repository
            or pr.get('number') != 31 or head.get('repo', {}).get('full_name') != repository
            or head.get('repo', {}).get('fork') is not False or head.get('sha') != revision
            or event.get('label', {}).get('name') != LABEL or mutation.git('diff', 'HEAD', '--')):
        raise ValueError('Adapter validation requires exact same-repository labeled PR source')
    if (host_classifier(), os.environ.get('RUNNER_OS'), os.environ.get('RUNNER_ARCH')) != (
            target, host['runnerOS'], host['runnerArch']):
        raise ValueError('Adapter validation requires its actual native host')
    if target == 'macos-x64':
        translated = subprocess.run(['/usr/sbin/sysctl', '-n', 'sysctl.proc_translated'], capture_output=True, text=True)
        if translated.returncode not in (0, 1) or translated.stdout.strip() not in ('', '0'):
            raise ValueError('Real Intel required; no translated host')
    java = Path(os.environ.get('JAVA_HOME', '')) / ('bin/java.exe' if target == 'windows-x64' else 'bin/java')
    node_path = shutil.which('node')
    if not java.is_absolute() or not java.is_file() or node_path is None:
        raise ValueError('Selected Java17 and Node24.18.0 required before intake')
    node = Path(node_path).resolve(strict=True)
    java_version = subprocess.check_output([str(java), '-version'], stderr=subprocess.STDOUT, text=True)
    node_version = subprocess.check_output([str(node), '--version'], text=True).strip()
    node_host = json.loads(subprocess.check_output([str(node), '-p', 'JSON.stringify({platform:process.platform,arch:process.arch})'], text=True))
    if ('version "17.' not in java_version or node_version != 'v24.18.0'
            or node_host != {'platform':'win32' if target=='windows-x64' else 'darwin', 'arch':'x64'}):
        raise ValueError('Actual Java/Node version or host differs')
    producer = validate_producer(dict(commit=revision, tree=mutation.git('rev-parse', 'HEAD^{tree}'),
        repository=repository, event='pull_request', pullRequest=31, workflowPath='.github/workflows/portable-reuse-proof.yml',
        runId=int(os.environ['GITHUB_RUN_ID']), runAttempt=int(os.environ['GITHUB_RUN_ATTEMPT'])))
    return dict(producer=producer, workflowEventCommit=os.environ['GITHUB_SHA'], target=target,
        runnerOS=host['runnerOS'], runnerArch=host['runnerArch'], javaExecutable=str(java), javaVersion=java_version,
        nodeExecutable=str(node), nodeVersion=node_version, nodeHost=node_host)


def verify_inputs(spec, inputs, target, component=None):
    host = spec['hosts'][target]
    rows = [r for r in host['files'] if component is None or r['relativePath'].startswith(
        ('executor/', 'native/', 'receipts/native.json', 'receipts/'+component+'.json', 'adapters/'+component+'/'))]
    for row in rows:
        path = inputs / row['relativePath']
        if path.stat().st_size != row['bytes'] or sha256_file(path, reject_symlink_parents=True) != row['sha256'] or path.is_symlink():
            raise ValueError('Consumed original input changed')
    selected = COMPONENTS if component is None else (component,)
    receipts = {}
    for owner in ('native', *selected):
        receipt = validate_phase_receipt(load_canonical_json_bytes(read_regular_file_bytes(
            inputs / 'receipts' / (owner+'.json'), reject_symlink_parents=True)))
        name = target if owner=='native' else owner
        expected_producer = host['nativeProducer'] if owner=='native' else spec['adapterProducers'][owner]
        if ([receipt[k] for k in ('product','component','phase','target','productVersion','trustDomain','result')]
                != ['runtime',name,'package',name,spec['productVersion'],'development','success']
                or receipt['producer'] != expected_producer):
            raise ValueError('Original package identity or producer changed')
        kind = 'app-server' if owner=='native' else 'validation-runner'
        output, = [r for r in receipt['outputs'] if r['kind']==kind]
        relative = 'native/'+output['relativePath'] if owner=='native' else 'adapters/'+owner+'/runner/'+Path(output['relativePath']).name
        if dict(relativePath=relative,bytes=output['bytes'],sha256=output['sha256']) not in rows:
            raise ValueError('Consumed selected bytes are not the exact original receipt member')
        receipts[owner] = receipt
    if receipts['native']['buildKey'] != host['nativePackageBuildKey']:
        raise ValueError('Original native package election changed')
    return receipts


def elect(spec, inputs, source, target, component, receipts):
    instance = PhaseInstanceId('runtime',component,'validation',target)
    if (required_contract_components(instance) or mutation.git('rev-parse','HEAD',cwd=source) != spec['sourceCommit']
            or mutation.git('rev-parse','HEAD^{tree}',cwd=source) != spec['sourceTree']
            or mutation.git('rev-parse',spec['sourceCommit']+':runtime/build-logic',cwd=source) != spec['buildLogicTree']):
        raise ValueError('Exact private adapter/executor source required')
    plan = plan_phase(instance, inventory=phase_git_inventory(source,spec['sourceCommit'],instance),
        versions=git_product_versions(source,spec['sourceCommit']), upstream_receipts=[receipts[component],receipts['native']],
        toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,flags_digest=NOT_APPLICABLE_FLAGS_DIGEST)
    if plan != spec['plans'][component+':'+target] or plan['buildKey'] in spec['retainedKeys']:
        raise ValueError('Changed or already-retained adapter election')
    return plan


def prepare(destination, storage, target):
    controller = hosted_context(target)  # All source/host checks precede acquisition.
    spec = specification(); tick = time.monotonic_ns()
    prepared, _ = prepare_windows_source(destination, storage)  # Existing two tiny bundles, no Contract/B bodies.
    inputs = destination/'inputs'; source = destination/'source'
    write_canonical_json(destination/'context.json',controller)
    intake = receive(spec['hosts'][target]['files'], inputs, storage)
    write_canonical_json(destination/'intake.json',intake)
    with mutation.fixture_environment(prepared['environment']):
        receipts = verify_inputs(spec,inputs,target)
        plans = {c:elect(spec,inputs,source,target,c,receipts) for c in COMPONENTS}
    result = dict(passed=True,selectionSha256=SELECTION_SHA256,target=target,controller=controller,
        sourcePreparationSha256=sha256_file(destination/'source-preparation.json'),plans=plans,
        intake=intake,elapsedNs=time.monotonic_ns()-tick,productExecutions=0,releaseAdmission=False)
    write_canonical_json(destination/'preparation.json',result)
    return result


def execute(destination, target, component):
    from product_reuse import _runtime_worker_checkout, _runtime_worker_environment
    from runtime_adapter_phase import preflight
    spec = specification(); controller = hosted_context(target)
    raw = read_regular_file_bytes(destination/'preparation.json', reject_symlink_parents=True)
    prepared = load_canonical_json_bytes(raw)
    if (prepared['passed'] is not True or prepared['selectionSha256'] != SELECTION_SHA256
            or prepared['target'] != target or prepared['controller'] != controller):
        raise ValueError('Require this exact successful shared preparation and controller')
    source_record = destination/'source-preparation.json'
    if sha256_file(source_record) != prepared['sourcePreparationSha256']:
        raise ValueError('Prepared source custody changed')
    source_prepared = load_canonical_json_bytes(read_regular_file_bytes(source_record,reject_symlink_parents=True))
    source = destination/'source'
    expected_environment = dict(GIT_DIR=str(destination/'git'),GIT_WORK_TREE=str(source),
        GIT_ALTERNATE_OBJECT_DIRECTORIES=str(Path(mutation.git('rev-parse','--git-path','objects')).resolve()))
    if (source_prepared['environment'] != expected_environment
            or (source_prepared['sourceCommit'],source_prepared['sourceTree']) != (spec['sourceCommit'],spec['sourceTree'])):
        raise ValueError('Exact owned prepared source environment required')
    producer = dict(controller['producer'],commit=spec['sourceCommit'],tree=spec['sourceTree'])
    out = destination/component
    out.mkdir()  # Never overwrite or re-execute a prior component, including a failed one.
    tick = time.monotonic_ns()
    with mutation.fixture_environment(expected_environment):
        _runtime_worker_checkout(source,producer)
        inputs = destination/'inputs'; receipts = verify_inputs(spec,inputs,target,component)
        plan = elect(spec,inputs,source,target,component,receipts)
        if prepared['plans'][component] != plan:
            raise ValueError('Shared preparation plan changed')
        write_canonical_json(out/'plan.json',plan)
        fixture = out/'executor'
        for name in ('settings.gradle','codex-agent-runtime-desktop/build.gradle'):
            path = fixture/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(FIXTURES/name,path)
        fixture_hashes = {name:sha256_file(fixture/name) for name in ('settings.gradle','codex-agent-runtime-desktop/build.gradle')}
        host = spec['hosts'][target]
        runner = next(r for r in host['files'] if r['relativePath'].startswith('adapters/'+component+'/'))
        classifier = next(r for r in host['files'] if r['relativePath'].startswith('native/'))
        context = dict(classpath=[str(inputs/r['relativePath']) for r in host['files'] if r['relativePath'].startswith('executor/')],
            repositoryRoot=str(source),evidenceRoot=str(out/'reports'),stageRoot=str(out/'stage'),component=component,
            target=target,evidenceTarget=host['evidenceTarget'],runnerOs=host['runnerOS'],runnerArch=host['runnerArch'],
            producerCommit=producer['commit'],javaExecutable=controller['javaExecutable'],nodeExecutable=controller['nodeExecutable'],
            runnerArchive=str(inputs/runner['relativePath']),classifierArchive=str(inputs/classifier['relativePath']))
        context_path = out/'executor-context.json';write_canonical_json(context_path,context);context_sha=sha256_file(context_path)
        environment, wrapper = _runtime_worker_environment(source,producer,out/'diagnostics',os.environ)
        if environment.get('CODEX_AGENT_VERIFIED_DEPENDENCY_FETCH'):
            raise ValueError('Only preprovisioned offline execution is allowed')
        if component!='jvm' and preflight(plan,repository_root=source,environ=environment) != {
                'nodeExecutable':controller['nodeExecutable'],'nodeVersion':'24.18.0'}:
            raise ValueError('Selected Node changed after preparation')
        launcher = ([controller['javaExecutable'],'-Xmx64m','-Xms64m','-Dorg.gradle.appname=gradlew','-jar',
            str(source/'gradle/wrapper/gradle-wrapper.jar')] if target=='windows-x64' else [str(wrapper)])
        command = [*launcher,'-p',str(fixture),'--offline','--no-daemon','--no-configuration-cache','--max-workers=1',
            '--console=plain','-Dorg.gradle.jvmargs=-Xmx1536m -Dfile.encoding=UTF-8','-Pphase9.context='+str(context_path),TASK]
        write_canonical_json(out/'election.json',dict(plan=plan,controller=controller,fixtureExecution=producer,
            originalProducers={k:r['producer'] for k,r in receipts.items()},preparationSha256=sha256_bytes(raw),
            command=command,preparationNs=time.monotonic_ns()-tick,retainedKeysSearched=spec['retainedKeyCount']))
        started=time.monotonic_ns()
        with (out/'validation.log').open('xb') as log:
            process=subprocess.run(command,cwd=source,env=dict(environment,GH_TOKEN='',GITHUB_TOKEN=''),stdout=log,stderr=subprocess.STDOUT)
        execution_ns=time.monotonic_ns()-started
        write_canonical_json(out/'execution.json',dict(returnCode=process.returncode,elapsedNs=execution_ns,
            command=command,logSha256=sha256_file(out/'validation.log')))
        if process.returncode:
            raise ValueError('Preserve failed component; later components may run independently')
        _runtime_worker_checkout(source,producer)
        if (verify_inputs(spec,inputs,target,component) != receipts or elect(spec,inputs,source,target,component,receipts) != plan
                or read_regular_file_bytes(destination/'preparation.json') != raw
                or sha256_file(source_record) != prepared['sourcePreparationSha256']
                or sha256_file(context_path) != context_sha
                or any(sha256_file(fixture/name)!=digest or sha256_file(FIXTURES/name)!=digest for name,digest in fixture_hashes.items())
                or (out/'diagnostics/python-bytecode').exists()):
            raise ValueError('Original input/source/fixture lifetime changed; preserve raw evidence only')
        stage=out/'stage';manifest=verify_output_manifest_identity(stage,'runtime',component,'validation',target,spec['productVersion'])
        # The original JVM reader is intentionally not patched or invoked here (S1253).
        # Raw task success and original output receipt are not semantic/phase admission.
        receipt=write_phase_receipt(stage,out,'runtime',component,'validation',target,spec['productVersion'],
            plan['buildKey'],plan['inputs'],producer,'development')
        result=dict(passed=True,buildKey=receipt['buildKey'],receiptSha256=sha256_file(out/'phase-receipt.json'),
            verifier=dict(controller=controller,fixtureExecution=producer),originalProducers={k:r['producer'] for k,r in receipts.items()},
            outputCount=len(manifest['outputs']),outputBytes=sum(r['bytes'] for r in manifest['outputs']),
            executionNs=execution_ns,elapsedNs=time.monotonic_ns()-tick,productBuilds=0,validationExecutions=1,
            semanticAdmissionPending=True,semanticConsumer='Separate reviewed S1253 consumer' if component=='jvm' else 'Existing unchanged Node consumer after capture',
            phaseAdmitted=False,releaseAdmission=False)
        write_canonical_json(out/'result.json',result)
        return result


def main():
    parser=argparse.ArgumentParser(allow_abbrev=False)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true');mode.add_argument('--component',choices=COMPONENTS)
    parser.add_argument('--target',choices=TARGETS,required=True)
    parser.add_argument('destination',type=lambda value:Path(value).resolve())
    parser.add_argument('storage',type=lambda value:Path(value).resolve(),nargs='?')
    args=parser.parse_args()
    if args.prepare:
        if args.storage is None:parser.error('--prepare requires LFS_STORAGE')
        result=prepare(args.destination,args.storage,args.target)
    else:
        if args.storage is not None:parser.error('Component execution cannot acquire inputs')
        result=execute(args.destination,args.target,args.component)
    print(canonical_json_bytes(result).decode(),flush=True)

if __name__=='__main__':
    main()
