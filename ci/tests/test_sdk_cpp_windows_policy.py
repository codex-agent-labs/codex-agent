"""Local CMake/policy checks; not Windows compilation or product acceptance."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_cpp_windows_policy as policy
from products.inventory import sha256_bytes


class WindowsCppPolicyTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("cmake") and shutil.which("c++"), "local CMake/C++ unavailable")
    def test_real_cmake_keeps_original_libraries_and_scopes_compiler_choice(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            toolchain = root / "toolchain.cmake"
            compiler = Path(shutil.which("c++"))
            toolchain.write_bytes(policy.cmake_policy(compiler, root / "cl"))
            for name, enabled in (("CodexAgent", True), ("CodexAgentConsumer", False), ("CMAKE_TRY_COMPILE", True)):
                source, build = root / name, root / (name + "-build")
                source.mkdir()
                text = "cmake_minimum_required(VERSION 3.24)\nproject(" + name + " LANGUAGES NONE)\n"
                if name == "CodexAgent":
                    text += '''enable_language(CXX)
include(CheckCXXSourceCompiles)
check_cxx_source_compiles("int main() { return 0; }" CODEX_POLICY_TRY_COMPILE)
if(NOT CODEX_POLICY_TRY_COMPILE)
message(FATAL_ERROR "Toolchain did not propagate through try_compile")
endif()
foreach(kind agent host leaf)
add_library(codex_agent_cpp_${kind}_test INTERFACE)
set(libraries "CodexAgent::CodexAgent;CodexAgent::C;codex_agent_${kind}_mock")
if(NOT kind STREQUAL "agent")
list(APPEND libraries Threads::Threads)
endif()
set_property(TARGET codex_agent_cpp_${kind}_test PROPERTY LINK_LIBRARIES "${libraries}")
file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/${kind}.txt" CONTENT "$<TARGET_PROPERTY:codex_agent_cpp_${kind}_test,LINK_LIBRARIES>")
endforeach()
'''
                text += 'file(WRITE "${CMAKE_BINARY_DIR}/compiler.txt" "${CMAKE_CXX_COMPILER}|${CMAKE_CXX_FLAGS_INIT}")\n'
                (source / "CMakeLists.txt").write_text(text)
                command = ["cmake", "-S", str(source), "-B", str(build), "-DCMAKE_TOOLCHAIN_FILE=" + str(toolchain),
                           "-DCODEX_AGENT_CPP_BUILD_TESTS=" + ("ON" if enabled else "OFF")]
                completed = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
                expected = str(compiler if enabled else root / "cl") + "|" + ("" if enabled else "/Zc:preprocessor")
                self.assertEqual(expected, (build / "compiler.txt").read_text().strip())
                if name == "CodexAgent":
                    for kind in ("agent", "host", "leaf"):
                        expected = [f"codex_agent_{kind}_mock", "CodexAgent::CodexAgent", "CodexAgent::C"]
                        if kind != "agent": expected += ["Threads::Threads"]
                        self.assertEqual(expected, (build / (kind + ".txt")).read_text().split(";"))
                    # A changed original link graph must fail, not silently discard a library.
                    (source / "CMakeLists.txt").write_text(text.replace(";CodexAgent::C;", ";unexpected;"))
                    rejected = subprocess.run(command, capture_output=True, text=True)
                    self.assertNotEqual(0, rejected.returncode)
                    self.assertIn("Unexpected original mock linkage", rejected.stderr)

    def test_exact_source_compiler_and_post_execution_guard(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / policy.POLICY
            source.parent.mkdir()
            source.write_bytes(b"unit policy source")
            compiler = root / "clang-cl"
            compiler.write_bytes(b"unit compiler, never executed")
            destination = root / "diagnostics"
            destination.mkdir()
            # dict(os.environ) on Windows has uppercase keys, unlike os.environ's
            # case-insensitive lookup. Exercise the real copied-worker shape.
            environment = {"VCTOOLSVERSION": "14.51.36231", "PATH": "unit"}
            paths = {"clang-cl": str(compiler), "cl": str(root / "cl"), "ninja": str(root / "ninja")}
            with patch.object(policy, "git_regular_blob_bytes", return_value=source.read_bytes()), \
                    patch.object(policy.shutil, "which", side_effect=lambda name, **kw: paths[name]), \
                    patch.object(policy, "CLANG_SHA256", sha256_bytes(compiler.read_bytes())):
                files, unchanged = policy.prepare(root, "unit-revision", destination, environment)
                self.assertEqual("Ninja Multi-Config", environment["CMAKE_GENERATOR"])
                self.assertEqual(str(destination / "windows-cpp-validation.cmake"), environment["CMAKE_TOOLCHAIN_FILE"])
                self.assertEqual({source, destination / "windows-cpp-validation.cmake"}, set(files))
                unchanged()
                compiler.write_bytes(b"changed compiler")
                with self.assertRaisesRegex(ValueError, "authenticated hosted identity"):
                    unchanged()
                with self.assertRaisesRegex(ValueError, "injected compiler option"):
                    policy.prepare(root, "unit-revision", destination, environment)
            with patch.object(policy, "git_regular_blob_bytes", return_value=b"different source"), \
                    self.assertRaisesRegex(ValueError, "elected Git input"):
                policy.prepare(root, "unit-revision", destination, environment)

    def test_cmake_paths_reject_delimiter_injection(self):
        for invalid in ("relative/compiler", "/bad]]/compiler", "/bad\n/compiler"):
            with self.assertRaises(ValueError):
                policy.cmake_policy(invalid, Path.cwd() / "cl")


if __name__ == "__main__":
    unittest.main()
