use crate::ffi;
use crate::{
    CodexError, ContextInner, Status, check, operation_error, quarantine_token, retry_cleanup,
};
use futures_core::Stream;
use std::any::Any;
use std::collections::VecDeque;
use std::ffi::c_void;
use std::future::Future;
use std::marker::PhantomData;
use std::pin::Pin;
use std::rc::Rc;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::task::{Context, Poll, Waker};

struct OperationSignal {
    context: Arc<ContextInner>,
    _owner: Arc<dyn Any + Send + Sync>,
    operation: Mutex<usize>,
    completed: AtomicBool,
    waker: Mutex<Option<Waker>>,
    callback_claimed: AtomicBool,
    callback_raw: AtomicUsize,
    cleanup_started: AtomicBool,
}

unsafe extern "C" fn operation_callback(
    _: *mut ffi::Context,
    operation: *mut ffi::Operation,
    user_data: *mut c_void,
) {
    let raw = user_data.cast::<OperationSignal>();
    // SAFETY: user_data is the persistent Arc pointer created by start_operation. It remains live
    // until either this callback or successful destruction atomically claims it.
    let claimed = unsafe { (*raw).callback_claimed.swap(true, Ordering::AcqRel) };
    if claimed {
        return;
    }
    // SAFETY: this callback just claimed the Arc created by start_operation.
    let state = unsafe { Arc::from_raw(raw) };
    let _ = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        *state
            .operation
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner()) = operation as usize;
        state.completed.store(true, Ordering::Release);
        if let Some(waker) = state
            .waker
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .take()
        {
            waker.wake();
        }
    }));
}

fn reclaim_operation_callback(state: &OperationSignal) {
    if !state.callback_claimed.swap(true, Ordering::AcqRel) {
        let raw = state.callback_raw.load(Ordering::Acquire) as *const OperationSignal;
        if !raw.is_null() {
            // SAFETY: successful destroy guarantees the callback cannot start, and this branch
            // atomically owns the persistent Arc reference passed as user_data.
            drop(unsafe { Arc::from_raw(raw) });
        }
    }
}

fn cleanup_operation(state: Arc<OperationSignal>) {
    if state.cleanup_started.swap(true, Ordering::AcqRel) {
        return;
    }
    let operation = std::mem::take(
        &mut *state
            .operation
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner()),
    );
    if operation == 0 {
        reclaim_operation_callback(&state);
        return;
    }

    let cleanup_state = state.clone();
    let destroy = move || destroy_operation(cleanup_state, operation);

    // Never block Drop or a synchronously waking executor on native callback quiescence.
    if std::thread::Builder::new()
        .name("codex-agent-operation-cleanup".into())
        .spawn(destroy)
        .is_err()
    {
        quarantine_operation(state, operation, ffi::STATUS_INTERNAL_ERROR, 1);
    }
}

fn destroy_operation(state: Arc<OperationSignal>, operation: usize) {
    let mut raw = operation as *mut ffi::Operation;
    let (status, attempts) = retry_cleanup(|| {
        // SAFETY: raw is the unique owned operation token, and this thread-local slot is not shared.
        unsafe { (state.context.library.api.operation_destroy)(state.context.ptr(), &mut raw) }
    });
    if status == ffi::STATUS_OK {
        reclaim_operation_callback(&state);
    } else {
        quarantine_operation(state, raw as usize, status, attempts);
    }
}

fn quarantine_operation(state: Arc<OperationSignal>, operation: usize, status: i32, attempts: u32) {
    *state
        .operation
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner()) = operation;
    quarantine_token(
        state.context.clone(),
        operation,
        "operation",
        status,
        attempts,
    );
    let _ = Arc::into_raw(state);
}

/// A cancellable native Codex operation projected as a Rust [`Future`].
///
/// Dropping an unfinished operation requests cancellation and retains callback storage until the
/// native C SDK proves quiescence.
type OperationProjector<T> =
    dyn FnOnce(&Arc<ContextInner>, *mut ffi::Operation) -> Result<T, CodexError>;

pub struct CodexOperation<T> {
    state: Arc<OperationSignal>,
    projector: Option<Box<OperationProjector<T>>>,
    finished: bool,
    _not_send_or_sync: PhantomData<Rc<()>>,
}

