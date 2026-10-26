"""Synthetic signed original closure, not hosted release authority."""

from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from ci import runtime_phase10_library_caller as caller
from ci.tests import test_runtime_aggregate_handoff as fixture
from products.inventory import (canonical_json_bytes, load_canonical_json_bytes,
    public_key_fingerprint, regular_file_inventory, sha256_bytes, snapshot_regular_tree)
from products.registry import NATIVE_TARGETS
from products.runtime_library_authorization import verified_runtime_libraries
from products.sdk_runtime_root import verify_external_library_authorization
from products.signatures import generate_development_key


class RuntimeLibraryAuthorizationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.RuntimeAggregateHandoffTest.setUpClass()
        cls.addClassCleanup(fixture.RuntimeAggregateHandoffTest.doClassCleanups)
        cls.source = fixture.RuntimeAggregateHandoffTest()
        cls.source.setUp()
        cls.addClassCleanup(cls.source.doCleanups)
        policy = cls.source.source.policy
        cls.signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
        cls.signing.update(policy["activeKey"])

    def test_signed_originals_project_exact_five_libraries_and_identities(self):
        with self.source.read() as verified:
            projected = verified_runtime_libraries(verified, self.signing)
            self.assertEqual(set(NATIVE_TARGETS), set(projected))
            for target, item in projected.items():
                claim = item["claim"]
                self.assertEqual(target, claim["runtimeIdentity"]["target"])
                self.assertEqual("0.2.7", claim["runtimeVersion"])
                self.assertEqual(sha256_bytes(item["library"]), claim["runtimeLibrarySha256"])
                self.assertTrue(item["fileName"])

    def test_observation_token_rejected_before_handoff_or_signing(self):
        with tempfile.TemporaryDirectory(prefix="runtime-library-token-negative-") as temporary:
            destination = Path(temporary) / "unauthorized"
            with patch.dict(os.environ, {"GITHUB_TOKEN": "observation-token"}), \
                    patch.object(caller, "verified_runtime_aggregate_handoff") as gate, \
                    patch.object(caller, "issue_root_delegation") as signer, \
                    self.assertRaisesRegex(ValueError, "observation token"):
                caller.produce_authenticated_runtime_libraries(
                    self.source.carrier, destination,
                    expected_metadata_receipt_sha256="sha256:" + "a" * 64,
                    expected_build_key="sha256:" + "b" * 64,
                    keyring=self.source.keyring, keys_directory=self.source.keys,
                    root_public_key=Path(temporary) / "missing-root.pub",
                    expected_root_fingerprint="sha256:" + "c" * 64,
                    expected_root_public_key_sha256="sha256:" + "d" * 64,
                    root_delegation=Path(temporary) / "missing-delegation",
                    expected_delegation_inventory_sha256="sha256:" + "e" * 64,
                    release_private_key=Path(temporary) / "missing-release-key",
                )
            gate.assert_not_called()
            signer.assert_not_called()
            self.assertFalse(destination.exists())
            with patch.dict(os.environ, {"GITHUB_TOKEN": "observation-token"}), \
                    patch.object(caller, "issue_root_delegation") as signer, \
                    self.assertRaisesRegex(ValueError, "observation token"):
                caller.issue_authenticated_runtime_root_delegation(
                    destination, keyring=self.source.keyring, keys_directory=self.source.keys,
                    root_public_key=Path(temporary) / "missing-root.pub",
                    expected_root_public_key_sha256="sha256:" + "d" * 64,
                    expected_keyring_sha256="sha256:" + "f" * 64,
                    expected_keys_inventory_sha256="sha256:" + "0" * 64,
                    root_private_key=Path(temporary) / "missing-root-key")
            signer.assert_not_called()

    def test_root_and_release_signing_secrets_cannot_share_a_job(self):
        with tempfile.TemporaryDirectory(prefix="runtime-library-secret-split-") as temporary:
            work = Path(temporary)
            with patch.dict(os.environ, {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": "forbidden"}), \
                    patch.object(caller, "issue_root_delegation") as issuer, \
                    self.assertRaisesRegex(ValueError, "product signing secret"):
                caller.issue_authenticated_runtime_root_delegation(
                    work / "delegation", keyring=self.source.keyring, keys_directory=self.source.keys,
                    root_public_key=work / "missing-root.pub",
                    expected_root_public_key_sha256="sha256:" + "a" * 64,
                    expected_keyring_sha256="sha256:" + "b" * 64,
                    expected_keys_inventory_sha256="sha256:" + "c" * 64,
                    root_private_key=work / "missing-root-key")
            issuer.assert_not_called()
            with patch.dict(os.environ, {"CODEX_AGENT_SDK_RUNTIME_ROOT_ED25519_PRIVATE_KEY": "forbidden"}), \
                    patch.object(caller, "verified_runtime_aggregate_handoff") as gate, \
                    self.assertRaisesRegex(ValueError, "SDK root secret"):
                caller.produce_authenticated_runtime_libraries(
                    self.source.carrier, work / "released",
                    expected_metadata_receipt_sha256="sha256:" + "a" * 64,
                    expected_build_key="sha256:" + "b" * 64,
                    keyring=self.source.keyring, keys_directory=self.source.keys,
                    root_public_key=work / "missing-root.pub",
                    expected_root_fingerprint="sha256:" + "c" * 64,
                    expected_root_public_key_sha256="sha256:" + "d" * 64,
                    root_delegation=work / "missing-delegation",
                    expected_delegation_inventory_sha256="sha256:" + "e" * 64,
                    release_private_key=work / "missing-release-key")
            gate.assert_not_called()

    def test_protected_caller_signs_exact_external_bytes_after_full_handoff(self):
        with tempfile.TemporaryDirectory(prefix="runtime-library-authorization-test-") as temporary:
            work = Path(temporary).resolve()
            root_private, root_public, _ = generate_development_key(work / "root")
            fingerprint = public_key_fingerprint(root_public.read_bytes())
            root_digest = sha256_bytes(root_public.read_bytes())
            delegation = work / "delegation"
            delegated = caller.issue_authenticated_runtime_root_delegation(
                delegation, keyring=self.source.keyring, keys_directory=self.source.keys,
                root_public_key=root_public, expected_root_public_key_sha256=root_digest,
                expected_keyring_sha256=sha256_bytes(self.source.keyring.read_bytes()),
                expected_keys_inventory_sha256=sha256_bytes(canonical_json_bytes(
                    regular_file_inventory(self.source.keys))), root_private_key=root_private)
            receipt = load_canonical_json_bytes(
                (self.source.carrier / "aggregate-input/metadata-receipt.json").read_bytes())
            arguments = dict(
                expected_metadata_receipt_sha256=sha256_bytes(
                    (self.source.carrier / "aggregate-input/metadata-receipt.json").read_bytes()),
                expected_build_key=receipt["buildKey"], keyring=self.source.keyring,
                keys_directory=self.source.keys, root_public_key=root_public,
                expected_root_fingerprint=fingerprint, expected_root_public_key_sha256=root_digest,
                root_delegation=delegation,
                expected_delegation_inventory_sha256=delegated["inventorySha256"],
                release_private_key=self.source.source.context["private_key"],
            )
            destination = work / "released"
            with patch.object(caller, "verified_runtime_aggregate_handoff",
                              wraps=caller.verified_runtime_aggregate_handoff) as gate:
                result = caller.produce_authenticated_runtime_libraries(
                    self.source.carrier, destination, **arguments)
            gate.assert_called_once()
            self.assertEqual(fingerprint, result["rootFingerprint"])
            self.assertEqual(delegated["inventorySha256"], result["delegationInventorySha256"])
            sidecars = work / "validation-sidecars"
            with patch.object(caller, "verified_runtime_aggregate_handoff",
                              wraps=caller.verified_runtime_aggregate_handoff) as gate, \
                    patch.object(caller, "_original_carrier", wraps=caller._original_carrier) as pins, \
                    patch.object(caller, "snapshot_regular_tree",
                                 wraps=caller.snapshot_regular_tree) as snapshots:
                sidecar_result = caller.produce_authenticated_runtime_libraries(
                    self.source.carrier, sidecars, sidecars_only=True, **arguments)
            gate.assert_called_once()
            self.assertEqual(2, pins.call_count)
            self.assertNotEqual(pins.call_args_list[0].args[0], pins.call_args_list[1].args[0])
            self.assertEqual(pins.call_args_list[0].args[1:], pins.call_args_list[1].args[1:])
            self.assertNotIn(self.source.carrier, [call.args[0] for call in snapshots.call_args_list])
            self.assertTrue(all(".evidence/" in row["relativePath"] for row in sidecar_result["files"]))
            self.assertEqual([row for row in result["files"] if ".evidence/" in row["relativePath"]],
                             sidecar_result["files"])
            compatibility = load_canonical_json_bytes(self.source.source.chain["compatibility"].read_bytes())
            for target in NATIVE_TARGETS:
                paths = list((destination / target).glob("libcodex_agent.*")) + \
                    list((destination / target).glob("codex_agent.dll"))
                libraries = [path for path in paths if path.is_file()]
                self.assertEqual(1, len(libraries), target)
                library = libraries[0]
                claim = verify_external_library_authorization(
                    library.with_name(library.name + ".evidence"),
                    sdk_pinned_root_public_key=root_public.read_bytes(),
                    sdk_compatibility=compatibility, target=target, library_snapshot=library,
                )
                self.assertEqual(sha256_bytes(library.read_bytes()), claim["runtimeLibrarySha256"])
                self.assertEqual(claim, verify_external_library_authorization(
                    sidecars / target / (library.name + ".evidence"),
                    sdk_pinned_root_public_key=root_public.read_bytes(),
                    sdk_compatibility=compatibility, target=target, library_snapshot=library))
            with patch.object(caller, "verified_runtime_aggregate_handoff") as gate, \
                    self.assertRaisesRegex(ValueError, "caller pin"):
                caller.produce_authenticated_runtime_libraries(
                    self.source.carrier, work / "wrong-root", **{
                        **arguments, "expected_root_fingerprint": sha256_bytes(b"wrong"),
                    })
            gate.assert_not_called()
            self.assertFalse((work / "wrong-root").exists())

    def test_corrupt_original_variant_signature_cannot_reach_private_keys_or_publish(self):
        with tempfile.TemporaryDirectory(prefix="runtime-library-corrupt-original-") as temporary:
            work = Path(temporary).resolve()
            corrupt = work / "corrupt-original"
            snapshot_regular_tree(self.source.carrier, corrupt, allow_empty=True)
            signatures = list((corrupt / "variant-inputs/macos-arm64").glob("*.attestation.sig"))
            self.assertEqual(1, len(signatures))
            signatures[0].write_bytes(signatures[0].read_bytes() + b"x")
            receipt = (self.source.carrier / "aggregate-input/metadata-receipt.json").read_bytes()
            root_private, root_public, _ = generate_development_key(work / "root")
            delegation = work / "delegation"
            delegated = caller.issue_authenticated_runtime_root_delegation(
                delegation, keyring=self.source.keyring, keys_directory=self.source.keys,
                root_public_key=root_public,
                expected_root_public_key_sha256=sha256_bytes(root_public.read_bytes()),
                expected_keyring_sha256=sha256_bytes(self.source.keyring.read_bytes()),
                expected_keys_inventory_sha256=sha256_bytes(canonical_json_bytes(
                    regular_file_inventory(self.source.keys))), root_private_key=root_private)
            destination = work / "unauthorized"
            with patch.object(caller, "verified_runtime_libraries", side_effect=AssertionError("claim signer reached")) as signer, \
                    self.assertRaises(ValueError):
                caller.produce_authenticated_runtime_libraries(
                    corrupt, destination,
                    expected_metadata_receipt_sha256=sha256_bytes(receipt),
                    expected_build_key=load_canonical_json_bytes(receipt)["buildKey"],
                    keyring=self.source.keyring, keys_directory=self.source.keys,
                    root_public_key=root_public,
                    expected_root_fingerprint=public_key_fingerprint(root_public.read_bytes()),
                    expected_root_public_key_sha256=sha256_bytes(root_public.read_bytes()),
                    root_delegation=delegation,
                    expected_delegation_inventory_sha256=delegated["inventorySha256"],
                    release_private_key=work / "no-release-private-key",
                )
            signer.assert_not_called()
            self.assertFalse(destination.exists())

    def test_repinned_bad_delegation_cannot_reach_release_signer(self):
        with tempfile.TemporaryDirectory(prefix="runtime-library-bad-delegation-") as temporary:
            work = Path(temporary).resolve()
            root_private, root_public, _ = generate_development_key(work / "root")
            delegation = work / "delegation"
            delegated = caller.issue_authenticated_runtime_root_delegation(
                delegation, keyring=self.source.keyring, keys_directory=self.source.keys,
                root_public_key=root_public,
                expected_root_public_key_sha256=sha256_bytes(root_public.read_bytes()),
                expected_keyring_sha256=sha256_bytes(self.source.keyring.read_bytes()),
                expected_keys_inventory_sha256=sha256_bytes(canonical_json_bytes(
                    regular_file_inventory(self.source.keys))), root_private_key=root_private)
            signature = delegation / "root-delegation.sig"
            signature.write_bytes(signature.read_bytes() + b"tampered")
            tampered_pin = sha256_bytes(canonical_json_bytes(regular_file_inventory(delegation)))
            self.assertNotEqual(delegated["inventorySha256"], tampered_pin)
            receipt = (self.source.carrier / "aggregate-input/metadata-receipt.json").read_bytes()
            destination = work / "unauthorized"
            with patch.object(caller, "verified_runtime_aggregate_handoff") as gate, \
                    self.assertRaises(ValueError):
                caller.produce_authenticated_runtime_libraries(
                    self.source.carrier, destination,
                    expected_metadata_receipt_sha256=sha256_bytes(receipt),
                    expected_build_key=load_canonical_json_bytes(receipt)["buildKey"],
                    keyring=self.source.keyring, keys_directory=self.source.keys,
                    root_public_key=root_public,
                    expected_root_fingerprint=public_key_fingerprint(root_public.read_bytes()),
                    expected_root_public_key_sha256=sha256_bytes(root_public.read_bytes()),
                    root_delegation=delegation,
                    expected_delegation_inventory_sha256=tampered_pin,
                    release_private_key=self.source.source.context["private_key"])
            gate.assert_not_called()
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()


class ImportedOriginalScopeTest(unittest.TestCase):
    """Parser/isolation checks only; no signing keys or product acceptance."""
    def scope(self):
        digest="sha256:"+"a"*64
        value={name:digest for name in caller._IMPORTED_CONTROL_KEYS}
        value.update(schemaVersion=2,kind="sdk-runtime-library-imported-validation",
            trustedSourceCommit="b"*40,sourceTrustDomain="development",inputManifestBytes=1024,
            libraries=[{name:(target if name=="target" else digest)
                for name in caller._IMPORTED_LIBRARY_KEYS} for target in sorted(NATIVE_TARGETS)])
        return value

    def test_scope_is_exact_and_preserves_development_originals(self):
        value=self.scope();raw=canonical_json_bytes(value)
        self.assertEqual(value,caller.validate_imported_validation_control(raw,
            expected_sha256=sha256_bytes(raw),trusted_source_commit=value["trustedSourceCommit"]))
        for field,new in (("schemaVersion",True),("sourceTrustDomain","release"),("inputManifestBytes",0)):
            with self.subTest(field=field),self.assertRaises(ValueError):
                bad=canonical_json_bytes({**value,field:new})
                caller.validate_imported_validation_control(bad,expected_sha256=sha256_bytes(bad),
                    trusted_source_commit=value["trustedSourceCommit"])

    def test_scope_rejects_unapproved_source_and_unknown_fields(self):
        value=self.scope()
        for new,source in (({**value,"unapproved":True},"b"*40),(value,"c"*40)):
            raw=canonical_json_bytes(new)
            with self.assertRaises(ValueError):
                caller.validate_imported_validation_control(raw,expected_sha256=sha256_bytes(raw),
                    trusted_source_commit=source)

    def test_observation_token_cannot_enter_imported_signer(self):
        with patch.dict(os.environ,{"GITHUB_TOKEN":"forbidden"}), \
                patch.object(caller,"verified_imported_development_content") as gate, \
                patch.object(caller,"_write_library_authorizations") as signer, \
                self.assertRaisesRegex(ValueError,"observation token"):
            caller.produce_imported_runtime_libraries(Path("missing"),Path("missing-control"),Path("missing-output"),
                expected_control_sha256="sha256:"+"a"*64,trusted_source_commit="b"*40,
                keyring=Path("missing-keyring"),keys_directory=Path("missing-keys"),root_public_key=Path("missing-root"),
                expected_root_public_key_sha256="sha256:"+"c"*64,release_private_key=Path("missing-secret"))
        gate.assert_not_called();signer.assert_not_called()


class ImportedLfsTransportTest(unittest.TestCase):
    """Transport-only bytes and observations; no keys or product evidence."""

    class Response:
        def __init__(self, raw, url, status=200):
            import io
            self.stream, self.url, self.status = io.BytesIO(raw), url, status
        def read(self, size): return self.stream.read(size)
        def geturl(self): return self.url
        def __enter__(self): return self
        def __exit__(self, *unused): self.stream.close()

    def inputs(self, root, count=1279):
        bodies = {sha256_bytes(f"unit-object-{i}".encode())[7:]: f"unit-object-{i}".encode()
                  for i in range(count)}
        files = [dict(relativePath=f"unit/{i:04d}",bytes=len(raw),sha256="sha256:"+oid)
                 for i,(oid,raw) in enumerate(sorted(bodies.items()))]
        manifest = dict(schemaVersion=1,kind=caller._IMPORTED_KIND,files=files,
            originals=[],contractStage="unit",runtimeStageRoot="unit",custodyCheckpoint="unit/custody",
            compatibilityRequest="unit/compatibility",rootDelegation="unit/delegation",sourceMappings=[])
        raw = canonical_json_bytes(manifest)
        value = ImportedOriginalScopeTest().scope()
        value.update(inputManifestBytes=len(raw),inputManifestSha256=sha256_bytes(raw))
        control = root / "control.json";control.write_bytes(canonical_json_bytes(value))
        bodies[value["inputManifestSha256"][7:]] = raw
        return control,value,bodies

    def action(self, oid, size):
        return dict(oid=oid,size=size,actions={"download": {
            "href": f"https://github-cloud.githubusercontent.com/alambic/media/{oid}?unit-signature=fixture"}})

    def test_1280_objects_use_14_authenticated_batches_and_four_streams(self):
        import base64,json,threading
        from collections import Counter
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();control,value,bodies=self.inputs(root)
            calls=[];lock=threading.Lock();download_threads=set()
            def opened(request):
                with lock:calls.append(request)
                if request.get_method()=="POST":
                    self.assertEqual(caller._IMPORTED_LFS_ENDPOINT,request.full_url)
                    self.assertEqual("Basic "+base64.b64encode(b"x-access-token:unit-read-token").decode(),
                                     request.get_header("Authorization"))
                    query=json.loads(request.data);self.assertEqual("download",query["operation"])
                    self.assertLessEqual(len(query["objects"]),100)
                    data=canonical_json_bytes(dict(objects=[self.action(r["oid"],r["size"]) for r in query["objects"]]))
                else:
                    self.assertIsNone(request.get_header("Authorization"))
                    oid=request.full_url.split("/media/",1)[1].split("?",1)[0];data=bodies[oid]
                    if oid!=value["inputManifestSha256"][7:]:
                        with lock:download_threads.add(threading.current_thread().ident)
                return self.Response(data,request.full_url)
            with patch.dict(os.environ,{"GH_TOKEN":"unit-read-token"},clear=True), \
                    patch.object(caller,"_imported_lfs_open",side_effect=opened), \
                    patch("concurrent.futures.ThreadPoolExecutor",wraps=ThreadPoolExecutor) as workers, \
                    patch.object(caller.subprocess,"run",side_effect=AssertionError("No transport subprocess")):
                result=caller.capture_imported_validation_objects(control,root/"capture",root/"storage",
                    expected_control_sha256=sha256_bytes(control.read_bytes()),trusted_source_commit=value["trustedSourceCommit"])
            self.assertEqual(14,result["lfsBatchRequests"]);self.assertEqual(1280,result["lfsObjectRequests"])
            self.assertEqual(0,result["transportSubprocesses"]);self.assertEqual(0,result["payloadCopies"])
            self.assertEqual(sum(map(len,bodies.values())),result["downloadedBytes"])
            workers.assert_called_once_with(max_workers=4);self.assertLessEqual(len(download_threads),4)
            self.assertEqual(14,sum(r.get_method()=="POST" for r in calls))
            seen=Counter(r.full_url.split("/media/",1)[1].split("?",1)[0] for r in calls if r.get_method()=="GET")
            self.assertEqual(Counter({oid:1 for oid in bodies}),seen)
            self.assertEqual(1279,len(list((root/"capture/objects").iterdir())))
            for path in (root/"capture/objects").iterdir():
                self.assertEqual(bodies[path.name],path.read_bytes())
                self.assertEqual(path.stat().st_ino,(root/"storage"/path.name).stat().st_ino)
            self.assertEqual((root/"capture/manifest.json").stat().st_ino,
                             (root/"storage"/value["inputManifestSha256"][7:]).stat().st_ino)

    def test_batch_rejects_missing_duplicate_extra_wrong_and_untrusted_actions(self):
        from copy import deepcopy
        rows=[dict(sha256="sha256:"+x*64,bytes=1) for x in "ab"]
        good=dict(objects=[self.action(row["sha256"][7:],1) for row in rows])
        values=[]
        for mode in ("missing","duplicate","extra","size","error","host","credentials","header","http","fragment"):
            value=deepcopy(good);item=value["objects"][0];action=item["actions"]["download"]
            if mode=="missing":value["objects"].pop()
            elif mode=="duplicate":value["objects"][1]=deepcopy(item)
            elif mode=="extra":value["objects"].append(self.action("c"*64,1))
            elif mode=="size":item["size"]=2
            elif mode=="error":item["error"]={"code":404}
            elif mode=="host":action["href"]="https://untrusted.invalid/object?query=unit"
            elif mode=="credentials":action["href"]="https://user:unit-secret@github-cloud.githubusercontent.com/a?query=unit"
            elif mode=="header":action["header"]={"Authorization":"unit-secret"}
            elif mode=="http":action["href"]=action["href"].replace("https:","http:")
            elif mode=="fragment":action["href"]+="#fragment"
            values.append((mode,value))
        for name,value in values:
            with self.subTest(mode=name),patch.object(caller,"_imported_lfs_open",return_value=self.Response(
                    canonical_json_bytes(value),caller._IMPORTED_LFS_ENDPOINT)),self.assertRaises(ValueError):
                caller._imported_lfs_batch(rows,"unit-read-token")

    def test_stream_checks_size_digest_and_keeps_preexisting_files(self):
        raw=b"exact-unit-object";row=dict(sha256=sha256_bytes(raw),bytes=len(raw))
        url=self.action(row["sha256"][7:],len(raw))["actions"]["download"]["href"]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();path=root/row["sha256"][7:]
            for candidate in (raw[:-1],raw+b"x",b"x"*len(raw)):
                with self.subTest(bodyBytes=len(candidate)),patch.object(caller,"_imported_lfs_open",
                        return_value=self.Response(candidate,url)),self.assertRaises(ValueError):
                    caller._receive_imported_lfs_object(row,url,root)
                self.assertFalse(path.exists())
            path.write_bytes(b"existing immutable bytes")
            with patch.object(caller,"_imported_lfs_open") as opened,self.assertRaises(FileExistsError):
                caller._receive_imported_lfs_object(row,url,root)
            opened.assert_not_called();self.assertEqual(b"existing immutable bytes",path.read_bytes())

    def test_missing_token_rejects_before_network_or_capture_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();control,value,_=self.inputs(root,1)
            with patch.dict(os.environ,{},clear=True),patch.object(caller,"_imported_lfs_open") as opened, \
                    self.assertRaisesRegex(ValueError,"explicit observation token"):
                caller.capture_imported_validation_objects(control,root/"capture",root/"storage",
                    expected_control_sha256=sha256_bytes(control.read_bytes()),trusted_source_commit=value["trustedSourceCommit"])
            opened.assert_not_called();self.assertFalse((root/"capture").exists())

    def test_redirect_is_rejected_without_exposing_presigned_url(self):
        from urllib.error import HTTPError
        from urllib.request import Request
        from runtime_reference_transport import _NoRedirect
        request=Request("https://github-cloud.githubusercontent.com/alambic/media/unit?unit-secret=hidden")
        with patch("urllib.request.build_opener") as build:
            build.return_value.open.side_effect=HTTPError(request.full_url,302,"redirect",{},None)
            with self.assertRaisesRegex(ValueError,"HTTP status 302") as raised:
                caller._imported_lfs_open(request)
            self.assertNotIn("unit-secret",str(raised.exception))
            self.assertIsInstance(build.call_args.args[0],_NoRedirect)
            self.assertIsNone(build.call_args.args[0].redirect_request(request,None,302,"redirect",{},"https://untrusted.invalid"))


class ImportedDeclaredReleaseKeysTest(unittest.TestCase):
    """Exercise only the imported policy join using actual tracked public keys."""
    def test_colocated_root_is_separate_and_declared_key_mutations_reject(self):
        from contextlib import contextmanager
        import shutil
        repository = Path(caller.__file__).resolve()
        while not (repository / "gradle/release/product-signing-keys.json").is_file():
            if repository == repository.parent: self.fail("Repository public policy unavailable")
            repository = repository.parent
        policy_source=repository / "gradle/release/product-signing-keys.json"
        keys_source=repository / "gradle/release/keys"
        policy=load_canonical_json_bytes(policy_source.read_bytes())
        records=([policy["activeKey"]] if policy["activeKey"] else [])+policy["retiredKeys"]
        active_name=policy["activeKey"]["keyId"]+".pub"
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();keys=root/"keys";shutil.copytree(keys_source,keys)
            keyring=root/"keyring.json";keyring.write_bytes(policy_source.read_bytes())
            root_public=keys/"sdk-runtime-root.pub"
            delegation=root/"inputs/delegation";(delegation/"keys").mkdir(parents=True)
            for record in records:
                name=record["keyId"]+".pub";(delegation/"keys"/name).write_bytes((keys/name).read_bytes())
            @contextmanager
            def content(*unused,**ignored):
                yield dict(rootDelegation=delegation,control={"rootDelegationInventorySha256":"sha256:"+"a"*64,"libraries":[]})
            public_path_only=root/"public-path-only.pub"
            public_path_only.write_bytes((keys/active_name).read_bytes())
            arguments=dict(expected_control_sha256="sha256:"+"b"*64,trusted_source_commit="c"*40,
                keyring=keyring,keys_directory=keys,root_public_key=root_public,
                expected_root_public_key_sha256=sha256_bytes(root_public.read_bytes()),
                # Public file supplies only an existing path; the mocked writer
                # must stop before any private-key operation or output creation.
                release_private_key=public_path_only)
            with patch.dict(os.environ,{},clear=True), \
                    patch.object(caller,"verified_imported_development_content",side_effect=content), \
                    patch.object(caller,"_verify_pinned_delegation",return_value=(keyring.read_bytes(),regular_file_inventory(delegation))), \
                    patch.object(caller,"verified_runtime_libraries",return_value={}), \
                    patch.object(caller,"_write_library_authorizations",side_effect=RuntimeError("policy join reached writer boundary")) as writer:
                with self.assertRaisesRegex(RuntimeError,"policy join reached writer boundary"):
                    caller.produce_imported_runtime_libraries(root/"inputs",root/"control",root/"output",**arguments)
                writer.assert_called_once();writer.reset_mock()
                original=(keys/active_name).read_bytes()
                for mutation in ("changed","missing"):
                    with self.subTest(mutation=mutation):
                        if mutation=="changed":(keys/active_name).write_bytes(root_public.read_bytes())
                        else:(keys/active_name).unlink()
                        with self.assertRaises((ValueError,FileNotFoundError)):
                            caller.produce_imported_runtime_libraries(root/"inputs",root/"control",root/"output",**arguments)
                        writer.assert_not_called();(keys/active_name).write_bytes(original)
                self.assertFalse((root/"output").exists())
