use std::env;
use std::fs;
use std::path::{Path, PathBuf};

fn is_link_or_reparse(metadata: &fs::Metadata) -> bool {
    if metadata.file_type().is_symlink() {
        return true;
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        return metadata.file_attributes() & 0x400 != 0;
    }
    #[cfg(not(windows))]
    false
}

fn regular_asset(path: &Path) -> Option<fs::Metadata> {
    let leaf = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return None,
        Err(error) => panic!("inspect package asset {}: {error}", path.display()),
    };
    let mut current = Some(path);
    while let Some(entry) = current {
        let metadata = fs::symlink_metadata(entry)
            .unwrap_or_else(|error| panic!("inspect package asset {}: {error}", entry.display()));
        assert!(
            !is_link_or_reparse(&metadata)
                && if entry == path {
                    metadata.is_file()
                } else {
                    metadata.is_dir()
                },
            "symbolic, reparse, or nonregular package asset path: {}",
            entry.display()
        );
        current = entry.parent().filter(|parent| parent != &entry);
    }
    Some(leaf)
}

const LIBRARIES: [(&str, &str); 5] = [
    ("osx-arm64", "libcodex_agent.dylib"),
    ("osx-x64", "libcodex_agent.dylib"),
    ("linux-arm64", "libcodex_agent.so"),
    ("linux-x64", "libcodex_agent.so"),
    ("win-x64", "codex_agent.dll"),
];

fn require_package_assets(root: &Path) {
    for path in [
        "native/sdk-compatibility.json",
        "native/sdk-runtime-root.pub",
    ]
    .into_iter()
    .map(|path| root.join(path))
    .chain(
        LIBRARIES
            .iter()
            .map(|(target, library)| root.join("native").join(target).join(library)),
    ) {
        let metadata = regular_asset(&path)
            .unwrap_or_else(|| panic!("missing package asset: {}", path.display()));
        assert!(
            metadata.len() > 0,
            "invalid package asset: {}",
            path.display()
        );
    }
}

fn main() {
    let root = PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR"));
    let root_key = root.join("native/sdk-runtime-root.pub");
    let root_output =
        PathBuf::from(env::var_os("OUT_DIR").expect("OUT_DIR")).join("sdk-runtime-root.pub");
    println!("cargo:rerun-if-changed={}", root_key.display());
    if regular_asset(&root_key).is_some() {
        fs::copy(&root_key, root_output).expect("copy SDK-pinned Runtime root key");
    } else {
        fs::write(root_output, []).expect("write absent SDK Runtime root marker");
    }
    // Cargo generates Cargo.toml.orig only in the package verification extraction.
    // Source builds may intentionally use an explicit external Runtime instead.
    if regular_asset(&root.join("Cargo.toml.orig")).is_some() {
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
    if regular_asset(&root.join(&source)).is_some() {
        fs::copy(&source, &output).expect("copy embedded Codex Agent runtime");
    } else {
        fs::write(&output, []).expect("write absent embedded-runtime marker");
    }
}

#[cfg(all(test, unix))]
mod tests {
    use super::regular_asset;
    use std::os::unix::fs::symlink;

    #[test]
    fn package_asset_rejects_symbolic_parent() {
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "codex-agent-rust-build-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir(&root).unwrap();
        std::fs::create_dir(root.join("real")).unwrap();
        std::fs::write(root.join("real/root.pub"), b"key").unwrap();
        symlink(root.join("real"), root.join("alias")).unwrap();
        let rejected = std::panic::catch_unwind(|| regular_asset(&root.join("alias/root.pub")));
        std::fs::remove_dir_all(root).unwrap();
        assert!(rejected.is_err());
    }
}
