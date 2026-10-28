"""Whole collector plus real delta export/resolve before the next consumer."""
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch

import product_reuse as adapter
import runtime_reference_transport as transport
from products.inventory import regular_file_inventory,snapshot_regular_tree,write_canonical_json
from products.restore import object_relative_path
from ci.tests.test_checkpoint_collector_execution import CORE
from ci.tests.test_checkpoint_collector_handoff import CheckpointCollectorHandoffTest


class CheckpointCollectorExportTest(CheckpointCollectorHandoffTest):
    measurements=[]
    export_measurements=[]

    def test_actual_collector_export_resolution_and_next_consumer_leave_old_bodies_unopened(self):
        original_replay=adapter._verified_product_state
        exported=[]
        def replay(plan,discovery,state,*args,**kwargs):
            handoff=Path(discovery).parent
            if handoff!=self.scratch/'collected/handoff':
                return original_replay(plan,discovery,state,*args,**kwargs)
            self.assertFalse(exported,'export exactly once before the next consumer')
            base=self.scratch/'original';capture=self.scratch/'base-capture.json'
            # Structural locator for already captured fixture input. This is not
            # a new native/fresh original-upload authentication claim.
            write_canonical_json(capture,{'artifact':{'id':101,'digest':'sha256:'+'a'*64},
                'stateWave':0,'sdkStateWave':10,'captureProducer':self.producer})
            delta=self.scratch/'exported';resolved=self.scratch/'resolved'
            value=transport.stage_reference_handoff(handoff,base,capture,delta,state_wave=0,sdk_state_wave=11)
            files=regular_file_inventory(delta,allow_empty=True)
            snapshot_regular_tree(delta,resolved,allow_empty=True)
            transport.resolve_reference_handoff(resolved,base,value,state_wave=0,sdk_state_wave=11)
            self.assertEqual(regular_file_inventory(handoff,allow_empty=True),regular_file_inventory(resolved,allow_empty=True))
            result=original_replay(resolved/'product-resume-inputs/plan/impact-plan.json',
                resolved/'product-resume-state',resolved/'runtime-state',*args,**kwargs)
            self.assertTrue(result.sources[CORE].is_relative_to(resolved),'next consumer must use resolved new bytes')
            exported.append(True)
            type(self).export_measurements.append({'exportedFileBytes':sum(row['bytes'] for row in files),
                'exportedFiles':len(files),'referenceLogicalBytes':sum(row['bytes'] for row in value['references']),
                'referenceFiles':len(value['references']),
                'scope':'Local files before upload ZIP overhead; referenced controls resolved from already captured fixture base.'})
            return result
        with patch.object(adapter,'_verified_product_state',side_effect=replay):
            super().test_outer_collector_handoff_and_next_consumer_do_not_reopen_qualified_contract_bodies()
        self.assertEqual([True],exported)


class ReferenceExportSelectionTest(unittest.TestCase):
    def test_needed_objects_keep_cross_directory_references_while_unneeded_objects_are_not_opened(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();base=root/'base';handoff=root/'handoff'
            def write(directory,name,raw):
                path=directory/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);return path
            needed=object_relative_path('sha256:'+'a'*64,'sha256:'+'b'*64)
            unused=object_relative_path('sha256:'+'c'*64,'sha256:'+'d'*64)
            write(base,'product-resume-state/old/'+needed,b'needed exact original')
            old=write(base,'product-resume-state/old/'+unused,b'noncanonical alias bytes')
            write(handoff,'runtime-state/new/'+needed,b'needed exact original')
            # A noncanonical alias still publishes exact bytes; it cannot force
            # the exporter to hash an unrelated canonical old object.
            write(handoff,'runtime-state/alias.bin',b'noncanonical alias bytes')
            for directory in (base,handoff):write(directory,'product-resume-inputs/control.json',b'unchanged controls')
            capture=root/'capture.json';write_canonical_json(capture,{'artifact':{'id':101,'digest':'sha256:'+'e'*64},'stateWave':1})
            delta=root/'delta'
            with CheckpointCollectorHandoffTest.reads(self,[old]) as opened:
                value=transport.stage_reference_handoff(handoff,base,capture,delta,state_wave=2)
            self.assertEqual([],opened)
            self.assertEqual('product-resume-state/old/'+needed,next(row['sourcePath'] for row in value['references']
                if row['relativePath']=='runtime-state/new/'+needed))
            self.assertEqual(b'noncanonical alias bytes',(delta/'runtime-state/alias.bin').read_bytes())
            resolved=root/'resolved';snapshot_regular_tree(delta,resolved)
            transport.resolve_reference_handoff(resolved,base,value,state_wave=2)
            self.assertEqual(regular_file_inventory(handoff),regular_file_inventory(resolved))
            # Excluding a body never exempts it from path safety.
            raw=old.read_bytes();old.unlink();old.symlink_to(delta/'runtime-state/alias.bin')
            with self.assertRaises(ValueError):transport.stage_reference_handoff(handoff,base,capture,root/'unsafe',state_wave=2)
            self.assertFalse((root/'unsafe').exists());old.unlink();old.write_bytes(raw)

    def test_referenced_control_mutation_still_rejects_before_export_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();base=root/'base';handoff=root/'handoff'
            for directory in (base,handoff):
                (directory/'product-resume-state').mkdir(parents=True)
                (directory/'product-resume-state/control.json').write_bytes(b'original controls')
            (handoff/'runtime-state').mkdir();(handoff/'runtime-state/new.json').write_bytes(b'new file')
            capture=root/'capture.json';write_canonical_json(capture,{'artifact':{'id':101,'digest':'sha256:'+'e'*64},'stateWave':1})
            copy=transport._copy_exact
            def mutate(*args,**kwargs):
                result=copy(*args,**kwargs)
                (base/'product-resume-state/control.json').write_bytes(b'changed controls')
                return result
            with patch.object(transport,'_copy_exact',side_effect=mutate),self.assertRaisesRegex(ValueError,'inputs changed'):
                transport.stage_reference_handoff(handoff,base,capture,root/'rejected',state_wave=2)
            self.assertFalse((root/'rejected').exists())
