import 'dart:async';
import 'dart:convert';
import 'dart:ffi';

import 'cancellation.dart';
import 'conversation_native.dart';
import 'errors.dart';
import 'ffi.dart';
import 'models.dart';
import 'residual_models.dart';
import 'value_native.dart';

part 'leaf_services.dart';

typedef _OperationStarter = int Function(
  Pointer<NativeFunction<OperationCallbackNative>> callback,
  Pointer<Void> userData,
  Pointer<Pointer<CodexNativeOperation>> outOperation,
);

typedef _SubscriptionStarter = int Function(
  Pointer<NativeFunction<StateCallbackNative>> callback,
  Pointer<Void> userData,
  Pointer<Pointer<CodexNativeSubscription>> outSubscription,
);

@pragma('vm:never-inline')
void _keepAlive(Object value) {
  identityHashCode(value);
}

final class _NativeContextOwner {
  _NativeContextOwner(this.api)
      : conversationApi = ConversationNativeApi(api),
        slot = newHandleSlot<CodexNativeContext>() {
    try {
      checkStatus(api.contextCreate(slot), 'codex_agent_context_create');
    } catch (_) {
      nativeMemory.free(slot);
      rethrow;
    }
  }

  final NativeApi api;
  final ConversationNativeApi conversationApi;
  final Pointer<Pointer<CodexNativeContext>> slot;
  final List<Future<void> Function()> _deferredCleanups = [];
  final Set<Future<void> Function()> _subscriptions = {};
  bool open = true;
  bool _subscriptionsClosing = false;
  Future<void>? _closeFuture;

  Pointer<CodexNativeContext> require() {
    if (!open || slot.value == nullptr) {
      throw const CodexClosedException('the owning CodexHost is closed');
    }
    return slot.value;
  }

  void deferCleanup(Future<void> Function() cleanup) {
    _deferredCleanups.add(cleanup);
  }

  bool registerSubscription(Future<void> Function() close) {
    if (_subscriptionsClosing || !open) return false;
    _subscriptions.add(close);
    return true;
  }

  void unregisterSubscription(Future<void> Function() close) {
    _subscriptions.remove(close);
  }

  Future<void> closeSubscriptions() async {
    _subscriptionsClosing = true;
    await Future.wait<void>(
      _subscriptions.toList(growable: false).map((close) => close()),
    );
  }

  Future<void> retryDeferredCleanups() async {
    for (final cleanup in _deferredCleanups.toList(growable: false)) {
      await cleanup();
      _deferredCleanups.remove(cleanup);
    }
  }

  Future<void> close() {
    if (!open) return Future<void>.value();
    final active = _closeFuture;
    if (active != null) return active;
    final completer = Completer<void>();
    _closeFuture = completer.future;
    unawaited(
      _closeImpl()
          .then(completer.complete, onError: completer.completeError)
          .whenComplete(() {
        if (open) _closeFuture = null;
      }),
    );
    return completer.future;
  }

  Future<void> _closeImpl() async {
    await closeSubscriptions();
    await retryDeferredCleanups();
    while (true) {
      final status = api.contextDestroy(slot);
      if (status == CodexStatus.busy.value) {
        await Future<void>.delayed(Duration.zero);
        continue;
      }
      checkStatus(status, 'codex_agent_context_destroy');
      open = false;
      nativeMemory.free(slot);
      return;
    }
  }
}

final class _ReleaseTicket<T extends NativeType> {
  _ReleaseTicket(this.owner, this.slot, this.release);

  final _NativeContextOwner owner;
  final Pointer<Pointer<T>> slot;
  final int Function(Pointer<CodexNativeContext>, Pointer<Pointer<T>>) release;
  bool released = false;
  Future<void>? _closeFuture;

  Future<void> close(String name) {
    if (released) return Future<void>.value();
    final active = _closeFuture;
    if (active != null) return active;
    final completer = Completer<void>();
    _closeFuture = completer.future;
    unawaited(
      _closeImpl(name)
          .then(completer.complete, onError: completer.completeError)
          .whenComplete(() {
        if (!released) _closeFuture = null;
      }),
    );
    return completer.future;
  }

  Future<void> _closeImpl(String name) async {
    if (!owner.open) {
      released = true;
      nativeMemory.free(slot);
      return;
    }
    while (true) {
      final status = release(owner.require(), slot);
      if (status == CodexStatus.busy.value) {
        await Future<void>.delayed(Duration.zero);
        continue;
      }
      checkStatus(status, name);
      released = true;
      nativeMemory.free(slot);
      return;
    }
  }

  void finalize(String name) {
    if (released) return;
    final work = close(name);
    _finalizerWork.add(work);
    unawaited(work.then<void>((_) {
      _finalizerWork.remove(work);
    }, onError: (Object _, StackTrace __) {
      _finalizerWork.remove(work);
      _failedFinalizers.add(this);
    }));
  }
}

final Set<Future<void>> _finalizerWork = <Future<void>>{};
final Set<Object> _failedFinalizers = <Object>{};

final class _SubscriptionScope {
  final Set<Future<void> Function()> _subscriptions = {};
  Future<void>? _closeFuture;
  bool closed = false;
  bool _closing = false;

  bool register(Future<void> Function() close) {
    if (_closing || closed) return false;
    _subscriptions.add(close);
    return true;
  }

  void unregister(Future<void> Function() close) {
    _subscriptions.remove(close);
  }

  Future<void> close() {
    if (closed) return Future<void>.value();
    final active = _closeFuture;
    if (active != null) return active;
    final completer = Completer<void>();
    _closeFuture = completer.future;
    _closing = true;
    unawaited(() async {
      try {
        await Future.wait<void>(
          _subscriptions.toList(growable: false).map((close) => close()),
        );
        closed = true;
        completer.complete();
      } catch (error, stack) {
        completer.completeError(error, stack);
      } finally {
        if (!closed) {
          _closing = false;
          _closeFuture = null;
        }
      }
    }());
    return completer.future;
  }
}

final class _HostLifetime implements Finalizable {
  _HostLifetime(this.coordinator) {
    _finalizer.attach(this, coordinator, detach: this);
  }

  static final Finalizer<_HostCloseCoordinator> _finalizer =
      Finalizer<_HostCloseCoordinator>((coordinator) => coordinator.finalize());

  final _HostCloseCoordinator coordinator;

  void detach() => _finalizer.detach(this);
}

final class _OwnedNative<T extends NativeType> {
  _OwnedNative(this.owner, this.lifetime, Pointer<Pointer<T>> slot,
      int Function(Pointer<CodexNativeContext>, Pointer<Pointer<T>>) release)
      : ticket = _ReleaseTicket<T>(owner, slot, release);

  final _NativeContextOwner owner;
  final _HostLifetime lifetime;
  final _ReleaseTicket<T> ticket;

  Pointer<T> requireHandle(String name) {
    owner.require();
    if (ticket.released || ticket.slot.value == nullptr) {
      throw CodexClosedException('$name is closed');
    }
    return ticket.slot.value;
  }
}

final class _HostCloseCoordinator {
  _HostCloseCoordinator(
    this.owner,
    Pointer<Pointer<CodexNativeHost>> hostSlot,
  ) : host = _ReleaseTicket<CodexNativeHost>(
          owner,
          hostSlot,
          owner.api.hostRelease,
        );

  final _NativeContextOwner owner;
  final _ReleaseTicket<CodexNativeHost> host;
  bool _semanticClosed = false;
  Future<void>? _closeFuture;

  Future<void> close({CodexCancellation? cancellation}) {
    if (!owner.open) return Future<void>.value();
    final active = _closeFuture;
    if (active != null) return active;
    final completer = Completer<void>();
    _closeFuture = completer.future;
    unawaited(
      _closeImpl(cancellation)
          .then(completer.complete, onError: completer.completeError)
          .whenComplete(() {
        if (owner.open) _closeFuture = null;
      }),
    );
    return completer.future;
  }

