package io.github.codex_agent_labs.codexmobile.agent;

import static io.github.codex_agent_labs.codexmobile.agent.CodexJava.*;
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Optional;
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
        InteractionControllerKt.isResolving(state, interaction);
    }

    @Test
    void canonicalHostAgentConversationLifecycleIsJavaFriendly() throws Exception {
        CodexHost host = JavaCodexApiFixture.selectableHost();
        List<CodexHostState> hostStates = new CopyOnWriteArrayList<>();
        CodexJavaObservation hostObservation = observeLifecycle(host, Runnable::run, hostStates::add);

        assertInstanceOf(CodexHostState.New.class, hostStates.get(0));
        startAsync(host).get(1, TimeUnit.SECONDS);
        assertInstanceOf(CodexHostState.WorkspaceRequired.class, currentLifecycleState(host));

        selectWorkspaceAsync(host, new CodexPathWorkspaceSelection("/workspace"))
            .get(1, TimeUnit.SECONDS);
        CodexAgent agent = readyAgent(currentLifecycleState(host)).orElseThrow();
        assertEquals("/workspace", agent.getWorkspace().getPath());
        assertEquals("/workspace", hostWorkspace(currentLifecycleState(host)).orElseThrow().getPath());

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
        assertEquals(AgentConversationStatus.READY, conversationStates.get(0).getStatus());
        assertTrue(conversationId(currentConversationState(conversation)).isPresent());

        AgentTurnRequest request = turnRequest("hello")
            .clientMessageId("java-message")
            .approvalPreset(AgentApprovalPreset.AUTO_REVIEW)
            .collaborationMode(AgentCollaborationMode.DEFAULT)
            .build();
        sendAsync(conversation, request).get(1, TimeUnit.SECONDS);
        assertEquals(AgentConversationStatus.RUNNING_TURN, currentConversationState(conversation).getStatus());
        cancelTurnAsync(conversation).get(1, TimeUnit.SECONDS);
        awaitStatus(conversation, AgentConversationStatus.READY);
        reloadAsync(conversation).get(1, TimeUnit.SECONDS);
        assertEquals(AgentConversationStatus.READY, currentConversationState(conversation).getStatus());

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
        assertEquals(deliveredConversationStates, conversationStates.size());
        assertEquals(deliveredHostStates, hostStates.size());
        assertThrows(ExecutionException.class, () -> sendAsync(conversation, "after close").get());
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

    private static void awaitTrue(java.util.function.BooleanSupplier condition) throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(1);
        while (!condition.getAsBoolean() && System.nanoTime() < deadline) {
            Thread.sleep(5);
        }
        assertTrue(condition.getAsBoolean());
    }
}
