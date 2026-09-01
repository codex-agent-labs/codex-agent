import 'dart:convert';
import 'dart:ffi';
import 'dart:io';
import 'dart:isolate';
import 'dart:typed_data';

import 'errors.dart';
import 'runtime_compatibility.dart';

const int requiredAbiVersion = (1 << 24) | (13 << 16);

final class CodexNativeContext extends Opaque {}

final class CodexNativeHost extends Opaque {}

final class CodexNativeAgent extends Opaque {}

final class CodexNativeWorkspace extends Opaque {}

final class CodexNativeConversations extends Opaque {}

final class CodexNativeConversation extends Opaque {}

final class CodexNativeOperation extends Opaque {}

final class CodexNativeSubscription extends Opaque {}

final class CodexNativeSnapshot extends Opaque {}

final class CodexNativeFailure extends Opaque {}

final class CodexNativeConversationSummary extends Opaque {}

final class CodexNativeConversationId extends Opaque {}

final class CodexStringView extends Struct {
  external Pointer<Uint8> data;

  @Size()
  external int size;
}

final class CodexClientInfoStruct extends Struct {
  @Uint32()
  external int structSize;

  external CodexStringView name;
  external CodexStringView title;
  external CodexStringView version;
}

final class CodexHostOptionsStruct extends Struct {
  @Uint32()
  external int structSize;

  external CodexStringView bundleDirectory;
  external CodexStringView dataDirectory;
  external CodexClientInfoStruct clientInfo;
}

final class CodexPathWorkspaceSelectionStruct extends Struct {
  @Uint32()
  external int structSize;

  external CodexStringView path;
}

final class CodexConversationOpenOptionsStruct extends Struct {
  @Uint32()
  external int structSize;

  @Int32()
  external int hasConversationId;
  external CodexStringView conversationId;

  @Int32()
  external int hasApprovalPreset;

  @Int32()
  external int approvalPreset;

  @Int32()
  external int hasServiceTier;
  external CodexStringView serviceTier;
}

typedef OperationCallbackNative = Void Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
  Pointer<Void>,
);
typedef StateCallbackNative = Void Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeSubscription>,
  Int32,
  Pointer<CodexNativeSnapshot>,
  Int32,
  Pointer<Void>,
);

typedef CodexAbiVersionNative = Uint32 Function();
typedef CodexAbiVersionDart = int Function();
typedef CodexAbiCompatibleNative = Int32 Function(Uint32);
typedef CodexAbiCompatibleDart = int Function(int);
typedef CodexRuntimeIdentityNative = Int32 Function(
  Pointer<Uint8>,
  Pointer<Size>,
);
typedef CodexRuntimeIdentityDart = int Function(Pointer<Uint8>, Pointer<Size>);

typedef _OpenNative = Int32 Function(Pointer<Uint8>, Int32);
typedef _OpenDart = int Function(Pointer<Uint8>, int);
typedef _CloseNative = Int32 Function(Int32);
typedef _CloseDart = int Function(int);
typedef _SeekNative = Int64 Function(Int32, Int64, Int32);
typedef _SeekDart = int Function(int, int, int);
typedef _FstatNative = Int32 Function(Int32, Pointer<Uint8>);
typedef _FstatDart = int Function(int, Pointer<Uint8>);
typedef _StatNative = Int32 Function(Pointer<Uint8>, Pointer<Uint8>);
typedef _StatDart = int Function(Pointer<Uint8>, Pointer<Uint8>);
typedef _CreateFileNative = IntPtr Function(
  Pointer<Uint16>,
  Uint32,
  Uint32,
  Pointer<Void>,
  Uint32,
  Uint32,
  IntPtr,
);
typedef _CreateFileDart = int Function(
  Pointer<Uint16>,
  int,
  int,
  Pointer<Void>,
  int,
  int,
  int,
);
typedef _CloseHandleNative = Int32 Function(IntPtr);
typedef _CloseHandleDart = int Function(int);

typedef CodexCreateContextNative = Int32 Function(
  Pointer<Pointer<CodexNativeContext>>,
);
typedef CodexCreateContextDart = int Function(
  Pointer<Pointer<CodexNativeContext>>,
);
typedef CodexDestroyContextNative = Int32 Function(
  Pointer<Pointer<CodexNativeContext>>,
);
typedef CodexDestroyContextDart = int Function(
  Pointer<Pointer<CodexNativeContext>>,
);

typedef CodexCreateHostNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexHostOptionsStruct>,
  Pointer<Pointer<CodexNativeHost>>,
);
typedef CodexCreateHostDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexHostOptionsStruct>,
  Pointer<Pointer<CodexNativeHost>>,
);
typedef CodexReleaseHostNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Pointer<CodexNativeHost>>,
);
typedef CodexReleaseHostDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Pointer<CodexNativeHost>>,
);
typedef CodexNativeHostOperationNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeHost>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef CodexNativeHostOperationDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeHost>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef CodexNativeHostSelectWorkspaceNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeHost>,
  Pointer<CodexPathWorkspaceSelectionStruct>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef CodexNativeHostSelectWorkspaceDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeHost>,
  Pointer<CodexPathWorkspaceSelectionStruct>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);

typedef CodexGetSnapshotNative<T extends NativeType> = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<T>,
  Pointer<Pointer<CodexNativeSnapshot>>,
);
typedef CodexGetSnapshotDart<T extends NativeType> = int Function(
  Pointer<CodexNativeContext>,
  Pointer<T>,
  Pointer<Pointer<CodexNativeSnapshot>>,
);
typedef CodexSubscribeNative<T extends NativeType> = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<T>,
  Pointer<NativeFunction<StateCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeSubscription>>,
);
typedef CodexSubscribeDart<T extends NativeType> = int Function(
  Pointer<CodexNativeContext>,
  Pointer<T>,
  Pointer<NativeFunction<StateCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeSubscription>>,
);

