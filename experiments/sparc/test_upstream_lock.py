import json, pathlib, unittest
P=pathlib.Path(__file__).with_name("upstream-lock.json")
class LockTests(unittest.TestCase):
 def setUp(self): self.x=json.loads(P.read_text())
 def test_sckan_tag_pinned(self): self.assertEqual(self.x["sckan"]["tag"],"sckan-2026-06-23")
 def test_sckan_release_digest_pinned(self): self.assertEqual(len(self.x["sckan"]["sha256"]),64)
 def test_sckan_graph_digest_pinned(self): self.assertEqual(len(self.x["sckan"]["graph_sha256"]),64)
 def test_prerelease_explicit(self): self.assertEqual(self.x["sckan"]["release_status"],"prerelease")
 def test_ascent_doi_pinned(self): self.assertEqual(self.x["ascent_guided_mode_demo"]["doi"],"10.26275/0JZ3-ZRLO")
 def test_no_guessed_tolerance(self): self.assertIn("Do not set",self.x["ascent_guided_mode_demo"]["reference_output_gate"])
if __name__=="__main__": unittest.main()
