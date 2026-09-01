if(NOT IS_ABSOLUTE "${LIBRARY}" OR NOT EXISTS "${LIBRARY}")
    message(FATAL_ERROR "loader fixture library is missing")
endif()
file(SHA256 "${LIBRARY}" LIBRARY_SHA256)
foreach(TARGET linux-arm64 linux-x64 macos-arm64 macos-x64 windows-x64)
    string(REPLACE "-" "_" TARGET_VARIABLE "${TARGET}")
    string(TOUPPER "${TARGET_VARIABLE}" TARGET_VARIABLE)
    set(${TARGET_VARIABLE}_SHA256 "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd")
endforeach()
set(LINUX_ARM64_COMPONENT "1111111111111111111111111111111111111111111111111111111111111111")
set(LINUX_X64_COMPONENT "3333333333333333333333333333333333333333333333333333333333333333")
set(MACOS_ARM64_COMPONENT "4444444444444444444444444444444444444444444444444444444444444444")
set(MACOS_X64_COMPONENT "5555555555555555555555555555555555555555555555555555555555555555")
set(WINDOWS_X64_COMPONENT "6666666666666666666666666666666666666666666666666666666666666666")
set(LINUX_ARM64_MANIFEST "1111111111111111111111111111111111111111111111111111111111111111")
set(LINUX_X64_MANIFEST "2222222222222222222222222222222222222222222222222222222222222222")
set(MACOS_ARM64_MANIFEST "3333333333333333333333333333333333333333333333333333333333333333")
set(MACOS_X64_MANIFEST "4444444444444444444444444444444444444444444444444444444444444444")
set(WINDOWS_X64_MANIFEST "5555555555555555555555555555555555555555555555555555555555555555")
string(REPLACE "-" "_" SELECTED_VARIABLE "${SELECTED_TARGET}")
string(TOUPPER "${SELECTED_VARIABLE}" SELECTED_VARIABLE)
set(${SELECTED_VARIABLE}_SHA256 "${LIBRARY_SHA256}")
set(${SELECTED_VARIABLE}_COMPONENT "2222222222222222222222222222222222222222222222222222222222222222")
file(WRITE "${OUTPUT}"
    "{\"contract\":{\"digest\":\"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"version\":\"0.2.0\"},"
    "\"platformRuntime\":{\"android\":{\"desktopRuntimeApplicable\":false,\"owner\":\"sdk\"},\"ios\":{\"desktopRuntimeApplicable\":false,\"owner\":\"sdk\"}},"
    "\"runtime\":{\"compatibleReleaseRange\":\">=0.2.0 <0.3.0\",\"compatibleRuntimeCompatibilityRange\":\">=0.2.0 <0.3.0\","
    "\"defaultManifestSha256\":\"sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd\",\"defaultRuntimeVersion\":\"0.2.0\","
    "\"embeddedVariants\":["
    "{\"bundleSha256\":\"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"componentId\":\"sha256:${LINUX_ARM64_COMPONENT}\",\"manifestSha256\":\"sha256:${LINUX_ARM64_MANIFEST}\",\"runtimeLibrarySha256\":\"sha256:${LINUX_ARM64_SHA256}\",\"target\":\"linux-arm64\"},"
    "{\"bundleSha256\":\"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"componentId\":\"sha256:${LINUX_X64_COMPONENT}\",\"manifestSha256\":\"sha256:${LINUX_X64_MANIFEST}\",\"runtimeLibrarySha256\":\"sha256:${LINUX_X64_SHA256}\",\"target\":\"linux-x64\"},"
    "{\"bundleSha256\":\"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"componentId\":\"sha256:${MACOS_ARM64_COMPONENT}\",\"manifestSha256\":\"sha256:${MACOS_ARM64_MANIFEST}\",\"runtimeLibrarySha256\":\"sha256:${MACOS_ARM64_SHA256}\",\"target\":\"macos-arm64\"},"
    "{\"bundleSha256\":\"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"componentId\":\"sha256:${MACOS_X64_COMPONENT}\",\"manifestSha256\":\"sha256:${MACOS_X64_MANIFEST}\",\"runtimeLibrarySha256\":\"sha256:${MACOS_X64_SHA256}\",\"target\":\"macos-x64\"},"
    "{\"bundleSha256\":\"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"componentId\":\"sha256:${WINDOWS_X64_COMPONENT}\",\"manifestSha256\":\"sha256:${WINDOWS_X64_MANIFEST}\",\"runtimeLibrarySha256\":\"sha256:${WINDOWS_X64_SHA256}\",\"target\":\"windows-x64\"}],"
    "\"minimumAbiMinor\":13,\"requiredAbiMajor\":1,\"requiredContractDigest\":\"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"requiredIdentitySchema\":1},"
    "\"schemaVersion\":1,\"sdkVersion\":\"0.2.0\"}\n")
