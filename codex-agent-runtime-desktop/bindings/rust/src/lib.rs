//! Rust 1.95+ projection of the local Codex Agent Desktop/Host C SDK.
//!
//! The crate contains no runtime or protocol implementation. It validates and loads the stable
//! `codex_agent_*` C ABI, then projects its Host → Agent → Conversation lifecycle as typed owned
//! values, cancellable futures, and state streams. Hosts and conversations require an explicitly
//! awaited asynchronous close before their native token can be released.

mod async_runtime;
mod enums;
mod ffi;
#[allow(dead_code)]
mod native_values;
mod residual_values;
mod services;
mod values;

pub use async_runtime::{CodexOperation, CodexStateStream, NextState};
pub use enums::*;
pub use residual_values::*;
pub use services::*;
pub use values::*;

use std::error::Error;
use std::fmt::{Display, Formatter};
use std::marker::PhantomData;
use std::path::{Path, PathBuf};
use std::rc::Rc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, OnceLock, Weak};
use std::time::Duration;

use async_runtime::{start_operation, start_subscription};

/// Encoded C ABI version required by this crate (1.12.0).
pub const CODEX_AGENT_ABI_VERSION: u32 = ffi::ABI_VERSION;

/// Status returned by the stable C SDK.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[non_exhaustive]
pub enum Status {
    /// Success.
    Ok,
    /// Invalid input or output slot.
    InvalidArgument,
    /// Allocation failed.
    OutOfMemory,
    /// A destroyed handle was reused.
    StaleHandle,
    /// A handle had the wrong type.
    WrongHandleType,
    /// A handle belongs to a different context.
    WrongContext,
    /// The native object is still in use.
    Busy,
    /// The operation was cancelled.
    Cancelled,
    /// Unexpected native failure.
    InternalError,
    /// A destination buffer was too small.
    BufferTooSmall,
    /// The loaded C ABI is incompatible.
    UnsupportedAbi,
    /// The object is closed.
    Closed,
    /// Waiting here would deadlock.
    WouldDeadlock,
    /// The requested value is absent or not ready.
    NotReady,
    /// The operation completed with a structured failure.
    OperationFailed,
    /// A status added by a newer ABI.
    Unknown(i32),
}

impl Status {
    pub(crate) const fn from_raw(value: i32) -> Self {
        match value {
            0 => Self::Ok,
            1 => Self::InvalidArgument,
            2 => Self::OutOfMemory,
            3 => Self::StaleHandle,
            4 => Self::WrongHandleType,
            5 => Self::WrongContext,
            6 => Self::Busy,
            7 => Self::Cancelled,
            8 => Self::InternalError,
            9 => Self::BufferTooSmall,
            10 => Self::UnsupportedAbi,
            11 => Self::Closed,
            12 => Self::WouldDeadlock,
            13 => Self::NotReady,
            14 => Self::OperationFailed,
            other => Self::Unknown(other),
        }
    }
}

impl Display for Status {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        let name = match self {
            Self::Ok => "ok",
            Self::InvalidArgument => "invalid argument",
            Self::OutOfMemory => "out of memory",
            Self::StaleHandle => "stale handle",
            Self::WrongHandleType => "wrong handle type",
            Self::WrongContext => "wrong context",
            Self::Busy => "busy",
            Self::Cancelled => "cancelled",
            Self::InternalError => "internal error",
            Self::BufferTooSmall => "buffer too small",
            Self::UnsupportedAbi => "unsupported ABI",
            Self::Closed => "closed",
            Self::WouldDeadlock => "would deadlock",
            Self::NotReady => "not ready",
            Self::OperationFailed => "operation failed",
            Self::Unknown(value) => return write!(formatter, "unknown status {value}"),
        };
        formatter.write_str(name)
    }
}

/// Structured failure reported by a completed Codex operation or state.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CodexFailure {
    /// Stable failure code.
    pub code: String,
    /// Human-readable failure detail.
    pub message: String,
    /// Whether retry or user remediation may recover.
    pub recoverable: bool,
}

/// Error surfaced by the Rust projection.
#[derive(Debug)]
pub struct CodexError {
    /// C SDK status.
    pub status: Status,
    /// Operation being attempted.
    pub action: String,
    /// Structured failure when the C SDK reported `OPERATION_FAILED`.
    pub failure: Option<CodexFailure>,
}

impl CodexError {
    pub(crate) fn new(status: Status, action: impl Into<String>) -> Self {
        Self {
            status,
            action: action.into(),
            failure: None,
        }
    }

    fn load(action: impl Into<String>) -> Self {
        Self::new(Status::InternalError, action)
    }
}

impl Display for CodexError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        if let Some(failure) = &self.failure {
            write!(
                formatter,
                "{}: {} ({}: {})",
                self.action, self.status, failure.code, failure.message
            )
        } else {
            write!(formatter, "{}: {}", self.action, self.status)
        }
    }
}

impl Error for CodexError {}

/// A native resource that could not be released after bounded quiescence retries.
///
/// The Rust binding quarantines the associated context/library instead of unloading live native
/// state. Applications can drain these diagnostics for logging or fail-fast policy.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CleanupIssue {
    /// Resource kind whose release failed.
    pub resource: String,
    /// Final native status.
    pub status: Status,
    /// Total release attempts.
    pub attempts: u32,
}

enum CleanupLease {
    Token {
        _context: Arc<ContextInner>,
        _token: usize,
    },
    Context {
        _library: Arc<LibraryInner>,
        _original_slot: usize,
    },
}

#[derive(Default)]
struct CleanupRegistry {
    issues: Vec<CleanupIssue>,
    leases: Vec<CleanupLease>,
}

fn cleanup_registry() -> &'static Mutex<CleanupRegistry> {
    static REGISTRY: OnceLock<Mutex<CleanupRegistry>> = OnceLock::new();
    REGISTRY.get_or_init(|| Mutex::new(CleanupRegistry::default()))
}

const CLEANUP_MAX_ATTEMPTS: u32 = 24;

pub(crate) fn retry_cleanup(mut release: impl FnMut() -> i32) -> (i32, u32) {
    let mut last_status = ffi::STATUS_BUSY;
    for attempt in 1..=CLEANUP_MAX_ATTEMPTS {
        let status = release();
        last_status = status;
        if status == ffi::STATUS_OK {
            return (status, attempt);
        }
        if status != ffi::STATUS_BUSY {
            return (status, attempt);
        }
        if attempt < CLEANUP_MAX_ATTEMPTS {
            if attempt <= 3 {
                std::thread::yield_now();
            } else {
                let shift = (attempt - 4).min(4);
                std::thread::sleep(Duration::from_micros(100_u64 << shift));
            }
        }
    }
    (last_status, CLEANUP_MAX_ATTEMPTS)
}

pub(crate) fn quarantine_token(
    context: Arc<ContextInner>,
    token: usize,
    resource: &str,
    status: i32,
    attempts: u32,
) {
    let mut registry = cleanup_registry()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    registry.issues.push(CleanupIssue {
        resource: resource.into(),
        status: Status::from_raw(status),
        attempts,
    });
    registry.leases.push(CleanupLease::Token {
        _context: context,
        _token: token,
    });
}

fn quarantine_context(
    library: Arc<LibraryInner>,
    original_slot: usize,
    status: i32,
    attempts: u32,
) {
    let mut registry = cleanup_registry()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    registry.issues.push(CleanupIssue {
        resource: "context".into(),
        status: Status::from_raw(status),
        attempts,
    });
    registry.leases.push(CleanupLease::Context {
        _library: library,
        _original_slot: original_slot,
    });
}

pub(crate) fn check(status: i32, action: &'static str) -> Result<(), CodexError> {
    if status == ffi::STATUS_OK {
        Ok(())
    } else {
        Err(CodexError::new(Status::from_raw(status), action))
    }
}

/// One of the five native desktop targets shipped by the verified C SDK.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RuntimeTarget {
    /// Apple Silicon macOS.
    MacosArm64,
    /// Intel macOS.
    MacosX64,
    /// Arm64 Linux.
    LinuxArm64,
    /// x86-64 Linux.
    LinuxX64,
    /// x86-64 Windows.
    WindowsX64,
}

impl RuntimeTarget {
    /// Detects the current supported process target.
    pub fn current() -> Result<Self, CodexError> {
        match (std::env::consts::OS, std::env::consts::ARCH) {
            ("macos", "aarch64") => Ok(Self::MacosArm64),
            ("macos", "x86_64") => Ok(Self::MacosX64),
            ("linux", "aarch64") => Ok(Self::LinuxArm64),
            ("linux", "x86_64") => Ok(Self::LinuxX64),
            ("windows", "x86_64") => Ok(Self::WindowsX64),
            (os, arch) => Err(CodexError::load(format!(
                "unsupported Codex Agent desktop target {os}-{arch}"
            ))),
        }
    }

    /// Stable package target identifier.
    pub const fn identifier(self) -> &'static str {
        match self {
            Self::MacosArm64 => "osx-arm64",
            Self::MacosX64 => "osx-x64",
            Self::LinuxArm64 => "linux-arm64",
            Self::LinuxX64 => "linux-x64",
            Self::WindowsX64 => "win-x64",
        }
    }

    /// Native library file name for this target.
    pub const fn library_name(self) -> &'static str {
        match self {
            Self::MacosArm64 | Self::MacosX64 => "libcodex_agent.dylib",
            Self::LinuxArm64 | Self::LinuxX64 => "libcodex_agent.so",
            Self::WindowsX64 => "codex_agent.dll",
        }
    }
}

struct LibraryInner {
    api: ffi::Api,
}

/// A loaded, ABI-validated C SDK library.
#[derive(Clone)]
pub struct CodexNativeLibrary {
    inner: Arc<LibraryInner>,
}

impl CodexNativeLibrary {
    /// Loads an explicit C SDK shared library and rejects missing symbols or incompatible ABI.
    pub fn load(path: impl AsRef<Path>) -> Result<Self, CodexError> {
        let api = ffi::Api::load(path.as_ref()).map_err(|error| match error {
            ffi::LoadError::UnsupportedAbi(actual) => CodexError::new(
                Status::UnsupportedAbi,
                format!(
                    "incompatible Codex Agent C SDK ABI 0x{actual:08x}; Rust binding requires ABI 1.12 compatibility"
                ),
            ),
            ffi::LoadError::Open(message) | ffi::LoadError::MissingSymbol(message) => {
                CodexError::load(message)
            }
        })?;
        Ok(Self {
            inner: Arc::new(LibraryInner { api }),
        })
    }

