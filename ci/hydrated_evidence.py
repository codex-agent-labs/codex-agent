"""Untrusted content-addressed storage for freshly qualified reference bytes.

No receipts, locators, policy decisions or private verification seals are cached.
The caller must obtain each expected hash through its normal authentication gate.
"""
from pathlib import Path
import os
import uuid
import subprocess

from products.inventory import require_sha256, sha256_file, _open_directory, _is_windows, _windows_directory_path
from runtime_reference_transport import _copy_exact


def root():
    value = os.environ.get("CODEX_AGENT_HYDRATED_EVIDENCE")
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("Hydrated evidence root must be absolute")
    return path


def blob(record):
    base = root()
    digest = require_sha256(record["sha256"], "Qualified evidence SHA")[7:]
    return None if base is None else base / "blobs" / digest[:2] / digest


def copy(record, destination):
    """Cache hits still hash every consumed byte; occupied corruption fails closed."""
    path = blob(record)
    if path is None or not path.exists() and not path.is_symlink():
        return False
    _copy_exact(path, Path(destination), record)
    return True


def retain(record, source):
    path = blob(record)
    if path is None:
        return
    if path.exists() or path.is_symlink():
        if path.stat().st_size != record["bytes"] or sha256_file(path, reject_symlink_parents=True) != record["sha256"]:
            raise ValueError("Occupied hydrated evidence differs from its qualified identity")
        return
    parent = None
    if _is_windows():
        _windows_directory_path(path.parent, "Hydrated evidence parent", create=True)
    else:
        parent = _open_directory(path.parent, "Hydrated evidence parent", create=True)
    temporary = path.with_name(".pending-" + uuid.uuid4().hex)
    try:
        _copy_exact(Path(source), temporary, record, destination_directory=parent)
        try:
            if parent is None:
                _windows_directory_path(path.parent, "Hydrated evidence parent")
                os.rename(temporary, path)  # Windows atomically rejects an existing target.
            else:
                os.link(temporary.name, path.name, src_dir_fd=parent, dst_dir_fd=parent,
                        follow_symlinks=False)
        except FileExistsError:
            if path.stat().st_size != record["bytes"] or sha256_file(path, reject_symlink_parents=True) != record["sha256"]:
                raise ValueError("Concurrent hydrated evidence differs from its qualified identity")
    finally:
        try:
            if parent is None:
                temporary.unlink()
            else:
                os.unlink(temporary.name, dir_fd=parent)
        except FileNotFoundError:
            pass
        if parent is not None:
            os.close(parent)


def hosted(mode, references, directory, *, selected_paths=None):
    """Storage only, called after the enclosing reference manifest authenticates."""
    backend = os.environ.get("CODEX_AGENT_HOSTED_CACHE_BACKEND")
    if backend is None:
        return
    from runtime_reference_transport import validate_original_references
    references = validate_original_references(references)
    sources = {source["relativePath"] for source in references["sources"]}
    records = [row for row in references["references"] if row["source"] in sources
               and row["relativePath"].startswith(row["source"] + "/")
               and (selected_paths is None or row['relativePath'] in selected_paths)]
    hosted_records(mode, records, directory)


def hosted_records(mode, records, directory, *, already_compressed=False):
    """Cache exact body identities already selected by the authenticated caller."""
    backend = os.environ.get("CODEX_AGENT_HOSTED_CACHE_BACKEND")
    if backend is None:
        return
    from products.inventory import write_canonical_json
    manifest = Path(directory) / ("cache-" + mode + "-manifest.json")
    write_canonical_json(manifest, [{"sha256": row["sha256"], "bytes": row["bytes"],
        **({"gzipLevel": 0} if already_compressed else {})} for row in records])
    subprocess.run([os.environ["CODEX_AGENT_CACHE_NODE"], backend], check=True,
        env={**os.environ, "INPUT_MODE": mode, "INPUT_ROOT": str(root()),
             "INPUT_MANIFEST": str(manifest), "INPUT_REPORT": str(Path(directory) / ("cache-" + mode + ".json"))})
