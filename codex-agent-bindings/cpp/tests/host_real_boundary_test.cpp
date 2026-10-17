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
                "typed real SDK Host boundary reported success");
        ++calls;
        return;
    } catch (const std::exception&) {
        ++calls;
        return;
    }
    require(false, "typed wrapper accepted an invalid real Host");
}

}  // namespace

int main(int argc, char** argv) {
    require(argc == 2, "usage: host_real_boundary_test RECEIPT");
    codex_agent::Host host;

    std::map<std::string, std::size_t> typed;
    const auto prove = [&](const char* capability, auto&& action) {
        typed_real_rejection(action, typed[capability]);
    };
    prove("cpp.host:000", [&] {
        (void)codex_agent::HostStateReady(host.agent());
    });
    prove("cpp.host:001", [&] { (void)host.agent(); });
    prove("cpp.host:002", [&] {
        (void)codex_agent::Host::create({
            "", "", {"real-boundary", "Real boundary", "1"}});
    });
    prove("cpp.host:003", [&] { (void)host.close(); });
    prove("cpp.host:004", [&] {
        (void)host.select_workspace("/workspace");
    });
    prove("cpp.host:005", [&] { (void)host.start(); });
    prove("cpp.host:006", [&] { (void)host.state(); });
    require(typed.size() == 7,
            "typed real SDK Host capability coverage is incomplete");

    std::map<std::string, std::size_t> raw;
#define HOST_NATIVE_BOUNDARY(capability, function)                          \
    do {                                                                    \
        const auto status = invoke_null_boundary(&function);                \
        require(status != CODEX_AGENT_STATUS_OK,                            \
                "real SDK accepted a null Host boundary");                \
        ++raw[capability];                                                   \
    } while (false);
#define HOST_NATIVE_TYPE(capability, type)                                  \
    do {                                                                    \
        static_assert(std::is_same_v<type, type>);                           \
        ++raw[capability];                                                   \
    } while (false);
#include "host_native_boundaries.inc"
#undef HOST_NATIVE_TYPE
#undef HOST_NATIVE_BOUNDARY
#define HOST_NATIVE_CONSTANT(capability, constant)                          \
    do {                                                                    \
        require(static_cast<codex_agent_host_state_kind_t>(constant) ==     \
                    CODEX_AGENT_HOST_STATE_READY,                           \
                "real SDK Ready constant changed");                       \
        ++raw[capability];                                                   \
    } while (false);
#include "host_native_constants.inc"
#undef HOST_NATIVE_CONSTANT
    require(raw.size() == 7,
            "real SDK exact Host boundary coverage is incomplete");

    std::ofstream output(
        std::filesystem::path(argv[1]), std::ios::binary | std::ios::trunc);
    require(output.good(), "cannot create Host real-boundary receipt");
    output << "executedTestId\tboundary\tstatus\n";
    for (const auto& [capability, calls] : typed) {
        require(calls == 1 && raw.at(capability) != 0,
                "Host real-boundary count is stale");
        output << capability
               << "\ttyped-production-real-sdk-invalid-host+raw-exact-null-boundary\tpassed\n";
    }
    require(output.good(), "cannot write Host real-boundary receipt");
}
