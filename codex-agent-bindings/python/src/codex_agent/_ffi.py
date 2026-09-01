from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import stat
import tempfile
from importlib.resources import files
from pathlib import Path
from typing import Any, Callable

from ._errors import Status, UnsupportedAbiError, check


ABI_VERSION = (1 << 24) | (13 << 16)
MINIMUM_ABI_VERSION = 1 << 24

_IDENTITY_KEYS = {
    "appServerVersion",
    "buildInputDigest",
    "cAbiVersion",
    "componentId",
    "contractComponentDigest",
    "contractDigest",
    "runtimeCompatibilityVersion",
    "schemaVersion",
    "target",
}
_SHA256_PREFIX = "sha256:"
_SNAPSHOT_DIRECTORIES: list[tempfile.TemporaryDirectory[str]] = []

Handle = ctypes.c_void_p
HandlePointer = ctypes.POINTER(Handle)


class StringView(ctypes.Structure):
    _fields_ = [("data", ctypes.POINTER(ctypes.c_uint8)), ("size", ctypes.c_size_t)]


class ClientInfoStruct(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("name", StringView),
        ("title", StringView),
        ("version", StringView),
    ]


class HostOptionsStruct(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("bundle_directory", StringView),
        ("data_directory", StringView),
        ("client_info", ClientInfoStruct),
    ]


class PathWorkspaceSelectionStruct(ctypes.Structure):
    _fields_ = [("struct_size", ctypes.c_uint32), ("path", StringView)]


class ConversationOpenOptionsStruct(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("has_conversation_id", ctypes.c_int32),
        ("conversation_id", StringView),
        ("has_approval_preset", ctypes.c_int32),
        ("approval_preset", ctypes.c_int32),
        ("has_service_tier", ctypes.c_int32),
        ("service_tier", StringView),
    ]


OperationCallback = ctypes.CFUNCTYPE(None, Handle, Handle, ctypes.c_void_p)
StateCallback = ctypes.CFUNCTYPE(
    None,
    Handle,
    Handle,
    ctypes.c_int32,
    Handle,
    ctypes.c_int32,
    ctypes.c_void_p,
)


def utf8_view(value: str) -> tuple[StringView, Any]:
    encoded = value.encode("utf-8", errors="strict")
    if not encoded:
        return StringView(None, 0), None
    backing = (ctypes.c_uint8 * len(encoded)).from_buffer_copy(encoded)
    return StringView(backing, len(encoded)), backing


def null_view() -> StringView:
    return StringView(None, 0)


def current_classifier() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    architectures = {
        "arm64": "arm64",
        "aarch64": "arm64",
        "x86_64": "x64",
        "amd64": "x64",
    }
    architecture = architectures.get(machine)
    if system == "darwin" and architecture is not None:
        return f"macos-{architecture}"
    if system == "linux" and architecture is not None:
        return f"linux-{architecture}"
    if system == "windows" and architecture == "x64":
        return "windows-x64"
    raise OSError(f"unsupported Codex Agent desktop host: {system}-{machine}")


