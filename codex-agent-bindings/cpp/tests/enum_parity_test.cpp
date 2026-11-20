#include <codex_agent/codex_agent.hpp>

#include <algorithm>
#include <array>
#include <cctype>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#define CODEX_AGENT_CPP_ENUM(index, type, member, constant, symbol)            \
    static_assert(static_cast<std::int32_t>(                                  \
                      codex_agent::type::member) == constant);
#include "enum_capabilities.inc"
#undef CODEX_AGENT_CPP_ENUM

namespace {

constexpr std::string_view claims_header =
    "capabilityKey\tpublicSymbols\texecutedTests\tcompilerEvidenceIds\tsharedScenarios";

struct EnumEvidence {
    std::size_t index;
    std::string_view public_symbol;
    std::int32_t public_value;
    std::int32_t c_value;
};

constexpr std::array<EnumEvidence, 110> enum_evidence{{
#define CODEX_AGENT_CPP_ENUM(index, type, member, constant, symbol)            \
    EnumEvidence{index, symbol,                                                \
                 static_cast<std::int32_t>(codex_agent::type::member),         \
                 constant},
#include "enum_capabilities.inc"
#undef CODEX_AGENT_CPP_ENUM
}};

struct Claim {
    std::string capability_key;
    std::vector<std::string> public_symbols;
    std::vector<std::string> executed_tests;
    std::vector<std::string> compiler_evidence_ids;
    std::vector<std::string> shared_scenarios;
};

[[noreturn]] void fail(std::string message) {
    throw std::runtime_error(std::move(message));
}

void require(bool condition, std::string message) {
    if (!condition) {
        fail(std::move(message));
    }
}

std::string read_file(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    require(input.good(), "missing evidence input: " + path.string());
    return {std::istreambuf_iterator<char>(input),
            std::istreambuf_iterator<char>()};
}

std::vector<std::string> split(std::string_view value, char delimiter) {
    std::vector<std::string> result;
    std::size_t start = 0;
    for (;;) {
        const auto end = value.find(delimiter, start);
        result.emplace_back(value.substr(start, end - start));
        if (end == std::string_view::npos) {
            return result;
        }
        start = end + 1;
    }
}

bool exact_record(std::string_view value) {
    return !value.empty() && value.front() != ' ' && value.back() != ' ' &&
           value.find('*') == std::string_view::npos &&
           std::none_of(value.begin(), value.end(), [](unsigned char character) {
               return std::iscntrl(character) != 0;
           });
}

std::vector<std::string> exact_list(
    std::string_view value,
    std::string_view label) {
    auto result = split(value, ',');
    require(
        std::all_of(result.begin(), result.end(), [](const std::string& item) {
            return exact_record(item);
        }),
        std::string(label) + " contains a malformed record");
    require(std::is_sorted(result.begin(), result.end()) &&
                std::adjacent_find(result.begin(), result.end()) == result.end(),
            std::string(label) + " must be sorted and unique");
    return result;
}

std::vector<Claim> parse_claims(std::string_view contents) {
    require(!contents.empty() && contents.back() == '\n' &&
                contents.find('\r') == std::string_view::npos,
            "claims must use canonical LF encoding");
    contents.remove_suffix(1);
    auto lines = split(contents, '\n');
    require(!lines.empty() && lines.front() == claims_header,
            "invalid claims header");
    std::vector<Claim> result;
    for (std::size_t index = 1; index < lines.size(); ++index) {
        auto columns = split(lines[index], '\t');
        require(columns.size() == 5 &&
                    std::all_of(columns.begin(), columns.end(), exact_record),
                "malformed claims row " + std::to_string(index + 1));
        result.push_back({
            std::move(columns[0]),
            exact_list(columns[1], "publicSymbols"),
            exact_list(columns[2], "executedTests"),
            exact_list(columns[3], "compilerEvidenceIds"),
            exact_list(columns[4], "sharedScenarios"),
        });
    }
    require(!result.empty(), "claims inventory is empty");
    for (std::size_t index = 1; index < result.size(); ++index) {
        require(result[index - 1].capability_key < result[index].capability_key,
                "capability keys must be sorted and unique");
    }
    return result;
}

std::set<std::string> canonical_enum_capabilities(
    const std::filesystem::path& report_path) {
    std::set<std::string> result;
    std::istringstream lines(read_file(report_path));
    std::string line;
    while (std::getline(lines, line)) {
        const auto first_quote = line.find('"');
        const auto last_quote = line.rfind('"');
        if (first_quote == std::string::npos || first_quote == last_quote) {
            continue;
        }
        auto value = line.substr(first_quote + 1, last_quote - first_quote - 1);
        if (value.find("|kind=enum-entry|") != std::string::npos) {
            result.insert(std::move(value));
        }
    }
    require(result.size() == 110,
            "canonical report must contain exactly 110 enum capabilities");
    return result;
}

template <typename Range, typename Select>
std::set<std::string> collect_unique(
    const Range& range,
    Select select,
    std::string_view label) {
    std::set<std::string> result;
    std::size_t count = 0;
    for (const auto& item : range) {
        for (const auto& value : select(item)) {
            ++count;
            require(result.insert(std::string(value)).second,
                    std::string(label) + " must be globally unique");
        }
    }
    require(result.size() == count, std::string(label) + " contains duplicates");
    return result;
}

std::string padded_index(std::size_t index) {
    std::ostringstream value;
    value << std::setw(3) << std::setfill('0') << index;
    return value.str();
}

void validate_claims(
    const std::vector<Claim>& claims,
    const std::set<std::string>& canonical) {
    require(claims.size() == enum_evidence.size(),
            "C++ enum claim count must be exactly 110");
    std::set<std::string> capability_keys;
    std::set<std::string> compiled_symbols;
    for (const auto& evidence : enum_evidence) {
        compiled_symbols.emplace(evidence.public_symbol);
    }
    for (std::size_t index = 0; index < claims.size(); ++index) {
        const auto& claim = claims[index];
        const auto& evidence = enum_evidence[index];
        require(evidence.index == index && evidence.public_value == evidence.c_value,
                "compiled C++ enum does not match codex_agent.h at index " +
                    std::to_string(index));
        require(capability_keys.insert(claim.capability_key).second,
                "duplicate capability key");
        require(claim.public_symbols ==
                    std::vector<std::string>{std::string(evidence.public_symbol)},
                "claim public symbol does not match compiled C++ at index " +
                    std::to_string(index));
        require(claim.executed_tests ==
                    std::vector<std::string>{"cpp.enum:" + padded_index(index)},
                "claim test ID is not exact at index " + std::to_string(index));
        require(claim.compiler_evidence_ids ==
                    std::vector<std::string>{"cpp-header-enum:" +
                                             std::to_string(index)},
                "claim compiler evidence ID is not exact at index " +
                    std::to_string(index));
        require(claim.shared_scenarios ==
                    std::vector<std::string>{"value-conversion"},
                "claim scenario is not exact at index " + std::to_string(index));
    }
    require(capability_keys == canonical,
            "C++ enum claims are stale, missing, or overclaimed");
    require(collect_unique(claims, [](const Claim& claim) {
                return claim.public_symbols;
            }, "public symbols") == compiled_symbols,
            "C++ public symbol inventory does not match compiler evidence");
    (void)collect_unique(claims, [](const Claim& claim) {
        return claim.executed_tests;
    }, "executed tests");
    (void)collect_unique(claims, [](const Claim& claim) {
        return claim.compiler_evidence_ids;
    }, "compiler evidence IDs");
}

template <typename Action>
void require_rejected(Action&& action, std::string_view label) {
    try {
        action();
    } catch (const std::exception&) {
        return;
    }
    fail(std::string(label) + " was accepted");
}

void write_evidence(
    const std::filesystem::path& output_directory,
    const std::map<std::string, std::string>& compiler_evidence,
    const std::set<std::string>& executed_tests) {
    std::filesystem::create_directories(output_directory);
    {
        std::ofstream output(
            output_directory / "compiler-evidence.tsv",
            std::ios::binary | std::ios::trunc);
        require(output.good(), "cannot create compiler evidence");
        output << "compilerEvidenceId\tpublicSymbols\n";
        for (const auto& [id, symbol] : compiler_evidence) {
            output << id << '\t' << symbol << '\n';
        }
        require(output.good(), "cannot write compiler evidence");
    }
    {
        std::ofstream output(
            output_directory / "executed-tests.tsv",
            std::ios::binary | std::ios::trunc);
        require(output.good(), "cannot create executed test evidence");
        output << "executedTestId\tstatus\n";
        for (const auto& id : executed_tests) {
            output << id << "\tpassed\n";
        }
        require(output.good(), "cannot write executed test evidence");
    }
}

}  // namespace