typedef CodexReleaseHandleNative<T extends NativeType> = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Pointer<T>>,
);
typedef CodexReleaseHandleDart<T extends NativeType> = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Pointer<T>>,
);
typedef CodexNativeAgentConversationsNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeAgent>,
  Pointer<Pointer<CodexNativeConversations>>,
);
typedef CodexNativeAgentConversationsDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeAgent>,
  Pointer<Pointer<CodexNativeConversations>>,
);
typedef CodexNativeAgentWorkspaceNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeAgent>,
  Pointer<Pointer<CodexNativeWorkspace>>,
);
typedef CodexNativeAgentWorkspaceDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeAgent>,
  Pointer<Pointer<CodexNativeWorkspace>>,
);
typedef CodexCopyWorkspaceStringNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeWorkspace>,
  Pointer<Uint8>,
  Size,
  Pointer<Size>,
);
typedef CodexCopyWorkspaceStringDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeWorkspace>,
  Pointer<Uint8>,
  int,
  Pointer<Size>,
);
typedef CodexNativeConversationsOperationNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversations>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef CodexNativeConversationsOperationDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversations>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef CodexNativeConversationsOpenNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversations>,
  Pointer<CodexConversationOpenOptionsStruct>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef CodexNativeConversationsOpenDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversations>,
  Pointer<CodexConversationOpenOptionsStruct>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef CodexNativeConversationStringOperationNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversation>,
  Pointer<CodexStringView>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef CodexNativeConversationStringOperationDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversation>,
  Pointer<CodexStringView>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef CodexNativeConversationOperationNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversation>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef CodexNativeConversationOperationDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversation>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef CodexNativeConversationSameNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversation>,
  Pointer<CodexNativeConversation>,
  Pointer<Int32>,
);
typedef CodexNativeConversationSameDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversation>,
  Pointer<CodexNativeConversation>,
  Pointer<Int32>,
);

typedef CodexCancelOperationNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
);
typedef CodexCancelOperationDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
);
typedef CodexNativeOperationResultNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
  Pointer<Int32>,
);
typedef CodexNativeOperationResultDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
  Pointer<Int32>,
);
typedef CodexNativeOperationConversationNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversations>,
  Pointer<CodexNativeOperation>,
  Pointer<Pointer<CodexNativeConversation>>,
);
typedef CodexNativeOperationConversationDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversations>,
  Pointer<CodexNativeOperation>,
  Pointer<Pointer<CodexNativeConversation>>,
);
typedef CodexNativeOperationFailureNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
  Pointer<Pointer<CodexNativeFailure>>,
);
typedef CodexNativeOperationFailureDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
  Pointer<Pointer<CodexNativeFailure>>,
);
typedef CodexNativeOperationCountNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
  Pointer<Size>,
);
typedef CodexNativeOperationCountDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
  Pointer<Size>,
);
typedef CodexNativeOperationSummaryAtNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
  Size,
  Pointer<Pointer<CodexNativeConversationSummary>>,
);
typedef CodexNativeOperationSummaryAtDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
  int,
  Pointer<Pointer<CodexNativeConversationSummary>>,
);

typedef CodexStateIntNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeSnapshot>,
  Pointer<Int32>,
);
typedef CodexStateIntDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeSnapshot>,
  Pointer<Int32>,
);
typedef CodexNativeHostStateAgentNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeHost>,
  Pointer<CodexNativeSnapshot>,
  Pointer<Pointer<CodexNativeAgent>>,
);
typedef CodexNativeHostStateAgentDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeHost>,
  Pointer<CodexNativeSnapshot>,
  Pointer<Pointer<CodexNativeAgent>>,
);
typedef CodexActiveConversationNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversations>,
  Pointer<CodexNativeSnapshot>,
  Pointer<Pointer<CodexNativeConversation>>,
);
typedef CodexActiveConversationDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversations>,
  Pointer<CodexNativeSnapshot>,
  Pointer<Pointer<CodexNativeConversation>>,
);
typedef CodexStateFailureNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeSnapshot>,
  Pointer<Pointer<CodexNativeFailure>>,
);
typedef CodexStateFailureDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeSnapshot>,
  Pointer<Pointer<CodexNativeFailure>>,
);
typedef CodexCopySnapshotStringNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeSnapshot>,
  Pointer<Uint8>,
  Size,
  Pointer<Size>,
);
typedef CodexCopySnapshotStringDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeSnapshot>,
  Pointer<Uint8>,
  int,
  Pointer<Size>,
);
typedef CodexCopyFailureStringNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeFailure>,
  Pointer<Uint8>,
  Size,
  Pointer<Size>,
);
typedef CodexCopyFailureStringDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeFailure>,
  Pointer<Uint8>,
  int,
  Pointer<Size>,
);
typedef CodexNativeFailureRecoverableNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeFailure>,
  Pointer<Int32>,
);
typedef CodexNativeFailureRecoverableDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeFailure>,
  Pointer<Int32>,
);
typedef CodexSummaryConversationIdNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversationSummary>,
  Pointer<Pointer<CodexNativeConversationId>>,
);
typedef CodexSummaryConversationIdDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversationSummary>,
  Pointer<Pointer<CodexNativeConversationId>>,
);
typedef CodexCopySummaryStringNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversationSummary>,
  Pointer<Uint8>,
  Size,
  Pointer<Size>,
);
typedef CodexCopySummaryStringDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversationSummary>,
  Pointer<Uint8>,
  int,
  Pointer<Size>,
);
typedef CodexSummaryUpdatedNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversationSummary>,
  Pointer<Int64>,
);
typedef CodexSummaryUpdatedDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversationSummary>,
  Pointer<Int64>,
);
typedef CodexCopyConversationIdNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversationId>,
  Pointer<Uint8>,
  Size,
  Pointer<Size>,
);
typedef CodexCopyConversationIdDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversationId>,
  Pointer<Uint8>,
  int,
  Pointer<Size>,
);

