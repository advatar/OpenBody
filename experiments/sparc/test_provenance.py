import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from experiments.sparc.authenticate_ascent import file_check, object_url, external_directory
from experiments.sparc.audit_ascent import classify_manifest, measure_manifest
from experiments.sparc.adapter import sparql_envelope
from experiments.sparc.evidence_tools import compact_result, verify_results

class ManifestTests(unittest.TestCase):
    def setUp(self):
        raw=b'{"files": [{"path": "manifest.json", "size": 56}]}\n'
        # Iterate only fixture self-size generation, never scientific values.
        while True:
            x=json.loads(raw);n=len(raw)
            if x['files'][0]['size']==n:break
            x['files'][0]['size']=n;raw=json.dumps(x).encode()+b'\n'
        self.raw=raw;digest=hashlib.sha256(raw).digest()
        self.entry=dict(path='manifest.json',size=len(raw)-1,sha256=base64.b64encode(digest).decode(),s3Version='v1')
        self.observation=dict(byte_count=len(raw),sha256=digest.hex(),headers={'content-length':str(len(raw)),'x-amz-version-id':'v1'},measurements=measure_manifest(raw))
    def classify(self,a=None):return classify_manifest(self.entry,[self.observation,a or copy.deepcopy(self.observation)])
    def test_stable_size_defect_not_waived(self):
        self.assertEqual(self.classify(),'UPSTREAM_METADATA_DEFECT')
        self.assertEqual(file_check(self.entry,self.raw)['status'],'FAILED')
    def test_one_retrieval_insufficient(self):self.assertEqual(classify_manifest(self.entry,[self.observation]),'UNRESOLVED')
    def test_digest_mismatch(self):
        x=copy.deepcopy(self.observation);x['sha256']='0'*64;self.assertEqual(self.classify(x),'UNRESOLVED')
    def test_changed_version(self):
        x=copy.deepcopy(self.observation);x['headers']['x-amz-version-id']='v2';self.assertEqual(self.classify(x),'VERSION_MISMATCH')
    def test_encoded_representation_not_assumed_equal(self):
        x=copy.deepcopy(self.observation);x['headers']['content-encoding']='gzip';self.assertEqual(self.classify(x),'UNRESOLVED')
    def test_self_entry_not_enough(self):
        x=copy.deepcopy(self.observation);x['headers']['content-length']='4110';self.assertEqual(self.classify(x),'UNRESOLVED')
    def test_actual_size_agrees(self):
        self.entry['size']=len(self.raw);self.assertEqual(self.classify(),'RESOLVED')
    def test_traversal_rejected(self):
        with self.assertRaises(ValueError):object_url(364,{'path':'../x'})
    def test_git_output_rejected(self):
        with self.assertRaises(ValueError):external_directory(Path(__file__).parent/'evidence')
    def test_retrieved_identity_chain(self):
        x=json.loads((Path(__file__).parent/'evidence/receipts/ascent-identity.json').read_text())
        self.assertEqual(x['resolution'],'DISTINCT_STUDIES')
        self.assertEqual(x['equivalence'],'INCOMPARABLE')
        self.assertEqual(x['studies']['guided']['dataset'],364)
        self.assertEqual(x['studies']['tutorial']['dataset'],365)
        self.assertNotEqual(x['studies']['guided']['uuid'],x['studies']['tutorial']['uuid'])

    def test_observed_manifest_diagnosis(self):
        root=Path(__file__).parent/'evidence/receipts'
        x=json.loads((root/'ascent-manifest-investigation.json').read_text())
        self.assertEqual(classify_manifest(x['declared_entry'],x['observations']),'UPSTREAM_METADATA_DEFECT')
        self.assertEqual(x['file_verification_status'],'FAILED')
        self.assertEqual({r['byte_count'] for r in x['observations']},{5318})
        self.assertEqual(x['declared_entry']['size'],4110)
    def test_primary_template_hashes_and_lock_correction(self):
        root=Path(__file__).parent
        chain=json.loads((root/'evidence/receipts/ascent-identity.json').read_text())
        lock=json.loads((root/'upstream-lock.json').read_text())['ascent_guided_mode_demo']
        for node in chain['studies'].values():
            r=node['template_receipt']
            self.assertEqual(r['status'],'VERIFIED')
            self.assertEqual(r['expected_sha256'],r['observed_sha256'])
            self.assertEqual(r['expected_size'],r['size'])
        self.assertEqual(lock['osparc_study'],chain['studies']['guided']['uuid'])
        self.assertEqual(lock['previous_osparc_study'],chain['studies']['tutorial']['uuid'])
    def test_no_executable_contract(self):
        self.assertFalse((Path(__file__).parent/'ascent-reproduction-contract.json').exists())
    def test_committed_evidence_is_bounded(self):
        root=Path(__file__).parent/'evidence'
        for path in root.rglob('*'):
            if path.is_file():
                self.assertLess(path.stat().st_size,64*1024,str(path.relative_to(root)))
                self.assertIn(path.suffix,('.json','.md'))

class CompactEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);text='SELECT ?x WHERE {?x ?p ?o}\n';(self.root/'test.rq').write_text(text)
        result=sparql_envelope({'head':{'vars':['x']},'results':{'bindings':[{'x':{'type':'uri','value':'urn:'+str(i)}} for i in range(3)]}})
        self.record=dict(query_id='test',query_text=text,query_sha256=hashlib.sha256(text.encode()).hexdigest(),
                         source_artifact_sha256='a'*64,journal_sha256='b'*64,release='test',release_status='prerelease',
                         engine='test',engine_commit='c',engine_image='test@sha256:x',execution_status='REPRODUCED',**result)
        self.compact=compact_result(self.record)
    def test_compaction_preserves_full_digest(self):
        self.assertEqual(self.compact['result_sha256'],self.record['result_sha256'])
        self.assertEqual(len(self.compact['selected_bindings']),2)
        self.assertEqual(verify_results([self.record],[self.compact],self.root),1)
    def test_tampered_unselected_row_rejected(self):
        self.record['canonical_result']['results']['bindings'][2]['x']['value']='urn:changed'
        with self.assertRaises(ValueError):verify_results([self.record],[self.compact],self.root)
    def test_recomputed_tampered_result_rejected(self):
        self.record['canonical_result']['results']['bindings'][2]['x']['value']='urn:changed'
        self.record.update(sparql_envelope(self.record['canonical_result']))
        with self.assertRaises(ValueError):verify_results([self.record],[self.compact],self.root)
    def test_changed_query_rejected(self):
        (self.root/'test.rq').write_text('ASK {?s ?p ?o}')
        with self.assertRaises(ValueError):verify_results([self.record],[self.compact],self.root)
    def test_missing_result_rejected(self):
        with self.assertRaises(ValueError):verify_results([],[self.compact],self.root)
    def test_unbound_journal_rejected(self):
        self.record['journal_sha256']='c'*64
        with self.assertRaises(ValueError):verify_results([self.record],[self.compact],self.root)
