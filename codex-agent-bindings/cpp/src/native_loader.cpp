#include <codex_agent/native_dispatch.hpp>

#include <algorithm>
#include <array>
#include <atomic>
#include <charconv>
#include <cstdint>
#include <fstream>
#include <map>
#include <mutex>
#include <set>
#include <stdexcept>
#include <string>
#include <system_error>
#include <variant>
#include <vector>

#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#else
#include <dlfcn.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace codex_agent::detail {
namespace {

#ifdef CODEX_AGENT_NATIVE_LOADER_TEST_HOOK
using LoaderTestHook = void (*)(const std::filesystem::path&);
std::atomic<LoaderTestHook> loader_test_hook{};
#endif

struct Json {
    using Object = std::map<std::string, Json>;
    using Array = std::vector<Json>;
    std::variant<std::nullptr_t, bool, std::int64_t, std::string, Object, Array> value;
};

class JsonParser final {
public:
    explicit JsonParser(std::string text) : text_(std::move(text)) {}

    Json parse() {
        auto result = value();
        if (offset_ != text_.size()) fail("trailing content");
        return result;
    }

private:
    [[noreturn]] void fail(const char* reason) const {
        throw std::runtime_error(std::string("invalid runtime JSON: ") + reason);
    }

    char take() {
        if (offset_ == text_.size()) fail("unexpected end");
        return text_[offset_++];
    }

    void literal(std::string_view expected) {
        if (text_.substr(offset_, expected.size()) != expected) fail("invalid literal");
        offset_ += expected.size();
    }

    Json value() {
        if (offset_ == text_.size()) fail("missing value");
        switch (text_[offset_]) {
            case '{': return object();
            case '[': return array();
            case '"': return Json{string()};
            case 't': literal("true"); return Json{true};
            case 'f': literal("false"); return Json{false};
            case 'n': literal("null"); return Json{nullptr};
            default: return number();
        }
    }

    Json object() {
        take();
        Json::Object result;
        if (offset_ < text_.size() && text_[offset_] == '}') {
            ++offset_;
            return Json{std::move(result)};
        }
        std::string previous;
        for (;;) {
            if (offset_ == text_.size() || text_[offset_] != '"') fail("object key");
            auto key = string();
            if (!previous.empty() && key <= previous) fail("object keys are not canonical");
            previous = key;
            if (take() != ':') fail("object separator");
            if (!result.emplace(std::move(key), value()).second) fail("duplicate key");
            const auto separator = take();
            if (separator == '}') return Json{std::move(result)};
            if (separator != ',') fail("object terminator");
        }
    }

    Json array() {
        take();
        Json::Array result;
        if (offset_ < text_.size() && text_[offset_] == ']') {
            ++offset_;
            return Json{std::move(result)};
        }
        for (;;) {
            result.push_back(value());
            const auto separator = take();
            if (separator == ']') return Json{std::move(result)};
            if (separator != ',') fail("array terminator");
        }
    }

    std::string string() {
        if (take() != '"') fail("string");
        std::string result;
        while (offset_ < text_.size()) {
            const auto character = static_cast<unsigned char>(take());
            if (character == '"') return result;
            if (character < 0x20 || character == '\\') {
                fail(character == '\\' ? "escaped strings are not canonical" : "control character");
            }
            if (character >= 0x80) fail("non-ASCII identity field");
            result.push_back(static_cast<char>(character));
        }
        fail("unterminated string");
    }

    Json number() {
        const auto begin = offset_;
        if (text_[offset_] == '-') ++offset_;
        if (offset_ == text_.size() || text_[offset_] < '0' || text_[offset_] > '9') {
            fail("number");
        }
        if (text_[offset_] == '0' && offset_ + 1 < text_.size() &&
            text_[offset_ + 1] >= '0' && text_[offset_ + 1] <= '9') {
            fail("leading zero");
        }
        while (offset_ < text_.size() && text_[offset_] >= '0' && text_[offset_] <= '9') {
            ++offset_;
        }
        if (offset_ < text_.size() && (text_[offset_] == '.' || text_[offset_] == 'e' || text_[offset_] == 'E')) {
            fail("floating-point number");
        }
        std::int64_t result = 0;
        const auto parsed = std::from_chars(text_.data() + begin, text_.data() + offset_, result);
        if (parsed.ec != std::errc{} || parsed.ptr != text_.data() + offset_) fail("integer range");
        return Json{result};
    }