typedef CodexMallocNative = Pointer<Void> Function(Size);
typedef CodexMallocDart = Pointer<Void> Function(int);
typedef CodexFreeNative = Void Function(Pointer<Void>);
typedef CodexFreeDart = void Function(Pointer<Void>);

final class NativeMemory {
  NativeMemory._(DynamicLibrary library)
      : _malloc = library.lookupFunction<CodexMallocNative, CodexMallocDart>(
          'malloc',
        ),
        _free = library.lookupFunction<CodexFreeNative, CodexFreeDart>('free');

  factory NativeMemory.platform() {
    final library = Platform.isWindows
        ? DynamicLibrary.open('ucrtbase.dll')
        : DynamicLibrary.process();
    return NativeMemory._(library);
  }

  final CodexMallocDart _malloc;
  final CodexFreeDart _free;

  Pointer<T> allocate<T extends NativeType>(int bytes) {
    final pointer = _malloc(bytes).cast<T>();
    if (pointer == nullptr) {
      throw const CodexNativeException(2, 'native allocation failed');
    }
    return pointer;
  }

  void free(Pointer<NativeType> pointer) {
    if (pointer != nullptr) _free(pointer.cast<Void>());
  }
}

final NativeMemory nativeMemory = NativeMemory.platform();

final class NativeString {
  NativeString(String value) : _bytes = utf8.encode(value) {
    final allocatedView = nativeMemory.allocate<CodexStringView>(
      sizeOf<CodexStringView>(),
    );
    Pointer<Uint8> data = nullptr;
    try {
      if (_bytes.isNotEmpty) {
        data = nativeMemory.allocate<Uint8>(_bytes.length);
        data.asTypedList(_bytes.length).setAll(0, _bytes);
      }
      allocatedView.ref
        ..data = data
        ..size = _bytes.length;
      view = allocatedView;
    } catch (_) {
      nativeMemory.free(data);
      nativeMemory.free(allocatedView);
      rethrow;
    }
  }

  NativeString.absent() : _bytes = const <int>[] {
    view = nativeMemory.allocate<CodexStringView>(sizeOf<CodexStringView>());
    view.ref
      ..data = nullptr
      ..size = 0;
  }

  final List<int> _bytes;
  late final Pointer<CodexStringView> view;
  bool _closed = false;

  void close() {
    if (_closed) return;
    _closed = true;
    nativeMemory.free(view.ref.data);
    nativeMemory.free(view);
  }
}

String currentClassifier() {
  final architecture = switch (Abi.current()) {
    Abi.macosArm64 || Abi.linuxArm64 => 'arm64',
    Abi.macosX64 || Abi.linuxX64 || Abi.windowsX64 => 'x64',
    _ => throw CodexUnsupportedPlatformException(
        'unsupported Codex Agent desktop ABI: ${Abi.current()}',
      ),
  };
  if (Platform.isMacOS) return 'macos-$architecture';
  if (Platform.isLinux) return 'linux-$architecture';
  if (Platform.isWindows && architecture == 'x64') return 'windows-x64';
  throw CodexUnsupportedPlatformException(
    'unsupported Codex Agent desktop platform: ${Platform.operatingSystem}-$architecture',
  );
}

String libraryNameFor(String classifier) {
  if (classifier.startsWith('macos-')) return 'libcodex_agent.dylib';
  if (classifier.startsWith('linux-')) return 'libcodex_agent.so';
  if (classifier == 'windows-x64') return 'codex_agent.dll';
  throw CodexUnsupportedPlatformException(
    'unsupported Codex Agent native classifier: $classifier',
  );
}

String resolveLibraryPathSync([String? explicit]) {
  final environment = Platform.environment['CODEX_AGENT_LIBRARY'];
  final configured = explicit ?? environment;
  if (configured != null) {
    final file = File(configured);
    requireAbsoluteRegularFile(file, 'Codex Agent C SDK');
    return file.path;
  }

  final classifier = currentClassifier();
  final uri = Isolate.resolvePackageUriSync(
    Uri.parse(
      'package:codex_agent/src/native/$classifier/${libraryNameFor(classifier)}',
    ),
  );
  if (uri == null || uri.scheme != 'file' || !File.fromUri(uri).existsSync()) {
    throw CodexException(
      'Codex Agent C SDK for $classifier is absent; pass libraryPath '
      'or set CODEX_AGENT_LIBRARY',
    );
  }
  final packaged = File.fromUri(uri);
  requireAbsoluteRegularFile(packaged, 'packaged Codex Agent C SDK');
  return packaged.path;
}

Future<String> resolveLibraryPath([String? explicit]) async =>
    resolveLibraryPathSync(explicit);

