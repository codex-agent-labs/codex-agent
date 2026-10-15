"""Pure native workflow routing, not state authentication or product admission.

Ready plans must come from the existing authenticated replay. Needs are workflow
job results; consumers must still recapture and authenticate returned locators.
This final gate never schedules or suppresses sibling-failure collection.
"""

from pathlib import Path
import re
import json
import os
import tempfile
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.inventory import (
    require_array, require_exact_keys, require_integer, require_object,
    require_sha256, require_string,
)
from products.receipt import compute_build_key, validate_receipt_inputs
from products.registry import NATIVE_BINDINGS, PHASE_INSTANCE_IDS, PhaseInstanceId
from products.inventory import canonical_json_bytes
from products.receipt import validate_producer
from reuse import github_output
from products.restore import PHASE_PLAN_KEYS
from sdk_native_prepare import validate_anchor


_IDENTITY = ("product", "component", "phase", "target")
_LOCATOR = ("artifact_id", "artifact_digest", "state_wave", "sdk_state_wave")
_STAGES = {
    # Wave 19 is an additive pre-package compatibility slot; numbers are upload identities, not chronology.
    "csharp-binary": ("sdk-javascript-metadata-result", "sdk-csharp-binary-plan", "sdk-csharp-binary", "sdk-collect-19", "19"),
    "package": ("sdk-csharp-binary-result", "sdk-native-plan", "sdk-native-workers", "sdk-collect-4", "4"),
    "ios-package": ("sdk-native-packages", "sdk-ios-package-plan", "sdk-ios-package", "sdk-collect-5", "5"),
    "javascript-metadata": ("sdk-javascript", "sdk-javascript-metadata-plan", "sdk-javascript-metadata", "sdk-collect-6", "6"),
    "validation": ("sdk-ios-packages", "sdk-native-validation-plan", "sdk-native-validation", "sdk-collect-7", "7"),
    "metadata": ("sdk-native-validation-result", "sdk-native-metadata-plan", "sdk-native-metadata", "sdk-collect-8", "8"),
    "ios-validation": ("sdk-native-result", "sdk-native-result", "sdk-ios-validation", "sdk-collect-9", "9"),
    "ios-metadata": ("sdk-ios-validation-result", "sdk-ios-metadata-plan", "sdk-ios-metadata", "sdk-collect-10", "10"),
    "core-binary": ("sdk-ios-metadata-result", "sdk-core-binary-plan", "sdk-core-binary", "sdk-collect-11", "11"),
    "core-package": ("sdk-core-binary-wave", "sdk-core-package-plan", "sdk-core-package", "sdk-collect-12", "12"),
    "core-validation": ("sdk-core-package-wave", "sdk-core-validation-plan", "sdk-core-validation", "sdk-collect-13", "13"),
    "core-metadata": ("sdk-core-validation-wave", "sdk-core-metadata-plan", "sdk-core-metadata", "sdk-collect-14", "14"),
    "android-binary": ("sdk-core-metadata-wave", "sdk-android-binary-plan", "sdk-android-binary", "sdk-collect-15", "15"),
    "android-package": ("sdk-android-binary-result", "sdk-android-package-plan", "sdk-android-package", "sdk-collect-16", "16"),
    "android-validation": ("sdk-android-package-result", "sdk-android-validation-plan", "sdk-android-validation", "sdk-collect-17", "17"),
    "android-metadata": ("sdk-android-validation-result", "sdk-android-metadata-plan", "sdk-android-metadata", "sdk-collect-18", "18"),
}

# These jobs ordinarily just forward sdk-plan when no earlier SDK family is ready.
_IOS_PREFIX_RESULTS = (
    "sdk-javascript", "sdk-javascript-metadata-result", "sdk-csharp-binary-result",
    "sdk-native-packages", "sdk-ios-packages", "sdk-native-validation-result",
)


