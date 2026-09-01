use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, Write};
use std::path::{Path, PathBuf};
use std::sync::OnceLock;
use std::sync::atomic::{AtomicU64, Ordering};

const DECLARATION: &[u8] = include_bytes!("../native/sdk-compatibility.json");
const EMBEDDED_RUNTIME: &[u8] = include_bytes!(concat!(env!("OUT_DIR"), "/codex-agent-runtime"));

#[derive(Debug)]
enum Json {
    Object(BTreeMap<String, Json>),
    Array(Vec<Json>),
    String(String),
    Number(u64),
    Bool(bool),
}

struct Parser<'a> {
    bytes: &'a [u8],
    offset: usize,
}

impl<'a> Parser<'a> {
    fn parse_body(bytes: &'a [u8]) -> Result<Json, String> {
        let mut parser = Self { bytes, offset: 0 };
        let value = parser.value()?;
        if parser.offset != parser.bytes.len() {
            return Err("JSON has trailing or insignificant whitespace".into());
        }
        Ok(value)
    }

    fn declaration(bytes: &'a [u8]) -> Result<Json, String> {
        let body = bytes
            .strip_suffix(b"\n")
            .ok_or("SDK compatibility must have exactly one final LF")?;
        if body.contains(&b'\n') {
            return Err("SDK compatibility must have exactly one final LF".into());
        }
        Self::parse_body(body)
    }

    fn identity(bytes: &'a [u8]) -> Result<Json, String> {
        if bytes.contains(&b'\n') {
            return Err("Runtime identity must not contain an LF".into());
        }
        Self::parse_body(bytes)
    }

    fn value(&mut self) -> Result<Json, String> {
        match self.bytes.get(self.offset) {
            Some(b'{') => self.object(),
            Some(b'[') => self.array(),
            Some(b'\"') => self.string().map(Json::String),
            Some(b'0'..=b'9') => self.number().map(Json::Number),
            Some(_) if self.take(b"true") => Ok(Json::Bool(true)),
            Some(_) if self.take(b"false") => Ok(Json::Bool(false)),
            _ => Err("JSON contains an unsupported value".into()),
        }
    }

    fn object(&mut self) -> Result<Json, String> {
        self.expect(b'{')?;
        let mut values = BTreeMap::new();
        let mut previous: Option<String> = None;
        if self.bytes.get(self.offset) == Some(&b'}') {
            self.offset += 1;
            return Ok(Json::Object(values));
        }
        loop {
            let key = self.string()?;
            if previous.as_ref().is_some_and(|value| value >= &key) {
                return Err("JSON object keys are duplicated or not canonical".into());
            }
            previous = Some(key.clone());
            self.expect(b':')?;
            let value = self.value()?;
            values.insert(key, value);
            match self.bytes.get(self.offset) {
                Some(b',') => self.offset += 1,
                Some(b'}') => {
                    self.offset += 1;
                    return Ok(Json::Object(values));
                }
                _ => return Err("JSON object is malformed".into()),
            }
        }
    }

    fn array(&mut self) -> Result<Json, String> {
        self.expect(b'[')?;
        let mut values = Vec::new();
        if self.bytes.get(self.offset) == Some(&b']') {
            self.offset += 1;
            return Ok(Json::Array(values));
        }
        loop {
            values.push(self.value()?);
            match self.bytes.get(self.offset) {
                Some(b',') => self.offset += 1,
                Some(b']') => {
                    self.offset += 1;
                    return Ok(Json::Array(values));
                }
                _ => return Err("JSON array is malformed".into()),
            }
        }
    }

    fn string(&mut self) -> Result<String, String> {
        self.expect(b'\"')?;
        let start = self.offset;
        while let Some(byte) = self.bytes.get(self.offset) {
            match byte {
                b'\"' => {
                    let value = std::str::from_utf8(&self.bytes[start..self.offset])
                        .map_err(|_| "JSON string is not UTF-8")?
                        .to_owned();
                    self.offset += 1;
                    return Ok(value);
                }
                b' '..=b'!' | b'#'..=b'[' | b']'..=b'~' => self.offset += 1,
                _ => return Err("JSON strings must use canonical printable ASCII".into()),
            }
        }
        Err("JSON string is unterminated".into())
    }

    fn number(&mut self) -> Result<u64, String> {
        let start = self.offset;
        while self.bytes.get(self.offset).is_some_and(u8::is_ascii_digit) {
            self.offset += 1;
        }
        let text = std::str::from_utf8(&self.bytes[start..self.offset]).expect("ASCII digits");
        if text.len() > 1 && text.starts_with('0') {
            return Err("JSON integer has a leading zero".into());
        }
        text.parse()
            .map_err(|_| "JSON integer is out of range".into())
    }

