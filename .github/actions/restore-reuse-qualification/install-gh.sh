#!/usr/bin/env bash
set -euo pipefail
# Native verification needs source/signer digest pins absent from older gh.
case "$(uname -s)/$(uname -m)" in
  Linux/x86_64)
    asset=gh_2.102.0_linux_amd64.tar.gz
    digest=bb766f710eef8ede859c18578c72c327597cd4c8a85b06001b1f3843c6019386
    ;;
  Linux/aarch64)
    asset=gh_2.102.0_linux_arm64.tar.gz
    digest=7862c86c72f43df3a2d93ddde6f473285b4e2af61b494849846827e513ef6484
    ;;
  Darwin/x86_64)
    asset=gh_2.102.0_macOS_amd64.zip
    digest=b245f24eb2bf5f75b426b4c26da3651a107f8d5b6f4fddfbfccc5679041378b3
    ;;
  Darwin/arm64)
    asset=gh_2.102.0_macOS_arm64.zip
    digest=da922c20d1792e5b2cbf375593d7a658acf034c12c84e007e71c76ef959c337e
    ;;
  *)
    echo 'Portable qualification custody unavailable; retain cold authentication.' >&2
    echo 'supported=false' >> "$GITHUB_OUTPUT"
    exit 0
    ;;
esac
directory="$RUNNER_TEMP/reuse-qualification-gh"
mkdir "$directory"
curl --fail --location --silent --show-error \
  "https://github.com/cli/cli/releases/download/v2.102.0/$asset" -o "$directory/$asset"
printf '%s  %s\n' "$digest" "$directory/$asset" | shasum -a 256 --check --status
if [[ "$asset" == *.zip ]]; then
  unzip -q "$directory/$asset" '*/bin/gh' -d "$directory"
else
  tar -xzf "$directory/$asset" -C "$directory" --wildcards '*/bin/gh'
fi
binary=$(find "$directory" -type f -path '*/bin/gh')
test -n "$binary"
echo "$(dirname "$binary")" >> "$GITHUB_PATH"
echo 'supported=true' >> "$GITHUB_OUTPUT"
