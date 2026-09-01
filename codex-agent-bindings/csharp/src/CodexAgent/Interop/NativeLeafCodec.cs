namespace CodexAgent.Interop;

internal static unsafe class NativeLeafCodec
{
    internal unsafe delegate Task<T> StringOperation<T>(NativeStringView* value);
    internal unsafe delegate Task StringOperation(NativeStringView* value);

    internal static Task<T> WithStringAsync<T>(string value, StringOperation<T> operation)
    {
        var strings = new Utf8Arena();
        var view = strings.View(value);
        try { return NativeTaskLifetime.AwaitAndDispose(operation(&view), strings); }
        catch { strings.Dispose(); throw; }
    }
    internal static Task WithStringAsync(string value, StringOperation operation)
    {
        var strings = new Utf8Arena();
        var view = strings.View(value);
        try { return NativeTaskLifetime.AwaitAndDispose(operation(&view), strings); }
        catch { strings.Dispose(); throw; }
    }
    internal static bool BooleanState(nint owner, nint snapshot)
    {
        NativeApi.ThrowIfFailed(NativeMethods.StateBooleanValue(NativeCallContext.Current, snapshot, out var value), "read Boolean state");
        return value != 0;
    }

    internal static IReadOnlyList<CodexModel> OperationModels(nint owner, nint operation)
    {
        var context = NativeCallContext.Current;
        NativeApi.ThrowIfFailed(NativeMethods.OperationModelsCount(context, operation, out var count), "read model count");
        var result = new CodexModel[Checked(count)];
        for (var i = 0; i < result.Length; i++)
        {
            NativeApi.ThrowIfFailed(NativeMethods.OperationModelAt(context, operation, (nuint)i, out var model), "read model");
            result[i] = ReadOwnedModel(context, ref model);
        }
        return Array.AsReadOnly(result);
    }

    internal static CodexModel OperationModel(nint owner, nint operation)
    {
        var context = NativeCallContext.Current;
        NativeApi.ThrowIfFailed(NativeMethods.OperationModel(context, operation, out var model), "read model");
        return ReadOwnedModel(context, ref model);
    }

    internal static string OperationString(nint owner, nint operation)
    {
        var context = NativeCallContext.Current;
        return NativeApi.CopyString((byte* buffer, nuint capacity, out nuint required) =>
            NativeMethods.OperationStringCopy(context, operation, buffer, capacity, out required));
    }

    internal static CodexServiceTier? OperationServiceTier(nint owner, nint operation)
    {
        var context = NativeCallContext.Current;
        NativeApi.ThrowIfFailed(NativeMethods.OperationHasServiceTier(context, operation, out var present), "read service-tier presence");
        if (present == 0) return null;
        NativeApi.ThrowIfFailed(NativeMethods.OperationServiceTier(context, operation, out var tier), "read service tier");
        return ReadOwnedTier(context, ref tier);
    }

    internal static IReadOnlyList<CodexConversationSummary> OperationConversationSummaries(nint owner, nint operation)
    {
        var context = NativeCallContext.Current;
        NativeApi.ThrowIfFailed(
            NativeMethods.OperationConversationSummariesCount(context, operation, out var count),
            "read conversation summary count");
        var result = new CodexConversationSummary[Checked(count)];
        for (var index = 0; index < result.Length; index++)
        {
            NativeApi.ThrowIfFailed(
                NativeMethods.OperationConversationSummaryAt(context, operation, (nuint)index, out var summary),
                "read conversation summary");
            result[index] = ReadOwnedConversationSummary(context, ref summary);
        }
        return Array.AsReadOnly(result);
    }

    internal static CodexConversationSnapshot OperationConversation(nint owner, nint operation)
    {
        var context = NativeCallContext.Current;
        NativeApi.ThrowIfFailed(
            NativeMethods.OperationConversationValue(context, operation, out var conversation),
            "read conversation value");
        return ReadOwnedConversation(context, ref conversation);
    }

    internal static IReadOnlyList<CodexMessage> ConversationMessages(nint owner, nint snapshot)
    {
        var context = NativeCallContext.Current;
        NativeApi.ThrowIfFailed(
            NativeMethods.ConversationCurrentMessagesCount(context, snapshot, out var count),
            "read current message count");
        var result = new CodexMessage[Checked(count)];
        for (var index = 0; index < result.Length; index++)
        {
            NativeApi.ThrowIfFailed(
                NativeMethods.ConversationCurrentMessagesAt(context, snapshot, (nuint)index, out var message),
                "read current message");
            result[index] = ReadOwnedMessage(context, ref message);
        }
        return Array.AsReadOnly(result);
    }

    internal static CodexTurnProgress? ActiveTurnProgress(nint owner, nint snapshot)
    {
        var context = NativeCallContext.Current;
        NativeApi.ThrowIfFailed(
            NativeMethods.ConversationActiveTurnProgressHasValue(context, snapshot, out var present),
            "read active turn-progress presence");
        if (present == 0) return null;
        NativeApi.ThrowIfFailed(
            NativeMethods.ConversationActiveTurnProgressValue(context, snapshot, out var progress),
            "read active turn progress");
        return ReadOwnedTurnProgress(context, ref progress);
    }

    internal static IReadOnlyList<CodexConnector> OperationConnectors(nint owner, nint operation)
    {
        var context = NativeCallContext.Current;
        NativeApi.ThrowIfFailed(NativeMethods.OperationConnectorsCount(context, operation, out var count), "read connector count");
        var result = new CodexConnector[Checked(count)];
        for (var i = 0; i < result.Length; i++)
        {
            NativeApi.ThrowIfFailed(NativeMethods.OperationConnectorAt(context, operation, (nuint)i, out var connector), "read connector");
            result[i] = ReadOwnedConnector(context, ref connector);
        }
        return Array.AsReadOnly(result);
    }

    internal static CodexSkill OperationSkill(nint owner, nint operation)
    {
        var context = NativeCallContext.Current;
        NativeApi.ThrowIfFailed(NativeMethods.OperationSkill(context, operation, out var value), "read skill");
        return ReadOwnedSkill(context, ref value);
    }

