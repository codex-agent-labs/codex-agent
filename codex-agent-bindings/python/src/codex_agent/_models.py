from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

from ._enums import (
    ApprovalPreset,
    Capability,
    CollaborationMode,
    ConversationStatus,
    MessageRole,
    WorkspaceSelectionReason,
)
from ._errors import Failure

if TYPE_CHECKING:
    from ._client import CodexAgent
    from ._residual_values import ConversationValue
    from ._values import TurnProgress


def _empty_turn_progress() -> TurnProgress:
    from ._values import TurnProgress

    return TurnProgress()


class HostStateKind(IntEnum):
    NEW = 0
    RESTORING = 1
    WORKSPACE_REQUIRED = 2
    PREPARING = 3
    READY = 4
    FAILED = 5
    CLOSED = 6


@dataclass(frozen=True, slots=True)
class ClientInfo:
    name: str
    title: str
    version: str

    def __post_init__(self) -> None:
        if any(
            not value or value.isspace() or any(ord(char) < 32 for char in value)
            for value in (self.name, self.title, self.version)
        ):
            raise ValueError(
                "client information must not be blank or contain control characters"
            )


@dataclass(frozen=True, slots=True)
class Workspace:
    path: str
    display_name: str | None = None

    def __post_init__(self) -> None:
        if not self.path or self.path.isspace() or "\0" in self.path:
            raise ValueError("workspace path must not be blank")
        display_name = self.path if self.display_name is None else self.display_name
        if not display_name or display_name.isspace():
            raise ValueError("workspace display name must not be blank")
        object.__setattr__(self, "display_name", display_name)


@dataclass(frozen=True, slots=True)
class WorkspaceRequirement:
    reason: WorkspaceSelectionReason
    message: str


@dataclass(frozen=True, slots=True)
class ConversationId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or self.value.isspace():
            raise ValueError("conversation ID must not be blank")


@dataclass(frozen=True, slots=True)
class ConversationSummary:
    conversation_id: ConversationId
    title: str
    updated_at_epoch_seconds: int


@dataclass(frozen=True, slots=True)
class ConversationState:
    status: ConversationStatus = ConversationStatus.NEW
    failure: Failure | None = None
    conversation_id: ConversationId | None = None
    conversation: ConversationValue | None = None
    model: str | None = None
    effort: str | None = None
    service_tier: str | None = None
    turn_progress: TurnProgress = field(default_factory=_empty_turn_progress)

    @property
    def can_start_turn(self) -> bool:
        return self.conversation_id is not None and (
            self.status == ConversationStatus.READY
            or (
                self.status == ConversationStatus.FAILED
                and self.failure is not None
                and self.failure.is_recoverable
            )
        )

    @property
    def can_cancel_turn(self) -> bool:
        return self.status in {
            ConversationStatus.STARTING_TURN,
            ConversationStatus.RUNNING_TURN,
        }

    @property
    def can_reload(self) -> bool:
        return self.conversation_id is not None and self.status in {
            ConversationStatus.READY,
            ConversationStatus.FAILED,
        }


@dataclass(frozen=True, slots=True)
class HostState:
    kind: HostStateKind
    agent: CodexAgent | None = None
    workspace: Workspace | None = None
    requirement: WorkspaceRequirement | None = None
    failure: Failure | None = None
