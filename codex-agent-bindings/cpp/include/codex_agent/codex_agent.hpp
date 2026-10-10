#pragma once

#include <codex_agent.h>
#include <codex_agent/native_dispatch.hpp>

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cmath>
#include <condition_variable>
#include <cstdint>
#include <exception>
#include <functional>
#include <future>
#include <iterator>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <type_traits>
#include <utility>
#include <variant>
#include <vector>

#include <codex_agent/native_remap.hpp>

namespace codex_agent {

namespace detail {

struct AgentOwnership;
struct LivePending;
}

enum class Status : std::int32_t {
    ok = CODEX_AGENT_STATUS_OK,
    invalid_argument = CODEX_AGENT_STATUS_INVALID_ARGUMENT,
    out_of_memory = CODEX_AGENT_STATUS_OUT_OF_MEMORY,
    stale_handle = CODEX_AGENT_STATUS_STALE_HANDLE,
    wrong_handle_type = CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
    wrong_context = CODEX_AGENT_STATUS_WRONG_CONTEXT,
    busy = CODEX_AGENT_STATUS_BUSY,
    cancelled = CODEX_AGENT_STATUS_CANCELLED,
    internal_error = CODEX_AGENT_STATUS_INTERNAL_ERROR,
    buffer_too_small = CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
    unsupported_abi = CODEX_AGENT_STATUS_UNSUPPORTED_ABI,
    closed = CODEX_AGENT_STATUS_CLOSED,
    would_deadlock = CODEX_AGENT_STATUS_WOULD_DEADLOCK,
    not_ready = CODEX_AGENT_STATUS_NOT_READY,
    operation_failed = CODEX_AGENT_STATUS_OPERATION_FAILED,
};

inline constexpr Status status_from_raw(codex_agent_status_t value) noexcept {
    return static_cast<Status>(value);
}

inline constexpr codex_agent_status_t status_to_raw(Status value) noexcept {
    return static_cast<codex_agent_status_t>(value);
}

inline std::string_view status_name(Status status) noexcept {
    switch (status) {
        case Status::ok: return "ok";
        case Status::invalid_argument: return "invalid_argument";
        case Status::out_of_memory: return "out_of_memory";
        case Status::stale_handle: return "stale_handle";
        case Status::wrong_handle_type: return "wrong_handle_type";
        case Status::wrong_context: return "wrong_context";
        case Status::busy: return "busy";
        case Status::cancelled: return "cancelled";
        case Status::internal_error: return "internal_error";
        case Status::buffer_too_small: return "buffer_too_small";
        case Status::unsupported_abi: return "unsupported_abi";
        case Status::closed: return "closed";
        case Status::would_deadlock: return "would_deadlock";
        case Status::not_ready: return "not_ready";
        case Status::operation_failed: return "operation_failed";
    }
    return "unknown";
}

class Error : public std::runtime_error {
public:
    explicit Error(Status status, std::string message = {})
        : std::runtime_error(
              message.empty() ? std::string(status_name(status)) : std::move(message)),
          status_(status) {}

    [[nodiscard]] Status status() const noexcept { return status_; }

private:
    Status status_;
};

struct Failure {
    Failure() = default;
    Failure(std::string code_value, std::string message_value,
            bool recoverable_value)
        : code(std::move(code_value)),
          message(std::move(message_value)),
          recoverable(recoverable_value) {
        if (code.find_first_not_of(" \t\n\r\f\v") == std::string::npos) {
            throw std::invalid_argument("Failure code must not be blank");
        }
        if (message.find_first_not_of(" \t\n\r\f\v") == std::string::npos ||
            message.size() > 500) {
            throw std::invalid_argument("Failure message is invalid");
        }
    }

    std::string code;
    std::string message;
    bool recoverable = false;
};

class OperationError : public Error {
public:
    OperationError(Status status, std::optional<Failure> failure)
        : Error(
              status,
              failure ? failure->code + ": " + failure->message
                      : std::string(status_name(status))),
          failure_(std::move(failure)) {}

    [[nodiscard]] const std::optional<Failure>& failure() const noexcept {
        return failure_;
    }

private:
    std::optional<Failure> failure_;
};

enum class HostStateKind : std::int32_t {
    new_ = CODEX_AGENT_HOST_STATE_NEW,
    restoring = CODEX_AGENT_HOST_STATE_RESTORING,
    workspace_required = CODEX_AGENT_HOST_STATE_WORKSPACE_REQUIRED,
    preparing = CODEX_AGENT_HOST_STATE_PREPARING,
    ready = CODEX_AGENT_HOST_STATE_READY,
    failed = CODEX_AGENT_HOST_STATE_FAILED,
    closed = CODEX_AGENT_HOST_STATE_CLOSED,
};

enum class ApprovalDecision : std::int32_t {
    accept = CODEX_AGENT_APPROVAL_DECISION_ACCEPT,
    decline = CODEX_AGENT_APPROVAL_DECISION_DECLINE,
};

enum class AuthenticationStatus : std::int32_t {
    signed_out = CODEX_AGENT_AUTHENTICATION_STATUS_SIGNED_OUT,
    authenticating = CODEX_AGENT_AUTHENTICATION_STATUS_AUTHENTICATING,
    authenticated = CODEX_AGENT_AUTHENTICATION_STATUS_AUTHENTICATED,
};

enum class Capability : std::int32_t {
    web_search = CODEX_AGENT_CAPABILITY_WEB_SEARCH,
};

enum class CatalogFreshness : std::int32_t {
    live = CODEX_AGENT_CATALOG_FRESHNESS_LIVE,
    fresh_cache = CODEX_AGENT_CATALOG_FRESHNESS_FRESH_CACHE,
    stale_cache = CODEX_AGENT_CATALOG_FRESHNESS_STALE_CACHE,
};

enum class CollaborationMode : std::int32_t {
    default_ = CODEX_AGENT_COLLABORATION_MODE_DEFAULT,
    plan = CODEX_AGENT_COLLABORATION_MODE_PLAN,
};

enum class WorkspaceSelectionReason : std::int32_t {
    not_selected = CODEX_AGENT_WORKSPACE_REASON_NOT_SELECTED,
    not_found = CODEX_AGENT_WORKSPACE_REASON_NOT_FOUND,
    access_revoked = CODEX_AGENT_WORKSPACE_REASON_ACCESS_REVOKED,
    invalid_selection = CODEX_AGENT_WORKSPACE_REASON_INVALID_SELECTION,
};

enum class ConversationStatus : std::int32_t {
    new_ = CODEX_AGENT_CONVERSATION_STATUS_NEW,
    opening = CODEX_AGENT_CONVERSATION_STATUS_OPENING,
    ready = CODEX_AGENT_CONVERSATION_STATUS_READY,
    starting_turn = CODEX_AGENT_CONVERSATION_STATUS_STARTING_TURN,
    running_turn = CODEX_AGENT_CONVERSATION_STATUS_RUNNING_TURN,
    cancelling_turn = CODEX_AGENT_CONVERSATION_STATUS_CANCELLING_TURN,
    reloading = CODEX_AGENT_CONVERSATION_STATUS_RELOADING,
    failed = CODEX_AGENT_CONVERSATION_STATUS_FAILED,
    closed = CODEX_AGENT_CONVERSATION_STATUS_CLOSED,
};

enum class ApprovalPreset : std::int32_t {
    never = CODEX_AGENT_APPROVAL_PRESET_NEVER,
    auto_review = CODEX_AGENT_APPROVAL_PRESET_AUTO_REVIEW,
    ask_me = CODEX_AGENT_APPROVAL_PRESET_ASK_ME,
    strict = CODEX_AGENT_APPROVAL_PRESET_STRICT,
};

enum class ElicitationAction : std::int32_t {
    accept = CODEX_AGENT_ELICITATION_ACTION_ACCEPT,
    decline = CODEX_AGENT_ELICITATION_ACTION_DECLINE,
    cancel = CODEX_AGENT_ELICITATION_ACTION_CANCEL,
};

enum class ElicitationValidationReason : std::int32_t {
    missing_required = CODEX_AGENT_ELICITATION_VALIDATION_MISSING_REQUIRED,
    unknown_field = CODEX_AGENT_ELICITATION_VALIDATION_UNKNOWN_FIELD,
    invalid_type = CODEX_AGENT_ELICITATION_VALIDATION_INVALID_TYPE,
    non_finite_number = CODEX_AGENT_ELICITATION_VALIDATION_NON_FINITE_NUMBER,
    below_minimum = CODEX_AGENT_ELICITATION_VALIDATION_BELOW_MINIMUM,
    above_maximum = CODEX_AGENT_ELICITATION_VALIDATION_ABOVE_MAXIMUM,
    non_integer = CODEX_AGENT_ELICITATION_VALIDATION_NON_INTEGER,
    invalid_format = CODEX_AGENT_ELICITATION_VALIDATION_INVALID_FORMAT,
    invalid_selection = CODEX_AGENT_ELICITATION_VALIDATION_INVALID_SELECTION,
    duplicate_selection = CODEX_AGENT_ELICITATION_VALIDATION_DUPLICATE_SELECTION,
};

enum class FormFieldType : std::int32_t {
    string = CODEX_AGENT_FORM_FIELD_TYPE_STRING,
    number = CODEX_AGENT_FORM_FIELD_TYPE_NUMBER,
    integer = CODEX_AGENT_FORM_FIELD_TYPE_INTEGER,
    boolean = CODEX_AGENT_FORM_FIELD_TYPE_BOOLEAN,
    single_select = CODEX_AGENT_FORM_FIELD_TYPE_SINGLE_SELECT,
    multi_select = CODEX_AGENT_FORM_FIELD_TYPE_MULTI_SELECT,
};

enum class FormStringFormat : std::int32_t {
    email = CODEX_AGENT_FORM_STRING_FORMAT_EMAIL,
    uri = CODEX_AGENT_FORM_STRING_FORMAT_URI,
    date = CODEX_AGENT_FORM_STRING_FORMAT_DATE,
    date_time = CODEX_AGENT_FORM_STRING_FORMAT_DATE_TIME,
};

enum class HookRunStatus : std::int32_t {
    running = CODEX_AGENT_HOOK_RUN_STATUS_RUNNING,
    completed = CODEX_AGENT_HOOK_RUN_STATUS_COMPLETED,
    failed = CODEX_AGENT_HOOK_RUN_STATUS_FAILED,
    blocked = CODEX_AGENT_HOOK_RUN_STATUS_BLOCKED,
    stopped = CODEX_AGENT_HOOK_RUN_STATUS_STOPPED,
};

enum class HookTrustStatus : std::int32_t {
    managed = CODEX_AGENT_HOOK_TRUST_STATUS_MANAGED,
    untrusted = CODEX_AGENT_HOOK_TRUST_STATUS_UNTRUSTED,
    trusted = CODEX_AGENT_HOOK_TRUST_STATUS_TRUSTED,
    modified = CODEX_AGENT_HOOK_TRUST_STATUS_MODIFIED,
};

enum class InstallationScope : std::int32_t {
    user = CODEX_AGENT_INSTALLATION_SCOPE_USER,
    workspace = CODEX_AGENT_INSTALLATION_SCOPE_WORKSPACE,
};

enum class IntegrationAuthorizationStatus : std::int32_t {
    idle = CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_IDLE,
    starting = CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_STARTING,
    awaiting_completion = CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_AWAITING_COMPLETION,
    authorized = CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_AUTHORIZED,
    failed = CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_FAILED,
};

enum class McpAuthStatus : std::int32_t {
    unknown = CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN,
    unsupported = CODEX_AGENT_MCP_AUTH_STATUS_UNSUPPORTED,
    not_logged_in = CODEX_AGENT_MCP_AUTH_STATUS_NOT_LOGGED_IN,
    bearer_token = CODEX_AGENT_MCP_AUTH_STATUS_BEARER_TOKEN,
    oauth = CODEX_AGENT_MCP_AUTH_STATUS_OAUTH,
};

enum class McpAuthentication : std::int32_t {
    oauth = CODEX_AGENT_MCP_AUTHENTICATION_OAUTH,
    chat_gpt = CODEX_AGENT_MCP_AUTHENTICATION_CHAT_GPT,
};

enum class McpEnvironmentSource : std::int32_t {
    local = CODEX_AGENT_MCP_ENVIRONMENT_SOURCE_LOCAL,
    remote = CODEX_AGENT_MCP_ENVIRONMENT_SOURCE_REMOTE,
};

enum class McpToolApproval : std::int32_t {
    auto_ = CODEX_AGENT_MCP_TOOL_APPROVAL_AUTO,
    prompt = CODEX_AGENT_MCP_TOOL_APPROVAL_PROMPT,
    writes = CODEX_AGENT_MCP_TOOL_APPROVAL_WRITES,
    approve = CODEX_AGENT_MCP_TOOL_APPROVAL_APPROVE,
};

enum class McpToolExposureSurface : std::int32_t {
    code_mode = CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_CODE_MODE,
    deferred = CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_DEFERRED,
    direct = CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_DIRECT,
};

enum class MessageRole : std::int32_t {
    user = CODEX_AGENT_MESSAGE_ROLE_USER,
    assistant = CODEX_AGENT_MESSAGE_ROLE_ASSISTANT,
};

enum class PlanStepStatus : std::int32_t {
    pending = CODEX_AGENT_PLAN_STEP_PENDING,
    in_progress = CODEX_AGENT_PLAN_STEP_IN_PROGRESS,
    completed = CODEX_AGENT_PLAN_STEP_COMPLETED,
};

enum class PluginAuthPolicy : std::int32_t {
    on_install = CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_INSTALL,
    on_use = CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_USE,
};

enum class PluginInstallPolicy : std::int32_t {
    not_available = CODEX_AGENT_PLUGIN_INSTALL_POLICY_NOT_AVAILABLE,
    available = CODEX_AGENT_PLUGIN_INSTALL_POLICY_AVAILABLE,
    installed_by_default = CODEX_AGENT_PLUGIN_INSTALL_POLICY_INSTALLED_BY_DEFAULT,
};

enum class Resolution : std::int32_t {
    preferred = CODEX_AGENT_RESOLUTION_PREFERRED,
    default_ = CODEX_AGENT_RESOLUTION_DEFAULT,
    first = CODEX_AGENT_RESOLUTION_FIRST,
};

enum class ResourceOrigin : std::int32_t {
    user = CODEX_AGENT_RESOURCE_ORIGIN_USER,
    workspace = CODEX_AGENT_RESOURCE_ORIGIN_WORKSPACE,
    plugin = CODEX_AGENT_RESOURCE_ORIGIN_PLUGIN,
    managed = CODEX_AGENT_RESOURCE_ORIGIN_MANAGED,
    unknown = CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN,
};

enum class SkillScope : std::int32_t {
    system = CODEX_AGENT_SKILL_SCOPE_SYSTEM,
    user = CODEX_AGENT_SKILL_SCOPE_USER,
    repo = CODEX_AGENT_SKILL_SCOPE_REPO,
    plugin = CODEX_AGENT_SKILL_SCOPE_PLUGIN,
    admin = CODEX_AGENT_SKILL_SCOPE_ADMIN,
};

enum class WorkActivity : std::int32_t {
    running_command = CODEX_AGENT_WORK_ACTIVITY_RUNNING_COMMAND,
    writing_files = CODEX_AGENT_WORK_ACTIVITY_WRITING_FILES,
};

enum class AuthorizationPurpose : std::int32_t {
    chat_gpt = CODEX_AGENT_AUTHORIZATION_PURPOSE_CHAT_GPT,
    external = CODEX_AGENT_AUTHORIZATION_PURPOSE_EXTERNAL,
};

struct ClientInfo {
    ClientInfo() = default;
    ClientInfo(std::string name_value, std::string title_value,
               std::string version_value)
        : name(std::move(name_value)),
          title(std::move(title_value)),
          version(std::move(version_value)) {
        const auto valid = [](const std::string& value) {
            return value.find_first_not_of(" \t\n\r\f\v") !=
                       std::string::npos &&
                   std::none_of(value.begin(), value.end(), [](unsigned char byte) {
                       return std::iscntrl(byte) != 0;
                   });
        };
        if (!valid(name) || !valid(title) || !valid(version)) {
            throw std::invalid_argument("Client information is invalid");
        }
    }

    std::string name;
    std::string title;
    std::string version;
};

struct ConversationId {
    explicit ConversationId(std::string value_value)
        : value(std::move(value_value)) {
        if (value.find_first_not_of(" \t\n\r\f\v") == std::string::npos) {
            throw std::invalid_argument("Conversation ID must not be blank");
        }
    }

    std::string value;
};

struct ConversationSettings {
    ApprovalPreset approval_preset = ApprovalPreset::auto_review;
    std::optional<std::string> service_tier;
};

struct HostOptions {
    std::string bundle_directory;
    std::string data_directory;
    ClientInfo client_info;
};

struct ConversationOpenOptions {
    std::optional<std::string> conversation_id;
    std::optional<ApprovalPreset> approval_preset;
    std::optional<std::string> service_tier;
};

struct Workspace {
    Workspace() = default;
    explicit Workspace(std::string path_value,
                       std::optional<std::string> display_name_value = std::nullopt)
        : path(std::move(path_value)),
          display_name(display_name_value.value_or(path)) {
        if (path.find_first_not_of(" \t\n\r\f\v") == std::string::npos ||
            path.find('\0') != std::string::npos ||
            display_name.find_first_not_of(" \t\n\r\f\v") ==
                std::string::npos) {
            throw std::invalid_argument("Workspace is invalid");
        }
    }

    std::string path;
    std::string display_name;
};

struct ElicitationValidationIssue {
    std::string field_name;
    ElicitationValidationReason reason;
};

struct ElicitationValidation {
    std::vector<ElicitationValidationIssue> issues;