    fn take(&mut self, value: &[u8]) -> bool {
        if self.bytes.get(self.offset..self.offset + value.len()) == Some(value) {
            self.offset += value.len();
            true
        } else {
            false
        }
    }

    fn expect(&mut self, byte: u8) -> Result<(), String> {
        if self.bytes.get(self.offset) == Some(&byte) {
            self.offset += 1;
            Ok(())
        } else {
            Err("JSON punctuation is malformed".into())
        }
    }
}

fn object<'a>(
    value: &'a Json,
    keys: &[&str],
    label: &str,
) -> Result<&'a BTreeMap<String, Json>, String> {
    let Json::Object(value) = value else {
        return Err(format!("{label} must be an object"));
    };
    if value.keys().map(String::as_str).ne(keys.iter().copied()) {
        return Err(format!("{label} fields differ from the exact schema"));
    }
    Ok(value)
}

fn string<'a>(
    value: &'a BTreeMap<String, Json>,
    key: &str,
    label: &str,
) -> Result<&'a str, String> {
    match value.get(key) {
        Some(Json::String(value)) => Ok(value),
        _ => Err(format!("{label}.{key} must be a string")),
    }
}

fn number(value: &BTreeMap<String, Json>, key: &str, label: &str) -> Result<u64, String> {
    match value.get(key) {
        Some(Json::Number(value)) => Ok(*value),
        _ => Err(format!("{label}.{key} must be an integer")),
    }
}

fn sha256_value(value: &str, label: &str) -> Result<(), String> {
    if value.len() != 71
        || !value.starts_with("sha256:")
        || !value[7..]
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(format!("{label} must be a lowercase SHA-256 identity"));
    }
    Ok(())
}

type Version = (u64, u64, u64);
type VersionRange = (Version, Version);

fn semver(value: &str, label: &str) -> Result<Version, String> {
    let mut parts = value.split('.');
    let raw = (parts.next(), parts.next(), parts.next());
    if parts.next().is_some()
        || [raw.0, raw.1, raw.2].into_iter().any(|part| {
            part.is_none_or(|part| part.is_empty() || (part.len() > 1 && part.starts_with('0')))
        })
    {
        return Err(format!("{label} must be a stable SemVer"));
    }
    let parsed = (
        raw.0.unwrap().parse().ok(),
        raw.1.unwrap().parse().ok(),
        raw.2.unwrap().parse().ok(),
    );
    if parsed.0.is_none() || parsed.1.is_none() || parsed.2.is_none() {
        return Err(format!("{label} must be a stable SemVer"));
    }
    Ok((parsed.0.unwrap(), parsed.1.unwrap(), parsed.2.unwrap()))
}

fn version_range(value: &str, label: &str) -> Result<VersionRange, String> {
    let (lower, upper) = value
        .split_once(' ')
        .ok_or_else(|| format!("{label} must contain exact lower and upper bounds"))?;
    let lower = lower
        .strip_prefix(">=")
        .ok_or_else(|| format!("{label} lacks >= lower bound"))?;
    let upper = upper
        .strip_prefix('<')
        .ok_or_else(|| format!("{label} lacks < upper bound"))?;
    let bounds = (semver(lower, label)?, semver(upper, label)?);
    if bounds.0 >= bounds.1 {
        return Err(format!("{label} bounds are empty"));
    }
    Ok(bounds)
}

#[derive(Clone, Debug)]
struct EmbeddedVariant {
    component_id: String,
    library_sha256: String,
}

#[derive(Clone, Debug)]
pub(crate) struct Compatibility {
    contract_digest: String,
    runtime_range: VersionRange,
    identity_schema: u64,
    abi_major: u64,
    minimum_abi_minor: u64,
    embedded: BTreeMap<String, EmbeddedVariant>,
}