final class NativeApi {
  NativeApi._(this.library)
      : abiVersion =
            library.lookupFunction<CodexAbiVersionNative, CodexAbiVersionDart>(
          'codex_agent_abi_version',
        ),
        abiCompatible = library
            .lookupFunction<CodexAbiCompatibleNative, CodexAbiCompatibleDart>(
          'codex_agent_abi_is_compatible',
        ),
        contextCreate = library
            .lookupFunction<CodexCreateContextNative, CodexCreateContextDart>(
          'codex_agent_context_create',
        ),
        contextDestroy = library
            .lookupFunction<CodexDestroyContextNative, CodexDestroyContextDart>(
          'codex_agent_context_destroy',
        ),
        hostCreate =
            library.lookupFunction<CodexCreateHostNative, CodexCreateHostDart>(
          'codex_agent_host_create',
        ),
        hostRelease = library
            .lookupFunction<CodexReleaseHostNative, CodexReleaseHostDart>(
          'codex_agent_host_release',
        ),
        hostStart = library.lookupFunction<CodexNativeHostOperationNative,
            CodexNativeHostOperationDart>('codex_agent_host_start'),
        hostClose = library.lookupFunction<CodexNativeHostOperationNative,
            CodexNativeHostOperationDart>('codex_agent_host_close'),
        hostSelectWorkspace = library.lookupFunction<
                CodexNativeHostSelectWorkspaceNative,
                CodexNativeHostSelectWorkspaceDart>(
            'codex_agent_host_select_workspace'),
        hostStateGet = library.lookupFunction<
                CodexGetSnapshotNative<CodexNativeHost>,
                CodexGetSnapshotDart<CodexNativeHost>>(
            'codex_agent_host_state_get'),
        hostStateSubscribe = library.lookupFunction<
                CodexSubscribeNative<CodexNativeHost>,
                CodexSubscribeDart<CodexNativeHost>>(
            'codex_agent_host_state_subscribe'),
        agentRelease = library.lookupFunction<
                CodexReleaseHandleNative<CodexNativeAgent>,
                CodexReleaseHandleDart<CodexNativeAgent>>(
            'codex_agent_agent_release'),
        agentConversations = library.lookupFunction<
                CodexNativeAgentConversationsNative,
                CodexNativeAgentConversationsDart>(
            'codex_agent_agent_conversations'),
        agentWorkspace = library.lookupFunction<CodexNativeAgentWorkspaceNative,
            CodexNativeAgentWorkspaceDart>('codex_agent_agent_workspace'),
        workspaceDestroy = library.lookupFunction<
                CodexReleaseHandleNative<CodexNativeWorkspace>,
                CodexReleaseHandleDart<CodexNativeWorkspace>>(
            'codex_agent_workspace_destroy'),
        workspacePath = library.lookupFunction<CodexCopyWorkspaceStringNative,
            CodexCopyWorkspaceStringDart>('codex_agent_workspace_path_copy'),
        workspaceDisplayName = library.lookupFunction<
                CodexCopyWorkspaceStringNative, CodexCopyWorkspaceStringDart>(
            'codex_agent_workspace_display_name_copy'),
        conversationsRelease = library.lookupFunction<
                CodexReleaseHandleNative<CodexNativeConversations>,
                CodexReleaseHandleDart<CodexNativeConversations>>(
            'codex_agent_conversations_release'),
        conversationsActiveGet = library.lookupFunction<
                CodexGetSnapshotNative<CodexNativeConversations>,
                CodexGetSnapshotDart<CodexNativeConversations>>(
            'codex_agent_conversations_active_get'),
        conversationsActiveSubscribe = library.lookupFunction<
                CodexSubscribeNative<CodexNativeConversations>,
                CodexSubscribeDart<CodexNativeConversations>>(
            'codex_agent_conversations_active_subscribe'),
        conversationsList = library.lookupFunction<
                CodexNativeConversationsOperationNative,
                CodexNativeConversationsOperationDart>(
            'codex_agent_conversations_list'),
        conversationsOpen = library.lookupFunction<
            CodexNativeConversationsOpenNative,
            CodexNativeConversationsOpenDart>('codex_agent_conversations_open'),
        conversationRelease = library.lookupFunction<
                CodexReleaseHandleNative<CodexNativeConversation>,
                CodexReleaseHandleDart<CodexNativeConversation>>(
            'codex_agent_conversation_release'),
        conversationSame = library.lookupFunction<
                CodexNativeConversationSameNative,
                CodexNativeConversationSameDart>(
            'codex_agent_conversation_is_same'),
        conversationSend = library.lookupFunction<
                CodexNativeConversationStringOperationNative,
                CodexNativeConversationStringOperationDart>(
            'codex_agent_conversation_send'),
        conversationShell = library.lookupFunction<
                CodexNativeConversationStringOperationNative,
                CodexNativeConversationStringOperationDart>(
            'codex_agent_conversation_run_shell_command'),
        conversationReload = library.lookupFunction<
                CodexNativeConversationOperationNative,
                CodexNativeConversationOperationDart>(
            'codex_agent_conversation_reload'),
        conversationCancelTurn = library.lookupFunction<
                CodexNativeConversationOperationNative,
                CodexNativeConversationOperationDart>(
            'codex_agent_conversation_cancel_turn'),
        conversationClose = library.lookupFunction<
                CodexNativeConversationOperationNative,
                CodexNativeConversationOperationDart>(
            'codex_agent_conversation_close'),
        conversationStateGet = library.lookupFunction<
                CodexGetSnapshotNative<CodexNativeConversation>,
                CodexGetSnapshotDart<CodexNativeConversation>>(
            'codex_agent_conversation_state_get'),
        conversationStateSubscribe = library.lookupFunction<
                CodexSubscribeNative<CodexNativeConversation>,
                CodexSubscribeDart<CodexNativeConversation>>(
            'codex_agent_conversation_state_subscribe'),
        operationCancel = library.lookupFunction<CodexCancelOperationNative,
            CodexCancelOperationDart>(
          'codex_agent_operation_cancel',
        ),
        operationResult = library.lookupFunction<
            CodexNativeOperationResultNative,
            CodexNativeOperationResultDart>('codex_agent_operation_result'),
        operationConversation = library.lookupFunction<
                CodexNativeOperationConversationNative,
                CodexNativeOperationConversationDart>(
            'codex_agent_operation_conversation'),
        operationFailure = library.lookupFunction<
            CodexNativeOperationFailureNative,
            CodexNativeOperationFailureDart>('codex_agent_operation_failure'),
        operationSummariesCount = library.lookupFunction<
                CodexNativeOperationCountNative, CodexNativeOperationCountDart>(
            'codex_agent_operation_conversation_summaries_count'),
        operationSummaryAt = library.lookupFunction<
                CodexNativeOperationSummaryAtNative,
                CodexNativeOperationSummaryAtDart>(
            'codex_agent_operation_conversation_summary_at'),
        operationDestroy = library.lookupFunction<
                CodexReleaseHandleNative<CodexNativeOperation>,
                CodexReleaseHandleDart<CodexNativeOperation>>(
            'codex_agent_operation_destroy'),
        subscriptionDestroy = library.lookupFunction<
                CodexReleaseHandleNative<CodexNativeSubscription>,
                CodexReleaseHandleDart<CodexNativeSubscription>>(
            'codex_agent_subscription_destroy'),
        snapshotDestroy = library.lookupFunction<
                CodexReleaseHandleNative<CodexNativeSnapshot>,
                CodexReleaseHandleDart<CodexNativeSnapshot>>(
            'codex_agent_snapshot_destroy'),
        hostStateKind =
            library.lookupFunction<CodexStateIntNative, CodexStateIntDart>(
          'codex_agent_host_state_kind',
        ),
        hostStateAgent = library.lookupFunction<CodexNativeHostStateAgentNative,
            CodexNativeHostStateAgentDart>('codex_agent_host_state_agent'),
        hostStateFailure = library
            .lookupFunction<CodexStateFailureNative, CodexStateFailureDart>(
          'codex_agent_host_state_failure',
        ),
        hostStateHasWorkspace =
            library.lookupFunction<CodexStateIntNative, CodexStateIntDart>(
          'codex_agent_host_state_has_workspace',
        ),
        hostStateWorkspacePath = library.lookupFunction<
                CodexCopySnapshotStringNative, CodexCopySnapshotStringDart>(
            'codex_agent_host_state_workspace_path_copy'),
        hostStateWorkspaceDisplayName = library.lookupFunction<
                CodexCopySnapshotStringNative, CodexCopySnapshotStringDart>(
            'codex_agent_host_state_workspace_display_name_copy'),
        hostStateRequirementReason =
            library.lookupFunction<CodexStateIntNative, CodexStateIntDart>(
          'codex_agent_host_state_requirement_reason',
        ),
        hostStateRequirementMessage = library.lookupFunction<
                CodexCopySnapshotStringNative, CodexCopySnapshotStringDart>(
            'codex_agent_host_state_requirement_message_copy'),
        activeConversation = library.lookupFunction<
            CodexActiveConversationNative,
            CodexActiveConversationDart>('codex_agent_active_conversation'),
        conversationStateStatus =
            library.lookupFunction<CodexStateIntNative, CodexStateIntDart>(
          'codex_agent_conversation_state_status',
        ),
        conversationStateFailure = library
            .lookupFunction<CodexStateFailureNative, CodexStateFailureDart>(
          'codex_agent_conversation_state_failure',
        ),
        stateBooleanValue =
            library.lookupFunction<CodexStateIntNative, CodexStateIntDart>(
          'codex_agent_state_boolean_value',
        ),
        failureRelease = library.lookupFunction<
                CodexReleaseHandleNative<CodexNativeFailure>,
                CodexReleaseHandleDart<CodexNativeFailure>>(
            'codex_agent_failure_release'),
        failureCode = library.lookupFunction<CodexCopyFailureStringNative,
            CodexCopyFailureStringDart>('codex_agent_failure_code_copy'),
        failureMessage = library.lookupFunction<CodexCopyFailureStringNative,
            CodexCopyFailureStringDart>('codex_agent_failure_message_copy'),
        failureRecoverable = library.lookupFunction<
                CodexNativeFailureRecoverableNative,
                CodexNativeFailureRecoverableDart>(
            'codex_agent_failure_is_recoverable'),
        summaryDestroy = library.lookupFunction<
                CodexReleaseHandleNative<CodexNativeConversationSummary>,
                CodexReleaseHandleDart<CodexNativeConversationSummary>>(
            'codex_agent_conversation_summary_destroy'),
        summaryConversationId = library.lookupFunction<
                CodexSummaryConversationIdNative,
                CodexSummaryConversationIdDart>(
            'codex_agent_conversation_summary_conversation_id'),
        summaryTitle = library.lookupFunction<CodexCopySummaryStringNative,
                CodexCopySummaryStringDart>(
            'codex_agent_conversation_summary_title_copy'),
        summaryUpdated = library
            .lookupFunction<CodexSummaryUpdatedNative, CodexSummaryUpdatedDart>(
          'codex_agent_conversation_summary_updated_at_epoch_seconds',
        ),
        conversationIdDestroy = library.lookupFunction<
                CodexReleaseHandleNative<CodexNativeConversationId>,
                CodexReleaseHandleDart<CodexNativeConversationId>>(
            'codex_agent_conversation_id_destroy'),
        conversationIdValue = library.lookupFunction<
                CodexCopyConversationIdNative, CodexCopyConversationIdDart>(
            'codex_agent_conversation_id_value_copy'),
        conversationCanStartTurnGet = library.lookupFunction<
                CodexGetSnapshotNative<CodexNativeConversation>,
                CodexGetSnapshotDart<CodexNativeConversation>>(
            'codex_agent_conversation_can_start_turn_get'),
        conversationCanStartTurnSubscribe = library.lookupFunction<
                CodexSubscribeNative<CodexNativeConversation>,
                CodexSubscribeDart<CodexNativeConversation>>(
            'codex_agent_conversation_can_start_turn_subscribe'),
        conversationCanReloadGet = library.lookupFunction<
                CodexGetSnapshotNative<CodexNativeConversation>,
                CodexGetSnapshotDart<CodexNativeConversation>>(
            'codex_agent_conversation_can_reload_get'),
        conversationCanReloadSubscribe = library.lookupFunction<
                CodexSubscribeNative<CodexNativeConversation>,
                CodexSubscribeDart<CodexNativeConversation>>(
            'codex_agent_conversation_can_reload_subscribe'),
        conversationCanCancelTurnGet = library.lookupFunction<
                CodexGetSnapshotNative<CodexNativeConversation>,
                CodexGetSnapshotDart<CodexNativeConversation>>(
            'codex_agent_conversation_can_cancel_turn_get'),
        conversationCanCancelTurnSubscribe = library.lookupFunction<
                CodexSubscribeNative<CodexNativeConversation>,
                CodexSubscribeDart<CodexNativeConversation>>(
            'codex_agent_conversation_can_cancel_turn_subscribe'),
        conversationCanRunShellGet = library.lookupFunction<
                CodexGetSnapshotNative<CodexNativeConversation>,
                CodexGetSnapshotDart<CodexNativeConversation>>(
            'codex_agent_conversation_can_run_shell_command_get'),
        conversationCanRunShellSubscribe = library.lookupFunction<
                CodexSubscribeNative<CodexNativeConversation>,
                CodexSubscribeDart<CodexNativeConversation>>(
            'codex_agent_conversation_can_run_shell_command_subscribe'),
        conversationIsTurnActiveGet = library.lookupFunction<
                CodexGetSnapshotNative<CodexNativeConversation>,
                CodexGetSnapshotDart<CodexNativeConversation>>(
            'codex_agent_conversation_is_turn_active_get'),
        conversationIsTurnActiveSubscribe = library.lookupFunction<
                CodexSubscribeNative<CodexNativeConversation>,
                CodexSubscribeDart<CodexNativeConversation>>(
            'codex_agent_conversation_is_turn_active_subscribe');

