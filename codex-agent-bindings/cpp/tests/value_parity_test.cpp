#include <codex_agent/codex_agent.hpp>

#include <algorithm>
#include <array>
#include <cctype>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <vector>

#define CODEX_AGENT_CPP_C_HEADER_REFERENCE(symbol)                            \
    static_assert(std::is_pointer_v<decltype(&symbol)>);
#define CODEX_AGENT_CPP_C_HEADER_CONSTANT(symbol)                             \
    static_assert(std::is_integral_v<decltype(symbol)>);
#define CODEX_AGENT_CPP_C_HEADER_TYPE(symbol)                                 \
    static_assert(std::is_same_v<symbol, symbol>);
#define CODEX_AGENT_CPP_C_HEADER_DECLARATION(type, member)                    \
    struct CHeaderDeclarationEvidence { type member; };
#include "c_header_value_references.inc"
#undef CODEX_AGENT_CPP_C_HEADER_REFERENCE
#undef CODEX_AGENT_CPP_C_HEADER_CONSTANT
#undef CODEX_AGENT_CPP_C_HEADER_TYPE
#undef CODEX_AGENT_CPP_C_HEADER_DECLARATION

#define CONVERSATION_NATIVE_BOUNDARY(capability, function)                  \
    static_assert(std::is_pointer_v<decltype(&function)>);
#include "conversation_native_boundaries.inc"
#undef CONVERSATION_NATIVE_BOUNDARY

#define AGENT_NATIVE_BOUNDARY(capability, function)                       \
    static_assert(std::is_pointer_v<decltype(&function)>);
#include "agent_native_boundaries.inc"
#undef AGENT_NATIVE_BOUNDARY

#define HOST_NATIVE_BOUNDARY(capability, function)                         \
    static_assert(std::is_pointer_v<decltype(&function)>);
#define HOST_NATIVE_TYPE(capability, type)                                 \
    static_assert(std::is_same_v<type, type>);
#include "host_native_boundaries.inc"
#undef HOST_NATIVE_TYPE
#undef HOST_NATIVE_BOUNDARY
#define HOST_NATIVE_CONSTANT(capability, constant)                         \
    static_assert(std::is_integral_v<decltype(constant)>);
#include "host_native_constants.inc"
#undef HOST_NATIVE_CONSTANT

#define CODEX_AGENT_CPP_ENUM(index, type, member, constant, symbol)           \
    static_assert(static_cast<std::int32_t>(codex_agent::type::member) ==     \
                  constant);
#include "enum_capabilities.inc"
#undef CODEX_AGENT_CPP_ENUM

static_assert(std::is_same_v<
              decltype(&codex_agent::ElicitationResponse::cancel),
              codex_agent::ElicitationResponse (*)()>);
static_assert(std::is_same_v<
              decltype(&codex_agent::ElicitationResponse::decline),
              codex_agent::ElicitationResponse (*)()>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Elicitation::accepts),
              bool (codex_agent::Elicitation::*)(
                  const codex_agent::ElicitationResponse&) const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Elicitation::accept),
              codex_agent::ElicitationResponse (codex_agent::Elicitation::*)(
                  const std::map<std::string, codex_agent::FormValue>&) const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Elicitation::initial_values),
              std::map<std::string, codex_agent::FormValue>
                  (codex_agent::Elicitation::*)() const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Elicitation::validate),
              codex_agent::ElicitationValidation (codex_agent::Elicitation::*)(
                  const std::map<std::string, codex_agent::FormValue>&) const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::FormField::accepts),
              bool (codex_agent::FormField::*)(
                  const std::optional<codex_agent::FormValue>&) const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::InteractionState::is_resolving),
              bool (codex_agent::InteractionState::*)(
                  const codex_agent::PendingInteraction&) const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::InteractionState::pending_for),
              std::vector<codex_agent::PendingInteractionValue>
                  (codex_agent::InteractionState::*)(
                      const codex_agent::ConversationId&) const>);
static_assert(std::is_same_v<
              decltype(&codex_agent::AuthorizationUrl::chat_gpt),
              codex_agent::AuthorizationUrl (*)(std::string)>);
static_assert(std::is_same_v<
              decltype(&codex_agent::AuthorizationUrl::external),
              codex_agent::AuthorizationUrl (*)(std::string)>);

