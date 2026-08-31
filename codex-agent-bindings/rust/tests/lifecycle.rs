use codex_agent::{
    CODEX_AGENT_ABI_VERSION, CleanupIssue, ClientInfo, CodexHost, CodexNativeLibrary,
    ConversationOpenOptions, ConversationStatus, HostOptions, HostStateKind, RuntimeTarget, Status,
};
use futures_core::Stream;
use libloading::Library;
use std::future::Future;
use std::path::{Path, PathBuf};
use std::pin::Pin;
use std::process::Command;
use std::sync::{Arc, OnceLock};
use std::task::{Context, Poll, Wake, Waker};
use std::time::{Duration, Instant};

fn mock_library() -> &'static Path {
    static LIBRARY: OnceLock<PathBuf> = OnceLock::new();
    LIBRARY
        .get_or_init(|| compile_fixture("mock_codex_agent.c", "codex_agent"))
        .as_path()
}

fn incompatible_library() -> &'static Path {
    static LIBRARY: OnceLock<PathBuf> = OnceLock::new();
    LIBRARY
        .get_or_init(|| compile_fixture("mock_incompatible_abi.c", "codex_agent_incompatible"))
        .as_path()
}

fn compile_fixture(source_name: &str, library_name: &str) -> PathBuf {
    let directory =
        std::env::temp_dir().join(format!("codex-agent-rust-binding-{}", std::process::id()));
    std::fs::create_dir_all(&directory).expect("create mock output directory");
    let output = if cfg!(target_os = "macos") {
        directory.join(format!("lib{library_name}.dylib"))
    } else if cfg!(target_os = "linux") {
        directory.join(format!("lib{library_name}.so"))
    } else {
        panic!("native mock compilation is supported on macOS and Linux")
    };
    let source = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures")
        .join(source_name);
    let mut command = Command::new("cc");
    command
        .arg("-std=gnu11")
        .arg("-fPIC")
        .arg("-pthread")
        .arg("-Wall")
        .arg("-Wextra")
        .arg("-Werror");
    if cfg!(target_os = "macos") {
        command.arg("-dynamiclib");
    } else {
        command.arg("-shared");
    }
    let result = command
        .arg(source)
        .arg("-o")
        .arg(&output)
        .output()
        .expect("run cc");
    assert!(
        result.status.success(),
        "mock C SDK compile failed:\n{}",
        String::from_utf8_lossy(&result.stderr)
    );
    output
}

struct ThreadWake(std::thread::Thread);

impl Wake for ThreadWake {
    fn wake(self: Arc<Self>) {
        self.0.unpark();
    }

    fn wake_by_ref(self: &Arc<Self>) {
        self.0.unpark();
    }
}

fn block_on<F: Future>(future: F) -> F::Output {
    let waker = Waker::from(Arc::new(ThreadWake(std::thread::current())));
    let mut context = Context::from_waker(&waker);
    let mut future = Box::pin(future);
    loop {
        match Future::poll(future.as_mut(), &mut context) {
            Poll::Ready(value) => return value,
            Poll::Pending => std::thread::park_timeout(Duration::from_millis(10)),
        }
    }
}

struct PanicWake;

impl Wake for PanicWake {
    fn wake(self: Arc<Self>) {
        panic!("test waker panic");
    }

    fn wake_by_ref(self: &Arc<Self>) {
        panic!("test waker panic");
    }
}

fn wait_until(mut condition: impl FnMut() -> bool) {
    let deadline = Instant::now() + Duration::from_secs(2);
    while !condition() {
        assert!(
            Instant::now() < deadline,
            "timed out waiting for native cleanup"
        );
        std::thread::sleep(Duration::from_millis(1));
    }
}

type Getter = unsafe extern "C" fn() -> i32;
type Setter = unsafe extern "C" fn(i32);
type Action = unsafe extern "C" fn();
type CopyLog = unsafe extern "C" fn(*mut u8, usize, *mut usize) -> i32;

