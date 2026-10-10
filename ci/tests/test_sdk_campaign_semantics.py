"""The campaign composer cannot skip a family or substitute a selected receipt."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from ci.products import sdk_campaign_semantics as campaign
from ci.products.registry import SDK_FACADE_TARGETS


class SdkCampaignSemanticsTest(TestCase):
    def setUp(self):
        self.originals = {instance: repr(instance).encode() for instance in campaign.SDK_CAMPAIGN_INSTANCES}
        self.sources = {instance: SimpleNamespace(receipt_bytes=raw, release_admission=None)
                        for instance, raw in self.originals.items()}
        self.envelopes = {instance: {"instance": instance, "bytes": raw}
                          for instance, raw in self.originals.items()}
        self.stages = {instance: object() for instance in self.originals}
        self.calls = []

    def run_campaign(self, *, native_result=None):
        def maven(envelope, stage, **_):
            self.calls.append(("maven", envelope["instance"]))
            return envelope["bytes"]

        def core(selections, **_):
            self.calls.append(("core", set(selections)))
            return {target: selection["envelope"]["bytes"] for target, selection in selections.items()}

        def android(*, envelopes, stages, **_):
            self.calls.append(("android", set(envelopes)))
            return {phase: value["bytes"] for phase, value in envelopes.items()}

        def apple(binary, binary_stage, package, package_stage, validations,
                  validation_stages, metadata, metadata_stage, **_):
            self.calls.append(("apple", set(validations)))
            return {"binary": binary["bytes"], "package": package["bytes"],
                    "validation": {target: value["bytes"] for target, value in validations.items()},
                    "metadata": metadata["bytes"]}

        def javascript(**kwargs):
            self.calls.append(("javascript", set(kwargs)))
            return {phase: kwargs[f"{phase}_envelope"]["bytes"]
                    for phase in ("package", "validation", "metadata")}

        def native(*, sources, stages, **_):
            self.calls.append(("native", set(sources)))
            return (native_result if native_result is not None else
                    {instance: ({}, source.receipt_bytes) for instance, source in sources.items()}), {}

        admission = SimpleNamespace(verify_metadata=lambda *_: self.calls.append(("metadata", None)))
        with patch.object(campaign, "_validate_envelope",
                          side_effect=lambda value: (value["instance"], {"receiptBytes": value["bytes"]})), \
             patch.object(campaign, "verify_campaign_maven_phase", side_effect=maven), \
             patch.object(campaign, "verify_campaign_core_validations", side_effect=core), \
             patch.object(campaign, "FacadeMetadataAdmission", return_value=admission), \
             patch.object(campaign, "verify_campaign_android_family", side_effect=android), \
             patch.object(campaign, "verify_campaign_apple_family", side_effect=apple), \
             patch.object(campaign, "verify_campaign_javascript", side_effect=javascript), \
             patch.object(campaign, "verify_sdk_campaign_native", side_effect=native):
            return campaign.verify_sdk_campaign_semantics(
                sources=self.sources, envelopes=self.envelopes, stages=self.stages,
                maven_controls={instance: {} for instance in self.originals
                                if instance.component in ("sdk-core", "sdk-android")
                                and instance.phase in ("binary", "package")},
                core_validation_controls={target: {} for target in SDK_FACADE_TARGETS},
                core_validation_policy={}, core_metadata_control={}, android_control={},
                apple_control={}, javascript_control={}, native_control={})

    def test_all_62_originals_require_every_family(self):
        self.assertEqual(self.run_campaign(), self.originals)
        self.assertEqual([name for name, _ in self.calls].count("maven"), 4)
        self.assertEqual({name for name, _ in self.calls},
                         {"maven", "core", "metadata", "android", "apple", "javascript", "native"})

    def test_native_family_cannot_substitute_or_omit_an_original(self):
        native = {instance: ({}, source.receipt_bytes)
                  for instance, source in self.sources.items()
                  if instance in campaign.NATIVE_CAMPAIGN_INSTANCES}
        changed = next(iter(native))
        native[changed] = ({}, b"other")
        with self.assertRaisesRegex(ValueError, "changed an original receipt"):
            self.run_campaign(native_result=native)
        native.pop(changed)
        with self.assertRaisesRegex(ValueError, "all 36 phases"):
            self.run_campaign(native_result=native)

    def test_missing_selection_fails_before_any_family_gate(self):
        self.sources.pop(next(iter(self.sources)))
        with self.assertRaisesRegex(ValueError, "all 62 instances"):
            self.run_campaign()
        self.assertEqual(self.calls, [])
