import 'dart:convert';
import 'dart:io';

import 'package:codex_agent/codex_agent.dart';
import 'package:codex_agent/src/ffi.dart';
import 'package:codex_agent/src/value_native.dart';
import 'package:test/test.dart';

final class DartFunctionClaim {
  const DartFunctionClaim({
    required this.capabilityKey,
    required this.publicSymbols,
    required this.executedTests,
    required this.compilerEvidenceIds,
    required this.sharedScenarios,
  });

  final String capabilityKey;
  final List<String> publicSymbols;
  final List<String> executedTests;
  final List<String> compilerEvidenceIds;
  final List<String> sharedScenarios;
}

const _owners = <String>{
  'AgentElicitationResponse.Companion',
  'AgentElicitation',
  'AgentFormField',
  'AgentInteractionState',
  'CodexAuthorizationUrl.Companion',
};

const _publicSymbols = <String, String>{
  'AgentElicitationResponse.Companion.cancel':
      'CodexElicitationResponse.cancel',
  'AgentElicitationResponse.Companion.decline':
      'CodexElicitationResponse.decline',
  'AgentElicitation.accepts': 'CodexElicitation.accepts',
  'AgentElicitation.accept': 'CodexElicitation.accept',
  'AgentElicitation.initialValues': 'CodexElicitation.initialValues',
  'AgentElicitation.validate': 'CodexElicitation.validate',
  'AgentFormField.accepts': 'CodexFormField.accepts',
  'AgentInteractionState.isResolving': 'CodexInteractionState.isResolving',
  'AgentInteractionState.pendingFor': 'CodexInteractionState.pendingFor',
  'CodexAuthorizationUrl.Companion.chatGpt': 'CodexAuthorizationUrl.chatGpt',
  'CodexAuthorizationUrl.Companion.external': 'CodexAuthorizationUrl.external',
};

const functionCallSymbols = <String, String>{
  'AgentElicitationResponse.Companion.cancel':
      'codex_agent_elicitation_response_cancel',
  'AgentElicitationResponse.Companion.decline':
      'codex_agent_elicitation_response_decline',
  'AgentElicitation.accepts': 'codex_agent_elicitation_accepts',
  'AgentElicitation.accept': 'codex_agent_elicitation_accept',
  'AgentElicitation.initialValues': 'codex_agent_elicitation_initial_values',
  'AgentElicitation.validate': 'codex_agent_elicitation_validate',
  'AgentFormField.accepts': 'codex_agent_form_field_accepts',
  'AgentInteractionState.isResolving':
      'codex_agent_interaction_state_is_resolving',
  'AgentInteractionState.pendingFor':
      'codex_agent_interaction_state_pending_for',
  'CodexAuthorizationUrl.Companion.chatGpt':
      'codex_agent_authorization_url_chat_gpt',
  'CodexAuthorizationUrl.Companion.external':
      'codex_agent_authorization_url_external',
};

const _bridgeFunctions = <String, String>{
  'AgentElicitationResponse.Companion.cancel': 'nativeResponseFactory',
  'AgentElicitationResponse.Companion.decline': 'nativeResponseFactory',
  'AgentElicitation.accepts': 'nativeElicitationAccepts',
  'AgentElicitation.accept': 'nativeElicitationAccept',
  'AgentElicitation.initialValues': 'nativeElicitationInitialValues',
  'AgentElicitation.validate': 'nativeElicitationValidate',
  'AgentFormField.accepts': 'nativeFormFieldAccepts',
  'AgentInteractionState.isResolving': 'nativeInteractionIsResolving',
  'AgentInteractionState.pendingFor': 'nativeInteractionPendingFor',
  'CodexAuthorizationUrl.Companion.chatGpt': 'nativeAuthorizationUrl',
  'CodexAuthorizationUrl.Companion.external': 'nativeAuthorizationUrl',
};

