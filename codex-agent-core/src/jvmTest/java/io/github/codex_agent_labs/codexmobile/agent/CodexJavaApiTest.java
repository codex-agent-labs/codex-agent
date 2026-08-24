package io.github.codex_agent_labs.codexmobile.agent;

import static io.github.codex_agent_labs.codexmobile.agent.CodexJava.*;
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

final class CodexJavaApiTest {
    @SuppressWarnings("ResultOfMethodCallIgnored")
    private static void compileConvenienceSurface(
        CodexAgent agent,
        CodexConversation conversation,
        AgentMcpServer mcpServer,
        AgentHook hook,
        AgentInteractionState state,
        AgentPendingInteraction interaction
    ) {
        agent.getAuthentication().isAuthenticated();
        agent.getAuthentication().isAuthenticating();
        conversation.isTurnActive();
        agent.getIntegrationAuthorization().isAuthorizing();
        mcpServer.isAuthorized();
        hook.getCanTrust();
        state.isResolving(interaction);
    }

    @Test
    void canonicalHostAgentConversationLifecycleIsJavaFriendly() throws Exception {
        CodexHost host = JavaCodexApiFixture.selectableHost();
        List<CodexHostState> hostStates = new CopyOnWriteArrayList<>();
        CodexJavaObservation hostObservation = observeLifecycle(host, Runnable::run, hostStates::add);

        assertInstanceOf(CodexHostState.New.class, hostStates.get(0));
        startAsync(host).get(1, TimeUnit.SECONDS);
        assertInstanceOf(CodexHostState.WorkspaceRequired.class, currentLifecycleState(host));
        awaitTrue(() -> hostStates.stream().anyMatch(CodexHostState.WorkspaceRequired.class::isInstance));

        selectWorkspaceAsync(host, new CodexPathWorkspaceSelection("/workspace"))
            .get(1, TimeUnit.SECONDS);
        CodexAgent agent = readyAgent(currentLifecycleState(host)).orElseThrow();
        assertEquals("/workspace", agent.getWorkspace().getPath());
        assertEquals("/workspace", hostWorkspace(currentLifecycleState(host)).orElseThrow().getPath());
        awaitTrue(() -> hostStates.stream().anyMatch(CodexHostState.Ready.class::isInstance));

        List<CodexJavaObservation> projectionObservations = new ArrayList<>();
        List<AgentAuthenticationState> authenticationStates = new CopyOnWriteArrayList<>();
        List<Boolean> authenticatedStates = new CopyOnWriteArrayList<>();
        List<Boolean> authenticatingStates = new CopyOnWriteArrayList<>();
        List<AgentIntegrationAuthorizationState> integrationStates = new CopyOnWriteArrayList<>();
        List<Optional<AgentIntegration>> activeIntegrations = new CopyOnWriteArrayList<>();
        List<Boolean> integrationAuthorizingStates = new CopyOnWriteArrayList<>();
        List<AgentInteractionState> interactionStates = new CopyOnWriteArrayList<>();
        List<List<AgentPendingApproval>> approvalSnapshots = new CopyOnWriteArrayList<>();
        List<List<AgentPendingElicitation>> elicitationSnapshots = new CopyOnWriteArrayList<>();
        projectionObservations.add(observeAuthenticationState(agent, Runnable::run, authenticationStates::add));
        projectionObservations.add(observeAuthenticated(agent, Runnable::run, authenticatedStates::add));
        projectionObservations.add(observeAuthenticating(agent, Runnable::run, authenticatingStates::add));
        projectionObservations.add(
            observeIntegrationAuthorizationState(agent, Runnable::run, integrationStates::add)
        );
        projectionObservations.add(
            observeActiveIntegrationAuthorization(agent, Runnable::run, activeIntegrations::add)
        );
        projectionObservations.add(
            observeIntegrationAuthorizing(agent, Runnable::run, integrationAuthorizingStates::add)
        );
        projectionObservations.add(observeInteractionState(agent, Runnable::run, interactionStates::add));
        projectionObservations.add(observeApprovals(agent, Runnable::run, approvalSnapshots::add));
        projectionObservations.add(observeElicitations(agent, Runnable::run, elicitationSnapshots::add));
        assertEquals(currentAuthenticationState(agent), last(authenticationStates));
        assertEquals(isAuthenticated(agent), last(authenticatedStates));
        assertEquals(isAuthenticating(agent), last(authenticatingStates));
        assertEquals(currentIntegrationAuthorizationState(agent), last(integrationStates));
        assertEquals(activeIntegrationAuthorization(agent), last(activeIntegrations));
        assertEquals(isIntegrationAuthorizing(agent), last(integrationAuthorizingStates));
        assertEquals(currentInteractionState(agent), last(interactionStates));
        assertEquals(currentApprovals(agent), last(approvalSnapshots));
        assertEquals(currentElicitations(agent), last(elicitationSnapshots));
        assertImmutable(currentApprovals(agent));
        assertImmutable(currentElicitations(agent));
        assertImmutable(last(approvalSnapshots));
        assertImmutable(last(elicitationSnapshots));

        List<Optional<CodexConversation>> activeConversations = new CopyOnWriteArrayList<>();
        CodexJavaObservation activeObservation =
            observeActiveConversation(agent, Runnable::run, activeConversations::add);
        assertTrue(activeConversations.get(0).isEmpty());

        AgentConversationSettings settings = conversationSettings()
            .approvalPreset(AgentApprovalPreset.AUTO_REVIEW)
            .serviceTier("fast")
            .clearServiceTier()
            .build();
        CodexConversation conversation = openConversationAsync(agent, settings)
            .get(1, TimeUnit.SECONDS);
        assertSame(conversation, activeConversation(agent).orElseThrow());
        awaitTrue(() -> activeConversations.stream().anyMatch(Optional::isPresent));
        assertSame(conversation, activeConversations.get(activeConversations.size() - 1).orElseThrow());

        List<AgentConversationState> conversationStates = new CopyOnWriteArrayList<>();
        CodexJavaObservation conversationObservation =
            observeConversation(conversation, Runnable::run, conversationStates::add);
        List<Optional<AgentTurnProgress>> turnProgressStates = new CopyOnWriteArrayList<>();
        List<Boolean> canCancelStates = new CopyOnWriteArrayList<>();
        List<Boolean> canReloadStates = new CopyOnWriteArrayList<>();
        List<Boolean> canRunShellStates = new CopyOnWriteArrayList<>();
        List<Boolean> canStartStates = new CopyOnWriteArrayList<>();
        List<List<AgentMessage>> messageSnapshots = new CopyOnWriteArrayList<>();
        List<Boolean> turnActiveStates = new CopyOnWriteArrayList<>();
        projectionObservations.add(observeTurnProgress(conversation, Runnable::run, turnProgressStates::add));
        projectionObservations.add(observeCanCancelTurn(conversation, Runnable::run, canCancelStates::add));
        projectionObservations.add(observeCanReload(conversation, Runnable::run, canReloadStates::add));
        projectionObservations.add(
            observeCanRunShellCommand(conversation, Runnable::run, canRunShellStates::add)
        );
        projectionObservations.add(observeCanStartTurn(conversation, Runnable::run, canStartStates::add));
        projectionObservations.add(observeMessages(conversation, Runnable::run, messageSnapshots::add));
        projectionObservations.add(observeTurnActive(conversation, Runnable::run, turnActiveStates::add));
        assertEquals(AgentConversationStatus.READY, conversationStates.get(0).getStatus());
        assertTrue(conversationId(currentConversationState(conversation)).isPresent());
        assertEquals(currentTurnProgress(conversation), last(turnProgressStates));
        assertEquals(canCancelTurn(conversation), last(canCancelStates));
        assertEquals(canReload(conversation), last(canReloadStates));
        assertEquals(canRunShellCommand(conversation), last(canRunShellStates));
        assertEquals(canStartTurn(conversation), last(canStartStates));
        assertEquals(currentMessages(conversation), last(messageSnapshots));
        assertEquals(isTurnActive(conversation), last(turnActiveStates));
        assertImmutable(currentMessages(conversation));
        assertImmutable(last(messageSnapshots));

        AgentTurnRequest request = turnRequest("hello")
            .clientMessageId("java-message")
            .approvalPreset(AgentApprovalPreset.AUTO_REVIEW)
            .collaborationMode(AgentCollaborationMode.DEFAULT)
            .build();
        sendAsync(conversation, request).get(1, TimeUnit.SECONDS);
        assertEquals(AgentConversationStatus.RUNNING_TURN, currentConversationState(conversation).getStatus());
        assertTrue(isTurnActive(conversation));
        assertTrue(canCancelTurn(conversation));
        assertEquals(List.of("hello"), currentMessages(conversation).stream().map(AgentMessage::getText).toList());
        awaitTrue(() -> conversationStates.stream().anyMatch(
            state -> state.getStatus() == AgentConversationStatus.RUNNING_TURN
        ));
        awaitTrue(() -> turnProgressStates.stream().anyMatch(Optional::isPresent));
        awaitTrue(() -> canCancelStates.contains(Boolean.TRUE));
        awaitTrue(() -> canReloadStates.contains(Boolean.FALSE));
        awaitTrue(() -> canRunShellStates.contains(Boolean.FALSE));
        awaitTrue(() -> canStartStates.contains(Boolean.FALSE));
        awaitTrue(() -> turnActiveStates.contains(Boolean.TRUE));
        awaitTrue(() -> last(messageSnapshots).stream().map(AgentMessage::getText).toList().equals(List.of("hello")));
        cancelTurnAsync(conversation).get(1, TimeUnit.SECONDS);
        awaitStatus(conversation, AgentConversationStatus.READY);
        awaitTrue(() -> last(conversationStates).getStatus() == AgentConversationStatus.READY);
        awaitTrue(() -> last(turnProgressStates).isEmpty());
        awaitTrue(() -> last(canCancelStates).equals(Boolean.FALSE));
        awaitTrue(() -> last(canReloadStates).equals(Boolean.TRUE));
        awaitTrue(() -> last(canRunShellStates).equals(Boolean.TRUE));
        awaitTrue(() -> last(canStartStates).equals(Boolean.TRUE));
        awaitTrue(() -> last(turnActiveStates).equals(Boolean.FALSE));
        reloadAsync(conversation).get(1, TimeUnit.SECONDS);
        assertEquals(AgentConversationStatus.READY, currentConversationState(conversation).getStatus());
        awaitTrue(() -> currentMessages(conversation).size() == 2);
        assertEquals(
            List.of("First message", "Second message"),
            currentMessages(conversation).stream().map(AgentMessage::getText).toList()
        );
        assertEquals(currentMessages(conversation), last(messageSnapshots));
        assertImmutable(currentMessages(conversation));
        assertImmutable(last(messageSnapshots));
        assertImmutable(last(messageSnapshots).get(0).getCapabilities());
        assertImmutable(last(messageSnapshots).get(0).getInvocations());
        AgentConversation observedConversation = last(conversationStates).getConversation();
        assertNotNull(observedConversation);
        assertImmutable(observedConversation.getMessages());
        assertImmutable(observedConversation.getMessages().get(0).getCapabilities());
        assertImmutable(observedConversation.getMessages().get(0).getInvocations());

        conversationObservation.close();
        conversationObservation.close();
        int deliveredConversationStates = conversationStates.size();
        hostObservation.close();
        hostObservation.close();
        int deliveredHostStates = hostStates.size();

        CompletableFuture<Void> firstClose = closeAsync(host);
        CompletableFuture<Void> repeatedClose = closeAsync(host);
        CompletableFuture.allOf(firstClose, repeatedClose).get(1, TimeUnit.SECONDS);
        assertEquals(AgentConversationStatus.CLOSED, currentConversationState(conversation).getStatus());
        assertInstanceOf(CodexHostState.Closed.class, currentLifecycleState(host));
        awaitTrue(() -> activeConversations.get(activeConversations.size() - 1).isEmpty());
        activeObservation.close();
        projectionObservations.forEach(CodexJavaObservation::close);
        assertTrue(projectionObservations.stream().allMatch(CodexJavaObservation::isClosed));
        assertEquals(deliveredConversationStates, conversationStates.size());
        assertEquals(deliveredHostStates, hostStates.size());
        assertThrows(ExecutionException.class, () -> sendAsync(conversation, "after close").get());
    }