    [[nodiscard]] bool is_valid() const noexcept { return issues.empty(); }
};

struct FormOption {
    std::string value;
    std::string title;
    std::optional<std::string> description;
};

struct McpEnvironmentVariable {
    explicit McpEnvironmentVariable(
        std::string name_value,
        std::optional<McpEnvironmentSource> source_value = std::nullopt)
        : name(std::move(name_value)), source(source_value) {
        if (name.find_first_not_of(" \t\n\r\f\v") == std::string::npos) {
            throw std::invalid_argument(
                "MCP environment variable name must not be blank");
        }
    }

    std::string name;
    std::optional<McpEnvironmentSource> source;
};

struct McpOauthConfiguration {
    explicit McpOauthConfiguration(
        std::optional<std::string> client_id_value = std::nullopt,
        std::optional<std::int32_t> callback_port_value = std::nullopt)
        : client_id(std::move(client_id_value)), callback_port(callback_port_value) {
        if (callback_port && (*callback_port < 1 || *callback_port > 65535)) {
            throw std::invalid_argument("MCP OAuth callback port is invalid");
        }
    }

    std::optional<std::string> client_id;
    std::optional<std::int32_t> callback_port;
};

struct McpToolConfiguration {
    std::optional<McpToolApproval> approval;
};

namespace detail {

inline bool non_blank(std::string_view value) {
    return value.find_first_not_of(" \t\n\r\f\v") != std::string_view::npos;
}

inline bool safe_mcp_http_url(std::string_view value) {
    if (value.find_first_of(" \t\n\r\f\v") != std::string_view::npos) return false;
    const auto scheme_end = value.find("://");
    if (scheme_end == std::string_view::npos) return false;
    auto scheme = value.substr(0, scheme_end);
    auto authority = value.substr(scheme_end + 3);
    authority = authority.substr(0, authority.find_first_of("/?#"));
    if (authority.empty() || authority.find('@') != std::string_view::npos) {
        return false;
    }
    std::string_view host;
    std::string_view port;
    if (authority.front() == '[') {
        const auto close = authority.find(']');
        if (close == std::string_view::npos) return false;
        host = authority.substr(1, close - 1);
        const auto suffix = authority.substr(close + 1);
        if (!suffix.empty()) {
            if (suffix.front() != ':') return false;
            port = suffix.substr(1);
        }
    } else {
        const auto colon = authority.rfind(':');
        if (colon == std::string_view::npos) {
            host = authority;
        } else {
            host = authority.substr(0, colon);
            port = authority.substr(colon + 1);
        }
    }
    if (host.empty() || (!port.empty() &&
            !std::all_of(port.begin(), port.end(), [](unsigned char value) {
                return std::isdigit(value) != 0;
            }))) {
        return false;
    }
    if (scheme == "https") return true;
    if (scheme != "http") return false;
    std::string normalized(host);
    std::transform(normalized.begin(), normalized.end(), normalized.begin(),
                   [](unsigned char value) {
                       return static_cast<char>(std::tolower(value));
                   });
    return normalized == "localhost" || normalized == "127.0.0.1" ||
           normalized == "::1";
}

}  // namespace detail

struct McpHttpTransport {
    explicit McpHttpTransport(
        std::string url_value,
        std::optional<std::string> bearer_token_environment_variable_value =
            std::nullopt,
        std::optional<std::map<std::string, std::string>> headers_value =
            std::nullopt,
        std::optional<std::map<std::string, std::string>>
            environment_headers_value = std::nullopt,
        std::optional<std::string> headers_helper_value = std::nullopt)
        : url(std::move(url_value)),
          bearer_token_environment_variable(
              std::move(bearer_token_environment_variable_value)),
          headers(std::move(headers_value)),
          environment_headers(std::move(environment_headers_value)),
          headers_helper(std::move(headers_helper_value)) {
        if (!detail::safe_mcp_http_url(url) ||
            (bearer_token_environment_variable &&
             !detail::non_blank(*bearer_token_environment_variable)) ||
            (headers_helper && !detail::non_blank(*headers_helper))) {
            throw std::invalid_argument("MCP HTTP transport is invalid");
        }
    }

    std::string url;
    std::optional<std::string> bearer_token_environment_variable;
    std::optional<std::map<std::string, std::string>> headers;
    std::optional<std::map<std::string, std::string>> environment_headers;
    std::optional<std::string> headers_helper;
};

struct McpStdioTransport {
    explicit McpStdioTransport(
        std::string command_value,
        std::vector<std::string> arguments_value = {},
        std::optional<std::string> working_directory_value = std::nullopt,
        std::optional<std::map<std::string, std::string>> environment_value =
            std::nullopt,
        std::vector<McpEnvironmentVariable> forwarded_environment_value = {})
        : command(std::move(command_value)),
          arguments(std::move(arguments_value)),
          working_directory(std::move(working_directory_value)),
          environment(std::move(environment_value)),
          forwarded_environment(std::move(forwarded_environment_value)) {
        if (!detail::non_blank(command)) {
            throw std::invalid_argument("MCP stdio command must not be blank");
        }
    }

    std::string command;
    std::vector<std::string> arguments;
    std::optional<std::string> working_directory;
    std::optional<std::map<std::string, std::string>> environment;
    std::vector<McpEnvironmentVariable> forwarded_environment;
};

using McpTransport = std::variant<McpHttpTransport, McpStdioTransport>;

struct McpServerConfiguration {
    explicit McpServerConfiguration(
        std::string name_value, McpTransport transport_value,
        std::optional<McpAuthentication> authentication_value = std::nullopt,
        std::string environment_id_value = "local", bool is_enabled_value = true,
        bool is_required_value = false,
        bool supports_parallel_tool_calls_value = false,
        std::optional<std::vector<McpToolExposureSurface>> omit_tools_from_value =
            std::nullopt,
        std::optional<double> startup_timeout_seconds_value = std::nullopt,
        std::optional<double> tool_timeout_seconds_value = std::nullopt,
        std::optional<McpToolApproval> default_tool_approval_value = std::nullopt,
        std::optional<std::vector<std::string>> enabled_tools_value = std::nullopt,
        std::optional<std::vector<std::string>> disabled_tools_value = std::nullopt,
        std::optional<std::vector<std::string>> scopes_value = std::nullopt,
        std::optional<McpOauthConfiguration> oauth_value = std::nullopt,
        std::optional<std::string> oauth_resource_value = std::nullopt,
        std::map<std::string, McpToolConfiguration> tools_value = {})
        : name(std::move(name_value)),
          transport(std::move(transport_value)),
          authentication(authentication_value),
          environment_id(std::move(environment_id_value)),
          is_enabled(is_enabled_value),
          is_required(is_required_value),
          supports_parallel_tool_calls(supports_parallel_tool_calls_value),
          omit_tools_from(std::move(omit_tools_from_value)),
          startup_timeout_seconds(startup_timeout_seconds_value),
          tool_timeout_seconds(tool_timeout_seconds_value),
          default_tool_approval(default_tool_approval_value),
          enabled_tools(std::move(enabled_tools_value)),
          disabled_tools(std::move(disabled_tools_value)),
          scopes(std::move(scopes_value)),
          oauth(std::move(oauth_value)),
          oauth_resource(std::move(oauth_resource_value)),
          tools(std::move(tools_value)) {
        const auto valid_name = !name.empty() &&
            std::all_of(name.begin(), name.end(), [](unsigned char value) {
                return std::isalnum(value) != 0 || value == '-' || value == '_';
            });
        const auto valid_timeout = [](const std::optional<double>& value) {
            return !value || (std::isfinite(*value) && *value > 0.0);
        };
        const auto stdio = std::holds_alternative<McpStdioTransport>(transport);
        const auto local_headers_helper = [&] {
            const auto* http = std::get_if<McpHttpTransport>(&transport);
            return !http || !http->headers_helper || environment_id == "local";
        }();
        if (!valid_name || !detail::non_blank(environment_id) ||
            !valid_timeout(startup_timeout_seconds) ||
            !valid_timeout(tool_timeout_seconds) ||
            (stdio && (authentication || oauth || oauth_resource)) ||
            !local_headers_helper) {
            throw std::invalid_argument("MCP server configuration is invalid");
        }
    }

    std::string name;
    McpTransport transport;
    std::optional<McpAuthentication> authentication;
    std::string environment_id;
    bool is_enabled;
    bool is_required;
    bool supports_parallel_tool_calls;
    std::optional<std::vector<McpToolExposureSurface>> omit_tools_from;
    std::optional<double> startup_timeout_seconds;
    std::optional<double> tool_timeout_seconds;
    std::optional<McpToolApproval> default_tool_approval;
    std::optional<std::vector<std::string>> enabled_tools;
    std::optional<std::vector<std::string>> disabled_tools;
    std::optional<std::vector<std::string>> scopes;
    std::optional<McpOauthConfiguration> oauth;
    std::optional<std::string> oauth_resource;
    std::map<std::string, McpToolConfiguration> tools;
};

struct McpServer {
    McpServer(std::string name_value, std::string display_name_value,
              McpAuthStatus auth_status_value,
              std::optional<McpServerConfiguration> configuration_value =
                  std::nullopt,
              ResourceOrigin origin_value = ResourceOrigin::unknown,
              bool can_remove_value = false)
        : name(std::move(name_value)),
          display_name(std::move(display_name_value)),
          auth_status(auth_status_value),
          configuration(std::move(configuration_value)),
          origin(origin_value),
          can_remove(can_remove_value) {}

    [[nodiscard]] bool is_authorized() const noexcept {
        return auth_status == McpAuthStatus::bearer_token ||
               auth_status == McpAuthStatus::oauth;
    }

    std::string name;
    std::string display_name;
    McpAuthStatus auth_status;
    std::optional<McpServerConfiguration> configuration;
    ResourceOrigin origin;
    bool can_remove;
};

struct PlanStep {
    std::string text;
    PlanStepStatus status;
};

struct PlanProgress {
    std::optional<std::string> explanation;
    std::vector<PlanStep> steps;
};

struct ServiceTier {
    std::string id;
    std::string name;
    std::string description;
};

struct Model {
    std::string id;
    std::string display_name;
    std::string description;
    std::vector<std::string> supported_efforts;
    std::string default_effort;
    bool is_default = false;
    std::vector<ServiceTier> service_tiers;
    std::optional<std::string> default_service_tier;
};

struct Connector {
    std::string id;
    std::string name;
    std::string description;
    std::optional<std::string> install_url;
    bool is_accessible = false;
    bool is_enabled = true;
    std::vector<std::string> plugin_names;
};

struct PluginReference {
    std::string id;
    std::string name;
    std::string marketplace_name;
    std::optional<std::string> marketplace_path;
    std::optional<std::string> remote_plugin_id;

    [[nodiscard]] std::string uri() const {
        return "plugin://" + name + "@" + marketplace_name;
    }
};

struct PluginSkill {
    std::string name;
    std::string description;
    bool is_enabled = false;
    std::optional<std::string> path;
};

struct PluginSummary {
    PluginReference reference;
    std::string display_name;
    std::string description;
    bool is_installed = false;
    bool is_enabled = false;
    PluginInstallPolicy install_policy;
    PluginAuthPolicy auth_policy;
    bool is_available = false;
    std::vector<std::string> capabilities;
    std::optional<std::string> brand_color;
    std::optional<std::string> privacy_policy_url;
    std::optional<std::string> terms_of_service_url;
    std::optional<std::string> website_url;
};

struct PluginCatalog {
    std::vector<PluginSummary> plugins;
    std::vector<std::string> errors;
    CatalogFreshness freshness = CatalogFreshness::live;
};

struct PluginDetail {
    PluginSummary summary;
    std::string description;
    std::vector<PluginSkill> skills;
    std::vector<Connector> connectors;
    std::vector<std::string> mcp_servers;
    std::int32_t hook_count = 0;
};

struct PluginInstallResult {
    PluginAuthPolicy auth_policy;
    std::vector<Connector> connectors_needing_authentication;
    std::optional<std::string> message;
};

struct Skill {
    Skill(std::string name_value, std::string display_name_value,
          std::string description_value, std::string path_value,
          SkillScope scope_value, bool is_enabled_value,
          std::optional<std::string> brand_color_value = std::nullopt,
          std::vector<std::string> dependencies_value = {},
          bool can_uninstall_value = false,
          std::optional<ResourceOrigin> origin_value = std::nullopt)
        : name(std::move(name_value)),
          display_name(std::move(display_name_value)),
          description(std::move(description_value)),
          path(std::move(path_value)),
          scope(scope_value),
          is_enabled(is_enabled_value),
          brand_color(std::move(brand_color_value)),
          dependencies(std::move(dependencies_value)),
          can_uninstall(can_uninstall_value),
          origin(origin_value.value_or(origin_for(scope_value))) {}

    std::string name;
    std::string display_name;
    std::string description;
    std::string path;
    SkillScope scope;
    bool is_enabled = false;
    std::optional<std::string> brand_color;
    std::vector<std::string> dependencies;
    bool can_uninstall = false;
    ResourceOrigin origin = ResourceOrigin::unknown;

private:
    static constexpr ResourceOrigin origin_for(SkillScope value) noexcept {
        switch (value) {
            case SkillScope::user: return ResourceOrigin::user;
            case SkillScope::repo: return ResourceOrigin::workspace;
            case SkillScope::plugin: return ResourceOrigin::plugin;
            case SkillScope::system:
            case SkillScope::admin: return ResourceOrigin::managed;
        }
        return ResourceOrigin::unknown;
    }
};

struct SkillCatalog {
    std::vector<Skill> skills;
    std::vector<std::string> errors;
};

struct SkillChunk {
    std::string content;
    std::optional<std::int64_t> next_offset;
    std::int64_t total_bytes = 0;
};

struct HookActivity {
    std::string id;
    std::string event_name;
    std::string handler_type;
    HookRunStatus status;
    std::optional<std::string> status_message;
    std::vector<std::string> details;
};

struct TurnProgress {
    std::string text;
    std::string commentary;
    std::string reasoning;
    std::string plan;
    std::optional<PlanProgress> plan_progress;
    std::string shell_output;
    std::optional<std::int32_t> shell_exit_code;
    std::optional<WorkActivity> work_activity;
    std::vector<HookActivity> hook_activities;
    bool is_truncated = false;
};

inline std::string_view approval_preset_display_name(ApprovalPreset value) noexcept {
    switch (value) {
        case ApprovalPreset::never: return "Never";
        case ApprovalPreset::auto_review: return "Auto review";
        case ApprovalPreset::ask_me: return "Ask me";
        case ApprovalPreset::strict: return "Strict";
    }
    return {};
}

inline std::string_view capability_id(Capability) noexcept { return "web_search"; }
inline std::string_view capability_display_label(Capability) noexcept {
    return "Web search";
}
inline std::string_view capability_prompt_label(Capability) noexcept {
    return "Search the web";
}
inline std::optional<std::string_view> capability_icon(Capability) noexcept {
    return "globe";
}

inline std::string_view skill_scope_display_name(SkillScope value) noexcept {
    switch (value) {
        case SkillScope::system: return "System";
        case SkillScope::user: return "User";
        case SkillScope::repo: return "Repository";
        case SkillScope::plugin: return "Plugin";
        case SkillScope::admin: return "Admin";
    }
    return {};
}

struct AuthorizationUrl {
    [[nodiscard]] static AuthorizationUrl chat_gpt(std::string value);

    [[nodiscard]] static AuthorizationUrl external(std::string value);

    std::string value;
    AuthorizationPurpose purpose;
};

struct ApiKeyAuthentication {
    explicit ApiKeyAuthentication(std::string value_value)
        : value(std::move(value_value)) {
        if (!detail::non_blank(value)) {
            throw std::invalid_argument("API key must not be blank");
        }
    }
    std::string value;
};

struct ChatGptBrowserAuthentication {};
struct ChatGptDeviceCodeAuthentication {};
inline constexpr ChatGptBrowserAuthentication chat_gpt_browser_authentication{};
inline constexpr ChatGptDeviceCodeAuthentication
    chat_gpt_device_code_authentication{};

struct AuthenticationState {
    AuthenticationStatus status;
    std::optional<AuthorizationUrl> pending_sign_in_url;
    std::optional<AuthorizationUrl> device_verification_url;
    std::optional<std::string> device_user_code;
    std::optional<Failure> failure;
};

struct FormBooleanValue { bool value; };
struct FormNumberValue { double value; };
struct FormTextValue { std::string value; };
struct FormTextListValue { std::vector<std::string> value; };
using FormValue = std::variant<FormBooleanValue, FormNumberValue, FormTextValue,
                               FormTextListValue>;

struct FormField {
    std::string name;
    std::string title;
    std::optional<std::string> description;
    FormFieldType type;
    bool is_required = false;
    bool is_secret = false;
    std::optional<FormStringFormat> format;
    std::optional<FormValue> default_value;
    std::optional<double> minimum;
    std::optional<double> maximum;
    std::optional<std::int64_t> minimum_length;
    std::optional<std::int64_t> maximum_length;
    std::vector<FormOption> options;
    bool allows_other = false;
    std::optional<std::int64_t> minimum_selections;
    std::optional<std::int64_t> maximum_selections;

    [[nodiscard]] bool accepts(
        const std::optional<FormValue>& value) const;
};

struct ElicitationResponse;

struct Elicitation {
    std::string request_id;
    ConversationId conversation_id;
    std::string server_name;
    std::string message;
    std::optional<std::string> url;
    std::optional<std::vector<FormField>> form;

    [[nodiscard]] std::map<std::string, FormValue> initial_values() const;
    [[nodiscard]] ElicitationValidation validate(
        const std::map<std::string, FormValue>& content) const;
    [[nodiscard]] ElicitationResponse accept(
        const std::map<std::string, FormValue>& content) const;
    [[nodiscard]] bool accepts(const ElicitationResponse& response) const;
};

struct ElicitationResponse {
    [[nodiscard]] static ElicitationResponse decline();

