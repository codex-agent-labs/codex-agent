import CodexAgent
@testable import CodexAgentObservation
import CodexAgentObjectiveCConsumer
import CodexAgentSwiftSupport
import Foundation
import XCTest

final class CodexAgentObservationTests: XCTestCase {
    func testBufferingCancellationAndDroppedStreamReleaseTheObservation() async {
        let buffered: AsyncStream<Int> = codexAsyncStream { yield in
            yield(1)
            yield(2)
            return {}
        }
        var iterator = buffered.makeAsyncIterator()
        let latest = await iterator.next()
        XCTAssertEqual(latest, 2)

        let closed = expectation(description: "observation closed")
        let cancellable: AsyncStream<Int> = codexAsyncStream { _ in
            return { closed.fulfill() }
        }
        let task = Task {
            for await _ in cancellable { /* wait for cancellation */ }
        }
        task.cancel()
        await fulfillment(of: [closed], timeout: 1)

        let droppedClosed = expectation(description: "dropped observation closed")
        let droppedDeinitialized = expectation(description: "dropped observation released")
        weak var weakToken: TestObservationToken?
        var dropped: AsyncStream<Int>? = codexAsyncStream { yield in
            let token = TestObservationToken(
                onClose: { droppedClosed.fulfill() },
                onDeinit: { droppedDeinitialized.fulfill() }
            )
            token.yield = yield
            weakToken = token
            return token.close
        }
        XCTAssertNotNil(dropped)
        XCTAssertNotNil(weakToken)

        dropped = nil

        await fulfillment(of: [droppedClosed, droppedDeinitialized], timeout: 1)
        XCTAssertNil(weakToken)
    }

    func testCodexOperationErrorsExposeStructuredFailure() async throws {
        let conversationId = ConversationId(value: "conversation-1")
        XCTAssertEqual(conversationId.value, "conversation-1")

        let accept = AgentApprovalDecision.accept
        let decline = AgentApprovalDecision.decline
        XCTAssertEqual(accept.name, "ACCEPT")
        XCTAssertEqual(accept.ordinal, 0)
        XCTAssertEqual(decline.name, "DECLINE")
        XCTAssertEqual(decline.ordinal, 1)
        XCTAssertFalse(accept === decline)
        XCTAssertTrue(accept === AgentApprovalDecision.accept)
        XCTAssertTrue(decline === AgentApprovalDecision.decline)

        let defaultMode = AgentCollaborationMode.default_
        let plan = AgentCollaborationMode.plan
        XCTAssertEqual(defaultMode.name, "DEFAULT")
        XCTAssertEqual(defaultMode.ordinal, 0)
        XCTAssertEqual(plan.name, "PLAN")
        XCTAssertEqual(plan.ordinal, 1)
        XCTAssertFalse(defaultMode === plan)
        XCTAssertTrue(defaultMode === AgentCollaborationMode.default_)
        XCTAssertTrue(plan === AgentCollaborationMode.plan)

        let user = AgentMessageRole.user
        let assistant = AgentMessageRole.assistant
        XCTAssertEqual(user.name, "USER")
        XCTAssertEqual(user.ordinal, 0)
        XCTAssertEqual(assistant.name, "ASSISTANT")
        XCTAssertEqual(assistant.ordinal, 1)
        XCTAssertFalse(user === assistant)
        XCTAssertTrue(user === AgentMessageRole.user)
        XCTAssertTrue(assistant === AgentMessageRole.assistant)

        let userScope = AgentInstallationScope.user
        let workspaceScope = AgentInstallationScope.workspace
        XCTAssertEqual(userScope.name, "User")
        XCTAssertEqual(userScope.ordinal, 0)
        XCTAssertEqual(workspaceScope.name, "Workspace")
        XCTAssertEqual(workspaceScope.ordinal, 1)
        XCTAssertFalse(userScope === workspaceScope)
        XCTAssertTrue(userScope === AgentInstallationScope.user)
        XCTAssertTrue(workspaceScope === AgentInstallationScope.workspace)

        let localEnvironment = AgentMcpEnvironmentSource.local
        let remoteEnvironment = AgentMcpEnvironmentSource.remote
        XCTAssertEqual(localEnvironment.name, "LOCAL")
        XCTAssertEqual(localEnvironment.ordinal, 0)
        XCTAssertEqual(remoteEnvironment.name, "REMOTE")
        XCTAssertEqual(remoteEnvironment.ordinal, 1)
        XCTAssertFalse(localEnvironment === remoteEnvironment)
        XCTAssertTrue(localEnvironment === AgentMcpEnvironmentSource.local)
        XCTAssertTrue(remoteEnvironment === AgentMcpEnvironmentSource.remote)

        assertD065EnumValues()
        assertD065ImmutableValues()
        assertD073OrdinaryValues()
        assertD074OrdinaryValues()
        assertD075PendingValues()
        assertD077McpServerValues()
        assertD078McpAndElicitationValues()
        assertD079ConversationValues()
        assertD080StateSnapshots()
        assertD081SingletonObjects()
        assertD082ElicitationHelpers()
        try await assertD084HostLifecycle()

        let authorizationUrlCompanion = CodexAuthorizationUrl.companion
        let chatGptAuthorizationUrl = authorizationUrlCompanion.chatGpt(
            value: "https://auth.openai.com/authorize?client=codex"
        )
        XCTAssertEqual(chatGptAuthorizationUrl.value, "https://auth.openai.com/authorize?client=codex")
        XCTAssertTrue(chatGptAuthorizationUrl.purpose === CodexAuthorizationPurpose.chatGpt)

        let externalAuthorizationUrl = authorizationUrlCompanion.external(
            value: "https://example.com/oauth"
        )
        XCTAssertEqual(externalAuthorizationUrl.value, "https://example.com/oauth")
        XCTAssertTrue(externalAuthorizationUrl.purpose === CodexAuthorizationPurpose.external)

        let failure = CodexFailure(
            code: "workspace_unavailable",
            message: "Workspace is unavailable",
            isRecoverable: true
        )
        let error = CodexOperationException(failure: failure, cause: nil).asError()

        XCTAssertEqual(error.codexFailure?.code, failure.code)
        XCTAssertEqual(error.codexFailure?.message, failure.message)
        XCTAssertEqual(error.codexFailure?.isRecoverable, failure.isRecoverable)
    }

