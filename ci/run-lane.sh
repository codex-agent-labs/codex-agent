#!/usr/bin/env bash
set -euo pipefail

lane=${1:?lane is required}
build=${CI_LANE_BUILD:-false}
test_lane=${CI_LANE_TEST:-false}
metadata=${CI_LANE_METADATA:-false}
commit=${CI_VALIDATION_COMMIT:?validation commit is required}
tree=${CI_VALIDATION_TREE:?validation tree is required}
args=(--build-cache --parallel --stacktrace -PcodexAgent.candidateCommit="$commit" -PcodexAgent.candidateTree="$tree")
[ -z "${IOS_NATIVE_EVIDENCE:-}" ] || args+=(-PcodexAgent.iosNativeEvidenceDirectory="$IOS_NATIVE_EVIDENCE")
[ -z "${IOS_DEVICE_FRAMEWORK:-}" ] || args+=(-PcodexAgent.iosDeviceFrameworkDirectory="$IOS_DEVICE_FRAMEWORK")
[ -z "${IOS_SIMULATOR_FRAMEWORK:-}" ] || args+=(-PcodexAgent.iosSimulatorFrameworkDirectory="$IOS_SIMULATOR_FRAMEWORK")
[ -z "${IOS_DEVICE_RUST_EVIDENCE:-}" ] || args+=(-PcodexAgent.iosDeviceRustEvidenceDirectory="$IOS_DEVICE_RUST_EVIDENCE")
[ -z "${IOS_SIMULATOR_RUST_EVIDENCE:-}" ] || args+=(-PcodexAgent.iosSimulatorRustEvidenceDirectory="$IOS_SIMULATOR_RUST_EVIDENCE")
[ -z "${MAVEN_REPOSITORY:-}" ] || args+=(-PcodexAgent.mavenRepositoryDirectory="$MAVEN_REPOSITORY")
[ -z "${DESKTOP_CLASSIFIERS:-}" ] || args+=(-PcodexAgent.desktopClassifierDirectory="$DESKTOP_CLASSIFIERS")
[ -z "${ANDROID_RELEASE_AAR:-}" ] || args+=(-PcodexAgent.importedAndroidReleaseAar="$ANDROID_RELEASE_AAR")
[ -z "${ANDROID_EVIDENCE:-}" ] || args+=(-PcodexAgent.androidRuntimeEvidenceDirectory="$ANDROID_EVIDENCE")