  factory NativeApi.load(String path) {
    return NativeApi._(_authenticatedRuntime(path).library);
  }

  final DynamicLibrary library;
  final CodexAbiVersionDart abiVersion;
  final CodexAbiCompatibleDart abiCompatible;
  final CodexCreateContextDart contextCreate;
  final CodexDestroyContextDart contextDestroy;
  final CodexCreateHostDart hostCreate;
  final CodexReleaseHostDart hostRelease;
  final CodexNativeHostOperationDart hostStart;
  final CodexNativeHostOperationDart hostClose;
  final CodexNativeHostSelectWorkspaceDart hostSelectWorkspace;
  final CodexGetSnapshotDart<CodexNativeHost> hostStateGet;
  final CodexSubscribeDart<CodexNativeHost> hostStateSubscribe;
  final CodexReleaseHandleDart<CodexNativeAgent> agentRelease;
  final CodexNativeAgentConversationsDart agentConversations;
  final CodexNativeAgentWorkspaceDart agentWorkspace;
  final CodexReleaseHandleDart<CodexNativeWorkspace> workspaceDestroy;
  final CodexCopyWorkspaceStringDart workspacePath;
  final CodexCopyWorkspaceStringDart workspaceDisplayName;
  final CodexReleaseHandleDart<CodexNativeConversations> conversationsRelease;
  final CodexGetSnapshotDart<CodexNativeConversations> conversationsActiveGet;
  final CodexSubscribeDart<CodexNativeConversations>
      conversationsActiveSubscribe;
  final CodexNativeConversationsOperationDart conversationsList;
  final CodexNativeConversationsOpenDart conversationsOpen;
  final CodexReleaseHandleDart<CodexNativeConversation> conversationRelease;
  final CodexNativeConversationSameDart conversationSame;
  final CodexNativeConversationStringOperationDart conversationSend;
  final CodexNativeConversationStringOperationDart conversationShell;
  final CodexNativeConversationOperationDart conversationReload;
  final CodexNativeConversationOperationDart conversationCancelTurn;
  final CodexNativeConversationOperationDart conversationClose;
  final CodexGetSnapshotDart<CodexNativeConversation> conversationStateGet;
  final CodexSubscribeDart<CodexNativeConversation> conversationStateSubscribe;
  final CodexCancelOperationDart operationCancel;
  final CodexNativeOperationResultDart operationResult;
  final CodexNativeOperationConversationDart operationConversation;
  final CodexNativeOperationFailureDart operationFailure;
  final CodexNativeOperationCountDart operationSummariesCount;
  final CodexNativeOperationSummaryAtDart operationSummaryAt;
  final CodexReleaseHandleDart<CodexNativeOperation> operationDestroy;
  final CodexReleaseHandleDart<CodexNativeSubscription> subscriptionDestroy;
  final CodexReleaseHandleDart<CodexNativeSnapshot> snapshotDestroy;
  final CodexStateIntDart hostStateKind;
  final CodexNativeHostStateAgentDart hostStateAgent;
  final CodexStateFailureDart hostStateFailure;
  final CodexStateIntDart hostStateHasWorkspace;
  final CodexCopySnapshotStringDart hostStateWorkspacePath;
  final CodexCopySnapshotStringDart hostStateWorkspaceDisplayName;
  final CodexStateIntDart hostStateRequirementReason;
  final CodexCopySnapshotStringDart hostStateRequirementMessage;
  final CodexActiveConversationDart activeConversation;
  final CodexStateIntDart conversationStateStatus;
  final CodexStateFailureDart conversationStateFailure;
  final CodexStateIntDart stateBooleanValue;
  final CodexReleaseHandleDart<CodexNativeFailure> failureRelease;
  final CodexCopyFailureStringDart failureCode;
  final CodexCopyFailureStringDart failureMessage;
  final CodexNativeFailureRecoverableDart failureRecoverable;
  final CodexReleaseHandleDart<CodexNativeConversationSummary> summaryDestroy;
  final CodexSummaryConversationIdDart summaryConversationId;
  final CodexCopySummaryStringDart summaryTitle;
  final CodexSummaryUpdatedDart summaryUpdated;
  final CodexReleaseHandleDart<CodexNativeConversationId> conversationIdDestroy;
  final CodexCopyConversationIdDart conversationIdValue;
  final CodexGetSnapshotDart<CodexNativeConversation>
      conversationCanStartTurnGet;
  final CodexSubscribeDart<CodexNativeConversation>
      conversationCanStartTurnSubscribe;
  final CodexGetSnapshotDart<CodexNativeConversation> conversationCanReloadGet;
  final CodexSubscribeDart<CodexNativeConversation>
      conversationCanReloadSubscribe;
  final CodexGetSnapshotDart<CodexNativeConversation>
      conversationCanCancelTurnGet;
  final CodexSubscribeDart<CodexNativeConversation>
      conversationCanCancelTurnSubscribe;
  final CodexGetSnapshotDart<CodexNativeConversation>
      conversationCanRunShellGet;
  final CodexSubscribeDart<CodexNativeConversation>
      conversationCanRunShellSubscribe;
  final CodexGetSnapshotDart<CodexNativeConversation>
      conversationIsTurnActiveGet;
  final CodexSubscribeDart<CodexNativeConversation>
      conversationIsTurnActiveSubscribe;
}