    private func assertD065EnumValues() {
        assertEnumValue(AgentApprovalPreset.never, stable: AgentApprovalPreset.never, name: "NEVER", ordinal: 0)
        assertEnumValue(AgentApprovalPreset.autoReview, stable: AgentApprovalPreset.autoReview, name: "AUTO_REVIEW", ordinal: 1)
        assertEnumValue(AgentApprovalPreset.askMe, stable: AgentApprovalPreset.askMe, name: "ASK_ME", ordinal: 2)
        assertEnumValue(AgentApprovalPreset.strict, stable: AgentApprovalPreset.strict, name: "STRICT", ordinal: 3)

        assertEnumValue(AgentAuthenticationStatus.signedOut, stable: AgentAuthenticationStatus.signedOut, name: "SIGNED_OUT", ordinal: 0)
        assertEnumValue(AgentAuthenticationStatus.authenticating, stable: AgentAuthenticationStatus.authenticating, name: "AUTHENTICATING", ordinal: 1)
        assertEnumValue(AgentAuthenticationStatus.authenticated, stable: AgentAuthenticationStatus.authenticated, name: "AUTHENTICATED", ordinal: 2)

        assertEnumValue(AgentCapability.webSearch, stable: AgentCapability.webSearch, name: "WEB_SEARCH", ordinal: 0)

        assertEnumValue(AgentCatalogFreshness.live, stable: AgentCatalogFreshness.live, name: "LIVE", ordinal: 0)
        assertEnumValue(AgentCatalogFreshness.freshCache, stable: AgentCatalogFreshness.freshCache, name: "FRESH_CACHE", ordinal: 1)
        assertEnumValue(AgentCatalogFreshness.staleCache, stable: AgentCatalogFreshness.staleCache, name: "STALE_CACHE", ordinal: 2)

        assertEnumValue(AgentConversationStatus.theNew, stable: AgentConversationStatus.theNew, name: "NEW", ordinal: 0)
        assertEnumValue(AgentConversationStatus.opening, stable: AgentConversationStatus.opening, name: "OPENING", ordinal: 1)
        assertEnumValue(AgentConversationStatus.ready, stable: AgentConversationStatus.ready, name: "READY", ordinal: 2)
        assertEnumValue(AgentConversationStatus.startingTurn, stable: AgentConversationStatus.startingTurn, name: "STARTING_TURN", ordinal: 3)
        assertEnumValue(AgentConversationStatus.runningTurn, stable: AgentConversationStatus.runningTurn, name: "RUNNING_TURN", ordinal: 4)
        assertEnumValue(AgentConversationStatus.cancellingTurn, stable: AgentConversationStatus.cancellingTurn, name: "CANCELLING_TURN", ordinal: 5)
        assertEnumValue(AgentConversationStatus.reloading, stable: AgentConversationStatus.reloading, name: "RELOADING", ordinal: 6)
        assertEnumValue(AgentConversationStatus.failed, stable: AgentConversationStatus.failed, name: "FAILED", ordinal: 7)
        assertEnumValue(AgentConversationStatus.closed, stable: AgentConversationStatus.closed, name: "CLOSED", ordinal: 8)

        assertEnumValue(AgentElicitationAction.accept, stable: AgentElicitationAction.accept, name: "ACCEPT", ordinal: 0)
        assertEnumValue(AgentElicitationAction.decline, stable: AgentElicitationAction.decline, name: "DECLINE", ordinal: 1)
        assertEnumValue(AgentElicitationAction.cancel, stable: AgentElicitationAction.cancel, name: "CANCEL", ordinal: 2)

        assertEnumValue(AgentElicitationValidationReason.missingRequired, stable: AgentElicitationValidationReason.missingRequired, name: "MISSING_REQUIRED", ordinal: 0)
        assertEnumValue(AgentElicitationValidationReason.unknownField, stable: AgentElicitationValidationReason.unknownField, name: "UNKNOWN_FIELD", ordinal: 1)
        assertEnumValue(AgentElicitationValidationReason.invalidType, stable: AgentElicitationValidationReason.invalidType, name: "INVALID_TYPE", ordinal: 2)
        assertEnumValue(AgentElicitationValidationReason.nonFiniteNumber, stable: AgentElicitationValidationReason.nonFiniteNumber, name: "NON_FINITE_NUMBER", ordinal: 3)
        assertEnumValue(AgentElicitationValidationReason.belowMinimum, stable: AgentElicitationValidationReason.belowMinimum, name: "BELOW_MINIMUM", ordinal: 4)
        assertEnumValue(AgentElicitationValidationReason.aboveMaximum, stable: AgentElicitationValidationReason.aboveMaximum, name: "ABOVE_MAXIMUM", ordinal: 5)
        assertEnumValue(AgentElicitationValidationReason.nonInteger, stable: AgentElicitationValidationReason.nonInteger, name: "NON_INTEGER", ordinal: 6)
        assertEnumValue(AgentElicitationValidationReason.invalidFormat, stable: AgentElicitationValidationReason.invalidFormat, name: "INVALID_FORMAT", ordinal: 7)
        assertEnumValue(AgentElicitationValidationReason.invalidSelection, stable: AgentElicitationValidationReason.invalidSelection, name: "INVALID_SELECTION", ordinal: 8)
        assertEnumValue(AgentElicitationValidationReason.duplicateSelection, stable: AgentElicitationValidationReason.duplicateSelection, name: "DUPLICATE_SELECTION", ordinal: 9)

        assertEnumValue(AgentFormFieldType.string, stable: AgentFormFieldType.string, name: "STRING", ordinal: 0)
        assertEnumValue(AgentFormFieldType.number, stable: AgentFormFieldType.number, name: "NUMBER", ordinal: 1)
        assertEnumValue(AgentFormFieldType.integer, stable: AgentFormFieldType.integer, name: "INTEGER", ordinal: 2)
        assertEnumValue(AgentFormFieldType.boolean, stable: AgentFormFieldType.boolean, name: "BOOLEAN", ordinal: 3)
        assertEnumValue(AgentFormFieldType.singleSelect, stable: AgentFormFieldType.singleSelect, name: "SINGLE_SELECT", ordinal: 4)
        assertEnumValue(AgentFormFieldType.multiSelect, stable: AgentFormFieldType.multiSelect, name: "MULTI_SELECT", ordinal: 5)

        assertEnumValue(AgentFormStringFormat.email, stable: AgentFormStringFormat.email, name: "EMAIL", ordinal: 0)
        assertEnumValue(AgentFormStringFormat.uri, stable: AgentFormStringFormat.uri, name: "URI", ordinal: 1)
        assertEnumValue(AgentFormStringFormat.date, stable: AgentFormStringFormat.date, name: "DATE", ordinal: 2)
        assertEnumValue(AgentFormStringFormat.dateTime, stable: AgentFormStringFormat.dateTime, name: "DATE_TIME", ordinal: 3)

        assertEnumValue(AgentHookRunStatus.running, stable: AgentHookRunStatus.running, name: "RUNNING", ordinal: 0)
        assertEnumValue(AgentHookRunStatus.completed, stable: AgentHookRunStatus.completed, name: "COMPLETED", ordinal: 1)
        assertEnumValue(AgentHookRunStatus.failed, stable: AgentHookRunStatus.failed, name: "FAILED", ordinal: 2)
        assertEnumValue(AgentHookRunStatus.blocked, stable: AgentHookRunStatus.blocked, name: "BLOCKED", ordinal: 3)
        assertEnumValue(AgentHookRunStatus.stopped, stable: AgentHookRunStatus.stopped, name: "STOPPED", ordinal: 4)

        assertEnumValue(AgentHookTrustStatus.managed, stable: AgentHookTrustStatus.managed, name: "MANAGED", ordinal: 0)
        assertEnumValue(AgentHookTrustStatus.untrusted, stable: AgentHookTrustStatus.untrusted, name: "UNTRUSTED", ordinal: 1)
        assertEnumValue(AgentHookTrustStatus.trusted, stable: AgentHookTrustStatus.trusted, name: "TRUSTED", ordinal: 2)
        assertEnumValue(AgentHookTrustStatus.modified, stable: AgentHookTrustStatus.modified, name: "MODIFIED", ordinal: 3)

        assertEnumValue(AgentIntegrationAuthorizationStatus.idle, stable: AgentIntegrationAuthorizationStatus.idle, name: "IDLE", ordinal: 0)
        assertEnumValue(AgentIntegrationAuthorizationStatus.starting, stable: AgentIntegrationAuthorizationStatus.starting, name: "STARTING", ordinal: 1)
        assertEnumValue(AgentIntegrationAuthorizationStatus.awaitingCompletion, stable: AgentIntegrationAuthorizationStatus.awaitingCompletion, name: "AWAITING_COMPLETION", ordinal: 2)
        assertEnumValue(AgentIntegrationAuthorizationStatus.authorized, stable: AgentIntegrationAuthorizationStatus.authorized, name: "AUTHORIZED", ordinal: 3)
        assertEnumValue(AgentIntegrationAuthorizationStatus.failed, stable: AgentIntegrationAuthorizationStatus.failed, name: "FAILED", ordinal: 4)

        assertEnumValue(AgentMcpAuthStatus.unknown, stable: AgentMcpAuthStatus.unknown, name: "UNKNOWN", ordinal: 0)
        assertEnumValue(AgentMcpAuthStatus.unsupported, stable: AgentMcpAuthStatus.unsupported, name: "UNSUPPORTED", ordinal: 1)
        assertEnumValue(AgentMcpAuthStatus.notLoggedIn, stable: AgentMcpAuthStatus.notLoggedIn, name: "NOT_LOGGED_IN", ordinal: 2)
        assertEnumValue(AgentMcpAuthStatus.bearerToken, stable: AgentMcpAuthStatus.bearerToken, name: "BEARER_TOKEN", ordinal: 3)
        assertEnumValue(AgentMcpAuthStatus.oauth, stable: AgentMcpAuthStatus.oauth, name: "OAUTH", ordinal: 4)

        assertEnumValue(AgentMcpAuthentication.oauth, stable: AgentMcpAuthentication.oauth, name: "OAUTH", ordinal: 0)
        assertEnumValue(AgentMcpAuthentication.chatGpt, stable: AgentMcpAuthentication.chatGpt, name: "CHAT_GPT", ordinal: 1)

        assertEnumValue(AgentMcpToolApproval.auto_, stable: AgentMcpToolApproval.auto_, name: "AUTO", ordinal: 0)
        assertEnumValue(AgentMcpToolApproval.prompt, stable: AgentMcpToolApproval.prompt, name: "PROMPT", ordinal: 1)
        assertEnumValue(AgentMcpToolApproval.writes, stable: AgentMcpToolApproval.writes, name: "WRITES", ordinal: 2)
        assertEnumValue(AgentMcpToolApproval.approve, stable: AgentMcpToolApproval.approve, name: "APPROVE", ordinal: 3)

        assertEnumValue(AgentMcpToolExposureSurface.codeMode, stable: AgentMcpToolExposureSurface.codeMode, name: "CODE_MODE", ordinal: 0)
        assertEnumValue(AgentMcpToolExposureSurface.deferred, stable: AgentMcpToolExposureSurface.deferred, name: "DEFERRED", ordinal: 1)
        assertEnumValue(AgentMcpToolExposureSurface.direct, stable: AgentMcpToolExposureSurface.direct, name: "DIRECT", ordinal: 2)

        assertEnumValue(AgentPlanStepStatus.pending, stable: AgentPlanStepStatus.pending, name: "PENDING", ordinal: 0)
        assertEnumValue(AgentPlanStepStatus.inProgress, stable: AgentPlanStepStatus.inProgress, name: "IN_PROGRESS", ordinal: 1)
        assertEnumValue(AgentPlanStepStatus.completed, stable: AgentPlanStepStatus.completed, name: "COMPLETED", ordinal: 2)

        assertEnumValue(AgentPluginAuthPolicy.onInstall, stable: AgentPluginAuthPolicy.onInstall, name: "ON_INSTALL", ordinal: 0)
        assertEnumValue(AgentPluginAuthPolicy.onUse, stable: AgentPluginAuthPolicy.onUse, name: "ON_USE", ordinal: 1)

        assertEnumValue(AgentPluginInstallPolicy.notAvailable, stable: AgentPluginInstallPolicy.notAvailable, name: "NOT_AVAILABLE", ordinal: 0)
        assertEnumValue(AgentPluginInstallPolicy.available, stable: AgentPluginInstallPolicy.available, name: "AVAILABLE", ordinal: 1)
        assertEnumValue(AgentPluginInstallPolicy.installedByDefault, stable: AgentPluginInstallPolicy.installedByDefault, name: "INSTALLED_BY_DEFAULT", ordinal: 2)

        assertEnumValue(AgentResolution.preferred, stable: AgentResolution.preferred, name: "Preferred", ordinal: 0)
        assertEnumValue(AgentResolution.default_, stable: AgentResolution.default_, name: "Default", ordinal: 1)
        assertEnumValue(AgentResolution.first, stable: AgentResolution.first, name: "First", ordinal: 2)

        assertEnumValue(AgentResourceOrigin.user, stable: AgentResourceOrigin.user, name: "USER", ordinal: 0)
        assertEnumValue(AgentResourceOrigin.workspace, stable: AgentResourceOrigin.workspace, name: "WORKSPACE", ordinal: 1)
        assertEnumValue(AgentResourceOrigin.plugin, stable: AgentResourceOrigin.plugin, name: "PLUGIN", ordinal: 2)
        assertEnumValue(AgentResourceOrigin.managed, stable: AgentResourceOrigin.managed, name: "MANAGED", ordinal: 3)
        assertEnumValue(AgentResourceOrigin.unknown, stable: AgentResourceOrigin.unknown, name: "UNKNOWN", ordinal: 4)

        assertEnumValue(AgentSkillScope.system, stable: AgentSkillScope.system, name: "SYSTEM", ordinal: 0)
        assertEnumValue(AgentSkillScope.user, stable: AgentSkillScope.user, name: "USER", ordinal: 1)
        assertEnumValue(AgentSkillScope.repo, stable: AgentSkillScope.repo, name: "REPO", ordinal: 2)
        assertEnumValue(AgentSkillScope.plugin, stable: AgentSkillScope.plugin, name: "PLUGIN", ordinal: 3)
        assertEnumValue(AgentSkillScope.admin, stable: AgentSkillScope.admin, name: "ADMIN", ordinal: 4)

        assertEnumValue(AgentWorkActivity.runningCommand, stable: AgentWorkActivity.runningCommand, name: "RUNNING_COMMAND", ordinal: 0)
        assertEnumValue(AgentWorkActivity.writingFiles, stable: AgentWorkActivity.writingFiles, name: "WRITING_FILES", ordinal: 1)

        assertEnumValue(CodexAuthorizationPurpose.chatGpt, stable: CodexAuthorizationPurpose.chatGpt, name: "CHAT_GPT", ordinal: 0)
        assertEnumValue(CodexAuthorizationPurpose.external, stable: CodexAuthorizationPurpose.external, name: "EXTERNAL", ordinal: 1)

        assertEnumValue(CodexWorkspaceSelectionReason.notSelected, stable: CodexWorkspaceSelectionReason.notSelected, name: "NOT_SELECTED", ordinal: 0)
        assertEnumValue(CodexWorkspaceSelectionReason.notFound, stable: CodexWorkspaceSelectionReason.notFound, name: "NOT_FOUND", ordinal: 1)
        assertEnumValue(CodexWorkspaceSelectionReason.accessRevoked, stable: CodexWorkspaceSelectionReason.accessRevoked, name: "ACCESS_REVOKED", ordinal: 2)
        assertEnumValue(CodexWorkspaceSelectionReason.invalidSelection, stable: CodexWorkspaceSelectionReason.invalidSelection, name: "INVALID_SELECTION", ordinal: 3)
    }

    private func assertD065ImmutableValues() {
        let conversationId = ConversationId(value: "d065-conversation")
        let summary = AgentConversationSummary(
            conversationId: conversationId,
            title: "D065 conversation",
            updatedAtEpochSeconds: 1_700_000_065
        )
        XCTAssertTrue(summary.conversationId === conversationId)
        XCTAssertEqual(summary.title, "D065 conversation")
        XCTAssertEqual(summary.updatedAtEpochSeconds, 1_700_000_065)

        let option = AgentFormOption(value: "option", title: "Option", description: "Description")
        XCTAssertEqual(option.value, "option")
        XCTAssertEqual(option.title, "Option")
        XCTAssertEqual(option.description_, "Description")
        XCTAssertNil(AgentFormOption(value: "nil", title: "Nil", description: nil).description_)

        let environment = AgentMcpEnvironmentVariable(name: "TOKEN", source: .remote)
        XCTAssertEqual(environment.name, "TOKEN")
        XCTAssertTrue(environment.source === AgentMcpEnvironmentSource.remote)
        XCTAssertNil(AgentMcpEnvironmentVariable(name: "LOCAL_TOKEN", source: nil).source)

        let oauth = AgentMcpOauthConfiguration(
            clientId: "d065-client",
            callbackPort: KotlinInt(value: 8_065)
        )
        XCTAssertEqual(oauth.clientId, "d065-client")
        XCTAssertEqual(oauth.callbackPort?.int32Value, 8_065)
        let defaultOauth = AgentMcpOauthConfiguration(clientId: nil, callbackPort: nil)
        XCTAssertNil(defaultOauth.clientId)
        XCTAssertNil(defaultOauth.callbackPort)

        let plugin = AgentPluginReference(
            id: "d065-plugin-id",
            name: "d065-plugin",
            marketplaceName: "d065-marketplace",
            marketplacePath: "/d065/marketplace",
            remotePluginId: "d065-remote"
        )
        XCTAssertEqual(plugin.id, "d065-plugin-id")
        XCTAssertEqual(plugin.name, "d065-plugin")
        XCTAssertEqual(plugin.marketplaceName, "d065-marketplace")
        XCTAssertEqual(plugin.marketplacePath, "/d065/marketplace")
        XCTAssertEqual(plugin.remotePluginId, "d065-remote")
        XCTAssertEqual(plugin.uri, "plugin://d065-plugin@d065-marketplace")
        let localPlugin = AgentPluginReference(
            id: "local",
            name: "local",
            marketplaceName: "marketplace",
            marketplacePath: nil,
            remotePluginId: nil
        )
        XCTAssertNil(localPlugin.marketplacePath)
        XCTAssertNil(localPlugin.remotePluginId)

        let pluginSkill = AgentPluginSkill(
            name: "d065-skill",
            description: "D065 skill",
            isEnabled: true,
            path: "/d065/skill"
        )
        XCTAssertEqual(pluginSkill.name, "d065-skill")
        XCTAssertEqual(pluginSkill.description_, "D065 skill")
        XCTAssertTrue(pluginSkill.isEnabled)
        XCTAssertEqual(pluginSkill.path, "/d065/skill")
        XCTAssertNil(AgentPluginSkill(name: "nil", description: "Nil", isEnabled: false, path: nil).path)

        let tier = AgentServiceTier(id: "d065-tier", name: "D065 Tier", description: "D065 service tier")
        XCTAssertEqual(tier.id, "d065-tier")
        XCTAssertEqual(tier.name, "D065 Tier")
        XCTAssertEqual(tier.description_, "D065 service tier")

        let chunk = AgentSkillChunk(content: "chunk", nextOffset: KotlinLong(value: 65), totalBytes: 100)
        XCTAssertEqual(chunk.content, "chunk")
        XCTAssertEqual(chunk.nextOffset?.int64Value, 65)
        XCTAssertEqual(chunk.totalBytes, 100)
        XCTAssertNil(AgentSkillChunk(content: "complete", nextOffset: nil, totalBytes: 8).nextOffset)

        let clientInfo = CodexClientInfo(name: "d065", title: "D065", version: "1.0")
        XCTAssertEqual(clientInfo.name, "d065")
        XCTAssertEqual(clientInfo.title, "D065")
        XCTAssertEqual(clientInfo.version, "1.0")

        let workspace = CodexWorkspace(path: "/d065/workspace", displayName: "D065 Workspace")
        XCTAssertEqual(workspace.path, "/d065/workspace")
        XCTAssertEqual(workspace.displayName, "D065 Workspace")

        XCTAssertEqual(AgentApprovalPreset.never.displayName, "Never")
        XCTAssertEqual(AgentApprovalPreset.autoReview.displayName, "Auto review")
        XCTAssertEqual(AgentApprovalPreset.askMe.displayName, "Ask me")
        XCTAssertEqual(AgentApprovalPreset.strict.displayName, "Strict")

        let capability = AgentCapability.webSearch
        XCTAssertEqual(capability.id, "web_search")
        XCTAssertEqual(capability.displayLabel, "Web search")
        XCTAssertEqual(capability.icon, "🌐")
        XCTAssertEqual(capability.promptLabel, "Use 🌐 Web search")

        XCTAssertEqual(AgentSkillScope.system.displayName, "Built in")
        XCTAssertEqual(AgentSkillScope.user.displayName, "User")
        XCTAssertEqual(AgentSkillScope.repo.displayName, "Workspace")
        XCTAssertEqual(AgentSkillScope.plugin.displayName, "Plugin")
        XCTAssertEqual(AgentSkillScope.admin.displayName, "Managed")

        let settings = AgentConversationSettings(approvalPreset: .strict, serviceTier: "fast")
        XCTAssertTrue(settings.approvalPreset === AgentApprovalPreset.strict)
        XCTAssertEqual(settings.serviceTier, "fast")
        XCTAssertNil(AgentConversationSettings(approvalPreset: .autoReview, serviceTier: nil).serviceTier)

        let issue = AgentElicitationValidationIssue(fieldName: "email", reason: .invalidFormat)
        XCTAssertEqual(issue.fieldName, "email")
        XCTAssertTrue(issue.reason === AgentElicitationValidationReason.invalidFormat)

        let step = AgentPlanStep(text: "Verify D065", status: .inProgress)
        XCTAssertEqual(step.text, "Verify D065")
        XCTAssertTrue(step.status === AgentPlanStepStatus.inProgress)

        let tool = AgentMcpToolConfiguration(approval: .writes)
        XCTAssertTrue(tool.approval === AgentMcpToolApproval.writes)
        XCTAssertNil(AgentMcpToolConfiguration(approval: nil).approval)
    }

