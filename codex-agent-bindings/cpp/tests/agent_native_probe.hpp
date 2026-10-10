#pragma once

#include <cstddef>

enum class AgentNativeEdge {
#define AGENT_NATIVE_SYMBOL(function) function,
#include "agent_native_symbols.inc"
#undef AGENT_NATIVE_SYMBOL
};

void codex_agent_cpp_mock_agent_reset();
std::size_t codex_agent_cpp_mock_agent_event_count();
AgentNativeEdge codex_agent_cpp_mock_agent_event_at(std::size_t index);