  Future<void> _closeImpl(CodexCancellation? cancellation) async {
    if (!_semanticClosed) {
      await _runOperation<void>(
        owner,
        (callback, userData, out) => owner.api.hostClose(
          owner.require(),
          host.slot.value,
          callback,
          userData,
          out,
        ),
        (_) {},
        cancellation: cancellation,
        pin: this,
      );
      _semanticClosed = true;
    }
    await owner.closeSubscriptions();
    await owner.retryDeferredCleanups();
    await host.close('codex_agent_host_release');
    await owner.close();
  }

  void finalize() {
    final work = close();
    _finalizerWork.add(work);
    unawaited(work.then<void>((_) {
      _finalizerWork.remove(work);
    }, onError: (Object _, StackTrace __) {
      _finalizerWork.remove(work);
      _failedFinalizers.add(this);
    }));
  }
}

Future<T> _runOperation<T>(
  _NativeContextOwner owner,
  _OperationStarter start,
  T Function(Pointer<CodexNativeOperation>) decode, {
  CodexCancellation? cancellation,
  required Object pin,
}) {
  final completer = Completer<T>();
  final operation = newHandleSlot<CodexNativeOperation>();
  var callbackArrived = false;
  var destroyed = false;
  var cleanupDeferred = false;
  Object? result;
  StackTrace? resultStack;
  void Function() detachCancellation = () {};
  late final NativeCallable<OperationCallbackNative> callable;

  void finishDestroy() {
    destroyed = true;
    detachCancellation();
    callable.close();
    nativeMemory.free(operation);
    _keepAlive(pin);
    if (completer.isCompleted) return;
    if (result is _OperationValue<T>) {
      completer.complete((result as _OperationValue<T>).value);
    } else {
      completer.completeError(
        result ?? StateError('operation produced no result'),
        resultStack,
      );
    }
  }

  Future<void> destroy() async {
    if (destroyed) return;
    if (operation.value == nullptr) {
      finishDestroy();
      return;
    }
    while (true) {
      final int status;
      try {
        status = owner.api.operationDestroy(owner.require(), operation);
      } catch (error, stack) {
        if (!cleanupDeferred) {
          cleanupDeferred = true;
          owner.deferCleanup(destroy);
        }
        if (!completer.isCompleted) completer.completeError(error, stack);
        return;
      }
      if (status == CodexStatus.busy.value) {
        await Future<void>.delayed(const Duration(milliseconds: 1));
        continue;
      }
      try {
        checkStatus(status, 'codex_agent_operation_destroy');
      } catch (error, stack) {
        if (!cleanupDeferred) {
          cleanupDeferred = true;
          owner.deferCleanup(destroy);
        }
        if (!completer.isCompleted) completer.completeError(error, stack);
        return;
      }
      finishDestroy();
      return;
    }
  }

  try {
    callable = NativeCallable<OperationCallbackNative>.listener(
      (
        Pointer<CodexNativeContext> context,
        Pointer<CodexNativeOperation> nativeOperation,
        Pointer<Void> userData,
      ) {
        if (callbackArrived) return;
        callbackArrived = true;
        Pointer<Int32>? status;
        try {
          status = nativeMemory.allocate<Int32>(sizeOf<Int32>());
          checkStatus(
            owner.api.operationResult(owner.require(), nativeOperation, status),
            'codex_agent_operation_result',
          );
          final operationStatus = CodexStatus.fromValue(status.value);
          if (operationStatus != CodexStatus.ok) {
            result = CodexOperationException(
              operationStatus,
              _operationFailure(owner, nativeOperation),
            );
          } else {
            result = _OperationValue<T>(decode(nativeOperation));
          }
        } catch (error, stack) {
          result = error;
          resultStack = stack;
        } finally {
          if (status != null) nativeMemory.free(status);
          unawaited(Future<void>.microtask(destroy));
        }
      },
    );
  } catch (error, stack) {
    nativeMemory.free(operation);
    completer.completeError(error, stack);
    return completer.future;
  }

  detachCancellation = cancellation?.attach(() {
        if (operation.value != nullptr && !destroyed) {
          final status =
              owner.api.operationCancel(owner.require(), operation.value);
          checkStatus(
            status,
            'codex_agent_operation_cancel',
            allow: const {CodexStatus.closed, CodexStatus.staleHandle},
          );
        }
      }) ??
      () {};

  try {
    checkStatus(
      start(callable.nativeFunction, nullptr, operation),
      'asynchronous Codex Agent operation',
    );
    if (cancellation?.isCancelled ?? false) {
      final status =
          owner.api.operationCancel(owner.require(), operation.value);
      checkStatus(
        status,
        'codex_agent_operation_cancel',
        allow: const {CodexStatus.closed, CodexStatus.staleHandle},
      );
    }
  } catch (error, stack) {
    result = error;
    resultStack = stack;
    unawaited(destroy());
  }
  return completer.future;
}

final class _OperationValue<T> {
  const _OperationValue(this.value);
  final T value;
}

Future<void> _destroyOwnedSlot<T extends NativeType>(
  _NativeContextOwner owner,
  Pointer<Pointer<T>> slot,
  int Function(Pointer<CodexNativeContext>, Pointer<Pointer<T>>) destroy,
  String name, {
  bool deferOnError = true,
}) async {
  if (slot.value == nullptr || !owner.open) {
    nativeMemory.free(slot);
    return;
  }
  while (true) {
    final int status;
    try {
      status = destroy(owner.require(), slot);
    } catch (_) {
      if (deferOnError) {
        owner.deferCleanup(
          () => _destroyOwnedSlot(
            owner,
            slot,
            destroy,
            name,
            deferOnError: false,
          ),
        );
      }
      rethrow;
    }
    if (status == CodexStatus.busy.value) {
      await Future<void>.delayed(const Duration(milliseconds: 1));
      continue;
    }
    try {
      checkStatus(status, name);
    } catch (_) {
      if (deferOnError) {
        owner.deferCleanup(
          () => _destroyOwnedSlot(
            owner,
            slot,
            destroy,
            name,
            deferOnError: false,
          ),
        );
      }
      rethrow;
    }
    nativeMemory.free(slot);
    return;
  }
}

void _releaseOwnedSlotOrDefer<T extends NativeType>(
  _NativeContextOwner owner,
  Pointer<Pointer<T>> slot,
  int Function(Pointer<CodexNativeContext>, Pointer<Pointer<T>>) release,
  String name,
) {
  final int status;
  try {
    status = release(owner.require(), slot);
  } catch (_) {
    owner.deferCleanup(
      () => _destroyOwnedSlot(owner, slot, release, name, deferOnError: false),
    );
    rethrow;
  }
  if (status == CodexStatus.ok.value) {
    nativeMemory.free(slot);
    return;
  }
  owner.deferCleanup(
    () => _destroyOwnedSlot(owner, slot, release, name, deferOnError: false),
  );
  if (status != CodexStatus.busy.value) checkStatus(status, name);
}

CodexFailure? _operationFailure(
  _NativeContextOwner owner,
  Pointer<CodexNativeOperation> operation,
) {
  final slot = newHandleSlot<CodexNativeFailure>();
  var transferred = false;
  try {
    final status = owner.api.operationFailure(owner.require(), operation, slot);
    if (status == CodexStatus.notReady.value) return null;
    checkStatus(status, 'codex_agent_operation_failure');
    transferred = true;
    return _decodeFailure(owner, slot);
  } finally {
    if (!transferred) {
      if (slot.value != nullptr) {
        _releaseOwnedSlotOrDefer(
          owner,
          slot,
          owner.api.failureRelease,
          'codex_agent_failure_release',
        );
      } else {
        nativeMemory.free(slot);
      }
    }
  }
}