final class _AuthenticatedRuntime {
  const _AuthenticatedRuntime(this.library, this.digest);

  final DynamicLibrary library;
  final String digest;
}

final _authenticatedRuntimes = <String, _AuthenticatedRuntime>{};

_AuthenticatedRuntime _authenticatedRuntime(
  String path, {
  void Function(File snapshot)? beforeDynamicOpen,
}) {
  final file = File(path);
  requireAbsoluteRegularFile(file, 'Codex Agent C SDK');
  final cached = _authenticatedRuntimes[path];
  if (cached != null) {
    if (runtimeFileSha256(file) != cached.digest) {
      throw const CodexException(
        'Codex Agent Runtime changed after authentication',
      );
    }
    return cached;
  }

  final compatibility = RuntimeCompatibility.load();
  final target = currentClassifier();
  final packagedUri = Isolate.resolvePackageUriSync(
    Uri.parse(
      'package:codex_agent/src/native/$target/${libraryNameFor(target)}',
    ),
  );
  final embedded = packagedUri != null &&
      packagedUri.scheme == 'file' &&
      File.fromUri(packagedUri).path == file.path;
  final snapshot = snapshotRuntimeLibrary(
    file,
    compatibility,
    target,
    embedded: embedded,
  );
  try {
    final library = _openProtectedRuntime(
      snapshot,
      beforeDynamicOpen: beforeDynamicOpen,
    );
    final identityAbi = compatibility.verifyRuntimeIdentity(
      readRuntimeIdentity(library),
      target,
      embedded: embedded,
    );
    late final CodexAbiVersionDart abiVersion;
    late final CodexAbiCompatibleDart abiCompatible;
    try {
      abiVersion =
          library.lookupFunction<CodexAbiVersionNative, CodexAbiVersionDart>(
        'codex_agent_abi_version',
      );
      abiCompatible = library.lookupFunction<CodexAbiCompatibleNative,
          CodexAbiCompatibleDart>('codex_agent_abi_is_compatible');
    } on Object {
      throw const CodexException('Codex Agent Runtime cannot prove its ABI');
    }
    final actual = abiVersion();
    if (actual != identityAbi ||
        (actual >> 24) != compatibility.requiredAbiMajor ||
        ((actual >> 16) & 0xff) < compatibility.minimumAbiMinor ||
        abiCompatible(requiredAbiVersion) != 1) {
      throw CodexNativeException(
        CodexStatus.unsupportedAbi.value,
        'Codex Agent C SDK ABI 1.13+ is required; loaded '
        '0x${actual.toRadixString(16).padLeft(8, '0')}',
      );
    }
    snapshot.removeAfterLoad();
    return _authenticatedRuntimes[path] =
        _AuthenticatedRuntime(library, snapshot.digest);
  } catch (_) {
    snapshot.removeAfterLoad();
    rethrow;
  }
}

