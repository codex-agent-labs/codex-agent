# Third-party notices

`codex-agent-runtime-android` packages and `codex-agent-runtime-ios` statically
embeds Codex App Server `0.149.0`, built from OpenAI Codex revision
`758ef40f50c1a458425c7cfbf1eb12cbc07af0b0` and licensed under Apache-2.0. The
iOS source archive SHA-256 is
`6481974e9740023493eda1f240005cb1507d6969f79d6f6aa97092f967f3f0fc`.
The upstream licence and notice are included in the Android AAR and staged
Apple package as `openai-codex-LICENSE.txt` and `openai-codex-NOTICE.txt`.

The iOS bridge applies the checked-in, iOS-scoped adapter under
`codex-agent-runtime-ios/native/patches`. It exposes the upstream uninitialized
in-process host, removes the disabled V8 code-mode dependency for iOS, and uses
an in-process filesystem environment whose process backend always returns an
unsupported-capability error. Non-iOS upstream behavior is unchanged.

The published artifacts also depend on Kotlin and kotlinx libraries, AndroidX,
and Okio, which are licensed under Apache-2.0. The embedded Rust dependency set
is fixed by the pinned upstream `Cargo.lock` and Rust `1.95.0`; Kotlin
dependency versions are pinned in `gradle/libs.versions.toml` and Gradle
lockfiles.