    std::string text_;
    std::size_t offset_ = 0;
};

const Json::Object& object(const Json& value, std::initializer_list<std::string_view> keys) {
    const auto* result = std::get_if<Json::Object>(&value.value);
    if (!result || result->size() != keys.size()) throw std::runtime_error("runtime JSON object shape mismatch");
    for (const auto key : keys) {
        if (!result->contains(std::string(key))) throw std::runtime_error("runtime JSON field missing");
    }
    return *result;
}

const Json::Array& array(const Json& value) {
    const auto* result = std::get_if<Json::Array>(&value.value);
    if (!result) throw std::runtime_error("runtime JSON array expected");
    return *result;
}

const std::string& string(const Json::Object& value, std::string_view key) {
    const auto* result = std::get_if<std::string>(&value.at(std::string(key)).value);
    if (!result || result->empty()) throw std::runtime_error("runtime JSON string expected");
    return *result;
}

std::int64_t integer(const Json::Object& value, std::string_view key) {
    const auto* result = std::get_if<std::int64_t>(&value.at(std::string(key)).value);
    if (!result) throw std::runtime_error("runtime JSON integer expected");
    return *result;
}

bool boolean(const Json::Object& value, std::string_view key) {
    const auto* result = std::get_if<bool>(&value.at(std::string(key)).value);
    if (!result) throw std::runtime_error("runtime JSON boolean expected");
    return *result;
}

void require_sha256(std::string_view value) {
    if (value.size() != 71 || !value.starts_with("sha256:")) throw std::runtime_error("invalid SHA-256 identity");
    for (const auto character : value.substr(7)) {
        if (!((character >= '0' && character <= '9') || (character >= 'a' && character <= 'f'))) {
            throw std::runtime_error("invalid SHA-256 identity");
        }
    }
}

using Version = std::array<unsigned, 3>;

Version version(std::string_view value) {
    Version result{};
    std::size_t begin = 0;
    for (std::size_t index = 0; index < 3; ++index) {
        const auto end = index == 2 ? value.size() : value.find('.', begin);
        if (end == std::string_view::npos || end == begin) throw std::runtime_error("invalid semantic version");
        if (end - begin > 1 && value[begin] == '0') throw std::runtime_error("invalid semantic version");
        const auto parsed = std::from_chars(value.data() + begin, value.data() + end, result[index]);
        if (parsed.ec != std::errc{} || parsed.ptr != value.data() + end) throw std::runtime_error("invalid semantic version");
        begin = end + 1;
    }
    return result;
}

Version semver(std::string_view value) {
    const auto build = value.find('+');
    if (build != std::string_view::npos && value.find('+', build + 1) != std::string_view::npos)
        throw std::runtime_error("invalid semantic version");
    const auto core_and_prerelease = value.substr(0, build);
    const auto prerelease = core_and_prerelease.find('-');
    const auto core = core_and_prerelease.substr(0, prerelease);
    const auto parsed = version(core);
    const auto validate_identifiers = [](std::string_view identifiers, bool reject_numeric_zero) {
        if (identifiers.empty()) throw std::runtime_error("invalid semantic version");
        std::size_t begin = 0;
        while (begin < identifiers.size()) {
            const auto end = identifiers.find('.', begin);
            const auto identifier = identifiers.substr(
                begin, end == std::string_view::npos ? identifiers.size() - begin : end - begin);
            if (identifier.empty()) throw std::runtime_error("invalid semantic version");
            bool numeric = true;
            for (const auto character : identifier) {
                const bool digit = character >= '0' && character <= '9';
                numeric = numeric && digit;
                if (!(digit || (character >= 'A' && character <= 'Z') ||
                      (character >= 'a' && character <= 'z') || character == '-'))
                    throw std::runtime_error("invalid semantic version");
            }
            if (reject_numeric_zero && numeric && identifier.size() > 1 && identifier.front() == '0')
                throw std::runtime_error("invalid semantic version");
            if (end == std::string_view::npos) break;
            begin = end + 1;
        }
    };
    if (prerelease != std::string_view::npos)
        validate_identifiers(core_and_prerelease.substr(prerelease + 1), true);
    if (build != std::string_view::npos)
        validate_identifiers(value.substr(build + 1), false);
    return parsed;
}

bool in_range(std::string_view candidate, std::string_view expression) {
    const auto split = expression.find(' ');
    if (split == std::string_view::npos || !expression.starts_with(">=") ||
        expression.substr(split + 1).substr(0, 1) != "<") {
        throw std::runtime_error("invalid compatibility range");
    }
    return version(candidate) >= version(expression.substr(2, split - 2)) &&
           version(candidate) < version(expression.substr(split + 2));
}

std::string host_target() {
#if defined(_WIN32) && defined(_M_X64)
    return "windows-x64";
#elif defined(__APPLE__) && defined(__aarch64__)
    return "macos-arm64";
#elif defined(__APPLE__) && defined(__x86_64__)
    return "macos-x64";
#elif defined(__linux__) && defined(__aarch64__)
    return "linux-arm64";
#elif defined(__linux__) && defined(__x86_64__)
    return "linux-x64";
#else
#error Unsupported CodexAgent C++ runtime target
#endif
}

struct Compatibility {
    std::string release_range;
    std::string compatibility_range;
    std::string contract_digest;
    std::string default_runtime_version;
    std::string component_id;
    std::string library_sha256;
    std::int64_t identity_schema;
    std::int64_t abi_major;
    std::int64_t abi_minor;
};

Compatibility read_compatibility(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) throw std::runtime_error("SDK compatibility declaration is unavailable");
    std::string bytes(std::istreambuf_iterator<char>(stream), {});
    if (bytes.empty() || bytes.size() > 1024 * 1024 || bytes.back() != '\n') {
        throw std::runtime_error("SDK compatibility declaration is invalid");
    }
    bytes.pop_back();
    const auto root = object(JsonParser(std::move(bytes)).parse(),
        {"schemaVersion", "sdkVersion", "contract", "runtime", "platformRuntime"});
    if (integer(root, "schemaVersion") != 1) throw std::runtime_error("unsupported SDK compatibility schema");
    (void)semver(string(root, "sdkVersion"));
    const auto contract = object(root.at("contract"), {"version", "digest"});
    (void)version(string(contract, "version"));
    require_sha256(string(contract, "digest"));
    const auto runtime = object(root.at("runtime"), {
        "compatibleReleaseRange", "compatibleRuntimeCompatibilityRange",
        "requiredIdentitySchema", "requiredContractDigest", "requiredAbiMajor",
        "minimumAbiMinor", "defaultRuntimeVersion", "defaultManifestSha256",
        "embeddedVariants"});
    require_sha256(string(runtime, "requiredContractDigest"));
    require_sha256(string(runtime, "defaultManifestSha256"));
    if (string(contract, "digest") != string(runtime, "requiredContractDigest")) {
        throw std::runtime_error("SDK Contract identities disagree");
    }
    const auto platform = object(root.at("platformRuntime"), {"android", "ios"});
    for (const auto name : {"android", "ios"}) {
        const auto entry = object(platform.at(name), {"owner", "desktopRuntimeApplicable"});
        if (string(entry, "owner") != "sdk" || boolean(entry, "desktopRuntimeApplicable")) {
            throw std::runtime_error("invalid SDK platform runtime policy");
        }
    }
    const auto target = host_target();
    const Json::Object* selected = nullptr;
    const auto& variants = array(runtime.at("embeddedVariants"));
    if (variants.size() != 5) throw std::runtime_error("SDK compatibility must declare five variants");
    std::set<std::string> targets;
    std::set<std::string> component_ids;
    std::set<std::string> manifest_digests;
    static constexpr std::array<std::string_view, 5> expected_targets{
        "linux-arm64", "linux-x64", "macos-arm64", "macos-x64", "windows-x64"};
    std::size_t target_index = 0;
    for (const auto& item : variants) {
        const auto& entry = object(item, {"target", "componentId", "bundleSha256", "manifestSha256", "runtimeLibrarySha256"});
        const auto& entry_target = string(entry, "target");
        if (entry_target != expected_targets[target_index++]) {
            throw std::runtime_error("SDK runtime targets are not canonically ordered");
        }
        if (!targets.emplace(entry_target).second) throw std::runtime_error("duplicate SDK runtime target");
        for (const auto key : {"componentId", "bundleSha256", "manifestSha256", "runtimeLibrarySha256"}) {
            require_sha256(string(entry, key));
        }
        if (!component_ids.emplace(string(entry, "componentId")).second ||
            !manifest_digests.emplace(string(entry, "manifestSha256")).second) {
            throw std::runtime_error("duplicate SDK runtime variant identity");
        }
        if (entry_target == target) selected = &entry;
    }
    if (targets != std::set<std::string>{
            "linux-arm64", "linux-x64", "macos-arm64", "macos-x64", "windows-x64"}) {
        throw std::runtime_error("SDK compatibility has an invalid runtime target set");
    }
    if (!selected) throw std::runtime_error("SDK compatibility lacks the host runtime");
    Compatibility result{
        string(runtime, "compatibleReleaseRange"),
        string(runtime, "compatibleRuntimeCompatibilityRange"),
        string(runtime, "requiredContractDigest"),
        string(runtime, "defaultRuntimeVersion"),
        string(*selected, "componentId"),
        string(*selected, "runtimeLibrarySha256"),
        integer(runtime, "requiredIdentitySchema"),
        integer(runtime, "requiredAbiMajor"),
        integer(runtime, "minimumAbiMinor"),
    };
    if (result.identity_schema != 1 || result.abi_major != 1 || result.abi_minor < 13 ||
        !in_range(result.default_runtime_version, result.release_range)) {
        throw std::runtime_error("invalid SDK runtime compatibility policy");
    }
    return result;
}

