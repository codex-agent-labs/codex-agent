use std::collections::BTreeSet;
use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};

use base64::Engine;
use base64::engine::general_purpose::STANDARD;
use serde_json::{Map, Value};

use crate::compatibility::EmbeddedRuntimeSnapshot;

const ROOT_NAMESPACE: &str = "codex-agent-sdk-runtime-root-v1";
const PRODUCT_NAMESPACE: &str = "codex-agent-product-v1";
const MAX_JSON: u64 = 1024 * 1024;

fn sha256(bytes: &[u8]) -> String {
    // Reuse the crate's verified SHA-256 implementation rather than another crypto dependency.
    crate::compatibility::sha256_identity(bytes)
}

fn read_file(path: &Path, limit: u64) -> Result<Vec<u8>, String> {
    let mut current = Some(path);
    while let Some(entry) = current {
        let metadata = fs::symlink_metadata(entry)
            .map_err(|error| format!("external evidence is missing or unsafe: {error}"))?;
        if metadata.file_type().is_symlink()
            || (entry == path && (!metadata.is_file() || metadata.len() > limit))
            || (entry != path && !metadata.is_dir())
        {
            return Err(
                "external evidence contains a symlink, nonregular file, or oversized file".into(),
            );
        }
        current = entry.parent().filter(|parent| parent != &entry);
    }
    let file = fs::File::open(path).map_err(|error| format!("open external evidence: {error}"))?;
    let metadata = file
        .metadata()
        .map_err(|error| format!("inspect opened external evidence: {error}"))?;
    if !metadata.is_file() || metadata.len() > limit {
        return Err("opened external evidence is nonregular or oversized".into());
    }
    read_bounded(file, limit)
}

fn read_bounded(reader: impl Read, limit: u64) -> Result<Vec<u8>, String> {
    let mut bytes = Vec::new();
    reader
        .take(
            limit
                .checked_add(1)
                .ok_or("external evidence size limit overflows")?,
        )
        .read_to_end(&mut bytes)
        .map_err(|error| format!("read external evidence: {error}"))?;
    if bytes.len() as u64 > limit {
        return Err("external evidence file exceeds its size limit".into());
    }
    Ok(bytes)
}

fn canonical_json(bytes: &[u8]) -> Result<Value, String> {
    let value: Value =
        serde_json::from_slice(bytes).map_err(|error| format!("invalid evidence JSON: {error}"))?;
    fn no_float(value: &Value) -> Result<(), String> {
        match value {
            Value::Number(number) if !number.is_i64() && !number.is_u64() => {
                Err("external evidence JSON cannot contain floating-point numbers".into())
            }
            Value::Array(values) => values.iter().try_for_each(no_float),
            Value::Object(values) => values.values().try_for_each(no_float),
            _ => Ok(()),
        }
    }
    no_float(&value)?;
    let mut canonical = serde_json::to_vec(&value).map_err(|error| error.to_string())?;
    canonical.push(b'\n');
    if canonical != bytes {
        return Err("external evidence JSON is not canonical".into());
    }
    Ok(value)
}

fn object<'a>(value: &'a Value, keys: &[&str]) -> Result<&'a Map<String, Value>, String> {
    let map = value
        .as_object()
        .ok_or("external evidence must be a JSON object")?;
    if map.keys().map(String::as_str).ne(keys.iter().copied()) {
        return Err("external evidence JSON fields differ from the exact schema".into());
    }
    Ok(map)
}

fn text<'a>(map: &'a Map<String, Value>, key: &str) -> Result<&'a str, String> {
    map.get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("external evidence {key} must be a string"))
}

fn digest(value: &str) -> Result<(), String> {
    if value.len() != 71
        || !value.starts_with("sha256:")
        || !value.as_bytes()[7..]
            .iter()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(byte))
    {
        return Err("external evidence contains an invalid SHA-256 identity".into());
    }
    Ok(())
}

fn version(value: &str) -> Result<(u64, u64, u64), String> {
    let parts: Vec<_> = value.split('.').collect();
    if parts.len() != 3
        || parts.iter().any(|part| {
            part.is_empty()
                || (part.len() > 1 && part.starts_with('0'))
                || !part.bytes().all(|byte| byte.is_ascii_digit())
        })
    {
        return Err("external evidence version must be stable SemVer".into());
    }
    Ok((
        parts[0].parse().map_err(|_| "invalid major version")?,
        parts[1].parse().map_err(|_| "invalid minor version")?,
        parts[2].parse().map_err(|_| "invalid patch version")?,
    ))
}