    /// Loads the matching-host library from deterministic package/application locations.
    ///
    /// `CODEX_AGENT_LIBRARY` takes precedence. Otherwise the loader checks beside the executable,
    /// then `runtimes/<target>/native`. It never depends on a Cargo source/cache directory or
    /// falls back to a same-named library from the platform loader search path.
    pub fn load_default() -> Result<Self, CodexError> {
        let target = RuntimeTarget::current()?;
        if let Some(path) = std::env::var_os("CODEX_AGENT_LIBRARY") {
            return Self::load(PathBuf::from(path));
        }
        let file = target.library_name();
        let mut candidates = Vec::new();
        if let Ok(executable) = std::env::current_exe()
            && let Some(directory) = executable.parent()
        {
            candidates.push(directory.join(file));
            candidates.push(
                directory
                    .join("runtimes")
                    .join(target.identifier())
                    .join("native")
                    .join(file),
            );
        }
        if let Some(path) = candidates.iter().find(|candidate| candidate.is_file()) {
            return Self::load(path);
        }
        Err(CodexError::load(format!(
            "could not find verified {} C SDK library {file}; set CODEX_AGENT_LIBRARY to an explicit verified library",
            target.identifier()
        )))
    }

    /// Returns the loaded library's encoded ABI version.
    pub fn abi_version(&self) -> u32 {
        // SAFETY: the function has no inputs and the library outlives its function table.
        unsafe { (self.inner.api.abi_version)() }
    }

    /// Drains cleanup failures recorded by native destructors.
    ///
    /// Quarantined native storage remains retained even after its diagnostic is drained.
    pub fn take_cleanup_issues() -> Vec<CleanupIssue> {
        std::mem::take(
            &mut cleanup_registry()
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner())
                .issues,
        )
    }
}

pub(crate) struct ContextInner {
    library: Arc<LibraryInner>,
    // The heap allocation preserves the exact slot address passed to context_create, as required
    // by the C ABI's unique context ownership rule.
    slot: Mutex<Box<*mut ffi::Context>>,
}

// SAFETY: the C ABI explicitly invokes callbacks on worker threads. The context pointer is opaque,
// remains alive through Arc ownership, and its sole mutable owner slot is serialized by `slot`.
unsafe impl Send for ContextInner {}
// SAFETY: same argument as Send; native calls copy the opaque pointer while destruction exclusively
// locks and mutates the original heap slot after all child Arcs have been released.
unsafe impl Sync for ContextInner {}

impl ContextInner {
    fn create(library: Arc<LibraryInner>) -> Result<Arc<Self>, CodexError> {
        let mut slot = Box::new(std::ptr::null_mut());
        // SAFETY: this is a non-null, initially-null output slot that remains heap-stable.
        let status = unsafe { (library.api.context_create)(&mut *slot) };
        check(status, "create native context")?;
        Ok(Arc::new(Self {
            library,
            slot: Mutex::new(slot),
        }))
    }

    fn ptr(&self) -> *mut ffi::Context {
        **self
            .slot
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    fn destroy_snapshot(self: &Arc<Self>, snapshot: *mut ffi::Snapshot) {
        if snapshot.is_null() {
            return;
        }
        let mut raw = snapshot;
        let (status, attempts) = retry_cleanup(|| {
            // SAFETY: raw is a unique transferred snapshot token in this local slot.
            unsafe { (self.library.api.snapshot_destroy)(self.ptr(), &mut raw) }
        });
        if status != ffi::STATUS_OK {
            quarantine_token(self.clone(), raw as usize, "snapshot", status, attempts);
        }
    }
}

impl Drop for ContextInner {
    fn drop(&mut self) {
        let slot = self
            .slot
            .get_mut()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let (status, attempts) = retry_cleanup(|| {
            // SAFETY: this is the original, stable output slot and no child Arc remains.
            unsafe { (self.library.api.context_destroy)(&mut **slot) }
        });
        if status != ffi::STATUS_OK {
            let original_slot =
                Box::into_raw(std::mem::replace(slot, Box::new(std::ptr::null_mut()))) as usize;
            quarantine_context(self.library.clone(), original_slot, status, attempts);
        }
    }
}

type Release<T> = unsafe fn(&ffi::Api, *mut ffi::Context, *mut *mut T) -> i32;

#[derive(Clone, Copy, Eq, PartialEq)]
enum ReleasePolicy {
    Ordinary,
    ExplicitAsyncClose,
}

struct OwnedHandle<T> {
    context: Arc<ContextInner>,
    raw: Mutex<usize>,
    release: Release<T>,
    resource: &'static str,
    release_policy: ReleasePolicy,
    semantically_closed: AtomicBool,
}

// SAFETY: the only mutable state is the owned token slot guarded by `raw`; the opaque pointer is
// copied for calls while ContextInner and its loaded library remain alive.
unsafe impl<T> Send for OwnedHandle<T> {}
// SAFETY: release is serialized and all other access is read-only pointer copying.
unsafe impl<T> Sync for OwnedHandle<T> {}

impl<T> OwnedHandle<T> {
    fn new(
        context: Arc<ContextInner>,
        raw: *mut T,
        release: Release<T>,
        resource: &'static str,
    ) -> Self {
        Self {
            context,
            raw: Mutex::new(raw as usize),
            release,
            resource,
            release_policy: ReleasePolicy::Ordinary,
            semantically_closed: AtomicBool::new(false),
        }
    }

    fn new_explicit_close(
        context: Arc<ContextInner>,
        raw: *mut T,
        release: Release<T>,
        resource: &'static str,
    ) -> Self {
        Self {
            context,
            raw: Mutex::new(raw as usize),
            release,
            resource,
            release_policy: ReleasePolicy::ExplicitAsyncClose,
            semantically_closed: AtomicBool::new(false),
        }
    }

    fn mark_semantically_closed(&self) {
        self.semantically_closed.store(true, Ordering::Release);
    }

    fn ptr(&self) -> Result<*mut T, CodexError> {
        let raw = *self
            .raw
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if raw == 0 {
            Err(CodexError::new(
                Status::Closed,
                "use released native handle",
            ))
        } else {
            Ok(raw as *mut T)
        }
    }
}

impl<T> Drop for OwnedHandle<T> {
    fn drop(&mut self) {
        let raw = self
            .raw
            .get_mut()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let mut pointer = *raw as *mut T;
        let release = || {
            // SAFETY: pointer is this object's unique owned token and the local slot is exclusive.
            unsafe { (self.release)(&self.context.library.api, self.context.ptr(), &mut pointer) }
        };
        let explicitly_unclosed = self.release_policy == ReleasePolicy::ExplicitAsyncClose
            && !self.semantically_closed.load(Ordering::Acquire);
        // An unmarked alias may still have been semantically closed through another alias, so it
        // must receive the same bounded BUSY quiescence check before being diagnosed as unclosed.
        let (status, attempts) = retry_cleanup(release);
        if status != ffi::STATUS_OK {
            let resource = if explicitly_unclosed && status == ffi::STATUS_BUSY {
                match self.resource {
                    "host" => "host (explicit async close required)",
                    "conversation" => "conversation (explicit async close required)",
                    resource => resource,
                }
            } else {
                self.resource
            };
            quarantine_token(
                self.context.clone(),
                pointer as usize,
                resource,
                status,
                attempts,
            );
        }
        *raw = 0;
    }
}

unsafe fn release_host(
    api: &ffi::Api,
    context: *mut ffi::Context,
    value: *mut *mut ffi::Host,
) -> i32 {
    // SAFETY: forwarded unchanged to the exact loaded C ABI function.
    unsafe { (api.host_release)(context, value) }
}
unsafe fn release_agent(
    api: &ffi::Api,
    context: *mut ffi::Context,
    value: *mut *mut ffi::Agent,
) -> i32 {
    // SAFETY: forwarded unchanged to the exact loaded C ABI function.
    unsafe { (api.agent_release)(context, value) }
}
unsafe fn release_conversations(
    api: &ffi::Api,
    context: *mut ffi::Context,
    value: *mut *mut ffi::Conversations,
) -> i32 {
    // SAFETY: forwarded unchanged to the exact loaded C ABI function.
    unsafe { (api.conversations_release)(context, value) }
}
unsafe fn release_conversation(
    api: &ffi::Api,
    context: *mut ffi::Context,
    value: *mut *mut ffi::Conversation,
) -> i32 {
    // SAFETY: forwarded unchanged to the exact loaded C ABI function.
    unsafe { (api.conversation_release)(context, value) }
}

struct Snapshot {
    context: Arc<ContextInner>,
    raw: *mut ffi::Snapshot,
}

impl Drop for Snapshot {
    fn drop(&mut self) {
        self.context.destroy_snapshot(self.raw);
    }
}

fn copy_string(
    mut copy: impl FnMut(*mut u8, usize, *mut usize) -> i32,
) -> Result<String, CodexError> {
    let mut required = 0;
    let status = copy(std::ptr::null_mut(), 0, &mut required);
    if status != ffi::STATUS_OK && status != ffi::STATUS_BUFFER_TOO_SMALL {
        return Err(CodexError::new(
            Status::from_raw(status),
            "measure native UTF-8 string",
        ));
    }
    let mut bytes = vec![0; required];
    if required != 0 {
        let mut written = required;
        check(
            copy(bytes.as_mut_ptr(), bytes.len(), &mut written),
            "copy native UTF-8 string",
        )?;
        if written != required {
            return Err(CodexError::new(
                Status::InternalError,
                "immutable native string changed size",
            ));
        }
    }
    String::from_utf8(bytes)
        .map_err(|_| CodexError::new(Status::InternalError, "native C SDK returned invalid UTF-8"))
}

fn read_failure(
    context: &Arc<ContextInner>,
    mut raw: *mut ffi::Failure,
) -> Result<CodexFailure, CodexError> {
    let api = &context.library.api;
    let result = (|| {
        let code = copy_string(|buffer, capacity, required| {
            // SAFETY: raw is a live owned failure and output buffers obey the C copy contract.
            unsafe { (api.failure_code_copy)(context.ptr(), raw, buffer, capacity, required) }
        })?;
        let message = copy_string(|buffer, capacity, required| {
            // SAFETY: raw is a live owned failure and output buffers obey the C copy contract.
            unsafe { (api.failure_message_copy)(context.ptr(), raw, buffer, capacity, required) }
        })?;
        let mut recoverable = 0;
        // SAFETY: recoverable is a valid scalar output for this live failure.
        let status = unsafe { (api.failure_is_recoverable)(context.ptr(), raw, &mut recoverable) };
        check(status, "read native failure recovery status")?;
        Ok(CodexFailure {
            code,
            message,
            recoverable: recoverable != 0,
        })
    })();
    let (release, attempts) = retry_cleanup(|| {
        // SAFETY: raw is the unique failure token returned to this projection.
        unsafe { (api.failure_release)(context.ptr(), &mut raw) }
    });
    if release != ffi::STATUS_OK {
        quarantine_token(context.clone(), raw as usize, "failure", release, attempts);
        return Err(CodexError::new(
            Status::from_raw(release),
            "release native failure",
        ));
    }
    result
}

pub(crate) fn operation_error(
    context: &Arc<ContextInner>,
    operation: *mut ffi::Operation,
    result: i32,
) -> CodexError {
    let mut error = CodexError::new(Status::from_raw(result), "complete native operation");
    if result == ffi::STATUS_OPERATION_FAILED {
        let mut failure = std::ptr::null_mut();
        // SAFETY: operation is complete/live and failure is an initially-null output slot.
        if unsafe {
            (context.library.api.operation_failure)(context.ptr(), operation, &mut failure)
        } == ffi::STATUS_OK
        {
            match read_failure(context, failure) {
                Ok(value) => error.failure = Some(value),
                Err(cleanup_error) => return cleanup_error,
            }
        }
    }
    error
}

/// Client identity supplied to the Codex host.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ClientInfo {
    /// Stable client name.
    pub name: String,
    /// Display title.
    pub title: String,
    /// Client version.
    pub version: String,
}