    private func assertD073OrdinaryValues() {
        let connector = AgentConnector(
            id: "d073-connector",
            name: "D073 Connector",
            description: "D073 connector description",
            installUrl: "https://example.com/install",
            isAccessible: true,
            isEnabled: false,
            pluginNames: ["d073-plugin"]
        )
        XCTAssertEqual(connector.id, "d073-connector")
        XCTAssertEqual(connector.name, "D073 Connector")
        XCTAssertEqual(connector.description_, "D073 connector description")
        XCTAssertEqual(connector.installUrl, "https://example.com/install")
        XCTAssertTrue(connector.isAccessible)
        XCTAssertFalse(connector.isEnabled)
        XCTAssertEqual(connector.pluginNames, ["d073-plugin"])

        let issue = AgentElicitationValidationIssue(fieldName: "field", reason: .invalidType)
        let validation = AgentElicitationValidation(issues: [issue])
        XCTAssertFalse(validation.isValid)
        XCTAssertTrue(validation.issues.count == 1 && validation.issues[0] === issue)

        let booleanValue = AgentFormValueBooleanValue(value: true)
        XCTAssertTrue(booleanValue.value)
        let numberValue = AgentFormValueNumber(value: 73.5)
        XCTAssertEqual(numberValue.value, 73.5)
        let textValue = AgentFormValueText(value: "D073 text")
        XCTAssertEqual(textValue.value, "D073 text")
        let textListValue = AgentFormValueTextList(value: ["D073", "text"])
        XCTAssertEqual(textListValue.value, ["D073", "text"])

        let tier = AgentServiceTier(id: "d073-tier", name: "D073 Tier", description: "D073 tier")
        let model = AgentModel(
            id: "d073-model",
            displayName: "D073 Model",
            description: "D073 model description",
            supportedEfforts: ["low", "high"],
            defaultEffort: "high",
            isDefault: true,
            serviceTiers: [tier],
            defaultServiceTier: "d073-tier"
        )
        XCTAssertEqual(model.id, "d073-model")
        XCTAssertEqual(model.displayName, "D073 Model")
        XCTAssertEqual(model.description_, "D073 model description")
        XCTAssertEqual(model.supportedEfforts, ["low", "high"])
        XCTAssertEqual(model.defaultEffort, "high")
        XCTAssertTrue(model.isDefault)
        XCTAssertTrue(model.serviceTiers.count == 1 && model.serviceTiers[0] === tier)
        XCTAssertEqual(model.defaultServiceTier, "d073-tier")

        let step = AgentPlanStep(text: "Verify D073", status: .inProgress)
        let progress = AgentPlanProgress(explanation: "D073 plan", steps: [step])
        XCTAssertEqual(progress.explanation, "D073 plan")
        XCTAssertTrue(progress.steps.count == 1 && progress.steps[0] === step)

        let reference = AgentPluginReference(
            id: "d073-plugin",
            name: "d073-plugin",
            marketplaceName: "d073-marketplace",
            marketplacePath: "/d073/marketplace",
            remotePluginId: "d073-remote"
        )
        let summary = AgentPluginSummary(
            reference: reference,
            displayName: "D073 Plugin",
            description: "D073 plugin description",
            isInstalled: true,
            isEnabled: false,
            installPolicy: .available,
            authPolicy: .onUse,
            isAvailable: true,
            capabilities: ["skill", "connector"],
            brandColor: "#123456",
            privacyPolicyUrl: "https://example.com/privacy",
            termsOfServiceUrl: "https://example.com/terms",
            websiteUrl: "https://example.com/plugin"
        )
        XCTAssertTrue(summary.reference === reference)
        XCTAssertEqual(summary.displayName, "D073 Plugin")
        XCTAssertEqual(summary.description_, "D073 plugin description")
        XCTAssertTrue(summary.isInstalled)
        XCTAssertFalse(summary.isEnabled)
        XCTAssertTrue(summary.installPolicy === AgentPluginInstallPolicy.available)
        XCTAssertTrue(summary.authPolicy === AgentPluginAuthPolicy.onUse)
        XCTAssertTrue(summary.isAvailable)
        XCTAssertEqual(summary.capabilities, ["skill", "connector"])
        XCTAssertEqual(summary.brandColor, "#123456")
        XCTAssertEqual(summary.privacyPolicyUrl, "https://example.com/privacy")
        XCTAssertEqual(summary.termsOfServiceUrl, "https://example.com/terms")
        XCTAssertEqual(summary.websiteUrl, "https://example.com/plugin")

        let catalog = AgentPluginCatalog(
            plugins: [summary],
            errors: ["D073 warning"],
            freshness: .freshCache
        )
        XCTAssertTrue(catalog.plugins.count == 1 && catalog.plugins[0] === summary)
        XCTAssertEqual(catalog.errors, ["D073 warning"])
        XCTAssertTrue(catalog.freshness === AgentCatalogFreshness.freshCache)

        let pluginSkill = AgentPluginSkill(
            name: "d073-plugin-skill",
            description: "D073 plugin skill",
            isEnabled: true,
            path: "/d073/plugin-skill"
        )
        let detail = AgentPluginDetail(
            summary: summary,
            description: "D073 detail",
            skills: [pluginSkill],
            connectors: [connector],
            mcpServers: ["d073-server"],
            hookCount: 2
        )
        XCTAssertTrue(detail.summary === summary)
        XCTAssertEqual(detail.description_, "D073 detail")
        XCTAssertTrue(detail.skills.count == 1 && detail.skills[0] === pluginSkill)
        XCTAssertTrue(detail.connectors.count == 1 && detail.connectors[0] === connector)
        XCTAssertEqual(detail.mcpServers, ["d073-server"])
        XCTAssertEqual(detail.hookCount, 2)

        let installResult = AgentPluginInstallResult(
            authPolicy: .onUse,
            connectorsNeedingAuthentication: [connector],
            message: "D073 authentication required"
        )
        XCTAssertTrue(installResult.authPolicy === AgentPluginAuthPolicy.onUse)
        XCTAssertTrue(
            installResult.connectorsNeedingAuthentication.count == 1 &&
                installResult.connectorsNeedingAuthentication[0] === connector
        )
        XCTAssertEqual(installResult.message, "D073 authentication required")

        let skill = AgentSkill(
            name: "d073-skill",
            displayName: "D073 Skill",
            description: "D073 skill description",
            path: "/d073/skill",
            scope: .repo,
            isEnabled: true,
            brandColor: "#654321",
            dependencies: ["git"],
            canUninstall: true,
            origin: .workspace
        )
        XCTAssertEqual(skill.name, "d073-skill")
        XCTAssertEqual(skill.displayName, "D073 Skill")
        XCTAssertEqual(skill.description_, "D073 skill description")
        XCTAssertEqual(skill.path, "/d073/skill")
        XCTAssertTrue(skill.scope === AgentSkillScope.repo)
        XCTAssertTrue(skill.isEnabled)
        XCTAssertEqual(skill.brandColor, "#654321")
        XCTAssertEqual(skill.dependencies, ["git"])
        XCTAssertTrue(skill.canUninstall)
        XCTAssertTrue(skill.origin === AgentResourceOrigin.workspace)

        let skillCatalog = AgentSkillCatalog(skills: [skill], errors: ["D073 warning"])
        XCTAssertTrue(skillCatalog.skills.count == 1 && skillCatalog.skills[0] === skill)
        XCTAssertEqual(skillCatalog.errors, ["D073 warning"])

        let selection = CodexPathWorkspaceSelection(path: "/d073/workspace")
        XCTAssertEqual(selection.path, "/d073/workspace")

        let workspace = CodexWorkspace(path: "/d073/workspace", displayName: "D073 Workspace")
        let available = CodexWorkspaceResolutionAvailable(workspace: workspace)
        XCTAssertTrue(available.workspace === workspace)

        let selectionRequired = CodexWorkspaceResolutionSelectionRequired(
            reason: .notSelected,
            message: "Select a workspace"
        )
        XCTAssertTrue(selectionRequired.reason === CodexWorkspaceSelectionReason.notSelected)
        XCTAssertEqual(selectionRequired.message, "Select a workspace")
    }