fn range(value: &str) -> Result<((u64, u64, u64), (u64, u64, u64)), String> {
    let (lower, upper) = value
        .split_once(' ')
        .ok_or("external evidence range is malformed")?;
    let lower = version(
        lower
            .strip_prefix(">=")
            .ok_or("external evidence range lacks lower bound")?,
    )?;
    let upper = version(
        upper
            .strip_prefix('<')
            .ok_or("external evidence range lacks upper bound")?,
    )?;
    if lower >= upper {
        return Err("external evidence range is empty".into());
    }
    Ok((lower, upper))
}

fn key_fingerprint(bytes: &[u8]) -> Result<String, String> {
    let line = std::str::from_utf8(bytes).map_err(|_| "public key is not UTF-8")?;
    let encoded = line
        .strip_prefix("ssh-ed25519 ")
        .and_then(|value| value.strip_suffix('\n'))
        .ok_or("public key is not canonical ssh-ed25519")?;
    let blob = STANDARD
        .decode(encoded)
        .map_err(|_| "public key Base64 is invalid")?;
    if STANDARD.encode(&blob) != encoded
        || blob.len() != 51
        || &blob[..15] != b"\0\0\0\x0bssh-ed25519"
        || &blob[15..19] != b"\0\0\0\x20"
    {
        return Err("public key is not a canonical Ed25519 key".into());
    }
    Ok(sha256(&blob))
}

#[cfg(test)]
pub(crate) fn fingerprint_for_test(bytes: &[u8]) -> Result<String, String> {
    key_fingerprint(bytes)
}

fn canonical_signature(bytes: &[u8]) -> Result<(), String> {
    const HEADER: &[u8] = b"-----BEGIN SSH SIGNATURE-----\n";
    const FOOTER: &[u8] = b"-----END SSH SIGNATURE-----\n";
    let body = bytes
        .strip_prefix(HEADER)
        .and_then(|value| value.strip_suffix(FOOTER))
        .ok_or("SSHSIG armor is malformed")?;
    let lines: Vec<_> = body.split_inclusive(|byte| *byte == b'\n').collect();
    if lines.is_empty()
        || lines.iter().enumerate().any(|(index, line)| {
            !line.ends_with(b"\n")
                || line.len() < 2
                || line.len() > 71
                || (index + 1 < lines.len() && line.len() != 71)
        })
    {
        return Err("SSHSIG armor wrapping is noncanonical".into());
    }
    let encoded: Vec<u8> = lines
        .iter()
        .flat_map(|line| line[..line.len() - 1].iter().copied())
        .collect();
    let blob = STANDARD
        .decode(&encoded)
        .map_err(|_| "SSHSIG Base64 is invalid")?;
    if STANDARD.encode(&blob).as_bytes() != encoded || !blob.starts_with(b"SSHSIG") {
        return Err("SSHSIG envelope is noncanonical".into());
    }
    Ok(())
}

struct VerificationFiles(PathBuf);
impl Drop for VerificationFiles {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[cfg(unix)]
fn trusted_ssh_keygen() -> Result<PathBuf, String> {
    Ok(PathBuf::from("/usr/bin/ssh-keygen"))
}

#[cfg(windows)]
fn trusted_ssh_keygen() -> Result<PathBuf, String> {
    use std::os::windows::ffi::OsStringExt;
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn GetSystemDirectoryW(buffer: *mut u16, capacity: u32) -> u32;
    }
    let mut buffer = [0u16; 32768];
    // SAFETY: buffer is writable for the advertised number of UTF-16 code units.
    let length = unsafe { GetSystemDirectoryW(buffer.as_mut_ptr(), buffer.len() as u32) } as usize;
    if length == 0 || length >= buffer.len() {
        return Err("trusted Windows OpenSSH directory is unavailable".into());
    }
    Ok(
        PathBuf::from(std::ffi::OsString::from_wide(&buffer[..length]))
            .join("OpenSSH")
            .join("ssh-keygen.exe"),
    )
}

