#include <codex_agent/codex_agent.hpp>

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <map>
#include <string>

namespace {

void require(bool condition, const char* message) {
    if (!condition) {
        (void)message;
        std::abort();
    }
}

template <typename Value>
Value null_argument() {
    return Value{};
}

template <typename... Arguments>
codex_agent_status_t invoke_null_boundary(
    codex_agent_status_t (*function)(Arguments...)) {
    return function(null_argument<Arguments>()...);
}

template <typename Action>
void typed_real_rejection(Action&& action, std::size_t& calls) {
    try {
        action();
    } catch (const codex_agent::Error& error) {
        require(error.status() != codex_agent::Status::ok,
                "typed real SDK boundary reported success");
        ++calls;
        return;
    }
    require(false, "typed wrapper accepted an invalid real agent");
}

}  // namespace

int main(int argc, char** argv) {
    require(argc == 2, "usage: agent_real_boundary_test RECEIPT");
    codex_agent::Agent agent;

    std::map<std::string, std::size_t> typed;
    const auto prove = [&](const char* capability, auto&& action) {
        typed_real_rejection(action, typed[capability]);
    };
    prove("cpp.agent:000", [&] { (void)agent.authentication(); });
    prove("cpp.agent:001", [&] { (void)agent.connectors(); });
    prove("cpp.agent:002", [&] { (void)agent.conversations(); });
    prove("cpp.agent:003", [&] { (void)agent.hooks(); });
    prove("cpp.agent:004", [&] {
        (void)agent.integration_authorization();
    });
    prove("cpp.agent:005", [&] { (void)agent.interactions(); });
    prove("cpp.agent:006", [&] { (void)agent.mcp_servers(); });
    prove("cpp.agent:007", [&] { (void)agent.models(); });
    prove("cpp.agent:008", [&] { (void)agent.plugins(); });
    prove("cpp.agent:009", [&] { (void)agent.skills(); });
    prove("cpp.agent:010", [&] { (void)agent.workspace(); });
    require(typed.size() == 11,
            "typed real SDK agent capability coverage is incomplete");

    std::map<std::string, std::size_t> raw;
#define AGENT_NATIVE_BOUNDARY(capability, function)                        \
    do {                                                                   \
        const auto status = invoke_null_boundary(&function);               \
        require(status != CODEX_AGENT_STATUS_OK,                           \
                "real SDK accepted a null agent boundary");              \
        ++raw[capability];                                                  \
    } while (false);
#include "agent_native_boundaries.inc"
#undef AGENT_NATIVE_BOUNDARY
    require(raw.size() == 11,
            "real SDK exact agent boundary coverage is incomplete");

    std::ofstream output(
        std::filesystem::path(argv[1]), std::ios::binary | std::ios::trunc);
    require(output.good(), "cannot create agent real-boundary receipt");
    output << "executedTestId\tboundary\tstatus\n";
    for (const auto& [capability, calls] : typed) {
        require(calls == 1 && raw.at(capability) == 1,
                "agent real-boundary count is stale");
        output << capability
               << "\ttyped-production-real-sdk-invalid-agent+raw-exact-null-boundary\tpassed\n";
    }
    require(output.good(), "cannot write agent real-boundary receipt");
}