def select_ios_ready_prefix(needs):
    """Collapse only an elected no-work prefix; the V worker still authenticates it."""
    planned = _job(needs, "sdk-plan")
    if planned["outputs"].get("ios_validation_direct") != "true":
        return select_native_state(needs, stage="metadata")
    if planned["result"] != "success" or planned["outputs"].get("sdk_workers_required") != "false":
        raise ValueError("Direct iOS validation requires a successful no-work SDK prefix election")
    for name in (*_IOS_PREFIX_RESULTS, "sdk-native-metadata-plan", "sdk-native-metadata", "sdk-collect-8"):
        job = _job(needs, name)
        if job["result"] != "skipped" or any(_locator(job["outputs"]).values()):
            raise ValueError("Direct iOS validation cannot bypass an executed prefix job: " + name)
    state = forward_routing(planned["outputs"], planned["outputs"])
    if not state["artifact_id"] or not state.get("routing"):
        raise ValueError("Direct iOS validation requires the unchanged planned state and routing")
    return state


def select_preparation_anchor(ready_plans):
    """Choose one unchanged native diagnostic anchor from verified ready plans."""
    seen, candidates = set(), []
    for plan in require_array(ready_plans, "Native continuation ready plans"):
        require_exact_keys(plan, PHASE_PLAN_KEYS, "Native continuation ready plan")
        if require_integer(plan["schemaVersion"], "Ready plan schema", 1) != 1:
            raise ValueError("Unsupported ready plan schema")
        identity = PhaseInstanceId(*(require_string(plan[name], "Ready plan " + name) for name in _IDENTITY))
        if identity not in PHASE_INSTANCE_IDS or identity in seen:
            raise ValueError("Unknown or duplicate ready plan identity")
        seen.add(identity)
        key = require_sha256(plan["buildKey"], "Ready plan build key")
        validate_receipt_inputs(plan["inputs"])
        if identity.product == "sdk" and identity.component in NATIVE_BINDINGS:
            validate_anchor(plan)
            candidates.append(plan)
        elif compute_build_key(**{name: plan[name] for name in (*_IDENTITY, "inputs")}) != key:
            raise ValueError("Ready plan identity or inputs differ from its build key")
    if not candidates:
        return dict(preparation_required=False, component="", phase="", target="", build_key="")
    priority = {"package": 0, "validation": 1, "metadata": 2}
    plan = min(candidates, key=lambda row: (priority[row["phase"]], *(row[name] for name in _IDENTITY)))
    return dict(preparation_required=True, component=plan["component"], phase=plan["phase"],
                target=plan["target"], build_key=plan["buildKey"])


def _job(needs, name):
    job = require_object(needs.get(name), "Native continuation job " + name)
    if job.get("result") not in ("success", "failure", "cancelled", "skipped"):
        raise ValueError("Native continuation job is missing or still running: " + name)
    require_object(job.get("outputs"), "Native continuation job outputs " + name)
    return job


def _locator(outputs):
    result = {name: outputs.get(name, "") for name in _LOCATOR}
    if any(type(value) is not str for value in result.values()):
        raise ValueError("Native state locator fields must be strings")
    if not any(result.values()):
        return result
    if (not re.fullmatch(r"[1-9][0-9]*", result["artifact_id"])
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", result["artifact_digest"])
            or result["state_wave"] not in ("0", "1", "2", "3", "4", "5")
            or result["sdk_state_wave"] not in ("", *(str(wave) for wave in range(1, 20)))
            or (result["sdk_state_wave"] and result["state_wave"] != "0")):
        raise ValueError("Invalid native state artifact identity or wave")
    return result


def forward_routing(locator, outputs):
    """Forward a job hint only with its exact immutable state locator."""
    state = _locator(locator)
    routing = outputs.get("routing")
    if routing:
        import json
        if type(routing) is not str or len(routing.encode()) > 128 * 1024 or "\n" in routing or "\r" in routing:
            raise ValueError("Invalid routing control")
        value = json.loads(routing)
        if type(value) is not dict or value.get("locator") != state:
            raise ValueError("Routing control differs from the selected state")
        state["routing"] = routing
    return state