def _library_name(classifier: str) -> str:
    if classifier.startswith("macos-"):
        return "libcodex_agent.dylib"
    if classifier.startswith("linux-"):
        return "libcodex_agent.so"
    return "codex_agent.dll"


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _strict_json(data: bytes, description: str) -> dict[str, Any]:
    try:
        value = json.loads(data, object_pairs_hook=_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise OSError(f"invalid {description}: {error}") from error
    if not isinstance(value, dict):
        raise OSError(f"invalid {description}: expected an object")
    return value


def _canonical_json(value: dict[str, Any], final_lf: bool) -> bytes:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return encoded + (b"\n" if final_lf else b"")


def _exact_keys(value: dict[str, Any], keys: set[str], description: str) -> None:
    if set(value) != keys:
        raise OSError(f"invalid {description}: unexpected fields")


def _sha256(value: Any, description: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith(_SHA256_PREFIX)
        or len(value) != 71
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise OSError(f"invalid {description}")
    return value


def _integer(value: Any, description: str, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise OSError(f"invalid {description}")
    return value


def _semver(value: Any, description: str) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise OSError(f"invalid {description}")
    parts = value.split(".")
    if (
        len(parts) != 3
        or any(not part.isascii() or not part.isdigit() for part in parts)
        or any(len(part) > 1 and part.startswith("0") for part in parts)
    ):
        raise OSError(f"invalid {description}")
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


def _range(value: Any, description: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    if not isinstance(value, str) or len(parts := value.split(" ")) != 2:
        raise OSError(f"invalid {description}")
    if not parts[0].startswith(">=") or not parts[1].startswith("<"):
        raise OSError(f"invalid {description}")
    lower = _semver(parts[0][2:], description)
    upper = _semver(parts[1][1:], description)
    if lower >= upper:
        raise OSError(f"invalid {description}")
    return lower, upper


def _in_range(version: Any, bounds: tuple[tuple[int, int, int], tuple[int, int, int]], description: str) -> bool:
    parsed = _semver(version, description)
    return bounds[0] <= parsed < bounds[1]


def _validate_compatibility(data: bytes) -> dict[str, Any]:
    root = _strict_json(data, "SDK compatibility declaration")
    _exact_keys(root, {"schemaVersion", "sdkVersion", "contract", "runtime", "platformRuntime"}, "SDK compatibility declaration")
    if _integer(root["schemaVersion"], "SDK compatibility schema") != 1:
        raise OSError("unsupported SDK compatibility schema")
    _semver(root["sdkVersion"], "SDK version")
    contract = root["contract"]
    runtime = root["runtime"]
    platform_runtime = root["platformRuntime"]
    if not isinstance(contract, dict) or not isinstance(runtime, dict) or not isinstance(platform_runtime, dict):
        raise OSError("invalid SDK compatibility declaration")
    _exact_keys(contract, {"version", "digest"}, "Contract compatibility")
    _semver(contract["version"], "Contract version")
    _sha256(contract["digest"], "Contract digest")
    _exact_keys(
        runtime,
        {
            "compatibleReleaseRange", "compatibleRuntimeCompatibilityRange",
            "requiredIdentitySchema", "requiredContractDigest", "requiredAbiMajor",
            "minimumAbiMinor", "defaultRuntimeVersion", "defaultManifestSha256",
            "embeddedVariants",
        },
        "Runtime compatibility",
    )
    release_range = _range(runtime["compatibleReleaseRange"], "Runtime release range")
    _range(runtime["compatibleRuntimeCompatibilityRange"], "Runtime compatibility range")
    if _integer(runtime["requiredIdentitySchema"], "required identity schema") != 1 or _integer(runtime["requiredAbiMajor"], "required ABI major") != 1:
        raise OSError("unsupported Runtime identity or ABI major")
    _integer(runtime["minimumAbiMinor"], "minimum ABI minor")
    if _sha256(runtime["requiredContractDigest"], "required Contract digest") != contract["digest"]:
        raise OSError("SDK compatibility Contract digest mismatch")
    _sha256(runtime["defaultManifestSha256"], "default Runtime manifest digest")
    if not _in_range(runtime["defaultRuntimeVersion"], release_range, "default Runtime version"):
        raise OSError("default Runtime version is outside its compatible range")
    variants = runtime["embeddedVariants"]
    if not isinstance(variants, list):
        raise OSError("invalid embedded Runtime variants")
    expected_targets = ["linux-arm64", "linux-x64", "macos-arm64", "macos-x64", "windows-x64"]
    if [variant.get("target") if isinstance(variant, dict) else None for variant in variants] != expected_targets:
        raise OSError("SDK compatibility must contain exactly five sorted Runtime targets")
    for variant in variants:
        _exact_keys(variant, {"target", "componentId", "bundleSha256", "manifestSha256", "runtimeLibrarySha256"}, "embedded Runtime variant")
        for key in ("componentId", "bundleSha256", "manifestSha256", "runtimeLibrarySha256"):
            _sha256(variant[key], f"embedded Runtime {key}")
    if len({variant["componentId"] for variant in variants}) != len(variants):
        raise OSError("embedded Runtime component IDs must be unique")
    if len({variant["manifestSha256"] for variant in variants}) != len(variants):
        raise OSError("embedded Runtime manifest digests must be unique")
    _exact_keys(platform_runtime, {"android", "ios"}, "platform Runtime compatibility")
    for name in ("android", "ios"):
        value = platform_runtime[name]
        if not isinstance(value, dict):
            raise OSError(f"invalid {name} Runtime compatibility")
        _exact_keys(value, {"owner", "desktopRuntimeApplicable"}, f"{name} Runtime compatibility")
        if value["owner"] != "sdk" or value["desktopRuntimeApplicable"] is not False:
            raise OSError(f"invalid {name} Runtime ownership")
    if data != _canonical_json(root, True):
        raise OSError("SDK compatibility declaration is not canonical JSON")
    return root


def _load_compatibility() -> dict[str, Any]:
    resource = files("codex_agent").joinpath("native", "sdk-compatibility.json")
    try:
        return _validate_compatibility(resource.read_bytes())
    except FileNotFoundError as error:
        raise OSError("Codex Agent SDK compatibility declaration is missing") from error


def _is_link_or_reparse(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _validate_absolute_regular_path(path: Path, description: str) -> Path:
    if not path.is_absolute():
        raise ValueError(f"{description} must be an absolute path")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError as error:
            raise FileNotFoundError(f"{description} does not exist: {path}") from error
        if _is_link_or_reparse(metadata):
            raise OSError(f"{description} must not contain symlinks or reparse points: {path}")
    if not stat.S_ISREG(path.lstat().st_mode):
        raise FileNotFoundError(f"{description} is not a regular file: {path}")
    return path


def _snapshot_embedded_library(path: Path, expected_digest: str) -> Path:
    _validate_absolute_regular_path(path, "embedded Codex Agent Runtime library")
    directory = tempfile.TemporaryDirectory(prefix="codex-agent-runtime-")
    _SNAPSHOT_DIRECTORIES.append(directory)
    destination = Path(directory.name) / path.name
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    digest = hashlib.sha256()
    try:
        with os.fdopen(os.open(path, flags), "rb") as source, destination.open("xb") as output:
            while block := source.read(1024 * 1024):
                digest.update(block)
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
        if _SHA256_PREFIX + digest.hexdigest() != expected_digest:
            raise OSError("embedded Codex Agent Runtime library digest mismatch")
        destination.chmod(stat.S_IRUSR)
        return destination
    except Exception:
        _SNAPSHOT_DIRECTORIES.remove(directory)
        directory.cleanup()
        raise


def _validate_runtime_identity(
    identity: dict[str, Any], compatibility: dict[str, Any], classifier: str, embedded: bool
) -> None:
    _exact_keys(identity, _IDENTITY_KEYS, "Runtime identity")
    runtime = compatibility["runtime"]
    if _integer(identity["schemaVersion"], "Runtime identity schema") != runtime["requiredIdentitySchema"]:
        raise OSError("Runtime identity schema mismatch")
    for key in ("componentId", "contractDigest", "contractComponentDigest", "buildInputDigest"):
        _sha256(identity[key], f"Runtime identity {key}")
    if identity["target"] != classifier:
        raise OSError("Runtime identity target mismatch")
    if identity["contractDigest"] != runtime["requiredContractDigest"]:
        raise OSError("Runtime identity Contract mismatch")
    abi = _semver(identity["cAbiVersion"], "Runtime identity ABI")
    if abi[0] != runtime["requiredAbiMajor"] or abi[1] < runtime["minimumAbiMinor"]:
        raise OSError("Runtime identity ABI is incompatible")
    if not _in_range(identity["runtimeCompatibilityVersion"], _range(runtime["compatibleRuntimeCompatibilityRange"], "Runtime compatibility range"), "Runtime compatibility version"):
        raise OSError("Runtime compatibility version is unsupported")
    _semver(identity["appServerVersion"], "Runtime app-server version")
    if embedded:
        variant = next(item for item in runtime["embeddedVariants"] if item["target"] == classifier)
        if identity["componentId"] != variant["componentId"]:
            raise OSError("embedded Runtime component mismatch")


def _read_runtime_identity(library: Any) -> dict[str, Any]:
    function = getattr(library, "codex_agent_runtime_identity")
    function.argtypes = [ctypes.POINTER(ctypes.c_char), ctypes.POINTER(ctypes.c_size_t)]
    function.restype = ctypes.c_int32
    required = ctypes.c_size_t()
    if int(function(None, ctypes.byref(required))) != Status.BUFFER_TOO_SMALL or required.value < 2:
        raise OSError("Runtime identity size query failed")
    buffer = (ctypes.c_char * required.value)()
    capacity = ctypes.c_size_t(required.value)
    if int(function(buffer, ctypes.byref(capacity))) != Status.OK or capacity.value != required.value:
        raise OSError("Runtime identity read failed")
    raw = bytes(buffer)
    if raw[-1:] != b"\0" or b"\0" in raw[:-1]:
        raise OSError("Runtime identity is not a canonical NUL-terminated string")
    identity = _strict_json(raw[:-1], "Runtime identity")
    if raw[:-1] != _canonical_json(identity, False):
        raise OSError("Runtime identity is not canonical JSON")
    return identity


def resolve_library_path(explicit: str | os.PathLike[str] | None = None) -> Path:
    if explicit is not None:
        raw = os.fspath(explicit)
        if not raw.strip():
            raise ValueError("Codex Agent native library path must not be blank")
        configured: str | os.PathLike[str] | None = raw
    elif "CODEX_AGENT_LIBRARY" in os.environ:
        configured = os.environ["CODEX_AGENT_LIBRARY"]
        if not configured.strip():
            raise ValueError("CODEX_AGENT_LIBRARY must not be blank")
    else:
        configured = None
    if configured is not None:
        path = Path(configured)
    else:
        classifier = current_classifier()
        path = Path(
            str(
                files("codex_agent").joinpath(
                    "native", classifier, _library_name(classifier)
                )
            )
        )
    return _validate_absolute_regular_path(path, "Codex Agent C SDK library")


class NativeLibrary:
    """Strict ctypes declarations for the Python-owned portion of ABI 1.13."""

    def __init__(self, library: Any) -> None:
        self.library = library
        self._declare_all()
        actual = int(self.library.codex_agent_abi_version())
        compatible = int(self.library.codex_agent_abi_is_compatible(ABI_VERSION))
        if compatible != 1 or actual < MINIMUM_ABI_VERSION or actual >> 24 != 1:
            raise UnsupportedAbiError(
                f"Codex Agent ABI 1.13 is required; loaded 0x{actual:08x}"
            )

    @classmethod
    def load(cls, path: str | os.PathLike[str] | None = None) -> NativeLibrary:
        compatibility = _load_compatibility()
        classifier = current_classifier()
        library_path = resolve_library_path(path)
        embedded = path is None and "CODEX_AGENT_LIBRARY" not in os.environ
        if embedded:
            variant = next(item for item in compatibility["runtime"]["embeddedVariants"] if item["target"] == classifier)
            library_path = _snapshot_embedded_library(library_path, variant["runtimeLibrarySha256"])
        library = ctypes.CDLL(str(library_path))
        identity = _read_runtime_identity(library)
        _validate_runtime_identity(identity, compatibility, classifier, embedded)
        abi = _semver(identity["cAbiVersion"], "Runtime identity ABI")
        encoded_abi = (abi[0] << 24) | (abi[1] << 16) | abi[2]
        abi_version = getattr(library, "codex_agent_abi_version")
        abi_version.argtypes = []
        abi_version.restype = ctypes.c_uint32
        if int(abi_version()) != encoded_abi:
            raise OSError("Runtime identity ABI disagrees with the loaded library")
        return cls(library)

    def function(self, name: str) -> Any:
        return getattr(self.library, name)

    def call(self, name: str, *args: Any, allow: tuple[Status, ...] = ()) -> Status:
        return check(int(self.function(name)(*args)), name, allow=allow)

    def copy_string(
        self, name: str, *prefix: Any, nullable: bool = False
    ) -> str | None:
        function = self.function(name)
        required = ctypes.c_size_t()
        status = check(
            int(function(*prefix, None, 0, ctypes.byref(required))),
            name,
            allow=(
                (Status.BUFFER_TOO_SMALL, Status.NOT_READY)
                if nullable
                else (Status.BUFFER_TOO_SMALL,)
            ),
        )
        if status is Status.NOT_READY:
            return None
        if required.value == 0:
            return ""
        buffer = (ctypes.c_uint8 * required.value)()
        self.call(name, *prefix, buffer, required.value, ctypes.byref(required))
        return bytes(buffer[: required.value]).decode("utf-8", errors="strict")

    def _declare(
        self, name: str, arguments: list[Any], result: Any = ctypes.c_int32
    ) -> None:
        function = getattr(self.library, name)  # Missing required symbols fail closed.
        function.argtypes = arguments
        function.restype = result

    def _declare_all(self) -> None:
        h = Handle
        hp = HandlePointer
        p_i32 = ctypes.POINTER(ctypes.c_int32)
        p_i64 = ctypes.POINTER(ctypes.c_int64)
        p_size = ctypes.POINTER(ctypes.c_size_t)
        bytes_out = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t, p_size]

        self._declare("codex_agent_abi_version", [], ctypes.c_uint32)
        self._declare(
            "codex_agent_abi_is_compatible", [ctypes.c_uint32], ctypes.c_int32
        )
        self._declare(
            "codex_agent_runtime_identity",
            [ctypes.POINTER(ctypes.c_char), ctypes.POINTER(ctypes.c_size_t)],
        )
        self._declare("codex_agent_context_create", [hp])
        self._declare("codex_agent_context_destroy", [hp])
        self._declare(
            "codex_agent_host_create", [h, ctypes.POINTER(HostOptionsStruct), hp]
        )
        self._declare("codex_agent_host_release", [h, hp])
        self._declare(
            "codex_agent_host_start", [h, h, OperationCallback, ctypes.c_void_p, hp]
        )
        self._declare(
            "codex_agent_host_select_workspace",
            [
                h,
                h,
                ctypes.POINTER(PathWorkspaceSelectionStruct),
                OperationCallback,
                ctypes.c_void_p,
                hp,
            ],
        )
        self._declare(
            "codex_agent_host_close", [h, h, OperationCallback, ctypes.c_void_p, hp]
        )
        self._declare("codex_agent_host_state_get", [h, h, hp])
        self._declare(
            "codex_agent_host_state_subscribe",
            [h, h, StateCallback, ctypes.c_void_p, hp],
        )
        self._declare("codex_agent_host_state_kind", [h, h, p_i32])
        self._declare("codex_agent_host_state_agent", [h, h, h, hp])
        self._declare("codex_agent_host_state_failure", [h, h, hp])
        self._declare("codex_agent_host_state_has_workspace", [h, h, p_i32])
        self._declare("codex_agent_host_state_workspace_path_copy", [h, h, *bytes_out])
        self._declare(
            "codex_agent_host_state_workspace_display_name_copy", [h, h, *bytes_out]
        )
        self._declare("codex_agent_host_state_requirement_reason", [h, h, p_i32])
        self._declare(
            "codex_agent_host_state_requirement_message_copy", [h, h, *bytes_out]
        )

        self._declare("codex_agent_agent_release", [h, hp])
        self._declare("codex_agent_agent_conversations", [h, h, hp])
        self._declare("codex_agent_agent_authentication", [h, h, hp])
        self._declare("codex_agent_agent_interactions", [h, h, hp])
        self._declare("codex_agent_agent_integration_authorization", [h, h, hp])
        self._declare("codex_agent_agent_models", [h, h, hp])
        self._declare("codex_agent_agent_skills", [h, h, hp])
        self._declare("codex_agent_agent_hooks", [h, h, hp])
        self._declare("codex_agent_agent_plugins", [h, h, hp])
        self._declare("codex_agent_agent_connectors", [h, h, hp])
        self._declare("codex_agent_agent_mcp_servers", [h, h, hp])
        self._declare("codex_agent_agent_workspace", [h, h, hp])
        self._declare("codex_agent_workspace_destroy", [h, hp])
        self._declare("codex_agent_workspace_path_copy", [h, h, *bytes_out])
        self._declare("codex_agent_workspace_display_name_copy", [h, h, *bytes_out])

        self._declare("codex_agent_conversations_release", [h, hp])
        self._declare("codex_agent_conversations_active_get", [h, h, hp])
        self._declare(
            "codex_agent_conversations_active_subscribe",
            [h, h, StateCallback, ctypes.c_void_p, hp],
        )
        self._declare("codex_agent_active_conversation", [h, h, h, hp])
        self._declare(
            "codex_agent_conversations_list",
            [h, h, OperationCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_conversations_read",
            [h, h, h, OperationCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_conversations_rename",
            [
                h,
                h,
                h,
                ctypes.POINTER(StringView),
                OperationCallback,
                ctypes.c_void_p,
                hp,
            ],
        )
        self._declare(
            "codex_agent_conversations_delete",
            [h, h, h, OperationCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_conversations_open",
            [
                h,
                h,
                ctypes.POINTER(ConversationOpenOptionsStruct),
                OperationCallback,
                ctypes.c_void_p,
                hp,
            ],
        )

        self._declare("codex_agent_conversation_release", [h, hp])
        self._declare("codex_agent_conversation_is_same", [h, h, h, p_i32])
        self._declare(
            "codex_agent_conversation_send",
            [h, h, ctypes.POINTER(StringView), OperationCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_conversation_send_request",
            [h, h, h, OperationCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_conversation_run_shell_command",
            [h, h, ctypes.POINTER(StringView), OperationCallback, ctypes.c_void_p, hp],
        )
        for name in ("reload", "cancel_turn", "close"):
            self._declare(
                f"codex_agent_conversation_{name}",
                [h, h, OperationCallback, ctypes.c_void_p, hp],
            )
        self._declare("codex_agent_conversation_state_get", [h, h, hp])
        self._declare(
            "codex_agent_conversation_state_subscribe",
            [h, h, StateCallback, ctypes.c_void_p, hp],
        )
        self._declare("codex_agent_conversation_state_status", [h, h, p_i32])
        self._declare("codex_agent_conversation_state_failure", [h, h, hp])
        self._declare("codex_agent_conversation_current_messages_get", [h, h, hp])
        self._declare(
            "codex_agent_conversation_current_messages_subscribe",
            [h, h, StateCallback, ctypes.c_void_p, hp],
        )
        self._declare("codex_agent_conversation_current_messages_count", [h, h, p_size])
        self._declare(
            "codex_agent_conversation_current_messages_at", [h, h, ctypes.c_size_t, hp]
        )
        self._declare("codex_agent_conversation_active_turn_progress_get", [h, h, hp])
        self._declare(
            "codex_agent_conversation_active_turn_progress_subscribe",
            [h, h, StateCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_conversation_active_turn_progress_has_value", [h, h, p_i32]
        )
        self._declare("codex_agent_conversation_active_turn_progress_value", [h, h, hp])
        for property_name in (
            "can_start_turn",
            "can_reload",
            "can_cancel_turn",
            "can_run_shell_command",
            "is_turn_active",
        ):
            self._declare(f"codex_agent_conversation_{property_name}_get", [h, h, hp])
            self._declare(
                f"codex_agent_conversation_{property_name}_subscribe",
                [h, h, StateCallback, ctypes.c_void_p, hp],
            )
        self._declare("codex_agent_state_boolean_value", [h, h, p_i32])

        self._declare("codex_agent_operation_cancel", [h, h])
        self._declare("codex_agent_operation_result", [h, h, p_i32])
        self._declare("codex_agent_operation_failure", [h, h, hp])
        self._declare("codex_agent_operation_destroy", [h, hp])
        self._declare("codex_agent_operation_conversation", [h, h, h, hp])
        self._declare("codex_agent_operation_conversation_value", [h, h, hp])
        self._declare(
            "codex_agent_operation_conversation_summaries_count", [h, h, p_size]
        )
        self._declare(
            "codex_agent_operation_conversation_summary_at", [h, h, ctypes.c_size_t, hp]
        )
        self._declare("codex_agent_subscription_destroy", [h, hp])
        self._declare("codex_agent_snapshot_destroy", [h, hp])

        self._declare("codex_agent_failure_release", [h, hp])
        self._declare("codex_agent_failure_code_copy", [h, h, *bytes_out])
        self._declare("codex_agent_failure_message_copy", [h, h, *bytes_out])
        self._declare("codex_agent_failure_is_recoverable", [h, h, p_i32])
        self._declare(
            "codex_agent_conversation_id_create", [h, ctypes.POINTER(StringView), hp]
        )
        self._declare("codex_agent_conversation_id_destroy", [h, hp])
        self._declare("codex_agent_conversation_id_value_copy", [h, h, *bytes_out])
        self._declare("codex_agent_conversation_summary_destroy", [h, hp])
        self._declare("codex_agent_conversation_summary_conversation_id", [h, h, hp])
        self._declare("codex_agent_conversation_summary_title_copy", [h, h, *bytes_out])
        self._declare(
            "codex_agent_conversation_summary_updated_at_epoch_seconds", [h, h, p_i64]
        )

        self._declare(
            "codex_agent_turn_request_create",
            [
                h,
                ctypes.POINTER(StringView),
                ctypes.c_int32,
                ctypes.POINTER(StringView),
                ctypes.c_int32,
                ctypes.POINTER(StringView),
                ctypes.c_int32,
                ctypes.POINTER(StringView),
                ctypes.c_int32,
                ctypes.POINTER(StringView),
                ctypes.c_int32,
                p_i32,
                ctypes.c_size_t,
                ctypes.POINTER(h),
                ctypes.c_size_t,
                ctypes.c_int32,
                hp,
            ],
        )
        self._declare("codex_agent_turn_request_destroy", [h, hp])
        self._declare(
            "codex_agent_invocation_plugin_create",
            [h, ctypes.POINTER(StringView), ctypes.POINTER(StringView), hp],
        )
        self._declare("codex_agent_invocation_plugin_destroy", [h, hp])
        self._declare(
            "codex_agent_invocation_skill_create",
            [h, ctypes.POINTER(StringView), ctypes.POINTER(StringView), hp],
        )
        self._declare("codex_agent_invocation_skill_destroy", [h, hp])
        self._declare("codex_agent_invocation_from_plugin", [h, h, hp])
        self._declare("codex_agent_invocation_from_skill", [h, h, hp])
        self._declare("codex_agent_invocation_destroy", [h, hp])
        self._declare("codex_agent_invocation_kind", [h, h, p_i32])
        self._declare("codex_agent_invocation_plugin", [h, h, hp])
        self._declare("codex_agent_invocation_skill", [h, h, hp])
        for kind in ("plugin", "skill"):
            self._declare(
                f"codex_agent_invocation_{kind}_name_copy", [h, h, *bytes_out]
            )
        self._declare("codex_agent_invocation_plugin_uri_copy", [h, h, *bytes_out])
        self._declare("codex_agent_invocation_skill_path_copy", [h, h, *bytes_out])

        self._declare("codex_agent_message_destroy", [h, hp])
        for name in (
            "id",
            "client_message_id",
            "text",
            "reasoning",
            "plan",
            "shell_command",
        ):
            self._declare(f"codex_agent_message_{name}_copy", [h, h, *bytes_out])
        for name in (
            "has_client_message_id",
            "role",
            "collaboration_mode",
            "has_reasoning",
            "has_plan",
            "has_shell_command",
        ):
            self._declare(f"codex_agent_message_{name}", [h, h, p_i32])
        self._declare("codex_agent_message_exit_code", [h, h, p_i32, p_i32])
        self._declare("codex_agent_message_capabilities_count", [h, h, p_size])
        self._declare(
            "codex_agent_message_has_capability", [h, h, ctypes.c_int32, p_i32]
        )
        self._declare("codex_agent_message_invocations_count", [h, h, p_size])
        self._declare("codex_agent_message_invocation_at", [h, h, ctypes.c_size_t, hp])

        self._declare("codex_agent_conversation_value_destroy", [h, hp])
        self._declare("codex_agent_conversation_value_summary", [h, h, hp])
        self._declare("codex_agent_conversation_value_messages_count", [h, h, p_size])
        self._declare(
            "codex_agent_conversation_value_message_at", [h, h, ctypes.c_size_t, hp]
        )

        self._declare("codex_agent_turn_progress_destroy", [h, hp])
        for name in ("text", "commentary", "reasoning", "plan", "shell_output"):
            self._declare(f"codex_agent_turn_progress_{name}_copy", [h, h, *bytes_out])
        self._declare("codex_agent_turn_progress_has_plan_progress", [h, h, p_i32])
        self._declare("codex_agent_turn_progress_plan_progress", [h, h, hp])
        self._declare("codex_agent_turn_progress_shell_exit_code", [h, h, p_i32, p_i32])
        self._declare("codex_agent_turn_progress_work_activity", [h, h, p_i32, p_i32])
        self._declare("codex_agent_turn_progress_hook_activities_count", [h, h, p_size])
        self._declare(
            "codex_agent_turn_progress_hook_activity_at", [h, h, ctypes.c_size_t, hp]
        )
        self._declare("codex_agent_turn_progress_is_truncated", [h, h, p_i32])

        self._declare("codex_agent_plan_progress_destroy", [h, hp])
        self._declare("codex_agent_plan_progress_has_explanation", [h, h, p_i32])
        self._declare("codex_agent_plan_progress_explanation_copy", [h, h, *bytes_out])
        self._declare("codex_agent_plan_progress_steps_count", [h, h, p_size])
        self._declare("codex_agent_plan_progress_step_at", [h, h, ctypes.c_size_t, hp])
        self._declare("codex_agent_plan_step_destroy", [h, hp])
        self._declare("codex_agent_plan_step_text_copy", [h, h, *bytes_out])
        self._declare("codex_agent_plan_step_status", [h, h, p_i32])

        self._declare("codex_agent_hook_activity_destroy", [h, hp])
        for name in ("id", "event_name", "handler_type", "status_message"):
            self._declare(f"codex_agent_hook_activity_{name}_copy", [h, h, *bytes_out])
        self._declare("codex_agent_hook_activity_status", [h, h, p_i32])
        self._declare("codex_agent_hook_activity_has_status_message", [h, h, p_i32])
        self._declare("codex_agent_hook_activity_details_count", [h, h, p_size])
        self._declare(
            "codex_agent_hook_activity_detail_copy_at",
            [h, h, ctypes.c_size_t, *bytes_out],
        )

        for value in (
            "mcp_environment_variable",
            "mcp_oauth_configuration",
            "mcp_tool_configuration",
            "mcp_transport_http",
            "mcp_transport_stdio",
            "mcp_transport",
            "mcp_server_configuration",
            "mcp_server",
        ):
            self._declare(f"codex_agent_{value}_destroy", [h, hp])

        for name in (
            "mcp_environment_variable_name_copy",
            "mcp_oauth_configuration_client_id_copy",
            "mcp_transport_http_url_copy",
            "mcp_transport_http_bearer_token_environment_variable_copy",
            "mcp_transport_http_headers_helper_copy",
            "mcp_transport_stdio_command_copy",
            "mcp_transport_stdio_working_directory_copy",
            "mcp_server_configuration_name_copy",
            "mcp_server_configuration_environment_id_copy",
            "mcp_server_configuration_oauth_resource_copy",
            "mcp_server_name_copy",
            "mcp_server_display_name_copy",
        ):
            self._declare(f"codex_agent_{name}", [h, h, *bytes_out])
        for name in (
            "mcp_transport_http_headers_key_copy_at",
            "mcp_transport_http_headers_value_copy_at",
            "mcp_transport_http_environment_headers_key_copy_at",
            "mcp_transport_http_environment_headers_value_copy_at",
            "mcp_transport_stdio_argument_copy_at",
            "mcp_transport_stdio_environment_key_copy_at",
            "mcp_transport_stdio_environment_value_copy_at",
            "mcp_server_configuration_enabled_tool_copy_at",
            "mcp_server_configuration_disabled_tool_copy_at",
            "mcp_server_configuration_scope_copy_at",
            "mcp_server_configuration_tools_key_copy_at",
        ):
            self._declare(f"codex_agent_{name}", [h, h, ctypes.c_size_t, *bytes_out])

        for name in (
            "mcp_transport_http_has_bearer_token_environment_variable",
            "mcp_transport_http_has_headers",
            "mcp_transport_http_has_environment_headers",
            "mcp_transport_http_has_headers_helper",
            "mcp_transport_stdio_has_working_directory",
            "mcp_transport_stdio_has_environment",
            "mcp_server_configuration_is_enabled",
            "mcp_server_configuration_is_required",
            "mcp_server_configuration_supports_parallel_tool_calls",
            "mcp_server_configuration_has_omit_tools_from",
            "mcp_server_configuration_has_enabled_tools",
            "mcp_server_configuration_has_disabled_tools",
            "mcp_server_configuration_has_scopes",
            "mcp_server_configuration_has_oauth",
            "mcp_server_configuration_has_oauth_resource",
            "mcp_server_has_configuration",
            "mcp_server_can_remove",
            "mcp_server_is_authorized",
            "mcp_oauth_configuration_has_client_id",
        ):
            self._declare(f"codex_agent_{name}", [h, h, p_i32])
        for name in (
            "mcp_transport_http_headers_count",
            "mcp_transport_http_environment_headers_count",
            "mcp_transport_stdio_arguments_count",
            "mcp_transport_stdio_environment_count",
            "mcp_transport_stdio_forwarded_environment_count",
            "mcp_server_configuration_omit_tools_from_count",
            "mcp_server_configuration_enabled_tools_count",
            "mcp_server_configuration_disabled_tools_count",
            "mcp_server_configuration_scopes_count",
            "mcp_server_configuration_tools_count",
        ):
            self._declare(f"codex_agent_{name}", [h, h, p_size])

        for name in (
            "mcp_environment_variable_source",
            "mcp_oauth_configuration_callback_port",
            "mcp_tool_configuration_approval",
            "mcp_server_configuration_authentication",
            "mcp_server_configuration_default_tool_approval",
        ):
            self._declare(f"codex_agent_{name}", [h, h, p_i32, p_i32])
        for name in (
            "mcp_server_configuration_startup_timeout_seconds",
            "mcp_server_configuration_tool_timeout_seconds",
        ):
            self._declare(
                f"codex_agent_{name}",
                [h, h, p_i32, ctypes.POINTER(ctypes.c_double)],
            )
        for name in (
            "mcp_transport_kind",
            "mcp_server_auth_status",
            "mcp_server_origin",
        ):
            self._declare(f"codex_agent_{name}", [h, h, p_i32])
        for name in (
            "mcp_transport_http",
            "mcp_transport_stdio",
            "mcp_server_configuration_transport",
            "mcp_server_configuration_oauth",
            "mcp_server_configuration_tools_value_at",
            "mcp_server_configuration",
        ):
            arguments = [h, h]
            if name.endswith("_value_at"):
                arguments.append(ctypes.c_size_t)
            arguments.append(hp)
            self._declare(f"codex_agent_{name}", arguments)
        for name in ("mcp_transport_stdio_forwarded_environment_at",):
            self._declare(f"codex_agent_{name}", [h, h, ctypes.c_size_t, hp])
        self._declare(
            "codex_agent_mcp_server_configuration_omit_tools_from_at",
            [h, h, ctypes.c_size_t, p_i32],
        )

        p_view = ctypes.POINTER(StringView)
        p_double = ctypes.POINTER(ctypes.c_double)

        self._declare(
            "codex_agent_failure_create", [h, p_view, p_view, ctypes.c_int32, hp]
        )
        self._declare(
            "codex_agent_pending_approval_create", [h, p_view, h, p_view, p_view, hp]
        )
        self._declare("codex_agent_pending_approval_destroy", [h, hp])
        self._declare("codex_agent_pending_elicitation_create", [h, h, hp])
        self._declare("codex_agent_pending_elicitation_destroy", [h, hp])
        self._declare("codex_agent_pending_interaction_from_approval", [h, h, hp])
        self._declare("codex_agent_pending_interaction_from_elicitation", [h, h, hp])
        self._declare("codex_agent_pending_interaction_destroy", [h, hp])
        self._declare(
            "codex_agent_pending_interaction_request_id_copy", [h, h, *bytes_out]
        )
        self._declare("codex_agent_pending_interaction_conversation_id", [h, h, hp])

        self._declare("codex_agent_form_boolean_value_create", [h, ctypes.c_int32, hp])
        self._declare("codex_agent_form_boolean_value_value", [h, h, p_i32])
        self._declare("codex_agent_form_number_value_create", [h, ctypes.c_double, hp])
        self._declare("codex_agent_form_number_value_value", [h, h, p_double])
        self._declare("codex_agent_form_text_value_create", [h, p_view, hp])
        self._declare("codex_agent_form_text_value_value_copy", [h, h, *bytes_out])
        self._declare(
            "codex_agent_form_text_list_value_create", [h, p_view, ctypes.c_size_t, hp]
        )
        self._declare("codex_agent_form_text_list_value_count", [h, h, p_size])
        self._declare(
            "codex_agent_form_text_list_value_copy_at",
            [h, h, ctypes.c_size_t, *bytes_out],
        )
        for kind in ("boolean", "number", "text", "text_list"):
            self._declare(f"codex_agent_form_value_from_{kind}", [h, h, hp])
            self._declare(f"codex_agent_form_value_{kind}", [h, h, hp])
        self._declare("codex_agent_form_value_destroy", [h, hp])
        self._declare("codex_agent_form_value_kind", [h, h, p_i32])

        self._declare(
            "codex_agent_form_option_create",
            [h, p_view, ctypes.c_int32, p_view, ctypes.c_int32, p_view, hp],
        )
        self._declare("codex_agent_form_option_destroy", [h, hp])
        self._declare(
            "codex_agent_form_field_create",
            [
                h,
                p_view,
                p_view,
                ctypes.c_int32,
                p_view,
                ctypes.c_int32,
                ctypes.c_int32,
                hp,
                ctypes.c_size_t,
                ctypes.c_int32,
                h,
                ctypes.c_int32,
                ctypes.c_double,
                ctypes.c_int32,
                ctypes.c_double,
                ctypes.c_int32,
                ctypes.c_int32,
                ctypes.c_int32,
                ctypes.c_int64,
                ctypes.c_int32,
                ctypes.c_int64,
                ctypes.c_int32,
                ctypes.c_int64,
                ctypes.c_int32,
                ctypes.c_int64,
                ctypes.c_int32,
                ctypes.c_int32,
                hp,
            ],
        )
        self._declare("codex_agent_form_field_destroy", [h, hp])
        self._declare("codex_agent_form_field_accepts", [h, h, h, p_i32])

        self._declare(
            "codex_agent_elicitation_create",
            [
                h,
                p_view,
                p_view,
                h,
                p_view,
                ctypes.c_int32,
                hp,
                ctypes.c_size_t,
                ctypes.c_int32,
                p_view,
                hp,
            ],
        )
        self._declare("codex_agent_elicitation_destroy", [h, hp])
        self._declare(
            "codex_agent_elicitation_response_create",
            [h, ctypes.c_int32, p_view, hp, ctypes.c_size_t, hp],
        )
        self._declare("codex_agent_elicitation_response_destroy", [h, hp])
        self._declare("codex_agent_elicitation_response_action", [h, h, p_i32])
        self._declare("codex_agent_elicitation_response_content_count", [h, h, p_size])
        self._declare(
            "codex_agent_elicitation_response_content_value", [h, h, p_view, hp]
        )

        self._declare(
            "codex_agent_form_content_create", [h, p_view, hp, ctypes.c_size_t, hp]
        )
        self._declare("codex_agent_form_content_destroy", [h, hp])
        self._declare("codex_agent_form_content_count", [h, h, p_size])
        self._declare(
            "codex_agent_form_content_key_copy", [h, h, ctypes.c_size_t, *bytes_out]
        )
        self._declare("codex_agent_form_content_value_at", [h, h, p_view, hp])
        self._declare("codex_agent_elicitation_initial_values", [h, h, hp])
        self._declare("codex_agent_elicitation_validate", [h, h, h, hp])
        self._declare("codex_agent_elicitation_accept", [h, h, h, hp])
        self._declare("codex_agent_elicitation_accepts", [h, h, h, p_i32])
        self._declare("codex_agent_elicitation_response_decline", [h, hp])
        self._declare("codex_agent_elicitation_response_cancel", [h, hp])

        self._declare("codex_agent_elicitation_validation_destroy", [h, hp])
        self._declare("codex_agent_elicitation_validation_issue_count", [h, h, p_size])
        self._declare(
            "codex_agent_elicitation_validation_issue_at", [h, h, ctypes.c_size_t, hp]
        )
        self._declare("codex_agent_elicitation_validation_issue_destroy", [h, hp])
        self._declare(
            "codex_agent_elicitation_validation_issue_field_name_copy",
            [h, h, *bytes_out],
        )
        self._declare("codex_agent_elicitation_validation_issue_reason", [h, h, p_i32])

        self._declare(
            "codex_agent_interaction_state_create",
            [h, hp, ctypes.c_size_t, p_view, ctypes.c_size_t, ctypes.c_int32, h, hp],
        )
        self._declare("codex_agent_interaction_state_destroy", [h, hp])
        self._declare(
            "codex_agent_interaction_state_resolving_request_ids_contains",
            [h, h, p_view, p_i32],
        )
        self._declare("codex_agent_interaction_state_is_resolving", [h, h, h, p_i32])
        self._declare("codex_agent_interaction_state_pending_for", [h, h, h, hp])
        self._declare("codex_agent_pending_interaction_list_destroy", [h, hp])
        self._declare("codex_agent_pending_interaction_list_count", [h, h, p_size])
        self._declare(
            "codex_agent_pending_interaction_list_at", [h, h, ctypes.c_size_t, hp]
        )

        self._declare("codex_agent_authorization_url_chat_gpt", [h, p_view, hp])
        self._declare("codex_agent_authorization_url_external", [h, p_view, hp])
        self._declare("codex_agent_authorization_url_destroy", [h, hp])
        self._declare("codex_agent_authorization_url_value_copy", [h, h, *bytes_out])
        self._declare("codex_agent_authorization_url_purpose", [h, h, p_i32])

        self._declare_service_api()

    def _declare_service_api(self) -> None:
        h = Handle
        hp = HandlePointer
        p_i32 = ctypes.POINTER(ctypes.c_int32)
        p_i64 = ctypes.POINTER(ctypes.c_int64)
        p_size = ctypes.POINTER(ctypes.c_size_t)
        p_double = ctypes.POINTER(ctypes.c_double)
        p_view = ctypes.POINTER(StringView)
        bytes_out = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t, p_size]

        for owner in (
            "authentication",
            "interactions",
            "integration_authorization",
            "models",
            "skills",
            "hooks",
            "plugins",
            "connectors",
            "mcp_servers",
        ):
            self._declare(f"codex_agent_{owner}_release", [h, hp])
        for owner in ("skills", "hooks", "plugins", "connectors", "mcp_servers"):
            self._declare(f"codex_agent_{owner}_is_available", [h, h, p_i32])

        for suffix in ("api_key", "chat_gpt_browser", "chat_gpt_device_code"):
            arguments = [h]
            if suffix == "api_key":
                arguments.append(p_view)
            arguments.append(hp)
            self._declare(
                f"codex_agent_authentication_method_{suffix}_create", arguments
            )
            self._declare(
                f"codex_agent_authentication_method_{suffix}_destroy", [h, hp]
            )
            self._declare(
                f"codex_agent_authentication_authenticate_{suffix}",
                [h, h, h, OperationCallback, ctypes.c_void_p, hp],
            )
        for suffix in ("cancel", "sign_out"):
            self._declare(
                f"codex_agent_authentication_{suffix}",
                [h, h, OperationCallback, ctypes.c_void_p, hp],
            )

        state_owners = {
            "authentication": ("state", "is_authenticated", "is_authenticating"),
            "integration_authorization": ("state", "active", "is_authorizing"),
            "interactions": ("state", "approvals", "elicitations"),
        }
        for owner, properties in state_owners.items():
            for property_name in properties:
                self._declare(f"codex_agent_{owner}_{property_name}_get", [h, h, hp])
                self._declare(
                    f"codex_agent_{owner}_{property_name}_subscribe",
                    [h, h, StateCallback, ctypes.c_void_p, hp],
                )
        for name in (
            "authentication_state_value",
            "integration_authorization_state_value",
            "integration_authorization_active_value",
            "interactions_state_value",
        ):
            self._declare(f"codex_agent_{name}", [h, h, hp])
        self._declare(
            "codex_agent_integration_authorization_active_has_value", [h, h, p_i32]
        )
        for name in ("interactions_approvals", "interactions_elicitations"):
            self._declare(f"codex_agent_{name}_count", [h, h, p_size])
            self._declare(f"codex_agent_{name}_at", [h, h, ctypes.c_size_t, hp])

        self._declare("codex_agent_authentication_state_destroy", [h, hp])
        self._declare("codex_agent_authentication_state_status", [h, h, p_i32])
        for name in (
            "pending_sign_in_url",
            "device_verification_url",
            "device_user_code",
            "failure",
        ):
            self._declare(f"codex_agent_authentication_state_has_{name}", [h, h, p_i32])
        for name in ("pending_sign_in_url", "device_verification_url", "failure"):
            self._declare(f"codex_agent_authentication_state_{name}", [h, h, hp])
        self._declare(
            "codex_agent_authentication_state_device_user_code_copy", [h, h, *bytes_out]
        )

        self._declare("codex_agent_integration_authorization_state_destroy", [h, hp])
        self._declare(
            "codex_agent_integration_authorization_state_status", [h, h, p_i32]
        )
        self._declare("codex_agent_integration_authorization_state_target", [h, h, hp])
        self._declare("codex_agent_integration_authorization_state_failure", [h, h, hp])
        self._declare(
            "codex_agent_integration_authorization_authorize",
            [h, h, h, OperationCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_integration_authorization_cancel",
            [h, h, OperationCallback, ctypes.c_void_p, hp],
        )

        self._declare("codex_agent_interaction_state_pending_count", [h, h, p_size])
        self._declare(
            "codex_agent_interaction_state_pending_at", [h, h, ctypes.c_size_t, hp]
        )
        self._declare(
            "codex_agent_interaction_state_resolving_request_ids_count", [h, h, p_size]
        )
        self._declare("codex_agent_interaction_state_has_failure", [h, h, p_i32])
        self._declare("codex_agent_interaction_state_failure", [h, h, hp])
        self._declare("codex_agent_pending_interaction_kind", [h, h, p_i32])
        self._declare("codex_agent_pending_interaction_approval", [h, h, hp])
        self._declare("codex_agent_pending_interaction_elicitation", [h, h, hp])
        for name in ("request_id", "title", "details"):
            self._declare(
                f"codex_agent_pending_approval_{name}_copy", [h, h, *bytes_out]
            )
        self._declare("codex_agent_pending_approval_conversation_id", [h, h, hp])
        self._declare("codex_agent_pending_elicitation_elicitation", [h, h, hp])
        self._declare("codex_agent_elicitation_conversation_id", [h, h, hp])
        for name in ("request_id", "server_name", "message", "url"):
            self._declare(f"codex_agent_elicitation_{name}_copy", [h, h, *bytes_out])
        self._declare("codex_agent_elicitation_has_form", [h, h, p_i32])
        self._declare("codex_agent_elicitation_form_count", [h, h, p_size])
        self._declare("codex_agent_elicitation_form_at", [h, h, ctypes.c_size_t, hp])
        self._declare("codex_agent_elicitation_has_url", [h, h, p_i32])
        for name, arguments in (
            ("open_url", [h]),
            ("resolve_approval", [h, ctypes.c_int32]),
            ("resolve_elicitation", [h, h]),
        ):
            self._declare(
                f"codex_agent_interactions_{name}",
                [h, h, *arguments, OperationCallback, ctypes.c_void_p, hp],
            )

        for name in ("name", "title"):
            self._declare(f"codex_agent_form_field_{name}_copy", [h, h, *bytes_out])
        self._declare("codex_agent_form_field_has_description", [h, h, p_i32])
        self._declare("codex_agent_form_field_description_copy", [h, h, *bytes_out])
        for name in (
            "is_required",
            "type",
            "has_default_value",
            "allows_other",
            "is_secret",
        ):
            self._declare(f"codex_agent_form_field_{name}", [h, h, p_i32])
        self._declare("codex_agent_form_field_options_count", [h, h, p_size])
        self._declare("codex_agent_form_field_option_at", [h, h, ctypes.c_size_t, hp])
        self._declare("codex_agent_form_field_default_value", [h, h, hp])
        for name in ("minimum", "maximum"):
            self._declare(f"codex_agent_form_field_{name}", [h, h, p_i32, p_double])
        self._declare("codex_agent_form_field_format", [h, h, p_i32, p_i32])
        for name in (
            "minimum_length",
            "maximum_length",
            "minimum_selections",
            "maximum_selections",
        ):
            self._declare(f"codex_agent_form_field_{name}", [h, h, p_i32, p_i64])
        self._declare("codex_agent_form_option_destroy", [h, hp])
        for name in ("value", "title", "description"):
            self._declare(f"codex_agent_form_option_{name}_copy", [h, h, *bytes_out])
        self._declare("codex_agent_form_option_has_description", [h, h, p_i32])

        for name in (
            "models_list",
            "hooks_list",
            "mcp_servers_list",
        ):
            self._declare(
                f"codex_agent_{name}", [h, h, OperationCallback, ctypes.c_void_p, hp]
            )
        self._declare(
            "codex_agent_models_resolve",
            [h, h, ctypes.c_int32, OperationCallback, ctypes.c_void_p, hp],
        )
        for name in ("resolve_effort", "resolve_service_tier"):
            self._declare(
                f"codex_agent_models_{name}",
                [h, h, h, ctypes.c_int32, OperationCallback, ctypes.c_void_p, hp],
            )
        self._declare(
            "codex_agent_skills_list",
            [h, h, ctypes.c_int32, OperationCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_skills_read",
            [h, h, p_view, ctypes.c_int64, OperationCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_skills_install",
            [h, h, p_view, ctypes.c_int32, OperationCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_skills_uninstall",
            [h, h, h, OperationCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_hooks_install",
            [h, h, p_view, ctypes.c_int32, OperationCallback, ctypes.c_void_p, hp],
        )
        for name in ("uninstall", "trust"):
            self._declare(
                f"codex_agent_hooks_{name}",
                [h, h, h, OperationCallback, ctypes.c_void_p, hp],
            )
        for owner in ("plugins", "connectors"):
            self._declare(
                f"codex_agent_{owner}_list",
                [h, h, ctypes.c_int32, OperationCallback, ctypes.c_void_p, hp],
            )
        for name in ("read", "install", "uninstall"):
            self._declare(
                f"codex_agent_plugins_{name}",
                [h, h, h, OperationCallback, ctypes.c_void_p, hp],
            )
        for name in ("add", "remove"):
            self._declare(
                f"codex_agent_mcp_servers_{name}",
                [h, h, h, OperationCallback, ctypes.c_void_p, hp],
            )

        for name in ("models", "connectors", "mcp_servers"):
            self._declare(f"codex_agent_operation_{name}_count", [h, h, p_size])
        for name in ("model", "connector", "mcp_server"):
            self._declare(
                f"codex_agent_operation_{name}_at", [h, h, ctypes.c_size_t, hp]
            )
        for name in (
            "model",
            "service_tier",
            "skill_catalog",
            "skill_chunk",
            "skill",
            "hook_catalog",
            "hook",
            "plugin_catalog",
            "plugin_detail",
            "plugin_install_result",
            "mcp_server",
        ):
            self._declare(f"codex_agent_operation_{name}", [h, h, hp])
        self._declare("codex_agent_operation_string_copy", [h, h, *bytes_out])
        self._declare("codex_agent_operation_has_service_tier", [h, h, p_i32])

        self._declare(
            "codex_agent_service_tier_create", [h, p_view, p_view, p_view, hp]
        )
        self._declare("codex_agent_service_tier_destroy", [h, hp])
        for name in ("id", "name", "description"):
            self._declare(f"codex_agent_service_tier_{name}_copy", [h, h, *bytes_out])
        self._declare(
            "codex_agent_model_create",
            [
                h,
                p_view,
                p_view,
                p_view,
                p_view,
                ctypes.c_size_t,
                p_view,
                ctypes.c_int32,
                hp,
                ctypes.c_size_t,
                ctypes.c_int32,
                p_view,
                hp,
            ],
        )
        self._declare("codex_agent_model_destroy", [h, hp])
        for name in ("id", "display_name", "description", "default_effort"):
            self._declare(f"codex_agent_model_{name}_copy", [h, h, *bytes_out])
        self._declare("codex_agent_model_supported_efforts_count", [h, h, p_size])
        self._declare(
            "codex_agent_model_supported_effort_copy_at",
            [h, h, ctypes.c_size_t, *bytes_out],
        )
        self._declare("codex_agent_model_is_default", [h, h, p_i32])
        self._declare("codex_agent_model_service_tiers_count", [h, h, p_size])
        self._declare("codex_agent_model_service_tier_at", [h, h, ctypes.c_size_t, hp])
        self._declare("codex_agent_model_has_default_service_tier", [h, h, p_i32])
        self._declare("codex_agent_model_default_service_tier_copy", [h, h, *bytes_out])

        self._declare(
            "codex_agent_connector_create",
            [
                h,
                p_view,
                p_view,
                p_view,
                ctypes.c_int32,
                p_view,
                ctypes.c_int32,
                ctypes.c_int32,
                p_view,
                ctypes.c_size_t,
                hp,
            ],
        )
        self._declare("codex_agent_connector_destroy", [h, hp])
        for name in ("id", "name", "description", "install_url"):
            self._declare(f"codex_agent_connector_{name}_copy", [h, h, *bytes_out])
        for name in ("has_install_url", "is_accessible", "is_enabled"):
            self._declare(f"codex_agent_connector_{name}", [h, h, p_i32])
        self._declare("codex_agent_connector_plugin_names_count", [h, h, p_size])
        self._declare(
            "codex_agent_connector_plugin_names_copy_at",
            [h, h, ctypes.c_size_t, *bytes_out],
        )

        self._declare(
            "codex_agent_plugin_reference_create",
            [
                h,
                p_view,
                p_view,
                p_view,
                ctypes.c_int32,
                p_view,
                ctypes.c_int32,
                p_view,
                hp,
            ],
        )
        self._declare("codex_agent_plugin_reference_destroy", [h, hp])
        for name in (
            "id",
            "name",
            "marketplace_name",
            "marketplace_path",
            "remote_plugin_id",
            "uri",
        ):
            self._declare(
                f"codex_agent_plugin_reference_{name}_copy", [h, h, *bytes_out]
            )
        for name in ("has_marketplace_path", "has_remote_plugin_id"):
            self._declare(f"codex_agent_plugin_reference_{name}", [h, h, p_i32])
        self._declare("codex_agent_plugin_skill_destroy", [h, hp])
        for name in ("name", "description", "path"):
            self._declare(f"codex_agent_plugin_skill_{name}_copy", [h, h, *bytes_out])
        for name in ("is_enabled", "has_path"):
            self._declare(f"codex_agent_plugin_skill_{name}", [h, h, p_i32])
        self._declare("codex_agent_plugin_summary_destroy", [h, hp])
        self._declare("codex_agent_plugin_summary_reference", [h, h, hp])
        for name in (
            "display_name",
            "description",
            "brand_color",
            "privacy_policy_url",
            "terms_of_service_url",
            "website_url",
        ):
            self._declare(f"codex_agent_plugin_summary_{name}_copy", [h, h, *bytes_out])
        for name in (
            "is_installed",
            "is_enabled",
            "install_policy",
            "auth_policy",
            "is_available",
            "has_brand_color",
            "has_privacy_policy_url",
            "has_terms_of_service_url",
            "has_website_url",
        ):
            self._declare(f"codex_agent_plugin_summary_{name}", [h, h, p_i32])
        self._declare("codex_agent_plugin_summary_capabilities_count", [h, h, p_size])
        self._declare(
            "codex_agent_plugin_summary_capabilities_copy_at",
            [h, h, ctypes.c_size_t, *bytes_out],
        )
        self._declare("codex_agent_plugin_catalog_destroy", [h, hp])
        self._declare("codex_agent_plugin_catalog_plugins_count", [h, h, p_size])
        self._declare(
            "codex_agent_plugin_catalog_plugins_at", [h, h, ctypes.c_size_t, hp]
        )
        self._declare("codex_agent_plugin_catalog_errors_count", [h, h, p_size])
        self._declare(
            "codex_agent_plugin_catalog_errors_copy_at",
            [h, h, ctypes.c_size_t, *bytes_out],
        )
        self._declare("codex_agent_plugin_catalog_freshness", [h, h, p_i32])
        self._declare("codex_agent_plugin_detail_destroy", [h, hp])
        self._declare("codex_agent_plugin_detail_summary", [h, h, hp])
        self._declare("codex_agent_plugin_detail_description_copy", [h, h, *bytes_out])
        for name, child in (("skills", "skill"), ("connectors", "connector")):
            self._declare(f"codex_agent_plugin_detail_{name}_count", [h, h, p_size])
            self._declare(
                f"codex_agent_plugin_detail_{name}_at", [h, h, ctypes.c_size_t, hp]
            )
        self._declare("codex_agent_plugin_detail_mcp_servers_count", [h, h, p_size])
        self._declare(
            "codex_agent_plugin_detail_mcp_servers_copy_at",
            [h, h, ctypes.c_size_t, *bytes_out],
        )
        self._declare("codex_agent_plugin_detail_hook_count", [h, h, p_i32])
        self._declare("codex_agent_plugin_install_result_destroy", [h, hp])
        self._declare("codex_agent_plugin_install_result_auth_policy", [h, h, p_i32])
        self._declare(
            "codex_agent_plugin_install_result_connectors_count", [h, h, p_size]
        )
        self._declare(
            "codex_agent_plugin_install_result_connectors_at",
            [h, h, ctypes.c_size_t, hp],
        )
        self._declare("codex_agent_plugin_install_result_has_message", [h, h, p_i32])
        self._declare(
            "codex_agent_plugin_install_result_message_copy", [h, h, *bytes_out]
        )

        self._declare(
            "codex_agent_skill_create",
            [
                h,
                p_view,
                p_view,
                p_view,
                p_view,
                ctypes.c_int32,
                ctypes.c_int32,
                ctypes.c_int32,
                p_view,
                p_view,
                ctypes.c_size_t,
                ctypes.c_int32,
                ctypes.c_int32,
                ctypes.c_int32,
                hp,
            ],
        )
        self._declare("codex_agent_skill_destroy", [h, hp])
        for name in ("name", "display_name", "description", "path", "brand_color"):
            self._declare(f"codex_agent_skill_{name}_copy", [h, h, *bytes_out])
        for name in (
            "scope",
            "is_enabled",
            "has_brand_color",
            "can_uninstall",
            "origin",
        ):
            self._declare(f"codex_agent_skill_{name}", [h, h, p_i32])
        self._declare("codex_agent_skill_dependencies_count", [h, h, p_size])
        self._declare(
            "codex_agent_skill_dependencies_copy_at",
            [h, h, ctypes.c_size_t, *bytes_out],
        )
        self._declare("codex_agent_skill_catalog_destroy", [h, hp])
        self._declare("codex_agent_skill_catalog_skills_count", [h, h, p_size])
        self._declare(
            "codex_agent_skill_catalog_skills_at", [h, h, ctypes.c_size_t, hp]
        )
        self._declare("codex_agent_skill_catalog_errors_count", [h, h, p_size])
        self._declare(
            "codex_agent_skill_catalog_errors_copy_at",
            [h, h, ctypes.c_size_t, *bytes_out],
        )
        self._declare("codex_agent_skill_chunk_destroy", [h, hp])
        self._declare("codex_agent_skill_chunk_content_copy", [h, h, *bytes_out])
        self._declare("codex_agent_skill_chunk_next_offset", [h, h, p_i32, p_i64])
        self._declare("codex_agent_skill_chunk_total_bytes", [h, h, p_i64])

        for name in ("agent", "prompt"):
            self._declare(f"codex_agent_hook_handler_{name}_acquire", [h, hp])
            self._declare(f"codex_agent_hook_handler_{name}_destroy", [h, hp])
        self._declare(
            "codex_agent_hook_handler_command_create", [h, p_view, ctypes.c_int32, hp]
        )
        self._declare("codex_agent_hook_handler_command_destroy", [h, hp])
        self._declare(
            "codex_agent_hook_handler_command_command_copy", [h, h, *bytes_out]
        )
        self._declare("codex_agent_hook_handler_command_is_async", [h, h, p_i32])
        self._declare(
            "codex_agent_hook_handler_mcp_tool_create", [h, p_view, p_view, hp]
        )
        self._declare("codex_agent_hook_handler_mcp_tool_destroy", [h, hp])
        self._declare(
            "codex_agent_hook_handler_mcp_tool_server_copy", [h, h, *bytes_out]
        )
        self._declare("codex_agent_hook_handler_mcp_tool_tool_copy", [h, h, *bytes_out])
        for name in ("agent", "command", "mcp_tool", "prompt"):
            self._declare(f"codex_agent_hook_handler_from_{name}", [h, h, hp])
            self._declare(f"codex_agent_hook_handler_{name}", [h, h, hp])
        self._declare("codex_agent_hook_handler_destroy", [h, hp])
        self._declare("codex_agent_hook_handler_kind", [h, h, p_i32])
        self._declare(
            "codex_agent_hook_create",
            [
                h,
                p_view,
                p_view,
                ctypes.c_int32,
                p_view,
                h,
                ctypes.c_int32,
                p_view,
                p_view,
                ctypes.c_int64,
                ctypes.c_int32,
                ctypes.c_int32,
                p_view,
                ctypes.c_int32,
                p_view,
                ctypes.c_int32,
                p_view,
                ctypes.c_int32,
                ctypes.c_int32,
                ctypes.c_int32,
                hp,
            ],
        )
        self._declare("codex_agent_hook_destroy", [h, hp])
        for name in (
            "key",
            "current_hash",
            "event_name",
            "source",
            "source_path",
            "matcher",
            "plugin_id",
            "status_message",
        ):
            self._declare(f"codex_agent_hook_{name}_copy", [h, h, *bytes_out])
        for name in (
            "is_enabled",
            "is_managed",
            "trust_status",
            "has_matcher",
            "has_plugin_id",
            "has_status_message",
            "origin",
            "can_uninstall",
            "can_trust",
        ):
            self._declare(f"codex_agent_hook_{name}", [h, h, p_i32])
        self._declare("codex_agent_hook_handler", [h, h, hp])
        self._declare("codex_agent_hook_timeout_seconds", [h, h, p_i64])
        self._declare("codex_agent_hook_catalog_destroy", [h, hp])
        for name in ("hooks", "warnings", "errors"):
            self._declare(f"codex_agent_hook_catalog_{name}_count", [h, h, p_size])
        self._declare("codex_agent_hook_catalog_hooks_at", [h, h, ctypes.c_size_t, hp])
        for name in ("warnings", "errors"):
            self._declare(
                f"codex_agent_hook_catalog_{name}_copy_at",
                [h, h, ctypes.c_size_t, *bytes_out],
            )

        for name in ("connector", "mcp_server"):
            self._declare(f"codex_agent_integration_{name}_create", [h, h, hp])
            self._declare(f"codex_agent_integration_{name}_destroy", [h, hp])
            self._declare(f"codex_agent_integration_from_{name}", [h, h, hp])
            self._declare(f"codex_agent_integration_{name}", [h, h, hp])
        self._declare("codex_agent_integration_connector_connector", [h, h, hp])
        self._declare("codex_agent_integration_mcp_server_server", [h, h, hp])
        self._declare("codex_agent_integration_destroy", [h, hp])
        self._declare("codex_agent_integration_kind", [h, h, p_i32])

        self._declare(
            "codex_agent_mcp_environment_variable_create",
            [h, p_view, ctypes.c_int32, ctypes.c_int32, hp],
        )
        self._declare(
            "codex_agent_mcp_oauth_configuration_create",
            [h, ctypes.c_int32, p_view, ctypes.c_int32, ctypes.c_int32, hp],
        )
        self._declare(
            "codex_agent_mcp_tool_configuration_create",
            [h, ctypes.c_int32, ctypes.c_int32, hp],
        )
        self._declare(
            "codex_agent_mcp_transport_http_create",
            [
                h,
                p_view,
                ctypes.c_int32,
                p_view,
                ctypes.c_int32,
                p_view,
                p_view,
                ctypes.c_size_t,
                ctypes.c_int32,
                p_view,
                p_view,
                ctypes.c_size_t,
                ctypes.c_int32,
                p_view,
                hp,
            ],
        )
        self._declare(
            "codex_agent_mcp_transport_stdio_create",
            [
                h,
                p_view,
                p_view,
                ctypes.c_size_t,
                ctypes.c_int32,
                p_view,
                ctypes.c_int32,
                p_view,
                p_view,
                ctypes.c_size_t,
                hp,
                ctypes.c_size_t,
                hp,
            ],
        )
        self._declare("codex_agent_mcp_transport_from_http", [h, h, hp])
        self._declare("codex_agent_mcp_transport_from_stdio", [h, h, hp])
        self._declare(
            "codex_agent_mcp_server_configuration_create",
            [
                h,
                p_view,
                h,
                ctypes.c_int32,
                ctypes.c_int32,
                p_view,
                ctypes.c_int32,
                ctypes.c_int32,
                ctypes.c_int32,
                ctypes.c_int32,
                p_i32,
                ctypes.c_size_t,
                ctypes.c_int32,
                ctypes.c_double,
                ctypes.c_int32,
                ctypes.c_double,
                ctypes.c_int32,
                ctypes.c_int32,
                ctypes.c_int32,
                p_view,
                ctypes.c_size_t,
                ctypes.c_int32,
                p_view,
                ctypes.c_size_t,
                ctypes.c_int32,
                p_view,
                ctypes.c_size_t,
                ctypes.c_int32,
                h,
                ctypes.c_int32,
                p_view,
                p_view,
                hp,
                ctypes.c_size_t,
                hp,
            ],
        )
        self._declare(
            "codex_agent_mcp_server_create",
            [h, p_view, p_view, ctypes.c_int32, h, ctypes.c_int32, ctypes.c_int32, hp],
        )
        for name in ("boolean", "number", "text", "text_list"):
            self._declare(f"codex_agent_form_{name}_value_destroy", [h, hp])


def load_native(path: str | os.PathLike[str] | None = None) -> NativeLibrary:
    return NativeLibrary.load(path)
