"""Offline signed external Runtime fixture for the C++ loader."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def system_ssh_keygen() -> str:
    if sys.platform != "win32":
        return "/usr/bin/ssh-keygen"
    import ctypes

    directory = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetSystemDirectoryW(directory, len(directory))
    if not 0 < length < len(directory):
        raise RuntimeError("Windows system OpenSSH directory is unavailable")
    return str(Path(directory.value) / "OpenSSH" / "ssh-keygen.exe")


SSH = system_ssh_keygen()


def canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def key(root: Path, name: str) -> tuple[Path, bytes]:
    private = root / name
    subprocess.run([SSH, "-q", "-t", "ed25519", "-N", "", "-f", str(private)], check=True)
    parts = Path(f"{private}.pub").read_bytes().split()
    public = parts[0] + b" " + parts[1] + b"\n"
    Path(f"{private}.pub").write_bytes(public)
    return private, public


def fingerprint(public: bytes) -> str:
    import base64
    return digest(base64.b64decode(public.split()[1], validate=True))


def sign(path: Path, private: Path, namespace: str, destination: Path) -> None:
    subprocess.run([SSH, "-Y", "sign", "-f", str(private), "-n", namespace, str(path)],
                   check=True, capture_output=True)
    Path(f"{path}.sig").replace(destination)


def run(executable: Path, default: Path, compatibility: Path, mode: str,
        library: Path, public: Path) -> None:
    result = subprocess.run([str(executable), str(default), str(compatibility), mode,
                             str(library), str(public)], capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(f"{mode}: {result.stderr}")


def main() -> None:
    executable, default, compatibility, external = map(Path, sys.argv[1:5])
    target = sys.argv[5]
    with tempfile.TemporaryDirectory(prefix="codex-agent-cpp-signed-") as temporary:
        root = Path(temporary).resolve()
        library = root / external.name
        shutil.copyfile(external, library)
        evidence = Path(f"{library}.evidence")
        (evidence / "keys").mkdir(parents=True)
        root_private, root_public = key(root, "root")
        signer_private, signer_public = key(root, "signer")
        wrong_private, wrong_public = key(root, "wrong")
        del wrong_private
        (evidence / "keys/release.pub").write_bytes(signer_public)
        keyring = canonical({"schemaVersion": 1, "namespace": "codex-agent-product-v1",
                             "algorithm": "ssh-ed25519", "trustDomain": "release",
                             "activeKey": {"keyId": "release", "fingerprint": fingerprint(signer_public)},
                             "retiredKeys": []})
        (evidence / "release-keyring.json").write_bytes(keyring)
        delegation = evidence / "root-delegation.json"
        delegation.write_bytes(canonical({"schemaVersion": 1,
            "kind": "sdk-runtime-release-keyring-delegation", "scope": "desktop-runtime-library",
            "rootFingerprint": fingerprint(root_public), "keyringSha256": digest(keyring)}))
        sign(delegation, root_private, "codex-agent-sdk-runtime-root-v1",
             evidence / "root-delegation.sig")
        identity = {"schemaVersion": 1, "componentId": "sha256:" + "3" * 64,
                    "runtimeCompatibilityVersion": "0.8.5", "contractDigest": "sha256:" + "a" * 64,
                    "contractComponentDigest": "sha256:" + "f" * 64,
                    "cAbiVersion": "1.13.0", "target": target, "appServerVersion": "0.149.0",
                    "buildInputDigest": "sha256:" + "e" * 64}
        claim = evidence / "runtime-library-authorization.json"
        claim.write_bytes(canonical({"schemaVersion": 1, "kind": "desktop-runtime-library-authorization",
            "runtimeVersion": "0.8.5", "runtimeIdentity": identity,
            "runtimeLibrarySha256": digest(library.read_bytes()),
            "variantBundleSha256": digest(b"bundle"),
            "variantManifestSha256": digest(b"manifest"),
            "aggregateManifestSha256": digest(b"aggregate"),
            "variantAttestationSha256": digest(b"variant-attestation"),
            "aggregateAttestationSha256": digest(b"aggregate-attestation"),
            "signing": {"algorithm": "ssh-ed25519", "namespace": "codex-agent-product-v1",
                        "trustDomain": "release", "keyId": "release",
                        "fingerprint": fingerprint(signer_public)}}))
        signature = evidence / "runtime-library-authorization.sig"
        sign(claim, signer_private, "codex-agent-product-v1", signature)
        root_file = root / "root.pub"
        root_file.write_bytes(root_public)
        wrong_file = root / "wrong.pub"
        wrong_file.write_bytes(wrong_public)
        run(executable, default, compatibility, "signed-wrong-root", library, wrong_file)
        run(executable, default, compatibility, "signed-external", library, root_file)
        keyring_file = evidence / "release-keyring.json"
        keyring_file.write_bytes(keyring + b" " * (1024 * 1024))
        run(executable, default, compatibility, "signed-oversized-evidence", library, root_file)
        keyring_file.write_bytes(keyring)
        original = signature.read_bytes()
        changed = bytearray(original)
        offset = len(b"-----BEGIN SSH SIGNATURE-----\n") + 40
        changed[offset] = ord("A") if changed[offset] != ord("A") else ord("B")
        signature.write_bytes(changed)
        run(executable, default, compatibility, "signed-bad-signature", library, root_file)
        signature.write_bytes(original)
        original_library = library.read_bytes()
        library.write_bytes(original_library + b"x")
        run(executable, default, compatibility, "signed-bad-library", library, root_file)
        library.write_bytes(original_library)
        altered_claim = json.loads(claim.read_bytes())
        altered_claim["runtimeIdentity"]["componentId"] = "sha256:" + "9" * 64
        claim.write_bytes(canonical(altered_claim))
        sign(claim, signer_private, "codex-agent-product-v1", signature)
        run(executable, default, compatibility, "signed-identity-mismatch", library, root_file)
        altered_claim["runtimeIdentity"]["componentId"] = identity["componentId"]
        altered_claim["runtimeIdentity"]["cAbiVersion"] = "1.269.0"
        claim.write_bytes(canonical(altered_claim))
        sign(claim, signer_private, "codex-agent-product-v1", signature)
        run(executable, default, compatibility, "signed-abi-width", library, root_file)
        for field, value in (
            ("contractDigest", "sha256:" + "b" * 64),
            ("target", "wrong-target"),
            ("runtimeVersion", "0.9.0"),
        ):
            altered_claim = json.loads(claim.read_bytes())
            altered_claim["runtimeIdentity"] = identity.copy()
            if field == "runtimeVersion":
                altered_claim[field] = value
            else:
                altered_claim["runtimeIdentity"][field] = value
            claim.write_bytes(canonical(altered_claim))
            sign(claim, signer_private, "codex-agent-product-v1", signature)
            run(executable, default, compatibility, "signed-incompatible-claim", library, root_file)


if __name__ == "__main__":
    main()
