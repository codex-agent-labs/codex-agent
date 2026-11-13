#!/usr/bin/env bash
# Select the hosted image's Java 17 alias without changing the pinned toolchain.
set -euo pipefail

case "$RUNNER_OS/$RUNNER_ARCH" in
  macOS/ARM64) java_home_variable=JAVA_HOME_17_arm64 ;;
  Linux/ARM64) java_home_variable=JAVA_HOME_17_X64 ;;
  *) java_home_variable="JAVA_HOME_17_${RUNNER_ARCH}" ;;
esac
selected_java_home="${!java_home_variable:-}"
test -n "$selected_java_home"
