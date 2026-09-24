"""Test-only release evidence for an exact external native fixture."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from codex_agent._runtime_evidence import _fingerprint


def authorize(library: Path, identity: dict, runtime_version: str) -> bytes:
    evidence = Path(str(library) + ".evidence")
    keys = evidence / "keys"
    keys.mkdir(parents=True)

    def key(name: str) -> tuple[Path, bytes]:
        private = library.parent / name
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private)],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        parts = Path(str(private) + ".pub").read_bytes().split()
        return private, parts[0] + b" " + parts[1] + b"\n"

    def write(path: Path, value: dict) -> None:
        path.write_bytes((json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode())

    def sign(path: Path, private: Path, namespace: str, destination: Path) -> None:
        subprocess.run(["ssh-keygen", "-Y", "sign", "-f", str(private), "-n", namespace, str(path)],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        Path(str(path) + ".sig").replace(destination)

    def digest(raw: bytes) -> str:
        return "sha256:" + hashlib.sha256(raw).hexdigest()

    root_private, root_public = key("root-key")
    release_private, release_public = key("release-key")
    (keys / "release.pub").write_bytes(release_public)
    fingerprint = _fingerprint(release_public)
    keyring = evidence / "release-keyring.json"
    write(keyring, {
        "schemaVersion": 1, "namespace": "codex-agent-product-v1", "algorithm": "ssh-ed25519",
        "trustDomain": "release", "activeKey": {"keyId": "release", "fingerprint": fingerprint},
        "retiredKeys": [],
    })
    delegation = evidence / "root-delegation.json"
    write(delegation, {
        "schemaVersion": 1, "kind": "sdk-runtime-release-keyring-delegation",
        "scope": "desktop-runtime-library", "rootFingerprint": _fingerprint(root_public),
        "keyringSha256": digest(keyring.read_bytes()),
    })
    sign(delegation, root_private, "codex-agent-sdk-runtime-root-v1", evidence / "root-delegation.sig")
    claim = evidence / "runtime-library-authorization.json"
    write(claim, {
        "schemaVersion": 1, "kind": "desktop-runtime-library-authorization",
        "runtimeVersion": runtime_version, "runtimeIdentity": identity,
        "runtimeLibrarySha256": digest(library.read_bytes()),
        **{field: digest(field.encode()) for field in (
            "variantBundleSha256", "variantManifestSha256", "aggregateManifestSha256",
            "variantAttestationSha256", "aggregateAttestationSha256",
        )},
        "signing": {"algorithm": "ssh-ed25519", "namespace": "codex-agent-product-v1",
                    "trustDomain": "release", "keyId": "release", "fingerprint": fingerprint},
    })
    sign(claim, release_private, "codex-agent-product-v1",
         evidence / "runtime-library-authorization.sig")
    return root_public
