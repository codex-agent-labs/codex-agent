#include "codex_agent.h"

#include <cstdlib>
#include <cstring>
#include <type_traits>
#include <vector>

using AbiVersionFunction = uint32_t (CODEX_AGENT_CALL *)(void);
using AbiCompatibilityFunction = int32_t (CODEX_AGENT_CALL *)(uint32_t);
using RuntimeIdentityFunction = codex_agent_status_t (CODEX_AGENT_CALL *)(char *, size_t *);
using ContextFunction = codex_agent_status_t (CODEX_AGENT_CALL *)(codex_agent_context_t **);

static_assert(CODEX_AGENT_ABI_VERSION_CURRENT == UINT32_C(0x010D0000));
static_assert(CODEX_AGENT_ABI_VERSION_MINIMUM_COMPATIBLE == UINT32_C(0x01000000));
static_assert(std::is_same_v<codex_agent_status_t, int32_t>);
static_assert(std::is_same_v<decltype(&codex_agent_abi_version), AbiVersionFunction>);
static_assert(std::is_same_v<decltype(&codex_agent_abi_is_compatible), AbiCompatibilityFunction>);
static_assert(std::is_same_v<decltype(&codex_agent_runtime_identity), RuntimeIdentityFunction>);
static_assert(std::is_same_v<decltype(&codex_agent_context_create), ContextFunction>);
static_assert(std::is_same_v<decltype(&codex_agent_context_destroy), ContextFunction>);

#define CHECK(condition) do { if (!(condition)) std::abort(); } while (false)

int main() {
    codex_agent_context_t *first = nullptr;
    codex_agent_context_t *second = nullptr;
    std::size_t identity_size = 0;

    CHECK(codex_agent_abi_version() == CODEX_AGENT_ABI_VERSION_CURRENT);
    CHECK(codex_agent_abi_is_compatible(CODEX_AGENT_ABI_VERSION_MINIMUM_COMPATIBLE) != 0);
    CHECK(codex_agent_abi_is_compatible(CODEX_AGENT_ABI_VERSION_CURRENT) != 0);
    CHECK(codex_agent_abi_is_compatible(
        CODEX_AGENT_ABI_VERSION_MINIMUM_COMPATIBLE - UINT32_C(1)) == 0);
    CHECK(codex_agent_abi_is_compatible(CODEX_AGENT_ABI_VERSION_CURRENT + UINT32_C(1)) == 0);
    CHECK(codex_agent_abi_is_compatible(CODEX_AGENT_ABI_VERSION_ENCODE(2, 0, 0)) == 0);
    CHECK(codex_agent_runtime_identity(nullptr, nullptr) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_runtime_identity(nullptr, &identity_size) == CODEX_AGENT_STATUS_BUFFER_TOO_SMALL);
    std::vector<char> identity(identity_size);
    CHECK(codex_agent_runtime_identity(identity.data(), &identity_size) == CODEX_AGENT_STATUS_OK);
    CHECK(std::strlen(identity.data()) + 1 == identity_size);

    CHECK(codex_agent_context_create(&first) == CODEX_AGENT_STATUS_OK);
    CHECK(codex_agent_context_create(&second) == CODEX_AGENT_STATUS_OK);
    CHECK(first != nullptr);
    CHECK(second != nullptr);
    CHECK(first != second);

    CHECK(codex_agent_context_destroy(&first) == CODEX_AGENT_STATUS_OK);
    CHECK(first == nullptr);
    CHECK(second != nullptr);
    CHECK(codex_agent_context_destroy(&second) == CODEX_AGENT_STATUS_OK);
    CHECK(second == nullptr);

    return EXIT_SUCCESS;
}
