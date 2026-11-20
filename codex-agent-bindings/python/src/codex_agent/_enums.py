from enum import IntEnum


class ApprovalDecision(IntEnum):
    ACCEPT = 0
    DECLINE = 1


class ApprovalPreset(IntEnum):
    NEVER = 0
    AUTO_REVIEW = 1
    ASK_ME = 2
    STRICT = 3

    @property
    def display_name(self) -> str:
        return {
            ApprovalPreset.NEVER: "Never",
            ApprovalPreset.AUTO_REVIEW: "Auto review",
            ApprovalPreset.ASK_ME: "Ask me",
            ApprovalPreset.STRICT: "Strict",
        }[self]


class AuthenticationStatus(IntEnum):
    SIGNED_OUT = 0
    AUTHENTICATING = 1
    AUTHENTICATED = 2


class Capability(IntEnum):
    WEB_SEARCH = 0

    @property
    def id(self) -> str:
        return "web_search"

    @property
    def display_label(self) -> str:
        return "Web search"

    @property
    def prompt_label(self) -> str:
        return "Use 🌐 Web search"

    @property
    def icon(self) -> str | None:
        return "🌐"


class CatalogFreshness(IntEnum):
    LIVE = 0
    FRESH_CACHE = 1
    STALE_CACHE = 2


class CollaborationMode(IntEnum):
    DEFAULT = 0
    PLAN = 1


class ConversationStatus(IntEnum):
    NEW = 0
    OPENING = 1
    READY = 2
    STARTING_TURN = 3
    RUNNING_TURN = 4
    CANCELLING_TURN = 5
    RELOADING = 6
    FAILED = 7
    CLOSED = 8


class ElicitationAction(IntEnum):
    ACCEPT = 0
    DECLINE = 1
    CANCEL = 2


class ElicitationValidationReason(IntEnum):
    MISSING_REQUIRED = 0
    UNKNOWN_FIELD = 1
    INVALID_TYPE = 2
    NON_FINITE_NUMBER = 3
    BELOW_MINIMUM = 4
    ABOVE_MAXIMUM = 5
    NON_INTEGER = 6
    INVALID_FORMAT = 7
    INVALID_SELECTION = 8
    DUPLICATE_SELECTION = 9


class FormFieldType(IntEnum):
    STRING = 0
    NUMBER = 1
    INTEGER = 2
    BOOLEAN = 3
    SINGLE_SELECT = 4
    MULTI_SELECT = 5


class FormStringFormat(IntEnum):
    EMAIL = 0
    URI = 1
    DATE = 2
    DATE_TIME = 3


class HookRunStatus(IntEnum):
    RUNNING = 0
    COMPLETED = 1
    FAILED = 2
    BLOCKED = 3
    STOPPED = 4


class HookTrustStatus(IntEnum):
    MANAGED = 0
    UNTRUSTED = 1
    TRUSTED = 2
    MODIFIED = 3


class InstallationScope(IntEnum):
    USER = 0
    WORKSPACE = 1


class IntegrationAuthorizationStatus(IntEnum):
    IDLE = 0
    STARTING = 1
    AWAITING_COMPLETION = 2
    AUTHORIZED = 3
    FAILED = 4


class McpAuthStatus(IntEnum):
    UNKNOWN = 0
    UNSUPPORTED = 1
    NOT_LOGGED_IN = 2
    BEARER_TOKEN = 3
    OAUTH = 4


class McpAuthentication(IntEnum):
    OAUTH = 0
    CHAT_GPT = 1


class McpEnvironmentSource(IntEnum):
    LOCAL = 0
    REMOTE = 1


class McpToolApproval(IntEnum):
    AUTO = 0
    PROMPT = 1
    WRITES = 2
    APPROVE = 3


class McpToolExposureSurface(IntEnum):
    CODE_MODE = 0
    DEFERRED = 1
    DIRECT = 2


class MessageRole(IntEnum):
    USER = 0
    ASSISTANT = 1


class PlanStepStatus(IntEnum):
    PENDING = 0
    IN_PROGRESS = 1
    COMPLETED = 2


class PluginAuthPolicy(IntEnum):
    ON_INSTALL = 0
    ON_USE = 1


class PluginInstallPolicy(IntEnum):
    NOT_AVAILABLE = 0
    AVAILABLE = 1
    INSTALLED_BY_DEFAULT = 2


class Resolution(IntEnum):
    PREFERRED = 0
    DEFAULT = 1
    FIRST = 2


class ResourceOrigin(IntEnum):
    USER = 0
    WORKSPACE = 1
    PLUGIN = 2
    MANAGED = 3
    UNKNOWN = 4


class SkillScope(IntEnum):
    SYSTEM = 0
    USER = 1
    REPO = 2
    PLUGIN = 3
    ADMIN = 4

    @property
    def display_name(self) -> str:
        return {
            SkillScope.SYSTEM: "Built in",
            SkillScope.USER: "User",
            SkillScope.REPO: "Workspace",
            SkillScope.PLUGIN: "Plugin",
            SkillScope.ADMIN: "Managed",
        }[self]


class WorkActivity(IntEnum):
    RUNNING_COMMAND = 0
    WRITING_FILES = 1


class AuthorizationPurpose(IntEnum):
    CHAT_GPT = 0
    EXTERNAL = 1


class WorkspaceSelectionReason(IntEnum):
    NOT_SELECTED = 0
    NOT_FOUND = 1
    ACCESS_REVOKED = 2
    INVALID_SELECTION = 3