/// Directories and client identity used to create a host.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HostOptions {
    /// Directory containing the verified Codex runtime bundle.
    pub bundle_directory: String,
    /// Writable host data directory.
    pub data_directory: String,
    /// Calling application identity.
    pub client_info: ClientInfo,
}

impl HostOptions {
    fn validate(&self) -> Result<(), CodexError> {
        if [
            self.bundle_directory.as_str(),
            self.data_directory.as_str(),
            self.client_info.name.as_str(),
            self.client_info.title.as_str(),
            self.client_info.version.as_str(),
        ]
        .iter()
        .any(|value| value.trim().is_empty())
        {
            Err(CodexError::new(
                Status::InvalidArgument,
                "host options must not contain blank strings",
            ))
        } else {
            Ok(())
        }
    }
}

/// Host lifecycle state kind.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum HostStateKind {
    /// Created, not started.
    New,
    /// Restoring persisted state.
    Restoring,
    /// Waiting for workspace selection.
    WorkspaceRequired,
    /// Preparing the runtime.
    Preparing,
    /// Ready with an agent.
    Ready = 4,
    /// Failed.
    Failed,
    /// Closed.
    Closed,
}

impl TryFrom<i32> for HostStateKind {
    type Error = CodexError;

    fn try_from(value: i32) -> Result<Self, Self::Error> {
        match value {
            0 => Ok(Self::New),
            1 => Ok(Self::Restoring),
            2 => Ok(Self::WorkspaceRequired),
            3 => Ok(Self::Preparing),
            4 => Ok(Self::Ready),
            5 => Ok(Self::Failed),
            6 => Ok(Self::Closed),
            _ => Err(CodexError::new(
                Status::InternalError,
                format!("unknown host state kind {value}"),
            )),
        }
    }
}

/// Why a workspace must be selected again.
#[repr(i32)]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum WorkspaceSelectionReason {
    /// No previous selection.
    NotSelected = 0,
    /// The selected path no longer exists.
    NotFound = 1,
    /// Access to the path was revoked.
    AccessRevoked = 2,
    /// The selection is invalid.
    InvalidSelection = 3,
}

impl TryFrom<i32> for WorkspaceSelectionReason {
    type Error = CodexError;

    fn try_from(value: i32) -> Result<Self, Self::Error> {
        match value {
            0 => Ok(Self::NotSelected),
            1 => Ok(Self::NotFound),
            2 => Ok(Self::AccessRevoked),
            3 => Ok(Self::InvalidSelection),
            _ => Err(CodexError::new(
                Status::InternalError,
                format!("unknown workspace selection reason {value}"),
            )),
        }
    }
}

/// Selected workspace value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Workspace {
    /// Canonical path.
    pub path: String,
    /// User-facing name.
    pub display_name: String,
}

/// Workspace selection requirement.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct WorkspaceRequirement {
    /// Reason selection is needed.
    pub reason: WorkspaceSelectionReason,
    /// User-facing explanation.
    pub message: String,
}

/// Immutable host state snapshot.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HostStateReady {
    agent: CodexAgent,
}

impl HostStateReady {
    /// Creates the canonical ready-state projection for an identity-stable Agent.
    pub const fn new(agent: CodexAgent) -> Self {
        Self { agent }
    }

    /// Returns the identity-stable Agent projected by this ready state.
    pub fn agent(&self) -> CodexAgent {
        self.agent.clone()
    }
}

/// Immutable host lifecycle snapshot.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HostState {
    /// Lifecycle state.
    pub kind: HostStateKind,
    /// Workspace when one is available.
    pub workspace: Option<Workspace>,
    /// Selection requirement in `WorkspaceRequired`.
    pub requirement: Option<WorkspaceRequirement>,
    /// Structured failure in `Failed`.
    pub failure: Option<CodexFailure>,
    /// Typed ready-state payload when `kind` is [`HostStateKind::Ready`].
    pub ready: Option<HostStateReady>,
}

/// Conversation approval preset.
#[repr(i32)]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ApprovalPreset {
    /// Never approve privileged actions.
    Never = 0,
    /// Let the runtime review automatically.
    AutoReview = 1,
    /// Ask the user.
    AskMe = 2,
    /// Use strict approval policy.
    Strict = 3,
}

impl ApprovalPreset {
    const fn raw(self) -> i32 {
        self as i32
    }

    pub(crate) const fn from_raw(value: i32) -> Option<Self> {
        match value {
            0 => Some(Self::Never),
            1 => Some(Self::AutoReview),
            2 => Some(Self::AskMe),
            3 => Some(Self::Strict),
            _ => None,
        }
    }
}

/// Options for opening a new or existing conversation.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct ConversationOpenOptions {
    /// Existing conversation identifier, or `None` to create one.
    pub conversation_id: Option<String>,
    /// Optional approval override.
    pub approval_preset: Option<ApprovalPreset>,
    /// Optional service tier.
    pub service_tier: Option<String>,
}

/// Conversation lifecycle status.
#[repr(i32)]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ConversationStatus {
    /// Created, not opened.
    New = 0,
    /// Opening.
    Opening = 1,
    /// Ready for a turn.
    Ready = 2,
    /// Starting a turn.
    StartingTurn = 3,
    /// Running a turn.
    RunningTurn = 4,
    /// Cancelling a turn.
    CancellingTurn = 5,
    /// Reloading.
    Reloading = 6,
    /// Failed.
    Failed = 7,
    /// Closed.
    Closed = 8,
}

impl TryFrom<i32> for ConversationStatus {
    type Error = CodexError;

    fn try_from(value: i32) -> Result<Self, Self::Error> {
        match value {
            0 => Ok(Self::New),
            1 => Ok(Self::Opening),
            2 => Ok(Self::Ready),
            3 => Ok(Self::StartingTurn),
            4 => Ok(Self::RunningTurn),
            5 => Ok(Self::CancellingTurn),
            6 => Ok(Self::Reloading),
            7 => Ok(Self::Failed),
            8 => Ok(Self::Closed),
            _ => Err(CodexError::new(
                Status::InternalError,
                format!("unknown conversation status {value}"),
            )),
        }
    }
}

/// Immutable conversation state snapshot.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ConversationState {
    /// Current lifecycle status.
    pub status: ConversationStatus,
    /// Structured failure in `Failed`.
    pub failure: Option<CodexFailure>,
}

fn parse_host_state(
    context: &Arc<ContextInner>,
    snapshot: *mut ffi::Snapshot,
    host: &Arc<HostInner>,
) -> Result<HostState, CodexError> {
    let api = &context.library.api;
    type Kind = unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Snapshot, *mut i32) -> i32;
    let kind_getter: services::ExactSymbol<Kind> =
        services::exact_symbol(context, b"codex_agent_host_state_kind\0")?;
    let mut raw_kind = 0;
    // SAFETY: snapshot is live for the duration of this projection and output is valid.
    let status = kind_getter.invoke(|call| unsafe { call(context.ptr(), snapshot, &mut raw_kind) });
    check(status, "read host state kind")?;
    let kind = HostStateKind::try_from(raw_kind)?;
    let mut has_workspace = 0;
    // SAFETY: snapshot and scalar output obey the getter contract.
    let status =
        unsafe { (api.host_state_has_workspace)(context.ptr(), snapshot, &mut has_workspace) };
    check(status, "read host workspace availability")?;
    let workspace = if has_workspace != 0 {
        Some(Workspace {
            path: copy_string(|buffer, capacity, required| {
                // SAFETY: output buffer follows the immutable snapshot copy contract.
                unsafe {
                    (api.host_state_workspace_path_copy)(
                        context.ptr(),
                        snapshot,
                        buffer,
                        capacity,
                        required,
                    )
                }
            })?,
            display_name: copy_string(|buffer, capacity, required| {
                // SAFETY: output buffer follows the immutable snapshot copy contract.
                unsafe {
                    (api.host_state_workspace_display_name_copy)(
                        context.ptr(),
                        snapshot,
                        buffer,
                        capacity,
                        required,
                    )
                }
            })?,
        })
    } else {
        None
    };
    let requirement = if kind == HostStateKind::WorkspaceRequired {
        let mut raw_reason = 0;
        // SAFETY: this getter is valid for WorkspaceRequired state snapshots.
        let status = unsafe {
            (api.host_state_requirement_reason)(context.ptr(), snapshot, &mut raw_reason)
        };
        check(status, "read workspace selection reason")?;
        Some(WorkspaceRequirement {
            reason: WorkspaceSelectionReason::try_from(raw_reason)?,
            message: copy_string(|buffer, capacity, required| {
                // SAFETY: output buffer follows the immutable snapshot copy contract.
                unsafe {
                    (api.host_state_requirement_message_copy)(
                        context.ptr(),
                        snapshot,
                        buffer,
                        capacity,
                        required,
                    )
                }
            })?,
        })
    } else {
        None
    };
    let failure = if kind == HostStateKind::Failed {
        let mut raw = std::ptr::null_mut();
        // SAFETY: raw is an initially-null owned failure output.
        let status = unsafe { (api.host_state_failure)(context.ptr(), snapshot, &mut raw) };
        check(status, "read host failure")?;
        Some(read_failure(context, raw)?)
    } else {
        None
    };
    let ready = if kind == HostStateKind::Ready {
        Some(HostStateReady::new(agent_from_snapshot(
            context, host, snapshot,
        )?))
    } else {
        None
    };
    Ok(HostState {
        kind,
        workspace,
        requirement,
        failure,
        ready,
    })
}