def select_native_state(needs, *, stage):
    """Return a collected locator or the exact unchanged parent after final gates.

    Preparation is independent of package misses. Its original locator tuple is
    forwarded separately by the workflow and is never reconstructed here.
    """
    if type(stage) is not str or stage not in _STAGES:
        raise ValueError("Unknown native continuation stage")
    require_object(needs, "Native continuation needs")
    parent_name, election_name, workers_name, collector_name, wave = _STAGES[stage]
    parent, election, workers, collector = (_job(needs, name) for name in
        (parent_name, election_name, workers_name, collector_name))
    if parent["result"] != "success":
        raise ValueError("Native predecessor gate failed")
    state = _locator(parent["outputs"])
    if stage == "ios-validation":
        planned = _job(needs, "plan")
        native = _job(needs, "sdk-ios-validation-native")
        direct = planned["outputs"].get("native_ios_worker_ready", "")
        if direct not in ("", "true", "false"):
            raise ValueError("Native iOS worker election is malformed")
        if direct == "true":
            outputs = planned["outputs"]
            original = _locator(dict(artifact_id=outputs.get("native_resume_artifact_id", ""),
                artifact_digest=outputs.get("native_resume_artifact_digest", ""),
                state_wave="0", sdk_state_wave=""))
            if (planned["result"] != "success" or workers["result"] != "skipped"
                    or not original["artifact_id"] or state != original
                    or election["outputs"].get("sdk_workers_required") != "true"
                    or not outputs.get("native_ios_matrix")
                    or election["outputs"].get("sdk_matrix") != outputs["native_ios_matrix"]):
                raise ValueError("Native iOS worker differs from its exclusive planned election")
            workers = native
        elif native["result"] != "skipped":
            raise ValueError("Unexpected native iOS worker without its planned election")
    preparation = _job(needs, "sdk-native-prepare") if stage == "package" else None
    apple_signing = tuple(_job(needs, name) for name in
        ("sdk-apple-signing-prepare", "sdk-apple-validation-attestation")) if stage == "ios-validation" else ()
    if not state["artifact_id"]:
        # The iOS prefix gate and its election share one successful job; an absent
        # parent must still skip its route step and every downstream operation.
        if parent_name == election_name and election["outputs"].get("sdk_workers_required", "") != "":
            raise ValueError("Unexpected native election without parent state")
        if any(job["result"] != "skipped" for job in
               (*((election,) if parent_name != election_name else ()), workers, collector,
                *apple_signing, *((preparation,) if preparation is not None else ()))):
            raise ValueError("Unexpected native jobs without parent state")
        return state
    if election["result"] != "success":
        raise ValueError("Native election did not complete")
    required = election["outputs"].get("sdk_workers_required")
    if required not in ("true", "false"):
        raise ValueError("Native worker election is incomplete")
    if preparation is not None:
        prepare = election["outputs"].get("preparation_required")
        if prepare not in ("true", "false") or (required == "true" and prepare != "true"):
            raise ValueError("Native preparation election is incomplete or inconsistent")
        if preparation["result"] != ("success" if prepare == "true" else "skipped"):
            raise ValueError("Native preparation did not match its election")
    expected = "success" if required == "true" else "skipped"
    signing_expected = expected
    if apple_signing and required == "true" and "sdk-ios-validation-outcome" in needs:
        outcome = _job(needs, "sdk-ios-validation-outcome")
        signing = outcome["outputs"].get("signing_required")
        if (outcome["result"] != "success" or signing not in ("true", "false")
                or outcome["outputs"].get("all_failed") != "false"):
            raise ValueError("Apple signing outcome failed or is incomplete")
        signing_expected = "success" if signing == "true" else "skipped"
    if any(job["result"] != signing_expected for job in apple_signing):
        raise ValueError("Apple preparation or attestation failed or differed from election")
    if workers["result"] != expected or collector["result"] != expected:
        raise ValueError("Native workers or collection failed or differed from election")
    if required == "false":
        return forward_routing(state, parent["outputs"])
    if collector["outputs"].get("wave_failed") != "false":
        raise ValueError("Native collection retained failed or incomplete siblings")
    return forward_routing({**collector["outputs"], "state_wave": "0", "sdk_state_wave": wave}, collector["outputs"])