struct Control {
    _library: Library,
    publish: Action,
    finish_states: Action,
    context_errors: Getter,
    operation_destroys: Getter,
    subscription_destroys: Getter,
    copy_release_log: CopyLog,
    set_abi_compatible: Setter,
    set_operation_destroy_mode: Setter,
    set_subscription_destroy_mode: Setter,
    set_owned_release_mode: Setter,
    set_failure_release_mode: Setter,
    set_context_destroy_mode: Setter,
    set_host_workspace_available: Setter,
    last_open_has_conversation_id: Getter,
    last_open_conversation_id_size: Getter,
    last_open_has_service_tier: Getter,
    last_open_service_tier_size: Getter,
}

unsafe fn symbol<T: Copy>(library: &Library, name: &[u8]) -> T {
    // SAFETY: every caller supplies the exact signature exported by this test-only C fixture.
    unsafe { *library.get::<T>(name).expect("load mock control symbol") }
}

fn get(getter: Getter) -> i32 {
    // SAFETY: Control contains only exact no-argument fixture getter signatures.
    unsafe { getter() }
}

fn set(setter: Setter, value: i32) {
    // SAFETY: Control contains only exact fixture setter signatures.
    unsafe { setter(value) }
}

fn act(action: Action) {
    // SAFETY: Control contains only exact no-argument fixture action signatures.
    unsafe { action() }
}

impl Control {
    fn load(path: &Path) -> Self {
        // SAFETY: the path names the fixture compiled by mock_library and remains loaded in Self.
        let library = unsafe { Library::new(path) }.expect("load mock control symbols");
        // SAFETY: all names and signatures are declarations in mock_codex_agent.c.
        unsafe {
            Self {
                publish: symbol(&library, b"codex_agent_test_publish_host_state\0"),
                finish_states: symbol(&library, b"codex_agent_test_finish_host_state\0"),
                context_errors: symbol(&library, b"codex_agent_test_context_destroy_errors\0"),
                operation_destroys: symbol(&library, b"codex_agent_test_operation_destroy_count\0"),
                subscription_destroys: symbol(
                    &library,
                    b"codex_agent_test_subscription_destroy_count\0",
                ),
                copy_release_log: symbol(&library, b"codex_agent_test_release_log_copy\0"),
                set_abi_compatible: symbol(&library, b"codex_agent_test_set_abi_compatible\0"),
                set_operation_destroy_mode: symbol(
                    &library,
                    b"codex_agent_test_set_operation_destroy_mode\0",
                ),
                set_subscription_destroy_mode: symbol(
                    &library,
                    b"codex_agent_test_set_subscription_destroy_mode\0",
                ),
                set_owned_release_mode: symbol(
                    &library,
                    b"codex_agent_test_set_owned_release_mode\0",
                ),
                set_failure_release_mode: symbol(
                    &library,
                    b"codex_agent_test_set_failure_release_mode\0",
                ),
                set_context_destroy_mode: symbol(
                    &library,
                    b"codex_agent_test_set_context_destroy_mode\0",
                ),
                set_host_workspace_available: symbol(
                    &library,
                    b"codex_agent_test_set_host_workspace_available\0",
                ),
                last_open_has_conversation_id: symbol(
                    &library,
                    b"codex_agent_test_last_open_has_conversation_id\0",
                ),
                last_open_conversation_id_size: symbol(
                    &library,
                    b"codex_agent_test_last_open_conversation_id_size\0",
                ),
                last_open_has_service_tier: symbol(
                    &library,
                    b"codex_agent_test_last_open_has_service_tier\0",
                ),
                last_open_service_tier_size: symbol(
                    &library,
                    b"codex_agent_test_last_open_service_tier_size\0",
                ),
                _library: library,
            }
        }
    }

    fn release_log(&self) -> Vec<u8> {
        let mut required = 0;
        let mut bytes = Vec::new();
        loop {
            let buffer = if bytes.is_empty() {
                std::ptr::null_mut()
            } else {
                bytes.as_mut_ptr()
            };
            // SAFETY: buffer is null for zero capacity or writable for bytes.len().
            let status = unsafe { (self.copy_release_log)(buffer, bytes.len(), &mut required) };
            match status {
                0 => {
                    bytes.truncate(required);
                    return bytes;
                }
                9 => {
                    assert!(required > bytes.len(), "release-log size must grow");
                    bytes.resize(required, 0);
                }
                _ => panic!("unexpected release-log copy status: {status}"),
            }
        }
    }
}