    private func assertD074OrdinaryValues() {
        let option = AgentFormOption(value: "swift", title: "Swift", description: "Swift option")
        let defaultValue = AgentFormValueTextList(value: ["swift"])
        let field = AgentFormField(
            name: "languages",
            title: "Languages",
            description: "Select languages",
            isRequired: true,
            type: .multiSelect,
            options: [option],
            defaultValue: defaultValue,
            minimum: KotlinDouble(value: 1),
            maximum: KotlinDouble(value: 10),
            format: .uri,
            minimumLength: KotlinLong(value: 1),
            maximumLength: KotlinLong(value: 20),
            minimumSelections: KotlinLong(value: 1),
            maximumSelections: KotlinLong(value: 3),
            allowsOther: true,
            isSecret: false
        )
        XCTAssertEqual(field.name, "languages")
        XCTAssertEqual(field.title, "Languages")
        XCTAssertEqual(field.description_, "Select languages")
        XCTAssertTrue(field.isRequired)
        XCTAssertTrue(field.type === AgentFormFieldType.multiSelect)
        XCTAssertTrue(field.options.count == 1 && field.options[0] === option)
        XCTAssertTrue((field.defaultValue as? AgentFormValueTextList) === defaultValue)
        XCTAssertEqual(field.minimum?.doubleValue, 1)
        XCTAssertEqual(field.maximum?.doubleValue, 10)
        XCTAssertTrue(field.format === AgentFormStringFormat.uri)
        XCTAssertEqual(field.minimumLength?.int64Value, 1)
        XCTAssertEqual(field.maximumLength?.int64Value, 20)
        XCTAssertEqual(field.minimumSelections?.int64Value, 1)
        XCTAssertEqual(field.maximumSelections?.int64Value, 3)
        XCTAssertTrue(field.allowsOther)
        XCTAssertFalse(field.isSecret)

        let conversationId = ConversationId(value: "d074-conversation")
        let elicitation = AgentElicitation(
            requestId: "d074-request",
            serverName: "d074-server",
            conversationId: conversationId,
            message: "Select languages",
            form: [field],
            url: "https://example.com/elicit"
        )
        XCTAssertEqual(elicitation.requestId, "d074-request")
        XCTAssertEqual(elicitation.serverName, "d074-server")
        XCTAssertTrue(elicitation.conversationId === conversationId)
        XCTAssertEqual(elicitation.message, "Select languages")
        XCTAssertTrue(elicitation.form?.count == 1 && elicitation.form?[0] === field)
        XCTAssertEqual(elicitation.url, "https://example.com/elicit")

        let commandHandler = AgentHookHandlerCommand(command: "echo d074", isAsync: true)
        XCTAssertEqual(commandHandler.command, "echo d074")
        XCTAssertTrue(commandHandler.isAsync)

        let mcpHandler = AgentHookHandlerMcpTool(server: "d074-server", tool: "review")
        XCTAssertEqual(mcpHandler.server, "d074-server")
        XCTAssertEqual(mcpHandler.tool, "review")

        let hook = AgentHook(
            key: "d074-hook",
            currentHash: "d074-hash",
            isEnabled: true,
            eventName: "afterTurn",
            handler: commandHandler,
            isManaged: false,
            source: "PLUGIN",
            sourcePath: "/d074/hook",
            timeoutSeconds: 74,
            trustStatus: .modified,
            matcher: "*.swift",
            pluginId: "d074-plugin",
            statusMessage: "D074 hook",
            origin: .plugin,
            canUninstall: true
        )
        XCTAssertEqual(hook.key, "d074-hook")
        XCTAssertEqual(hook.currentHash, "d074-hash")
        XCTAssertTrue(hook.isEnabled)
        XCTAssertEqual(hook.eventName, "afterTurn")
        XCTAssertTrue((hook.handler as? AgentHookHandlerCommand) === commandHandler)
        XCTAssertFalse(hook.isManaged)
        XCTAssertEqual(hook.source, "PLUGIN")
        XCTAssertEqual(hook.sourcePath, "/d074/hook")
        XCTAssertEqual(hook.timeoutSeconds, 74)
        XCTAssertTrue(hook.trustStatus === AgentHookTrustStatus.modified)
        XCTAssertEqual(hook.matcher, "*.swift")
        XCTAssertEqual(hook.pluginId, "d074-plugin")
        XCTAssertEqual(hook.statusMessage, "D074 hook")
        XCTAssertTrue(hook.origin === AgentResourceOrigin.plugin)
        XCTAssertTrue(hook.canUninstall)
        XCTAssertTrue(hook.canTrust)

        let hookCatalog = AgentHookCatalog(
            hooks: [hook],
            warnings: ["D074 warning"],
            errors: ["D074 error"]
        )
        XCTAssertTrue(hookCatalog.hooks.count == 1 && hookCatalog.hooks[0] === hook)
        XCTAssertEqual(hookCatalog.warnings, ["D074 warning"])
        XCTAssertEqual(hookCatalog.errors, ["D074 error"])

        let hookActivity = AgentHookActivity(
            id: "d074-activity",
            eventName: "afterTurn",
            handlerType: "command",
            status: .completed,
            statusMessage: "D074 complete",
            details: ["D074 detail"]
        )
        XCTAssertEqual(hookActivity.id, "d074-activity")
        XCTAssertEqual(hookActivity.eventName, "afterTurn")
        XCTAssertEqual(hookActivity.handlerType, "command")
        XCTAssertTrue(hookActivity.status === AgentHookRunStatus.completed)
        XCTAssertEqual(hookActivity.statusMessage, "D074 complete")
        XCTAssertEqual(hookActivity.details, ["D074 detail"])

        let connector = AgentConnector(
            id: "d074-connector",
            name: "D074 Connector",
            description: "D074 connector",
            installUrl: nil,
            isAccessible: true,
            isEnabled: true,
            pluginNames: ["d074-plugin"]
        )
        let connectorIntegration = AgentIntegrationConnector(connector: connector)
        let connectorTarget: any AgentIntegration = connectorIntegration
        XCTAssertTrue(connectorIntegration.connector === connector)
        XCTAssertEqual(connectorIntegration.id, "d074-connector")
        XCTAssertEqual(connectorIntegration.displayName, "D074 Connector")
        XCTAssertEqual(connectorTarget.id, "d074-connector")
        XCTAssertEqual(connectorTarget.displayName, "D074 Connector")

        let pluginInvocation = AgentInvocationPlugin(name: "D074 Plugin", uri: "plugin://d074")
        XCTAssertEqual(pluginInvocation.name, "D074 Plugin")
        XCTAssertEqual(pluginInvocation.uri, "plugin://d074")
        XCTAssertEqual(pluginInvocation.key, "plugin:plugin://d074")

        let skillInvocation = AgentInvocationSkill(name: "D074 Skill", path: "/d074/skill")
        XCTAssertEqual(skillInvocation.name, "D074 Skill")
        XCTAssertEqual(skillInvocation.path, "/d074/skill")
        XCTAssertEqual(skillInvocation.key, "skill:/d074/skill")

        let planStep = AgentPlanStep(text: "Verify D074", status: .completed)
        let planProgress = AgentPlanProgress(explanation: "D074 plan", steps: [planStep])
        let turnProgress = AgentTurnProgress(
            text: "D074 text",
            commentary: "D074 commentary",
            reasoning: "D074 reasoning",
            plan: "D074 plan",
            planProgress: planProgress,
            shellOutput: "D074 output",
            shellExitCode: KotlinInt(value: 0),
            workActivity: .writingFiles,
            hookActivities: [hookActivity],
            isTruncated: true
        )
        XCTAssertEqual(turnProgress.text, "D074 text")
        XCTAssertEqual(turnProgress.commentary, "D074 commentary")
        XCTAssertEqual(turnProgress.reasoning, "D074 reasoning")
        XCTAssertEqual(turnProgress.plan, "D074 plan")
        XCTAssertTrue(turnProgress.planProgress === planProgress)
        XCTAssertEqual(turnProgress.shellOutput, "D074 output")
        XCTAssertEqual(turnProgress.shellExitCode?.int32Value, 0)
        XCTAssertTrue(turnProgress.workActivity === AgentWorkActivity.writingFiles)
        XCTAssertTrue(turnProgress.hookActivities.count == 1 && turnProgress.hookActivities[0] === hookActivity)
        XCTAssertTrue(turnProgress.isTruncated)

        let apiKey = CodexAuthenticationMethodApiKey(value: "d074-api-key")
        XCTAssertEqual(apiKey.value, "d074-api-key")
    }

    private func assertD075PendingValues() {
        let conversationId = ConversationId(value: "d075-conversation")
        let approval = AgentPendingApproval(
            requestId: "d075-approval",
            conversationId: conversationId,
            title: "D075 approval",
            details: "D075 approval details"
        )
        XCTAssertTrue(approval.conversationId === conversationId)
        XCTAssertEqual(approval.details, "D075 approval details")
        XCTAssertEqual(approval.requestId, "d075-approval")
        XCTAssertEqual(approval.title, "D075 approval")

        let elicitation = AgentElicitation(
            requestId: "d075-elicitation",
            serverName: "d075-server",
            conversationId: conversationId,
            message: "D075 elicitation",
            form: nil,
            url: nil
        )
        let pendingElicitation = AgentPendingElicitation(elicitation: elicitation)
        XCTAssertTrue(pendingElicitation.conversationId === conversationId)
        XCTAssertTrue(pendingElicitation.elicitation === elicitation)
        XCTAssertEqual(pendingElicitation.requestId, "d075-elicitation")
    }

    private func assertD077McpServerValues() {
        let oauthServer = AgentMcpServer(
            name: "d077-oauth",
            displayName: "D077 OAuth Server",
            authStatus: .oauth,
            configuration: nil,
            origin: .workspace,
            canRemove: true
        )
        XCTAssertEqual(oauthServer.name, "d077-oauth")
        XCTAssertEqual(oauthServer.displayName, "D077 OAuth Server")
        XCTAssertTrue(oauthServer.authStatus === AgentMcpAuthStatus.oauth)
        XCTAssertNil(oauthServer.configuration)
        XCTAssertTrue(oauthServer.origin === AgentResourceOrigin.workspace)
        XCTAssertTrue(oauthServer.canRemove)
        XCTAssertTrue(oauthServer.isAuthorized)

        let signedOutServer = AgentMcpServer(
            name: "d077-signed-out",
            displayName: "D077 Signed-out Server",
            authStatus: .notLoggedIn,
            configuration: nil,
            origin: .workspace,
            canRemove: false
        )
        XCTAssertFalse(signedOutServer.isAuthorized)

        let integration = AgentIntegrationMcpServer(server: oauthServer)
        let integrationTarget: any AgentIntegration = integration
        XCTAssertTrue(integration.server === oauthServer)
        XCTAssertEqual(integration.id, "d077-oauth")
        XCTAssertEqual(integration.displayName, "D077 OAuth Server")
        XCTAssertEqual(integrationTarget.id, "d077-oauth")
        XCTAssertEqual(integrationTarget.displayName, "D077 OAuth Server")
    }

    private func assertD078McpAndElicitationValues() {
        let http = AgentMcpTransportHttp(
            url: "https://example.com/d078-mcp",
            bearerTokenEnvironmentVariable: "MCP_BEARER_TOKEN",
            headers: ["Authorization": "Bearer d078", "X-Trace": "d078"],
            environmentHeaders: ["X-Region": "REGION", "X-Workspace": "WORKSPACE_ID"],
            headersHelper: "security find-generic-password"
        )
        XCTAssertEqual(http.url, "https://example.com/d078-mcp")
        XCTAssertEqual(http.bearerTokenEnvironmentVariable, "MCP_BEARER_TOKEN")
        XCTAssertEqual(http.headers, ["Authorization": "Bearer d078", "X-Trace": "d078"])
        XCTAssertEqual(http.environmentHeaders, ["X-Region": "REGION", "X-Workspace": "WORKSPACE_ID"])
        XCTAssertEqual(http.headersHelper, "security find-generic-password")

        let defaultHttp = AgentMcpTransportHttp(
            url: "http://127.0.0.1:8",
            bearerTokenEnvironmentVariable: nil,
            headers: nil,
            environmentHeaders: nil,
            headersHelper: nil
        )
        XCTAssertNil(defaultHttp.bearerTokenEnvironmentVariable)
        XCTAssertNil(defaultHttp.headers)
        XCTAssertNil(defaultHttp.environmentHeaders)
        XCTAssertNil(defaultHttp.headersHelper)

        let forwardedToken = AgentMcpEnvironmentVariable(name: "TOKEN", source: .remote)
        let forwardedHome = AgentMcpEnvironmentVariable(name: "HOME", source: nil)
        let stdio = AgentMcpTransportStdio(
            command: "npx",
            arguments: ["-y", "@example/mcp", "--stdio"],
            workingDirectory: "/tmp/d078",
            environment: ["NODE_ENV": "test", "TRACE": "d078"],
            forwardedEnvironment: [forwardedToken, forwardedHome]
        )
        XCTAssertEqual(stdio.command, "npx")
        XCTAssertEqual(stdio.arguments, ["-y", "@example/mcp", "--stdio"])
        XCTAssertEqual(stdio.workingDirectory, "/tmp/d078")
        XCTAssertEqual(stdio.environment, ["NODE_ENV": "test", "TRACE": "d078"])
        XCTAssertEqual(stdio.forwardedEnvironment.count, 2)
        XCTAssertTrue(stdio.forwardedEnvironment[0] === forwardedToken)
        XCTAssertTrue(stdio.forwardedEnvironment[1] === forwardedHome)
        XCTAssertEqual(stdio.forwardedEnvironment[0].name, "TOKEN")
        XCTAssertTrue(stdio.forwardedEnvironment[0].source === AgentMcpEnvironmentSource.remote)
        XCTAssertEqual(stdio.forwardedEnvironment[1].name, "HOME")
        XCTAssertNil(stdio.forwardedEnvironment[1].source)

        let defaultStdio = AgentMcpTransportStdio(
            command: "mcp",
            arguments: [],
            workingDirectory: nil,
            environment: nil,
            forwardedEnvironment: []
        )
        XCTAssertEqual(defaultStdio.arguments, [])
        XCTAssertNil(defaultStdio.workingDirectory)
        XCTAssertNil(defaultStdio.environment)
        XCTAssertTrue(defaultStdio.forwardedEnvironment.isEmpty)

        let startupTimeout = KotlinDouble(value: 12.5)
        let toolTimeout = KotlinDouble(value: 45.75)
        let oauth = AgentMcpOauthConfiguration(
            clientId: "d078-client",
            callbackPort: KotlinInt(value: 8_078)
        )
        let readTool = AgentMcpToolConfiguration(approval: .auto_)
        let writeTool = AgentMcpToolConfiguration(approval: .prompt)
        let configuration = AgentMcpServerConfiguration(
            name: "d078-server",
            transport: http,
            authentication: .oauth,
            environmentId: "local",
            isEnabled: true,
            isRequired: true,
            supportsParallelToolCalls: true,
            omitToolsFrom: [.codeMode, .deferred],
            startupTimeoutSeconds: startupTimeout,
            toolTimeoutSeconds: toolTimeout,
            defaultToolApproval: .writes,
            enabledTools: ["read", "write"],
            disabledTools: ["delete", "admin"],
            scopes: ["files.read", "files.write"],
            oauth: oauth,
            oauthResource: "https://example.com/d078-resource",
            tools: ["read": readTool, "write": writeTool]
        )
        XCTAssertEqual(configuration.name, "d078-server")
        XCTAssertTrue((configuration.transport as? AgentMcpTransportHttp) === http)
        XCTAssertTrue(configuration.authentication === AgentMcpAuthentication.oauth)
        XCTAssertEqual(configuration.environmentId, "local")
        XCTAssertTrue(configuration.isEnabled)
        XCTAssertTrue(configuration.isRequired)
        XCTAssertTrue(configuration.supportsParallelToolCalls)
        XCTAssertEqual(configuration.omitToolsFrom?.count, 2)
        XCTAssertTrue(configuration.omitToolsFrom?[0] === AgentMcpToolExposureSurface.codeMode)
        XCTAssertTrue(configuration.omitToolsFrom?[1] === AgentMcpToolExposureSurface.deferred)
        XCTAssertEqual(configuration.startupTimeoutSeconds?.doubleValue, 12.5)
        XCTAssertEqual(configuration.toolTimeoutSeconds?.doubleValue, 45.75)
        XCTAssertTrue(configuration.defaultToolApproval === AgentMcpToolApproval.writes)
        XCTAssertEqual(configuration.enabledTools, ["read", "write"])
        XCTAssertEqual(configuration.disabledTools, ["delete", "admin"])
        XCTAssertEqual(configuration.scopes, ["files.read", "files.write"])
        XCTAssertTrue(configuration.oauth === oauth)
        XCTAssertEqual(configuration.oauth?.clientId, "d078-client")
        XCTAssertEqual(configuration.oauth?.callbackPort?.int32Value, 8_078)
        XCTAssertEqual(configuration.oauthResource, "https://example.com/d078-resource")
        XCTAssertEqual(Set(configuration.tools.keys), Set(["read", "write"]))
        XCTAssertTrue(configuration.tools["read"] === readTool)
        XCTAssertTrue(configuration.tools["write"] === writeTool)
        XCTAssertTrue(configuration.tools["read"]?.approval === AgentMcpToolApproval.auto_)
        XCTAssertTrue(configuration.tools["write"]?.approval === AgentMcpToolApproval.prompt)

        let defaultConfiguration = AgentMcpServerConfiguration(
            name: "d078-defaults",
            transport: defaultHttp,
            authentication: nil,
            environmentId: "local",
            isEnabled: true,
            isRequired: false,
            supportsParallelToolCalls: false,
            omitToolsFrom: nil,
            startupTimeoutSeconds: nil,
            toolTimeoutSeconds: nil,
            defaultToolApproval: nil,
            enabledTools: nil,
            disabledTools: nil,
            scopes: nil,
            oauth: nil,
            oauthResource: nil,
            tools: [:]
        )
        XCTAssertNil(defaultConfiguration.authentication)
        XCTAssertEqual(defaultConfiguration.environmentId, "local")
        XCTAssertTrue(defaultConfiguration.isEnabled)
        XCTAssertFalse(defaultConfiguration.isRequired)
        XCTAssertFalse(defaultConfiguration.supportsParallelToolCalls)
        XCTAssertNil(defaultConfiguration.omitToolsFrom)
        XCTAssertNil(defaultConfiguration.startupTimeoutSeconds)
        XCTAssertNil(defaultConfiguration.toolTimeoutSeconds)
        XCTAssertNil(defaultConfiguration.defaultToolApproval)
        XCTAssertNil(defaultConfiguration.enabledTools)
        XCTAssertNil(defaultConfiguration.disabledTools)
        XCTAssertNil(defaultConfiguration.scopes)
        XCTAssertNil(defaultConfiguration.oauth)
        XCTAssertNil(defaultConfiguration.oauthResource)
        XCTAssertTrue(defaultConfiguration.tools.isEmpty)

        let text = AgentFormValueText(value: "D078 text")
        let number = AgentFormValueNumber(value: 78.5)
        let boolean = AgentFormValueBooleanValue(value: true)
        let list = AgentFormValueTextList(value: ["D078", "ordered", "list"])
        let response = AgentElicitationResponse(
            action: .accept,
            content: ["text": text, "number": number, "boolean": boolean, "list": list]
        )
        XCTAssertTrue(response.action === AgentElicitationAction.accept)
        XCTAssertEqual(Set(response.content.keys), Set(["text", "number", "boolean", "list"]))
        XCTAssertTrue((response.content["text"] as? AgentFormValueText) === text)
        XCTAssertEqual((response.content["text"] as? AgentFormValueText)?.value, "D078 text")
        XCTAssertTrue((response.content["number"] as? AgentFormValueNumber) === number)
        XCTAssertEqual((response.content["number"] as? AgentFormValueNumber)?.value, 78.5)
        XCTAssertTrue((response.content["boolean"] as? AgentFormValueBooleanValue) === boolean)
        XCTAssertEqual((response.content["boolean"] as? AgentFormValueBooleanValue)?.value, true)
        XCTAssertTrue((response.content["list"] as? AgentFormValueTextList) === list)
        XCTAssertEqual((response.content["list"] as? AgentFormValueTextList)?.value, ["D078", "ordered", "list"])

        let emptyResponse = AgentElicitationResponse(action: .decline, content: [:])
        XCTAssertTrue(emptyResponse.action === AgentElicitationAction.decline)
        XCTAssertTrue(emptyResponse.content.isEmpty)
    }