namespace {

constexpr std::string_view claims_header =
    "capabilityKey\tpublicSymbols\texecutedTests\tcompilerEvidenceIds\tsharedScenarios";

struct Claim {
    std::string capability_key;
    std::vector<std::string> public_symbols;
    std::vector<std::string> executed_tests;
    std::vector<std::string> compiler_evidence_ids;
    std::vector<std::string> shared_scenarios;
};

struct EnumEvidence {
    std::size_t index;
    std::string_view public_symbol;
    std::int32_t public_value;
    std::int32_t c_value;
};

constexpr std::array<EnumEvidence, 110> enum_evidence{{
#define CODEX_AGENT_CPP_ENUM(index, type, member, constant, symbol)           \
    EnumEvidence{index, symbol,                                               \
                 static_cast<std::int32_t>(codex_agent::type::member),        \
                 constant},
#include "enum_capabilities.inc"
#undef CODEX_AGENT_CPP_ENUM
}};

constexpr std::array<std::string_view, 739> compiled_c_header_references{{
#define CODEX_AGENT_CPP_C_HEADER_REFERENCE(symbol) #symbol,
#define CODEX_AGENT_CPP_C_HEADER_CONSTANT(symbol) #symbol,
#define CODEX_AGENT_CPP_C_HEADER_TYPE(symbol) #symbol,
#define CODEX_AGENT_CPP_C_HEADER_DECLARATION(type, member) #type " " #member ";",
#include "c_header_value_references.inc"
#undef CODEX_AGENT_CPP_C_HEADER_REFERENCE
#undef CODEX_AGENT_CPP_C_HEADER_CONSTANT
#undef CODEX_AGENT_CPP_C_HEADER_TYPE
#undef CODEX_AGENT_CPP_C_HEADER_DECLARATION
#define CONVERSATION_NATIVE_BOUNDARY(capability, function) #function,
#include "conversation_native_boundaries.inc"
#undef CONVERSATION_NATIVE_BOUNDARY
#define AGENT_NATIVE_BOUNDARY(capability, function) #function,
#include "agent_native_boundaries.inc"
#undef AGENT_NATIVE_BOUNDARY
#define HOST_NATIVE_BOUNDARY(capability, function) #function,
#define HOST_NATIVE_TYPE(capability, type) #type,
#include "host_native_boundaries.inc"
#undef HOST_NATIVE_TYPE
#undef HOST_NATIVE_BOUNDARY
#define HOST_NATIVE_CONSTANT(capability, constant) #constant,
#include "host_native_constants.inc"
#undef HOST_NATIVE_CONSTANT
}};

[[noreturn]] void fail(std::string message) {
    throw std::runtime_error(std::move(message));
}

void require(bool condition, std::string message) {
    if (!condition) fail(std::move(message));
}

template <typename Action>
void require_rejected(Action&& action, std::string_view label) {
    try {
        action();
    } catch (const std::exception&) {
        return;
    }
    fail(std::string(label) + " was accepted");
}

std::string read_file(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    require(input.good(), "missing evidence input: " + path.string());
    return {std::istreambuf_iterator<char>(input),
            std::istreambuf_iterator<char>()};
}

std::vector<std::string> split(std::string_view value, char delimiter) {
    std::vector<std::string> result;
    std::size_t start = 0;
    for (;;) {
        const auto end = value.find(delimiter, start);
        result.emplace_back(value.substr(start, end - start));
        if (end == std::string_view::npos) return result;
        start = end + 1;
    }
}

std::string padded_index(std::size_t index);

const std::map<std::string, std::string>& expected_leaf_scenarios() {
    static const std::map<std::string, std::string> result{
#define LEAF_SCENARIO(capability, scenario) {capability, scenario},
#include "leaf_scenarios.inc"
#undef LEAF_SCENARIO
    };
    require(result.size() == 42,
            "leaf scenario inventory must contain exactly 42 capabilities");
    return result;
}

const std::map<std::string, std::vector<std::string>>&
expected_leaf_native_references() {
    static const auto result = [] {
        std::map<std::string, std::vector<std::string>> values;
        std::size_t rows = 0;
#define LEAF_NATIVE_BOUNDARY(capability, function)                          \
        values[capability].push_back(#function);                            \
        ++rows;
#include "leaf_native_boundaries.inc"
#undef LEAF_NATIVE_BOUNDARY
        require(rows == 112,
                "leaf native connection inventory must contain 112 rows");
        require(values.size() == 42,
                "leaf native connection inventory must contain 42 capabilities");
        for (auto& [capability, references] : values) {
            (void)capability;
            std::sort(references.begin(), references.end());
            require(std::adjacent_find(
                        references.begin(), references.end()) ==
                        references.end(),
                    "leaf native connection inventory contains a duplicate");
        }
        return values;
    }();
    return result;
}

const std::map<std::string, std::string>& expected_conversation_scenarios() {
    static const std::map<std::string, std::string> result{
#define CONVERSATION_SCENARIO(capability, scenario) {capability, scenario},
#include "conversation_scenarios.inc"
#undef CONVERSATION_SCENARIO
    };
    require(result.size() == 20,
            "conversation scenario inventory must contain exactly 20 capabilities");
    return result;
}

const std::map<std::string, std::vector<std::string>>&
expected_conversation_native_references() {
    static const auto result = [] {
        std::map<std::string, std::vector<std::string>> values;
        std::size_t rows = 0;
#define CONVERSATION_NATIVE_BOUNDARY(capability, function)                  \
        values[capability].push_back(#function);                            \
        ++rows;
#include "conversation_native_boundaries.inc"
#undef CONVERSATION_NATIVE_BOUNDARY
        require(rows == 49,
                "conversation native connection inventory must contain 49 rows");
        require(values.size() == 20,
                "conversation native connection inventory must contain 20 capabilities");
        for (auto& [capability, references] : values) {
            (void)capability;
            std::sort(references.begin(), references.end());
            require(std::adjacent_find(
                        references.begin(), references.end()) ==
                        references.end(),
                    "conversation native connection inventory contains a duplicate");
        }
        return values;
    }();
    return result;
}

const std::map<std::string, std::string>& expected_agent_scenarios() {
    static const std::map<std::string, std::string> result{
#define AGENT_SCENARIO(capability, scenario) {capability, scenario},
#include "agent_scenarios.inc"
#undef AGENT_SCENARIO
    };
    require(result.size() == 11,
            "agent scenario inventory must contain exactly 11 capabilities");
    return result;
}

const std::map<std::string, std::vector<std::string>>&
expected_agent_native_references() {
    static const auto result = [] {
        std::map<std::string, std::vector<std::string>> values;
        std::size_t rows = 0;
#define AGENT_NATIVE_BOUNDARY(capability, function)                        \
        values[capability].push_back(#function);                           \
        ++rows;
#include "agent_native_boundaries.inc"
#undef AGENT_NATIVE_BOUNDARY
        require(rows == 11 && values.size() == 11,
                "agent native inventory must contain exactly 11 capabilities");
        return values;
    }();
    return result;
}

const std::map<std::string, std::string>& expected_host_scenarios() {
    static const std::map<std::string, std::string> result{
#define HOST_SCENARIO(capability, scenario) {capability, scenario},
#include "host_scenarios.inc"
#undef HOST_SCENARIO
    };
    require(result.size() == 7,
            "Host scenario inventory must contain exactly 7 capabilities");
    return result;
}

const std::map<std::string, std::vector<std::string>>&
expected_host_native_references() {
    static const auto result = [] {
        std::map<std::string, std::vector<std::string>> values;
        std::size_t rows = 0;
#define HOST_NATIVE_BOUNDARY(capability, function)                         \
        values[capability].push_back(#function);                           \
        ++rows;
#define HOST_NATIVE_TYPE(capability, type)                                 \
        values[capability].push_back(#type);                               \
        ++rows;
#include "host_native_boundaries.inc"
#undef HOST_NATIVE_TYPE
#undef HOST_NATIVE_BOUNDARY
#define HOST_NATIVE_CONSTANT(capability, constant)                         \
        values[capability].push_back(#constant);                           \
        ++rows;
#include "host_native_constants.inc"
#undef HOST_NATIVE_CONSTANT
        require(rows == 12 && values.size() == 7,
                "Host native inventory must contain 12 rows for 7 capabilities");
        for (auto& [capability, references] : values) {
            (void)capability;
            std::sort(references.begin(), references.end());
            require(std::adjacent_find(
                        references.begin(), references.end()) ==
                        references.end(),
                    "Host native inventory contains a duplicate");
        }
        return values;
    }();
    return result;
}

std::set<std::string> parse_leaf_behavior_receipt(
    const std::filesystem::path& path) {
    auto contents = read_file(path);
    require(!contents.empty() && contents.back() == '\n' &&
                contents.find('\r') == std::string::npos,
            "leaf behavior receipt must use canonical LF encoding");
    contents.pop_back();
    const auto lines = split(contents, '\n');
    require(lines.size() == 43 &&
                lines.front() == "executedTestId\tscenarios\tstatus",
            "leaf behavior receipt must contain exactly 42 results");
    std::set<std::string> result;
    for (std::size_t index = 1; index < lines.size(); ++index) {
        const auto columns = split(lines[index], '\t');
        require(columns.size() == 3 && columns[2] == "passed" &&
                    columns[0] == "cpp.leaf:" + padded_index(index - 1) &&
                    columns[1] ==
                        expected_leaf_scenarios().at(columns[0]),
                "leaf behavior receipt is stale or malformed");
        require(result.insert(columns[0]).second,
                "duplicate leaf behavior result");
    }
    return result;
}

std::set<std::string> parse_leaf_real_boundary_receipt(
    const std::filesystem::path& path) {
    auto contents = read_file(path);
    require(!contents.empty() && contents.back() == '\n' &&
                contents.find('\r') == std::string::npos,
            "real SDK leaf boundary receipt must use canonical LF encoding");
    contents.pop_back();
    const auto lines = split(contents, '\n');
    require(lines.size() == 43 &&
                lines.front() == "executedTestId\tboundary\tstatus",
            "real SDK leaf boundary receipt must contain exactly 42 results");
    std::set<std::string> result;
    for (std::size_t index = 1; index < lines.size(); ++index) {
        const auto columns = split(lines[index], '\t');
        require(columns.size() == 3 &&
                    columns[0] == "cpp.leaf:" + padded_index(index - 1) &&
                    columns[1] ==
                        "typed-public-default-invalid+raw-exact-real-sdk-null-boundary" &&
                    columns[2] == "passed",
                "real SDK leaf boundary receipt is stale or malformed");
        require(result.insert(columns[0]).second,
                "duplicate real SDK leaf boundary result");
    }
    return result;
}

std::set<std::string> parse_conversation_behavior_receipt(
    const std::filesystem::path& path) {
    auto contents = read_file(path);
    require(!contents.empty() && contents.back() == '\n' &&
                contents.find('\r') == std::string::npos,
            "conversation behavior receipt must use canonical LF encoding");
    contents.pop_back();
    const auto lines = split(contents, '\n');
    require(lines.size() == 21 &&
                lines.front() == "executedTestId\tscenarios\tstatus",
            "conversation behavior receipt must contain exactly 20 results");
    std::set<std::string> result;
    for (std::size_t index = 1; index < lines.size(); ++index) {
        const auto columns = split(lines[index], '\t');
        require(columns.size() == 3 && columns[2] == "passed" &&
                    columns[0] ==
                        "cpp.conversation:" + padded_index(index - 1) &&
                    columns[1] ==
                        expected_conversation_scenarios().at(columns[0]),
                "conversation behavior receipt is stale or malformed");
        require(result.insert(columns[0]).second,
                "duplicate conversation behavior result");
    }
    return result;
}

std::set<std::string> parse_conversation_real_boundary_receipt(
    const std::filesystem::path& path) {
    auto contents = read_file(path);
    require(!contents.empty() && contents.back() == '\n' &&
                contents.find('\r') == std::string::npos,
            "real SDK conversation receipt must use canonical LF encoding");
    contents.pop_back();
    const auto lines = split(contents, '\n');
    require(lines.size() == 21 &&
                lines.front() == "executedTestId\tboundary\tstatus",
            "real SDK conversation receipt must contain exactly 20 results");
    std::set<std::string> result;
    for (std::size_t index = 1; index < lines.size(); ++index) {
        const auto columns = split(lines[index], '\t');
        require(columns.size() == 3 &&
                    columns[0] ==
                        "cpp.conversation:" + padded_index(index - 1) &&
                    columns[1] ==
                        "typed-production-real-sdk-invalid-owner+raw-exact-null-boundary" &&
                    columns[2] == "passed",
                "real SDK conversation receipt is stale or malformed");
        require(result.insert(columns[0]).second,
                "duplicate real SDK conversation result");
    }
    return result;
}

std::set<std::string> parse_agent_behavior_receipt(
    const std::filesystem::path& path) {
    auto contents = read_file(path);
    require(!contents.empty() && contents.back() == '\n' &&
                contents.find('\r') == std::string::npos,
            "agent behavior receipt must use canonical LF encoding");
    contents.pop_back();
    const auto lines = split(contents, '\n');
    require(lines.size() == 12 &&
                lines.front() == "executedTestId\tscenarios\tstatus",
            "agent behavior receipt must contain exactly 11 results");
    std::set<std::string> result;
    for (std::size_t index = 1; index < lines.size(); ++index) {
        const auto columns = split(lines[index], '\t');
        require(columns.size() == 3 && columns[2] == "passed" &&
                    columns[0] == "cpp.agent:" + padded_index(index - 1) &&
                    columns[1] == expected_agent_scenarios().at(columns[0]),
                "agent behavior receipt is stale or malformed");
        require(result.insert(columns[0]).second,
                "duplicate agent behavior result");
    }
    return result;
}

std::set<std::string> parse_agent_real_boundary_receipt(
    const std::filesystem::path& path) {
    auto contents = read_file(path);
    require(!contents.empty() && contents.back() == '\n' &&
                contents.find('\r') == std::string::npos,
            "real SDK agent receipt must use canonical LF encoding");
    contents.pop_back();
    const auto lines = split(contents, '\n');
    require(lines.size() == 12 &&
                lines.front() == "executedTestId\tboundary\tstatus",
            "real SDK agent receipt must contain exactly 11 results");
    std::set<std::string> result;
    for (std::size_t index = 1; index < lines.size(); ++index) {
        const auto columns = split(lines[index], '\t');
        require(columns.size() == 3 &&
                    columns[0] == "cpp.agent:" + padded_index(index - 1) &&
                    columns[1] ==
                        "typed-production-real-sdk-invalid-agent+raw-exact-null-boundary" &&
                    columns[2] == "passed",
                "real SDK agent receipt is stale or malformed");
        require(result.insert(columns[0]).second,
                "duplicate real SDK agent result");
    }
    return result;
}

std::set<std::string> parse_host_behavior_receipt(
    const std::filesystem::path& path) {
    auto contents = read_file(path);
    require(!contents.empty() && contents.back() == '\n' &&
                contents.find('\r') == std::string::npos,
            "Host behavior receipt must use canonical LF encoding");
    contents.pop_back();
    const auto lines = split(contents, '\n');
    require(lines.size() == 8 &&
                lines.front() == "executedTestId\tscenarios\tstatus",
            "Host behavior receipt must contain exactly 7 results");
    std::set<std::string> result;
    for (std::size_t index = 1; index < lines.size(); ++index) {
        const auto columns = split(lines[index], '\t');
        require(columns.size() == 3 && columns[2] == "passed" &&
                    columns[0] == "cpp.host:" + padded_index(index - 1) &&
                    columns[1] == expected_host_scenarios().at(columns[0]),
                "Host behavior receipt is stale or malformed");
        require(result.insert(columns[0]).second,
                "duplicate Host behavior result");
    }
    return result;
}

std::set<std::string> parse_host_real_boundary_receipt(
    const std::filesystem::path& path) {
    auto contents = read_file(path);
    require(!contents.empty() && contents.back() == '\n' &&
                contents.find('\r') == std::string::npos,
            "real SDK Host receipt must use canonical LF encoding");
    contents.pop_back();
    const auto lines = split(contents, '\n');
    require(lines.size() == 8 &&
                lines.front() == "executedTestId\tboundary\tstatus",
            "real SDK Host receipt must contain exactly 7 results");
    std::set<std::string> result;
    for (std::size_t index = 1; index < lines.size(); ++index) {
        const auto columns = split(lines[index], '\t');
        require(columns.size() == 3 &&
                    columns[0] == "cpp.host:" + padded_index(index - 1) &&
                    columns[1] ==
                        "typed-production-real-sdk-invalid-host+raw-exact-null-boundary" &&
                    columns[2] == "passed",
                "real SDK Host receipt is stale or malformed");
        require(result.insert(columns[0]).second,
                "duplicate real SDK Host result");
    }
    return result;
}

bool exact_record(std::string_view value) {
    return !value.empty() && value.front() != ' ' && value.back() != ' ' &&
           value.find('*') == std::string_view::npos &&
           std::none_of(value.begin(), value.end(), [](unsigned char character) {
               return std::iscntrl(character) != 0;
           });
}

std::vector<std::string> exact_list(
    std::string_view value, std::string_view label) {
    auto result = split(value, ',');
    require(std::all_of(result.begin(), result.end(), [](const auto& item) {
                return exact_record(item);
            }),
            std::string(label) + " contains a malformed record");
    require(std::is_sorted(result.begin(), result.end()) &&
                std::adjacent_find(result.begin(), result.end()) == result.end(),
            std::string(label) + " must be sorted and unique");
    return result;
}

std::vector<Claim> parse_claims(std::string_view contents) {
    require(!contents.empty() && contents.back() == '\n' &&
                contents.find('\r') == std::string_view::npos,
            "claims must use canonical LF encoding");
    contents.remove_suffix(1);
    auto lines = split(contents, '\n');
    require(!lines.empty() && lines.front() == claims_header,
            "invalid claims header");
    std::vector<Claim> result;
    for (std::size_t index = 1; index < lines.size(); ++index) {
        auto columns = split(lines[index], '\t');
        require(columns.size() == 5 &&
                    std::all_of(columns.begin(), columns.end(), exact_record),
                "malformed claims row " + std::to_string(index + 1));
        result.push_back({
            std::move(columns[0]),
            exact_list(columns[1], "publicSymbols"),
            exact_list(columns[2], "executedTests"),
            exact_list(columns[3], "compilerEvidenceIds"),
            exact_list(columns[4], "sharedScenarios"),
        });
    }
    require(!result.empty(), "claims inventory is empty");
    for (std::size_t index = 1; index < result.size(); ++index) {
        require(result[index - 1].capability_key < result[index].capability_key,
                "capability keys must be sorted and unique");
    }
    return result;
}

const std::map<std::string, std::vector<std::string>>&
expected_cpp_shared_scenarios() {
    static const std::map<std::string, std::vector<std::string>> result{
#define CPP_SHARED_SCENARIOS(capability, scenarios)                        \
        {capability, exact_list(scenarios, "shared scenarios")},
#include "shared_scenarios.inc"
#undef CPP_SHARED_SCENARIOS
    };
    require(result.size() == 80,
            "C++ service shared-scenario inventory must contain 80 capabilities");
    return result;
}

const std::map<std::string, std::string>& cpp_types() {
    static const std::map<std::string, std::string> value{
        {"AgentApprovalPreset", "ApprovalPreset"},
        {"AgentAuthenticationState", "AuthenticationState"},
        {"AgentCapability", "Capability"},
        {"AgentConnector", "Connector"},
        {"AgentConversation", "ConversationValue"},
        {"AgentConversationState", "ConversationState"},
        {"AgentConversationSettings", "ConversationSettings"},
        {"AgentConversationSummary", "ConversationSummary"},
        {"AgentElicitation", "Elicitation"},
        {"AgentElicitationResponse", "ElicitationResponse"},
        {"AgentElicitationValidation", "ElicitationValidation"},
        {"AgentElicitationValidationIssue", "ElicitationValidationIssue"},
        {"AgentFormField", "FormField"},
        {"AgentFormOption", "FormOption"},
        {"AgentFormValue.BooleanValue", "FormBooleanValue"},
        {"AgentFormValue.Number", "FormNumberValue"},
        {"AgentFormValue.Text", "FormTextValue"},
        {"AgentFormValue.TextList", "FormTextListValue"},
        {"AgentHook", "Hook"},
        {"AgentHookActivity", "HookActivity"},
        {"AgentHookCatalog", "HookCatalog"},
        {"AgentHookHandler.Agent", "HookHandlerAgent"},
        {"AgentHookHandler.Command", "HookHandlerCommand"},
        {"AgentHookHandler.McpTool", "HookHandlerMcpTool"},
        {"AgentHookHandler.Prompt", "HookHandlerPrompt"},
        {"AgentIntegration", "Integration"},
        {"AgentIntegration.Connector", "ConnectorIntegration"},
        {"AgentIntegration.McpServer", "McpServerIntegration"},
        {"AgentIntegrationAuthorizationState", "IntegrationAuthorizationState"},
        {"AgentInteractionState", "InteractionState"},
        {"AgentInvocation", "Invocation"},
        {"AgentInvocation.Plugin", "PluginInvocation"},
        {"AgentInvocation.Skill", "SkillInvocation"},
        {"AgentMcpEnvironmentVariable", "McpEnvironmentVariable"},
        {"AgentMcpServer", "McpServer"},
        {"AgentMcpServerConfiguration", "McpServerConfiguration"},
        {"AgentMcpOauthConfiguration", "McpOauthConfiguration"},
        {"AgentMcpToolConfiguration", "McpToolConfiguration"},
        {"AgentMcpTransport.Http", "McpHttpTransport"},
        {"AgentMcpTransport.Stdio", "McpStdioTransport"},
        {"AgentModel", "Model"},
        {"AgentMessage", "Message"},
        {"AgentPendingApproval", "PendingApproval"},
        {"AgentPendingElicitation", "PendingElicitation"},
        {"AgentPendingInteraction", "PendingInteraction"},
        {"AgentPlanProgress", "PlanProgress"},
        {"AgentPlanStep", "PlanStep"},
        {"AgentPluginCatalog", "PluginCatalog"},
        {"AgentPluginDetail", "PluginDetail"},
        {"AgentPluginInstallResult", "PluginInstallResult"},
        {"AgentPluginReference", "PluginReference"},
        {"AgentPluginSkill", "PluginSkill"},
        {"AgentPluginSummary", "PluginSummary"},
        {"AgentServiceTier", "ServiceTier"},
        {"AgentSkill", "Skill"},
        {"AgentSkillScope", "SkillScope"},
        {"AgentSkillCatalog", "SkillCatalog"},
        {"AgentSkillChunk", "SkillChunk"},
        {"AgentTurnProgress", "TurnProgress"},
        {"AgentTurnRequest", "TurnRequest"},
        {"CodexAuthenticationMethod.ApiKey", "ApiKeyAuthentication"},
        {"CodexAuthenticationMethod.ChatGptBrowser", "ChatGptBrowserAuthentication"},
        {"CodexAuthenticationMethod.ChatGptDeviceCode", "ChatGptDeviceCodeAuthentication"},
        {"CodexAuthorizationUrl", "AuthorizationUrl"},
        {"CodexClientInfo", "ClientInfo"},
        {"CodexFailure", "Failure"},
        {"CodexHostState.Closed", "HostStateClosed"},
        {"CodexHostState.Failed", "HostStateFailed"},
        {"CodexHostState.New", "HostStateNew"},
        {"CodexHostState.Preparing", "HostStatePreparing"},
        {"CodexHostState.Restoring", "HostStateRestoring"},
        {"CodexHostState.WorkspaceRequired", "HostStateWorkspaceRequired"},
        {"CodexPathWorkspaceSelection", "PathWorkspaceSelection"},
        {"CodexWorkspace", "Workspace"},
        {"CodexWorkspaceResolution.Available", "WorkspaceAvailable"},
        {"CodexWorkspaceResolution.SelectionRequired", "WorkspaceSelectionRequired"},
        {"ConversationId", "ConversationId"},
    };
    return value;
}

std::string owner_name(std::string_view key) {
    constexpr std::string_view prefix = "|owner=";
    const auto start = key.find(prefix);
    require(start != std::string_view::npos, "capability lacks owner");
    const auto end = key.find('|', start + prefix.size());
    const auto slash = key.rfind('/', end);
    require(end != std::string_view::npos && slash != std::string_view::npos,
            "capability owner is malformed");
    return std::string(key.substr(slash + 1, end - slash - 1));
}

std::string property_name(std::string_view key) {
    if (key.find("|kind=constructor|") != std::string_view::npos) {
        return "constructor";
    }
    if (key.find("|kind=object|") != std::string_view::npos) return "object";
    const auto abi = key.find("|abi=");
    const auto end = key.find('|', abi + 5);
    const auto dot = key.rfind('.', end);
    require(abi != std::string_view::npos && end != std::string_view::npos &&
                dot != std::string_view::npos,
            "property ABI is malformed");
    return std::string(key.substr(dot + 1, end - dot - 1));
}

std::string snake_case(std::string_view value) {
    std::string result;
    for (char character : value) {
        if (std::isupper(static_cast<unsigned char>(character)) != 0) {
            if (!result.empty()) result.push_back('_');
            result.push_back(static_cast<char>(std::tolower(
                static_cast<unsigned char>(character))));
        } else {
            result.push_back(character);
        }
    }
    return result;
}

std::string expected_public_symbol(const Claim& claim) {
    const auto owner = owner_name(claim.capability_key);
    if (claim.capability_key.find("|kind=object|") != std::string::npos) {
        static const std::map<std::string, std::string> objects{
            {"AgentHookHandler.Agent", "hook_handler_agent"},
            {"AgentHookHandler.Prompt", "hook_handler_prompt"},
            {"CodexAuthenticationMethod.ChatGptBrowser",
             "chat_gpt_browser_authentication"},
            {"CodexAuthenticationMethod.ChatGptDeviceCode",
             "chat_gpt_device_code_authentication"},
            {"CodexHostState.Closed", "host_state_closed"},
            {"CodexHostState.New", "host_state_new"},
            {"CodexHostState.Restoring", "host_state_restoring"},
        };
        return "codex_agent::" + objects.at(owner);
    }
    auto property = property_name(claim.capability_key);
    if (owner == "AgentApprovalPreset") {
        return "codex_agent::approval_preset_display_name";
    }
    if (owner == "AgentCapability") {
        return "codex_agent::capability_" + snake_case(property);
    }
    if (owner == "AgentSkillScope") {
        return "codex_agent::skill_scope_display_name";
    }
    const auto type = cpp_types().at(owner);
    if (property == "constructor") property = type;
    else if (property == "isRecoverable") property = "recoverable";
    else if (property == "isValid") property = "is_valid";
    else property = snake_case(property);
    return "codex_agent::" + type + "::" + property;
}

bool is_sync_value_function_capability(std::string_view key) {
    if (key.find("|kind=function|") == std::string_view::npos) return false;
    const auto owner = owner_name(key);
    const auto member = property_name(key);
    if (owner == "AgentElicitationResponse.Companion") {
        return member == "cancel" || member == "decline";
    }
    if (owner == "AgentElicitation") {
        return member == "accept" || member == "accepts" ||
               member == "initialValues" || member == "validate";
    }
    if (owner == "AgentFormField") return member == "accepts";
    if (owner == "AgentInteractionState") {
        return member == "isResolving" || member == "pendingFor";
    }
    if (owner == "CodexAuthorizationUrl.Companion") {
        return member == "chatGpt" || member == "external";
    }
    return false;
}

bool is_leaf_service_capability(std::string_view key) {
    static const std::set<std::string> owners{
        "CodexAuthentication", "CodexConnectors", "CodexHooks",
        "CodexIntegrationAuthorization", "CodexInteractions",
        "CodexMcpServers", "CodexModels", "CodexPlugins", "CodexSkills"};
    return owners.contains(owner_name(key));
}

bool is_conversation_capability(std::string_view key) {
    const auto owner = owner_name(key);
    return owner == "CodexConversation" || owner == "CodexConversations";
}

bool is_agent_capability(std::string_view key) {
    return owner_name(key) == "CodexAgent";
}

bool is_host_capability(std::string_view key) {
    if (!key.starts_with("common|") ||
        key.find("kotlinx.coroutines/CoroutineScope") !=
            std::string_view::npos)
        return false;
    const auto owner = owner_name(key);
    return owner == "CodexHost" || owner == "CodexHostState.Ready";
}

const std::vector<std::string>& expected_host_public_symbols() {
    static const std::vector<std::string> values{
        "codex_agent::HostStateReady::HostStateReady",
        "codex_agent::HostStateReady::agent",
        "codex_agent::Host::create",
        "codex_agent::Host::close",
        "codex_agent::Host::select_workspace",
        "codex_agent::Host::start",
        "codex_agent::Host::state",
    };
    return values;
}

const std::vector<std::string>& expected_agent_public_symbols() {
    static const std::vector<std::string> values{
        "codex_agent::Agent::authentication",
        "codex_agent::Agent::connectors",
        "codex_agent::Agent::conversations",
        "codex_agent::Agent::hooks",
        "codex_agent::Agent::integration_authorization",
        "codex_agent::Agent::interactions",
        "codex_agent::Agent::mcp_servers",
        "codex_agent::Agent::models",
        "codex_agent::Agent::plugins",
        "codex_agent::Agent::skills",
        "codex_agent::Agent::workspace",
    };
    return values;
}

const std::vector<std::string>& expected_conversation_public_symbols() {
    static const std::vector<std::string> values{
        "codex_agent::Conversations::remove",
        "codex_agent::Conversations::list",
        "codex_agent::Conversations::open",
        "codex_agent::Conversations::read",
        "codex_agent::Conversations::rename",
        "codex_agent::Conversations::active",
        "codex_agent::Conversation::cancel_turn",
        "codex_agent::Conversation::close",
        "codex_agent::Conversation::reload",
        "codex_agent::Conversation::run_shell_command",
        "codex_agent::Conversation::send(TurnRequest)",
        "codex_agent::Conversation::send(String)",
        "codex_agent::Conversation::active_turn_progress",
        "codex_agent::Conversation::can_cancel_turn",
        "codex_agent::Conversation::can_reload",
        "codex_agent::Conversation::can_run_shell_command",
        "codex_agent::Conversation::can_start_turn",
        "codex_agent::Conversation::current_messages",
        "codex_agent::Conversation::is_turn_active",
        "codex_agent::Conversation::state",
    };
    return values;
}

const std::vector<std::string>& expected_leaf_public_symbols() {
    static const std::vector<std::string> values{
        "codex_agent::Authentication::authenticate",
        "codex_agent::Authentication::cancel",
        "codex_agent::Authentication::sign_out",
        "codex_agent::Authentication::is_authenticated",
        "codex_agent::Authentication::is_authenticating",
        "codex_agent::Authentication::state",
        "codex_agent::Connectors::list",
        "codex_agent::Connectors::is_available",
        "codex_agent::Hooks::install",
        "codex_agent::Hooks::list",
        "codex_agent::Hooks::trust",
        "codex_agent::Hooks::uninstall",
        "codex_agent::Hooks::is_available",
        "codex_agent::IntegrationAuthorization::authorize",
        "codex_agent::IntegrationAuthorization::cancel",
        "codex_agent::IntegrationAuthorization::active",
        "codex_agent::IntegrationAuthorization::is_authorizing",
        "codex_agent::IntegrationAuthorization::state",
        "codex_agent::Interactions::open_url",
        "codex_agent::Interactions::resolve(PendingApproval)",
        "codex_agent::Interactions::resolve(PendingElicitation)",
        "codex_agent::Interactions::approvals",
        "codex_agent::Interactions::elicitations",
        "codex_agent::Interactions::state",
        "codex_agent::McpServers::add",
        "codex_agent::McpServers::list",
        "codex_agent::McpServers::remove",
        "codex_agent::McpServers::is_available",
        "codex_agent::Models::list",
        "codex_agent::Models::resolve_effort",
        "codex_agent::Models::resolve_service_tier",
        "codex_agent::Models::resolve",
        "codex_agent::Plugins::install",
        "codex_agent::Plugins::list",
        "codex_agent::Plugins::read",
        "codex_agent::Plugins::uninstall",
        "codex_agent::Plugins::is_available",
        "codex_agent::Skills::install",
        "codex_agent::Skills::list",
        "codex_agent::Skills::read",
        "codex_agent::Skills::uninstall",
        "codex_agent::Skills::is_available",
    };
    return values;
}

std::string expected_function_public_symbol(const Claim& claim) {
    const auto owner = owner_name(claim.capability_key);
    const auto member = property_name(claim.capability_key);
    if (owner == "AgentElicitationResponse.Companion") {
        return "codex_agent::ElicitationResponse::" + snake_case(member);
    }
    if (owner == "CodexAuthorizationUrl.Companion") {
        return "codex_agent::AuthorizationUrl::" + snake_case(member);
    }
    return "codex_agent::" + cpp_types().at(owner) + "::" +
           snake_case(member);
}

bool is_value_capability(std::string_view key) {
    const auto owner = owner_name(key);
    return cpp_types().contains(owner);
}

bool is_mcp_graph_capability(std::string_view key) {
    const auto owner = owner_name(key);
    return owner == "AgentMcpServer" ||
           owner == "AgentMcpServerConfiguration" ||
           owner == "AgentMcpTransport.Http" ||
           owner == "AgentMcpTransport.Stdio";
}

bool is_residual_value_capability(std::string_view key) {
    static const std::set<std::string> owners{
        "AgentApprovalPreset", "AgentAuthenticationState", "AgentCapability",
        "AgentConversation", "AgentConversationState", "AgentElicitation",
        "AgentElicitationResponse", "AgentFormField",
        "AgentFormValue.BooleanValue", "AgentFormValue.Number",
        "AgentFormValue.Text", "AgentFormValue.TextList", "AgentHook",
        "AgentHookCatalog", "AgentHookHandler.Agent",
        "AgentHookHandler.Command", "AgentHookHandler.McpTool",
        "AgentHookHandler.Prompt", "AgentIntegration",
        "AgentIntegration.Connector", "AgentIntegration.McpServer",
        "AgentIntegrationAuthorizationState", "AgentInteractionState",
        "AgentInvocation", "AgentInvocation.Plugin", "AgentInvocation.Skill",
        "AgentMessage", "AgentPendingApproval", "AgentPendingElicitation",
        "AgentPendingInteraction", "AgentSkillScope", "AgentTurnRequest",
        "CodexAuthenticationMethod.ApiKey",
        "CodexAuthenticationMethod.ChatGptBrowser",
        "CodexAuthenticationMethod.ChatGptDeviceCode", "CodexAuthorizationUrl",
        "CodexHostState.Closed", "CodexHostState.Failed", "CodexHostState.New",
        "CodexHostState.Preparing", "CodexHostState.Restoring",
        "CodexHostState.WorkspaceRequired", "CodexPathWorkspaceSelection",
        "CodexWorkspaceResolution.Available",
        "CodexWorkspaceResolution.SelectionRequired",
    };
    return owners.contains(owner_name(key));
}

std::string padded_index(std::size_t index) {
    std::ostringstream value;
    value << std::setw(3) << std::setfill('0') << index;
    return value.str();
}

std::set<std::string> canonical_value_capabilities(
    const std::filesystem::path& report_path) {
    std::set<std::string> result;
    std::istringstream lines(read_file(report_path));
    std::string line;
    while (std::getline(lines, line)) {
        const auto first_quote = line.find('"');
        const auto last_quote = line.rfind('"');
        if (first_quote == std::string::npos || first_quote == last_quote) continue;
        const auto value = line.substr(first_quote + 1, last_quote - first_quote - 1);
        if (value.find("|owner=") != std::string::npos &&
            value.find("|kind=enum-entry|") == std::string::npos &&
            is_value_capability(value) && !is_mcp_graph_capability(value) &&
            !is_residual_value_capability(value)) {
            result.insert(value);
        }
    }
    require(result.size() == 142,
            "canonical report must contain exactly 142 selected value capabilities");
    return result;
}

std::set<std::string> canonical_mcp_graph_capabilities(
    const std::filesystem::path& report_path) {
    std::set<std::string> result;
    std::istringstream lines(read_file(report_path));
    std::string line;
    while (std::getline(lines, line)) {
        const auto first_quote = line.find('"');
        const auto last_quote = line.rfind('"');
        if (first_quote == std::string::npos || first_quote == last_quote) continue;
        const auto value = line.substr(first_quote + 1, last_quote - first_quote - 1);
        if (value.find("|owner=") != std::string::npos &&
            value.find("|kind=enum-entry|") == std::string::npos &&
            is_mcp_graph_capability(value)) {
            result.insert(value);
        }
    }
    require(result.size() == 38,
            "canonical report must contain exactly 38 MCP graph capabilities");
    return result;
}

std::set<std::string> canonical_residual_value_capabilities(
    const std::filesystem::path& report_path) {
    std::set<std::string> result;
    std::istringstream lines(read_file(report_path));
    std::string line;
    while (std::getline(lines, line)) {
        const auto first_quote = line.find('"');
        const auto last_quote = line.rfind('"');
        if (first_quote == std::string::npos || first_quote == last_quote) continue;
        const auto value = line.substr(first_quote + 1, last_quote - first_quote - 1);
        const auto ordinary_kind = value.find("|kind=constructor|") !=
                                       std::string::npos ||
                                   value.find("|kind=property|") !=
                                       std::string::npos ||
                                   value.find("|kind=object|") !=
                                       std::string::npos;
        if (ordinary_kind && value.find("|owner=") != std::string::npos &&
            is_residual_value_capability(value)) {
            result.insert(value);
        }
    }
    require(result.size() == 175,
            "canonical report must contain exactly 175 residual value capabilities");
    return result;
}

std::set<std::string> canonical_sync_value_function_capabilities(
    const std::filesystem::path& report_path) {
    std::set<std::string> result;
    std::istringstream lines(read_file(report_path));
    std::string line;
    while (std::getline(lines, line)) {
        const auto first_quote = line.find('"');
        const auto last_quote = line.rfind('"');
        if (first_quote == std::string::npos || first_quote == last_quote) continue;
        const auto value = line.substr(first_quote + 1, last_quote - first_quote - 1);
        if (value.find("|owner=") != std::string::npos &&
            is_sync_value_function_capability(value)) {
            result.insert(value);
        }
    }
    require(result.size() == 11,
            "canonical report must contain exactly 11 synchronous value functions");
    return result;
}

std::set<std::string> canonical_leaf_service_capabilities(
    const std::filesystem::path& report_path) {
    std::set<std::string> result;
    std::istringstream lines(read_file(report_path));
    std::string line;
    while (std::getline(lines, line)) {
        const auto first_quote = line.find('"');
        const auto last_quote = line.rfind('"');
        if (first_quote == std::string::npos || first_quote == last_quote) continue;
        const auto value = line.substr(first_quote + 1, last_quote - first_quote - 1);
        if (value.find("|owner=") != std::string::npos &&
            is_leaf_service_capability(value)) {
            result.insert(value);
        }
    }
    require(result.size() == 42,
            "canonical report must contain exactly 42 leaf-service capabilities");
    return result;
}

std::set<std::string> canonical_conversation_capabilities(
    const std::filesystem::path& report_path) {
    std::set<std::string> result;
    std::istringstream lines(read_file(report_path));
    std::string line;
    while (std::getline(lines, line)) {
        const auto first_quote = line.find('"');
        const auto last_quote = line.rfind('"');
        if (first_quote == std::string::npos || first_quote == last_quote)
            continue;
        const auto value =
            line.substr(first_quote + 1, last_quote - first_quote - 1);
        if (value.find("|owner=") != std::string::npos &&
            is_conversation_capability(value)) {
            result.insert(value);
        }
    }
    require(result.size() == 20,
            "canonical report must contain exactly 20 conversation capabilities");
    return result;
}

std::set<std::string> canonical_agent_capabilities(
    const std::filesystem::path& report_path) {
    std::set<std::string> result;
    std::istringstream lines(read_file(report_path));
    std::string line;
    while (std::getline(lines, line)) {
        const auto first_quote = line.find('"');
        const auto last_quote = line.rfind('"');
        if (first_quote == std::string::npos || first_quote == last_quote)
            continue;
        const auto value =
            line.substr(first_quote + 1, last_quote - first_quote - 1);
        if (value.find("|owner=") != std::string::npos &&
            is_agent_capability(value)) {
            result.insert(value);
        }
    }
    require(result.size() == 11,
            "canonical report must contain exactly 11 Agent capabilities");
    return result;
}

std::set<std::string> canonical_host_capabilities(
    const std::filesystem::path& report_path) {
    std::set<std::string> result;
    std::istringstream lines(read_file(report_path));
    std::string line;
    while (std::getline(lines, line)) {
        const auto first_quote = line.find('"');
        const auto last_quote = line.rfind('"');
        if (first_quote == std::string::npos || first_quote == last_quote)
            continue;
        const auto value =
            line.substr(first_quote + 1, last_quote - first_quote - 1);
        if (value.find("|owner=") != std::string::npos &&
            is_host_capability(value)) {
            result.insert(value);
        }
    }
    require(result.size() == 7,
            "canonical report must contain exactly 7 Host capabilities");
    return result;
}

std::vector<std::string> json_string_array(
    std::string_view object, std::string_view field) {
    const auto field_at = object.find("\"" + std::string(field) + "\"");
    require(field_at != std::string_view::npos,
            "bootstrap claim lacks " + std::string(field));
    const auto open = object.find('[', field_at);
    require(open != std::string_view::npos, "bootstrap array is malformed");
    auto close = std::string_view::npos;
    bool in_string = false;
    bool escaped = false;
    for (auto index = open + 1; index < object.size(); ++index) {
        const auto character = object[index];
        if (in_string && character == '\\' && !escaped) {
            escaped = true;
            continue;
        }
        if (character == '"' && !escaped) in_string = !in_string;
        if (character == ']' && !in_string) {
            close = index;
            break;
        }
        escaped = false;
    }
    require(open != std::string_view::npos && close != std::string_view::npos,
            "bootstrap array is malformed");
    std::vector<std::string> result;
    auto cursor = open + 1;
    while (cursor < close) {
        const auto quote = object.find('"', cursor);
        if (quote == std::string_view::npos || quote >= close) break;
        const auto end_quote = object.find('"', quote + 1);
        require(end_quote != std::string_view::npos && end_quote < close,
                "bootstrap string is malformed");
        result.emplace_back(object.substr(quote + 1, end_quote - quote - 1));
        cursor = end_quote + 1;
    }
    require(std::is_sorted(result.begin(), result.end()) &&
                std::adjacent_find(result.begin(), result.end()) == result.end(),
            "bootstrap array must be sorted and unique");
    return result;
}

struct BootstrapClaim {
    std::vector<std::string> header_references;
    std::vector<std::string> native_test_ids;
};

BootstrapClaim bootstrap_claim(
    std::string_view bootstrap, std::string_view capability_key) {
    const auto claims_at = bootstrap.find("\"claims\": [");
    require(claims_at != std::string_view::npos, "bootstrap claims are missing");
    const auto needle = "\"capabilityKey\": \"" + std::string(capability_key) + "\"";
    const auto start = bootstrap.find(needle, claims_at);
    require(start != std::string_view::npos, "stale bootstrap capability reference");
    const auto next = bootstrap.find("\"capabilityKey\":", start + needle.size());
    const auto object = bootstrap.substr(start, next - start);
    return {json_string_array(object, "headerReferences"),
            json_string_array(object, "nativeTestIds")};
}

std::set<std::string> passed_native_tests(std::string_view bootstrap) {
    std::set<std::string> result;
    std::istringstream lines{std::string(bootstrap)};
    std::string line;
    std::optional<std::string> pending;
    while (std::getline(lines, line)) {
        const auto test_at = line.find("\"testId\": \"");
        if (test_at != std::string::npos) {
            const auto start = test_at + std::string_view("\"testId\": \"").size();
            const auto end = line.find('"', start);
            require(end != std::string::npos, "bootstrap test ID is malformed");
            pending = line.substr(start, end - start);
        } else if (pending && line.find("\"status\": \"passed\"") !=
                                  std::string::npos) {
            require(result.insert(*pending).second, "duplicate passed bootstrap test");
            pending.reset();
        }
    }
    require(!result.empty(), "bootstrap has no passed native tests");
    return result;
}

std::vector<std::string> expected_scenarios(const Claim& claim) {
    std::set<std::string> result{"value-conversion"};
    if (claim.capability_key.find('?') != std::string::npos) {
        result.emplace("nullability");
    }
    if (claim.capability_key.find("kotlin.collections/") != std::string::npos) {
        result.emplace("collection-immutability-ordering");
    }
    if (owner_name(claim.capability_key) == "CodexFailure") {
        result.emplace("structured-failure");
    }
    return {result.begin(), result.end()};
}

std::vector<Claim> validate_value_claims(
    const std::vector<Claim>& all_claims,
    const std::set<std::string>& canonical,
    std::string_view bootstrap) {
    std::vector<Claim> values;
    std::copy_if(all_claims.begin(), all_claims.end(), std::back_inserter(values),
                 [](const Claim& claim) {
                     return claim.capability_key.find("|kind=enum-entry|") ==
                                std::string::npos &&
                            is_value_capability(claim.capability_key) &&
                            !is_mcp_graph_capability(claim.capability_key) &&
                            !is_residual_value_capability(claim.capability_key);
                 });
    require(values.size() == 142, "C++ value claim count must be exactly 142");
    std::set<std::string> keys;
    const auto passed = passed_native_tests(bootstrap);
    for (std::size_t index = 0; index < values.size(); ++index) {
        const auto& claim = values[index];
        require(keys.insert(claim.capability_key).second,
                "duplicate selected value capability");
        require(claim.public_symbols ==
                    std::vector<std::string>{expected_public_symbol(claim)},
                "value public symbol is stale");
        require(claim.executed_tests ==
                    std::vector<std::string>{"cpp.value:" + padded_index(index)},
                "value executed test ID is stale");
        const auto reference = bootstrap_claim(bootstrap, claim.capability_key);
        std::vector<std::string> expected;
        for (const auto& header : reference.header_references) {
            expected.push_back("c-header:" + header);
        }
        for (const auto& test : reference.native_test_ids) {
            require(passed.contains(test), "C ABI fixture is not currently passed");
            expected.push_back("cabi-fixture:" + test);
        }
        expected.push_back("cpp-header-value:" + padded_index(index));
        std::sort(expected.begin(), expected.end());
        require(claim.compiler_evidence_ids == expected,
                "value reference evidence is stale");
        require(claim.shared_scenarios == expected_scenarios(claim),
                "value scenario inventory is stale");
    }
    require(keys == canonical, "C++ value claims are stale, missing, or overclaimed");
    return values;
}

std::vector<Claim> validate_mcp_graph_claims(
    const std::vector<Claim>& all_claims,
    const std::set<std::string>& canonical,
    std::string_view bootstrap) {
    std::vector<Claim> values;
    std::copy_if(all_claims.begin(), all_claims.end(), std::back_inserter(values),
                 [](const Claim& claim) {
                     return claim.capability_key.find("|kind=enum-entry|") ==
                                std::string::npos &&
                            is_mcp_graph_capability(claim.capability_key);
                 });
    require(values.size() == 38, "C++ MCP graph claim count must be exactly 38");
    std::set<std::string> keys;
    const auto passed = passed_native_tests(bootstrap);
    for (std::size_t index = 0; index < values.size(); ++index) {
        const auto& claim = values[index];
        require(keys.insert(claim.capability_key).second,
                "duplicate selected MCP graph capability");
        require(claim.public_symbols ==
                    std::vector<std::string>{expected_public_symbol(claim)},
                "MCP graph public symbol is stale");
        require(claim.executed_tests ==
                    std::vector<std::string>{"cpp.mcp:" + padded_index(index)},
                "MCP graph executed test ID is stale");
        const auto reference = bootstrap_claim(bootstrap, claim.capability_key);
        std::vector<std::string> expected;
        for (const auto& header : reference.header_references) {
            expected.push_back("c-header:" + header);
        }
        for (const auto& test : reference.native_test_ids) {
            require(passed.contains(test), "C ABI fixture is not currently passed");
            expected.push_back("cabi-fixture:" + test);
        }
        expected.push_back("cpp-header-mcp:" + padded_index(index));
        std::sort(expected.begin(), expected.end());
        require(claim.compiler_evidence_ids == expected,
                "MCP graph reference evidence is stale");
        require(claim.shared_scenarios == expected_scenarios(claim),
                "MCP graph scenario inventory is stale");
    }
    require(keys == canonical,
            "C++ MCP graph claims are stale, missing, or overclaimed");
    return values;
}

std::vector<Claim> validate_residual_value_claims(
    const std::vector<Claim>& all_claims,
    const std::set<std::string>& canonical,
    std::string_view bootstrap) {
    std::vector<Claim> values;
    std::copy_if(all_claims.begin(), all_claims.end(), std::back_inserter(values),
                 [](const Claim& claim) {
                     return is_residual_value_capability(claim.capability_key) &&
                            claim.capability_key.find("|kind=enum-entry|") ==
                                std::string::npos &&
                            claim.capability_key.find("|kind=function|") ==
                                std::string::npos;
                 });
    require(values.size() == 175,
            "C++ residual value claim count must be exactly 175");
    std::set<std::string> keys;
    const auto passed = passed_native_tests(bootstrap);
    for (std::size_t index = 0; index < values.size(); ++index) {
        const auto& claim = values[index];
        require(keys.insert(claim.capability_key).second,
                "duplicate selected residual value capability");
        require(claim.public_symbols ==
                    std::vector<std::string>{expected_public_symbol(claim)},
                "residual value public symbol is stale");
        require(claim.executed_tests ==
                    std::vector<std::string>{"cpp.residual:" + padded_index(index)},
                "residual value executed test ID is stale");
        const auto reference = bootstrap_claim(bootstrap, claim.capability_key);
        std::vector<std::string> expected;
        for (const auto& header : reference.header_references) {
            expected.push_back("c-header:" + header);
        }
        for (const auto& test : reference.native_test_ids) {
            require(passed.contains(test), "C ABI fixture is not currently passed");
            expected.push_back("cabi-fixture:" + test);
        }
        expected.push_back("cpp-header-residual:" + padded_index(index));
        std::sort(expected.begin(), expected.end());
        require(claim.compiler_evidence_ids == expected,
                "residual value reference evidence is stale");
        require(claim.shared_scenarios == expected_scenarios(claim),
                "residual value scenario inventory is stale");
    }
    require(keys == canonical,
            "C++ residual value claims are stale, missing, or overclaimed");
    return values;
}

std::vector<Claim> validate_sync_value_function_claims(
    const std::vector<Claim>& all_claims,
    const std::set<std::string>& canonical,
    std::string_view bootstrap) {
    std::vector<Claim> functions;
    std::copy_if(all_claims.begin(), all_claims.end(),
                 std::back_inserter(functions), [](const Claim& claim) {
                     return is_sync_value_function_capability(
                         claim.capability_key);
                 });
    require(functions.size() == 11,
            "C++ synchronous value-function claim count must be exactly 11");
    std::set<std::string> keys;
    const auto passed = passed_native_tests(bootstrap);
    for (std::size_t index = 0; index < functions.size(); ++index) {
        const auto& claim = functions[index];
        require(keys.insert(claim.capability_key).second,
                "duplicate synchronous value-function capability");
        require(claim.public_symbols == std::vector<std::string>{
                    expected_function_public_symbol(claim)},
                "synchronous value-function public symbol is stale");
        require(claim.executed_tests == std::vector<std::string>{
                    "cpp.function:" + padded_index(index)},
                "synchronous value-function executed test ID is stale");
        const auto reference = bootstrap_claim(bootstrap, claim.capability_key);
        std::vector<std::string> expected;
        for (const auto& header : reference.header_references) {
            expected.push_back("c-header:" + header);
        }
        for (const auto& test : reference.native_test_ids) {
            require(passed.contains(test),
                    "synchronous value-function C ABI fixture is not passed");
            expected.push_back("cabi-fixture:" + test);
        }
        expected.push_back("cpp-header-function:" + padded_index(index));
        std::sort(expected.begin(), expected.end());
        require(claim.compiler_evidence_ids == expected,
                "synchronous value-function reference evidence is stale");
        require(claim.shared_scenarios == expected_scenarios(claim),
                "synchronous value-function scenarios are stale");
    }
    require(keys == canonical,
            "C++ synchronous value-function claims are stale, missing, or overclaimed");
    return functions;
}

std::vector<Claim> validate_leaf_service_claims(
    const std::vector<Claim>& all_claims,
    const std::set<std::string>& canonical,
    std::string_view bootstrap) {
    std::vector<Claim> leaves;
    std::copy_if(all_claims.begin(), all_claims.end(),
                 std::back_inserter(leaves), [](const Claim& claim) {
                     return is_leaf_service_capability(claim.capability_key);
                 });
    require(leaves.size() == 42,
            "C++ leaf-service claim count must be exactly 42");
    const auto& public_symbols = expected_leaf_public_symbols();
    const auto passed = passed_native_tests(bootstrap);
    std::set<std::string> keys;
    for (std::size_t index = 0; index < leaves.size(); ++index) {
        const auto& claim = leaves[index];
        require(keys.insert(claim.capability_key).second,
                "duplicate C++ leaf-service capability");
        require(claim.public_symbols ==
                    std::vector<std::string>{public_symbols[index]},
                "C++ leaf-service public symbol is stale");
        require(claim.executed_tests == std::vector<std::string>{
                    "cpp.leaf:" + padded_index(index)},
                "C++ leaf-service executed test ID is stale");
        const auto reference = bootstrap_claim(bootstrap, claim.capability_key);
        require(expected_leaf_native_references().at(
                    "cpp.leaf:" + padded_index(index)) ==
                    reference.header_references,
                "C++ public member/native call connection is stale, missing, or overclaimed");
        std::vector<std::string> expected;
        for (const auto& header : reference.header_references) {
            expected.push_back("c-header:" + header);
        }
        for (const auto& test : reference.native_test_ids) {
            require(passed.contains(test),
                    "C++ leaf-service C ABI fixture is not passed");
            expected.push_back("cabi-fixture:" + test);
        }
        expected.push_back("cpp-header-leaf:" + padded_index(index));
        std::sort(expected.begin(), expected.end());
        require(claim.compiler_evidence_ids == expected,
                "C++ leaf-service compiler/reference evidence is stale");
        require(claim.shared_scenarios == expected_cpp_shared_scenarios().at(
                    "cpp.leaf:" + padded_index(index)),
                "C++ leaf-service scenario is stale");
    }
    require(keys == canonical,
            "C++ leaf-service claims are stale, missing, or overclaimed");
    return leaves;
}

std::vector<Claim> validate_conversation_claims(
    const std::vector<Claim>& all_claims,
    const std::set<std::string>& canonical,
    std::string_view bootstrap) {
    std::vector<Claim> conversations;
    std::copy_if(all_claims.begin(), all_claims.end(),
                 std::back_inserter(conversations), [](const Claim& claim) {
                     return is_conversation_capability(claim.capability_key);
                 });
    require(conversations.size() == 20,
            "C++ conversation claim count must be exactly 20");
    const auto& public_symbols = expected_conversation_public_symbols();
    const auto passed = passed_native_tests(bootstrap);
    std::set<std::string> keys;
    for (std::size_t index = 0; index < conversations.size(); ++index) {
        const auto& claim = conversations[index];
        require(keys.insert(claim.capability_key).second,
                "duplicate C++ conversation capability");
        require(claim.public_symbols ==
                    std::vector<std::string>{public_symbols[index]},
                "C++ conversation public symbol is stale");
        const auto id = "cpp.conversation:" + padded_index(index);
        require(claim.executed_tests == std::vector<std::string>{id},
                "C++ conversation executed test ID is stale");
        const auto reference = bootstrap_claim(bootstrap, claim.capability_key);
        require(expected_conversation_native_references().at(id) ==
                    reference.header_references,
                "C++ conversation public/native connection is stale, missing, or overclaimed");
        std::vector<std::string> expected;
        for (const auto& header : reference.header_references)
            expected.push_back("c-header:" + header);
        for (const auto& test : reference.native_test_ids) {
            require(passed.contains(test),
                    "C++ conversation C ABI fixture is not passed");
            expected.push_back("cabi-fixture:" + test);
        }
        expected.push_back("cpp-header-conversation:" + padded_index(index));
        std::sort(expected.begin(), expected.end());
        require(claim.compiler_evidence_ids == expected,
                "C++ conversation compiler/reference evidence is stale");
        require(claim.shared_scenarios == expected_cpp_shared_scenarios().at(id),
                "C++ conversation scenario is stale");
    }
    require(keys == canonical,
            "C++ conversation claims are stale, missing, or overclaimed");
    return conversations;
}

std::vector<Claim> validate_agent_claims(
    const std::vector<Claim>& all_claims,
    const std::set<std::string>& canonical,
    std::string_view bootstrap) {
    std::vector<Claim> agents;
    std::copy_if(all_claims.begin(), all_claims.end(),
                 std::back_inserter(agents), [](const Claim& claim) {
                     return is_agent_capability(claim.capability_key);
                 });
    require(agents.size() == 11,
            "C++ Agent claim count must be exactly 11");
    const auto& public_symbols = expected_agent_public_symbols();
    const auto passed = passed_native_tests(bootstrap);
    std::set<std::string> keys;
    for (std::size_t index = 0; index < agents.size(); ++index) {
        const auto& claim = agents[index];
        require(keys.insert(claim.capability_key).second,
                "duplicate C++ Agent capability");
        require(claim.public_symbols ==
                    std::vector<std::string>{public_symbols[index]},
                "C++ Agent public symbol is stale");
        const auto id = "cpp.agent:" + padded_index(index);
        require(claim.executed_tests == std::vector<std::string>{id},
                "C++ Agent executed test ID is stale");
        const auto reference = bootstrap_claim(bootstrap, claim.capability_key);
        require(expected_agent_native_references().at(id) ==
                    reference.header_references,
                "C++ Agent public/native connection is stale, missing, or overclaimed");
        std::vector<std::string> expected;
        for (const auto& header : reference.header_references)
            expected.push_back("c-header:" + header);
        for (const auto& test : reference.native_test_ids) {
            require(passed.contains(test),
                    "C++ Agent C ABI fixture is not passed");
            expected.push_back("cabi-fixture:" + test);
        }
        expected.push_back("cpp-header-agent:" + padded_index(index));
        std::sort(expected.begin(), expected.end());
        require(claim.compiler_evidence_ids == expected,
                "C++ Agent compiler/reference evidence is stale");
        require(claim.shared_scenarios == expected_cpp_shared_scenarios().at(id),
                "C++ Agent scenario is stale");
    }
    require(keys == canonical,
            "C++ Agent claims are stale, missing, or overclaimed");
    return agents;
}

std::vector<Claim> validate_host_claims(
    const std::vector<Claim>& all_claims,
    const std::set<std::string>& canonical,
    std::string_view bootstrap) {
    std::vector<Claim> hosts;
    std::copy_if(all_claims.begin(), all_claims.end(),
                 std::back_inserter(hosts), [](const Claim& claim) {
                     return is_host_capability(claim.capability_key);
                 });
    require(hosts.size() == 7,
            "C++ Host claim count must be exactly 7");
    const auto& public_symbols = expected_host_public_symbols();
    const auto passed = passed_native_tests(bootstrap);
    std::set<std::string> keys;
    for (std::size_t index = 0; index < hosts.size(); ++index) {
        const auto& claim = hosts[index];
        require(keys.insert(claim.capability_key).second,
                "duplicate C++ Host capability");
        require(claim.public_symbols ==
                    std::vector<std::string>{public_symbols[index]},
                "C++ Host public symbol is stale");
        const auto id = "cpp.host:" + padded_index(index);
        require(claim.executed_tests == std::vector<std::string>{id},
                "C++ Host executed test ID is stale");
        const auto reference = bootstrap_claim(bootstrap, claim.capability_key);
        require(expected_host_native_references().at(id) ==
                    reference.header_references,
                "C++ Host public/native connection is stale, missing, or overclaimed");
        std::vector<std::string> expected;
        for (const auto& header : reference.header_references)
            expected.push_back("c-header:" + header);
        for (const auto& test : reference.native_test_ids) {
            require(passed.contains(test),
                    "C++ Host C ABI fixture is not passed");
            expected.push_back("cabi-fixture:" + test);
        }
        expected.push_back("cpp-header-host:" + padded_index(index));
        std::sort(expected.begin(), expected.end());
        require(claim.compiler_evidence_ids == expected,
                "C++ Host compiler/reference evidence is stale");
        require(claim.shared_scenarios == expected_cpp_shared_scenarios().at(id),
                "C++ Host scenario is stale");
    }
    require(keys == canonical,
            "C++ Host claims are stale, missing, or overclaimed");
    return hosts;
}

class Recorder {
public:
    explicit Recorder(const std::vector<Claim>& claims) {
        for (const auto& claim : claims) {
            const auto key = owner_name(claim.capability_key) + ":" +
                             property_name(claim.capability_key);
            require(by_member_.emplace(key, &claim).second,
                    "duplicate behavior member");
        }
    }

    void pass(std::string_view owner, std::string_view member) {
        const auto key = std::string(owner) + ":" + std::string(member);
        const auto found = by_member_.find(key);
        require(found != by_member_.end(), "behavior references stale capability " + key);
        require(passed_.insert(found->second->executed_tests.front()).second,
                "behavior executed twice for " + key);
    }

    [[nodiscard]] const std::set<std::string>& passed() const noexcept {
        return passed_;
    }

private:
    std::map<std::string, const Claim*> by_member_;
    std::set<std::string> passed_;
};

void exercise_conversation_values(Recorder& record) {
    codex_agent::ConversationId id("conversation-1");
    record.pass("ConversationId", "constructor");
    require(id.value == "conversation-1", "conversation ID conversion failed");
    record.pass("ConversationId", "value");
    require_rejected([] { (void)codex_agent::ConversationId(" \t"); },
                     "blank conversation ID");

    codex_agent::ConversationSettings settings{
        codex_agent::ApprovalPreset::strict, "fast"};
    record.pass("AgentConversationSettings", "constructor");
    require(settings.approval_preset == codex_agent::ApprovalPreset::strict,
            "approval preset conversion failed");
    record.pass("AgentConversationSettings", "approvalPreset");
    require(settings.service_tier == std::optional<std::string>("fast"),
            "service tier optional conversion failed");
    record.pass("AgentConversationSettings", "serviceTier");

    codex_agent::ConversationSummary summary{
        codex_agent::ConversationId("conversation-2"), "Title", 42};
    record.pass("AgentConversationSummary", "constructor");
    require(summary.conversation_id.value == "conversation-2",
            "nested conversation ID conversion failed");
    record.pass("AgentConversationSummary", "conversationId");
    require(summary.title == "Title", "summary title conversion failed");
    record.pass("AgentConversationSummary", "title");
    require(summary.updated_at_epoch_seconds == 42,
            "summary timestamp conversion failed");
    record.pass("AgentConversationSummary", "updatedAtEpochSeconds");
}

void exercise_configuration_values(Recorder& record) {
    codex_agent::FormOption option{"value", "Title", "Description"};
    record.pass("AgentFormOption", "constructor");
    require(option.value == "value", "form option value conversion failed");
    record.pass("AgentFormOption", "value");
    require(option.title == "Title", "form option title conversion failed");
    record.pass("AgentFormOption", "title");
    require(option.description == std::optional<std::string>("Description"),
            "form option optional conversion failed");
    record.pass("AgentFormOption", "description");

}

void exercise_mcp_graph_values(Recorder& record) {
    codex_agent::McpEnvironmentVariable forwarded(
        "REMOTE_TOKEN", codex_agent::McpEnvironmentSource::remote);
    record.pass("AgentMcpEnvironmentVariable", "constructor");
    require(forwarded.name == "REMOTE_TOKEN", "MCP environment name failed");
    record.pass("AgentMcpEnvironmentVariable", "name");
    require(forwarded.source ==
                std::optional(codex_agent::McpEnvironmentSource::remote),
            "MCP environment source failed");
    record.pass("AgentMcpEnvironmentVariable", "source");

    codex_agent::McpOauthConfiguration oauth("client", 49152);
    record.pass("AgentMcpOauthConfiguration", "constructor");
    require(oauth.client_id == std::optional<std::string>("client"),
            "MCP OAuth client ID failed");
    record.pass("AgentMcpOauthConfiguration", "clientId");
    require(oauth.callback_port == std::optional<std::int32_t>(49152),
            "MCP OAuth callback port failed");
    record.pass("AgentMcpOauthConfiguration", "callbackPort");

    codex_agent::McpToolConfiguration tool{codex_agent::McpToolApproval::prompt};
    record.pass("AgentMcpToolConfiguration", "constructor");
    require(tool.approval == std::optional(codex_agent::McpToolApproval::prompt),
            "MCP tool approval failed");
    record.pass("AgentMcpToolConfiguration", "approval");

    std::map<std::string, std::string> headers{{"X-A", "one"}, {"X-B", "two"}};
    std::map<std::string, std::string> environment_headers{
        {"Authorization", "AUTH_HEADER"}};
    codex_agent::McpHttpTransport http{
        "https://example.com/mcp", "TOKEN_ENV", headers, environment_headers,
        "/usr/bin/headers-helper"};
    headers["X-A"] = "mutated";
    environment_headers["Authorization"] = "mutated";
    record.pass("AgentMcpTransport.Http", "constructor");
    require(http.url == "https://example.com/mcp", "MCP HTTP URL failed");
    record.pass("AgentMcpTransport.Http", "url");
    require(http.bearer_token_environment_variable ==
                std::optional<std::string>("TOKEN_ENV"),
            "MCP HTTP bearer environment failed");
    record.pass("AgentMcpTransport.Http", "bearerTokenEnvironmentVariable");
    require(http.headers && http.headers->at("X-A") == "one" &&
                http.headers->at("X-B") == "two",
            "MCP HTTP headers were not copied");
    record.pass("AgentMcpTransport.Http", "headers");
    require(http.environment_headers &&
                http.environment_headers->at("Authorization") == "AUTH_HEADER",
            "MCP HTTP environment headers were not copied");
    record.pass("AgentMcpTransport.Http", "environmentHeaders");
    require(http.headers_helper ==
                std::optional<std::string>("/usr/bin/headers-helper"),
            "MCP HTTP headers helper failed");
    record.pass("AgentMcpTransport.Http", "headersHelper");

    std::vector<std::string> arguments{"server.js", "--flag", "--flag"};
    std::map<std::string, std::string> environment{{"A", "1"}, {"B", "2"}};
    std::vector<codex_agent::McpEnvironmentVariable> forwarded_environment{
        forwarded};
    codex_agent::McpStdioTransport stdio{
        "node", arguments, "/workspace", environment, forwarded_environment};
    arguments.front() = "mutated";
    environment["A"] = "mutated";
    forwarded_environment.front().name = "mutated";
    record.pass("AgentMcpTransport.Stdio", "constructor");
    require(stdio.command == "node", "MCP stdio command failed");
    record.pass("AgentMcpTransport.Stdio", "command");
    require(stdio.arguments ==
                std::vector<std::string>({"server.js", "--flag", "--flag"}),
            "MCP stdio arguments did not preserve ordered copies");
    record.pass("AgentMcpTransport.Stdio", "arguments");
    require(stdio.working_directory == std::optional<std::string>("/workspace"),
            "MCP stdio working directory failed");
    record.pass("AgentMcpTransport.Stdio", "workingDirectory");
    require(stdio.environment && stdio.environment->at("A") == "1" &&
                stdio.environment->at("B") == "2",
            "MCP stdio environment was not copied");
    record.pass("AgentMcpTransport.Stdio", "environment");
    require(stdio.forwarded_environment.size() == 1 &&
                stdio.forwarded_environment.front().name == "REMOTE_TOKEN",
            "MCP stdio forwarded environment was not deeply copied");
    record.pass("AgentMcpTransport.Stdio", "forwardedEnvironment");

    std::vector<codex_agent::McpToolExposureSurface> omitted{
        codex_agent::McpToolExposureSurface::code_mode,
        codex_agent::McpToolExposureSurface::direct};
    std::vector<std::string> enabled{"one", "one"};
    std::vector<std::string> disabled{};
    std::vector<std::string> scopes{"scope-a", "scope-a"};
    std::map<std::string, codex_agent::McpToolConfiguration> tools{{"tool", tool}};
    codex_agent::McpServerConfiguration configuration{
        "server_1", http, codex_agent::McpAuthentication::oauth, "local", true,
        false, true, omitted, 1.5, 2.5, codex_agent::McpToolApproval::writes,
        enabled, disabled, scopes, oauth, "", tools};
    omitted.front() = codex_agent::McpToolExposureSurface::deferred;
    enabled.front() = "mutated";
    scopes.front() = "mutated";
    tools.at("tool").approval = std::nullopt;
    record.pass("AgentMcpServerConfiguration", "constructor");
    require(configuration.name == "server_1", "MCP configuration name failed");
    record.pass("AgentMcpServerConfiguration", "name");
    require(std::holds_alternative<codex_agent::McpHttpTransport>(
                configuration.transport),
            "MCP configuration transport tag failed");
    record.pass("AgentMcpServerConfiguration", "transport");
    require(configuration.authentication ==
                std::optional(codex_agent::McpAuthentication::oauth),
            "MCP configuration authentication failed");
    record.pass("AgentMcpServerConfiguration", "authentication");
    require(configuration.environment_id == "local",
            "MCP configuration environment failed");
    record.pass("AgentMcpServerConfiguration", "environmentId");
    require(configuration.is_enabled, "MCP configuration enabled failed");
    record.pass("AgentMcpServerConfiguration", "isEnabled");
    require(!configuration.is_required, "MCP configuration required failed");
    record.pass("AgentMcpServerConfiguration", "isRequired");
    require(configuration.supports_parallel_tool_calls,
            "MCP parallel tools flag failed");
    record.pass("AgentMcpServerConfiguration", "supportsParallelToolCalls");
    require(configuration.omit_tools_from &&
                configuration.omit_tools_from->front() ==
                    codex_agent::McpToolExposureSurface::code_mode,
            "MCP omitted surfaces were not copied");
    record.pass("AgentMcpServerConfiguration", "omitToolsFrom");
    require(configuration.startup_timeout_seconds == std::optional(1.5),
            "MCP startup timeout failed");
    record.pass("AgentMcpServerConfiguration", "startupTimeoutSeconds");
    require(configuration.tool_timeout_seconds == std::optional(2.5),
            "MCP tool timeout failed");
    record.pass("AgentMcpServerConfiguration", "toolTimeoutSeconds");
    require(configuration.default_tool_approval ==
                std::optional(codex_agent::McpToolApproval::writes),
            "MCP default approval failed");
    record.pass("AgentMcpServerConfiguration", "defaultToolApproval");
    require(configuration.enabled_tools &&
                *configuration.enabled_tools ==
                    std::vector<std::string>({"one", "one"}),
            "MCP enabled tools did not preserve ordered copies");
    record.pass("AgentMcpServerConfiguration", "enabledTools");
    require(configuration.disabled_tools && configuration.disabled_tools->empty(),
            "MCP present-empty disabled tools failed");
    record.pass("AgentMcpServerConfiguration", "disabledTools");
    require(configuration.scopes &&
                *configuration.scopes ==
                    std::vector<std::string>({"scope-a", "scope-a"}),
            "MCP scopes did not preserve ordered copies");
    record.pass("AgentMcpServerConfiguration", "scopes");
    require(configuration.oauth &&
                configuration.oauth->client_id ==
                    std::optional<std::string>("client"),
            "MCP nested OAuth failed");
    record.pass("AgentMcpServerConfiguration", "oauth");
    require(configuration.oauth_resource == std::optional<std::string>(""),
            "MCP OAuth resource present-empty conversion failed");
    record.pass("AgentMcpServerConfiguration", "oauthResource");
    require(configuration.tools.at("tool").approval ==
                std::optional(codex_agent::McpToolApproval::prompt),
            "MCP tools map was not deeply copied");
    record.pass("AgentMcpServerConfiguration", "tools");

    codex_agent::McpServer server{
        "server_1", "Server One", codex_agent::McpAuthStatus::oauth,
        configuration, codex_agent::ResourceOrigin::plugin, true};
    configuration.name = "mutated";
    record.pass("AgentMcpServer", "constructor");
    require(server.name == "server_1", "MCP server name failed");
    record.pass("AgentMcpServer", "name");
    require(server.display_name == "Server One", "MCP server display name failed");
    record.pass("AgentMcpServer", "displayName");
    require(server.auth_status == codex_agent::McpAuthStatus::oauth,
            "MCP server auth status failed");
    record.pass("AgentMcpServer", "authStatus");
    require(server.configuration && server.configuration->name == "server_1",
            "MCP server did not deeply copy configuration");
    record.pass("AgentMcpServer", "configuration");
    require(server.origin == codex_agent::ResourceOrigin::plugin,
            "MCP server origin failed");
    record.pass("AgentMcpServer", "origin");
    require(server.can_remove, "MCP server removal flag failed");
    record.pass("AgentMcpServer", "canRemove");
    require(server.is_authorized(), "MCP server authorization failed");
    record.pass("AgentMcpServer", "isAuthorized");

    const codex_agent::McpServerConfiguration sparse{
        "server_2", codex_agent::McpHttpTransport("http://127.0.0.1:7777/mcp"),
        std::nullopt, "local", true, false, false,
        std::vector<codex_agent::McpToolExposureSurface>{}, std::nullopt,
        std::nullopt, std::nullopt, std::vector<std::string>{},
        std::vector<std::string>{}, std::vector<std::string>{}};
    require(sparse.omit_tools_from && sparse.omit_tools_from->empty() &&
                sparse.enabled_tools && sparse.enabled_tools->empty() &&
                sparse.disabled_tools && sparse.disabled_tools->empty() &&
                sparse.scopes && sparse.scopes->empty() && !sparse.oauth &&
                !sparse.oauth_resource,
            "MCP null and present-empty values were collapsed");
    require_rejected([] { (void)codex_agent::McpHttpTransport("http://example.com"); },
                     "non-loopback HTTP MCP URL");
    require_rejected([] { (void)codex_agent::McpStdioTransport(" "); },
                     "blank MCP stdio command");
    require_rejected(
        [] {
            (void)codex_agent::McpServerConfiguration{
                "bad name", codex_agent::McpHttpTransport("https://example.com")};
        },
        "invalid MCP server name");
    require_rejected(
        [&] {
            (void)codex_agent::McpServerConfiguration{
                "server", stdio, codex_agent::McpAuthentication::oauth};
        },
        "stdio MCP authentication");
    require_rejected(
        [] { (void)codex_agent::McpOauthConfiguration(std::nullopt, 0); },
        "invalid OAuth callback port");
}

void exercise_residual_metadata_and_authentication(Recorder& record) {
    require(codex_agent::approval_preset_display_name(
                codex_agent::ApprovalPreset::ask_me) == "Ask me",
            "approval preset display name failed");
    record.pass("AgentApprovalPreset", "displayName");
    require(codex_agent::capability_id(codex_agent::Capability::web_search) ==
                "web_search",
            "capability ID failed");
    record.pass("AgentCapability", "id");
    require(codex_agent::capability_display_label(
                codex_agent::Capability::web_search) == "Web search",
            "capability display label failed");
    record.pass("AgentCapability", "displayLabel");
    require(codex_agent::capability_prompt_label(
                codex_agent::Capability::web_search) == "Search the web",
            "capability prompt label failed");
    record.pass("AgentCapability", "promptLabel");
    require(codex_agent::capability_icon(codex_agent::Capability::web_search) ==
                std::optional<std::string_view>("globe"),
            "capability icon failed");
    record.pass("AgentCapability", "icon");
    require(codex_agent::skill_scope_display_name(codex_agent::SkillScope::repo) ==
                "Repository",
            "skill scope display name failed");
    record.pass("AgentSkillScope", "displayName");

    codex_agent::AuthorizationUrl pending{
        "https://example.com/sign-in", codex_agent::AuthorizationPurpose::chat_gpt};
    require(pending.value == "https://example.com/sign-in",
            "authorization URL value failed");
    record.pass("CodexAuthorizationUrl", "value");
    require(pending.purpose == codex_agent::AuthorizationPurpose::chat_gpt,
            "authorization URL purpose failed");
    record.pass("CodexAuthorizationUrl", "purpose");

    codex_agent::AuthenticationState state{
        codex_agent::AuthenticationStatus::authenticating, pending, std::nullopt,
        "ABCD-EFGH", codex_agent::Failure("auth", "Sign in failed", true)};
    record.pass("AgentAuthenticationState", "constructor");
    require(state.status == codex_agent::AuthenticationStatus::authenticating,
            "authentication status failed");
    record.pass("AgentAuthenticationState", "status");
    require(state.pending_sign_in_url &&
                state.pending_sign_in_url->value == "https://example.com/sign-in",
            "pending sign-in URL failed");
    record.pass("AgentAuthenticationState", "pendingSignInUrl");
    require(!state.device_verification_url,
            "device verification nullability failed");
    record.pass("AgentAuthenticationState", "deviceVerificationUrl");
    require(state.device_user_code == std::optional<std::string>("ABCD-EFGH"),
            "device user code failed");
    record.pass("AgentAuthenticationState", "deviceUserCode");
    require(state.failure && state.failure->code == "auth",
            "authentication failure failed");
    record.pass("AgentAuthenticationState", "failure");

    codex_agent::ApiKeyAuthentication api_key("secret");
    record.pass("CodexAuthenticationMethod.ApiKey", "constructor");
    require(api_key.value == "secret", "API key projection failed");
    record.pass("CodexAuthenticationMethod.ApiKey", "value");
    require_rejected([] { (void)codex_agent::ApiKeyAuthentication(" "); },
                     "blank API key");
    (void)codex_agent::chat_gpt_browser_authentication;
    record.pass("CodexAuthenticationMethod.ChatGptBrowser", "object");
    (void)codex_agent::chat_gpt_device_code_authentication;
    record.pass("CodexAuthenticationMethod.ChatGptDeviceCode", "object");
}

void exercise_residual_forms_and_elicitation(Recorder& record) {
    codex_agent::FormBooleanValue boolean_value{true};
    record.pass("AgentFormValue.BooleanValue", "constructor");
    require(boolean_value.value, "boolean form value failed");
    record.pass("AgentFormValue.BooleanValue", "value");
    codex_agent::FormNumberValue number_value{2.5};
    record.pass("AgentFormValue.Number", "constructor");
    require(number_value.value == 2.5, "number form value failed");
    record.pass("AgentFormValue.Number", "value");
    codex_agent::FormTextValue text_value{"default"};
    record.pass("AgentFormValue.Text", "constructor");
    require(text_value.value == "default", "text form value failed");
    record.pass("AgentFormValue.Text", "value");
    std::vector<std::string> selected{"one", "one", "two"};
    codex_agent::FormTextListValue text_list{selected};
    selected.front() = "mutated";
    record.pass("AgentFormValue.TextList", "constructor");
    require(text_list.value ==
                std::vector<std::string>({"one", "one", "two"}),
            "text-list form value did not copy ordered values");
    record.pass("AgentFormValue.TextList", "value");

    std::vector<codex_agent::FormOption> options{
        {"one", "One", "First"}, {"two", "Two", std::nullopt}};
    codex_agent::FormField field{
        "choice", "Choice", "Choose", codex_agent::FormFieldType::multi_select,
        true, true, codex_agent::FormStringFormat::uri,
        codex_agent::FormValue{codex_agent::FormTextValue{"default"}}, 1.0, 9.0,
        2, 20, options, true, 1, 2};
    options.front().title = "mutated";
    record.pass("AgentFormField", "constructor");
    require(field.name == "choice", "form field name failed");
    record.pass("AgentFormField", "name");
    require(field.title == "Choice", "form field title failed");
    record.pass("AgentFormField", "title");
    require(field.description == std::optional<std::string>("Choose"),
            "form field description failed");
    record.pass("AgentFormField", "description");
    require(field.type == codex_agent::FormFieldType::multi_select,
            "form field type failed");
    record.pass("AgentFormField", "type");
    require(field.is_required, "form required flag failed");
    record.pass("AgentFormField", "isRequired");
    require(field.is_secret, "form secret flag failed");
    record.pass("AgentFormField", "isSecret");
    require(field.format == std::optional(codex_agent::FormStringFormat::uri),
            "form format failed");
    record.pass("AgentFormField", "format");
    require(field.default_value &&
                std::get<codex_agent::FormTextValue>(*field.default_value).value ==
                    "default",
            "form default value failed");
    record.pass("AgentFormField", "defaultValue");
    require(field.minimum == std::optional(1.0), "form minimum failed");
    record.pass("AgentFormField", "minimum");
    require(field.maximum == std::optional(9.0), "form maximum failed");
    record.pass("AgentFormField", "maximum");
    require(field.minimum_length == std::optional<std::int64_t>(2),
            "form minimum length failed");
    record.pass("AgentFormField", "minimumLength");
    require(field.maximum_length == std::optional<std::int64_t>(20),
            "form maximum length failed");
    record.pass("AgentFormField", "maximumLength");
    require(field.options.size() == 2 && field.options.front().title == "One",
            "form options were not deeply copied");
    record.pass("AgentFormField", "options");
    require(field.allows_other, "form allows-other flag failed");
    record.pass("AgentFormField", "allowsOther");
    require(field.minimum_selections == std::optional<std::int64_t>(1),
            "form minimum selections failed");
    record.pass("AgentFormField", "minimumSelections");
    require(field.maximum_selections == std::optional<std::int64_t>(2),
            "form maximum selections failed");
    record.pass("AgentFormField", "maximumSelections");

    std::vector<codex_agent::FormField> form{field};
    codex_agent::Elicitation elicitation{
        "request-1", codex_agent::ConversationId("conversation-1"), "server",
        "Please choose", "https://example.com/help", form};
    form.front().name = "mutated";
    record.pass("AgentElicitation", "constructor");
    require(elicitation.request_id == "request-1", "elicitation request ID failed");
    record.pass("AgentElicitation", "requestId");
    require(elicitation.conversation_id.value == "conversation-1",
            "elicitation conversation ID failed");
    record.pass("AgentElicitation", "conversationId");
    require(elicitation.server_name == "server", "elicitation server failed");
    record.pass("AgentElicitation", "serverName");
    require(elicitation.message == "Please choose", "elicitation message failed");
    record.pass("AgentElicitation", "message");
    require(elicitation.url == std::optional<std::string>(
                "https://example.com/help"),
            "elicitation URL failed");
    record.pass("AgentElicitation", "url");
    require(elicitation.form && elicitation.form->front().name == "choice",
            "elicitation form was not deeply copied");
    record.pass("AgentElicitation", "form");

    std::map<std::string, codex_agent::FormValue> content{
        {"choice", codex_agent::FormTextListValue{{"one", "two"}}}};
    codex_agent::ElicitationResponse response{
        codex_agent::ElicitationAction::accept, content};
    content.clear();
    record.pass("AgentElicitationResponse", "constructor");
    require(response.action == codex_agent::ElicitationAction::accept,
            "elicitation response action failed");
    record.pass("AgentElicitationResponse", "action");
    require(response.content.size() == 1 && response.content.contains("choice"),
            "elicitation response content was not copied");
    record.pass("AgentElicitationResponse", "content");
}

void exercise_sync_value_functions(Recorder& record) {
    const auto field = [](
        std::string name, codex_agent::FormFieldType type,
        bool required = false) {
        codex_agent::FormField result{};
        result.name = std::move(name);
        result.title = result.name;
        result.type = type;
        result.is_required = required;
        return result;
    };
    const auto form_value = [](auto value) {
        return std::optional<codex_agent::FormValue>{
            codex_agent::FormValue{std::move(value)}};
    };

    const auto cancelled = codex_agent::ElicitationResponse::cancel();
    require(cancelled.action == codex_agent::ElicitationAction::cancel &&
                cancelled.content.empty(),
            "cancel response factory failed");
    record.pass("AgentElicitationResponse.Companion", "cancel");
    const auto declined = codex_agent::ElicitationResponse::decline();
    require(declined.action == codex_agent::ElicitationAction::decline &&
                declined.content.empty(),
            "decline response factory failed");
    record.pass("AgentElicitationResponse.Companion", "decline");

    auto required = field("required", codex_agent::FormFieldType::string, true);
    require(required.accepts(form_value(codex_agent::FormTextValue{"value"})) &&
                !required.accepts(std::nullopt) &&
                !required.accepts(form_value(codex_agent::FormTextValue{"  "})) &&
                !required.accepts(
                    form_value(codex_agent::FormTextValue{"\xe3\x80\x80"})) &&
                !required.accepts(
                    form_value(codex_agent::FormBooleanValue{true})),
            "required string validation failed");
    auto utf16_length = field("unicode", codex_agent::FormFieldType::string);
    utf16_length.minimum_length = 2;
    utf16_length.maximum_length = 2;
    require(utf16_length.accepts(
                form_value(codex_agent::FormTextValue{"\xf0\x9f\x98\x80"})),
            "UTF-8 form length did not use Kotlin UTF-16 units");
    utf16_length.minimum_length = std::nullopt;
    utf16_length.maximum_length = 1;
    require(!utf16_length.accepts(
                form_value(codex_agent::FormTextValue{"\xf0\x9f\x98\x80"})),
            "UTF-8 form maximum length failed");

    auto number = field("number", codex_agent::FormFieldType::number);
    number.minimum = 1.0;
    number.maximum = 3.0;
    require(number.accepts(form_value(codex_agent::FormNumberValue{1.0})) &&
                number.accepts(form_value(codex_agent::FormNumberValue{2.5})) &&
                number.accepts(form_value(codex_agent::FormNumberValue{3.0})) &&
                !number.accepts(form_value(codex_agent::FormNumberValue{0.9})) &&
                !number.accepts(form_value(codex_agent::FormNumberValue{3.1})) &&
                !number.accepts(form_value(
                    codex_agent::FormNumberValue{std::numeric_limits<double>::quiet_NaN()})),
            "number validation failed");
    auto integer = field("integer", codex_agent::FormFieldType::integer);
    require(integer.accepts(form_value(codex_agent::FormNumberValue{2.0})) &&
                !integer.accepts(form_value(codex_agent::FormNumberValue{1.5})),
            "integer validation failed");
    auto boolean = field("boolean", codex_agent::FormFieldType::boolean);
    require(boolean.accepts(form_value(codex_agent::FormBooleanValue{false})) &&
                !boolean.accepts(form_value(codex_agent::FormTextValue{"false"})),
            "boolean validation failed");

    const std::vector<std::pair<codex_agent::FormStringFormat,
                                std::pair<std::string, std::string>>>
        formats{
            {codex_agent::FormStringFormat::email,
             {"user@example.com", "invalid"}},
            {codex_agent::FormStringFormat::uri,
             {"https://example.com/path", "not a uri"}},
            {codex_agent::FormStringFormat::date,
             {"2024-02-29", "2026-02-31"}},
            {codex_agent::FormStringFormat::date_time,
             {"2026-01-01T12:00:00.123+01:00",
              "2026-01-01T12:00:00+garbage"}},
        };
    for (const auto& [format, values] : formats) {
        auto formatted = field("formatted", codex_agent::FormFieldType::string);
        formatted.format = format;
        require(formatted.accepts(
                    form_value(codex_agent::FormTextValue{values.first})) &&
                    !formatted.accepts(
                        form_value(codex_agent::FormTextValue{values.second})),
                "formatted string validation failed");
    }
    auto whitespace_date = field(
        "date", codex_agent::FormFieldType::string);
    whitespace_date.format = codex_agent::FormStringFormat::date;
    require(!whitespace_date.accepts(
                form_value(codex_agent::FormTextValue{"2024- 1-01"})),
            "embedded date whitespace was accepted");
    const std::vector<codex_agent::FormOption> options{
        {"alpha", "Alpha", std::nullopt},
        {"beta", "Beta", std::nullopt},
    };
    auto single = field("single", codex_agent::FormFieldType::single_select);
    single.options = options;
    require(single.accepts(form_value(codex_agent::FormTextValue{"alpha"})) &&
                !single.accepts(form_value(codex_agent::FormTextValue{"other"})),
            "single selection validation failed");
    single.allows_other = true;
    require(single.accepts(form_value(codex_agent::FormTextValue{"other"})) &&
                !single.accepts(form_value(codex_agent::FormTextValue{" "})),
            "single other-selection validation failed");
    auto multi = field("many", codex_agent::FormFieldType::multi_select, true);
    multi.options = options;
    multi.minimum_selections = 1;
    multi.maximum_selections = 2;
    require(multi.accepts(form_value(
                codex_agent::FormTextListValue{{"alpha", "beta"}})) &&
                !multi.accepts(form_value(codex_agent::FormTextListValue{{}})) &&
                !multi.accepts(form_value(
                    codex_agent::FormTextListValue{{"alpha", "alpha"}})) &&
                !multi.accepts(form_value(
                    codex_agent::FormTextListValue{{"other"}})),
            "multiple selection validation failed");
    multi.allows_other = true;
    require(multi.accepts(form_value(
                codex_agent::FormTextListValue{{"alpha", "other"}})) &&
                !multi.accepts(form_value(
                    codex_agent::FormTextListValue{{"alpha", " "}})),
            "multiple other-selection validation failed");
    record.pass("AgentFormField", "accepts");

    auto first_default = field("choices", codex_agent::FormFieldType::multi_select);
    first_default.default_value =
        codex_agent::FormValue{codex_agent::FormTextListValue{{"first"}}};
    auto no_default = field("omitted", codex_agent::FormFieldType::string);
    auto last_default = first_default;
    last_default.default_value =
        codex_agent::FormValue{codex_agent::FormTextListValue{{"last"}}};
    codex_agent::Elicitation defaults{
        "defaults", codex_agent::ConversationId("conversation"), "server",
        "Defaults", std::nullopt,
        std::vector<codex_agent::FormField>{
            first_default, no_default, last_default}};
    auto initial = defaults.initial_values();
    require(initial.size() == 1 && initial.contains("choices") &&
                std::get<codex_agent::FormTextListValue>(initial.at("choices"))
                        .value == std::vector<std::string>{"last"},
            "elicitation initial values failed");
    std::get<codex_agent::FormTextListValue>(
        *defaults.form->back().default_value).value.push_back("mutated");
    require(std::get<codex_agent::FormTextListValue>(initial.at("choices"))
                    .value == std::vector<std::string>{"last"},
            "elicitation initial values were not deeply copied");
    record.pass("AgentElicitation", "initialValues");

    codex_agent::Elicitation required_form{
        "required", codex_agent::ConversationId("conversation"), "server",
        "Required", std::nullopt,
        std::vector<codex_agent::FormField>{required}};
    std::map<std::string, codex_agent::FormValue> invalid_content{
        {"unknown", codex_agent::FormTextValue{"value"}}};
    const auto invalid_validation = required_form.validate(invalid_content);
    require(invalid_validation.issues.size() == 2 &&
                invalid_validation.issues[0].field_name == "unknown" &&
                invalid_validation.issues[0].reason ==
                    codex_agent::ElicitationValidationReason::unknown_field &&
                invalid_validation.issues[1].field_name == "required" &&
                invalid_validation.issues[1].reason ==
                    codex_agent::ElicitationValidationReason::missing_required,
            "elicitation validation issue ordering failed");
    const std::map<std::string, codex_agent::FormValue> valid_required{
        {"required", codex_agent::FormTextValue{"answer"}}};
    require(required_form.validate(valid_required).is_valid(),
            "valid elicitation content was rejected");
    record.pass("AgentElicitation", "validate");

    codex_agent::Elicitation multi_form{
        "multi", codex_agent::ConversationId("conversation"), "server",
        "Multiple", std::nullopt,
        std::vector<codex_agent::FormField>{multi}};
    std::map<std::string, codex_agent::FormValue> accepted_content{
        {"many", codex_agent::FormTextListValue{{"alpha"}}}};
    const auto accepted = multi_form.accept(accepted_content);
    std::get<codex_agent::FormTextListValue>(accepted_content.at("many"))
        .value.push_back("other");
    require(accepted.action == codex_agent::ElicitationAction::accept &&
                std::get<codex_agent::FormTextListValue>(
                    accepted.content.at("many")).value ==
                    std::vector<std::string>{"alpha"},
            "elicitation acceptance did not snapshot content");
    require_rejected(
        [&] { (void)multi_form.accept({}); }, "invalid elicitation acceptance");
    record.pass("AgentElicitation", "accept");

    require(required_form.accepts(
                {codex_agent::ElicitationAction::accept, valid_required}) &&
                !required_form.accepts(
                    {codex_agent::ElicitationAction::accept, {}}) &&
                required_form.accepts(codex_agent::ElicitationResponse::decline()) &&
                required_form.accepts(codex_agent::ElicitationResponse::cancel()) &&
                !required_form.accepts(
                    {codex_agent::ElicitationAction::decline, valid_required}) &&
                !required_form.accepts(
                    {codex_agent::ElicitationAction::cancel, valid_required}),
            "elicitation response truth table failed");
    record.pass("AgentElicitation", "accepts");

    const codex_agent::ConversationId target("target");
    const codex_agent::ConversationId other("other");
    const codex_agent::PendingApproval approval{
        {"approval", target}, "Title", "Details"};
    const codex_agent::Elicitation pending_value{
        "elicitation", target, "server", "Message", std::nullopt, std::nullopt};
    const codex_agent::PendingElicitation pending_elicitation{
        {"elicitation", target}, pending_value};
    const codex_agent::PendingApproval other_approval{
        {"other", other}, "Other", "Other"};
    codex_agent::InteractionState interactions{
        {approval, other_approval, pending_elicitation, approval},
        {"approval", "elicitation"}, std::nullopt};
    const auto& live_approval =
        std::get<codex_agent::PendingApproval>(interactions.pending.front());
    const auto copied_approval = live_approval;
    require(interactions.is_resolving(live_approval) &&
                !interactions.is_resolving(copied_approval),
            "interaction resolution did not require exact live identity");
    record.pass("AgentInteractionState", "isResolving");
    auto filtered = interactions.pending_for(target);
    require(filtered.size() == 3 &&
                std::holds_alternative<codex_agent::PendingApproval>(filtered[0]) &&
                std::holds_alternative<codex_agent::PendingElicitation>(filtered[1]) &&
                std::holds_alternative<codex_agent::PendingApproval>(filtered[2]) &&
                std::get<codex_agent::PendingApproval>(filtered[0]).request_id ==
                    "approval" &&
                std::get<codex_agent::PendingApproval>(filtered[2]).request_id ==
                    "approval",
            "pending interaction filtering lost order or duplicates");
    std::get<codex_agent::PendingApproval>(filtered[0]).request_id = "mutated";
    require(std::get<codex_agent::PendingApproval>(interactions.pending[0])
                    .request_id == "approval",
            "pending interaction result was not defensively copied");
    record.pass("AgentInteractionState", "pendingFor");

    for (const auto& value : std::vector<std::string>{
             "https://auth.openai.com/authorize?client=codex",
             "https://chatgpt.com/", "https://login.chatgpt.com:443/"}) {
        const auto url = codex_agent::AuthorizationUrl::chat_gpt(value);
        require(url.value == value &&
                    url.purpose == codex_agent::AuthorizationPurpose::chat_gpt,
                "ChatGPT authorization URL projection failed");
    }
    for (const auto& value : std::vector<std::string>{
             "http://auth.openai.com/", "https://openai.com.evil.example/",
             "https://evilopenai.com/", "https://user@openai.com/",
             "https://openai.com:444/", "https://openai.com:/",
             "https://openai.com./"}) {
        require_rejected(
            [&] { (void)codex_agent::AuthorizationUrl::chat_gpt(value); },
            "untrusted ChatGPT authorization URL");
    }
    record.pass("CodexAuthorizationUrl.Companion", "chatGpt");

    for (const auto& value : std::vector<std::string>{
             "https://accounts.example.com/oauth",
             "http://localhost:8787/callback",
             "http://127.0.0.1:8787/callback",
             "http://[::1]:8787/callback"}) {
        const auto url = codex_agent::AuthorizationUrl::external(value);
        require(url.value == value &&
                    url.purpose == codex_agent::AuthorizationPurpose::external,
                "external authorization URL projection failed");
    }
    for (const auto& value : std::vector<std::string>{
             "http://192.168.1.2/login", "ftp://accounts.example.com/login",
             "https://user@accounts.example.com/login",
             "https://accounts.example.com:0/login",
             "https://accounts.example.com:65536/login",
             "https://accounts.example.com:/login",
             "https://accounts.example.com\\@evil.example/login",
             "https://accounts.example.com/space here"}) {
        require_rejected(
            [&] { (void)codex_agent::AuthorizationUrl::external(value); },
            "unsafe external authorization URL");
    }
    record.pass("CodexAuthorizationUrl.Companion", "external");
}

void exercise_residual_hooks(Recorder& record) {
    (void)codex_agent::hook_handler_agent;
    record.pass("AgentHookHandler.Agent", "object");
    (void)codex_agent::hook_handler_prompt;
    record.pass("AgentHookHandler.Prompt", "object");
    codex_agent::HookHandlerCommand command{"echo ok", true};
    record.pass("AgentHookHandler.Command", "constructor");
    require(command.command == "echo ok", "hook command failed");
    record.pass("AgentHookHandler.Command", "command");
    require(command.is_async, "hook async flag failed");
    record.pass("AgentHookHandler.Command", "isAsync");
    codex_agent::HookHandlerMcpTool mcp_tool{"server", "tool"};
    record.pass("AgentHookHandler.McpTool", "constructor");
    require(mcp_tool.server == "server", "hook MCP server failed");
    record.pass("AgentHookHandler.McpTool", "server");
    require(mcp_tool.tool == "tool", "hook MCP tool failed");
    record.pass("AgentHookHandler.McpTool", "tool");

    codex_agent::Hook hook{
        "hook-key", "after-turn", "*.cpp", command, 30,
        codex_agent::HookTrustStatus::trusted, "sha256:current", true, "plugin",
        "/workspace/hooks/hook.json", codex_agent::ResourceOrigin::plugin,
        "plugin-id", false, true, true, "ready"};
    record.pass("AgentHook", "constructor");
    require(hook.key == "hook-key", "hook key failed");
    record.pass("AgentHook", "key");
    require(hook.event_name == "after-turn", "hook event failed");
    record.pass("AgentHook", "eventName");
    require(hook.matcher == std::optional<std::string>("*.cpp"),
            "hook matcher failed");
    record.pass("AgentHook", "matcher");
    require(std::get<codex_agent::HookHandlerCommand>(hook.handler).command ==
                "echo ok",
            "hook handler failed");
    record.pass("AgentHook", "handler");
    require(hook.timeout_seconds == 30, "hook timeout failed");
    record.pass("AgentHook", "timeoutSeconds");
    require(hook.trust_status == codex_agent::HookTrustStatus::trusted,
            "hook trust status failed");
    record.pass("AgentHook", "trustStatus");
    require(hook.current_hash == "sha256:current", "hook hash failed");
    record.pass("AgentHook", "currentHash");
    require(hook.is_enabled, "hook enabled flag failed");
    record.pass("AgentHook", "isEnabled");
    require(hook.source == "plugin", "hook source failed");
    record.pass("AgentHook", "source");
    require(hook.source_path == "/workspace/hooks/hook.json",
            "hook source path failed");
    record.pass("AgentHook", "sourcePath");
    require(hook.origin == codex_agent::ResourceOrigin::plugin,
            "hook origin failed");
    record.pass("AgentHook", "origin");
    require(hook.plugin_id == std::optional<std::string>("plugin-id"),
            "hook plugin ID failed");
    record.pass("AgentHook", "pluginId");
    require(!hook.is_managed, "hook managed flag failed");
    record.pass("AgentHook", "isManaged");
    require(hook.can_trust, "hook can-trust flag failed");
    record.pass("AgentHook", "canTrust");
    require(hook.can_uninstall, "hook uninstall flag failed");
    record.pass("AgentHook", "canUninstall");
    require(hook.status_message == std::optional<std::string>("ready"),
            "hook status message failed");
    record.pass("AgentHook", "statusMessage");

    std::vector<codex_agent::Hook> hooks{hook, hook};
    std::vector<std::string> warnings{"warning", "warning"};
    std::vector<std::string> errors{"error"};
    codex_agent::HookCatalog catalog{hooks, warnings, errors};
    hooks.front().key = "mutated";
    warnings.front() = "mutated";
    errors.front() = "mutated";
    record.pass("AgentHookCatalog", "constructor");
    require(catalog.hooks.size() == 2 && catalog.hooks.front().key == "hook-key",
            "hook catalog hooks were not copied");
    record.pass("AgentHookCatalog", "hooks");
    require(catalog.warnings ==
                std::vector<std::string>({"warning", "warning"}),
            "hook catalog warnings were not copied");
    record.pass("AgentHookCatalog", "warnings");
    require(catalog.errors == std::vector<std::string>({"error"}),
            "hook catalog errors were not copied");
    record.pass("AgentHookCatalog", "errors");
}

void exercise_residual_integrations_and_invocations(Recorder& record) {
    codex_agent::Connector connector{
        "connector", "Connector", "Description", std::nullopt, true, true, {}};
    codex_agent::ConnectorIntegration connector_integration{
        {"connector:connector", "Connector"}, connector};
    record.pass("AgentIntegration.Connector", "constructor");
    require(connector_integration.id == "connector:connector",
            "connector integration ID failed");
    record.pass("AgentIntegration.Connector", "id");
    require(connector_integration.display_name == "Connector",
            "connector integration display name failed");
    record.pass("AgentIntegration.Connector", "displayName");
    require(connector_integration.connector.id == "connector",
            "connector integration payload failed");
    record.pass("AgentIntegration.Connector", "connector");
    require(connector_integration.id == "connector:connector",
            "integration base ID failed");
    record.pass("AgentIntegration", "id");
    require(connector_integration.display_name == "Connector",
            "integration base display name failed");
    record.pass("AgentIntegration", "displayName");

    codex_agent::McpServer server{
        "server", "Server", codex_agent::McpAuthStatus::unknown};
    codex_agent::McpServerIntegration server_integration{
        {"mcp:server", "Server"}, server};
    record.pass("AgentIntegration.McpServer", "constructor");
    require(server_integration.id == "mcp:server", "MCP integration ID failed");
    record.pass("AgentIntegration.McpServer", "id");
    require(server_integration.display_name == "Server",
            "MCP integration display name failed");
    record.pass("AgentIntegration.McpServer", "displayName");
    require(server_integration.server.name == "server",
            "MCP integration payload failed");
    record.pass("AgentIntegration.McpServer", "server");

    codex_agent::IntegrationAuthorizationState authorization{
        codex_agent::IntegrationAuthorizationStatus::awaiting_completion,
        codex_agent::IntegrationValue{connector_integration},
        codex_agent::Failure("authorization", "Authorization failed", true)};
    record.pass("AgentIntegrationAuthorizationState", "constructor");
    require(authorization.status ==
                codex_agent::IntegrationAuthorizationStatus::awaiting_completion,
            "integration authorization status failed");
    record.pass("AgentIntegrationAuthorizationState", "status");
    require(authorization.target &&
                std::get<codex_agent::ConnectorIntegration>(*authorization.target)
                        .connector.id == "connector",
            "integration authorization target failed");
    record.pass("AgentIntegrationAuthorizationState", "target");
    require(authorization.failure && authorization.failure->code == "authorization",
            "integration authorization failure failed");
    record.pass("AgentIntegrationAuthorizationState", "failure");

    codex_agent::PluginInvocation plugin{{"plugin:key", "Plugin"},
                                         "plugin://plugin@marketplace"};
    record.pass("AgentInvocation.Plugin", "constructor");
    require(plugin.key == "plugin:key", "plugin invocation key failed");
    record.pass("AgentInvocation.Plugin", "key");
    require(plugin.name == "Plugin", "plugin invocation name failed");
    record.pass("AgentInvocation.Plugin", "name");
    require(plugin.uri == "plugin://plugin@marketplace",
            "plugin invocation URI failed");
    record.pass("AgentInvocation.Plugin", "uri");
    require(plugin.key == "plugin:key", "invocation base key failed");
    record.pass("AgentInvocation", "key");
    require(plugin.name == "Plugin", "invocation base name failed");
    record.pass("AgentInvocation", "name");

    codex_agent::SkillInvocation skill{{"skill:key", "Skill"},
                                       "/workspace/SKILL.md"};
    record.pass("AgentInvocation.Skill", "constructor");
    require(skill.key == "skill:key", "skill invocation key failed");
    record.pass("AgentInvocation.Skill", "key");
    require(skill.name == "Skill", "skill invocation name failed");
    record.pass("AgentInvocation.Skill", "name");
    require(skill.path == "/workspace/SKILL.md", "skill invocation path failed");
    record.pass("AgentInvocation.Skill", "path");
}

void exercise_residual_messages_and_turn_requests(Recorder& record) {
    std::vector<codex_agent::InvocationValue> invocations{
        codex_agent::PluginInvocation{{"plugin:key", "Plugin"},
                                      "plugin://plugin@marketplace"},
        codex_agent::SkillInvocation{{"skill:key", "Skill"},
                                     "/workspace/SKILL.md"}};
    std::set<codex_agent::Capability> capabilities{
        codex_agent::Capability::web_search};
    codex_agent::Message message{
        "message-1", codex_agent::MessageRole::assistant, "text", "reasoning",
        "plan", "echo ok", 0, invocations, capabilities,
        codex_agent::CollaborationMode::plan, "client-message-1"};
    invocations.clear();
    capabilities.clear();
    record.pass("AgentMessage", "constructor");
    require(message.id == "message-1", "message ID failed");
    record.pass("AgentMessage", "id");
    require(message.role == codex_agent::MessageRole::assistant,
            "message role failed");
    record.pass("AgentMessage", "role");
    require(message.text == "text", "message text failed");
    record.pass("AgentMessage", "text");
    require(message.reasoning == std::optional<std::string>("reasoning"),
            "message reasoning failed");
    record.pass("AgentMessage", "reasoning");
    require(message.plan == std::optional<std::string>("plan"),
            "message plan failed");
    record.pass("AgentMessage", "plan");
    require(message.shell_command == std::optional<std::string>("echo ok"),
            "message shell command failed");
    record.pass("AgentMessage", "shellCommand");
    require(message.exit_code == std::optional<std::int32_t>(0),
            "message exit code failed");
    record.pass("AgentMessage", "exitCode");
    require(message.invocations.size() == 2,
            "message invocations were not copied");
    record.pass("AgentMessage", "invocations");
    require(message.capabilities ==
                std::set<codex_agent::Capability>{
                    codex_agent::Capability::web_search},
            "message capabilities were not copied");
    record.pass("AgentMessage", "capabilities");
    require(message.collaboration_mode == codex_agent::CollaborationMode::plan,
            "message collaboration mode failed");
    record.pass("AgentMessage", "collaborationMode");
    require(message.client_message_id ==
                std::optional<std::string>("client-message-1"),
            "message client ID failed");
    record.pass("AgentMessage", "clientMessageId");

    std::vector<codex_agent::InvocationValue> request_invocations{
        codex_agent::SkillInvocation{{"skill:key", "Skill"},
                                     "/workspace/SKILL.md"}};
    std::set<codex_agent::Capability> request_capabilities{
        codex_agent::Capability::web_search};
    codex_agent::TurnRequest request{
        "prompt", "model", "high", codex_agent::ApprovalPreset::strict,
        "priority", request_capabilities, codex_agent::CollaborationMode::plan,
        request_invocations, "client-message-2"};
    request_invocations.clear();
    request_capabilities.clear();
    record.pass("AgentTurnRequest", "constructor");
    require(request.prompt == "prompt", "turn request prompt failed");
    record.pass("AgentTurnRequest", "prompt");
    require(request.model == std::optional<std::string>("model"),
            "turn request model failed");
    record.pass("AgentTurnRequest", "model");
    require(request.effort == std::optional<std::string>("high"),
            "turn request effort failed");
    record.pass("AgentTurnRequest", "effort");
    require(request.approval_preset == codex_agent::ApprovalPreset::strict,
            "turn request approval failed");
    record.pass("AgentTurnRequest", "approvalPreset");
    require(request.service_tier == std::optional<std::string>("priority"),
            "turn request service tier failed");
    record.pass("AgentTurnRequest", "serviceTier");
    require(request.capabilities ==
                std::set<codex_agent::Capability>{
                    codex_agent::Capability::web_search},
            "turn request capabilities were not copied");
    record.pass("AgentTurnRequest", "capabilities");
    require(request.collaboration_mode == codex_agent::CollaborationMode::plan,
            "turn request collaboration mode failed");
    record.pass("AgentTurnRequest", "collaborationMode");
    require(request.invocations.size() == 1,
            "turn request invocations were not copied");
    record.pass("AgentTurnRequest", "invocations");
    require(request.client_message_id ==
                std::optional<std::string>("client-message-2"),
            "turn request client ID failed");
    record.pass("AgentTurnRequest", "clientMessageId");
}

void exercise_residual_interactions_and_conversation(Recorder& record) {
    codex_agent::PendingApproval approval{
        {"approval-1", codex_agent::ConversationId("conversation-1")},
        "Run command", "echo ok"};
    record.pass("AgentPendingApproval", "constructor");
    require(approval.request_id == "approval-1", "pending approval request ID failed");
    record.pass("AgentPendingApproval", "requestId");
    require(approval.conversation_id.value == "conversation-1",
            "pending approval conversation failed");
    record.pass("AgentPendingApproval", "conversationId");
    require(approval.title == "Run command", "pending approval title failed");
    record.pass("AgentPendingApproval", "title");
    require(approval.details == "echo ok", "pending approval details failed");
    record.pass("AgentPendingApproval", "details");
    require(approval.request_id == "approval-1",
            "pending interaction request ID failed");
    record.pass("AgentPendingInteraction", "requestId");
    require(approval.conversation_id.value == "conversation-1",
            "pending interaction conversation failed");
    record.pass("AgentPendingInteraction", "conversationId");

    codex_agent::Elicitation elicitation{
        "elicitation-1", codex_agent::ConversationId("conversation-1"),
        "server", "Choose", std::nullopt, std::nullopt};
    codex_agent::PendingElicitation pending_elicitation{
        {"elicitation-1", codex_agent::ConversationId("conversation-1")},
        elicitation};
    record.pass("AgentPendingElicitation", "constructor");
    require(pending_elicitation.request_id == "elicitation-1",
            "pending elicitation request ID failed");
    record.pass("AgentPendingElicitation", "requestId");
    require(pending_elicitation.conversation_id.value == "conversation-1",
            "pending elicitation conversation failed");
    record.pass("AgentPendingElicitation", "conversationId");
    require(pending_elicitation.elicitation.server_name == "server",
            "pending elicitation payload failed");
    record.pass("AgentPendingElicitation", "elicitation");

    std::vector<codex_agent::PendingInteractionValue> pending{
        approval, pending_elicitation};
    std::set<std::string> resolving{"approval-1", "elicitation-1"};
    codex_agent::InteractionState interactions{
        pending, resolving, codex_agent::Failure("interaction", "Failed", true)};
    pending.clear();
    resolving.clear();
    record.pass("AgentInteractionState", "constructor");
    require(interactions.pending.size() == 2,
            "interaction pending list was not copied");
    record.pass("AgentInteractionState", "pending");
    require(interactions.resolving_request_ids ==
                std::set<std::string>({"approval-1", "elicitation-1"}),
            "interaction resolving set was not copied");
    record.pass("AgentInteractionState", "resolvingRequestIds");
    require(interactions.failure && interactions.failure->code == "interaction",
            "interaction failure failed");
    record.pass("AgentInteractionState", "failure");

    codex_agent::Message message{
        "message-1", codex_agent::MessageRole::assistant, "hello", std::nullopt,
        std::nullopt, std::nullopt, std::nullopt, {}, {},
        codex_agent::CollaborationMode::default_, std::nullopt};
    std::vector<codex_agent::Message> messages{message, message};
    codex_agent::ConversationSummary summary{
        codex_agent::ConversationId("conversation-1"), "Conversation", 42};
    codex_agent::ConversationValue conversation{summary, messages};
    messages.front().text = "mutated";
    record.pass("AgentConversation", "constructor");
    require(conversation.summary.conversation_id.value == "conversation-1",
            "conversation summary failed");
    record.pass("AgentConversation", "summary");
    require(conversation.messages.size() == 2 &&
                conversation.messages.front().text == "hello",
            "conversation messages were not deeply copied");
    record.pass("AgentConversation", "messages");

    codex_agent::TurnProgress progress{
        "text", "commentary", "reasoning", "plan", std::nullopt, "output", 0,
        std::nullopt, {}, false};
    codex_agent::ConversationState state{
        codex_agent::ConversationStatus::running_turn, std::nullopt,
        codex_agent::ConversationId("conversation-1"), conversation, "model",
        "high", "priority", progress, false, true, true};
    record.pass("AgentConversationState", "constructor");
    require(state.status == codex_agent::ConversationStatus::running_turn,
            "conversation state status failed");
    record.pass("AgentConversationState", "status");
    require(!state.failure, "conversation state failure nullability failed");
    record.pass("AgentConversationState", "failure");
    require(state.conversation_id && state.conversation_id->value == "conversation-1",
            "conversation state ID failed");
    record.pass("AgentConversationState", "conversationId");
    require(state.conversation && state.conversation->summary.title == "Conversation",
            "conversation state value failed");
    record.pass("AgentConversationState", "conversation");
    require(state.model == std::optional<std::string>("model"),
            "conversation state model failed");
    record.pass("AgentConversationState", "model");
    require(state.effort == std::optional<std::string>("high"),
            "conversation state effort failed");
    record.pass("AgentConversationState", "effort");
    require(state.service_tier == std::optional<std::string>("priority"),
            "conversation state service tier failed");
    record.pass("AgentConversationState", "serviceTier");
    require(state.turn_progress.text == "text",
            "conversation state turn progress failed");
    record.pass("AgentConversationState", "turnProgress");
    require(!state.can_start_turn, "conversation can-start flag failed");
    record.pass("AgentConversationState", "canStartTurn");
    require(state.can_cancel_turn, "conversation can-cancel flag failed");
    record.pass("AgentConversationState", "canCancelTurn");
    require(state.can_reload, "conversation can-reload flag failed");
    record.pass("AgentConversationState", "canReload");
}

void exercise_residual_host_and_workspace_values(Recorder& record) {
    (void)codex_agent::host_state_new;
    record.pass("CodexHostState.New", "object");
    (void)codex_agent::host_state_restoring;
    record.pass("CodexHostState.Restoring", "object");
    (void)codex_agent::host_state_closed;
    record.pass("CodexHostState.Closed", "object");

    codex_agent::Workspace workspace{"/workspace", "Workspace"};
    codex_agent::HostStatePreparing preparing{workspace};
    record.pass("CodexHostState.Preparing", "constructor");
    require(preparing.workspace.path == "/workspace",
            "preparing workspace failed");
    record.pass("CodexHostState.Preparing", "workspace");

    codex_agent::WorkspaceSelectionRequired requirement{
        codex_agent::WorkspaceSelectionReason::not_found, "Select a workspace"};
    record.pass("CodexWorkspaceResolution.SelectionRequired", "constructor");
    require(requirement.reason ==
                codex_agent::WorkspaceSelectionReason::not_found,
            "workspace selection reason failed");
    record.pass("CodexWorkspaceResolution.SelectionRequired", "reason");
    require(requirement.message == "Select a workspace",
            "workspace selection message failed");
    record.pass("CodexWorkspaceResolution.SelectionRequired", "message");

    codex_agent::HostStateWorkspaceRequired workspace_required{requirement};
    record.pass("CodexHostState.WorkspaceRequired", "constructor");
    require(workspace_required.requirement.message == "Select a workspace",
            "workspace-required resolution failed");
    record.pass("CodexHostState.WorkspaceRequired", "requirement");

    codex_agent::Failure failure{"prepare", "Preparation failed", true};
    codex_agent::HostStateFailed failed{failure, workspace};
    record.pass("CodexHostState.Failed", "constructor");
    require(failed.failure.code == "prepare", "failed host failure failed");
    record.pass("CodexHostState.Failed", "failure");
    require(failed.workspace && failed.workspace->path == "/workspace",
            "failed host workspace failed");
    record.pass("CodexHostState.Failed", "workspace");

    codex_agent::PathWorkspaceSelection selection{"/workspace"};
    record.pass("CodexPathWorkspaceSelection", "constructor");
    require(selection.path == "/workspace", "path selection failed");
    record.pass("CodexPathWorkspaceSelection", "path");
    require_rejected([] { (void)codex_agent::PathWorkspaceSelection(" "); },
                     "blank workspace selection");

    codex_agent::WorkspaceAvailable available{workspace};
    record.pass("CodexWorkspaceResolution.Available", "constructor");
    require(available.workspace.display_name == "Workspace",
            "available workspace failed");
    record.pass("CodexWorkspaceResolution.Available", "workspace");
}

void exercise_validation_and_progress_values(Recorder& record) {
    codex_agent::ElicitationValidationIssue issue{
        "email", codex_agent::ElicitationValidationReason::invalid_format};
    record.pass("AgentElicitationValidationIssue", "constructor");
    require(issue.field_name == "email", "validation field conversion failed");
    record.pass("AgentElicitationValidationIssue", "fieldName");
    require(issue.reason == codex_agent::ElicitationValidationReason::invalid_format,
            "validation reason conversion failed");
    record.pass("AgentElicitationValidationIssue", "reason");
    std::vector<codex_agent::ElicitationValidationIssue> issues{issue};
    codex_agent::ElicitationValidation validation{issues};
    issues.front().field_name = "mutated";
    record.pass("AgentElicitationValidation", "constructor");
    require(validation.issues.front().field_name == "email",
            "validation issues were not defensively copied");
    record.pass("AgentElicitationValidation", "issues");
    require(!validation.is_valid() &&
                codex_agent::ElicitationValidation{{}}.is_valid(),
            "validation computed property failed");
    record.pass("AgentElicitationValidation", "isValid");

    codex_agent::PlanStep step{"compile", codex_agent::PlanStepStatus::completed};
    record.pass("AgentPlanStep", "constructor");
    require(step.text == "compile", "plan step text conversion failed");
    record.pass("AgentPlanStep", "text");
    require(step.status == codex_agent::PlanStepStatus::completed,
            "plan step status conversion failed");
    record.pass("AgentPlanStep", "status");
    std::vector<codex_agent::PlanStep> steps{step, step};
    codex_agent::PlanProgress plan{"done", steps};
    steps.front().text = "mutated";
    record.pass("AgentPlanProgress", "constructor");
    require(plan.explanation == std::optional<std::string>("done"),
            "plan explanation conversion failed");
    record.pass("AgentPlanProgress", "explanation");
    require(plan.steps.size() == 2 && plan.steps.front().text == "compile",
            "ordered plan steps were not defensively copied");
    record.pass("AgentPlanProgress", "steps");

    std::vector<std::string> details{"one", "one", "two"};
    codex_agent::HookActivity hook{
        "hook-1", "after-turn", "command", codex_agent::HookRunStatus::completed,
        "ok", details};
    details.front() = "mutated";
    record.pass("AgentHookActivity", "constructor");
    require(hook.id == "hook-1", "hook ID conversion failed");
    record.pass("AgentHookActivity", "id");
    require(hook.event_name == "after-turn", "hook event conversion failed");
    record.pass("AgentHookActivity", "eventName");
    require(hook.handler_type == "command", "hook handler conversion failed");
    record.pass("AgentHookActivity", "handlerType");
    require(hook.status == codex_agent::HookRunStatus::completed,
            "hook status conversion failed");
    record.pass("AgentHookActivity", "status");
    require(hook.status_message == std::optional<std::string>("ok"),
            "hook message conversion failed");
    record.pass("AgentHookActivity", "statusMessage");
    require(hook.details == std::vector<std::string>({"one", "one", "two"}),
            "hook details did not preserve ordered duplicates and copy");
    record.pass("AgentHookActivity", "details");

    std::vector<codex_agent::HookActivity> hooks{hook, hook};
    codex_agent::TurnProgress progress{
        "text", "commentary", "reasoning", "plan", plan, "output", 7,
        codex_agent::WorkActivity::writing_files, hooks, true};
    hooks.front().id = "mutated";
    record.pass("AgentTurnProgress", "constructor");
    require(progress.text == "text", "turn text conversion failed");
    record.pass("AgentTurnProgress", "text");
    require(progress.commentary == "commentary", "turn commentary conversion failed");
    record.pass("AgentTurnProgress", "commentary");
    require(progress.reasoning == "reasoning", "turn reasoning conversion failed");
    record.pass("AgentTurnProgress", "reasoning");
    require(progress.plan == "plan", "turn plan conversion failed");
    record.pass("AgentTurnProgress", "plan");
    require(progress.plan_progress && progress.plan_progress->steps.size() == 2,
            "nested plan conversion failed");
    record.pass("AgentTurnProgress", "planProgress");
    require(progress.shell_output == "output", "shell output conversion failed");
    record.pass("AgentTurnProgress", "shellOutput");
    require(progress.shell_exit_code == std::optional<std::int32_t>(7),
            "shell exit conversion failed");
    record.pass("AgentTurnProgress", "shellExitCode");
    require(progress.work_activity ==
                std::optional(codex_agent::WorkActivity::writing_files),
            "work activity conversion failed");
    record.pass("AgentTurnProgress", "workActivity");
    require(progress.hook_activities.size() == 2 &&
                progress.hook_activities.front().id == "hook-1",
            "nested hooks were not defensively copied");
    record.pass("AgentTurnProgress", "hookActivities");
    require(progress.is_truncated, "truncation flag conversion failed");
    record.pass("AgentTurnProgress", "isTruncated");
}

void exercise_resource_values(Recorder& record) {
    std::vector<std::string> plugin_names{"plugin-a", "plugin-a", "plugin-b"};
    codex_agent::Connector connector{
        "connector", "Connector", "Description", "https://example.test", true,
        false, plugin_names};
    plugin_names.front() = "mutated";
    record.pass("AgentConnector", "constructor");
    require(connector.id == "connector", "connector ID conversion failed");
    record.pass("AgentConnector", "id");
    require(connector.name == "Connector", "connector name conversion failed");
    record.pass("AgentConnector", "name");
    require(connector.description == "Description", "connector description failed");
    record.pass("AgentConnector", "description");
    require(connector.install_url ==
                std::optional<std::string>("https://example.test"),
            "connector install URL conversion failed");
    record.pass("AgentConnector", "installUrl");
    require(connector.is_accessible, "connector accessibility conversion failed");
    record.pass("AgentConnector", "isAccessible");
    require(!connector.is_enabled, "connector enabled conversion failed");
    record.pass("AgentConnector", "isEnabled");
    require(connector.plugin_names ==
                std::vector<std::string>({"plugin-a", "plugin-a", "plugin-b"}),
            "connector plugins did not preserve ordered duplicates and copy");
    record.pass("AgentConnector", "pluginNames");

    codex_agent::PluginReference reference{
        "plugin-id", "plugin-name", "marketplace", "path", "remote"};
    record.pass("AgentPluginReference", "constructor");
    require(reference.id == "plugin-id", "plugin reference ID failed");
    record.pass("AgentPluginReference", "id");
    require(reference.name == "plugin-name", "plugin reference name failed");
    record.pass("AgentPluginReference", "name");
    require(reference.marketplace_name == "marketplace",
            "plugin marketplace conversion failed");
    record.pass("AgentPluginReference", "marketplaceName");
    require(reference.marketplace_path == std::optional<std::string>("path"),
            "plugin marketplace path conversion failed");
    record.pass("AgentPluginReference", "marketplacePath");
    require(reference.remote_plugin_id == std::optional<std::string>("remote"),
            "plugin remote ID conversion failed");
    record.pass("AgentPluginReference", "remotePluginId");
    require(reference.uri() == "plugin://plugin-name@marketplace",
            "plugin URI projection failed");
    record.pass("AgentPluginReference", "uri");

    codex_agent::PluginSkill plugin_skill{"skill", "Skill", true, "skill.md"};
    record.pass("AgentPluginSkill", "constructor");
    require(plugin_skill.name == "skill", "plugin skill name failed");
    record.pass("AgentPluginSkill", "name");
    require(plugin_skill.description == "Skill", "plugin skill description failed");
    record.pass("AgentPluginSkill", "description");
    require(plugin_skill.is_enabled, "plugin skill enabled failed");
    record.pass("AgentPluginSkill", "isEnabled");
    require(plugin_skill.path == std::optional<std::string>("skill.md"),
            "plugin skill path failed");
    record.pass("AgentPluginSkill", "path");

    std::vector<std::string> capabilities{"one", "one", "two"};
    codex_agent::PluginSummary summary{
        reference, "Display", "Summary", true, false,
        codex_agent::PluginInstallPolicy::available,
        codex_agent::PluginAuthPolicy::on_use, true, capabilities, "#fff",
        "privacy", "terms", "website"};
    capabilities.front() = "mutated";
    record.pass("AgentPluginSummary", "constructor");
    require(summary.reference.id == "plugin-id", "nested reference failed");
    record.pass("AgentPluginSummary", "reference");
    require(summary.display_name == "Display", "plugin display name failed");
    record.pass("AgentPluginSummary", "displayName");
    require(summary.description == "Summary", "plugin description failed");
    record.pass("AgentPluginSummary", "description");
    require(summary.is_installed, "plugin installed flag failed");
    record.pass("AgentPluginSummary", "isInstalled");
    require(!summary.is_enabled, "plugin enabled flag failed");
    record.pass("AgentPluginSummary", "isEnabled");
    require(summary.install_policy == codex_agent::PluginInstallPolicy::available,
            "plugin install policy failed");
    record.pass("AgentPluginSummary", "installPolicy");
    require(summary.auth_policy == codex_agent::PluginAuthPolicy::on_use,
            "plugin auth policy failed");
    record.pass("AgentPluginSummary", "authPolicy");
    require(summary.is_available, "plugin available flag failed");
    record.pass("AgentPluginSummary", "isAvailable");
    require(summary.capabilities ==
                std::vector<std::string>({"one", "one", "two"}),
            "plugin capabilities did not preserve ordered duplicates and copy");
    record.pass("AgentPluginSummary", "capabilities");
    require(summary.brand_color == std::optional<std::string>("#fff"),
            "plugin brand color failed");
    record.pass("AgentPluginSummary", "brandColor");
    require(summary.privacy_policy_url == std::optional<std::string>("privacy"),
            "plugin privacy URL failed");
    record.pass("AgentPluginSummary", "privacyPolicyUrl");
    require(summary.terms_of_service_url == std::optional<std::string>("terms"),
            "plugin terms URL failed");
    record.pass("AgentPluginSummary", "termsOfServiceUrl");
    require(summary.website_url == std::optional<std::string>("website"),
            "plugin website URL failed");
    record.pass("AgentPluginSummary", "websiteUrl");

    std::vector<codex_agent::PluginSummary> summaries{summary, summary};
    std::vector<std::string> errors{"error", "error"};
    codex_agent::PluginCatalog catalog{
        summaries, errors, codex_agent::CatalogFreshness::stale_cache};
    summaries.front().display_name = "mutated";
    errors.front() = "mutated";
    record.pass("AgentPluginCatalog", "constructor");
    require(catalog.plugins.size() == 2 &&
                catalog.plugins.front().display_name == "Display",
            "plugin catalog did not defensively copy ordered plugins");
    record.pass("AgentPluginCatalog", "plugins");
    require(catalog.errors == std::vector<std::string>({"error", "error"}),
            "plugin catalog did not preserve ordered errors");
    record.pass("AgentPluginCatalog", "errors");
    require(catalog.freshness == codex_agent::CatalogFreshness::stale_cache,
            "catalog freshness conversion failed");
    record.pass("AgentPluginCatalog", "freshness");

    std::vector<codex_agent::PluginSkill> skills{plugin_skill};
    std::vector<codex_agent::Connector> connectors{connector};
    std::vector<std::string> servers{"mcp", "mcp"};
    codex_agent::PluginDetail detail{
        summary, "Detail", skills, connectors, servers, 2};
    skills.front().name = "mutated";
    connectors.front().id = "mutated";
    servers.front() = "mutated";
    record.pass("AgentPluginDetail", "constructor");
    require(detail.summary.reference.id == "plugin-id", "detail summary failed");
    record.pass("AgentPluginDetail", "summary");
    require(detail.description == "Detail", "detail description failed");
    record.pass("AgentPluginDetail", "description");
    require(detail.skills.front().name == "skill", "detail skills copy failed");
    record.pass("AgentPluginDetail", "skills");
    require(detail.connectors.front().id == "connector",
            "detail connectors copy failed");
    record.pass("AgentPluginDetail", "connectors");
    require(detail.mcp_servers == std::vector<std::string>({"mcp", "mcp"}),
            "detail servers did not preserve ordered duplicates");
    record.pass("AgentPluginDetail", "mcpServers");
    require(detail.hook_count == 2, "detail hook count failed");
    record.pass("AgentPluginDetail", "hookCount");

    codex_agent::PluginInstallResult install{
        codex_agent::PluginAuthPolicy::on_install, {connector, connector}, "ok"};
    record.pass("AgentPluginInstallResult", "constructor");
    require(install.auth_policy == codex_agent::PluginAuthPolicy::on_install,
            "install auth policy failed");
    record.pass("AgentPluginInstallResult", "authPolicy");
    require(install.connectors_needing_authentication.size() == 2,
            "install connectors ordering failed");
    record.pass("AgentPluginInstallResult", "connectorsNeedingAuthentication");
    require(install.message == std::optional<std::string>("ok"),
            "install message failed");
    record.pass("AgentPluginInstallResult", "message");
}

void exercise_model_and_skill_values(Recorder& record) {
    codex_agent::ServiceTier tier{"fast", "Fast", "Low latency"};
    record.pass("AgentServiceTier", "constructor");
    require(tier.id == "fast", "tier ID conversion failed");
    record.pass("AgentServiceTier", "id");
    require(tier.name == "Fast", "tier name conversion failed");
    record.pass("AgentServiceTier", "name");
    require(tier.description == "Low latency", "tier description failed");
    record.pass("AgentServiceTier", "description");

    std::vector<std::string> efforts{"low", "low", "high"};
    std::vector<codex_agent::ServiceTier> tiers{tier, tier};
    codex_agent::Model model{
        "model", "Model", "Description", efforts, "low", true, tiers, "fast"};
    efforts.front() = "mutated";
    tiers.front().id = "mutated";
    record.pass("AgentModel", "constructor");
    require(model.id == "model", "model ID failed");
    record.pass("AgentModel", "id");
    require(model.display_name == "Model", "model display name failed");
    record.pass("AgentModel", "displayName");
    require(model.description == "Description", "model description failed");
    record.pass("AgentModel", "description");
    require(model.supported_efforts ==
                std::vector<std::string>({"low", "low", "high"}),
            "model efforts did not preserve ordered duplicates and copy");
    record.pass("AgentModel", "supportedEfforts");
    require(model.default_effort == "low", "model default effort failed");
    record.pass("AgentModel", "defaultEffort");
    require(model.is_default, "model default flag failed");
    record.pass("AgentModel", "isDefault");
    require(model.service_tiers.size() == 2 && model.service_tiers.front().id == "fast",
            "model tiers were not defensively copied");
    record.pass("AgentModel", "serviceTiers");
    require(model.default_service_tier == std::optional<std::string>("fast"),
            "model default tier failed");
    record.pass("AgentModel", "defaultServiceTier");

    std::vector<std::string> dependencies{"dep", "dep"};
    codex_agent::Skill skill{
        "skill", "Skill", "Description", "skill.md",
        codex_agent::SkillScope::repo, true, "#000", dependencies, true};
    dependencies.front() = "mutated";
    record.pass("AgentSkill", "constructor");
    require(skill.name == "skill", "skill name failed");
    record.pass("AgentSkill", "name");
    require(skill.display_name == "Skill", "skill display name failed");
    record.pass("AgentSkill", "displayName");
    require(skill.description == "Description", "skill description failed");
    record.pass("AgentSkill", "description");
    require(skill.path == "skill.md", "skill path failed");
    record.pass("AgentSkill", "path");
    require(skill.scope == codex_agent::SkillScope::repo, "skill scope failed");
    record.pass("AgentSkill", "scope");
    require(skill.is_enabled, "skill enabled failed");
    record.pass("AgentSkill", "isEnabled");
    require(skill.brand_color == std::optional<std::string>("#000"),
            "skill brand color failed");
    record.pass("AgentSkill", "brandColor");
    require(skill.dependencies == std::vector<std::string>({"dep", "dep"}),
            "skill dependencies did not preserve ordered duplicates and copy");
    record.pass("AgentSkill", "dependencies");
    require(skill.can_uninstall, "skill uninstall flag failed");
    record.pass("AgentSkill", "canUninstall");
    require(skill.origin == codex_agent::ResourceOrigin::workspace,
            "skill derived origin failed");
    record.pass("AgentSkill", "origin");

    std::vector<codex_agent::Skill> skills{skill, skill};
    std::vector<std::string> errors{"error", "error"};
    codex_agent::SkillCatalog catalog{skills, errors};
    skills.front().name = "mutated";
    errors.front() = "mutated";
    record.pass("AgentSkillCatalog", "constructor");
    require(catalog.skills.size() == 2 && catalog.skills.front().name == "skill",
            "skill catalog did not defensively copy ordered skills");
    record.pass("AgentSkillCatalog", "skills");
    require(catalog.errors == std::vector<std::string>({"error", "error"}),
            "skill catalog errors ordering failed");
    record.pass("AgentSkillCatalog", "errors");

    codex_agent::SkillChunk chunk{"content", 7, 12};
    record.pass("AgentSkillChunk", "constructor");
    require(chunk.content == "content", "skill chunk content failed");
    record.pass("AgentSkillChunk", "content");
    require(chunk.next_offset == std::optional<std::int64_t>(7),
            "skill chunk next offset failed");
    record.pass("AgentSkillChunk", "nextOffset");
    require(chunk.total_bytes == 12, "skill chunk total bytes failed");
    record.pass("AgentSkillChunk", "totalBytes");
}

void exercise_core_values(Recorder& record) {
    codex_agent::ClientInfo client("client", "Client", "1.0");
    record.pass("CodexClientInfo", "constructor");
    require(client.name == "client", "client name failed");
    record.pass("CodexClientInfo", "name");
    require(client.title == "Client", "client title failed");
    record.pass("CodexClientInfo", "title");
    require(client.version == "1.0", "client version failed");
    record.pass("CodexClientInfo", "version");
    require_rejected([] { (void)codex_agent::ClientInfo("", "Client", "1"); },
                     "invalid client information");

    codex_agent::Failure failure("failed", "Failure", true);
    record.pass("CodexFailure", "constructor");
    require(failure.code == "failed", "failure code failed");
    record.pass("CodexFailure", "code");
    require(failure.message == "Failure", "failure message failed");
    record.pass("CodexFailure", "message");
    require(failure.recoverable, "failure recoverable flag failed");
    record.pass("CodexFailure", "isRecoverable");
    require_rejected([] { (void)codex_agent::Failure("", "Failure", false); },
                     "invalid failure");

    codex_agent::Workspace workspace("/workspace", "Workspace");
    record.pass("CodexWorkspace", "constructor");
    require(workspace.path == "/workspace", "workspace path failed");
    record.pass("CodexWorkspace", "path");
    require(workspace.display_name == "Workspace", "workspace display name failed");
    record.pass("CodexWorkspace", "displayName");
    require_rejected([] { (void)codex_agent::Workspace(" "); },
                     "invalid workspace");
}

std::string join(const std::set<std::string>& values) {
    std::ostringstream output;
    bool first = true;
    for (const auto& value : values) {
        if (!first) output << ',';
        first = false;
        output << value;
    }
    return output.str();
}

void write_evidence(
    const std::filesystem::path& output_directory,
    const std::map<std::string, std::set<std::string>>& compiler_evidence,
    const std::set<std::string>& executed_tests) {
    std::filesystem::create_directories(output_directory);
    {
        std::ofstream output(output_directory / "compiler-evidence.tsv",
                             std::ios::binary | std::ios::trunc);
        require(output.good(), "cannot create compiler evidence");
        output << "compilerEvidenceId\tpublicSymbols\n";
        for (const auto& [id, symbols] : compiler_evidence) {
            output << id << '\t' << join(symbols) << '\n';
        }
        require(output.good(), "cannot write compiler evidence");
    }
    {
        std::ofstream output(output_directory / "executed-tests.tsv",
                             std::ios::binary | std::ios::trunc);
        require(output.good(), "cannot create executed test evidence");
        output << "executedTestId\tstatus\n";
        for (const auto& id : executed_tests) output << id << "\tpassed\n";
        require(output.good(), "cannot write executed test evidence");
    }
}

}  // namespace

int main(int argc, char** argv) {
    require(argc == 13,
            "usage: value_parity_test CLAIMS CANONICAL_REPORT C_ABI_BOOTSTRAP OUTPUT_DIRECTORY LEAF_BEHAVIOR_RECEIPT LEAF_REAL_BOUNDARY_RECEIPT CONVERSATION_BEHAVIOR_RECEIPT CONVERSATION_REAL_BOUNDARY_RECEIPT AGENT_BEHAVIOR_RECEIPT AGENT_REAL_BOUNDARY_RECEIPT HOST_BEHAVIOR_RECEIPT HOST_REAL_BOUNDARY_RECEIPT");
    const auto claims_contents = read_file(argv[1]);
    const auto all_claims = parse_claims(claims_contents);
    const auto bootstrap = read_file(argv[3]);
    require(all_claims.size() == 556, "C++ claim union must be exactly 556");
    const auto canonical = canonical_value_capabilities(argv[2]);
    const auto canonical_mcp = canonical_mcp_graph_capabilities(argv[2]);
    const auto canonical_residual =
        canonical_residual_value_capabilities(argv[2]);
    const auto canonical_functions =
        canonical_sync_value_function_capabilities(argv[2]);
    const auto canonical_leaves =
        canonical_leaf_service_capabilities(argv[2]);
    const auto canonical_conversations =
        canonical_conversation_capabilities(argv[2]);
    const auto canonical_agents = canonical_agent_capabilities(argv[2]);
    const auto canonical_hosts = canonical_host_capabilities(argv[2]);
    const auto values = validate_value_claims(all_claims, canonical, bootstrap);
    const auto mcp_values =
        validate_mcp_graph_claims(all_claims, canonical_mcp, bootstrap);
    const auto residual_values =
        validate_residual_value_claims(all_claims, canonical_residual, bootstrap);
    const auto functions = validate_sync_value_function_claims(
        all_claims, canonical_functions, bootstrap);
    const auto leaves = validate_leaf_service_claims(
        all_claims, canonical_leaves, bootstrap);
    const auto conversations = validate_conversation_claims(
        all_claims, canonical_conversations, bootstrap);
    const auto agents = validate_agent_claims(
        all_claims, canonical_agents, bootstrap);
    const auto hosts = validate_host_claims(
        all_claims, canonical_hosts, bootstrap);
    const auto leaf_behavior = parse_leaf_behavior_receipt(argv[5]);
    const auto leaf_real_boundaries =
        parse_leaf_real_boundary_receipt(argv[6]);
    require(leaf_behavior == leaf_real_boundaries,
            "leaf behavior and real SDK boundary evidence disagree");
    const auto conversation_behavior =
        parse_conversation_behavior_receipt(argv[7]);
    const auto conversation_real_boundaries =
        parse_conversation_real_boundary_receipt(argv[8]);
    require(conversation_behavior == conversation_real_boundaries,
            "conversation behavior and real SDK evidence disagree");
    const auto agent_behavior = parse_agent_behavior_receipt(argv[9]);
    const auto agent_real_boundaries =
        parse_agent_real_boundary_receipt(argv[10]);
    require(agent_behavior == agent_real_boundaries,
            "agent behavior and real SDK evidence disagree");
    const auto host_behavior = parse_host_behavior_receipt(argv[11]);
    const auto host_real_boundaries =
        parse_host_real_boundary_receipt(argv[12]);
    require(host_behavior == host_real_boundaries,
            "Host behavior and real SDK evidence disagree");

    require_rejected(
        [&] {
            auto malformed = claims_contents;
            malformed.replace(0, claims_header.size(), "bad header");
            (void)parse_claims(malformed);
        },
        "malformed inventory");
    require_rejected(
        [&] {
            const auto first_newline = claims_contents.find('\n');
            const auto second_newline =
                claims_contents.find('\n', first_newline + 1);
            auto duplicate = claims_contents;
            duplicate.insert(second_newline + 1,
                             claims_contents.substr(first_newline + 1,
                                                    second_newline - first_newline));
            (void)parse_claims(duplicate);
        },
        "duplicate inventory");
    require_rejected(
        [&] {
            auto stale = values;
            const auto fixture = std::find_if(
                stale.front().compiler_evidence_ids.begin(),
                stale.front().compiler_evidence_ids.end(), [](const auto& id) {
                    return id.starts_with("cabi-fixture:");
                });
            require(fixture != stale.front().compiler_evidence_ids.end(),
                    "test precondition lacks a fixture");
            *fixture += ".stale";
            std::vector<Claim> mutated;
            std::copy_if(all_claims.begin(), all_claims.end(),
                         std::back_inserter(mutated), [](const Claim& claim) {
                             return !is_value_capability(claim.capability_key) ||
                                    claim.capability_key.find("|kind=enum-entry|") !=
                                        std::string::npos;
                         });
            mutated.insert(mutated.end(), stale.begin(), stale.end());
            std::sort(mutated.begin(), mutated.end(), [](const Claim& left, const Claim& right) {
                return left.capability_key < right.capability_key;
            });
            (void)validate_value_claims(mutated, canonical, bootstrap);
        },
        "stale C ABI fixture reference");
    require_rejected(
        [&] {
            auto stale = mcp_values;
            const auto fixture = std::find_if(
                stale.front().compiler_evidence_ids.begin(),
                stale.front().compiler_evidence_ids.end(), [](const auto& id) {
                    return id.starts_with("cabi-fixture:");
                });
            require(fixture != stale.front().compiler_evidence_ids.end(),
                    "MCP test precondition lacks a fixture");
            *fixture += ".stale";
            (void)validate_mcp_graph_claims(stale, canonical_mcp, bootstrap);
        },
        "stale MCP C ABI fixture reference");
    require_rejected(
        [&] {
            auto stale = mcp_values;
            const auto header = std::find_if(
                stale.front().compiler_evidence_ids.begin(),
                stale.front().compiler_evidence_ids.end(), [](const auto& id) {
                    return id.starts_with("c-header:");
                });
            require(header != stale.front().compiler_evidence_ids.end(),
                    "MCP test precondition lacks a header reference");
            *header = "c-header:codex_agent_removed_stale_symbol";
            (void)validate_mcp_graph_claims(stale, canonical_mcp, bootstrap);
        },
        "stale MCP C-header reference");
    require_rejected(
        [&] {
            auto stale = residual_values;
            const auto fixture = std::find_if(
                stale.front().compiler_evidence_ids.begin(),
                stale.front().compiler_evidence_ids.end(), [](const auto& id) {
                    return id.starts_with("cabi-fixture:");
                });
            require(fixture != stale.front().compiler_evidence_ids.end(),
                    "residual test precondition lacks a fixture");
            *fixture += ".stale";
            (void)validate_residual_value_claims(
                stale, canonical_residual, bootstrap);
        },
        "stale residual C ABI fixture reference");
    require_rejected(
        [&] {
            auto stale = residual_values;
            const auto header = std::find_if(
                stale.front().compiler_evidence_ids.begin(),
                stale.front().compiler_evidence_ids.end(), [](const auto& id) {
                    return id.starts_with("c-header:");
                });
            require(header != stale.front().compiler_evidence_ids.end(),
                    "residual test precondition lacks a header reference");
            *header = "c-header:codex_agent_removed_stale_symbol";
            (void)validate_residual_value_claims(
                stale, canonical_residual, bootstrap);
        },
        "stale residual C-header reference");
    require_rejected(
        [&] {
            auto stale = functions;
            const auto fixture = std::find_if(
                stale.front().compiler_evidence_ids.begin(),
                stale.front().compiler_evidence_ids.end(), [](const auto& id) {
                    return id.starts_with("cabi-fixture:");
                });
            require(fixture != stale.front().compiler_evidence_ids.end(),
                    "function test precondition lacks a fixture");
            *fixture += ".stale";
            (void)validate_sync_value_function_claims(
                stale, canonical_functions, bootstrap);
        },
        "stale function C ABI fixture reference");
    require_rejected(
        [&] {
            auto stale = functions;
            const auto header = std::find_if(
                stale.front().compiler_evidence_ids.begin(),
                stale.front().compiler_evidence_ids.end(), [](const auto& id) {
                    return id.starts_with("c-header:");
                });
            require(header != stale.front().compiler_evidence_ids.end(),
                    "function test precondition lacks a header reference");
            *header = "c-header:codex_agent_removed_stale_symbol";
            (void)validate_sync_value_function_claims(
                stale, canonical_functions, bootstrap);
        },
        "stale function C-header reference");
    require_rejected(
        [&] {
            auto stale = functions;
            stale.front().public_symbols.front() += "_stale";
            (void)validate_sync_value_function_claims(
                stale, canonical_functions, bootstrap);
        },
        "stale function public symbol");
    require_rejected(
        [&] {
            auto stale = leaves;
            stale.front().public_symbols.front() += "_stale";
            (void)validate_leaf_service_claims(
                stale, canonical_leaves, bootstrap);
        },
        "stale leaf-service public symbol");
    require_rejected(
        [&] {
            auto stale = leaves;
            stale.front().executed_tests.front() = "cpp.leaf:999";
            (void)validate_leaf_service_claims(
                stale, canonical_leaves, bootstrap);
        },
        "stale leaf-service executed test");
    require_rejected(
        [&] {
            auto stale = leaves;
            stale.front().shared_scenarios.front() =
                "leaf-service-self-reported-trace";
            (void)validate_leaf_service_claims(
                stale, canonical_leaves, bootstrap);
        },
        "stale leaf-service scenario/trace");
    require_rejected(
        [&] {
            auto stale = leaves;
            auto header = std::find_if(
                stale.front().compiler_evidence_ids.begin(),
                stale.front().compiler_evidence_ids.end(), [](const auto& id) {
                    return id.starts_with("c-header:");
                });
            require(header != stale.front().compiler_evidence_ids.end(),
                    "leaf-service test precondition lacks a header reference");
            *header = "c-header:codex_agent_removed_stale_symbol";
            (void)validate_leaf_service_claims(
                stale, canonical_leaves, bootstrap);
        },
        "stale leaf-service C-header reference");
    require_rejected(
        [&] {
            auto stale = leaves;
            auto fixture = std::find_if(
                stale.front().compiler_evidence_ids.begin(),
                stale.front().compiler_evidence_ids.end(), [](const auto& id) {
                    return id.starts_with("cabi-fixture:");
                });
            require(fixture != stale.front().compiler_evidence_ids.end(),
                    "leaf-service test precondition lacks a fixture");
            *fixture += ".stale";
            (void)validate_leaf_service_claims(
                stale, canonical_leaves, bootstrap);
        },
        "stale leaf-service C ABI fixture reference");
    require_rejected(
        [&] {
            auto stale = conversations;
            stale.front().public_symbols.front() += "_stale";
            (void)validate_conversation_claims(
                stale, canonical_conversations, bootstrap);
        },
        "stale conversation public symbol");
    require_rejected(
        [&] {
            auto stale = conversations;
            stale.front().executed_tests.front() = "cpp.conversation:999";
            (void)validate_conversation_claims(
                stale, canonical_conversations, bootstrap);
        },
        "stale conversation executed test");
    require_rejected(
        [&] {
            auto stale = conversations;
            stale.front().shared_scenarios.front() =
                "conversation-self-reported-trace";
            (void)validate_conversation_claims(
                stale, canonical_conversations, bootstrap);
        },
        "stale conversation scenario/trace");
    require_rejected(
        [&] {
            auto stale = conversations;
            auto header = std::find_if(
                stale.front().compiler_evidence_ids.begin(),
                stale.front().compiler_evidence_ids.end(), [](const auto& id) {
                    return id.starts_with("c-header:");
                });
            require(header != stale.front().compiler_evidence_ids.end(),
                    "conversation test precondition lacks a header reference");
            *header = "c-header:codex_agent_removed_stale_symbol";
            (void)validate_conversation_claims(
                stale, canonical_conversations, bootstrap);
        },
        "stale conversation C-header reference");
    require_rejected(
        [&] {
            auto stale = conversations;
            auto fixture = std::find_if(
                stale.front().compiler_evidence_ids.begin(),
                stale.front().compiler_evidence_ids.end(), [](const auto& id) {
                    return id.starts_with("cabi-fixture:");
                });
            require(fixture != stale.front().compiler_evidence_ids.end(),
                    "conversation test precondition lacks a fixture");
            *fixture += ".stale";
            (void)validate_conversation_claims(
                stale, canonical_conversations, bootstrap);
        },
        "stale conversation C ABI fixture reference");
    require_rejected(
        [&] {
            auto stale = agents;
            stale.front().public_symbols.front() += "_stale";
            (void)validate_agent_claims(stale, canonical_agents, bootstrap);
        },
        "stale Agent public symbol");
    require_rejected(
        [&] {
            auto stale = agents;
            stale.front().executed_tests.front() = "cpp.agent:999";
            (void)validate_agent_claims(stale, canonical_agents, bootstrap);
        },
        "stale Agent executed test");
    require_rejected(
        [&] {
            auto stale = agents;
            stale.front().shared_scenarios.front() =
                "agent-self-reported-trace";
            (void)validate_agent_claims(stale, canonical_agents, bootstrap);
        },
        "stale Agent scenario/trace");
    require_rejected(
        [&] {
            auto stale = agents;
            auto header = std::find_if(
                stale.front().compiler_evidence_ids.begin(),
                stale.front().compiler_evidence_ids.end(), [](const auto& id) {
                    return id.starts_with("c-header:");
                });
            require(header != stale.front().compiler_evidence_ids.end(),
                    "Agent test precondition lacks a header reference");
            *header = "c-header:codex_agent_removed_stale_symbol";
            (void)validate_agent_claims(stale, canonical_agents, bootstrap);
        },
        "stale Agent C-header reference");
    require_rejected(
        [&] {
            auto stale = agents;
            auto fixture = std::find_if(
                stale.front().compiler_evidence_ids.begin(),
                stale.front().compiler_evidence_ids.end(), [](const auto& id) {
                    return id.starts_with("cabi-fixture:");
                });
            require(fixture != stale.front().compiler_evidence_ids.end(),
                    "Agent test precondition lacks a fixture");
            *fixture += ".stale";
            (void)validate_agent_claims(stale, canonical_agents, bootstrap);
        },
        "stale Agent C ABI fixture reference");
    require_rejected(
        [&] {
            auto stale = hosts;
            stale.front().public_symbols.front() += "_stale";
            (void)validate_host_claims(stale, canonical_hosts, bootstrap);
        },
        "stale Host public symbol");
    require_rejected(
        [&] {
            auto stale = hosts;
            stale.front().executed_tests.front() = "cpp.host:999";
            (void)validate_host_claims(stale, canonical_hosts, bootstrap);
        },
        "stale Host executed test");
    require_rejected(
        [&] {
            auto stale = hosts;
            stale.front().shared_scenarios.front() =
                "host-self-reported-trace";
            (void)validate_host_claims(stale, canonical_hosts, bootstrap);
        },
        "stale Host scenario/trace");
    require_rejected(
        [&] {
            auto stale = hosts;
            auto header = std::find_if(
                stale.front().compiler_evidence_ids.begin(),
                stale.front().compiler_evidence_ids.end(), [](const auto& id) {
                    return id.starts_with("c-header:");
                });
            require(header != stale.front().compiler_evidence_ids.end(),
                    "Host test precondition lacks a header reference");
            *header = "c-header:codex_agent_removed_stale_symbol";
            (void)validate_host_claims(stale, canonical_hosts, bootstrap);
        },
        "stale Host C-header reference");
    require_rejected(
        [&] {
            auto stale = hosts;
            auto fixture = std::find_if(
                stale.front().compiler_evidence_ids.begin(),
                stale.front().compiler_evidence_ids.end(), [](const auto& id) {
                    return id.starts_with("cabi-fixture:");
                });
            require(fixture != stale.front().compiler_evidence_ids.end(),
                    "Host test precondition lacks a fixture");
            *fixture += ".stale";
            (void)validate_host_claims(stale, canonical_hosts, bootstrap);
        },
        "stale Host C ABI fixture reference");

    std::vector<Claim> projected_values = values;
    projected_values.insert(projected_values.end(), mcp_values.begin(),
                            mcp_values.end());
    projected_values.insert(projected_values.end(), residual_values.begin(),
                            residual_values.end());
    projected_values.insert(projected_values.end(), functions.begin(),
                            functions.end());
    Recorder recorder(projected_values);
    exercise_conversation_values(recorder);
    exercise_configuration_values(recorder);
    exercise_mcp_graph_values(recorder);
    exercise_residual_metadata_and_authentication(recorder);
    exercise_residual_forms_and_elicitation(recorder);
    exercise_sync_value_functions(recorder);
    exercise_residual_hooks(recorder);
    exercise_residual_integrations_and_invocations(recorder);
    exercise_residual_messages_and_turn_requests(recorder);
    exercise_residual_interactions_and_conversation(recorder);
    exercise_residual_host_and_workspace_values(recorder);
    exercise_validation_and_progress_values(recorder);
    exercise_resource_values(recorder);
    exercise_model_and_skill_values(recorder);
    exercise_core_values(recorder);
    std::set<std::string> expected_value_tests;
    for (const auto& claim : projected_values) {
        expected_value_tests.insert(claim.executed_tests.front());
    }
    require(recorder.passed() == expected_value_tests,
            "independent value behavior execution is incomplete");

    std::map<std::string, std::set<std::string>> compiler_evidence;
    std::set<std::string> executed_tests = recorder.passed();
    for (const auto& id : leaf_behavior) {
        require(executed_tests.insert(id).second,
                "duplicate leaf-service behavior evidence");
    }
    for (const auto& id : conversation_behavior) {
        require(executed_tests.insert(id).second,
                "duplicate conversation behavior evidence");
    }
    for (const auto& id : agent_behavior) {
        require(executed_tests.insert(id).second,
                "duplicate Agent behavior evidence");
    }
    for (const auto& id : host_behavior) {
        require(executed_tests.insert(id).second,
                "duplicate Host behavior evidence");
    }
    std::vector<Claim> enums;
    std::copy_if(all_claims.begin(), all_claims.end(), std::back_inserter(enums),
                 [](const Claim& claim) {
                     return claim.capability_key.find("|kind=enum-entry|") !=
                            std::string::npos;
                 });
    require(enums.size() == enum_evidence.size(), "enum inventory changed");
    for (std::size_t index = 0; index < enums.size(); ++index) {
        const auto& claim = enums[index];
        const auto& evidence = enum_evidence[index];
        require(evidence.index == index && evidence.public_value == evidence.c_value &&
                    claim.public_symbols ==
                        std::vector<std::string>{std::string(evidence.public_symbol)},
                "compiled enum evidence is stale");
        require(executed_tests.insert(claim.executed_tests.front()).second,
                "duplicate enum test evidence");
    }
    for (const auto& claim : all_claims) {
        require(claim.public_symbols.size() == 1,
                "ordinary C++ claim must have one public symbol");
        for (const auto& id : claim.compiler_evidence_ids) {
            compiler_evidence[id].insert(claim.public_symbols.front());
        }
    }
    std::set<std::string> claimed_c_header_references;
    for (const auto& [id, ignored] : compiler_evidence) {
        (void)ignored;
        if (id.starts_with("c-header:")) {
            claimed_c_header_references.insert(id.substr(9));
        }
    }
    require(claimed_c_header_references ==
                std::set<std::string>(compiled_c_header_references.begin(),
                                      compiled_c_header_references.end()),
            "compiled C-header reference set is incomplete or stale");
    std::set<std::string> expected_tests;
    std::set<std::string> expected_compiler;
    for (const auto& claim : all_claims) {
        expected_tests.insert(claim.executed_tests.begin(), claim.executed_tests.end());
        expected_compiler.insert(claim.compiler_evidence_ids.begin(),
                                 claim.compiler_evidence_ids.end());
    }
    std::set<std::string> compiler_ids;
    for (const auto& [id, ignored] : compiler_evidence) {
        (void)ignored;
        compiler_ids.insert(id);
    }
    require(executed_tests == expected_tests, "executed evidence is incomplete");
    require(compiler_ids == expected_compiler, "compiler evidence is incomplete");
    write_evidence(argv[4], compiler_evidence, executed_tests);
}