    [[nodiscard]] static ElicitationResponse cancel();

    ElicitationAction action;
    std::map<std::string, FormValue> content;
};

struct HookHandlerAgent {};
struct HookHandlerPrompt {};
inline constexpr HookHandlerAgent hook_handler_agent{};
inline constexpr HookHandlerPrompt hook_handler_prompt{};

struct HookHandlerCommand {
    std::string command;
    bool is_async = false;
};

struct HookHandlerMcpTool {
    std::string server;
    std::string tool;
};

using HookHandler = std::variant<HookHandlerAgent, HookHandlerCommand,
                                 HookHandlerMcpTool, HookHandlerPrompt>;

struct Hook {
    std::string key;
    std::string event_name;
    std::optional<std::string> matcher;
    HookHandler handler;
    std::int64_t timeout_seconds = 0;
    HookTrustStatus trust_status;
    std::string current_hash;
    bool is_enabled = false;
    std::string source;
    std::string source_path;
    ResourceOrigin origin;
    std::optional<std::string> plugin_id;
    bool is_managed = false;
    bool can_trust = false;
    bool can_uninstall = false;
    std::optional<std::string> status_message;
};

struct HookCatalog {
    std::vector<Hook> hooks;
    std::vector<std::string> warnings;
    std::vector<std::string> errors;
};

struct Integration {
    std::string id;
    std::string display_name;
};

struct ConnectorIntegration : Integration {
    Connector connector;
};

struct McpServerIntegration : Integration {
    McpServer server;
};

using IntegrationValue = std::variant<ConnectorIntegration, McpServerIntegration>;

struct IntegrationAuthorizationState {
    IntegrationAuthorizationStatus status;
    std::optional<IntegrationValue> target;
    std::optional<Failure> failure;
};

struct Invocation {
    std::string key;
    std::string name;
};

struct PluginInvocation : Invocation {
    std::string uri;
};

struct SkillInvocation : Invocation {
    std::string path;
};

using InvocationValue = std::variant<PluginInvocation, SkillInvocation>;

struct Message {
    std::string id;
    MessageRole role;
    std::string text;
    std::optional<std::string> reasoning;
    std::optional<std::string> plan;
    std::optional<std::string> shell_command;
    std::optional<std::int32_t> exit_code;
    std::vector<InvocationValue> invocations;
    std::set<Capability> capabilities;
    CollaborationMode collaboration_mode = CollaborationMode::default_;
    std::optional<std::string> client_message_id;
};

struct TurnRequest {
    std::string prompt;
    std::optional<std::string> model;
    std::optional<std::string> effort;
    ApprovalPreset approval_preset = ApprovalPreset::auto_review;
    std::optional<std::string> service_tier;
    std::set<Capability> capabilities;
    CollaborationMode collaboration_mode = CollaborationMode::default_;
    std::vector<InvocationValue> invocations;
    std::optional<std::string> client_message_id;
};

struct PendingInteraction {
    PendingInteraction(
        std::string request_id_value,
        ConversationId conversation_id_value,
        std::shared_ptr<detail::LivePending> native_identity = nullptr)
        : request_id(std::move(request_id_value)),
          conversation_id(std::move(conversation_id_value)),
          _native_identity(std::move(native_identity)) {}

    std::string request_id;
    ConversationId conversation_id;
    std::shared_ptr<detail::LivePending> _native_identity;
};

struct PendingApproval : PendingInteraction {
    std::string title;
    std::string details;
};

struct PendingElicitation : PendingInteraction {
    Elicitation elicitation;
};

using PendingInteractionValue = std::variant<PendingApproval, PendingElicitation>;

struct InteractionState {
    std::vector<PendingInteractionValue> pending;
    std::set<std::string> resolving_request_ids;
    std::optional<Failure> failure;

    [[nodiscard]] std::vector<PendingInteractionValue> pending_for(
        const ConversationId& conversation_id) const;

    [[nodiscard]] bool is_resolving(
        const PendingInteraction& interaction) const;
};

struct PathWorkspaceSelection {
    explicit PathWorkspaceSelection(std::string path_value)
        : path(std::move(path_value)) {
        if (!detail::non_blank(path)) {
            throw std::invalid_argument("workspace path must not be blank");
        }
    }
    std::string path;
};

struct WorkspaceAvailable { Workspace workspace; };
struct WorkspaceSelectionRequired {
    WorkspaceSelectionReason reason;
    std::string message;
};

struct HostStateNew {};
struct HostStateRestoring {};
struct HostStateClosed {};
inline constexpr HostStateNew host_state_new{};
inline constexpr HostStateRestoring host_state_restoring{};
inline constexpr HostStateClosed host_state_closed{};

struct HostStatePreparing { Workspace workspace; };
struct HostStateWorkspaceRequired { WorkspaceSelectionRequired requirement; };
struct HostStateFailed {
    Failure failure;
    std::optional<Workspace> workspace;
};

struct WorkspaceRequirement {
    WorkspaceSelectionReason reason;
    std::string message;
};

struct HostState {
    HostStateKind kind;
    std::optional<Workspace> workspace;
    std::optional<WorkspaceRequirement> requirement;
    std::optional<Failure> failure;
};

struct ConversationSummary {
    ConversationId conversation_id;
    std::string title;
    std::int64_t updated_at_epoch_seconds;
};

struct ConversationValue {
    ConversationSummary summary;
    std::vector<Message> messages;
};

struct ConversationState {
    explicit ConversationState(
        ConversationStatus status_value,
        std::optional<Failure> failure_value = std::nullopt,
        std::optional<ConversationId> conversation_id_value = std::nullopt,
        std::optional<ConversationValue> conversation_value = std::nullopt,
        std::optional<std::string> model_value = std::nullopt,
        std::optional<std::string> effort_value = std::nullopt,
        std::optional<std::string> service_tier_value = std::nullopt,
        TurnProgress turn_progress_value = {}, bool can_start_turn_value = false,
        bool can_cancel_turn_value = false, bool can_reload_value = false)
        : status(status_value),
          failure(std::move(failure_value)),
          conversation_id(std::move(conversation_id_value)),
          conversation(std::move(conversation_value)),
          model(std::move(model_value)),
          effort(std::move(effort_value)),
          service_tier(std::move(service_tier_value)),
          turn_progress(std::move(turn_progress_value)),
          can_start_turn(can_start_turn_value),
          can_cancel_turn(can_cancel_turn_value),
          can_reload(can_reload_value) {}

    ConversationStatus status;
    std::optional<Failure> failure;
    std::optional<ConversationId> conversation_id;
    std::optional<ConversationValue> conversation;
    std::optional<std::string> model;
    std::optional<std::string> effort;
    std::optional<std::string> service_tier;
    TurnProgress turn_progress;
    bool can_start_turn = false;
    bool can_cancel_turn = false;
    bool can_reload = false;
};

template <typename Value>
struct StateEvent {
    Status status;
    std::optional<Value> value;
    bool terminal;
};

class Host;
class Agent;
class Authentication;
class Connectors;
class Conversations;
class Conversation;
class Hooks;
class IntegrationAuthorization;
class Interactions;
class McpServers;
class Models;
class Plugins;
class Skills;

namespace detail {

inline codex_agent_string_view_t string_view(std::string_view value) noexcept {
    return {
        reinterpret_cast<const std::uint8_t*>(value.data()),
        value.size(),
    };
}

inline void check(codex_agent_status_t status) {
    if (status != CODEX_AGENT_STATUS_OK) {
        throw Error(status_from_raw(status));
    }
}

template <typename Copy>
std::string copy_string(Copy&& copy) {
    std::size_t required = 0;
    auto status = copy(nullptr, 0, &required);
    if (status != CODEX_AGENT_STATUS_OK && status != CODEX_AGENT_STATUS_BUFFER_TOO_SMALL) {
        check(status);
    }
    std::string result(required, '\0');
    if (required != 0) {
        check(copy(reinterpret_cast<std::uint8_t*>(result.data()), result.size(), &required));
        result.resize(required);
    }
    return result;
}

template <typename Copy>
std::optional<std::string> copy_optional_string(Copy&& copy) {
    std::size_t required = 0;
    const auto status = copy(nullptr, 0, &required);
    if (status == CODEX_AGENT_STATUS_NOT_READY) {
        return std::nullopt;
    }
    if (status != CODEX_AGENT_STATUS_OK && status != CODEX_AGENT_STATUS_BUFFER_TOO_SMALL) {
        check(status);
    }
    std::string result(required, '\0');
    if (required != 0) {
        check(copy(reinterpret_cast<std::uint8_t*>(result.data()), result.size(), &required));
        result.resize(required);
    }
    return result;
}

struct ContextState final {
    codex_agent_context_t* raw = nullptr;

    ~ContextState() noexcept {
        while (raw != nullptr) {
            const auto status = codex_agent_context_destroy(&raw);
            if (status == CODEX_AGENT_STATUS_OK) {
                return;
            }
            if (status != CODEX_AGENT_STATUS_BUSY) {
                return;
            }
            std::this_thread::yield();
        }
    }
};

using Context = std::shared_ptr<ContextState>;

template <typename Handle, codex_agent_status_t (CODEX_AGENT_CALL *Release)(
                               codex_agent_context_t*, Handle**)>
class OwnedHandle final {
public:
    OwnedHandle() = default;
    OwnedHandle(Context context, Handle* raw)
        : context_(std::move(context)), raw_(raw) {}

    OwnedHandle(const OwnedHandle&) = delete;
    OwnedHandle& operator=(const OwnedHandle&) = delete;

    OwnedHandle(OwnedHandle&& other) noexcept
        : context_(std::move(other.context_)), raw_(std::exchange(other.raw_, nullptr)) {}

    OwnedHandle& operator=(OwnedHandle&& other) noexcept {
        if (this != &other) {
            reset();
            context_ = std::move(other.context_);
            raw_ = std::exchange(other.raw_, nullptr);
        }
        return *this;
    }

    ~OwnedHandle() noexcept { reset(); }

    [[nodiscard]] Handle* get() const noexcept { return raw_; }
    [[nodiscard]] codex_agent_context_t* context_raw() const noexcept {
        return context_ ? context_->raw : nullptr;
    }
    [[nodiscard]] const Context& context() const noexcept { return context_; }
    [[nodiscard]] explicit operator bool() const noexcept { return raw_ != nullptr; }