    private func assertD079ConversationValues() {
        let plugin = AgentInvocationPlugin(name: "D079 Plugin", uri: "plugin://d079")
        let skill = AgentInvocationSkill(name: "D079 Skill", path: "/d079/skill")
        let richMessage = AgentMessage(
            id: "d079-rich-message",
            clientMessageId: "d079-rich-client-message",
            role: .assistant,
            text: "D079 rich message",
            collaborationMode: .plan,
            reasoning: "D079 reasoning",
            plan: "D079 plan",
            shellCommand: "printf d079",
            exitCode: KotlinInt(value: 79),
            capabilities: [.webSearch],
            invocations: [plugin, skill]
        )
        XCTAssertEqual(richMessage.id, "d079-rich-message")
        XCTAssertEqual(richMessage.clientMessageId, "d079-rich-client-message")
        XCTAssertTrue(richMessage.role === AgentMessageRole.assistant)
        XCTAssertEqual(richMessage.text, "D079 rich message")
        XCTAssertTrue(richMessage.collaborationMode === AgentCollaborationMode.plan)
        XCTAssertEqual(richMessage.reasoning, "D079 reasoning")
        XCTAssertEqual(richMessage.plan, "D079 plan")
        XCTAssertEqual(richMessage.shellCommand, "printf d079")
        XCTAssertEqual(richMessage.exitCode?.int32Value, 79)
        XCTAssertEqual(richMessage.capabilities.count, 1)
        XCTAssertTrue(richMessage.capabilities.contains(AgentCapability.webSearch))
        XCTAssertEqual(richMessage.invocations.count, 2)
        XCTAssertTrue((richMessage.invocations[0] as? AgentInvocationPlugin) === plugin)
        XCTAssertTrue((richMessage.invocations[1] as? AgentInvocationSkill) === skill)
        let firstInvocation: any AgentInvocation = richMessage.invocations[0]
        let secondInvocation: any AgentInvocation = richMessage.invocations[1]
        XCTAssertEqual(firstInvocation.name, "D079 Plugin")
        XCTAssertEqual(firstInvocation.key, "plugin:plugin://d079")
        XCTAssertEqual(secondInvocation.name, "D079 Skill")
        XCTAssertEqual(secondInvocation.key, "skill:/d079/skill")

        let defaultMessage = AgentMessage(
            id: "d079-default-message",
            clientMessageId: nil,
            role: .user,
            text: "D079 default message",
            collaborationMode: .default_,
            reasoning: nil,
            plan: nil,
            shellCommand: nil,
            exitCode: nil,
            capabilities: [],
            invocations: []
        )
        XCTAssertNil(defaultMessage.clientMessageId)
        XCTAssertTrue(defaultMessage.role === AgentMessageRole.user)
        XCTAssertTrue(defaultMessage.collaborationMode === AgentCollaborationMode.default_)
        XCTAssertNil(defaultMessage.reasoning)
        XCTAssertNil(defaultMessage.plan)
        XCTAssertNil(defaultMessage.shellCommand)
        XCTAssertNil(defaultMessage.exitCode)
        XCTAssertTrue(defaultMessage.capabilities.isEmpty)
        XCTAssertTrue(defaultMessage.invocations.isEmpty)

        let richRequest = AgentTurnRequest(
            prompt: "D079 rich request",
            clientMessageId: "d079-request-client-message",
            model: "d079-model",
            effort: "high",
            serviceTier: "fast",
            approvalPreset: .strict,
            capabilities: [.webSearch],
            invocations: [skill, plugin],
            collaborationMode: .plan
        )
        XCTAssertEqual(richRequest.prompt, "D079 rich request")
        XCTAssertEqual(richRequest.clientMessageId, "d079-request-client-message")
        XCTAssertEqual(richRequest.model, "d079-model")
        XCTAssertEqual(richRequest.effort, "high")
        XCTAssertEqual(richRequest.serviceTier, "fast")
        XCTAssertTrue(richRequest.approvalPreset === AgentApprovalPreset.strict)
        XCTAssertEqual(richRequest.capabilities.count, 1)
        XCTAssertTrue(richRequest.capabilities.contains(AgentCapability.webSearch))
        XCTAssertEqual(richRequest.invocations.count, 2)
        XCTAssertTrue((richRequest.invocations[0] as? AgentInvocationSkill) === skill)
        XCTAssertTrue((richRequest.invocations[1] as? AgentInvocationPlugin) === plugin)
        XCTAssertTrue(richRequest.collaborationMode === AgentCollaborationMode.plan)

        let defaultRequest = AgentTurnRequest(
            prompt: "D079 default request",
            clientMessageId: nil,
            model: nil,
            effort: nil,
            serviceTier: nil,
            approvalPreset: .autoReview,
            capabilities: [],
            invocations: [],
            collaborationMode: .default_
        )
        XCTAssertNil(defaultRequest.clientMessageId)
        XCTAssertNil(defaultRequest.model)
        XCTAssertNil(defaultRequest.effort)
        XCTAssertNil(defaultRequest.serviceTier)
        XCTAssertTrue(defaultRequest.approvalPreset === AgentApprovalPreset.autoReview)
        XCTAssertTrue(defaultRequest.capabilities.isEmpty)
        XCTAssertTrue(defaultRequest.invocations.isEmpty)
        XCTAssertTrue(defaultRequest.collaborationMode === AgentCollaborationMode.default_)

        let summary = AgentConversationSummary(
            conversationId: ConversationId(value: "d079-conversation"),
            title: "D079 Conversation",
            updatedAtEpochSeconds: 79
        )
        let conversation = AgentConversation(summary: summary, messages: [richMessage, defaultMessage])
        XCTAssertTrue(conversation.summary === summary)
        XCTAssertEqual(conversation.messages.count, 2)
        XCTAssertTrue(conversation.messages[0] === richMessage)
        XCTAssertTrue(conversation.messages[1] === defaultMessage)
    }

