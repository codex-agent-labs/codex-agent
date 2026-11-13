import java.io.File
import java.io.InputStream
import java.nio.file.AtomicMoveNotSupportedException
import java.nio.file.Files
import java.nio.file.StandardCopyOption.ATOMIC_MOVE
import java.nio.file.StandardCopyOption.REPLACE_EXISTING
import java.security.MessageDigest
import javax.xml.XMLConstants
import javax.xml.parsers.DocumentBuilderFactory
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull

internal val releaseJson = Json { prettyPrint = true }

internal fun secureDocumentBuilderFactory(namespaceAware: Boolean = false) =
    DocumentBuilderFactory.newInstance().apply {
        isNamespaceAware = namespaceAware
        setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true)
        setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)
        setFeature("http://xml.org/sax/features/external-general-entities", false)
        setFeature("http://xml.org/sax/features/external-parameter-entities", false)
        setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false)
        setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "")
        setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "")
        isXIncludeAware = false
        isExpandEntityReferences = false
    }

internal fun File.readReleaseObject(): JsonObject = releaseJson.parseToJsonElement(readText()).jsonObject

internal fun File.atomicWriteJson(value: JsonElement) {
    parentFile.mkdirs()
    val temporary = Files.createTempFile(parentFile.toPath(), ".$name-", ".tmp")
    try {
        Files.writeString(temporary, releaseJson.encodeToString(JsonElement.serializer(), value) + "\n")
        try {
            Files.move(temporary, toPath(), ATOMIC_MOVE, REPLACE_EXISTING)
        } catch (_: AtomicMoveNotSupportedException) {
            Files.move(temporary, toPath(), REPLACE_EXISTING)
        }
    } finally {
        Files.deleteIfExists(temporary)
    }
}

internal fun File.releaseDigest(algorithm: String = "SHA-256"): String = inputStream().use {
    it.releaseDigest(algorithm)
}

internal fun InputStream.releaseDigest(algorithm: String = "SHA-256"): String {
    val digest = MessageDigest.getInstance(algorithm)
    val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
    while (true) {
        val count = read(buffer)
        if (count < 0) break
        digest.update(buffer, 0, count)
    }
    return digest.digest().joinToString("") { "%02x".format(it.toInt() and 0xff) }
}

internal fun File.releaseRecord(fileName: String = name): JsonObject = buildJsonObject {
    put("fileName", JsonPrimitive(fileName))
    put("bytes", JsonPrimitive(length()))
    put("sha256", JsonPrimitive(releaseDigest()))
}

internal fun JsonObject.releaseString(name: String): String = this[name]?.jsonPrimitive?.contentOrNull
    ?: error("Missing JSON string: $name")

internal fun JsonObject.releaseInt(name: String): Int = this[name]?.jsonPrimitive?.intOrNull
    ?: error("Missing JSON integer: $name")

internal fun JsonObject.releaseLong(name: String): Long = this[name]?.jsonPrimitive?.longOrNull
    ?: error("Missing JSON integer: $name")

internal fun JsonObject.releaseObject(name: String): JsonObject = this[name]?.jsonObject
    ?: error("Missing JSON object: $name")

internal fun JsonObject.releaseArray(name: String): JsonArray = this[name] as? JsonArray
    ?: error("Missing JSON array: $name")