const _ffiFields = <String, String>{
  'AgentElicitationResponse.Companion.cancel': 'responseCancel',
  'AgentElicitationResponse.Companion.decline': 'responseDecline',
  'AgentElicitation.accepts': 'elicitationAccepts',
  'AgentElicitation.accept': 'elicitationAccept',
  'AgentElicitation.initialValues': 'elicitationInitialValues',
  'AgentElicitation.validate': 'elicitationValidate',
  'AgentFormField.accepts': 'formFieldAccepts',
  'AgentInteractionState.isResolving': 'interactionIsResolving',
  'AgentInteractionState.pendingFor': 'interactionPendingFor',
  'CodexAuthorizationUrl.Companion.chatGpt': 'authorizationChatGpt',
  'CodexAuthorizationUrl.Companion.external': 'authorizationExternal',
};

const _publicEdges = <String, String>{
  'AgentElicitationResponse.Companion.cancel':
      "factoryCodexElicitationResponse.cancel()=>nativeResponseFactory('codex_agent_elicitation_response_cancel',);",
  'AgentElicitationResponse.Companion.decline':
      "factoryCodexElicitationResponse.decline()=>nativeResponseFactory('codex_agent_elicitation_response_decline',);",
  'AgentElicitation.accepts':
      'boolaccepts(CodexElicitationResponseresponse)=>nativeElicitationAccepts(this,response);',
  'AgentElicitation.accept':
      'CodexElicitationResponseaccept(Map<String,CodexFormValue>content)=>nativeElicitationAccept(this,content);',
  'AgentElicitation.initialValues':
      'Map<String,CodexFormValue>initialValues()=>nativeElicitationInitialValues(this);',
  'AgentElicitation.validate':
      'CodexElicitationValidationvalidate(Map<String,CodexFormValue>content)=>nativeElicitationValidate(this,content);',
  'AgentFormField.accepts':
      'boolaccepts(CodexFormValue?value)=>nativeFormFieldAccepts(this,value);',
  'AgentInteractionState.isResolving':
      'boolisResolving(CodexPendingInteractioninteraction)=>nativeInteractionIsResolving(this,interaction);',
  'AgentInteractionState.pendingFor':
      'List<CodexPendingInteraction>pendingFor(CodexConversationIdconversationId)=>nativeInteractionPendingFor(this,conversationId);',
  'CodexAuthorizationUrl.Companion.chatGpt':
      "factoryCodexAuthorizationUrl.chatGpt(Stringvalue){finalnative=nativeAuthorizationUrl('codex_agent_authorization_url_chat_gpt',value,);returnCodexAuthorizationUrl._(native.value,native.purpose);}",
  'CodexAuthorizationUrl.Companion.external':
      "factoryCodexAuthorizationUrl.external(Stringvalue){finalnative=nativeAuthorizationUrl('codex_agent_authorization_url_external',value,);returnCodexAuthorizationUrl._(native.value,native.purpose);}",
};

// Explicitly typed compiler references: changing or removing any projection
// breaks `dart analyze` before claims can be emitted.
CodexElicitationResponse _cancel() => CodexElicitationResponse.cancel();
CodexElicitationResponse _decline() => CodexElicitationResponse.decline();
bool _elicitationAccepts(
  CodexElicitation value,
  CodexElicitationResponse response,
) =>
    value.accepts(response);
CodexElicitationResponse _elicitationAccept(
  CodexElicitation value,
  Map<String, CodexFormValue> content,
) =>
    value.accept(content);
Map<String, CodexFormValue> _initialValues(CodexElicitation value) =>
    value.initialValues();
CodexElicitationValidation _validate(
  CodexElicitation value,
  Map<String, CodexFormValue> content,
) =>
    value.validate(content);
bool _fieldAccepts(CodexFormField field, CodexFormValue? value) =>
    field.accepts(value);
bool _isResolving(
  CodexInteractionState state,
  CodexPendingInteraction interaction,
) =>
    state.isResolving(interaction);
List<CodexPendingInteraction> _pendingFor(
  CodexInteractionState state,
  CodexConversationId conversationId,
) =>
    state.pendingFor(conversationId);
CodexAuthorizationUrl _chatGpt(String value) =>
    CodexAuthorizationUrl.chatGpt(value);
CodexAuthorizationUrl _external(String value) =>
    CodexAuthorizationUrl.external(value);

