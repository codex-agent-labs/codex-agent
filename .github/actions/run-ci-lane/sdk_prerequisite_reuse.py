"""Use unchanged legacy gates, sharing body-authenticated negative discovery.

This is not cached phase admission. Every positive candidate still passes the
original download, receipt, content and downstream original-CI gates.
"""
from argparse import Namespace
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'ci'))
from products.inventory import regular_file_inventory, sha256_file
from sdk_apple_source import _producer_from_receipt


def _legacy_module():
    spec = importlib.util.spec_from_file_location('sdk_native_legacy_lookup', ROOT / 'ci/reuse.py')
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    return legacy


def restore_both(arguments):
    # A private module keeps these observation hooks out of all other callers.
    legacy = _legacy_module()
    original_download = legacy.download_artifact
    original_validate = legacy.validate_receipt
    original_candidates = legacy.candidate_artifacts
    original_promoted = legacy.promoted_artifacts
    negative = {}
    current = None
    production_mode = False
    inventories = arguments.plan.parent / 'inventories' / arguments.lane
    def context():
        return (sha256_file(arguments.plan), regular_file_inventory(inventories, allow_empty=True),
                tuple(arguments.runner), tuple(arguments.toolchain), arguments.lane,
                arguments.api_url, arguments.workflow)
    before = context()

    def identity(artifact):
        return json.dumps({key: artifact.get(key) for key in (
            'id', 'name', 'digest', 'archive_download_url', 'workflow_run', '_promoted',
        )}, sort_keys=True, separators=(',', ':'))

    def download(artifact, token):
        nonlocal current
        current = None
        raw = original_download(artifact, token)  # Mandatory enclosing-archive SHA.
        current = artifact
        return raw

    def validate(*args, **kwargs):
        try:
            return original_validate(*args, **kwargs)
        except (OSError, ValueError, json.JSONDecodeError, KeyError):
            if not production_mode and current is not None:
                try:
                    original_validate(*args, **{**kwargs, 'categories': ('production',)})
                except (OSError, ValueError, json.JSONDecodeError, KeyError) as rejected:
                    # Bind the witness to the authenticated upload and its exact
                    # original receipt/provenance; never retain a positive verdict.
                    try:
                        receipt = legacy.read_json(args[0])
                        producer = _producer_from_receipt(receipt)
                        observed = current.get('workflow_run')
                        if (type(current.get('id')) is int and isinstance(observed, dict)
                                and observed.get('id') == producer['runId']):
                            negative[identity(current)] = {
                                'artifactId': current['id'], 'archiveSha256': current['digest'],
                                'receiptSha256': sha256_file(args[0]), 'producer': producer,
                                'reason': str(rejected),
                            }
                    except (OSError, ValueError, json.JSONDecodeError, KeyError):
                        pass
            raise

    def candidates(*args, **kwargs):
        values = original_candidates(*args, **kwargs)
        return [value for value in values if not production_mode or identity(value) not in negative]

    def promoted(*args, **kwargs):
        values = original_promoted(*args, **kwargs)
        return [value for value in values if not production_mode or identity(value) not in negative]

    legacy.download_artifact = download
    legacy.validate_receipt = validate
    legacy.candidate_artifacts = candidates
    legacy.promoted_artifacts = promoted
    full = legacy.restore(Namespace(**{**vars(arguments), 'mode': 'full'}))
    production_mode = True
    if before != context():
        raise ValueError('SDK prerequisite plan/inventory/profile changed during lookup')
    production = ({'reused': False, 'mode': 'production', 'reason': 'full-reuse-selected'}
                  if full['reused'] else legacy.restore(Namespace(**{
                      **vars(arguments), 'mode': 'production', 'destination': arguments.production_destination,
                  })))
    if before != context():
        raise ValueError('SDK prerequisite plan/inventory/profile changed during lookup')
    return full, production, list(negative.values())


def main():
    legacy = _legacy_module()
    parser = legacy.parser()
    parser.add_argument('--production-destination', type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.lane not in ('ios-native-tests', 'ios-rust-device', 'ios-rust-simulator') or arguments.mode != 'full':
        raise ValueError('Combined lookup requires an SDK Apple prerequisite in full mode')
    full_path, production_path = arguments.destination.resolve(), arguments.production_destination.resolve()
    if full_path == production_path or full_path in production_path.parents or production_path in full_path.parents:
        raise ValueError('Full and production reuse destinations must be separate')
    full, production, witnesses = restore_both(arguments)
    values = {**full, 'production_discovery_complete': True,
              **{'production_' + key: value for key, value in production.items()}}
    legacy.github_output(arguments.github_output, values)
    print(json.dumps({'full': full, 'production': production,
                      'bodyAuthenticatedNegativeWitnesses': witnesses}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
