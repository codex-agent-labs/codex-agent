#include <codex_agent/codex_agent.hpp>

#include "host_native_probe.hpp"

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <map>
#include <string>
#include <type_traits>

using HostCreate = codex_agent::Host (*)(const codex_agent::HostOptions&);
using HostClose = codex_agent::AsyncOperation<void>
    (codex_agent::Host::*)() const;
using HostSelect = codex_agent::AsyncOperation<void>
    (codex_agent::Host::*)(std::string) const;
using HostStart = codex_agent::AsyncOperation<void>
    (codex_agent::Host::*)() const;
using HostState = codex_agent::HostState (codex_agent::Host::*)() const;
using HostSubscribe = codex_agent::StateSubscription<codex_agent::HostState>
    (codex_agent::Host::*)(std::function<void(
        codex_agent::StateEvent<codex_agent::HostState>)>) const;

static_assert(std::is_same_v<decltype(&codex_agent::Host::create), HostCreate>);
static_assert(std::is_same_v<decltype(&codex_agent::Host::close), HostClose>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Host::select_workspace), HostSelect>);
static_assert(std::is_same_v<decltype(&codex_agent::Host::start), HostStart>);
static_assert(std::is_same_v<decltype(&codex_agent::Host::state), HostState>);
static_assert(std::is_same_v<
              decltype(&codex_agent::Host::subscribe), HostSubscribe>);
static_assert(std::is_constructible_v<
              codex_agent::HostStateReady, codex_agent::Agent>);
static_assert(std::is_same_v<
              decltype(codex_agent::HostStateReady::agent),
              codex_agent::Agent>);
static_assert(std::is_move_constructible_v<codex_agent::HostStateReady>);
static_assert(!std::is_copy_constructible_v<codex_agent::HostStateReady>);

#define HOST_NATIVE_BOUNDARY(capability, function)                          \
    static_assert(std::is_pointer_v<decltype(&function)>);
#define HOST_NATIVE_TYPE(capability, type)                                  \
    static_assert(std::is_same_v<type, type>);
#include "host_native_boundaries.inc"
#undef HOST_NATIVE_TYPE
#undef HOST_NATIVE_BOUNDARY
#define HOST_NATIVE_CONSTANT(capability, constant)                          \
    static_assert(std::is_integral_v<decltype(constant)>);
#include "host_native_constants.inc"
#undef HOST_NATIVE_CONSTANT

extern "C" void codex_agent_cpp_mock_host_delay_next();
extern "C" void codex_agent_cpp_mock_host_fail_next();
extern "C" void codex_agent_cpp_mock_host_complete_pending();
extern "C" void codex_agent_cpp_mock_host_publish();
extern "C" void codex_agent_cpp_mock_host_change_workspace();
extern "C" const char* codex_agent_cpp_mock_host_bundle();
extern "C" const char* codex_agent_cpp_mock_host_data();
extern "C" const char* codex_agent_cpp_mock_host_name();
extern "C" const char* codex_agent_cpp_mock_host_title();
extern "C" const char* codex_agent_cpp_mock_host_version();
extern "C" const char* codex_agent_cpp_mock_host_selection();
extern "C" int codex_agent_cpp_mock_host_identity_stable();
extern "C" int codex_agent_cpp_mock_host_release_order();
extern "C" std::size_t codex_agent_cpp_mock_host_premature_releases();
extern "C" std::size_t codex_agent_cpp_mock_host_context_destroys();
extern "C" std::size_t codex_agent_cpp_mock_host_ready_projections();
extern "C" std::size_t codex_agent_cpp_mock_host_agent_retains();
extern "C" std::size_t codex_agent_cpp_mock_host_agent_releases();