fn agent_from_snapshot(
    context: &Arc<ContextInner>,
    host: &Arc<HostInner>,
    snapshot: *mut ffi::Snapshot,
) -> Result<CodexAgent, CodexError> {
    let mut cached = host
        .agent
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    if let Some(inner) = cached.upgrade() {
        return Ok(CodexAgent::from_inner(inner));
    }
    type Project = unsafe extern "C" fn(
        *mut ffi::Context,
        *mut ffi::Host,
        *mut ffi::Snapshot,
        *mut *mut ffi::Agent,
    ) -> i32;
    let projector: services::ExactSymbol<Project> =
        services::exact_symbol(context, b"codex_agent_host_state_agent\0")?;
    let raw_host = host.handle.ptr()?;
    let mut raw = std::ptr::null_mut();
    check(
        // SAFETY: the Host and snapshot share this context and `raw` is initially null.
        projector.invoke(|call| unsafe { call(context.ptr(), raw_host, snapshot, &mut raw) }),
        "acquire ready Codex agent",
    )?;
    let agent = CodexAgent::from_raw(context.clone(), raw, host.clone());
    *cached = Arc::downgrade(&agent.inner);
    Ok(agent)
}

fn parse_conversation_state(
    context: &Arc<ContextInner>,
    snapshot: *mut ffi::Snapshot,
) -> Result<ConversationState, CodexError> {
    let api = &context.library.api;
    let mut raw_status = 0;
    // SAFETY: snapshot is live and output is a valid scalar slot.
    let native_status =
        unsafe { (api.conversation_state_status)(context.ptr(), snapshot, &mut raw_status) };
    check(native_status, "read conversation status")?;
    let status = ConversationStatus::try_from(raw_status)?;
    let failure = if status == ConversationStatus::Failed {
        let mut raw = std::ptr::null_mut();
        // SAFETY: raw is an initially-null owned failure output.
        let native_status =
            unsafe { (api.conversation_state_failure)(context.ptr(), snapshot, &mut raw) };
        check(native_status, "read conversation failure")?;
        Some(read_failure(context, raw)?)
    } else {
        None
    };
    Ok(ConversationState { status, failure })
}

struct HostInner {
    handle: OwnedHandle<ffi::Host>,
    agent: Mutex<Weak<AgentInner>>,
}

/// Owns one local Codex host and its child lifecycle.
///
/// Handles deliberately remain on their creating Rust thread because the C contract does not grant
/// arbitrary concurrent caller access:
///
/// ```compile_fail
/// fn require_send<T: Send>() {}
/// require_send::<codex_agent::CodexHost>();
/// ```
pub struct CodexHost {
    inner: Arc<HostInner>,
    _not_send_or_sync: PhantomData<Rc<()>>,
}

impl CodexHost {
    /// Loads the matching C SDK and creates a host.
    pub fn create(options: HostOptions) -> Result<Self, CodexError> {
        let library = CodexNativeLibrary::load_default()?;
        Self::create_with_library(&library, options)
    }

    /// Creates a host using an explicitly loaded library.
    pub fn create_with_library(
        library: &CodexNativeLibrary,
        options: HostOptions,
    ) -> Result<Self, CodexError> {
        options.validate()?;
        let context = ContextInner::create(library.inner.clone())?;
        let native_client = ffi::ClientInfo {
            struct_size: std::mem::size_of::<ffi::ClientInfo>() as u32,
            name: ffi::StringView::new(&options.client_info.name),
            title: ffi::StringView::new(&options.client_info.title),
            version: ffi::StringView::new(&options.client_info.version),
        };
        let native_options = ffi::HostOptions {
            struct_size: std::mem::size_of::<ffi::HostOptions>() as u32,
            bundle_directory: ffi::StringView::new(&options.bundle_directory),
            data_directory: ffi::StringView::new(&options.data_directory),
            client_info: native_client,
        };
        type Create = unsafe extern "C" fn(
            *mut ffi::Context,
            *const ffi::HostOptions,
            *mut *mut ffi::Host,
        ) -> i32;
        let create: services::ExactSymbol<Create> =
            services::exact_symbol(&context, b"codex_agent_host_create\0")?;
        let mut host = std::ptr::null_mut();
        let status = create.invoke(|call| unsafe {
            // SAFETY: all views borrow valid Rust strings until this copying call returns.
            call(context.ptr(), &native_options, &mut host)
        });
        check(status, "create Codex host")?;
        Ok(Self {
            inner: Arc::new(HostInner {
                handle: OwnedHandle::new_explicit_close(context, host, release_host, "host"),
                agent: Mutex::new(Weak::new()),
            }),
            _not_send_or_sync: PhantomData,
        })
    }

    /// Reads the current immutable state.
    pub fn state(&self) -> Result<HostState, CodexError> {
        type Get =
            unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Host, *mut *mut ffi::Snapshot) -> i32;
        let context = self.inner.handle.context.clone();
        let getter: services::ExactSymbol<Get> =
            services::exact_symbol(&context, b"codex_agent_host_state_get\0")?;
        let mut raw = std::ptr::null_mut();
        let host = self.inner.handle.ptr()?;
        let status = getter.invoke(|call| unsafe {
            // SAFETY: raw is an initially-null output and host is retained by self.
            call(context.ptr(), host, &mut raw)
        });
        check(status, "read host state")?;
        let snapshot = Snapshot { context, raw };
        parse_host_state(&snapshot.context, snapshot.raw, &self.inner)
    }

    /// Subscribes to current value plus subsequent host state updates.
    pub fn states(&self) -> Result<CodexStateStream<HostState>, CodexError> {
        type Subscribe = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Host,
            ffi::StateCallback,
            *mut std::ffi::c_void,
            *mut *mut ffi::Subscription,
        ) -> i32;
        let owner = self.inner.clone();
        let host = owner.handle.ptr()?;
        let context = owner.handle.context.clone();
        let start_context = context.clone();
        let subscriber: services::ExactSymbol<Subscribe> =
            services::exact_symbol(&context, b"codex_agent_host_state_subscribe\0")?;
        let projector_owner = owner.clone();
        start_subscription(
            context,
            owner,
            move |callback, user_data, output| {
                // SAFETY: callback/user_data/output follow the C subscription contract; owner
                // keeps the host alive for the stream lifetime.
                subscriber.invoke(|call| unsafe {
                    call(start_context.ptr(), host, callback, user_data, output)
                })
            },
            move |context, snapshot| parse_host_state(context, snapshot, &projector_owner),
        )
    }

    /// Starts runtime restoration/preparation.
    pub fn start(&self) -> Result<CodexOperation<()>, CodexError> {
        self.host_operation(b"codex_agent_host_start\0", false)
    }

    /// Selects a workspace path.
    pub fn select_workspace(
        &self,
        path: impl Into<String>,
    ) -> Result<CodexOperation<()>, CodexError> {
        let path = path.into();
        if path.trim().is_empty() {
            return Err(CodexError::new(
                Status::InvalidArgument,
                "workspace path must not be blank",
            ));
        }
        let owner = self.inner.clone();
        let host = owner.handle.ptr()?;
        let context = owner.handle.context.clone();
        let start_context = context.clone();
        type Select = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Host,
            *const ffi::PathWorkspaceSelection,
            ffi::OperationCallback,
            *mut std::ffi::c_void,
            *mut *mut ffi::Operation,
        ) -> i32;
        let selector: services::ExactSymbol<Select> =
            services::exact_symbol(&context, b"codex_agent_host_select_workspace\0")?;
        let selection = ffi::PathWorkspaceSelection {
            struct_size: std::mem::size_of::<ffi::PathWorkspaceSelection>() as u32,
            path: ffi::StringView::new(&path),
        };
        start_operation(
            context,
            owner,
            move |callback, user_data, output| {
                // SAFETY: selection is copied before this call returns and owner keeps host live.
                selector.invoke(|call| unsafe {
                    call(
                        start_context.ptr(),
                        host,
                        &selection,
                        callback,
                        user_data,
                        output,
                    )
                })
            },
            |_, _| Ok(()),
        )
    }

    /// Closes the host asynchronously and enables native release after successful completion.
    ///
    /// This operation must be awaited before the host leaves scope.
    pub fn close(&self) -> Result<CodexOperation<()>, CodexError> {
        self.host_operation(b"codex_agent_host_close\0", true)
    }

    /// Acquires the ready agent from the current state.
    pub fn agent(&self) -> Result<CodexAgent, CodexError> {
        type Get =
            unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Host, *mut *mut ffi::Snapshot) -> i32;
        let context = self.inner.handle.context.clone();
        let host = self.inner.handle.ptr()?;
        let getter: services::ExactSymbol<Get> =
            services::exact_symbol(&context, b"codex_agent_host_state_get\0")?;
        let mut raw_snapshot = std::ptr::null_mut();
        let status = getter.invoke(|call| unsafe {
            // SAFETY: output is initially null and host is live.
            call(context.ptr(), host, &mut raw_snapshot)
        });
        check(status, "read host state for agent")?;
        let snapshot = Snapshot {
            context: context.clone(),
            raw: raw_snapshot,
        };
        agent_from_snapshot(&context, &self.inner, snapshot.raw)
    }

    fn host_operation(
        &self,
        symbol: &'static [u8],
        marks_semantic_close: bool,
    ) -> Result<CodexOperation<()>, CodexError> {
        type Operation = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Host,
            ffi::OperationCallback,
            *mut std::ffi::c_void,
            *mut *mut ffi::Operation,
        ) -> i32;
        let owner = self.inner.clone();
        let completion_owner = owner.clone();
        let host = owner.handle.ptr()?;
        let context = owner.handle.context.clone();
        let start_context = context.clone();
        let function: services::ExactSymbol<Operation> = services::exact_symbol(&context, symbol)?;
        start_operation(
            context,
            owner,
            move |callback, user_data, output| {
                // SAFETY: callback slots obey the C contract and owner keeps host live.
                function.invoke(|call| unsafe {
                    call(start_context.ptr(), host, callback, user_data, output)
                })
            },
            move |_, _| {
                if marks_semantic_close {
                    completion_owner.handle.mark_semantically_closed();
                }
                Ok(())
            },
        )
    }
}

