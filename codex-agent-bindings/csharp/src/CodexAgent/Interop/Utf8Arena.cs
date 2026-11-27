using System.Runtime.InteropServices;

namespace CodexAgent.Interop;

internal sealed unsafe class Utf8Arena : IDisposable
{
    private readonly List<nint> allocations = [];

    internal NativeStringView View(string? value)
    {
        if (value is null) return default;
        var bytes = NativeApi.Utf8(value);
        if (bytes.Length == 0) return default;
        var pointer = Marshal.AllocHGlobal(bytes.Length);
        Marshal.Copy(bytes, 0, pointer, bytes.Length);
        allocations.Add(pointer);
        return new NativeStringView { Data = (byte*)pointer, Size = (nuint)bytes.Length };
    }

    public void Dispose()
    {
        foreach (var pointer in allocations) Marshal.FreeHGlobal(pointer);
    }
}
