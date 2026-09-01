#include <codex_agent.h>

#include <algorithm>
#include <cstring>
#include <string_view>

#ifndef CODEX_AGENT_FIXTURE_COMPONENT
#define CODEX_AGENT_FIXTURE_COMPONENT "2222222222222222222222222222222222222222222222222222222222222222"
#endif
#ifndef CODEX_AGENT_FIXTURE_ABI
#define CODEX_AGENT_FIXTURE_ABI "1.13.0"
#endif
#ifndef CODEX_AGENT_FIXTURE_TARGET
#define CODEX_AGENT_FIXTURE_TARGET "macos-arm64"
#endif
#ifndef CODEX_AGENT_FIXTURE_CONTRACT
#define CODEX_AGENT_FIXTURE_CONTRACT "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
#endif
#ifndef CODEX_AGENT_FIXTURE_ACTUAL_ABI_MAJOR
#define CODEX_AGENT_FIXTURE_ACTUAL_ABI_MAJOR 1
#endif
#ifndef CODEX_AGENT_FIXTURE_ACTUAL_ABI_MINOR
#define CODEX_AGENT_FIXTURE_ACTUAL_ABI_MINOR 13
#endif
#ifndef CODEX_AGENT_FIXTURE_ACTUAL_ABI_PATCH
#define CODEX_AGENT_FIXTURE_ACTUAL_ABI_PATCH 0
#endif

namespace {
constexpr std::string_view identity =
    "{\"appServerVersion\":\"0.149.0\","
    "\"buildInputDigest\":\"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee\","
    "\"cAbiVersion\":\"" CODEX_AGENT_FIXTURE_ABI "\","
    "\"componentId\":\"sha256:" CODEX_AGENT_FIXTURE_COMPONENT "\","
    "\"contractComponentDigest\":\"sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff\","
    "\"contractDigest\":\"sha256:" CODEX_AGENT_FIXTURE_CONTRACT "\","
    "\"runtimeCompatibilityVersion\":\"0.2.0\","
    "\"schemaVersion\":1,\"target\":\"" CODEX_AGENT_FIXTURE_TARGET "\"}";
}

extern "C" {

#ifndef CODEX_AGENT_FIXTURE_NO_IDENTITY
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL
codex_agent_runtime_identity(char* buffer, std::size_t* inout_size) {
    if (!inout_size) return CODEX_AGENT_STATUS_INVALID_ARGUMENT;
    const auto required = identity.size() + 1;
    const auto capacity = *inout_size;
    *inout_size = required;
    if (!buffer || capacity < required) return CODEX_AGENT_STATUS_BUFFER_TOO_SMALL;
    std::copy(identity.begin(), identity.end(), buffer);
    buffer[identity.size()] = '\0';
    return CODEX_AGENT_STATUS_OK;
}
#endif

CODEX_AGENT_API std::int32_t CODEX_AGENT_CALL
codex_agent_abi_is_compatible(std::uint32_t) {
    return 1;
}

CODEX_AGENT_API std::uint32_t CODEX_AGENT_CALL codex_agent_abi_version() {
    return CODEX_AGENT_ABI_VERSION_ENCODE(
        CODEX_AGENT_FIXTURE_ACTUAL_ABI_MAJOR,
        CODEX_AGENT_FIXTURE_ACTUAL_ABI_MINOR,
        CODEX_AGENT_FIXTURE_ACTUAL_ABI_PATCH);
}

}