final functionPublicReferences = <String, Object>{
  'CodexElicitationResponse.cancel': _cancel,
  'CodexElicitationResponse.decline': _decline,
  'CodexElicitation.accepts': _elicitationAccepts,
  'CodexElicitation.accept': _elicitationAccept,
  'CodexElicitation.initialValues': _initialValues,
  'CodexElicitation.validate': _validate,
  'CodexFormField.accepts': _fieldAccepts,
  'CodexInteractionState.isResolving': _isResolving,
  'CodexInteractionState.pendingFor': _pendingFor,
  'CodexAuthorizationUrl.chatGpt': _chatGpt,
  'CodexAuthorizationUrl.external': _external,
};

String _functionName(String capability) => capability
    .split('|abi=io.github.codex_agent_labs.codexagent.agent/')[1]
    .split('|')[0];

bool _sameSet(Set<String> left, Set<String> right) =>
    left.length == right.length && left.containsAll(right);

Set<String> _canonicalFunctions(Directory root) {
  final report = jsonDecode(
    File(
      '${root.path}/codex-agent-core/build/reports/'
      'cross-language-api/canonical-api.json',
    ).readAsStringSync(),
  ) as Map<String, dynamic>;
  return {
    for (final owner in report['owners'] as List<dynamic>)
      if (_owners.contains(
        ((owner as Map<String, dynamic>)['name'] as String).split('/').last,
      ))
        for (final capability in owner['capabilities'] as List<dynamic>)
          if ((capability as String).contains('|kind=function|')) capability,
  };
}

List<String> _expectedScenarios(String function) {
  final scenarios = <String>{'value-conversion'};
  if (const <String>{
    'AgentElicitation.accept',
    'AgentElicitation.initialValues',
    'AgentElicitation.validate',
    'AgentInteractionState.pendingFor',
  }.contains(function)) {
    scenarios.add('collection-immutability-ordering');
  }
  if (function == 'AgentFormField.accepts') scenarios.add('nullability');
  return scenarios.toList()..sort();
}