CodexFailure _decodeFailure(
  _NativeContextOwner owner,
  Pointer<Pointer<CodexNativeFailure>> slot,
) {
  Pointer<Int32>? recoverable;
  try {
    recoverable = nativeMemory.allocate<Int32>(sizeOf<Int32>());
    final failure = slot.value;
    final code = copyString(owner.api.failureCode, owner.require(), failure);
    final message =
        copyString(owner.api.failureMessage, owner.require(), failure);
    checkStatus(
      owner.api.failureRecoverable(owner.require(), failure, recoverable),
      'codex_agent_failure_is_recoverable',
    );
    return CodexFailure(
      code: code,
      message: message,
      isRecoverable: recoverable.value != 0,
    );
  } finally {
    if (recoverable != null) nativeMemory.free(recoverable);
    _releaseOwnedSlotOrDefer(
      owner,
      slot,
      owner.api.failureRelease,
      'codex_agent_failure_release',
    );
  }
}

Future<T> _currentState<T, H extends NativeType>(
  _NativeContextOwner owner,
  Pointer<H> handle,
  CodexGetSnapshotDart<H> get,
  T Function(Pointer<CodexNativeSnapshot>) decode,
) async {
  final snapshot = newHandleSlot<CodexNativeSnapshot>();
  try {
    checkStatus(
        get(owner.require(), handle, snapshot), 'state current-value read');
    return decode(snapshot.value);
  } finally {
    if (snapshot.value != nullptr && owner.open) {
      await _destroyOwnedSlot(
        owner,
        snapshot,
        owner.api.snapshotDestroy,
        'codex_agent_snapshot_destroy',
      );
    } else {
      nativeMemory.free(snapshot);
    }
  }
}

Stream<T> _stateStream<T>(
  _NativeContextOwner owner,
  _SubscriptionStarter subscribe,
  T Function(Pointer<CodexNativeSnapshot>) decode,
  Object pin,
  _SubscriptionScope scope,
) {
  late final StreamController<T> controller;
  final subscription = newHandleSlot<CodexNativeSubscription>();
  var closed = false;
  var deliveryClosed = false;
  var cleanupDeferred = false;
  Future<void>? closeFuture;
  Future<void> eventTail = Future<void>.value();
  late final Future<void> Function() closeNative;
  late final Future<void> Function() closeStream;
  late final NativeCallable<StateCallbackNative> callable;

  Future<void> attemptDestroy() async {
    if (closed) return;
    deliveryClosed = true;
    if (owner.open && subscription.value != nullptr) {
      while (true) {
        final int status;
        try {
          status = owner.api.subscriptionDestroy(owner.require(), subscription);
        } catch (_) {
          if (!cleanupDeferred) {
            cleanupDeferred = true;
            owner.deferCleanup(attemptDestroy);
          }
          rethrow;
        }
        if (status == CodexStatus.busy.value) {
          await Future<void>.delayed(const Duration(milliseconds: 1));
          continue;
        }
        try {
          checkStatus(status, 'codex_agent_subscription_destroy');
        } catch (_) {
          if (!cleanupDeferred) {
            cleanupDeferred = true;
            owner.deferCleanup(attemptDestroy);
          }
          rethrow;
        }
        break;
      }
    }
    // A listener callback posts to this isolate. Once the native destroy has
    // quiesced its worker, give already-posted callbacks an event turn to join
    // eventTail, then await their snapshot cleanup before reclaiming anything.
    await Future<void>.delayed(Duration.zero);
    await eventTail;
    closed = true;
    owner.unregisterSubscription(closeStream);
    scope.unregister(closeStream);
    callable.close();
    nativeMemory.free(subscription);
    _keepAlive(pin);
  }

  closeNative = () {
    if (closed) return Future<void>.value();
    final active = closeFuture;
    if (active != null) return active;
    final completer = Completer<void>();
    closeFuture = completer.future;
    unawaited(
      attemptDestroy()
          .then(completer.complete, onError: completer.completeError)
          .whenComplete(() {
        if (!closed) closeFuture = null;
      }),
    );
    return completer.future;
  };

  closeStream = () async {
    await closeNative();
    if (!controller.isClosed) await controller.close();
  };

  try {
    callable = NativeCallable<StateCallbackNative>.listener(
      (
        Pointer<CodexNativeContext> context,
        Pointer<CodexNativeSubscription> nativeSubscription,
        int eventStatus,
        Pointer<CodexNativeSnapshot> snapshot,
        int isTerminal,
        Pointer<Void> userData,
      ) {
        eventTail = eventTail.then((_) async {
          Object? value;
          Object? eventError;
          StackTrace? eventStack;
          Pointer<Pointer<CodexNativeSnapshot>>? slot;
          try {
            if (snapshot != nullptr) {
              slot = newHandleSlot<CodexNativeSnapshot>()..value = snapshot;
            }
            if (eventStatus != CodexStatus.ok.value) {
              throw CodexNativeException(
                eventStatus,
                'state subscription event failed',
              );
            }
            if (snapshot != nullptr) value = decode(snapshot);
          } catch (error, stack) {
            eventError = error;
            eventStack = stack;
          }
          if (slot != null) {
            try {
              await _destroyOwnedSlot(
                owner,
                slot,
                owner.api.snapshotDestroy,
                'codex_agent_snapshot_destroy',
              );
            } catch (error, stack) {
              eventError ??= error;
              eventStack ??= stack;
            }
          }
          if (!deliveryClosed && !controller.isClosed) {
            if (eventError != null) {
              controller.addError(eventError, eventStack);
            } else if (snapshot != nullptr) {
              controller.add(value as T);
            }
          }
        });
        if (isTerminal != 0) {
          unawaited(eventTail.then((_) => closeStream()).catchError(
            (Object error, StackTrace stack) {
              if (!controller.isClosed) controller.addError(error, stack);
            },
          ));
        }
      },
    );
  } catch (_) {
    nativeMemory.free(subscription);
    rethrow;
  }

  try {
    controller = StreamController<T>.broadcast(
      sync: true,
      onListen: () {
        var ownerRegistered = false;
        var scopeRegistered = false;
        try {
          ownerRegistered = owner.registerSubscription(closeStream);
          if (!ownerRegistered) {
            throw const CodexClosedException('the owning CodexHost is closing');
          }
          scopeRegistered = scope.register(closeStream);
          if (!scopeRegistered) {
            throw const CodexClosedException('the state owner is closing');
          }
          checkStatus(
            subscribe(callable.nativeFunction, nullptr, subscription),
            'state subscription',
          );
        } catch (error, stack) {
          if (ownerRegistered && !scopeRegistered) {
            owner.unregisterSubscription(closeStream);
          }
          controller.addError(error, stack);
          unawaited(closeStream());
        }
      },
      onCancel: closeNative,
    );
  } catch (_) {
    callable.close();
    nativeMemory.free(subscription);
    rethrow;
  }
  return controller.stream;
}

final class CodexHost {
  CodexHost._(
    this._owner,
    Pointer<Pointer<CodexNativeHost>> hostSlot,
  ) : _closeCoordinator = _HostCloseCoordinator(_owner, hostSlot) {
    _lifetime = _HostLifetime(_closeCoordinator);
    state = CodexObservableState<CodexHostState>(
      current: _readCurrentState,
      changes: _createStateStream,
    );
  }

  final _NativeContextOwner _owner;
  final _HostCloseCoordinator _closeCoordinator;
  late final _HostLifetime _lifetime;
  final _SubscriptionScope _subscriptions = _SubscriptionScope();
  late final CodexObservableState<CodexHostState> state;
  CodexAgent? _readyAgent;

