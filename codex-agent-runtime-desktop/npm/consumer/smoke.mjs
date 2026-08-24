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
  const typeExports = [];
  const valueExports = [];

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
      publicSymbols.push(`class:${name}${heritage.length === 0 ? '' : `:${heritage.join(':')}`}`);
      for (const member of declaration.members) {
        if (nonPublicMember(member)) continue;
        if (ts.isConstructorDeclaration(member)) {
          memberQualifiers(member, [], `Constructor ${name}`);
          assert.equal(member.typeParameters?.length ?? 0, 0, `Generic constructor ${name} is unsupported`);
          publicSymbols.push(`constructor:${name}#(${renderParameters(member.parameters, source, aliases)})`);
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
          publicSymbols.push(
            `method:${name}#${memberName}${qualifiers}:${renderSignature(member, source, aliases, `method ${name}.${memberName}`)}`,
          );
        } else if (ts.isGetAccessorDeclaration(member)) {
          const qualifiers = memberQualifiers(
            member,
            [ts.SyntaxKind.StaticKeyword],
            `Getter ${name}.${memberName}`,
          );
          assert.ok(member.type, `Getter ${name}.${memberName} must have an explicit type`);
          publicSymbols.push(
            `getter:${name}#${memberName}${qualifiers}:${renderType(member.type, source, aliases)}`,
          );
        } else if (ts.isPropertyDeclaration(member)) {
          const qualifiers = memberQualifiers(
            member,
            [ts.SyntaxKind.ReadonlyKeyword, ts.SyntaxKind.StaticKeyword],
            `Property ${name}.${memberName}`,
          );
          assert.ok(member.type, `Property ${name}.${memberName} must have an explicit type`);
          publicSymbols.push(
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
      publicSymbols.push(`function:${name}:${renderSignature(declaration, source, aliases, `function ${name}`)}`);
    } else if (ts.isTypeAliasDeclaration(declaration)) {
      assertModifiers(declaration, [ts.SyntaxKind.ExportKeyword], `Exported TypeScript type ${name}`);
      assert.equal(declaration.typeParameters?.length ?? 0, 0, `Unsupported type parameters on type ${name}`);
      typeExports.push(name);
      publicSymbols.push(`type:${name}:${renderType(declaration.type, source, aliases)}`);
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
  };
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
  const source = program.getSourceFile(declarationFile);
  assert.ok(source, 'The installed declaration must belong to the compiler program');
  return discoverPublicApi(source);
}

test('esm exposes the same runtime values as CommonJS', () => {
  const commonJsExports = Object.getOwnPropertyNames(require('@codex-agent-labs/codex-agent')).sort();
  const esmExports = Object.keys(sdk).sort();
  assert.deepEqual(esmExports, commonJsExports);
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
    schema: 1,
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
    },
  };
  fs.writeFileSync(path.join(process.cwd(), 'public-api.json'), `${JSON.stringify(report, null, 2)}\n`);
});
