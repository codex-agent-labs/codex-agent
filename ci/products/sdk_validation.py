"""Receipt-bound SDK comparison proof from the authenticated full tooling gate."""

import os
from pathlib import Path
import subprocess
import tempfile

from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes, regular_file_inventory,
    require_array, require_exact_keys, require_integer, require_relative_path, require_sha256, require_string,
    sha256_bytes, snapshot_regular_tree,
)
from .receipt import output_inventory_digest, validate_phase_receipt, verify_output_manifest_identity
from .registry import NATIVE_BINDINGS, NATIVE_TARGETS


_VERIFIED = object()
_IDENTITY = ("product", "component", "phase", "target", "productVersion", "buildKey")
_LIMIT = 16 * 1024 * 1024
_EVIDENCE_PATHS = {
    "packageStage": "package_stage", "packageReceipt": "package_receipt",
    "compatibilityRequest": "compatibility_request", "runtimeStages": "runtime_stages",
    "stagedSdks": "staged_sdks", "validationStage": "validation_stage", "validationReceipt": "validation_receipt",
    "runtimeAuthorization": "runtime_authorization",
}


def sdk_validation_paths(component):
    return {**_EVIDENCE_PATHS, **({"binaryStage": "binary_stage", "binaryReceipt": "binary_receipt"}
                               if component == "csharp" else {})}


def map_sdk_validation_record(record, path):
    fields = sdk_validation_paths(record.get("component") if isinstance(record, dict) else None)
    record = require_exact_keys(record, {"receiptSha256", "component", "target", *fields}, "SDK validation evidence")
    require_sha256(record["receiptSha256"], "SDK validation original receipt")
    if record["component"] not in NATIVE_BINDINGS or record["target"] not in NATIVE_TARGETS:
        raise ValueError("SDK validation evidence requires an exact native language/host")
    return {**record, **{name: path(record[name]) for name in fields}}


def decode_sdk_validation_records(root: Path, records):
    result = {}
    for value in require_array(records, "SDK validation records"):
        record = map_sdk_validation_record(value, lambda path: root / require_relative_path(path, "SDK evidence path"))
        digest = record["receiptSha256"]
        if digest in result:
            raise ValueError("Duplicate SDK validation receipt")
        result[digest] = record
    if list(result) != sorted(result):
        raise ValueError("SDK validation evidence must be sorted by original receipt")
    return result


def rebase_sdk_validation_records(records, source_root: Path, destination_root: Path):
    decode_sdk_validation_records(source_root, records)
    return [map_sdk_validation_record(record, lambda value:
            (source_root / require_relative_path(value, "SDK evidence path")).relative_to(destination_root).as_posix())
            for record in records]


def sdk_validation_provider(root: Path, records, *, repository: Path, policy_revision: str, tooling):
    """Trusted invocation policy is separate from transported original SDK records."""
    originals = decode_sdk_validation_records(root, records)
    if not originals:
        return None
    context = require_exact_keys(tooling,
        {"evidence", "publicKey", "javaExecutable", "requiredTrustDomain", "keyring", "keysDirectory"},
        "SDK validation caller tooling policy")
    arguments = {}
    for field, name in (("evidence", "tooling_evidence"), ("publicKey", "tooling_public_key"),
                        ("javaExecutable", "java_executable"), ("keyring", "tooling_keyring"),
                        ("keysDirectory", "tooling_keys_directory")):
        if field in {"keyring", "keysDirectory"} and context[field] is None:
            arguments[name] = None
        else:
            path = Path(require_string(context[field], f"SDK tooling {field}"))
            if not path.is_absolute():
                raise ValueError("SDK tooling policy paths must be absolute caller inputs")
            arguments[name] = path
    trust = context["requiredTrustDomain"]
    if trust not in {"development", "release"} or ((trust == "release") !=
            (arguments["tooling_keyring"] is not None and arguments["tooling_keys_directory"] is not None)):
        raise ValueError("SDK tooling trust requires exact caller-pinned release keys")
    if trust == "development" and any(arguments[name] is not None for name in ("tooling_keyring", "tooling_keys_directory")):
        raise ValueError("Development SDK tooling rejects release keys")
    proofs = {}

    def verify(entry, _verified_object=None):
        digest = entry["receiptSha256"]
        record = originals.get(digest)
        if record is None or (entry["component"], entry["target"]) != (record["component"], record["target"]):
            raise ValueError("SDK validation comparison lacks exact original language/host evidence")
        if digest not in proofs:
            proof = verify_sdk_validation_projection(repository=repository, policy_revision=policy_revision,
                component=record["component"], target=record["target"], required_trust_domain=trust,
                **arguments, **{dest: record[src] for src, dest in sdk_validation_paths(record["component"]).items()})
            if type(proof) is not VerifiedSdkValidationProjection:
                raise ValueError("SDK validation provider requires the full authenticated proof")
            proofs[digest] = proof
        proof = proofs[digest]
        proof.output_inventory(digest, entry["outputs"], identity=entry)
        return proof

    return verify


