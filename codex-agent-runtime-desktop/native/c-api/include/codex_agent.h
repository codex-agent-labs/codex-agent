#ifndef CODEX_AGENT_H
#define CODEX_AGENT_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#if defined(_WIN32)
#if defined(CODEX_AGENT_BUILD)
#define CODEX_AGENT_API __declspec(dllexport)
#else
#define CODEX_AGENT_API __declspec(dllimport)
#endif
#define CODEX_AGENT_CALL __cdecl
#else
#define CODEX_AGENT_API __attribute__((visibility("default")))
#define CODEX_AGENT_CALL
#endif

#define CODEX_AGENT_ABI_VERSION_MAJOR UINT32_C(1)
#define CODEX_AGENT_ABI_VERSION_MINOR UINT32_C(0)
#define CODEX_AGENT_ABI_VERSION_PATCH UINT32_C(0)
#define CODEX_AGENT_ABI_VERSION_ENCODE(major, minor, patch) \
    ((((uint32_t)(major) & UINT32_C(0xff)) << 24) | \
     (((uint32_t)(minor) & UINT32_C(0xff)) << 16) | \
     ((uint32_t)(patch) & UINT32_C(0xffff)))
#define CODEX_AGENT_ABI_VERSION_CURRENT \
    CODEX_AGENT_ABI_VERSION_ENCODE( \
        CODEX_AGENT_ABI_VERSION_MAJOR, \
        CODEX_AGENT_ABI_VERSION_MINOR, \
        CODEX_AGENT_ABI_VERSION_PATCH)
#define CODEX_AGENT_ABI_VERSION_MINIMUM_COMPATIBLE \
    CODEX_AGENT_ABI_VERSION_ENCODE(1, 0, 0)

typedef int32_t codex_agent_status_t;

#define CODEX_AGENT_STATUS_OK INT32_C(0)
#define CODEX_AGENT_STATUS_INVALID_ARGUMENT INT32_C(1)
#define CODEX_AGENT_STATUS_OUT_OF_MEMORY INT32_C(2)
#define CODEX_AGENT_STATUS_STALE_HANDLE INT32_C(3)
#define CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE INT32_C(4)
#define CODEX_AGENT_STATUS_WRONG_CONTEXT INT32_C(5)
#define CODEX_AGENT_STATUS_BUSY INT32_C(6)
#define CODEX_AGENT_STATUS_CANCELLED INT32_C(7)
#define CODEX_AGENT_STATUS_INTERNAL_ERROR INT32_C(8)
#define CODEX_AGENT_STATUS_BUFFER_TOO_SMALL INT32_C(9)
#define CODEX_AGENT_STATUS_UNSUPPORTED_ABI INT32_C(10)
#define CODEX_AGENT_STATUS_CLOSED INT32_C(11)
#define CODEX_AGENT_STATUS_WOULD_DEADLOCK INT32_C(12)
#define CODEX_AGENT_STATUS_NOT_READY INT32_C(13)

typedef struct codex_agent_context codex_agent_context_t;

/*
 * ABI 1.x is backward compatible within major version 1. Additive minor and
 * patch releases accept every encoded version in the closed interval from
 * MINIMUM_COMPATIBLE through CURRENT.
 */
CODEX_AGENT_API uint32_t CODEX_AGENT_CALL codex_agent_abi_version(void);
CODEX_AGENT_API int32_t CODEX_AGENT_CALL codex_agent_abi_is_compatible(
    uint32_t requested_version);

/*
 * Creates an opaque context. The output slot must be non-null and initially
 * contain NULL. The returned pointer is uniquely owned and must not be copied.
 */
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_context_create(
    codex_agent_context_t **out_context);

/*
 * Destroys the context and writes NULL to the supplied slot. Calling this with
 * an already-null slot is successful. The slot must not be accessed
 * concurrently. Only the original output slot may be passed to this function;
 * use or destruction through a copied pointer is invalid caller behavior.
 */
CODEX_AGENT_API codex_agent_status_t CODEX_AGENT_CALL codex_agent_context_destroy(
    codex_agent_context_t **context);

#ifdef __cplusplus
}
#endif

#endif
