"""Original native SDK metadata admission through the existing full five-host gate.

This returns an unchanged receipt, not a planner, producer, or release capability.
The caller must still authenticate the selected original metadata source/key.
"""

from contextlib import contextmanager
from contextvars import ContextVar
import os
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile
import tempfile

from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_array, require_exact_keys, require_integer,
    require_object, require_regular_directory, require_relative_path, sha256_bytes,
)
from .receipt import output_inventory_digest, validate_phase_receipt, verify_output_manifest_identity
from .registry import NATIVE_BINDINGS, NATIVE_TARGETS
from .restore import memoized_file_inventory as regular_file_inventory
from .sdk_apple_content import _snapshot_apple_tree as snapshot_regular_tree
from .sdk_inputs import REQUEST_NAME
from .sdk_package import _require_capability_output_separate, csharp_binary_inputs
from .sdk_validation_inputs import _request_inventory
from .tooling import verified_tooling_capture


_LIMIT = 16 * 1024 * 1024
_OUTPUT = "outputs/evidence/native-metadata.json"

_NATIVE_METADATA_OWNER = ContextVar("native_metadata_tooling_owner", default=None)
_OWNER_TOKEN = object()


class _NativeMetadataTooling:
    """Private executable capture, usable only inside its exact owning lifetime."""

    def __init__(self, jar, root, authority, key, token):
        if token is not _OWNER_TOKEN:
            raise TypeError("Native metadata tooling must come from its owning capture")
        from .sdk_validation import _verified_file_stamp
        self.jar, self.root, self.code = jar, root, root / "code"
        self.authority, self.key, self.active = authority, key, True
        self.jar_identity = _verified_file_stamp(jar)
        # The existing full tooling policy has authenticated every bounded regular
        # resource against Git. Retain that exact closure once, with exclusive files.
        with ZipFile(jar) as archive:
            for entry in archive.infolist():
                if entry.filename.startswith("python/") and not entry.is_dir():
                    relative = require_relative_path(entry.filename.removeprefix("python/"), "signed resource")
                    output = self.code / relative
                    output.parent.mkdir(parents=True, exist_ok=True)
                    with output.open("xb") as stream:
                        stream.write(archive.read(entry))
        (self.code / "ci/__init__.py").write_bytes(b"")
        self.code_inventory = regular_file_inventory(self.code, allow_empty=True)
        if _verified_file_stamp(jar) != self.jar_identity:
            raise ValueError("Authenticated metadata tooling changed during resource capture")

    def check(self, authority):
        from .sdk_validation import _SharedCollection, _verified_file_stamp
        if (not self.active or _NATIVE_METADATA_OWNER.get() is not self
                or _SharedCollection.authority_key(authority)[1] != self.key
                or _verified_file_stamp(self.jar) != self.jar_identity
                or regular_file_inventory(self.code, allow_empty=True) != self.code_inventory):
            raise ValueError("Native metadata tooling owner, authority or captured code changed")

    def stage(self, request, output, *, request_directory=None, diagnostics=None):
        from .sdk_validation import _fixed_environment
        self.check(self.authority)
        # Fixed code and fixed callable from the authenticated JAR, never checkout
        # imports or a caller-selected executable. Keep captured request semantics.
        bootstrap = ("import sys;sys.path.insert(0,sys.argv.pop(1));from pathlib import Path;"
            "from ci.products.sdk_inputs import stage_sdk_inputs;"
            "stage_sdk_inputs(Path(sys.argv[1]),Path(sys.argv[2]),"
            "request_directory=Path(sys.argv[3]) if sys.argv[3] else None)")
        command = [sys.executable, "-I", "-S", "-B", "-c", bootstrap, str(self.code),
                   str(request), str(output), "" if request_directory is None else str(request_directory)]
        try:
            if diagnostics is None:
                subprocess.run(command, cwd=self.root, env=_fixed_environment(), check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            else:
                with Path(diagnostics).open("xb") as log:
                    subprocess.run(command, cwd=self.root, env=_fixed_environment(), check=True,
                                   stdout=log, stderr=subprocess.STDOUT)
        finally:
            self.check(self.authority)


def _require_tooling_owner(owner, authority):
    if type(owner) is not _NativeMetadataTooling:
        raise TypeError("Native metadata requires its exact live tooling owner")
    owner.check(authority)
    return owner


@contextmanager
def native_metadata_tooling(*, owner=None, **authority):
    """Reuse one existing required capture; never start a shared verifier worker."""
    revision = authority["policy_revision"]
    if (type(revision) is not str or len(revision) != 40
            or any(character not in "0123456789abcdef" for character in revision)):
        raise ValueError("Native SDK metadata requires an exact caller-pinned Git policy")
    if owner is not None:
        held = _require_tooling_owner(owner, authority)
        try:
            yield held
        finally:
            _require_tooling_owner(held, authority)
        return
    if _NATIVE_METADATA_OWNER.get() is not None:
        raise ValueError("Nested native metadata tooling must explicitly borrow its current owner")
    from .sdk_validation import _SharedCollection
    java = Path(authority["java_executable"])
    if not java.is_absolute() or java.name not in {"java", "java.exe"}:
        raise ValueError("Native metadata requires an explicit trusted Java executable")
    fields, key = _SharedCollection.authority_key(authority)
    with verified_tooling_capture(fields["tooling_evidence"], fields["repository"], fields["tooling_public_key"],
            required_trust_domain=fields["required_trust_domain"], keyring=fields["tooling_keyring"],
            keys_directory=fields["tooling_keys_directory"], policy_revision=fields["policy_revision"]) as jar:
        with tempfile.TemporaryDirectory(prefix="native-metadata-tooling-") as temporary:
            held = _NativeMetadataTooling(jar, Path(temporary).resolve(), fields, key, _OWNER_TOKEN)
            token = _NATIVE_METADATA_OWNER.set(held)
            try:
                held.check(authority)
                yield held
            finally:
                try:
                    held.check(authority)
                finally:
                    held.active = False
                    _NATIVE_METADATA_OWNER.reset(token)



def _inventory(path, *, allow_empty=False):
    path = Path(path).absolute()
    for parent in path.parents:
        require_regular_directory(parent, "Native metadata input ancestry")
    return regular_file_inventory(path, allow_empty=allow_empty)


def verify_sdk_native_metadata_content(
    *, repository: Path, component: str, metadata_stage: Path, metadata_receipt: Path,
    package_stage: Path, package_receipt: Path, compatibility_request: Path,
    runtime_stages: Path, staged_sdks: Path, validation_stages: Path, validation_receipts: Path,
    tooling_evidence: Path, tooling_public_key: Path, java_executable: Path,
    policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
    _tooling_owner=None,
) -> tuple[dict, bytes]:
    """Reconstruct all five full host results and compare the sole original output.

    No caller-supplied content, command, digest, or callback can replace the fixed
    authenticated tooling invocation. K/R authentication and native matching run
    in that existing gate; metadata source/plan replay belongs to its caller.
    """
    if component not in NATIVE_BINDINGS:
        raise ValueError("Native SDK metadata requires an exact language")
    if (type(policy_revision) is not str or len(policy_revision) != 40
            or any(character not in "0123456789abcdef" for character in policy_revision)):
        raise ValueError("Native SDK metadata requires an exact caller-pinned Git policy")
    java_executable = Path(java_executable)
    if not java_executable.is_absolute() or java_executable.name not in {"java", "java.exe"}:
        raise ValueError("Native SDK metadata requires an explicit trusted Java executable")
    java_bytes = read_regular_file_bytes(java_executable, max_bytes=128 * 1024 * 1024,
                                         reject_symlink_parents=True)
    trees = {"metadata": Path(metadata_stage), "package": Path(package_stage),
             "runtime": Path(runtime_stages), "sdks": Path(staged_sdks),
             "validations": Path(validation_stages), "validation-receipts": Path(validation_receipts),
             "runtime-authorization": Path(package_receipt).parent / "runtime-authorization"}
    if component == "csharp":
        trees["csharp-binary"] = csharp_binary_inputs(package_receipt)["binary_stage_root"].parent
    before = {name: _inventory(path) for name, path in trees.items()}
    paths = {"metadata.json": Path(metadata_receipt), "package.json": Path(package_receipt),
             "original-request.json": Path(compatibility_request)}
    originals = {name: read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True)
                 for name, path in paths.items()}
    request_inventory = _request_inventory(paths["original-request.json"])
    receipts = {phase: validate_phase_receipt(load_canonical_json_bytes(originals[f"{phase}.json"]))
                for phase in ("metadata", "package")}
    metadata, package = receipts["metadata"], receipts["package"]
    version = metadata["productVersion"]
    for phase, receipt in receipts.items():
        if ((receipt["product"], receipt["component"], receipt["phase"], receipt["target"]) !=
                ("sdk", component, phase, "desktop") or receipt["productVersion"] != version):
            raise ValueError("Native metadata and package receipts have different phase/version identities")
    with tempfile.TemporaryDirectory(prefix="sdk-native-metadata-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, [*trees.values(), *paths.values(),
            *request_inventory, Path(repository), Path(tooling_evidence), Path(tooling_public_key),
            java_executable, *(Path(path) for path in (tooling_keyring, tooling_keys_directory) if path is not None)])
        for name, source in trees.items():
            snapshot_regular_tree(source, private / name)
            if _inventory(private / name) != before[name]:
                raise ValueError("Native metadata original tree changed during capture")
        for name, data in originals.items():
            (private / name).write_bytes(data)
        for phase, receipt in receipts.items():
            manifest = verify_output_manifest_identity(private / phase, "sdk", component, phase, "desktop", version)
            if manifest["outputs"] != receipt["outputs"]:
                raise ValueError("Native metadata/package stage differs from its original receipt")
        if (len(metadata["outputs"]) != 1 or metadata["outputs"][0]["relativePath"] != _OUTPUT
                or metadata["outputs"][0]["kind"] != "native-wrapper-metadata"):
            raise ValueError("Native metadata requires its sole exact content output")
        targets = sorted(NATIVE_TARGETS)
        if (sorted(path.name for path in (private / "validations").iterdir()) != targets
                or {record["relativePath"] for record in before["validation-receipts"]} !=
                {f"{target}.json" for target in targets}):
            raise ValueError("Native metadata requires exactly five original host stages and receipts")
        hosts = {}
        for target in targets:
            raw = read_regular_file_bytes(private / "validation-receipts" / f"{target}.json", max_bytes=_LIMIT)
            receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
            if ((receipt["product"], receipt["component"], receipt["phase"], receipt["target"]) !=
                    ("sdk", component, "validation", target) or receipt["productVersion"] != version):
                raise ValueError("Native metadata host receipt has a different original identity")
            manifest = verify_output_manifest_identity(private / "validations" / target,
                                                       "sdk", component, "validation", target, version)
            if manifest["outputs"] != receipt["outputs"]:
                raise ValueError("Native metadata host stage differs from its original receipt")
            hosts[target] = receipt, raw
        # One held capture authenticates packaged staging and the unchanged
        # fixed Java five-host gate. Original compatibility checks remain inside.
        with native_metadata_tooling(owner=_tooling_owner, repository=repository,
                java_executable=java_executable, tooling_evidence=tooling_evidence,
                tooling_public_key=tooling_public_key, policy_revision=policy_revision,
                required_trust_domain=required_trust_domain, tooling_keyring=tooling_keyring,
                tooling_keys_directory=tooling_keys_directory) as tooling:
            tooling.stage(private / "original-request.json", private / "compatibility",
                          request_directory=paths["original-request.json"].parent)
            compatibility_before = _inventory(private / "compatibility", allow_empty=True)
            output = private / "verified-content.json"
            arguments = {"repository": repository, "language": component, "sdk-version": version,
                "package-stage": private / "package", "package-receipt": private / "package.json",
                "compatibility-request": private / "compatibility" / REQUEST_NAME,
                "runtime-stages": private / "runtime", "staged-sdks": private / "sdks",
                "validation-stages": private / "validations", "validation-receipts": private / "validation-receipts",
                "content-output": output}
            command = [str(java_executable), "-jar", str(tooling.jar), "write-native-wrapper-metadata-content"]
            command += [part for name, value in arguments.items() for part in (f"--{name}", str(value))]
            environment = {key: value for key, value in os.environ.items() if key in {
                "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL"}}
            subprocess.run(command, cwd=private, env=environment, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        content = read_regular_file_bytes(output, max_bytes=_LIMIT, reject_symlink_parents=True)
        if content != read_regular_file_bytes(private / "metadata" / _OUTPUT, max_bytes=_LIMIT):
            raise ValueError("Original native metadata differs from the complete authenticated five-host result")
        value = require_exact_keys(load_canonical_json_bytes(content),
            {"schemaVersion", "kind", "component", "sdkVersion", "contractDigest", "canonicalApiDigest",
             "canonicalCoverageDigest", "packageOutputsDigest", "hosts"}, "Native metadata content")
        if (require_integer(value["schemaVersion"], "Native metadata schema", 1) != 1
                or value["kind"] != "sdk-native-metadata-content" or value["component"] != component
                or value["sdkVersion"] != version
                or value["packageOutputsDigest"] != output_inventory_digest(package["outputs"])):
            raise ValueError("Full native metadata result differs from the original package identity")
        contents = [require_object(host, "Native metadata host")
                    for host in require_array(value["hosts"], "Native metadata hosts")]
        if [host.get("target") for host in contents] != targets:
            raise ValueError("Full native metadata result lacks exact ordered host contents")
        # Reuse the planner's record representation, without planning or granting
        # source authority here. Every semantic digest binds an original raw receipt.
        from .plan import _upstream_record
        expected = [_upstream_record(package)]
        for host in contents:
            receipt, raw = hosts[host["target"]]
            expected.append(_upstream_record(receipt, semantic_projection={
                "schemaVersion": 1, "kind": "sdk-native-validation-content",
                "sha256": sha256_bytes(canonical_json_bytes(host)), "receiptSha256": sha256_bytes(raw)}))
        expected.sort(key=lambda member: tuple(member[field] for field in ("product", "component", "phase", "target")))
        if metadata["inputs"]["upstreamArtifacts"] != expected:
            raise ValueError("Native metadata does not bind its exact original package and five host projections")
        for name, source in trees.items():
            if _inventory(source) != before[name] or _inventory(private / name) != before[name]:
                raise ValueError("Original or private native metadata inputs changed during verification")
        for name, source in paths.items():
            if any(read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True) != originals[name]
                   for path in (source, private / name)):
                raise ValueError("Original or private native metadata receipt/request changed during verification")
        if (_inventory(private / "compatibility", allow_empty=True) != compatibility_before
                or _request_inventory(paths["original-request.json"]) != request_inventory):
            raise ValueError("Native metadata original or captured K/R compatibility inputs changed")
    if read_regular_file_bytes(java_executable, max_bytes=128 * 1024 * 1024,
                               reject_symlink_parents=True) != java_bytes:
        raise ValueError("Trusted Java executable changed during native metadata verification")
    return metadata, originals["metadata.json"]
