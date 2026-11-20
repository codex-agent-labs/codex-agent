from __future__ import annotations

import os
from pathlib import Path


def _required_file(variable: str) -> Path:
    value = os.environ.get(variable)
    if not value:
        raise RuntimeError(f"{variable} must name a declared artifact file")
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise RuntimeError(f"{variable} is not a file: {path}")
    return path


def canonical_api_report() -> Path:
    return _required_file("CODEX_AGENT_CANONICAL_API_REPORT")


def c_abi_bootstrap_evidence() -> Path:
    return _required_file("CODEX_AGENT_C_ABI_BOOTSTRAP_EVIDENCE")


def c_sdk_root() -> Path:
    value = os.environ.get("CODEX_AGENT_C_SDK_ROOT")
    if not value:
        raise RuntimeError("CODEX_AGENT_C_SDK_ROOT must name a declared C SDK root")
    root = Path(value).expanduser().resolve()
    header = root / "include" / "codex_agent.h"
    if not root.is_dir() or not header.is_file():
        raise RuntimeError(
            "CODEX_AGENT_C_SDK_ROOT must contain include/codex_agent.h: "
            f"{root}"
        )
    return root


def c_header() -> Path:
    return c_sdk_root() / "include" / "codex_agent.h"


def c_include_directory() -> Path:
    return c_sdk_root() / "include"


def real_library() -> Path:
    return _required_file("CODEX_AGENT_LIBRARY")