    @Test
    void controllerFuturesProjectAuthenticationInteractionsAndCancellation() throws Exception {
        assertCanonicalSingletonSurface();
        assertEquals(AgentElicitationAction.DECLINE, AgentElicitationResponse.decline().getAction());
        assertEquals(AgentElicitationAction.CANCEL, AgentElicitationResponse.cancel().getAction());
        CodexAuthorizationUrl chatGptUrl = CodexAuthorizationUrl.chatGpt("https://chatgpt.com/auth");
        CodexAuthorizationUrl externalUrl = CodexAuthorizationUrl.external("https://example.com/auth");
        assertEquals(CodexAuthorizationPurpose.CHAT_GPT, chatGptUrl.getPurpose());
        assertEquals("https://chatgpt.com/auth", chatGptUrl.getValue());
        assertEquals(CodexAuthorizationPurpose.EXTERNAL, externalUrl.getPurpose());
        assertEquals("https://example.com/auth", externalUrl.getValue());

        try (JavaFacadeFixture fixture = JavaCodexApiFixture.facadeFixture()) {
            fixture.start();
            CodexAgent agent = fixture.getAgent();
            List<AgentAuthenticationState> authenticationStates = new CopyOnWriteArrayList<>();
            List<Boolean> authenticatedStates = new CopyOnWriteArrayList<>();
            List<Boolean> authenticatingStates = new CopyOnWriteArrayList<>();
            List<AgentIntegrationAuthorizationState> integrationStates = new CopyOnWriteArrayList<>();
            List<Optional<AgentIntegration>> activeIntegrations = new CopyOnWriteArrayList<>();
            List<Boolean> integrationAuthorizingStates = new CopyOnWriteArrayList<>();
            List<AgentInteractionState> interactionStates = new CopyOnWriteArrayList<>();
            List<List<AgentPendingApproval>> approvalSnapshots = new CopyOnWriteArrayList<>();
            List<List<AgentPendingElicitation>> elicitationSnapshots = new CopyOnWriteArrayList<>();
            List<CodexJavaObservation> observations = List.of(
                observeAuthenticationState(agent, Runnable::run, authenticationStates::add),
                observeAuthenticated(agent, Runnable::run, authenticatedStates::add),
                observeAuthenticating(agent, Runnable::run, authenticatingStates::add),
                observeIntegrationAuthorizationState(agent, Runnable::run, integrationStates::add),
                observeActiveIntegrationAuthorization(agent, Runnable::run, activeIntegrations::add),
                observeIntegrationAuthorizing(agent, Runnable::run, integrationAuthorizingStates::add),
                observeInteractionState(agent, Runnable::run, interactionStates::add),
                observeApprovals(agent, Runnable::run, approvalSnapshots::add),
                observeElicitations(agent, Runnable::run, elicitationSnapshots::add)
            );
            try {
                authenticateAsync(agent, new CodexAuthenticationMethod.ApiKey("sk-java-test"))
                    .get(1, TimeUnit.SECONDS);
                awaitTrue(() -> isAuthenticated(agent) && authenticatedStates.contains(Boolean.TRUE));
                awaitTrue(() -> authenticationStates.stream().anyMatch(
                    state -> state.getStatus() == AgentAuthenticationStatus.AUTHENTICATED
                ));
                signOutAsync(agent).get(1, TimeUnit.SECONDS);
                awaitTrue(() -> !isAuthenticated(agent) && !last(authenticatedStates));

                authenticateAsync(agent).get(1, TimeUnit.SECONDS);
                awaitTrue(() -> isAuthenticating(agent) && authenticatingStates.contains(Boolean.TRUE));
                cancelAuthenticationAsync(agent).get(1, TimeUnit.SECONDS);
                awaitTrue(() -> !isAuthenticating(agent) && !last(authenticatingStates));

                fixture.publishInteractions();
                awaitTrue(() -> currentApprovals(agent).size() == 2 && last(approvalSnapshots).size() == 2);
                awaitTrue(() -> currentElicitations(agent).size() == 2 && last(elicitationSnapshots).size() == 2);
                awaitTrue(() -> last(interactionStates).getPending().size() == 4);
                List<AgentPendingApproval> approvals = currentApprovals(agent);
                List<AgentPendingElicitation> elicitations = currentElicitations(agent);
                assertEquals(
                    List.of("201", "202"),
                    approvals.stream().map(AgentPendingApproval::getRequestId).toList()
                );
                assertEquals(
                    List.of("203", "204"),
                    elicitations.stream().map(AgentPendingElicitation::getRequestId).toList()
                );
                assertSame(approvals.get(0), last(approvalSnapshots).get(0));
                assertSame(elicitations.get(0), last(elicitationSnapshots).get(0));
                assertImmutable(approvals);
                assertImmutable(elicitations);
                assertImmutable(last(approvalSnapshots));
                assertImmutable(last(elicitationSnapshots));
                AgentInteractionState interactionSnapshot = last(interactionStates);
                assertImmutable(interactionSnapshot.getPending());
                assertThrows(
                    UnsupportedOperationException.class,
                    () -> interactionSnapshot.getResolvingRequestIds().add("java-mutation")
                );
                assertEquals(4, currentInteractionState(agent).getPending().size());

                resolveApprovalAsync(agent, approvals.get(0), AgentApprovalDecision.ACCEPT)
                    .get(1, TimeUnit.SECONDS);
                openElicitationUrlAsync(agent, elicitations.get(0)).get(1, TimeUnit.SECONDS);
                resolveElicitationAsync(agent, elicitations.get(0), AgentElicitationResponse.decline())
                    .get(1, TimeUnit.SECONDS);
                awaitTrue(() -> currentApprovals(agent).size() == 1 && last(approvalSnapshots).size() == 1);
                awaitTrue(() -> currentElicitations(agent).size() == 1 && last(elicitationSnapshots).size() == 1);
                awaitTrue(() -> last(interactionStates).getPending().size() == 2);
                assertEquals(4, interactionSnapshot.getPending().size());
                assertEquals(List.of("201", "202"), approvals.stream().map(AgentPendingApproval::getRequestId).toList());
                assertEquals(
                    List.of("203", "204"),
                    elicitations.stream().map(AgentPendingElicitation::getRequestId).toList()
                );
                assertFutureFailure(resolveApprovalAsync(agent, approvals.get(0), AgentApprovalDecision.ACCEPT));

                AgentConnector connector = listConnectorsAsync(agent).get(1, TimeUnit.SECONDS).get(0);
                CompletableFuture<Void> authorization = authorizeIntegrationAsync(
                    agent,
                    new AgentIntegration.Connector(connector)
                );
                awaitTrue(() -> activeIntegrationAuthorization(agent).isPresent());
                awaitTrue(() -> last(activeIntegrations).isPresent());
                awaitTrue(() -> isIntegrationAuthorizing(agent) && integrationAuthorizingStates.contains(Boolean.TRUE));
                assertEquals(connector.getId(), last(activeIntegrations).orElseThrow().getId());
                assertTrue(integrationStates.stream().anyMatch(
                    state -> state.getStatus() != AgentIntegrationAuthorizationStatus.IDLE
                ));
                cancelIntegrationAuthorizationAsync(agent).get(1, TimeUnit.SECONDS);
                awaitTrue(authorization::isCancelled);
                awaitTrue(() -> activeIntegrationAuthorization(agent).isEmpty() && last(activeIntegrations).isEmpty());
                awaitTrue(() -> !isIntegrationAuthorizing(agent) && !last(integrationAuthorizingStates));
            } finally {
                observations.forEach(CodexJavaObservation::close);
                assertTrue(observations.stream().allMatch(CodexJavaObservation::isClosed));
            }
        }
    }

