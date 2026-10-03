using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;

const int maxRootBytes = 4096;
const int maxCompatibilityBytes = 65536;

static byte[] ReadBounded(string path, int maximum, string label)
{
    using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read,
        4096, FileOptions.SequentialScan);
    if (!stream.CanSeek)
        throw new InvalidDataException($"Expected {label} has invalid size.");
    var length = stream.Length;
    if (length is <= 0 || length > maximum)
        throw new InvalidDataException($"Expected {label} has invalid size.");
    var bytes = new byte[(int)length];
    var copied = 0;
    while (copied < bytes.Length)
    {
        var count = stream.Read(bytes.AsSpan(copied));
        if (count == 0) throw new InvalidDataException($"Expected {label} changed while reading.");
        copied += count;
    }
    if (stream.ReadByte() != -1 || stream.Length != length)
        throw new InvalidDataException($"Expected {label} changed while reading.");
    return bytes;
}

if (args.Length != 3)
{
    Console.Error.WriteLine("Usage: VerifySdkRuntimeRoot <package-dll> <expected-root-pub> <expected-compatibility-json>");
    return 2;
}

try
{
    var expectedRoot = ReadBounded(args[1], maxRootBytes, "SDK root");
    var expectedCompatibility = ReadBounded(args[2], maxCompatibilityBytes, "SDK compatibility");

    using var stream = File.OpenRead(args[0]);
    using var pe = new PEReader(stream);
    var header = pe.PEHeaders.CorHeader
        ?? throw new InvalidDataException("Package DLL has no CLR header.");
    if (!pe.HasMetadata)
        throw new InvalidDataException("Package DLL has no CLR metadata.");

    var metadata = pe.GetMetadataReader();
    var directory = header.ResourcesDirectory;
    var size = (long)directory.Size;
    if (directory.RelativeVirtualAddress == 0 || size < 4 || size > int.MaxValue)
        throw new InvalidDataException("Package DLL has invalid CLR resource directory.");
    var block = pe.GetSectionData(directory.RelativeVirtualAddress);
    if (block.Length < size)
        throw new InvalidDataException("CLR resource directory is truncated.");
    foreach (var (name, expected, maximum, label) in new[] {
        ("CodexAgent.sdk-runtime-root.pub", expectedRoot, maxRootBytes, "SDK root"),
        ("CodexAgent.sdk-compatibility.json", expectedCompatibility, maxCompatibilityBytes, "SDK compatibility"),
    })
    {
        var matches = metadata.ManifestResources
            .Where(handle => metadata.GetString(metadata.GetManifestResource(handle).Name) == name)
            .ToArray();
        if (matches.Length != 1)
            throw new InvalidDataException($"Package DLL must contain exactly one {label} resource.");
        var resource = metadata.GetManifestResource(matches[0]);
        if (!resource.Implementation.IsNil)
            throw new InvalidDataException($"{label} resource is not embedded in the package DLL.");
        var offset = (long)resource.Offset;
        if (offset > size - sizeof(int))
            throw new InvalidDataException($"{label} resource is outside the CLR resource directory.");
        var length = block.GetReader((int)offset, sizeof(int)).ReadInt32();
        if (length is <= 0 || length > maximum || offset + sizeof(int) + length > size)
            throw new InvalidDataException($"{label} resource has invalid bounds.");
        if (!block.GetContent((int)offset + sizeof(int), length).AsSpan().SequenceEqual(expected))
            throw new InvalidDataException($"Embedded {label} differs from the expected {label}.");
    }

    Console.WriteLine("Embedded SDK root and compatibility match expected bytes.");
    return 0;
}
catch (Exception error) when (error is IOException or UnauthorizedAccessException or BadImageFormatException or InvalidDataException or OverflowException or ArgumentException)
{
    Console.Error.WriteLine(error.Message);
    return 1;
}
