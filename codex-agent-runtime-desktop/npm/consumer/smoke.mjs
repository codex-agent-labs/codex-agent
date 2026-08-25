import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import test from 'node:test';
import * as sdk from '@codex-agent-labs/codex-agent';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const packageEntry = require.resolve('@codex-agent-labs/codex-agent');
const packageRoot = path.dirname(packageEntry);
const declarationFile = path.join(packageRoot, 'index.d.ts');
const commonJsFile = path.join(packageRoot, 'index.cjs');
const esmFile = path.join(packageRoot, 'index.mjs');
const packageJsonFile = path.join(packageRoot, 'package.json');
const tarballFile = process.env.CODEX_AGENT_NPM_TARBALL;
const keywordTypeKinds = new Set([
  ts.SyntaxKind.AnyKeyword,
  ts.SyntaxKind.BigIntKeyword,
  ts.SyntaxKind.BooleanKeyword,
  ts.SyntaxKind.IntrinsicKeyword,
  ts.SyntaxKind.NeverKeyword,
  ts.SyntaxKind.NumberKeyword,
  ts.SyntaxKind.ObjectKeyword,
  ts.SyntaxKind.StringKeyword,
  ts.SyntaxKind.SymbolKeyword,
  ts.SyntaxKind.UndefinedKeyword,
  ts.SyntaxKind.UnknownKeyword,
  ts.SyntaxKind.VoidKeyword,
]);

function identity(file) {
  const bytes = fs.readFileSync(file);
  return {
    fileName: path.basename(file),
    bytes: bytes.length,
    sha256: createHash('sha256').update(bytes).digest('hex'),
  };
}

function hasModifier(node, kind) {
  return node.modifiers?.some((modifier) => modifier.kind === kind) === true;
}

function exported(node) {
  return ts.isExportAssignment(node) || ts.isExportDeclaration(node) || hasModifier(node, ts.SyntaxKind.ExportKeyword);
}

function nonPublicMember(node) {
  return (node.name && ts.isPrivateIdentifier(node.name)) ||
    hasModifier(node, ts.SyntaxKind.PrivateKeyword) ||
    hasModifier(node, ts.SyntaxKind.ProtectedKeyword);
}

function assertModifiers(node, allowed, context) {
  const unsupported = (node.modifiers ?? [])
    .filter((modifier) => !allowed.includes(modifier.kind))
    .map((modifier) => ts.SyntaxKind[modifier.kind]);
  assert.deepEqual(unsupported, [], `${context} has unsupported modifiers`);
}

function memberQualifiers(node, allowedModifiers, context) {
  assertModifiers(node, [ts.SyntaxKind.PublicKeyword, ...allowedModifiers], context);
  const qualifiers = [];
  if (node.questionToken) qualifiers.push('optional');
  if (hasModifier(node, ts.SyntaxKind.ReadonlyKeyword)) qualifiers.push('readonly');
  if (hasModifier(node, ts.SyntaxKind.StaticKeyword)) qualifiers.push('static');
  return qualifiers.length === 0 ? '' : `[${qualifiers.join(',')}]`;
}

function declarationName(node, source) {
  if (!node.name) return null;
  return ts.isIdentifier(node.name) || ts.isStringLiteralLike(node.name) || ts.isNumericLiteral(node.name)
    ? node.name.text
    : node.name.getText(source);
}

function renderType(node, source, aliases, substitutions = new Map(), expanding = new Set()) {
  if (ts.isTypeReferenceNode(node)) {
    const name = node.typeName.getText(source);
    if (ts.isIdentifier(node.typeName) && substitutions.has(name)) {
      assert.equal(node.typeArguments?.length ?? 0, 0, `Substituted type ${name} cannot have type arguments`);
      return substitutions.get(name);
    }
    const alias = ts.isIdentifier(node.typeName) ? aliases.get(name) : null;
    if (alias && !exported(alias)) {
      assert.ok(!expanding.has(alias), `Recursive non-exported type alias ${name} is unsupported`);
      const parameters = alias.typeParameters ?? [];
      const arguments_ = node.typeArguments ?? [];
      assert.equal(arguments_.length, parameters.length, `Type argument count differs for alias ${name}`);
      const aliasSubstitutions = new Map(substitutions);
      parameters.forEach((parameter, index) => {
        assert.equal(parameter.constraint, undefined, `Constrained non-exported alias ${name} is unsupported`);
        assert.equal(parameter.default, undefined, `Defaulted non-exported alias ${name} is unsupported`);
        aliasSubstitutions.set(parameter.name.text, renderType(arguments_[index], source, aliases, substitutions, expanding));
      });
      return renderType(alias.type, source, aliases, aliasSubstitutions, new Set([...expanding, alias]));
    }
    const arguments_ = node.typeArguments?.map((argument) => renderType(argument, source, aliases, substitutions, expanding));
    return `${name}${arguments_?.length ? `<${arguments_.join(', ')}>` : ''}`;
  }
  if (ts.isUnionTypeNode(node)) {
    return node.types.map((type) => renderType(type, source, aliases, substitutions, expanding)).join(' | ');
  }
  if (ts.isFunctionTypeNode(node)) {
    assert.equal(node.typeParameters?.length ?? 0, 0, 'Generic function types are unsupported');
    return `(${renderParameters(node.parameters, source, aliases, substitutions, expanding)}) => ${renderType(node.type, source, aliases, substitutions, expanding)}`;
  }
  if (ts.isParenthesizedTypeNode(node)) {
    return `(${renderType(node.type, source, aliases, substitutions, expanding)})`;
  }
  if (ts.isArrayTypeNode(node)) {
    const element = renderType(node.elementType, source, aliases, substitutions, expanding);
    return `${ts.isUnionTypeNode(node.elementType) ? `(${element})` : element}[]`;
  }
  if (ts.isTupleTypeNode(node)) {
    return `[${node.elements.map((element) => renderType(element, source, aliases, substitutions, expanding)).join(', ')}]`;
  }
  if (ts.isTypeOperatorNode(node)) {
    return `${ts.tokenToString(node.operator)} ${renderType(node.type, source, aliases, substitutions, expanding)}`;
  }
  if (ts.isTypeLiteralNode(node)) {
    const members = node.members.map((member) => {
      assert.ok(ts.isPropertySignature(member), 'Public type literals support only property signatures');
      assertModifiers(member, [ts.SyntaxKind.ReadonlyKeyword], 'Public type literal property');
      assert.ok(
        hasModifier(member, ts.SyntaxKind.ReadonlyKeyword),
        'Public type literal properties must be readonly',
      );
      assert.ok(ts.isIdentifier(member.name), 'Public type literal property names must be identifiers');
      assert.ok(member.type, `Public type literal property ${member.name.text} must have a type`);
      return `readonly ${member.name.text}${member.questionToken ? '?' : ''}: ${renderType(member.type, source, aliases, substitutions, expanding)}`;
    });
    return `{ ${members.join('; ')}; }`;
  }
  if (ts.isLiteralTypeNode(node) || ts.isThisTypeNode(node) || keywordTypeKinds.has(node.kind)) {
    return node.getText(source);
  }
  assert.fail(`Unsupported public TypeScript type: ${ts.SyntaxKind[node.kind]}`);
}