struct AgentInner {
    handle: OwnedHandle<ffi::Agent>,
    _host: Arc<HostInner>,
    authentication: Mutex<Weak<services::ServiceInner<ffi::Authentication>>>,
    connectors: Mutex<Weak<services::ServiceInner<ffi::Connectors>>>,
    conversations: Mutex<Weak<ConversationsInner>>,
    hooks: Mutex<Weak<services::ServiceInner<ffi::Hooks>>>,
    integration_authorization: Mutex<Weak<services::ServiceInner<ffi::IntegrationAuthorization>>>,
    interactions: Mutex<Weak<services::ServiceInner<ffi::Interactions>>>,
    mcp_servers: Mutex<Weak<services::ServiceInner<ffi::McpServers>>>,
    models: Mutex<Weak<services::ServiceInner<ffi::Models>>>,
    plugins: Mutex<Weak<services::ServiceInner<ffi::Plugins>>>,
    skills: Mutex<Weak<services::ServiceInner<ffi::Skills>>>,
    workspace: Mutex<Option<Workspace>>,
}

/// Canonical agent services owned by a ready host.
pub struct CodexAgent {
    inner: Arc<AgentInner>,
    _not_send_or_sync: PhantomData<Rc<()>>,
}

impl CodexAgent {
    fn from_raw(context: Arc<ContextInner>, raw: *mut ffi::Agent, host: Arc<HostInner>) -> Self {
        Self {
            inner: Arc::new(AgentInner {
                handle: OwnedHandle::new(context, raw, release_agent, "agent"),
                _host: host,
                authentication: Mutex::new(Weak::new()),
                connectors: Mutex::new(Weak::new()),
                conversations: Mutex::new(Weak::new()),
                hooks: Mutex::new(Weak::new()),
                integration_authorization: Mutex::new(Weak::new()),
                interactions: Mutex::new(Weak::new()),
                mcp_servers: Mutex::new(Weak::new()),
                models: Mutex::new(Weak::new()),
                plugins: Mutex::new(Weak::new()),
                skills: Mutex::new(Weak::new()),
                workspace: Mutex::new(None),
            }),
            _not_send_or_sync: PhantomData,
        }
    }

    fn from_inner(inner: Arc<AgentInner>) -> Self {
        Self {
            inner,
            _not_send_or_sync: PhantomData,
        }
    }
}

impl Clone for CodexAgent {
    fn clone(&self) -> Self {
        Self::from_inner(self.inner.clone())
    }
}

impl std::fmt::Debug for CodexAgent {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.debug_struct("CodexAgent").finish_non_exhaustive()
    }
}

impl PartialEq for CodexAgent {
    fn eq(&self, other: &Self) -> bool {
        Arc::ptr_eq(&self.inner, &other.inner)
    }
}

impl Eq for CodexAgent {}

impl CodexAgent {
    /// Acquires the identity-stable authentication service.
    pub fn authentication(&self) -> Result<CodexAuthentication, CodexError> {
        type Get = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Agent,
            *mut *mut ffi::Authentication,
        ) -> i32;
        let mut cached = self
            .inner
            .authentication
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if let Some(inner) = cached.upgrade() {
            return Ok(CodexAuthentication::from_inner(inner));
        }
        let context = self.inner.handle.context.clone();
        let agent = self.inner.handle.ptr()?;
        let getter: services::ExactSymbol<Get> =
            services::exact_symbol(&context, b"codex_agent_agent_authentication\0")?;
        let mut raw = std::ptr::null_mut();
        check(
            // SAFETY: the agent is live and `raw` is an initially-null writable output slot.
            getter.invoke(|call| unsafe { call(context.ptr(), agent, &mut raw) }),
            "acquire authentication service",
        )?;
        let service = CodexAuthentication::from_agent(context, raw, self.inner.clone());
        *cached = service.downgrade();
        Ok(service)
    }

    /// Acquires the identity-stable connector service.
    pub fn connectors(&self) -> Result<CodexConnectors, CodexError> {
        type Get = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Agent,
            *mut *mut ffi::Connectors,
        ) -> i32;
        let mut cached = self
            .inner
            .connectors
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if let Some(inner) = cached.upgrade() {
            return Ok(CodexConnectors::from_inner(inner));
        }
        let context = self.inner.handle.context.clone();
        let agent = self.inner.handle.ptr()?;
        let getter: services::ExactSymbol<Get> =
            services::exact_symbol(&context, b"codex_agent_agent_connectors\0")?;
        let mut raw = std::ptr::null_mut();
        check(
            // SAFETY: the agent is live and `raw` is an initially-null writable output slot.
            getter.invoke(|call| unsafe { call(context.ptr(), agent, &mut raw) }),
            "acquire connector service",
        )?;
        let service = CodexConnectors::from_agent(context, raw, self.inner.clone());
        *cached = service.downgrade();
        Ok(service)
    }

    /// Acquires the conversation service.
    pub fn conversations(&self) -> Result<CodexConversations, CodexError> {
        type Get = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Agent,
            *mut *mut ffi::Conversations,
        ) -> i32;
        let mut cached = self
            .inner
            .conversations
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if let Some(inner) = cached.upgrade() {
            return Ok(CodexConversations {
                inner,
                _not_send_or_sync: PhantomData,
            });
        }
        let context = self.inner.handle.context.clone();
        let agent = self.inner.handle.ptr()?;
        let getter: services::ExactSymbol<Get> =
            services::exact_symbol(&context, b"codex_agent_agent_conversations\0")?;
        let mut raw = std::ptr::null_mut();
        check(
            // SAFETY: the agent is live and `raw` is an initially-null writable output slot.
            getter.invoke(|call| unsafe { call(context.ptr(), agent, &mut raw) }),
            "acquire conversation service",
        )?;
        let service = CodexConversations {
            inner: Arc::new(ConversationsInner {
                handle: OwnedHandle::new(context, raw, release_conversations, "conversations"),
                _agent: self.inner.clone(),
            }),
            _not_send_or_sync: PhantomData,
        };
        *cached = Arc::downgrade(&service.inner);
        Ok(service)
    }

    /// Acquires the identity-stable hook service.
    pub fn hooks(&self) -> Result<CodexHooks, CodexError> {
        type Get =
            unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Agent, *mut *mut ffi::Hooks) -> i32;
        let mut cached = self
            .inner
            .hooks
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if let Some(inner) = cached.upgrade() {
            return Ok(CodexHooks::from_inner(inner));
        }
        let context = self.inner.handle.context.clone();
        let agent = self.inner.handle.ptr()?;
        let getter: services::ExactSymbol<Get> =
            services::exact_symbol(&context, b"codex_agent_agent_hooks\0")?;
        let mut raw = std::ptr::null_mut();
        check(
            // SAFETY: the agent is live and `raw` is an initially-null writable output slot.
            getter.invoke(|call| unsafe { call(context.ptr(), agent, &mut raw) }),
            "acquire hook service",
        )?;
        let service = CodexHooks::from_agent(context, raw, self.inner.clone());
        *cached = service.downgrade();
        Ok(service)
    }

    /// Acquires the identity-stable integration-authorization service.
    pub fn integration_authorization(&self) -> Result<CodexIntegrationAuthorization, CodexError> {
        type Get = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Agent,
            *mut *mut ffi::IntegrationAuthorization,
        ) -> i32;
        let mut cached = self
            .inner
            .integration_authorization
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if let Some(inner) = cached.upgrade() {
            return Ok(CodexIntegrationAuthorization::from_inner(inner));
        }
        let context = self.inner.handle.context.clone();
        let agent = self.inner.handle.ptr()?;
        let getter: services::ExactSymbol<Get> =
            services::exact_symbol(&context, b"codex_agent_agent_integration_authorization\0")?;
        let mut raw = std::ptr::null_mut();
        check(
            // SAFETY: the agent is live and `raw` is an initially-null writable output slot.
            getter.invoke(|call| unsafe { call(context.ptr(), agent, &mut raw) }),
            "acquire integration-authorization service",
        )?;
        let service = CodexIntegrationAuthorization::from_agent(context, raw, self.inner.clone());
        *cached = service.downgrade();
        Ok(service)
    }

    /// Acquires the identity-stable interaction service.
    pub fn interactions(&self) -> Result<CodexInteractions, CodexError> {
        type Get = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Agent,
            *mut *mut ffi::Interactions,
        ) -> i32;
        let mut cached = self
            .inner
            .interactions
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if let Some(inner) = cached.upgrade() {
            return Ok(CodexInteractions::from_inner(inner));
        }
        let context = self.inner.handle.context.clone();
        let agent = self.inner.handle.ptr()?;
        let getter: services::ExactSymbol<Get> =
            services::exact_symbol(&context, b"codex_agent_agent_interactions\0")?;
        let mut raw = std::ptr::null_mut();
        check(
            // SAFETY: the agent is live and `raw` is an initially-null writable output slot.
            getter.invoke(|call| unsafe { call(context.ptr(), agent, &mut raw) }),
            "acquire interaction service",
        )?;
        let service = CodexInteractions::from_agent(context, raw, self.inner.clone());
        *cached = service.downgrade();
        Ok(service)
    }

    /// Acquires the identity-stable MCP-server service.
    pub fn mcp_servers(&self) -> Result<CodexMcpServers, CodexError> {
        type Get = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Agent,
            *mut *mut ffi::McpServers,
        ) -> i32;
        let mut cached = self
            .inner
            .mcp_servers
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if let Some(inner) = cached.upgrade() {
            return Ok(CodexMcpServers::from_inner(inner));
        }
        let context = self.inner.handle.context.clone();
        let agent = self.inner.handle.ptr()?;
        let getter: services::ExactSymbol<Get> =
            services::exact_symbol(&context, b"codex_agent_agent_mcp_servers\0")?;
        let mut raw = std::ptr::null_mut();
        check(
            // SAFETY: the agent is live and `raw` is an initially-null writable output slot.
            getter.invoke(|call| unsafe { call(context.ptr(), agent, &mut raw) }),
            "acquire MCP-server service",
        )?;
        let service = CodexMcpServers::from_agent(context, raw, self.inner.clone());
        *cached = service.downgrade();
        Ok(service)
    }

    /// Acquires the identity-stable model service.
    pub fn models(&self) -> Result<CodexModels, CodexError> {
        type Get =
            unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Agent, *mut *mut ffi::Models) -> i32;
        let mut cached = self
            .inner
            .models
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if let Some(inner) = cached.upgrade() {
            return Ok(CodexModels::from_inner(inner));
        }
        let context = self.inner.handle.context.clone();
        let agent = self.inner.handle.ptr()?;
        let getter: services::ExactSymbol<Get> =
            services::exact_symbol(&context, b"codex_agent_agent_models\0")?;
        let mut raw = std::ptr::null_mut();
        check(
            // SAFETY: the agent is live and `raw` is an initially-null writable output slot.
            getter.invoke(|call| unsafe { call(context.ptr(), agent, &mut raw) }),
            "acquire model service",
        )?;
        let service = CodexModels::from_agent(context, raw, self.inner.clone());
        *cached = service.downgrade();
        Ok(service)
    }

    /// Acquires the identity-stable plugin service.
    pub fn plugins(&self) -> Result<CodexPlugins, CodexError> {
        type Get =
            unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Agent, *mut *mut ffi::Plugins) -> i32;
        let mut cached = self
            .inner
            .plugins
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if let Some(inner) = cached.upgrade() {
            return Ok(CodexPlugins::from_inner(inner));
        }
        let context = self.inner.handle.context.clone();
        let agent = self.inner.handle.ptr()?;
        let getter: services::ExactSymbol<Get> =
            services::exact_symbol(&context, b"codex_agent_agent_plugins\0")?;
        let mut raw = std::ptr::null_mut();
        check(
            // SAFETY: the agent is live and `raw` is an initially-null writable output slot.
            getter.invoke(|call| unsafe { call(context.ptr(), agent, &mut raw) }),
            "acquire plugin service",
        )?;
        let service = CodexPlugins::from_agent(context, raw, self.inner.clone());
        *cached = service.downgrade();
        Ok(service)
    }

    /// Acquires the identity-stable skill service.
    pub fn skills(&self) -> Result<CodexSkills, CodexError> {
        type Get =
            unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Agent, *mut *mut ffi::Skills) -> i32;
        let mut cached = self
            .inner
            .skills
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if let Some(inner) = cached.upgrade() {
            return Ok(CodexSkills::from_inner(inner));
        }
        let context = self.inner.handle.context.clone();
        let agent = self.inner.handle.ptr()?;
        let getter: services::ExactSymbol<Get> =
            services::exact_symbol(&context, b"codex_agent_agent_skills\0")?;
        let mut raw = std::ptr::null_mut();
        check(
            // SAFETY: the agent is live and `raw` is an initially-null writable output slot.
            getter.invoke(|call| unsafe { call(context.ptr(), agent, &mut raw) }),
            "acquire skill service",
        )?;
        let service = CodexSkills::from_agent(context, raw, self.inner.clone());
        *cached = service.downgrade();
        Ok(service)
    }

    /// Copies the agent's immutable workspace snapshot.
    pub fn workspace(&self) -> Result<Workspace, CodexError> {
        type Get = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Agent,
            *mut *mut ffi::Workspace,
        ) -> i32;
        let mut cached = self
            .inner
            .workspace
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if let Some(workspace) = cached.as_ref() {
            return Ok(workspace.clone());
        }
        let context = self.inner.handle.context.clone();
        let agent = self.inner.handle.ptr()?;
        let getter: services::ExactSymbol<Get> =
            services::exact_symbol(&context, b"codex_agent_agent_workspace\0")?;
        let mut raw = std::ptr::null_mut();
        check(
            // SAFETY: the agent is live and `raw` is an initially-null writable output slot.
            getter.invoke(|call| unsafe { call(context.ptr(), agent, &mut raw) }),
            "acquire agent workspace",
        )?;
        let workspace = native_values::decode_workspace(&context, raw)?;
        *cached = Some(workspace.clone());
        Ok(workspace)
    }
}