    void reset() noexcept {
        while (raw_ != nullptr && context_ && context_->raw != nullptr) {
            const auto status = Release(context_->raw, &raw_);
            if (status == CODEX_AGENT_STATUS_OK) {
                break;
            }
            if (status != CODEX_AGENT_STATUS_BUSY) {
                break;
            }
            std::this_thread::yield();
        }
        raw_ = nullptr;
        context_.reset();
    }

private:
    Context context_;
    Handle* raw_ = nullptr;
};

using HostHandle = OwnedHandle<codex_agent_host_t, codex_agent_host_release>;
using AgentHandle = OwnedHandle<codex_agent_agent_t, codex_agent_agent_release>;
using ConversationsHandle =
    OwnedHandle<codex_agent_conversations_t, codex_agent_conversations_release>;
using ConversationHandle =
    OwnedHandle<codex_agent_conversation_t, codex_agent_conversation_release>;

struct AgentOwnership final {
    std::shared_ptr<HostHandle> host;
    std::shared_ptr<AgentHandle> agent;
};

template <typename Handle, auto Release>
using SyncHandle = OwnedHandle<Handle, Release>;

using FormBooleanHandle = SyncHandle<
    codex_agent_form_boolean_value_t, codex_agent_form_boolean_value_destroy>;
using FormNumberHandle = SyncHandle<
    codex_agent_form_number_value_t, codex_agent_form_number_value_destroy>;
using FormTextHandle = SyncHandle<
    codex_agent_form_text_value_t, codex_agent_form_text_value_destroy>;
using FormTextListHandle = SyncHandle<
    codex_agent_form_text_list_value_t, codex_agent_form_text_list_value_destroy>;
using FormValueHandle =
    SyncHandle<codex_agent_form_value_t, codex_agent_form_value_destroy>;
using FormOptionHandle =
    SyncHandle<codex_agent_form_option_t, codex_agent_form_option_destroy>;
using FormFieldHandle =
    SyncHandle<codex_agent_form_field_t, codex_agent_form_field_destroy>;
using ConversationIdHandle = SyncHandle<
    codex_agent_conversation_id_t, codex_agent_conversation_id_destroy>;
using ConversationSummaryHandle = SyncHandle<
    codex_agent_conversation_summary_t,
    codex_agent_conversation_summary_destroy>;
using ConversationValueHandle = SyncHandle<
    codex_agent_conversation_value_t,
    codex_agent_conversation_value_destroy>;
using MessageHandle =
    SyncHandle<codex_agent_message_t, codex_agent_message_destroy>;
using TurnProgressHandle = SyncHandle<
    codex_agent_turn_progress_t, codex_agent_turn_progress_destroy>;
using TurnRequestHandle = SyncHandle<
    codex_agent_turn_request_t, codex_agent_turn_request_destroy>;
using InvocationHandle = SyncHandle<
    codex_agent_invocation_t, codex_agent_invocation_destroy>;
using InvocationPluginHandle = SyncHandle<
    codex_agent_invocation_plugin_t,
    codex_agent_invocation_plugin_destroy>;
using InvocationSkillHandle = SyncHandle<
    codex_agent_invocation_skill_t,
    codex_agent_invocation_skill_destroy>;
using PlanProgressHandle = SyncHandle<
    codex_agent_plan_progress_t, codex_agent_plan_progress_destroy>;
using PlanStepHandle =
    SyncHandle<codex_agent_plan_step_t, codex_agent_plan_step_destroy>;
using HookActivityHandle = SyncHandle<
    codex_agent_hook_activity_t, codex_agent_hook_activity_destroy>;
using ElicitationHandle =
    SyncHandle<codex_agent_elicitation_t, codex_agent_elicitation_destroy>;
using ElicitationResponseHandle = SyncHandle<
    codex_agent_elicitation_response_t,
    codex_agent_elicitation_response_destroy>;
using FormContentHandle =
    SyncHandle<codex_agent_form_content_t, codex_agent_form_content_destroy>;
using ElicitationValidationHandle = SyncHandle<
    codex_agent_elicitation_validation_t,
    codex_agent_elicitation_validation_destroy>;
using ElicitationValidationIssueHandle = SyncHandle<
    codex_agent_elicitation_validation_issue_t,
    codex_agent_elicitation_validation_issue_destroy>;
using AuthorizationUrlHandle = SyncHandle<
    codex_agent_authorization_url_t, codex_agent_authorization_url_destroy>;
using FailureHandle =
    SyncHandle<codex_agent_failure_t, codex_agent_failure_release>;
using PendingApprovalHandle = SyncHandle<
    codex_agent_pending_approval_t, codex_agent_pending_approval_destroy>;
using PendingElicitationHandle = SyncHandle<
    codex_agent_pending_elicitation_t, codex_agent_pending_elicitation_destroy>;
using PendingInteractionHandle = SyncHandle<
    codex_agent_pending_interaction_t, codex_agent_pending_interaction_destroy>;
using InteractionStateHandle = SyncHandle<
    codex_agent_interaction_state_t, codex_agent_interaction_state_destroy>;
using PendingInteractionListHandle = SyncHandle<
    codex_agent_pending_interaction_list_t,
    codex_agent_pending_interaction_list_destroy>;

template <typename Handle, auto Release, typename Create>
SyncHandle<Handle, Release> make_sync_handle(
    const Context& context, Create&& create) {
    if (!context || context->raw == nullptr) {
        throw Error(Status::closed);
    }
    Handle* raw = nullptr;
    check(create(&raw));
    return {context, raw};
}

inline Context make_sync_context() {
    auto context = std::make_shared<ContextState>();
    check(codex_agent_context_create(&context->raw));
    return context;
}

inline ConversationIdHandle make_conversation_id(
    const Context& context, const ConversationId& value) {
    const auto raw_value = string_view(value.value);
    return make_sync_handle<
        codex_agent_conversation_id_t, codex_agent_conversation_id_destroy>(
        context, [&](auto** out) {
            return codex_agent_conversation_id_create(
                context->raw, &raw_value, out);
        });
}

inline FormValueHandle make_form_value(
    const Context& context, const FormValue& value) {
    return std::visit(
        [&](const auto& selected) -> FormValueHandle {
            using Value = std::decay_t<decltype(selected)>;
            codex_agent_form_value_t* raw = nullptr;
            if constexpr (std::is_same_v<Value, FormBooleanValue>) {
                auto primitive = make_sync_handle<
                    codex_agent_form_boolean_value_t,
                    codex_agent_form_boolean_value_destroy>(
                    context, [&](auto** out) {
                        return codex_agent_form_boolean_value_create(
                            context->raw, selected.value ? 1 : 0, out);
                    });
                check(codex_agent_form_value_from_boolean(
                    context->raw, primitive.get(), &raw));
            } else if constexpr (std::is_same_v<Value, FormNumberValue>) {
                auto primitive = make_sync_handle<
                    codex_agent_form_number_value_t,
                    codex_agent_form_number_value_destroy>(
                    context, [&](auto** out) {
                        return codex_agent_form_number_value_create(
                            context->raw, selected.value, out);
                    });
                check(codex_agent_form_value_from_number(
                    context->raw, primitive.get(), &raw));
            } else if constexpr (std::is_same_v<Value, FormTextValue>) {
                const auto raw_text = string_view(selected.value);
                auto primitive = make_sync_handle<
                    codex_agent_form_text_value_t,
                    codex_agent_form_text_value_destroy>(
                    context, [&](auto** out) {
                        return codex_agent_form_text_value_create(
                            context->raw, &raw_text, out);
                    });
                check(codex_agent_form_value_from_text(
                    context->raw, primitive.get(), &raw));
            } else {
                std::vector<codex_agent_string_view_t> raw_values;
                raw_values.reserve(selected.value.size());
                for (const auto& item : selected.value) {
                    raw_values.push_back(string_view(item));
                }
                auto primitive = make_sync_handle<
                    codex_agent_form_text_list_value_t,
                    codex_agent_form_text_list_value_destroy>(
                    context, [&](auto** out) {
                        return codex_agent_form_text_list_value_create(
                            context->raw,
                            raw_values.empty() ? nullptr : raw_values.data(),
                            raw_values.size(), out);
                    });
                check(codex_agent_form_value_from_text_list(
                    context->raw, primitive.get(), &raw));
            }
            return {context, raw};
        },
        value);
}

inline FormValue read_form_value(
    const Context& context, codex_agent_form_value_t* raw) {
    codex_agent_form_value_kind_t kind = -1;
    check(codex_agent_form_value_kind(context->raw, raw, &kind));
    switch (kind) {
        case CODEX_AGENT_FORM_VALUE_KIND_BOOLEAN: {
            codex_agent_form_boolean_value_t* child = nullptr;
            check(codex_agent_form_value_boolean(context->raw, raw, &child));
            FormBooleanHandle owned(context, child);
            std::int32_t value = 0;
            check(codex_agent_form_boolean_value_value(
                context->raw, owned.get(), &value));
            return FormBooleanValue{value != 0};
        }
        case CODEX_AGENT_FORM_VALUE_KIND_NUMBER: {
            codex_agent_form_number_value_t* child = nullptr;
            check(codex_agent_form_value_number(context->raw, raw, &child));
            FormNumberHandle owned(context, child);
            double value = 0.0;
            check(codex_agent_form_number_value_value(
                context->raw, owned.get(), &value));
            return FormNumberValue{value};
        }
        case CODEX_AGENT_FORM_VALUE_KIND_TEXT: {
            codex_agent_form_text_value_t* child = nullptr;
            check(codex_agent_form_value_text(context->raw, raw, &child));
            FormTextHandle owned(context, child);
            return FormTextValue{copy_string(
                [&](std::uint8_t* buffer, std::size_t capacity,
                    std::size_t* required) {
                    return codex_agent_form_text_value_value_copy(
                        context->raw, owned.get(), buffer, capacity, required);
                })};
        }
        case CODEX_AGENT_FORM_VALUE_KIND_TEXT_LIST: {
            codex_agent_form_text_list_value_t* child = nullptr;
            check(codex_agent_form_value_text_list(context->raw, raw, &child));
            FormTextListHandle owned(context, child);
            std::size_t count = 0;
            check(codex_agent_form_text_list_value_count(
                context->raw, owned.get(), &count));
            std::vector<std::string> values;
            values.reserve(count);
            for (std::size_t index = 0; index < count; ++index) {
                values.push_back(copy_string(
                    [&](std::uint8_t* buffer, std::size_t capacity,
                        std::size_t* required) {
                        return codex_agent_form_text_list_value_copy_at(
                            context->raw, owned.get(), index, buffer, capacity,
                            required);
                    }));
            }
            return FormTextListValue{std::move(values)};
        }
        default:
            throw Error(Status::internal_error);
    }
}

inline FormOptionHandle make_form_option(
    const Context& context, const FormOption& option) {
    const auto raw_value = string_view(option.value);
    const auto raw_title = string_view(option.title);
    const auto raw_description = option.description
        ? string_view(*option.description)
        : codex_agent_string_view_t{nullptr, 0};
    return make_sync_handle<
        codex_agent_form_option_t, codex_agent_form_option_destroy>(
        context, [&](auto** out) {
            return codex_agent_form_option_create(
                context->raw, &raw_value, 1, &raw_title,
                option.description ? 1 : 0, &raw_description, out);
        });
}

inline FormFieldHandle make_form_field(
    const Context& context, const FormField& field) {
    std::vector<FormOptionHandle> options;
    std::vector<codex_agent_form_option_t*> raw_options;
    options.reserve(field.options.size());
    raw_options.reserve(field.options.size());
    for (const auto& option : field.options) {
        options.push_back(make_form_option(context, option));
        raw_options.push_back(options.back().get());
    }
    std::optional<FormValueHandle> default_value;
    if (field.default_value) {
        default_value.emplace(make_form_value(context, *field.default_value));
    }
    const auto raw_name = string_view(field.name);
    const auto raw_title = string_view(field.title);
    const auto raw_description = field.description
        ? string_view(*field.description)
        : codex_agent_string_view_t{nullptr, 0};
    return make_sync_handle<
        codex_agent_form_field_t, codex_agent_form_field_destroy>(
        context, [&](auto** out) {
            return codex_agent_form_field_create(
                context->raw, &raw_name, &raw_title,
                field.description ? 1 : 0, &raw_description,
                field.is_required ? 1 : 0,
                static_cast<codex_agent_form_field_type_t>(field.type),
                raw_options.empty() ? nullptr : raw_options.data(),
                raw_options.size(), field.default_value ? 1 : 0,
                default_value ? default_value->get() : nullptr,
                field.minimum ? 1 : 0, field.minimum.value_or(0.0),
                field.maximum ? 1 : 0, field.maximum.value_or(0.0),
                field.format ? 1 : 0,
                static_cast<codex_agent_form_string_format_t>(
                    field.format.value_or(FormStringFormat::email)),
                field.minimum_length ? 1 : 0,
                field.minimum_length.value_or(0),
                field.maximum_length ? 1 : 0,
                field.maximum_length.value_or(0),
                field.minimum_selections ? 1 : 0,
                field.minimum_selections.value_or(0),
                field.maximum_selections ? 1 : 0,
                field.maximum_selections.value_or(0),
                field.allows_other ? 1 : 0, field.is_secret ? 1 : 0, out);
        });
}

inline ElicitationHandle make_elicitation(
    const Context& context, const Elicitation& elicitation) {
    auto conversation_id = make_conversation_id(
        context, elicitation.conversation_id);
    std::vector<FormFieldHandle> fields;
    std::vector<codex_agent_form_field_t*> raw_fields;
    if (elicitation.form) {
        fields.reserve(elicitation.form->size());
        raw_fields.reserve(elicitation.form->size());
        for (const auto& field : *elicitation.form) {
            fields.push_back(make_form_field(context, field));
            raw_fields.push_back(fields.back().get());
        }
    }
    const auto request_id = string_view(elicitation.request_id);
    const auto server_name = string_view(elicitation.server_name);
    const auto message = string_view(elicitation.message);
    const auto url = elicitation.url
        ? string_view(*elicitation.url)
        : codex_agent_string_view_t{nullptr, 0};
    return make_sync_handle<
        codex_agent_elicitation_t, codex_agent_elicitation_destroy>(
        context, [&](auto** out) {
            return codex_agent_elicitation_create(
                context->raw, &request_id, &server_name,
                conversation_id.get(), &message, elicitation.form ? 1 : 0,
                raw_fields.empty() ? nullptr : raw_fields.data(),
                raw_fields.size(), elicitation.url ? 1 : 0, &url, out);
        });
}

inline FormContentHandle make_form_content(
    const Context& context,
    const std::map<std::string, FormValue>& content) {
    std::vector<codex_agent_string_view_t> keys;
    std::vector<FormValueHandle> values;
    std::vector<codex_agent_form_value_t*> raw_values;
    keys.reserve(content.size());
    values.reserve(content.size());
    raw_values.reserve(content.size());
    for (const auto& [key, value] : content) {
        keys.push_back(string_view(key));
        values.push_back(make_form_value(context, value));
        raw_values.push_back(values.back().get());
    }
    return make_sync_handle<
        codex_agent_form_content_t, codex_agent_form_content_destroy>(
        context, [&](auto** out) {
            return codex_agent_form_content_create(
                context->raw, keys.empty() ? nullptr : keys.data(),
                raw_values.empty() ? nullptr : raw_values.data(),
                keys.size(), out);
        });
}

inline std::map<std::string, FormValue> read_form_content(
    const Context& context, codex_agent_form_content_t* content) {
    std::size_t count = 0;
    check(codex_agent_form_content_count(context->raw, content, &count));
    std::map<std::string, FormValue> result;
    for (std::size_t index = 0; index < count; ++index) {
        auto key = copy_string(
            [&](std::uint8_t* buffer, std::size_t capacity,
                std::size_t* required) {
                return codex_agent_form_content_key_copy(
                    context->raw, content, index, buffer, capacity, required);
            });
        const auto raw_key = string_view(key);
        codex_agent_form_value_t* raw_value = nullptr;
        check(codex_agent_form_content_value_at(
            context->raw, content, &raw_key, &raw_value));
        FormValueHandle value(context, raw_value);
        result.insert_or_assign(
            std::move(key), read_form_value(context, value.get()));
    }
    return result;
}

inline ElicitationResponseHandle make_elicitation_response(
    const Context& context, const ElicitationResponse& response) {
    std::vector<codex_agent_string_view_t> keys;
    std::vector<FormValueHandle> values;
    std::vector<codex_agent_form_value_t*> raw_values;
    keys.reserve(response.content.size());
    values.reserve(response.content.size());
    raw_values.reserve(response.content.size());
    for (const auto& [key, value] : response.content) {
        keys.push_back(string_view(key));
        values.push_back(make_form_value(context, value));
        raw_values.push_back(values.back().get());
    }
    return make_sync_handle<
        codex_agent_elicitation_response_t,
        codex_agent_elicitation_response_destroy>(
        context, [&](auto** out) {
            return codex_agent_elicitation_response_create(
                context->raw,
                static_cast<codex_agent_elicitation_action_t>(response.action),
                keys.empty() ? nullptr : keys.data(),
                raw_values.empty() ? nullptr : raw_values.data(),
                keys.size(), out);
        });
}

inline ElicitationResponse read_elicitation_response(
    const Context& context, codex_agent_elicitation_response_t* response,
    const std::map<std::string, FormValue>& expected_content) {
    codex_agent_elicitation_action_t action = -1;
    check(codex_agent_elicitation_response_action(
        context->raw, response, &action));
    std::size_t count = 0;
    check(codex_agent_elicitation_response_content_count(
        context->raw, response, &count));
    if (count != expected_content.size()) {
        throw Error(Status::internal_error);
    }
    std::map<std::string, FormValue> content;
    for (const auto& [key, ignored] : expected_content) {
        (void)ignored;
        const auto raw_key = string_view(key);
        codex_agent_form_value_t* raw_value = nullptr;
        check(codex_agent_elicitation_response_content_value(
            context->raw, response, &raw_key, &raw_value));
        FormValueHandle value(context, raw_value);
        content.emplace(key, read_form_value(context, value.get()));
    }
    return {static_cast<ElicitationAction>(action), std::move(content)};
}

inline ElicitationValidation read_elicitation_validation(
    const Context& context,
    codex_agent_elicitation_validation_t* validation) {
    std::size_t count = 0;
    check(codex_agent_elicitation_validation_issue_count(
        context->raw, validation, &count));
    std::vector<ElicitationValidationIssue> issues;
    issues.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        codex_agent_elicitation_validation_issue_t* raw_issue = nullptr;
        check(codex_agent_elicitation_validation_issue_at(
            context->raw, validation, index, &raw_issue));
        ElicitationValidationIssueHandle issue(context, raw_issue);
        auto field_name = copy_string(
            [&](std::uint8_t* buffer, std::size_t capacity,
                std::size_t* required) {
                return codex_agent_elicitation_validation_issue_field_name_copy(
                    context->raw, issue.get(), buffer, capacity, required);
            });
        codex_agent_elicitation_validation_reason_t reason = -1;
        check(codex_agent_elicitation_validation_issue_reason(
            context->raw, issue.get(), &reason));
        issues.push_back({
            std::move(field_name),
            static_cast<ElicitationValidationReason>(reason),
        });
    }
    return {std::move(issues)};
}

inline AuthorizationUrl read_authorization_url(
    const Context& context, const AuthorizationUrlHandle& url,
    AuthorizationPurpose expected_purpose) {
    auto projected_value = copy_string(
        [&](std::uint8_t* buffer, std::size_t capacity,
            std::size_t* required) {
            return codex_agent_authorization_url_value_copy(
                context->raw, url.get(), buffer, capacity, required);
        });
    codex_agent_authorization_purpose_t raw_purpose = -1;
    check(codex_agent_authorization_url_purpose(
        context->raw, url.get(), &raw_purpose));
    const auto purpose = static_cast<AuthorizationPurpose>(raw_purpose);
    if (purpose != expected_purpose) {
        throw Error(Status::internal_error);
    }
    return {std::move(projected_value), purpose};
}

inline PendingInteractionHandle make_pending_interaction(
    const Context& context, const PendingInteractionValue& interaction) {
    return std::visit(
        [&](const auto& selected) -> PendingInteractionHandle {
            using Value = std::decay_t<decltype(selected)>;
            codex_agent_pending_interaction_t* raw = nullptr;
            if constexpr (std::is_same_v<Value, PendingApproval>) {
                auto conversation_id = make_conversation_id(
                    context, selected.conversation_id);
                const auto request_id = string_view(selected.request_id);
                const auto title = string_view(selected.title);
                const auto details = string_view(selected.details);
                auto approval = make_sync_handle<
                    codex_agent_pending_approval_t,
                    codex_agent_pending_approval_destroy>(
                    context, [&](auto** out) {
                        return codex_agent_pending_approval_create(
                            context->raw, &request_id, conversation_id.get(),
                            &title, &details, out);
                    });
                check(codex_agent_pending_interaction_from_approval(
                    context->raw, approval.get(), &raw));
            } else {
                auto elicitation = make_elicitation(
                    context, selected.elicitation);
                auto pending = make_sync_handle<
                    codex_agent_pending_elicitation_t,
                    codex_agent_pending_elicitation_destroy>(
                    context, [&](auto** out) {
                        return codex_agent_pending_elicitation_create(
                            context->raw, elicitation.get(), out);
                    });
                check(codex_agent_pending_interaction_from_elicitation(
                    context->raw, pending.get(), &raw));
            }
            return {context, raw};
        },
        interaction);
}

inline PendingInteractionHandle make_pending_interaction(
    const Context& context, const PendingInteraction& interaction) {
    return make_pending_interaction(
        context,
        PendingInteractionValue{PendingApproval{
            interaction, std::string{}, std::string{}}});
}

inline FailureHandle make_failure(
    const Context& context, const Failure& failure) {
    const auto code = string_view(failure.code);
    const auto message = string_view(failure.message);
    return make_sync_handle<codex_agent_failure_t, codex_agent_failure_release>(
        context, [&](auto** out) {
            return codex_agent_failure_create(
                context->raw, &code, &message,
                failure.recoverable ? 1 : 0, out);
        });
}

inline InteractionStateHandle make_interaction_state(
    const Context& context, const InteractionState& state) {
    std::vector<PendingInteractionHandle> pending;
    std::vector<codex_agent_pending_interaction_t*> raw_pending;
    pending.reserve(state.pending.size());
    raw_pending.reserve(state.pending.size());
    for (const auto& interaction : state.pending) {
        pending.push_back(make_pending_interaction(context, interaction));
        raw_pending.push_back(pending.back().get());
    }
    std::vector<codex_agent_string_view_t> resolving_request_ids;
    resolving_request_ids.reserve(state.resolving_request_ids.size());
    for (const auto& request_id : state.resolving_request_ids) {
        resolving_request_ids.push_back(string_view(request_id));
    }
    std::optional<FailureHandle> failure;
    if (state.failure) failure.emplace(make_failure(context, *state.failure));
    return make_sync_handle<
        codex_agent_interaction_state_t, codex_agent_interaction_state_destroy>(
        context, [&](auto** out) {
            return codex_agent_interaction_state_create(
                context->raw,
                raw_pending.empty() ? nullptr : raw_pending.data(),
                raw_pending.size(),
                resolving_request_ids.empty()
                    ? nullptr
                    : resolving_request_ids.data(),
                resolving_request_ids.size(), state.failure ? 1 : 0,
                failure ? failure->get() : nullptr, out);
        });
}

struct PendingSignature {
    codex_agent_pending_interaction_kind_t kind;
    std::string request_id;
    std::string conversation_id;