class VerifiedSdkValidationProjection:
    """Comparison only; original producer/receipt/signing bytes stay external."""

    __slots__ = ("_receipt", "_content", "_verified")

    def __init__(self, receipt: bytes, content: bytes, verified: object):
        if verified is not _VERIFIED:
            raise TypeError("SDK validation projection requires the authenticated full verifier")
        self._receipt, self._content, self._verified = receipt, content, verified

    def output_inventory(self, receipt_sha256, outputs, *, identity=None):
        receipt = load_canonical_json_bytes(self._receipt)
        if (self._verified is not _VERIFIED or receipt_sha256 != sha256_bytes(self._receipt)
                or outputs != receipt["outputs"] or identity is None
                or any(identity.get(field) != receipt[field] for field in _IDENTITY)):
            raise ValueError("SDK comparison differs from its exact original receipt/identity/outputs")
        return [{"kind": "sdk-native-validation-content", "relativePath": "outputs/sdk-native-validation-content.json",
                 "bytes": len(self._content), "sha256": sha256_bytes(self._content)}]

    def receipt_value(self, receipt, package_receipt):
        self.output_inventory(sha256_bytes(canonical_json_bytes(receipt)), receipt["outputs"], identity=receipt)
        content = load_canonical_json_bytes(self._content)
        if (tuple(package_receipt.get(field) for field in _IDENTITY[:4]) !=
                ("sdk", receipt["component"], "package", "desktop")
                or package_receipt["productVersion"] != content["sdkVersion"]
                or output_inventory_digest(package_receipt["outputs"]) != content["packageOutputsDigest"]):
            raise ValueError("SDK validation projection belongs to another metadata package")
        return {"schemaVersion": 1, "kind": "sdk-native-validation-content",
                "sha256": sha256_bytes(self._content), "receiptSha256": sha256_bytes(self._receipt)}


