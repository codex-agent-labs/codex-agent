#include <codex_agent/codex_agent.hpp>

#include <filesystem>
#include <iostream>
#include <string>

namespace {

constexpr int usage_error = 64;

int smoke(const std::filesystem::path& library) {
    std::error_code error;
    if (!std::filesystem::is_regular_file(library, error) || error ||
        !std::filesystem::equivalent(
            library, CODEX_AGENT_VERIFIED_LIBRARY_PATH, error) || error) {
        std::cerr << "the argument must be the installed package's verified C SDK library\n";
        return usage_error;
    }

    const auto temporary_directory = std::filesystem::temp_directory_path().string();
    auto host = codex_agent::Host::create({
        .bundle_directory = temporary_directory,
        .data_directory = temporary_directory,
        .client_info = {
            "installed-host-smoke", "Installed Host smoke", "1.0.0"},
    });
    if (host.state().kind != codex_agent::HostStateKind::new_) {
        std::cerr << "installed Host did not begin in NEW\n";
        return 1;
    }

    host.close().get();
    host.close().get();
    if (host.state().kind != codex_agent::HostStateKind::closed) {
        std::cerr << "repeated close did not leave the installed Host CLOSED\n";
        return 1;
    }
    std::cout << "C++ installed Host smoke passed.\n";
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: codex_agent_host_smoke <verified-c-sdk-library>\n";
        return usage_error;
    }
    try {
        return smoke(argv[1]);
    } catch (const std::exception& exception) {
        std::cerr << exception.what() << '\n';
        return 1;
    }
}