fn host_options() -> HostOptions {
    HostOptions {
        bundle_directory: "/tmp/bundle".into(),
        data_directory: "/tmp/data".into(),
        client_info: ClientInfo {
            name: "rust-tests".into(),
            title: "Rust tests".into(),
            version: "1".into(),
        },
    }
}

fn wait_for_issue(resource: &str, status: Status) -> CleanupIssue {
    let mut found = None;
    wait_until(|| {
        let mut issues = CodexNativeLibrary::take_cleanup_issues();
        assert!(issues.len() <= 1, "unexpected cleanup issues: {issues:?}");
        if let Some(issue) = issues.pop() {
            found = Some(issue);
            true
        } else {
            false
        }
    });
    let issue = found.expect("cleanup issue");
    assert_eq!(issue.resource, resource);
    assert_eq!(issue.status, status);
    issue
}

#[test]
fn private_ffi_symbols_are_declared_by_the_c_sdk_header() {
    let ffi = include_str!("../src/ffi.rs");
    let c_sdk_root = std::env::var_os("CODEX_AGENT_C_SDK_ROOT")
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .expect("CODEX_AGENT_C_SDK_ROOT must name a declared C SDK root");
    let header_path = c_sdk_root.join("include/codex_agent.h");
    let header = std::fs::read_to_string(&header_path).unwrap_or_else(|error| {
        panic!(
            "read public C SDK header {}: {error}",
            header_path.display()
        )
    });
    let symbols: Vec<_> = ffi
        .lines()
        .filter_map(|line| line.split("=> \"").nth(1))
        .filter_map(|suffix| suffix.split('"').next())
        .filter(|symbol| symbol.starts_with("codex_agent_"))
        .collect();
    assert_eq!(symbols.len(), 48, "unexpected Rust FFI symbol inventory");
    for symbol in symbols {
        assert!(
            header.contains(symbol),
            "Rust FFI symbol {symbol} is absent from codex_agent.h"
        );
    }
    assert!(header.contains("#define CODEX_AGENT_ABI_VERSION_MAJOR UINT32_C(1)"));
    assert!(header.contains("#define CODEX_AGENT_ABI_VERSION_MINOR UINT32_C(12)"));
    assert!(header.contains("#define CODEX_AGENT_ABI_VERSION_PATCH UINT32_C(0)"));
}

#[cfg(all(target_os = "macos", target_arch = "aarch64"))]
#[test]
#[ignore = "requires CODEX_AGENT_REAL_SDK pointing to the built macOS Arm64 C SDK"]
fn real_macos_sdk_closes_before_release() {
    let path = std::env::var_os("CODEX_AGENT_REAL_SDK")
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .expect("CODEX_AGENT_REAL_SDK must name a declared C SDK library");
    assert!(path.is_file(), "real C SDK is missing: {}", path.display());
    let _ = CodexNativeLibrary::take_cleanup_issues();
    let native = CodexNativeLibrary::load(&path).expect("load real macOS C SDK");

    let unclosed =
        CodexHost::create_with_library(&native, host_options()).expect("create unclosed real host");
    drop(unclosed);
    assert_eq!(
        CodexNativeLibrary::take_cleanup_issues(),
        vec![CleanupIssue {
            resource: "host (explicit async close required)".into(),
            status: Status::Busy,
            attempts: 24,
        }],
        "the real producer must reject release while Host is OPEN"
    );

    let host = CodexHost::create_with_library(&native, host_options()).expect("create real host");
    assert_eq!(host.state().unwrap().kind, HostStateKind::New);
    block_on(host.close().expect("start real host close")).expect("complete real host close");
    drop(host);
    drop(native);
    assert_eq!(
        CodexNativeLibrary::take_cleanup_issues(),
        Vec::<CleanupIssue>::new(),
        "real close must make host release/context destruction succeed"
    );
}