    private func assertD080StateSnapshots() {
        let failure = CodexFailure(
            code: "d080_failure",
            message: "D080 failure",
            isRecoverable: true
        )
        let pendingSignInUrl = CodexAuthorizationUrl.companion.chatGpt(
            value: "https://auth.openai.com/d080"
        )
        let deviceVerificationUrl = CodexAuthorizationUrl.companion.external(
            value: "https://example.com/d080/device"
        )
        let authenticationState = AgentAuthenticationState(
            status: .authenticating,
            pendingSignInUrl: pendingSignInUrl,
            deviceVerificationUrl: deviceVerificationUrl,
            deviceUserCode: "D080-CODE",
            failure: failure
        )
        XCTAssertTrue(authenticationState.status === AgentAuthenticationStatus.authenticating)
        XCTAssertTrue(authenticationState.pendingSignInUrl === pendingSignInUrl)
        XCTAssertTrue(authenticationState.deviceVerificationUrl === deviceVerificationUrl)
        XCTAssertEqual(authenticationState.deviceUserCode, "D080-CODE")
        XCTAssertTrue(authenticationState.failure === failure)

        let defaultAuthenticationState = AgentAuthenticationState(
            status: .signedOut,
            pendingSignInUrl: nil,
            deviceVerificationUrl: nil,
            deviceUserCode: nil,
            failure: nil
        )
        XCTAssertTrue(defaultAuthenticationState.status === AgentAuthenticationStatus.signedOut)
        XCTAssertNil(defaultAuthenticationState.pendingSignInUrl)
        XCTAssertNil(defaultAuthenticationState.deviceVerificationUrl)
        XCTAssertNil(defaultAuthenticationState.deviceUserCode)
        XCTAssertNil(defaultAuthenticationState.failure)

        let conversationId = ConversationId(value: "d080-conversation")
        let summary = AgentConversationSummary(
            conversationId: conversationId,
            title: "D080 Conversation",
            updatedAtEpochSeconds: 80
        )
        let conversation = AgentConversation(summary: summary, messages: [])
        let turnProgress = AgentTurnProgress(
            text: "D080 text",
            commentary: "D080 commentary",
            reasoning: "D080 reasoning",
            plan: "D080 plan",
            planProgress: nil,
            shellOutput: "D080 output",
            shellExitCode: KotlinInt(value: 80),
            workActivity: .runningCommand,
            hookActivities: [],
            isTruncated: false
        )
        let conversationState = AgentConversationState(
            status: .failed,
            conversationId: conversationId,
            conversation: conversation,
            turnProgress: turnProgress,
            model: "d080-model",
            effort: "high",
            serviceTier: "fast",
            failure: failure
        )
        XCTAssertTrue(conversationState.status === AgentConversationStatus.failed)
        XCTAssertTrue(conversationState.conversationId === conversationId)
        XCTAssertTrue(conversationState.conversation === conversation)
        XCTAssertTrue(conversationState.turnProgress === turnProgress)
        XCTAssertEqual(conversationState.model, "d080-model")
        XCTAssertEqual(conversationState.effort, "high")
        XCTAssertEqual(conversationState.serviceTier, "fast")
        XCTAssertTrue(conversationState.failure === failure)
        XCTAssertTrue(conversationState.canStartTurn)
        XCTAssertTrue(conversationState.canReload)
        XCTAssertFalse(conversationState.canCancelTurn)

        let defaultTurnProgress = AgentTurnProgress(
            text: "",
            commentary: "",
            reasoning: "",
            plan: "",
            planProgress: nil,
            shellOutput: "",
            shellExitCode: nil,
            workActivity: nil,
            hookActivities: [],
            isTruncated: false
        )
        let defaultConversationState = AgentConversationState(
            status: .theNew,
            conversationId: nil,
            conversation: nil,
            turnProgress: defaultTurnProgress,
            model: nil,
            effort: nil,
            serviceTier: nil,
            failure: nil
        )
        XCTAssertTrue(defaultConversationState.status === AgentConversationStatus.theNew)
        XCTAssertNil(defaultConversationState.conversationId)
        XCTAssertNil(defaultConversationState.conversation)
        XCTAssertTrue(defaultConversationState.turnProgress === defaultTurnProgress)
        XCTAssertNil(defaultConversationState.model)
        XCTAssertNil(defaultConversationState.effort)
        XCTAssertNil(defaultConversationState.serviceTier)
        XCTAssertNil(defaultConversationState.failure)
        XCTAssertFalse(defaultConversationState.canStartTurn)
        XCTAssertFalse(defaultConversationState.canReload)
        XCTAssertFalse(defaultConversationState.canCancelTurn)

        let nonRecoverableFailure = CodexFailure(
            code: "d080_terminal",
            message: "D080 terminal failure",
            isRecoverable: false
        )
        let snapshot: (
            AgentConversationStatus, ConversationId?, CodexFailure?
        ) -> AgentConversationState = { status, id, stateFailure in
            AgentConversationState(
                status: status,
                conversationId: id,
                conversation: nil,
                turnProgress: defaultTurnProgress,
                model: nil,
                effort: nil,
                serviceTier: nil,
                failure: stateFailure
            )
        }
        let capabilityMatrix: [(
            String, AgentConversationState, Bool, Bool, Bool
        )] = [
            ("NEW", snapshot(.theNew, conversationId, nil), false, false, false),
            ("OPENING", snapshot(.opening, conversationId, nil), false, false, false),
            ("READY", snapshot(.ready, conversationId, nil), true, true, false),
            ("READY without ID", snapshot(.ready, nil, nil), false, false, false),
            ("STARTING_TURN", snapshot(.startingTurn, conversationId, nil), false, false, true),
            ("RUNNING_TURN", snapshot(.runningTurn, conversationId, nil), false, false, true),
            ("CANCELLING_TURN", snapshot(.cancellingTurn, conversationId, nil), false, false, false),
            ("RELOADING", snapshot(.reloading, conversationId, nil), false, false, false),
            ("FAILED recoverable", snapshot(.failed, conversationId, failure), true, true, false),
            ("FAILED terminal", snapshot(.failed, conversationId, nonRecoverableFailure), false, true, false),
            ("FAILED without ID", snapshot(.failed, nil, failure), false, false, false),
            ("CLOSED", snapshot(.closed, conversationId, nil), false, false, false),
        ]
        for (label, state, canStart, canReload, canCancel) in capabilityMatrix {
            XCTAssertEqual(state.canStartTurn, canStart, label)
            XCTAssertEqual(state.canReload, canReload, label)
            XCTAssertEqual(state.canCancelTurn, canCancel, label)
        }

        let connector = AgentConnector(
            id: "d080-connector",
            name: "D080 Connector",
            description: "D080 integration target",
            installUrl: nil,
            isAccessible: true,
            isEnabled: true,
            pluginNames: []
        )
        let integration = AgentIntegrationConnector(connector: connector)
        let integrationState = AgentIntegrationAuthorizationState(
            status: .failed,
            target: integration,
            failure: failure
        )
        XCTAssertTrue(integrationState.status === AgentIntegrationAuthorizationStatus.failed)
        XCTAssertTrue((integrationState.target as? AgentIntegrationConnector) === integration)
        XCTAssertTrue(integrationState.failure === failure)

        let defaultIntegrationState = AgentIntegrationAuthorizationState(
            status: .idle,
            target: nil,
            failure: nil
        )
        XCTAssertTrue(defaultIntegrationState.status === AgentIntegrationAuthorizationStatus.idle)
        XCTAssertNil(defaultIntegrationState.target)
        XCTAssertNil(defaultIntegrationState.failure)

        let otherConversationId = ConversationId(value: "d080-other-conversation")
        let approval = AgentPendingApproval(
            requestId: "d080-resolving",
            conversationId: conversationId,
            title: "D080 approval",
            details: "D080 approval details"
        )
        let elicitation = AgentElicitation(
            requestId: "d080-elicitation",
            serverName: "d080-server",
            conversationId: conversationId,
            message: "D080 elicitation",
            form: nil,
            url: nil
        )
        let pendingElicitation = AgentPendingElicitation(elicitation: elicitation)
        let otherApproval = AgentPendingApproval(
            requestId: "d080-other",
            conversationId: otherConversationId,
            title: "D080 other approval",
            details: "D080 other approval details"
        )
        let interactionState = AgentInteractionState(
            pending: [approval, pendingElicitation, otherApproval],
            resolvingRequestIds: ["d080-resolving"],
            failure: failure
        )
        XCTAssertTrue(interactionState.failure === failure)
        XCTAssertEqual(interactionState.pending.count, 3)
        XCTAssertTrue((interactionState.pending[0] as? AgentPendingApproval) === approval)
        XCTAssertTrue((interactionState.pending[1] as? AgentPendingElicitation) === pendingElicitation)
        XCTAssertTrue((interactionState.pending[2] as? AgentPendingApproval) === otherApproval)
        let approvalInteraction: any AgentPendingInteraction = interactionState.pending[0]
        let elicitationInteraction: any AgentPendingInteraction = interactionState.pending[1]
        XCTAssertEqual(approvalInteraction.requestId, "d080-resolving")
        XCTAssertTrue(approvalInteraction.conversationId === conversationId)
        XCTAssertEqual(elicitationInteraction.requestId, "d080-elicitation")
        XCTAssertTrue(elicitationInteraction.conversationId === conversationId)
        XCTAssertEqual(interactionState.resolvingRequestIds.count, 1)
        XCTAssertTrue(interactionState.resolvingRequestIds.contains("d080-resolving"))

        let conversationPending = interactionState.pendingFor(conversationId: conversationId)
        XCTAssertEqual(conversationPending.count, 2)
        XCTAssertTrue((conversationPending[0] as? AgentPendingApproval) === approval)
        XCTAssertTrue((conversationPending[1] as? AgentPendingElicitation) === pendingElicitation)
        let otherPending = interactionState.pendingFor(conversationId: otherConversationId)
        XCTAssertEqual(otherPending.count, 1)
        XCTAssertTrue((otherPending[0] as? AgentPendingApproval) === otherApproval)
        XCTAssertTrue(
            interactionState.pendingFor(
                conversationId: ConversationId(value: "d080-unknown-conversation")
            ).isEmpty
        )

        XCTAssertTrue(interactionState.isResolving(interaction: approval))
        let sameIdClone = AgentPendingApproval(
            requestId: "d080-resolving",
            conversationId: conversationId,
            title: "D080 cloned approval",
            details: "D080 cloned approval details"
        )
        XCTAssertFalse(interactionState.isResolving(interaction: sameIdClone))
        XCTAssertFalse(interactionState.isResolving(interaction: pendingElicitation))
        XCTAssertFalse(interactionState.isResolving(interaction: otherApproval))

        let defaultInteractionState = AgentInteractionState(
            pending: [],
            resolvingRequestIds: [],
            failure: nil
        )
        XCTAssertTrue(defaultInteractionState.pending.isEmpty)
        XCTAssertTrue(defaultInteractionState.resolvingRequestIds.isEmpty)
        XCTAssertNil(defaultInteractionState.failure)
        XCTAssertTrue(defaultInteractionState.pendingFor(conversationId: conversationId).isEmpty)
        XCTAssertFalse(defaultInteractionState.isResolving(interaction: approval))
    }

    private func assertD081SingletonObjects() {
        let agent: AgentHookHandlerAgent = AgentHookHandlerAgent.shared
        let stableAgent: AgentHookHandlerAgent = AgentHookHandlerAgent.shared
        let prompt: AgentHookHandlerPrompt = AgentHookHandlerPrompt.shared
        let stablePrompt: AgentHookHandlerPrompt = AgentHookHandlerPrompt.shared
        XCTAssertTrue(agent.isEqual(stableAgent))
        XCTAssertTrue(prompt.isEqual(stablePrompt))
        XCTAssertFalse(agent.isEqual(prompt))

        let browser: CodexAuthenticationMethodChatGptBrowser =
            CodexAuthenticationMethodChatGptBrowser.shared
        let stableBrowser: CodexAuthenticationMethodChatGptBrowser =
            CodexAuthenticationMethodChatGptBrowser.shared
        let deviceCode: CodexAuthenticationMethodChatGptDeviceCode =
            CodexAuthenticationMethodChatGptDeviceCode.shared
        let stableDeviceCode: CodexAuthenticationMethodChatGptDeviceCode =
            CodexAuthenticationMethodChatGptDeviceCode.shared
        XCTAssertTrue(browser.isEqual(stableBrowser))
        XCTAssertTrue(deviceCode.isEqual(stableDeviceCode))
        XCTAssertFalse(browser.isEqual(deviceCode))

        let closed: CodexHostStateClosed = CodexHostStateClosed.shared
        let stableClosed: CodexHostStateClosed = CodexHostStateClosed.shared
        let new: CodexHostStateNew = CodexHostStateNew.shared
        let stableNew: CodexHostStateNew = CodexHostStateNew.shared
        let restoring: CodexHostStateRestoring = CodexHostStateRestoring.shared
        let stableRestoring: CodexHostStateRestoring = CodexHostStateRestoring.shared
        XCTAssertTrue(closed.isEqual(stableClosed))
        XCTAssertTrue(new.isEqual(stableNew))
        XCTAssertTrue(restoring.isEqual(stableRestoring))
        XCTAssertFalse(closed.isEqual(new))
        XCTAssertFalse(closed.isEqual(restoring))
        XCTAssertFalse(new.isEqual(restoring))
    }

