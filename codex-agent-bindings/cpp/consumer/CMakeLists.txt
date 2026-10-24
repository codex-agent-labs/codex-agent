cmake_minimum_required(VERSION 3.24)

project(CodexAgentConsumer LANGUAGES CXX)

find_package(CodexAgent CONFIG REQUIRED)
find_package(Threads REQUIRED)
enable_testing()

file(GLOB_RECURSE CODEX_AGENT_INSTALLED_PUBLIC_HEADERS
    "${CodexAgent_C_SDK_INCLUDE_DIR}/*.h"
    "${CodexAgent_C_SDK_INCLUDE_DIR}/*.hpp"
)
foreach(forbidden
    "AgentFactory"
    "HostFactory"
    "ConversationFactory"
    "LeafServicesFactory"
    "_for_testing"
)
    foreach(header IN LISTS CODEX_AGENT_INSTALLED_PUBLIC_HEADERS)
        file(READ "${header}" CODEX_AGENT_INSTALLED_PUBLIC_HEADER)
        string(FIND
            "${CODEX_AGENT_INSTALLED_PUBLIC_HEADER}"
            "${forbidden}"
            CODEX_AGENT_FORBIDDEN_TEST_SEAM
        )
        if(NOT CODEX_AGENT_FORBIDDEN_TEST_SEAM EQUAL -1)
            message(FATAL_ERROR
                "Installed public header ${header} exposes test seam: ${forbidden}"
            )
        endif()
    endforeach()
endforeach()

add_executable(codex_agent_consumer main.cpp)
target_link_libraries(codex_agent_consumer PRIVATE CodexAgent::CodexAgent)

add_executable(codex_agent_host_smoke host_smoke.cpp)
target_compile_definitions(
    codex_agent_host_smoke
    PRIVATE CODEX_AGENT_VERIFIED_LIBRARY_PATH="${CodexAgent_C_SDK_LIBRARY}"
)
target_link_libraries(codex_agent_host_smoke PRIVATE CodexAgent::CodexAgent)
if(MSVC)
    target_compile_options(codex_agent_host_smoke PRIVATE /W4 /WX)
else()
    target_compile_options(
        codex_agent_host_smoke PRIVATE -Wall -Wextra -Wpedantic -Werror
    )
endif()
add_test(
    NAME codex_agent_installed_host_smoke
    COMMAND codex_agent_host_smoke "${CodexAgent_C_SDK_LIBRARY}"
)

add_executable(
    codex_agent_leaf_consumer
    ../tests/leaf_behavior_test.cpp
    ../tests/leaf_mock.cpp
)
target_compile_definitions(codex_agent_leaf_consumer PRIVATE CODEX_AGENT_BUILD)
target_compile_definitions(codex_agent_leaf_consumer PRIVATE CODEX_AGENT_CPP_STATIC_TEST_DISPATCH)
target_link_libraries(
    codex_agent_leaf_consumer
    PRIVATE CodexAgent::CodexAgent CodexAgent::C Threads::Threads
)
if(MSVC)
    target_compile_options(codex_agent_leaf_consumer PRIVATE /W4 /WX)
else()
    target_compile_options(
        codex_agent_leaf_consumer PRIVATE -Wall -Wextra -Wpedantic -Werror
    )
endif()
add_test(
    NAME codex_agent_installed_leaf_consumer
    COMMAND
        codex_agent_leaf_consumer
        "${CMAKE_BINARY_DIR}/leaf-installed-consumer.tsv"
)

add_executable(
    codex_agent_conversation_consumer
    ../tests/conversation_behavior_test.cpp
    ../tests/mock_codex_agent.cpp
)
target_compile_definitions(
    codex_agent_conversation_consumer PRIVATE CODEX_AGENT_BUILD CODEX_AGENT_CPP_STATIC_TEST_DISPATCH
)
target_link_libraries(
    codex_agent_conversation_consumer
    PRIVATE CodexAgent::CodexAgent CodexAgent::C Threads::Threads
)
if(MSVC)
    target_compile_options(codex_agent_conversation_consumer PRIVATE /W4 /WX)
else()
    target_compile_options(
        codex_agent_conversation_consumer
        PRIVATE -Wall -Wextra -Wpedantic -Werror
    )
endif()
add_test(
    NAME codex_agent_installed_conversation_consumer
    COMMAND
        codex_agent_conversation_consumer
        "${CMAKE_BINARY_DIR}/conversation-installed-consumer.tsv"
)

add_executable(
    codex_agent_lifecycle_example
    lifecycle_example.cpp
    ../tests/mock_codex_agent.cpp
)
target_compile_definitions(
    codex_agent_lifecycle_example PRIVATE CODEX_AGENT_BUILD CODEX_AGENT_CPP_STATIC_TEST_DISPATCH
)
target_link_libraries(
    codex_agent_lifecycle_example
    PRIVATE CodexAgent::CodexAgent CodexAgent::C Threads::Threads
)
if(MSVC)
    target_compile_options(codex_agent_lifecycle_example PRIVATE /W4 /WX)
else()
    target_compile_options(
        codex_agent_lifecycle_example PRIVATE -Wall -Wextra -Wpedantic -Werror
    )
endif()
add_test(
    NAME codex_agent_installed_lifecycle_example
    COMMAND codex_agent_lifecycle_example
)

add_executable(
    codex_agent_agent_consumer
    ../tests/agent_behavior_test.cpp
    ../tests/agent_mock.cpp
)
target_compile_definitions(
    codex_agent_agent_consumer PRIVATE CODEX_AGENT_BUILD CODEX_AGENT_CPP_STATIC_TEST_DISPATCH
)
target_link_libraries(
    codex_agent_agent_consumer PRIVATE CodexAgent::CodexAgent CodexAgent::C
)
if(MSVC)
    target_compile_options(codex_agent_agent_consumer PRIVATE /W4 /WX)
else()
    target_compile_options(
        codex_agent_agent_consumer PRIVATE -Wall -Wextra -Wpedantic -Werror
    )
endif()
add_test(
    NAME codex_agent_installed_agent_consumer
    COMMAND
        codex_agent_agent_consumer
        "${CMAKE_BINARY_DIR}/agent-installed-consumer.tsv"
)

add_executable(
    codex_agent_host_consumer
    ../tests/host_behavior_test.cpp
    ../tests/host_mock.cpp
)
target_compile_definitions(
    codex_agent_host_consumer PRIVATE CODEX_AGENT_BUILD CODEX_AGENT_CPP_STATIC_TEST_DISPATCH
)
target_link_libraries(
    codex_agent_host_consumer
    PRIVATE CodexAgent::CodexAgent CodexAgent::C Threads::Threads
)
if(MSVC)
    target_compile_options(codex_agent_host_consumer PRIVATE /W4 /WX)
else()
    target_compile_options(
        codex_agent_host_consumer PRIVATE -Wall -Wextra -Wpedantic -Werror
    )
endif()
add_test(
    NAME codex_agent_installed_host_consumer
    COMMAND
        codex_agent_host_consumer
        "${CMAKE_BINARY_DIR}/host-installed-consumer.tsv"
)
