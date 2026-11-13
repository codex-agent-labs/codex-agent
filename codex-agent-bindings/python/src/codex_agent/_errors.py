from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Status(IntEnum):
    OK = 0
    INVALID_ARGUMENT = 1
    OUT_OF_MEMORY = 2
    STALE_HANDLE = 3
    WRONG_HANDLE_TYPE = 4
    WRONG_CONTEXT = 5
    BUSY = 6
    CANCELLED = 7
    INTERNAL_ERROR = 8
    BUFFER_TOO_SMALL = 9
    UNSUPPORTED_ABI = 10
    CLOSED = 11
    WOULD_DEADLOCK = 12
    NOT_READY = 13
    OPERATION_FAILED = 14


class CodexError(Exception):
    """Base error raised by the Python projection."""


class NativeStatusError(CodexError):
    def __init__(self, status: Status, function: str) -> None:
        self.status = status
        self.function = function
        super().__init__(f"{function} failed with {status.name} ({status.value})")


class UnsupportedAbiError(CodexError):
    pass


class ClosedError(CodexError):
    pass


@dataclass(frozen=True, slots=True)
class Failure:
    code: str
    message: str
    is_recoverable: bool

    def __post_init__(self) -> None:
        if not self.code or self.code.isspace():
            raise ValueError("failure code must not be blank")
        if not self.message or self.message.isspace() or len(self.message) > 500:
            raise ValueError("failure message is invalid")


class OperationError(CodexError):
    def __init__(self, status: Status, failure: Failure | None = None) -> None:
        self.status = status
        self.failure = failure
        message = failure.message if failure is not None else status.name
        super().__init__(message)


def check(status: int, function: str, *, allow: tuple[Status, ...] = ()) -> Status:
    try:
        value = Status(status)
    except ValueError:
        raise NativeStatusError(
            Status.INTERNAL_ERROR, f"{function} (unknown status {status})"
        ) from None
    if value is not Status.OK and value not in allow:
        raise NativeStatusError(value, function)
    return value