struct ConversationsInner {
    handle: OwnedHandle<ffi::Conversations>,
    _agent: Arc<AgentInner>,
}

/// Conversation catalog and active-conversation owner.
pub struct CodexConversations {
    inner: Arc<ConversationsInner>,
    _not_send_or_sync: PhantomData<Rc<()>>,
}

impl Clone for CodexConversations {
    fn clone(&self) -> Self {
        Self {
            inner: self.inner.clone(),
            _not_send_or_sync: PhantomData,
        }
    }
}

impl CodexConversations {
    /// Current value plus subsequent updates of the active conversation.
    pub fn active(
        &self,
    ) -> Result<services::CodexObservableState<Option<CodexConversation>>, CodexError> {
        type Get = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Conversations,
            *mut *mut ffi::Snapshot,
        ) -> i32;
        type Subscribe = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Conversations,
            ffi::StateCallback,
            *mut std::ffi::c_void,
            *mut *mut ffi::Subscription,
        ) -> i32;
        type Project = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Conversations,
            *mut ffi::Snapshot,
            *mut *mut ffi::Conversation,
        ) -> i32;
        let owner = self.inner.clone();
        let conversations = owner.handle.ptr()?;
        let context = owner.handle.context.clone();
        let getter: services::ExactSymbol<Get> =
            services::exact_symbol(&context, b"codex_agent_conversations_active_get\0")?;
        let subscriber: services::ExactSymbol<Subscribe> =
            services::exact_symbol(&context, b"codex_agent_conversations_active_subscribe\0")?;
        let projector: services::ExactSymbol<Project> =
            services::exact_symbol(&context, b"codex_agent_active_conversation\0")?;
        let current_owner = owner.clone();
        let current_context = context.clone();
        let stream_owner = owner.clone();
        let stream_context = context.clone();
        Ok(services::CodexObservableState::from_parts(
            move || {
                let mut raw = std::ptr::null_mut();
                check(
                    // SAFETY: conversations is retained by `current_owner` and `raw` is writable.
                    getter.invoke(|call| unsafe {
                        call(current_context.ptr(), conversations, &mut raw)
                    }),
                    "read active conversation state",
                )?;
                let snapshot = Snapshot {
                    context: current_context.clone(),
                    raw,
                };
                let mut conversation = std::ptr::null_mut();
                check(
                    // SAFETY: snapshot and conversations remain live for this projection call.
                    projector.invoke(|call| unsafe {
                        call(
                            current_context.ptr(),
                            conversations,
                            snapshot.raw,
                            &mut conversation,
                        )
                    }),
                    "project active conversation",
                )?;
                project_active_raw(&current_owner, &current_context, conversation)
            },
            move || {
                let start_context = stream_context.clone();
                let project_owner = stream_owner.clone();
                start_subscription(
                    stream_context.clone(),
                    stream_owner.clone(),
                    move |callback, user_data, output| {
                        // SAFETY: the subscription bridge owns callback state and writable output.
                        subscriber.invoke(|call| unsafe {
                            call(
                                start_context.ptr(),
                                conversations,
                                callback,
                                user_data,
                                output,
                            )
                        })
                    },
                    move |context, snapshot| {
                        let mut conversation = std::ptr::null_mut();
                        check(
                            // SAFETY: the callback snapshot is live for this projection call.
                            projector.invoke(|call| unsafe {
                                call(context.ptr(), conversations, snapshot, &mut conversation)
                            }),
                            "project active conversation",
                        )?;
                        project_active_raw(&project_owner, context, conversation)
                    },
                )
            },
        ))
    }

    /// Lists immutable conversation summaries in exact native order.
    pub fn list(&self) -> Result<CodexOperation<Vec<ConversationSummary>>, CodexError> {
        type Start = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Conversations,
            ffi::OperationCallback,
            *mut std::ffi::c_void,
            *mut *mut ffi::Operation,
        ) -> i32;
        type Count =
            unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Operation, *mut usize) -> i32;
        type At = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Operation,
            usize,
            *mut *mut ffi::ConversationSummary,
        ) -> i32;
        let owner = self.inner.clone();
        let conversations = owner.handle.ptr()?;
        let context = owner.handle.context.clone();
        let start: services::ExactSymbol<Start> =
            services::exact_symbol(&context, b"codex_agent_conversations_list\0")?;
        let count: services::ExactSymbol<Count> = services::exact_symbol(
            &context,
            b"codex_agent_operation_conversation_summaries_count\0",
        )?;
        let at: services::ExactSymbol<At> =
            services::exact_symbol(&context, b"codex_agent_operation_conversation_summary_at\0")?;
        let start_context = context.clone();
        start_operation(
            context,
            owner,
            move |callback, user_data, output| {
                // SAFETY: conversations is retained by the operation owner and output is writable.
                start.invoke(|call| unsafe {
                    call(
                        start_context.ptr(),
                        conversations,
                        callback,
                        user_data,
                        output,
                    )
                })
            },
            move |context, operation| {
                let mut length = 0;
                check(
                    // SAFETY: operation is live during result projection and `length` is writable.
                    count.invoke(|call| unsafe { call(context.ptr(), operation, &mut length) }),
                    "count conversation summaries",
                )?;
                if length > 1_000_000 {
                    return Err(CodexError::new(
                        Status::InternalError,
                        "native C SDK returned too many conversation summaries",
                    ));
                }
                (0..length)
                    .map(|index| {
                        let mut raw = std::ptr::null_mut();
                        check(
                            // SAFETY: operation is live, index is bounds-checked, and `raw` is writable.
                            at.invoke(|call| unsafe {
                                call(context.ptr(), operation, index, &mut raw)
                            }),
                            "read conversation summary",
                        )?;
                        native_values::decode_conversation_summary(context, raw)
                    })
                    .collect()
            },
        )
    }

    /// Reads one complete immutable conversation snapshot.
    pub fn read(
        &self,
        conversation_id: &ConversationId,
    ) -> Result<CodexOperation<ConversationSnapshot>, CodexError> {
        type Start = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Conversations,
            *mut ffi::ConversationId,
            ffi::OperationCallback,
            *mut std::ffi::c_void,
            *mut *mut ffi::Operation,
        ) -> i32;
        type Output = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Operation,
            *mut *mut ffi::ConversationValue,
        ) -> i32;
        let owner = self.inner.clone();
        let conversations = owner.handle.ptr()?;
        let context = owner.handle.context.clone();
        let id = native_values::encode_conversation_id(&context, conversation_id)?;
        let id_raw = id.raw();
        let start: services::ExactSymbol<Start> =
            services::exact_symbol(&context, b"codex_agent_conversations_read\0")?;
        let output: services::ExactSymbol<Output> =
            services::exact_symbol(&context, b"codex_agent_operation_conversation_value\0")?;
        let start_context = context.clone();
        let result = start_operation(
            context.clone(),
            owner,
            move |callback, user_data, out| {
                // SAFETY: conversations and encoded id are retained through synchronous start.
                start.invoke(|call| unsafe {
                    call(
                        start_context.ptr(),
                        conversations,
                        id_raw,
                        callback,
                        user_data,
                        out,
                    )
                })
            },
            move |context, operation| {
                let mut raw = std::ptr::null_mut();
                check(
                    // SAFETY: operation is live during result projection and `raw` is writable.
                    output.invoke(|call| unsafe { call(context.ptr(), operation, &mut raw) }),
                    "read conversation value",
                )?;
                native_values::decode_conversation_snapshot(context, raw)
            },
        );
        id.close()?;
        result
    }

    /// Renames one conversation.
    pub fn rename(
        &self,
        conversation_id: &ConversationId,
        name: impl Into<String>,
    ) -> Result<CodexOperation<()>, CodexError> {
        type Start = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Conversations,
            *mut ffi::ConversationId,
            *const ffi::StringView,
            ffi::OperationCallback,
            *mut std::ffi::c_void,
            *mut *mut ffi::Operation,
        ) -> i32;
        let name = name.into();
        let owner = self.inner.clone();
        let conversations = owner.handle.ptr()?;
        let context = owner.handle.context.clone();
        let id = native_values::encode_conversation_id(&context, conversation_id)?;
        let id_raw = id.raw();
        let view = ffi::StringView::new(&name);
        let start: services::ExactSymbol<Start> =
            services::exact_symbol(&context, b"codex_agent_conversations_rename\0")?;
        let start_context = context.clone();
        let result = start_operation(
            context.clone(),
            owner,
            move |callback, user_data, out| {
                // SAFETY: conversations, id, and string view remain live through synchronous start.
                start.invoke(|call| unsafe {
                    call(
                        start_context.ptr(),
                        conversations,
                        id_raw,
                        &view,
                        callback,
                        user_data,
                        out,
                    )
                })
            },
            |_, _| Ok(()),
        );
        id.close()?;
        result
    }

    /// Deletes one conversation.
    pub fn delete(
        &self,
        conversation_id: &ConversationId,
    ) -> Result<CodexOperation<()>, CodexError> {
        type Start = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Conversations,
            *mut ffi::ConversationId,
            ffi::OperationCallback,
            *mut std::ffi::c_void,
            *mut *mut ffi::Operation,
        ) -> i32;
        let owner = self.inner.clone();
        let conversations = owner.handle.ptr()?;
        let context = owner.handle.context.clone();
        let id = native_values::encode_conversation_id(&context, conversation_id)?;
        let id_raw = id.raw();
        let start: services::ExactSymbol<Start> =
            services::exact_symbol(&context, b"codex_agent_conversations_delete\0")?;
        let start_context = context.clone();
        let result = start_operation(
            context.clone(),
            owner,
            move |callback, user_data, out| {
                // SAFETY: conversations and encoded id remain live through synchronous start.
                start.invoke(|call| unsafe {
                    call(
                        start_context.ptr(),
                        conversations,
                        id_raw,
                        callback,
                        user_data,
                        out,
                    )
                })
            },
            |_, _| Ok(()),
        );
        id.close()?;
        result
    }

    /// Opens a new or existing conversation.
    pub fn open(
        &self,
        options: ConversationOpenOptions,
    ) -> Result<CodexOperation<CodexConversation>, CodexError> {
        type Start = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Conversations,
            *const ffi::ConversationOpenOptions,
            ffi::OperationCallback,
            *mut std::ffi::c_void,
            *mut *mut ffi::Operation,
        ) -> i32;
        let owner = self.inner.clone();
        let conversations = owner.handle.ptr()?;
        let context = owner.handle.context.clone();
        let start_context = context.clone();
        let has_conversation_id = options.conversation_id.is_some();
        let has_service_tier = options.service_tier.is_some();
        let conversation_id = options.conversation_id.unwrap_or_default();
        let service_tier = options.service_tier.unwrap_or_default();
        let native_options = ffi::ConversationOpenOptions {
            struct_size: std::mem::size_of::<ffi::ConversationOpenOptions>() as u32,
            has_conversation_id: i32::from(has_conversation_id),
            conversation_id: if has_conversation_id {
                ffi::StringView::new(&conversation_id)
            } else {
                ffi::StringView::absent()
            },
            has_approval_preset: i32::from(options.approval_preset.is_some()),
            approval_preset: options
                .approval_preset
                .unwrap_or(ApprovalPreset::Never)
                .raw(),
            has_service_tier: i32::from(has_service_tier),
            service_tier: if has_service_tier {
                ffi::StringView::new(&service_tier)
            } else {
                ffi::StringView::absent()
            },
        };
        let start: services::ExactSymbol<Start> =
            services::exact_symbol(&context, b"codex_agent_conversations_open\0")?;
        start_operation(
            context.clone(),
            owner.clone(),
            move |callback, user_data, output| {
                // SAFETY: native_options and its string views remain live for this copying call.
                start.invoke(|call| unsafe {
                    call(
                        start_context.ptr(),
                        conversations,
                        &native_options,
                        callback,
                        user_data,
                        output,
                    )
                })
            },
            move |context, operation| {
                let mut raw = std::ptr::null_mut();
                // SAFETY: operation completed successfully and output is initially null.
                let status = unsafe {
                    (context.library.api.operation_conversation)(
                        context.ptr(),
                        conversations,
                        operation,
                        &mut raw,
                    )
                };
                check(status, "read opened conversation")?;
                Ok(CodexConversation {
                    inner: Arc::new(ConversationInner {
                        handle: OwnedHandle::new_explicit_close(
                            context.clone(),
                            raw,
                            release_conversation,
                            "conversation",
                        ),
                        _conversations: owner,
                    }),
                    _not_send_or_sync: PhantomData,
                })
            },
        )
    }
}