  static Future<CodexHost> create({
    required String bundleDirectory,
    required String dataDirectory,
    required CodexClientInfo clientInfo,
    String? libraryPath,
  }) async {
    final path = await resolveLibraryPath(libraryPath);
    final owner = _NativeContextOwner(NativeApi.load(path));
    Pointer<Pointer<CodexNativeHost>>? host;
    Pointer<CodexHostOptionsStruct>? options;
    NativeString? bundle;
    NativeString? data;
    NativeString? name;
    NativeString? title;
    NativeString? version;
    try {
      host = newHandleSlot<CodexNativeHost>();
      bundle = NativeString(bundleDirectory);
      data = NativeString(dataDirectory);
      name = NativeString(clientInfo.name);
      title = NativeString(clientInfo.title);
      version = NativeString(clientInfo.version);
      options = nativeMemory.allocate<CodexHostOptionsStruct>(
        sizeOf<CodexHostOptionsStruct>(),
      );
      options.ref
        ..structSize = sizeOf<CodexHostOptionsStruct>()
        ..bundleDirectory.data = bundle.view.ref.data
        ..bundleDirectory.size = bundle.view.ref.size
        ..dataDirectory.data = data.view.ref.data
        ..dataDirectory.size = data.view.ref.size
        ..clientInfo.structSize = sizeOf<CodexClientInfoStruct>()
        ..clientInfo.name.data = name.view.ref.data
        ..clientInfo.name.size = name.view.ref.size
        ..clientInfo.title.data = title.view.ref.data
        ..clientInfo.title.size = title.view.ref.size
        ..clientInfo.version.data = version.view.ref.data
        ..clientInfo.version.size = version.view.ref.size;
      checkStatus(
        owner.api.hostCreate(owner.require(), options, host),
        'codex_agent_host_create',
      );
      final result = CodexHost._(owner, host);
      return result;
    } catch (error, stack) {
      try {
        if (host != null) {
          if (host.value != nullptr) {
            await _destroyOwnedSlot(
              owner,
              host,
              owner.api.hostRelease,
              'codex_agent_host_release',
            );
          } else {
            nativeMemory.free(host);
          }
        }
      } finally {
        await owner.close();
      }
      Error.throwWithStackTrace(error, stack);
    } finally {
      bundle?.close();
      data?.close();
      name?.close();
      title?.close();
      version?.close();
      if (options != null) nativeMemory.free(options);
    }
  }

  Pointer<CodexNativeHost> _require() {
    _owner.require();
    if (_closeCoordinator.host.released ||
        _closeCoordinator.host.slot.value == nullptr) {
      throw const CodexClosedException('CodexHost is closed');
    }
    return _closeCoordinator.host.slot.value;
  }

  Future<void> start({CodexCancellation? cancellation}) => _runOperation<void>(
        _owner,
        (callback, userData, out) => _owner.api.hostStart(
          _owner.require(),
          _require(),
          callback,
          userData,
          out,
        ),
        (_) {},
        cancellation: cancellation,
        pin: this,
      );

  Future<void> selectWorkspace(
    String path, {
    CodexCancellation? cancellation,
  }) async {
    final value = NativeString(path);
    Pointer<CodexPathWorkspaceSelectionStruct>? selection;
    try {
      selection = nativeMemory.allocate<CodexPathWorkspaceSelectionStruct>(
        sizeOf<CodexPathWorkspaceSelectionStruct>(),
      );
      selection.ref
        ..structSize = sizeOf<CodexPathWorkspaceSelectionStruct>()
        ..path.data = value.view.ref.data
        ..path.size = value.view.ref.size;
      await _runOperation<void>(
        _owner,
        (callback, userData, out) => _owner.api.hostSelectWorkspace(
          _owner.require(),
          _require(),
          selection!,
          callback,
          userData,
          out,
        ),
        (_) {},
        cancellation: cancellation,
        pin: this,
      );
    } finally {
      value.close();
      if (selection != null) nativeMemory.free(selection);
    }
  }

  Future<CodexHostState> get currentState => state.current;
  Stream<CodexHostState> get states => state.changes;

  Future<CodexHostState> _readCurrentState() => _currentState(
        _owner,
        _require(),
        _owner.api.hostStateGet,
        _decodeState,
      );

  Stream<CodexHostState> _createStateStream() => _stateStream(
        _owner,
        (callback, userData, out) => _owner.api.hostStateSubscribe(
          _owner.require(),
          _require(),
          callback,
          userData,
          out,
        ),
        _decodeState,
        this,
        _subscriptions,
      );

  CodexHostState _decodeState(Pointer<CodexNativeSnapshot> snapshot) {
    final scalar = nativeMemory.allocate<Int32>(sizeOf<Int32>());
    try {
      checkStatus(
        _owner.api.hostStateKind(_owner.require(), snapshot, scalar),
        'codex_agent_host_state_kind',
      );
      final kind = CodexHostStateKind.fromValue(scalar.value);
      CodexWorkspace? workspace;
      checkStatus(
        _owner.api.hostStateHasWorkspace(_owner.require(), snapshot, scalar),
        'codex_agent_host_state_has_workspace',
      );
      if (scalar.value != 0) {
        workspace = CodexWorkspace(
          path: copyString(
            _owner.api.hostStateWorkspacePath,
            _owner.require(),
            snapshot,
          ),
          displayName: _copyOptionalSnapshotString(
            _owner,
            _owner.api.hostStateWorkspaceDisplayName,
            snapshot,
          ),
        );
      }
      CodexWorkspaceRequirement? requirement;
      if (kind == CodexHostStateKind.workspaceRequired) {
        checkStatus(
          _owner.api
              .hostStateRequirementReason(_owner.require(), snapshot, scalar),
          'codex_agent_host_state_requirement_reason',
        );
        requirement = CodexWorkspaceRequirement(
          reason: CodexWorkspaceSelectionReason.fromValue(scalar.value),
          message: copyString(
            _owner.api.hostStateRequirementMessage,
            _owner.require(),
            snapshot,
          ),
        );
      }
      CodexFailure? failure;
      if (kind == CodexHostStateKind.failed) {
        failure = _stateFailure(_owner, _owner.api.hostStateFailure, snapshot);
      }
      CodexAgent? agent;
      if (kind == CodexHostStateKind.ready) {
        final slot = newHandleSlot<CodexNativeAgent>();
        var transferred = false;
        try {
          checkStatus(
            _owner.api
                .hostStateAgent(_owner.require(), _require(), snapshot, slot),
            'codex_agent_host_state_agent',
          );
          if (slot.value == nullptr) {
            throw const CodexException(
                'codex_agent_host_state_agent returned an absent owned value');
          }
          final readyAgent = _readyAgent;
          if (readyAgent == null) {
            agent = CodexAgent._(_owner, _lifetime, slot);
            _readyAgent = agent;
            transferred = true;
          } else {
            transferred = true;
            _releaseOwnedSlotOrDefer(
              _owner,
              slot,
              _owner.api.agentRelease,
              'codex_agent_agent_release',
            );
            agent = readyAgent;
          }
        } finally {
          if (!transferred) {
            if (slot.value != nullptr) {
              _releaseOwnedSlotOrDefer(
                _owner,
                slot,
                _owner.api.agentRelease,
                'codex_agent_agent_release',
              );
            } else {
              nativeMemory.free(slot);
            }
          }
        }
      }
      return kind == CodexHostStateKind.ready
          ? CodexReadyHostState(
              agent!,
              workspace: workspace,
            )
          : CodexHostState(
              kind: kind,
              workspace: workspace,
              workspaceRequirement: requirement,
              failure: failure,
            );
    } finally {
      nativeMemory.free(scalar);
    }
  }

  Future<void> close({CodexCancellation? cancellation}) async {
    await _closeCoordinator.close(cancellation: cancellation);
    _lifetime.detach();
  }
}

class CodexHostState {
  const CodexHostState({
    required this.kind,
    this.agent,
    this.workspace,
    this.workspaceRequirement,
    this.failure,
  });

  final CodexHostStateKind kind;
  final CodexAgent? agent;
  final CodexWorkspace? workspace;
  final CodexWorkspaceRequirement? workspaceRequirement;
  final CodexFailure? failure;
}