function renderParameters(parameters, source, aliases, substitutions = new Map(), expanding = new Set()) {
  return parameters.map((parameter) => {
    assertModifiers(parameter, [], `Parameter ${parameter.name.getText(source)}`);
    assert.equal(parameter.initializer, undefined, 'Public parameter initializers are unsupported');
    assert.ok(ts.isIdentifier(parameter.name), 'Public parameter binding patterns are unsupported');
    assert.ok(parameter.type, `Public parameter ${parameter.name.text} must have a type`);
    return `${parameter.dotDotDotToken ? '...' : ''}${parameter.name.text}${parameter.questionToken ? '?' : ''}: ${renderType(parameter.type, source, aliases, substitutions, expanding)}`;
  }).join(', ');
}

function renderSignature(declaration, source, aliases, context) {
  assert.equal(declaration.typeParameters?.length ?? 0, 0, `Generic ${context} is unsupported`);
  assert.ok(declaration.type, `${context} must have an explicit return type`);
  return `(${renderParameters(declaration.parameters, source, aliases)}): ${renderType(declaration.type, source, aliases)}`;
}

function discoverPublicApi(source) {
  const aliases = new Map(
    source.statements
      .filter(ts.isTypeAliasDeclaration)
      .map((declaration) => [declaration.name.text, declaration]),
  );
  const publicSymbols = [];
  const symbolsByDeclaration = new Map();
  const typeExports = [];
  const valueExports = [];

  function recordPublicSymbol(declaration, symbol) {
    publicSymbols.push(symbol);
    assert.ok(!symbolsByDeclaration.has(declaration), `Public declaration was recorded twice: ${symbol}`);
    symbolsByDeclaration.set(declaration, symbol);
  }

  for (const declaration of source.statements) {
    if (!exported(declaration)) continue;
    const name = declarationName(declaration, source);
    assert.ok(name, `Exported TypeScript declaration must be named: ${ts.SyntaxKind[declaration.kind]}`);
    if (ts.isClassDeclaration(declaration)) {
      assertModifiers(
        declaration,
        [ts.SyntaxKind.ExportKeyword, ts.SyntaxKind.DeclareKeyword],
        `Exported TypeScript class ${name}`,
      );
      assert.equal(declaration.typeParameters?.length ?? 0, 0, `Unsupported type parameters on class ${name}`);
      typeExports.push(name);
      valueExports.push(name);
      const heritage = (declaration.heritageClauses ?? []).map((clause) => {
        const label = clause.token === ts.SyntaxKind.ExtendsKeyword ? 'extends' :
          clause.token === ts.SyntaxKind.ImplementsKeyword ? 'implements' : null;
        assert.ok(label, `Unsupported heritage clause on class ${name}`);
        assert.ok(clause.types.length > 0, `Empty heritage clause on class ${name}`);
        return `${label}=${clause.types.map((type) => type.getText(source).replace(/\s+/g, ' ')).join(',')}`;
      });
      recordPublicSymbol(
        declaration,
        `class:${name}${heritage.length === 0 ? '' : `:${heritage.join(':')}`}`,
      );
      for (const member of declaration.members) {
        if (nonPublicMember(member)) continue;
        if (ts.isConstructorDeclaration(member)) {
          memberQualifiers(member, [], `Constructor ${name}`);
          assert.equal(member.typeParameters?.length ?? 0, 0, `Generic constructor ${name} is unsupported`);
          recordPublicSymbol(member, `constructor:${name}#(${renderParameters(member.parameters, source, aliases)})`);
          continue;
        }
        const memberName = declarationName(member, source);
        assert.ok(memberName, `Public member of ${name} must be named: ${ts.SyntaxKind[member.kind]}`);
        if (ts.isMethodDeclaration(member)) {
          const qualifiers = memberQualifiers(
            member,
            [ts.SyntaxKind.StaticKeyword],
            `Method ${name}.${memberName}`,
          );
          recordPublicSymbol(
            member,
            `method:${name}#${memberName}${qualifiers}:${renderSignature(member, source, aliases, `method ${name}.${memberName}`)}`,
          );
        } else if (ts.isGetAccessorDeclaration(member)) {
          const qualifiers = memberQualifiers(
            member,
            [ts.SyntaxKind.StaticKeyword],
            `Getter ${name}.${memberName}`,
          );
          assert.ok(member.type, `Getter ${name}.${memberName} must have an explicit type`);
          recordPublicSymbol(
            member,
            `getter:${name}#${memberName}${qualifiers}:${renderType(member.type, source, aliases)}`,
          );
        } else if (ts.isPropertyDeclaration(member)) {
          const qualifiers = memberQualifiers(
            member,
            [ts.SyntaxKind.ReadonlyKeyword, ts.SyntaxKind.StaticKeyword],
            `Property ${name}.${memberName}`,
          );
          assert.ok(member.type, `Property ${name}.${memberName} must have an explicit type`);
          recordPublicSymbol(
            member,
            `property:${name}#${memberName}${qualifiers}:${renderType(member.type, source, aliases)}`,
          );
        } else {
          assert.fail(`Unsupported public TypeScript class member: ${name}.${memberName} (${ts.SyntaxKind[member.kind]})`);
        }
      }
    } else if (ts.isFunctionDeclaration(declaration)) {
      assertModifiers(
        declaration,
        [ts.SyntaxKind.ExportKeyword, ts.SyntaxKind.DeclareKeyword],
        `Exported TypeScript function ${name}`,
      );
      valueExports.push(name);
      recordPublicSymbol(
        declaration,
        `function:${name}:${renderSignature(declaration, source, aliases, `function ${name}`)}`,
      );
    } else if (ts.isTypeAliasDeclaration(declaration)) {
      assertModifiers(declaration, [ts.SyntaxKind.ExportKeyword], `Exported TypeScript type ${name}`);
      assert.equal(declaration.typeParameters?.length ?? 0, 0, `Unsupported type parameters on type ${name}`);
      typeExports.push(name);
      recordPublicSymbol(declaration, `type:${name}:${renderType(declaration.type, source, aliases)}`);
    } else {
      assert.fail(`Unsupported exported TypeScript declaration: ${ts.SyntaxKind[declaration.kind]} ${name}`);
    }
  }

  const sortedSymbols = publicSymbols.sort();
  assert.equal(new Set(sortedSymbols).size, sortedSymbols.length, 'Public TypeScript symbols must be unique');
  assert.ok(sortedSymbols.length > 0, 'Public TypeScript symbol inventory must not be empty');
  return {
    typeExports: typeExports.sort(),
    valueExports: valueExports.sort(),
    publicSymbols: sortedSymbols,
    symbolsByDeclaration,
  };
}

