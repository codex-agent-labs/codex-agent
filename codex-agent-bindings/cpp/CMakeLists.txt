cmake_minimum_required(VERSION 3.24)

option(
    CODEX_AGENT_CPP_PACKAGE_ONLY
    "Configure the target-specific source package without enabling a host C++ toolchain"
    OFF
)
project(CodexAgent VERSION 0.8.0 LANGUAGES NONE)
if(NOT CODEX_AGENT_CPP_PACKAGE_ONLY)
    enable_language(CXX)
endif()

include(CMakePackageConfigHelpers)
if(CODEX_AGENT_CPP_PACKAGE_ONLY AND NOT DEFINED CMAKE_INSTALL_LIBDIR)
    set(CMAKE_INSTALL_LIBDIR "lib" CACHE PATH "Object code libraries")
endif()
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
    set(CodexAgent_SDK_COMPATIBILITY
        "${CodexAgent_C_SDK_ROOT}/share/CodexAgent/native/sdk-compatibility.json")
    set(CodexAgent_SDK_RUNTIME_ROOT
        "${CodexAgent_C_SDK_ROOT}/share/CodexAgent/native/sdk-runtime-root.pub")
    foreach(required
        "${CodexAgent_C_SDK_INCLUDE_DIR}/codex_agent.h"
        "${CodexAgent_C_SDK_LIBRARY}"
        "${CodexAgent_SDK_COMPATIBILITY}"
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
    file(SHA256 "${CodexAgent_SDK_COMPATIBILITY}" CODEX_AGENT_SDK_COMPATIBILITY_SHA256)
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

if(NOT CODEX_AGENT_CPP_PACKAGE_ONLY)
    add_library(CodexAgent INTERFACE)
    add_library(CodexAgent::CodexAgent ALIAS CodexAgent)
    add_library(CodexAgentLoader STATIC src/native_loader.cpp)
    add_library(CodexAgent::Loader ALIAS CodexAgentLoader)
    target_compile_features(CodexAgentLoader PUBLIC cxx_std_20)
    target_include_directories(
        CodexAgentLoader
        PUBLIC
            "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
            "$<BUILD_INTERFACE:${CodexAgent_C_SDK_INCLUDE_DIR}>"
            "$<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>"
    )
    if(CMAKE_DL_LIBS)
        target_link_libraries(CodexAgentLoader PUBLIC ${CMAKE_DL_LIBS})
    endif()
    if(MSVC)
        target_compile_options(CodexAgentLoader PRIVATE /W4 /WX)
    else()
        target_compile_options(CodexAgentLoader PRIVATE -Wall -Wextra -Wpedantic -Werror)
    endif()
    target_compile_features(CodexAgent INTERFACE cxx_std_20)
    target_include_directories(
        CodexAgent
        INTERFACE
            "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
            "$<BUILD_INTERFACE:${CodexAgent_C_SDK_INCLUDE_DIR}>"
            "$<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>"
    )
    target_compile_definitions(
        CodexAgent
        INTERFACE
            CODEX_AGENT_CPP_DEFAULT_LIBRARY_PATH="$<BUILD_INTERFACE:${CodexAgent_C_SDK_LIBRARY}>"
            CODEX_AGENT_CPP_COMPATIBILITY_PATH="$<BUILD_INTERFACE:${CodexAgent_SDK_COMPATIBILITY}>"
    )
    target_link_libraries(CodexAgent INTERFACE CodexAgentLoader)

    if(CodexAgent_C_SDK_LIBRARY)
        if(NOT EXISTS "${CodexAgent_C_SDK_LIBRARY}")
            message(FATAL_ERROR "CodexAgent_C_SDK_LIBRARY does not exist: ${CodexAgent_C_SDK_LIBRARY}")
        endif()
        if(WIN32)
            add_library(CodexAgentC SHARED IMPORTED)
        else()
            add_library(CodexAgentC UNKNOWN IMPORTED)
        endif()
        add_library(CodexAgent::C ALIAS CodexAgentC)
        set_target_properties(
            CodexAgentC
            PROPERTIES
                IMPORTED_LOCATION "${CodexAgent_C_SDK_LIBRARY}"
                INTERFACE_INCLUDE_DIRECTORIES "${CodexAgent_C_SDK_INCLUDE_DIR}"
        )
        if(WIN32)
            if(MSVC)
                set_property(TARGET CodexAgentC PROPERTY IMPORTED_IMPLIB "${CODEX_AGENT_C_SDK_MSVC_IMPORT}")
            else()
                set_property(TARGET CodexAgentC PROPERTY IMPORTED_IMPLIB "${CODEX_AGENT_C_SDK_GNU_IMPORT}")
            endif()
        endif()
    endif()
endif()

option(CODEX_AGENT_CPP_BUILD_TESTS "Build the typed C++ wrapper tests" OFF)
if(CODEX_AGENT_CPP_PACKAGE_ONLY AND CODEX_AGENT_CPP_BUILD_TESTS)
    message(FATAL_ERROR "CODEX_AGENT_CPP_BUILD_TESTS requires a normal C++ configuration")
endif()
if(NOT CodexAgent_C_SDK_LIBRARY AND NOT CODEX_AGENT_CPP_BUILD_TESTS)
    message(FATAL_ERROR "Set CodexAgent_C_SDK_LIBRARY to the verified native C SDK library")
endif()
if(CODEX_AGENT_CPP_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
    get_target_property(_codex_agent_release_loader_definitions CodexAgentLoader COMPILE_DEFINITIONS)
    if(_codex_agent_release_loader_definitions MATCHES "CODEX_AGENT_NATIVE_LOADER_TEST_HOOK")
        message(FATAL_ERROR "Installable CodexAgentLoader must not contain test trust-root hooks")
    endif()
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
        FILES "${CodexAgent_SDK_COMPATIBILITY}"
        DESTINATION "${CMAKE_INSTALL_DATADIR}/CodexAgent/native"
    )
    if(EXISTS "${CodexAgent_SDK_RUNTIME_ROOT}")
        install(FILES "${CodexAgent_SDK_RUNTIME_ROOT}"
            DESTINATION "${CMAKE_INSTALL_DATADIR}/CodexAgent/native")
    endif()
    install(
        FILES src/native_loader.cpp tools/generate_native_dispatch.py
        DESTINATION "${CMAKE_INSTALL_DATADIR}/CodexAgent/loader"
    )
    install(
        FILES README.md "${CodexAgent_C_SDK_ROOT}/LICENSE.txt"
        DESTINATION "${CMAKE_INSTALL_DATADIR}/doc/CodexAgent"
    )

    file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/src/native_loader.cpp" CODEX_AGENT_CPP_LOADER_SOURCE_SHA256)
    if(EXISTS "${CodexAgent_SDK_RUNTIME_ROOT}")
        file(SHA256 "${CodexAgent_SDK_RUNTIME_ROOT}" CODEX_AGENT_SDK_RUNTIME_ROOT_SHA256)
    else()
        set(CODEX_AGENT_SDK_RUNTIME_ROOT_SHA256 "")
    endif()
    configure_package_config_file(
        cmake/CodexAgentConfig.cmake.in
        "${CMAKE_CURRENT_BINARY_DIR}/CodexAgentConfig.cmake"
        INSTALL_DESTINATION "${CMAKE_INSTALL_LIBDIR}/cmake/CodexAgent"
    )
    write_basic_package_version_file(
        "${CMAKE_CURRENT_BINARY_DIR}/CodexAgentConfigVersion.cmake"
        VERSION "${PROJECT_VERSION}"
        COMPATIBILITY SameMinorVersion
    )
    install(
        FILES
            "${CMAKE_CURRENT_BINARY_DIR}/CodexAgentConfig.cmake"
            "${CMAKE_CURRENT_BINARY_DIR}/CodexAgentConfigVersion.cmake"
        DESTINATION "${CMAKE_INSTALL_LIBDIR}/cmake/CodexAgent"
    )
endif()
