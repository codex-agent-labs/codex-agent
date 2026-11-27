#pragma once

#include <cstddef>

enum class HostNativeEdge {
#define HOST_NATIVE_SYMBOL(function) function,
#include "host_native_symbols.inc"
#undef HOST_NATIVE_SYMBOL
};

void codex_agent_cpp_mock_host_reset();
std::size_t codex_agent_cpp_mock_host_event_count();
HostNativeEdge codex_agent_cpp_mock_host_event_at(std::size_t index);