impl Compatibility {
    fn parse(bytes: &[u8]) -> Result<Self, String> {
        let root_value = Parser::declaration(bytes)?;
        let root = object(
            &root_value,
            &[
                "contract",
                "platformRuntime",
                "runtime",
                "schemaVersion",
                "sdkVersion",
            ],
            "SDK compatibility",
        )?;
        if number(root, "schemaVersion", "SDK compatibility")? != 1 {
            return Err("unsupported SDK compatibility schema".into());
        }
        semver(
            string(root, "sdkVersion", "SDK compatibility")?,
            "SDK version",
        )?;

        let contract = object(
            root.get("contract").unwrap(),
            &["digest", "version"],
            "SDK compatibility Contract",
        )?;
        let contract_digest = string(contract, "digest", "SDK compatibility Contract")?.to_owned();
        sha256_value(&contract_digest, "SDK compatibility Contract digest")?;
        semver(
            string(contract, "version", "SDK compatibility Contract")?,
            "Contract version",
        )?;

        let platform = object(
            root.get("platformRuntime").unwrap(),
            &["android", "ios"],
            "SDK platform runtimes",
        )?;
        for name in ["android", "ios"] {
            let record = object(
                platform.get(name).unwrap(),
                &["desktopRuntimeApplicable", "owner"],
                name,
            )?;
            if !matches!(
                record.get("desktopRuntimeApplicable"),
                Some(Json::Bool(false))
            ) || string(record, "owner", name)? != "sdk"
            {
                return Err(format!("{name} must remain an SDK-owned platform runtime"));
            }
        }

        let runtime = object(
            root.get("runtime").unwrap(),
            &[
                "compatibleReleaseRange",
                "compatibleRuntimeCompatibilityRange",
                "defaultManifestSha256",
                "defaultRuntimeVersion",
                "embeddedVariants",
                "minimumAbiMinor",
                "requiredAbiMajor",
                "requiredContractDigest",
                "requiredIdentitySchema",
            ],
            "SDK compatibility Runtime",
        )?;
        let release_range = version_range(
            string(runtime, "compatibleReleaseRange", "Runtime")?,
            "Runtime release range",
        )?;
        let default_runtime = semver(
            string(runtime, "defaultRuntimeVersion", "Runtime")?,
            "default Runtime version",
        )?;
        if default_runtime < release_range.0 || default_runtime >= release_range.1 {
            return Err("default Runtime version is outside its compatible release range".into());
        }
        sha256_value(
            string(runtime, "defaultManifestSha256", "Runtime")?,
            "Runtime manifest digest",
        )?;
        let required_contract = string(runtime, "requiredContractDigest", "Runtime")?;
        if required_contract != contract_digest {
            return Err("required Contract digest differs".into());
        }
        let runtime_range = version_range(
            string(runtime, "compatibleRuntimeCompatibilityRange", "Runtime")?,
            "Runtime compatibility range",
        )?;
        let identity_schema = number(runtime, "requiredIdentitySchema", "Runtime")?;
        let abi_major = number(runtime, "requiredAbiMajor", "Runtime")?;
        let minimum_abi_minor = number(runtime, "minimumAbiMinor", "Runtime")?;
        if identity_schema != 1 || abi_major != 1 || minimum_abi_minor < 13 {
            return Err("SDK compatibility Runtime identity/ABI policy is unsupported".into());
        }

        let Json::Array(variants) = runtime.get("embeddedVariants").unwrap() else {
            return Err("embeddedVariants must be an array".into());
        };
        let mut embedded = BTreeMap::new();
        let mut component_ids = BTreeSet::new();
        let mut manifest_digests = BTreeSet::new();
        let mut target_order = Vec::new();
        for variant in variants {
            let record = object(
                variant,
                &[
                    "bundleSha256",
                    "componentId",
                    "manifestSha256",
                    "runtimeLibrarySha256",
                    "target",
                ],
                "embedded Runtime variant",
            )?;
            for key in [
                "bundleSha256",
                "componentId",
                "manifestSha256",
                "runtimeLibrarySha256",
            ] {
                sha256_value(string(record, key, "embedded Runtime variant")?, key)?;
            }
            let target = string(record, "target", "embedded Runtime variant")?.to_owned();
            let component_id = string(record, "componentId", "embedded Runtime variant")?;
            let manifest_digest = string(record, "manifestSha256", "embedded Runtime variant")?;
            if !component_ids.insert(component_id) || !manifest_digests.insert(manifest_digest) {
                return Err(
                    "embedded Runtime component and manifest identities must be unique".into(),
                );
            }
            target_order.push(target.clone());
            if embedded
                .insert(
                    target,
                    EmbeddedVariant {
                        component_id: component_id.to_owned(),
                        library_sha256: string(
                            record,
                            "runtimeLibrarySha256",
                            "embedded Runtime variant",
                        )?
                        .to_owned(),
                    },
                )
                .is_some()
            {
                return Err("duplicate embedded Runtime target".into());
            }
        }
        let expected = [
            "linux-arm64",
            "linux-x64",
            "macos-arm64",
            "macos-x64",
            "windows-x64",
        ];
        if target_order.iter().map(String::as_str).ne(expected) {
            return Err("SDK compatibility must contain exactly five Runtime targets".into());
        }
        Ok(Self {
            contract_digest,
            runtime_range,
            identity_schema,
            abi_major,
            minimum_abi_minor,
            embedded,
        })
    }