    private static void assertCanonicalSingletonSurface() {
        assertEquals(
            7,
            Set.of(
                CodexAuthenticationMethod.ChatGptBrowser.INSTANCE,
                CodexAuthenticationMethod.ChatGptDeviceCode.INSTANCE,
                CodexHostState.New.INSTANCE,
                CodexHostState.Restoring.INSTANCE,
                CodexHostState.Closed.INSTANCE,
                AgentHookHandler.Prompt.INSTANCE,
                AgentHookHandler.Agent.INSTANCE
            ).size()
        );
    }

    @Test
    void catalogAndResourceFuturesProjectValuesOptionalsAndOwnership() throws Exception {
        try (JavaFacadeFixture fixture = JavaCodexApiFixture.facadeFixture()) {
            fixture.start();
            CodexAgent agent = fixture.getAgent();

            List<AgentConversationSummary> conversations = listConversationsAsync(agent)
                .get(1, TimeUnit.SECONDS);
            assertEquals(List.of("First", "Second"), conversations.stream().map(AgentConversationSummary::getTitle).toList());
            assertImmutable(conversations);
            ConversationId conversationId = conversations.get(0).getConversationId();
            AgentConversation read = readConversationAsync(agent, conversationId).get(1, TimeUnit.SECONDS);
            assertEquals(conversationId, read.getSummary().getConversationId());
            assertImmutable(read.getMessages());
            renameConversationAsync(agent, conversationId, "Renamed").get(1, TimeUnit.SECONDS);
            deleteConversationAsync(agent, conversationId).get(1, TimeUnit.SECONDS);

            List<AgentModel> models = listModelsAsync(agent).get(1, TimeUnit.SECONDS);
            assertEquals(List.of("preferred", "other"), models.stream().map(AgentModel::getId).toList());
            assertImmutable(models);
            assertEquals(List.of("low", "medium"), models.get(0).getSupportedEfforts());
            assertEquals(
                List.of("free", "fast"),
                models.get(0).getServiceTiers().stream().map(AgentServiceTier::getId).toList()
            );
            assertImmutable(models.get(0).getSupportedEfforts());
            assertImmutable(models.get(0).getServiceTiers());
            AgentModel preferred = resolveModelAsync(agent).get(1, TimeUnit.SECONDS);
            assertEquals("preferred", preferred.getId());
            assertImmutable(preferred.getSupportedEfforts());
            assertImmutable(preferred.getServiceTiers());
            assertEquals("low", resolveEffortAsync(agent, preferred).get(1, TimeUnit.SECONDS));
            assertEquals(
                "fast",
                resolveServiceTierAsync(agent, preferred)
                    .get(1, TimeUnit.SECONDS)
                    .orElseThrow()
                    .getId()
            );
            assertTrue(
                resolveServiceTierAsync(agent, fixture.getNoTierModel(), AgentResolution.First)
                    .get(1, TimeUnit.SECONDS)
                    .isEmpty()
            );

            AgentSkillCatalog skills = listSkillsAsync(agent).get(1, TimeUnit.SECONDS);
            AgentSkill skill = skills.getSkills().get(0);
            assertEquals("review", skill.getName());
            assertEquals(List.of("git", "rg"), skill.getDependencies());
            assertImmutable(skills.getSkills());
            assertImmutable(skills.getErrors());
            assertImmutable(skill.getDependencies());
            assertTrue(readSkillAsync(agent, skill.getPath()).get(1, TimeUnit.SECONDS).getContent().contains("Review code"));
            assertFutureFailure(
                installSkillAsync(agent, fixture.getMissingDirectory(), AgentInstallationScope.Workspace)
            );
            assertFutureFailure(uninstallSkillAsync(agent, skill));

            AgentHookCatalog hooks = listHooksAsync(agent).get(1, TimeUnit.SECONDS);
            AgentHook hook = hooks.getHooks().get(0);
            assertEquals("java-hook", hook.getKey());
            assertImmutable(hooks.getHooks());
            assertImmutable(hooks.getWarnings());
            assertImmutable(hooks.getErrors());
            trustHookAsync(agent, hook).get(1, TimeUnit.SECONDS);
            assertFutureFailure(
                installHookAsync(agent, fixture.getMissingDirectory(), AgentInstallationScope.Workspace)
            );
            assertFutureFailure(uninstallHookAsync(agent, hook));

            AgentPluginCatalog plugins = listPluginsAsync(agent).get(1, TimeUnit.SECONDS);
            AgentPluginReference plugin = plugins.getPlugins().get(0).getReference();
            assertEquals(List.of("Search files", "Read files"), plugins.getPlugins().get(0).getCapabilities());
            assertImmutable(plugins.getPlugins());
            assertImmutable(plugins.getErrors());
            assertImmutable(plugins.getPlugins().get(0).getCapabilities());
            AgentPluginDetail pluginDetail = readPluginAsync(agent, plugin).get(1, TimeUnit.SECONDS);
            assertEquals("drive", pluginDetail.getSummary().getReference().getName());
            assertEquals(List.of("drive"), pluginDetail.getMcpServers());
            assertImmutable(pluginDetail.getSummary().getCapabilities());
            assertImmutable(pluginDetail.getSkills());
            assertImmutable(pluginDetail.getConnectors());
            assertImmutable(pluginDetail.getMcpServers());
            assertImmutable(pluginDetail.getConnectors().get(0).getPluginNames());
            AgentPluginInstallResult installResult = installPluginAsync(agent, plugin).get(1, TimeUnit.SECONDS);
            assertEquals(AgentPluginAuthPolicy.ON_INSTALL, installResult.getAuthPolicy());
            assertImmutable(installResult.getConnectorsNeedingAuthentication());
            assertImmutable(installResult.getConnectorsNeedingAuthentication().get(0).getPluginNames());
            uninstallPluginAsync(agent, plugin).get(1, TimeUnit.SECONDS);

            List<AgentConnector> connectors = listConnectorsAsync(agent, false).get(1, TimeUnit.SECONDS);
            assertEquals(List.of("drive"), connectors.stream().map(AgentConnector::getId).toList());
            assertImmutable(connectors);
            assertEquals(List.of("Drive", "OpenAI curated"), connectors.get(0).getPluginNames());
            assertImmutable(connectors.get(0).getPluginNames());

            List<AgentMcpServer> servers = listMcpServersAsync(agent).get(1, TimeUnit.SECONDS);
            assertEquals(List.of("drive"), servers.stream().map(AgentMcpServer::getName).toList());
            assertImmutable(servers);
            AgentMcpServerConfiguration listedConfiguration = servers.get(0).getConfiguration();
            assertNotNull(listedConfiguration);
            assertEquals(List.of("search", "read"), listedConfiguration.getEnabledTools());
            assertImmutable(listedConfiguration.getEnabledTools());
            assertImmutable(listedConfiguration.getTools());
            AgentMcpTransport.Http listedHttp = assertInstanceOf(
                AgentMcpTransport.Http.class,
                listedConfiguration.getTransport()
            );
            assertEquals(List.of("X-First", "X-Second"), new ArrayList<>(listedHttp.getHeaders().keySet()));
            assertImmutable(listedHttp.getHeaders());
            AgentMcpTransport.Stdio stdio = new AgentMcpTransport.Stdio("drive-mcp");
            assertEquals(List.of(), stdio.getArguments());
            AgentMcpServerConfiguration configuration = new AgentMcpServerConfiguration("drive", stdio);
            assertEquals("local", configuration.getEnvironmentId());
            assertTrue(configuration.isEnabled());
            AgentMcpTransport.Http http = new AgentMcpTransport.Http("https://mcp.example.com");
            assertNull(http.getBearerTokenEnvironmentVariable());
            assertNull(new AgentMcpEnvironmentVariable("TOKEN").getSource());
            assertNull(new AgentMcpOauthConfiguration().getClientId());
            assertNull(new AgentMcpToolConfiguration().getApproval());
            assertFutureFailure(addMcpServerAsync(agent, configuration));
            assertFutureFailure(removeMcpServerAsync(agent, servers.get(0)));
        }
    }

