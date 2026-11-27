use std::path::{Path, PathBuf};

fn required_file(variable: &str) -> PathBuf {
    let path = std::env::var_os(variable)
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| panic!("{variable} must name a declared artifact file"));
    assert!(
        path.is_file(),
        "{variable} is not a file: {}",
        path.display()
    );
    path
}

pub fn canonical_api_report() -> PathBuf {
    required_file("CODEX_AGENT_CANONICAL_API_REPORT")
}

pub fn c_abi_bootstrap_evidence() -> PathBuf {
    required_file("CODEX_AGENT_C_ABI_BOOTSTRAP_EVIDENCE")
}

pub fn c_sdk_root() -> PathBuf {
    let root = std::env::var_os("CODEX_AGENT_C_SDK_ROOT")
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .expect("CODEX_AGENT_C_SDK_ROOT must name a declared C SDK root");
    let header = root.join("include/codex_agent.h");
    assert!(
        root.is_dir() && header.is_file(),
        "CODEX_AGENT_C_SDK_ROOT must contain include/codex_agent.h: {}",
        root.display()
    );
    root
}

pub fn c_header() -> PathBuf {
    c_sdk_root().join("include/codex_agent.h")
}

pub fn c_include_directory() -> PathBuf {
    c_sdk_root().join("include")
}

pub fn real_sdk_library() -> PathBuf {
    required_file("CODEX_AGENT_REAL_SDK")
}

pub fn read(path: &Path, label: &str) -> String {
    std::fs::read_to_string(path)
        .unwrap_or_else(|error| panic!("read {label} {}: {error}", path.display()))
}