def emit(plan, result, ready_plans, sources, request, root, environment, workflow_sha, output, *, runtime_wave=None,
         completed_frozen=None):
    """Called inside an authenticated transition, before its successful job gate."""
    import product_reuse as products
    from runtime_workflow import continuation_from_inspection
    ready = list(ready_plans)
    sdk_ready = [row for row in ready if row['product'] == 'sdk']
    runtime = products._runtime_matrix_from_plans(ready)
    if runtime_wave is not None:
        if type(runtime_wave) is not int or runtime_wave not in range(1, 6):
            raise ValueError('Runtime routing wave must be one through five')
        if runtime_wave == 4 and runtime['include']:
            raise ValueError('Runtime workers remain after four dependency-ordered waves')
    github_output(output, {
        'runtime_matrix': canonical_json_bytes(runtime).decode().strip(),
        'runtime_workers_required': bool(runtime['include']),
        'supervisor_key': next((row['buildKey'] for row in runtime['include']
            if (row['component'], row['phase'], row['target']) == ('linux-arm64', 'binary', 'linux-arm64')), ''),
    })
    continuation = None
    aggregate = PhaseInstanceId('runtime', 'runtime-aggregate', 'metadata', 'aggregate')
    phases = {products._identity(row): row for row in result['phases']}
    if (aggregate not in phases or all(phases.get(identity, {}).get('state') in {'retained', 'reused'}
            for identity in products._dependency_closure((aggregate,)) if identity != aggregate)):
        selection = products._sdk_input_selection_from_transition(plan, result, sources,
            request['versions'], request, root, completed_frozen=completed_frozen)
        inspected = {'result': result, 'readyPlans': ready, 'sdkInputSelection': selection,
            products._AGGREGATE_REQUEST_KEY: request.get(products._AGGREGATE_REQUEST_KEY, [])}
        with tempfile.TemporaryDirectory(prefix='product-routing-') as temporary:
            path = Path(temporary) / 'outputs'
            continuation_from_inspection(inspected, path, if_selected=True,
                **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}))
            continuation = dict(line.split('=', 1) for line in path.read_text().splitlines())
    if runtime_wave == 5:
        if continuation is None or continuation['aggregate_state'] != 'completed':
            raise ValueError('Runtime aggregate payload remains incomplete after collection')
        github_output(output, continuation)
    decisions = dict(schemaVersion=1, producer=products._consumer(plan, environment)['producer'],
        workflowSha=workflow_sha, ready=[{key: row[key] for key in
            ('product', 'component', 'phase', 'target', 'buildKey')} for row in sdk_ready],
        preparation=select_preparation_anchor([row for row in sdk_ready if row["phase"] != "binary"]), runtime=continuation)
    github_output(output, {'routing_decisions': canonical_json_bytes(decisions).decode().strip()})


def context(environment):
    return {key: environment[name] for key, name in (
        ('commit', 'VALIDATION_COMMIT'), ('tree', 'VALIDATION_TREE'),
        ('workflowSha', 'TRUSTED_WORKFLOW_SHA'), ('planId', 'PLAN_ID'),
        ('repository', 'GITHUB_REPOSITORY'), ('runId', 'GITHUB_RUN_ID'),
        ('runAttempt', 'GITHUB_RUN_ATTEMPT'))}


