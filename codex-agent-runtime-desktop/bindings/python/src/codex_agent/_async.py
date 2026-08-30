from __future__ import annotations

import asyncio
import ctypes
import itertools
import threading
from collections.abc import AsyncIterator, Callable
from typing import Generic, TypeVar

from ._errors import Failure, OperationError, Status, check
from ._ffi import Handle, NativeLibrary, OperationCallback, StateCallback


T = TypeVar("T")
_tokens = itertools.count(1)
_lock = threading.Lock()
_operations: dict[int, _PendingOperation[object]] = {}
_subscriptions: dict[int, StateSubscription[object]] = {}


def _token_value(user_data: int | None) -> int:
    if user_data is None:
        return 0
    return int(user_data)


@OperationCallback
def _operation_callback(_context: int, _operation: int, user_data: int | None) -> None:
    pending: _PendingOperation[object] | None = None
    try:
        with _lock:
            pending = _operations.get(_token_value(user_data))
        if pending is not None:
            pending._notify_from_native()
    except BaseException as error:  # ctypes callbacks must never unwind into C.
        if pending is not None:
            pending._fail_from_native(error)


@StateCallback
def _state_callback(
    _context: int,
    _subscription: int,
    event_status: int,
    snapshot: int | None,
    is_terminal: int,
    user_data: int | None,
) -> None:
    subscription: StateSubscription[object] | None = None
    try:
        with _lock:
            subscription = _subscriptions.get(_token_value(user_data))
        if subscription is not None:
            subscription._notify_from_native(event_status, snapshot, bool(is_terminal))
    except BaseException as error:  # ctypes callbacks must never unwind into C.
        if subscription is not None:
            subscription._fail_from_native(error)


class _PendingOperation(Generic[T]):
    def __init__(
        self,
        native: NativeLibrary,
        context: Handle,
        decoder: Callable[[Handle], T],
        failure_decoder: Callable[[Handle], Failure],
    ) -> None:
        self.native = native
        self.context = context
        self.decoder = decoder
        self.failure_decoder = failure_decoder
        self.loop = asyncio.get_running_loop()
        self.future: asyncio.Future[T] = self.loop.create_future()
        self.operation = Handle()
        self.token = next(_tokens)
        self.notified = False
        self.result: T | None = None
        self.error: BaseException | None = None
        with _lock:
            _operations[self.token] = self  # type: ignore[assignment]
        self.future.add_done_callback(self._cancel_if_requested)

    def start(self, invoke: Callable[[OperationCallback, ctypes.c_void_p, ctypes.POINTER(Handle)], int]) -> None:
        try:
            check(
                int(invoke(_operation_callback, ctypes.c_void_p(self.token), ctypes.byref(self.operation))),
                "asynchronous operation",
            )
        except BaseException:
            with _lock:
                _operations.pop(self.token, None)
            raise

    def _cancel_if_requested(self, future: asyncio.Future[T]) -> None:
        if future.cancelled() and self.operation.value:
            try:
                self.native.call(
                    "codex_agent_operation_cancel",
                    self.context,
                    self.operation,
                    allow=(Status.CLOSED, Status.STALE_HANDLE),
                )
            except BaseException:
                pass

    def _notify_from_native(self) -> None:
        if self.notified:
            return
        self.notified = True
        self.loop.call_soon_threadsafe(self._complete)

    def _fail_from_native(self, error: BaseException) -> None:
        self.loop.call_soon_threadsafe(self._complete_with_error, error)

    def _complete_with_error(self, error: BaseException) -> None:
        self.error = error
        self._destroy()

    def _complete(self) -> None:
        try:
            result_status = ctypes.c_int32()
            self.native.call(
                "codex_agent_operation_result",
                self.context,
                self.operation,
                ctypes.byref(result_status),
            )
            status = Status(result_status.value)
            if status is not Status.OK:
                failure: Failure | None = None
                failure_handle = Handle()
                failure_status = self.native.call(
                    "codex_agent_operation_failure",
                    self.context,
                    self.operation,
                    ctypes.byref(failure_handle),
                    allow=(Status.NOT_READY,),
                )
                if failure_status is Status.OK:
                    failure = self.failure_decoder(failure_handle)
                raise OperationError(status, failure)
            self.result = self.decoder(self.operation)
        except BaseException as error:
            self.error = error
        self._destroy()

    def _destroy(self) -> None:
        status = self.native.call(
            "codex_agent_operation_destroy",
            self.context,
            ctypes.byref(self.operation),
            allow=(Status.BUSY,),
        )
        if status is Status.BUSY:
            self.loop.call_later(0.001, self._destroy)
            return
        with _lock:
            _operations.pop(self.token, None)
        if self.future.done():
            return
        if self.error is not None:
            self.future.set_exception(self.error)
        else:
            self.future.set_result(self.result)  # type: ignore[arg-type]


