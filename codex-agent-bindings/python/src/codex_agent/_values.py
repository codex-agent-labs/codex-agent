from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ._enums import (
    ApprovalPreset,
    CatalogFreshness,
    ElicitationValidationReason,
    HookRunStatus,
    PlanStepStatus,
    PluginAuthPolicy,
    PluginInstallPolicy,
    ResourceOrigin,
    SkillScope,
    WorkActivity,
)
from ._models import ConversationId


@dataclass(frozen=True, slots=True)
class ConversationSettings:
    approval_preset: ApprovalPreset = ApprovalPreset.AUTO_REVIEW
    service_tier: str | None = None


@dataclass(frozen=True, slots=True)
class Connector:
    id: str
    name: str
    description: str = ""
    install_url: str | None = None
    is_accessible: bool = False
    is_enabled: bool = True
    plugin_names: Sequence[str] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "plugin_names", tuple(self.plugin_names))


@dataclass(frozen=True, slots=True)
class ElicitationValidationIssue:
    field_name: str
    reason: ElicitationValidationReason


@dataclass(frozen=True, slots=True)
class ElicitationValidation:
    issues: Sequence[ElicitationValidationIssue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "issues", tuple(self.issues))

    @property
    def is_valid(self) -> bool:
        return not self.issues


@dataclass(frozen=True, slots=True)
class FormOption:
    value: str
    title: str = ""
    description: str | None = None


@dataclass(frozen=True, slots=True)
class PlanStep:
    text: str
    status: PlanStepStatus


@dataclass(frozen=True, slots=True)
class PlanProgress:
    explanation: str | None = None
    steps: Sequence[PlanStep] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "steps", tuple(self.steps))


@dataclass(frozen=True, slots=True)
class ServiceTier:
    id: str
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class Model:
    id: str
    display_name: str
    description: str
    supported_efforts: Sequence[str]
    default_effort: str
    is_default: bool
    service_tiers: Sequence[ServiceTier] = ()
    default_service_tier: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "supported_efforts", tuple(self.supported_efforts))
        object.__setattr__(self, "service_tiers", tuple(self.service_tiers))


@dataclass(frozen=True, slots=True)
class PluginReference:
    id: str
    name: str
    marketplace_name: str
    marketplace_path: str | None = None
    remote_plugin_id: str | None = None

    @property
    def uri(self) -> str:
        return f"plugin://{self.name}@{self.marketplace_name}"


@dataclass(frozen=True, slots=True)
class PluginSkill:
    name: str
    description: str
    is_enabled: bool
    path: str | None = None


@dataclass(frozen=True, slots=True)
class PluginSummary:
    reference: PluginReference
    display_name: str
    description: str
    is_installed: bool
    is_enabled: bool
    install_policy: PluginInstallPolicy
    auth_policy: PluginAuthPolicy
    is_available: bool
    capabilities: Sequence[str] = ()
    brand_color: str | None = None
    privacy_policy_url: str | None = None
    terms_of_service_url: str | None = None
    website_url: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "capabilities", tuple(self.capabilities))


@dataclass(frozen=True, slots=True)
class PluginCatalog:
    plugins: Sequence[PluginSummary]
    errors: Sequence[str] = ()
    freshness: CatalogFreshness = CatalogFreshness.LIVE

    def __post_init__(self) -> None:
        object.__setattr__(self, "plugins", tuple(self.plugins))
        object.__setattr__(self, "errors", tuple(self.errors))


@dataclass(frozen=True, slots=True)
class PluginDetail:
    summary: PluginSummary
    description: str
    skills: Sequence[PluginSkill]
    connectors: Sequence[Connector]
    mcp_servers: Sequence[str]
    hook_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "skills", tuple(self.skills))
        object.__setattr__(self, "connectors", tuple(self.connectors))
        object.__setattr__(self, "mcp_servers", tuple(self.mcp_servers))


@dataclass(frozen=True, slots=True)
class PluginInstallResult:
    auth_policy: PluginAuthPolicy
    connectors_needing_authentication: Sequence[Connector]
    message: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "connectors_needing_authentication",
            tuple(self.connectors_needing_authentication),
        )


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    display_name: str
    description: str
    path: str
    scope: SkillScope
    is_enabled: bool
    brand_color: str | None = None
    dependencies: Sequence[str] = ()
    can_uninstall: bool = False
    origin: ResourceOrigin | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "dependencies", tuple(self.dependencies))
        if self.origin is None:
            origins = {
                SkillScope.USER: ResourceOrigin.USER,
                SkillScope.REPO: ResourceOrigin.WORKSPACE,
                SkillScope.PLUGIN: ResourceOrigin.PLUGIN,
                SkillScope.SYSTEM: ResourceOrigin.MANAGED,
                SkillScope.ADMIN: ResourceOrigin.MANAGED,
            }
            object.__setattr__(self, "origin", origins[self.scope])


@dataclass(frozen=True, slots=True)
class SkillCatalog:
    skills: Sequence[Skill]
    errors: Sequence[str] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "skills", tuple(self.skills))
        object.__setattr__(self, "errors", tuple(self.errors))


@dataclass(frozen=True, slots=True)
class SkillChunk:
    content: str
    next_offset: int | None
    total_bytes: int


@dataclass(frozen=True, slots=True)
class HookActivity:
    id: str
    event_name: str
    handler_type: str
    status: HookRunStatus
    status_message: str | None = None
    details: Sequence[str] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", tuple(self.details))


@dataclass(frozen=True, slots=True)
class TurnProgress:
    text: str = ""
    commentary: str = ""
    reasoning: str = ""
    plan: str = ""
    plan_progress: PlanProgress | None = None
    shell_output: str = ""
    shell_exit_code: int | None = None
    work_activity: WorkActivity | None = None
    hook_activities: Sequence[HookActivity] = ()
    is_truncated: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_activities", tuple(self.hook_activities))
