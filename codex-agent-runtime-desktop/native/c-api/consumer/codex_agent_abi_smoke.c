#include "codex_agent.h"

#include <stdlib.h>

_Static_assert(CODEX_AGENT_ABI_VERSION_MAJOR == UINT32_C(1), "ABI major changed");
_Static_assert(CODEX_AGENT_ABI_VERSION_MINOR == UINT32_C(6), "ABI minor changed");
_Static_assert(CODEX_AGENT_ABI_VERSION_PATCH == UINT32_C(0), "ABI patch changed");
_Static_assert(
    CODEX_AGENT_ABI_VERSION_CURRENT == UINT32_C(0x01060000),
    "current ABI encoding changed");
_Static_assert(
    CODEX_AGENT_ABI_VERSION_MINIMUM_COMPATIBLE == UINT32_C(0x01000000),
    "minimum compatible ABI changed");

_Static_assert(sizeof(codex_agent_status_t) == sizeof(int32_t), "status width changed");
_Static_assert(CODEX_AGENT_STATUS_OK == INT32_C(0), "OK status changed");
_Static_assert(CODEX_AGENT_STATUS_INVALID_ARGUMENT == INT32_C(1), "invalid-argument status changed");
_Static_assert(CODEX_AGENT_STATUS_OUT_OF_MEMORY == INT32_C(2), "out-of-memory status changed");
_Static_assert(CODEX_AGENT_STATUS_STALE_HANDLE == INT32_C(3), "stale-handle status changed");
_Static_assert(CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE == INT32_C(4), "wrong-handle-type status changed");
_Static_assert(CODEX_AGENT_STATUS_WRONG_CONTEXT == INT32_C(5), "wrong-context status changed");
_Static_assert(CODEX_AGENT_STATUS_BUSY == INT32_C(6), "busy status changed");
_Static_assert(CODEX_AGENT_STATUS_CANCELLED == INT32_C(7), "cancelled status changed");
_Static_assert(CODEX_AGENT_STATUS_INTERNAL_ERROR == INT32_C(8), "internal-error status changed");
_Static_assert(CODEX_AGENT_STATUS_BUFFER_TOO_SMALL == INT32_C(9), "buffer-too-small status changed");
_Static_assert(CODEX_AGENT_STATUS_UNSUPPORTED_ABI == INT32_C(10), "unsupported-ABI status changed");
_Static_assert(CODEX_AGENT_STATUS_CLOSED == INT32_C(11), "closed status changed");
_Static_assert(CODEX_AGENT_STATUS_WOULD_DEADLOCK == INT32_C(12), "would-deadlock status changed");
_Static_assert(CODEX_AGENT_STATUS_NOT_READY == INT32_C(13), "not-ready status changed");
_Static_assert(CODEX_AGENT_STATUS_OPERATION_FAILED == INT32_C(14), "operation-failed status changed");

#define CHECK(condition) do { if (!(condition)) abort(); } while (0)

int main(void) {
    codex_agent_context_t *context = NULL;
    CHECK(codex_agent_abi_version() == CODEX_AGENT_ABI_VERSION_CURRENT);
    CHECK(codex_agent_abi_is_compatible(CODEX_AGENT_ABI_VERSION_MINIMUM_COMPATIBLE) != 0);
    CHECK(codex_agent_abi_is_compatible(CODEX_AGENT_ABI_VERSION_CURRENT) != 0);
    CHECK(codex_agent_abi_is_compatible(
        CODEX_AGENT_ABI_VERSION_MINIMUM_COMPATIBLE - UINT32_C(1)) == 0);
    CHECK(codex_agent_abi_is_compatible(CODEX_AGENT_ABI_VERSION_CURRENT + UINT32_C(1)) == 0);
    CHECK(codex_agent_abi_is_compatible(CODEX_AGENT_ABI_VERSION_ENCODE(2, 0, 0)) == 0);

    CHECK(codex_agent_context_create(NULL) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(context != NULL);

    CHECK(codex_agent_context_create(&context) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);
    CHECK(context != NULL);

    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(context == NULL);
    CHECK(codex_agent_context_destroy(&context) == CODEX_AGENT_STATUS_OK);
    CHECK(context == NULL);
    CHECK(codex_agent_context_destroy(NULL) == CODEX_AGENT_STATUS_INVALID_ARGUMENT);

    return EXIT_SUCCESS;
}