def _decisions(value, expected):
    require_exact_keys(value, {'schemaVersion', 'producer', 'workflowSha', 'ready', 'preparation', 'runtime'},
                       'Routing decisions')
    producer = validate_producer(value['producer'])
    if (type(value['schemaVersion']) is not int or value['schemaVersion'] != 1 or value['workflowSha'] != expected['workflowSha']
            or any(str(producer[key]) != str(expected[key]) for key in
                   ('repository', 'commit', 'tree', 'runId', 'runAttempt'))):
        raise ValueError('Routing decisions differ from current plan/run/policy')
    if type(value['ready']) is not list or len(value['ready']) > len(PHASE_INSTANCE_IDS):
        raise ValueError('Routing frontier is oversized or malformed')
    seen = set()
    for row in value['ready']:
        require_exact_keys(row, {'product', 'component', 'phase', 'target', 'buildKey'}, 'Routing phase')
        identity = PhaseInstanceId(*(row[key] for key in ('product', 'component', 'phase', 'target')))
        if identity not in PHASE_INSTANCE_IDS or identity.product != 'sdk' or identity in seen:
            raise ValueError('Unknown or duplicate SDK routing identity')
        seen.add(identity)
        require_sha256(row['buildKey'], 'Routing elected key')
    preparation = require_exact_keys(value['preparation'],
        {'preparation_required', 'component', 'phase', 'target', 'build_key'}, 'Routing preparation')
    from products.registry import NATIVE_BINDINGS
    candidates = [row for row in value['ready'] if row['component'] in NATIVE_BINDINGS and row['phase'] != 'binary']
    if type(preparation['preparation_required']) is not bool:
        raise ValueError('Routing preparation must be boolean')
    if candidates:
        priority = {'package': 0, 'validation': 1, 'metadata': 2}
        candidate = min(candidates, key=lambda row: (priority[row['phase']],
            *(row[key] for key in ('product', 'component', 'phase', 'target'))))
        expected_preparation = dict(preparation_required=True, component=candidate['component'],
            phase=candidate['phase'], target=candidate['target'], build_key=candidate['buildKey'])
    else:
        expected_preparation = dict(preparation_required=False, component='', phase='', target='', build_key='')
    if preparation != expected_preparation:
        raise ValueError('Routing preparation differs from the elected frontier')
    runtime_keys = {'sdk_handoff_required', 'sdk_input_selection', 'native_attestation_matrix',
        'native_receipt_sha256s', 'aggregate_state', 'aggregate_key', 'aggregate_receipt_sha256',
        'aggregate_required', 'aggregate_payload_complete'}
    if value['runtime'] is not None and (type(value['runtime']) is not dict or
            not set(value['runtime']) <= runtime_keys or
            any(type(member) is not str or '\n' in member or '\r' in member for member in value['runtime'].values())):
        raise ValueError('Runtime routing outputs are malformed')
    return value


def bind(decisions, locator, expected):
    value = {'schemaVersion': 1, 'planId': expected['planId'],
             'locator': _locator(locator), 'decisions': _decisions(decisions, expected)}
    if not value['locator']['artifact_id']:
        raise ValueError('Routing requires its completed state upload')
    if len(canonical_json_bytes(value)) > 128 * 1024:
        raise ValueError('Routing control exceeds its bound')
    return value


