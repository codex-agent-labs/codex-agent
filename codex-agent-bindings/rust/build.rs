use std::env;
use std::fs;
use std::path::PathBuf;

fn main() {
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
