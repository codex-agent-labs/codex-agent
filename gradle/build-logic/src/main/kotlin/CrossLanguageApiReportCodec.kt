import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.File

private const val CROSS_LANGUAGE_REPORT_BINARY_VERSION = 1

internal fun File.writeCrossLanguageApiReport(report: CrossLanguageApiReport) {
    parentFile.mkdirs()
    outputStream().buffered().use { stream ->
        DataOutputStream(stream).use { output ->
            output.writeInt(CROSS_LANGUAGE_REPORT_BINARY_VERSION)
            output.writeUTF(report.libraryUniqueName)
            output.writeInt(report.signatureVersion)
            output.writeUTF(report.markerAnnotation)
            output.writeStrings(report.boundaryTypes)
            output.writeBoolean(report.memberExclusionAnnotation != null)
            report.memberExclusionAnnotation?.let(output::writeUTF)
            output.writeStrings(report.excludedReachableTypes)
            output.writeStrings(report.excludedMemberKeys)
            output.writeBoolean(report.dataClassMetadataAvailable)
            output.writeStrings(report.dataClassNames)
            output.writeInt(report.owners.size)
            report.owners.forEach { owner ->
                output.writeUTF(owner.name)
                output.writeStrings(owner.memberKeys)
            }
        }
    }
}

internal fun File.readCrossLanguageApiReport(): CrossLanguageApiReport =
    inputStream().buffered().use { stream ->
        DataInputStream(stream).use { input ->
            check(input.readInt() == CROSS_LANGUAGE_REPORT_BINARY_VERSION) {
                "Unsupported cross-language compiler report version"
            }
            val report = CrossLanguageApiReport(
                libraryUniqueName = input.readUTF(),
                signatureVersion = input.readInt(),
                markerAnnotation = input.readUTF(),
                boundaryTypes = input.readStrings(),
                memberExclusionAnnotation = if (input.readBoolean()) input.readUTF() else null,
                excludedReachableTypes = input.readStrings(),
                excludedMemberKeys = input.readStrings(),
                dataClassMetadataAvailable = input.readBoolean(),
                dataClassNames = input.readStrings(),
                owners = List(input.readInt().also { check(it >= 0) }) {
                    CrossLanguageApiOwner(input.readUTF(), input.readStrings())
                },
            )
            check(input.read() == -1) { "Cross-language compiler report has trailing bytes" }
            report
        }
    }

internal fun File.writeCrossLanguageStrings(values: Collection<String>) {
    parentFile.mkdirs()
    outputStream().buffered().use { stream ->
        DataOutputStream(stream).use { it.writeStrings(values.sorted()) }
    }
}

internal fun File.readCrossLanguageStrings(): Set<String> =
    inputStream().buffered().use { stream -> DataInputStream(stream).use { it.readStrings().toSet() } }

private fun DataOutputStream.writeStrings(values: Collection<String>) {
    writeInt(values.size)
    values.forEach(::writeUTF)
}

private fun DataInputStream.readStrings(): List<String> =
    List(readInt().also { check(it >= 0) }) { readUTF() }
