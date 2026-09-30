from openbody_ref.mechanistic_pathway import pathway_evidence_summary, validate_pathway

def fixture():
 return {"profile":"openbody.mechanistic-pathway.v1","id":"path:exercise-klotho","revision":"1","generated_at":"2026-09-30T00:00:00Z",
 "nodes":[{"id":"exercise","kind":"intervention","label":"exercise"},{"id":"ev","kind":"molecule","label":"EV cargo"},{"id":"mir29","kind":"rna","label":"miR-29"},{"id":"kl","kind":"gene","label":"KL"},{"id":"klotho","kind":"protein","label":"alpha-Klotho"},{"id":"tissue","kind":"tissue_state","label":"tissue phenotype"}],
 "edges":[
 {"id":"e1","source":"exercise","target":"ev","claim_type":"intervention_response","context":{"species":"human","biological_scope":"circulation","population_ref":"synthetic"},"evidence":{"maturity":"interventional_human","provenance_refs":["synthetic:e1"]}},
 {"id":"e2","source":"ev","target":"mir29","claim_type":"association","context":{"species":"human","biological_scope":"circulation"},"evidence":{"maturity":"interventional_human","provenance_refs":["synthetic:e2"]}},
 {"id":"e3","source":"mir29","target":"kl","claim_type":"regulates","context":{"species":"human","biological_scope":"cell"},"evidence":{"maturity":"in_vitro_ex_vivo","provenance_refs":["synthetic:e3"]}},
 {"id":"e4","source":"kl","target":"klotho","claim_type":"activates","context":{"species":"human","biological_scope":"cell"},"evidence":{"maturity":"in_vitro_ex_vivo","provenance_refs":["synthetic:e4"]}},
 {"id":"e5","source":"klotho","target":"tissue","claim_type":"surrogate","context":{"species":"mouse","biological_scope":"tissue"},"evidence":{"maturity":"animal_in_vivo","provenance_refs":["synthetic:e5"]}}
 ]}

def test_mixed_evidence_path_is_limited_not_promoted():
 p=fixture(); s=pathway_evidence_summary(p)
 assert s["limiting_maturity"]=="in_vitro_ex_vivo"
 assert s["mixed_species"]
 assert not s["clinically_validated"]

def test_strengthening_one_edge_does_not_rewrite_other_edges():
 p=fixture(); old=p["edges"][2]["evidence"]["maturity"]
 p["revision"]="2"; p["edges"][0]["evidence"]["maturity"]="replicated_human"
 validate_pathway(p)
 assert p["edges"][2]["evidence"]["maturity"]==old

def test_unknown_node_is_rejected():
 import pytest
 p=fixture(); p["edges"][0]["target"]="missing"
 with pytest.raises(ValueError,match="unknown node"): validate_pathway(p)