    pub(crate) fn authenticate_identity(
        &self,
        bytes: &[u8],
        target: &str,
        embedded: bool,
    ) -> Result<u32, String> {
        let identity_value = Parser::identity(bytes)?;
        let identity = object(
            &identity_value,
            &[
                "appServerVersion",
                "buildInputDigest",
                "cAbiVersion",
                "componentId",
                "contractComponentDigest",
                "contractDigest",
                "runtimeCompatibilityVersion",
                "schemaVersion",
                "target",
            ],
            "Runtime identity",
        )?;
        for key in [
            "buildInputDigest",
            "componentId",
            "contractComponentDigest",
            "contractDigest",
        ] {
            sha256_value(string(identity, key, "Runtime identity")?, key)?;
        }
        semver(
            string(identity, "appServerVersion", "Runtime identity")?,
            "app-server version",
        )?;
        let abi = semver(
            string(identity, "cAbiVersion", "Runtime identity")?,
            "C ABI version",
        )?;
        let runtime = semver(
            string(identity, "runtimeCompatibilityVersion", "Runtime identity")?,
            "Runtime compatibility version",
        )?;
        if number(identity, "schemaVersion", "Runtime identity")? != self.identity_schema
            || string(identity, "target", "Runtime identity")? != target
            || string(identity, "contractDigest", "Runtime identity")? != self.contract_digest
            || abi.0 != self.abi_major
            || abi.1 < self.minimum_abi_minor
            || abi.0 > u8::MAX.into()
            || abi.1 > u8::MAX.into()
            || abi.2 > u16::MAX.into()
            || runtime < self.runtime_range.0
            || runtime >= self.runtime_range.1
        {
            return Err("Runtime identity is incompatible with this SDK".into());
        }
        if embedded
            && string(identity, "componentId", "Runtime identity")?
                != self
                    .embedded
                    .get(target)
                    .ok_or("missing embedded Runtime target")?
                    .component_id
        {
            return Err("embedded Runtime component identity differs from its declaration".into());
        }
        Ok(((abi.0 as u32) << 24) | ((abi.1 as u32) << 16) | (abi.2 as u32))
    }

    fn embedded_variant(&self, target: &str) -> Result<&EmbeddedVariant, String> {
        self.embedded
            .get(target)
            .ok_or_else(|| format!("missing embedded Runtime target {target}"))
    }
}

pub(crate) fn compatibility() -> Result<&'static Compatibility, String> {
    static VALUE: OnceLock<Result<Compatibility, String>> = OnceLock::new();
    VALUE
        .get_or_init(|| Compatibility::parse(DECLARATION))
        .as_ref()
        .map_err(Clone::clone)
}

pub(crate) struct EmbeddedRuntimeSnapshot {
    path: PathBuf,
    expected_digest: String,
    file: Option<File>,
}

#[cfg(windows)]
static WINDOWS_CLEANUP: OnceLock<Result<(), String>> = OnceLock::new();
#[cfg(windows)]
static WINDOWS_SNAPSHOTS: OnceLock<std::sync::Mutex<Vec<(usize, EmbeddedRuntimeSnapshot)>>> =
    OnceLock::new();

#[cfg(windows)]
unsafe extern "C" fn cleanup_windows_snapshots() {
    let values = WINDOWS_SNAPSHOTS.get_or_init(|| std::sync::Mutex::new(Vec::new()));
    let mut values = values
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    for (handle, snapshot) in values.drain(..) {
        // SAFETY: handle came from LoadLibrary and is released once at process exit.
        unsafe { free_library(handle) };
        drop(snapshot);
    }
}

#[cfg(windows)]
unsafe fn free_library(handle: usize) {
    unsafe extern "system" {
        fn FreeLibrary(module: *mut std::ffi::c_void) -> i32;
    }
    // SAFETY: handle came from LoadLibrary and is released exactly once.
    unsafe { FreeLibrary(handle as *mut std::ffi::c_void) };
}

impl EmbeddedRuntimeSnapshot {
    #[cfg(test)]
    pub(crate) fn path(&self) -> &Path {
        &self.path
    }

    pub(crate) fn verify(&self) -> Result<(), String> {
        verify_path_binding(
            self.file.as_ref().expect("live Runtime snapshot"),
            &self.path,
            &self.expected_digest,
        )
    }

