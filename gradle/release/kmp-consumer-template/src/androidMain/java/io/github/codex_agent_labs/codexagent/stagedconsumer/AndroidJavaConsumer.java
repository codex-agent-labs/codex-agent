package io.github.codex_agent_labs.codexagent.stagedconsumer;

import android.content.Context;
import io.github.codex_agent_labs.codexmobile.agent.CodexClientInfo;
import io.github.codex_agent_labs.codexmobile.agent.CodexHost;
import io.github.codex_agent_labs.codexmobile.agent.CodexJava;
import io.github.codex_agent_labs.codexmobile.agent.CodexJavaObservation;
import io.github.codex_agent_labs.codexmobile.agent.runtime.AndroidCodex;
import java.util.concurrent.CompletionStage;

public final class AndroidJavaConsumer {
    private AndroidJavaConsumer() {}

    public static CompletionStage<Void> closeNewHost(Context context) {
        CodexHost host = AndroidCodex.createHost(
            context,
            new CodexClientInfo("staged_android_java", "Staged Android Java", "test")
        );
        CodexJavaObservation observation = CodexJava.observeLifecycle(
            host,
            Runnable::run,
            state -> {}
        );
        observation.close();
        return CodexJava.closeAsync(host);
    }
}