fn verify_signature(
    contents: &[u8],
    signature: &[u8],
    public_key: &[u8],
    namespace: &str,
    principal: &str,
) -> Result<(), String> {
    canonical_signature(signature)?;
    key_fingerprint(public_key)?;
    static NEXT: AtomicU64 = AtomicU64::new(0);
    #[cfg(unix)]
    let temp = {
        use std::os::unix::fs::MetadataExt;
        let path = fs::canonicalize("/tmp").map_err(|error| error.to_string())?;
        let metadata = fs::metadata(&path).map_err(|error| error.to_string())?;
        if !metadata.is_dir() || metadata.uid() != 0 || metadata.mode() & 0o1000 == 0 {
            return Err("trusted system temporary directory is unavailable".into());
        }
        path
    };
    #[cfg(not(unix))]
    let temp = fs::canonicalize(std::env::temp_dir()).map_err(|error| error.to_string())?;
    let root = loop {
        let candidate = temp.join(format!(
            "sdk-runtime-verify-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        #[cfg(unix)]
        let created = {
            use std::os::unix::fs::DirBuilderExt;
            let mut builder = fs::DirBuilder::new();
            builder.mode(0o700);
            builder.create(&candidate)
        };
        #[cfg(not(unix))]
        let created = fs::create_dir(&candidate);
        match created {
            Ok(()) => break candidate,
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => {
                return Err(format!(
                    "create private signature verifier directory: {error}"
                ));
            }
        }
    };
    let guard = VerificationFiles(root.clone());
    let allowed = root.join("allowed-signers");
    let detached = root.join("signature.sig");
    let mut allowed_bytes = format!("{principal} ").into_bytes();
    allowed_bytes.extend_from_slice(public_key);
    fs::write(&allowed, allowed_bytes).map_err(|error| error.to_string())?;
    fs::write(&detached, signature).map_err(|error| error.to_string())?;
    let mut child = Command::new(trusted_ssh_keygen()?)
        .args(["-Y", "verify", "-f"])
        .arg(&allowed)
        .args(["-I", principal, "-n", namespace, "-s"])
        .arg(&detached)
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| format!("trusted OpenSSH verifier is unavailable: {error}"))?;
    child
        .stdin
        .take()
        .ok_or("OpenSSH verifier has no standard input")?
        .write_all(contents)
        .map_err(|error| error.to_string())?;
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
    let status = loop {
        if let Some(status) = child.try_wait().map_err(|error| error.to_string())? {
            break status;
        }
        if std::time::Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            return Err("trusted OpenSSH signature verification timed out".into());
        }
        std::thread::sleep(std::time::Duration::from_millis(10));
    };
    drop(guard);
    if !status.success() {
        return Err("external Runtime signature verification failed".into());
    }
    Ok(())
}

fn key_id(value: &str) -> Result<(), String> {
    if value.is_empty()
        || value.len() > 64
        || !(value.bytes().next().unwrap().is_ascii_lowercase()
            || value.bytes().next().unwrap().is_ascii_digit())
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-')
    {
        return Err("release key ID is invalid".into());
    }
    Ok(())
}

fn record(value: &Value) -> Result<(&str, &str), String> {
    let map = object(value, &["fingerprint", "keyId"])?;
    let id = text(map, "keyId")?;
    key_id(id)?;
    let fingerprint = text(map, "fingerprint")?;
    digest(fingerprint)?;
    Ok((id, fingerprint))
}

