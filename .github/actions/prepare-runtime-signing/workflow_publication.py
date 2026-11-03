"""Derive the exact reviewed reusable-workflow closure for protected publication.

This prepares immutable control bytes, not authorization. The protected owner
must approve the source and publish the complete closure in one Git commit.
"""
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "ci"))
from products.inventory import git_regular_blob_bytes, require_relative_path, sha256_bytes

PROJECT = "codex-agent-labs/codex-agent/"
PROTECTED_REF = "reuse-authority"
ENTRYPOINT = ".github/workflows/product-validation.yml"


def reviewed_workflow_closure(repository, revision, *, entrypoints=(ENTRYPOINT,)):
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Workflow publication needs an exact approved source revision")
    pending, files = list(entrypoints), {}
    while pending:
        path = pending.pop()
        if path in files:
            continue
        require_relative_path(path, "Reviewed workflow")
        if not re.fullmatch(r"\.github/workflows/[a-z0-9-]+\.yml", path):
            raise ValueError("Reviewed workflow is outside the fixed publication boundary")
        if len(files) >= 128:
            raise ValueError("Reviewed workflow closure exceeds bound")
        raw = git_regular_blob_bytes(Path(repository), revision, path, max_bytes=1024 * 1024)
        if sum(map(len, files.values())) + len(raw) > 16 * 1024 * 1024:
            raise ValueError("Reviewed workflow closure bytes exceed bound")
        files[path] = raw
        for value in re.findall(r"^\s*(?:-\s+)?uses:[ \t]*([^\r\n]*)$", raw.decode("utf-8"), re.MULTILINE):
            value = value.split("#", 1)[0].strip()
            if "${{" in value or not value or value[0] in "*&>|":
                raise ValueError("Dynamic or aliased workflow/action references cannot be published")
            if value[0] in "\"'":
                if len(value) < 2 or value[-1] != value[0]:
                    raise ValueError("Malformed quoted workflow/action reference")
                value = value[1:-1]
            if any(character.isspace() for character in value):
                raise ValueError("Workflow/action reference must be a single literal")
            if value.startswith("./.github/workflows/"):
                pending.append(value[2:])
            elif value.startswith(PROJECT):
                member, separator, ref = value[len(PROJECT):].partition("@")
                if not separator or ref != PROTECTED_REF:
                    raise ValueError("Reviewed project execution must use the protected stable reference")
                if member.startswith(".github/workflows/"):
                    pending.append(member)
    return dict(sorted(files.items()))


def publication_inventory(files):
    """No publisher self-identity or incidental execution data in the closure."""
    return [{"path": path, "bytes": len(raw), "sha256": sha256_bytes(raw)}
            for path, raw in sorted(files.items())]
