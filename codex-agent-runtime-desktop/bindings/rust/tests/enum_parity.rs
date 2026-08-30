use codex_agent::*;
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};
use std::process::Command;

#[path = "support/residual_behavior.rs"]
mod residual_behavior;
#[path = "support/value_behavior.rs"]
mod value_behavior;

const CLAIMS_HEADER: &str =
    "capabilityKey\tpublicSymbols\texecutedTests\tcompilerEvidenceIds\tsharedScenarios";

const RUST_ENUM_VALUES: [(&str, i32); 110] = [
    ("ApprovalDecision::Accept", ApprovalDecision::Accept as i32),
    (
        "ApprovalDecision::Decline",
        ApprovalDecision::Decline as i32,
    ),
    ("ApprovalPreset::AskMe", ApprovalPreset::AskMe as i32),
    (
        "ApprovalPreset::AutoReview",
        ApprovalPreset::AutoReview as i32,
    ),
    ("ApprovalPreset::Never", ApprovalPreset::Never as i32),
    ("ApprovalPreset::Strict", ApprovalPreset::Strict as i32),
    (
        "AuthenticationStatus::Authenticated",
        AuthenticationStatus::Authenticated as i32,
    ),
    (
        "AuthenticationStatus::Authenticating",
        AuthenticationStatus::Authenticating as i32,
    ),
    (
        "AuthenticationStatus::SignedOut",
        AuthenticationStatus::SignedOut as i32,
    ),
    ("Capability::WebSearch", Capability::WebSearch as i32),
    (
        "CatalogFreshness::FreshCache",
        CatalogFreshness::FreshCache as i32,
    ),
    ("CatalogFreshness::Live", CatalogFreshness::Live as i32),
    (
        "CatalogFreshness::StaleCache",
        CatalogFreshness::StaleCache as i32,
    ),
    (
        "CollaborationMode::Default",
        CollaborationMode::Default as i32,
    ),
    ("CollaborationMode::Plan", CollaborationMode::Plan as i32),
    (
        "ConversationStatus::CancellingTurn",
        ConversationStatus::CancellingTurn as i32,
    ),
    (
        "ConversationStatus::Closed",
        ConversationStatus::Closed as i32,
    ),
    (
        "ConversationStatus::Failed",
        ConversationStatus::Failed as i32,
    ),
    ("ConversationStatus::New", ConversationStatus::New as i32),
    (
        "ConversationStatus::Opening",
        ConversationStatus::Opening as i32,
    ),
    (
        "ConversationStatus::Ready",
        ConversationStatus::Ready as i32,
    ),
    (
        "ConversationStatus::Reloading",
        ConversationStatus::Reloading as i32,
    ),
    (
        "ConversationStatus::RunningTurn",
        ConversationStatus::RunningTurn as i32,
    ),
    (
        "ConversationStatus::StartingTurn",
        ConversationStatus::StartingTurn as i32,
    ),
    (
        "ElicitationAction::Accept",
        ElicitationAction::Accept as i32,
    ),
    (
        "ElicitationAction::Cancel",
        ElicitationAction::Cancel as i32,
    ),
    (
        "ElicitationAction::Decline",
        ElicitationAction::Decline as i32,
    ),
    (
        "ElicitationValidationReason::AboveMaximum",
        ElicitationValidationReason::AboveMaximum as i32,
    ),
    (
        "ElicitationValidationReason::BelowMinimum",
        ElicitationValidationReason::BelowMinimum as i32,
    ),
    (
        "ElicitationValidationReason::DuplicateSelection",
        ElicitationValidationReason::DuplicateSelection as i32,
    ),
    (
        "ElicitationValidationReason::InvalidFormat",
        ElicitationValidationReason::InvalidFormat as i32,
    ),
    (
        "ElicitationValidationReason::InvalidSelection",
        ElicitationValidationReason::InvalidSelection as i32,
    ),
    (
        "ElicitationValidationReason::InvalidType",
        ElicitationValidationReason::InvalidType as i32,
    ),
    (
        "ElicitationValidationReason::MissingRequired",
        ElicitationValidationReason::MissingRequired as i32,
    ),
    (
        "ElicitationValidationReason::NonFiniteNumber",
        ElicitationValidationReason::NonFiniteNumber as i32,
    ),
    (
        "ElicitationValidationReason::NonInteger",
        ElicitationValidationReason::NonInteger as i32,
    ),
    (
        "ElicitationValidationReason::UnknownField",
        ElicitationValidationReason::UnknownField as i32,
    ),
    ("FormFieldType::Boolean", FormFieldType::Boolean as i32),
    ("FormFieldType::Integer", FormFieldType::Integer as i32),
    (
        "FormFieldType::MultiSelect",
        FormFieldType::MultiSelect as i32,
    ),
    ("FormFieldType::Number", FormFieldType::Number as i32),
    (
        "FormFieldType::SingleSelect",
        FormFieldType::SingleSelect as i32,
    ),
    ("FormFieldType::String", FormFieldType::String as i32),
    (
        "FormStringFormat::DateTime",
        FormStringFormat::DateTime as i32,
    ),
    ("FormStringFormat::Date", FormStringFormat::Date as i32),
    ("FormStringFormat::Email", FormStringFormat::Email as i32),
    ("FormStringFormat::Uri", FormStringFormat::Uri as i32),
    ("HookRunStatus::Blocked", HookRunStatus::Blocked as i32),
    ("HookRunStatus::Completed", HookRunStatus::Completed as i32),
    ("HookRunStatus::Failed", HookRunStatus::Failed as i32),
    ("HookRunStatus::Running", HookRunStatus::Running as i32),
    ("HookRunStatus::Stopped", HookRunStatus::Stopped as i32),
    ("HookTrustStatus::Managed", HookTrustStatus::Managed as i32),
    (
        "HookTrustStatus::Modified",
        HookTrustStatus::Modified as i32,
    ),
    ("HookTrustStatus::Trusted", HookTrustStatus::Trusted as i32),
    (
        "HookTrustStatus::Untrusted",
        HookTrustStatus::Untrusted as i32,
    ),
    ("InstallationScope::User", InstallationScope::User as i32),
    (
        "InstallationScope::Workspace",
        InstallationScope::Workspace as i32,
    ),
    (
        "IntegrationAuthorizationStatus::Authorized",
        IntegrationAuthorizationStatus::Authorized as i32,
    ),
    (
        "IntegrationAuthorizationStatus::AwaitingCompletion",
        IntegrationAuthorizationStatus::AwaitingCompletion as i32,
    ),
    (
        "IntegrationAuthorizationStatus::Failed",
        IntegrationAuthorizationStatus::Failed as i32,
    ),
    (
        "IntegrationAuthorizationStatus::Idle",
        IntegrationAuthorizationStatus::Idle as i32,
    ),
    (
        "IntegrationAuthorizationStatus::Starting",
        IntegrationAuthorizationStatus::Starting as i32,
    ),
    (
        "McpAuthStatus::BearerToken",
        McpAuthStatus::BearerToken as i32,
    ),
    (
        "McpAuthStatus::NotLoggedIn",
        McpAuthStatus::NotLoggedIn as i32,
    ),
    ("McpAuthStatus::Oauth", McpAuthStatus::Oauth as i32),
    ("McpAuthStatus::Unknown", McpAuthStatus::Unknown as i32),
    (
        "McpAuthStatus::Unsupported",
        McpAuthStatus::Unsupported as i32,
    ),
    (
        "McpAuthentication::ChatGpt",
        McpAuthentication::ChatGpt as i32,
    ),
    ("McpAuthentication::Oauth", McpAuthentication::Oauth as i32),
    (
        "McpEnvironmentSource::Local",
        McpEnvironmentSource::Local as i32,
    ),
    (
        "McpEnvironmentSource::Remote",
        McpEnvironmentSource::Remote as i32,
    ),
    ("McpToolApproval::Approve", McpToolApproval::Approve as i32),
    ("McpToolApproval::Auto", McpToolApproval::Auto as i32),
    ("McpToolApproval::Prompt", McpToolApproval::Prompt as i32),
    ("McpToolApproval::Writes", McpToolApproval::Writes as i32),
    (
        "McpToolExposureSurface::CodeMode",
        McpToolExposureSurface::CodeMode as i32,
    ),
    (
        "McpToolExposureSurface::Deferred",
        McpToolExposureSurface::Deferred as i32,
    ),
    (
        "McpToolExposureSurface::Direct",
        McpToolExposureSurface::Direct as i32,
    ),
    ("MessageRole::Assistant", MessageRole::Assistant as i32),
    ("MessageRole::User", MessageRole::User as i32),
    (
        "PlanStepStatus::Completed",
        PlanStepStatus::Completed as i32,
    ),
    (
        "PlanStepStatus::InProgress",
        PlanStepStatus::InProgress as i32,
    ),
    ("PlanStepStatus::Pending", PlanStepStatus::Pending as i32),
    (
        "PluginAuthPolicy::OnInstall",
        PluginAuthPolicy::OnInstall as i32,
    ),
    ("PluginAuthPolicy::OnUse", PluginAuthPolicy::OnUse as i32),
    (
        "PluginInstallPolicy::Available",
        PluginInstallPolicy::Available as i32,
    ),
    (
        "PluginInstallPolicy::InstalledByDefault",
        PluginInstallPolicy::InstalledByDefault as i32,
    ),
    (
        "PluginInstallPolicy::NotAvailable",
        PluginInstallPolicy::NotAvailable as i32,
    ),
    ("Resolution::Default", Resolution::Default as i32),
    ("Resolution::First", Resolution::First as i32),
    ("Resolution::Preferred", Resolution::Preferred as i32),
    ("ResourceOrigin::Managed", ResourceOrigin::Managed as i32),
    ("ResourceOrigin::Plugin", ResourceOrigin::Plugin as i32),
    ("ResourceOrigin::Unknown", ResourceOrigin::Unknown as i32),
    ("ResourceOrigin::User", ResourceOrigin::User as i32),
    (
        "ResourceOrigin::Workspace",
        ResourceOrigin::Workspace as i32,
    ),
    ("SkillScope::Admin", SkillScope::Admin as i32),
    ("SkillScope::Plugin", SkillScope::Plugin as i32),
    ("SkillScope::Repo", SkillScope::Repo as i32),
    ("SkillScope::System", SkillScope::System as i32),
    ("SkillScope::User", SkillScope::User as i32),
    (
        "WorkActivity::RunningCommand",
        WorkActivity::RunningCommand as i32,
    ),
    (
        "WorkActivity::WritingFiles",
        WorkActivity::WritingFiles as i32,
    ),
    (
        "AuthorizationPurpose::ChatGpt",
        AuthorizationPurpose::ChatGpt as i32,
    ),
    (
        "AuthorizationPurpose::External",
        AuthorizationPurpose::External as i32,
    ),
    (
        "WorkspaceSelectionReason::AccessRevoked",
        WorkspaceSelectionReason::AccessRevoked as i32,
    ),
    (
        "WorkspaceSelectionReason::InvalidSelection",
        WorkspaceSelectionReason::InvalidSelection as i32,
    ),
    (
        "WorkspaceSelectionReason::NotFound",
        WorkspaceSelectionReason::NotFound as i32,
    ),
    (
        "WorkspaceSelectionReason::NotSelected",
        WorkspaceSelectionReason::NotSelected as i32,
    ),
];