pub(crate) fn verify(
    snapshot: &EmbeddedRuntimeSnapshot,
    evidence: &Path,
    target: &str,
    root_key: &[u8],
) -> Result<Value, String> {
    if root_key.is_empty() {
        return Err("SDK-pinned release root is missing".into());
    }
    let root_fingerprint = key_fingerprint(root_key)?;
    let keyring_bytes = read_file(&evidence.join("release-keyring.json"), MAX_JSON)?;
    let delegation_bytes = read_file(&evidence.join("root-delegation.json"), MAX_JSON)?;
    let delegation_sig = read_file(&evidence.join("root-delegation.sig"), MAX_JSON)?;
    let claim_bytes = read_file(
        &evidence.join("runtime-library-authorization.json"),
        MAX_JSON,
    )?;
    let claim_sig = read_file(
        &evidence.join("runtime-library-authorization.sig"),
        MAX_JSON,
    )?;
    let delegation_value = canonical_json(&delegation_bytes)?;
    let delegation = object(
        &delegation_value,
        &[
            "keyringSha256",
            "kind",
            "rootFingerprint",
            "schemaVersion",
            "scope",
        ],
    )?;
    if delegation.get("schemaVersion").and_then(Value::as_u64) != Some(1)
        || text(delegation, "kind")? != "sdk-runtime-release-keyring-delegation"
        || text(delegation, "scope")? != "desktop-runtime-library"
        || text(delegation, "rootFingerprint")? != root_fingerprint
        || text(delegation, "keyringSha256")? != sha256(&keyring_bytes)
    {
        return Err("root delegation differs from the SDK-pinned root or exact keyring".into());
    }
    verify_signature(
        &delegation_bytes,
        &delegation_sig,
        root_key,
        ROOT_NAMESPACE,
        "codex-agent-sdk-runtime-root",
    )?;
    let keyring_value = canonical_json(&keyring_bytes)?;
    let keyring = object(
        &keyring_value,
        &[
            "activeKey",
            "algorithm",
            "namespace",
            "retiredKeys",
            "schemaVersion",
            "trustDomain",
        ],
    )?;
    if keyring.get("schemaVersion").and_then(Value::as_u64) != Some(1)
        || text(keyring, "algorithm")? != "ssh-ed25519"
        || text(keyring, "namespace")? != PRODUCT_NAMESPACE
        || text(keyring, "trustDomain")? != "release"
    {
        return Err("release keyring policy is invalid".into());
    }
    let mut keys = Vec::new();
    if !keyring["activeKey"].is_null() {
        keys.push(record(&keyring["activeKey"])?);
    }
    let retired = keyring["retiredKeys"]
        .as_array()
        .ok_or("retired release keys must be an array")?;
    let mut previous = "";
    for value in retired {
        let entry = record(value)?;
        if entry.0 <= previous {
            return Err("retired release keys are not sorted and unique".into());
        }
        previous = entry.0;
        keys.push(entry);
    }
    let mut ids = BTreeSet::new();
    let mut fingerprints = BTreeSet::new();
    for (id, fingerprint) in &keys {
        if !ids.insert(*id) || !fingerprints.insert(*fingerprint) {
            return Err("release keyring contains duplicate keys".into());
        }
        let bytes = read_file(&evidence.join("keys").join(format!("{id}.pub")), 4096)?;
        if key_fingerprint(&bytes)? != *fingerprint {
            return Err("release public key fingerprint mismatch".into());
        }
    }
    let mut expected: BTreeSet<String> = [
        "release-keyring.json",
        "root-delegation.json",
        "root-delegation.sig",
        "runtime-library-authorization.json",
        "runtime-library-authorization.sig",
    ]
    .into_iter()
    .map(str::to_owned)
    .collect();
    for (id, _) in &keys {
        expected.insert(format!("keys/{id}.pub"));
    }
    let mut actual = BTreeSet::new();
    for entry in fs::read_dir(evidence).map_err(|error| error.to_string())? {
        let entry = entry.map_err(|error| error.to_string())?;
        let name = entry
            .file_name()
            .into_string()
            .map_err(|_| "non-UTF-8 evidence entry")?;
        if name == "keys" {
            for key in fs::read_dir(entry.path()).map_err(|error| error.to_string())? {
                let key = key.map_err(|error| error.to_string())?;
                actual.insert(format!(
                    "keys/{}",
                    key.file_name()
                        .into_string()
                        .map_err(|_| "non-UTF-8 key entry")?
                ));
            }
        } else {
            actual.insert(name);
        }
    }
    if actual != expected {
        return Err("external Runtime evidence has extra or missing files".into());
    }
    let claim_value = canonical_json(&claim_bytes)?;
    let claim = object(
        &claim_value,
        &[
            "aggregateAttestationSha256",
            "aggregateManifestSha256",
            "kind",
            "runtimeIdentity",
            "runtimeLibrarySha256",
            "runtimeVersion",
            "schemaVersion",
            "signing",
            "variantAttestationSha256",
            "variantBundleSha256",
            "variantManifestSha256",
        ],
    )?;
    if claim.get("schemaVersion").and_then(Value::as_u64) != Some(1)
        || text(claim, "kind")? != "desktop-runtime-library-authorization"
    {
        return Err("Runtime library authorization schema is invalid".into());
    }
    for field in [
        "runtimeLibrarySha256",
        "variantBundleSha256",
        "variantManifestSha256",
        "aggregateManifestSha256",
        "variantAttestationSha256",
        "aggregateAttestationSha256",
    ] {
        digest(text(claim, field)?)?;
    }
    if text(claim, "runtimeLibrarySha256")? != snapshot.digest() {
        return Err("external Runtime library differs from its signed authorization".into());
    }
    snapshot.verify()?;
    let signing = object(
        &claim["signing"],
        &[
            "algorithm",
            "fingerprint",
            "keyId",
            "namespace",
            "trustDomain",
        ],
    )?;
    if text(signing, "algorithm")? != "ssh-ed25519"
        || text(signing, "namespace")? != PRODUCT_NAMESPACE
        || text(signing, "trustDomain")? != "release"
    {
        return Err("release signing metadata is invalid".into());
    }
    let signer = keys
        .iter()
        .find(|(id, fingerprint)| {
            *id == text(signing, "keyId").unwrap_or("")
                && *fingerprint == text(signing, "fingerprint").unwrap_or("")
        })
        .ok_or("authorization signer is not in the root-delegated keyring")?;
    let signer_bytes = read_file(
        &evidence.join("keys").join(format!("{}.pub", signer.0)),
        4096,
    )?;
    if key_fingerprint(&signer_bytes)? != signer.1 {
        return Err("authorization signer key changed during verification".into());
    }
    verify_signature(
        &claim_bytes,
        &claim_sig,
        &signer_bytes,
        PRODUCT_NAMESPACE,
        "codex-agent-product",
    )?;
    let compatibility_value = canonical_json(include_bytes!("../native/sdk-compatibility.json"))?;
    let compatibility = object(
        &compatibility_value,
        &[
            "contract",
            "platformRuntime",
            "runtime",
            "schemaVersion",
            "sdkVersion",
        ],
    )?;
    let runtime = compatibility["runtime"]
        .as_object()
        .ok_or("SDK Runtime policy is malformed")?;
    let identity = object(
        &claim["runtimeIdentity"],
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
    )?;
    for field in [
        "buildInputDigest",
        "componentId",
        "contractComponentDigest",
        "contractDigest",
    ] {
        digest(text(identity, field)?)?;
    }
    version(text(identity, "appServerVersion")?)?;
    let abi = version(text(identity, "cAbiVersion")?)?;
    let release = version(text(claim, "runtimeVersion")?)?;
    let runtime_version = version(text(identity, "runtimeCompatibilityVersion")?)?;
    let release_range = range(
        runtime["compatibleReleaseRange"]
            .as_str()
            .ok_or("SDK release range is invalid")?,
    )?;
    let runtime_range = range(
        runtime["compatibleRuntimeCompatibilityRange"]
            .as_str()
            .ok_or("SDK Runtime range is invalid")?,
    )?;
    if identity.get("schemaVersion").and_then(Value::as_u64)
        != runtime["requiredIdentitySchema"].as_u64()
        || text(identity, "target")? != target
        || text(identity, "contractDigest")?
            != runtime["requiredContractDigest"]
                .as_str()
                .ok_or("SDK Contract digest is invalid")?
        || !(release_range.0 <= release && release < release_range.1)
        || !(runtime_range.0 <= runtime_version && runtime_version < runtime_range.1)
        || abi.0
            != runtime["requiredAbiMajor"]
                .as_u64()
                .ok_or("SDK ABI major is invalid")?
        || abi.1
            < runtime["minimumAbiMinor"]
                .as_u64()
                .ok_or("SDK ABI minor is invalid")?
        || abi.0 > 255
        || abi.1 > 255
        || abi.2 > 65535
    {
        return Err("external Runtime authorization is incompatible with this SDK".into());
    }
    Ok(claim["runtimeIdentity"].clone())
}