    internal static CodexSkillCatalog OperationSkillCatalog(nint owner, nint operation)
    {
        var context = NativeCallContext.Current;
        NativeApi.ThrowIfFailed(NativeMethods.OperationSkillCatalog(context, operation, out var catalog), "read skill catalog");
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.SkillCatalogSkillsCount(context, catalog, out var skillCount), "read skill count");
            var skills = new CodexSkill[Checked(skillCount)];
            for (var i = 0; i < skills.Length; i++)
            {
                NativeApi.ThrowIfFailed(NativeMethods.SkillCatalogSkillsAt(context, catalog, (nuint)i, out var value), "read skill");
                skills[i] = ReadOwnedSkill(context, ref value);
            }
            NativeApi.ThrowIfFailed(NativeMethods.SkillCatalogErrorsCount(context, catalog, out var errorCount), "read skill error count");
            var errors = Strings(context, catalog, errorCount, NativeMethods.SkillCatalogErrorsCopyAt);
            return new CodexSkillCatalog(skills, errors);
        }
        finally { Destroy(context, ref catalog, NativeMethods.SkillCatalogDestroy, "skill catalog"); }
    }

    internal static CodexSkillChunk OperationSkillChunk(nint owner, nint operation)
    {
        var context = NativeCallContext.Current;
        NativeApi.ThrowIfFailed(NativeMethods.OperationSkillChunk(context, operation, out var chunk), "read skill chunk");
        try
        {
            var content = Copy(context, chunk, NativeMethods.SkillChunkContentCopy);
            NativeApi.ThrowIfFailed(NativeMethods.SkillChunkNextOffset(context, chunk, out var present, out var offset), "read next skill offset");
            NativeApi.ThrowIfFailed(NativeMethods.SkillChunkTotalBytes(context, chunk, out var total), "read skill byte count");
            return new CodexSkillChunk(content, present == 0 ? null : offset, total);
        }
        finally { Destroy(context, ref chunk, NativeMethods.SkillChunkDestroy, "skill chunk"); }
    }

    internal static CodexMcpServer OperationMcpServer(nint owner, nint operation)
    {
        var context = NativeCallContext.Current;
        NativeApi.ThrowIfFailed(NativeMethods.OperationMcpServer(context, operation, out var server), "read MCP server");
        return NativeMcpValues.ReadOwnedServer(NativeCallContext.Owner, ref server);
    }

    internal static IReadOnlyList<CodexMcpServer> OperationMcpServers(nint owner, nint operation)
    {
        var context = NativeCallContext.Current;
        NativeApi.ThrowIfFailed(NativeMethods.OperationMcpServersCount(context, operation, out var count), "read MCP server count");
        var result = new CodexMcpServer[Checked(count)];
        for (var i = 0; i < result.Length; i++)
        {
            NativeApi.ThrowIfFailed(NativeMethods.OperationMcpServerAt(context, operation, (nuint)i, out var server), "read MCP server");
            result[i] = NativeMcpValues.ReadOwnedServer(NativeCallContext.Owner, ref server);
        }
        return Array.AsReadOnly(result);
    }

    internal static T WithAuthenticationMethod<T>(ServiceHandle owner, CodexAuthenticationMethod method, Func<nint,T> action) =>
        WithInput(owner, scope => scope.AuthenticationMethod(method), action);
    internal static T WithModel<T>(ServiceHandle owner, CodexModel value, Func<nint,T> action) =>
        WithInput(owner, scope => scope.Model(value), action);
    internal static T WithSkill<T>(ServiceHandle owner, CodexSkill value, Func<nint,T> action) =>
        WithInput(owner, scope => scope.Skill(value), action);

    internal static T WithHook<T>(ServiceHandle owner, CodexHook value, Func<nint,T> action) =>
        WithInput(owner,scope=>scope.Hook(value),action);
    internal static T WithPluginReference<T>(ServiceHandle owner, CodexPluginReference value, Func<nint,T> action) =>
        WithInput(owner,scope=>scope.PluginReference(value),action);
    internal static T WithIntegration<T>(ServiceHandle owner, CodexIntegration value, Func<nint,T> action) =>
        WithInput(owner,scope=>scope.Integration(value),action);
    internal static T WithElicitationResponse<T>(ServiceHandle owner, CodexElicitationResponse value, Func<nint,T> action) =>
        WithInput(owner,scope=>scope.ElicitationResponse(value),action);
    internal static T WithMcpConfiguration<T>(ServiceHandle owner, CodexMcpServerConfiguration value, Func<nint,T> action) =>
        WithInput(owner,scope=>scope.McpConfiguration(value),action);
    internal static T WithMcpServer<T>(ServiceHandle owner, CodexMcpServer value, Func<nint,T> action) =>
        WithInput(owner,scope=>scope.McpServer(value),action);
    internal static T WithConversationId<T>(ContextBoundHandle owner, CodexConversationId value, Func<nint,T> action) =>
        WithInput(owner, scope => scope.ConversationId(value), action);
    internal static T WithTurnRequest<T>(ContextBoundHandle owner, CodexTurnRequest value, Func<nint,T> action) =>
        WithInput(owner, scope => scope.TurnRequest(value), action);

    internal static CodexAuthenticationState AuthenticationState(nint owner,nint snapshot)
    {
        var context=NativeCallContext.Current;
        NativeApi.ThrowIfFailed(NativeMethods.AuthenticationStateValue(context,snapshot,out var state),"read authentication state");
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.AuthenticationStateStatus(context,state,out var status),"read authentication status");
            NativeApi.ThrowIfFailed(NativeMethods.AuthenticationStateHasPendingSignInUrl(context,state,out var hasPending),"read sign-in URL presence");
            var pending=hasPending==0?null:ReadAuthorizationUrl(context,state,NativeMethods.AuthenticationStatePendingSignInUrl);
            NativeApi.ThrowIfFailed(NativeMethods.AuthenticationStateHasDeviceVerificationUrl(context,state,out var hasDevice),"read device URL presence");
            var device=hasDevice==0?null:ReadAuthorizationUrl(context,state,NativeMethods.AuthenticationStateDeviceVerificationUrl);
            NativeApi.ThrowIfFailed(NativeMethods.AuthenticationStateHasDeviceUserCode(context,state,out var hasCode),"read device-code presence");
            NativeApi.ThrowIfFailed(NativeMethods.AuthenticationStateHasFailure(context,state,out var hasFailure),"read authentication failure presence");
            CodexFailure? failure=null;
            if(hasFailure!=0){NativeApi.ThrowIfFailed(NativeMethods.AuthenticationStateFailure(context,state,out var nativeFailure),"read authentication failure");failure=NativeApi.ReadFailure(NativeCallContext.Owner,nativeFailure);}
            return new(status,pending,device,hasCode==0?null:Copy(context,state,NativeMethods.AuthenticationStateDeviceUserCodeCopy),failure);
        }
        finally { Destroy(context,ref state,NativeMethods.AuthenticationStateDestroy,"authentication state"); }
    }
    internal static CodexIntegrationAuthorizationState IntegrationAuthorizationState(nint owner,nint snapshot)
    {
        var context=NativeCallContext.Current;
        NativeApi.ThrowIfFailed(NativeMethods.IntegrationAuthorizationStateValue(context,snapshot,out var state),"read integration authorization state");
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.IntegrationAuthorizationStateStatus(context,state,out var status),"read integration authorization status");
            CodexIntegration? target=null; var targetStatus=NativeMethods.IntegrationAuthorizationStateTarget(context,state,out var nativeTarget);
            if(targetStatus==CodexStatus.Ok) target=ReadOwnedIntegration(context,ref nativeTarget); else if(targetStatus!=CodexStatus.NotReady) NativeApi.ThrowIfFailed(targetStatus,"read authorization target");
            CodexFailure? failure=null; var failureStatus=NativeMethods.IntegrationAuthorizationStateFailure(context,state,out var nativeFailure);
            if(failureStatus==CodexStatus.Ok) failure=NativeApi.ReadFailure(NativeCallContext.Owner,nativeFailure); else if(failureStatus!=CodexStatus.NotReady) NativeApi.ThrowIfFailed(failureStatus,"read authorization failure");
            return new(status,target,failure);
        }
        finally { Destroy(context,ref state,NativeMethods.IntegrationAuthorizationStateDestroy,"integration authorization state"); }
    }

    internal static CodexIntegration? ActiveIntegration(nint owner,nint snapshot)
    {
        var context=NativeCallContext.Current;
        NativeApi.ThrowIfFailed(NativeMethods.IntegrationAuthorizationActiveHasValue(context,snapshot,out var present),"read active integration presence");
        if(present==0)return null;
        NativeApi.ThrowIfFailed(NativeMethods.IntegrationAuthorizationActiveValue(context,snapshot,out var value),"read active integration");
        return ReadOwnedIntegration(context,ref value);
    }
    internal static CodexInteractionState InteractionState(NativePendingRegistry registry,nint owner,nint snapshot)
    {
        var context=NativeCallContext.Current;NativeApi.ThrowIfFailed(NativeMethods.InteractionsStateValue(context,snapshot,out var state),"read interaction state");
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.InteractionStatePendingCount(context,state,out var count),"read pending interaction count");var pending=new CodexPendingInteraction[Checked(count)];var resolving=new List<string>();
            for(var i=0;i<pending.Length;i++){NativeApi.ThrowIfFailed(NativeMethods.InteractionStatePendingAt(context,state,(nuint)i,out var wrapped),"read pending interaction");try{NativeApi.ThrowIfFailed(NativeMethods.PendingInteractionKind(context,wrapped,out var kind),"read pending interaction kind");if(kind==0){var concrete=ExtractApproval(context,wrapped);pending[i]=ReadAndRegisterApproval(registry,context,ref concrete);}else if(kind==1){var concrete=ExtractElicitation(context,wrapped);pending[i]=ReadAndRegisterElicitation(registry,context,ref concrete);}else throw new CodexException(CodexStatus.InternalError,$"Unknown native pending kind {kind}.");NativeApi.ThrowIfFailed(NativeMethods.InteractionStateIsResolvingValue(context,state,wrapped,out var active),"read resolving interaction");if(active!=0)resolving.Add(pending[i].RequestId);}finally{Destroy(context,ref wrapped,NativeMethods.PendingInteractionDestroy,"pending interaction");}}
            NativeApi.ThrowIfFailed(NativeMethods.InteractionStateHasFailure(context,state,out var hasFailure),"read interaction failure presence");CodexFailure? failure=null;if(hasFailure!=0){NativeApi.ThrowIfFailed(NativeMethods.InteractionStateFailure(context,state,out var nativeFailure),"read interaction failure");failure=NativeApi.ReadFailure(NativeCallContext.Owner,nativeFailure);}return new(pending,resolving,failure);
        }
        finally{Destroy(context,ref state,NativeMethods.InteractionStateDestroy,"interaction state");}
    }

    internal static IReadOnlyList<CodexPendingApproval> Approvals(NativePendingRegistry registry,nint owner,nint snapshot)
    {
        var context=NativeCallContext.Current;NativeApi.ThrowIfFailed(NativeMethods.InteractionsApprovalsCount(context,snapshot,out var count),"read approval count");var result=new CodexPendingApproval[Checked(count)];for(var i=0;i<result.Length;i++){NativeApi.ThrowIfFailed(NativeMethods.InteractionsApprovalsAt(context,snapshot,(nuint)i,out var value),"read pending approval");result[i]=ReadAndRegisterApproval(registry,context,ref value);}return Array.AsReadOnly(result);
    }
    internal static IReadOnlyList<CodexPendingElicitation> Elicitations(NativePendingRegistry registry,nint owner,nint snapshot)
    {
        var context=NativeCallContext.Current;NativeApi.ThrowIfFailed(NativeMethods.InteractionsElicitationsCount(context,snapshot,out var count),"read elicitation count");var result=new CodexPendingElicitation[Checked(count)];for(var i=0;i<result.Length;i++){NativeApi.ThrowIfFailed(NativeMethods.InteractionsElicitationsAt(context,snapshot,(nuint)i,out var value),"read pending elicitation");result[i]=ReadAndRegisterElicitation(registry,context,ref value);}return Array.AsReadOnly(result);
    }
    internal static CodexHookCatalog OperationHookCatalog(nint owner,nint operation)
    {
        var context=NativeCallContext.Current;NativeApi.ThrowIfFailed(NativeMethods.OperationHookCatalog(context,operation,out var value),"read hook catalog");
        try{NativeApi.ThrowIfFailed(NativeMethods.HookCatalogHooksCount(context,value,out var count),"read hook count");var hooks=new CodexHook[Checked(count)];for(var i=0;i<hooks.Length;i++){NativeApi.ThrowIfFailed(NativeMethods.HookCatalogHooksAt(context,value,(nuint)i,out var hook),"read hook");hooks[i]=ReadOwnedHook(context,ref hook);}NativeApi.ThrowIfFailed(NativeMethods.HookCatalogWarningsCount(context,value,out var warningCount),"read hook warnings");NativeApi.ThrowIfFailed(NativeMethods.HookCatalogErrorsCount(context,value,out var errorCount),"read hook errors");return new(hooks,Strings(context,value,warningCount,NativeMethods.HookCatalogWarningsCopyAt),Strings(context,value,errorCount,NativeMethods.HookCatalogErrorsCopyAt));}
        finally{Destroy(context,ref value,NativeMethods.HookCatalogDestroy,"hook catalog");}
    }
    internal static CodexHook OperationHook(nint owner,nint operation){var context=NativeCallContext.Current;NativeApi.ThrowIfFailed(NativeMethods.OperationHook(context,operation,out var value),"read hook");return ReadOwnedHook(context,ref value);}
    internal static CodexPluginCatalog OperationPluginCatalog(nint owner,nint operation)
    {
        var context=NativeCallContext.Current;NativeApi.ThrowIfFailed(NativeMethods.OperationPluginCatalog(context,operation,out var value),"read plugin catalog");
        try{NativeApi.ThrowIfFailed(NativeMethods.PluginCatalogPluginsCount(context,value,out var count),"read plugin count");var plugins=new CodexPluginSummary[Checked(count)];for(var i=0;i<plugins.Length;i++){NativeApi.ThrowIfFailed(NativeMethods.PluginCatalogPluginsAt(context,value,(nuint)i,out var item),"read plugin summary");plugins[i]=ReadOwnedPluginSummary(context,ref item);}NativeApi.ThrowIfFailed(NativeMethods.PluginCatalogErrorsCount(context,value,out var errorCount),"read plugin error count");NativeApi.ThrowIfFailed(NativeMethods.PluginCatalogFreshness(context,value,out var freshness),"read plugin freshness");return new(plugins,Strings(context,value,errorCount,NativeMethods.PluginCatalogErrorsCopyAt),freshness);}
        finally{Destroy(context,ref value,NativeMethods.PluginCatalogDestroy,"plugin catalog");}
    }
    internal static CodexPluginDetail OperationPluginDetail(nint owner,nint operation)
    {
        var context=NativeCallContext.Current;NativeApi.ThrowIfFailed(NativeMethods.OperationPluginDetail(context,operation,out var value),"read plugin detail");
        try{NativeApi.ThrowIfFailed(NativeMethods.PluginDetailSummary(context,value,out var summary),"read plugin summary");NativeApi.ThrowIfFailed(NativeMethods.PluginDetailSkillsCount(context,value,out var skillCount),"read plugin skill count");var skills=new CodexPluginSkill[Checked(skillCount)];for(var i=0;i<skills.Length;i++){NativeApi.ThrowIfFailed(NativeMethods.PluginDetailSkillsAt(context,value,(nuint)i,out var item),"read plugin skill");skills[i]=ReadOwnedPluginSkill(context,ref item);}NativeApi.ThrowIfFailed(NativeMethods.PluginDetailConnectorsCount(context,value,out var connectorCount),"read plugin connector count");var connectors=new CodexConnector[Checked(connectorCount)];for(var i=0;i<connectors.Length;i++){NativeApi.ThrowIfFailed(NativeMethods.PluginDetailConnectorsAt(context,value,(nuint)i,out var item),"read plugin connector");connectors[i]=ReadOwnedConnector(context,ref item);}NativeApi.ThrowIfFailed(NativeMethods.PluginDetailMcpServersCount(context,value,out var mcpCount),"read plugin MCP count");NativeApi.ThrowIfFailed(NativeMethods.PluginDetailHookCount(context,value,out var hooks),"read plugin hook count");return new(ReadOwnedPluginSummary(context,ref summary),Copy(context,value,NativeMethods.PluginDetailDescriptionCopy),skills,connectors,Strings(context,value,mcpCount,NativeMethods.PluginDetailMcpServersCopyAt),hooks);}
        finally{Destroy(context,ref value,NativeMethods.PluginDetailDestroy,"plugin detail");}
    }
    internal static CodexPluginInstallResult OperationPluginInstallResult(nint owner,nint operation)
    {
        var context=NativeCallContext.Current;NativeApi.ThrowIfFailed(NativeMethods.OperationPluginInstallResult(context,operation,out var value),"read plugin installation result");
        try{NativeApi.ThrowIfFailed(NativeMethods.PluginInstallResultAuthPolicy(context,value,out var policy),"read plugin auth policy");NativeApi.ThrowIfFailed(NativeMethods.PluginInstallResultConnectorsCount(context,value,out var count),"read plugin connector count");var connectors=new CodexConnector[Checked(count)];for(var i=0;i<connectors.Length;i++){NativeApi.ThrowIfFailed(NativeMethods.PluginInstallResultConnectorsAt(context,value,(nuint)i,out var item),"read plugin connector");connectors[i]=ReadOwnedConnector(context,ref item);}NativeApi.ThrowIfFailed(NativeMethods.PluginInstallResultHasMessage(context,value,out var present),"read plugin message presence");return new(policy,connectors,present==0?null:Copy(context,value,NativeMethods.PluginInstallResultMessageCopy));}
        finally{Destroy(context,ref value,NativeMethods.PluginInstallResultDestroy,"plugin installation result");}
    }

    private static T WithInput<T>(ContextBoundHandle owner, Func<InputScope,nint> create, Func<nint,T> action)
    {
        using var scope = new InputScope(owner.Context);
        using var call = NativeCallContext.Enter(owner.Context);
        return action(create(scope));
    }

    private static CodexModel ReadOwnedModel(nint context, ref nint model)
    {
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.ModelSupportedEffortsCount(context, model, out var effortCount), "read model efforts");
            NativeApi.ThrowIfFailed(NativeMethods.ModelServiceTiersCount(context, model, out var tierCount), "read model tiers");
            var tiers = new CodexServiceTier[Checked(tierCount)];
            for (var i=0;i<tiers.Length;i++) { NativeApi.ThrowIfFailed(NativeMethods.ModelServiceTierAt(context, model, (nuint)i, out var tier), "read model tier"); tiers[i]=ReadOwnedTier(context,ref tier); }
            NativeApi.ThrowIfFailed(NativeMethods.ModelIsDefault(context,model,out var isDefault),"read default model");
            NativeApi.ThrowIfFailed(NativeMethods.ModelHasDefaultServiceTier(context,model,out var hasDefaultTier),"read default tier presence");
            return new CodexModel(Copy(context,model,NativeMethods.ModelIdCopy),Copy(context,model,NativeMethods.ModelDisplayNameCopy),Copy(context,model,NativeMethods.ModelDescriptionCopy),Strings(context,model,effortCount,NativeMethods.ModelSupportedEffortCopyAt),Copy(context,model,NativeMethods.ModelDefaultEffortCopy),isDefault!=0,tiers,hasDefaultTier==0?null:Copy(context,model,NativeMethods.ModelDefaultServiceTierCopy));
        }
        finally { Destroy(context,ref model,NativeMethods.ModelDestroy,"model"); }
    }

    private static CodexServiceTier ReadOwnedTier(nint context,ref nint value)
    {
        try { return new(Copy(context,value,NativeMethods.ServiceTierIdCopy),Copy(context,value,NativeMethods.ServiceTierNameCopy),Copy(context,value,NativeMethods.ServiceTierDescriptionCopy)); }
        finally { Destroy(context,ref value,NativeMethods.ServiceTierDestroy,"service tier"); }
    }

    private delegate CodexStatus OwnedGetter(nint c,nint value,out nint owned);
    private static CodexAuthorizationUrl ReadAuthorizationUrl(nint context,nint parent,OwnedGetter getter)
    {
        NativeApi.ThrowIfFailed(getter(context,parent,out var url),"read authorization URL");
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.AuthorizationUrlPurpose(context,url,out var purpose),"read authorization purpose");
            return CodexAuthorizationUrl.FromNative(Copy(context,url,NativeMethods.AuthorizationUrlValueCopy),purpose);
        }
        finally { Destroy(context,ref url,NativeMethods.AuthorizationUrlDestroy,"authorization URL"); }
    }

    private static CodexConnector ReadOwnedConnector(nint context,ref nint value)
    {
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.ConnectorHasInstallUrl(context,value,out var hasUrl),"read connector URL presence");
            NativeApi.ThrowIfFailed(NativeMethods.ConnectorIsAccessible(context,value,out var accessible),"read connector access");
            NativeApi.ThrowIfFailed(NativeMethods.ConnectorIsEnabled(context,value,out var enabled),"read connector enabled");
            NativeApi.ThrowIfFailed(NativeMethods.ConnectorPluginNamesCount(context,value,out var count),"read connector plugin count");
            return new(Copy(context,value,NativeMethods.ConnectorIdCopy),Copy(context,value,NativeMethods.ConnectorNameCopy),Copy(context,value,NativeMethods.ConnectorDescriptionCopy),hasUrl==0?null:Copy(context,value,NativeMethods.ConnectorInstallUrlCopy),accessible!=0,enabled!=0,Strings(context,value,count,NativeMethods.ConnectorPluginNamesCopyAt));
        }
        finally { Destroy(context,ref value,NativeMethods.ConnectorDestroy,"connector"); }
    }

    private static CodexIntegration ReadOwnedIntegration(nint context,ref nint value)
    {
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.IntegrationKind(context,value,out var kind),"read integration kind");
            if(kind==0)
            {
                NativeApi.ThrowIfFailed(NativeMethods.IntegrationConnector(context,value,out var concrete),"read connector integration");
                try { NativeApi.ThrowIfFailed(NativeMethods.IntegrationConnectorConnector(context,concrete,out var connector),"read integrated connector"); return new CodexIntegration.Connector(ReadOwnedConnector(context,ref connector)); }
                finally { Destroy(context,ref concrete,NativeMethods.IntegrationConnectorDestroy,"connector integration"); }
            }
            if(kind==1)
            {
                NativeApi.ThrowIfFailed(NativeMethods.IntegrationMcpServer(context,value,out var concrete),"read MCP integration");
                try { NativeApi.ThrowIfFailed(NativeMethods.IntegrationMcpServerServer(context,concrete,out var server),"read integrated MCP server"); return new CodexIntegration.McpServer(NativeMcpValues.ReadOwnedServer(NativeCallContext.Owner,ref server)); }
                finally { Destroy(context,ref concrete,NativeMethods.IntegrationMcpServerDestroy,"MCP integration"); }
            }
            throw new CodexException(CodexStatus.InternalError,$"Unknown native integration kind {kind}.");
        }
        finally { Destroy(context,ref value,NativeMethods.IntegrationDestroy,"integration"); }
    }

    private static CodexPluginReference ReadOwnedPluginReference(nint context,ref nint value)
    {
        try{NativeApi.ThrowIfFailed(NativeMethods.PluginReferenceHasMarketplacePath(context,value,out var hasPath),"read plugin path presence");NativeApi.ThrowIfFailed(NativeMethods.PluginReferenceHasRemotePluginId(context,value,out var hasRemote),"read remote plugin ID presence");return new(Copy(context,value,NativeMethods.PluginReferenceIdCopy),Copy(context,value,NativeMethods.PluginReferenceNameCopy),Copy(context,value,NativeMethods.PluginReferenceMarketplaceNameCopy),hasPath==0?null:Copy(context,value,NativeMethods.PluginReferenceMarketplacePathCopy),hasRemote==0?null:Copy(context,value,NativeMethods.PluginReferenceRemotePluginIdCopy));}
        finally{Destroy(context,ref value,NativeMethods.PluginReferenceDestroy,"plugin reference");}
    }

    private static CodexPluginSkill ReadOwnedPluginSkill(nint context,ref nint value)
    {
        try{NativeApi.ThrowIfFailed(NativeMethods.PluginSkillIsEnabled(context,value,out var enabled),"read plugin skill enabled");NativeApi.ThrowIfFailed(NativeMethods.PluginSkillHasPath(context,value,out var hasPath),"read plugin skill path presence");return new(Copy(context,value,NativeMethods.PluginSkillNameCopy),Copy(context,value,NativeMethods.PluginSkillDescriptionCopy),enabled!=0,hasPath==0?null:Copy(context,value,NativeMethods.PluginSkillPathCopy));}
        finally{Destroy(context,ref value,NativeMethods.PluginSkillDestroy,"plugin skill");}
    }

    private static CodexPluginSummary ReadOwnedPluginSummary(nint context,ref nint value)
    {
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.PluginSummaryReference(context,value,out var reference),"read plugin reference");NativeApi.ThrowIfFailed(NativeMethods.PluginSummaryIsInstalled(context,value,out var installed),"read plugin installed");NativeApi.ThrowIfFailed(NativeMethods.PluginSummaryIsEnabled(context,value,out var enabled),"read plugin enabled");NativeApi.ThrowIfFailed(NativeMethods.PluginSummaryInstallPolicy(context,value,out var installPolicy),"read plugin install policy");NativeApi.ThrowIfFailed(NativeMethods.PluginSummaryAuthPolicy(context,value,out var authPolicy),"read plugin auth policy");NativeApi.ThrowIfFailed(NativeMethods.PluginSummaryIsAvailable(context,value,out var available),"read plugin availability");NativeApi.ThrowIfFailed(NativeMethods.PluginSummaryCapabilitiesCount(context,value,out var capabilityCount),"read plugin capabilities");
            var brand=Optional(context,value,NativeMethods.PluginSummaryHasBrandColor,NativeMethods.PluginSummaryBrandColorCopy);var privacy=Optional(context,value,NativeMethods.PluginSummaryHasPrivacyPolicyUrl,NativeMethods.PluginSummaryPrivacyPolicyUrlCopy);var terms=Optional(context,value,NativeMethods.PluginSummaryHasTermsOfServiceUrl,NativeMethods.PluginSummaryTermsOfServiceUrlCopy);var website=Optional(context,value,NativeMethods.PluginSummaryHasWebsiteUrl,NativeMethods.PluginSummaryWebsiteUrlCopy);
            return new(ReadOwnedPluginReference(context,ref reference),Copy(context,value,NativeMethods.PluginSummaryDisplayNameCopy),Copy(context,value,NativeMethods.PluginSummaryDescriptionCopy),installed!=0,enabled!=0,installPolicy,authPolicy,available!=0,Strings(context,value,capabilityCount,NativeMethods.PluginSummaryCapabilitiesCopyAt),brand,privacy,terms,website);
        }
        finally{Destroy(context,ref value,NativeMethods.PluginSummaryDestroy,"plugin summary");}
    }

    private static CodexHookHandler ReadOwnedHookHandler(nint context,ref nint value)
    {
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.HookHandlerKind(context,value,out var kind),"read hook handler kind");
            if(kind==0){NativeApi.ThrowIfFailed(NativeMethods.HookHandlerAgent(context,value,out var concrete),"read agent handler");Destroy(context,ref concrete,NativeMethods.HookHandlerAgentDestroy,"agent handler");return CodexHookHandler.Agent.Instance;}
            if(kind==1){NativeApi.ThrowIfFailed(NativeMethods.HookHandlerCommand(context,value,out var concrete),"read command handler");try{NativeApi.ThrowIfFailed(NativeMethods.HookHandlerCommandIsAsync(context,concrete,out var isAsync),"read command async flag");return new CodexHookHandler.Command(Copy(context,concrete,NativeMethods.HookHandlerCommandCommandCopy),isAsync!=0);}finally{Destroy(context,ref concrete,NativeMethods.HookHandlerCommandDestroy,"command handler");}}
            if(kind==2){NativeApi.ThrowIfFailed(NativeMethods.HookHandlerMcpTool(context,value,out var concrete),"read MCP handler");try{return new CodexHookHandler.McpTool(Copy(context,concrete,NativeMethods.HookHandlerMcpToolServerCopy),Copy(context,concrete,NativeMethods.HookHandlerMcpToolToolCopy));}finally{Destroy(context,ref concrete,NativeMethods.HookHandlerMcpToolDestroy,"MCP handler");}}
            if(kind==3){NativeApi.ThrowIfFailed(NativeMethods.HookHandlerPrompt(context,value,out var concrete),"read prompt handler");Destroy(context,ref concrete,NativeMethods.HookHandlerPromptDestroy,"prompt handler");return CodexHookHandler.Prompt.Instance;}
            throw new CodexException(CodexStatus.InternalError,$"Unknown native hook handler kind {kind}.");
        }
        finally{Destroy(context,ref value,NativeMethods.HookHandlerDestroy,"hook handler");}
    }

    private static CodexHook ReadOwnedHook(nint context,ref nint value)
    {
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.HookIsEnabled(context,value,out var enabled),"read hook enabled");NativeApi.ThrowIfFailed(NativeMethods.HookHandler(context,value,out var handler),"read hook handler");NativeApi.ThrowIfFailed(NativeMethods.HookIsManaged(context,value,out var managed),"read managed hook");NativeApi.ThrowIfFailed(NativeMethods.HookTimeoutSeconds(context,value,out var timeout),"read hook timeout");NativeApi.ThrowIfFailed(NativeMethods.HookTrustStatus(context,value,out var trust),"read hook trust");NativeApi.ThrowIfFailed(NativeMethods.HookOrigin(context,value,out var origin),"read hook origin");NativeApi.ThrowIfFailed(NativeMethods.HookCanUninstall(context,value,out var canUninstall),"read hook removal");
            return new(Copy(context,value,NativeMethods.HookKeyCopy),Copy(context,value,NativeMethods.HookCurrentHashCopy),enabled!=0,Copy(context,value,NativeMethods.HookEventNameCopy),ReadOwnedHookHandler(context,ref handler),managed!=0,Copy(context,value,NativeMethods.HookSourceCopy),Copy(context,value,NativeMethods.HookSourcePathCopy),timeout,trust,Optional(context,value,NativeMethods.HookHasMatcher,NativeMethods.HookMatcherCopy),Optional(context,value,NativeMethods.HookHasPluginId,NativeMethods.HookPluginIdCopy),Optional(context,value,NativeMethods.HookHasStatusMessage,NativeMethods.HookStatusMessageCopy),origin,canUninstall!=0);
        }
        finally{Destroy(context,ref value,NativeMethods.HookDestroy,"hook");}
    }

    private static CodexConversationSummary ReadOwnedConversationSummary(nint context, ref nint value)
    {
        try
        {
            NativeApi.ThrowIfFailed(
                NativeMethods.ConversationSummaryConversationId(context, value, out var id),
                "read conversation-summary ID");
            NativeApi.ThrowIfFailed(
                NativeMethods.ConversationSummaryUpdatedAtEpochSeconds(context, value, out var updated),
                "read conversation-summary timestamp");
            return new(
                ReadOwnedConversationId(context, ref id),
                Copy(context, value, NativeMethods.ConversationSummaryTitleCopy),
                updated);
        }
        finally { Destroy(context, ref value, NativeMethods.ConversationSummaryDestroy, "conversation summary"); }
    }

    private static CodexConversationSnapshot ReadOwnedConversation(nint context, ref nint value)
    {
        try
        {
            NativeApi.ThrowIfFailed(
                NativeMethods.ConversationValueSummary(context, value, out var summary),
                "read conversation summary");
            NativeApi.ThrowIfFailed(
                NativeMethods.ConversationValueMessagesCount(context, value, out var count),
                "read conversation message count");
            var messages = new CodexMessage[Checked(count)];
            for (var index = 0; index < messages.Length; index++)
            {
                NativeApi.ThrowIfFailed(
                    NativeMethods.ConversationValueMessageAt(context, value, (nuint)index, out var message),
                    "read conversation message");
                messages[index] = ReadOwnedMessage(context, ref message);
            }
            return new(ReadOwnedConversationSummary(context, ref summary), messages);
        }
        finally { Destroy(context, ref value, NativeMethods.ConversationValueDestroy, "conversation value"); }
    }

    private static CodexMessage ReadOwnedMessage(nint context, ref nint value)
    {
        try
        {
            var messageValue = value;
            NativeApi.ThrowIfFailed(NativeMethods.MessageHasClientMessageId(context, value, out var hasClientId), "read client-message ID presence");
            NativeApi.ThrowIfFailed(NativeMethods.MessageRole(context, value, out var role), "read message role");
            NativeApi.ThrowIfFailed(NativeMethods.MessageCollaborationMode(context, value, out var collaboration), "read collaboration mode");
            NativeApi.ThrowIfFailed(NativeMethods.MessageHasReasoning(context, value, out var hasReasoning), "read message reasoning presence");
            NativeApi.ThrowIfFailed(NativeMethods.MessageHasPlan(context, value, out var hasPlan), "read message plan presence");
            NativeApi.ThrowIfFailed(NativeMethods.MessageHasShellCommand(context, value, out var hasCommand), "read shell-command presence");
            NativeApi.ThrowIfFailed(NativeMethods.MessageExitCode(context, value, out var hasExitCode, out var exitCode), "read shell exit code");
            NativeApi.ThrowIfFailed(NativeMethods.MessageCapabilitiesCount(context, value, out _), "read message capability count");
            var capabilities = Enum.GetValues<CodexCapability>().Where(capability =>
            {
                NativeApi.ThrowIfFailed(NativeMethods.MessageHasCapability(context, messageValue, capability, out var present), "read message capability");
                return present != 0;
            }).ToArray();
            NativeApi.ThrowIfFailed(NativeMethods.MessageInvocationsCount(context, value, out var invocationCount), "read message invocation count");
            var invocations = new CodexInvocation[Checked(invocationCount)];
            for (var index = 0; index < invocations.Length; index++)
            {
                NativeApi.ThrowIfFailed(NativeMethods.MessageInvocationAt(context, value, (nuint)index, out var invocation), "read message invocation");
                invocations[index] = ReadOwnedInvocation(context, ref invocation);
            }
            return new(
                Copy(context, value, NativeMethods.MessageIdCopy),
                hasClientId == 0 ? null : Copy(context, value, NativeMethods.MessageClientMessageIdCopy),
                role,
                Copy(context, value, NativeMethods.MessageTextCopy),
                collaboration,
                hasReasoning == 0 ? null : Copy(context, value, NativeMethods.MessageReasoningCopy),
                hasPlan == 0 ? null : Copy(context, value, NativeMethods.MessagePlanCopy),
                hasCommand == 0 ? null : Copy(context, value, NativeMethods.MessageShellCommandCopy),
                hasExitCode == 0 ? null : exitCode,
                capabilities,
                invocations);
        }
        finally { Destroy(context, ref value, NativeMethods.MessageDestroy, "message"); }
    }

    private static CodexInvocation ReadOwnedInvocation(nint context, ref nint value)
    {
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.InvocationKind(context, value, out var kind), "read invocation kind");
            if (kind == 0)
            {
                NativeApi.ThrowIfFailed(NativeMethods.InvocationPlugin(context, value, out var plugin), "read plugin invocation");
                try { return new CodexInvocation.Plugin(Copy(context, plugin, NativeMethods.InvocationPluginNameCopy), Copy(context, plugin, NativeMethods.InvocationPluginUriCopy)); }
                finally { Destroy(context, ref plugin, NativeMethods.InvocationPluginDestroy, "plugin invocation"); }
            }
            if (kind == 1)
            {
                NativeApi.ThrowIfFailed(NativeMethods.InvocationSkill(context, value, out var skill), "read skill invocation");
                try { return new CodexInvocation.Skill(Copy(context, skill, NativeMethods.InvocationSkillNameCopy), Copy(context, skill, NativeMethods.InvocationSkillPathCopy)); }
                finally { Destroy(context, ref skill, NativeMethods.InvocationSkillDestroy, "skill invocation"); }
            }
            throw new CodexException(CodexStatus.InternalError, $"Unknown native invocation kind {kind}.");
        }
        finally { Destroy(context, ref value, NativeMethods.InvocationDestroy, "invocation"); }
    }

    private static CodexTurnProgress ReadOwnedTurnProgress(nint context, ref nint value)
    {
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.TurnProgressHasPlanProgress(context, value, out var hasPlanProgress), "read plan-progress presence");
            NativeApi.ThrowIfFailed(NativeMethods.TurnProgressShellExitCode(context, value, out var hasExitCode, out var exitCode), "read progress exit code");
            NativeApi.ThrowIfFailed(NativeMethods.TurnProgressWorkActivity(context, value, out var hasWorkActivity, out var workActivity), "read work activity");
            NativeApi.ThrowIfFailed(NativeMethods.TurnProgressHookActivitiesCount(context, value, out var hookCount), "read hook-activity count");
            NativeApi.ThrowIfFailed(NativeMethods.TurnProgressIsTruncated(context, value, out var truncated), "read truncation flag");
            CodexPlanProgress? planProgress = null;
            if (hasPlanProgress != 0)
            {
                NativeApi.ThrowIfFailed(NativeMethods.TurnProgressPlanProgress(context, value, out var nativePlanProgress), "read plan progress");
                planProgress = ReadOwnedPlanProgress(context, ref nativePlanProgress);
            }
            var hookActivities = new CodexHookActivity[Checked(hookCount)];
            for (var index = 0; index < hookActivities.Length; index++)
            {
                NativeApi.ThrowIfFailed(NativeMethods.TurnProgressHookActivityAt(context, value, (nuint)index, out var activity), "read hook activity");
                hookActivities[index] = ReadOwnedHookActivity(context, ref activity);
            }
            return new(
                Copy(context, value, NativeMethods.TurnProgressTextCopy),
                Copy(context, value, NativeMethods.TurnProgressCommentaryCopy),
                Copy(context, value, NativeMethods.TurnProgressReasoningCopy),
                Copy(context, value, NativeMethods.TurnProgressPlanCopy),
                planProgress,
                Copy(context, value, NativeMethods.TurnProgressShellOutputCopy),
                hasExitCode == 0 ? null : exitCode,
                hasWorkActivity == 0 ? null : workActivity,
                hookActivities,
                truncated != 0);
        }
        finally { Destroy(context, ref value, NativeMethods.TurnProgressDestroy, "turn progress"); }
    }

    private static CodexPlanProgress ReadOwnedPlanProgress(nint context, ref nint value)
    {
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.PlanProgressHasExplanation(context, value, out var hasExplanation), "read plan explanation presence");
            NativeApi.ThrowIfFailed(NativeMethods.PlanProgressStepsCount(context, value, out var count), "read plan-step count");
            var steps = new CodexPlanStep[Checked(count)];
            for (var index = 0; index < steps.Length; index++)
            {
                NativeApi.ThrowIfFailed(NativeMethods.PlanProgressStepAt(context, value, (nuint)index, out var step), "read plan step");
                steps[index] = ReadOwnedPlanStep(context, ref step);
            }
            return new(hasExplanation == 0 ? null : Copy(context, value, NativeMethods.PlanProgressExplanationCopy), steps);
        }
        finally { Destroy(context, ref value, NativeMethods.PlanProgressDestroy, "plan progress"); }
    }

    private static CodexPlanStep ReadOwnedPlanStep(nint context, ref nint value)
    {
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.PlanStepStatus(context, value, out var status), "read plan-step status");
            return new(Copy(context, value, NativeMethods.PlanStepTextCopy), status);
        }
        finally { Destroy(context, ref value, NativeMethods.PlanStepDestroy, "plan step"); }
    }

    private static CodexHookActivity ReadOwnedHookActivity(nint context, ref nint value)
    {
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.HookActivityStatus(context, value, out var status), "read hook status");
            NativeApi.ThrowIfFailed(NativeMethods.HookActivityHasStatusMessage(context, value, out var hasMessage), "read hook status-message presence");
            NativeApi.ThrowIfFailed(NativeMethods.HookActivityDetailsCount(context, value, out var count), "read hook-detail count");
            return new(
                Copy(context, value, NativeMethods.HookActivityIdCopy),
                Copy(context, value, NativeMethods.HookActivityEventNameCopy),
                Copy(context, value, NativeMethods.HookActivityHandlerTypeCopy),
                status,
                hasMessage == 0 ? null : Copy(context, value, NativeMethods.HookActivityStatusMessageCopy),
                Strings(context, value, count, NativeMethods.HookActivityDetailCopyAt));
        }
        finally { Destroy(context, ref value, NativeMethods.HookActivityDestroy, "hook activity"); }
    }

    private static CodexConversationId ReadOwnedConversationId(nint context,ref nint value)
    {
        try{return new(Copy(context,value,NativeMethods.ConversationIdValueCopy));}
        finally{Destroy(context,ref value,NativeMethods.ConversationIdDestroy,"conversation ID");}
    }

    private static CodexFormOption ReadOwnedFormOption(nint context,ref nint value)
    {
        try{return new(Copy(context,value,NativeMethods.FormOptionValueCopy),Copy(context,value,NativeMethods.FormOptionTitleCopy),Optional(context,value,NativeMethods.FormOptionHasDescription,NativeMethods.FormOptionDescriptionCopy));}
        finally{Destroy(context,ref value,NativeMethods.FormOptionDestroy,"form option");}
    }

    private static CodexFormValue ReadOwnedFormValue(nint context,ref nint value)
    {
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.FormValueKind(context,value,out var kind),"read form value kind");nint concrete=0;
            if(kind==0){NativeApi.ThrowIfFailed(NativeMethods.FormValueBoolean(context,value,ref concrete),"read Boolean form value");try{NativeApi.ThrowIfFailed(NativeMethods.FormBooleanValue(context,concrete,out var item),"read Boolean form value");return new CodexFormValue.BooleanValue(item!=0);}finally{Destroy(context,ref concrete,NativeMethods.FormBooleanDestroy,"Boolean form value");}}
            if(kind==1){NativeApi.ThrowIfFailed(NativeMethods.FormValueNumber(context,value,ref concrete),"read number form value");try{NativeApi.ThrowIfFailed(NativeMethods.FormNumberValue(context,concrete,out var item),"read number form value");return new CodexFormValue.Number(item);}finally{Destroy(context,ref concrete,NativeMethods.FormNumberDestroy,"number form value");}}
            if(kind==2){NativeApi.ThrowIfFailed(NativeMethods.FormValueText(context,value,ref concrete),"read text form value");try{return new CodexFormValue.Text(Copy(context,concrete,NativeMethods.FormTextValueCopy));}finally{Destroy(context,ref concrete,NativeMethods.FormTextDestroy,"text form value");}}
            if(kind==3){NativeApi.ThrowIfFailed(NativeMethods.FormValueTextList(context,value,ref concrete),"read text-list form value");try{NativeApi.ThrowIfFailed(NativeMethods.FormTextListCount(context,concrete,out var count),"read text-list count");return new CodexFormValue.TextList(Strings(context,concrete,count,NativeMethods.FormTextListCopyAt));}finally{Destroy(context,ref concrete,NativeMethods.FormTextListDestroy,"text-list form value");}}
            throw new CodexException(CodexStatus.InternalError,$"Unknown native form-value kind {kind}.");
        }
        finally{Destroy(context,ref value,NativeMethods.FormValueDestroy,"form value");}
    }

    private static CodexFormField ReadOwnedFormField(nint context,ref nint value)
    {
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.FormFieldType(context,value,out var type),"read form field type");NativeApi.ThrowIfFailed(NativeMethods.FormFieldIsRequired(context,value,out var required),"read required form field");NativeApi.ThrowIfFailed(NativeMethods.FormFieldIsSecret(context,value,out var secret),"read secret form field");NativeApi.ThrowIfFailed(NativeMethods.FormFieldFormat(context,value,out var hasFormat,out var format),"read form field format");NativeApi.ThrowIfFailed(NativeMethods.FormFieldHasDefaultValue(context,value,out var hasDefault),"read form default presence");
            CodexFormValue? defaultValue=null;if(hasDefault!=0){NativeApi.ThrowIfFailed(NativeMethods.FormFieldDefaultValue(context,value,out var nativeDefault),"read form default");defaultValue=ReadOwnedFormValue(context,ref nativeDefault);}
            NativeApi.ThrowIfFailed(NativeMethods.FormFieldOptionsCount(context,value,out var optionCount),"read form option count");var options=new CodexFormOption[Checked(optionCount)];for(var i=0;i<options.Length;i++){NativeApi.ThrowIfFailed(NativeMethods.FormFieldOptionAt(context,value,(nuint)i,out var option),"read form option");options[i]=ReadOwnedFormOption(context,ref option);}
            NativeApi.ThrowIfFailed(NativeMethods.FormFieldMinimum(context,value,out var hasMin,out var min),"read form minimum");NativeApi.ThrowIfFailed(NativeMethods.FormFieldMaximum(context,value,out var hasMax,out var max),"read form maximum");NativeApi.ThrowIfFailed(NativeMethods.FormFieldMinimumLength(context,value,out var hasMinLength,out var minLength),"read minimum length");NativeApi.ThrowIfFailed(NativeMethods.FormFieldMaximumLength(context,value,out var hasMaxLength,out var maxLength),"read maximum length");NativeApi.ThrowIfFailed(NativeMethods.FormFieldMinimumSelections(context,value,out var hasMinSelections,out var minSelections),"read minimum selections");NativeApi.ThrowIfFailed(NativeMethods.FormFieldMaximumSelections(context,value,out var hasMaxSelections,out var maxSelections),"read maximum selections");NativeApi.ThrowIfFailed(NativeMethods.FormFieldAllowsOther(context,value,out var allowsOther),"read allows-other flag");
            return new(Copy(context,value,NativeMethods.FormFieldNameCopy),Copy(context,value,NativeMethods.FormFieldTitleCopy),type,Optional(context,value,NativeMethods.FormFieldHasDescription,NativeMethods.FormFieldDescriptionCopy),required!=0,options,defaultValue,hasMin==0?null:min,hasMax==0?null:max,hasFormat==0?null:format,hasMinLength==0?null:minLength,hasMaxLength==0?null:maxLength,hasMinSelections==0?null:minSelections,hasMaxSelections==0?null:maxSelections,allowsOther!=0,secret!=0);
        }
        finally{Destroy(context,ref value,NativeMethods.FormFieldDestroy,"form field");}
    }

    private static CodexElicitation ReadOwnedElicitation(nint context,ref nint value)
    {
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.ElicitationConversationId(context,value,out var id),"read elicitation conversation ID");NativeApi.ThrowIfFailed(NativeMethods.ElicitationHasForm(context,value,out var hasForm),"read elicitation form presence");IReadOnlyList<CodexFormField>? form=null;if(hasForm!=0){NativeApi.ThrowIfFailed(NativeMethods.ElicitationFormCount(context,value,out var count),"read elicitation form count");var fields=new CodexFormField[Checked(count)];for(var i=0;i<fields.Length;i++){NativeApi.ThrowIfFailed(NativeMethods.ElicitationFormAt(context,value,(nuint)i,out var field),"read elicitation form field");fields[i]=ReadOwnedFormField(context,ref field);}form=Array.AsReadOnly(fields);}NativeApi.ThrowIfFailed(NativeMethods.ElicitationHasUrl(context,value,out var hasUrl),"read elicitation URL presence");return new(Copy(context,value,NativeMethods.ElicitationRequestIdCopy),Copy(context,value,NativeMethods.ElicitationServerNameCopy),ReadOwnedConversationId(context,ref id),Copy(context,value,NativeMethods.ElicitationMessageCopy),form,hasUrl==0?null:Copy(context,value,NativeMethods.ElicitationUrlCopy));
        }
        finally{Destroy(context,ref value,NativeMethods.ElicitationDestroy,"elicitation");}
    }

    private static nint ExtractApproval(nint context,nint wrapped){nint value=0;NativeApi.ThrowIfFailed(NativeMethods.PendingInteractionApproval(context,wrapped,ref value),"read pending approval");return value;}
    private static nint ExtractElicitation(nint context,nint wrapped){nint value=0;NativeApi.ThrowIfFailed(NativeMethods.PendingInteractionElicitation(context,wrapped,ref value),"read pending elicitation");return value;}
    private static CodexPendingApproval ReadAndRegisterApproval(NativePendingRegistry registry,nint context,ref nint value)
    {
        try{var id=ExtractApprovalConversationId(context,value);var result=new CodexPendingApproval(Copy(context,value,NativeMethods.PendingApprovalRequestIdCopy),ReadOwnedConversationId(context,ref id),Copy(context,value,NativeMethods.PendingApprovalTitleCopy),Copy(context,value,NativeMethods.PendingApprovalDetailsCopy));registry.Register(result,value,NativeMethods.PendingApprovalDestroy);value=0;return result;}
        finally{Destroy(context,ref value,NativeMethods.PendingApprovalDestroy,"pending approval");}
    }
    private static nint ExtractApprovalConversationId(nint context,nint approval){nint value=0;NativeApi.ThrowIfFailed(NativeMethods.PendingApprovalConversationId(context,approval,ref value),"read approval conversation ID");return value;}
    private static CodexPendingElicitation ReadAndRegisterElicitation(NativePendingRegistry registry,nint context,ref nint value)
    {
        try{NativeApi.ThrowIfFailed(NativeMethods.PendingElicitationElicitation(context,value,out var elicitation),"read elicitation");var result=new CodexPendingElicitation(ReadOwnedElicitation(context,ref elicitation));registry.Register(result,value,NativeMethods.PendingElicitationDestroy);value=0;return result;}
        finally{Destroy(context,ref value,NativeMethods.PendingElicitationDestroy,"pending elicitation");}
    }

    private static CodexSkill ReadOwnedSkill(nint context,ref nint value)
    {
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.SkillScope(context,value,out var scope),"read skill scope");
            NativeApi.ThrowIfFailed(NativeMethods.SkillIsEnabled(context,value,out var enabled),"read skill enabled");
            NativeApi.ThrowIfFailed(NativeMethods.SkillHasBrandColor(context,value,out var hasBrand),"read skill brand presence");
            NativeApi.ThrowIfFailed(NativeMethods.SkillDependenciesCount(context,value,out var count),"read skill dependencies");
            NativeApi.ThrowIfFailed(NativeMethods.SkillCanUninstall(context,value,out var canUninstall),"read skill removal");
            NativeApi.ThrowIfFailed(NativeMethods.SkillOrigin(context,value,out var origin),"read skill origin");
            return new(Copy(context,value,NativeMethods.SkillNameCopy),Copy(context,value,NativeMethods.SkillDisplayNameCopy),Copy(context,value,NativeMethods.SkillDescriptionCopy),Copy(context,value,NativeMethods.SkillPathCopy),scope,enabled!=0,hasBrand==0?null:Copy(context,value,NativeMethods.SkillBrandColorCopy),Strings(context,value,count,NativeMethods.SkillDependenciesCopyAt),canUninstall!=0,origin);
        }
        finally { Destroy(context,ref value,NativeMethods.SkillDestroy,"skill"); }
    }

    private delegate CodexStatus CopyFn(nint c,nint value,byte* buffer,nuint capacity,out nuint required);
    private delegate CodexStatus PresenceFn(nint c,nint value,out int present);
    private delegate CodexStatus CopyAtFn(nint c,nint value,nuint index,byte* buffer,nuint capacity,out nuint required);
    private delegate CodexStatus DestroyFn(nint c,ref nint value);
    private static string Copy(nint c,nint value,CopyFn copy) => NativeApi.CopyString((byte* b,nuint n,out nuint r)=>copy(c,value,b,n,out r));
    private static string? Optional(nint c,nint value,PresenceFn presence,CopyFn copy){NativeApi.ThrowIfFailed(presence(c,value,out var present),"read optional value presence");return present==0?null:Copy(c,value,copy);}
    private static string[] Strings(nint c,nint value,nuint count,CopyAtFn copy) { var result=new string[Checked(count)]; for(var i=0;i<result.Length;i++) result[i]=NativeApi.CopyString((byte* b,nuint n,out nuint r)=>copy(c,value,(nuint)i,b,n,out r)); return result; }
    private static int Checked(nuint count) => count>int.MaxValue ? throw new CodexException(CodexStatus.OutOfMemory,"Native collection is too large.") : (int)count;
    private static void Destroy(nint c,ref nint value,DestroyFn destroy,string name) { if(value!=0) NativeApi.ThrowIfFailed(destroy(c,ref value),$"destroy {name}"); }

    private sealed class InputScope(NativeContext context) : IDisposable
    {
        private readonly List<(nint Value,DestroyFn Destroy)> owned=[];
        internal nint Own(nint value,DestroyFn destroy) { if(value==0) throw new CodexException(CodexStatus.InternalError,"Native value creation returned null."); owned.Add((value,destroy)); return value; }
        internal nint ConversationId(CodexConversationId value)
        {
            using var strings = new Utf8Arena();
            var text = strings.View(value.Value);
            NativeApi.ThrowIfFailed(NativeMethods.ConversationIdCreate(context.Pointer, &text, out var id), "create conversation ID");
            return Own(id, NativeMethods.ConversationIdDestroy);
        }
        private nint Invocation(CodexInvocation value)
        {
            using var strings = new Utf8Arena();
            nint concrete;
            CodexStatus status;
            DestroyFn destroy;
            Func<nint, nint, (CodexStatus Status, nint Value)> wrap;
            if (value is CodexInvocation.Plugin plugin)
            {
                var name = strings.View(plugin.Name); var uri = strings.View(plugin.Uri);
                status = NativeMethods.InvocationPluginCreate(context.Pointer, &name, &uri, out concrete);
                destroy = NativeMethods.InvocationPluginDestroy;
                wrap = (c, v) => { var resultStatus = NativeMethods.InvocationFromPlugin(c, v, out var result); return (resultStatus, result); };
            }
            else if (value is CodexInvocation.Skill skill)
            {
                var name = strings.View(skill.Name); var path = strings.View(skill.Path);
                status = NativeMethods.InvocationSkillCreate(context.Pointer, &name, &path, out concrete);
                destroy = NativeMethods.InvocationSkillDestroy;
                wrap = (c, v) => { var resultStatus = NativeMethods.InvocationFromSkill(c, v, out var result); return (resultStatus, result); };
            }
            else throw new ArgumentOutOfRangeException(nameof(value));
            NativeApi.ThrowIfFailed(status, "create invocation");
            Own(concrete, destroy);
            var (wrappedStatus, wrapped) = wrap(context.Pointer, concrete);
            NativeApi.ThrowIfFailed(wrappedStatus, "wrap invocation");
            return Own(wrapped, NativeMethods.InvocationDestroy);
        }
        internal nint TurnRequest(CodexTurnRequest value)
        {
            using var strings = new Utf8Arena();
            var prompt = strings.View(value.Prompt); var clientId = strings.View(value.ClientMessageId);
            var model = strings.View(value.Model); var effort = strings.View(value.Effort);
            var serviceTier = strings.View(value.ServiceTier);
            var capabilities = value.Capabilities.ToArray();
            var invocations = value.Invocations.Select(Invocation).ToArray();
            fixed (CodexCapability* capabilityValues = capabilities)
            fixed (nint* invocationValues = invocations)
            {
                NativeApi.ThrowIfFailed(NativeMethods.TurnRequestCreate(
                    context.Pointer, &prompt,
                    value.ClientMessageId is null ? 0 : 1, &clientId,
                    value.Model is null ? 0 : 1, &model,
                    value.Effort is null ? 0 : 1, &effort,
                    value.ServiceTier is null ? 0 : 1, &serviceTier,
                    value.ApprovalPreset,
                    capabilityValues, (nuint)capabilities.Length,
                    invocationValues, (nuint)invocations.Length,
                    value.CollaborationMode,
                    out var request), "create turn request");
                return Own(request, NativeMethods.TurnRequestDestroy);
            }
        }
        internal nint AuthenticationMethod(CodexAuthenticationMethod value)
        {
            CodexStatus status; nint method;
            if(value is CodexAuthenticationMethod.ApiKey key) { using var strings=new Utf8Arena(); var view=strings.View(key.Value); status=NativeMethods.AuthenticationMethodApiKeyCreate(context.Pointer,&view,out method); if(status==CodexStatus.Ok) return Own(method,NativeMethods.AuthenticationMethodApiKeyDestroy); }
            else if(value is CodexAuthenticationMethod.ChatGptBrowser) { status=NativeMethods.AuthenticationMethodChatGptBrowserCreate(context.Pointer,out method); if(status==CodexStatus.Ok) return Own(method,NativeMethods.AuthenticationMethodChatGptBrowserDestroy); }
            else if(value is CodexAuthenticationMethod.ChatGptDeviceCode) { status=NativeMethods.AuthenticationMethodChatGptDeviceCodeCreate(context.Pointer,out method); if(status==CodexStatus.Ok) return Own(method,NativeMethods.AuthenticationMethodChatGptDeviceCodeDestroy); }
            else throw new ArgumentOutOfRangeException(nameof(value));
            NativeApi.ThrowIfFailed(status,"create authentication method"); return 0;
        }
        internal nint Model(CodexModel value)
        {
            using var strings=new Utf8Arena(); var id=strings.View(value.Id);var display=strings.View(value.DisplayName);var description=strings.View(value.Description);var effortViews=value.SupportedEfforts.Select(strings.View).ToArray();var defaultEffort=strings.View(value.DefaultEffort);var defaultTier=strings.View(value.DefaultServiceTier);var tiers=value.ServiceTiers.Select(Tier).ToArray();
            fixed(NativeStringView* efforts=effortViews) fixed(nint* tierValues=tiers) { NativeApi.ThrowIfFailed(NativeMethods.ModelCreate(context.Pointer,&id,&display,&description,efforts,(nuint)effortViews.Length,&defaultEffort,value.IsDefault?1:0,tierValues,(nuint)tiers.Length,value.DefaultServiceTier is null?0:1,&defaultTier,out var model),"create model"); return Own(model,NativeMethods.ModelDestroy); }
        }
        private nint Tier(CodexServiceTier value) { using var strings=new Utf8Arena();var id=strings.View(value.Id);var name=strings.View(value.Name);var description=strings.View(value.Description);NativeApi.ThrowIfFailed(NativeMethods.ServiceTierCreate(context.Pointer,&id,&name,&description,out var tier),"create service tier");return Own(tier,NativeMethods.ServiceTierDestroy); }
        internal nint Skill(CodexSkill value) { using var strings=new Utf8Arena();var name=strings.View(value.Name);var display=strings.View(value.DisplayName);var description=strings.View(value.Description);var path=strings.View(value.Path);var brand=strings.View(value.BrandColor);var dependencies=value.Dependencies.Select(strings.View).ToArray();fixed(NativeStringView* dependencyValues=dependencies){NativeApi.ThrowIfFailed(NativeMethods.SkillCreate(context.Pointer,&name,&display,&description,&path,value.Scope,value.IsEnabled?1:0,value.BrandColor is null?0:1,&brand,dependencyValues,(nuint)dependencies.Length,value.CanUninstall?1:0,1,value.Origin,out var skill),"create skill");return Own(skill,NativeMethods.SkillDestroy);}}
        private nint Connector(CodexConnector value){using var strings=new Utf8Arena();var id=strings.View(value.Id);var name=strings.View(value.Name);var description=strings.View(value.Description);var install=strings.View(value.InstallUrl);var plugins=value.PluginNames.Select(strings.View).ToArray();fixed(NativeStringView* pluginValues=plugins){NativeApi.ThrowIfFailed(NativeMethods.ConnectorCreate(context.Pointer,&id,&name,&description,value.InstallUrl is null?0:1,&install,value.IsAccessible?1:0,value.IsEnabled?1:0,pluginValues,(nuint)plugins.Length,out var connector),"create connector");return Own(connector,NativeMethods.ConnectorDestroy);}}
        internal nint PluginReference(CodexPluginReference value){using var strings=new Utf8Arena();var id=strings.View(value.Id);var name=strings.View(value.Name);var marketplace=strings.View(value.MarketplaceName);var path=strings.View(value.MarketplacePath);var remote=strings.View(value.RemotePluginId);NativeApi.ThrowIfFailed(NativeMethods.PluginReferenceCreate(context.Pointer,&id,&name,&marketplace,value.MarketplacePath is null?0:1,&path,value.RemotePluginId is null?0:1,&remote,out var result),"create plugin reference");return Own(result,NativeMethods.PluginReferenceDestroy);}
        private nint HookHandler(CodexHookHandler value)
        {
            nint concrete;CodexStatus status;DestroyFn destroy;Func<nint,nint,(CodexStatus Status,nint Value)> wrap;
            if(value is CodexHookHandler.Agent){status=NativeMethods.HookHandlerAgentAcquire(context.Pointer,out concrete);destroy=NativeMethods.HookHandlerAgentDestroy;wrap=(c,v)=>{var s=NativeMethods.HookHandlerFromAgent(c,v,out var r);return(s,r);};}
            else if(value is CodexHookHandler.Prompt){status=NativeMethods.HookHandlerPromptAcquire(context.Pointer,out concrete);destroy=NativeMethods.HookHandlerPromptDestroy;wrap=(c,v)=>{var s=NativeMethods.HookHandlerFromPrompt(c,v,out var r);return(s,r);};}
            else if(value is CodexHookHandler.Command command){using var strings=new Utf8Arena();var text=strings.View(command.CommandText);status=NativeMethods.HookHandlerCommandCreate(context.Pointer,&text,command.IsAsync?1:0,out concrete);destroy=NativeMethods.HookHandlerCommandDestroy;wrap=(c,v)=>{var s=NativeMethods.HookHandlerFromCommand(c,v,out var r);return(s,r);};}
            else if(value is CodexHookHandler.McpTool tool){using var strings=new Utf8Arena();var server=strings.View(tool.Server);var name=strings.View(tool.Tool);status=NativeMethods.HookHandlerMcpToolCreate(context.Pointer,&server,&name,out concrete);destroy=NativeMethods.HookHandlerMcpToolDestroy;wrap=(c,v)=>{var s=NativeMethods.HookHandlerFromMcpTool(c,v,out var r);return(s,r);};}
            else throw new ArgumentOutOfRangeException(nameof(value));
            NativeApi.ThrowIfFailed(status,"create hook handler");Own(concrete,destroy);var (wrappedStatus,result)=wrap(context.Pointer,concrete);NativeApi.ThrowIfFailed(wrappedStatus,"wrap hook handler");return Own(result,NativeMethods.HookHandlerDestroy);
        }
        internal nint Hook(CodexHook value)
        {
            using var strings=new Utf8Arena();var key=strings.View(value.Key);var hash=strings.View(value.CurrentHash);var eventName=strings.View(value.EventName);var source=strings.View(value.Source);var sourcePath=strings.View(value.SourcePath);var matcher=strings.View(value.Matcher);var plugin=strings.View(value.PluginId);var status=strings.View(value.StatusMessage);var handler=HookHandler(value.Handler);
            NativeApi.ThrowIfFailed(NativeMethods.HookCreate(context.Pointer,&key,&hash,value.IsEnabled?1:0,&eventName,handler,value.IsManaged?1:0,&source,&sourcePath,value.TimeoutSeconds,value.TrustStatus,value.Matcher is null?0:1,&matcher,value.PluginId is null?0:1,&plugin,value.StatusMessage is null?0:1,&status,1,value.Origin,value.CanUninstall?1:0,out var result),"create hook");return Own(result,NativeMethods.HookDestroy);
        }
        private nint FormValue(CodexFormValue value)
        {
            nint concrete;CodexStatus status;DestroyFn destroy;Func<nint,nint,(CodexStatus Status,nint Value)> wrap;
            if(value is CodexFormValue.BooleanValue boolean){status=NativeMethods.FormBooleanCreate(context.Pointer,boolean.Value?1:0,out concrete);destroy=NativeMethods.FormBooleanDestroy;wrap=(c,v)=>{var s=NativeMethods.FormValueFromBoolean(c,v,out var r);return(s,r);};}
            else if(value is CodexFormValue.Number number){status=NativeMethods.FormNumberCreate(context.Pointer,number.Value,out concrete);destroy=NativeMethods.FormNumberDestroy;wrap=(c,v)=>{var s=NativeMethods.FormValueFromNumber(c,v,out var r);return(s,r);};}
            else if(value is CodexFormValue.Text text){using var strings=new Utf8Arena();var item=strings.View(text.Value);status=NativeMethods.FormTextCreate(context.Pointer,&item,out concrete);destroy=NativeMethods.FormTextDestroy;wrap=(c,v)=>{var s=NativeMethods.FormValueFromText(c,v,out var r);return(s,r);};}
            else if(value is CodexFormValue.TextList list){using var strings=new Utf8Arena();var items=list.Value.Select(strings.View).ToArray();fixed(NativeStringView* views=items)status=NativeMethods.FormTextListCreate(context.Pointer,views,(nuint)items.Length,out concrete);destroy=NativeMethods.FormTextListDestroy;wrap=(c,v)=>{var s=NativeMethods.FormValueFromTextList(c,v,out var r);return(s,r);};}
            else throw new ArgumentOutOfRangeException(nameof(value));
            NativeApi.ThrowIfFailed(status,"create form value");Own(concrete,destroy);var (wrappedStatus,result)=wrap(context.Pointer,concrete);NativeApi.ThrowIfFailed(wrappedStatus,"wrap form value");return Own(result,NativeMethods.FormValueDestroy);
        }
        internal nint ElicitationResponse(CodexElicitationResponse value)
        {
            using var strings=new Utf8Arena();var entries=value.Content.ToArray();var keys=entries.Select(entry=>strings.View(entry.Key)).ToArray();var values=entries.Select(entry=>FormValue(entry.Value)).ToArray();fixed(NativeStringView* keyViews=keys)fixed(nint* nativeValues=values){NativeApi.ThrowIfFailed(NativeMethods.ElicitationResponseCreate(context.Pointer,value.Action,keyViews,nativeValues,(nuint)entries.Length,out var response),"create elicitation response");return Own(response,NativeMethods.ElicitationResponseDestroy);}
        }
        internal nint Integration(CodexIntegration value)
        {
            if(value is CodexIntegration.Connector connector)
            {
                var item=Connector(connector.ConnectorValue);NativeApi.ThrowIfFailed(NativeMethods.IntegrationConnectorCreate(context.Pointer,item,out var concrete),"create connector integration");Own(concrete,NativeMethods.IntegrationConnectorDestroy);NativeApi.ThrowIfFailed(NativeMethods.IntegrationFromConnector(context.Pointer,concrete,out var result),"wrap connector integration");return Own(result,NativeMethods.IntegrationDestroy);
            }
            if(value is CodexIntegration.McpServer server)
            {
                var item=McpServer(server.Server);NativeApi.ThrowIfFailed(NativeMethods.IntegrationMcpServerCreate(context.Pointer,item,out var concrete),"create MCP integration");Own(concrete,NativeMethods.IntegrationMcpServerDestroy);NativeApi.ThrowIfFailed(NativeMethods.IntegrationFromMcpServer(context.Pointer,concrete,out var result),"wrap MCP integration");return Own(result,NativeMethods.IntegrationDestroy);
            }
            throw new ArgumentOutOfRangeException(nameof(value));
        }
        private nint McpEnvironmentVariable(CodexMcpEnvironmentVariable value){using var strings=new Utf8Arena();var name=strings.View(value.Name);NativeApi.ThrowIfFailed(NativeMethods.McpEnvironmentVariableCreate(context.Pointer,&name,value.Source is null?0:1,value.Source??default,out var result),"create MCP environment variable");return Own(result,NativeMethods.McpEnvironmentVariableDestroy);}
        private nint McpOauth(CodexMcpOauthConfiguration value){using var strings=new Utf8Arena();var client=strings.View(value.ClientId);NativeApi.ThrowIfFailed(NativeMethods.McpOauthConfigurationCreate(context.Pointer,value.ClientId is null?0:1,&client,value.CallbackPort is null?0:1,value.CallbackPort??0,out var result),"create MCP OAuth configuration");return Own(result,NativeMethods.McpOauthConfigurationDestroy);}
        private nint McpTool(CodexMcpToolConfiguration value){NativeApi.ThrowIfFailed(NativeMethods.McpToolConfigurationCreate(context.Pointer,value.Approval is null?0:1,value.Approval??default,out var result),"create MCP tool configuration");return Own(result,NativeMethods.McpToolConfigurationDestroy);}
        private nint McpTransport(CodexMcpTransport value)
        {
            nint concrete;CodexStatus status;DestroyFn destroy;Func<nint,nint,(CodexStatus Status,nint Value)> wrap;
            if(value is CodexMcpTransport.Http http){using var strings=new Utf8Arena();var url=strings.View(http.Url);var bearer=strings.View(http.BearerTokenEnvironmentVariable);var headerItems=(http.Headers??new Dictionary<string,string>()).ToArray();var headerKeys=headerItems.Select(item=>strings.View(item.Key)).ToArray();var headerValues=headerItems.Select(item=>strings.View(item.Value)).ToArray();var environmentItems=(http.EnvironmentHeaders??new Dictionary<string,string>()).ToArray();var environmentKeys=environmentItems.Select(item=>strings.View(item.Key)).ToArray();var environmentValues=environmentItems.Select(item=>strings.View(item.Value)).ToArray();var helper=strings.View(http.HeadersHelper);fixed(NativeStringView* hk=headerKeys)fixed(NativeStringView* hv=headerValues)fixed(NativeStringView* ek=environmentKeys)fixed(NativeStringView* ev=environmentValues)status=NativeMethods.McpTransportHttpCreate(context.Pointer,&url,http.BearerTokenEnvironmentVariable is null?0:1,&bearer,http.Headers is null?0:1,hk,hv,(nuint)headerItems.Length,http.EnvironmentHeaders is null?0:1,ek,ev,(nuint)environmentItems.Length,http.HeadersHelper is null?0:1,&helper,out concrete);destroy=NativeMethods.McpTransportHttpDestroy;wrap=(c,v)=>{var s=NativeMethods.McpTransportFromHttp(c,v,out var r);return(s,r);};}
            else if(value is CodexMcpTransport.Stdio stdio){using var strings=new Utf8Arena();var command=strings.View(stdio.Command);var arguments=stdio.Arguments.Select(strings.View).ToArray();var directory=strings.View(stdio.WorkingDirectory);var environmentItems=(stdio.Environment??new Dictionary<string,string>()).ToArray();var keys=environmentItems.Select(item=>strings.View(item.Key)).ToArray();var mapped=environmentItems.Select(item=>strings.View(item.Value)).ToArray();var forwarded=stdio.ForwardedEnvironment.Select(McpEnvironmentVariable).ToArray();fixed(NativeStringView* av=arguments)fixed(NativeStringView* ek=keys)fixed(NativeStringView* ev=mapped)fixed(nint* fv=forwarded)status=NativeMethods.McpTransportStdioCreate(context.Pointer,&command,av,(nuint)arguments.Length,stdio.WorkingDirectory is null?0:1,&directory,stdio.Environment is null?0:1,ek,ev,(nuint)environmentItems.Length,fv,(nuint)forwarded.Length,out concrete);destroy=NativeMethods.McpTransportStdioDestroy;wrap=(c,v)=>{var s=NativeMethods.McpTransportFromStdio(c,v,out var r);return(s,r);};}
            else throw new ArgumentOutOfRangeException(nameof(value));NativeApi.ThrowIfFailed(status,"create MCP transport");Own(concrete,destroy);var (wrappedStatus,result)=wrap(context.Pointer,concrete);NativeApi.ThrowIfFailed(wrappedStatus,"wrap MCP transport");return Own(result,NativeMethods.McpTransportDestroy);
        }
        internal nint McpConfiguration(CodexMcpServerConfiguration value)
        {
            using var strings=new Utf8Arena();var name=strings.View(value.Name);var environment=strings.View(value.EnvironmentId);var enabled=(value.EnabledTools??[]).Select(strings.View).ToArray();var disabled=(value.DisabledTools??[]).Select(strings.View).ToArray();var scopes=(value.Scopes??[]).Select(strings.View).ToArray();var oauthResource=strings.View(value.OauthResource);var omit=(value.OmitToolsFrom??[]).ToArray();var toolItems=value.Tools.ToArray();var toolKeys=toolItems.Select(item=>strings.View(item.Key)).ToArray();var tools=toolItems.Select(item=>McpTool(item.Value)).ToArray();var oauth=value.Oauth is null?0:McpOauth(value.Oauth);var transport=McpTransport(value.Transport);
            fixed(NativeStringView* enabledValues=enabled)fixed(NativeStringView* disabledValues=disabled)fixed(NativeStringView* scopeValues=scopes)fixed(CodexMcpToolExposureSurface* omitValues=omit)fixed(NativeStringView* keys=toolKeys)fixed(nint* toolValues=tools){NativeApi.ThrowIfFailed(NativeMethods.McpServerConfigurationCreate(context.Pointer,&name,transport,value.Authentication is null?0:1,value.Authentication??default,&environment,value.IsEnabled?1:0,value.IsRequired?1:0,value.SupportsParallelToolCalls?1:0,value.OmitToolsFrom is null?0:1,omitValues,(nuint)omit.Length,value.StartupTimeoutSeconds is null?0:1,value.StartupTimeoutSeconds??0,value.ToolTimeoutSeconds is null?0:1,value.ToolTimeoutSeconds??0,value.DefaultToolApproval is null?0:1,value.DefaultToolApproval??default,value.EnabledTools is null?0:1,enabledValues,(nuint)enabled.Length,value.DisabledTools is null?0:1,disabledValues,(nuint)disabled.Length,value.Scopes is null?0:1,scopeValues,(nuint)scopes.Length,value.Oauth is null?0:1,oauth,value.OauthResource is null?0:1,&oauthResource,keys,toolValues,(nuint)tools.Length,out var result),"create MCP server configuration");return Own(result,NativeMethods.McpServerConfigurationDestroy);}
        }
        internal nint McpServer(CodexMcpServer value)
        {
            using var strings=new Utf8Arena();var name=strings.View(value.Name);var display=strings.View(value.DisplayName);var configuration=value.Configuration is null?0:McpConfiguration(value.Configuration);NativeApi.ThrowIfFailed(NativeMethods.McpServerCreate(context.Pointer,&name,&display,value.AuthStatus,configuration,value.Origin,value.CanRemove?1:0,out var result),"create MCP server");return Own(result,NativeMethods.McpServerDestroy);
        }
        public void Dispose(){for(var i=owned.Count-1;i>=0;i--){var (value,destroy)=owned[i];Destroy(context.Pointer,ref value,destroy,"input value");}}
    }
}

