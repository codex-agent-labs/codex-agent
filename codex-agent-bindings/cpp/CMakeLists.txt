cmake_minimum_required(VERSION 3.24)

project(CodexAgent VERSION 0.2.0 LANGUAGES CXX)

include(CMakePackageConfigHelpers)
include(GNUInstallDirs)

set(
    CodexAgent_C_SDK_INCLUDE_DIR
    ""
    CACHE PATH
    "Directory containing the verified codex_agent.h C SDK header"
)
set(
    CodexAgent_C_SDK_LIBRARY
    ""
    CACHE FILEPATH
    "Verified codex_agent native library; required outside the wrapper tests"
)
set(CodexAgent_C_SDK_ROOT "" CACHE PATH "One classifier directory emitted by stageNativeWrapperCAbiSdks")
set(CodexAgent_NATIVE_CLASSIFIER "" CACHE STRING "Exact packaged native classifier")
if(NOT CodexAgent_C_SDK_ROOT OR NOT IS_DIRECTORY "${CodexAgent_C_SDK_ROOT}")
    message(FATAL_ERROR "CodexAgent_C_SDK_ROOT must name a declared C SDK classifier directory")
endif()
if(CodexAgent_C_SDK_ROOT)
    if(NOT CodexAgent_NATIVE_CLASSIFIER MATCHES "^(macos-arm64|macos-x64|linux-arm64|linux-x64|windows-x64)$")
        message(FATAL_ERROR "CodexAgent_NATIVE_CLASSIFIER must name one exact supported desktop host")
    endif()
    if(CodexAgent_NATIVE_CLASSIFIER MATCHES "^macos-")
        set(CODEX_AGENT_C_SDK_LIBRARY_RELATIVE "lib/libcodex_agent.dylib")
    elseif(CodexAgent_NATIVE_CLASSIFIER MATCHES "^linux-")
        set(CODEX_AGENT_C_SDK_LIBRARY_RELATIVE "lib/libcodex_agent.so")
    else()
        set(CODEX_AGENT_C_SDK_LIBRARY_RELATIVE "bin/codex_agent.dll")
    endif()
    set(CodexAgent_C_SDK_INCLUDE_DIR "${CodexAgent_C_SDK_ROOT}/include")
    set(CodexAgent_C_SDK_LIBRARY "${CodexAgent_C_SDK_ROOT}/${CODEX_AGENT_C_SDK_LIBRARY_RELATIVE}")
    foreach(required
        "${CodexAgent_C_SDK_INCLUDE_DIR}/codex_agent.h"
        "${CodexAgent_C_SDK_LIBRARY}"
        "${CodexAgent_C_SDK_ROOT}/codex-agent-c-abi-manifest.json"
        "${CodexAgent_C_SDK_ROOT}/codex-agent-c-abi-evidence.json"
    )
        if(NOT EXISTS "${required}")
            message(FATAL_ERROR "Verified CodexAgent C SDK package member is missing: ${required}")
        endif()
    endforeach()
    if(CodexAgent_NATIVE_CLASSIFIER MATCHES "^linux-")
        set(CODEX_AGENT_C_SDK_SONAME "${CodexAgent_C_SDK_ROOT}/lib/libcodex_agent.so.1")
        if(NOT EXISTS "${CODEX_AGENT_C_SDK_SONAME}")
            message(FATAL_ERROR "Verified CodexAgent C SDK package member is missing: ${CODEX_AGENT_C_SDK_SONAME}")
        endif()
    elseif(CodexAgent_NATIVE_CLASSIFIER STREQUAL "windows-x64")
        set(CODEX_AGENT_C_SDK_GNU_IMPORT "${CodexAgent_C_SDK_ROOT}/lib/libcodex_agent.dll.a")
        set(CODEX_AGENT_C_SDK_MSVC_IMPORT "${CodexAgent_C_SDK_ROOT}/lib/codex_agent.lib")
        foreach(required "${CODEX_AGENT_C_SDK_GNU_IMPORT}" "${CODEX_AGENT_C_SDK_MSVC_IMPORT}")
            if(NOT EXISTS "${required}")
                message(FATAL_ERROR "Verified CodexAgent C SDK package member is missing: ${required}")
            endif()
        endforeach()
    endif()
    file(SHA256 "${CodexAgent_C_SDK_INCLUDE_DIR}/codex_agent.h" CODEX_AGENT_C_SDK_HEADER_SHA256)
    file(SHA256 "${CodexAgent_C_SDK_LIBRARY}" CODEX_AGENT_C_SDK_LIBRARY_SHA256)
    file(SHA256 "${CodexAgent_C_SDK_ROOT}/codex-agent-c-abi-manifest.json" CODEX_AGENT_C_SDK_MANIFEST_SHA256)
    file(SHA256 "${CodexAgent_C_SDK_ROOT}/codex-agent-c-abi-evidence.json" CODEX_AGENT_C_SDK_EVIDENCE_SHA256)
    if(CODEX_AGENT_C_SDK_SONAME)
        file(SHA256 "${CODEX_AGENT_C_SDK_SONAME}" CODEX_AGENT_C_SDK_SONAME_SHA256)
    elseif(CODEX_AGENT_C_SDK_GNU_IMPORT)
        file(SHA256 "${CODEX_AGENT_C_SDK_GNU_IMPORT}" CODEX_AGENT_C_SDK_GNU_IMPORT_SHA256)
        file(SHA256 "${CODEX_AGENT_C_SDK_MSVC_IMPORT}" CODEX_AGENT_C_SDK_MSVC_IMPORT_SHA256)
    endif()
