import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "research" / "sparc" / "release-watch.v1.json"

ALLOWED = {
    "anatomical_connectivity",
    "anatomical_variability",
    "simulated_recruitment",
    "measured_implanted_vns_response",
}

def load():
    return json.loads(MANIFEST.read_text())

def test_manifest_is_versioned_and_unique():
    data = load()
    assert data["schema_version"] == 1
    ids = [r["id"] for r in data["resources"]]
    assert len(ids) == len(set(ids))

def test_evidence_classes_are_explicit():
    for resource in load()["resources"]:
        assert resource["evidence_class"] in ALLOWED
        assert resource["qualification_state"]
        assert resource["limitations"]

def test_quiet_week_is_not_a_release():
    for resource in load()["resources"]:
        if not resource["material_update"]:
            assert resource["material_update_since"]

def test_sckan_prerelease_is_preserved():
    sckan = next(r for r in load()["resources"] if r["id"] == "sckan")
    assert sckan["release_status"] == "prerelease"
    assert sckan["evidence_class"] == "anatomical_connectivity"

def test_ascent_cannot_claim_measured_response():
    ascent = next(r for r in load()["resources"] if r["id"] == "ascent")
    assert ascent["evidence_class"] == "simulated_recruitment"
    assert ascent["qualification_state"] == "reproduction_blocked"

def test_vespa_is_scoped_to_implanted_vns():
    vespa = next(r for r in load()["resources"] if r["id"] == "vespa")
    assert vespa["evidence_class"] == "measured_implanted_vns_response"
    assert "auricular" in " ".join(vespa["limitations"]).lower()
