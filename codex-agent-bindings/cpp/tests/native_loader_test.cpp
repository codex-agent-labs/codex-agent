#include <codex_agent/native_dispatch.hpp>

#include <atomic>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <string_view>
#include <thread>

#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#endif

namespace {
using AbiCompatible = std::int32_t(CODEX_AGENT_CALL*)(std::uint32_t);

namespace loader_test_hook {
std::atomic_bool attempted{}, changed{};

void reject_ordinary_snapshot_replacement(const std::filesystem::path& snapshot) {
    attempted = true;
    std::error_code error;
    const auto moved = snapshot.parent_path() / "replaced-runtime";
    std::filesystem::rename(snapshot, moved, error);
    if (!error) {
        changed = true;
        return;
    }
    std::ofstream output(snapshot, std::ios::binary | std::ios::app);
    if (output) {
        output.put('\0');
        output.flush();
        changed = true;
    }
}
}

}

namespace codex_agent::detail {
void set_native_loader_test_hook(void (*hook)(const std::filesystem::path&));
}

namespace {

struct TemporaryDirectory {
    std::filesystem::path path;
    TemporaryDirectory() {
        const auto root = std::filesystem::canonical(std::filesystem::temp_directory_path());
#ifdef _WIN32
        const auto process = GetCurrentProcessId();
#else
        const auto process = getpid();
#endif
        static std::atomic_uint64_t sequence{};
        path = root / ("codex-agent-loader-test-" + std::to_string(process) + "-" +
                       std::to_string(sequence++));
        std::filesystem::create_directory(path);
    }
    ~TemporaryDirectory() { std::error_code ignored; std::filesystem::remove_all(path, ignored); }
};

void replace_once(std::string& value, std::string_view from, std::string_view to) {
    const auto offset = value.find(from);
    if (offset == std::string::npos) throw std::runtime_error("loader test mutation source is stale");
    value.replace(offset, from.size(), to);
}

std::filesystem::path mutated_compatibility(
    const std::filesystem::path& original, std::string_view mode,
    TemporaryDirectory& temporary) {
    std::ifstream input(original, std::ios::binary);
    std::string value(std::istreambuf_iterator<char>(input), {});
    if (mode == "noncanonical-json") {
        value.insert(1, " ");
    } else if (mode == "reordered-json") {
        const std::string field = ",\"schemaVersion\":1";
        const auto offset = value.find(field);
        if (offset == std::string::npos) throw std::runtime_error("schema field missing");
        value.erase(offset, field.size());
        value.insert(1, "\"schemaVersion\":1,");
    } else if (mode == "duplicate-json-key") {
        value.insert(value.size() - 2, ",\"sdkVersion\":\"0.2.0\"");
    } else if (mode == "reordered-variants") {
        replace_once(value, "\"target\":\"linux-arm64\"", "\"target\":\"temporary-target\"");
        replace_once(value, "\"target\":\"linux-x64\"", "\"target\":\"linux-arm64\"");
        replace_once(value, "\"target\":\"temporary-target\"", "\"target\":\"linux-x64\"");
    } else if (mode == "duplicate-component" || mode == "duplicate-manifest") {
        const std::string marker = mode == "duplicate-component"
            ? "\"componentId\":\"" : "\"manifestSha256\":\"";
        const auto first = value.find(marker);
        const auto first_end = value.find('"', first + marker.size());
        const auto second = value.find(marker, first_end);
        const auto second_end = value.find('"', second + marker.size());
        if (first == std::string::npos || first_end == std::string::npos ||
            second == std::string::npos || second_end == std::string::npos) {
            throw std::runtime_error("variant identity fields missing");
        }
        value.replace(second + marker.size(), second_end - second - marker.size(),
            value.substr(first + marker.size(), first_end - first - marker.size()));
    } else if (mode == "invalid-sdk-version") {
        replace_once(value, "\"sdkVersion\":\"0.2.0\"", "\"sdkVersion\":\"00.2.0\"");
    } else if (mode == "invalid-sdk-prerelease") {
        replace_once(value, "\"sdkVersion\":\"0.2.0\"", "\"sdkVersion\":\"0.2.0-01\"");
    } else if (mode == "valid-sdk-prerelease") {
        replace_once(value, "\"sdkVersion\":\"0.2.0\"", "\"sdkVersion\":\"0.2.0-rc.1+build.07\"");
    } else if (mode == "invalid-identity-schema") {
        replace_once(value, "\"requiredIdentitySchema\":1", "\"requiredIdentitySchema\":2");
    } else if (mode == "invalid-abi-major") {
        replace_once(value, "\"requiredAbiMajor\":1", "\"requiredAbiMajor\":2");
    } else if (mode == "invalid-abi-minor") {
        replace_once(value, "\"minimumAbiMinor\":13", "\"minimumAbiMinor\":12");
    } else {
        throw std::runtime_error("unknown JSON mutation");
    }
    const auto output = temporary.path / "sdk-compatibility.json";
    std::ofstream(output, std::ios::binary).write(value.data(), static_cast<std::streamsize>(value.size()));
    return output;
}

int resolved(
    const std::filesystem::path& library,
    const std::filesystem::path& compatibility,
    const std::filesystem::path* external) {
    if (external) codex_agent::CodexNativeLibrary::configure(*external);
    auto* raw = codex_agent::detail::resolve_native_symbol(
        codex_agent::detail::NativeSymbol::s000,
        library.string(), compatibility.string());
    return reinterpret_cast<AbiCompatible>(raw)(0x00010000u) == 1 ? 0 : 1;
}

int execute(
    const std::filesystem::path& library,
    const std::filesystem::path& compatibility,
    std::string_view mode,
    const std::filesystem::path* external) {
    TemporaryDirectory temporary;
    if (mode == "parent-symlink-library" || mode == "final-symlink-library") {
        const auto real = temporary.path / "real";
        std::filesystem::create_directory(real);
        const auto copy = real / library.filename();
        std::filesystem::copy_file(library, copy);
        if (mode == "parent-symlink-library") {
            const auto alias = temporary.path / "alias";
            std::filesystem::create_directory_symlink(real, alias);
            return resolved(alias / library.filename(), compatibility, nullptr);
        }
        const auto alias = temporary.path / library.filename();
        std::filesystem::create_symlink(copy, alias);
        return resolved(alias, compatibility, nullptr);
    }
    if (mode == "parent-symlink-compatibility" || mode == "final-symlink-compatibility") {
        const auto real = temporary.path / "real";
        std::filesystem::create_directory(real);
        const auto copy = real / compatibility.filename();
        std::filesystem::copy_file(compatibility, copy);
        if (mode == "parent-symlink-compatibility") {
            const auto alias = temporary.path / "alias";
            std::filesystem::create_directory_symlink(real, alias);
            return resolved(library, alias / compatibility.filename(), nullptr);
        }
        const auto alias = temporary.path / compatibility.filename();
        std::filesystem::create_symlink(copy, alias);
        return resolved(library, alias, nullptr);
    }
    if (mode == "snapshot-aba") {
        loader_test_hook::attempted = false;
        loader_test_hook::changed = false;
        codex_agent::detail::set_native_loader_test_hook(
            loader_test_hook::reject_ordinary_snapshot_replacement);
        try {
            const auto result = resolved(library, compatibility, external);
            codex_agent::detail::set_native_loader_test_hook(nullptr);
            if (!loader_test_hook::attempted || loader_test_hook::changed) {
                throw std::runtime_error("snapshot owner controls did not reject ordinary ABA");
            }
            return result;
        } catch (...) {
            codex_agent::detail::set_native_loader_test_hook(nullptr);
            throw;
        }
    }
    if (mode == "source-aba") {
        const auto changing = temporary.path / library.filename();
        std::filesystem::copy_file(library, changing);
        {
            std::ofstream padding(changing, std::ios::binary | std::ios::app);
            const std::string block(1024 * 1024, '\0');
            for (int index = 0; index < 64; ++index) padding.write(block.data(), block.size());
        }
        std::atomic_bool stop{};
        std::thread mutator([&] {
            char byte = 0;
            while (!stop.load()) {
                std::fstream file(changing, std::ios::binary | std::ios::in | std::ios::out);
                file.seekp(-1, std::ios::end);
                byte ^= 1;
                file.write(&byte, 1);
                file.flush();
            }
        });
        try {
            const auto result = resolved(library, compatibility, &changing);
            stop = true;
            mutator.join();
            return result;
        } catch (...) {
            stop = true;
            mutator.join();
            throw;
        }
    }
    if (mode == "noncanonical-json" || mode == "reordered-json" ||
        mode == "duplicate-json-key" || mode == "reordered-variants" ||
        mode == "duplicate-component" || mode == "duplicate-manifest" ||
        mode == "invalid-sdk-version" || mode == "invalid-sdk-prerelease" ||
        mode == "valid-sdk-prerelease" || mode == "invalid-identity-schema" ||
        mode == "invalid-abi-major" || mode == "invalid-abi-minor") {
        return resolved(library, mutated_compatibility(compatibility, mode, temporary), external);
    }
    return resolved(library, compatibility, external);
}
}

int main(int argc, char** argv) {
    if (argc < 4 || argc > 5) return 64;
    const auto mode = std::string_view(argv[3]);
    const auto expect_success = mode == "success" || mode == "external-component" ||
        mode == "valid-sdk-prerelease" || mode == "snapshot-aba";
    const std::filesystem::path external = argc == 5 ? argv[4] : "";
    try {
        const auto result = execute(argv[1], argv[2], mode, argc == 5 ? &external : nullptr);
        if (!expect_success) {
            std::cerr << "loader unexpectedly accepted incompatible input\n";
            return 1;
        }
        return result;
    } catch (const std::exception& error) {
        if (expect_success) {
            std::cerr << error.what() << '\n';
            return 1;
        }
        return 0;
    }
}
