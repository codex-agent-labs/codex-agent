#pragma once

#include <cstddef>

enum class ConversationNativeEdge {
#define CONVERSATION_NATIVE_SYMBOL(function) function,
#include "conversation_native_symbols.inc"
#undef CONVERSATION_NATIVE_SYMBOL
};

void codex_agent_cpp_mock_conversation_reset();
std::size_t codex_agent_cpp_mock_conversation_event_count();
ConversationNativeEdge codex_agent_cpp_mock_conversation_event_at(
    std::size_t index);
void codex_agent_cpp_mock_conversation_delay_next_operation();
void codex_agent_cpp_mock_conversation_complete_pending_operation();
void codex_agent_cpp_mock_conversation_set_failure();
void codex_agent_cpp_mock_conversation_set_phase(int kind, int phase);
void codex_agent_cpp_mock_conversation_publish(int kind, int terminal);