    pub(crate) fn load_path(&self) -> PathBuf {
        self.path.clone()
    }

    #[cfg(windows)]
    pub(crate) fn retain_until_exit(self, library_handle: usize) -> Result<(), String> {
        if let Err(error) = WINDOWS_CLEANUP
            .get_or_init(|| {
                unsafe extern "C" {
                    fn atexit(callback: unsafe extern "C" fn()) -> i32;
                }
                // SAFETY: cleanup has C ABI, process lifetime, and no captured state.
                if unsafe { atexit(cleanup_windows_snapshots) } != 0 {
                    Err("register Windows Runtime snapshot cleanup".into())
                } else {
                    Ok(())
                }
            })
            .clone()
        {
            // SAFETY: ownership was transferred from libloading immediately before this call.
            unsafe { free_library(library_handle) };
            return Err(error);
        }
        WINDOWS_SNAPSHOTS
            .get_or_init(|| std::sync::Mutex::new(Vec::new()))
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .push((library_handle, self));
        Ok(())
    }
}

impl Drop for EmbeddedRuntimeSnapshot {
    fn drop(&mut self) {
        drop(self.file.take());
        if let Some(owner) = self.path.parent() {
            let _ = set_private_directory(owner);
        }
        let _ = fs::remove_file(&self.path);
        if let Some(owner) = self.path.parent() {
            let _ = fs::remove_dir(owner);
        }
    }
}

pub(crate) fn embedded_runtime_snapshot(
    target: &str,
    library_name: &str,
) -> Result<EmbeddedRuntimeSnapshot, String> {
    if EMBEDDED_RUNTIME.is_empty() {
        return Err("this source build does not contain an embedded Runtime; set CODEX_AGENT_LIBRARY to an absolute compatible library".into());
    }
    let compatibility = compatibility()?;
    let variant = compatibility.embedded_variant(target)?;
    let actual = format!("sha256:{}", hex(&sha256(EMBEDDED_RUNTIME)));
    if actual != variant.library_sha256 {
        return Err("embedded Runtime library digest differs from sdk-compatibility.json".into());
    }
    let root = cache_root()?
        .join("codex-agent/runtime")
        .join(&variant.component_id[7..])
        .join(target)
        .join("snapshots");
    private_snapshot(&root, library_name, EMBEDDED_RUNTIME, &actual)
}

fn private_snapshot(
    root: &Path,
    library_name: &str,
    bytes: &[u8],
    expected_digest: &str,
) -> Result<EmbeddedRuntimeSnapshot, String> {
    static NEXT: AtomicU64 = AtomicU64::new(0);
    create_safe_directory(root)?;
    let directory = loop {
        let candidate = root.join(format!(
            "{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed),
        ));
        match fs::create_dir(&candidate) {
            Ok(()) => break candidate,
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(format!("create private Runtime snapshot: {error}")),
        }
    };
    set_private_directory(&directory)?;
    let destination = directory.join(library_name);
    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&destination)
        .map_err(|error| {
            format!(
                "create embedded Runtime snapshot {}: {error}",
                destination.display()
            )
        })?;
    let result = (|| {
        output
            .write_all(bytes)
            .map_err(|error| format!("write embedded Runtime: {error}"))?;
        output
            .sync_all()
            .map_err(|error| format!("sync embedded Runtime: {error}"))?;
        drop(output);
        set_read_only(&destination)?;
        verify_regular_digest(&destination, expected_digest)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&destination);
        let _ = fs::remove_dir(&directory);
    }
    result?;
    let file = match open_locked_snapshot(&destination) {
        Ok(file) => file,
        Err(error) => {
            let _ = fs::remove_file(&destination);
            let _ = fs::remove_dir(&directory);
            return Err(error);
        }
    };
    if let Err(error) = verify_file_digest(&file, expected_digest) {
        drop(file);
        let _ = fs::remove_file(&destination);
        let _ = fs::remove_dir(&directory);
        return Err(error);
    }
    if let Err(error) = set_read_only_directory(&directory) {
        drop(file);
        let _ = set_private_directory(&directory);
        let _ = fs::remove_file(&destination);
        let _ = fs::remove_dir(&directory);
        return Err(error);
    }
    Ok(EmbeddedRuntimeSnapshot {
        path: destination,
        expected_digest: expected_digest.to_owned(),
        file: Some(file),
    })
}