    [[nodiscard]] bool operator==(const PendingSignature&) const = default;
};

inline PendingSignature pending_signature(
    const PendingInteractionValue& interaction) {
    return std::visit(
        [](const auto& selected) {
            using Value = std::decay_t<decltype(selected)>;
            return PendingSignature{
                std::is_same_v<Value, PendingApproval>
                    ? CODEX_AGENT_PENDING_INTERACTION_KIND_APPROVAL
                    : CODEX_AGENT_PENDING_INTERACTION_KIND_ELICITATION,
                selected.request_id,
                selected.conversation_id.value,
            };
        },
        interaction);
}

inline PendingSignature pending_signature(
    const Context& context, codex_agent_pending_interaction_t* interaction) {
    codex_agent_pending_interaction_kind_t kind = -1;
    check(codex_agent_pending_interaction_kind(
        context->raw, interaction, &kind));
    auto request_id = copy_string(
        [&](std::uint8_t* buffer, std::size_t capacity,
            std::size_t* required) {
            return codex_agent_pending_interaction_request_id_copy(
                context->raw, interaction, buffer, capacity, required);
        });
    codex_agent_conversation_id_t* raw_conversation_id = nullptr;
    check(codex_agent_pending_interaction_conversation_id(
        context->raw, interaction, &raw_conversation_id));
    ConversationIdHandle conversation_id(context, raw_conversation_id);
    auto conversation_id_value = copy_string(
        [&](std::uint8_t* buffer, std::size_t capacity,
            std::size_t* required) {
            return codex_agent_conversation_id_value_copy(
                context->raw, conversation_id.get(), buffer, capacity,
                required);
        });
    return {
        kind, std::move(request_id), std::move(conversation_id_value)};
}

template <
    typename Handle,
    codex_agent_status_t (CODEX_AGENT_CALL *Retain)(
        codex_agent_context_t*, Handle*, Handle**),
    codex_agent_status_t (CODEX_AGENT_CALL *Release)(
        codex_agent_context_t*, Handle**)>
std::shared_ptr<OwnedHandle<Handle, Release>> retain_handle(
    const OwnedHandle<Handle, Release>& source) {
    Handle* retained = nullptr;
    check(Retain(source.context_raw(), source.get(), &retained));
    return std::make_shared<OwnedHandle<Handle, Release>>(
        source.context(), retained);
}

inline auto retain_host(const HostHandle& source) {
    return retain_handle<codex_agent_host_t, codex_agent_host_retain,
                         codex_agent_host_release>(source);
}

inline auto retain_agent_ownership(
    const std::shared_ptr<AgentOwnership>& source) {
    auto agent = retain_handle<codex_agent_agent_t, codex_agent_agent_retain,
                               codex_agent_agent_release>(*source->agent);
    return std::make_shared<AgentOwnership>(AgentOwnership{
        source->host, std::move(agent)});
}

inline auto retain_conversations(const ConversationsHandle& source) {
    if (source.get() == nullptr) {
        return std::make_shared<ConversationsHandle>(
            source.context(), nullptr);
    }
    return retain_handle<codex_agent_conversations_t,
                         codex_agent_conversations_retain,
                         codex_agent_conversations_release>(source);
}

inline auto retain_conversation(const ConversationHandle& source) {
    if (source.get() == nullptr) {
        return std::make_shared<ConversationHandle>(
            source.context(), nullptr);
    }
    return retain_handle<codex_agent_conversation_t,
                         codex_agent_conversation_retain,
                         codex_agent_conversation_release>(source);
}

class Snapshot final {
public:
    Snapshot(Context context, codex_agent_snapshot_t* raw)
        : context_(std::move(context)), raw_(raw) {}
    Snapshot(const Snapshot&) = delete;
    Snapshot& operator=(const Snapshot&) = delete;
    ~Snapshot() noexcept {
        if (raw_ != nullptr && context_ && context_->raw != nullptr) {
            while (codex_agent_snapshot_destroy(context_->raw, &raw_) ==
                   CODEX_AGENT_STATUS_BUSY) {
                std::this_thread::yield();
            }
        }
    }
    [[nodiscard]] codex_agent_snapshot_t* get() const noexcept { return raw_; }

private:
    Context context_;
    codex_agent_snapshot_t* raw_;
};

inline Failure read_failure(Context context, codex_agent_failure_t* raw) {
    Failure value;
    value.code = copy_string([&](std::uint8_t* buffer, std::size_t capacity, std::size_t* out) {
        return codex_agent_failure_code_copy(context->raw, raw, buffer, capacity, out);
    });
    value.message = copy_string([&](std::uint8_t* buffer, std::size_t capacity, std::size_t* out) {
        return codex_agent_failure_message_copy(context->raw, raw, buffer, capacity, out);
    });
    std::int32_t recoverable = 0;
    check(codex_agent_failure_is_recoverable(context->raw, raw, &recoverable));
    value.recoverable = recoverable != 0;
    return value;
}

inline std::optional<Failure> operation_failure(
    const Context& context,
    codex_agent_operation_t* operation) {
    codex_agent_failure_t* raw = nullptr;
    const auto status = codex_agent_operation_failure(context->raw, operation, &raw);
    if (status == CODEX_AGENT_STATUS_NOT_READY) {
        return std::nullopt;
    }
    check(status);
    try {
        auto value = read_failure(context, raw);
        check(codex_agent_failure_release(context->raw, &raw));
        return value;
    } catch (...) {
        if (raw != nullptr) {
            (void)codex_agent_failure_release(context->raw, &raw);
        }
        throw;
    }
}

struct OperationState final {
    explicit OperationState(Context context_value) : context(std::move(context_value)) {}

    Context context;
    std::mutex mutex;
    std::condition_variable changed;
    codex_agent_operation_t* operation = nullptr;
    bool callback_seen = false;
    bool call_in_progress = false;
};

inline void CODEX_AGENT_CALL operation_callback(
    codex_agent_context_t*,
    codex_agent_operation_t* operation,
    void* user_data) noexcept {
    auto* token = static_cast<std::shared_ptr<OperationState>*>(user_data);
    try {
        auto state = *token;
        {
            std::lock_guard lock(state->mutex);
            state->operation = operation;
            state->callback_seen = true;
        }
        state->changed.notify_all();
    } catch (...) {
        // The callback contract forbids exceptions from crossing the C ABI.
    }
    delete token;
}

inline void destroy_operation(OperationState& state) {
    while (state.operation != nullptr) {
        const auto status = codex_agent_operation_destroy(
            state.context->raw,
            &state.operation);
        if (status == CODEX_AGENT_STATUS_OK) {
            return;
        }
        if (status != CODEX_AGENT_STATUS_BUSY) {
            check(status);
        }
        std::this_thread::yield();
    }
}

template <typename Value>
class AsyncOperationFactory;

template <typename Value, typename Initiate, typename Extract>
auto start_operation(
    Context context, Initiate&& initiate, Extract&& extract);

template <typename Value, typename Parse>
class SubscriptionState final {
public:
    SubscriptionState(Context context_value, std::shared_ptr<void> owner_value,
                      Parse parse_value,
                      std::function<void(StateEvent<Value>)> callback_value)
        : context(std::move(context_value)),
          owner(std::move(owner_value)),
          parse(std::move(parse_value)),
          callback(std::move(callback_value)) {}

    Context context;
    std::shared_ptr<void> owner;
    Parse parse;
    std::function<void(StateEvent<Value>)> callback;
    std::mutex mutex;
    codex_agent_subscription_t* subscription = nullptr;
    std::exception_ptr callback_error;
    std::thread::id callback_thread;
};

template <typename State>
void CODEX_AGENT_CALL state_callback(
    codex_agent_context_t*,
    codex_agent_subscription_t* subscription,
    codex_agent_status_t event_status,
    codex_agent_snapshot_t* raw_snapshot,
    std::int32_t is_terminal,
    void* user_data) noexcept {
    auto* token = static_cast<std::shared_ptr<State>*>(user_data);
    auto state = *token;
    {
        std::lock_guard lock(state->mutex);
        state->subscription = subscription;
        state->callback_thread = std::this_thread::get_id();
    }
    try {
        using Value = std::invoke_result_t<
            decltype(state->parse), codex_agent_context_t*, codex_agent_snapshot_t*>;
        std::optional<Value> value;
        if (event_status == CODEX_AGENT_STATUS_OK && raw_snapshot != nullptr) {
            value.emplace(state->parse(state->context->raw, raw_snapshot));
        }
        state->callback(StateEvent<Value>{
            status_from_raw(event_status),
            std::move(value),
            is_terminal != 0,
        });
    } catch (...) {
        std::lock_guard lock(state->mutex);
        state->callback_error = std::current_exception();
    }
    if (raw_snapshot != nullptr) {
        while (codex_agent_snapshot_destroy(state->context->raw, &raw_snapshot) ==
               CODEX_AGENT_STATUS_BUSY) {
            std::this_thread::yield();
        }
    }
    {
        std::lock_guard lock(state->mutex);
        state->callback_thread = {};
    }
}

inline HostState parse_host_state(
    const Context& context,
    codex_agent_snapshot_t* snapshot) {
    codex_agent_host_state_kind_t raw_kind = 0;
    check(codex_agent_host_state_kind(context->raw, snapshot, &raw_kind));
    HostState state{static_cast<HostStateKind>(raw_kind), std::nullopt, std::nullopt,
                    std::nullopt};

    std::int32_t has_workspace = 0;
    if (codex_agent_host_state_has_workspace(context->raw, snapshot, &has_workspace) ==
            CODEX_AGENT_STATUS_OK &&
        has_workspace != 0) {
        Workspace workspace;
        workspace.path = copy_string([&](std::uint8_t* buffer, std::size_t capacity,
                                         std::size_t* out) {
            return codex_agent_host_state_workspace_path_copy(
                context->raw, snapshot, buffer, capacity, out);
        });
        workspace.display_name = copy_optional_string(
            [&](std::uint8_t* buffer, std::size_t capacity, std::size_t* out) {
                return codex_agent_host_state_workspace_display_name_copy(
                    context->raw, snapshot, buffer, capacity, out);
            }).value_or("");
        state.workspace = std::move(workspace);
    }

    if (state.kind == HostStateKind::workspace_required) {
        codex_agent_workspace_selection_reason_t reason = 0;
        check(codex_agent_host_state_requirement_reason(context->raw, snapshot, &reason));
        state.requirement = WorkspaceRequirement{
            static_cast<WorkspaceSelectionReason>(reason),
            copy_string([&](std::uint8_t* buffer, std::size_t capacity,
                            std::size_t* out) {
                return codex_agent_host_state_requirement_message_copy(
                    context->raw, snapshot, buffer, capacity, out);
            }),
        };
    }

    if (state.kind == HostStateKind::failed) {
        codex_agent_failure_t* raw_failure = nullptr;
        check(codex_agent_host_state_failure(context->raw, snapshot, &raw_failure));
        try {
            state.failure = read_failure(context, raw_failure);
            check(codex_agent_failure_release(context->raw, &raw_failure));
        } catch (...) {
            if (raw_failure != nullptr) {
                (void)codex_agent_failure_release(context->raw, &raw_failure);
            }
            throw;
        }
    }
    return state;
}

template <typename Has, typename Copy>
inline std::optional<std::string> read_present_string(
    Has&& has, Copy&& copy) {
    std::int32_t present = 0;
    check(has(&present));
    if (present == 0) return std::nullopt;
    return copy_string(std::forward<Copy>(copy));
}

inline ConversationId read_conversation_id(
    const Context& context, codex_agent_conversation_id_t* raw) {
    return ConversationId(copy_string(
        [&](std::uint8_t* buffer, std::size_t capacity,
            std::size_t* required) {
            return codex_agent_conversation_id_value_copy(
                context->raw, raw, buffer, capacity, required);
        }));
}

inline ConversationSummary read_conversation_summary(
    const Context& context, codex_agent_conversation_summary_t* raw) {
    codex_agent_conversation_id_t* raw_id = nullptr;
    check(codex_agent_conversation_summary_conversation_id(
        context->raw, raw, &raw_id));
    ConversationIdHandle id(context, raw_id);
    auto title = copy_string(
        [&](std::uint8_t* buffer, std::size_t capacity,
            std::size_t* required) {
            return codex_agent_conversation_summary_title_copy(
                context->raw, raw, buffer, capacity, required);
        });
    std::int64_t updated_at = 0;
    check(codex_agent_conversation_summary_updated_at_epoch_seconds(
        context->raw, raw, &updated_at));
    return {read_conversation_id(context, id.get()), std::move(title),
            updated_at};
}

inline InvocationValue read_invocation(
    const Context& context, codex_agent_invocation_t* raw) {
    auto read = [&](auto copy) {
        return copy_string(
            [&](std::uint8_t* buffer, std::size_t capacity,
                std::size_t* required) {
                return copy(context->raw, raw, buffer, capacity, required);
            });
    };
    const auto key = read(codex_agent_invocation_key_copy);
    const auto name = read(codex_agent_invocation_name_copy);
    codex_agent_invocation_kind_t kind = -1;
    check(codex_agent_invocation_kind(context->raw, raw, &kind));
    if (kind == CODEX_AGENT_INVOCATION_KIND_PLUGIN) {
        codex_agent_invocation_plugin_t* plugin_raw = nullptr;
        check(codex_agent_invocation_plugin(context->raw, raw, &plugin_raw));
        InvocationPluginHandle plugin(context, plugin_raw);
        auto uri = copy_string(
            [&](std::uint8_t* buffer, std::size_t capacity,
                std::size_t* required) {
                return codex_agent_invocation_plugin_uri_copy(
                    context->raw, plugin.get(), buffer, capacity, required);
            });
        return PluginInvocation{{key, name}, std::move(uri)};
    }
    if (kind == CODEX_AGENT_INVOCATION_KIND_SKILL) {
        codex_agent_invocation_skill_t* skill_raw = nullptr;
        check(codex_agent_invocation_skill(context->raw, raw, &skill_raw));
        InvocationSkillHandle skill(context, skill_raw);
        auto path = copy_string(
            [&](std::uint8_t* buffer, std::size_t capacity,
                std::size_t* required) {
                return codex_agent_invocation_skill_path_copy(
                    context->raw, skill.get(), buffer, capacity, required);
            });
        return SkillInvocation{{key, name}, std::move(path)};
    }
    throw Error(Status::internal_error);
}

inline Message read_message(
    const Context& context, codex_agent_message_t* raw) {
    auto copy = [&](auto function) {
        return copy_string(
            [&](std::uint8_t* buffer, std::size_t capacity,
                std::size_t* required) {
                return function(
                    context->raw, raw, buffer, capacity, required);
            });
    };
    Message result;
    result.id = copy(codex_agent_message_id_copy);
    result.client_message_id = read_present_string(
        [&](auto* present) {
            return codex_agent_message_has_client_message_id(
                context->raw, raw, present);
        },
        [&](std::uint8_t* buffer, std::size_t capacity,
            std::size_t* required) {
            return codex_agent_message_client_message_id_copy(
                context->raw, raw, buffer, capacity, required);
        });
    codex_agent_message_role_t role = -1;
    check(codex_agent_message_role(context->raw, raw, &role));
    result.role = static_cast<MessageRole>(role);
    result.text = copy(codex_agent_message_text_copy);
    result.reasoning = read_present_string(
        [&](auto* present) {
            return codex_agent_message_has_reasoning(
                context->raw, raw, present);
        },
        [&](std::uint8_t* buffer, std::size_t capacity,
            std::size_t* required) {
            return codex_agent_message_reasoning_copy(
                context->raw, raw, buffer, capacity, required);
        });
    result.plan = read_present_string(
        [&](auto* present) {
            return codex_agent_message_has_plan(context->raw, raw, present);
        },
        [&](std::uint8_t* buffer, std::size_t capacity,
            std::size_t* required) {
            return codex_agent_message_plan_copy(
                context->raw, raw, buffer, capacity, required);
        });
    result.shell_command = read_present_string(
        [&](auto* present) {
            return codex_agent_message_has_shell_command(
                context->raw, raw, present);
        },
        [&](std::uint8_t* buffer, std::size_t capacity,
            std::size_t* required) {
            return codex_agent_message_shell_command_copy(
                context->raw, raw, buffer, capacity, required);
        });
    std::int32_t has_exit_code = 0;
    std::int32_t exit_code = 0;
    check(codex_agent_message_exit_code(
        context->raw, raw, &has_exit_code, &exit_code));
    if (has_exit_code != 0) result.exit_code = exit_code;
    codex_agent_collaboration_mode_t mode = -1;
    check(codex_agent_message_collaboration_mode(
        context->raw, raw, &mode));
    result.collaboration_mode = static_cast<CollaborationMode>(mode);
    std::size_t capability_count = 0;
    check(codex_agent_message_capabilities_count(
        context->raw, raw, &capability_count));
    std::int32_t has_web_search = 0;
    check(codex_agent_message_has_capability(
        context->raw, raw, CODEX_AGENT_CAPABILITY_WEB_SEARCH,
        &has_web_search));
    if (has_web_search != 0) result.capabilities.insert(Capability::web_search);
    if (result.capabilities.size() != capability_count) {
        throw Error(Status::internal_error);
    }
    std::size_t invocation_count = 0;
    check(codex_agent_message_invocations_count(
        context->raw, raw, &invocation_count));
    result.invocations.reserve(invocation_count);
    for (std::size_t index = 0; index < invocation_count; ++index) {
        codex_agent_invocation_t* invocation_raw = nullptr;
        check(codex_agent_message_invocation_at(
            context->raw, raw, index, &invocation_raw));
        InvocationHandle invocation(context, invocation_raw);
        result.invocations.push_back(
            read_invocation(context, invocation.get()));
    }
    return result;
}

inline ConversationValue read_conversation_value(
    const Context& context, codex_agent_conversation_value_t* raw) {
    codex_agent_conversation_summary_t* summary_raw = nullptr;
    check(codex_agent_conversation_value_summary(
        context->raw, raw, &summary_raw));
    ConversationSummaryHandle summary(context, summary_raw);
    std::size_t count = 0;
    check(codex_agent_conversation_value_messages_count(
        context->raw, raw, &count));
    std::vector<Message> messages;
    messages.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        codex_agent_message_t* message_raw = nullptr;
        check(codex_agent_conversation_value_message_at(
            context->raw, raw, index, &message_raw));
        MessageHandle message(context, message_raw);
        messages.push_back(read_message(context, message.get()));
    }
    return {read_conversation_summary(context, summary.get()),
            std::move(messages)};
}

inline PlanProgress read_plan_progress(
    const Context& context, codex_agent_plan_progress_t* raw) {
    PlanProgress result;
    result.explanation = read_present_string(
        [&](auto* present) {
            return codex_agent_plan_progress_has_explanation(
                context->raw, raw, present);
        },
        [&](std::uint8_t* buffer, std::size_t capacity,
            std::size_t* required) {
            return codex_agent_plan_progress_explanation_copy(
                context->raw, raw, buffer, capacity, required);
        });
    std::size_t count = 0;
    check(codex_agent_plan_progress_steps_count(
        context->raw, raw, &count));
    result.steps.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        codex_agent_plan_step_t* step_raw = nullptr;
        check(codex_agent_plan_progress_step_at(
            context->raw, raw, index, &step_raw));
        PlanStepHandle step(context, step_raw);
        auto text = copy_string(
            [&](std::uint8_t* buffer, std::size_t capacity,
                std::size_t* required) {
                return codex_agent_plan_step_text_copy(
                    context->raw, step.get(), buffer, capacity, required);
            });
        codex_agent_plan_step_status_t status = -1;
        check(codex_agent_plan_step_status(
            context->raw, step.get(), &status));
        result.steps.push_back(
            {std::move(text), static_cast<PlanStepStatus>(status)});
    }
    return result;
}