fn manifest_path(relative: impl AsRef<Path>) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join(relative)
}

fn canonical_capabilities(report: &str) -> Vec<&str> {
    let owners = report
        .split_once("\n    \"owners\": [")
        .expect("canonical report contains owners")
        .1
        .split_once("\n    ],\n    \"targets\": [")
        .expect("canonical report contains targets after owners")
        .0;
    owners
        .lines()
        .filter_map(|line| {
            let quoted = line.trim().strip_prefix('"')?;
            quoted
                .strip_suffix("\",")
                .or_else(|| quoted.strip_suffix('"'))
        })
        .filter(|value| value.starts_with("common|owner="))
        .collect()
}

fn write_evidence_file(name: &str, header: &str, rows: impl IntoIterator<Item = String>) {
    let directory = manifest_path("target/cross-language-evidence");
    std::fs::create_dir_all(&directory).expect("create generated Rust evidence directory");
    let mut content = String::from(header);
    content.push('\n');
    for row in rows {
        content.push_str(&row);
        content.push('\n');
    }
    std::fs::write(directory.join(name), content).expect("write generated Rust evidence");
}

fn evidence_values() -> Vec<i32> {
    let directory = std::env::temp_dir().join(format!(
        "codex-agent-rust-enum-evidence-{}",
        std::process::id()
    ));
    std::fs::create_dir_all(&directory).expect("create enum evidence directory");
    let executable = directory.join(if cfg!(windows) {
        "codex-agent-enum-evidence.exe"
    } else {
        "codex-agent-enum-evidence"
    });
    let source = manifest_path("tests/fixtures/enum_evidence.c");
    let include = manifest_path("../../native/c-api/include");
    let compiler = std::env::var_os("CC").unwrap_or_else(|| "cc".into());
    let compile = Command::new(compiler)
        .arg("-std=c11")
        .arg("-Wall")
        .arg("-Wextra")
        .arg("-Werror")
        .arg("-I")
        .arg(include)
        .arg(source)
        .arg("-o")
        .arg(&executable)
        .output()
        .expect("run C compiler for enum evidence");
    assert!(
        compile.status.success(),
        "C-header enum evidence compilation failed:\n{}",
        String::from_utf8_lossy(&compile.stderr)
    );
    let run = Command::new(executable)
        .output()
        .expect("run C-header enum evidence");
    assert!(
        run.status.success(),
        "C-header enum evidence execution failed:\n{}",
        String::from_utf8_lossy(&run.stderr)
    );
    String::from_utf8(run.stdout)
        .expect("C-header enum evidence is UTF-8")
        .lines()
        .map(|value| value.parse().expect("C-header enum evidence is i32"))
        .collect()
}

