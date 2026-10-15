"""Prepare the selected offline Core consumer's tools; never produce a phase."""

import argparse
import os
from pathlib import Path

from .products.gradle_bootstrap import require_preprovisioned_gradle, seed_sdk_maven_binary_dependencies
from .products.inventory import git_regular_blob_bytes
from .products.sdk_compatibility import load_sdk_compatibility_request
from .products.sdk_facade_inputs import _request
from .products.signing_isolation import require_no_signing_secret


def prepare(request, *, repository, revision, target, destination, native_archive, environment):
    require_no_signing_secret(environment)
    root = Path(repository).resolve(strict=True)
    value, _ = _request(Path(request))
    if value['target'] != target or Path(value['repository']) != root:
        raise ValueError('Dependency preparation differs from the elected Core consumer')
    compatibility = load_sdk_compatibility_request(Path(value['compatibilityRequest']))
    properties = {'codexAgent.component': 'sdk-core',
                  'codexAgent.contractVersion': value['contractVersion']}
    for field, key in (
        ('contract_payload', 'contractPayload'), ('contract_metadata_receipt', 'contractMetadataReceipt'),
        ('contract_attestation', 'contractAttestation'), ('contract_attestation_signature', 'contractAttestationSignature'),
        ('contract_public_key', 'contractPublicKey'),
    ):
        properties['codexAgent.' + key] = str(compatibility[field])
    environment = dict(environment)
    java_home = Path(environment['JAVA_HOME'])
    if not java_home.is_absolute():
        raise ValueError('Core dependency preparation requires absolute JAVA_HOME')
    environment['JAVA_HOME'] = str(java_home.resolve(strict=True))
    require_preprovisioned_gradle(git_regular_blob_bytes(root, revision,
        'gradle/wrapper/gradle-wrapper.properties', max_bytes=64 * 1024), environment)
    seed_sdk_maven_binary_dependencies(root, revision, root / 'gradlew', environment,
        Path(destination), properties, consumer_target=target, native_archive=native_archive)
    require_no_signing_secret(environment)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('request', 'repository', 'revision', 'target', 'destination'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--native-archive', type=Path)
    arguments = vars(parser.parse_args(argv))
    prepare(**arguments, environment=os.environ)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
