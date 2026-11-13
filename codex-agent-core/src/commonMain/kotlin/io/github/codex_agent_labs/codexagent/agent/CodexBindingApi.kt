package io.github.codex_agent_labs.codexagent.agent

/** Marks an owner whose public user-facing API must be projected by every applicable binding. */
@Target(AnnotationTarget.CLASS)
@Retention(AnnotationRetention.BINARY)
public annotation class CodexBindingApi

/** Excludes a member whose only extra contract is Kotlin coroutine-scope ownership. */
@Target(AnnotationTarget.CONSTRUCTOR, AnnotationTarget.FUNCTION, AnnotationTarget.PROPERTY)
@Retention(AnnotationRetention.BINARY)
public annotation class CodexBindingApiKotlinOnly