    private func assertD082ElicitationHelpers() {
        let alpha = AgentFormOption(value: "a", title: "Alpha", description: nil)
        let beta = AgentFormOption(value: "b", title: "Beta", description: nil)
        let defaultName = AgentFormValueText(value: "Ada")
        var defaultSelections = ["a"]
        let defaultMany = AgentFormValueTextList(value: defaultSelections)

        let name = AgentFormField(
            name: "name",
            title: "Name",
            description: nil,
            isRequired: true,
            type: .string,
            options: [],
            defaultValue: defaultName,
            minimum: nil,
            maximum: nil,
            format: nil,
            minimumLength: KotlinLong(value: 2),
            maximumLength: KotlinLong(value: 4),
            minimumSelections: nil,
            maximumSelections: nil,
            allowsOther: false,
            isSecret: false
        )
        let email = AgentFormField(
            name: "email",
            title: "Email",
            description: nil,
            isRequired: false,
            type: .string,
            options: [],
            defaultValue: nil,
            minimum: nil,
            maximum: nil,
            format: .email,
            minimumLength: nil,
            maximumLength: nil,
            minimumSelections: nil,
            maximumSelections: nil,
            allowsOther: false,
            isSecret: false
        )
        let count = AgentFormField(
            name: "count",
            title: "Count",
            description: nil,
            isRequired: false,
            type: .integer,
            options: [],
            defaultValue: nil,
            minimum: KotlinDouble(value: 1),
            maximum: KotlinDouble(value: 3),
            format: nil,
            minimumLength: nil,
            maximumLength: nil,
            minimumSelections: nil,
            maximumSelections: nil,
            allowsOther: false,
            isSecret: false
        )
        let ratio = AgentFormField(
            name: "ratio",
            title: "Ratio",
            description: nil,
            isRequired: false,
            type: .number,
            options: [],
            defaultValue: nil,
            minimum: KotlinDouble(value: 0),
            maximum: KotlinDouble(value: 1),
            format: nil,
            minimumLength: nil,
            maximumLength: nil,
            minimumSelections: nil,
            maximumSelections: nil,
            allowsOther: false,
            isSecret: false
        )
        let enabled = AgentFormField(
            name: "enabled",
            title: "Enabled",
            description: nil,
            isRequired: false,
            type: .boolean,
            options: [],
            defaultValue: nil,
            minimum: nil,
            maximum: nil,
            format: nil,
            minimumLength: nil,
            maximumLength: nil,
            minimumSelections: nil,
            maximumSelections: nil,
            allowsOther: false,
            isSecret: false
        )
        let choice = AgentFormField(
            name: "choice",
            title: "Choice",
            description: nil,
            isRequired: false,
            type: .singleSelect,
            options: [alpha, beta],
            defaultValue: nil,
            minimum: nil,
            maximum: nil,
            format: nil,
            minimumLength: nil,
            maximumLength: nil,
            minimumSelections: nil,
            maximumSelections: nil,
            allowsOther: false,
            isSecret: false
        )
        let many = AgentFormField(
            name: "many",
            title: "Many",
            description: nil,
            isRequired: true,
            type: .multiSelect,
            options: [alpha, beta],
            defaultValue: defaultMany,
            minimum: nil,
            maximum: nil,
            format: nil,
            minimumLength: nil,
            maximumLength: nil,
            minimumSelections: KotlinLong(value: 1),
            maximumSelections: KotlinLong(value: 2),
            allowsOther: false,
            isSecret: false
        )
        let elicitation = AgentElicitation(
            requestId: "d082-request",
            serverName: "d082-server",
            conversationId: ConversationId(value: "d082-conversation"),
            message: "Configure D082",
            form: [name, email, count, ratio, enabled, choice, many],
            url: nil
        )

        let initialValues = elicitation.initialValues()
        defaultSelections.append("b")
        XCTAssertEqual(Set(initialValues.keys), Set(["name", "many"]))
        XCTAssertEqual((initialValues["name"] as? AgentFormValueText)?.value, "Ada")
        XCTAssertEqual((initialValues["many"] as? AgentFormValueTextList)?.value, ["a"])
        XCTAssertNil(initialValues["email"])

        let validContent: [String: any AgentFormValue] = [
            "name": AgentFormValueText(value: "okay"),
            "email": AgentFormValueText(value: "user@example.com"),
            "count": AgentFormValueNumber(value: 2),
            "ratio": AgentFormValueNumber(value: 0.5),
            "enabled": AgentFormValueBooleanValue(value: true),
            "choice": AgentFormValueText(value: "a"),
            "many": AgentFormValueTextList(value: ["a", "b"]),
        ]
        let valid = elicitation.validate(content: validContent)
        XCTAssertTrue(valid.isValid)
        XCTAssertTrue(valid.issues.isEmpty)

        var missingContent = validContent
        missingContent.removeValue(forKey: "name")
        let missing = elicitation.validate(content: missingContent)
        XCTAssertEqual(missing.issues.count, 1)
        XCTAssertEqual(missing.issues[0].fieldName, "name")
        XCTAssertTrue(missing.issues[0].reason === AgentElicitationValidationReason.missingRequired)

        var unknownContent = validContent
        unknownContent["unknown"] = AgentFormValueText(value: "value")
        let unknown = elicitation.validate(content: unknownContent)
        XCTAssertEqual(unknown.issues.count, 1)
        XCTAssertEqual(unknown.issues[0].fieldName, "unknown")
        XCTAssertTrue(unknown.issues[0].reason === AgentElicitationValidationReason.unknownField)

        let invalidValues: [(String, any AgentFormValue, AgentElicitationValidationReason)] = [
            ("name", AgentFormValueNumber(value: 1), .invalidType),
            ("count", AgentFormValueNumber(value: .nan), .nonFiniteNumber),
            ("name", AgentFormValueText(value: "x"), .belowMinimum),
            ("name", AgentFormValueText(value: "abcde"), .aboveMaximum),
            ("count", AgentFormValueNumber(value: 1.5), .nonInteger),
            ("email", AgentFormValueText(value: "invalid"), .invalidFormat),
            ("choice", AgentFormValueText(value: "z"), .invalidSelection),
            ("many", AgentFormValueTextList(value: ["a", "a"]), .duplicateSelection),
        ]
        for (fieldName, value, reason) in invalidValues {
            var content = validContent
            content[fieldName] = value
            let validation = elicitation.validate(content: content)
            XCTAssertEqual(validation.issues.count, 1)
            XCTAssertEqual(validation.issues[0].fieldName, fieldName)
            XCTAssertTrue(validation.issues[0].reason === reason)
        }

        var selected = ["a"]
        let selectedValue = AgentFormValueTextList(value: selected)
        var acceptedContent = validContent
        acceptedContent["many"] = selectedValue
        let accepted = elicitation.accept(content: acceptedContent)
        selected.append("b")
        XCTAssertTrue(accepted.action === AgentElicitationAction.accept)
        XCTAssertEqual(Set(accepted.content.keys), Set(acceptedContent.keys))
        XCTAssertEqual((accepted.content["name"] as? AgentFormValueText)?.value, "okay")
        XCTAssertEqual((accepted.content["many"] as? AgentFormValueTextList)?.value, ["a"])
        XCTAssertTrue(elicitation.accepts(response: accepted))

        var invalidAcceptedContent = validContent
        invalidAcceptedContent["name"] = AgentFormValueText(value: "")
        let invalidAccepted = AgentElicitationResponse(
            action: .accept,
            content: invalidAcceptedContent
        )
        XCTAssertFalse(elicitation.accepts(response: invalidAccepted))

        let companion = AgentElicitationResponse.companion
        let cancelled = companion.cancel()
        let declined = companion.decline()
        XCTAssertTrue(cancelled.action === AgentElicitationAction.cancel)
        XCTAssertTrue(cancelled.content.isEmpty)
        XCTAssertTrue(declined.action === AgentElicitationAction.decline)
        XCTAssertTrue(declined.content.isEmpty)
        XCTAssertTrue(elicitation.accepts(response: cancelled))
        XCTAssertTrue(elicitation.accepts(response: declined))
        XCTAssertFalse(
            elicitation.accepts(
                response: AgentElicitationResponse(
                    action: .cancel,
                    content: ["name": AgentFormValueText(value: "okay")]
                )
            )
        )
        XCTAssertFalse(
            elicitation.accepts(
                response: AgentElicitationResponse(
                    action: .decline,
                    content: ["name": AgentFormValueText(value: "okay")]
                )
            )
        )

        let urlOnly = AgentElicitation(
            requestId: "d082-url-request",
            serverName: "d082-server",
            conversationId: ConversationId(value: "d082-url-conversation"),
            message: "Authorize D082",
            form: nil,
            url: "https://example.com/d082"
        )
        XCTAssertTrue(
            urlOnly.accepts(response: AgentElicitationResponse(action: .accept, content: [:]))
        )
        XCTAssertFalse(
            urlOnly.accepts(
                response: AgentElicitationResponse(
                    action: .accept,
                    content: ["unexpected": AgentFormValueText(value: "value")]
                )
            )
        )

        XCTAssertFalse(name.accepts(value: nil))
        XCTAssertTrue(name.accepts(value: AgentFormValueText(value: "okay")))
        XCTAssertFalse(name.accepts(value: AgentFormValueText(value: " ")))
        XCTAssertFalse(name.accepts(value: AgentFormValueText(value: "x")))
        XCTAssertFalse(name.accepts(value: AgentFormValueText(value: "abcde")))
        XCTAssertFalse(name.accepts(value: AgentFormValueBooleanValue(value: true)))
        XCTAssertTrue(email.accepts(value: nil))
        XCTAssertTrue(email.accepts(value: AgentFormValueText(value: "user@example.com")))
        XCTAssertFalse(email.accepts(value: AgentFormValueText(value: "invalid")))
        XCTAssertTrue(count.accepts(value: AgentFormValueNumber(value: 1)))
        XCTAssertTrue(count.accepts(value: AgentFormValueNumber(value: 3)))
        XCTAssertFalse(count.accepts(value: AgentFormValueNumber(value: 0)))
        XCTAssertFalse(count.accepts(value: AgentFormValueNumber(value: 4)))
        XCTAssertFalse(count.accepts(value: AgentFormValueNumber(value: 1.5)))
        XCTAssertFalse(count.accepts(value: AgentFormValueNumber(value: .infinity)))
        XCTAssertFalse(count.accepts(value: AgentFormValueText(value: "2")))
        XCTAssertTrue(ratio.accepts(value: AgentFormValueNumber(value: 0.5)))
        XCTAssertFalse(ratio.accepts(value: AgentFormValueText(value: "0.5")))
        XCTAssertTrue(enabled.accepts(value: AgentFormValueBooleanValue(value: false)))
        XCTAssertFalse(enabled.accepts(value: AgentFormValueText(value: "false")))
        XCTAssertTrue(choice.accepts(value: AgentFormValueText(value: "a")))
        XCTAssertFalse(choice.accepts(value: AgentFormValueText(value: "z")))
        XCTAssertFalse(choice.accepts(value: AgentFormValueNumber(value: 1)))
        XCTAssertTrue(many.accepts(value: AgentFormValueTextList(value: ["a", "b"])))
        XCTAssertFalse(many.accepts(value: AgentFormValueTextList(value: [])))
        XCTAssertFalse(many.accepts(value: AgentFormValueTextList(value: ["a", "a"])))
        XCTAssertFalse(many.accepts(value: AgentFormValueTextList(value: ["z"])))
        XCTAssertFalse(many.accepts(value: AgentFormValueTextList(value: ["a", "b", "a"])))
        XCTAssertFalse(many.accepts(value: AgentFormValueText(value: "a")))

    }

    private func assertD084HostLifecycle() async throws {
        let sandbox = FileManager.default.temporaryDirectory.appendingPathComponent(
            "codex-agent-swift-d084-\(UUID().uuidString)",
            isDirectory: true
        )
        let workspaceURL = sandbox.appendingPathComponent("workspace", isDirectory: true)
        try FileManager.default.createDirectory(
            at: workspaceURL,
            withIntermediateDirectories: true
        )
        defer { try? FileManager.default.removeItem(at: sandbox) }

        let firstRestoreEntered = expectation(description: "D084 first restore entered")
        let selectionEntered = expectation(description: "D084 selection entered")
        let firstPrepareEntered = expectation(description: "D084 first prepare entered")
        let secondPrepareEntered = expectation(description: "D084 second prepare entered")

        let newObserved = expectation(description: "D084 New observed")
        let firstRestoringObserved = expectation(description: "D084 first Restoring observed")
        let workspaceRequiredObserved = expectation(description: "D084 WorkspaceRequired observed")
        let secondRestoringObserved = expectation(description: "D084 second Restoring observed")
        let firstPreparingObserved = expectation(description: "D084 first Preparing observed")
        let failedObserved = expectation(description: "D084 Failed observed")
        let secondPreparingObserved = expectation(description: "D084 second Preparing observed")
        let readyObserved = expectation(description: "D084 Ready observed")
        let closedObserved = expectation(description: "D084 Closed observed")
        let lateStateObserved = expectation(description: "D084 state observed after Closed")
        lateStateObserved.isInverted = true

        let backingPlatform = IosCodexPlatform(
            sandboxRootPath: sandbox.path,
            credentialProtection: .whenUnlocked,
            authorizationBrowser: D084AuthorizationBrowser(),
            codexHomePath: sandbox
                .appendingPathComponent("Library/Application Support/CodexAgent", isDirectory: true)
                .path,
            storageRoots: nil
        )
        let platform = D084GatedPlatform(
            backing: backingPlatform,
            restoreEntered: { firstRestoreEntered.fulfill() },
            selectionEntered: { selectionEntered.fulfill() },
            prepareEntered: [
                { firstPrepareEntered.fulfill() },
                { secondPrepareEntered.fulfill() },
            ]
        )
        let host = CodexHost(
            platform: platform,
            clientInfo: CodexClientInfo(
                name: "swift-d084",
                title: "Swift D084",
                version: "0.2.0"
            )
        )

        let lifecycleReceipt = Task { () -> [String] in
            var receipt: [String] = []
            var restoringCount = 0
            var preparingCount = 0
            var didObserveClosed = false
            for await state in host.lifecycleStates {
                if didObserveClosed {
                    lateStateObserved.fulfill()
                    return receipt
                }
                switch state {
                case is CodexHostStateNew:
                    receipt.append("New")
                    newObserved.fulfill()
                case is CodexHostStateRestoring:
                    restoringCount += 1
                    receipt.append("Restoring")
                    if restoringCount == 1 {
                        firstRestoringObserved.fulfill()
                    } else {
                        secondRestoringObserved.fulfill()
                    }
                case is CodexHostStateWorkspaceRequired:
                    receipt.append("WorkspaceRequired")
                    workspaceRequiredObserved.fulfill()
                case is CodexHostStatePreparing:
                    preparingCount += 1
                    receipt.append("Preparing")
                    if preparingCount == 1 {
                        firstPreparingObserved.fulfill()
                    } else {
                        secondPreparingObserved.fulfill()
                    }
                case is CodexHostStateFailed:
                    receipt.append("Failed")
                    failedObserved.fulfill()
                case is CodexHostStateReady:
                    receipt.append("Ready")
                    readyObserved.fulfill()
                case is CodexHostStateClosed:
                    receipt.append("Closed")
                    closedObserved.fulfill()
                    didObserveClosed = true
                default:
                    XCTFail("Unexpected D084 host state: \(type(of: state))")
                }
            }
            return receipt
        }
        defer { lifecycleReceipt.cancel() }

        _ = try XCTUnwrap(host.lifecycleState.value as? CodexHostStateNew)
        await fulfillment(of: [newObserved], timeout: 30)

        let start = Task { try await host.start() }
        await fulfillment(
            of: [firstRestoringObserved, firstRestoreEntered],
            timeout: 30
        )
        platform.releaseRestore()
        try await start.value
        await fulfillment(of: [workspaceRequiredObserved], timeout: 30)

        let workspaceRequired = try XCTUnwrap(
            host.lifecycleState.value as? CodexHostStateWorkspaceRequired
        )
        XCTAssertTrue(
            workspaceRequired.requirement.reason === CodexWorkspaceSelectionReason.notSelected
        )
        let workspaceRequiredCopy = CodexHostStateWorkspaceRequired(
            requirement: workspaceRequired.requirement
        )
        XCTAssertEqual(workspaceRequiredCopy.requirement.message, workspaceRequired.requirement.message)

        let selection = Task {
            try await host.selectWorkspace(selection: IosCodexWorkspaceSelection(url: workspaceURL))
        }
        await fulfillment(
            of: [secondRestoringObserved, selectionEntered],
            timeout: 30
        )
        platform.releaseSelection()
        await fulfillment(
            of: [firstPreparingObserved, firstPrepareEntered],
            timeout: 30
        )

        let preparing = try XCTUnwrap(host.lifecycleState.value as? CodexHostStatePreparing)
        XCTAssertEqual(preparing.workspace.path, workspaceURL.path)
        let preparingCopy = CodexHostStatePreparing(workspace: preparing.workspace)
        XCTAssertEqual(preparingCopy.workspace.path, workspaceURL.path)

        platform.releasePrepare(
            failure: NSError(
                domain: "CodexAgent.D084",
                code: 84,
                userInfo: [NSLocalizedDescriptionKey: "D084 deterministic prepare failure"]
            )
        )
        do {
            try await selection.value
            XCTFail("D084 workspace selection should expose the injected prepare failure")
        } catch {
            // The structured Failed state below is the public error receipt.
        }
        await fulfillment(of: [failedObserved], timeout: 30)

        let failed = try XCTUnwrap(host.lifecycleState.value as? CodexHostStateFailed)
        XCTAssertEqual(failed.workspace?.path, workspaceURL.path)
        XCTAssertEqual(failed.failure.code, "runtime_prepare_failed")
        XCTAssertTrue(failed.failure.isRecoverable)
        let failedCopy = CodexHostStateFailed(
            workspace: failed.workspace,
            failure: failed.failure
        )
        XCTAssertEqual(failedCopy.workspace?.path, workspaceURL.path)
        XCTAssertEqual(failedCopy.failure.code, failed.failure.code)
        XCTAssertTrue(failedCopy.failure === failed.failure)
        let failedWithoutWorkspace = CodexHostStateFailed(workspace: nil, failure: failed.failure)
        XCTAssertNil(failedWithoutWorkspace.workspace)
        XCTAssertTrue(failedWithoutWorkspace.failure === failed.failure)

        let retry = Task { try await host.start() }
        await fulfillment(
            of: [secondPreparingObserved, secondPrepareEntered],
            timeout: 30
        )
        platform.releasePrepare(failure: nil)
        try await retry.value
        await fulfillment(of: [readyObserved], timeout: 120)

        let ready = try XCTUnwrap(host.lifecycleState.value as? CodexHostStateReady)
        let readyCopy = CodexHostStateReady(agent: ready.agent)
        XCTAssertTrue(readyCopy.agent === ready.agent)

        try await host.close()
        await fulfillment(of: [closedObserved], timeout: 30)
        _ = try XCTUnwrap(host.lifecycleState.value as? CodexHostStateClosed)
        await fulfillment(of: [lateStateObserved], timeout: 0.1)
        lifecycleReceipt.cancel()
        let observedLifecycle = await lifecycleReceipt.value
        XCTAssertEqual(
            observedLifecycle,
            [
                "New",
                "Restoring",
                "WorkspaceRequired",
                "Restoring",
                "Preparing",
                "Failed",
                "Preparing",
                "Ready",
                "Closed",
            ]
        )
    }

