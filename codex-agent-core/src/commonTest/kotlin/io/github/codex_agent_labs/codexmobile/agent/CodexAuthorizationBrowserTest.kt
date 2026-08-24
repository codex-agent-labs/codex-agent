package io.github.codex_agent_labs.codexmobile.agent

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class CodexAuthorizationBrowserTest {
    @Test
    @CoversApi(
        "api-v1:CodexAuthorizationUrl#property:value#sha256:baccc0a42dbeef1b9a06cbcefae83cf5147fe726a0763358d4a93753c5456176",
        "api-v1:CodexAuthorizationUrl.Companion#function:chatGpt#sha256:b9a2ed2e00deca1c26990e59f433f2a3fbb6f31dbd6cdfc2c0ac488fe1a1e939",
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
        "api-v1:CodexAuthorizationUrl.Companion#function:external#sha256:1df63c749bdeb117c03d6e790978c1cb3207ed50e82ed968cc745f1328f5d6d1",
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
        "api-v1:CodexAuthorizationPurpose#enum-entry:EXTERNAL#sha256:492cd9f0170382074654bb2399c71ab72be8a01ec8806dc20aa717b69b42506a",
    )
    fun authorizationUrlsDoNotLeakTheirValueFromToString() {
        val url = CodexAuthorizationUrl.external("https://accounts.example.com/oauth?secret=value")
        assertEquals("CodexAuthorizationUrl(purpose=EXTERNAL)", url.toString())
    }
}
