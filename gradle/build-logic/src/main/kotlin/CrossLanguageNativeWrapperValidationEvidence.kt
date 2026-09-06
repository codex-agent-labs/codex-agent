import java.io.File
import kotlinx.serialization.json.jsonObject

/** Joins exact installed-package identity to full capability proof; no phase/host trust is minted. */
internal fun verifyCrossLanguageNativeWrapperValidationEvidence(
    language: CrossLanguageBinding, classifier: String, capabilityInputs: File,
    installedEvidence: File, capabilityEvidence: File, claims: File,
): CrossLanguageNativeWrapperCapabilityEvidence {
    val host = requireExactNativeWrapperInstalledConsumerEvidence(installedEvidence, language.id, classifier)
    val receipt = capabilityInputs.resolve("receipts/sdk-package.json").readReleaseObject()
    check(receipt.releaseString("product") == "sdk" && receipt.releaseString("component") == language.id &&
        receipt.releaseString("phase") == "package" && receipt.releaseString("target") == "desktop") {
        "Installed capability input receipt is not the original language package"
    }
    val packagePath = "outputs/${language.id}/" + host[1].removePrefix("${language.id}-package/")
    val packages = receipt.releaseArray("outputs").map { it.jsonObject }
        .filter { it.releaseString("relativePath") == packagePath }
    check(packages.size == 1 && packages.single().releaseString("kind") == "package" &&
        packages.single().releaseString("sha256") == "sha256:${host[2]}") {
        "Installed host proof differs from the authenticated SDK package artifact"
    }
    val library = crossLanguageCAbiTargetSpecs.values.singleOrNull { it.classifier == "c-abi-$classifier" }
        ?.libraryPath ?: error("Unsupported native capability target: $classifier")
    val native = verifiedRegularFiles(capabilityInputs.resolve("sdks/$classifier"))[library]
        ?: error("Authenticated native capability library is missing")
    check(native.releaseDigest() == host[3]) {
        "Installed host proof differs from the authenticated target library"
    }
    check(verifiedRegularFiles(capabilityEvidence).isNotEmpty()) { "Capability evidence is empty" }
    return verifyCrossLanguageNativeWrapperCapabilityEvidence(
        language, capabilityInputs.resolve("contract/canonical-api.json"),
        capabilityInputs.resolve("contract/canonical-coverage.json"),
        capabilityInputs.resolve("bootstrap/bootstrap-evidence.json"), claims,
        capabilityEvidence.resolve("compiler-evidence.tsv"), capabilityEvidence.resolve("test-program"),
        capabilityEvidence.resolve("executed-tests.tsv"),
    )
}
