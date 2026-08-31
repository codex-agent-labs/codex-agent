# Release-populated native libraries

The release build inserts exactly one release-supplied `codex_agent` C SDK library in
each directory below before publishing this package:

- `macos-arm64/libcodex_agent.dylib`
- `macos-x64/libcodex_agent.dylib`
- `linux-arm64/libcodex_agent.so`
- `linux-x64/libcodex_agent.so`
- `windows-x64/codex_agent.dll`

The Dart loader accepts only the current desktop ABI classifier and validates
ABI compatibility before creating a context. These files are not source
artifacts. Repository release integration must verify their checksums and
provenance before package assembly; the Dart package does not yet duplicate
that shared evidence.