    @Test
    void structuredFailuresAndFutureCancellationPreserveCanonicalSemantics() throws Exception {
        CodexHost unsupportedHost = JavaCodexApiFixture.hostWithoutRuntimeFeatures();
        startAsync(unsupportedHost).get(1, TimeUnit.SECONDS);
        selectWorkspaceAsync(unsupportedHost, new CodexPathWorkspaceSelection("/workspace"))
            .get(1, TimeUnit.SECONDS);
        CodexConversation unsupportedConversation = openConversationAsync(
            readyAgent(currentLifecycleState(unsupportedHost)).orElseThrow()
        ).get(1, TimeUnit.SECONDS);

        ExecutionException unsupported = assertThrows(
            ExecutionException.class,
            () -> runShellCommandAsync(unsupportedConversation, "pwd").get()
        );
        CodexFailure failure = failure(unsupported).orElseThrow();
        assertEquals("unsupported_feature", failure.getCode());
        assertFalse(failure.isRecoverable());
        assertInstanceOf(CodexOperationException.class, unsupported.getCause());
        closeAsync(unsupportedConversation).get(1, TimeUnit.SECONDS);
        assertEquals(AgentConversationStatus.CLOSED, currentConversationState(unsupportedConversation).getStatus());
        closeAsync(unsupportedHost).get(1, TimeUnit.SECONDS);

        JavaCancellationFixture fixture = JavaCodexApiFixture.cancellableHost();
        CompletableFuture<Void> starting = startAsync(fixture.getHost());
        assertTrue(fixture.getEntered().await(1, TimeUnit.SECONDS));
        assertTrue(starting.cancel(true));
        awaitTrue(fixture.getCancelled()::get);
        assertTrue(starting.isCancelled());
        assertTrue(failure(new java.util.concurrent.CancellationException()).isEmpty());
        closeAsync(fixture.getHost()).get(1, TimeUnit.SECONDS);
    }