impl<T> CodexOperation<T> {
    /// Requests cancellation. Completion still arrives through the future.
    pub fn cancel(&self) -> Result<(), CodexError> {
        let operation = *self
            .state
            .operation
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if operation == 0 {
            return Ok(());
        }
        // SAFETY: the operation remains owned by state and its slot is not mutated here.
        check(
            unsafe {
                (self.state.context.library.api.operation_cancel)(
                    self.state.context.ptr(),
                    operation as *mut ffi::Operation,
                )
            },
            "cancel native operation",
        )
    }
}

impl<T> Future for CodexOperation<T> {
    type Output = Result<T, CodexError>;

    fn poll(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Self::Output> {
        if self.finished {
            panic!("CodexOperation polled after completion");
        }
        if !self.state.completed.load(Ordering::Acquire) {
            *self
                .state
                .waker
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner()) = Some(cx.waker().clone());
            if !self.state.completed.load(Ordering::Acquire) {
                return Poll::Pending;
            }
        }

        let operation = *self
            .state
            .operation
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            as *mut ffi::Operation;
        let mut result = ffi::STATUS_OK;
        #[cfg(test)]
        ffi::test_trace_invocation("codex_agent_operation_result");
        // SAFETY: callback completion published this still-owned operation token.
        let status = unsafe {
            (self.state.context.library.api.operation_result)(
                self.state.context.ptr(),
                operation,
                &mut result,
            )
        };
        let value = if status != ffi::STATUS_OK {
            Err(CodexError::new(
                Status::from_raw(status),
                "read native operation result",
            ))
        } else if result == ffi::STATUS_OK {
            self.projector
                .take()
                .expect("operation projector consumed once")(
                &self.state.context, operation
            )
        } else {
            Err(operation_error(&self.state.context, operation, result))
        };
        self.finished = true;
        cleanup_operation(self.state.clone());
        Poll::Ready(value)
    }
}

impl<T> Unpin for CodexOperation<T> {}

impl<T> Drop for CodexOperation<T> {
    fn drop(&mut self) {
        if self.finished {
            return;
        }
        let _ = self.cancel();
        cleanup_operation(self.state.clone());
    }
}

pub(crate) fn start_operation<T>(
    context: Arc<ContextInner>,
    owner: Arc<dyn Any + Send + Sync>,
    initiate: impl FnOnce(ffi::OperationCallback, *mut c_void, *mut *mut ffi::Operation) -> i32,
    projector: impl FnOnce(&Arc<ContextInner>, *mut ffi::Operation) -> Result<T, CodexError> + 'static,
) -> Result<CodexOperation<T>, CodexError> {
    let state = Arc::new(OperationSignal {
        context,
        _owner: owner,
        operation: Mutex::new(0),
        completed: AtomicBool::new(false),
        waker: Mutex::new(None),
        callback_claimed: AtomicBool::new(false),
        callback_raw: AtomicUsize::new(0),
        cleanup_started: AtomicBool::new(false),
    });
    let raw = Arc::into_raw(state.clone());
    state.callback_raw.store(raw as usize, Ordering::Release);
    let mut operation = std::ptr::null_mut();
    let status = initiate(operation_callback, raw.cast_mut().cast(), &mut operation);
    if status != ffi::STATUS_OK {
        reclaim_operation_callback(&state);
        return Err(CodexError::new(
            Status::from_raw(status),
            "start native operation",
        ));
    }
    *state
        .operation
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner()) = operation as usize;
    Ok(CodexOperation {
        state,
        projector: Some(Box::new(projector)),
        finished: false,
        _not_send_or_sync: PhantomData,
    })
}

#[derive(Clone, Copy)]
struct RawEvent {
    status: i32,
    snapshot: usize,
}

struct SubscriptionSignal {
    context: Arc<ContextInner>,
    _owner: Arc<dyn Any + Send + Sync>,
    subscription: Mutex<usize>,
    queue: Mutex<VecDeque<RawEvent>>,
    terminal: AtomicBool,
    closed: AtomicBool,
    waker: Mutex<Option<Waker>>,
    callback_claimed: AtomicBool,
    callback_raw: AtomicUsize,
    cleanup_started: AtomicBool,
}