inline HookActivity read_hook_activity(
    const Context& context, codex_agent_hook_activity_t* raw) {
    auto copy = [&](auto function) {
        return copy_string(
            [&](std::uint8_t* buffer, std::size_t capacity,
                std::size_t* required) {
                return function(
                    context->raw, raw, buffer, capacity, required);
            });
    };
    HookActivity result;
    result.id = copy(codex_agent_hook_activity_id_copy);
    result.event_name = copy(codex_agent_hook_activity_event_name_copy);
    result.handler_type = copy(codex_agent_hook_activity_handler_type_copy);
    codex_agent_hook_run_status_t status = -1;
    check(codex_agent_hook_activity_status(context->raw, raw, &status));
    result.status = static_cast<HookRunStatus>(status);
    result.status_message = read_present_string(
        [&](auto* present) {
            return codex_agent_hook_activity_has_status_message(
                context->raw, raw, present);
        },
        [&](std::uint8_t* buffer, std::size_t capacity,
            std::size_t* required) {
            return codex_agent_hook_activity_status_message_copy(
                context->raw, raw, buffer, capacity, required);
        });
    std::size_t count = 0;
    check(codex_agent_hook_activity_details_count(
        context->raw, raw, &count));
    result.details.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        result.details.push_back(copy_string(
            [&](std::uint8_t* buffer, std::size_t capacity,
                std::size_t* required) {
                return codex_agent_hook_activity_detail_copy_at(
                    context->raw, raw, index, buffer, capacity, required);
            }));
    }
    return result;
}

inline TurnProgress read_turn_progress(
    const Context& context, codex_agent_turn_progress_t* raw) {
    auto copy = [&](auto function) {
        return copy_string(
            [&](std::uint8_t* buffer, std::size_t capacity,
                std::size_t* required) {
                return function(
                    context->raw, raw, buffer, capacity, required);
            });
    };
    TurnProgress result;
    result.text = copy(codex_agent_turn_progress_text_copy);
    result.commentary = copy(codex_agent_turn_progress_commentary_copy);
    result.reasoning = copy(codex_agent_turn_progress_reasoning_copy);
    result.plan = copy(codex_agent_turn_progress_plan_copy);
    std::int32_t has_plan_progress = 0;
    check(codex_agent_turn_progress_has_plan_progress(
        context->raw, raw, &has_plan_progress));
    if (has_plan_progress != 0) {
        codex_agent_plan_progress_t* progress_raw = nullptr;
        check(codex_agent_turn_progress_plan_progress(
            context->raw, raw, &progress_raw));
        PlanProgressHandle progress(context, progress_raw);
        result.plan_progress = read_plan_progress(context, progress.get());
    }
    result.shell_output = copy(codex_agent_turn_progress_shell_output_copy);
    std::int32_t has_exit_code = 0;
    std::int32_t exit_code = 0;
    check(codex_agent_turn_progress_shell_exit_code(
        context->raw, raw, &has_exit_code, &exit_code));
    if (has_exit_code != 0) result.shell_exit_code = exit_code;
    std::int32_t has_activity = 0;
    codex_agent_work_activity_t activity = -1;
    check(codex_agent_turn_progress_work_activity(
        context->raw, raw, &has_activity, &activity));
    if (has_activity != 0) {
        result.work_activity = static_cast<WorkActivity>(activity);
    }
    std::size_t count = 0;
    check(codex_agent_turn_progress_hook_activities_count(
        context->raw, raw, &count));
    result.hook_activities.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        codex_agent_hook_activity_t* activity_raw = nullptr;
        check(codex_agent_turn_progress_hook_activity_at(
            context->raw, raw, index, &activity_raw));
        HookActivityHandle hook_activity(context, activity_raw);
        result.hook_activities.push_back(
            read_hook_activity(context, hook_activity.get()));
    }
    std::int32_t truncated = 0;
    check(codex_agent_turn_progress_is_truncated(
        context->raw, raw, &truncated));
    result.is_truncated = truncated != 0;
    return result;
}

inline InvocationHandle make_invocation(
    const Context& context, const InvocationValue& invocation) {
    return std::visit(
        [&](const auto& selected) -> InvocationHandle {
            using Value = std::decay_t<decltype(selected)>;
            const auto name = string_view(selected.name);
            codex_agent_invocation_t* raw = nullptr;
            if constexpr (std::is_same_v<Value, PluginInvocation>) {
                const auto uri = string_view(selected.uri);
                auto plugin = make_sync_handle<
                    codex_agent_invocation_plugin_t,
                    codex_agent_invocation_plugin_destroy>(
                    context, [&](auto** out) {
                        return codex_agent_invocation_plugin_create(
                            context->raw, &name, &uri, out);
                    });
                check(codex_agent_invocation_from_plugin(
                    context->raw, plugin.get(), &raw));
            } else {
                const auto path = string_view(selected.path);
                auto skill = make_sync_handle<
                    codex_agent_invocation_skill_t,
                    codex_agent_invocation_skill_destroy>(
                    context, [&](auto** out) {
                        return codex_agent_invocation_skill_create(
                            context->raw, &name, &path, out);
                    });
                check(codex_agent_invocation_from_skill(
                    context->raw, skill.get(), &raw));
            }
            return {context, raw};
        },
        invocation);
}

inline TurnRequestHandle make_turn_request(
    const Context& context, const TurnRequest& request) {
    std::vector<InvocationHandle> invocations;
    std::vector<codex_agent_invocation_t*> raw_invocations;
    invocations.reserve(request.invocations.size());
    raw_invocations.reserve(request.invocations.size());
    for (const auto& invocation : request.invocations) {
        invocations.push_back(make_invocation(context, invocation));
        raw_invocations.push_back(invocations.back().get());
    }
    std::vector<codex_agent_capability_t> capabilities;
    capabilities.reserve(request.capabilities.size());
    for (const auto capability : request.capabilities) {
        capabilities.push_back(
            static_cast<codex_agent_capability_t>(capability));
    }
    const std::string empty;
    const auto prompt = string_view(request.prompt);
    const auto client_message_id = string_view(
        request.client_message_id ? *request.client_message_id : empty);
    const auto model = string_view(request.model ? *request.model : empty);
    const auto effort = string_view(request.effort ? *request.effort : empty);
    const auto service_tier = string_view(
        request.service_tier ? *request.service_tier : empty);
    return make_sync_handle<
        codex_agent_turn_request_t, codex_agent_turn_request_destroy>(
        context, [&](auto** out) {
            return codex_agent_turn_request_create(
                context->raw, &prompt, request.client_message_id ? 1 : 0,
                &client_message_id, request.model ? 1 : 0, &model,
                request.effort ? 1 : 0, &effort,
                request.service_tier ? 1 : 0, &service_tier,
                static_cast<codex_agent_approval_preset_t>(
                    request.approval_preset),
                capabilities.empty() ? nullptr : capabilities.data(),
                capabilities.size(),
                raw_invocations.empty() ? nullptr : raw_invocations.data(),
                raw_invocations.size(),
                static_cast<codex_agent_collaboration_mode_t>(
                    request.collaboration_mode),
                out);
        });
}

inline ConversationState parse_conversation_state(
    const Context& context,
    codex_agent_snapshot_t* snapshot) {
    codex_agent_conversation_status_t raw_status = 0;
    check(codex_agent_conversation_state_status(context->raw, snapshot, &raw_status));
    ConversationState state{static_cast<ConversationStatus>(raw_status), std::nullopt};
    std::int32_t present = 0;
    check(codex_agent_conversation_state_has_conversation_id(
        context->raw, snapshot, &present));
    if (present != 0) {
        codex_agent_conversation_id_t* raw_id = nullptr;
        check(codex_agent_conversation_state_conversation_id(
            context->raw, snapshot, &raw_id));
        ConversationIdHandle id(context, raw_id);
        state.conversation_id = read_conversation_id(context, id.get());
    }
    check(codex_agent_conversation_state_has_conversation(
        context->raw, snapshot, &present));
    if (present != 0) {
        codex_agent_conversation_value_t* raw_value = nullptr;
        check(codex_agent_conversation_state_conversation(
            context->raw, snapshot, &raw_value));
        ConversationValueHandle value(context, raw_value);
        state.conversation = read_conversation_value(context, value.get());
    }
    codex_agent_turn_progress_t* raw_progress = nullptr;
    check(codex_agent_conversation_state_turn_progress(
        context->raw, snapshot, &raw_progress));
    TurnProgressHandle progress(context, raw_progress);
    state.turn_progress = read_turn_progress(context, progress.get());
    state.model = read_present_string(
        [&](auto* has) {
            return codex_agent_conversation_state_has_model(
                context->raw, snapshot, has);
        },
        [&](std::uint8_t* buffer, std::size_t capacity,
            std::size_t* required) {
            return codex_agent_conversation_state_model_copy(
                context->raw, snapshot, buffer, capacity, required);
        });
    state.effort = read_present_string(
        [&](auto* has) {
            return codex_agent_conversation_state_has_effort(
                context->raw, snapshot, has);
        },
        [&](std::uint8_t* buffer, std::size_t capacity,
            std::size_t* required) {
            return codex_agent_conversation_state_effort_copy(
                context->raw, snapshot, buffer, capacity, required);
        });
    state.service_tier = read_present_string(
        [&](auto* has) {
            return codex_agent_conversation_state_has_service_tier(
                context->raw, snapshot, has);
        },
        [&](std::uint8_t* buffer, std::size_t capacity,
            std::size_t* required) {
            return codex_agent_conversation_state_service_tier_copy(
                context->raw, snapshot, buffer, capacity, required);
        });
    check(codex_agent_conversation_state_can_start_turn(
        context->raw, snapshot, &present));
    state.can_start_turn = present != 0;
    check(codex_agent_conversation_state_can_cancel_turn(
        context->raw, snapshot, &present));
    state.can_cancel_turn = present != 0;
    check(codex_agent_conversation_state_can_reload(
        context->raw, snapshot, &present));
    state.can_reload = present != 0;
    if (state.status == ConversationStatus::failed) {
        codex_agent_failure_t* raw_failure = nullptr;
        check(codex_agent_conversation_state_failure(
            context->raw, snapshot, &raw_failure));
        try {
            state.failure = read_failure(context, raw_failure);
            check(codex_agent_failure_release(context->raw, &raw_failure));
        } catch (...) {
            if (raw_failure != nullptr) {
                (void)codex_agent_failure_release(context->raw, &raw_failure);
            }
            throw;
        }
    }
    return state;
}

}  // namespace detail

inline AuthorizationUrl AuthorizationUrl::chat_gpt(std::string value) {
    auto context = detail::make_sync_context();
    const auto raw_value = detail::string_view(value);
    auto url = detail::make_sync_handle<
        codex_agent_authorization_url_t, codex_agent_authorization_url_destroy>(
        context, [&](auto** out) {
            return codex_agent_authorization_url_chat_gpt(
                context->raw, &raw_value, out);
        });
    return detail::read_authorization_url(
        context, url, AuthorizationPurpose::chat_gpt);
}

inline AuthorizationUrl AuthorizationUrl::external(std::string value) {
    auto context = detail::make_sync_context();
    const auto raw_value = detail::string_view(value);
    auto url = detail::make_sync_handle<
        codex_agent_authorization_url_t, codex_agent_authorization_url_destroy>(
        context, [&](auto** out) {
            return codex_agent_authorization_url_external(
                context->raw, &raw_value, out);
        });
    return detail::read_authorization_url(
        context, url, AuthorizationPurpose::external);
}

inline ElicitationResponse ElicitationResponse::decline() {
    auto context = detail::make_sync_context();
    auto response = detail::make_sync_handle<
        codex_agent_elicitation_response_t,
        codex_agent_elicitation_response_destroy>(
        context, [&](auto** out) {
            return codex_agent_elicitation_response_decline(
                context->raw, out);
        });
    return detail::read_elicitation_response(context, response.get(), {});
}

inline ElicitationResponse ElicitationResponse::cancel() {
    auto context = detail::make_sync_context();
    auto response = detail::make_sync_handle<
        codex_agent_elicitation_response_t,
        codex_agent_elicitation_response_destroy>(
        context, [&](auto** out) {
            return codex_agent_elicitation_response_cancel(
                context->raw, out);
        });
    return detail::read_elicitation_response(context, response.get(), {});
}

inline bool FormField::accepts(
    const std::optional<FormValue>& value) const {
    auto context = detail::make_sync_context();
    auto field = detail::make_form_field(context, *this);
    std::optional<detail::FormValueHandle> raw_value;
    if (value) raw_value.emplace(detail::make_form_value(context, *value));
    std::int32_t accepts = 0;
    detail::check(codex_agent_form_field_accepts(
        context->raw, field.get(), raw_value ? raw_value->get() : nullptr,
        &accepts));
    return accepts != 0;
}

inline std::map<std::string, FormValue> Elicitation::initial_values() const {
    auto context = detail::make_sync_context();
    auto elicitation = detail::make_elicitation(context, *this);
    auto content = detail::make_sync_handle<
        codex_agent_form_content_t, codex_agent_form_content_destroy>(
        context, [&](auto** out) {
            return codex_agent_elicitation_initial_values(
                context->raw, elicitation.get(), out);
        });
    return detail::read_form_content(context, content.get());
}

inline ElicitationValidation Elicitation::validate(
    const std::map<std::string, FormValue>& content) const {
    auto context = detail::make_sync_context();
    auto elicitation = detail::make_elicitation(context, *this);
    auto raw_content = detail::make_form_content(context, content);
    auto validation = detail::make_sync_handle<
        codex_agent_elicitation_validation_t,
        codex_agent_elicitation_validation_destroy>(
        context, [&](auto** out) {
            return codex_agent_elicitation_validate(
                context->raw, elicitation.get(), raw_content.get(), out);
        });
    return detail::read_elicitation_validation(context, validation.get());
}

inline ElicitationResponse Elicitation::accept(
    const std::map<std::string, FormValue>& content) const {
    auto context = detail::make_sync_context();
    auto elicitation = detail::make_elicitation(context, *this);
    auto raw_content = detail::make_form_content(context, content);
    auto response = detail::make_sync_handle<
        codex_agent_elicitation_response_t,
        codex_agent_elicitation_response_destroy>(
        context, [&](auto** out) {
            return codex_agent_elicitation_accept(
                context->raw, elicitation.get(), raw_content.get(), out);
        });
    return detail::read_elicitation_response(
        context, response.get(), content);
}

inline bool Elicitation::accepts(
    const ElicitationResponse& response) const {
    auto context = detail::make_sync_context();
    auto elicitation = detail::make_elicitation(context, *this);
    auto raw_response = detail::make_elicitation_response(context, response);
    std::int32_t accepts = 0;
    detail::check(codex_agent_elicitation_accepts(
        context->raw, elicitation.get(), raw_response.get(), &accepts));
    return accepts != 0;
}

inline std::vector<PendingInteractionValue> InteractionState::pending_for(
    const ConversationId& conversation_id) const {
    auto context = detail::make_sync_context();
    auto state = detail::make_interaction_state(context, *this);
    auto raw_conversation_id = detail::make_conversation_id(
        context, conversation_id);
    auto selected = detail::make_sync_handle<
        codex_agent_pending_interaction_list_t,
        codex_agent_pending_interaction_list_destroy>(
        context, [&](auto** out) {
            return codex_agent_interaction_state_pending_for(
                context->raw, state.get(), raw_conversation_id.get(), out);
        });
    std::size_t count = 0;
    detail::check(codex_agent_pending_interaction_list_count(
        context->raw, selected.get(), &count));
    std::vector<PendingInteractionValue> result;
    result.reserve(count);
    std::size_t search_from = 0;
    for (std::size_t index = 0; index < count; ++index) {
        codex_agent_pending_interaction_t* raw_interaction = nullptr;
        detail::check(codex_agent_pending_interaction_list_at(
            context->raw, selected.get(), index, &raw_interaction));
        detail::PendingInteractionHandle interaction(
            context, raw_interaction);
        const auto signature = detail::pending_signature(
            context, interaction.get());
        while (search_from < pending.size() &&
               detail::pending_signature(pending[search_from]) != signature) {
            ++search_from;
        }
        if (search_from == pending.size()) {
            throw Error(Status::internal_error);
        }
        result.push_back(pending[search_from++]);
    }
    return result;
}

inline bool InteractionState::is_resolving(
    const PendingInteraction& interaction) const {
    std::optional<std::size_t> live_index;
    for (std::size_t index = 0; index < pending.size(); ++index) {
        const auto* candidate = std::visit(
            [](const auto& value) {
                return static_cast<const PendingInteraction*>(&value);
            },
            pending[index]);
        if (candidate == &interaction) {
            live_index = index;
            break;
        }
    }

    auto context = detail::make_sync_context();
    auto state = detail::make_interaction_state(context, *this);
    detail::PendingInteractionHandle raw_interaction;
    if (live_index) {
        codex_agent_pending_interaction_t* raw = nullptr;
        detail::check(codex_agent_interaction_state_pending_at(
            context->raw, state.get(), *live_index, &raw));
        raw_interaction = detail::PendingInteractionHandle(context, raw);
    } else {
        raw_interaction = detail::make_pending_interaction(
            context, interaction);
    }
    std::int32_t resolving = 0;
    detail::check(codex_agent_interaction_state_is_resolving(
        context->raw, state.get(), raw_interaction.get(), &resolving));
    if (resolving != 0 || !live_index) return resolving != 0;

    const auto request_id = detail::string_view(interaction.request_id);
    std::int32_t contains = 0;
    detail::check(codex_agent_interaction_state_resolving_request_ids_contains(
        context->raw, state.get(), &request_id, &contains));
    return contains != 0;
}

