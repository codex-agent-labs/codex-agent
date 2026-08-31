use codex_agent::{
    ClientInfo, CodexError, CodexHost, CodexNativeLibrary, HostOptions, HostStateKind, Status,
};
use std::ffi::OsString;
use std::future::Future;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::task::{Context, Poll, Wake, Waker};
use std::time::Duration;

const USAGE: &str = "usage: codex-agent-rust-host-smoke <absolute-c-sdk-library>";

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

fn consumer_error(status: Status, action: impl Into<String>) -> CodexError {
    CodexError {
        status,
        action: action.into(),
        failure: None,
    }
}

fn parse_library_path(
    arguments: impl IntoIterator<Item = OsString>,
) -> Result<PathBuf, CodexError> {
    let mut arguments = arguments.into_iter();
    let library_path = arguments
        .next()
        .ok_or_else(|| consumer_error(Status::InvalidArgument, USAGE))?;
    if arguments.next().is_some() {
        return Err(consumer_error(Status::InvalidArgument, USAGE));
    }
    Ok(PathBuf::from(library_path))
}

fn real_host_smoke(library_path: &Path) -> Result<(), CodexError> {
    let library_path = library_path.canonicalize().map_err(|error| {
        consumer_error(
            Status::InvalidArgument,
            format!(
                "resolve explicit C SDK library {}: {error}",
                library_path.display()
            ),
        )
    })?;
    if !library_path.is_file() {
        return Err(consumer_error(
            Status::InvalidArgument,
            format!(
                "explicit C SDK library is not a file: {}",
                library_path.display()
            ),
        ));
    }
    let stale_issues = CodexNativeLibrary::take_cleanup_issues();
    if !stale_issues.is_empty() {
        return Err(consumer_error(
            Status::InternalError,
            format!("unexpected pre-existing cleanup issues: {stale_issues:?}"),
        ));
    }

    let native = CodexNativeLibrary::load(&library_path)?;
    let host = CodexHost::create_with_library(
        &native,
        HostOptions {
            bundle_directory: "unused-unprepared-bundle".into(),
            data_directory: "unused-host-consumer-data".into(),
            client_info: ClientInfo {
                name: "installed-host-smoke".into(),
                title: "Installed Host smoke".into(),
                version: "1.0.0".into(),
            },
        },
    )?;
    let initial = host.state()?;
    if initial.kind != HostStateKind::New {
        block_on(host.close()?)?;
        return Err(consumer_error(
            Status::InternalError,
            format!("expected new Host state, got {:?}", initial.kind),
        ));
    }

    block_on(host.close()?)?;
    block_on(host.close()?)?;
    if host.state()?.kind != HostStateKind::Closed {
        return Err(consumer_error(
            Status::InternalError,
            "repeated close did not leave the Host closed",
        ));
    }
    drop(host);
    drop(native);

    let cleanup_issues = CodexNativeLibrary::take_cleanup_issues();
    if !cleanup_issues.is_empty() {
        return Err(consumer_error(
            Status::InternalError,
            format!("installed Host cleanup failed: {cleanup_issues:?}"),
        ));
    }
    println!(
        "installed-crate Host smoke passed with {}",
        library_path.display()
    );
    Ok(())
}

fn main() -> Result<(), CodexError> {
    let library_path = parse_library_path(std::env::args_os().skip(1))?;
    real_host_smoke(&library_path)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn requires_exactly_one_sdk_path() {
        let missing = parse_library_path(Vec::<OsString>::new()).unwrap_err();
        assert_eq!(missing.status, Status::InvalidArgument);
        assert_eq!(missing.action, USAGE);

        let path = parse_library_path([OsString::from("sdk")]).unwrap();
        assert_eq!(path, PathBuf::from("sdk"));

        let extra =
            parse_library_path([OsString::from("sdk"), OsString::from("extra")]).unwrap_err();
        assert_eq!(extra.status, Status::InvalidArgument);
        assert_eq!(extra.action, USAGE);
    }
}