function compilerConsumerReferences(program, declarationSource, symbolsByDeclaration) {
  const checker = program.getTypeChecker();
  const consumerPath = path.resolve(process.cwd(), 'smoke.ts');
  const consumer = program.getSourceFiles().filter((source) => path.resolve(source.fileName) === consumerPath);
  assert.equal(consumer.length, 1, 'The compiled TypeScript consumer must contain exactly smoke.ts');
  const references = new Set();

  function recordDeclaration(declaration) {
    if (!declaration || declaration.getSourceFile() !== declarationSource) return;
    const publicSymbol = symbolsByDeclaration.get(declaration);
    assert.ok(publicSymbol, `Compiled consumer reached an unreported public declaration: ${declaration.getText(declarationSource)}`);
    references.add(publicSymbol);
  }

  function invocationTarget(identifier) {
    const parent = identifier.parent;
    if ((ts.isCallExpression(parent) || ts.isNewExpression(parent)) && parent.expression === identifier) return true;
    if (ts.isPropertyAccessExpression(parent) && parent.name === identifier) {
      const invocation = parent.parent;
      return (ts.isCallExpression(invocation) || ts.isNewExpression(invocation)) && invocation.expression === parent;
    }
    return false;
  }

  function importBinding(identifier) {
    const parent = identifier.parent;
    return ts.isImportSpecifier(parent) || ts.isImportClause(parent) || ts.isNamespaceImport(parent);
  }

  function resolvedSymbol(identifier) {
    let symbol = checker.getSymbolAtLocation(identifier);
    if (!symbol) return null;
    if ((symbol.flags & ts.SymbolFlags.Alias) !== 0) symbol = checker.getAliasedSymbol(symbol);
    return symbol;
  }

  function visit(node) {
    if (ts.isCallExpression(node) || ts.isNewExpression(node)) {
      recordDeclaration(checker.getResolvedSignature(node)?.declaration);
    } else if (ts.isIdentifier(node) && !invocationTarget(node) && !importBinding(node)) {
      const declarations = resolvedSymbol(node)?.declarations?.filter(
        (declaration) => declaration.getSourceFile() === declarationSource,
      ) ?? [];
      assert.ok(declarations.length <= 1, `Compiled consumer reference is ambiguous: ${node.text}`);
      declarations.forEach(recordDeclaration);
    }
    ts.forEachChild(node, visit);
  }

  visit(consumer[0]);
  const result = [...references].sort();
  assert.ok(result.length > 0, 'The compiled TypeScript consumer did not reference the installed public API');
  return result;
}

function compilerPublicApi() {
  const configFile = path.join(process.cwd(), 'tsconfig.json');
  const config = ts.readConfigFile(configFile, ts.sys.readFile);
  assert.equal(config.error, undefined, 'TypeScript configuration must parse');
  const parsed = ts.parseJsonConfigFileContent(config.config, ts.sys, process.cwd(), undefined, configFile);
  assert.deepEqual(parsed.errors, [], 'TypeScript configuration must be valid');
  const program = ts.createProgram({
    rootNames: [...new Set([...parsed.fileNames, declarationFile])],
    options: parsed.options,
  });
  const diagnostics = ts.getPreEmitDiagnostics(program);
  assert.deepEqual(
    diagnostics.map((diagnostic) => ts.flattenDiagnosticMessageText(diagnostic.messageText, '\n')),
    [],
    'The installed SDK and TypeScript consumer must compile without diagnostics',
  );
  const negativeConsumer = path.resolve(process.cwd(), 'negative.ts');
  assert.equal(
    program.getSourceFiles().filter((candidate) => path.resolve(candidate.fileName) === negativeConsumer).length,
    1,
    'The negative TypeScript consumer must be compiled but excluded from positive references',
  );
  const source = program.getSourceFile(declarationFile);
  assert.ok(source, 'The installed declaration must belong to the compiler program');
  const discovered = discoverPublicApi(source);
  return {
    typeExports: discovered.typeExports,
    valueExports: discovered.valueExports,
    publicSymbols: discovered.publicSymbols,
    referencedSymbols: compilerConsumerReferences(program, source, discovered.symbolsByDeclaration),
  };
}