run_desktop() {
  local target=$1 native_task=$2 jvm_task=$3 node_task=$4 wasm_task=$5 classifier=$6 evidence_task=${7:-} scenario_task=${8:-}
  local imported=(codex-agent-runtime-desktop/build/distributions/codex-agent-runtime-desktop-*-${classifier}.zip)
  local c_abi_classifier package_task c_abi_package_task c_abi_evidence_task
  case "$target" in
    macosArm64) package_task=packageMacosArm64AppServer; c_abi_classifier=c-abi-macos-arm64; c_abi_package_task=packageMacosArm64CAbiSdk; c_abi_evidence_task=generateMacosArm64CAbiPackageEvidence ;;
    macosX64) package_task=packageMacosX64AppServer; c_abi_classifier=c-abi-macos-x64; c_abi_package_task=packageMacosX64CAbiSdk; c_abi_evidence_task=generateMacosX64CAbiPackageEvidence ;;
    linuxX64) package_task=packageLinuxX64AppServer; c_abi_classifier=c-abi-linux-x64; c_abi_package_task=packageLinuxX64CAbiSdk; c_abi_evidence_task=generateLinuxX64CAbiPackageEvidence ;;
    mingwX64) package_task=packageMingwX64AppServer; c_abi_classifier=c-abi-windows-x64; c_abi_package_task=packageMingwX64CAbiSdk; c_abi_evidence_task=generateMingwX64CAbiPackageEvidence ;;
    *) echo "Unsupported direct desktop target: $target" >&2; return 2 ;;
  esac
  local imported_c_abi=(codex-agent-runtime-desktop/build/distributions/codex-agent-runtime-desktop-*-${c_abi_classifier}.zip)
  if [ "${#imported[@]}" -eq 1 ] && [ -f "${imported[0]}" ] && \
      [ "${#imported_c_abi[@]}" -eq 1 ] && [ -f "${imported_c_abi[0]}" ]; then
    args+=(-PcodexAgent.desktopClassifierDirectory="$PWD/codex-agent-runtime-desktop/build/distributions")
  fi
  if [ "$test_lane" = true ]; then
    args+=(-PcodexAgent.desktopEvidenceTarget="$target")
    local native_tasks=(":codex-agent-runtime-desktop:$native_task" ":codex-agent-runtime-desktop:$c_abi_evidence_task")
    [ -z "$evidence_task" ] || native_tasks+=("$evidence_task")
    [ -z "$scenario_task" ] || native_tasks+=("$scenario_task")
    ./gradlew "${native_tasks[@]}" "${args[@]}"
  elif [ "$build" = true ]; then
    ./gradlew ":codex-agent-runtime-desktop:$package_task" \
      ":codex-agent-runtime-desktop:$c_abi_package_task" "${args[@]}"
  fi
  if [ "$test_lane" = true ]; then
    local archives=(codex-agent-runtime-desktop/build/distributions/*-"$classifier".zip)
    local c_abi_archives=(codex-agent-runtime-desktop/build/distributions/*-"$c_abi_classifier".zip)
    if [ ! -f "${archives[0]}" ]; then
      ./gradlew ":codex-agent-runtime-desktop:$native_task" "${args[@]}"
      archives=(codex-agent-runtime-desktop/build/distributions/*-"$classifier".zip)
    fi
    test "${#archives[@]}" -eq 1
    test "${#c_abi_archives[@]}" -eq 1
    test -f codex-agent-runtime-desktop/build/distributions/codex-agent-jvm-runtime-evidence-runner.zip
    test -f codex-agent-runtime-desktop/build/distributions/codex-agent-node-runtime-evidence-runner.zip
    test -f codex-agent-runtime-desktop/build/distributions/codex-agent-node-wasm-runtime-evidence-runner.zip
    local tasks=(":codex-agent-runtime-desktop:$jvm_task")
    [ "${CI_NODE_JS_REQUIRED:-true}" != true ] || tasks+=(":codex-agent-runtime-desktop:$node_task")
    [ "${CI_NODE_WASM_REQUIRED:-true}" != true ] || tasks+=(":codex-agent-runtime-desktop:$wasm_task")
    ./gradlew "${tasks[@]}" \
      -PcodexAgent.jvmClassifierArchive="$PWD/${archives[0]}" \
      -PcodexAgent.jvmRuntimeEvidenceRunner="$PWD/codex-agent-runtime-desktop/build/distributions/codex-agent-jvm-runtime-evidence-runner.zip" \
      -PcodexAgent.nodeClassifierArchive="$PWD/${archives[0]}" \
      -PcodexAgent.nodeRuntimeEvidenceRunnerArchive="$PWD/codex-agent-runtime-desktop/build/distributions/codex-agent-node-runtime-evidence-runner.zip" \
      -PcodexAgent.nodeWasmRuntimeEvidenceRunnerArchive="$PWD/codex-agent-runtime-desktop/build/distributions/codex-agent-node-wasm-runtime-evidence-runner.zip" \
      -PcodexAgent.desktopDistributionManifest="$PWD/codex-agent-runtime-desktop/codex-app-server-distributions.json" \
      "${args[@]}"
  fi
}

case "$lane" in
  contracts)
    if [ "$build" = true ] || [ "$test_lane" = true ]; then
      contract_tasks=(
        :codex-agent-core:verifyKotlinBindingParity
        :codex-agent-core:verifyJavaBindingParity
      )
      [ "$build" != true ] || contract_tasks=(:codex-agent-core:verifyProtocolSource "${contract_tasks[@]}")
      ./gradlew "${contract_tasks[@]}" "${args[@]}"
    fi
    [ "$build" != true ] || ./gradlew -p gradle/build-logic releaseToolingJar --stacktrace
    if [ "$test_lane" = true ]; then
      ./gradlew :codex-agent-core:jvmTest :tooling:protocol-generator:test "${args[@]}"
      ./gradlew -p gradle/build-logic test --parallel --stacktrace
    fi
    [ "$metadata" != true ] || ./gradlew -p gradle/build-logic test --tests '*WorkflowContractTest' --parallel --stacktrace
    ;;
  portable)
    [ "$build" != true ] || ./gradlew :codex-agent-runtime-desktop:packageJvmRuntimeEvidenceRunner \
        :codex-agent-runtime-desktop:packageNodeRuntimeEvidenceRunner \
        :codex-agent-runtime-desktop:packageNodeWasmRuntimeEvidenceRunner "${args[@]}"
    if [ "$test_lane" = true ]; then
      ./gradlew :codex-agent-runtime-desktop:jvmTest "${args[@]}"
      ./gradlew -p gradle/build-logic test --tests '*RuntimeEvidence*' --parallel --stacktrace
    fi
    ;;
  android)
    tasks=()
    if [ "$build" != true ] && [ "${CI_PRODUCTION_REUSED:-false}" != true ]; then build=true; fi
    [ "$build" != true ] || tasks+=(
      :codex-agent-runtime-android:assembleRelease
      :tooling:android-runtime-evidence:assembleDebug
      :tooling:android-runtime-evidence:assembleDebugAndroidTest
    )
    [ "$test_lane" != true ] || tasks+=(:codex-agent-runtime-android:testDebugUnitTest)
    [ "$metadata" != true ] || tasks+=(:codex-agent-runtime-android:lintRelease)
    ./gradlew "${tasks[@]}" "${args[@]}"
    ;;
  node-js)
    if [ "$build" = true ] || [ "$test_lane" = true ]; then
      ./gradlew :codex-agent-runtime-desktop:verifyJavaScriptTypeScriptBindingParity "${args[@]}"
    fi
    ;;
  node-wasm)
    [ "$test_lane" != true ] || ./gradlew :codex-agent-runtime-desktop:wasmJsNodeTest "${args[@]}"
    ;;
  desktop-macos-arm64)
    run_desktop macosArm64 recordMacosArm64DesktopRuntimeEvidence recordJvmRuntimeMacosArm64Evidence \
      nodeRuntimeMacosArm64Test nodeWasmRuntimeMacosArm64Test app-server-macos-arm64 \
      :codex-agent-runtime-desktop:generateCodexAgentCAbiBootstrapEvidence \
      :codex-agent-runtime-desktop:generateCodexAgentCAbiScenarioProof
    ;;
  desktop-macos-x64)
    run_desktop macosX64 recordMacosX64DesktopRuntimeEvidence recordJvmRuntimeMacosX64Evidence \
      nodeRuntimeMacosX64Test nodeWasmRuntimeMacosX64Test app-server-macos-x64
    ;;
  desktop-linux-arm64)
    if [ "$build" = true ]; then
      test -f codex-agent-runtime-desktop/build/distributions/codex-agent-*-app-server-linux-arm64.zip
      test -f codex-agent-runtime-desktop/build/distributions/codex-agent-*-c-abi-linux-arm64.zip
    fi
    if [ "$test_lane" = true ]; then
      test -n "${LINUX_ARM64_RUNTIME_BUNDLE:-}"
      ./gradlew -p gradle/build-logic executeLinuxArm64RuntimeEvidenceBundle \
        -PcodexAgent.candidateCommit="$commit" \
        -PcodexAgent.candidateTree="$tree" \
        -PcodexAgent.linuxArm64RuntimeEvidenceBundle="$LINUX_ARM64_RUNTIME_BUNDLE" \
        -PcodexAgent.desktopEvidenceOutput="$PWD/codex-agent-runtime-desktop/build/reports/desktop-runtime-evidence/desktop-runtime-linuxArm64.json" \
        -PcodexAgent.jvmEvidenceOutput="$PWD/codex-agent-runtime-desktop/build/reports/jvm-runtime-evidence/jvm-runtime-linuxArm64.json" \
        -PcodexAgent.nodeEvidenceOutput="$PWD/codex-agent-runtime-desktop/build/reports/node-runtime-evidence/node-runtime-linuxArm64.json" \
        -PcodexAgent.nodeWasmEvidenceOutput="$PWD/codex-agent-runtime-desktop/build/reports/node-runtime-evidence/node-wasm-runtime-linuxArm64.json" \
        -PcodexAgent.javaExecutable=java --parallel --stacktrace
      c_abi_archives=(codex-agent-runtime-desktop/build/distributions/*-c-abi-linux-arm64.zip)
      test "${#c_abi_archives[@]}" -eq 1
      ./gradlew :codex-agent-runtime-desktop:generateLinuxArm64CAbiPackageEvidence \
        -PcodexAgent.desktopClassifierDirectory="$PWD/codex-agent-runtime-desktop/build/distributions" \
        -PcodexAgent.desktopEvidenceTarget=linuxArm64 "${args[@]}"
    fi
    ;;
  desktop-linux-x64)
    run_desktop linuxX64 recordLinuxX64DesktopRuntimeEvidence recordJvmRuntimeLinuxX64Evidence \
      nodeRuntimeLinuxX64Test nodeWasmRuntimeLinuxX64Test app-server-linux-x64
    ;;
  desktop-windows-x64)
    run_desktop mingwX64 recordMingwX64DesktopRuntimeEvidence recordJvmRuntimeMingwX64Evidence \
      nodeRuntimeMingwX64Test nodeWasmRuntimeMingwX64Test app-server-windows-x64
    ;;
  ios-native-tests)
    [ "$test_lane" != true ] || ./gradlew :codex-agent-runtime-ios:exportCodexAgentIosNativeTestsProof "${args[@]}"
    ;;
  ios-rust-device)
    [ "$build" != true ] || ./gradlew :codex-agent-runtime-ios:verifyAppleToolchain \
      :codex-agent-runtime-ios:exportCodexAgentIosArm64RustSlice "${args[@]}"
    ;;
  ios-rust-simulator)
    [ "$build" != true ] || ./gradlew :codex-agent-runtime-ios:verifyAppleToolchain \
      :codex-agent-runtime-ios:exportCodexAgentIosSimulatorArm64RustSlice "${args[@]}"
    ;;
  ios-framework-device)
    [ "$build" != true ] || ./gradlew :codex-agent-runtime-ios:linkReleaseFrameworkIosArm64 "${args[@]}"
    ;;
  ios-framework-simulator)
    [ "$build" != true ] || ./gradlew :codex-agent-runtime-ios:linkReleaseFrameworkIosSimulatorArm64 "${args[@]}"
    ;;
  ios-kotlin-tests)
    [ "$test_lane" != true ] || ./gradlew :codex-agent-runtime-ios:iosSimulatorArm64Test "${args[@]}"
    ;;
  ios-swift-build)
    [ "$build" != true ] || ./gradlew :codex-agent-runtime-ios:verifyCodexAgentSwiftSimulatorCompilation "${args[@]}"
    [ "$test_lane" != true ] || ./gradlew :codex-agent-runtime-ios:verifyCodexAgentSwiftSimulatorCompilation "${args[@]}"
    ;;
  ios-swift-tests)
    [ "$test_lane" != true ] || ./gradlew \
      :codex-agent-runtime-ios:generateCodexAgentAppleBindingEvidence "${args[@]}"
    ;;
  ios-package)
    tasks=()
    [ "$build" != true ] || tasks+=(
      :codex-agent-runtime-ios:packageCodexAgentSwiftPackageBinary
      :codex-agent-runtime-ios:verifyIosDeploymentTargets
      :codex-agent-runtime-ios:verifyIosLicensePackaging
      :codex-agent-runtime-ios:verifyIosReleaseBudgets
    )
    [ "$metadata" != true ] || tasks+=(
      :codex-agent-runtime-ios:generateCodexAgentSwiftPackageChecksum
      :codex-agent-runtime-ios:verifyCodexAgentRemoteSwiftPackage
      :codex-agent-runtime-ios:verifyIosReleaseBudgets
    )
    if [ "$metadata" = true ] && [ "$build" != true ]; then
      shopt -s nullglob
      archives=(codex-agent-runtime-ios/build/distributions/CodexAgent-*.xcframework.zip)
      test "${#archives[@]}" -eq 1
      export CODEX_AGENT_IMPORTED_SWIFT_ZIP="$PWD/${archives[0]}"
      metrics=codex-agent-runtime-ios/build/reports/ios-release/artifact-metrics.json
      if [ -f "$metrics" ]; then
        mkdir -p build/ci
        cp "$metrics" build/ci/imported-ios-artifact-metrics.json
        export CODEX_AGENT_IMPORTED_IOS_METRICS="$PWD/build/ci/imported-ios-artifact-metrics.json"
      fi
    fi
    [ "${#tasks[@]}" -eq 0 ] || ./gradlew "${tasks[@]}" "${args[@]}"
    ;;
  ios-privacy-metrics)
    tasks=()
    [ "$test_lane" != true ] || tasks+=(:codex-agent-runtime-ios:collectIosPrivacyEvidence)
    if [ "$metadata" = true ] || [ "$test_lane" = true ]; then
      tasks+=(
        :codex-agent-runtime-ios:generateIosPrivacyRequiredReasonReview
        :codex-agent-runtime-ios:verifyIosPrivacyManifest
      )
    fi
    if [ "$metadata" = true ] && [ "$test_lane" != true ]; then
      privacy=codex-agent-runtime-ios/build/reports/ios-release/privacy
      if [ -f "$privacy/policy.json" ] && [ -f "$privacy/evidence.json" ]; then
        export CODEX_AGENT_IMPORTED_PRIVACY_EVIDENCE="$PWD/$privacy"
      fi
    fi
    [ "${#tasks[@]}" -eq 0 ] || ./gradlew "${tasks[@]}" "${args[@]}"
    ;;
  consumer-common) ./gradlew verifyStagedKmpConsumerCommon "${args[@]}" ;;
  consumer-android) ./gradlew verifyStagedKmpConsumerAndroid "${args[@]}" ;;
  consumer-desktop) ./gradlew verifyStagedKmpConsumerDesktop "${args[@]}" ;;
  consumer-ios-device) ./gradlew verifyStagedKmpConsumerIosDevice "${args[@]}" ;;
  consumer-ios-simulator) ./gradlew verifyStagedKmpConsumerIosSimulator "${args[@]}" ;;
  consumer-node-js) ./gradlew verifyStagedKmpConsumerNodeJs "${args[@]}" ;;
  consumer-node-wasm) ./gradlew verifyStagedKmpConsumerNodeWasm "${args[@]}" ;;
  *) echo "Unknown CI lane: $lane" >&2; exit 2 ;;
esac