unsafe extern "C" fn state_callback(
    _: *mut ffi::Context,
    subscription: *mut ffi::Subscription,
    event_status: i32,
    snapshot: *mut ffi::Snapshot,
    is_terminal: i32,
    user_data: *mut c_void,
) {
    let raw = user_data.cast::<SubscriptionSignal>();
    // SAFETY: the persistent callback Arc remains allocated until terminal or destroy; this adds a
    // temporary callback-local reference without consuming it.
    unsafe { Arc::increment_strong_count(raw) };
    // SAFETY: paired with increment_strong_count immediately above.
    let state = unsafe { Arc::from_raw(raw) };
    let terminal = is_terminal != 0;
    let _ = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        *state
            .subscription
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner()) = subscription as usize;
        if state.closed.load(Ordering::Acquire) {
            if !snapshot.is_null() {
                state.context.destroy_snapshot(snapshot);
            }
        } else if !snapshot.is_null() || event_status != ffi::STATUS_OK {
            state
                .queue
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner())
                .push_back(RawEvent {
                    status: event_status,
                    snapshot: snapshot as usize,
                });
        }
        if terminal {
            state.terminal.store(true, Ordering::Release);
        }
        if let Some(waker) = state
            .waker
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .take()
        {
            waker.wake();
        }
    }));
    if terminal {
        reclaim_subscription_callback(&state);
    }
}

fn reclaim_subscription_callback(state: &SubscriptionSignal) {
    if !state.callback_claimed.swap(true, Ordering::AcqRel) {
        let raw = state.callback_raw.load(Ordering::Acquire) as *const SubscriptionSignal;
        if !raw.is_null() {
            // SAFETY: terminal callback or successful destruction exclusively owns this persistent
            // callback Arc reference, selected by callback_claimed.
            drop(unsafe { Arc::from_raw(raw) });
        }
    }
}

fn drain_snapshots(state: &SubscriptionSignal) {
    let events: Vec<_> = state
        .queue
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .drain(..)
        .collect();
    for event in events {
        if event.snapshot != 0 {
            state
                .context
                .destroy_snapshot(event.snapshot as *mut ffi::Snapshot);
        }
    }
}

fn cleanup_subscription(state: Arc<SubscriptionSignal>) {
    if state.cleanup_started.swap(true, Ordering::AcqRel) {
        return;
    }
    state.closed.store(true, Ordering::Release);
    drain_snapshots(&state);
    let subscription = std::mem::take(
        &mut *state
            .subscription
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner()),
    );
    if subscription == 0 {
        reclaim_subscription_callback(&state);
        return;
    }
    let cleanup_state = state.clone();
    let cleanup = move || destroy_subscription(cleanup_state, subscription);
    if std::thread::Builder::new()
        .name("codex-agent-subscription-cleanup".into())
        .spawn(cleanup)
        .is_err()
    {
        quarantine_subscription(state, subscription, ffi::STATUS_INTERNAL_ERROR, 1);
    }
}

fn destroy_subscription(state: Arc<SubscriptionSignal>, subscription: usize) {
    let mut raw = subscription as *mut ffi::Subscription;
    let (status, attempts) = retry_cleanup(|| {
        // SAFETY: raw is the one owned subscription token in a thread-local slot.
        unsafe { (state.context.library.api.subscription_destroy)(state.context.ptr(), &mut raw) }
    });
    if status == ffi::STATUS_OK {
        drain_snapshots(&state);
        reclaim_subscription_callback(&state);
    } else {
        quarantine_subscription(state, raw as usize, status, attempts);
    }
}

fn quarantine_subscription(
    state: Arc<SubscriptionSignal>,
    subscription: usize,
    status: i32,
    attempts: u32,
) {
    *state
        .subscription
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner()) = subscription;
    quarantine_token(
        state.context.clone(),
        subscription,
        "subscription",
        status,
        attempts,
    );
    let _ = Arc::into_raw(state);
}

/// A stream of immutable current-value/state updates from the native SDK.
type StateProjector<T> = dyn FnMut(&Arc<ContextInner>, *mut ffi::Snapshot) -> Result<T, CodexError>;

pub struct CodexStateStream<T> {
    state: Arc<SubscriptionSignal>,
    projector: Box<StateProjector<T>>,
    ended: bool,
    _not_send_or_sync: PhantomData<Rc<()>>,
}

