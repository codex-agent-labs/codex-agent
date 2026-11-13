package io.github.codex_agent_labs.codexagent.appserver.runtime

internal fun main() {
    if (js("typeof require !== 'undefined' && require.main === module") as Boolean) {
        runNodeRuntimeEvidenceMain()
    }
}