Set<String> verifyFunctionClaims(
  List<DartFunctionClaim> claims,
  Directory root, {
  Map<String, String> callSymbols = functionCallSymbols,
  String? publicSourceOverride,
  String? bridgeSourceOverride,
}) {
  if (claims.length != 11 ||
      !_sameSet(
        claims.map((claim) => claim.capabilityKey).toSet(),
        _canonicalFunctions(root),
      ) ||
      !_sameSet(
        claims.expand((claim) => claim.publicSymbols).toSet(),
        functionPublicReferences.keys.toSet(),
      ) ||
      claims.map((claim) => claim.capabilityKey).toSet().length != 11) {
    final keys = claims.map((claim) => claim.capabilityKey).toSet();
    final canonical = _canonicalFunctions(root);
    final symbols = claims.expand((claim) => claim.publicSymbols).toSet();
    throw StateError(
      'Dart synchronous-function claims are incomplete or stale: '
      'claims=${claims.length}, keysMissing=${canonical.difference(keys)}, '
      'keysExtra=${keys.difference(canonical)}, symbolsMissing='
      '${functionPublicReferences.keys.toSet().difference(symbols)}, '
      'symbolsExtra=${symbols.difference(functionPublicReferences.keys.toSet())}',
    );
  }

  final bootstrap = jsonDecode(
    File(
      '${root.path}/codex-agent-runtime-desktop/build/reports/'
      'cross-language-api/c-abi/bootstrap-evidence.json',
    ).readAsStringSync(),
  ) as Map<String, dynamic>;
  final bootstrapClaims = <String, Map<String, dynamic>>{
    for (final claim in bootstrap['claims'] as List<dynamic>)
      (claim as Map<String, dynamic>)['capabilityKey'] as String: claim,
  };
  final passedTests = <String>{
    for (final test in bootstrap['nativeTests'] as List<dynamic>)
      if ((test as Map<String, dynamic>)['status'] == 'passed')
        test['testId'] as String,
  };
  final header = File(
    '${root.path}/codex-agent-runtime-desktop/native/c-api/include/'
    'codex_agent.h',
  ).readAsStringSync();
  final publicSource = publicSourceOverride ??
      File(
        '${root.path}/codex-agent-runtime-desktop/bindings/dart/'
        'lib/src/residual_models.dart',
      ).readAsStringSync();
  final bridgeSource = bridgeSourceOverride ??
      File(
        '${root.path}/codex-agent-runtime-desktop/bindings/dart/'
        'lib/src/value_native.dart',
      ).readAsStringSync();
  final compactPublic = publicSource.replaceAll(RegExp(r'\s+'), '');
  final compactBridge = bridgeSource.replaceAll(RegExp(r'\s+'), '');
  final references = <String>{};
  final sorted = claims.toList()
    ..sort((left, right) => left.capabilityKey.compareTo(right.capabilityKey));
  for (var index = 0; index < sorted.length; index++) {
    final claim = sorted[index];
    final function = _functionName(claim.capabilityKey);
    final expectedSymbol = _publicSymbols[function];
    final exactCall = callSymbols[function];
    final bridge = _bridgeFunctions[function];
    final ffiField = _ffiFields[function];
    final publicEdge = _publicEdges[function];
    final expectedTest = 'dart.function:${index.toString().padLeft(3, '0')}';
    final expectedAnalyzer =
        'dart-analyzer-function:${index.toString().padLeft(3, '0')}';
    final bootstrapClaim = bootstrapClaims[claim.capabilityKey];
    if (expectedSymbol == null ||
        exactCall == null ||
        bridge == null ||
        ffiField == null ||
        publicEdge == null ||
        bootstrapClaim == null ||
        claim.publicSymbols.length != 1 ||
        claim.publicSymbols.single != expectedSymbol ||
        claim.executedTests.length != 1 ||
        claim.executedTests.single != expectedTest ||
        claim.sharedScenarios.join(',') !=
            _expectedScenarios(function).join(',')) {
      throw StateError('inexact Dart function claim: ${claim.capabilityKey}');
    }
    if (!compactPublic.contains(publicEdge)) {
      throw StateError('public projection is disconnected from $bridge');
    }
    final lookupStart = compactBridge.indexOf(
      '$ffiField=core.library.lookupFunction<',
    );
    final lookupCall = lookupStart < 0
        ? -1
        : compactBridge.indexOf("'$exactCall'", lookupStart);
    if (lookupStart < 0 ||
        lookupCall < lookupStart ||
        lookupCall - lookupStart > 500) {
      throw StateError(
        'production bridge is disconnected from exact FFI call: $exactCall',
      );
    }
    if (bridge == 'nativeResponseFactory' ||
        bridge == 'nativeAuthorizationUrl') {
      if (!compactPublic.contains("'$exactCall'")) {
        throw StateError('public factory is disconnected from $exactCall');
      }
      if (!compactBridge.contains("'$exactCall'=>api.$ffiField")) {
        throw StateError(
            'native factory dispatch is disconnected from $exactCall');
      }
    } else {
      final bridgeStart = compactBridge.indexOf('$bridge(');
      final invocation = bridgeStart < 0
          ? -1
          : compactBridge.indexOf('api.$ffiField(', bridgeStart);
      if (bridgeStart < 0 ||
          invocation < bridgeStart ||
          invocation - bridgeStart > 6000) {
        throw StateError('public bridge does not invoke api.$ffiField');
      }
    }
    final headerNames =
        (bootstrapClaim['headerReferences'] as List<dynamic>).cast<String>();
    final nativeTests =
        (bootstrapClaim['nativeTestIds'] as List<dynamic>).cast<String>();
    if (!headerNames.contains(exactCall)) {
      throw StateError('native call is not connected to bootstrap: $exactCall');
    }
    final expectedEvidence = <String>{
      ...headerNames.map((name) => 'c-header:$name'),
      ...nativeTests.map((test) => 'cabi-fixture:$test'),
      expectedAnalyzer,
    };
    if (!_sameSet(claim.compilerEvidenceIds.toSet(), expectedEvidence)) {
      throw StateError(
          'inexact Dart function evidence: ${claim.capabilityKey}');
    }
    for (final name in headerNames) {
      if (!RegExp('\\b${RegExp.escape(name)}\\s*\\(').hasMatch(header)) {
        throw StateError('stale C header reference: $name');
      }
      references.add(name);
    }
    for (final test in nativeTests) {
      if (!passedTests.contains(test)) {
        throw StateError('stale C ABI fixture reference: $test');
      }
    }
  }
  return references;
}