impl<T> CodexStateStream<T> {
    /// Returns a future for the next state update without requiring an extension-trait crate.
    #[allow(
        clippy::should_implement_trait,
        reason = "this is asynchronous Stream::next"
    )]
    pub fn next(&mut self) -> NextState<'_, T> {
        NextState { stream: self }
    }
}

impl<T> Stream for CodexStateStream<T> {
    type Item = Result<T, CodexError>;

    fn poll_next(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Option<Self::Item>> {
        if self.ended {
            return Poll::Ready(None);
        }
        let event = {
            self.state
                .queue
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner())
                .pop_front()
        };
        if let Some(event) = event {
            let value = if event.status != ffi::STATUS_OK {
                if event.snapshot != 0 {
                    self.state
                        .context
                        .destroy_snapshot(event.snapshot as *mut ffi::Snapshot);
                }
                Err(CodexError::new(
                    Status::from_raw(event.status),
                    "observe native state",
                ))
            } else if event.snapshot == 0 {
                Err(CodexError::new(
                    Status::InternalError,
                    "native state event omitted its snapshot",
                ))
            } else {
                let context = self.state.context.clone();
                let snapshot = SnapshotGuard {
                    context: context.clone(),
                    raw: event.snapshot as *mut ffi::Snapshot,
                };
                (self.projector)(&context, snapshot.raw)
            };
            return Poll::Ready(Some(value));
        }
        if self.state.terminal.load(Ordering::Acquire) {
            self.ended = true;
            return Poll::Ready(None);
        }
        *self
            .state
            .waker
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner()) = Some(cx.waker().clone());
        if self.state.terminal.load(Ordering::Acquire)
            || !self
                .state
                .queue
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner())
                .is_empty()
        {
            cx.waker().wake_by_ref();
        }
        Poll::Pending
    }
}

impl<T> Unpin for CodexStateStream<T> {}

impl<T> Drop for CodexStateStream<T> {
    fn drop(&mut self) {
        cleanup_subscription(self.state.clone());
    }
}

/// Future returned by [`CodexStateStream::next`].
pub struct NextState<'a, T> {
    stream: &'a mut CodexStateStream<T>,
}

impl<T> Future for NextState<'_, T> {
    type Output = Option<Result<T, CodexError>>;

    fn poll(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Self::Output> {
        Pin::new(&mut *self.get_mut().stream).poll_next(cx)
    }
}

struct SnapshotGuard {
    context: Arc<ContextInner>,
    raw: *mut ffi::Snapshot,
}

impl Drop for SnapshotGuard {
    fn drop(&mut self) {
        self.context.destroy_snapshot(self.raw);
    }
}

pub(crate) fn start_subscription<T>(
    context: Arc<ContextInner>,
    owner: Arc<dyn Any + Send + Sync>,
    initiate: impl FnOnce(ffi::StateCallback, *mut c_void, *mut *mut ffi::Subscription) -> i32,
    projector: impl FnMut(&Arc<ContextInner>, *mut ffi::Snapshot) -> Result<T, CodexError> + 'static,
) -> Result<CodexStateStream<T>, CodexError> {
    let state = Arc::new(SubscriptionSignal {
        context,
        _owner: owner,
        subscription: Mutex::new(0),
        queue: Mutex::new(VecDeque::new()),
        terminal: AtomicBool::new(false),
        closed: AtomicBool::new(false),
        waker: Mutex::new(None),
        callback_claimed: AtomicBool::new(false),
        callback_raw: AtomicUsize::new(0),
        cleanup_started: AtomicBool::new(false),
    });
    let raw = Arc::into_raw(state.clone());
    state.callback_raw.store(raw as usize, Ordering::Release);
    let mut subscription = std::ptr::null_mut();
    let status = initiate(state_callback, raw.cast_mut().cast(), &mut subscription);
    if status != ffi::STATUS_OK {
        reclaim_subscription_callback(&state);
        drain_snapshots(&state);
        return Err(CodexError::new(
            Status::from_raw(status),
            "subscribe to native state",
        ));
    }
    *state
        .subscription
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner()) = subscription as usize;
    Ok(CodexStateStream {
        state,
        projector: Box::new(projector),
        ended: false,
        _not_send_or_sync: PhantomData,
    })
}
