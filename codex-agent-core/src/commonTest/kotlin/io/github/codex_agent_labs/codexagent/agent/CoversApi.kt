package io.github.codex_agent_labs.codexagent.agent

/** Declares the exact compiler-derived API members exercised by a canonical behavior test. */
@Target(AnnotationTarget.FUNCTION)
@Retention(AnnotationRetention.BINARY)
internal annotation class CoversApi(vararg val members: String)
