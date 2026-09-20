"""Synthetic artifacts only: ordering and fail-closed behavior, not physiology."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from experiments.sparc.contract import digest, execute


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Synthetic test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        self.inputs = {'input': b'synthetic input'}
        self.artifacts = {'model': b'synthetic model'}
        self.reference = b'synthetic reference output'
        self.environment = {'runtime': 'synthetic runtime v1', 'solvers': 'not applicable: synthetic byte callback'}
        self.contract = dict(profile='openbody.research-reproduction.v1',
            source=dict(identity='synthetic fixture', version='1', upstream_status='software test'),
            artifacts={'model': digest(self.artifacts['model'])}, inputs={'input': digest(self.inputs['input'])},
            model_version='synthetic 1', environment=self.environment,
            context={key: 'not applicable: synthetic software test' for key in
                     ('species','population_sample','anatomy','modality','device_electrode','parameters')},
            metric='synthetic byte identity', unit='not applicable: artifact bytes',
            reference_sha256=digest(self.reference),
            comparison=dict(method='exact_bytes', tolerance='zero', justification='Exact identity of the authenticated reference bytes'),
            provenance=['synthetic fixture; not upstream scientific evidence'],
            expected_outcomes=['PASS','FAIL','BLOCKED','INCOMPARABLE'])
        self.calls = 0
        self.commit()

    def git(self, *args):
        return subprocess.check_output(['git','-C',str(self.repo),*args], stderr=subprocess.DEVNULL).decode().strip()

    def commit(self):
        (self.repo/'contract.json').write_text(json.dumps(self.contract))
        self.git('add', 'contract.json')
        self.git('commit', '-qm', 'Declare synthetic comparison', '--allow-empty')
        self.sha = self.git('rev-parse','HEAD')

    def candidate(self, inputs):
        self.calls += 1
        self.assertEqual(inputs, self.inputs)
        # The contract already exists in Git when the callback is first invoked.
        self.assertEqual(json.loads(self.git('show',self.sha+':contract.json')),self.contract)
        return self.reference

    def invoke(self, **kw):
        args=dict(inputs=self.inputs, artifacts=self.artifacts, reference=self.reference,
                  environment=self.environment, run=self.candidate)
        args.update(kw)
        return execute(self.repo,'contract.json',self.sha,**args)

    def test_committed_before_invocation(self):
        r=self.invoke();self.assertEqual(r['outcome'],'PASS');self.assertEqual(self.calls,1)
        self.assertEqual(r['contract_commit'],self.sha);self.assertFalse(r['validated'])
    def test_no_commit_no_execution(self):
        self.sha=None;self.assertEqual(self.invoke()['outcome'],'BLOCKED');self.assertEqual(self.calls,0)
    def test_working_copy_tolerance_change_blocked(self):
        self.contract['comparison']['tolerance']='1%'
        (self.repo/'contract.json').write_text(json.dumps(self.contract))
        self.assertEqual(self.invoke()['outcome'],'BLOCKED');self.assertEqual(self.calls,0)
    def test_staged_change_blocked(self):
        (self.repo/'contract.json').write_text('{}');self.git('add','contract.json')
        self.assertEqual(self.invoke()['outcome'],'BLOCKED');self.assertEqual(self.calls,0)
    def test_committed_arbitrary_tolerance_blocked(self):
        self.contract['comparison']['tolerance']='1%';self.commit()
        self.assertEqual(self.invoke()['outcome'],'BLOCKED');self.assertEqual(self.calls,0)
    def test_unknown_context_blocked(self):
        self.contract['context']['species']='UNKNOWN';self.commit()
        self.assertEqual(self.invoke()['outcome'],'BLOCKED');self.assertEqual(self.calls,0)
    def test_missing_reference_blocks_before_execution(self):
        self.assertEqual(self.invoke(reference=None)['outcome'],'BLOCKED');self.assertEqual(self.calls,0)
    def test_wrong_reference_blocks_before_execution(self):
        self.assertEqual(self.invoke(reference=b'other')['outcome'],'BLOCKED');self.assertEqual(self.calls,0)
    def test_input_mismatch(self):
        self.assertEqual(self.invoke(inputs={'input':b'other'})['outcome'],'INCOMPARABLE');self.assertEqual(self.calls,0)
    def test_artifact_mismatch(self):
        self.assertEqual(self.invoke(artifacts={'model':b'other'})['outcome'],'INCOMPARABLE');self.assertEqual(self.calls,0)
    def test_runtime_mismatch(self):
        self.assertEqual(self.invoke(environment={'runtime':'other'})['outcome'],'INCOMPARABLE');self.assertEqual(self.calls,0)
    def test_failed_candidate(self):
        def fail(inputs): raise RuntimeError('sensitive log not retained')
        r=self.invoke(run=fail);self.assertEqual(r['outcome'],'FAIL');self.assertTrue(r['candidate_executed'])
        self.assertNotIn('sensitive',json.dumps(r))
    def test_missing_output_is_blocked(self):self.assertEqual(self.invoke(run=lambda _:None)['outcome'],'BLOCKED')
    def test_different_output_is_fail(self):self.assertEqual(self.invoke(run=lambda _:b'other')['outcome'],'FAIL')
    def test_unsupported_output_is_incomparable(self):self.assertEqual(self.invoke(run=lambda _:1.0)['outcome'],'INCOMPARABLE')
    def test_ascent_incomplete_gate_cannot_execute(self):
        self.contract=json.loads((Path(__file__).parent/'evidence/manifests/ascent-comparison-gate.json').read_text());self.commit()
        self.assertEqual(self.invoke()['outcome'],'BLOCKED');self.assertEqual(self.calls,0)
    def test_malformed_input_representation_blocked(self):
        self.assertEqual(self.invoke(inputs={'input':123})['outcome'],'BLOCKED');self.assertEqual(self.calls,0)
    def test_duplicate_keys_blocked(self):
        path=self.repo/'contract.json';path.write_text(path.read_text()[:-1]+',"profile":"openbody.research-reproduction.v1"}')
        self.git('add','contract.json');self.git('commit','-qm','Duplicate key');self.sha=self.git('rev-parse','HEAD')
        self.assertEqual(self.invoke()['outcome'],'BLOCKED');self.assertEqual(self.calls,0)
    def test_missing_binding_blocked(self):
        del self.contract['context']['modality'];self.commit()
        self.assertEqual(self.invoke()['outcome'],'BLOCKED');self.assertEqual(self.calls,0)
    def test_nan_tolerance_blocked(self):
        self.contract['comparison']['tolerance']=float('nan');self.commit()
        self.assertEqual(self.invoke()['outcome'],'BLOCKED');self.assertEqual(self.calls,0)
    def test_symlink_contract_blocked(self):
        path=self.repo/'contract.json';path.rename(self.repo/'target.json');path.symlink_to('target.json')
        self.git('add','.');self.git('commit','-qm','Symlink');self.sha=self.git('rev-parse','HEAD')
        self.assertEqual(self.invoke()['outcome'],'BLOCKED');self.assertEqual(self.calls,0)
    def test_nonancestor_contract_blocked(self):
        future=self.sha;self.git('checkout','--orphan','unrelated');self.git('rm','--cached','contract.json')
        self.git('commit','--allow-empty','-qm','unrelated')
        self.sha=future;self.assertEqual(self.invoke()['outcome'],'BLOCKED');self.assertEqual(self.calls,0)


class AdmissionExamples(unittest.TestCase):
    def test_examples_bind_frozen_evidence_without_qualification(self):
        root=Path(__file__).parent
        data=json.loads((root/'examples/admission.json').read_text())
        for example in data.values():
            self.assertIsNone(example['qualification_authority'])
            for key in ('model_qualification','context_qualification','clinical_validation','biological_validation','cymba_auricular_vns_qualification'):
                self.assertEqual(example[key],'NOT ESTABLISHED')
            for path in example['evidence']:self.assertTrue((root/path).is_file())
        queries=json.loads((root/'evidence/receipts/sckan-queries.json').read_text())
        self.assertEqual(len(queries),5)
        self.assertTrue(all(q['execution_status']==('VERIFIED' if q['query_id']=='missing-population' else 'REPRODUCED') for q in queries))
        self.assertTrue(all(q['result_sha256']==q['prior_execution']['result_sha256'] for q in queries))
        self.assertEqual(data['sckan']['bounded_reproduction'],'PASS')
        auth=json.loads((root/'evidence/receipts/sckan-artifacts.json').read_text())
        self.assertTrue(all(a['verification_result']=='VERIFIED' and a['observed_sha256']==a['expected_sha256'] for a in auth))
        gate=json.loads((root/'evidence/manifests/ascent-comparison-gate.json').read_text())
        self.assertEqual(data['ascent']['bounded_reproduction'],gate['status'])
        self.assertEqual(data['ascent']['candidate_executed'],gate['candidate_executed'])
        self.assertEqual(data['ascent']['study_uuid'],gate['study_uuid'])
        self.assertIsNone(gate['reference_output_sha256'])