def select(value, locator, expected, *, family):
    from sdk_workflow import _matrix_from_plans
    require_exact_keys(value, {'schemaVersion', 'planId', 'locator', 'decisions'}, 'Bound routing')
    if (type(value['schemaVersion']) is not int or value['schemaVersion'] != 1 or value['planId'] != expected['planId']
            or value['locator'] != _locator(locator) or not value['locator']['artifact_id']):
        raise ValueError('Routing plan or immutable state locator changed')
    decisions = _decisions(value['decisions'], expected)
    if family == 'runtime':
        if type(decisions['runtime']) is not dict:
            raise ValueError('Runtime transition still needs authenticated continuation')
        return decisions['runtime']
    matrix = _matrix_from_plans(decisions['ready'], ios_binary=family == 'ios-binary',
        family=None if family in {'javascript', 'ios-binary'} else family)
    result = {'sdk_matrix': canonical_json_bytes(matrix).decode().strip(),
              'sdk_workers_required': bool(matrix['include'])}
    if family == 'javascript':
        # Reuse exactly the ordinary family elections; no new phase-completion authority.
        preceding = ('javascript-metadata', 'csharp-binary', 'native-package',
                     'ios-package', 'native-validation', 'native-metadata')
        result['ios_validation_direct'] = (not matrix['include']
            and not decisions['preparation']['preparation_required']
            and not any(_matrix_from_plans(decisions['ready'], family=name)['include'] for name in preceding)
            and bool(_matrix_from_plans(decisions['ready'], family='ios-validation')['include']))
    if family == 'native-package':
        result.update({'native_preparation_' + name.removeprefix('preparation_'): member
                       for name, member in decisions['preparation'].items()})
    return result


def native_sdk_resume(decisions, locator, expected, *, sdk_recovery_only,
                      runtime_workers_required, supervisor_key):
    """Forward a completed native prefix; consumers still authenticate its upload."""
    if type(sdk_recovery_only) is not bool or runtime_workers_required not in ('true', 'false'):
        raise ValueError('Native SDK resume requires exact recovery and Runtime election flags')
    bound = bind(decisions, locator, expected)
    runtime = bound['decisions']['runtime']
    direct = (sdk_recovery_only and runtime_workers_required == 'false' and supervisor_key == ''
        and bound['locator']['state_wave'] == '0' and bound['locator']['sdk_state_wave'] == ''
        and isinstance(runtime, dict)
        and runtime.get('aggregate_state') == 'completed'
        and runtime.get('aggregate_required') == 'false'
        and runtime.get('aggregate_payload_complete') == 'true'
        and runtime.get('sdk_handoff_required') == 'true'
        and select(bound, locator, expected, family='javascript')['ios_validation_direct']
        and not select(bound, locator, expected, family='ios-binary')['sdk_workers_required'])
    if direct:
        source = json.loads(runtime.get('sdk_input_selection', '{}'))
        direct = isinstance(source, dict) and source.get('source') == 'current-runtime'
    if not direct:
        return {'native_sdk_direct': False}
    require_sha256(runtime.get('aggregate_key'), 'Completed native aggregate key')
    require_sha256(runtime.get('aggregate_receipt_sha256'), 'Completed native aggregate receipt')
    return {'native_sdk_direct': True,
        'sdk_matrix': select(bound, locator, expected, family='ios-validation')['sdk_matrix'],
        **{name: runtime[name] for name in (
        'sdk_input_selection', 'aggregate_key', 'aggregate_receipt_sha256',
        'aggregate_payload_complete')}}


def main():
    """Inputs are fixed workflow expressions, never artifacts or user dispatch JSON."""
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('bind', 'select'))
    parser.add_argument('--family', default='javascript')
    arguments = parser.parse_args()
    expected = context(os.environ)
    locator = (json.loads(os.environ['ROUTING_LOCATOR']) if 'ROUTING_LOCATOR' in os.environ else
        {key: os.environ[name] for key, name in (('artifact_id', 'ARTIFACT_ID'),
            ('artifact_digest', 'ARTIFACT_SHA256'), ('state_wave', 'STATE_WAVE'),
            ('sdk_state_wave', 'SDK_STATE_WAVE'))})
    raw = os.environ['ROUTING']
    if len(raw.encode()) > 128 * 1024:
        raise ValueError('Routing control exceeds its bound')
    value = json.loads(raw)
    outputs = ({'routing': canonical_json_bytes(bind(value, locator, expected)).decode().strip()}
               if arguments.command == 'bind' else select(value, locator, expected, family=arguments.family))
    github_output(Path(os.environ['GITHUB_OUTPUT']), outputs)


if __name__ == '__main__':
    main()