#[cfg(test)]
pub(crate) fn snapshot_for_test(
    root: &Path,
    library_name: &str,
    bytes: &[u8],
) -> EmbeddedRuntimeSnapshot {
    let digest = format!("sha256:{}", hex(&sha256(bytes)));
    private_snapshot(root, library_name, bytes, &digest).expect("create test Runtime snapshot")
}

#[cfg(all(test, windows))]
pub(crate) fn embedded_available_for_test() -> bool {
    !EMBEDDED_RUNTIME.is_empty()
}

#[cfg(unix)]
fn open_locked_snapshot(path: &Path) -> Result<File, String> {
    use std::os::unix::fs::OpenOptionsExt;

    #[cfg(target_os = "macos")]
    const O_NOFOLLOW: i32 = 0x100;
    #[cfg(not(target_os = "macos"))]
    const O_NOFOLLOW: i32 = 0x20000;
    OpenOptions::new()
        .read(true)
        .custom_flags(O_NOFOLLOW)
        .open(path)
        .map_err(|error| format!("open no-follow protected Runtime snapshot: {error}"))
}

#[cfg(windows)]
fn open_locked_snapshot(path: &Path) -> Result<File, String> {
    use std::os::windows::fs::OpenOptionsExt;
    OpenOptions::new()
        .read(true)
        .share_mode(1)
        .open(path)
        .map_err(|error| format!("open protected Runtime snapshot: {error}"))
}

#[cfg(unix)]
fn set_private_directory(path: &Path) -> Result<(), String> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o700))
        .map_err(|error| format!("protect Runtime snapshot directory: {error}"))
}

#[cfg(unix)]
fn set_read_only_directory(path: &Path) -> Result<(), String> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o500))
        .map_err(|error| format!("make Runtime snapshot directory read-only: {error}"))
}

#[cfg(not(unix))]
fn set_read_only_directory(_: &Path) -> Result<(), String> {
    Ok(())
}

#[cfg(not(unix))]
fn set_private_directory(_: &Path) -> Result<(), String> {
    Ok(())
}

#[cfg(unix)]
fn set_read_only(path: &Path) -> Result<(), String> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o400))
        .map_err(|error| format!("protect Runtime snapshot: {error}"))
}

#[cfg(not(unix))]
fn set_read_only(path: &Path) -> Result<(), String> {
    let mut permissions = fs::metadata(path)
        .map_err(|error| format!("inspect Runtime snapshot permissions: {error}"))?
        .permissions();
    permissions.set_readonly(true);
    fs::set_permissions(path, permissions)
        .map_err(|error| format!("protect Runtime snapshot: {error}"))
}

fn cache_root() -> Result<PathBuf, String> {
    #[cfg(target_os = "windows")]
    let value = std::env::var_os("LOCALAPPDATA").map(PathBuf::from);
    #[cfg(target_os = "macos")]
    let value = std::env::var_os("HOME").map(|home| PathBuf::from(home).join("Library/Caches"));
    #[cfg(all(unix, not(target_os = "macos")))]
    let value = std::env::var_os("XDG_CACHE_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".cache")));
    value.ok_or_else(|| "no per-user cache directory is available for the embedded Runtime".into())
}

fn create_safe_directory(path: &Path) -> Result<(), String> {
    fs::create_dir_all(path)
        .map_err(|error| format!("create Runtime cache {}: {error}", path.display()))?;
    let mut current = Some(path);
    while let Some(directory) = current {
        let metadata = fs::symlink_metadata(directory)
            .map_err(|error| format!("inspect Runtime cache {}: {error}", directory.display()))?;
        if metadata.file_type().is_symlink() || !metadata.is_dir() {
            return Err(format!(
                "Runtime cache has an unsafe directory: {}",
                directory.display()
            ));
        }
        current = directory.parent().filter(|parent| parent != &directory);
    }
    Ok(())
}

fn verify_regular_digest(path: &Path, expected: &str) -> Result<(), String> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| format!("inspect Runtime snapshot {}: {error}", path.display()))?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(format!(
            "Runtime snapshot is not a regular file: {}",
            path.display()
        ));
    }
    let bytes = fs::read(path)
        .map_err(|error| format!("read Runtime snapshot {}: {error}", path.display()))?;
    if format!("sha256:{}", hex(&sha256(&bytes))) != expected {
        return Err(format!(
            "Runtime snapshot digest mismatch: {}",
            path.display()
        ));
    }
    Ok(())
}