pub(crate) fn identity_matches(expected: &Value, bytes: &[u8]) -> Result<(), String> {
    let value = canonical_json(&[bytes, b"\n"].concat())?;
    if &value != expected {
        return Err("loaded Runtime identity differs from signed authorization".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{canonical_json, read_bounded};

    #[test]
    fn evidence_reader_caps_a_growing_source_before_allocating_more_than_limit() {
        let mut source = std::io::Cursor::new(vec![b'x'; 1024]);
        assert!(
            read_bounded(&mut source, 16)
                .unwrap_err()
                .contains("exceeds its size limit")
        );
        assert_eq!(source.position(), 17);

        let mut exact = std::io::Cursor::new(vec![b'x'; 16]);
        assert_eq!(read_bounded(&mut exact, 16).unwrap(), vec![b'x'; 16]);
    }

    #[test]
    fn evidence_json_rejects_duplicate_keys_and_floats() {
        assert!(canonical_json(b"{\"a\":1,\"a\":1}\n").is_err());
        assert!(canonical_json(b"{\"a\":1.0}\n").is_err());
        assert!(canonical_json(b"{\"a\":1}\n").is_ok());
    }

    #[cfg(unix)]
    #[test]
    fn evidence_reader_rejects_symlinked_sidecar_and_parent() {
        use super::read_file;
        use std::os::unix::fs::symlink;

        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "codex-agent-rust-evidence-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir(&root).unwrap();
        let real = root.join("real");
        std::fs::create_dir(&real).unwrap();
        std::fs::write(real.join("release-keyring.json"), b"evidence").unwrap();
        symlink(real.join("release-keyring.json"), root.join("sidecar.json")).unwrap();
        symlink(&real, root.join("sidecars")).unwrap();

        for path in [
            root.join("sidecar.json"),
            root.join("sidecars/release-keyring.json"),
        ] {
            assert!(read_file(&path, 1024).unwrap_err().contains("symlink"));
        }
        std::fs::remove_dir_all(root).unwrap();
    }
}