class Sha256 final {
public:
    void update(const std::uint8_t* input, std::size_t size) {
        total_ += size;
        while (size != 0) {
            const auto count = std::min(size, block_.size() - used_);
            std::copy_n(input, count, block_.begin() + static_cast<std::ptrdiff_t>(used_));
            used_ += count;
            input += count;
            size -= count;
            if (used_ == block_.size()) { transform(); used_ = 0; }
        }
    }

    std::string finish() {
        const auto bits = total_ * 8;
        block_[used_++] = 0x80;
        if (used_ > 56) { std::fill(block_.begin() + static_cast<std::ptrdiff_t>(used_), block_.end(), 0); transform(); used_ = 0; }
        std::fill(block_.begin() + static_cast<std::ptrdiff_t>(used_), block_.begin() + 56, 0);
        for (std::size_t index = 0; index < 8; ++index) block_[63 - index] = static_cast<std::uint8_t>(bits >> (index * 8));
        transform();
        static constexpr char hex[] = "0123456789abcdef";
        std::string output = "sha256:";
        output.reserve(71);
        for (const auto word : state_) for (int shift = 24; shift >= 0; shift -= 8) {
            const auto byte = static_cast<std::uint8_t>(word >> shift);
            output.push_back(hex[byte >> 4]); output.push_back(hex[byte & 15]);
        }
        return output;
    }

private:
    static std::uint32_t rotate(std::uint32_t value, unsigned bits) { return (value >> bits) | (value << (32 - bits)); }
    void transform() {
        static constexpr std::array<std::uint32_t, 64> constants{
            0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
            0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
            0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
            0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
            0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
            0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
            0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
            0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
        std::array<std::uint32_t, 64> words{};
        for (std::size_t index = 0; index < 16; ++index) words[index] =
            (static_cast<std::uint32_t>(block_[index * 4]) << 24) |
            (static_cast<std::uint32_t>(block_[index * 4 + 1]) << 16) |
            (static_cast<std::uint32_t>(block_[index * 4 + 2]) << 8) | block_[index * 4 + 3];
        for (std::size_t index = 16; index < 64; ++index) {
            const auto s0 = rotate(words[index - 15], 7) ^ rotate(words[index - 15], 18) ^ (words[index - 15] >> 3);
            const auto s1 = rotate(words[index - 2], 17) ^ rotate(words[index - 2], 19) ^ (words[index - 2] >> 10);
            words[index] = words[index - 16] + s0 + words[index - 7] + s1;
        }
        auto [a,b,c,d,e,f,g,h] = state_;
        for (std::size_t index = 0; index < 64; ++index) {
            const auto s1 = rotate(e,6)^rotate(e,11)^rotate(e,25), choose=(e&f)^((~e)&g);
            const auto t1=h+s1+choose+constants[index]+words[index];
            const auto s0=rotate(a,2)^rotate(a,13)^rotate(a,22), majority=(a&b)^(a&c)^(b&c);
            h=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+s0+majority;
        }
        state_[0]+=a; state_[1]+=b; state_[2]+=c; state_[3]+=d; state_[4]+=e; state_[5]+=f; state_[6]+=g; state_[7]+=h;
    }
    std::array<std::uint32_t,8> state_{0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    std::array<std::uint8_t,64> block_{};
    std::size_t used_=0; std::uint64_t total_=0;
};

std::filesystem::path safe_absolute_file(const std::filesystem::path& path, const char* label) {
    if (!path.is_absolute() || path.lexically_normal() != path) {
        throw std::runtime_error(std::string(label) + " must be a normalized absolute file");
    }
    auto current = path.root_path();
    for (const auto& part : path.relative_path()) {
        current /= part;
        std::error_code error;
        const auto status = std::filesystem::symlink_status(current, error);
        if (error || status.type() == std::filesystem::file_type::not_found) {
            throw std::runtime_error(std::string(label) + " has a missing path component");
        }
        if (std::filesystem::is_symlink(status)) {
            throw std::runtime_error(std::string(label) + " has a symlink component");
        }
#ifdef _WIN32
        const auto attributes = GetFileAttributesW(current.c_str());
        if (attributes == INVALID_FILE_ATTRIBUTES ||
            (attributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0) {
            throw std::runtime_error(std::string(label) + " has a reparse component");
        }
#endif
    }
    const auto canonical = std::filesystem::canonical(path);
    if (canonical != path) {
        throw std::runtime_error(std::string(label) + " changed during path validation");
    }
    if (!std::filesystem::is_regular_file(canonical)) {
        throw std::runtime_error(std::string(label) + " must be an absolute regular file");
    }
    return canonical;
}

void remove_snapshot(const std::filesystem::path& path) noexcept {
    if (path.empty()) return;
#ifdef _WIN32
    SetFileAttributesW(path.c_str(), FILE_ATTRIBUTE_NORMAL);
#else
    std::error_code permission_error;
    std::filesystem::permissions(
        path.parent_path(), std::filesystem::perms::owner_all,
        std::filesystem::perm_options::replace, permission_error);
#endif
    std::error_code ignored;
    std::filesystem::remove_all(path.parent_path(), ignored);
}

struct SnapshotCapture {
    std::filesystem::path path;
    std::string digest;
    bool owned = true;
#ifdef _WIN32
    HANDLE descriptor = INVALID_HANDLE_VALUE;
#else
    int descriptor = -1;
#endif

    SnapshotCapture(std::filesystem::path path_value, std::string digest_value)
        : path(std::move(path_value)), digest(std::move(digest_value)) {}
    SnapshotCapture(const SnapshotCapture&) = delete;
    SnapshotCapture& operator=(const SnapshotCapture&) = delete;
    SnapshotCapture(SnapshotCapture&& other) noexcept
        : path(std::move(other.path)), digest(std::move(other.digest)), owned(other.owned),
          descriptor(other.descriptor) {
        other.owned = false;
#ifdef _WIN32
        other.descriptor = INVALID_HANDLE_VALUE;
#else
        other.descriptor = -1;
#endif
    }
    ~SnapshotCapture() { cleanup(); }
    void close_descriptor() noexcept {
#ifdef _WIN32
        if (descriptor != INVALID_HANDLE_VALUE) CloseHandle(descriptor);
        descriptor = INVALID_HANDLE_VALUE;
#else
        if (descriptor >= 0) close(descriptor);
        descriptor = -1;
#endif
    }
    std::filesystem::path retain() { owned = false; return path; }
#ifdef _WIN32
    HANDLE release_descriptor() {
        const auto result = descriptor;
        descriptor = INVALID_HANDLE_VALUE;
        return result;
    }
#endif
    void cleanup() {
        close_descriptor();
        if (owned) { remove_snapshot(path); owned = false; }
    }
};

#ifndef _WIN32
struct FileDescriptor {
    int value = -1;
    explicit FileDescriptor(int descriptor) : value(descriptor) {}
    FileDescriptor(const FileDescriptor&) = delete;
    FileDescriptor& operator=(const FileDescriptor&) = delete;
    ~FileDescriptor() { if (value >= 0) close(value); }
    void close_now() { if (value >= 0) close(value); value = -1; }
    int release() { const auto result = value; value = -1; return result; }
};

bool same_source(const struct stat& left, const struct stat& right) {
    if (left.st_dev != right.st_dev || left.st_ino != right.st_ino ||
        left.st_mode != right.st_mode || left.st_size != right.st_size) return false;
#ifdef __APPLE__
    return left.st_mtimespec.tv_sec == right.st_mtimespec.tv_sec &&
        left.st_mtimespec.tv_nsec == right.st_mtimespec.tv_nsec &&
        left.st_ctimespec.tv_sec == right.st_ctimespec.tv_sec &&
        left.st_ctimespec.tv_nsec == right.st_ctimespec.tv_nsec;
#else
    return left.st_mtim.tv_sec == right.st_mtim.tv_sec &&
        left.st_mtim.tv_nsec == right.st_mtim.tv_nsec &&
        left.st_ctim.tv_sec == right.st_ctim.tv_sec &&
        left.st_ctim.tv_nsec == right.st_ctim.tv_nsec;
#endif
}

std::string hash_descriptor(int descriptor) {
    if (lseek(descriptor, 0, SEEK_SET) < 0) throw std::runtime_error("native snapshot seek failed");
    Sha256 hash;
    std::array<std::uint8_t, 64 * 1024> buffer{};
    for (;;) {
        const auto count = read(descriptor, buffer.data(), buffer.size());
        if (count < 0) throw std::runtime_error("native snapshot read failed");
        if (count == 0) break;
        hash.update(buffer.data(), static_cast<std::size_t>(count));
    }
    return hash.finish();
}

#ifndef __APPLE__
std::string descriptor_path(int descriptor) {
    return "/proc/self/fd/" + std::to_string(descriptor);
}
#endif
#endif

SnapshotCapture snapshot(const std::filesystem::path& source) {
    const auto temporary_root = std::filesystem::canonical(
        std::filesystem::temp_directory_path());
#ifdef _WIN32
    const auto source_handle = CreateFileW(
        source.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
    if (source_handle == INVALID_HANDLE_VALUE) throw std::runtime_error("native runtime source open failed");
    struct HandleGuard {
        HANDLE value;
        ~HandleGuard() { if (value != INVALID_HANDLE_VALUE) CloseHandle(value); }
        void close() {
            if (value != INVALID_HANDLE_VALUE) CloseHandle(value);
            value = INVALID_HANDLE_VALUE;
        }
    } source_guard{source_handle};
    BY_HANDLE_FILE_INFORMATION before{};
    if (!GetFileInformationByHandle(source_handle, &before) ||
        (before.dwFileAttributes & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT)) != 0) {
        throw std::runtime_error("native runtime source identity failed");
    }
    const auto directory = temporary_root /
        ("codex-agent-runtime-" + std::to_string(GetCurrentProcessId()) + "-" +
         std::to_string(GetTickCount64()) + "-" + std::to_string(reinterpret_cast<std::uintptr_t>(source_handle)));
    if (!CreateDirectoryW(directory.c_str(), nullptr)) throw std::runtime_error("native snapshot directory creation failed");
    const auto destination = directory / source.filename();
    SnapshotCapture capture(destination, {});
    const auto output = CreateFileW(destination.c_str(), GENERIC_READ | GENERIC_WRITE, 0,
        nullptr, CREATE_NEW, FILE_ATTRIBUTE_TEMPORARY, nullptr);
    if (output == INVALID_HANDLE_VALUE) throw std::runtime_error("native snapshot creation failed");
    HandleGuard output_guard{output};
    std::array<std::uint8_t, 64 * 1024> buffer{};
    for (;;) {
        DWORD count = 0;
        if (!ReadFile(source_handle, buffer.data(), static_cast<DWORD>(buffer.size()), &count, nullptr))
            throw std::runtime_error("native source read failed");
        if (count == 0) break;
        DWORD written = 0;
        if (!WriteFile(output, buffer.data(), count, &written, nullptr) || written != count)
            throw std::runtime_error("native snapshot write failed");
    }
    if (!FlushFileBuffers(output)) throw std::runtime_error("native snapshot flush failed");
    BY_HANDLE_FILE_INFORMATION after{};
    if (!GetFileInformationByHandle(source_handle, &after) ||
        before.dwVolumeSerialNumber != after.dwVolumeSerialNumber ||
        before.nFileIndexHigh != after.nFileIndexHigh ||
        before.nFileIndexLow != after.nFileIndexLow ||
        before.nFileSizeHigh != after.nFileSizeHigh ||
        before.nFileSizeLow != after.nFileSizeLow ||
        before.ftLastWriteTime.dwHighDateTime != after.ftLastWriteTime.dwHighDateTime ||
        before.ftLastWriteTime.dwLowDateTime != after.ftLastWriteTime.dwLowDateTime ||
        before.dwFileAttributes != after.dwFileAttributes) {
        throw std::runtime_error("native runtime source changed during snapshot");
    }
    LARGE_INTEGER zero{};
    if (!SetFilePointerEx(output, zero, nullptr, FILE_BEGIN)) throw std::runtime_error("native snapshot seek failed");
    Sha256 hash;
    for (;;) {
        DWORD count = 0;
        if (!ReadFile(output, buffer.data(), static_cast<DWORD>(buffer.size()), &count, nullptr))
            throw std::runtime_error("native snapshot verification read failed");
        if (count == 0) break;
        hash.update(buffer.data(), count);
    }
    capture.digest = hash.finish();
    output_guard.close();
    if (!SetFileAttributesW(destination.c_str(), FILE_ATTRIBUTE_READONLY))
        throw std::runtime_error("native snapshot protection failed");
    capture.descriptor = CreateFileW(destination.c_str(), GENERIC_READ,
        FILE_SHARE_READ, nullptr, OPEN_EXISTING,
        FILE_ATTRIBUTE_READONLY | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
    if (capture.descriptor == INVALID_HANDLE_VALUE)
        throw std::runtime_error("native snapshot protected reopen failed");
    return capture;
#else
    FileDescriptor source_descriptor(open(source.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW));
    if (source_descriptor.value < 0) throw std::runtime_error("native runtime source open failed");
    struct stat before{};
    if (fstat(source_descriptor.value, &before) != 0 || !S_ISREG(before.st_mode))
        throw std::runtime_error("native runtime source identity failed");
    auto pattern = (temporary_root /
        ("codex-agent-runtime-" + std::to_string(getpid()) + "-XXXXXX")).string();
    std::vector<char> writable(pattern.begin(), pattern.end());
    writable.push_back('\0');
    const auto created = mkdtemp(writable.data());
    if (!created) throw std::runtime_error("native snapshot directory creation failed");
    const auto directory = std::filesystem::path(created);
    const auto destination = directory / source.filename();
    SnapshotCapture capture(destination, {});
    FileDescriptor output(open(destination.c_str(), O_RDWR | O_CREAT | O_EXCL | O_CLOEXEC, 0400));
    if (output.value < 0) throw std::runtime_error("native snapshot creation failed");
    std::array<std::uint8_t, 64 * 1024> buffer{};
    std::uint64_t copied = 0;
    for (;;) {
        const auto count = read(source_descriptor.value, buffer.data(), buffer.size());
        if (count < 0) throw std::runtime_error("native source read failed");
        if (count == 0) break;
        copied += static_cast<std::uint64_t>(count);
        std::size_t offset = 0;
        while (offset != static_cast<std::size_t>(count)) {
            const auto written = write(output.value, buffer.data() + offset,
                static_cast<std::size_t>(count) - offset);
            if (written <= 0) throw std::runtime_error("native snapshot write failed");
            offset += static_cast<std::size_t>(written);
        }
    }
    if (fsync(output.value) != 0 || fchmod(output.value, 0400) != 0)
        throw std::runtime_error("native snapshot protection failed");
    struct stat after{};
    if (fstat(source_descriptor.value, &after) != 0 ||
        !same_source(before, after) || copied != static_cast<std::uint64_t>(before.st_size)) {
        throw std::runtime_error("native runtime source changed during snapshot");
    }
    struct stat written{};
    if (fstat(output.value, &written) != 0)
        throw std::runtime_error("native snapshot identity failed");
    if (chmod(directory.c_str(), 0500) != 0)
        throw std::runtime_error("native snapshot directory protection failed");
    FileDescriptor verified(open(destination.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW));
    output.close_now();
    struct stat reopened{};
    if (verified.value < 0 || fstat(verified.value, &reopened) != 0 ||
        !same_source(written, reopened)) {
        throw std::runtime_error("native snapshot changed before protected reopen");
    }
    capture.digest = hash_descriptor(verified.value);
    capture.descriptor = verified.release();
    return capture;
#endif
}

#ifdef CODEX_AGENT_NATIVE_LOADER_TEST_HOOK
void invoke_loader_test_hook(const std::filesystem::path& path) {
    if (const auto hook = loader_test_hook.load()) hook(path);
}
#endif

#ifdef __APPLE__
void verify_snapshot_binding(const SnapshotCapture& snapshot) {
    struct stat held{};
    if (fstat(snapshot.descriptor, &held) != 0 || !S_ISREG(held.st_mode))
        throw std::runtime_error("native snapshot descriptor identity failed");
    FileDescriptor path_descriptor(open(snapshot.path.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW));
    struct stat path_identity{};
    if (path_descriptor.value < 0 || fstat(path_descriptor.value, &path_identity) != 0 ||
        !same_source(held, path_identity) ||
        hash_descriptor(snapshot.descriptor) != snapshot.digest ||
        hash_descriptor(path_descriptor.value) != snapshot.digest) {
        throw std::runtime_error("native snapshot path binding failed");
    }
}
#endif

void* open_library(const SnapshotCapture& snapshot) {
#ifdef CODEX_AGENT_NATIVE_LOADER_TEST_HOOK
    invoke_loader_test_hook(snapshot.path);
#endif
#ifdef _WIN32
    const auto handle = LoadLibraryExW(snapshot.path.c_str(), nullptr,
        LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!handle) throw std::runtime_error("failed to load the exact native runtime path");
    return handle;
#elif defined(__APPLE__)
    verify_snapshot_binding(snapshot);
    const auto handle = dlopen(snapshot.path.c_str(), RTLD_NOW | RTLD_LOCAL);
    if (!handle)
        throw std::runtime_error(std::string("failed to load the exact native runtime path: ") + dlerror());
    try {
        verify_snapshot_binding(snapshot);
    } catch (...) {
        dlclose(handle);
        throw;
    }
    return handle;
#else
    const auto path = descriptor_path(snapshot.descriptor);
    const auto handle = dlopen(path.c_str(), RTLD_NOW | RTLD_LOCAL);
    if (!handle) throw std::runtime_error(std::string("failed to load the exact native runtime path: ") + dlerror());
    return handle;
#endif
}

void* symbol(void* library, const char* name) {
#ifdef _WIN32
    const auto result = GetProcAddress(static_cast<HMODULE>(library), name);
#else
    dlerror();
    const auto result = dlsym(library, name);
#endif
    if (!result) throw std::runtime_error(std::string("native runtime is missing symbol: ") + name);
    return reinterpret_cast<void*>(result);
}

const char* symbol_name(NativeSymbol symbol_value) {
    switch (symbol_value) {
#define CODEX_AGENT_NATIVE_SYMBOL(id, name) case NativeSymbol::id: return #name;
#include <codex_agent/native_symbols.inc>
#undef CODEX_AGENT_NATIVE_SYMBOL
    }
    throw std::runtime_error("unknown native symbol");
}

void validate_identity(void* library, const Compatibility& compatibility, bool embedded) {
    using Identity = codex_agent_status_t(CODEX_AGENT_CALL*)(char*, std::size_t*);
    const auto identity = reinterpret_cast<Identity>(symbol(library, "codex_agent_runtime_identity"));
    std::size_t required = 0;
    if (identity(nullptr, &required) != CODEX_AGENT_STATUS_BUFFER_TOO_SMALL || required < 3 || required > 1024 * 1024) {
        throw std::runtime_error("native runtime identity size contract failed");
    }
    std::vector<char> bytes(required);
    auto capacity = required;
    if (identity(bytes.data(), &capacity) != CODEX_AGENT_STATUS_OK || capacity != required || bytes.back() != '\0') {
        throw std::runtime_error("native runtime identity read failed");
    }
    bytes.pop_back();
    const auto root = object(JsonParser(std::string(bytes.begin(), bytes.end())).parse(), {
        "schemaVersion", "componentId", "runtimeCompatibilityVersion", "contractDigest",
        "contractComponentDigest", "cAbiVersion", "target", "appServerVersion", "buildInputDigest"});
    for (const auto key : {"componentId", "contractDigest", "contractComponentDigest", "buildInputDigest"}) require_sha256(string(root, key));
    const auto abi = version(string(root, "cAbiVersion"));
    using AbiVersion = std::uint32_t(CODEX_AGENT_CALL*)();
    const auto actual_abi = reinterpret_cast<AbiVersion>(symbol(library, "codex_agent_abi_version"))();
    const auto encoded_identity_abi =
        ((abi[0] & 0xffu) << 24) | ((abi[1] & 0xffu) << 16) | (abi[2] & 0xffffu);
    if (integer(root, "schemaVersion") != compatibility.identity_schema ||
        string(root, "target") != host_target() ||
        string(root, "contractDigest") != compatibility.contract_digest ||
        actual_abi != encoded_identity_abi ||
        abi[0] != static_cast<unsigned>(compatibility.abi_major) ||
        abi[1] < static_cast<unsigned>(compatibility.abi_minor) ||
        !in_range(string(root, "runtimeCompatibilityVersion"), compatibility.compatibility_range) ||
        (embedded && string(root, "componentId") != compatibility.component_id)) {
        throw std::runtime_error("native runtime identity is incompatible with this SDK");
    }
    (void)version(string(root, "runtimeCompatibilityVersion"));
    (void)version(string(root, "appServerVersion"));
}

struct LoaderState {
    std::mutex mutex;
    std::filesystem::path configured;
    void* library = nullptr;
    std::map<NativeSymbol, void*> symbols;
    std::filesystem::path retained_snapshot;
#ifdef _WIN32
    HANDLE retained_descriptor = INVALID_HANDLE_VALUE;
#endif

    ~LoaderState() {
        if (library) {
#ifdef _WIN32
            FreeLibrary(static_cast<HMODULE>(library));
#else
            dlclose(library);
#endif
        }
#ifdef _WIN32
        if (retained_descriptor != INVALID_HANDLE_VALUE) CloseHandle(retained_descriptor);
#endif
        remove_snapshot(retained_snapshot);
    }
};

LoaderState& state() { static LoaderState value; return value; }

void configure_native_library(const std::filesystem::path& path) {
    const auto canonical = safe_absolute_file(path, "configured native runtime");
    auto& loader = state();
    std::lock_guard lock(loader.mutex);
    if (loader.library) throw std::logic_error("native runtime is already loaded");
    if (!loader.configured.empty() && loader.configured != canonical) throw std::logic_error("native runtime is already configured");
    loader.configured = canonical;
}

}  // namespace

#ifdef CODEX_AGENT_NATIVE_LOADER_TEST_HOOK
void set_native_loader_test_hook(void (*hook)(const std::filesystem::path&)) {
    loader_test_hook.store(hook);
}
#endif

void* resolve_native_symbol(NativeSymbol requested, std::string_view default_library_path, std::string_view compatibility_path) {
    auto& loader = state();
    std::lock_guard lock(loader.mutex);
    if (!loader.library) {
        if (default_library_path.empty() || compatibility_path.empty()) throw std::runtime_error("CodexAgent package has no declared native runtime");
        const auto default_path = safe_absolute_file(
            std::filesystem::path(default_library_path), "embedded native runtime");
        const auto compatibility_file = safe_absolute_file(
            std::filesystem::path(compatibility_path), "SDK compatibility declaration");
        const auto compatibility = read_compatibility(compatibility_file);
        const bool embedded = loader.configured.empty();
        const auto source = embedded ? default_path : loader.configured;
        (void)safe_absolute_file(source, "selected native runtime");
        auto selected = snapshot(source);
        if (embedded) {
            if (selected.digest != compatibility.library_sha256) {
                throw std::runtime_error("embedded native runtime hash mismatch");
            }
        }
        loader.library = open_library(selected);
        try {
            validate_identity(loader.library, compatibility, embedded);
        } catch (...) {
#ifdef _WIN32
            FreeLibrary(static_cast<HMODULE>(loader.library));
#else
            dlclose(loader.library);
#endif
            loader.library = nullptr;
            throw;
        }
#ifdef _WIN32
        loader.retained_snapshot = selected.retain();
        loader.retained_descriptor = selected.release_descriptor();
#else
        selected.cleanup();
#endif
    }
    if (const auto found = loader.symbols.find(requested); found != loader.symbols.end()) return found->second;
    return loader.symbols.emplace(requested, symbol(loader.library, symbol_name(requested))).first->second;
}

}  // namespace codex_agent::detail

void codex_agent::CodexNativeLibrary::configure(const std::filesystem::path& absolute_library_path) {
    detail::configure_native_library(absolute_library_path);
}