fn verify_file_digest(file: &File, expected: &str) -> Result<(), String> {
    let mut file = file
        .try_clone()
        .map_err(|error| format!("clone protected Runtime snapshot: {error}"))?;
    file.rewind()
        .map_err(|error| format!("rewind protected Runtime snapshot: {error}"))?;
    let mut bytes = Vec::new();
    file.read_to_end(&mut bytes)
        .map_err(|error| format!("read protected Runtime snapshot: {error}"))?;
    if format!("sha256:{}", hex(&sha256(&bytes))) != expected {
        return Err("protected Runtime snapshot digest mismatch".into());
    }
    Ok(())
}

#[cfg(unix)]
fn verify_path_binding(file: &File, path: &Path, expected: &str) -> Result<(), String> {
    use std::os::unix::fs::MetadataExt;

    let held = file
        .metadata()
        .map_err(|error| format!("inspect held Runtime snapshot: {error}"))?;
    let path_metadata = fs::symlink_metadata(path)
        .map_err(|error| format!("inspect Runtime snapshot path: {error}"))?;
    if path_metadata.file_type().is_symlink()
        || !path_metadata.is_file()
        || held.dev() != path_metadata.dev()
        || held.ino() != path_metadata.ino()
    {
        return Err("Runtime snapshot path no longer names the verified file".into());
    }
    verify_file_digest(file, expected)?;
    verify_regular_digest(path, expected)
}

#[cfg(windows)]
fn verify_path_binding(file: &File, path: &Path, expected: &str) -> Result<(), String> {
    use std::os::windows::fs::MetadataExt;

    let held = file
        .metadata()
        .map_err(|error| format!("inspect held Runtime snapshot: {error}"))?;
    let path_metadata = fs::symlink_metadata(path)
        .map_err(|error| format!("inspect Runtime snapshot path: {error}"))?;
    if path_metadata.file_type().is_symlink()
        || !path_metadata.is_file()
        || held.volume_serial_number().is_none()
        || held.volume_serial_number() != path_metadata.volume_serial_number()
        || held.file_index().is_none()
        || held.file_index() != path_metadata.file_index()
    {
        return Err("Runtime snapshot path no longer names the verified file".into());
    }
    verify_file_digest(file, expected)?;
    verify_regular_digest(path, expected)
}

fn hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut value = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        value.push(DIGITS[(byte >> 4) as usize] as char);
        value.push(DIGITS[(byte & 15) as usize] as char);
    }
    value
}