({CodexElicitation elicitation, Map<String, CodexFormValue> content})
    _fixture() {
  final defaults = <String>['alpha'];
  final fields = <CodexFormField>[
    CodexFormField(
      name: 'name',
      title: 'Name',
      type: CodexFormFieldType.string,
      isRequired: true,
      defaultValue: const CodexTextFormValue('Codex'),
    ),
    CodexFormField(
      name: 'choices',
      title: 'Choices',
      type: CodexFormFieldType.multiSelect,
      isRequired: true,
      defaultValue: CodexTextListFormValue(defaults),
      options: [
        CodexFormOption(value: 'alpha', title: 'Alpha'),
        CodexFormOption(value: 'beta', title: 'Beta'),
      ],
    ),
  ];
  return (
    elicitation: CodexElicitation(
      requestId: 'request',
      serverName: 'server',
      conversationId: CodexConversationId('conversation'),
      message: 'Choose',
      form: fields,
    ),
    content: <String, CodexFormValue>{
      'name': const CodexTextFormValue('Codex'),
      'choices': CodexTextListFormValue(['alpha']),
    },
  );
}

void _verifyFormRules() {
  final option = CodexFormOption(value: 'alpha', title: 'Alpha');
  final optional = CodexFormField(
    name: 'optional',
    title: 'Optional',
    type: CodexFormFieldType.string,
  );
  final required = CodexFormField(
    name: 'required',
    title: 'Required',
    type: CodexFormFieldType.string,
    isRequired: true,
  );
  expect(optional.accepts(null), isTrue);
  expect(required.accepts(null), isFalse);
  final cases = <(CodexFormField, CodexFormValue, CodexFormValue)>[
    (
      CodexFormField(
        name: 'text',
        title: 'Text',
        type: CodexFormFieldType.string,
        isRequired: true,
        minimumLength: 2,
        maximumLength: 3,
      ),
      const CodexTextFormValue('ab'),
      const CodexTextFormValue(' '),
    ),
    (
      CodexFormField(
        name: 'number',
        title: 'Number',
        type: CodexFormFieldType.number,
        minimum: 1,
        maximum: 2,
      ),
      const CodexNumberFormValue(1.5),
      CodexNumberFormValue(double.nan),
    ),
    (
      CodexFormField(
        name: 'integer',
        title: 'Integer',
        type: CodexFormFieldType.integer,
      ),
      const CodexNumberFormValue(2),
      const CodexNumberFormValue(1.5),
    ),
    (
      CodexFormField(
        name: 'boolean',
        title: 'Boolean',
        type: CodexFormFieldType.boolean,
      ),
      const CodexBooleanFormValue(false),
      const CodexTextFormValue('false'),
    ),
    (
      CodexFormField(
        name: 'single',
        title: 'Single',
        type: CodexFormFieldType.singleSelect,
        options: [option],
      ),
      const CodexTextFormValue('alpha'),
      const CodexTextFormValue('other'),
    ),
    (
      CodexFormField(
        name: 'multi',
        title: 'Multi',
        type: CodexFormFieldType.multiSelect,
        options: [option],
        minimumSelections: 1,
        maximumSelections: 1,
      ),
      CodexTextListFormValue(['alpha']),
      CodexTextListFormValue(['alpha', 'alpha']),
    ),
  ];
  for (final (field, accepted, rejected) in cases) {
    expect(field.accepts(accepted), isTrue, reason: field.name);
    expect(field.accepts(rejected), isFalse, reason: field.name);
  }
  for (final (format, accepted, rejected)
      in <(CodexFormStringFormat, String, String)>[
    (CodexFormStringFormat.email, 'a@b', 'a@@b'),
    (CodexFormStringFormat.uri, 'https:value', '1https:value'),
    (CodexFormStringFormat.date, '2024-02-29', '2023-02-29'),
    (
      CodexFormStringFormat.dateTime,
      '2024-02-29T23:59:60Z',
      '2024-02-29T24:00:00Z',
    ),
  ]) {
    final field = CodexFormField(
      name: 'formatted',
      title: 'Formatted',
      type: CodexFormFieldType.string,
      format: format,
    );
    expect(field.accepts(CodexTextFormValue(accepted)), isTrue);
    expect(field.accepts(CodexTextFormValue(rejected)), isFalse);
  }
  for (final invalid in <String>[
    '2024- 1-01',
    '2024-01-01T 1:00:00Z',
    '2024-01-01T01:00:00+ 1:00',
    '2024-01-01T01:00:00.Z',
  ]) {
    final format = invalid.contains('T')
        ? CodexFormStringFormat.dateTime
        : CodexFormStringFormat.date;
    expect(
      CodexFormField(
        name: 'formatted',
        title: 'Formatted',
        type: CodexFormFieldType.string,
        format: format,
      ).accepts(CodexTextFormValue(invalid)),
      isFalse,
    );
  }
}