namespace {

[[noreturn]] void fail(const char* message) {
    std::fputs(message, stderr);
    std::fputc('\n', stderr);
    std::abort();
}

void require(bool condition, const char* message) {
    if (!condition) fail(message);
}

template <typename Action>
void require_status(Action&& action, codex_agent::Status status) {
    try {
        action();
    } catch (const codex_agent::Error& error) {
        require(error.status() == status, "unexpected host error status");
        return;
    }
    fail("expected host error was not reported");
}

template <typename Action>
void require_invalid_argument(Action&& action) {
    try {
        action();
    } catch (const std::invalid_argument&) {
        return;
    }
    fail("invalid Host input was accepted");
}

template <typename Action>
void require_operation_failure(Action&& action, codex_agent::Status status) {
    try {
        action();
    } catch (const codex_agent::OperationError& error) {
        require(error.status() == status, "unexpected operation status");
        if (status == codex_agent::Status::operation_failed) {
            require(error.failure().has_value() &&
                        error.failure()->code == "host_failed" &&
                        error.failure()->message ==
                            "mock host operation failed" &&
                        error.failure()->recoverable,
                    "structured host failure was not copied");
        } else {
            require(!error.failure().has_value(),
                    "cancellation unexpectedly carried a failure");
        }
        return;
    }
    fail("host operation unexpectedly succeeded");
}

bool edge_seen_since(HostNativeEdge edge, std::size_t start) {
    for (auto index = start; index < codex_agent_cpp_mock_host_event_count();
         ++index) {
        if (codex_agent_cpp_mock_host_event_at(index) == edge) return true;
    }
    return false;
}

void require_exact_edge(std::string_view capability, std::size_t start) {
    bool matched = false;
    bool complete = true;
#define HOST_NATIVE_BOUNDARY(expected, function)                            \
    if (capability == expected) {                                           \
        matched = true;                                                     \
        complete = complete &&                                              \
            edge_seen_since(HostNativeEdge::function, start);               \
    }
#define HOST_NATIVE_TYPE(expected, type)                                    \
    if (capability == expected) matched = true;
#include "host_native_boundaries.inc"
#undef HOST_NATIVE_TYPE
#undef HOST_NATIVE_BOUNDARY
#define HOST_NATIVE_CONSTANT(expected, constant)                            \
    if (capability == expected) matched = matched &&                        \
        static_cast<codex_agent_host_state_kind_t>(constant) ==             \
            CODEX_AGENT_HOST_STATE_READY;
#include "host_native_constants.inc"
#undef HOST_NATIVE_CONSTANT
    require(matched && complete, "Host capability missed its native edge");
}

const std::map<std::string, std::string>& scenarios() {
    static const std::map<std::string, std::string> values{
#define HOST_SCENARIO(capability, scenario) {capability, scenario},
#include "host_scenarios.inc"
#undef HOST_SCENARIO
    };
    return values;
}

void pass(const char* capability, std::size_t start,
          std::map<std::string, std::string>& passed) {
    require_exact_edge(capability, start);
    require(passed.emplace(capability, scenarios().at(capability)).second,
            "duplicate Host capability");
}

codex_agent::Host make_host() {
    codex_agent::HostOptions options{
        "/bundle", "/data", {"host-test", "Host Test", "1"}};
    auto host = codex_agent::Host::create(options);
    options.bundle_directory = "mutated-bundle";
    options.data_directory = "mutated-data";
    options.client_info.name = "mutated-name";
    options.client_info.title = "mutated-title";
    options.client_info.version = "mutated-version";
    require(std::string(codex_agent_cpp_mock_host_bundle()) == "/bundle" &&
                std::string(codex_agent_cpp_mock_host_data()) == "/data" &&
                std::string(codex_agent_cpp_mock_host_name()) == "host-test" &&
                std::string(codex_agent_cpp_mock_host_title()) == "Host Test" &&
                std::string(codex_agent_cpp_mock_host_version()) == "1",
            "Host factory did not copy all five inputs");
    return host;
}

void prove_async(codex_agent::Host& host,
                 codex_agent::AsyncOperation<void> (codex_agent::Host::*member)()
                     const) {
    (host.*member)().get();
    codex_agent_cpp_mock_host_fail_next();
    require_operation_failure(
        [&] { (host.*member)().get(); },
        codex_agent::Status::operation_failed);
    codex_agent_cpp_mock_host_delay_next();
    auto cancelled = (host.*member)();
    cancelled.cancel();
    require_operation_failure(
        [&] { cancelled.get(); }, codex_agent::Status::cancelled);
}

}  // namespace

