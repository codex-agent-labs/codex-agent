#include <stdint.h>

#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif

API uint32_t codex_agent_abi_version(void) { return (1u << 24); }
API int32_t codex_agent_abi_is_compatible(uint32_t requested) {
    (void)requested;
    return 0;
}