void _verifyBehavior(String testId) {
  final fixture = _fixture();
  final elicitation = fixture.elicitation;
  final content = fixture.content;
  switch (testId) {
    case 'dart.function:000':
      final response = CodexElicitationResponse.cancel();
      expect(response.action, CodexElicitationAction.cancel);
      expect(response.content, isEmpty);
    case 'dart.function:001':
      final response = CodexElicitationResponse.decline();
      expect(response.action, CodexElicitationAction.decline);
      expect(response.content, isEmpty);
    case 'dart.function:002':
      expect(elicitation.accepts(elicitation.accept(content)), isTrue);
      expect(
        elicitation.accepts(
          CodexElicitationResponse(action: CodexElicitationAction.accept),
        ),
        isFalse,
      );
      for (final action in <CodexElicitationAction>[
        CodexElicitationAction.decline,
        CodexElicitationAction.cancel,
      ]) {
        expect(elicitation.accepts(CodexElicitationResponse(action: action)),
            isTrue);
        expect(
          elicitation.accepts(
            CodexElicitationResponse(action: action, content: content),
          ),
          isFalse,
        );
      }
    case 'dart.function:003':
      final mutable = Map<String, CodexFormValue>.of(content);
      final response = elicitation.accept(mutable);
      expect(response.action, CodexElicitationAction.accept);
      expect(response.content.keys, <String>['name', 'choices']);
      mutable.clear();
      expect(response.content.keys, <String>['name', 'choices']);
      expect(() => response.content.clear(), throwsUnsupportedError);
      expect(() => elicitation.accept({}), throwsArgumentError);
    case 'dart.function:004':
      final values = elicitation.initialValues();
      expect(values.keys, <String>['name', 'choices']);
      expect((values['name']! as CodexTextFormValue).value, 'Codex');
      expect((values['choices']! as CodexTextListFormValue).value, ['alpha']);
      expect(values['choices'], isNot(same(elicitation.form![1].defaultValue)));
      expect(() => values.clear(), throwsUnsupportedError);
      final duplicates = CodexElicitation(
        requestId: 'duplicates',
        serverName: 'server',
        conversationId: CodexConversationId('conversation'),
        message: 'Choose',
        form: [
          CodexFormField(
            name: 'same',
            title: 'First',
            type: CodexFormFieldType.string,
            defaultValue: const CodexTextFormValue('first'),
          ),
          CodexFormField(
            name: 'other',
            title: 'Other',
            type: CodexFormFieldType.string,
            defaultValue: const CodexTextFormValue('other'),
          ),
          CodexFormField(
            name: 'same',
            title: 'Last',
            type: CodexFormFieldType.string,
            defaultValue: const CodexTextFormValue('last'),
          ),
        ],
      ).initialValues();
      expect(duplicates.keys, <String>['same', 'other']);
      expect((duplicates['same']! as CodexTextFormValue).value, 'last');
    case 'dart.function:005':
      final validation = elicitation.validate(
        <String, CodexFormValue>{
          'unknown': const CodexTextFormValue('value'),
        },
      );
      expect(
        validation.issues
            .map((issue) => (issue.fieldName, issue.reason))
            .toList(),
        <(String, CodexElicitationValidationReason)>[
          ('unknown', CodexElicitationValidationReason.unknownField),
          ('name', CodexElicitationValidationReason.missingRequired),
          ('choices', CodexElicitationValidationReason.missingRequired),
        ],
      );
    case 'dart.function:006':
      _verifyFormRules();
    case 'dart.function:007':
      final conversation = CodexConversationId('conversation');
      final approval = CodexPendingApproval(
        requestId: 'request',
        conversationId: conversation,
        title: 'Title',
        details: 'Details',
      );
      final copy = CodexPendingApproval(
        requestId: 'request',
        conversationId: conversation,
        title: 'Title',
        details: 'Details',
      );
      final state = CodexInteractionState(
        pending: [approval],
        resolvingRequestIds: ['request'],
      );
      expect(state.isResolving(approval), isTrue);
      expect(state.isResolving(copy), isFalse);
      expect(CodexInteractionState(pending: [approval]).isResolving(approval),
          isFalse);
    case 'dart.function:008':
      final conversation = CodexConversationId('conversation');
      final first = CodexPendingApproval(
        requestId: 'one',
        conversationId: conversation,
        title: 'One',
        details: '1',
      );
      final other = CodexPendingApproval(
        requestId: 'two',
        conversationId: CodexConversationId('other'),
        title: 'Two',
        details: '2',
      );
      final selected = CodexInteractionState(
        pending: [first, other, first],
      ).pendingFor(CodexConversationId('conversation'));
      expect(selected, hasLength(2));
      expect(selected[0], same(first));
      expect(selected[1], same(first));
      expect(() => selected.clear(), throwsUnsupportedError);
    case 'dart.function:009':
      const secret = 'do-not-print';
      final url = CodexAuthorizationUrl.chatGpt(
        'https://auth.openai.com/authorize?secret=$secret',
      );
      expect(url.purpose, CodexAuthorizationPurpose.chatGpt);
      expect(url.toString(), isNot(contains(secret)));
      for (final invalid in <String>[
        'http://openai.com/',
        'https://openai.com.evil.example/',
        'https://user@openai.com/',
        'https://openai.com:444/',
        'https://.openai.com/',
        'https://openai.com./',
      ]) {
        expect(
            () => CodexAuthorizationUrl.chatGpt(invalid), throwsArgumentError);
      }
    case 'dart.function:010':
      for (final valid in <String>[
        'https://accounts.example.com/oauth',
        'http://localhost:8787/callback',
        'http://127.0.0.1/callback',
        'http://[::1]:8787/callback',
      ]) {
        expect(CodexAuthorizationUrl.external(valid).value, valid);
      }
      for (final invalid in <String>[
        'http://192.168.1.2/login',
        'ftp://accounts.example.com/login',
        'https://user@accounts.example.com/login',
        'https://accounts.example.com:0/login',
        'https://accounts.example.com:65536/login',
        r'https://accounts.example.com\@evil.example/login',
        'https://accounts.example.com/space here',
        'https://accounts.example.com:\t/login',
      ]) {
        expect(
            () => CodexAuthorizationUrl.external(invalid), throwsArgumentError);
      }
    default:
      throw StateError('unknown Dart function behavior: $testId');
  }
}