DynamicLibrary authenticatedRuntimeLibraryForTesting(
  String path, {
  void Function(File snapshot)? beforeDynamicOpen,
}) =>
    _authenticatedRuntime(
      path,
      beforeDynamicOpen: beforeDynamicOpen,
    ).library;

DynamicLibrary _openProtectedRuntime(
  RuntimeLibrarySnapshot snapshot, {
  void Function(File snapshot)? beforeDynamicOpen,
}) =>
    Platform.isWindows
        ? _openProtectedWindows(snapshot, beforeDynamicOpen)
        : _openProtectedPosix(snapshot, beforeDynamicOpen);

DynamicLibrary _openProtectedPosix(
  RuntimeLibrarySnapshot snapshot,
  void Function(File snapshot)? beforeDynamicOpen,
) {
  final process = DynamicLibrary.process();
  final open = process.lookupFunction<_OpenNative, _OpenDart>('open');
  final close = process.lookupFunction<_CloseNative, _CloseDart>('close');
  final seek = process.lookupFunction<_SeekNative, _SeekDart>('lseek');
  final fstat = Platform.isMacOS
      ? process.lookupFunction<_FstatNative, _FstatDart>('fstat')
      : null;
  final stat = Platform.isMacOS
      ? process.lookupFunction<_StatNative, _StatDart>('stat')
      : null;
  final path = _nativeUtf8(snapshot.file.path);
  final noFollow = Platform.isMacOS ? 0x00000100 : 0x00020000;
  final closeOnExec = Platform.isMacOS ? 0x01000000 : 0x00080000;
  final descriptor = open(path, noFollow | closeOnExec);
  nativeMemory.free(path);
  if (descriptor < 0) {
    throw const CodexException('Codex Agent Runtime snapshot cannot be opened');
  }
  final descriptorFile = File(
    Platform.isMacOS ? '/dev/fd/$descriptor' : '/proc/self/fd/$descriptor',
  );
  void verifyDescriptor() {
    if (seek(descriptor, 0, 0) != 0) {
      throw const CodexException('Codex Agent Runtime snapshot cannot be read');
    }
    snapshot.verifyDescriptor(descriptorFile);
  }

  void verifyMacPathBinding() {
    verifyDescriptor();
    snapshot.verify();
    final descriptorStat = nativeMemory.allocate<Uint8>(256);
    final pathStat = nativeMemory.allocate<Uint8>(256);
    final snapshotPath = _nativeUtf8(snapshot.file.path);
    try {
      if (fstat!(descriptor, descriptorStat) != 0 ||
          stat!(snapshotPath, pathStat) != 0) {
        throw const CodexException(
          'Codex Agent Runtime snapshot identity cannot be read',
        );
      }
      final descriptorData = ByteData.sublistView(
        descriptorStat.asTypedList(16),
      );
      final pathData = ByteData.sublistView(pathStat.asTypedList(16));
      if (descriptorData.getInt32(0, Endian.host) !=
              pathData.getInt32(0, Endian.host) ||
          descriptorData.getUint64(8, Endian.host) !=
              pathData.getUint64(8, Endian.host)) {
        throw const CodexException(
          'Codex Agent Runtime snapshot identity changed',
        );
      }
    } finally {
      nativeMemory.free(snapshotPath);
      nativeMemory.free(pathStat);
      nativeMemory.free(descriptorStat);
    }
  }

  try {
    if (Platform.isLinux) {
      verifyDescriptor();
      snapshot.file.deleteSync();
      beforeDynamicOpen?.call(snapshot.file);
      verifyDescriptor();
    } else {
      verifyMacPathBinding();
      beforeDynamicOpen?.call(snapshot.file);
      verifyMacPathBinding();
    }
    seek(descriptor, 0, 0);
    final library = DynamicLibrary.open(
      Platform.isLinux ? descriptorFile.path : snapshot.file.path,
    );
    if (Platform.isLinux) {
      verifyDescriptor();
    } else {
      verifyMacPathBinding();
    }
    return library;
  } finally {
    close(descriptor);
  }
}

