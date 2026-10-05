"""Machine-local completed original verification; never transport authority.

The CAS is untrusted. A private verifier-owned key lives outside the selectable
product cache. Only a completed original verification may seal a record. Every
use freshly authenticates CI/policy in the caller and hashes consumed CAS bytes.
No key or seal is accepted from a product, workflow input or restored cache.
"""
from __future__ import annotations

import hashlib
import hmac
import inspect
import importlib
from dataclasses import asdict, is_dataclass
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import tempfile
from types import CodeType

from .inventory import (
    _open_directory,
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_exact_keys, require_relative_path, require_sha256, sha256_bytes,
    sha256_file, regular_file_inventory,
)
from .restore import native_cache_root, _VERIFICATION_SESSION


def _authority_root():
    # Separate from CODEX_AGENT_PRODUCT_CACHE, which is caller-selectable and
    # may be restored from an untrusted remote cache. The secret is never there.
    base = (Path.home() / "Library/Application Support" if sys.platform == "darwin"
            else Path.home() / ".local/state")
    return base / "codex-agent/verified-evidence-authority"


def _policy_value(value, *, checkout=None):
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is bytes:
        return {"bytes": value.hex()}
    if type(value) is float:
        return {"float": value.hex()}
    if type(value) is complex:
        return {"complex": [value.real.hex(), value.imag.hex()]}
    if value is Ellipsis:
        return {"ellipsis": True}
    if isinstance(value, slice):
        return {"slice": _policy_value((value.start, value.stop, value.step), checkout=checkout)}
    if isinstance(value, CodeType):
        # Canonical public code attributes, without marshal's transient
        # reference-sharing flags; includes nested code and Python3.14 slices.
        def attribute(field):
            member = getattr(value, field)
            if field == "co_filename" and checkout is not None:
                prefix = str(checkout) + os.sep
                if member.startswith(prefix):
                    member = "<checkout>/" + member[len(prefix):].replace(os.sep, "/")
            return _policy_value(member, checkout=checkout)
        return {"code": {field: attribute(field) for field in
                ("co_code", "co_consts", "co_names", "co_varnames", "co_freevars", "co_cellvars",
                 "co_argcount", "co_posonlyargcount", "co_kwonlyargcount", "co_nlocals",
                 "co_stacksize", "co_flags", "co_filename", "co_firstlineno",
                 "co_linetable", "co_exceptiontable")}}
    if isinstance(value, re.Pattern):
        return {"regex": {"pattern": _policy_value(value.pattern, checkout=checkout), "flags": value.flags}}
    if is_dataclass(value) and not inspect.isclass(value):
        return _policy_value(asdict(value), checkout=checkout)
    if type(value) is dict:
        return {"dict": sorted([[_policy_value(key, checkout=checkout), _policy_value(member, checkout=checkout)] for key, member in value.items()],
                               key=canonical_json_bytes)}
    if type(value) in (list, tuple, set, frozenset):
        members = [_policy_value(member, checkout=checkout) for member in value]
        return {type(value).__name__: sorted(members, key=canonical_json_bytes)
                if type(value) in (set, frozenset) else members}
    raise TypeError("Not immutable verification policy data")


def _portable_source_path(relative):
    # Only the benchmark caller may change independently of verifier policy.
    # Its original revision remains bound by native source authentication.
    return relative.as_posix() != ".github/workflows/portable-reuse-proof.yml"