endif()
if(NOT EXISTS "${CodexAgent_C_SDK_INCLUDE_DIR}/codex_agent.h")
    message(FATAL_ERROR "CodexAgent requires the verified codex_agent.h C SDK header")
endif()
set(
    CodexAgent_CANONICAL_API_REPORT
    ""
    CACHE FILEPATH
    "Compiler-derived canonical API report used by parity tests"
)
set(
    CodexAgent_C_ABI_BOOTSTRAP_EVIDENCE
    ""
    CACHE FILEPATH
    "Passed canonical C ABI fixture evidence used by native-wrapper parity tests"
)

add_library(CodexAgent INTERFACE)
add_library(CodexAgent::CodexAgent ALIAS CodexAgent)
target_compile_features(CodexAgent INTERFACE cxx_std_20)
target_include_directories(
    CodexAgent
    INTERFACE
        "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
        "$<BUILD_INTERFACE:${CodexAgent_C_SDK_INCLUDE_DIR}>"
        "$<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>"
)

if(CodexAgent_C_SDK_LIBRARY)
    if(NOT EXISTS "${CodexAgent_C_SDK_LIBRARY}")
        message(FATAL_ERROR "CodexAgent_C_SDK_LIBRARY does not exist: ${CodexAgent_C_SDK_LIBRARY}")
    endif()
    add_library(CodexAgentC UNKNOWN IMPORTED)
    set_target_properties(
        CodexAgentC
        PROPERTIES
            IMPORTED_LOCATION "${CodexAgent_C_SDK_LIBRARY}"
            INTERFACE_INCLUDE_DIRECTORIES "${CodexAgent_C_SDK_INCLUDE_DIR}"
    )
    target_link_libraries(CodexAgent INTERFACE CodexAgentC)
endif()

option(CODEX_AGENT_CPP_BUILD_TESTS "Build the typed C++ wrapper tests" OFF)
if(NOT CodexAgent_C_SDK_LIBRARY AND NOT CODEX_AGENT_CPP_BUILD_TESTS)
    message(FATAL_ERROR "Set CodexAgent_C_SDK_LIBRARY to the verified native C SDK library")
endif()
if(CODEX_AGENT_CPP_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()

set(_codex_agent_install_default OFF)
if(CodexAgent_C_SDK_ROOT)
    set(_codex_agent_install_default ON)
endif()
option(CODEX_AGENT_CPP_INSTALL_PACKAGE "Install the verified target-specific C++ package" ${_codex_agent_install_default})
if(CODEX_AGENT_CPP_INSTALL_PACKAGE)
    if(NOT CodexAgent_C_SDK_ROOT)
        message(FATAL_ERROR "Installing CodexAgent requires CodexAgent_C_SDK_ROOT from stageNativeWrapperCAbiSdks")
    endif()
    get_filename_component(CODEX_AGENT_C_SDK_LIBRARY_DIRECTORY "${CODEX_AGENT_C_SDK_LIBRARY_RELATIVE}" DIRECTORY)
    install(DIRECTORY include/ DESTINATION "${CMAKE_INSTALL_INCLUDEDIR}")
    install(DIRECTORY "${CodexAgent_C_SDK_INCLUDE_DIR}/" DESTINATION "${CMAKE_INSTALL_INCLUDEDIR}")
    install(
        FILES "${CodexAgent_C_SDK_LIBRARY}"
        DESTINATION "${CODEX_AGENT_C_SDK_LIBRARY_DIRECTORY}"
    )
    if(CodexAgent_NATIVE_CLASSIFIER MATCHES "^linux-")
        install(FILES "${CodexAgent_C_SDK_ROOT}/lib/libcodex_agent.so.1" DESTINATION lib)
    elseif(CodexAgent_NATIVE_CLASSIFIER STREQUAL "windows-x64")
        install(
            FILES
                "${CodexAgent_C_SDK_ROOT}/lib/libcodex_agent.dll.a"
                "${CodexAgent_C_SDK_ROOT}/lib/codex_agent.lib"
            DESTINATION lib
        )
    endif()
    install(
        FILES
            "${CodexAgent_C_SDK_ROOT}/codex-agent-c-abi-manifest.json"
            "${CodexAgent_C_SDK_ROOT}/codex-agent-c-abi-evidence.json"
        DESTINATION "${CMAKE_INSTALL_DATADIR}/CodexAgent/native"
    )
    install(
        FILES README.md "${CodexAgent_C_SDK_ROOT}/LICENSE.txt"
        DESTINATION "${CMAKE_INSTALL_DATADIR}/doc/CodexAgent"
    )

    configure_package_config_file(
        cmake/CodexAgentConfig.cmake.in
        "${CMAKE_CURRENT_BINARY_DIR}/CodexAgentConfig.cmake"
        INSTALL_DESTINATION "${CMAKE_INSTALL_LIBDIR}/cmake/CodexAgent"
    )
    write_basic_package_version_file(
        "${CMAKE_CURRENT_BINARY_DIR}/CodexAgentConfigVersion.cmake"
        VERSION "${PROJECT_VERSION}"
        COMPATIBILITY SameMajorVersion
    )
    install(
        FILES
            "${CMAKE_CURRENT_BINARY_DIR}/CodexAgentConfig.cmake"
            "${CMAKE_CURRENT_BINARY_DIR}/CodexAgentConfigVersion.cmake"
        DESTINATION "${CMAKE_INSTALL_LIBDIR}/cmake/CodexAgent"
    )
endif()
