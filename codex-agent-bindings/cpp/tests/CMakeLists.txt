find_package(Threads REQUIRED)
find_package(Python3 REQUIRED COMPONENTS Interpreter)

add_test(
    NAME codex_agent_native_dispatch_generated
    COMMAND "${Python3_EXECUTABLE}"
        "${CMAKE_CURRENT_SOURCE_DIR}/../tools/generate_native_dispatch.py"
        --header "${CodexAgent_C_SDK_INCLUDE_DIR}/codex_agent.h"
        --include "${CMAKE_CURRENT_SOURCE_DIR}/../include/codex_agent"
        --check
)

add_library(codex_agent_loader_valid SHARED native_loader_fixture.cpp)
add_library(codex_agent_loader_external SHARED native_loader_fixture.cpp)
target_compile_definitions(codex_agent_loader_external PRIVATE
    CODEX_AGENT_FIXTURE_COMPONENT="3333333333333333333333333333333333333333333333333333333333333333")
add_library(codex_agent_loader_old_abi SHARED native_loader_fixture.cpp)
target_compile_definitions(codex_agent_loader_old_abi PRIVATE
    CODEX_AGENT_FIXTURE_ABI="1.12.0" CODEX_AGENT_FIXTURE_ACTUAL_ABI_MINOR=12)
add_library(codex_agent_loader_abi_mismatch SHARED native_loader_fixture.cpp)
target_compile_definitions(codex_agent_loader_abi_mismatch PRIVATE
    CODEX_AGENT_FIXTURE_ACTUAL_ABI_MINOR=14)
