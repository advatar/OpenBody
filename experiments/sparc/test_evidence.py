"""Offline integrity checks for committed execution receipts, not live reruns."""
import hashlib
import json
import unittest
from pathlib import Path
from experiments.sparc.adapter import sparql_envelope
from experiments.sparc.authenticate import metadata_check
ROOT=Path(__file__).parent
E=ROOT/'evidence'
def read(p):return json.loads(p.read_text())

class EvidenceTests(unittest.TestCase):
    def test_release_metadata_matches_lock(self):
        metadata_check(read(ROOT/'upstream-lock.json')['sckan'],read(E/'manifests/sckan-release.json'))
    def test_artifacts_match_metadata(self):
        assets={a['name']:a for a in read(E/'manifests/sckan-release.json')['assets']}
        for r in read(E/'receipts/sckan-artifacts.json'):
            a=assets[r['asset']]
            self.assertEqual(r['observed_sha256'],a['digest'][7:])
            self.assertEqual(r['expected_sha256'],r['observed_sha256'])
            self.assertEqual(r['byte_count'],a['size'])
    def test_query_receipts_are_consistent(self):
        for r in read(E/'receipts/sckan-queries.json'):
            text=(ROOT/'queries'/(r['query_id']+'.rq')).read_bytes()
            self.assertEqual(text.decode(),r['query_text'])
            self.assertEqual(hashlib.sha256(text).hexdigest(),r['query_sha256'])
            result=sparql_envelope(r['canonical_result'])
            self.assertEqual(result['result_sha256'],r['result_sha256'])
            self.assertEqual(result['raw_row_count'],r['raw_row_count'])
            self.assertEqual(result['status'],r['status'])
    def test_repeat_digests_identical(self):
        def digests(name):return {r['query_id']:r['result_sha256'] for r in read(E/'receipts'/name)}
        self.assertEqual(digests('sckan-queries.json'),digests('sckan-queries-first-run.json'))
    def test_species_and_unknown(self):
        queries={r['query_id']:r for r in read(E/'receipts/sckan-queries.json')}
        self.assertEqual(queries['missing-population']['status'],'unknown')
        for row in queries['keast-5-rat']['canonical_result']['results']['bindings']:
            self.assertEqual(row['species']['value'],'http://purl.obolibrary.org/obo/NCBITaxon_10116')
    def test_ascent_does_not_claim_execution(self):
        gate=read(E/'manifests/ascent-comparison-gate.json')
        self.assertFalse(gate['candidate_executed'])
        self.assertEqual(gate['status'],'BLOCKED')
        self.assertIsNone(gate['atol'])
        self.assertIsNone(gate['reference_output_sha256'])
        self.assertNotEqual(gate['locked_study'],gate['deposited_study'])
    def test_ascent_failed_metadata_not_hidden(self):
        failures=[r for r in read(E/'receipts/ascent-artifacts.json') if r['status']=='FAILED']
        self.assertEqual([r['path'] for r in failures],['manifest.json'])
        self.assertNotEqual(failures[0]['size'],failures[0]['expected_size'])