template <typename Value>
class AsyncOperation final {
public:
    AsyncOperation() = default;
    AsyncOperation(const AsyncOperation&) = delete;
    AsyncOperation& operator=(const AsyncOperation&) = delete;
    AsyncOperation(AsyncOperation&&) noexcept = default;
    AsyncOperation& operator=(AsyncOperation&&) noexcept = default;

    ~AsyncOperation() noexcept {
        if (future_.valid() &&
            future_.wait_for(std::chrono::seconds(0)) != std::future_status::ready) {
            cancel_noexcept();
            future_.wait();
        }
    }

    [[nodiscard]] bool valid() const noexcept { return future_.valid(); }

    void cancel() {
        if (!state_) {
            return;
        }
        codex_agent_operation_t* operation = nullptr;
        {
            std::lock_guard lock(state_->mutex);
            if (state_->callback_seen || state_->operation == nullptr) {
                return;
            }
            state_->call_in_progress = true;
            operation = state_->operation;
        }
        const auto status = codex_agent_operation_cancel(state_->context->raw, operation);
        {
            std::lock_guard lock(state_->mutex);
            state_->call_in_progress = false;
        }
        state_->changed.notify_all();
        detail::check(status);
    }

    Value get() { return future_.get(); }

    void wait() const { future_.wait(); }

    template <typename Rep, typename Period>
    std::future_status wait_for(
        const std::chrono::duration<Rep, Period>& timeout) const {
        return future_.wait_for(timeout);
    }

private:
    friend class detail::AsyncOperationFactory<Value>;
    AsyncOperation(
        std::shared_ptr<detail::OperationState> state,
        std::future<Value> future)
        : state_(std::move(state)), future_(std::move(future)) {}

    void cancel_noexcept() noexcept {
        try {
            cancel();
        } catch (...) {
        }
    }

    std::shared_ptr<detail::OperationState> state_;
    std::future<Value> future_;
};

template <>
inline void AsyncOperation<void>::get() {
    future_.get();
}

namespace detail {

template <typename Value>
class AsyncOperationFactory final {
public:
    static AsyncOperation<Value> create(
        std::shared_ptr<OperationState> state,
        std::future<Value> future) {
        return AsyncOperation<Value>(std::move(state), std::move(future));
    }
};

template <typename Value, typename Initiate, typename Extract>
auto start_operation(
    Context context, Initiate&& initiate, Extract&& extract) {
    auto state = std::make_shared<OperationState>(std::move(context));
    auto* token = new std::shared_ptr<OperationState>(state);
    codex_agent_operation_t* operation = nullptr;
    const auto status = initiate(operation_callback, token, &operation);
    if (status != CODEX_AGENT_STATUS_OK) {
        delete token;
        check(status);
    }
    {
        std::lock_guard lock(state->mutex);
        state->operation = operation;
    }

    auto future = std::async(
        std::launch::async,
        [state, extract = std::forward<Extract>(extract)]() mutable -> Value {
            std::unique_lock lock(state->mutex);
            state->changed.wait(lock, [&] {
                return state->callback_seen && !state->call_in_progress;
            });
            const auto operation = state->operation;
            codex_agent_status_t result = CODEX_AGENT_STATUS_INTERNAL_ERROR;
            std::exception_ptr error;
            std::optional<std::conditional_t<std::is_void_v<Value>, bool, Value>> value;
            try {
                check(codex_agent_operation_result(
                    state->context->raw, operation, &result));
                if (result != CODEX_AGENT_STATUS_OK) {
                    throw OperationError(
                        status_from_raw(result),
                        operation_failure(state->context, operation));
                }
                if constexpr (std::is_void_v<Value>) {
                    extract(state->context, operation);
                    value = true;
                } else {
                    value.emplace(extract(state->context, operation));
                }
            } catch (...) {
                error = std::current_exception();
            }
            try {
                destroy_operation(*state);
            } catch (...) {
                if (!error) {
                    error = std::current_exception();
                }
            }
            lock.unlock();
            if (error) {
                std::rethrow_exception(error);
            }
            if constexpr (!std::is_void_v<Value>) {
                return std::move(*value);
            }
        });
    return AsyncOperationFactory<Value>::create(std::move(state), std::move(future));
}

}  // namespace detail

template <typename Value>
class StateSubscription final {
public:
    StateSubscription() = default;
    StateSubscription(const StateSubscription&) = delete;
    StateSubscription& operator=(const StateSubscription&) = delete;

    StateSubscription(StateSubscription&& other) noexcept
        : close_(std::move(other.close_)), error_(std::move(other.error_)) {}

    StateSubscription& operator=(StateSubscription&& other) noexcept {
        if (this != &other) {
            close_noexcept();
            close_ = std::move(other.close_);
            error_ = std::move(other.error_);
        }
        return *this;
    }

    ~StateSubscription() noexcept { close_noexcept(); }

    void close() {
        if (close_) {
            auto close = std::move(close_);
            close();
        }
    }

    [[nodiscard]] std::exception_ptr callback_error() const {
        return error_ ? error_() : std::exception_ptr{};
    }

    StateSubscription(
        std::function<void()> close,
        std::function<std::exception_ptr()> error)
        : close_(std::move(close)), error_(std::move(error)) {}

private:
    void close_noexcept() noexcept {
        try {
            close();
        } catch (...) {
        }
    }

    std::function<void()> close_;
    std::function<std::exception_ptr()> error_;
};

template <typename Value, typename State, typename Subscribe>
StateSubscription<Value> detail_subscribe(
    std::shared_ptr<State> state,
    Subscribe&& subscribe) {
    auto* token = new std::shared_ptr<State>(state);
    codex_agent_subscription_t* subscription = nullptr;
    const auto status = subscribe(
        &detail::state_callback<State>, token, &subscription);
    if (status != CODEX_AGENT_STATUS_OK) {
        delete token;
        detail::check(status);
    }
    {
        std::lock_guard lock(state->mutex);
        state->subscription = subscription;
    }

    auto close = [state, token]() mutable {
        auto destroy = [state, token]() mutable {
            for (;;) {
                codex_agent_status_t status;
                {
                    std::lock_guard lock(state->mutex);
                    if (state->subscription == nullptr) {
                        delete token;
                        return;
                    }
                    status = codex_agent_subscription_destroy(
                        state->context->raw, &state->subscription);
                }
                if (status == CODEX_AGENT_STATUS_OK) {
                    delete token;
                    return;
                }
                if (status != CODEX_AGENT_STATUS_BUSY) {
                    delete token;
                    detail::check(status);
                }
                std::this_thread::yield();
            }
        };

        bool on_callback_thread = false;
        {
            std::lock_guard lock(state->mutex);
            on_callback_thread = state->callback_thread == std::this_thread::get_id();
        }
        if (on_callback_thread) {
            std::thread([destroy = std::move(destroy)]() mutable noexcept {
                try {
                    destroy();
                } catch (...) {
                    // A destructor reached from a C callback cannot report errors.
                }
            }).detach();
        } else {
            destroy();
        }
    };
    auto error = [state] {
        std::lock_guard lock(state->mutex);
        return state->callback_error;
    };
    return StateSubscription<Value>(std::move(close), std::move(error));
}

class Host final {
public:
    Host() = default;
    Host(const Host&) = delete;
    Host& operator=(const Host&) = delete;
    Host(Host&&) noexcept = default;
    Host& operator=(Host&&) noexcept = default;

    static Host create(const HostOptions& options) {
        if (!detail::non_blank(options.bundle_directory) ||
            options.bundle_directory.find('\0') != std::string::npos ||
            !detail::non_blank(options.data_directory) ||
            options.data_directory.find('\0') != std::string::npos) {
            throw std::invalid_argument("Host paths are invalid");
        }
        (void)ClientInfo(
            options.client_info.name, options.client_info.title,
            options.client_info.version);
        if (codex_agent_abi_is_compatible(CODEX_AGENT_ABI_VERSION_CURRENT) == 0) {
            throw Error(Status::unsupported_abi);
        }
        auto context = std::make_shared<detail::ContextState>();
        detail::check(codex_agent_context_create(&context->raw));

        const auto bundle = detail::string_view(options.bundle_directory);
        const auto data = detail::string_view(options.data_directory);
        const auto name = detail::string_view(options.client_info.name);
        const auto title = detail::string_view(options.client_info.title);
        const auto version = detail::string_view(options.client_info.version);
        const codex_agent_host_options_t raw_options{
            sizeof(codex_agent_host_options_t),
            bundle,
            data,
            {
                sizeof(codex_agent_client_info_t),
                name,
                title,
                version,
            },
        };
        codex_agent_host_t* raw = nullptr;
        detail::check(codex_agent_host_create(context->raw, &raw_options, &raw));
        return Host(detail::HostHandle(std::move(context), raw));
    }

    [[nodiscard]] HostState state() const {
        ensure_valid();
        codex_agent_snapshot_t* raw = nullptr;
        detail::check(codex_agent_host_state_get(
            handle_.context_raw(), handle_.get(), &raw));
        detail::Snapshot snapshot(handle_.context(), raw);
        return detail::parse_host_state(handle_.context(), snapshot.get());
    }

    StateSubscription<HostState> subscribe(
        std::function<void(StateEvent<HostState>)> callback) const {
        ensure_valid();
        auto owner = detail::retain_host(handle_);
        using Parse = std::function<HostState(codex_agent_context_t*, codex_agent_snapshot_t*)>;
        Parse parse = [context = handle_.context()](
                          codex_agent_context_t*, codex_agent_snapshot_t* snapshot) {
            return detail::parse_host_state(context, snapshot);
        };
        using State = detail::SubscriptionState<HostState, Parse>;
        auto state = std::make_shared<State>(handle_.context(), owner, std::move(parse),
                                             std::move(callback));
        return detail_subscribe<HostState>(state, [owner](auto callback_fn, void* user_data,
                                                          auto** out_subscription) {
            return codex_agent_host_state_subscribe(
                owner->context_raw(), owner->get(), callback_fn, user_data,
                out_subscription);
        });
    }

    AsyncOperation<void> start() const {
        return simple_operation(codex_agent_host_start);
    }

    AsyncOperation<void> select_workspace(std::string path) const {
        ensure_valid();
        auto owner = detail::retain_host(handle_);
        auto context = owner->context();
        return detail::start_operation<void>(
            context,
            [context, owner, path = std::move(path)](
                auto callback, void* user_data, auto** out_operation) {
                const auto path_view = detail::string_view(path);
                const codex_agent_path_workspace_selection_t selection{
                    sizeof(codex_agent_path_workspace_selection_t), path_view};
                return codex_agent_host_select_workspace(
                    context->raw, owner->get(), &selection, callback, user_data,
                    out_operation);
            },
            [owner](const detail::Context&, codex_agent_operation_t*) {});
    }

    AsyncOperation<void> close() const {
        if (state().kind == HostStateKind::closed) {
            std::promise<void> completed;
            completed.set_value();
            return detail::AsyncOperationFactory<void>::create(
                nullptr, completed.get_future());
        }
        return simple_operation(codex_agent_host_close);
    }

    [[nodiscard]] Agent agent() const;

private:
    explicit Host(detail::HostHandle handle) : handle_(std::move(handle)) {}

    using HostOperation = codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t*, codex_agent_host_t*, codex_agent_operation_callback_t,
        void*, codex_agent_operation_t**);

    AsyncOperation<void> simple_operation(HostOperation operation) const {
        ensure_valid();
        auto owner = detail::retain_host(handle_);
        auto context = owner->context();
        return detail::start_operation<void>(
            context,
            [context, owner, operation](auto callback, void* user_data,
                                        auto** out_operation) {
                return operation(
                    context->raw, owner->get(), callback, user_data, out_operation);
            },
            [owner](const detail::Context&, codex_agent_operation_t*) {});
    }

    void ensure_valid() const {
        if (!handle_) {
            throw Error(Status::closed);
        }
    }

    detail::HostHandle handle_;
};

class Agent final {
public:
    Agent() = default;
    Agent(const Agent&) = delete;
    Agent& operator=(const Agent&) = delete;
    Agent(Agent&&) noexcept = default;
    Agent& operator=(Agent&&) noexcept = default;

    [[nodiscard]] Authentication authentication() const;
    [[nodiscard]] Connectors connectors() const;
    [[nodiscard]] Conversations conversations() const;
    [[nodiscard]] Hooks hooks() const;
    [[nodiscard]] IntegrationAuthorization integration_authorization() const;
    [[nodiscard]] Interactions interactions() const;
    [[nodiscard]] McpServers mcp_servers() const;
    [[nodiscard]] Models models() const;
    [[nodiscard]] Plugins plugins() const;
    [[nodiscard]] Skills skills() const;
    [[nodiscard]] Workspace workspace() const;

private:
    friend class Host;
    explicit Agent(std::shared_ptr<detail::AgentOwnership> owner)
        : owner_(std::move(owner)) {}

    void ensure_valid() const {
        if (!owner_ || !owner_->agent || !*owner_->agent) {
            throw Error(Status::closed);
        }
    }

    std::shared_ptr<detail::AgentOwnership> owner_;
};

struct HostStateReady final {
    explicit HostStateReady(Agent agent_value)
        : agent(std::move(agent_value)) {}

    HostStateReady(const HostStateReady&) = delete;
    HostStateReady& operator=(const HostStateReady&) = delete;
    HostStateReady(HostStateReady&&) noexcept = default;
    HostStateReady& operator=(HostStateReady&&) noexcept = default;

    Agent agent;
};

class Conversations final {
public:
    Conversations() = default;
    Conversations(const Conversations&) = delete;
    Conversations& operator=(const Conversations&) = delete;
    Conversations(Conversations&&) noexcept = default;
    Conversations& operator=(Conversations&&) noexcept = default;

    AsyncOperation<Conversation> open(
        std::optional<ConversationId> conversation_id = std::nullopt,
        ConversationSettings settings = {}) const;
    AsyncOperation<std::vector<ConversationSummary>> list() const;
    AsyncOperation<ConversationValue> read(ConversationId conversation_id) const;
    AsyncOperation<void> rename(
        ConversationId conversation_id, std::string title) const;
    AsyncOperation<void> remove(ConversationId conversation_id) const;
    [[nodiscard]] std::optional<Conversation> active() const;
    StateSubscription<std::optional<Conversation>> subscribe_active(
        std::function<void(StateEvent<std::optional<Conversation>>)> callback)
        const;

private:
    friend class Agent;
    Conversations(
        std::shared_ptr<detail::AgentOwnership> owner,
        detail::ConversationsHandle handle)
        : owner_(std::move(owner)), handle_(std::move(handle)) {}

    void ensure_valid() const {
        if (!handle_) {
            throw Error(Status::closed);
        }
    }

    std::shared_ptr<detail::AgentOwnership> owner_;
    detail::ConversationsHandle handle_;
};

class Conversation final {
public:
    Conversation() = default;
    Conversation(const Conversation&) = delete;
    Conversation& operator=(const Conversation&) = delete;
    Conversation(Conversation&&) noexcept = default;
    Conversation& operator=(Conversation&&) noexcept = default;

    [[nodiscard]] bool same_as(const Conversation& other) const {
        ensure_valid();
        other.ensure_valid();
        std::int32_t same = 0;
        detail::check(codex_agent_conversation_is_same(
            handle_.context_raw(), handle_.get(), other.handle_.get(), &same));
        return same != 0;
    }

    [[nodiscard]] ConversationState state() const {
        ensure_valid();
        codex_agent_snapshot_t* raw = nullptr;
        detail::check(codex_agent_conversation_state_get(
            handle_.context_raw(), handle_.get(), &raw));
        detail::Snapshot snapshot(handle_.context(), raw);
        return detail::parse_conversation_state(handle_.context(), snapshot.get());
    }

    StateSubscription<ConversationState> subscribe_state(
        std::function<void(StateEvent<ConversationState>)> callback) const {
        return subscribe_value<ConversationState>(
            codex_agent_conversation_state_subscribe,
            [](const detail::Context& context,
               codex_agent_snapshot_t* snapshot) {
                return detail::parse_conversation_state(context, snapshot);
            },
            std::move(callback));
    }

    StateSubscription<ConversationState> subscribe(
        std::function<void(StateEvent<ConversationState>)> callback) const {
        return subscribe_state(std::move(callback));
    }

    [[nodiscard]] std::vector<Message> current_messages() const {
        return current_value<std::vector<Message>>(
            codex_agent_conversation_current_messages_get,
            [](const detail::Context& context,
               codex_agent_snapshot_t* snapshot) {
                std::size_t count = 0;
                detail::check(codex_agent_conversation_current_messages_count(
                    context->raw, snapshot, &count));
                std::vector<Message> messages;
                messages.reserve(count);
                for (std::size_t index = 0; index < count; ++index) {
                    codex_agent_message_t* raw = nullptr;
                    detail::check(codex_agent_conversation_current_messages_at(
                        context->raw, snapshot, index, &raw));
                    detail::MessageHandle message(context, raw);
                    messages.push_back(
                        detail::read_message(context, message.get()));
                }
                return messages;
            });
    }

    StateSubscription<std::vector<Message>> subscribe_current_messages(
        std::function<void(StateEvent<std::vector<Message>>)> callback) const {
        return subscribe_value<std::vector<Message>>(
            codex_agent_conversation_current_messages_subscribe,
            [](const detail::Context& context,
               codex_agent_snapshot_t* snapshot) {
                std::size_t count = 0;
                detail::check(codex_agent_conversation_current_messages_count(
                    context->raw, snapshot, &count));
                std::vector<Message> messages;
                messages.reserve(count);
                for (std::size_t index = 0; index < count; ++index) {
                    codex_agent_message_t* raw = nullptr;
                    detail::check(codex_agent_conversation_current_messages_at(
                        context->raw, snapshot, index, &raw));
                    detail::MessageHandle message(context, raw);
                    messages.push_back(
                        detail::read_message(context, message.get()));
                }
                return messages;
            },
            std::move(callback));
    }