void registerSynchronousValueFunctionParity(
  List<DartFunctionClaim> claims,
  Directory root,
  Map<String, Set<String>> passedCompilerEvidence,
  Set<String> passedTestIds,
) {
  test('dart.function.inventory', () {
    expect(() => verifyFunctionClaims(claims, root), returnsNormally);
  });
  test('dart.function inventory and references fail closed', () {
    expect(
        () => verifyFunctionClaims(claims.sublist(1), root), throwsStateError);
    expect(
      () => verifyFunctionClaims(<DartFunctionClaim>[
        claims.first,
        claims.first,
        ...claims.skip(2),
      ], root),
      throwsStateError,
    );
    final first = claims.first;
    DartFunctionClaim changed({
      List<String>? symbols,
      List<String>? tests,
      List<String>? evidence,
      List<String>? scenarios,
    }) =>
        DartFunctionClaim(
          capabilityKey: first.capabilityKey,
          publicSymbols: symbols ?? first.publicSymbols,
          executedTests: tests ?? first.executedTests,
          compilerEvidenceIds: evidence ?? first.compilerEvidenceIds,
          sharedScenarios: scenarios ?? first.sharedScenarios,
        );
    for (final replacement in <DartFunctionClaim>[
      changed(symbols: ['CodexRemoved.function']),
      changed(tests: ['dart.function:999']),
      changed(scenarios: ['remote-execution']),
      changed(
        evidence: <String>[
          ...first.compilerEvidenceIds
              .where((value) => !value.startsWith('c-header:')),
          'c-header:codex_agent_removed_function',
        ]..sort(),
      ),
      changed(
        evidence: <String>[
          ...first.compilerEvidenceIds
              .where((value) => !value.startsWith('cabi-fixture:')),
          'cabi-fixture:removed.native.test#stale[macosArm64]',
        ]..sort(),
      ),
      changed(
        evidence: <String>[
          ...first.compilerEvidenceIds.where(
            (value) => !value.startsWith('dart-analyzer-function:'),
          ),
          'dart-analyzer-function:999',
        ]..sort(),
      ),
    ]) {
      expect(
        () => verifyFunctionClaims(
          <DartFunctionClaim>[replacement, ...claims.skip(1)],
          root,
        ),
        throwsStateError,
      );
    }
    final staleCalls = Map<String, String>.of(functionCallSymbols)
      ..[functionCallSymbols.keys.first] = 'codex_agent_removed_function';
    expect(
      () => verifyFunctionClaims(claims, root, callSymbols: staleCalls),
      throwsStateError,
    );
    final publicSource = File(
      '${root.path}/codex-agent-runtime-desktop/bindings/dart/'
      'lib/src/residual_models.dart',
    ).readAsStringSync();
    final bridgeSource = File(
      '${root.path}/codex-agent-runtime-desktop/bindings/dart/'
      'lib/src/value_native.dart',
    ).readAsStringSync();
    expect(
      () => verifyFunctionClaims(
        claims,
        root,
        publicSourceOverride:
            "${publicSource.replaceFirst('nativeResponseFactory(', 'localResponseFactory(')}\n"
            "valueNativeCallObserver?.call('codex_agent_elicitation_response_cancel');\n",
      ),
      throwsStateError,
    );
    expect(
      () => verifyFunctionClaims(
        claims,
        root,
        bridgeSourceOverride:
            "${bridgeSource.replaceFirst("'codex_agent_elicitation_response_cancel'", "'codex_agent_removed_function'")}\n"
            "valueNativeCallObserver?.call('codex_agent_elicitation_response_cancel');\n",
      ),
      throwsStateError,
    );
    final missing = '${Directory.systemTemp.path}/missing-codex-agent-$pid';
    expect(
        () => resolveLibraryPathSync(missing), throwsA(isA<CodexException>()));
  });

  final sorted = claims.toList()
    ..sort((left, right) => left.capabilityKey.compareTo(right.capabilityKey));
  for (final claim in sorted) {
    final testId = claim.executedTests.single;
    test(testId, () {
      final calls = <String>[];
      valueNativeCallObserver = calls.add;
      try {
        _verifyBehavior(testId);
      } finally {
        valueNativeCallObserver = null;
      }
      final function = _functionName(claim.capabilityKey);
      expect(calls, contains(functionCallSymbols[function]));
      final symbol = claim.publicSymbols.single;
      for (final evidence in claim.compilerEvidenceIds) {
        passedCompilerEvidence
            .putIfAbsent(evidence, () => <String>{})
            .add(symbol);
      }
      expect(passedTestIds.add(testId), isTrue);
    });
  }
}
