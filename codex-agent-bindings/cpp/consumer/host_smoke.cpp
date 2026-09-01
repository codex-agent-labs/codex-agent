#include <codex_agent/codex_agent.hpp>

#include <filesystem>
#include <iostream>
#include <string>

namespace {

constexpr int usage_error = 64;

int smoke() {
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
    if (argc > 2) {
        std::cerr << "usage: codex_agent_host_smoke [absolute-compatible-runtime]\n";
        return usage_error;
    }
    try {
        if (argc == 2) {
            const std::filesystem::path library(argv[1]);
            if (!library.is_absolute()) {
                std::cerr << "the explicit Runtime path must be absolute\n";
                return usage_error;
            }
            codex_agent::CodexNativeLibrary::configure(library);
        }
        return smoke();
    } catch (const std::exception& exception) {
        std::cerr << exception.what() << '\n';
        return 1;
    }
}
