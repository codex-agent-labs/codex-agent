"""Keyed Windows C++ test toolchain; never modify the imported SDK package."""

from pathlib import Path
import shutil

from products.inventory import git_regular_blob_bytes, read_regular_file_bytes, sha256_file


# Exact installed LLVM 20.1.8 from authenticated Windows diagnostic 39337115596/1,
# job 118349260547, original 12226972961. This is not a downloaded-file trust pin.
CLANG_SHA256 = "sha256:57e32b1ea2456f12f97bf802453171bbff12d56b2c486b4eca0c75343c0cda2c"
POLICY = "ci/sdk_cpp_windows_policy.py"


def cmake_policy(clang, msvc):
    """Use Clang only for the capability suite; installed consumers retain MSVC."""
    paths = [Path(path).as_posix() for path in (clang, msvc)]
    if any(not Path(path).is_absolute() or any(s in path for s in ("\n", "\r", "]]")) for path in paths):
        raise ValueError("Windows C++ compiler paths must be absolute CMake literals")
    return ('''include_guard(GLOBAL)
list(APPEND CMAKE_TRY_COMPILE_PLATFORM_VARIABLES CODEX_AGENT_CPP_BUILD_TESTS)
if(CODEX_AGENT_CPP_BUILD_TESTS)
    set(CMAKE_CXX_COMPILER [[@CLANG@]])
else()
    set(CMAKE_CXX_COMPILER [[@MSVC@]])
    set(CMAKE_CXX_FLAGS_INIT "/Zc:preprocessor")
endif()

function(codex_agent_windows_mock_order)
    if(NOT PROJECT_NAME STREQUAL "CodexAgent" OR NOT CODEX_AGENT_CPP_BUILD_TESTS)
        return()
    endif()
    foreach(kind agent host leaf)
        set(consumer "codex_agent_cpp_${kind}_test")
        set(mock "codex_agent_${kind}_mock")
        get_target_property(libraries "${consumer}" LINK_LIBRARIES)
        set(expected "CodexAgent::CodexAgent;CodexAgent::C;${mock}")
        if(NOT kind STREQUAL "agent")
            list(APPEND expected Threads::Threads)
        endif()
        if(NOT libraries STREQUAL expected)
            message(FATAL_ERROR "Unexpected original mock linkage for ${consumer}")
        endif()
        list(REMOVE_ITEM libraries "${mock}")
        list(PREPEND libraries "${mock}")
        set_property(TARGET "${consumer}" PROPERTY LINK_LIBRARIES "${libraries}")
    endforeach()
endfunction()
cmake_language(DEFER CALL codex_agent_windows_mock_order)
'''.replace("@CLANG@", paths[0]).replace("@MSVC@", paths[1])).encode("utf-8")


def prepare(root, revision, destination, environment):
    """Bind the exact Git policy and observed compiler before missing validation."""
    source = root / POLICY
    raw = read_regular_file_bytes(source, max_bytes=64 * 1024, reject_symlink_parents=True)
    if raw != git_regular_blob_bytes(root, revision, POLICY, max_bytes=64 * 1024):
        raise ValueError("Windows C++ compiler policy differs from the elected Git input")
    toolsets = {value.rstrip("/\\") for name, value in environment.items() if name.upper() == "VCTOOLSVERSION"}
    if toolsets != {"14.51.36231"}:
        raise ValueError("Windows C++ validation requires MSVC 14.51.36231 headers and libraries")
    for name in ("CL", "_CL_", "CC", "CXX", "CMAKE_TOOLCHAIN_FILE", "CMAKE_GENERATOR",
                 "CMAKE_GENERATOR_PLATFORM", "CMAKE_GENERATOR_TOOLSET"):
        if environment.get(name):
            raise ValueError(f"Windows C++ validation rejects injected compiler option: {name}")
    clang, msvc, ninja = [shutil.which(name, path=environment.get("PATH")) for name in ("clang-cl", "cl", "ninja")]
    if any(path is None or not Path(path).is_absolute() for path in (clang, msvc, ninja)):
        raise ValueError("Windows C++ validation requires installed clang-cl, MSVC and Ninja")

    def unchanged():
        if Path(clang).is_symlink() or sha256_file(Path(clang)) != CLANG_SHA256:
            raise ValueError("Windows C++ Clang executable differs from its authenticated hosted identity")

    unchanged()
    toolchain = destination / "windows-cpp-validation.cmake"
    content = cmake_policy(clang, msvc)
    with toolchain.open("xb") as stream:
        stream.write(content)
    # Multi-Config preserves the existing Windows Release executable layout.
    environment.update(CMAKE_TOOLCHAIN_FILE=str(toolchain), CMAKE_GENERATOR="Ninja Multi-Config")
    return {source: raw, toolchain: content}, unchanged