#[test]
fn lifecycle_state_failure_cancellation_identity_and_ownership() {
    let path = mock_library();
    let control = Control::load(path);

    let incompatible_prefix_only = CodexNativeLibrary::load(incompatible_library())
        .err()
        .expect("reject prefix-only incompatible ABI before full symbol resolution");
    assert_eq!(incompatible_prefix_only.status, Status::UnsupportedAbi);

    // SAFETY: fixture setter loaded with its exact signature.
    set(control.set_abi_compatible, 0);
    let incompatible = CodexNativeLibrary::load(path)
        .err()
        .expect("reject incompatible ABI");
    assert_eq!(incompatible.status, Status::UnsupportedAbi);
    // SAFETY: fixture setter loaded with its exact signature.
    set(control.set_abi_compatible, 1);

    let native = CodexNativeLibrary::load(path).expect("load ABI-complete mock");
    assert_eq!(native.abi_version(), CODEX_AGENT_ABI_VERSION);
    assert!(RuntimeTarget::current().is_ok());
    assert!(CodexNativeLibrary::load(path.with_extension("missing")).is_err());
    assert!(CodexNativeLibrary::take_cleanup_issues().is_empty());

    let host = CodexHost::create_with_library(&native, host_options()).expect("create host");
    assert_eq!(host.state().unwrap().kind, HostStateKind::New);

    let mut host_states = host.states().expect("subscribe host state");
    assert_eq!(
        block_on(host_states.next()).unwrap().unwrap().kind,
        HostStateKind::New
    );
    let panic_waker = Waker::from(Arc::new(PanicWake));
    let mut panic_context = Context::from_waker(&panic_waker);
    assert!(matches!(
        Pin::new(&mut host_states).poll_next(&mut panic_context),
        Poll::Pending
    ));

    block_on(host.start().unwrap()).expect("start host");
    // A panicking executor waker is contained inside the C callback.
    // SAFETY: publish is the no-argument test fixture function loaded with its exact signature.
    act(control.publish);
    let ready = block_on(host_states.next()).unwrap().unwrap();
    assert_eq!(ready.kind, HostStateKind::Ready);
    assert_eq!(ready.workspace.as_ref().unwrap().path, "/tmp/workspace");
    set(control.set_host_workspace_available, 0);
    let ready_without_workspace = host.state().expect("read READY without workspace");
    assert_eq!(ready_without_workspace.kind, HostStateKind::Ready);
    assert_eq!(ready_without_workspace.workspace, None);
    set(control.set_host_workspace_available, 1);
    // SAFETY: finish_states is the no-argument test fixture function loaded above.
    act(control.finish_states);
    assert!(block_on(host_states.next()).is_none());
    drop(host_states);

    let agent = host.agent().expect("ready agent");
    assert_eq!(ready.ready.as_ref().unwrap().agent(), agent);
    assert_eq!(
        ready_without_workspace.ready.as_ref().unwrap().agent(),
        agent
    );
    drop(ready);
    drop(ready_without_workspace);
    let conversations = agent.conversations().expect("conversation service");
    assert!(conversations.active().unwrap().current().unwrap().is_none());

    let invalid_empty = conversations
        .open(ConversationOpenOptions {
            conversation_id: Some(String::new()),
            ..ConversationOpenOptions::default()
        })
        .err()
        .expect("empty existing conversation ID is invalid");
    assert_eq!(invalid_empty.status, Status::InvalidArgument);
    // SAFETY: fixture getters loaded with exact signatures.
    assert_eq!(get(control.last_open_has_conversation_id), 1);
    assert_eq!(get(control.last_open_conversation_id_size), 0);

    let empty_tier_conversation = block_on(
        conversations
            .open(ConversationOpenOptions {
                service_tier: Some(String::new()),
                ..ConversationOpenOptions::default()
            })
            .unwrap(),
    )
    .expect("present empty service tier reaches ABI");
    assert_eq!(get(control.last_open_has_service_tier), 1);
    assert_eq!(get(control.last_open_service_tier_size), 0);
    block_on(empty_tier_conversation.close().unwrap()).expect("close empty-tier conversation");
    drop(empty_tier_conversation);

    let conversation = block_on(
        conversations
            .open(ConversationOpenOptions::default())
            .unwrap(),
    )
    .expect("open conversation");
    assert_eq!(get(control.last_open_has_conversation_id), 0);
    assert_eq!(get(control.last_open_conversation_id_size), 0);
    assert_eq!(get(control.last_open_has_service_tier), 0);
    assert_eq!(get(control.last_open_service_tier_size), 0);
    let active = conversations
        .active()
        .unwrap()
        .current()
        .unwrap()
        .expect("active conversation");
    assert!(conversation.is_same(&active).unwrap());
    assert_eq!(
        conversation.state().unwrap().current().unwrap().status,
        ConversationStatus::Ready
    );

    let mut conversation_states = conversation.states().unwrap();
    assert_eq!(
        block_on(conversation_states.next())
            .unwrap()
            .unwrap()
            .status,
        ConversationStatus::Ready
    );
    drop(conversation_states);

    block_on(conversation.send("hello").unwrap()).expect("send prompt");
    block_on(conversation.run_shell_command("pwd").unwrap()).expect("run command");
    block_on(conversation.reload().unwrap()).expect("reload");
    block_on(conversation.cancel_turn().unwrap()).expect("cancel turn operation");
    block_on(conversation.send("threaded").unwrap()).expect("worker-thread callback");

    let failure = block_on(conversation.send("fail").unwrap()).unwrap_err();
    assert_eq!(failure.status, Status::OperationFailed);
    assert_eq!(failure.failure.as_ref().unwrap().code, "mock.failure");
    assert!(failure.failure.unwrap().recoverable);

    let mut pending = conversation.send("pending").unwrap();
    assert!(matches!(
        Pin::new(&mut pending).poll(&mut panic_context),
        Poll::Pending
    ));
    // The cancellation callback wakes the deliberately panicking waker; no unwind crosses C.
    pending.cancel().expect("request cancellation");
    let cancelled = block_on(pending).unwrap_err();
    assert_eq!(cancelled.status, Status::Cancelled);

    let unfinished_before = get(control.operation_destroys);
    drop(conversation.send("pending").unwrap());
    wait_until(|| get(control.operation_destroys) > unfinished_before);

    let cross_thread_before = get(control.operation_destroys);
    drop(conversation.send("threaded").unwrap());
    wait_until(|| get(control.operation_destroys) > cross_thread_before);

    let orphaned_operation = conversation.send("pending").unwrap();
    // The operation and conversation retain their parent chain after public service wrappers drop.
    drop(conversations);
    drop(agent);
    orphaned_operation.cancel().unwrap();
    assert_eq!(
        block_on(orphaned_operation).unwrap_err().status,
        Status::Cancelled
    );
    block_on(conversation.close().unwrap()).expect("close conversation");
    block_on(conversation.close().unwrap()).expect("repeated close is safe");
    drop(conversation);
    drop(active);
    block_on(host.close().unwrap()).expect("close host before release");
    drop(host);

    let retained_host =
        CodexHost::create_with_library(&native, host_options()).expect("create retained host");
    let mut retained_states = retained_host.states().expect("subscribe retained host");
    assert_eq!(
        block_on(retained_states.next()).unwrap().unwrap().kind,
        HostStateKind::New
    );
    block_on(retained_host.close().unwrap()).expect("close subscribed host");
    drop(retained_host);
    // The stream's owner chain keeps the host alive while a callback crosses the ABI.
    act(control.publish);
    assert_eq!(
        block_on(retained_states.next()).unwrap().unwrap().kind,
        HostStateKind::Closed
    );
    drop(retained_states);

    drop(native);

    wait_until(|| get(control.operation_destroys) >= 18);
    wait_until(|| get(control.subscription_destroys) >= 3);
    wait_until(|| control.release_log().contains(&b'X'));
    let original_slot_errors = get(control.context_errors);
    assert_eq!(original_slot_errors, 0, "context original slot changed");
    let ordinary_issues = CodexNativeLibrary::take_cleanup_issues();
    assert!(
        ordinary_issues.is_empty(),
        "ordinary BUSY cleanup must quiesce without diagnostics: {ordinary_issues:?}"
    );

    unclosed_release_requires_async_close(path, &control);
    cleanup_failures_are_bounded_and_quarantined(path, &control);
}

