"""Replay every SDK campaign family against one caller-held original selection.

An independently reviewed, non-secret caller owns the held selection and
policy/capture pins. The protected signer separately authenticates its original
inputs and semantic output, then grants release trust without executing any
candidate or tooling code. This helper only checks that the existing full
family gates return the 62 selected original receipts.
"""

from collections.abc import Mapping

from .registry import SDK_FACADE_TARGETS, PhaseInstanceId
from .reuse import _validate_envelope
from .sdk_campaign_android import verify_campaign_android_family
from .sdk_campaign_apple import verify_campaign_apple_family
from .sdk_campaign_javascript import verify_campaign_javascript
from .sdk_campaign_maven import verify_campaign_maven_phase
from .sdk_campaign_native import NATIVE_CAMPAIGN_INSTANCES, verify_sdk_campaign_native
from .sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from .sdk_core_original_selection import verify_campaign_core_validations
from .sdk_facade_metadata_admission import FacadeMetadataAdmission


def _id(component, phase, target):
    return PhaseInstanceId("sdk", component, phase, target)


def verify_sdk_campaign_semantics(*, sources, envelopes, stages, maven_controls,
        core_validation_controls, core_validation_policy, core_metadata_control,
        android_control, apple_control, javascript_control, native_control):
    """Return exact original bytes only after all 62 real semantic gates pass.

    ``sources``, ``envelopes`` and ``stages`` must be the private values yielded
    by ``held_sdk_campaign_selection`` on the non-secret replay runner. Controls
    must be independently pinned and, where relevant, constructed for those
    private stages. A successful return is not producer, transport, or release
    trust; the protected signer must authenticate the exact evidence separately.
    """
    for name, values in (("sources", sources), ("envelopes", envelopes), ("stages", stages)):
        if not isinstance(values, Mapping) or set(values) != SDK_CAMPAIGN_INSTANCES:
            raise ValueError(f"SDK semantic campaign {name} must contain all 62 instances")
    originals = {}
    for instance in SDK_CAMPAIGN_INSTANCES:
        selected, envelope = _validate_envelope(envelopes[instance])
        if (selected != instance or sources[instance].release_admission is not None
                or sources[instance].receipt_bytes != envelope["receiptBytes"]):
            raise ValueError("SDK semantic campaign selected another original")
        originals[instance] = envelope["receiptBytes"]

    maven_ids = {_id(component, phase, target)
                 for component, target in (("sdk-core", "common"), ("sdk-android", "android"))
                 for phase in ("binary", "package")}
    if not isinstance(maven_controls, Mapping) or set(maven_controls) != maven_ids:
        raise ValueError("SDK semantic campaign requires four Maven controls")
    result = {}
    for instance in sorted(maven_ids):
        result[instance] = verify_campaign_maven_phase(
            envelopes[instance], stages[instance], **maven_controls[instance])

    if not isinstance(core_validation_controls, Mapping) or set(core_validation_controls) != set(SDK_FACADE_TARGETS):
        raise ValueError("SDK semantic campaign requires eleven Core controls")
    core_selections = {}
    for target in SDK_FACADE_TARGETS:
        instance = _id("sdk-core", "validation", target)
        control = dict(core_validation_controls[target])
        if "envelope" in control or "stage" in control:
            raise ValueError("Core selection envelope and stage come only from the held campaign")
        core_selections[target] = {**control, "envelope": envelopes[instance], "stage": stages[instance]}
    core_receipts = verify_campaign_core_validations(core_selections, **core_validation_policy)
    if not isinstance(core_receipts, Mapping) or set(core_receipts) != set(SDK_FACADE_TARGETS):
        raise ValueError("Core campaign did not verify every validation")
    result.update({_id("sdk-core", "validation", target): raw for target, raw in core_receipts.items()})

    core_metadata = _id("sdk-core", "metadata", "common")
    core_admission = FacadeMetadataAdmission(**core_metadata_control)
    core_admission.verify_metadata(
        envelopes[core_metadata],
        [envelopes[_id("sdk-core", "validation", target)] for target in SDK_FACADE_TARGETS])
    result[core_metadata] = originals[core_metadata]

    android_ids = {phase: _id("sdk-android", phase, "android")
                   for phase in ("binary", "package", "validation", "metadata")}
    android_receipts = verify_campaign_android_family(
        envelopes={phase: envelopes[instance] for phase, instance in android_ids.items()},
        stages={phase: stages[instance] for phase, instance in android_ids.items()},
        **android_control)
    if not isinstance(android_receipts, Mapping) or set(android_receipts) != set(android_ids):
        raise ValueError("Android campaign did not verify all four phases")
    result.update({instance: android_receipts[phase] for phase, instance in android_ids.items()})

    ios_validation = {target: _id("sdk-ios", "validation", target)
                      for target in ("ios-arm64", "ios-simulator-arm64")}
    ios_binary, ios_package, ios_metadata = (_id("sdk-ios", phase, "ios")
                                              for phase in ("binary", "package", "metadata"))
    apple_receipts = verify_campaign_apple_family(
        envelopes[ios_binary], stages[ios_binary], envelopes[ios_package], stages[ios_package],
        {target: envelopes[instance] for target, instance in ios_validation.items()},
        {target: stages[instance] for target, instance in ios_validation.items()},
        envelopes[ios_metadata], stages[ios_metadata], **apple_control)
    if (not isinstance(apple_receipts, Mapping) or set(apple_receipts) != {"binary", "package", "validation", "metadata"}
            or not isinstance(apple_receipts["validation"], Mapping)
            or set(apple_receipts["validation"]) != set(ios_validation)):
        raise ValueError("Apple campaign did not verify all five phases")
    result.update({ios_binary: apple_receipts["binary"], ios_package: apple_receipts["package"],
                   ios_metadata: apple_receipts["metadata"]})
    result.update({instance: apple_receipts["validation"][target]
                   for target, instance in ios_validation.items()})

    javascript_ids = {phase: _id("javascript", phase, "node")
                      for phase in ("package", "validation", "metadata")}
    javascript_receipts = verify_campaign_javascript(
        **{f"{phase}_envelope": envelopes[instance] for phase, instance in javascript_ids.items()},
        **{f"{phase}_stage": stages[instance] for phase, instance in javascript_ids.items()},
        **javascript_control)
    if not isinstance(javascript_receipts, Mapping) or set(javascript_receipts) != set(javascript_ids):
        raise ValueError("JavaScript campaign did not verify all three phases")
    result.update({instance: javascript_receipts[phase]
                   for phase, instance in javascript_ids.items()})

    native_receipts, _ = verify_sdk_campaign_native(
        sources={instance: sources[instance] for instance in NATIVE_CAMPAIGN_INSTANCES},
        stages={instance: stages[instance] for instance in NATIVE_CAMPAIGN_INSTANCES},
        **native_control)
    if not isinstance(native_receipts, Mapping) or set(native_receipts) != NATIVE_CAMPAIGN_INSTANCES:
        raise ValueError("Native campaign did not verify all 36 phases")
    result.update({instance: value[1] for instance, value in native_receipts.items()})
    if set(result) != SDK_CAMPAIGN_INSTANCES or result != originals:
        raise ValueError("SDK semantic campaign changed an original receipt")
    return result