final class CodexReadyHostState extends CodexHostState {
  CodexReadyHostState(
    CodexAgent agent, {
    super.workspace,
  }) : super(
          kind: CodexHostStateKind.ready,
          agent: agent,
        );

  @override
  CodexAgent get agent => super.agent!;
}

final class CodexAgent implements Finalizable {
  CodexAgent._(
    _NativeContextOwner owner,
    _HostLifetime lifetime,
    Pointer<Pointer<CodexNativeAgent>> slot,
  ) : _native = _OwnedNative<CodexNativeAgent>(
          owner,
          lifetime,
          slot,
          owner.api.agentRelease,
        ) {
    _finalizer.attach(this, _native.ticket, detach: this);
  }

  final _OwnedNative<CodexNativeAgent> _native;

  static final Finalizer<_ReleaseTicket<CodexNativeAgent>> _finalizer =
      Finalizer<_ReleaseTicket<CodexNativeAgent>>(
          (ticket) => ticket.finalize('codex_agent_agent_release'));

  CodexAuthentication? _authentication;
  CodexConnectors? _connectors;
  CodexConversations? _conversations;
  CodexHooks? _hooks;
  CodexIntegrationAuthorization? _integrationAuthorization;
  CodexInteractions? _interactions;
  CodexMcpServers? _mcpServers;
  CodexModels? _models;
  CodexPlugins? _plugins;
  CodexSkills? _skills;
  CodexWorkspace? _workspace;

  T _requireOpenProjection<T>(T projection) {
    _native.requireHandle('CodexAgent');
    return projection;
  }

  CodexAuthentication get authentication =>
      _requireOpenProjection(_authentication ??= CodexAuthentication._(
        _native.owner,
        _native.lifetime,
        _acquireAgentServiceSlot(
          this,
          'codex_agent_agent_authentication',
          _leafApi(_native.owner).agentAuthentication,
        ),
      ));

  CodexConnectors get connectors =>
      _requireOpenProjection(_connectors ??= CodexConnectors._(
        _native.owner,
        _native.lifetime,
        _acquireAgentServiceSlot(
          this,
          'codex_agent_agent_connectors',
          _leafApi(_native.owner).agentConnectors,
        ),
      ));

  CodexConversations get conversations =>
      _requireOpenProjection(_conversations ??= _acquireConversations());

  CodexHooks get hooks => _requireOpenProjection(_hooks ??= CodexHooks._(
        _native.owner,
        _native.lifetime,
        _acquireAgentServiceSlot(
          this,
          'codex_agent_agent_hooks',
          _leafApi(_native.owner).agentHooks,
        ),
      ));

  CodexIntegrationAuthorization get integrationAuthorization =>
      _requireOpenProjection(
          _integrationAuthorization ??= CodexIntegrationAuthorization._(
        _native.owner,
        _native.lifetime,
        _acquireAgentServiceSlot(
          this,
          'codex_agent_agent_integration_authorization',
          _leafApi(_native.owner).agentIntegrationAuthorization,
        ),
      ));

  CodexInteractions get interactions =>
      _requireOpenProjection(_interactions ??= CodexInteractions._(
        _native.owner,
        _native.lifetime,
        _acquireAgentServiceSlot(
          this,
          'codex_agent_agent_interactions',
          _leafApi(_native.owner).agentInteractions,
        ),
      ));

  CodexMcpServers get mcpServers =>
      _requireOpenProjection(_mcpServers ??= CodexMcpServers._(
        _native.owner,
        _native.lifetime,
        _acquireAgentServiceSlot(
          this,
          'codex_agent_agent_mcp_servers',
          _leafApi(_native.owner).agentMcpServers,
        ),
      ));

  CodexModels get models => _requireOpenProjection(_models ??= CodexModels._(
        _native.owner,
        _native.lifetime,
        _acquireAgentServiceSlot(
          this,
          'codex_agent_agent_models',
          _leafApi(_native.owner).agentModels,
        ),
      ));

  CodexPlugins get plugins =>
      _requireOpenProjection(_plugins ??= CodexPlugins._(
        _native.owner,
        _native.lifetime,
        _acquireAgentServiceSlot(
          this,
          'codex_agent_agent_plugins',
          _leafApi(_native.owner).agentPlugins,
        ),
      ));

  CodexSkills get skills => _requireOpenProjection(_skills ??= CodexSkills._(
        _native.owner,
        _native.lifetime,
        _acquireAgentServiceSlot(
          this,
          'codex_agent_agent_skills',
          _leafApi(_native.owner).agentSkills,
        ),
      ));

  CodexWorkspace get workspace =>
      _requireOpenProjection(_workspace ??= _readWorkspace());

  CodexConversations _acquireConversations() {
    final slot = newHandleSlot<CodexNativeConversations>();
    var transferred = false;
    try {
      checkStatus(
        _native.owner.api.agentConversations(
          _native.owner.require(),
          _native.requireHandle('CodexAgent'),
          slot,
        ),
        'codex_agent_agent_conversations',
      );
      final result = CodexConversations._(
        _native.owner,
        _native.lifetime,
        slot,
      );
      transferred = true;
      return result;
    } finally {
      if (!transferred) {
        if (slot.value != nullptr) {
          _releaseOwnedSlotOrDefer(
            _native.owner,
            slot,
            _native.owner.api.conversationsRelease,
            'codex_agent_conversations_release',
          );
        } else {
          nativeMemory.free(slot);
        }
      }
    }
  }

  CodexWorkspace _readWorkspace() {
    final owner = _native.owner;
    final slot = newHandleSlot<CodexNativeWorkspace>();
    try {
      checkStatus(
        owner.api.agentWorkspace(
          owner.require(),
          _native.requireHandle('CodexAgent'),
          slot,
        ),
        'codex_agent_agent_workspace',
      );
      if (slot.value == nullptr) {
        throw const CodexException(
            'codex_agent_agent_workspace returned an absent owned value');
      }
      return CodexWorkspace(
        path: copyString(owner.api.workspacePath, owner.require(), slot.value),
        displayName: copyString(
          owner.api.workspaceDisplayName,
          owner.require(),
          slot.value,
        ),
      );
    } finally {
      if (slot.value != nullptr) {
        checkStatus(
          owner.api.workspaceDestroy(owner.require(), slot),
          'codex_agent_workspace_destroy',
        );
      }
      nativeMemory.free(slot);
    }
  }

  Future<void> close() async {
    await _native.ticket.close('codex_agent_agent_release');
    _finalizer.detach(this);
  }
}

final class CodexConversations implements Finalizable {
  CodexConversations._(
    _NativeContextOwner owner,
    _HostLifetime lifetime,
    Pointer<Pointer<CodexNativeConversations>> slot,
  ) : _native = _OwnedNative<CodexNativeConversations>(
          owner,
          lifetime,
          slot,
          owner.api.conversationsRelease,
        ) {
    activeState = CodexObservableState<CodexConversation?>(
      current: _readCurrentActive,
      changes: _createActiveStream,
    );
    _finalizer.attach(this, _native.ticket, detach: this);
  }

  final _OwnedNative<CodexNativeConversations> _native;
  final _SubscriptionScope _subscriptions = _SubscriptionScope();
  late final CodexObservableState<CodexConversation?> activeState;

  static final Finalizer<_ReleaseTicket<CodexNativeConversations>> _finalizer =
      Finalizer<_ReleaseTicket<CodexNativeConversations>>(
          (ticket) => ticket.finalize('codex_agent_conversations_release'));

  Future<CodexConversation?> get currentActive => activeState.current;
  Stream<CodexConversation?> get active => activeState.changes;

  Future<CodexConversation?> _readCurrentActive() => _currentState(
        _native.owner,
        _native.requireHandle('CodexConversations'),
        _native.owner.api.conversationsActiveGet,
        _decodeActive,
      );

