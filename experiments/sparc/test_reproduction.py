import copy
import io
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from experiments.sparc.adapter import IntegrityError, load_export, sparql_envelope
from experiments.sparc.authenticate import metadata_check, safe_extract, verify
from benchmark import compare, reproduction_outcome

class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lock = json.loads(Path(__file__).with_name('upstream-lock.json').read_text())['sckan']
        self.release = dict(tag_name=self.lock['tag'], prerelease=True, published_at=self.lock['published_at'], assets=[
            dict(name=self.lock[p+'artifact'],size=self.lock[p+'size_bytes'],digest='sha256:'+self.lock[p+'sha256']) for p in ('','graph_')])
    def test_metadata(self): self.assertEqual(len(metadata_check(self.lock,self.release)),2)
    def test_wrong_release(self):
        self.release['tag_name']='wrong'
        with self.assertRaises(IntegrityError):metadata_check(self.lock,self.release)
    def test_wrong_prerelease(self):
        self.release['prerelease']=False
        with self.assertRaises(IntegrityError):metadata_check(self.lock,self.release)
    def test_wrong_upstream_digest(self):
        self.release['assets'][0]['digest']='sha256:'+'0'*64
        with self.assertRaises(IntegrityError):metadata_check(self.lock,self.release)
    def test_corrupt_download(self):
        p=self.root/'artifact';p.write_bytes(b'corrupt')
        with self.assertRaises(IntegrityError):verify(p,'0'*64,7)
    def extract(self,name='fine.txt',mode=None,**limits):
        p=self.root/'a.zip'
        with zipfile.ZipFile(p,'w',compression=zipfile.ZIP_DEFLATED) as z:
            info=zipfile.ZipInfo(name)
            if mode is not None:info.external_attr=mode<<16
            z.writestr(info,b'x'*100)
        return safe_extract(p,self.root/'out',**limits)
    def test_extract_regular(self):self.assertEqual(self.extract()['files'],1)
    def test_traversal(self):
        with self.assertRaises(ValueError):self.extract('../escape')
    def test_absolute(self):
        with self.assertRaises(ValueError):self.extract('/escape')
    def test_symlink(self):
        with self.assertRaises(ValueError):self.extract(mode=stat.S_IFLNK|0o777)
    def test_special(self):
        with self.assertRaises(ValueError):self.extract(mode=stat.S_IFIFO|0o600)
    def test_bomb_budget(self):
        with self.assertRaises(ValueError):self.extract(max_bytes=50)
    def test_existing_target_symlink(self):
        (self.root/'out').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):self.extract()
    def test_malformed_export(self):
        p=self.root/'export';p.write_text('{"edges":[{}]}')
        with self.assertRaises(ValueError):load_export(p)

class ResultTests(unittest.TestCase):
    def data(self):return {'head':{'vars':['population','relation']},'results':{'bindings':[
        {'population':{'type':'uri','value':'urn:p'},'relation':{'type':'uri','value':'urn:located-in-part-of'}}]}}
    def test_preserve_typed_terms(self):
        x=self.data(); self.assertEqual(sparql_envelope(x)['canonical_result'],x)
    def test_canonical_order(self):
        x=self.data();x['results']['bindings'].append({'population':{'type':'literal','value':'unknown','xml:lang':'en'}})
        a=sparql_envelope(x);x['results']['bindings'].reverse();x['head']['vars'].reverse()
        self.assertEqual(a['result_sha256'],sparql_envelope(x)['result_sha256'])
    def test_empty_unknown(self):
        x=self.data();x['results']['bindings']=[];self.assertEqual(sparql_envelope(x)['status'],'unknown')
    def test_unsupported_blank_node(self):
        x=self.data();x['results']['bindings'][0]['population']['type']='bnode'
        with self.assertRaises(ValueError):sparql_envelope(x)
    def test_malformed_binding(self):
        x=self.data();x['results']['bindings'][0]['population']['value']=None
        with self.assertRaises(ValueError):sparql_envelope(x)
    def test_no_created_relations(self):
        x=self.data();r=sparql_envelope(x);self.assertEqual(r['raw_row_count'],1);self.assertEqual(r['canonical_result']['results'],x['results'])

class ComparatorFailures(unittest.TestCase):
    def bound(self,**kw):
        d=dict(model='ascent',artifact='a',inputs='i',dataset_version='1',species='rat',modality='implanted-cervical-vns',metric='threshold',unit='mA',status='ok',value=1.0);d.update(kw);return d
    def test_unit_mismatch(self):self.assertEqual(compare(self.bound(),self.bound(unit='V'),atol=0)['status'],'incomparable')
    def test_artifact_mismatch(self):self.assertEqual(compare(self.bound(),self.bound(artifact='b'),atol=0)['status'],'incomparable')
    def test_missing_bindings(self):self.assertEqual(compare({'status':'ok','value':1},{'status':'ok','value':1},atol=0)['status'],'incomparable')
    def test_missing_output(self):self.assertEqual(reproduction_outcome(self.bound(),self.bound(status='missing',value=None),atol=0)['outcome'],'BLOCKED')
    def test_failed_execution(self):self.assertEqual(reproduction_outcome(self.bound(),self.bound(status='failed'),atol=0)['outcome'],'FAIL')
    def test_inf(self):self.assertEqual(compare(self.bound(),self.bound(value=float('inf')),atol=0)['status'],'invalid_numeric_output')
    def test_bool(self):self.assertEqual(compare(self.bound(),self.bound(value=True),atol=0)['status'],'invalid_numeric_output')
    def test_bad_tolerances(self):
        for v in (-1,float('nan'),float('inf'),True):
            with self.subTest(v=v):self.assertEqual(compare(self.bound(),self.bound(),atol=v)['status'],'invalid_tolerance')
    def test_outcomes_distinct(self):
        self.assertEqual(reproduction_outcome(self.bound(),self.bound(),atol=0)['outcome'],'PASS')
        self.assertEqual(reproduction_outcome(self.bound(),self.bound(value=2),atol=0)['outcome'],'FAIL')
        self.assertEqual(reproduction_outcome(self.bound(),self.bound(species='human'),atol=0)['outcome'],'INCOMPARABLE')

    def test_failed_incomparable_stays_incomparable(self):
        self.assertEqual(reproduction_outcome(self.bound(),self.bound(status='failed',species='human'),atol=0)['outcome'],'INCOMPARABLE')
    def test_missing_reference_stays_blocked(self):
        self.assertEqual(reproduction_outcome(self.bound(status='missing'),self.bound(status='failed'),atol=0)['outcome'],'BLOCKED')