internal sealed class NativePendingRegistry(NativeContext context) : IDisposable
{
    private readonly object gate=new();
    private readonly Dictionary<object,(nint Value,NativeHandleRelease Destroy)> values=new(ReferenceEqualityComparer.Instance);
    private bool disposed;
    internal void Register(object key,nint value,NativeHandleRelease destroy)
    {
        lock(gate){ObjectDisposedException.ThrowIf(disposed,this);if(values.TryGetValue(key,out var previous)){var old=previous.Value;NativeApi.ThrowIfFailed(previous.Destroy(context.Pointer,ref old),"replace pending interaction");}values[key]=(value,destroy);}
    }
    internal T Use<T>(object value,Func<nint,T> action)
    {
        ArgumentNullException.ThrowIfNull(value);lock(gate){ObjectDisposedException.ThrowIf(disposed,this);if(!values.TryGetValue(value,out var native))throw new ArgumentException("The pending interaction is not a live value owned by this service.",nameof(value));return action(native.Value);}
    }
    public void Dispose()
    {
        lock(gate){if(disposed)return;disposed=true;foreach(var native in values.Values){var value=native.Value;var status=NativeApi.RetryBusy(()=>native.Destroy(context.Pointer,ref value));if(status!=CodexStatus.Ok)NativeCleanup.Report("pending interaction",status,this);}values.Clear();}
    }
}

internal static class NativeTaskLifetime
{
    internal static async Task<T> AwaitAndDispose<T>(Task<T> task, IDisposable resource)
    {
        using (resource) return await task.ConfigureAwait(false);
    }
    internal static async Task AwaitAndDispose(Task task, IDisposable resource)
    {
        using (resource) await task.ConfigureAwait(false);
    }
}

internal static class NativeCallContext
{
    private static readonly AsyncLocal<NativeContext?> CurrentValue=new();
    internal static nint Current => CurrentValue.Value?.Pointer ?? throw new InvalidOperationException("No native call context is active.");
    internal static NativeContext Owner => CurrentValue.Value ?? throw new InvalidOperationException("No native call context is active.");
    internal static IDisposable Enter(NativeContext value){var previous=CurrentValue.Value;CurrentValue.Value=value;return new Exit(()=>CurrentValue.Value=previous);}
    private sealed class Exit(Action action):IDisposable{public void Dispose()=>action();}
}
