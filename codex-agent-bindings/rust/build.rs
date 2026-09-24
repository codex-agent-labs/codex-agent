use std::env;
use std::fs;
use std::path::{Path, PathBuf};

const LIBRARIES: [(&str, &str); 5] = [
    ("osx-arm64", "libcodex_agent.dylib"),
    ("osx-x64", "libcodex_agent.dylib"),
    ("linux-arm64", "libcodex_agent.so"),
    ("linux-x64", "libcodex_agent.so"),
    ("win-x64", "codex_agent.dll"),
];

fn require_package_assets(root: &Path) {
    for path in std::iter::once(root.join("native/sdk-compatibility.json")).chain(
        LIBRARIES
            .iter()
            .map(|(target, library)| root.join("native").join(target).join(library)),
    ) {
        let metadata = fs::symlink_metadata(&path)
            .unwrap_or_else(|_| panic!("missing package asset: {}", path.display()));
        assert!(
            metadata.file_type().is_file() && metadata.len() > 0,
            "invalid package asset: {}",
            path.display()
        );
    }
}

fn main() {
    let root = PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR"));
    // Cargo generates Cargo.toml.orig only in the package verification extraction.
    // Source builds may intentionally use an explicit external Runtime instead.
    if root.join("Cargo.toml.orig").is_file() {
        require_package_assets(&root);
    }
    let (classifier, library) = match (
        env::var("CARGO_CFG_TARGET_OS").as_deref(),
        env::var("CARGO_CFG_TARGET_ARCH").as_deref(),
    ) {
        (Ok("macos"), Ok("aarch64")) => ("osx-arm64", "libcodex_agent.dylib"),
        (Ok("macos"), Ok("x86_64")) => ("osx-x64", "libcodex_agent.dylib"),
        (Ok("linux"), Ok("aarch64")) => ("linux-arm64", "libcodex_agent.so"),
        (Ok("linux"), Ok("x86_64")) => ("linux-x64", "libcodex_agent.so"),
        (Ok("windows"), Ok("x86_64")) => ("win-x64", "codex_agent.dll"),
        _ => ("unsupported", "codex_agent.unsupported"),
    };
    let source = PathBuf::from("native").join(classifier).join(library);
    let output =
        PathBuf::from(env::var_os("OUT_DIR").expect("OUT_DIR")).join("codex-agent-runtime");
    println!("cargo:rerun-if-changed={}", source.display());
    if source.is_file() {
        fs::copy(&source, &output).expect("copy embedded Codex Agent runtime");
    } else {
        fs::write(&output, []).expect("write absent embedded-runtime marker");
    }
}