int main(int argc, char** argv) {
    require(argc == 4,
            "usage: enum_parity_test CLAIMS CANONICAL_REPORT OUTPUT_DIRECTORY");
    const auto claims_contents = read_file(argv[1]);
    const auto all_claims = parse_claims(claims_contents);
    std::vector<Claim> claims;
    std::copy_if(all_claims.begin(), all_claims.end(), std::back_inserter(claims),
                 [](const Claim& claim) {
                     return claim.capability_key.find("|kind=enum-entry|") !=
                            std::string::npos;
                 });
    const auto canonical = canonical_enum_capabilities(argv[2]);
    validate_claims(claims, canonical);

    require_rejected(
        [&] {
            auto malformed = claims_contents;
            malformed.replace(0, claims_header.size(), "bad header");
            (void)parse_claims(malformed);
        },
        "malformed inventory");
    require_rejected(
        [&] {
            const auto first_newline = claims_contents.find('\n');
            const auto second_newline = claims_contents.find('\n', first_newline + 1);
            auto duplicate = claims_contents;
            duplicate.insert(second_newline + 1,
                             claims_contents.substr(first_newline + 1,
                                                    second_newline - first_newline));
            (void)parse_claims(duplicate);
        },
        "duplicate inventory");
    require_rejected(
        [&] {
            auto stale = claims;
            stale.front().capability_key += ".stale";
            validate_claims(stale, canonical);
        },
        "stale inventory");

    std::map<std::string, std::string> passed_compiler_evidence;
    std::set<std::string> passed_tests;
    for (std::size_t index = 0; index < claims.size(); ++index) {
        const auto& claim = claims[index];
        const auto& evidence = enum_evidence[index];
        require(evidence.public_value == evidence.c_value,
                "enum value conversion failed for " + claim.capability_key);
        require(passed_compiler_evidence
                    .emplace(claim.compiler_evidence_ids.front(),
                             claim.public_symbols.front())
                    .second,
                "compiler evidence executed twice");
        require(passed_tests.insert(claim.executed_tests.front()).second,
                "test ID executed twice");
    }

    const auto expected_compiler = collect_unique(
        claims,
        [](const Claim& claim) { return claim.compiler_evidence_ids; },
        "expected compiler evidence");
    const auto expected_tests = collect_unique(
        claims,
        [](const Claim& claim) { return claim.executed_tests; },
        "expected tests");
    std::set<std::string> passed_compiler_ids;
    for (const auto& [id, ignored] : passed_compiler_evidence) {
        (void)ignored;
        passed_compiler_ids.insert(id);
    }
    require(passed_compiler_ids == expected_compiler,
            "compiler evidence ID execution is incomplete");
    require(passed_tests == expected_tests, "test ID execution is incomplete");
    write_evidence(argv[3], passed_compiler_evidence, passed_tests);
}
