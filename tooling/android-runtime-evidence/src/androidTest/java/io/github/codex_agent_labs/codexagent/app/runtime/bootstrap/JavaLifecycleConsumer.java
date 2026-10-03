package io.github.codex_agent_labs.codexagent.app.runtime.bootstrap;

import android.content.Context;
import io.github.codex_agent_labs.codexagent.agent.CodexClientInfo;
import io.github.codex_agent_labs.codexagent.agent.CodexHost;
import io.github.codex_agent_labs.codexagent.agent.CodexHostState;
import io.github.codex_agent_labs.codexagent.agent.CodexJava;
import io.github.codex_agent_labs.codexagent.agent.CodexJavaObservation;
import io.github.codex_agent_labs.codexagent.agent.runtime.AndroidCodex;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

public final class JavaLifecycleConsumer {
    private JavaLifecycleConsumer() {}

    public static void run(Context context) {
        try {
            CodexHost host = AndroidCodex.createHost(
                context,
                new CodexClientInfo("android_java_test", "Android Java Test", "test")
            );
            List<CodexHostState> retainedStates = new CopyOnWriteArrayList<>();
            CountDownLatch closedObserved = new CountDownLatch(1);
            CodexJavaObservation retained = CodexJava.observeLifecycle(
                host,
                Runnable::run,
                state -> {
                    retainedStates.add(state);
                    if (state instanceof CodexHostState.Closed) closedObserved.countDown();
                }
            );
            List<CodexHostState> disposedStates = new CopyOnWriteArrayList<>();
            CodexJavaObservation disposed = CodexJava.observeLifecycle(
                host,
                Runnable::run,
                disposedStates::add
            );
            disposed.close();
            disposed.close();

            CodexJava.closeAsync(host).get(5, TimeUnit.SECONDS);
            CodexJava.closeAsync(host).get(5, TimeUnit.SECONDS);
            if (!(CodexJava.currentLifecycleState(host) instanceof CodexHostState.Closed)) {
                throw new AssertionError("Android Java host did not close");
            }
            if (!closedObserved.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Android Java observation did not deliver Closed");
            }
            if (retainedStates.size() != 2) {
                throw new AssertionError("Android Java observation did not deliver New and Closed");
            }
            if (disposedStates.size() != 1 || !disposed.isClosed()) {
                throw new AssertionError("Disposed Android Java observation received another state");
            }
            try {
                CodexJava.startAsync(host).get(5, TimeUnit.SECONDS);
                throw new AssertionError("A closed Android Java host restarted");
            } catch (ExecutionException expected) {
                if (!(expected.getCause() instanceof IllegalStateException)) throw expected;
            }
            retained.close();
            retained.close();
        } catch (RuntimeException | Error error) {
            throw error;
        } catch (Exception error) {
            throw new AssertionError("Android Java lifecycle failed", error);
        }
    }
}
