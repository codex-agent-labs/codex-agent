//! Ordinary canonical enum projections.

macro_rules! ordinary_enum {
    (
        $(#[$meta:meta])*
        pub enum $name:ident {
            $($(#[$variant_meta:meta])* $variant:ident = $value:expr),+ $(,)?
        }
    ) => {
        $(#[$meta])*
        #[repr(i32)]
        #[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
        pub enum $name {
            $($(#[$variant_meta])* $variant = $value),+
        }

        impl $name {
            #[allow(dead_code)]
            pub(crate) const fn from_raw(value: i32) -> Option<Self> {
                match value {
                    $($value => Some(Self::$variant),)+
                    _ => None,
                }
            }
        }
    };
}

ordinary_enum! {
    /// A decision for an approval request.
    pub enum ApprovalDecision {
        /// Accept the request.
        Accept = 0,
        /// Decline the request.
        Decline = 1,
    }
}

ordinary_enum! {
    /// Agent authentication state.
    pub enum AuthenticationStatus {
        /// The user is signed out.
        SignedOut = 0,
        /// Authentication is in progress.
        Authenticating = 1,
        /// The user is authenticated.
        Authenticated = 2,
    }
}

ordinary_enum! {
    /// A capability available to an agent.
    pub enum Capability {
        /// Search the web.
        WebSearch = 0,
    }
}

ordinary_enum! {
    /// Freshness of catalog data.
    pub enum CatalogFreshness {
        /// Data came from the live source.
        Live = 0,
        /// Data came from a fresh cache.
        FreshCache = 1,
        /// Data came from a stale cache.
        StaleCache = 2,
    }
}

ordinary_enum! {
    /// Collaboration mode for a conversation.
    pub enum CollaborationMode {
        /// Use the default collaboration mode.
        Default = 0,
        /// Use planning mode.
        Plan = 1,
    }
}

ordinary_enum! {
    /// Action taken for an elicitation request.
    pub enum ElicitationAction {
        /// Accept the request.
        Accept = 0,
        /// Decline the request.
        Decline = 1,
        /// Cancel the request.
        Cancel = 2,
    }
}

ordinary_enum! {
    /// Reason elicitation input is invalid.
    pub enum ElicitationValidationReason {
        /// A required value is missing.
        MissingRequired = 0,
        /// The field is unknown.
        UnknownField = 1,
        /// The value has an invalid type.
        InvalidType = 2,
        /// The number is not finite.
        NonFiniteNumber = 3,
        /// The number is below the minimum.
        BelowMinimum = 4,
        /// The number is above the maximum.
        AboveMaximum = 5,
        /// The number is not an integer.
        NonInteger = 6,
        /// The string has an invalid format.
        InvalidFormat = 7,
        /// The selection is invalid.
        InvalidSelection = 8,
        /// The selection contains duplicates.
        DuplicateSelection = 9,
    }
}

ordinary_enum! {
    /// Data type of a form field.
    pub enum FormFieldType {
        /// A string value.
        String = 0,
        /// A numeric value.
        Number = 1,
        /// An integer value.
        Integer = 2,
        /// A Boolean value.
        Boolean = 3,
        /// One selected option.
        SingleSelect = 4,
        /// Multiple selected options.
        MultiSelect = 5,
    }
}

ordinary_enum! {
    /// Expected format of a string form field.
    pub enum FormStringFormat {
        /// An email address.
        Email = 0,
        /// A URI.
        Uri = 1,
        /// A calendar date.
        Date = 2,
        /// A date and time.
        DateTime = 3,
    }
}

ordinary_enum! {
    /// Execution state of a hook run.
    pub enum HookRunStatus {
        /// The hook is running.
        Running = 0,
        /// The hook completed successfully.
        Completed = 1,
        /// The hook failed.
        Failed = 2,
        /// The hook was blocked.
        Blocked = 3,
        /// The hook was stopped.
        Stopped = 4,
    }
}

ordinary_enum! {
    /// Trust state of a hook.
    pub enum HookTrustStatus {
        /// The hook is centrally managed.
        Managed = 0,
        /// The hook is not trusted.
        Untrusted = 1,
        /// The hook is trusted.
        Trusted = 2,
        /// The trusted hook has been modified.
        Modified = 3,
    }
}

ordinary_enum! {
    /// Installation scope of a resource.
    pub enum InstallationScope {
        /// Install for the user.
        User = 0,
        /// Install for the workspace.
        Workspace = 1,
    }
}

ordinary_enum! {
    /// State of integration authorization.
    pub enum IntegrationAuthorizationStatus {
        /// No authorization is active.
        Idle = 0,
        /// Authorization is starting.
        Starting = 1,
        /// Authorization is awaiting completion.
        AwaitingCompletion = 2,
        /// Authorization succeeded.
        Authorized = 3,
        /// Authorization failed.
        Failed = 4,
    }
}

ordinary_enum! {
    /// Authentication state of an MCP server.
    pub enum McpAuthStatus {
        /// The state is unknown.
        Unknown = 0,
        /// Authentication is unsupported.
        Unsupported = 1,
        /// The user is not logged in.
        NotLoggedIn = 2,
        /// A bearer token is configured.
        BearerToken = 3,
        /// OAuth is configured.
        Oauth = 4,
    }
}

ordinary_enum! {
    /// Authentication mechanism of an MCP server.
    pub enum McpAuthentication {
        /// OAuth authentication.
        Oauth = 0,
        /// ChatGPT authentication.
        ChatGpt = 1,
    }
}

ordinary_enum! {
    /// Source of an MCP environment value.
    pub enum McpEnvironmentSource {
        /// The local environment.
        Local = 0,
        /// The remote environment.
        Remote = 1,
    }
}

ordinary_enum! {
    /// Approval policy for an MCP tool.
    pub enum McpToolApproval {
        /// Apply automatic approval policy.
        Auto = 0,
        /// Prompt before use.
        Prompt = 1,
        /// Prompt for writes.
        Writes = 2,
        /// Approve use.
        Approve = 3,
    }
}

ordinary_enum! {
    /// Surface on which an MCP tool is exposed.
    pub enum McpToolExposureSurface {
        /// Expose the tool in code mode.
        CodeMode = 0,
        /// Expose the tool through deferred loading.
        Deferred = 1,
        /// Expose the tool directly.
        Direct = 2,
    }
}

ordinary_enum! {
    /// Author of a message.
    pub enum MessageRole {
        /// The user.
        User = 0,
        /// The assistant.
        Assistant = 1,
    }
}

ordinary_enum! {
    /// State of a plan step.
    pub enum PlanStepStatus {
        /// The step is pending.
        Pending = 0,
        /// The step is in progress.
        InProgress = 1,
        /// The step is complete.
        Completed = 2,
    }
}

ordinary_enum! {
    /// When a plugin requests authentication.
    pub enum PluginAuthPolicy {
        /// Authenticate during installation.
        OnInstall = 0,
        /// Authenticate on first use.
        OnUse = 1,
    }
}

ordinary_enum! {
    /// Installation policy for a plugin.
    pub enum PluginInstallPolicy {
        /// The plugin is not available.
        NotAvailable = 0,
        /// The plugin is available to install.
        Available = 1,
        /// The plugin is installed by default.
        InstalledByDefault = 2,
    }
}

ordinary_enum! {
    /// How a value was resolved.
    pub enum Resolution {
        /// The preferred value was selected.
        Preferred = 0,
        /// The default value was selected.
        Default = 1,
        /// The first available value was selected.
        First = 2,
    }
}

ordinary_enum! {
    /// Origin of a resource.
    pub enum ResourceOrigin {
        /// The resource belongs to the user.
        User = 0,
        /// The resource belongs to the workspace.
        Workspace = 1,
        /// The resource came from a plugin.
        Plugin = 2,
        /// The resource is centrally managed.
        Managed = 3,
        /// The resource origin is unknown.
        Unknown = 4,
    }
}

ordinary_enum! {
    /// Scope of a skill.
    pub enum SkillScope {
        /// A system skill.
        System = 0,
        /// A user skill.
        User = 1,
        /// A repository skill.
        Repo = 2,
        /// A plugin skill.
        Plugin = 3,
        /// An administrator-provided skill.
        Admin = 4,
    }
}

ordinary_enum! {
    /// Agent's current work activity.
    pub enum WorkActivity {
        /// The agent is running a command.
        RunningCommand = 0,
        /// The agent is writing files.
        WritingFiles = 1,
    }
}

ordinary_enum! {
    /// Purpose of an authorization request.
    pub enum AuthorizationPurpose {
        /// Authorization for ChatGPT.
        ChatGpt = 0,
        /// Authorization for an external service.
        External = 1,
    }
}