test('esm exposes the same runtime values as CommonJS', () => {
  const commonJsSdk = require('@codex-agent-labs/codex-agent');
  const commonJsExports = Object.getOwnPropertyNames(commonJsSdk).sort();
  const esmExports = Object.keys(sdk).sort();
  assert.deepEqual(esmExports, commonJsExports);
  assert.equal(sdk.AgentConnector, commonJsSdk.AgentConnector);
  assert.equal(sdk.AgentConversation, commonJsSdk.AgentConversation);
  assert.equal(sdk.AgentConversationSummary, commonJsSdk.AgentConversationSummary);
  assert.equal(sdk.AgentPluginInvocation, commonJsSdk.AgentPluginInvocation);
  assert.equal(sdk.AgentSkillInvocation, commonJsSdk.AgentSkillInvocation);
  assert.equal(sdk.AgentModel, commonJsSdk.AgentModel);
  assert.equal(sdk.AgentServiceTier, commonJsSdk.AgentServiceTier);
  assert.equal(sdk.AgentSkill, commonJsSdk.AgentSkill);
  assert.equal(sdk.AgentSkillCatalog, commonJsSdk.AgentSkillCatalog);
  assert.equal(sdk.AgentSkillChunk, commonJsSdk.AgentSkillChunk);
  assert.equal(sdk.AgentElicitationValidation, commonJsSdk.AgentElicitationValidation);
  assert.equal(sdk.AgentElicitationValidationIssue, commonJsSdk.AgentElicitationValidationIssue);
  assert.equal(sdk.AgentFormOption, commonJsSdk.AgentFormOption);
  assert.equal(sdk.AgentFormTextValue, commonJsSdk.AgentFormTextValue);
  assert.equal(sdk.AgentFormNumberValue, commonJsSdk.AgentFormNumberValue);
  assert.equal(sdk.AgentFormBooleanValue, commonJsSdk.AgentFormBooleanValue);
  assert.equal(sdk.AgentFormTextListValue, commonJsSdk.AgentFormTextListValue);
  assert.equal(sdk.AgentHookActivity, commonJsSdk.AgentHookActivity);
  assert.equal(sdk.AgentHook, commonJsSdk.AgentHook);
  assert.equal(sdk.AgentHookCatalog, commonJsSdk.AgentHookCatalog);
  assert.equal(sdk.AgentMcpEnvironmentVariable, commonJsSdk.AgentMcpEnvironmentVariable);
  assert.equal(sdk.AgentMcpOauthConfiguration, commonJsSdk.AgentMcpOauthConfiguration);
  assert.equal(sdk.AgentMcpToolConfiguration, commonJsSdk.AgentMcpToolConfiguration);
  assert.equal(sdk.AgentPlanProgress, commonJsSdk.AgentPlanProgress);
  assert.equal(sdk.AgentPlanStep, commonJsSdk.AgentPlanStep);
  assert.equal(sdk.CodexAgent.prototype.rename, commonJsSdk.CodexAgent.prototype.rename);
  assert.equal(sdk.CodexAgent.prototype.delete, commonJsSdk.CodexAgent.prototype.delete);
  assert.equal(
    sdk.CodexAgent.prototype.listConversations,
    commonJsSdk.CodexAgent.prototype.listConversations,
  );
  assert.equal(
    sdk.CodexAgent.prototype.readConversation,
    commonJsSdk.CodexAgent.prototype.readConversation,
  );
  assert.equal(sdk.CodexConnectors, commonJsSdk.CodexConnectors);
  assert.equal(sdk.CodexModels, commonJsSdk.CodexModels);
  assert.equal(sdk.CodexSkills, commonJsSdk.CodexSkills);
  assert.equal(sdk.CodexHooks, commonJsSdk.CodexHooks);
  assert.equal(
    Object.getOwnPropertyDescriptor(sdk.CodexAgent.prototype, 'skills').get,
    Object.getOwnPropertyDescriptor(commonJsSdk.CodexAgent.prototype, 'skills').get,
  );
  assert.equal(sdk.CodexSkills.prototype.list, commonJsSdk.CodexSkills.prototype.list);
  assert.equal(sdk.CodexSkills.prototype.read, commonJsSdk.CodexSkills.prototype.read);
  assert.equal(sdk.CodexSkills.prototype.install, commonJsSdk.CodexSkills.prototype.install);
  assert.equal(sdk.CodexSkills.prototype.uninstall, commonJsSdk.CodexSkills.prototype.uninstall);
  assert.equal(
    Object.getOwnPropertyDescriptor(sdk.CodexAgent.prototype, 'hooks').get,
    Object.getOwnPropertyDescriptor(commonJsSdk.CodexAgent.prototype, 'hooks').get,
  );
  assert.equal(sdk.CodexHooks.prototype.list, commonJsSdk.CodexHooks.prototype.list);
  assert.equal(sdk.CodexHooks.prototype.install, commonJsSdk.CodexHooks.prototype.install);
  assert.equal(sdk.CodexHooks.prototype.uninstall, commonJsSdk.CodexHooks.prototype.uninstall);
  assert.equal(sdk.CodexHooks.prototype.trust, commonJsSdk.CodexHooks.prototype.trust);
  assert.equal(
    sdk.codexApprovalPresetDisplayName,
    commonJsSdk.codexApprovalPresetDisplayName,
  );
  assert.equal(
    sdk.agentSkillScopeDisplayName,
    commonJsSdk.agentSkillScopeDisplayName,
  );
  for (const name of [
    'agentCapabilityId',
    'agentCapabilityDisplayLabel',
    'agentCapabilityIcon',
    'agentCapabilityPromptLabel',
  ]) {
    assert.equal(sdk[name], commonJsSdk[name]);
  }
  const sourceHandler = { type: 'command', command: './check', isAsync: false };
  const hook = new sdk.AgentHook(
    'esm-hook', 'sha256:esm', true, 'preToolUse', sourceHandler, false,
    'PROJECT', '/workspace/.codex/hooks.json', 10n, 'untrusted',
  );
  sourceHandler.command = 'changed';
  assert.deepEqual(hook.handler, { type: 'command', command: './check', isAsync: false });
  assert.equal(hook.origin, 'workspace');
  assert.equal(hook.canTrust, true);
  assert.equal(Object.isFrozen(hook), true);
  assert.equal(Object.isFrozen(hook.handler), true);
  const catalog = new sdk.AgentHookCatalog([hook], ['warning'], ['error']);
  assert.deepEqual(catalog.hooks.map(({ key }) => key), ['esm-hook']);
  assert.deepEqual(catalog.warnings, ['warning']);
  assert.deepEqual(catalog.errors, ['error']);
  assert.equal(Object.isFrozen(catalog), true);
  assert.equal(Object.isFrozen(catalog.hooks), true);
  assert.throws(
    () => new sdk.AgentHook(
      'bad', 'hash', false, 'stop', { type: 'future' }, false,
      'USER', '/hooks.json', 10n, 'trusted',
    ),
    (error) => error?.message === 'Unknown hook handler type: future',
  );
  assert.throws(
    () => new sdk.AgentHook(
      'bad', 'hash', false, 'stop', { type: 'prompt' }, false,
      'USER', '/hooks.json', 10, 'trusted',
    ),
    (error) => error?.message === 'timeoutSeconds must be a bigint',
  );
  for (const [preset, displayName] of [
    ['never', 'Never'],
    ['auto_review', 'Auto review'],
    ['ask_me', 'Ask me'],
    ['strict', 'Strict'],
  ]) {
    assert.equal(sdk.codexApprovalPresetDisplayName(preset), displayName);
    assert.equal(commonJsSdk.codexApprovalPresetDisplayName(preset), displayName);
  }
  for (const [scope, displayName] of [
    ['admin', 'Managed'],
    ['plugin', 'Plugin'],
    ['repo', 'Workspace'],
    ['system', 'Built in'],
    ['user', 'User'],
  ]) {
    assert.equal(sdk.agentSkillScopeDisplayName(scope), displayName);
    assert.equal(commonJsSdk.agentSkillScopeDisplayName(scope), displayName);
  }
  for (const [invalid, message] of [
    ['unknown', 'Unknown skill scope: unknown'],
    ['SYSTEM', 'Unknown skill scope: SYSTEM'],
    [0, 'scope must be a string'],
    [null, 'scope must be a string'],
    [undefined, 'scope must be a string'],
    [new String('system'), 'scope must be a string'],
    [new Proxy({}, {}), 'scope must be a string'],
  ]) {
    assert.throws(
      () => sdk.agentSkillScopeDisplayName(invalid),
      (error) => error?.message === message,
    );
    assert.throws(
      () => commonJsSdk.agentSkillScopeDisplayName(invalid),
      (error) => error?.message === message,
    );
  }
  for (const [name, expected] of [
    ['agentCapabilityId', 'web_search'],
    ['agentCapabilityDisplayLabel', 'Web search'],
    ['agentCapabilityIcon', '🌐'],
    ['agentCapabilityPromptLabel', 'Use 🌐 Web search'],
  ]) {
    assert.equal(sdk[name]('web_search'), expected);
    assert.equal(commonJsSdk[name]('web_search'), expected);
    for (const [invalid, message] of [
      ['unknown', 'Unknown agent capability: unknown'],
      ['WEB_SEARCH', 'Unknown agent capability: WEB_SEARCH'],
      [0, 'capability must be a string'],
      [null, 'capability must be a string'],
      [undefined, 'capability must be a string'],
      [new String('web_search'), 'capability must be a string'],
      [new Proxy({}, {}), 'capability must be a string'],
    ]) {
      assert.throws(() => sdk[name](invalid), (error) => error?.message === message);
      assert.throws(() => commonJsSdk[name](invalid), (error) => error?.message === message);
    }
  }
  const skillInvocation = new sdk.AgentSkillInvocation('review', '/skills/review/SKILL.md');
  const pluginInvocation = new sdk.AgentPluginInvocation('tools', 'plugin://tools@official');
  assert.deepEqual(
    [skillInvocation.name, skillInvocation.path, skillInvocation.key],
    ['review', '/skills/review/SKILL.md', 'skill:/skills/review/SKILL.md'],
  );
  assert.deepEqual(
    [pluginInvocation.name, pluginInvocation.uri, pluginInvocation.key],
    ['tools', 'plugin://tools@official', 'plugin:plugin://tools@official'],
  );
  for (const invocation of [skillInvocation, pluginInvocation]) {
    assert.equal(Object.isFrozen(invocation), true);
    assert.deepEqual(Object.keys(invocation), []);
  }
  assert.equal(typeof sdk.CodexHost, 'function');
  assert.equal(typeof sdk.CodexAuthentication, 'function');
  assert.equal(typeof sdk.CodexAuthenticationState, 'function');
  assert.equal(typeof sdk.createCodexHost, 'function');
});