fn unclosed_release_requires_async_close(path: &Path, control: &Control) {
    let setup_operations = get(control.operation_destroys);
    let native = CodexNativeLibrary::load(path).unwrap();
    let host = CodexHost::create_with_library(&native, host_options()).unwrap();
    block_on(host.start().unwrap()).unwrap();
    let agent = host.agent().unwrap();
    let conversations = agent.conversations().unwrap();
    let conversation = block_on(
        conversations
            .open(ConversationOpenOptions::default())
            .unwrap(),
    )
    .unwrap();
    wait_until(|| get(control.operation_destroys) >= setup_operations + 2);

    drop(conversation);
    let conversation_issue =
        wait_for_issue("conversation (explicit async close required)", Status::Busy);
    assert_eq!(conversation_issue.attempts, 24);
    drop(conversations);
    drop(agent);
    drop(host);
    let host_issue = wait_for_issue("host (explicit async close required)", Status::Busy);
    assert_eq!(host_issue.attempts, 24);
    drop(native);
}

fn cleanup_failures_are_bounded_and_quarantined(path: &Path, control: &Control) {
    let setup_operations = get(control.operation_destroys);
    let native = CodexNativeLibrary::load(path).unwrap();
    let host = CodexHost::create_with_library(&native, host_options()).unwrap();
    block_on(host.start().unwrap()).unwrap();
    let agent = host.agent().unwrap();
    let conversations = agent.conversations().unwrap();
    let conversation = block_on(
        conversations
            .open(ConversationOpenOptions::default())
            .unwrap(),
    )
    .unwrap();
    wait_until(|| get(control.operation_destroys) >= setup_operations + 2);

    // Permanent BUSY terminates after bounded backoff and retains the live native token.
    set(control.set_operation_destroy_mode, 1);
    drop(conversation.send("pending").unwrap());
    let busy = wait_for_issue("operation", Status::Busy);
    assert_eq!(busy.attempts, 24);
    set(control.set_operation_destroy_mode, 0);

    set(control.set_operation_destroy_mode, 2);
    block_on(conversation.send("hello").unwrap()).unwrap();
    let unexpected = wait_for_issue("operation", Status::InternalError);
    assert_eq!(unexpected.attempts, 1);
    set(control.set_operation_destroy_mode, 0);

    set(control.set_subscription_destroy_mode, 1);
    drop(conversation.states().unwrap());
    let subscription = wait_for_issue("subscription", Status::Busy);
    assert_eq!(subscription.attempts, 24);
    set(control.set_subscription_destroy_mode, 0);

    set(control.set_failure_release_mode, 2);
    let failure_cleanup = block_on(conversation.send("fail").unwrap()).unwrap_err();
    assert_eq!(failure_cleanup.status, Status::InternalError);
    let failure = wait_for_issue("failure", Status::InternalError);
    assert_eq!(failure.attempts, 1);
    set(control.set_failure_release_mode, 0);

    block_on(conversation.close().unwrap()).unwrap();
    drop(conversation);
    drop(conversations);
    drop(agent);
    block_on(host.close().unwrap()).unwrap();
    drop(host);
    drop(native);

    set(control.set_owned_release_mode, 2);
    let native = CodexNativeLibrary::load(path).unwrap();
    let host = CodexHost::create_with_library(&native, host_options()).unwrap();
    drop(host);
    let owner = wait_for_issue("host", Status::InternalError);
    assert_eq!(owner.attempts, 1);
    set(control.set_owned_release_mode, 0);
    drop(native);

    set(control.set_context_destroy_mode, 2);
    let native = CodexNativeLibrary::load(path).unwrap();
    let host = CodexHost::create_with_library(&native, host_options()).unwrap();
    block_on(host.close().unwrap()).unwrap();
    drop(host);
    let context = wait_for_issue("context", Status::InternalError);
    assert_eq!(context.attempts, 1);
    set(control.set_context_destroy_mode, 0);
    drop(native);
}