    [[nodiscard]] std::optional<TurnProgress> active_turn_progress() const {
        return current_value<std::optional<TurnProgress>>(
            codex_agent_conversation_active_turn_progress_get,
            [](const detail::Context& context,
               codex_agent_snapshot_t* snapshot)
                -> std::optional<TurnProgress> {
                std::int32_t present = 0;
                detail::check(
                    codex_agent_conversation_active_turn_progress_has_value(
                        context->raw, snapshot, &present));
                if (present == 0) return std::nullopt;
                codex_agent_turn_progress_t* raw = nullptr;
                detail::check(
                    codex_agent_conversation_active_turn_progress_value(
                        context->raw, snapshot, &raw));
                detail::TurnProgressHandle progress(context, raw);
                return detail::read_turn_progress(context, progress.get());
            });
    }

    StateSubscription<std::optional<TurnProgress>>
    subscribe_active_turn_progress(
        std::function<void(StateEvent<std::optional<TurnProgress>>)> callback)
        const {
        return subscribe_value<std::optional<TurnProgress>>(
            codex_agent_conversation_active_turn_progress_subscribe,
            [](const detail::Context& context,
               codex_agent_snapshot_t* snapshot)
                -> std::optional<TurnProgress> {
                std::int32_t present = 0;
                detail::check(
                    codex_agent_conversation_active_turn_progress_has_value(
                        context->raw, snapshot, &present));
                if (present == 0) return std::nullopt;
                codex_agent_turn_progress_t* raw = nullptr;
                detail::check(
                    codex_agent_conversation_active_turn_progress_value(
                        context->raw, snapshot, &raw));
                detail::TurnProgressHandle progress(context, raw);
                return detail::read_turn_progress(context, progress.get());
            },
            std::move(callback));
    }

    [[nodiscard]] bool can_cancel_turn() const {
        return boolean_value(codex_agent_conversation_can_cancel_turn_get);
    }
    StateSubscription<bool> subscribe_can_cancel_turn(
        std::function<void(StateEvent<bool>)> callback) const {
        return subscribe_boolean(
            codex_agent_conversation_can_cancel_turn_subscribe,
            std::move(callback));
    }
    [[nodiscard]] bool can_reload() const {
        return boolean_value(codex_agent_conversation_can_reload_get);
    }
    StateSubscription<bool> subscribe_can_reload(
        std::function<void(StateEvent<bool>)> callback) const {
        return subscribe_boolean(
            codex_agent_conversation_can_reload_subscribe,
            std::move(callback));
    }
    [[nodiscard]] bool can_run_shell_command() const {
        return boolean_value(
            codex_agent_conversation_can_run_shell_command_get);
    }
    StateSubscription<bool> subscribe_can_run_shell_command(
        std::function<void(StateEvent<bool>)> callback) const {
        return subscribe_boolean(
            codex_agent_conversation_can_run_shell_command_subscribe,
            std::move(callback));
    }
    [[nodiscard]] bool can_start_turn() const {
        return boolean_value(codex_agent_conversation_can_start_turn_get);
    }
    StateSubscription<bool> subscribe_can_start_turn(
        std::function<void(StateEvent<bool>)> callback) const {
        return subscribe_boolean(
            codex_agent_conversation_can_start_turn_subscribe,
            std::move(callback));
    }
    [[nodiscard]] bool is_turn_active() const {
        return boolean_value(codex_agent_conversation_is_turn_active_get);
    }
    StateSubscription<bool> subscribe_is_turn_active(
        std::function<void(StateEvent<bool>)> callback) const {
        return subscribe_boolean(
            codex_agent_conversation_is_turn_active_subscribe,
            std::move(callback));
    }

    AsyncOperation<void> send(std::string prompt) const {
        ensure_valid();
        auto owner = detail::retain_conversation(handle_);
        auto context = owner->context();
        return detail::start_operation<void>(
            context,
            [context, owner, prompt = std::move(prompt)](
                auto callback, void* user_data, auto** out_operation) {
                const auto view = detail::string_view(prompt);
                return codex_agent_conversation_send(
                    context->raw, owner->get(), &view, callback, user_data,
                    out_operation);
            },
            [owner](const detail::Context&, codex_agent_operation_t*) {});
    }

    AsyncOperation<void> send(TurnRequest request) const {
        ensure_valid();
        auto owner = detail::retain_conversation(handle_);
        auto context = owner->context();
        auto raw_request = std::make_shared<detail::TurnRequestHandle>(
            detail::make_turn_request(context, request));
        return detail::start_operation<void>(
            context,
            [context, owner, raw_request](
                auto callback, void* user_data, auto** out_operation) {
                return codex_agent_conversation_send_request(
                    context->raw, owner->get(), raw_request->get(), callback,
                    user_data, out_operation);
            },
            [owner, raw_request](
                const detail::Context&, codex_agent_operation_t*) {});
    }

    AsyncOperation<void> run_shell_command(std::string command) const {
        ensure_valid();
        auto owner = detail::retain_conversation(handle_);
        auto context = owner->context();
        return detail::start_operation<void>(
            context,
            [context, owner, command = std::move(command)](
                auto callback, void* user_data, auto** out_operation) {
                const auto view = detail::string_view(command);
                return codex_agent_conversation_run_shell_command(
                    context->raw, owner->get(), &view, callback, user_data,
                    out_operation);
            },
            [owner](const detail::Context&, codex_agent_operation_t*) {});
    }

    AsyncOperation<void> reload() const {
        return simple_operation(codex_agent_conversation_reload);
    }

    AsyncOperation<void> cancel_turn() const {
        return simple_operation(codex_agent_conversation_cancel_turn);
    }

    AsyncOperation<void> close() const {
        return simple_operation(codex_agent_conversation_close);
    }

private:
    friend class Conversations;
    explicit Conversation(detail::ConversationHandle handle)
        : handle_(std::move(handle)) {}

    using ConversationOperation = codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t*, codex_agent_conversation_t*,
        codex_agent_operation_callback_t, void*, codex_agent_operation_t**);
    using ConversationStateGet = codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t*, codex_agent_conversation_t*,
        codex_agent_snapshot_t**);
    using ConversationStateSubscribe = codex_agent_status_t (CODEX_AGENT_CALL *)(
        codex_agent_context_t*, codex_agent_conversation_t*,
        codex_agent_state_callback_t, void*, codex_agent_subscription_t**);

    template <typename Value, typename Parse>
    Value current_value(ConversationStateGet get, Parse parse) const {
        ensure_valid();
        codex_agent_snapshot_t* raw = nullptr;
        detail::check(get(handle_.context_raw(), handle_.get(), &raw));
        detail::Snapshot snapshot(handle_.context(), raw);
        return parse(handle_.context(), snapshot.get());
    }

    template <typename Value, typename Parse>
    StateSubscription<Value> subscribe_value(
        ConversationStateSubscribe subscribe, Parse parse,
        std::function<void(StateEvent<Value>)> callback) const {
        ensure_valid();
        auto owner = detail::retain_conversation(handle_);
        using Parser = std::function<Value(
            codex_agent_context_t*, codex_agent_snapshot_t*)>;
        Parser parser = [context = handle_.context(), parse = std::move(parse)](
                            codex_agent_context_t*,
                            codex_agent_snapshot_t* snapshot) mutable {
            return parse(context, snapshot);
        };
        using State = detail::SubscriptionState<Value, Parser>;
        auto state = std::make_shared<State>(
            handle_.context(), owner, std::move(parser), std::move(callback));
        return detail_subscribe<Value>(
            state,
            [owner, subscribe](auto callback_fn, void* user_data,
                               auto** out_subscription) {
                return subscribe(
                    owner->context_raw(), owner->get(), callback_fn,
                    user_data, out_subscription);
            });
    }

    bool boolean_value(ConversationStateGet get) const {
        return current_value<bool>(
            get,
            [](const detail::Context& context,
               codex_agent_snapshot_t* snapshot) {
                std::int32_t value = 0;
                detail::check(codex_agent_state_boolean_value(
                    context->raw, snapshot, &value));
                return value != 0;
            });
    }

    StateSubscription<bool> subscribe_boolean(
        ConversationStateSubscribe subscribe,
        std::function<void(StateEvent<bool>)> callback) const {
        return subscribe_value<bool>(
            subscribe,
            [](const detail::Context& context,
               codex_agent_snapshot_t* snapshot) {
                std::int32_t value = 0;
                detail::check(codex_agent_state_boolean_value(
                    context->raw, snapshot, &value));
                return value != 0;
            },
            std::move(callback));
    }

    AsyncOperation<void> simple_operation(ConversationOperation operation) const {
        ensure_valid();
        auto owner = detail::retain_conversation(handle_);
        auto context = owner->context();
        return detail::start_operation<void>(
            context,
            [context, owner, operation](auto callback, void* user_data,
                                         auto** out_operation) {
                return operation(
                    context->raw, owner->get(), callback, user_data, out_operation);
            },
            [owner](const detail::Context&, codex_agent_operation_t*) {});
    }

    void ensure_valid() const {
        if (!handle_) {
            throw Error(Status::closed);
        }
    }

    detail::ConversationHandle handle_;
};

inline Agent Host::agent() const {
    ensure_valid();
    auto host = detail::retain_host(handle_);
    codex_agent_snapshot_t* raw_snapshot = nullptr;
    detail::check(codex_agent_host_state_get(
        host->context_raw(), host->get(), &raw_snapshot));
    detail::Snapshot snapshot(handle_.context(), raw_snapshot);
    codex_agent_agent_t* raw_agent = nullptr;
    detail::check(codex_agent_host_state_agent(
        host->context_raw(), host->get(), snapshot.get(), &raw_agent));
    auto agent = std::make_shared<detail::AgentHandle>(
        handle_.context(), raw_agent);
    return Agent(std::make_shared<detail::AgentOwnership>(
        detail::AgentOwnership{std::move(host), std::move(agent)}));
}

inline Conversations Agent::conversations() const {
    ensure_valid();
    auto owner = detail::retain_agent_ownership(owner_);
    codex_agent_conversations_t* raw = nullptr;
    detail::check(codex_agent_agent_conversations(
        owner->agent->context_raw(), owner->agent->get(), &raw));
    return Conversations(
        owner,
        detail::ConversationsHandle(owner->agent->context(), raw));
}

inline AsyncOperation<Conversation> Conversations::open(
    std::optional<ConversationId> conversation_id,
    ConversationSettings settings) const {
    ensure_valid();
    auto owner = detail::retain_conversations(handle_);
    auto context = owner->context();
    return detail::start_operation<Conversation>(
        context,
        [context, owner, conversation_id = std::move(conversation_id),
         settings = std::move(settings)](
            auto callback, void* user_data, auto** out_operation) {
            const std::string empty;
            const auto id = detail::string_view(
                conversation_id ? conversation_id->value : empty);
            const auto service_tier = detail::string_view(
                settings.service_tier ? *settings.service_tier : empty);
            const codex_agent_conversation_open_options_t raw_options{
                sizeof(codex_agent_conversation_open_options_t),
                conversation_id ? 1 : 0,
                id,
                1,
                static_cast<codex_agent_approval_preset_t>(
                    settings.approval_preset),
                settings.service_tier ? 1 : 0,
                service_tier,
            };
            return codex_agent_conversations_open(
                context->raw, owner->get(), &raw_options, callback, user_data,
                out_operation);
        },
        [owner](const detail::Context& context, codex_agent_operation_t* operation) {
            codex_agent_conversation_t* raw = nullptr;
            detail::check(codex_agent_operation_conversation(
                context->raw, owner->get(), operation, &raw));
            return Conversation(detail::ConversationHandle(context, raw));
        });
}

inline AsyncOperation<std::vector<ConversationSummary>> Conversations::list() const {
    ensure_valid();
    auto owner = detail::retain_conversations(handle_);
    auto context = owner->context();
    return detail::start_operation<std::vector<ConversationSummary>>(
        context,
        [context, owner](auto callback, void* user_data, auto** out_operation) {
            return codex_agent_conversations_list(
                context->raw, owner->get(), callback, user_data, out_operation);
        },
        [](const detail::Context& context, codex_agent_operation_t* operation) {
            std::size_t count = 0;
            detail::check(codex_agent_operation_conversation_summaries_count(
                context->raw, operation, &count));
            std::vector<ConversationSummary> summaries;
            summaries.reserve(count);
            for (std::size_t index = 0; index < count; ++index) {
                codex_agent_conversation_summary_t* raw_summary = nullptr;
                detail::check(codex_agent_operation_conversation_summary_at(
                    context->raw, operation, index, &raw_summary));
                detail::ConversationSummaryHandle summary(
                    context, raw_summary);
                summaries.push_back(detail::read_conversation_summary(
                    context, summary.get()));
            }
            return summaries;
        });
}

inline AsyncOperation<ConversationValue> Conversations::read(
    ConversationId conversation_id) const {
    ensure_valid();
    auto owner = detail::retain_conversations(handle_);
    auto context = owner->context();
    auto id = std::make_shared<detail::ConversationIdHandle>(
        detail::make_conversation_id(context, conversation_id));
    return detail::start_operation<ConversationValue>(
        context,
        [context, owner, id](
            auto callback, void* user_data, auto** out_operation) {
            return codex_agent_conversations_read(
                context->raw, owner->get(), id->get(), callback, user_data,
                out_operation);
        },
        [owner, id](const detail::Context& context,
                    codex_agent_operation_t* operation) {
            codex_agent_conversation_value_t* raw = nullptr;
            detail::check(codex_agent_operation_conversation_value(
                context->raw, operation, &raw));
            detail::ConversationValueHandle value(context, raw);
            return detail::read_conversation_value(context, value.get());
        });
}

inline AsyncOperation<void> Conversations::rename(
    ConversationId conversation_id, std::string title) const {
    ensure_valid();
    auto owner = detail::retain_conversations(handle_);
    auto context = owner->context();
    auto id = std::make_shared<detail::ConversationIdHandle>(
        detail::make_conversation_id(context, conversation_id));
    return detail::start_operation<void>(
        context,
        [context, owner, id, title = std::move(title)](
            auto callback, void* user_data, auto** out_operation) {
            const auto value = detail::string_view(title);
            return codex_agent_conversations_rename(
                context->raw, owner->get(), id->get(), &value, callback,
                user_data, out_operation);
        },
        [owner, id](const detail::Context&, codex_agent_operation_t*) {});
}

inline AsyncOperation<void> Conversations::remove(
    ConversationId conversation_id) const {
    ensure_valid();
    auto owner = detail::retain_conversations(handle_);
    auto context = owner->context();
    auto id = std::make_shared<detail::ConversationIdHandle>(
        detail::make_conversation_id(context, conversation_id));
    return detail::start_operation<void>(
        context,
        [context, owner, id](
            auto callback, void* user_data, auto** out_operation) {
            return codex_agent_conversations_delete(
                context->raw, owner->get(), id->get(), callback, user_data,
                out_operation);
        },
        [owner, id](const detail::Context&, codex_agent_operation_t*) {});
}

inline std::optional<Conversation> Conversations::active() const {
    ensure_valid();
    codex_agent_snapshot_t* raw_snapshot = nullptr;
    detail::check(codex_agent_conversations_active_get(
        handle_.context_raw(), handle_.get(), &raw_snapshot));
    detail::Snapshot snapshot(handle_.context(), raw_snapshot);
    codex_agent_conversation_t* raw = nullptr;
    const auto status = codex_agent_active_conversation(
        handle_.context_raw(), handle_.get(), snapshot.get(), &raw);
    if (status == CODEX_AGENT_STATUS_NOT_READY) return std::nullopt;
    detail::check(status);
    return Conversation(detail::ConversationHandle(handle_.context(), raw));
}

inline StateSubscription<std::optional<Conversation>>
Conversations::subscribe_active(
    std::function<void(StateEvent<std::optional<Conversation>>)> callback)
    const {
    ensure_valid();
    auto owner = detail::retain_conversations(handle_);
    using Value = std::optional<Conversation>;
    using Parser = std::function<Value(
        codex_agent_context_t*, codex_agent_snapshot_t*)>;
    Parser parser = [context = handle_.context(), owner](
                        codex_agent_context_t*,
                        codex_agent_snapshot_t* snapshot) -> Value {
        codex_agent_conversation_t* raw = nullptr;
        const auto status = codex_agent_active_conversation(
            context->raw, owner->get(), snapshot, &raw);
        if (status == CODEX_AGENT_STATUS_NOT_READY) return std::nullopt;
        detail::check(status);
        return Conversation(detail::ConversationHandle(context, raw));
    };
    using State = detail::SubscriptionState<Value, Parser>;
    auto state = std::make_shared<State>(
        handle_.context(), owner, std::move(parser), std::move(callback));
    return detail_subscribe<Value>(
        state,
        [owner](auto callback_fn, void* user_data,
                auto** out_subscription) {
            return codex_agent_conversations_active_subscribe(
                owner->context_raw(), owner->get(), callback_fn, user_data,
                out_subscription);
        });
}

namespace detail {

}  // namespace detail

static_assert(!std::is_copy_constructible_v<Host>);
static_assert(!std::is_copy_constructible_v<Agent>);
static_assert(!std::is_copy_constructible_v<Conversations>);
static_assert(!std::is_copy_constructible_v<Conversation>);
static_assert(!std::is_copy_constructible_v<StateSubscription<HostState>>);

}  // namespace codex_agent

#include <codex_agent/leaf_services.hpp>
#include <codex_agent/native_unmap.hpp>
