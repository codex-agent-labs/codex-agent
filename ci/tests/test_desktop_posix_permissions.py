"""Compile the real POSIX helper; permission preparation must be idempotent."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.name == "posix" and shutil.which("cc"), "requires a POSIX C compiler")
class DesktopPosixPermissionsTest(unittest.TestCase):
    def test_permissions_are_added_once_without_accepting_unsafe_paths(self):
        root = Path(__file__).resolve().parents[2]
        source = r'''
#include <assert.h>
#include <sys/stat.h>
static int chmod_calls;
static int counted_chmod(const char *path, mode_t mode);
#define chmod counted_chmod
#include "codex_desktop.h"
#undef chmod
static int counted_chmod(const char *path, mode_t mode) {
    ++chmod_calls;
    return chmod(path, mode);
}
int main(void) {
    int file = open("binary", O_CREAT | O_EXCL | O_WRONLY, 0600);
    assert(file >= 0 && close(file) == 0);
    assert(codex_make_executable("binary") == 0 && chmod_calls == 1);
    struct stat status;
    assert(lstat("binary", &status) == 0 && (status.st_mode & 0777) == 0711);
    assert(codex_make_executable("binary") == 0 && chmod_calls == 1);
    assert(symlink("binary", "link") == 0);
    assert(codex_make_executable("link") == -1 && chmod_calls == 1);
    assert(codex_make_executable(".") == -1 && chmod_calls == 1);
    assert(codex_make_executable("missing") == -1 && chmod_calls == 1);
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix="desktop-posix-permissions-") as temporary:
            directory = Path(temporary)
            fixture = directory / "permissions.c"
            fixture.write_text(source)
            executable = directory / "permissions"
            subprocess.run([
                "cc", "-Wall", "-Wextra", "-Werror",
                "-I", str(root / "codex-agent-runtime-desktop/native/include"),
                str(fixture), "-o", str(executable),
            ], check=True, capture_output=True, text=True)
            subprocess.run([str(executable)], cwd=directory, check=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
