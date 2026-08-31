import com.vanniktech.maven.publish.JavaPlatform
import org.jetbrains.kotlin.gradle.targets.js.nodejs.NodeJsRootPlugin
import org.jetbrains.kotlin.gradle.targets.js.npm.NpmExtension
import org.jetbrains.kotlin.gradle.targets.wasm.nodejs.WasmNodeJsRootPlugin
import org.jetbrains.kotlin.gradle.targets.wasm.npm.WasmNpmExtension

plugins {
    base
    `java-platform`
    alias(libs.plugins.android.kmp.library) apply false
    alias(libs.plugins.android.library) apply false
    alias(libs.plugins.kotlin.jvm) apply false
    alias(libs.plugins.kotlin.multiplatform) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.maven.publish)
    id("codexagent.contract-product") apply false
    id("codexagent.root-release")
}

apply(plugin = "codexagent.contract-product")

dependencies {
    constraints {
        api("${project.group}:codex-agent:${project.version}")
        api("${project.group}:codex-agent-core:${project.extra["codexAgent.contractVersion"]}")
        api("${project.group}:codex-agent-runtime-desktop:${project.extra["codexAgent.runtimeVersion"]}")
        api("${project.group}:codex-agent-runtime-android:${project.version}")
        api("${project.group}:codex-agent-runtime-ios:${project.version}")
    }
}

mavenPublishing {
    configure(JavaPlatform())
    coordinates(project.group.toString(), "codex-agent-bom", project.version.toString())
    if (
        providers.gradleProperty("signingInMemoryKey").isPresent ||
        providers.gradleProperty("signing.secretKeyRingFile").isPresent
    ) {
        signAllPublications()
    }
    pom {
        name.set("Codex Agent BOM")
        description.set("Version alignment for the Codex Agent SDK, Contract, and runtimes.")
        inceptionYear.set("2026")
        url.set(project.extra["codexAgent.repositoryUrl"].toString())
        licenses {
            license {
                name.set("GNU General Public License v3.0 or later")
                url.set("https://www.gnu.org/licenses/gpl-3.0.txt")
                distribution.set("repo")
            }
        }
        developers {
            developer {
                id.set("ciurlaro")
                name.set("Cesare Iurlaro")
                url.set("https://github.com/ciurlaro")
            }
        }
        scm {
            val repositoryUrl = project.extra["codexAgent.repositoryUrl"].toString()
            url.set(repositoryUrl)
            connection.set("scm:git:$repositoryUrl.git")
            developerConnection.set("scm:git:ssh://git@github.com/${repositoryUrl.substringAfter("github.com/")}.git")
        }
    }
}

rootProject.plugins.withType<NodeJsRootPlugin> {
    rootProject.extensions.getByType(NpmExtension::class.java).lockFileDirectory.set(
        rootProject.layout.projectDirectory.dir("gradle/kotlin-js-store"),
    )
}
rootProject.plugins.withType<WasmNodeJsRootPlugin> {
    rootProject.extensions.getByType(WasmNpmExtension::class.java).lockFileDirectory.set(
        rootProject.layout.projectDirectory.dir("gradle/kotlin-js-store/wasm"),
    )
}