def _source_identity(*, portable=False):
    root = Path(__file__).resolve().parents[2]
    records = []
    for directory in (root / "ci", root / ".github"):
        for path in sorted(directory.rglob("*")):
            relative = path.relative_to(root)
            if (path.is_file() and "__pycache__" not in relative.parts
                    and "tests" not in relative.parts
                    and (not portable or "node_modules" not in relative.parts)
                    and (not portable or _portable_source_path(relative))
                    and path.suffix in ({".py", ".json", ".yml", ".yaml", ".sh", ".js", ".mjs"}
                                        if portable else {".py", ".json", ".yml", ".yaml", ".sh"})):
                raw = read_regular_file_bytes(path, reject_symlink_parents=True)
                records.append({"path": relative.as_posix(), "sha256": sha256_bytes(raw)})
    # Disk hashes alone can label already-imported old code with newer policy.
    # Bind the actual loaded authentication functions and immutable policy data
    # too. Fixed modules avoid depending on incidental lazy imports/consumer order.
    executed = []
    for name in ("product_reuse", "reuse", "products.inventory", "products.restore",
                 "products.receipt", "products.registry", "products.zip_central_directory",
                 "runtime_reference_archive", "runtime_reference_transport", "reuse_qualification",
                 __name__):
        main = sys.modules.get("__main__")
        executing_cli = (name == "product_reuse" and getattr(main, "__file__", None)
                         and Path(main.__file__).resolve() == root / "ci/product_reuse.py")
        module = main if executing_cli else importlib.import_module(name)
        for symbol, value in sorted(vars(module).items()):
            functions = [value] if inspect.isfunction(value) else []
            if inspect.isclass(value) and value.__module__ == module.__name__:
                for member in vars(value).values():
                    if isinstance(member, property):
                        functions.extend(function for function in (member.fget, member.fset, member.fdel)
                                         if function is not None)
                    elif isinstance(member, (classmethod, staticmethod)):
                        functions.append(member.__func__)
                    elif inspect.isfunction(member):
                        functions.append(member)
            for function in functions:
                seen = set()
                while inspect.isfunction(function) and id(function) not in seen:
                    seen.add(id(function))
                    executed.append({"symbol": f"{name}.{symbol}.{function.__qualname__}",
                                     "code": sha256_bytes(canonical_json_bytes(_policy_value(function.__code__, checkout=root if portable else None)))})
                    try:
                        defaults = _policy_value((function.__defaults__, function.__kwdefaults__), checkout=root if portable else None)
                    except TypeError:
                        pass
                    else:
                        executed.append({"symbol": f"{name}.{symbol}.{function.__qualname__}",
                                         "defaults": defaults})
                    function = getattr(function, "__wrapped__", None)
            if not symbol.startswith("__"):
                try:
                    policy_value = _policy_value(value, checkout=root if portable else None)
                except TypeError:
                    pass
                else:
                    executed.append({"symbol": f"{name}.{symbol}", "value": policy_value})
        if name == "products.registry":
            executed.append({"registeredPhases": [str(value) for value in module.PHASE_INSTANCE_IDS]})
    return sha256_bytes(canonical_json_bytes({"format": 1, "python": sys.version,
                                             "sources": records, "executed": executed}))