def verify_sdk_validation_projection(
    *, repository: Path, component: str, target: str, package_stage: Path, package_receipt: Path,
    compatibility_request: Path, runtime_stages: Path, staged_sdks: Path, runtime_authorization: Path,
    validation_stage: Path, validation_receipt: Path, tooling_evidence: Path, tooling_public_key: Path,
    java_executable: Path, policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
    binary_stage: Path | None = None, binary_receipt: Path | None = None,
) -> VerifiedSdkValidationProjection:
    """Only the existing fixed full matcher can mint this same-snapshot proof.

    Java and the applicable Git policy are trusted invocation/toolchain inputs,
    not fields selected by an imported product record. No arbitrary command,
    success callback, content file or digest can bypass executable admission.
    """
    shared = _SHARED_SCOPE.get()
    if shared is not None:
        arguments = locals().copy()
        del arguments['shared']
        return shared.verify(**arguments)
    from .tooling import verified_tooling_capture
    if component not in NATIVE_BINDINGS or target not in NATIVE_TARGETS:
        raise ValueError("SDK comparison requires an exact native language/host")
    java_executable = Path(java_executable)
    if not java_executable.is_absolute() or java_executable.name not in {"java", "java.exe"}:
        raise ValueError("SDK comparison requires an explicit trusted Java executable")
    java_bytes = read_regular_file_bytes(java_executable, max_bytes=128 * 1024 * 1024, reject_symlink_parents=True)
    stages = {"package": Path(package_stage), "validation": Path(validation_stage)}
    receipt_paths = {"package": Path(package_receipt), "validation": Path(validation_receipt)}
    if ((binary_stage is None) != (binary_receipt is None)
            or (binary_stage is not None) != (component == "csharp")):
        raise ValueError("C# validation requires its exact original binary input pair")
    if component == "csharp":
        stages["binary"] = Path(binary_stage)
        receipt_paths["binary"] = Path(binary_receipt)
    before = {phase: regular_file_inventory(path) for phase, path in stages.items()}
    authorization_inventory = regular_file_inventory(runtime_authorization)
    originals = {phase: read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True)
                 for phase, path in receipt_paths.items()}
    receipts = {phase: validate_phase_receipt(load_canonical_json_bytes(raw)) for phase, raw in originals.items()}
    if receipts["package"]["productVersion"] != receipts["validation"]["productVersion"]:
        raise ValueError("SDK validation and package versions differ")
    with tempfile.TemporaryDirectory(prefix="sdk-validation-proof-") as temporary:
        root = Path(temporary).resolve()
        authorization = root / "runtime-authorization" / target
        snapshot_regular_tree(runtime_authorization, authorization)
        if regular_file_inventory(authorization) != authorization_inventory:
            raise ValueError("SDK Runtime authorization changed during capture")
        captured = {}
        for phase, source in stages.items():
            stage = root / "csharp-binary/stage" if phase == "binary" else root / phase
            snapshot_regular_tree(source, stage)
            if regular_file_inventory(stage) != before[phase]:
                raise ValueError("SDK original stage changed during capture")
            expected_target = target if phase == "validation" else "desktop"
            receipt = receipts[phase]
            if tuple(receipt[field] for field in _IDENTITY[:4]) != ("sdk", component, phase, expected_target):
                raise ValueError("SDK original receipt differs from requested language/host/phase")
            manifest = verify_output_manifest_identity(stage, "sdk", component, phase,
                                                       expected_target, receipt["productVersion"])
            if manifest["outputs"] != receipt["outputs"]:
                raise ValueError("SDK original receipt differs from captured stage outputs")
            captured[phase] = (root / "csharp-binary/phase-receipt.json" if phase == "binary"
                               else root / f"{phase}-receipt.json")
            captured[phase].write_bytes(originals[phase])
        output = root / "content.json"
        with verified_tooling_capture(tooling_evidence, repository, tooling_public_key,
                required_trust_domain=required_trust_domain, keyring=tooling_keyring,
                keys_directory=tooling_keys_directory, policy_revision=policy_revision) as jar:
            arguments = {"repository": repository, "language": component, "target": target,
                "package-stage": root / "package", "package-receipt": captured["package"],
                "compatibility-request": compatibility_request, "runtime-stages": runtime_stages,
                "staged-sdks": staged_sdks, "validation-stage": root / "validation",
                "validation-receipt": captured["validation"], "content-output": output}
            command = [str(java_executable), "-jar", str(jar), "write-native-wrapper-validation-content"]
            command += [part for key, value in arguments.items() for part in (f"--{key}", str(value))]
            # Win32 OpenSSH needs ProgramData during process initialization,
            # including for verification; this is an OS path, not trust input.
            environment = {key: value for key, value in os.environ.items()
                           if key in {"PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL", "PROGRAMDATA"}}
            try:
                subprocess.run(command, cwd=root, env=environment, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as error:
                if error.stderr:
                    error.add_note("Native validation verifier stderr:\n" + error.stderr.decode("utf-8", errors="replace"))
                raise
        content = read_regular_file_bytes(output, max_bytes=_LIMIT, reject_symlink_parents=True)
        _checked_native_content(content, receipts['package'], component, target)
        if (regular_file_inventory(authorization) != authorization_inventory
                or regular_file_inventory(runtime_authorization) != authorization_inventory):
            raise ValueError("SDK Runtime authorization changed during verification")
        for phase, source in stages.items():
            stage = root / "csharp-binary/stage" if phase == "binary" else root / phase
            if (regular_file_inventory(stage) != before[phase] or regular_file_inventory(source) != before[phase]
                    or read_regular_file_bytes(captured[phase]) != originals[phase]
                    or read_regular_file_bytes(receipt_paths[phase], reject_symlink_parents=True) != originals[phase]):
                raise ValueError("Original or private SDK validation inputs changed during verification")
    if read_regular_file_bytes(java_executable, reject_symlink_parents=True) != java_bytes:
        raise ValueError("Trusted Java executable changed during SDK verification")
    return VerifiedSdkValidationProjection(originals["validation"], content, _VERIFIED)


def _checked_native_content(content, package_receipt, component, target):
    value = require_exact_keys(load_canonical_json_bytes(content),
        {"schemaVersion", "kind", "component", "target", "sdkVersion", "packageOutputsDigest",
         "contractDigest", "canonicalApiDigest", "canonicalCoverageDigest", "files", "packageNegativeCases"},
        "verified SDK validation content")
    if (require_integer(value["schemaVersion"], "SDK content schema", 1) != 2
            or value["kind"] != "sdk-native-validation-content" or value["component"] != component
            or value["target"] != target or value["sdkVersion"] != package_receipt["productVersion"]
            or value["packageOutputsDigest"] != output_inventory_digest(package_receipt["outputs"])):
        raise ValueError("Full SDK verifier returned a different package/language/host identity")
    for field in ("contractDigest", "canonicalApiDigest", "canonicalCoverageDigest"):
        require_sha256(value[field], f"verified SDK content {field}")


"""Local factoring experiment, NOT a production admission or trust capability.

The complete package gate runs once. Each host retains its original planner,
source, authorization, Kotlin semantic and C++ negative checks. No receipt is
minted or rewritten. Main must integrate/qualify matching signed tooling before
this can replace the production full matcher.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from types import FunctionType
import os
import subprocess
import sys
import tempfile
from threading import Lock, RLock
from time import perf_counter
from zipfile import ZipFile

if __package__ in {"ci.products", "products"}:
    from . import restore
    from .inventory import canonical_json_bytes, read_regular_file_bytes, sha256_bytes, snapshot_regular_tree
else:  # Standalone local factoring test, never the fixed signed entry.
    from ci.products import restore
    from ci.products.inventory import canonical_json_bytes, read_regular_file_bytes, sha256_bytes, snapshot_regular_tree


_BYTE_INVENTORIES = ContextVar("sdk_verifier_byte_inventories", default=None)
_inventory_function = restore.memoized_file_inventory
memoized_file_inventory = FunctionType(
    _inventory_function.__code__,
    {**vars(restore), "_VERIFICATION_SESSION": _BYTE_INVENTORIES},
    _inventory_function.__name__, _inventory_function.__defaults__, _inventory_function.__closure__)
memoized_file_inventory.__kwdefaults__ = _inventory_function.__kwdefaults__


@contextmanager
def _byte_inventory_scope():
    # This is ONLY the existing bounded byte-hash memo, not restore objects,
    # qualification state or authentication. No global verifier is replaced.
    if _BYTE_INVENTORIES.get() is not None:
        yield
        return
    cache = {"lock": RLock()}
    token = _BYTE_INVENTORIES.set(cache)
    try:
        yield
    finally:
        _BYTE_INVENTORIES.reset(token)
        cache.clear()


class SharedPackageSession:
    """One exact common input set; no global, serialized or cross-run cache."""

    def __init__(self, root, repository, package_stage, package_receipt, request,
                 runtime_stages, staged_sdks, *, binary_stage=None, binary_receipt=None):
        from . import sdk_package as package

        self.root, self.repository = root, repository
        self.inputs = dict(package_stage=package_stage, package_receipt=package_receipt, request=request,
                           runtime_stages=runtime_stages, staged_sdks=staged_sdks,
                           binary_stage=binary_stage, binary_receipt=binary_receipt)
        self.common = root / "common"
        self.ready = False
        self.metrics_lock = Lock()
        self.metrics = dict(commonVerifications=0, hostChecks=0, commonSeconds=0.0, hostSeconds=[])
        before = self.subject(self.inputs)
        captured = []

        def verified_plan(repository, receipt, versions, upstream, projection, native_projections=None):
            package._verify_plan(repository, receipt, versions, upstream, projection, native_projections)
            if receipt["phase"] == "package":
                captured.append((dict(versions), list(upstream), projection, tuple(native_projections)))

        # Reuse the repository's private namespace pattern. The original verifier
        # still runs unchanged, and no global function is replaced.
        namespace = {**vars(package), "_verify_plan": verified_plan}
        original = package.verify_sdk_package_inputs
        verify = FunctionType(original.__code__, namespace, original.__name__,
                              original.__defaults__, original.__closure__)
        verify.__kwdefaults__ = original.__kwdefaults__
        started = perf_counter()
        self.receipt, self.receipt_bytes = verify(
            repository, package_stage, package_receipt, request,
            runtime_stage_root=runtime_stages, staged_sdks=staged_sdks,
            binary_stage_root=binary_stage, binary_receipt_path=binary_receipt,
            validation_inputs_output=self.common,
        )
        if len(captured) != 1 or before != self.subject(self.inputs):
            raise ValueError("Common package inputs changed or lacked one complete original plan")
        self.versions, upstream, self.projection, self.native_projections = captured[0]
        self.upstream = {package._instance(value): value for value in [*upstream, self.receipt]}
        self.before = before
        self.common_inventory = memoized_file_inventory(self.common)
        self.metrics.update(commonVerifications=1, commonSeconds=perf_counter() - started)
        self.ready = True

    @staticmethod
    def subject(inputs):
        from . import sdk_package as package

        # Collector carriers already have a closed, shared compatibility category.
        # Do not scan the repository or rehash its multi-GB payloads per host.
        request = inputs["request"]
        inventory = memoized_file_inventory(request.parent)
        arguments = package.load_sdk_compatibility_request(request)
        # All effective input paths must be inside the closed retained category.
        # Its complete inventory also covers attestation closure and public keys.
        for directory in package._original_artifact_directories(arguments):
            directory.relative_to(request.parent)
        trees = {name: inputs[name] for name in ("package_stage", "runtime_stages", "staged_sdks")}
        files = {name: inputs[name] for name in ("package_receipt", "request")}
        if inputs["binary_stage"] is not None:
            trees["binary_stage"], files["binary_receipt"] = inputs["binary_stage"], inputs["binary_receipt"]
        return dict(
            trees={name: memoized_file_inventory(path) for name, path in trees.items()},
            files={name: sha256_bytes(read_regular_file_bytes(path, reject_symlink_parents=True))
                   for name, path in files.items()},
            inputs=inventory,
        )

    def check(self, inputs=None):
        if not self.ready:
            raise ValueError("Common package proof is outside its private lifetime")
        if (self.subject(self.inputs if inputs is None else inputs) != self.before
                or memoized_file_inventory(self.common) != self.common_inventory):
            raise ValueError("Common package inputs changed after full verification")

    def verify_host(self, stage, receipt_path, target, authorization, *, java, jar, inputs=None):
        """Return comparison bytes only, never production Verified* authority."""
        from . import sdk_package as package

        self.check(inputs)
        started = perf_counter()
        validation, original = package._receipt(receipt_path)
        if (validation["component"] != self.receipt["component"]
                or validation["productVersion"] != self.receipt["productVersion"]):
            raise ValueError("Host validation belongs to another package")
        before = memoized_file_inventory(stage)
        authorization_before = memoized_file_inventory(authorization)
        package._verify_native_validation_stage(stage, validation, target)
        instance = package._instance(validation)
        targets = {item.target for item in package.native_runtime_validation_dependencies(instance)}
        package._verify_plan(self.repository, validation, self.versions,
            [self.upstream[item] for item in package.phase_instance_dependencies(instance)],
            self.projection, tuple(value for value in self.native_projections if value.target in targets))
        with tempfile.TemporaryDirectory(prefix="host-", dir=self.root) as temporary:
            view = Path(temporary)
            snapshot_regular_tree(stage, view / "validation")
            if memoized_file_inventory(view / "validation") != before:
                raise ValueError("Host evidence changed during capture")
            (view / "receipts").mkdir()
            (view / "receipts/sdk-package.json").write_bytes(self.receipt_bytes)
            (view / "receipts/sdk-validation.json").write_bytes(original)
            (view / "contract").mkdir()
            (view / "contract/contract-manifest.json").write_bytes(read_regular_file_bytes(
                self.common / "contract/contract-manifest.json", reject_symlink_parents=True))
            package._capture_validation_sources(self.repository, validation, view / "validation", view)
            captured = memoized_file_inventory(view)
            with package.verified_native_consumer_authorization(authorization, self.common / "sdks", target):
                _host_gates(java, jar, self.common, view, validation["component"], target)
            content = canonical_json_bytes(package.native_validation_content(view, validation["component"], target))
            if (memoized_file_inventory(view) != captured or memoized_file_inventory(stage) != before
                    or package._receipt(receipt_path)[1] != original
                    or memoized_file_inventory(authorization) != authorization_before):
                raise ValueError("Host inputs changed during semantic verification")
            self.check(inputs)
        with self.metrics_lock:
            self.metrics["hostChecks"] += 1
            self.metrics["hostSeconds"].append(perf_counter() - started)
        return content


def _host_gates(java, jar, common, view, component, target):
    """Fixed existing verifier commands; no caller-selected matcher or callback."""
    environment = {key: value for key, value in os.environ.items() if key in {
        "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL", "PROGRAMDATA"}}
    raw = view / "validation/outputs"
    if component == "cpp":
        # Reuse this fixed worker's already-captured signed resource tree.
        # Keeping its original layout also resolves the signed inventory helper;
        # parent guards cover the complete tree before and after every request.
        code = Path(__file__).resolve().parents[2]
        script = code / "codex-agent-bindings/cpp/tools/verify_imported_package.py"
        subprocess.run([sys.executable, "-I", "-S", "-B", str(script), "verify-evidence",
            "--evidence", str(raw / "package-negatives"),
            "--expected-test-program", str(view / "validation-source/test_installed_package_tamper.py")],
            cwd=code, env=environment, check=True, capture_output=True)
    arguments = dict(language=component, target=target, **{
        "capability-inputs": common, "installed-evidence": raw / "installed",
        "capability-evidence": raw / "capability", "claims": view / "validation-source/capability-claims.tsv"})
    subprocess.run([str(java), "-jar", str(jar), "verify-native-wrapper-validation-evidence",
        *[part for name, value in arguments.items() for part in (f"--{name}", str(value))]],
        cwd=view, env=environment, check=True, capture_output=True)


@contextmanager
def shared_package(*args, **kwargs):
    with tempfile.TemporaryDirectory(prefix="shared-sdk-package-") as temporary, _byte_inventory_scope():
        session = SharedPackageSession(Path(temporary).resolve(), *args, **kwargs)
        try:
            yield session
        finally:
            session.ready = False
            session.upstream.clear()
            session.native_projections = ()
            session.projection = None


"""Held sdk_validation.py extension: fixed private process, not a network service.

Appended after shared_verifier.py by prepare_candidate.py. Its relative imports
resolve only from the already-authenticated JAR's private resource extraction.
No producer executable, mutable checkout import or serialized trust flag is used.
"""

from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import ExitStack
from contextvars import copy_context
from threading import Thread, BoundedSemaphore
import json


_SHARED_PROTOCOL = 1
_COMMON_FIELDS = {"package_stage", "package_receipt", "request", "runtime_stages", "staged_sdks",
                  "binary_stage", "binary_receipt"}
_HOST_FIELDS = {"stage", "receipt_path", "target", "authorization"}
_SHARED_SCOPE = ContextVar("sdk_shared_verifier", default=None)


def _fixed_environment():
    return {key: value for key, value in os.environ.items() if key in {
        "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL", "PROGRAMDATA"}}


def _path(value):
    if type(value) is not str or not Path(value).is_absolute() or ".." in Path(value).parts:
        raise ValueError("Shared verifier requires absolute, non-traversing caller paths")
    return Path(value)


def _verified_file_stamp(path):
    # The caller has authenticated the private JAR's bytes. Guard that one file,
    # not siblings or an entire work directory. Windows keeps the full byte check.
    if os.name == "nt":
        return sha256_bytes(read_regular_file_bytes(path, reject_symlink_parents=True))
    descriptor, metadata = restore._open_safe_regular(path, "Shared verifier JAR")
    try:
        return restore._stat_identity(metadata)
    finally:
        os.close(descriptor)


def _failure_detail(error):
    message = f"{type(error).__name__}: {error}"
    if isinstance(error, subprocess.CalledProcessError):
        raw = error.stderr or error.stdout or b""
        message += "\nVerifier diagnostics (last 64 KiB):\n" + raw[-65536:].decode("utf-8", errors="replace")
    return message


def _serve_shared_verifier(repository, java, jar):
    """At most two host gates and five retained package groups per collection."""
    from . import sdk_package as package

    # Keep protocol separate from all inherited child-tool stdout/stdin. A .NET
    # inspector's progress is diagnostic text, never a protocol/acceptance record.
    incoming = os.fdopen(os.dup(0), "rb")
    outgoing = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)
    with open(os.devnull, "rb") as empty:
        os.dup2(empty.fileno(), 0)
    output_lock, cache_lock = Lock(), Lock()
    cache, ids = {}, set()

    def emit(value):
        with output_lock:
            outgoing.write(canonical_json_bytes(value))
            outgoing.flush()

    with _byte_inventory_scope(), ExitStack() as lifetime, ThreadPoolExecutor(max_workers=2) as pool:
        def verify(request):
            started = perf_counter()
            owner, completed = False, False
            def metrics():
                return {"commonChecks": int(owner and completed), "commonReuses": int(not owner and completed),
                        "elapsedSeconds": f"{perf_counter() - started:.6f}"}
            try:
                common = package.require_exact_keys(request["common"], _COMMON_FIELDS, "shared package inputs")
                common = {key: None if value is None and key.startswith("binary_") else _path(value)
                          for key, value in common.items()}
                if (common["binary_stage"] is None) != (common["binary_receipt"] is None):
                    raise ValueError("C# binary inputs must be supplied as a pair")
                host = package.require_exact_keys(request["host"], _HOST_FIELDS, "shared host inputs")
                host = {key: value if key == "target" else _path(value) for key, value in host.items()}
                subject = SharedPackageSession.subject(common)
                key = sha256_bytes(canonical_json_bytes(subject))
                with cache_lock:
                    future = cache.get(key)
                    owner = future is None
                    if owner:
                        future = Future()
                        # Bounded retention, not an artificial compatibility rule.
                        if len(cache) < 5:
                            cache[key] = future
                local_context = None
                if owner:
                    try:
                        local_context = shared_package(repository=repository, **common)
                        session = local_context.__enter__()
                        if session.before != subject:
                            raise ValueError("Common input binding changed during verification")
                        with cache_lock:
                            if cache.get(key) is future:
                                lifetime.callback(local_context.__exit__, None, None, None)
                                local_context = None
                        future.set_result(session)
                    except BaseException as error:
                        if local_context is not None:
                            local_context.__exit__(None, None, None)
                            local_context = None
                        future.set_exception(error)
                        with cache_lock:
                            if cache.get(key) is future:
                                del cache[key]
                        raise
                try:
                    session = future.result()
                    completed = True
                    receipt_before = package._receipt(host["receipt_path"])[1]
                    content = session.verify_host(**host, java=java, jar=jar, inputs=common)
                    if package._receipt(host["receipt_path"])[1] != receipt_before:
                        raise ValueError("Original host receipt changed")
                    emit({"id": request["id"], "result": "success", "receiptSha256": sha256_bytes(receipt_before),
                          "content": package.load_canonical_json_bytes(content),
                          "metrics": metrics()})
                finally:
                    if local_context is not None:
                        local_context.__exit__(None, None, None)
            except Exception as error:
                detail = _failure_detail(error)
                print(detail, file=sys.stderr, flush=True)
                emit({"id": request["id"], "result": "failure", "error": detail,
                      "metrics": metrics()})

        emit({"protocol": _SHARED_PROTOCOL})
        # Only the parent submits two outstanding rows. Reject extra queued work
        # instead of turning a bounded collector into an unbounded body buffer.
        slots = BoundedSemaphore(2)
        while raw := incoming.readline(_LIMIT + 1):
            if len(raw) > _LIMIT or not raw.endswith(b"\n"):
                raise ValueError("Oversized or incomplete shared-verifier request")
            request = package.require_exact_keys(package.load_canonical_json_bytes(raw),
                {"id", "common", "host"}, "shared-verifier request")
            identity = request["id"]
            if type(identity) is not int or identity < 1 or identity in ids or len(ids) >= 128:
                raise ValueError("Invalid or repeated shared-verifier request identity")
            ids.add(identity)
            slots.acquire()
            pending = pool.submit(copy_context().run, verify, request)
            pending.add_done_callback(lambda _: slots.release())
    incoming.close()
    outgoing.close()


class _SharedVerifierProcess:
    """Fixed authenticated resource runner; callers cannot choose executable code."""

    def __init__(self, root, jar, repository, java):
        self.root, self.jar, self.java = root, jar, java
        self.code = root / "code"
        self.jar_before = _verified_file_stamp(jar)
        with ZipFile(jar) as archive:
            for name in archive.namelist():
                if name.startswith("python/") and not name.endswith("/"):
                    relative = require_relative_path(name.removeprefix("python/"), "signed resource")
                    output = self.code / relative
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(archive.read(name))
        (self.code / "ci/__init__.py").write_bytes(b"")
        self.before = memoized_file_inventory(self.code, allow_empty=True)
        self.java_before = read_regular_file_bytes(java, reject_symlink_parents=True)
        if _verified_file_stamp(jar) != self.jar_before:
            raise ValueError("Authenticated JAR changed during private resource capture")
        self.diagnostics = open(root / "diagnostics.log", "w+b")
        bootstrap = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('ci.products.sdk_validation',run_name='__main__')"
        self.process = subprocess.Popen([sys.executable, "-I", "-S", "-B", "-c", bootstrap, str(self.code),
            "--shared-worker", "--repository", str(repository), "--java", str(java), "--jar", str(jar)],
            cwd=root, env=_fixed_environment(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.diagnostics)
        self.lock, self.slots = Lock(), BoundedSemaphore(2)
        self.pending, self.serial, self.failed = {}, 0, None
        try:
            ready = load_canonical_json_bytes(self.process.stdout.readline(_LIMIT + 1))
            if ready != {"protocol": _SHARED_PROTOCOL}:
                raise ValueError("Signed tooling does not support the fixed shared verifier")
        except BaseException as error:
            self.process.stdin.close()
            self.process.wait()
            self.process.stdout.close()
            self.diagnostics.seek(0)
            error.add_note(self.diagnostics.read(_LIMIT).decode("utf-8", errors="replace"))
            self.diagnostics.close()
            raise
        self.reader = Thread(target=self._read, name="sdk-verifier-results", daemon=True)
        self.reader.start()

    def _read(self):
        try:
            while raw := self.process.stdout.readline(_LIMIT + 1):
                if len(raw) > _LIMIT:
                    raise ValueError("Oversized shared-verifier response")
                result = load_canonical_json_bytes(raw)
                if type(result) is not dict or type(result.get("id")) is not int:
                    raise ValueError("Malformed shared-verifier response")
                with self.lock:
                    future = self.pending.pop(result["id"], None)
                if future is None:
                    raise ValueError("Unexpected shared-verifier response identity")
                future.set_result(result)
            raise ValueError("Shared verifier exited before another request could be accepted")
        except BaseException as error:
            with self.lock:
                self.failed = error
                for future in self.pending.values():
                    future.set_exception(error)
                self.pending.clear()

    def check(self):
        if (memoized_file_inventory(self.code, allow_empty=True) != self.before
                or read_regular_file_bytes(self.java, reject_symlink_parents=True) != self.java_before
                or _verified_file_stamp(self.jar) != self.jar_before):
            raise ValueError("Shared verifier code or Java changed during its private lifetime")

    def verify(self, common, host):
        with self.slots:
            self.check()
            with self.lock:
                if self.failed is not None:
                    raise ValueError("Shared verifier is no longer available") from self.failed
                self.serial += 1
                future = Future()
                self.pending[self.serial] = future
                request = dict(id=self.serial,
                    common={key: str(value) if value is not None else None for key, value in common.items()},
                    host={key: str(value) for key, value in host.items()})
                self.process.stdin.write(canonical_json_bytes(request))
                self.process.stdin.flush()
            result = future.result()
            self.check()
            metrics = require_exact_keys(result.get("metrics"),
                {"commonChecks", "commonReuses", "elapsedSeconds"}, "shared-verifier measurements")
            if any(type(metrics[name]) is not int or metrics[name] not in (0, 1)
                   for name in ("commonChecks", "commonReuses")):
                raise ValueError("Malformed shared-verifier measurements")
            # Parent/collector only, never imported by the isolated signed worker.
            # Reuse the existing inclusive, thread-safe measurement context.
            from runtime_reference_transport import count
            count("nativeSdkSharedCommonChecks", metrics["commonChecks"])
            count("nativeSdkSharedCommonReuses", metrics["commonReuses"])
            if result.get("result") == "failure":
                require_exact_keys(result, {"id", "result", "error", "metrics"}, "shared-verifier failure")
                error = ValueError(result["error"])
                error.add_note("Shared verifier metrics: " + json.dumps(result["metrics"], sort_keys=True))
                raise error
            require_exact_keys(result, {"id", "result", "receiptSha256", "content", "metrics"},
                                       "shared-verifier success")
            if result["result"] != "success":
                raise ValueError("Shared verifier did not prove successful verification")
            return result

    def close(self):
        try:
            self.process.stdin.close()
        except BrokenPipeError:
            pass
        status = self.process.wait()
        self.reader.join()
        self.process.stdout.close()
        self.diagnostics.close()
        self.check()
        if status:
            raise ValueError(f"Shared verifier failed during shutdown ({status})")


@contextmanager
def verified_shared_sdk_process(*, repository, java_executable, tooling_evidence, tooling_public_key,
                               policy_revision, required_trust_domain, tooling_keyring=None,
                               tooling_keys_directory=None):
    from .tooling import verified_tooling_capture
    if not Path(java_executable).is_absolute() or Path(java_executable).name not in {"java", "java.exe"}:
        raise ValueError("Shared verifier requires an explicit trusted Java executable")
    with _byte_inventory_scope(), verified_tooling_capture(
            tooling_evidence, repository, tooling_public_key, policy_revision=policy_revision,
            required_trust_domain=required_trust_domain, keyring=tooling_keyring,
            keys_directory=tooling_keys_directory) as jar:
        with tempfile.TemporaryDirectory(prefix="sdk-shared-verifier-") as temporary:
            worker = _SharedVerifierProcess(Path(temporary).resolve(), jar, repository, java_executable)
            try:
                yield worker
            finally:
                worker.close()




"""Held collector bridge. Enabled only inside its explicit private scope."""


class _SharedCollection:
    def __init__(self):
        self.lifetime, self.lock = ExitStack(), Lock()
        self.worker, self.authority, self.active = None, None, True

    @staticmethod
    def authority_key(arguments):
        fields = {name: arguments[name] for name in ("repository", "java_executable", "tooling_evidence",
            "tooling_public_key", "policy_revision", "required_trust_domain", "tooling_keyring", "tooling_keys_directory")}
        inventories = {}
        for name in ("tooling_evidence", "tooling_keys_directory"):
            if fields[name] is not None:
                inventories[name] = memoized_file_inventory(Path(fields[name]), allow_empty=True)
        for name in ("java_executable", "tooling_public_key", "tooling_keyring"):
            if fields[name] is not None:
                inventories[name] = sha256_bytes(read_regular_file_bytes(Path(fields[name]), reject_symlink_parents=True))
        key = sha256_bytes(canonical_json_bytes({
            "policy": {name: str(value) if isinstance(value, Path) else value for name, value in fields.items()},
            "inventories": inventories}))
        return fields, key

    def verify(self, **arguments):
        from . import sdk_package as package

        with self.lock:
            if not self.active:
                raise ValueError("Shared collection is outside its private lifetime")
        fields, key = self.authority_key(arguments)
        with self.lock:
            if not self.active:
                raise ValueError("Shared collection is outside its private lifetime")
            if self.authority is not None and key != self.authority:
                raise ValueError("Shared collection verifier authority changed")
            if self.worker is None:
                self.worker = self.lifetime.enter_context(verified_shared_sdk_process(**fields))
                self.authority = key
        component, target = arguments["component"], arguments["target"]
        if component not in NATIVE_BINDINGS or target not in NATIVE_TARGETS:
            raise ValueError("SDK comparison requires an exact native language/host")
        if ((arguments["binary_stage"] is None) != (arguments["binary_receipt"] is None)
                or (arguments["binary_stage"] is not None) != (component == "csharp")):
            raise ValueError("C# validation requires its exact original binary pair")
        package_value, package_raw = package._receipt(arguments["package_receipt"])
        validation, original = package._receipt(arguments["validation_receipt"])
        if (package._instance(package_value) != package.PhaseInstanceId("sdk", component, "package", "desktop")
                or package._instance(validation) != package.PhaseInstanceId("sdk", component, "validation", target)):
            raise ValueError("Shared verifier original receipt differs from requested identity")
        common = {name: arguments[name] for name in ("package_stage", "package_receipt", "runtime_stages",
                                                     "staged_sdks", "binary_stage", "binary_receipt")}
        common["request"] = arguments["compatibility_request"]
        host = dict(stage=arguments["validation_stage"], receipt_path=arguments["validation_receipt"],
                    target=target, authorization=arguments["runtime_authorization"])
        result = self.worker.verify(common, host)
        content = canonical_json_bytes(result["content"])
        _checked_native_content(content, package_value, component, target)
        if (result["receiptSha256"] != sha256_bytes(original)
                or package._receipt(arguments["package_receipt"])[1] != package_raw
                or package._receipt(arguments["validation_receipt"])[1] != original
                or self.authority_key(arguments)[1] != key):
            raise ValueError("Shared verifier original inputs or authority changed")
        return VerifiedSdkValidationProjection(original, content, _VERIFIED)

    def close(self):
        with self.lock:
            self.active = False
        self.lifetime.close()


@contextmanager
def shared_sdk_validation_scope():
    if _SHARED_SCOPE.get() is not None:
        yield
        return
    scope = _SharedCollection()
    token = _SHARED_SCOPE.set(scope)
    try:
        with _byte_inventory_scope():
            yield
    finally:
        try:
            scope.close()
        finally:
            _SHARED_SCOPE.reset(token)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--shared-worker", action="store_true", required=True)
    for name in ("repository", "java", "jar"):
        parser.add_argument("--" + name, type=Path, required=True)
    options = parser.parse_args()
    _serve_shared_verifier(options.repository, options.java, options.jar)
