#pragma once

#include <cstddef>

enum class LeafNativeEdge {
#define LEAF_NATIVE_SYMBOL(function) function,
#include "leaf_native_symbols.inc"
#undef LEAF_NATIVE_SYMBOL
};

void codex_agent_cpp_mock_leaf_record(LeafNativeEdge edge);
std::size_t codex_agent_cpp_mock_leaf_event_count();
LeafNativeEdge codex_agent_cpp_mock_leaf_event_at(std::size_t index);