DynamicLibrary _openProtectedWindows(
  RuntimeLibrarySnapshot snapshot,
  void Function(File snapshot)? beforeDynamicOpen,
) {
  final kernel = DynamicLibrary.open('kernel32.dll');
  final createFile =
      kernel.lookupFunction<_CreateFileNative, _CreateFileDart>('CreateFileW');
  final closeHandle = kernel
      .lookupFunction<_CloseHandleNative, _CloseHandleDart>('CloseHandle');
  final path = _nativeUtf16(snapshot.file.path);
  final handle = createFile(
    path,
    0x80000000,
    0x00000001,
    nullptr,
    3,
    0x00200080,
    0,
  );
  nativeMemory.free(path);
  if (handle == -1) {
    throw const CodexException('Codex Agent Runtime cannot be locked');
  }
  try {
    snapshot.verify();
    beforeDynamicOpen?.call(snapshot.file);
    snapshot.verify();
    final library = DynamicLibrary.open(snapshot.file.path);
    snapshot.verify();
    return library;
  } finally {
    closeHandle(handle);
  }
}

Pointer<Uint8> _nativeUtf8(String value) {
  final bytes = utf8.encode(value);
  final result = nativeMemory.allocate<Uint8>(bytes.length + 1);
  result.asTypedList(bytes.length + 1)
    ..setRange(0, bytes.length, bytes)
    ..[bytes.length] = 0;
  return result;
}

Pointer<Uint16> _nativeUtf16(String value) {
  final units = value.codeUnits;
  final result = nativeMemory.allocate<Uint16>((units.length + 1) * 2);
  result.asTypedList(units.length + 1)
    ..setRange(0, units.length, units)
    ..[units.length] = 0;
  return result;
}

String readRuntimeIdentity(DynamicLibrary library) {
  CodexRuntimeIdentityDart identity;
  try {
    identity = library
        .lookupFunction<CodexRuntimeIdentityNative, CodexRuntimeIdentityDart>(
      'codex_agent_runtime_identity',
    );
  } on Object {
    throw const CodexException('Codex Agent Runtime cannot prove its identity');
  }
  final required = nativeMemory.allocate<Size>(sizeOf<Size>());
  required.value = 0;
  try {
    if (identity(nullptr, required) != CodexStatus.bufferTooSmall.value ||
        required.value < 2 ||
        required.value > 65536) {
      throw const CodexException('invalid Codex Agent Runtime identity query');
    }
    final capacity = required.value;
    final buffer = nativeMemory.allocate<Uint8>(capacity);
    try {
      if (identity(buffer, required) != CodexStatus.ok.value ||
          required.value != capacity) {
        throw const CodexException('invalid Codex Agent Runtime identity copy');
      }
      final bytes = buffer.asTypedList(capacity);
      if (bytes.last != 0 || bytes.take(capacity - 1).contains(0)) {
        throw const CodexException(
          'invalid Codex Agent Runtime identity bytes',
        );
      }
      return utf8.decode(bytes.sublist(0, capacity - 1), allowMalformed: false);
    } finally {
      nativeMemory.free(buffer);
    }
  } on CodexException {
    rethrow;
  } on Object catch (error) {
    throw CodexException('invalid Codex Agent Runtime identity: $error');
  } finally {
    nativeMemory.free(required);
  }
}

void checkStatus(
  int value,
  String operation, {
  Set<CodexStatus> allow = const {},
}) {
  if (value == CodexStatus.ok.value) return;
  final status = CodexStatus.fromValue(value);
  if (allow.contains(status)) return;
  throw CodexNativeException(value, '$operation failed with ${status.name}');
}

Pointer<Pointer<T>> newHandleSlot<T extends NativeType>() {
  final slot = nativeMemory.allocate<Pointer<T>>(sizeOf<Pointer<Void>>());
  slot.value = nullptr;
  return slot;
}

String copyString<T extends NativeType>(
  int Function(
    Pointer<CodexNativeContext>,
    Pointer<T>,
    Pointer<Uint8>,
    int,
    Pointer<Size>,
  ) copier,
  Pointer<CodexNativeContext> context,
  Pointer<T> owner, {
  bool nullable = false,
}) {
  final required = nativeMemory.allocate<Size>(sizeOf<Size>());
  try {
    final first = copier(context, owner, nullptr, 0, required);
    if (nullable && first == CodexStatus.notReady.value) return '';
    checkStatus(
      first,
      'string size query',
      allow: const {CodexStatus.bufferTooSmall},
    );
    if (required.value == 0) return '';
    final buffer = nativeMemory.allocate<Uint8>(required.value);
    try {
      checkStatus(
        copier(context, owner, buffer, required.value, required),
        'string copy',
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

Uint8List utf8Bytes(String value) => Uint8List.fromList(utf8.encode(value));
