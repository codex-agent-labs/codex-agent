using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;

const string resourceName = "CodexAgent.sdk-runtime-root.pub";
const int maxRootBytes = 4096;

if (args.Length != 2)
{
    Console.Error.WriteLine("Usage: VerifySdkRuntimeRoot <package-dll> <expected-root-pub>");
    return 2;
}

try
{
    var expected = File.ReadAllBytes(args[1]);
    if (expected.Length is 0 or > maxRootBytes)
        throw new InvalidDataException("Expected SDK root has invalid size.");

    using var stream = File.OpenRead(args[0]);
    using var pe = new PEReader(stream);
    var header = pe.PEHeaders.CorHeader
        ?? throw new InvalidDataException("Package DLL has no CLR header.");
    if (!pe.HasMetadata)
        throw new InvalidDataException("Package DLL has no CLR metadata.");

    var metadata = pe.GetMetadataReader();
    var matches = metadata.ManifestResources
        .Where(handle => metadata.GetString(metadata.GetManifestResource(handle).Name) == resourceName)
        .ToArray();
    if (matches.Length != 1)
        throw new InvalidDataException("Package DLL must contain exactly one SDK root resource.");

    var resource = metadata.GetManifestResource(matches[0]);
    if (!resource.Implementation.IsNil)
        throw new InvalidDataException("SDK root resource is not embedded in the package DLL.");

    var directory = header.ResourcesDirectory;
    var offset = (long)resource.Offset;
    var size = (long)directory.Size;
    if (directory.RelativeVirtualAddress == 0 || size < 4 ||
        offset < 0 || offset > size - 4 || size > int.MaxValue)
        throw new InvalidDataException("SDK root resource is outside the CLR resource directory.");

    var block = pe.GetSectionData(directory.RelativeVirtualAddress);
    if (block.Length < size)
        throw new InvalidDataException("CLR resource directory is truncated.");
    var length = block.GetReader((int)offset, sizeof(int)).ReadInt32();
    if (length is <= 0 or > maxRootBytes || offset + sizeof(int) + length > size)
        throw new InvalidDataException("SDK root resource has invalid bounds.");

    var actual = block.GetContent((int)offset + sizeof(int), length);
    if (!actual.AsSpan().SequenceEqual(expected))
        throw new InvalidDataException("Embedded SDK root differs from the expected root.");

    Console.WriteLine("Embedded SDK root matches expected bytes.");
    return 0;
}
catch (Exception error) when (error is IOException or UnauthorizedAccessException or BadImageFormatException or InvalidDataException or OverflowException or ArgumentException)
{
    Console.Error.WriteLine(error.Message);
    return 1;
}