  Stream<CodexConversation?> _createActiveStream() => _stateStream(
        _native.owner,
        (callback, userData, out) =>
            _native.owner.api.conversationsActiveSubscribe(
          _native.owner.require(),
          _native.requireHandle('CodexConversations'),
          callback,
          userData,
          out,
        ),
        _decodeActive,
        this,
        _subscriptions,
      );

  CodexConversation? _decodeActive(Pointer<CodexNativeSnapshot> snapshot) {
    final slot = newHandleSlot<CodexNativeConversation>();
    var transferred = false;
    try {
      final status = _native.owner.api.activeConversation(
        _native.owner.require(),
        _native.requireHandle('CodexConversations'),
        snapshot,
        slot,
      );
      if (status == CodexStatus.notReady.value) return null;
      checkStatus(status, 'codex_agent_active_conversation');
      final result = CodexConversation._(
        _native.owner,
        _native.lifetime,
        slot,
      );
      transferred = true;
      return result;
    } finally {
      if (!transferred) {
        if (slot.value != nullptr) {
          _releaseOwnedSlotOrDefer(
            _native.owner,
            slot,
            _native.owner.api.conversationRelease,
            'codex_agent_conversation_release',
          );
        } else {
          nativeMemory.free(slot);
        }
      }
    }
  }

  Future<List<CodexConversationSummary>> list({
    CodexCancellation? cancellation,
  }) =>
      _runOperation<List<CodexConversationSummary>>(
        _native.owner,
        (callback, userData, out) => _native.owner.api.conversationsList(
          _native.owner.require(),
          _native.requireHandle('CodexConversations'),
          callback,
          userData,
          out,
        ),
        _decodeSummaries,
        cancellation: cancellation,
        pin: this,
      );

  Future<CodexConversationSnapshot> read(
    CodexConversationId id, {
    CodexCancellation? cancellation,
  }) =>
      _withConversationId(
        id,
        (nativeId) => _runOperation<CodexConversationSnapshot>(
          _native.owner,
          (callback, userData, out) =>
              _native.owner.conversationApi.conversationsRead(
            _native.owner.require(),
            _native.requireHandle('CodexConversations'),
            nativeId,
            callback,
            userData,
            out,
          ),
          (operation) {
            final value = newHandleSlot<Void>();
            try {
              checkStatus(
                _native.owner.conversationApi.operationConversationValue(
                  _native.owner.require(),
                  operation.cast<Void>(),
                  value,
                ),
                'codex_agent_operation_conversation_value',
              );
              return readConversationValue(
                _native.owner.api,
                _native.owner.conversationApi,
                _native.owner.require(),
                value.value,
              );
            } finally {
              nativeMemory.free(value);
            }
          },
          cancellation: cancellation,
          pin: this,
        ),
      );

  Future<void> rename(
    CodexConversationId id,
    String name, {
    CodexCancellation? cancellation,
  }) =>
      _withConversationId(id, (nativeId) async {
        final nativeName = NativeString(name);
        try {
          await _runOperation<void>(
            _native.owner,
            (callback, userData, out) =>
                _native.owner.conversationApi.conversationsRename(
              _native.owner.require(),
              _native.requireHandle('CodexConversations'),
              nativeId,
              nativeName.view,
              callback,
              userData,
              out,
            ),
            (_) {},
            cancellation: cancellation,
            pin: this,
          );
        } finally {
          nativeName.close();
        }
      });

  Future<void> delete(
    CodexConversationId id, {
    CodexCancellation? cancellation,
  }) =>
      _withConversationId(
        id,
        (nativeId) => _runOperation<void>(
          _native.owner,
          (callback, userData, out) =>
              _native.owner.conversationApi.conversationsDelete(
            _native.owner.require(),
            _native.requireHandle('CodexConversations'),
            nativeId,
            callback,
            userData,
            out,
          ),
          (_) {},
          cancellation: cancellation,
          pin: this,
        ),
      );

  Future<T> _withConversationId<T>(
    CodexConversationId id,
    Future<T> Function(Pointer<Void>) body,
  ) async {
    final context = _native.owner.require();
    final nativeId = createConversationId(
      _native.owner.conversationApi,
      context,
      id,
    );
    try {
      return await body(nativeId);
    } finally {
      destroyConversationId(_native.owner.api, context, nativeId);
    }
  }

  List<CodexConversationSummary> _decodeSummaries(
    Pointer<CodexNativeOperation> operation,
  ) {
    final count = nativeMemory.allocate<Size>(sizeOf<Size>());
    try {
      checkStatus(
        _native.owner.api
            .operationSummariesCount(_native.owner.require(), operation, count),
        'codex_agent_operation_conversation_summaries_count',
      );
      return List<CodexConversationSummary>.generate(
        count.value,
        (index) => _decodeSummary(operation, index),
        growable: false,
      );
    } finally {
      nativeMemory.free(count);
    }
  }

  CodexConversationSummary _decodeSummary(
    Pointer<CodexNativeOperation> operation,
    int index,
  ) {
    Pointer<Pointer<CodexNativeConversationSummary>>? summary;
    Pointer<Pointer<CodexNativeConversationId>>? id;
    Pointer<Int64>? updated;
    try {
      summary = newHandleSlot<CodexNativeConversationSummary>();
      id = newHandleSlot<CodexNativeConversationId>();
      updated = nativeMemory.allocate<Int64>(sizeOf<Int64>());
      checkStatus(
        _native.owner.api.operationSummaryAt(
            _native.owner.require(), operation, index, summary),
        'codex_agent_operation_conversation_summary_at',
      );
      checkStatus(
        _native.owner.api
            .summaryConversationId(_native.owner.require(), summary.value, id),
        'codex_agent_conversation_summary_conversation_id',
      );
      checkStatus(
        _native.owner.api
            .summaryUpdated(_native.owner.require(), summary.value, updated),
        'codex_agent_conversation_summary_updated_at_epoch_seconds',
      );
      return CodexConversationSummary(
        conversationId: CodexConversationId(
          copyString(
            _native.owner.api.conversationIdValue,
            _native.owner.require(),
            id.value,
          ),
        ),
        title: copyString(
          _native.owner.api.summaryTitle,
          _native.owner.require(),
          summary.value,
        ),
        updatedAtEpochSeconds: updated.value,
      );
    } finally {
      if (updated != null) nativeMemory.free(updated);
      if (id != null) {
        if (id.value != nullptr) {
          _releaseOwnedSlotOrDefer(
            _native.owner,
            id,
            _native.owner.api.conversationIdDestroy,
            'codex_agent_conversation_id_destroy',
          );
        } else {
          nativeMemory.free(id);
        }
      }
      if (summary != null) {
        if (summary.value != nullptr) {
          _releaseOwnedSlotOrDefer(
            _native.owner,
            summary,
            _native.owner.api.summaryDestroy,
            'codex_agent_conversation_summary_destroy',
          );
        } else {
          nativeMemory.free(summary);
        }
      }
    }
  }