int main(int argc, char** argv) {
    require(argc == 2, "usage: host_behavior_test RECEIPT");
    codex_agent_cpp_mock_host_reset();
    std::map<std::string, std::string> passed;
    codex_agent::Workspace copied_workspace;
    {
        const auto before_invalid = codex_agent_cpp_mock_host_event_count();
        require_invalid_argument([&] {
            (void)codex_agent::Host::create({
                " ", "/data", {"host-test", "Host Test", "1"}});
        });
        require(codex_agent_cpp_mock_host_event_count() == before_invalid,
                "invalid Host input crossed the native boundary");
        const auto create_at = codex_agent_cpp_mock_host_event_count();
        auto host = make_host();
        pass("cpp.host:002", create_at, passed);

        const auto ready_constructor_at =
            codex_agent_cpp_mock_host_event_count();
        const auto current = host.state();
        require(current.kind == codex_agent::HostStateKind::ready &&
                    current.workspace.has_value() &&
                    current.workspace->path == "/workspace",
                "current Host state was not Ready");
        codex_agent::HostStateReady ready(host.agent());
        copied_workspace = ready.agent.workspace();
        pass("cpp.host:000", ready_constructor_at, passed);

        const auto ready_agent_at = codex_agent_cpp_mock_host_event_count();
        codex_agent::HostStateReady duplicate(host.agent());
        require(codex_agent_cpp_mock_host_identity_stable() != 0 &&
                    duplicate.agent.workspace().path == copied_workspace.path,
                "Ready Agent projection was not identity-stable");
        require(codex_agent_cpp_mock_host_ready_projections() == 2 &&
                    codex_agent_cpp_mock_host_agent_retains() == 2 &&
                    codex_agent_cpp_mock_host_agent_releases() == 2,
                "Ready aliases did not project/retain/release exactly");
        pass("cpp.host:001", ready_agent_at, passed);

        const auto state_at = codex_agent_cpp_mock_host_event_count();
        require(host.state().kind == codex_agent::HostStateKind::ready,
                "Host state getter lost its current Ready value");
        std::atomic<int> values = 0;
        std::atomic<int> terminals = 0;
        std::string first_path;
        std::string second_path;
        auto subscription = host.subscribe(
            [&](codex_agent::StateEvent<codex_agent::HostState> event) {
                if (event.terminal) {
                    require(event.status == codex_agent::Status::cancelled &&
                                !event.value.has_value(),
                            "Host terminal event was malformed");
                    ++terminals;
                    return;
                }
                require(event.status == codex_agent::Status::ok &&
                            event.value && event.value->workspace,
                        "Host state value was malformed");
                if (values++ == 0)
                    first_path = event.value->workspace->path;
                else
                    second_path = event.value->workspace->path;
            });
        codex_agent_cpp_mock_host_change_workspace();
        codex_agent_cpp_mock_host_publish();
        subscription.close();
        subscription.close();
        require(values == 2 && terminals == 1 &&
                    first_path == "/workspace" &&
                    second_path == "/workspace-next",
                "Host state did not deliver current/change/terminal exactly");
        const auto closed_values = values.load();
        const auto closed_terminals = terminals.load();
        const auto closed_first_path = first_path;
        const auto closed_second_path = second_path;
        codex_agent_cpp_mock_host_publish();
        require(values == closed_values && terminals == closed_terminals &&
                    first_path == closed_first_path &&
                    second_path == closed_second_path,
                "closed Host subscription delivered another event");
        pass("cpp.host:006", state_at, passed);

        const auto select_at = codex_agent_cpp_mock_host_event_count();
        std::string selected = "/selected";
        codex_agent_cpp_mock_host_delay_next();
        auto selection = host.select_workspace(selected);
        selected = "mutated";
        require(std::string(codex_agent_cpp_mock_host_selection()) ==
                    "/selected",
                "workspace selection was not copied before suspension");
        codex_agent_cpp_mock_host_complete_pending();
        selection.get();
        codex_agent_cpp_mock_host_fail_next();
        require_operation_failure(
            [&] { host.select_workspace("/failure").get(); },
            codex_agent::Status::operation_failed);
        codex_agent_cpp_mock_host_delay_next();
        auto cancelled_selection = host.select_workspace("/cancelled");
        cancelled_selection.cancel();
        require_operation_failure(
            [&] { cancelled_selection.get(); },
            codex_agent::Status::cancelled);
        pass("cpp.host:004", select_at, passed);

        const auto start_at = codex_agent_cpp_mock_host_event_count();
        prove_async(host, &codex_agent::Host::start);
        pass("cpp.host:005", start_at, passed);

        auto live = std::move(host);
        const auto before_closed = codex_agent_cpp_mock_host_event_count();
        require_status([&] { (void)host.state(); }, codex_agent::Status::closed);
        require_status([&] { (void)host.start(); }, codex_agent::Status::closed);
        require(codex_agent_cpp_mock_host_event_count() == before_closed,
                "moved-from Host crossed the native boundary");

        const auto close_at = codex_agent_cpp_mock_host_event_count();
        codex_agent_cpp_mock_host_fail_next();
        require_operation_failure(
            [&] { live.close().get(); },
            codex_agent::Status::operation_failed);
        codex_agent_cpp_mock_host_delay_next();
        auto cancelled_close = live.close();
        cancelled_close.cancel();
        require_operation_failure(
            [&] { cancelled_close.get(); }, codex_agent::Status::cancelled);
        live.close().get();
        live.close().get();
        require(live.state().kind == codex_agent::HostStateKind::closed,
                "repeated Host close was not idempotent");
        pass("cpp.host:003", close_at, passed);
    }

    require(copied_workspace.path == "/workspace" &&
                copied_workspace.display_name == "Workspace",
            "copied Workspace did not survive Host/Agent/context teardown");
    require(codex_agent_cpp_mock_host_premature_releases() == 0,
            "Host released before its Agent children");
    require(codex_agent_cpp_mock_host_ready_projections() == 2 &&
                codex_agent_cpp_mock_host_agent_retains() == 2 &&
                codex_agent_cpp_mock_host_agent_releases() == 4,
            "Ready Agent aliases did not release exactly after teardown");
    require(codex_agent_cpp_mock_host_release_order() != 0,
            "release order was not Workspace then Agent then Host then context");
    require(codex_agent_cpp_mock_host_context_destroys() == 1,
            "Host ownership did not quiesce its context exactly once");
    require(passed.size() == 7, "Host behavior coverage is incomplete");

    std::ofstream output(
        std::filesystem::path(argv[1]), std::ios::binary | std::ios::trunc);
    require(output.good(), "cannot create Host behavior receipt");
    output << "executedTestId\tscenarios\tstatus\n";
    for (const auto& [capability, scenario] : passed)
        output << capability << '\t' << scenario << "\tpassed\n";
    require(output.good(), "cannot write Host behavior receipt");
}