fn sha256(bytes: &[u8]) -> [u8; 32] {
    const K: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
        0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
        0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
        0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
        0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
        0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2,
    ];
    let mut hash = [
        0x6a09e667u32,
        0xbb67ae85,
        0x3c6ef372,
        0xa54ff53a,
        0x510e527f,
        0x9b05688c,
        0x1f83d9ab,
        0x5be0cd19,
    ];
    let bit_len = (bytes.len() as u64) * 8;
    let mut padded = bytes.to_vec();
    padded.push(0x80);
    while padded.len() % 64 != 56 {
        padded.push(0);
    }
    padded.extend_from_slice(&bit_len.to_be_bytes());
    for chunk in padded.chunks_exact(64) {
        let mut words = [0u32; 64];
        for (index, word) in words[..16].iter_mut().enumerate() {
            *word = u32::from_be_bytes(chunk[index * 4..index * 4 + 4].try_into().unwrap());
        }
        for index in 16..64 {
            let s0 = words[index - 15].rotate_right(7)
                ^ words[index - 15].rotate_right(18)
                ^ (words[index - 15] >> 3);
            let s1 = words[index - 2].rotate_right(17)
                ^ words[index - 2].rotate_right(19)
                ^ (words[index - 2] >> 10);
            words[index] = words[index - 16]
                .wrapping_add(s0)
                .wrapping_add(words[index - 7])
                .wrapping_add(s1);
        }
        let [mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut h] = hash;
        for index in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let choice = (e & f) ^ ((!e) & g);
            let first = h
                .wrapping_add(s1)
                .wrapping_add(choice)
                .wrapping_add(K[index])
                .wrapping_add(words[index]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let majority = (a & b) ^ (a & c) ^ (b & c);
            let second = s0.wrapping_add(majority);
            h = g;
            g = f;
            f = e;
            e = d.wrapping_add(first);
            d = c;
            c = b;
            b = a;
            a = first.wrapping_add(second);
        }
        for (value, add) in hash.iter_mut().zip([a, b, c, d, e, f, g, h]) {
            *value = value.wrapping_add(add);
        }
    }
    let mut output = [0u8; 32];
    for (chunk, value) in output.chunks_exact_mut(4).zip(hash) {
        chunk.copy_from_slice(&value.to_be_bytes());
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;

    fn identity(abi: &str) -> Vec<u8> {
        format!(
            "{{\"appServerVersion\":\"0.149.0\",\"buildInputDigest\":\"sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd\",\"cAbiVersion\":\"{abi}\",\"componentId\":\"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc\",\"contractComponentDigest\":\"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee\",\"contractDigest\":\"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"runtimeCompatibilityVersion\":\"0.2.0\",\"schemaVersion\":1,\"target\":\"macos-arm64\"}}"
        )
        .into_bytes()
    }

    #[test]
    fn declaration_and_hash_are_strict() {
        let parsed = Compatibility::parse(DECLARATION).expect("development declaration");
        assert_eq!(parsed.abi_major, 1);
        assert_eq!(
            hex(&sha256(b"abc")),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
        let mut noncanonical = DECLARATION.to_vec();
        noncanonical.insert(1, b' ');
        assert!(Compatibility::parse(&noncanonical).is_err());

        assert!(Compatibility::parse(DECLARATION.strip_suffix(b"\n").unwrap()).is_err());
        let mut extra_lf = DECLARATION.to_vec();
        extra_lf.push(b'\n');
        assert!(Compatibility::parse(&extra_lf).is_err());

        let leading_zero = String::from_utf8(DECLARATION.to_vec()).unwrap().replacen(
            "\"sdkVersion\":\"0.2.0\"",
            "\"sdkVersion\":\"00.2.0\"",
            1,
        );
        assert!(Compatibility::parse(leading_zero.as_bytes()).is_err());

        let unsorted = String::from_utf8(DECLARATION.to_vec())
            .unwrap()
            .replacen("\"target\":\"linux-arm64\"", "\"target\":\"temporary\"", 1)
            .replacen("\"target\":\"linux-x64\"", "\"target\":\"linux-arm64\"", 1)
            .replacen("\"target\":\"temporary\"", "\"target\":\"linux-x64\"", 1);
        assert!(Compatibility::parse(unsorted.as_bytes()).is_err());

        assert_eq!(
            parsed
                .authenticate_identity(&identity("1.13.0"), "macos-arm64", false)
                .unwrap(),
            (1 << 24) | (13 << 16),
        );
        let mut identity_lf = identity("1.13.0");
        identity_lf.push(b'\n');
        assert!(
            parsed
                .authenticate_identity(&identity_lf, "macos-arm64", false)
                .is_err()
        );
        assert!(
            parsed
                .authenticate_identity(&identity("1.013.0"), "macos-arm64", false)
                .is_err()
        );
    }

    #[test]
    fn default_release_and_variant_identities_are_strict() {
        let declaration = String::from_utf8(DECLARATION.to_vec()).unwrap();
        let rejected = [
            declaration.replacen(
                "\"defaultRuntimeVersion\":\"0.2.0\"",
                "\"defaultRuntimeVersion\":\"0.3.0\"",
                1,
            ),
            declaration.replacen(
                "sha256:2222222222222222222222222222222222222222222222222222222222222222",
                "sha256:2111111111111111111111111111111111111111111111111111111111111111",
                1,
            ),
            declaration.replacen(
                "sha256:3222222222222222222222222222222222222222222222222222222222222222",
                "sha256:3111111111111111111111111111111111111111111111111111111111111111",
                1,
            ),
        ];
        for value in rejected {
            assert!(Compatibility::parse(value.as_bytes()).is_err());
        }
    }

    #[cfg(unix)]
    #[test]
    fn private_snapshot_denies_ordinary_write_and_replacement() {
        let root = std::fs::canonicalize(std::env::temp_dir())
            .unwrap()
            .join(format!(
                "codex-agent-rust-snapshot-test-{}",
                std::process::id()
            ));
        let _ = std::fs::remove_dir_all(&root);
        let expected = format!("sha256:{}", hex(&sha256(b"trusted")));
        let snapshot = private_snapshot(&root, "runtime", b"trusted", &expected).unwrap();
        let owner = snapshot.path().parent().unwrap().to_owned();
        snapshot.verify().unwrap();
        assert!(
            OpenOptions::new()
                .write(true)
                .open(snapshot.path())
                .is_err()
        );
        let replacement = root.join("replacement");
        std::fs::write(&replacement, b"swapped").unwrap();
        assert!(std::fs::rename(&replacement, snapshot.path()).is_err());
        snapshot.verify().unwrap();
        drop(snapshot);
        assert!(!owner.exists());
        std::fs::remove_file(&replacement).unwrap();
        std::fs::remove_dir(&root).unwrap();
    }
}