async def run_operation(
    native: NativeLibrary,
    context: Handle,
    invoke: Callable[[OperationCallback, ctypes.c_void_p, ctypes.POINTER(Handle)], int],
    decoder: Callable[[Handle], T],
    failure_decoder: Callable[[Handle], Failure],
) -> T:
    pending = _PendingOperation(native, context, decoder, failure_decoder)
    pending.start(invoke)
    return await pending.future


_END = object()


class StateSubscription(AsyncIterator[T], Generic[T]):
    def __init__(
        self,
        native: NativeLibrary,
        context: Handle,
        subscribe: Callable[[StateCallback, ctypes.c_void_p, ctypes.POINTER(Handle)], int],
        decoder: Callable[[Handle], T],
    ) -> None:
        self.native = native
        self.context = context
        self.decoder = decoder
        self.loop = asyncio.get_running_loop()
        self.queue: asyncio.Queue[T | BaseException | object] = asyncio.Queue()
        self.subscription = Handle()
        self.token = next(_tokens)
        self.closed = False
        self._close_waiter: asyncio.Future[None] | None = None
        with _lock:
            _subscriptions[self.token] = self  # type: ignore[assignment]
        try:
            check(
                int(subscribe(_state_callback, ctypes.c_void_p(self.token), ctypes.byref(self.subscription))),
                "state subscription",
            )
        except BaseException:
            with _lock:
                _subscriptions.pop(self.token, None)
            raise

    def __aiter__(self) -> StateSubscription[T]:
        return self

    async def __anext__(self) -> T:
        item = await self.queue.get()
        if item is _END:
            raise StopAsyncIteration
        if isinstance(item, BaseException):
            raise item
        return item  # type: ignore[return-value]

    async def __aenter__(self) -> StateSubscription[T]:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    def _notify_from_native(self, event_status: int, snapshot: int | None, terminal: bool) -> None:
        self.loop.call_soon_threadsafe(self._accept, event_status, snapshot, terminal)

    def _fail_from_native(self, error: BaseException) -> None:
        self.loop.call_soon_threadsafe(self._accept_error, error)

    def _accept_error(self, error: BaseException) -> None:
        self.queue.put_nowait(error)
        self._begin_close()

    def _accept(self, event_status: int, snapshot_value: int | None, terminal: bool) -> None:
        snapshot = Handle(snapshot_value)
        try:
            status = Status(event_status)
            if status is not Status.OK:
                self.queue.put_nowait(OperationError(status))
            elif snapshot.value:
                self.queue.put_nowait(self.decoder(snapshot))
        except BaseException as error:
            self.queue.put_nowait(error)
            terminal = True
        finally:
            if snapshot.value:
                try:
                    self.native.call("codex_agent_snapshot_destroy", self.context, ctypes.byref(snapshot))
                except BaseException as error:
                    self.queue.put_nowait(error)
                    terminal = True
        if terminal:
            self._begin_close()

    async def aclose(self) -> None:
        if self.closed:
            return
        if self._close_waiter is None:
            self._close_waiter = self.loop.create_future()
            self._begin_close()
        await self._close_waiter

    def _begin_close(self) -> None:
        if self.closed:
            return
        if self._close_waiter is None:
            self._close_waiter = self.loop.create_future()
        status = self.native.call(
            "codex_agent_subscription_destroy",
            self.context,
            ctypes.byref(self.subscription),
            allow=(Status.BUSY,),
        )
        if status is Status.BUSY:
            self.loop.call_later(0.001, self._begin_close)
            return
        self.closed = True
        with _lock:
            _subscriptions.pop(self.token, None)
        self.queue.put_nowait(_END)
        if not self._close_waiter.done():
            self._close_waiter.set_result(None)


class StateStream(Generic[T]):
    def __init__(
        self,
        current: Callable[[], T],
        subscribe: Callable[[], StateSubscription[T]],
    ) -> None:
        self._current = current
        self._subscribe = subscribe

    @property
    def current(self) -> T:
        return self._current()

    def subscribe(self) -> StateSubscription[T]:
        return self._subscribe()

    def __aiter__(self) -> StateSubscription[T]:
        return self.subscribe()
