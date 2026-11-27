"""C# binary phase executes one elected compiler phase from explicit originals."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_csharp_binary_phase as worker
from ci.tests.product_chain_support import write_receipt
from products.receipt import verify_output_manifest_identity, write_output_manifest
from products.restore import PHASE_PLAN_KEYS


class CSharpBinaryPhaseTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.destination = self.root / "build/worker"
        self.stage = self.root / "codex-agent-sdk/build/product-stage/sdk/csharp/binary"
        self.producer = {"repository": "fixture/repository", "commit": "a" * 40,
            "tree": "b" * 40, "event": "local", "workflowPath": None,
            "runId": None, "runAttempt": None, "pullRequest": None}
        self.contract_stage = self.root / "contract/stage"
        self.contract_payload = self.contract_stage / "outputs/codex-agent-contract-0.8.0.zip"
        self.contract_payload.parent.mkdir(parents=True)
        self.contract_payload.write_bytes(b"original Contract payload")
        manifest = write_output_manifest(self.contract_stage, "contract", "contract", "metadata",
                                         "common", "0.8.0", {"contract-bundle": "outputs"})
        self.contract_receipt = self.root / "contract/phase-receipt.json"
        receipt = write_receipt(self.contract_receipt, product="contract", component="contract",
            phase="metadata", target="common", version="0.8.0", version_identity="0.8.0",
            outputs=manifest["outputs"], upstream=[], context={"producer": self.producer})
        self.contract = {"stage": self.contract_stage, "receiptPath": self.contract_receipt,
                         "receipt": receipt}
        self.handoff = self.root / "contract-handoff"
        self.handoff.mkdir()
        (self.handoff / "codex-agent-contract-0.8.0.zip").write_bytes(self.contract_payload.read_bytes())
        for name in ("codex-agent-contract-0.8.0.attestation.json",
                     "codex-agent-contract-0.8.0.attestation.sig", "public-key.pub"):
            (self.handoff / name).write_bytes(b"caller-authenticated original")
        self.request = self.root / "sdk-inputs/request.json"
        self.request.parent.mkdir()
        self.request.write_bytes(b"caller-authenticated request")
        self.dotnet_profile = self.root / "gradle/release/toolchains/sdk/csharp.json"
        self.dotnet_profile.parent.mkdir(parents=True)
        self.dotnet_profile.write_bytes(b"caller-authenticated pinned profile")
        elected = write_receipt(self.root / "elected.json", product="sdk", component="csharp",
            phase="binary", target="desktop", version="0.8.0", version_identity="0.8.0",
            outputs=manifest["outputs"], upstream=[], context={"producer": self.producer})
        self.plan = {name: elected[name] for name in PHASE_PLAN_KEYS}
        self.calls = []

    def process(self, command, **kwargs):
        self.calls.append(command)
        self.assertEqual(self.root, kwargs["cwd"])
        self.assertEqual({"SAFE": "yes"}, kwargs["env"])
        self.assertEqual(subprocess.STDOUT, kwargs["stderr"])
        self.assertFalse(kwargs["check"])
        for name in ("CodexAgent.dll", "CodexAgent.pdb", "CodexAgent.xml",
                     "CodexAgent.deps.json", "sdk-compatibility.json", "sdk-runtime-root.pub"):
            path = self.stage / "outputs/csharp" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())
        write_output_manifest(self.stage, "sdk", "csharp", "binary", "desktop", "0.8.0",
                              {"csharp-binary": "outputs/csharp"})
        return subprocess.CompletedProcess(command, 0)

    def invoke(self):
        with (patch.object(worker, "host_classifier", return_value="linux-x64"),
              patch.object(worker, "_runtime_worker_checkout"),
              patch.object(worker, "_runtime_worker_environment", return_value=({"SAFE": "yes"}, "gradlew")),
              patch.object(worker, "_runtime_worker_command", side_effect=self.command),
              patch.object(worker, "verify_sdk_dotnet_toolchain") as toolchain,
              patch.object(worker, "_request_inventory", return_value={}),
              patch.object(worker.subprocess, "run", side_effect=self.process)):
            result = worker.execute(self.plan, producer=self.producer, sdk_version="0.8.0",
                contract_metadata=self.contract, verified_contract_handoff=self.handoff,
                compatibility_request=self.request, repository_root=self.root,
                destination=self.destination, environ={"SAFE": "yes"})
            toolchain.assert_called_once_with(self.dotnet_profile)
            return result

    def command(self, wrapper, properties, environment, *, build_directory):
        self.assertEqual("gradlew", wrapper)
        self.assertEqual(".", build_directory)
        self.assertEqual({"SAFE": "yes"}, environment)
        self.assertEqual("sdk", properties["codexAgent.product"])
        self.assertEqual("csharp", properties["codexAgent.component"])
        self.assertEqual("binary", properties["codexAgent.phase"])
        self.assertEqual("desktop", properties["codexAgent.target"])
        self.assertEqual(str(self.request), properties["codexAgent.sdkCompatibilityRequest"])
        self.assertEqual(str(self.dotnet_profile), properties["codexAgent.csharpDotnetProfile"])
        self.assertEqual(str(self.contract_receipt),
                         properties["codexAgent.contractMetadataReceipt"])
        return ["gradlew", "ciProductPhase"]

    def test_exact_binary_stage_and_contract_handoff(self):
        result = self.invoke()
        self.assertEqual(self.stage, result["stage"])
        self.assertEqual(1, len(self.calls))
        self.assertEqual(7, len(result["outputInventory"]))
        outputs = verify_output_manifest_identity(self.stage, "sdk", "csharp", "binary",
                                                  "desktop", "0.8.0")["outputs"]
        receipt = write_receipt(self.root / "binary-receipt.json", product="sdk", component="csharp",
            phase="binary", target="desktop", version="0.8.0", version_identity="0.8.0",
            outputs=outputs, upstream=[], context={"producer": self.producer})
        compatibility = self.root / "original-compatibility.json"
        root_key = self.root / "original-root.pub"
        compatibility.write_bytes(b"sdk-compatibility.json")
        root_key.write_bytes(b"sdk-runtime-root.pub")
        self.assertEqual(outputs, worker.verify_csharp_binary_stage(
            self.stage, receipt, compatibility, root_key)["outputs"])
        root_key.write_bytes(b"different root")
        with self.assertRaisesRegex(ValueError, "SDK policy"):
            worker.verify_csharp_binary_stage(self.stage, receipt, compatibility, root_key)

    def test_tampered_contract_handoff_fails_before_gradle(self):
        (self.handoff / "codex-agent-contract-0.8.0.zip").write_bytes(b"different payload")
        with self.assertRaisesRegex(ValueError, "handoff differs"):
            self.invoke()
        self.assertEqual([], self.calls)

    def test_wrong_phase_fails_before_gradle(self):
        self.plan["phase"] = "package"
        with self.assertRaisesRegex(ValueError, "Unsupported C# binary"):
            self.invoke()
        self.assertEqual([], self.calls)

    def test_toolchain_mismatch_fails_before_gradle(self):
        with patch.object(worker, "verify_sdk_dotnet_toolchain", side_effect=ValueError("wrong dotnet")):
            with self.assertRaisesRegex(ValueError, "wrong dotnet"):
                worker.execute(self.plan, producer=self.producer, sdk_version="0.8.0",
                    contract_metadata=self.contract, verified_contract_handoff=self.handoff,
                    compatibility_request=self.request, repository_root=self.root,
                    destination=self.destination, environ={"SAFE": "yes"})
        self.assertEqual([], self.calls)
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
