package io.github.codex_agent_labs.codexagent.stagedconsumer;

import io.github.codex_agent_labs.codexmobile.agent.CodexClientInfo;
import io.github.codex_agent_labs.codexmobile.agent.CodexHost;
import io.github.codex_agent_labs.codexmobile.agent.CodexHostState;
import io.github.codex_agent_labs.codexmobile.agent.CodexJava;
import io.github.codex_agent_labs.codexmobile.agent.CodexJavaObservation;
import io.github.codex_agent_labs.codexmobile.agent.runtime.DesktopCodex;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.TimeUnit;

public final class DesktopJavaConsumer {
    private DesktopJavaConsumer() {}

    public static void main(String[] args) throws Exception {
        Path directory = Path.of(".").toAbsolutePath().normalize();
        CodexHost host = DesktopCodex.createHost(
            directory,
            directory,
            new CodexClientInfo("staged_desktop_java", "Staged Desktop Java", "test")
        );
        List<CodexHostState> states = new CopyOnWriteArrayList<>();
        CountDownLatch closedObserved = new CountDownLatch(1);
        CodexJavaObservation observation = CodexJava.observeLifecycle(host, Runnable::run, state -> {
            states.add(state);
            if (state instanceof CodexHostState.Closed) closedObserved.countDown();
        });
        if (!(CodexJava.currentLifecycleState(host) instanceof CodexHostState.New)) {
            throw new AssertionError("A new Java host did not start in New");
        }
        CodexJava.closeAsync(host).get(5, TimeUnit.SECONDS);
        CodexJava.closeAsync(host).get(5, TimeUnit.SECONDS);
        if (!(CodexJava.currentLifecycleState(host) instanceof CodexHostState.Closed)) {
            throw new AssertionError("The Java host did not close");
        }
        if (!closedObserved.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Java state observation did not deliver Closed");
        }
        if (states.size() < 2) throw new AssertionError("Java state observation did not deliver lifecycle changes");
        observation.close();
        observation.close();
    }
}
