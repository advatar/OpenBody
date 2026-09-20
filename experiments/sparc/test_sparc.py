import hashlib,json,tempfile,unittest
from pathlib import Path
from adapter import IntegrityError,envelope,load_export,query
from benchmark import compare

class SparcTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory(); self.p=Path(self.t.name)/"s.json"
  self.data={"upstream_version":"test","edges":[
   {"subject":"n1","predicate":"travelsVia","object":"vagus","species":"human","citation":"doi:x"},
   {"subject":"n1","predicate":"locatedInPartOf","object":"heart","species":"human"}]}
  self.p.write_text(json.dumps(self.data))
  self.digest=hashlib.sha256(self.p.read_bytes()).hexdigest()
 def tearDown(self): self.t.cleanup()
 def test_digest(self): self.assertEqual(load_export(self.p,self.digest)["upstream_version"],"test")
 def test_bad_digest_fails(self):
  with self.assertRaises(IntegrityError): load_export(self.p,"0"*64)
 def test_exact_query(self): self.assertEqual(len(query(self.data,object_="vagus",species="human")),1)
 def test_no_inverse_inference(self): self.assertEqual(query(self.data,subject="vagus"),[])
 def test_unknown_is_explicit(self): self.assertEqual(envelope(self.p,subject="missing")["status"],"unknown")
 def test_auth_unverified(self): self.assertEqual(envelope(self.p)["source"]["upstream_authentication"],"unverified")
 def test_relation_preserved(self): self.assertEqual(query(self.data,predicate="locatedInPartOf")[0]["predicate"],"locatedInPartOf")
 def bound(self,v,status="ok",**kw):
  d=dict(model="ascent",artifact="a",inputs="i",dataset_version="d",species="human",
         modality="implanted-cervical-vns",metric="threshold",unit="mA",value=v,status=status); d.update(kw); return d
 def test_compare_pass(self):
  x=compare(self.bound(1),self.bound(1.01),atol=.02); self.assertEqual(x["status"],"pass"); self.assertFalse(x["validated"])
 def test_compare_fail(self): self.assertEqual(compare(self.bound(1),self.bound(2),atol=.02)["status"],"fail")
 def test_species_mismatch(self): self.assertEqual(compare(self.bound(1),self.bound(1,species="pig"),atol=.1)["status"],"incomparable")
 def test_modality_mismatch(self): self.assertEqual(compare(self.bound(1),self.bound(1,modality="auricular"),atol=.1)["status"],"incomparable")
 def test_failed_output_visible(self): self.assertEqual(compare(self.bound(1),self.bound(1,status="failed"),atol=.1)["status"],"not_compared")
 def test_nan_rejected(self): self.assertEqual(compare(self.bound(1),self.bound(float("nan")),atol=.1)["status"],"invalid_numeric_output")
if __name__=="__main__": unittest.main()