def _private_key(root):
    # Reject symlink parents and group/world-accessible authority. The cache
    # may be attacker-controlled; the executing verifier's authority may not.
    ancestor = _open_directory(root.parent, "Verified evidence authority parent", create=True)
    try:
        try:
            os.mkdir(root.name, 0o700, dir_fd=ancestor)
        except FileExistsError:
            pass
    finally:
        os.close(ancestor)
    parent = _open_directory(root, "Verified evidence authority")
    temporary = ".key-" + secrets.token_hex(16)
    try:
        info = os.fstat(parent)
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Verified evidence authority is not private")
        # Atomic no-replace publication: another process never sees a partial
        # key, and a interrupted creator leaves only an unused private temp file.
        if "key" not in os.listdir(parent):
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=parent)
            with os.fdopen(descriptor, "wb") as output:
                output.write(secrets.token_bytes(32))
                output.flush()
                os.fsync(output.fileno())
            try:
                os.link(temporary, "key", src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
            except FileExistsError:
                pass
        descriptor = os.open("key", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError("Verified evidence authority key is not private")
            key = os.read(descriptor, 33)
            if info.st_size != 32 or len(key) != 32:
                raise ValueError("Verified evidence authority key is incomplete")
            return key
        finally:
            os.close(descriptor)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)


class RuntimeOriginalCache:
    def __init__(self):
        self.root = native_cache_root() / "v1/verified-runtime-originals"
        self.authority = _authority_root()
        cache_base, authority = native_cache_root().resolve(), self.authority.resolve()
        if (cache_base == authority or cache_base in authority.parents or authority in cache_base.parents):
            raise ValueError("Verified evidence authority must be disjoint from caller-selectable cache")
        self.policy = _source_identity()
        self.key = _private_key(self.authority)
        self.stats = {"hits": 0, "misses": 0, "readBytes": 0, "writtenBytes": 0}

    def _entry(self, locator):
        identity = {"policy": self.policy, "locator": locator}
        digest = sha256_bytes(canonical_json_bytes(identity))[7:]
        return self.root / "records" / f"{digest}.json", identity

    def _blob(self, record):
        digest = require_sha256(record["sha256"], "Verified member SHA")[7:]
        return self.root / "blobs" / digest[:2] / digest

    def read(self, locator):
        path, identity = self._entry(locator)
        if not path.exists() and not path.is_symlink():
            self.stats["misses"] += 1
            return None
        raw = read_regular_file_bytes(path, max_bytes=32 * 1024 * 1024, reject_symlink_parents=True)
        envelope = require_exact_keys(load_canonical_json_bytes(raw), {"record", "mac"}, "Evidence seal")
        expected = hmac.new(self.key, canonical_json_bytes(envelope["record"]), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, envelope["mac"]):
            raise ValueError("Verified original evidence seal is invalid")
        record = require_exact_keys(envelope["record"],
            {"identity", "receipt", "objectSha256", "originalFiles"}, "Verified original evidence")
        if record["identity"] != identity:
            raise ValueError("Verified original evidence has incompatible provenance/policy")
        self.stats["hits"] += 1
        return record

    def materialize(self, record, destination, *, members=None):
        rows = (members if members is not None else
                [row for row in record["originalFiles"] if not row["relativePath"].startswith("inputs/")])
        for row in rows:
            self.copy_member(record, row["relativePath"], Path(destination) / row["relativePath"], row)

    def copy_member(self, record, name, destination, expected):
        from runtime_reference_transport import _copy_exact
        original = {row["relativePath"]: row for row in record["originalFiles"]}
        name = require_relative_path(name, "Verified original member")
        row = original.get(name)
        if (row is None or name.startswith("inputs/")
                or any(row[field] != expected[field] for field in ("bytes", "sha256"))):
            raise ValueError("Requested original member is outside the verified projection")
        _copy_exact(self._blob(row), Path(destination), row)
        self.stats["readBytes"] += row["bytes"]

    def record_verified(self, locator, original, original_files, receipt, object_sha256):
        """Private caller must have completed original SHA/ZIP/shard verification.

        The full original inventory binds omitted predecessor inputs as well.
        Only required projection bodies enter CAS, independently content-hashed.
        """
        from runtime_reference_transport import _copy_exact
        projection = [row for row in original_files if not row["relativePath"].startswith("inputs/")]
        if regular_file_inventory(original, allow_empty=True) != projection:
            raise ValueError("Original projection changed before persistent verification")
        path, identity = self._entry(locator)
        record = {"identity": identity, "receipt": receipt,
                  "objectSha256": require_sha256(object_sha256, "Verified original object"),
                  "originalFiles": original_files}
        existing = self.read(locator)
        if existing is not None and existing != record:
            raise ValueError("Same original evidence identity has conflicting completed verification")
        for row in projection:
            blob = self._blob(row)
            parent = _open_directory(blob.parent, "Verified original CAS", create=True)
            try:
                if blob.exists() or blob.is_symlink():
                    # Occupied partial/corrupt CAS must never be overwritten into trust.
                    if sha256_file(blob, reject_symlink_parents=True) != row["sha256"] or blob.stat().st_size != row["bytes"]:
                        raise ValueError("Verified original CAS member is corrupt")
                    continue
                temporary = ".body-" + secrets.token_hex(16)
                try:
                    _copy_exact(Path(original) / row["relativePath"], Path(temporary), row,
                                destination_directory=parent)
                    try:
                        os.link(temporary, blob.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
                    except FileExistsError:
                        if sha256_file(blob, reject_symlink_parents=True) != row["sha256"]:
                            raise ValueError("Concurrent original CAS publication differs")
                    self.stats["writtenBytes"] += row["bytes"]
                finally:
                    try:
                        os.unlink(temporary, dir_fd=parent)
                    except FileNotFoundError:
                        pass
            finally:
                os.close(parent)
        if regular_file_inventory(original, allow_empty=True) != projection:
            raise ValueError("Original projection changed during persistent verification")
        envelope = {"record": record, "mac": hmac.new(self.key, canonical_json_bytes(record),
                                                       hashlib.sha256).hexdigest()}
        parent = _open_directory(path.parent, "Verified original records", create=True)
        temporary = ".seal-" + secrets.token_hex(16)
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=parent)
            with os.fdopen(descriptor, "wb") as output:
                output.write(canonical_json_bytes(envelope))
                output.flush()
                os.fsync(output.fileno())
            try:
                os.link(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
            except FileExistsError:
                if self.read(locator) != record:
                    raise ValueError("Same original evidence identity has conflicting concurrent verification")
        finally:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass
            os.close(parent)


def runtime_original_cache():
    # Windows retains the fully authenticated cold path. No unsafe authority
    # ACL approximation or portable cache seal is accepted there.
    if os.name == "nt":
        return None
    session = _VERIFICATION_SESSION.get()
    if session is None:
        return RuntimeOriginalCache()
    with session["lock"]:
        if "persistentOriginals" not in session:
            session["persistentOriginals"] = RuntimeOriginalCache()
        else:
            if session["persistentOriginals"].policy != _source_identity():
                raise ValueError("Original verification source/policy changed within the verification session")
        return session["persistentOriginals"]
