from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TypeAlias
from urllib.parse import urlsplit

from ._enums import (
    McpAuthentication,
    McpAuthStatus,
    McpEnvironmentSource,
    McpToolApproval,
    McpToolExposureSurface,
    ResourceOrigin,
)


def _mapping(values: Mapping[str, object] | None) -> Mapping[str, object] | None:
    return None if values is None else MappingProxyType(dict(values))


def _not_blank(value: str, name: str) -> None:
    if not value or value.isspace():
        raise ValueError(f"{name} must not be blank")


def _safe_http_url(value: str) -> bool:
    if any(character.isspace() or ord(character) < 32 for character in value):
        return False
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        _ = parsed.port
    except ValueError:
        return False
    if not host or parsed.username is not None or parsed.password is not None:
        return False
    if ":" in host:
        if any(character not in "0123456789abcdefABCDEF:." for character in host):
            return False
    else:
        index = 0
        while index < len(host):
            character = host[index]
            if character.isascii() and (character.isalnum() or character in "-._~!$&'()*+,;="):
                index += 1
                continue
            if (
                character == "%"
                and index + 2 < len(host)
                and all(value in "0123456789abcdefABCDEF" for value in host[index + 1 : index + 3])
            ):
                index += 3
                continue
            return False
    if parsed.scheme == "https":
        return True
    return parsed.scheme == "http" and host.lower() in {"localhost", "127.0.0.1", "::1"}


@dataclass(frozen=True, slots=True)
class McpEnvironmentVariable:
    """An environment variable forwarded to an MCP server."""

    name: str
    source: McpEnvironmentSource | None = None

    def __post_init__(self) -> None:
        _not_blank(self.name, "name")


@dataclass(frozen=True, slots=True)
class McpOauthConfiguration:
    """Optional OAuth settings for an MCP server."""

    client_id: str | None = None
    callback_port: int | None = None

    def __post_init__(self) -> None:
        if self.callback_port is not None and not 1 <= self.callback_port <= 65535:
            raise ValueError("callback_port must be between 1 and 65535")


@dataclass(frozen=True, slots=True)
class McpToolConfiguration:
    """Per-tool MCP approval settings."""

    approval: McpToolApproval | None = None


@dataclass(frozen=True, slots=True)
class McpHttpTransport:
    """An HTTP MCP transport."""

    url: str
    bearer_token_environment_variable: str | None = None
    headers: Mapping[str, str] | None = None
    environment_headers: Mapping[str, str] | None = None
    headers_helper: str | None = None

    def __post_init__(self) -> None:
        if not _safe_http_url(self.url):
            raise ValueError("url must use HTTPS or a loopback HTTP address")
        if self.bearer_token_environment_variable is not None:
            _not_blank(
                self.bearer_token_environment_variable,
                "bearer_token_environment_variable",
            )
        if self.headers_helper is not None:
            _not_blank(self.headers_helper, "headers_helper")
        object.__setattr__(self, "headers", _mapping(self.headers))
        object.__setattr__(self, "environment_headers", _mapping(self.environment_headers))


@dataclass(frozen=True, slots=True)
class McpStdioTransport:
    """A subprocess MCP transport."""

    command: str
    arguments: Sequence[str] = ()
    working_directory: str | None = None
    environment: Mapping[str, str] | None = None
    forwarded_environment: Sequence[McpEnvironmentVariable] = ()

    def __post_init__(self) -> None:
        _not_blank(self.command, "command")
        object.__setattr__(self, "arguments", tuple(self.arguments))
        object.__setattr__(self, "environment", _mapping(self.environment))
        object.__setattr__(self, "forwarded_environment", tuple(self.forwarded_environment))


McpTransport: TypeAlias = McpHttpTransport | McpStdioTransport


@dataclass(frozen=True, slots=True)
class McpServerConfiguration:
    """The full immutable configuration of an MCP server."""

    name: str
    transport: McpTransport
    authentication: McpAuthentication | None = None
    environment_id: str = "local"
    is_enabled: bool = True
    is_required: bool = False
    supports_parallel_tool_calls: bool = False
    omit_tools_from: Sequence[McpToolExposureSurface] | None = None
    startup_timeout_seconds: float | None = None
    tool_timeout_seconds: float | None = None
    default_tool_approval: McpToolApproval | None = None
    enabled_tools: Sequence[str] | None = None
    disabled_tools: Sequence[str] | None = None
    scopes: Sequence[str] | None = None
    oauth: McpOauthConfiguration | None = None
    oauth_resource: str | None = None
    tools: Mapping[str, McpToolConfiguration] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", self.name):
            raise ValueError("name may contain only ASCII letters, numbers, '-', and '_'")
        if not isinstance(self.transport, (McpHttpTransport, McpStdioTransport)):
            raise TypeError("transport must be an MCP transport")
        _not_blank(self.environment_id, "environment_id")
        for name, value in (
            ("startup_timeout_seconds", self.startup_timeout_seconds),
            ("tool_timeout_seconds", self.tool_timeout_seconds),
        ):
            if value is not None and (not math.isfinite(value) or value <= 0.0 or value >= 2**64):
                raise ValueError(f"{name} must be finite, positive, and below 2^64")
        if isinstance(self.transport, McpStdioTransport) and (
            self.authentication is not None
            or self.oauth is not None
            or self.oauth_resource is not None
        ):
            raise ValueError("stdio transports do not support authentication or OAuth")
        if (
            isinstance(self.transport, McpHttpTransport)
            and self.transport.headers_helper is not None
            and self.environment_id != "local"
        ):
            raise ValueError("HTTP headers helpers are supported only for local servers")
        for name in ("omit_tools_from", "enabled_tools", "disabled_tools", "scopes"):
            values = getattr(self, name)
            object.__setattr__(self, name, None if values is None else tuple(values))
        object.__setattr__(self, "tools", MappingProxyType(dict(self.tools)))


@dataclass(frozen=True, slots=True)
class McpServer:
    """An installed or discoverable MCP server."""

    name: str
    display_name: str
    auth_status: McpAuthStatus
    configuration: McpServerConfiguration | None = None
    origin: ResourceOrigin = ResourceOrigin.UNKNOWN
    can_remove: bool = False

    @property
    def is_authorized(self) -> bool:
        return self.auth_status in {McpAuthStatus.BEARER_TOKEN, McpAuthStatus.OAUTH}
