"""Mechanism tests only; temporary inputs are not SentriFace runtime evidence."""
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('reconcile', Path(__file__).with_name('reconcile.py'))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

class ReconciliationTests(unittest.TestCase):
    def test_exact_role_and_name_not_substring(self):
        names = r.tree_names('- button "Restore Safely" [disabled]\n- paragraph: Restore\n- textbox "Account name"\n')
        self.assertIn(('button', 'Restore Safely'), names)
        self.assertNotIn(('button', 'Restore'), names)
        self.assertNotIn(('button', 'Account name'), names)

    def test_static_labels_only(self):
        self.assertEqual(r.literal_label('"Save Changes"'), 'Save Changes')
        self.assertEqual(r.literal_label('Photo &amp; Favorite Changes'), 'Photo & Favorite Changes')
        self.assertIsNone(r.literal_label('{selected ? "Save" : "Next"}'))
        self.assertIsNone(r.literal_label('Keep {person.name}'))
        self.assertIsNone(r.literal_label('(dynamic or icon-only; inspect component/caller)'))

    def test_quoted_name_with_escape_and_colon(self):
        names = r.tree_names('- dialog "Review: \\"synthetic\\"" [active]:\n')
        self.assertIn(('dialog', 'Review: "synthetic"'), names)

    def setup_capture(self, directory, public=True, sanitized=False):
        captures = directory / 'captures'; captures.mkdir()
        original = captures / 'UX-01_J01_Step-01_original.png'
        original.write_bytes(b'mechanism-test-only-not-a-runtime-image')
        original.with_suffix('.png.txt').write_text('- button "Save"\n- paragraph: /Users/private-authority/secret\n')
        meta = {'file': original.name, 'ux':'UX-01', 'journey':'J01', 'step':1, 'state':'saved',
                'source_sha': r.BASE_SHA, 'sha256':r.digest(original), 'public_candidate':public,
                'role':'Administrator', 'theme':'light','viewport':{'width':1440,'height':900}}
        if sanitized:
            derivative = captures / 'UX-01_J01_Step-01_original_SANITIZED.png'
            derivative.write_bytes(b'mechanism-test-only-sanitized')
            meta.update(sanitized_file=derivative.name,sanitized_sha256=r.digest(derivative))
        (directory/'capture-metadata.json').write_text(json.dumps([meta]))
        return meta

    def test_private_only_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp); self.setup_capture(directory, public=False)
            accepted, rejected=r.capture_candidates(directory,r.BASE_SHA)
            self.assertEqual(accepted,[])
            self.assertEqual(rejected,{'private_without_public_derivative':1})

    def test_sanitized_preferred_and_hash_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp); meta=self.setup_capture(directory, public=False,sanitized=True)
            accepted,rejected=r.capture_candidates(directory,r.BASE_SHA)
            self.assertFalse(rejected)
            self.assertEqual(accepted[0]['public_file'],meta['sanitized_file'])
            self.assertTrue(accepted[0]['is_sanitized'])
            (directory/'captures'/meta['sanitized_file']).write_bytes(b'changed')
            accepted,rejected=r.capture_candidates(directory,r.BASE_SHA)
            self.assertEqual(accepted,[])
            self.assertEqual(rejected,{'capture_hash_mismatch':1})

    def test_path_traversal_and_wrong_source_refused(self):
        for key,value,reason in [('file','../sensitive.png','unsafe_original_basename'),
                                  ('source_sha','wrong','source_sha_mismatch')]:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                directory=Path(tmp);meta=self.setup_capture(directory);meta[key]=value
                (directory/'capture-metadata.json').write_text(json.dumps([meta]))
                accepted,rejected=r.capture_candidates(directory,r.BASE_SHA)
                self.assertEqual(accepted,[]);self.assertEqual(rejected,{reason:1})

    def test_candidates_never_prove_workflow_or_export_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);private=root/'private';private.mkdir();self.setup_capture(private)
            audit=root/'audit';audit.mkdir()
            source=[{'source_id':'SRC-static','source':'frontend/src/test.jsx:1','source_sha':r.BASE_SHA,
                     'inventory_kind':'control-definition','element':'Button','user_task':'"Save"',
                     'action':'{}','state_expressions':'{}','ux_id':'UX-01','role_capability':'add'},
                    {'source_id':'SRC-transition','source':'frontend/src/test.jsx:2','source_sha':r.BASE_SHA,
                     'inventory_kind':'transition','element':'cross-feature transition','user_task':'Save',
                     'action':'{}','state_expressions':'{}','ux_id':'UX-01','role_capability':'add'},
                    {'source_id':'SRC-container','source':'frontend/src/test.jsx:3','source_sha':r.BASE_SHA,
                     'inventory_kind':'container-or-composite','element':'Menu','user_task':'Save',
                     'action':'{}','state_expressions':'{}','ux_id':'UX-01','role_capability':'add'}]
            r.write_csv(audit/'source-inventory.csv',list(source[0]),source)
            r.write_csv(audit/'source-journeys.csv',['journey_id'],[{'journey_id':'SJ-001'}])
            r.write_csv(audit/'source-branches.csv',['source_branch_id'],[{'source_branch_id':'SJ-001-B01'}])
            summary=r.reconcile(audit,private,r.BASE_SHA)
            coverage=r.read_csv(audit/'coverage.csv')
            self.assertEqual(summary['definition_denominator'],2)
            self.assertEqual([x['result'] for x in coverage],['PARTIAL','NOT RUN'])
            self.assertEqual(summary['automatic_pass_numerator'],0)
            self.assertEqual(summary['semantic_workflows_assessed_by_this_tool'],0)
            for name in ['coverage.csv','evidence-candidates.csv','coverage-summary.json']:
                self.assertNotIn('/Users/private-authority', (audit/name).read_text())
                self.assertNotIn('paragraph: ', (audit/name).read_text())

if __name__=='__main__':
    unittest.main()