fn exact_list<'a>(value: &'a str, label: &str) -> Vec<&'a str> {
    assert!(!value.is_empty(), "{label} must not be empty");
    let entries: Vec<_> = value.split(',').collect();
    assert!(
        entries.iter().all(|entry| !entry.is_empty()),
        "{label} contains an empty entry"
    );
    assert!(
        entries.windows(2).all(|pair| pair[0] < pair[1]),
        "{label} must be sorted and duplicate-free"
    );
    entries
}

#[test]
fn ordinary_enum_claims_match_canonical_compiler_and_header_evidence() {
    let canonical_report = std::fs::read_to_string(manifest_path(
        "../../../codex-agent-core/build/reports/cross-language-api/canonical-api.json",
    ))
    .expect("read compiler-derived canonical API report");
    let canonical = canonical_capabilities(&canonical_report);
    assert_eq!(
        canonical.len(),
        556,
        "unexpected canonical capability count"
    );
    let canonical_enums: BTreeSet<_> = canonical
        .iter()
        .copied()
        .filter(|capability| capability.contains("|kind=enum-entry|"))
        .collect();
    assert_eq!(
        canonical_enums.len(),
        110,
        "unexpected canonical enum count"
    );

    let claims = std::fs::read_to_string(manifest_path("parity/capability-claims.tsv"))
        .expect("read Rust capability claims");
    let mut lines = claims.lines();
    assert_eq!(lines.next(), Some(CLAIMS_HEADER), "exact claims header");
    let all_rows: Vec<Vec<&str>> = lines
        .map(|line| {
            assert!(!line.is_empty(), "blank claim row");
            let columns: Vec<_> = line.split('\t').collect();
            assert_eq!(columns.len(), 5, "malformed claim row: {line}");
            columns
        })
        .collect();
    assert_eq!(all_rows.len(), 556, "exact combined Rust claim count");
    assert!(
        all_rows.windows(2).all(|pair| pair[0][0] < pair[1][0]),
        "claim capability keys must be sorted and duplicate-free"
    );
    let rows: Vec<_> = all_rows
        .iter()
        .filter(|row| row[0].contains("|kind=enum-entry|"))
        .cloned()
        .collect();
    assert_eq!(rows.len(), 110, "exact Rust enum claim count");

    let claimed_capabilities: BTreeSet<_> = rows.iter().map(|row| row[0]).collect();
    assert_eq!(
        claimed_capabilities, canonical_enums,
        "claims must exactly cover the compiler-discovered enum capabilities"
    );

    let rust_values: BTreeMap<_, _> = RUST_ENUM_VALUES.iter().copied().collect();
    assert_eq!(
        rust_values.len(),
        RUST_ENUM_VALUES.len(),
        "compiled Rust public enum symbols must be unique"
    );
    let claimed_symbols: BTreeSet<_> = rows
        .iter()
        .flat_map(|row| exact_list(row[1], "publicSymbols"))
        .map(|symbol| {
            symbol
                .strip_prefix("codex_agent::")
                .expect("public Rust enum symbols use the crate-qualified path")
        })
        .collect();
    assert_eq!(
        claimed_symbols,
        rust_values.keys().copied().collect(),
        "claims must exactly name the compiled public Rust enum symbols"
    );

    let c_values = evidence_values();
    assert_eq!(c_values.len(), rows.len(), "C-header evidence count");

    let mut executed_tests = BTreeSet::new();
    let mut executed_compiler_evidence = BTreeMap::new();
    let mut executed_scenarios = BTreeSet::new();
    for (index, row) in rows.iter().enumerate() {
        let capability = row[0];
        let symbols = exact_list(row[1], "publicSymbols");
        let tests = exact_list(row[2], "executedTests");
        let compiler_evidence = exact_list(row[3], "compilerEvidenceIds");
        let scenarios = exact_list(row[4], "sharedScenarios");
        assert_eq!(symbols.len(), 1, "{capability}: one enum public symbol");
        assert_eq!(
            tests.len(),
            1,
            "{capability}: one independently executed test"
        );
        assert_eq!(
            compiler_evidence,
            [format!("c-header-enum:{index}").as_str()],
            "{capability}: stable exact compiler-evidence index"
        );
        assert_eq!(
            scenarios,
            ["value-conversion"],
            "{capability}: exact shared behavior scenario"
        );
        assert_eq!(
            rust_values[symbols[0]
                .strip_prefix("codex_agent::")
                .expect("public Rust enum symbol uses the crate-qualified path")],
            c_values[index],
            "{}: Rust discriminant must equal the exact public C-header value",
            tests[0]
        );
        assert!(
            executed_tests.insert(tests[0]),
            "{}: test ID executed more than once",
            tests[0]
        );
        assert!(
            executed_compiler_evidence
                .insert(compiler_evidence[0], symbols[0])
                .is_none(),
            "{}: compiler evidence executed more than once",
            compiler_evidence[0]
        );
        assert!(
            executed_scenarios.insert((capability, scenarios[0])),
            "{capability}: shared scenario executed more than once"
        );
    }

    assert_eq!(executed_tests.len(), rows.len(), "every test ID executed");
    assert_eq!(
        executed_compiler_evidence.len(),
        rows.len(),
        "every compiler-evidence ID executed"
    );
    assert_eq!(
        executed_scenarios.len(),
        rows.len(),
        "value conversion executed independently for every capability"
    );

    let evidence = value_behavior::verify_and_execute(&all_rows);
    assert_eq!(
        evidence.tests.len(),
        556,
        "every claim executed exactly once"
    );
    assert!(
        executed_tests
            .iter()
            .all(|test| evidence.tests.contains(*test)),
        "combined evidence omitted an executed enum test"
    );
    assert!(
        executed_compiler_evidence
            .keys()
            .all(|id| evidence.compiler.contains_key(*id)),
        "combined evidence omitted compiled enum evidence"
    );
    write_evidence_file(
        "compiler-evidence.tsv",
        "compilerEvidenceId\tpublicSymbols",
        evidence
            .compiler
            .iter()
            .map(|(evidence, symbol)| format!("{evidence}\t{symbol}")),
    );
    write_evidence_file(
        "executed-tests.tsv",
        "executedTestId\tstatus",
        evidence.tests.iter().map(|test| format!("{test}\tpassed")),
    );
}
