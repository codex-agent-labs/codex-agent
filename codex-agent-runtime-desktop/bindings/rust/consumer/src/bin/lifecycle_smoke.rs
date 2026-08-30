use codex_agent::{
    ClientInfo, CodexError, CodexHost, CodexNativeLibrary, ConversationOpenOptions, HostOptions,
    HostStateKind,
};
use std::future::Future;
use std::path::PathBuf;
use std::sync::Arc;
use std::task::{Context, Poll, Wake, Waker};
use std::time::Duration;

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
        match future.as_mut().poll(&mut context) {
            Poll::Ready(value) => return value,
            Poll::Pending => std::thread::park_timeout(Duration::from_millis(10)),
        }
    }
}

fn main() -> Result<(), CodexError> {
    let library = PathBuf::from(
        std::env::args_os()
            .nth(1)
            .expect("usage: codex-agent-rust-lifecycle-smoke <fixture-library>"),
    );
    let native = CodexNativeLibrary::load(&library)?;
    let host = CodexHost::create_with_library(
        &native,
        HostOptions {
            bundle_directory: "/bundle".into(),
            data_directory: "/data".into(),
            client_info: ClientInfo {
                name: "rust-example".into(),
                title: "Rust example".into(),
                version: "1.0.0".into(),
            },
        },
    )?;

    block_on(host.start()?)?;
    assert_eq!(host.state()?.kind, HostStateKind::Ready);
    let agent = host.agent()?;
    let conversations = agent.conversations()?;
    let conversation = block_on(conversations.open(ConversationOpenOptions::default())?)?;
    block_on(conversation.send("Hello from Rust")?)?;
    block_on(conversation.close()?)?;

    drop(conversation);
    block_on(host.close()?)?;
    drop(conversations);
    drop(agent);
    drop(host);
    drop(native);
    assert!(CodexNativeLibrary::take_cleanup_issues().is_empty());
    Ok(())
}