  Future<CodexConversation> open({
    CodexConversationOpenOptions options = const CodexConversationOpenOptions(),
    CodexCancellation? cancellation,
  }) async {
    NativeString? conversationId;
    NativeString? serviceTier;
    Pointer<CodexConversationOpenOptionsStruct>? nativeOptions;
    try {
      conversationId = options.conversationId == null
          ? NativeString.absent()
          : NativeString(options.conversationId!);
      serviceTier = options.serviceTier == null
          ? NativeString.absent()
          : NativeString(options.serviceTier!);
      nativeOptions = nativeMemory.allocate<CodexConversationOpenOptionsStruct>(
        sizeOf<CodexConversationOpenOptionsStruct>(),
      );
      nativeOptions.ref
        ..structSize = sizeOf<CodexConversationOpenOptionsStruct>()
        ..hasConversationId = options.conversationId == null ? 0 : 1
        ..conversationId.data = conversationId.view.ref.data
        ..conversationId.size = conversationId.view.ref.size
        ..hasApprovalPreset = options.approvalPreset == null ? 0 : 1
        ..approvalPreset = options.approvalPreset?.value ?? 0
        ..hasServiceTier = options.serviceTier == null ? 0 : 1
        ..serviceTier.data = serviceTier.view.ref.data
        ..serviceTier.size = serviceTier.view.ref.size;
      return await _runOperation<CodexConversation>(
        _native.owner,
        (callback, userData, out) => _native.owner.api.conversationsOpen(
          _native.owner.require(),
          _native.requireHandle('CodexConversations'),
          nativeOptions!,
          callback,
          userData,
          out,
        ),
        (operation) {
          final conversation = newHandleSlot<CodexNativeConversation>();
          var transferred = false;
          try {
            checkStatus(
              _native.owner.api.operationConversation(
                _native.owner.require(),
                _native.requireHandle('CodexConversations'),
                operation,
                conversation,
              ),
              'codex_agent_operation_conversation',
            );
            final result = CodexConversation._(
              _native.owner,
              _native.lifetime,
              conversation,
            );
            transferred = true;
            return result;
          } finally {
            if (!transferred) {
              if (conversation.value != nullptr) {
                _releaseOwnedSlotOrDefer(
                  _native.owner,
                  conversation,
                  _native.owner.api.conversationRelease,
                  'codex_agent_conversation_release',
                );
              } else {
                nativeMemory.free(conversation);
              }
            }
          }
        },
        cancellation: cancellation,
        pin: this,
      );
    } finally {
      conversationId?.close();
      serviceTier?.close();
      if (nativeOptions != null) nativeMemory.free(nativeOptions);
    }
  }

  Future<void> close() async {
    await _subscriptions.close();
    await _native.ticket.close('codex_agent_conversations_release');
    _finalizer.detach(this);
  }
}

final class CodexConversation implements Finalizable {
  CodexConversation._(
    _NativeContextOwner owner,
    _HostLifetime lifetime,
    Pointer<Pointer<CodexNativeConversation>> slot,
  ) : _native = _OwnedNative<CodexNativeConversation>(
          owner,
          lifetime,
          slot,
          owner.api.conversationRelease,
        ) {
    state = CodexObservableState<CodexConversationState>(
      current: _readCurrentState,
      changes: _createStateStream,
    );
    messagesState = CodexObservableState<List<CodexMessage>>(
      current: _readCurrentMessages,
      changes: _createMessagesStream,
    );
    activeTurnProgressState = CodexObservableState<CodexTurnProgress?>(
      current: _readCurrentActiveTurnProgress,
      changes: _createActiveTurnProgressStream,
    );
    canStartTurnState = _booleanState(
      _native.owner.api.conversationCanStartTurnGet,
      _native.owner.api.conversationCanStartTurnSubscribe,
    );
    canReloadState = _booleanState(
      _native.owner.api.conversationCanReloadGet,
      _native.owner.api.conversationCanReloadSubscribe,
    );
    canCancelTurnState = _booleanState(
      _native.owner.api.conversationCanCancelTurnGet,
      _native.owner.api.conversationCanCancelTurnSubscribe,
    );
    canRunShellCommandState = _booleanState(
      _native.owner.api.conversationCanRunShellGet,
      _native.owner.api.conversationCanRunShellSubscribe,
    );
    isTurnActiveState = _booleanState(
      _native.owner.api.conversationIsTurnActiveGet,
      _native.owner.api.conversationIsTurnActiveSubscribe,
    );
    _finalizer.attach(this, _native.ticket, detach: this);
  }

  final _OwnedNative<CodexNativeConversation> _native;
  final _SubscriptionScope _subscriptions = _SubscriptionScope();
  late final CodexObservableState<CodexConversationState> state;
  late final CodexObservableState<List<CodexMessage>> messagesState;
  late final CodexObservableState<CodexTurnProgress?> activeTurnProgressState;
  late final CodexObservableState<bool> canStartTurnState;
  late final CodexObservableState<bool> canReloadState;
  late final CodexObservableState<bool> canCancelTurnState;
  late final CodexObservableState<bool> canRunShellCommandState;
  late final CodexObservableState<bool> isTurnActiveState;

  static final Finalizer<_ReleaseTicket<CodexNativeConversation>> _finalizer =
      Finalizer<_ReleaseTicket<CodexNativeConversation>>(
          (ticket) => ticket.finalize('codex_agent_conversation_release'));

  Future<bool> isSame(CodexConversation other) async {
    final result = nativeMemory.allocate<Int32>(sizeOf<Int32>());
    try {
      checkStatus(
        _native.owner.api.conversationSame(
          _native.owner.require(),
          _native.requireHandle('CodexConversation'),
          other._native.requireHandle('CodexConversation'),
          result,
        ),
        'codex_agent_conversation_is_same',
      );
      return result.value != 0;
    } finally {
      nativeMemory.free(result);
    }
  }

  Future<void> send(
    String prompt, {
    CodexCancellation? cancellation,
  }) =>
      _stringOperation(
          _native.owner.api.conversationSend, prompt, cancellation);

  Future<void> sendRequest(
    CodexTurnRequest request, {
    CodexCancellation? cancellation,
  }) async {
    final context = _native.owner.require();
    final nativeRequest = createTurnRequest(
      _native.owner.conversationApi,
      context,
      request,
    );
    try {
      await _runOperation<void>(
        _native.owner,
        (callback, userData, out) =>
            _native.owner.conversationApi.conversationSendRequest(
          context,
          _native.requireHandle('CodexConversation'),
          nativeRequest,
          callback,
          userData,
          out,
        ),
        (_) {},
        cancellation: cancellation,
        pin: this,
      );
    } finally {
      destroyTurnRequest(_native.owner.conversationApi, context, nativeRequest);
    }
  }

  Future<void> runShellCommand(
    String command, {
    CodexCancellation? cancellation,
  }) =>
      _stringOperation(
          _native.owner.api.conversationShell, command, cancellation);

  Future<void> _stringOperation(
    CodexNativeConversationStringOperationDart operation,
    String value,
    CodexCancellation? cancellation,
  ) async {
    final string = NativeString(value);
    try {
      await _runOperation<void>(
        _native.owner,
        (callback, userData, out) => operation(
          _native.owner.require(),
          _native.requireHandle('CodexConversation'),
          string.view,
          callback,
          userData,
          out,
        ),
        (_) {},
        cancellation: cancellation,
        pin: this,
      );
    } finally {
      string.close();
    }
  }

  Future<void> reload({CodexCancellation? cancellation}) =>
      _voidOperation(_native.owner.api.conversationReload, cancellation);

  Future<void> cancelTurn({CodexCancellation? cancellation}) =>
      _voidOperation(_native.owner.api.conversationCancelTurn, cancellation);

  Future<void> closeConversation({CodexCancellation? cancellation}) =>
      _voidOperation(_native.owner.api.conversationClose, cancellation);

  Future<void> _voidOperation(
    CodexNativeConversationOperationDart operation,
    CodexCancellation? cancellation,
  ) =>
      _runOperation<void>(
        _native.owner,
        (callback, userData, out) => operation(
          _native.owner.require(),
          _native.requireHandle('CodexConversation'),
          callback,
          userData,
          out,
        ),
        (_) {},
        cancellation: cancellation,
        pin: this,
      );

  Future<CodexConversationState> get currentState => state.current;
  Stream<CodexConversationState> get states => state.changes;
  Future<List<CodexMessage>> get currentMessages => messagesState.current;
  Stream<List<CodexMessage>> get messages => messagesState.changes;
  Future<CodexTurnProgress?> get currentActiveTurnProgress =>
      activeTurnProgressState.current;
  Stream<CodexTurnProgress?> get activeTurnProgress =>
      activeTurnProgressState.changes;

  Future<CodexConversationState> _readCurrentState() => _currentState(
        _native.owner,
        _native.requireHandle('CodexConversation'),
        _native.owner.api.conversationStateGet,
        _decodeState,
      );