fn project_active_raw(
    owner: &Arc<ConversationsInner>,
    context: &Arc<ContextInner>,
    raw: *mut ffi::Conversation,
) -> Result<Option<CodexConversation>, CodexError> {
    if raw.is_null() {
        return Ok(None);
    }
    Ok(Some(CodexConversation {
        inner: Arc::new(ConversationInner {
            handle: OwnedHandle::new_explicit_close(
                context.clone(),
                raw,
                release_conversation,
                "conversation",
            ),
            _conversations: owner.clone(),
        }),
        _not_send_or_sync: PhantomData,
    }))
}

struct ConversationInner {
    handle: OwnedHandle<ffi::Conversation>,
    _conversations: Arc<ConversationsInner>,
}

/// One owned conversation handle.
pub struct CodexConversation {
    inner: Arc<ConversationInner>,
    _not_send_or_sync: PhantomData<Rc<()>>,
}

impl Clone for CodexConversation {
    fn clone(&self) -> Self {
        Self {
            inner: self.inner.clone(),
            _not_send_or_sync: PhantomData,
        }
    }
}

type ConversationStateGet =
    unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Conversation, *mut *mut ffi::Snapshot) -> i32;
type ConversationStateSubscribe = unsafe extern "C" fn(
    *mut ffi::Context,
    *mut ffi::Conversation,
    ffi::StateCallback,
    *mut std::ffi::c_void,
    *mut *mut ffi::Subscription,
) -> i32;
type ConversationStringOperation = unsafe extern "C" fn(
    *mut ffi::Context,
    *mut ffi::Conversation,
    *const ffi::StringView,
    ffi::OperationCallback,
    *mut std::ffi::c_void,
    *mut *mut ffi::Operation,
) -> i32;
type ConversationOperation = unsafe extern "C" fn(
    *mut ffi::Context,
    *mut ffi::Conversation,
    ffi::OperationCallback,
    *mut std::ffi::c_void,
    *mut *mut ffi::Operation,
) -> i32;

impl CodexConversation {
    /// Tests canonical conversation identity.
    pub fn is_same(&self, other: &Self) -> Result<bool, CodexError> {
        let context = self.inner.handle.context.clone();
        let mut same = 0;
        // SAFETY: both live handles are passed to the checked C API; wrong contexts become errors.
        let status = unsafe {
            (context.library.api.conversation_is_same)(
                context.ptr(),
                self.inner.handle.ptr()?,
                other.inner.handle.ptr()?,
                &mut same,
            )
        };
        check(status, "compare conversation identity")?;
        Ok(same != 0)
    }

    /// Current value plus subsequent immutable conversation-state updates.
    pub fn state(&self) -> Result<services::CodexObservableState<ConversationState>, CodexError> {
        let context = self.inner.handle.context.clone();
        let getter = services::exact_symbol(&context, b"codex_agent_conversation_state_get\0")?;
        let subscriber =
            services::exact_symbol(&context, b"codex_agent_conversation_state_subscribe\0")?;
        conversation_observable(
            self.inner.clone(),
            getter,
            subscriber,
            parse_conversation_state,
        )
    }

    /// Subscribes to current value plus subsequent conversation state updates.
    pub fn states(&self) -> Result<CodexStateStream<ConversationState>, CodexError> {
        self.state()?.subscribe()
    }

    /// Sends a prompt.
    pub fn send(&self, prompt: impl Into<String>) -> Result<CodexOperation<()>, CodexError> {
        let function = services::exact_symbol(
            &self.inner.handle.context,
            b"codex_agent_conversation_send\0",
        )?;
        self.string_operation(prompt.into(), function)
    }