add_library(codex_agent_loader_wrong_contract SHARED native_loader_fixture.cpp)
target_compile_definitions(codex_agent_loader_wrong_contract PRIVATE
    CODEX_AGENT_FIXTURE_CONTRACT="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
add_library(codex_agent_loader_missing_identity SHARED native_loader_fixture.cpp)
target_compile_definitions(codex_agent_loader_missing_identity PRIVATE
    CODEX_AGENT_FIXTURE_NO_IDENTITY)
if(CodexAgent_NATIVE_CLASSIFIER STREQUAL "windows-x64")
    set(CODEX_AGENT_WRONG_FIXTURE_TARGET "linux-x64")
else()
    set(CODEX_AGENT_WRONG_FIXTURE_TARGET "windows-x64")
endif()
add_library(codex_agent_loader_wrong_target SHARED native_loader_fixture.cpp)
foreach(fixture codex_agent_loader_valid codex_agent_loader_external codex_agent_loader_old_abi
        codex_agent_loader_abi_mismatch
        codex_agent_loader_wrong_contract codex_agent_loader_missing_identity)
    target_compile_features(${fixture} PRIVATE cxx_std_20)
    target_compile_definitions(${fixture} PRIVATE CODEX_AGENT_BUILD)
    target_compile_definitions(${fixture} PRIVATE
        CODEX_AGENT_FIXTURE_TARGET="${CodexAgent_NATIVE_CLASSIFIER}")
    target_include_directories(${fixture} PRIVATE "${CodexAgent_C_SDK_INCLUDE_DIR}")
endforeach()
target_compile_features(codex_agent_loader_wrong_target PRIVATE cxx_std_20)
target_compile_definitions(codex_agent_loader_wrong_target PRIVATE CODEX_AGENT_BUILD
    CODEX_AGENT_FIXTURE_TARGET="${CODEX_AGENT_WRONG_FIXTURE_TARGET}")
target_include_directories(codex_agent_loader_wrong_target PRIVATE "${CodexAgent_C_SDK_INCLUDE_DIR}")
set(CODEX_AGENT_LOADER_COMPATIBILITY "${CMAKE_CURRENT_BINARY_DIR}/sdk-compatibility.json")
add_custom_command(
    OUTPUT "${CODEX_AGENT_LOADER_COMPATIBILITY}"
    COMMAND "${CMAKE_COMMAND}"
        -DLIBRARY=$<TARGET_FILE:codex_agent_loader_valid>
        -DOUTPUT=${CODEX_AGENT_LOADER_COMPATIBILITY}
        -DSELECTED_TARGET=${CodexAgent_NATIVE_CLASSIFIER}
        -P "${CMAKE_CURRENT_SOURCE_DIR}/write_loader_compatibility.cmake"
    DEPENDS codex_agent_loader_valid write_loader_compatibility.cmake
    VERBATIM
)
add_custom_target(codex_agent_loader_compatibility DEPENDS "${CODEX_AGENT_LOADER_COMPATIBILITY}")
add_executable(codex_agent_native_loader_test native_loader_test.cpp)
target_link_libraries(codex_agent_native_loader_test PRIVATE CodexAgent::Loader)
add_dependencies(codex_agent_native_loader_test codex_agent_loader_compatibility
    codex_agent_loader_external codex_agent_loader_old_abi
    codex_agent_loader_abi_mismatch
    codex_agent_loader_wrong_contract codex_agent_loader_wrong_target
    codex_agent_loader_missing_identity)
add_test(NAME codex_agent_native_loader_embedded COMMAND codex_agent_native_loader_test
    $<TARGET_FILE:codex_agent_loader_valid> "${CODEX_AGENT_LOADER_COMPATIBILITY}" success)
add_test(NAME codex_agent_native_loader_hash_mismatch COMMAND codex_agent_native_loader_test
    $<TARGET_FILE:codex_agent_loader_external> "${CODEX_AGENT_LOADER_COMPATIBILITY}" failure)
add_test(NAME codex_agent_native_loader_external_component COMMAND codex_agent_native_loader_test
    $<TARGET_FILE:codex_agent_loader_valid> "${CODEX_AGENT_LOADER_COMPATIBILITY}" external-component
    $<TARGET_FILE:codex_agent_loader_external>)
add_test(NAME codex_agent_native_loader_old_abi COMMAND codex_agent_native_loader_test
    $<TARGET_FILE:codex_agent_loader_valid> "${CODEX_AGENT_LOADER_COMPATIBILITY}" failure
    $<TARGET_FILE:codex_agent_loader_old_abi>)
add_test(NAME codex_agent_native_loader_actual_abi_mismatch COMMAND codex_agent_native_loader_test
    $<TARGET_FILE:codex_agent_loader_valid> "${CODEX_AGENT_LOADER_COMPATIBILITY}" failure
    $<TARGET_FILE:codex_agent_loader_abi_mismatch>)
add_test(NAME codex_agent_native_loader_wrong_contract COMMAND codex_agent_native_loader_test
    $<TARGET_FILE:codex_agent_loader_valid> "${CODEX_AGENT_LOADER_COMPATIBILITY}" failure
    $<TARGET_FILE:codex_agent_loader_wrong_contract>)
add_test(NAME codex_agent_native_loader_wrong_target COMMAND codex_agent_native_loader_test
    $<TARGET_FILE:codex_agent_loader_valid> "${CODEX_AGENT_LOADER_COMPATIBILITY}" failure
    $<TARGET_FILE:codex_agent_loader_wrong_target>)
add_test(NAME codex_agent_native_loader_missing_identity COMMAND codex_agent_native_loader_test
    $<TARGET_FILE:codex_agent_loader_valid> "${CODEX_AGENT_LOADER_COMPATIBILITY}" failure
    $<TARGET_FILE:codex_agent_loader_missing_identity>)
add_test(NAME codex_agent_native_loader_no_fallback COMMAND codex_agent_native_loader_test
    "${CMAKE_CURRENT_BINARY_DIR}/missing/$<TARGET_FILE_NAME:codex_agent_loader_valid>"
    "${CODEX_AGENT_LOADER_COMPATIBILITY}" failure)
add_test(NAME codex_agent_native_loader_relative_override COMMAND codex_agent_native_loader_test
    $<TARGET_FILE:codex_agent_loader_valid> "${CODEX_AGENT_LOADER_COMPATIBILITY}" failure
    relative-library-name)
foreach(mode noncanonical-json reordered-json duplicate-json-key reordered-variants
        duplicate-component duplicate-manifest invalid-sdk-version valid-sdk-prerelease
        invalid-sdk-prerelease invalid-identity-schema invalid-abi-major
        invalid-abi-minor source-aba snapshot-aba)
    string(REPLACE "-" "_" test_suffix "${mode}")
    add_test(NAME codex_agent_native_loader_${test_suffix} COMMAND codex_agent_native_loader_test
        $<TARGET_FILE:codex_agent_loader_valid> "${CODEX_AGENT_LOADER_COMPATIBILITY}" "${mode}")
endforeach()
if(NOT WIN32)
    foreach(mode parent-symlink-library final-symlink-library
            parent-symlink-compatibility final-symlink-compatibility)
        string(REPLACE "-" "_" test_suffix "${mode}")
        add_test(NAME codex_agent_native_loader_${test_suffix} COMMAND codex_agent_native_loader_test
            $<TARGET_FILE:codex_agent_loader_valid> "${CODEX_AGENT_LOADER_COMPATIBILITY}" "${mode}")
    endforeach()
endif()
add_test(NAME codex_agent_native_loader_zero_leaks COMMAND "${Python3_EXECUTABLE}"
    "${CMAKE_CURRENT_SOURCE_DIR}/test_loader_cleanup.py"
    $<TARGET_FILE:codex_agent_native_loader_test>
    $<TARGET_FILE:codex_agent_loader_valid>
    "${CODEX_AGENT_LOADER_COMPATIBILITY}"
    $<TARGET_FILE:codex_agent_loader_old_abi>)

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
    PRIVATE CodexAgent::CodexAgent CodexAgent::C codex_agent_mock Threads::Threads
)
target_compile_definitions(codex_agent_cpp_test PRIVATE CODEX_AGENT_CPP_STATIC_TEST_DISPATCH)
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
    PRIVATE CodexAgent::CodexAgent CodexAgent::C codex_agent_mock Threads::Threads
)
target_compile_definitions(codex_agent_cpp_conversation_test PRIVATE CODEX_AGENT_CPP_STATIC_TEST_DISPATCH)
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
    codex_agent_cpp_conversation_real_test PRIVATE CodexAgent::CodexAgent CodexAgent::C
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
    PRIVATE CodexAgent::CodexAgent CodexAgent::C codex_agent_agent_mock
)
target_compile_definitions(codex_agent_cpp_agent_test PRIVATE CODEX_AGENT_CPP_STATIC_TEST_DISPATCH)
add_executable(codex_agent_cpp_agent_real_test agent_real_boundary_test.cpp)
target_link_libraries(
    codex_agent_cpp_agent_real_test PRIVATE CodexAgent::CodexAgent CodexAgent::C
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
    PRIVATE CodexAgent::CodexAgent CodexAgent::C codex_agent_host_mock Threads::Threads
)
target_compile_definitions(codex_agent_cpp_host_test PRIVATE CODEX_AGENT_CPP_STATIC_TEST_DISPATCH)
add_executable(codex_agent_cpp_host_real_test host_real_boundary_test.cpp)
target_link_libraries(
    codex_agent_cpp_host_real_test PRIVATE CodexAgent::CodexAgent CodexAgent::C
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
    PRIVATE CodexAgent::CodexAgent CodexAgent::C codex_agent_leaf_mock Threads::Threads
)
target_compile_definitions(codex_agent_cpp_leaf_test PRIVATE CODEX_AGENT_CPP_STATIC_TEST_DISPATCH)

add_executable(codex_agent_cpp_leaf_real_test leaf_real_boundary_test.cpp)
target_link_libraries(
    codex_agent_cpp_leaf_real_test PRIVATE CodexAgent::CodexAgent CodexAgent::C
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