  Stream<CodexConversationState> _createStateStream() => _stateStream(
        _native.owner,
        (callback, userData, out) =>
            _native.owner.api.conversationStateSubscribe(
          _native.owner.require(),
          _native.requireHandle('CodexConversation'),
          callback,
          userData,
          out,
        ),
        _decodeState,
        this,
        _subscriptions,
      );

  Future<List<CodexMessage>> _readCurrentMessages() => _currentState(
        _native.owner,
        _native.requireHandle('CodexConversation'),
        _native.owner.conversationApi.currentMessagesGet,
        (snapshot) => readCurrentMessages(
          _native.owner.conversationApi,
          _native.owner.require(),
          snapshot,
        ),
      );

  Stream<List<CodexMessage>> _createMessagesStream() => _stateStream(
        _native.owner,
        (callback, userData, out) =>
            _native.owner.conversationApi.currentMessagesSubscribe(
          _native.owner.require(),
          _native.requireHandle('CodexConversation'),
          callback,
          userData,
          out,
        ),
        (snapshot) => readCurrentMessages(
          _native.owner.conversationApi,
          _native.owner.require(),
          snapshot,
        ),
        this,
        _subscriptions,
      );

  Future<CodexTurnProgress?> _readCurrentActiveTurnProgress() => _currentState(
        _native.owner,
        _native.requireHandle('CodexConversation'),
        _native.owner.conversationApi.activeProgressGet,
        (snapshot) => readActiveTurnProgress(
          _native.owner.conversationApi,
          _native.owner.require(),
          snapshot,
        ),
      );

  Stream<CodexTurnProgress?> _createActiveTurnProgressStream() => _stateStream(
        _native.owner,
        (callback, userData, out) =>
            _native.owner.conversationApi.activeProgressSubscribe(
          _native.owner.require(),
          _native.requireHandle('CodexConversation'),
          callback,
          userData,
          out,
        ),
        (snapshot) => readActiveTurnProgress(
          _native.owner.conversationApi,
          _native.owner.require(),
          snapshot,
        ),
        this,
        _subscriptions,
      );

  CodexConversationState _decodeState(Pointer<CodexNativeSnapshot> snapshot) {
    final status = nativeMemory.allocate<Int32>(sizeOf<Int32>());
    try {
      checkStatus(
        _native.owner.api
            .conversationStateStatus(_native.owner.require(), snapshot, status),
        'codex_agent_conversation_state_status',
      );
      final value = CodexConversationStatus.fromValue(status.value);
      return CodexConversationState(
        status: value,
        failure: value == CodexConversationStatus.failed
            ? _stateFailure(_native.owner,
                _native.owner.api.conversationStateFailure, snapshot)
            : null,
      );
    } finally {
      nativeMemory.free(status);
    }
  }

  Future<bool> get canStartTurn => canStartTurnState.current;
  Stream<bool> get canStartTurnChanges => canStartTurnState.changes;
  Future<bool> get canReload => canReloadState.current;
  Stream<bool> get canReloadChanges => canReloadState.changes;
  Future<bool> get canCancelTurn => canCancelTurnState.current;
  Stream<bool> get canCancelTurnChanges => canCancelTurnState.changes;
  Future<bool> get canRunShellCommand => canRunShellCommandState.current;
  Stream<bool> get canRunShellCommandChanges => canRunShellCommandState.changes;
  Future<bool> get isTurnActive => isTurnActiveState.current;
  Stream<bool> get isTurnActiveChanges => isTurnActiveState.changes;

  CodexObservableState<bool> _booleanState(
    CodexGetSnapshotDart<CodexNativeConversation> get,
    CodexSubscribeDart<CodexNativeConversation> subscribe,
  ) =>
      CodexObservableState<bool>(
        current: () => _currentBoolean(get),
        changes: () => _booleanStream(subscribe),
      );

  Future<bool> _currentBoolean(
          CodexGetSnapshotDart<CodexNativeConversation> get) =>
      _currentState(
        _native.owner,
        _native.requireHandle('CodexConversation'),
        get,
        _decodeBoolean,
      );

  Stream<bool> _booleanStream(
    CodexSubscribeDart<CodexNativeConversation> subscribe,
  ) =>
      _stateStream(
        _native.owner,
        (callback, userData, out) => subscribe(
          _native.owner.require(),
          _native.requireHandle('CodexConversation'),
          callback,
          userData,
          out,
        ),
        _decodeBoolean,
        this,
        _subscriptions,
      );

  bool _decodeBoolean(Pointer<CodexNativeSnapshot> snapshot) {
    final value = nativeMemory.allocate<Int32>(sizeOf<Int32>());
    try {
      checkStatus(
        _native.owner.api
            .stateBooleanValue(_native.owner.require(), snapshot, value),
        'codex_agent_state_boolean_value',
      );
      return value.value != 0;
    } finally {
      nativeMemory.free(value);
    }
  }

  Future<void> dispose() async {
    await _subscriptions.close();
    await _native.ticket.close('codex_agent_conversation_release');
    _finalizer.detach(this);
  }
}

final class CodexConversationState {
  CodexConversationState({
    this.status = CodexConversationStatus.newConversation,
    this.conversationId,
    this.conversation,
    CodexTurnProgress? turnProgress,
    this.model,
    this.effort,
    this.serviceTier,
    this.failure,
  }) : turnProgress = turnProgress ?? CodexTurnProgress();
  final CodexConversationStatus status;
  final CodexConversationId? conversationId;
  final CodexConversationSnapshot? conversation;
  final CodexTurnProgress turnProgress;
  final String? model;
  final String? effort;
  final String? serviceTier;
  final CodexFailure? failure;
  bool get canStartTurn =>
      conversationId != null &&
      (status == CodexConversationStatus.ready ||
          status == CodexConversationStatus.failed &&
              failure?.isRecoverable == true);
  bool get canReload =>
      conversationId != null &&
      (status == CodexConversationStatus.ready ||
          status == CodexConversationStatus.failed);
  bool get canCancelTurn =>
      status == CodexConversationStatus.startingTurn ||
      status == CodexConversationStatus.runningTurn;
}

CodexFailure? _stateFailure(
  _NativeContextOwner owner,
  CodexStateFailureDart getter,
  Pointer<CodexNativeSnapshot> snapshot,
) {
  final failure = newHandleSlot<CodexNativeFailure>();
  var transferred = false;
  try {
    final status = getter(owner.require(), snapshot, failure);
    if (status == CodexStatus.notReady.value) return null;
    checkStatus(status, 'state failure');
    transferred = true;
    return _decodeFailure(owner, failure);
  } finally {
    if (!transferred) {
      if (failure.value != nullptr) {
        _releaseOwnedSlotOrDefer(
          owner,
          failure,
          owner.api.failureRelease,
          'codex_agent_failure_release',
        );
      } else {
        nativeMemory.free(failure);
      }
    }
  }
}

String? _copyOptionalSnapshotString(
  _NativeContextOwner owner,
  CodexCopySnapshotStringDart copier,
  Pointer<CodexNativeSnapshot> snapshot,
) {
  final required = nativeMemory.allocate<Size>(sizeOf<Size>());
  try {
    final first = copier(owner.require(), snapshot, nullptr, 0, required);
    if (first == CodexStatus.notReady.value) return null;
    checkStatus(
      first,
      'optional string size query',
      allow: const {CodexStatus.bufferTooSmall},
    );
    if (required.value == 0) return '';
    final buffer = nativeMemory.allocate<Uint8>(required.value);
    try {
      checkStatus(
        copier(owner.require(), snapshot, buffer, required.value, required),
        'optional string copy',
      );
      return utf8.decode(
        buffer.asTypedList(required.value),
        allowMalformed: false,
      );
    } finally {
      nativeMemory.free(buffer);
    }
  } finally {
    nativeMemory.free(required);
  }
}