test('typescript compiler discovers the exact installed public API', () => {
  assert.ok(tarballFile, 'The exact npm tarball path must be supplied by Gradle');
  const compilerApi = compilerPublicApi();
  const commonJsExports = Object.getOwnPropertyNames(require('@codex-agent-labs/codex-agent')).sort();
  const esmExports = Object.keys(sdk).sort();
  assert.deepEqual(commonJsExports, compilerApi.valueExports);
  assert.deepEqual(esmExports, compilerApi.valueExports);
  assert.deepEqual(
    [...new Set(compilerApi.referencedSymbols)].sort(),
    compilerApi.referencedSymbols,
    'Compiled consumer references must be exact, sorted, and unique',
  );
  assert.ok(
    compilerApi.referencedSymbols.every((symbol) => compilerApi.publicSymbols.includes(symbol)),
    'Compiled consumer references must belong to the installed public API',
  );
  assert.ok(
    compilerApi.referencedSymbols.length < compilerApi.publicSymbols.length,
    'Unreferenced and future public symbols must not be absorbed into consumer evidence',
  );
  assert.ok(
    !compilerApi.referencedSymbols.includes('getter:CodexAgent#workspace:CodexWorkspace'),
    'Expected-error-only TypeScript usage must not become positive projection evidence',
  );
  assert.ok(!compilerApi.typeExports.includes('Nullable'), 'Unexported aliases must stay outside the public API');
  assert.ok(compilerApi.publicSymbols.includes('class:CodexError:extends=Error'));
  assert.ok(compilerApi.publicSymbols.includes('property:CodexError#cause[optional,readonly]:unknown'));
  const hostStatus = compilerApi.publicSymbols
    .find((symbol) => symbol.startsWith('type:CodexHostStatus:'))
    ?.slice('type:CodexHostStatus:'.length);
  assert.deepEqual(
    new Set(hostStatus?.split(' | ')),
    new Set(['"new"', '"restoring"', '"workspace_required"', '"preparing"', '"ready"', '"failed"', '"closed"']),
    'Type aliases must expand to their exact union members',
  );
  const authenticationMethod = compilerApi.publicSymbols
    .find((symbol) => symbol.startsWith('type:CodexAuthenticationMethod:'))
    ?.slice('type:CodexAuthenticationMethod:'.length);
  assert.deepEqual(
    new Set(authenticationMethod?.split(' | ')),
    new Set(['"chatgpt_browser"', '"chatgpt_device_code"', '"api_key"']),
    'Authentication methods must remain a closed typed domain',
  );
  const authenticationStatus = compilerApi.publicSymbols
    .find((symbol) => symbol.startsWith('type:CodexAuthenticationStatus:'))
    ?.slice('type:CodexAuthenticationStatus:'.length);
  assert.deepEqual(
    new Set(authenticationStatus?.split(' | ')),
    new Set(['"signed_out"', '"authenticating"', '"authenticated"']),
    'Authentication statuses must remain a closed typed domain',
  );
  assert.ok(
    compilerApi.publicSymbols.some((symbol) =>
      symbol.startsWith('getter:CodexHostState#workspace:') && symbol.includes('null') && symbol.includes('undefined')),
    'Nullable aliases must expand at their use sites',
  );
  assert.ok(compilerApi.publicSymbols.includes(
    'method:CodexAgent#openConversation:(conversationId?: string | null | undefined, approvalPreset?: CodexApprovalPreset | null | undefined, serviceTier?: string | null | undefined, signal?: AbortSignal | null | undefined): Promise<CodexConversation>',
  ), 'Nested method parameter aliases must expand structurally');
  assert.ok(compilerApi.publicSymbols.includes(
    'method:CodexAgent#rename:(conversationId: string, name: string, signal?: AbortSignal | null | undefined): Promise<void>',
  ), 'Conversation rename must preserve typed IDs, names, and AbortSignal cancellation');
  assert.ok(compilerApi.publicSymbols.includes(
    'method:CodexAgent#delete:(conversationId: string, signal?: AbortSignal | null | undefined): Promise<void>',
  ), 'Conversation deletion must preserve typed IDs and AbortSignal cancellation');
  assert.ok(compilerApi.publicSymbols.includes(
    'constructor:AgentConversationSummary#(conversationId: string, title: string, updatedAtEpochSeconds: bigint)',
  ), 'Conversation summaries must preserve typed IDs, titles, and bigint timestamps');
  assert.ok(compilerApi.publicSymbols.includes(
    'constructor:AgentConversation#(summary: AgentConversationSummary, messages: ReadonlyArray<CodexMessage>)',
  ), 'Historical conversations must preserve their summary and immutable message collection');
  assert.ok(compilerApi.publicSymbols.includes(
    'getter:AgentConversation#summary:AgentConversationSummary',
  ), 'Historical conversation summaries must remain readonly');
  assert.ok(compilerApi.publicSymbols.includes(
    'getter:AgentConversation#messages:ReadonlyArray<CodexMessage>',
  ), 'Historical conversation messages must remain readonly');
  assert.ok(compilerApi.publicSymbols.includes(
    'method:CodexAgent#listConversations:(signal?: AbortSignal | null | undefined): Promise<ReadonlyArray<AgentConversationSummary>>',
  ), 'Conversation listing must preserve cancellation and immutable result semantics');
  assert.ok(compilerApi.publicSymbols.includes(
    'method:CodexAgent#readConversation:(conversationId: string, signal?: AbortSignal | null | undefined): Promise<AgentConversation>',
  ), 'Conversation reading must preserve typed IDs, cancellation, and immutable result semantics');
  assert.ok(compilerApi.publicSymbols.includes(
    'function:codexApprovalPresetDisplayName:(preset: CodexApprovalPreset): string',
  ), 'Approval-preset display names must preserve the finite preset domain');
  assert.ok(compilerApi.publicSymbols.includes(
    'function:agentSkillScopeDisplayName:(scope: AgentSkillScope): string',
  ), 'Skill-scope display names must preserve the finite scope domain');
  assert.ok(compilerApi.publicSymbols.includes(
    'constructor:AgentConnector#(id: string, name: string, description?: string, installUrl?: string | null | undefined, isAccessible?: boolean, isEnabled?: boolean, pluginNames?: ReadonlyArray<string>)',
  ), 'Connector values must preserve canonical defaults and immutable plugin names');
  assert.ok(compilerApi.publicSymbols.includes(
    'getter:CodexAgent#connectors:CodexConnectors',
  ), 'Connector controller ownership must be discoverable from an Agent');
  assert.ok(compilerApi.publicSymbols.includes(
    'method:CodexConnectors#list:(forceReload?: boolean, signal?: AbortSignal | null | undefined): Promise<ReadonlyArray<AgentConnector>>',
  ), 'Connector listing must preserve reload, cancellation, and immutable result semantics');
  assert.ok(compilerApi.publicSymbols.includes(
    'constructor:AgentModel#(id: string, displayName: string, description: string, supportedEfforts: ReadonlyArray<string>, defaultEffort: string, isDefault: boolean, serviceTiers?: ReadonlyArray<AgentServiceTier>, defaultServiceTier?: string | null | undefined)',
  ), 'Models must preserve canonical defaults and immutable nested collections');
  assert.ok(compilerApi.publicSymbols.includes(
    'getter:CodexAgent#models:CodexModels',
  ), 'Model controller ownership must be discoverable from an Agent');
  assert.ok(compilerApi.publicSymbols.includes(
    'method:CodexModels#list:(signal?: AbortSignal | null | undefined): Promise<ReadonlyArray<AgentModel>>',
  ), 'Model listing must preserve cancellation and immutable result semantics');
  assert.ok(compilerApi.publicSymbols.includes(
    'method:CodexModels#resolveServiceTier:(model: AgentModel, resolution?: AgentResolution, signal?: AbortSignal | null | undefined): Promise<AgentServiceTier | null | undefined>',
  ), 'Service-tier resolution must preserve typed resolution, cancellation, and nullability');
  assert.ok(compilerApi.publicSymbols.includes(
    'constructor:AgentSkill#(name: string, displayName: string, description: string, path: string, scope: AgentSkillScope, isEnabled: boolean, brandColor?: string | null | undefined, dependencies?: ReadonlyArray<string>, canUninstall?: boolean, origin?: AgentResourceOrigin)',
  ), 'Skills must preserve enum domains, canonical defaults, and immutable dependencies');
  assert.ok(compilerApi.publicSymbols.includes(
    'constructor:AgentSkillCatalog#(skills: ReadonlyArray<AgentSkill>, errors?: ReadonlyArray<string>)',
  ), 'Skill catalogs must preserve immutable nested skills and errors');
  assert.ok(compilerApi.publicSymbols.includes(
    'constructor:AgentSkillChunk#(content: string, nextOffset: bigint | null | undefined, totalBytes: bigint)',
  ), 'Skill chunks must preserve nullable bigint offsets and bigint totals');
  assert.ok(compilerApi.publicSymbols.includes(
    'getter:CodexAgent#skills:CodexSkills',
  ), 'Skill controller ownership must be discoverable from an Agent');
  assert.ok(compilerApi.publicSymbols.includes(
    'method:CodexSkills#list:(forceReload?: boolean, signal?: AbortSignal | null | undefined): Promise<AgentSkillCatalog>',
  ), 'Skill listing must preserve reload, cancellation, and immutable catalog semantics');
  assert.ok(compilerApi.publicSymbols.includes(
    'method:CodexSkills#read:(path: string, offset?: bigint, signal?: AbortSignal | null | undefined): Promise<AgentSkillChunk>',
  ), 'Skill reading must preserve path, bigint offset, and cancellation semantics');
  assert.ok(compilerApi.publicSymbols.includes(
    'method:CodexSkills#install:(directory: string, scope: AgentInstallationScope, signal?: AbortSignal | null | undefined): Promise<AgentSkill>',
  ), 'Skill installation must preserve the finite installation scope and cancellation');
  assert.ok(compilerApi.publicSymbols.includes(
    'method:CodexSkills#uninstall:(skill: AgentSkill, signal?: AbortSignal | null | undefined): Promise<void>',
  ), 'Skill uninstallation must preserve canonical skill identity and cancellation');
  assert.ok(compilerApi.publicSymbols.includes(
    'type:AgentHookHandler:{ readonly type: "agent"; } | { readonly type: "command"; readonly command: string; readonly isAsync: boolean; } | { readonly type: "mcp_tool"; readonly server: string; readonly tool: string; } | { readonly type: "prompt"; }',
  ), 'Hook handlers must preserve the exact readonly discriminated union');
  assert.ok(compilerApi.publicSymbols.includes(
    'constructor:AgentHook#(key: string, currentHash: string, isEnabled: boolean, eventName: string, handler: AgentHookHandler, isManaged: boolean, source: string, sourcePath: string, timeoutSeconds: bigint, trustStatus: AgentHookTrustStatus, matcher?: string | null | undefined, pluginId?: string | null | undefined, statusMessage?: string | null | undefined, origin?: AgentResourceOrigin, canUninstall?: boolean)',
  ), 'Hooks must preserve canonical defaults, bigint timeout, and finite domains');
  assert.ok(compilerApi.publicSymbols.includes(
    'constructor:AgentHookCatalog#(hooks: ReadonlyArray<AgentHook>, warnings?: ReadonlyArray<string>, errors?: ReadonlyArray<string>)',
  ), 'Hook catalogs must preserve immutable nested values and diagnostics');
  assert.ok(compilerApi.publicSymbols.includes(
    'getter:CodexAgent#hooks:CodexHooks',
  ), 'Hook controller ownership must be discoverable from an Agent');
  assert.ok(compilerApi.publicSymbols.includes(
    'method:CodexHooks#trust:(hook: AgentHook, signal?: AbortSignal | null | undefined): Promise<void>',
  ), 'Hook trust must preserve canonical hook identity and cancellation');
  assert.ok(compilerApi.publicSymbols.includes(
    'getter:CodexAgent#authentication:CodexAuthentication',
  ), 'Agent authentication ownership must be discoverable');
  assert.ok(compilerApi.publicSymbols.includes(
    'method:CodexAuthentication#authenticate:(method?: "chatgpt_browser" | null | undefined, apiKey?: null, signal?: AbortSignal | null | undefined): Promise<void>',
  ), 'Default and browser authentication must forbid API keys');
  assert.ok(compilerApi.publicSymbols.includes(
    'method:CodexAuthentication#authenticate:(method: "chatgpt_device_code", apiKey?: null, signal?: AbortSignal | null | undefined): Promise<void>',
  ), 'Device-code authentication must forbid API keys');
  assert.ok(compilerApi.publicSymbols.includes(
    'method:CodexAuthentication#authenticate:(method: "api_key", apiKey: string, signal?: AbortSignal | null | undefined): Promise<void>',
  ), 'API-key authentication must require a key and preserve AbortSignal cancellation');
  assert.ok(compilerApi.publicSymbols.includes(
    'method:CodexAuthentication#observeState:(listener: (state: CodexAuthenticationState) => void): CodexObservation',
  ), 'Authentication state observation must be discoverable');
  assert.ok(compilerApi.publicSymbols.includes(
    'getter:CodexAuthenticationState#failure:CodexFailure | null | undefined',
  ), 'Authentication structured state failure must be discoverable');
  assert.ok(compilerApi.publicSymbols.includes(
    'type:AgentTurnRequest:{ readonly prompt: string; readonly clientMessageId?: string | null | undefined; readonly model?: string | null | undefined; readonly effort?: string | null | undefined; readonly serviceTier?: string | null | undefined; readonly approvalPreset?: CodexApprovalPreset; readonly capabilities?: ReadonlyArray<AgentCapability>; readonly invocations?: ReadonlyArray<AgentInvocation>; readonly collaborationMode?: AgentCollaborationMode; }',
  ), 'Structured turn requests must preserve exact readonly fields, defaults, and finite domains');
  const privateSurface = ts.createSourceFile(
    'private-surface.d.ts',
    'export declare class Visible { private constructor(); protected hidden(): void; #secret: string; }',
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  assert.deepEqual(discoverPublicApi(privateSurface).publicSymbols, ['class:Visible']);
  const anonymousExport = ts.createSourceFile(
    'anonymous-export.d.ts',
    'export default class {}',
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  assert.throws(() => discoverPublicApi(anonymousExport), /must be named/);
  const unsupportedMember = ts.createSourceFile(
    'unsupported-member.d.ts',
    'export declare class Mutable { set value(value: string); }',
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  assert.throws(() => discoverPublicApi(unsupportedMember), /Unsupported public TypeScript class member/);
  for (const declarationText of [
    'export type Mutable = { value: string };',
    'export type Method = { readonly run: string; execute(): void };',
    'export type Indexed = { readonly [key: string]: string };',
    'export type Callable = { (): void };',
    'export type Modified = { public readonly value: string };',
  ]) {
    const unsupportedTypeLiteral = ts.createSourceFile(
      'unsupported-type-literal.d.ts',
      declarationText,
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TS,
    );
    assert.throws(() => discoverPublicApi(unsupportedTypeLiteral), /Public type literal/);
  }
  const aliasBefore = ts.createSourceFile(
    'alias-before.d.ts',
    'type Maybe<T> = T | null; export declare class Projection { observe(listener: (value: Maybe<string>) => void): void; }',
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  const aliasAfter = ts.createSourceFile(
    'alias-after.d.ts',
    'type Maybe<T> = T | null | undefined; export declare class Projection { observe(listener: (value: Maybe<string>) => void): void; }',
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  assert.notDeepEqual(
    discoverPublicApi(aliasBefore).publicSymbols,
    discoverPublicApi(aliasAfter).publicSymbols,
    'A reachable non-exported alias change must alter the public inventory',
  );
  const declaration = fs.readFileSync(declarationFile, 'utf8');
  assert.doesNotMatch(declaration, /\$metadata\$|\bkotlin\b|\bany\b/i);

  const report = {
    schema: 2,
    result: 'passed',
    language: 'javascript-typescript',
    toolchain: {
      node: process.version,
      typescript: ts.version,
    },
    package: {
      name: JSON.parse(fs.readFileSync(packageJsonFile, 'utf8')).name,
      version: JSON.parse(fs.readFileSync(packageJsonFile, 'utf8')).version,
    },
    artifacts: {
      tarball: identity(tarballFile),
      packageJson: identity(packageJsonFile),
      declaration: identity(declarationFile),
      commonJs: identity(commonJsFile),
      esm: identity(esmFile),
    },
    exports: {
      types: compilerApi.typeExports,
      values: compilerApi.valueExports,
      commonJs: commonJsExports,
      esm: esmExports,
    },
    publicSymbols: compilerApi.publicSymbols,
    compilerEvidence: {
      testId: 'typescript compiler discovers the exact installed public API',
      status: 'passed',
      referencedSymbols: compilerApi.referencedSymbols,
    },
  };
  fs.writeFileSync(path.join(process.cwd(), 'public-api.json'), `${JSON.stringify(report, null, 4)}\n`);
});
