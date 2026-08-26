import CodexAgent
@testable import CodexAgentObservation
import CodexAgentObjectiveCConsumer
import CodexAgentSwiftSupport
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

    func testCodexOperationErrorsExposeStructuredFailure() {
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
        XCTAssertTrue(connectorIntegration.connector === connector)
        XCTAssertEqual(connectorIntegration.id, "d074-connector")
        XCTAssertEqual(connectorIntegration.displayName, "D074 Connector")

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
