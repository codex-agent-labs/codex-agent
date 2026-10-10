package io.github.codex_agent_labs.codexagent.agent

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class CodexAuthorizationBrowserTest {
    @Test
    @CoversApi(
        "api-v1:CodexAuthorizationUrl#property:value#sha256:1451f4017b23fd2fa0af1c4018f9cdaefe03e16c2ba303730f2efa2de977e007",
        "api-v1:CodexAuthorizationUrl.Companion#function:chatGpt#sha256:c1caab3bfd7e37b7cbaa33deb5c4a22758a28da3e03523e5d65ca307e7744301",
    )
    fun chatGptUrlsRequireTrustedHttpsHostsAndDefaultPort() {
        assertEquals(
            "https://auth.openai.com/authorize?client=codex",
            CodexAuthorizationUrl.chatGpt("https://auth.openai.com/authorize?client=codex").value,
        )
        CodexAuthorizationUrl.chatGpt("https://chatgpt.com/")
        CodexAuthorizationUrl.chatGpt("https://login.chatgpt.com:443/")

        listOf(
            "http://auth.openai.com/",
            "https://openai.com.evil.example/",
            "https://evilopenai.com/",
            "https://user@openai.com/",
            "https://openai.com:444/",
            "https://openai.com:/",
            "https://openai.com./",
        ).forEach { assertFailsWith<IllegalArgumentException> { CodexAuthorizationUrl.chatGpt(it) } }
    }

    @Test
    @CoversApi(
        "api-v1:CodexAuthorizationUrl.Companion#function:external#sha256:99e4e53ce7cf482c82c600e64c7d6493cca8b98e9a8ff9e00471811965f68467",
    )
    fun externalUrlsAllowHttpsAndOnlyLoopbackHttp() {
        CodexAuthorizationUrl.external("https://accounts.example.com/oauth")
        CodexAuthorizationUrl.external("http://localhost:8787/callback")
        CodexAuthorizationUrl.external("http://127.0.0.1:8787/callback")
        CodexAuthorizationUrl.external("http://[::1]:8787/callback")

        listOf(
            "http://192.168.1.2/login",
            "ftp://accounts.example.com/login",
            "https://user@accounts.example.com/login",
            "https://accounts.example.com:0/login",
            "https://accounts.example.com:65536/login",
            "https://accounts.example.com:/login",
            "https://accounts.example.com\\@evil.example/login",
            "https://accounts.example.com/space here",
        ).forEach { assertFailsWith<IllegalArgumentException> { CodexAuthorizationUrl.external(it) } }
    }

    @Test
    @CoversApi(
        "api-v1:CodexAuthorizationPurpose#enum-entry:EXTERNAL#sha256:d70acda039a078e5e35cf1277dfab3508d84b8938bdb4053f7160c5ae5cd0d81",
    )
    fun authorizationUrlsDoNotLeakTheirValueFromToString() {
        val url = CodexAuthorizationUrl.external("https://accounts.example.com/oauth?secret=value")
        assertEquals("CodexAuthorizationUrl(purpose=EXTERNAL)", url.toString())
    }
}