    @Test
    void cancellingCloseFutureDoesNotCancelCanonicalCleanup() throws Exception {
        JavaCloseCancellationFixture fixture = JavaCodexApiFixture.closeCancellationHost();
        CodexHost host = fixture.getHost();
        CompletableFuture<Void> starting = startAsync(host);
        try {
            assertTrue(fixture.getPrepareEntered().await(1, TimeUnit.SECONDS));
            CompletableFuture<Void> closing = closeAsync(host);
            awaitTrue(() -> currentLifecycleState(host) instanceof CodexHostState.Closed);
            assertFalse(closing.isDone());

            assertTrue(closing.cancel(true));
            fixture.getReleasePrepare().countDown();

            closeAsync(host).get(1, TimeUnit.SECONDS);
            awaitTrue(starting::isCancelled);
            assertTrue(closing.isCancelled());
            assertInstanceOf(CodexHostState.Closed.class, currentLifecycleState(host));
        } finally {
            fixture.getReleasePrepare().countDown();
            closeAsync(host).get(1, TimeUnit.SECONDS);
        }
    }

    @Test
    void observationCloseWaitsForAnInFlightCallbackAndFailureClosesTheToken() throws Exception {
        CodexHost host = JavaCodexApiFixture.selectableHost();
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch callbackEntered = new CountDownLatch(1);
        CountDownLatch releaseCallback = new CountDownLatch(1);
        AtomicInteger callbacks = new AtomicInteger();
        try {
            CodexJavaObservation observation = observeLifecycle(host, executor, state -> {
                callbacks.incrementAndGet();
                callbackEntered.countDown();
                try {
                    releaseCallback.await();
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                    throw new AssertionError(error);
                }
            });
            assertTrue(callbackEntered.await(1, TimeUnit.SECONDS));

            Thread closing = new Thread(observation::close, "java-observation-close");
            closing.start();
            awaitTrue(() -> closing.getState() == Thread.State.BLOCKED);
            releaseCallback.countDown();
            closing.join(TimeUnit.SECONDS.toMillis(1));
            assertFalse(closing.isAlive());
            assertTrue(observation.isClosed());

            closeAsync(host).get(1, TimeUnit.SECONDS);
            assertEquals(1, callbacks.get());

            CodexJavaObservation failed = observeLifecycle(host, Runnable::run, state -> {
                throw new IllegalStateException("observer failed");
            });
            assertTrue(failed.isClosed());
        } finally {
            releaseCallback.countDown();
            executor.shutdownNow();
            assertTrue(executor.awaitTermination(1, TimeUnit.SECONDS));
            closeAsync(host).get(1, TimeUnit.SECONDS);
        }
    }

    private static void awaitStatus(CodexConversation conversation, AgentConversationStatus expected)
        throws InterruptedException {
        awaitTrue(() -> currentConversationState(conversation).getStatus() == expected);
    }

    private static <T> T last(List<T> values) {
        return values.get(values.size() - 1);
    }

    private static void assertImmutable(List<?> values) {
        assertThrows(UnsupportedOperationException.class, () -> values.add(null));
    }

    private static void assertImmutable(Set<?> values) {
        assertThrows(UnsupportedOperationException.class, () -> values.add(null));
    }

    private static void assertImmutable(Map<?, ?> values) {
        assertThrows(UnsupportedOperationException.class, () -> values.put(null, null));
    }

    private static ExecutionException assertFutureFailure(CompletableFuture<?> future) {
        return assertThrows(ExecutionException.class, () -> future.get(1, TimeUnit.SECONDS));
    }

    private static void awaitTrue(java.util.function.BooleanSupplier condition) throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(1);
        while (!condition.getAsBoolean() && System.nanoTime() < deadline) {
            Thread.sleep(5);
        }
        assertTrue(condition.getAsBoolean());
    }
}