    private func assertEnumValue<E: AnyObject>(
        _ value: KotlinEnum<E>,
        stable: KotlinEnum<E>,
        name: String,
        ordinal: Int32
    ) {
        XCTAssertEqual(value.name, name)
        XCTAssertEqual(value.ordinal, ordinal)
        XCTAssertTrue(value === stable)
    }

    func testObjectiveCConsumerExposesStructuredFailure() async {
        let objectiveCConsumer = expectation(description: "Objective-C lifecycle consumer")
        CDXRunObjectiveCConsumer { failureMessage in
            XCTAssertNil(failureMessage, failureMessage ?? "Objective-C consumer failed")
            objectiveCConsumer.fulfill()
        }
        await fulfillment(of: [objectiveCConsumer], timeout: 120)
    }
}

private final class D084AuthorizationBrowser: NSObject, CodexAuthorizationBrowser {
    func open(url: CodexAuthorizationUrl) throws -> any CodexAuthorizationPresentation {
        D084AuthorizationPresentation()
    }
}

private final class D084AuthorizationPresentation: NSObject, CodexAuthorizationPresentation {
    func close() {}
}

private typealias D084ResolutionCompletion = @Sendable (
    (any CodexWorkspaceResolution)?,
    (any Error)?
) -> Void

private final class D084GatedWorkspaceStore: NSObject, CodexWorkspaceStore {
    private let backing: any CodexWorkspaceStore
    private let restoreEntered: () -> Void
    private let selectionEntered: () -> Void
    private let lock = NSLock()
    private var pendingRestore: D084ResolutionCompletion?
    private var pendingSelection: (
        selection: any CodexWorkspaceSelection,
        completion: D084ResolutionCompletion
    )?

    init(
        backing: any CodexWorkspaceStore,
        restoreEntered: @escaping () -> Void,
        selectionEntered: @escaping () -> Void
    ) {
        self.backing = backing
        self.restoreEntered = restoreEntered
        self.selectionEntered = selectionEntered
        super.init()
    }

    func restore(completionHandler: @escaping D084ResolutionCompletion) {
        lock.lock()
        precondition(pendingRestore == nil, "D084 restore is already pending")
        pendingRestore = completionHandler
        lock.unlock()
        restoreEntered()
    }

    func releaseRestore() {
        lock.lock()
        let completion = pendingRestore
        pendingRestore = nil
        lock.unlock()
        precondition(completion != nil, "D084 restore was not pending")
        backing.restore(completionHandler: completion!)
    }

    func select(
        selection: any CodexWorkspaceSelection,
        completionHandler: @escaping D084ResolutionCompletion
    ) {
        lock.lock()
        precondition(pendingSelection == nil, "D084 selection is already pending")
        pendingSelection = (selection, completionHandler)
        lock.unlock()
        selectionEntered()
    }

    func releaseSelection() {
        lock.lock()
        let pending = pendingSelection
        pendingSelection = nil
        lock.unlock()
        precondition(pending != nil, "D084 selection was not pending")
        backing.select(
            selection: pending!.selection,
            completionHandler: pending!.completion
        )
    }

    func clear(completionHandler: @escaping @Sendable ((any Error)?) -> Void) {
        backing.clear(completionHandler: completionHandler)
    }
}

private typealias D084PrepareCompletion = @Sendable (
    PreparedCodexRuntime?,
    (any Error)?
) -> Void

private final class D084GatedPlatform: NSObject, CodexPlatform {
    private let backing: IosCodexPlatform
    private let gatedWorkspaceStore: D084GatedWorkspaceStore
    private let prepareEntered: [() -> Void]
    private let lock = NSLock()
    private var prepareCallCount = 0
    private var pendingPrepares: [(
        workspace: CodexWorkspace,
        completion: D084PrepareCompletion
    )] = []

    var authorizationBrowser: any CodexAuthorizationBrowser {
        backing.authorizationBrowser
    }

    var workspaceStore: any CodexWorkspaceStore {
        gatedWorkspaceStore
    }

    init(
        backing: IosCodexPlatform,
        restoreEntered: @escaping () -> Void,
        selectionEntered: @escaping () -> Void,
        prepareEntered: [() -> Void]
    ) {
        self.backing = backing
        gatedWorkspaceStore = D084GatedWorkspaceStore(
            backing: backing.workspaceStore,
            restoreEntered: restoreEntered,
            selectionEntered: selectionEntered
        )
        self.prepareEntered = prepareEntered
        super.init()
    }

    func prepare(
        workspace: CodexWorkspace,
        completionHandler: @escaping D084PrepareCompletion
    ) {
        lock.lock()
        let callIndex = prepareCallCount
        precondition(callIndex < prepareEntered.count, "Unexpected D084 prepare call")
        prepareCallCount += 1
        pendingPrepares.append((workspace, completionHandler))
        lock.unlock()
        prepareEntered[callIndex]()
    }

    func releaseRestore() {
        gatedWorkspaceStore.releaseRestore()
    }

    func releaseSelection() {
        gatedWorkspaceStore.releaseSelection()
    }

    func releasePrepare(failure: (any Error)?) {
        lock.lock()
        let pending = pendingPrepares.isEmpty ? nil : pendingPrepares.removeFirst()
        lock.unlock()
        precondition(pending != nil, "D084 prepare was not pending")
        if let failure {
            pending!.completion(nil, failure)
        } else {
            backing.prepare(
                workspace: pending!.workspace,
                completionHandler: pending!.completion
            )
        }
    }
}

private final class TestObservationToken {
    var yield: ((Int) -> Void)?
    private let onClose: () -> Void
    private let onDeinit: () -> Void
    private var isClosed = false

    init(onClose: @escaping () -> Void, onDeinit: @escaping () -> Void) {
        self.onClose = onClose
        self.onDeinit = onDeinit
    }

    func close() {
        guard !isClosed else { return }
        isClosed = true
        yield = nil
        onClose()
    }

    deinit { onDeinit() }
}

private func compileTypedObservationSurface(
    host: CodexHost,
    agent: CodexAgent,
    conversation: CodexConversation
) {
    let _: AsyncStream<any CodexHostState> = host.lifecycleStates
    let _: AsyncStream<AgentAuthenticationState> = agent.authentication.states
    let _: AsyncStream<AgentInteractionState> = agent.interactions.states
    let _: AsyncStream<AgentIntegrationAuthorizationState> = agent.integrationAuthorization.states
    let _: AsyncStream<(any AgentIntegration)?> = agent.integrationAuthorization.activeIntegrations
    let _: AsyncStream<CodexConversation?> = agent.conversations.activeConversations
    let _: AsyncStream<AgentConversationState> = conversation.states
}

private func compileSimpleAndAdvancedOperations(
    agent: CodexAgent,
    conversation: CodexConversation
) async throws {
    try await agent.authentication.authenticate()
    try await agent.authentication.authenticate(method: CodexAuthenticationMethodChatGptDeviceCode())
    _ = try await agent.conversations.open()
    _ = try await agent.conversations.open(
        conversationId: nil,
        settings: AgentConversationSettings(
            approvalPreset: .strict,
            serviceTier: nil
        )
    )
    try await conversation.send("Hello")
    try await conversation.send(prompt: "Hello")
}

private func compileConvenienceSurface(
    agent: CodexAgent,
    conversation: CodexConversation,
    mcpServer: AgentMcpServer,
    hook: AgentHook,
    interactionState: AgentInteractionState,
    interaction: any AgentPendingInteraction
) {
    _ = agent.authentication.isAuthenticated
    _ = agent.authentication.isAuthenticating
    _ = conversation.isTurnActive
    _ = agent.integrationAuthorization.isAuthorizing
    _ = mcpServer.isAuthorized
    _ = hook.canTrust
    _ = interactionState.isResolving(interaction: interaction)
}

private func compileCapabilitiesMutationsAndElicitation(
    agent: CodexAgent,
    conversationState: AgentConversationState,
    skill: AgentSkill,
    hook: AgentHook,
    pluginReference: AgentPluginReference,
    approval: AgentPendingApproval,
    pendingElicitation: AgentPendingElicitation,
    integration: any AgentIntegration,
    elicitation: AgentElicitation
) async throws {
    _ = agent.skills.isAvailable
    _ = agent.hooks.isAvailable
    _ = agent.plugins.isAvailable
    _ = agent.connectors.isAvailable
    _ = agent.mcpServers.isAvailable
    let _: AgentConversationStatus = .closed
    _ = conversationState.canStartTurn
    _ = conversationState.canReload
    _ = conversationState.canCancelTurn

    _ = try await agent.skills.install(directory: "/tmp/skill", scope: .user)
    try await agent.skills.uninstall(skill: skill)
    let installedHook = try await agent.hooks.install(directory: "/tmp/hook", scope: .workspace)
    try await agent.hooks.trust(hook: installedHook)
    try await agent.hooks.uninstall(hook: hook)
    _ = try await agent.plugins.install(plugin: pluginReference)
    try await agent.plugins.uninstall(plugin: pluginReference)
    try await agent.interactions.resolve(approval: approval, decision: .accept)
    try await agent.interactions.resolve(
        elicitation: pendingElicitation,
        response: AgentElicitationResponse.decline()
    )
    try await agent.integrationAuthorization.authorize(target: integration)

    let initial = elicitation.initialValues()
    let validation = elicitation.validate(content: initial)
    _ = validation.isValid
    let accepted = elicitation.accept(content: initial)
    _ = elicitation.accepts(response: accepted)
    _ = AgentElicitationResponse.decline()
    _ = AgentElicitationResponse.cancel()
}
