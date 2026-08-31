find_package(Threads REQUIRED)

if(NOT CodexAgent_C_SDK_LIBRARY)
    message(FATAL_ERROR
        "C++ parity tests require the verified native C SDK library"
    )
endif()

add_library(codex_agent_mock STATIC mock_codex_agent.cpp)
target_compile_features(codex_agent_mock PRIVATE cxx_std_20)
target_compile_definitions(codex_agent_mock PRIVATE CODEX_AGENT_BUILD)
target_include_directories(codex_agent_mock PRIVATE "${CodexAgent_C_SDK_INCLUDE_DIR}")
target_link_libraries(codex_agent_mock PRIVATE Threads::Threads)

add_executable(codex_agent_cpp_test wrapper_test.cpp)
target_link_libraries(
    codex_agent_cpp_test
    PRIVATE CodexAgent::CodexAgent codex_agent_mock Threads::Threads
)
if(MSVC)
    target_compile_options(codex_agent_mock PRIVATE /W4 /WX)
    target_compile_options(codex_agent_cpp_test PRIVATE /W4 /WX)
else()
    target_compile_options(codex_agent_mock PRIVATE -Wall -Wextra -Wpedantic -Werror)
    target_compile_options(codex_agent_cpp_test PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
add_test(NAME codex_agent_cpp_test COMMAND codex_agent_cpp_test)

add_executable(codex_agent_cpp_conversation_test conversation_behavior_test.cpp)
target_link_libraries(
    codex_agent_cpp_conversation_test
    PRIVATE CodexAgent::CodexAgent codex_agent_mock Threads::Threads
)
if(MSVC)
    target_compile_options(codex_agent_cpp_conversation_test PRIVATE /W4 /WX)
else()
    target_compile_options(
        codex_agent_cpp_conversation_test
        PRIVATE -Wall -Wextra -Wpedantic -Werror
    )
endif()
set(CODEX_AGENT_CPP_CONVERSATION_RECEIPT
    "${CMAKE_BINARY_DIR}/parity/conversation-executed-tests.tsv")
add_test(
    NAME codex_agent_cpp_conversation_test
    COMMAND
        codex_agent_cpp_conversation_test
        "${CODEX_AGENT_CPP_CONVERSATION_RECEIPT}"
)

add_executable(
    codex_agent_cpp_conversation_real_test conversation_real_boundary_test.cpp
)
target_link_libraries(
    codex_agent_cpp_conversation_real_test PRIVATE CodexAgent::CodexAgent
)
if(MSVC)
    target_compile_options(
        codex_agent_cpp_conversation_real_test PRIVATE /W4 /WX
    )
else()
    target_compile_options(
        codex_agent_cpp_conversation_real_test
        PRIVATE -Wall -Wextra -Wpedantic -Werror
    )
endif()
set(CODEX_AGENT_CPP_CONVERSATION_REAL_RECEIPT
    "${CMAKE_BINARY_DIR}/parity/conversation-real-boundaries.tsv")
add_test(
    NAME codex_agent_cpp_conversation_real_test
    COMMAND
        codex_agent_cpp_conversation_real_test
        "${CODEX_AGENT_CPP_CONVERSATION_REAL_RECEIPT}"
)

add_library(codex_agent_agent_mock STATIC agent_mock.cpp)
target_compile_features(codex_agent_agent_mock PRIVATE cxx_std_20)
target_compile_definitions(codex_agent_agent_mock PRIVATE CODEX_AGENT_BUILD)
target_include_directories(
    codex_agent_agent_mock PRIVATE "${CodexAgent_C_SDK_INCLUDE_DIR}"
)

add_executable(codex_agent_cpp_agent_test agent_behavior_test.cpp)
target_link_libraries(
    codex_agent_cpp_agent_test
    PRIVATE CodexAgent::CodexAgent codex_agent_agent_mock
)
add_executable(codex_agent_cpp_agent_real_test agent_real_boundary_test.cpp)
target_link_libraries(
    codex_agent_cpp_agent_real_test PRIVATE CodexAgent::CodexAgent
)
if(MSVC)
    target_compile_options(codex_agent_agent_mock PRIVATE /W4 /WX)
    target_compile_options(codex_agent_cpp_agent_test PRIVATE /W4 /WX)
    target_compile_options(codex_agent_cpp_agent_real_test PRIVATE /W4 /WX)
else()
    target_compile_options(
        codex_agent_agent_mock PRIVATE -Wall -Wextra -Wpedantic -Werror
    )
    target_compile_options(
        codex_agent_cpp_agent_test PRIVATE -Wall -Wextra -Wpedantic -Werror
    )
    target_compile_options(
        codex_agent_cpp_agent_real_test PRIVATE -Wall -Wextra -Wpedantic -Werror
    )
endif()
set(CODEX_AGENT_CPP_AGENT_RECEIPT
    "${CMAKE_BINARY_DIR}/parity/agent-executed-tests.tsv")
set(CODEX_AGENT_CPP_AGENT_REAL_RECEIPT
    "${CMAKE_BINARY_DIR}/parity/agent-real-boundaries.tsv")
add_test(
    NAME codex_agent_cpp_agent_test
    COMMAND codex_agent_cpp_agent_test "${CODEX_AGENT_CPP_AGENT_RECEIPT}"
)
add_test(
    NAME codex_agent_cpp_agent_real_test
    COMMAND
        codex_agent_cpp_agent_real_test
        "${CODEX_AGENT_CPP_AGENT_REAL_RECEIPT}"
)

add_library(codex_agent_host_mock STATIC host_mock.cpp)
target_compile_features(codex_agent_host_mock PRIVATE cxx_std_20)
target_compile_definitions(codex_agent_host_mock PRIVATE CODEX_AGENT_BUILD)
target_include_directories(
    codex_agent_host_mock PRIVATE "${CodexAgent_C_SDK_INCLUDE_DIR}"
)
target_link_libraries(codex_agent_host_mock PRIVATE Threads::Threads)

add_executable(codex_agent_cpp_host_test host_behavior_test.cpp)
target_link_libraries(
    codex_agent_cpp_host_test
    PRIVATE CodexAgent::CodexAgent codex_agent_host_mock Threads::Threads
)
add_executable(codex_agent_cpp_host_real_test host_real_boundary_test.cpp)
target_link_libraries(
    codex_agent_cpp_host_real_test PRIVATE CodexAgent::CodexAgent
)
if(MSVC)
    target_compile_options(codex_agent_host_mock PRIVATE /W4 /WX)
    target_compile_options(codex_agent_cpp_host_test PRIVATE /W4 /WX)
    target_compile_options(codex_agent_cpp_host_real_test PRIVATE /W4 /WX)
else()
    target_compile_options(
        codex_agent_host_mock PRIVATE -Wall -Wextra -Wpedantic -Werror
    )
    target_compile_options(
        codex_agent_cpp_host_test PRIVATE -Wall -Wextra -Wpedantic -Werror
    )
    target_compile_options(
        codex_agent_cpp_host_real_test PRIVATE -Wall -Wextra -Wpedantic -Werror
    )
endif()
set(CODEX_AGENT_CPP_HOST_RECEIPT
    "${CMAKE_BINARY_DIR}/parity/host-executed-tests.tsv")
set(CODEX_AGENT_CPP_HOST_REAL_RECEIPT
    "${CMAKE_BINARY_DIR}/parity/host-real-boundaries.tsv")
add_test(
    NAME codex_agent_cpp_host_test
    COMMAND codex_agent_cpp_host_test "${CODEX_AGENT_CPP_HOST_RECEIPT}"
)
add_test(
    NAME codex_agent_cpp_host_real_test
    COMMAND
        codex_agent_cpp_host_real_test
        "${CODEX_AGENT_CPP_HOST_REAL_RECEIPT}"
)

add_library(codex_agent_leaf_mock STATIC leaf_mock.cpp)
target_compile_features(codex_agent_leaf_mock PRIVATE cxx_std_20)
target_compile_definitions(codex_agent_leaf_mock PRIVATE CODEX_AGENT_BUILD)
target_include_directories(
    codex_agent_leaf_mock PRIVATE "${CodexAgent_C_SDK_INCLUDE_DIR}"
)
target_link_libraries(codex_agent_leaf_mock PRIVATE Threads::Threads)

add_executable(codex_agent_cpp_leaf_test leaf_behavior_test.cpp)
target_link_libraries(
    codex_agent_cpp_leaf_test
    PRIVATE CodexAgent::CodexAgent codex_agent_leaf_mock Threads::Threads
)

add_executable(codex_agent_cpp_leaf_real_test leaf_real_boundary_test.cpp)
target_link_libraries(
    codex_agent_cpp_leaf_real_test PRIVATE CodexAgent::CodexAgent
)
if(MSVC)
    target_compile_options(codex_agent_leaf_mock PRIVATE /W4 /WX)
    target_compile_options(codex_agent_cpp_leaf_test PRIVATE /W4 /WX)
    target_compile_options(codex_agent_cpp_leaf_real_test PRIVATE /W4 /WX)
else()
    target_compile_options(
        codex_agent_leaf_mock PRIVATE -Wall -Wextra -Wpedantic -Werror
    )
    target_compile_options(
        codex_agent_cpp_leaf_test PRIVATE -Wall -Wextra -Wpedantic -Werror
    )
    target_compile_options(
        codex_agent_cpp_leaf_real_test PRIVATE -Wall -Wextra -Wpedantic -Werror
    )
endif()
set(CODEX_AGENT_CPP_LEAF_RECEIPT
    "${CMAKE_BINARY_DIR}/parity/leaf-executed-tests.tsv")
set(CODEX_AGENT_CPP_LEAF_REAL_RECEIPT
    "${CMAKE_BINARY_DIR}/parity/leaf-real-boundaries.tsv")
add_test(
    NAME codex_agent_cpp_leaf_test
    COMMAND codex_agent_cpp_leaf_test "${CODEX_AGENT_CPP_LEAF_RECEIPT}"
)
add_test(
    NAME codex_agent_cpp_leaf_real_test
    COMMAND codex_agent_cpp_leaf_real_test "${CODEX_AGENT_CPP_LEAF_REAL_RECEIPT}"
)
set_tests_properties(
    codex_agent_cpp_conversation_real_test
    codex_agent_cpp_agent_real_test
    codex_agent_cpp_host_real_test
    codex_agent_cpp_leaf_real_test
    PROPERTIES RESOURCE_LOCK codex_agent_real_sdk
)

if(NOT EXISTS "${CodexAgent_CANONICAL_API_REPORT}" OR IS_DIRECTORY "${CodexAgent_CANONICAL_API_REPORT}")
    message(FATAL_ERROR
        "C++ parity tests require the canonical API report: ${CodexAgent_CANONICAL_API_REPORT}"
    )
endif()
if(NOT EXISTS "${CodexAgent_C_ABI_BOOTSTRAP_EVIDENCE}" OR IS_DIRECTORY "${CodexAgent_C_ABI_BOOTSTRAP_EVIDENCE}")
    message(FATAL_ERROR
        "C++ parity tests require C ABI bootstrap evidence: ${CodexAgent_C_ABI_BOOTSTRAP_EVIDENCE}"
    )
endif()
add_executable(codex_agent_cpp_enum_test enum_parity_test.cpp)
target_link_libraries(codex_agent_cpp_enum_test PRIVATE CodexAgent::CodexAgent)
if(MSVC)
    target_compile_options(codex_agent_cpp_enum_test PRIVATE /W4 /WX)
else()
    target_compile_options(codex_agent_cpp_enum_test PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
add_test(
    NAME codex_agent_cpp_enum_test
    COMMAND
        codex_agent_cpp_enum_test
        "${CMAKE_CURRENT_SOURCE_DIR}/../parity/capability-claims.tsv"
        "${CodexAgent_CANONICAL_API_REPORT}"
        "${CMAKE_BINARY_DIR}/parity"
)

add_executable(codex_agent_cpp_value_test value_parity_test.cpp)
target_link_libraries(codex_agent_cpp_value_test PRIVATE CodexAgent::CodexAgent)
if(MSVC)
    target_compile_options(codex_agent_cpp_value_test PRIVATE /W4 /WX)
else()
    target_compile_options(codex_agent_cpp_value_test PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
add_test(
    NAME codex_agent_cpp_value_test
    COMMAND
        codex_agent_cpp_value_test
        "${CMAKE_CURRENT_SOURCE_DIR}/../parity/capability-claims.tsv"
        "${CodexAgent_CANONICAL_API_REPORT}"
        "${CodexAgent_C_ABI_BOOTSTRAP_EVIDENCE}"
        "${CMAKE_BINARY_DIR}/parity"
        "${CODEX_AGENT_CPP_LEAF_RECEIPT}"
        "${CODEX_AGENT_CPP_LEAF_REAL_RECEIPT}"
        "${CODEX_AGENT_CPP_CONVERSATION_RECEIPT}"
        "${CODEX_AGENT_CPP_CONVERSATION_REAL_RECEIPT}"
        "${CODEX_AGENT_CPP_AGENT_RECEIPT}"
        "${CODEX_AGENT_CPP_AGENT_REAL_RECEIPT}"
        "${CODEX_AGENT_CPP_HOST_RECEIPT}"
        "${CODEX_AGENT_CPP_HOST_REAL_RECEIPT}"
)
set_tests_properties(
    codex_agent_cpp_value_test
    PROPERTIES DEPENDS "codex_agent_cpp_leaf_test;codex_agent_cpp_leaf_real_test;codex_agent_cpp_conversation_test;codex_agent_cpp_conversation_real_test;codex_agent_cpp_agent_test;codex_agent_cpp_agent_real_test;codex_agent_cpp_host_test;codex_agent_cpp_host_real_test"
)
