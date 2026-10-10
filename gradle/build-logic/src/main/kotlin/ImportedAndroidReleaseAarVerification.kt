import java.io.File
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

internal fun verifyImportedAndroidReleaseAar(
    aar: File,
    firebaseEvidenceFile: File,
    candidateCommit: String,
    pinnedRuntimeSha256: String,
): JsonObject {
    check(candidateCommit.matches(Regex("[0-9a-f]{40}"))) { "Candidate commit must be immutable" }
    check(pinnedRuntimeSha256.matches(Regex("[0-9a-f]{64}"))) { "Pinned Android runtime SHA-256 is invalid" }
    check(aar.isFile && aar.name == FIREBASE_RELEASE_AAR) { "Exact-main Android release AAR is missing or misnamed" }
    val evidence = firebaseEvidenceFile.readReleaseObject()
    val errors = validateFirebaseAndroidEvidence(evidence, candidateCommit)
    check(errors.isEmpty()) { "Firebase Android evidence is invalid: ${errors.joinToString()}" }
    val aarSha256 = aar.releaseDigest()
    check(aarSha256 == evidence.releaseString("releaseAarSha256")) {
        "Exact-main Android release AAR is not bound to Firebase evidence"
    }
    val runtimeSha256 = aar.singleZipEntryDigest(AAR_RUNTIME_ENTRY)
    check(runtimeSha256 == pinnedRuntimeSha256 &&
        runtimeSha256 == evidence.releaseString("aarBundledRuntimeSha256")) {
        "Exact-main Android release AAR does not contain the pinned runtime"
    }
    return buildJsonObject {
        put("schemaVersion", JsonPrimitive(1))
        put("candidateCommit", JsonPrimitive(candidateCommit))
        put("firebaseEvidenceSha256", JsonPrimitive(firebaseEvidenceFile.releaseDigest()))
        put("releaseAarSha256", JsonPrimitive(aarSha256))
        put("bundledRuntimeSha256", JsonPrimitive(runtimeSha256))
        put("result", JsonPrimitive("passed"))
    }
}
