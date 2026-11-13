#pragma once

#include <codex_agent.h>

#include <filesystem>
#include <string_view>
#include <utility>

namespace codex_agent {

class CodexNativeLibrary final {
public:
    static void configure(const std::filesystem::path& absolute_library_path);
};

namespace detail {

enum class NativeSymbol {
#define CODEX_AGENT_NATIVE_SYMBOL(id, name) id,
#include <codex_agent/native_symbols.inc>
#undef CODEX_AGENT_NATIVE_SYMBOL
};

void* resolve_native_symbol(
    NativeSymbol symbol,
    std::string_view default_library_path,
    std::string_view compatibility_path);

template <typename Function, NativeSymbol Symbol>
struct NativeEntry;

template <typename Result, typename... Args, NativeSymbol Symbol>
struct NativeEntry<Result(CODEX_AGENT_CALL*)(Args...), Symbol> {
    static Result CODEX_AGENT_CALL call(Args... args) {
        using Function = Result(CODEX_AGENT_CALL*)(Args...);
        const auto raw = resolve_native_symbol(
            Symbol,
#ifdef CODEX_AGENT_CPP_DEFAULT_LIBRARY_PATH
            CODEX_AGENT_CPP_DEFAULT_LIBRARY_PATH,
#else
            {},
#endif
#ifdef CODEX_AGENT_CPP_COMPATIBILITY_PATH
            CODEX_AGENT_CPP_COMPATIBILITY_PATH
#else
            {}
#endif
        );
        return reinterpret_cast<Function>(raw)(std::forward<Args>(args)...);
    }
};

}  // namespace detail
}  // namespace codex_agent