    /// Sends a complete structured turn request.
    pub fn send_request(&self, request: &TurnRequest) -> Result<CodexOperation<()>, CodexError> {
        type Start = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Conversation,
            *mut ffi::TurnRequest,
            ffi::OperationCallback,
            *mut std::ffi::c_void,
            *mut *mut ffi::Operation,
        ) -> i32;
        let owner = self.inner.clone();
        let conversation = owner.handle.ptr()?;
        let context = owner.handle.context.clone();
        let request = native_values::encode_turn_request(&context, request)?;
        let request_raw = request.raw();
        let start: services::ExactSymbol<Start> =
            services::exact_symbol(&context, b"codex_agent_conversation_send_request\0")?;
        let start_context = context.clone();
        let result = start_operation(
            context.clone(),
            owner,
            move |callback, user_data, output| {
                // SAFETY: conversation and encoded request remain live through synchronous start.
                start.invoke(|call| unsafe {
                    call(
                        start_context.ptr(),
                        conversation,
                        request_raw,
                        callback,
                        user_data,
                        output,
                    )
                })
            },
            |_, _| Ok(()),
        );
        request.close()?;
        result
    }

    /// Runs a shell command through the conversation runtime.
    pub fn run_shell_command(
        &self,
        command: impl Into<String>,
    ) -> Result<CodexOperation<()>, CodexError> {
        let function = services::exact_symbol(
            &self.inner.handle.context,
            b"codex_agent_conversation_run_shell_command\0",
        )?;
        self.string_operation(command.into(), function)
    }

    /// Reloads persisted conversation state.
    pub fn reload(&self) -> Result<CodexOperation<()>, CodexError> {
        let function = services::exact_symbol(
            &self.inner.handle.context,
            b"codex_agent_conversation_reload\0",
        )?;
        self.operation(function, false)
    }

    /// Cancels the active turn.
    pub fn cancel_turn(&self) -> Result<CodexOperation<()>, CodexError> {
        let function = services::exact_symbol(
            &self.inner.handle.context,
            b"codex_agent_conversation_cancel_turn\0",
        )?;
        self.operation(function, false)
    }

    /// Closes this conversation and enables native release after successful completion.
    ///
    /// This operation must be awaited before the conversation leaves scope.
    pub fn close(&self) -> Result<CodexOperation<()>, CodexError> {
        let function = services::exact_symbol(
            &self.inner.handle.context,
            b"codex_agent_conversation_close\0",
        )?;
        self.operation(function, true)
    }

    /// Current value plus updates for active turn progress.
    pub fn active_turn_progress(
        &self,
    ) -> Result<services::CodexObservableState<Option<TurnProgress>>, CodexError> {
        type Has = unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Snapshot, *mut i32) -> i32;
        type Value = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Snapshot,
            *mut *mut ffi::TurnProgress,
        ) -> i32;
        let context = self.inner.handle.context.clone();
        let getter = services::exact_symbol(
            &context,
            b"codex_agent_conversation_active_turn_progress_get\0",
        )?;
        let subscriber = services::exact_symbol(
            &context,
            b"codex_agent_conversation_active_turn_progress_subscribe\0",
        )?;
        let has: services::ExactSymbol<Has> = services::exact_symbol(
            &context,
            b"codex_agent_conversation_active_turn_progress_has_value\0",
        )?;
        let value: services::ExactSymbol<Value> = services::exact_symbol(
            &context,
            b"codex_agent_conversation_active_turn_progress_value\0",
        )?;
        conversation_observable(
            self.inner.clone(),
            getter,
            subscriber,
            move |context, snapshot| {
                let mut present = 0;
                check(
                    // SAFETY: snapshot is live during projection and `present` is writable.
                    has.invoke(|call| unsafe { call(context.ptr(), snapshot, &mut present) }),
                    "read active turn progress presence",
                )?;
                match present {
                    0 => Ok(None),
                    1 => {
                        let mut raw = std::ptr::null_mut();
                        check(
                            // SAFETY: snapshot is live during projection and `raw` is writable.
                            value.invoke(|call| unsafe { call(context.ptr(), snapshot, &mut raw) }),
                            "read active turn progress",
                        )?;
                        native_values::decode_turn_progress(context, raw).map(Some)
                    }
                    _ => Err(CodexError::new(
                        Status::InternalError,
                        "native C SDK returned invalid active progress presence",
                    )),
                }
            },
        )
    }

    /// Current value plus updates for turn-cancellation availability.
    pub fn can_cancel_turn(&self) -> Result<services::CodexObservableState<bool>, CodexError> {
        self.boolean_state(
            b"codex_agent_conversation_can_cancel_turn_get\0",
            b"codex_agent_conversation_can_cancel_turn_subscribe\0",
            b"codex_agent_state_boolean_value\0",
        )
    }

    /// Current value plus updates for reload availability.
    pub fn can_reload(&self) -> Result<services::CodexObservableState<bool>, CodexError> {
        self.boolean_state(
            b"codex_agent_conversation_can_reload_get\0",
            b"codex_agent_conversation_can_reload_subscribe\0",
            b"codex_agent_state_boolean_value\0",
        )
    }

    /// Current value plus updates for shell-command availability.
    pub fn can_run_shell_command(
        &self,
    ) -> Result<services::CodexObservableState<bool>, CodexError> {
        self.boolean_state(
            b"codex_agent_conversation_can_run_shell_command_get\0",
            b"codex_agent_conversation_can_run_shell_command_subscribe\0",
            b"codex_agent_state_boolean_value\0",
        )
    }

    /// Current value plus updates for turn-start availability.
    pub fn can_start_turn(&self) -> Result<services::CodexObservableState<bool>, CodexError> {
        self.boolean_state(
            b"codex_agent_conversation_can_start_turn_get\0",
            b"codex_agent_conversation_can_start_turn_subscribe\0",
            b"codex_agent_state_boolean_value\0",
        )
    }

    /// Current value plus ordered immutable message updates.
    pub fn current_messages(
        &self,
    ) -> Result<services::CodexObservableState<Vec<Message>>, CodexError> {
        type Count = unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Snapshot, *mut usize) -> i32;
        type At = unsafe extern "C" fn(
            *mut ffi::Context,
            *mut ffi::Snapshot,
            usize,
            *mut *mut ffi::Message,
        ) -> i32;
        let context = self.inner.handle.context.clone();
        let getter =
            services::exact_symbol(&context, b"codex_agent_conversation_current_messages_get\0")?;
        let subscriber = services::exact_symbol(
            &context,
            b"codex_agent_conversation_current_messages_subscribe\0",
        )?;
        let count: services::ExactSymbol<Count> = services::exact_symbol(
            &context,
            b"codex_agent_conversation_current_messages_count\0",
        )?;
        let at: services::ExactSymbol<At> =
            services::exact_symbol(&context, b"codex_agent_conversation_current_messages_at\0")?;
        conversation_observable(
            self.inner.clone(),
            getter,
            subscriber,
            move |context, snapshot| {
                let mut length = 0;
                check(
                    // SAFETY: snapshot is live during projection and `length` is writable.
                    count.invoke(|call| unsafe { call(context.ptr(), snapshot, &mut length) }),
                    "count current messages",
                )?;
                if length > 1_000_000 {
                    return Err(CodexError::new(
                        Status::InternalError,
                        "native C SDK returned too many current messages",
                    ));
                }
                (0..length)
                    .map(|index| {
                        let mut raw = std::ptr::null_mut();
                        check(
                            // SAFETY: snapshot is live, index is bounds-checked, and `raw` is writable.
                            at.invoke(|call| unsafe {
                                call(context.ptr(), snapshot, index, &mut raw)
                            }),
                            "read current message",
                        )?;
                        native_values::decode_message(context, raw)
                    })
                    .collect()
            },
        )
    }

    /// Current value plus updates indicating whether a turn is active.
    pub fn is_turn_active(&self) -> Result<services::CodexObservableState<bool>, CodexError> {
        self.boolean_state(
            b"codex_agent_conversation_is_turn_active_get\0",
            b"codex_agent_conversation_is_turn_active_subscribe\0",
            b"codex_agent_state_boolean_value\0",
        )
    }

    fn boolean_state(
        &self,
        getter_name: &'static [u8],
        subscriber_name: &'static [u8],
        projector_name: &'static [u8],
    ) -> Result<services::CodexObservableState<bool>, CodexError> {
        type Project = unsafe extern "C" fn(*mut ffi::Context, *mut ffi::Snapshot, *mut i32) -> i32;
        let context = self.inner.handle.context.clone();
        let getter = services::exact_symbol(&context, getter_name)?;
        let subscriber = services::exact_symbol(&context, subscriber_name)?;
        let projector: services::ExactSymbol<Project> =
            services::exact_symbol(&context, projector_name)?;
        conversation_observable(
            self.inner.clone(),
            getter,
            subscriber,
            move |context, snapshot| {
                let mut value = 0;
                check(
                    // SAFETY: snapshot is live during projection and `value` is writable.
                    projector.invoke(|call| unsafe { call(context.ptr(), snapshot, &mut value) }),
                    "read conversation Boolean state",
                )?;
                match value {
                    0 => Ok(false),
                    1 => Ok(true),
                    _ => Err(CodexError::new(
                        Status::InternalError,
                        "native C SDK returned invalid Boolean state",
                    )),
                }
            },
        )
    }

    fn string_operation(
        &self,
        value: String,
        function: services::ExactSymbol<ConversationStringOperation>,
    ) -> Result<CodexOperation<()>, CodexError> {
        if value.trim().is_empty() {
            return Err(CodexError::new(
                Status::InvalidArgument,
                "conversation operation input must not be blank",
            ));
        }
        let owner = self.inner.clone();
        let conversation = owner.handle.ptr()?;
        let context = owner.handle.context.clone();
        let start_context = context.clone();
        let view = ffi::StringView::new(&value);
        start_operation(
            context,
            owner,
            move |callback, user_data, output| {
                // SAFETY: view borrows value until this copying call returns; owner keeps handle live.
                function.invoke(|call| unsafe {
                    call(
                        start_context.ptr(),
                        conversation,
                        &view,
                        callback,
                        user_data,
                        output,
                    )
                })
            },
            |_, _| Ok(()),
        )
    }

    fn operation(
        &self,
        function: services::ExactSymbol<ConversationOperation>,
        marks_semantic_close: bool,
    ) -> Result<CodexOperation<()>, CodexError> {
        let owner = self.inner.clone();
        let completion_owner = owner.clone();
        let conversation = owner.handle.ptr()?;
        let context = owner.handle.context.clone();
        let start_context = context.clone();
        start_operation(
            context,
            owner,
            move |callback, user_data, output| {
                // SAFETY: callback slots obey the C contract and owner keeps conversation live.
                function.invoke(|call| unsafe {
                    call(
                        start_context.ptr(),
                        conversation,
                        callback,
                        user_data,
                        output,
                    )
                })
            },
            move |_, _| {
                if marks_semantic_close {
                    completion_owner.handle.mark_semantically_closed();
                }
                Ok(())
            },
        )
    }
}

fn conversation_observable<T, P>(
    owner: Arc<ConversationInner>,
    getter: services::ExactSymbol<ConversationStateGet>,
    subscriber: services::ExactSymbol<ConversationStateSubscribe>,
    projector: P,
) -> Result<services::CodexObservableState<T>, CodexError>
where
    T: 'static,
    P: Fn(&Arc<ContextInner>, *mut ffi::Snapshot) -> Result<T, CodexError> + Clone + 'static,
{
    let conversation = owner.handle.ptr()?;
    let context = owner.handle.context.clone();
    let current_context = context.clone();
    let current_projector = projector.clone();
    let stream_owner = owner.clone();
    let stream_context = context.clone();
    Ok(services::CodexObservableState::from_parts(
        move || {
            let mut raw = std::ptr::null_mut();
            check(
                getter.invoke(|call| {
                    // SAFETY: conversation is retained by the observable owner and `raw` is writable.
                    unsafe { call(current_context.ptr(), conversation, &mut raw) }
                }),
                "read conversation observable state",
            )?;
            let snapshot = Snapshot {
                context: current_context.clone(),
                raw,
            };
            current_projector(&snapshot.context, snapshot.raw)
        },
        move || {
            let start_context = stream_context.clone();
            let value_projector = projector.clone();
            start_subscription(
                stream_context.clone(),
                stream_owner.clone(),
                move |callback, user_data, output| {
                    // SAFETY: the subscription bridge owns callback state and writable output.
                    subscriber.invoke(|call| unsafe {
                        call(
                            start_context.ptr(),
                            conversation,
                            callback,
                            user_data,
                            output,
                        )
                    })
                },
                move |context, snapshot| value_projector(context, snapshot),
            )
        },
    ))
}
