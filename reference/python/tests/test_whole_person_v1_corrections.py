"""v1 correctness items from the owner's acceptance decision on #30 (tracked in #46).

1  canonical digest: language-independent spec + cross-language vectors
2  native validation: published vocabulary, fail closed
3  per-code categorical value sets; presence and severity are separate dimensions
8  validation after as_of; current revocation constrains present use
10 candidate placement against the source envelope
11 tenant/controller-scoped SourceKey and the independence rule
12 synthetic terminology labels
"""

from __future__ import annotations

import copy
import json
import math
import random
import struct
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from openbody_ref import canonical_json, whole_person
from openbody_ref.schema_keywords import schema_vocabulary
from openbody_ref.validation import canonical_digest as legacy_digest
from openbody_ref.whole_person import (
    CORPUS_DIR,
    OBSERVATION_SCHEMA_PATH,
    STATE_SCHEMA_PATH,
    WholePersonStateError,
    assemble_state,
    load_value_sets,
    present_use,
    require_present_use,
    validate_observation,
    validate_state,
    verify_state_against_inputs,
)
from openbody_ref.whole_person_mapping import (
    MappingRefused,
    map_record,
    providehr_record_ref,
    providehr_source_id,
    terminology_label_failures,
)

ROOT = Path(__file__).resolve().parents[3]
VECTORS = json.loads((CORPUS_DIR / "canonical-digest-vectors.json").read_text(encoding="utf-8"))
NATIVE = json.loads((CORPUS_DIR / "native-validation.json").read_text(encoding="utf-8"))
INPUTS = json.loads((CORPUS_DIR / "inputs.json").read_text(encoding="utf-8"))
GOLDEN = json.loads((CORPUS_DIR / "snapshot.golden.json").read_text(encoding="utf-8"))
MAPPING = json.loads((CORPUS_DIR / "consumer-mapping.json").read_text(encoding="utf-8"))
INTEROP = json.loads((CORPUS_DIR / "interop-vectors.json").read_text(encoding="utf-8"))


def assemble(envelopes, **params):
    return assemble_state(
        envelopes,
        subject=params.get("subject", INPUTS["subject"]),
        as_of=params.get("as_of", INPUTS["as_of"]),
        purpose=params.get("purpose", INPUTS["purpose"]),
        revoked=params.get("revoked", INPUTS["revoked"]),
    )


def envelope(observation_id):
    return copy.deepcopy(next(e for e in INPUTS["envelopes"] if e["observation_id"] == observation_id))


def pointer(document, path):
    for part in [p for p in path.split("/")[1:]]:
        document = document[int(part)] if isinstance(document, list) else document[part]
    return document


# ---------------------------------------------------------------------------
# 1. Canonical digest
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vector", VECTORS["positive"], ids=lambda v: v["name"])
def test_positive_digest_vectors_reproduce(vector):
    value = canonical_json.parse(vector["wire"])
    assert canonical_json.canonical_text(value) == vector["canonical"]
    assert canonical_json.canonical_bytes(value).hex() == vector["canonical_utf8_hex"]
    assert canonical_json.digest(value) == vector["digest"]
    # The pinned v1 algorithm (Python json) gives the same bytes: the spec does
    # not change v1, it only states it.
    assert legacy_digest(json.loads(vector["wire"])) == vector["digest"]


@pytest.mark.parametrize("vector", VECTORS["negative"], ids=lambda v: v["name"])
def test_negative_digest_vectors_fail_closed(vector):
    wire = bytes.fromhex(vector["wire_hex"]) if "wire_hex" in vector else vector["wire"]
    with pytest.raises(canonical_json.CanonicalDomainError) as refused:
        canonical_json.parse(wire)
    assert refused.value.code == vector["error"]


@pytest.mark.parametrize("vector", VECTORS["corpus"]["vectors"], ids=lambda v: v["name"])
def test_corpus_digest_vectors(vector):
    document = json.loads((ROOT / vector["file"]).read_text(encoding="utf-8"))
    value = pointer(document, vector["pointer"]) if vector["pointer"] else document
    assert canonical_json.digest(value) == vector["digest"]


def test_earlier_interop_digest_vectors_still_hold():
    for vector in INTEROP["canonical_digest"]["vectors"]:
        assert canonical_json.digest_wire(vector["wire"]) == vector["digest"]


def test_spec_float_rule_matches_the_pinned_algorithm_on_random_doubles():
    rng = random.Random(30)
    samples = [0.1, 1e16, 1e15, 1e-5, 1e-4, 5e-324, 1.7976931348623157e308, -0.0, 0.0]
    while len(samples) < 20000:
        value = struct.unpack("<d", struct.pack("<Q", rng.getrandbits(64)))[0]
        if math.isfinite(value):
            samples.append(value)
    for value in samples:
        assert canonical_json.format_double(value) == repr(value)


def test_strict_digest_equals_pinned_digest_over_the_whole_corpus():
    documents = [INPUTS, GOLDEN, MAPPING, NATIVE, VECTORS]
    documents += [json.loads(p.read_text(encoding="utf-8")) for p in (OBSERVATION_SCHEMA_PATH, STATE_SCHEMA_PATH)]
    for document in documents:
        assert canonical_json.digest(document) == legacy_digest(document)
    for item in INPUTS["envelopes"]:
        assert whole_person.envelope_digest(item) == legacy_digest(item)


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (float("nan"), "non_finite_number"),
        (float("inf"), "non_finite_number"),
        (2**53, "integer_out_of_range"),
        ("\ud800", "lone_surrogate"),
        ({1: "x"}, "non_string_key"),
        ((1, 2), "unsupported_type"),
    ],
)
def test_out_of_domain_values_are_refused(value, code):
    with pytest.raises(canonical_json.CanonicalDomainError) as refused:
        canonical_json.digest({"v": value})
    assert refused.value.code == code


def test_whole_person_digest_fails_closed_on_out_of_domain_values():
    with pytest.raises(WholePersonStateError) as refused:
        whole_person.canonical_digest({"value": float("nan")})
    assert refused.value.code == "canonical_domain_violation"


def test_spec_is_published_next_to_the_vectors():
    spec = (ROOT / VECTORS["specification"]).read_text(encoding="utf-8")
    assert VECTORS["algorithm"] == canonical_json.ALGORITHM == "openbody.canonical-digest/1"
    assert canonical_json.ALGORITHM in spec
    for code in {v["error"] for v in VECTORS["negative"]}:
        assert f"`{code}`" in spec


# ---------------------------------------------------------------------------
# 2. Native validation vocabulary
# ---------------------------------------------------------------------------


def _schemas():
    observation = json.loads(OBSERVATION_SCHEMA_PATH.read_text(encoding="utf-8"))
    state = json.loads(STATE_SCHEMA_PATH.read_text(encoding="utf-8"))
    return observation, state


def test_published_vocabulary_is_exactly_what_the_schemas_use():
    observation, state = _schemas()
    used_o, used_s = schema_vocabulary(observation), schema_vocabulary(state)
    assert NATIVE["per_schema"] == {"whole-person-observation": used_o, "whole-person-state": used_s}
    for kind in ("keywords", "formats", "refs"):
        assert NATIVE["required_vocabulary"][kind] == sorted(set(used_o[kind]) | set(used_s[kind]))
    patterns = set()

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("pattern"), str):
                patterns.add(node["pattern"])
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(observation)
    walk(state)
    assert NATIVE["patterns"] == sorted(patterns)
    for keyword in NATIVE["required_vocabulary"]["keywords"]:
        if keyword not in {"$defs", "$id", "$schema", "title", "description", "properties", "required", "items"}:
            assert any(keyword in key for key in NATIVE["semantics"]) or keyword in json.dumps(NATIVE["semantics"])


def _apply(instance, operations):
    instance = copy.deepcopy(instance)
    for operation in operations:
        parts = [p.replace("~1", "/").replace("~0", "~") for p in operation["path"][1:].split("/")]
        parent = instance
        for part in parts[:-1]:
            parent = parent[int(part)] if isinstance(parent, list) else parent[part]
        key = int(parts[-1]) if isinstance(parent, list) else parts[-1]
        if operation["op"] == "set":
            parent[key] = copy.deepcopy(operation["value"])
        else:
            del parent[key]
    return instance


@pytest.mark.parametrize(
    "case",
    NATIVE["cases"]["observation"] + NATIVE["cases"]["state"],
    ids=lambda c: c["name"],
)
def test_native_validation_cases(case):
    observation, state = _schemas()
    registry = Registry().with_resource(observation["$id"], Resource.from_contents(observation))
    if case["schema"] == observation["$id"]:
        base = envelope(case["base"]["observation_id"])
        validator = Draft202012Validator(observation, format_checker=FormatChecker())
    else:
        base = GOLDEN
        validator = Draft202012Validator(state, registry=registry, format_checker=FormatChecker())
    instance = _apply(base, case["operations"])
    assert (not list(validator.iter_errors(instance))) is case["valid"]


def test_every_required_keyword_and_format_is_exercised_by_a_case():
    exercised = {k for c in NATIVE["cases"]["observation"] + NATIVE["cases"]["state"] for k in c["exercises"]}
    assertions = set(NATIVE["required_vocabulary"]["keywords"]) - {
        "$defs", "$id", "$ref", "$schema", "title", "description", "properties", "items", "format",
    }
    missing = sorted(k for k in assertions if k not in exercised)
    assert missing == []
    for fmt in NATIVE["required_vocabulary"]["formats"]:
        assert f"format:{fmt}" in exercised
    assert "$ref:external" in exercised


def test_reference_refuses_a_schema_keyword_outside_the_vocabulary(monkeypatch):
    observation, _ = _schemas()
    widened = copy.deepcopy(observation)
    widened["$defs"]["Digest"]["contentEncoding"] = "base16"
    with pytest.raises(WholePersonStateError) as refused:
        whole_person._require_supported_vocabulary(widened, FormatChecker())
    assert refused.value.code == "schema_vocabulary_unsupported"


def test_reference_refuses_a_format_without_a_checker():
    observation, _ = _schemas()
    checker = FormatChecker()
    checker.checkers.pop("uri")
    with pytest.raises(WholePersonStateError) as refused:
        whole_person._require_supported_vocabulary(observation, checker)
    assert refused.value.code == "schema_vocabulary_unsupported"


def test_rfc3339_lowercase_is_parsed_and_garbage_is_a_stable_error():
    item = envelope("wp-cgm-001")
    item["time"]["ingested_at"] = "2026-09-20t07:55:00z"
    validate_observation(item)
    with pytest.raises(WholePersonStateError) as refused:
        whole_person._time("not a time")
    assert refused.value.code == "structural_invalid"


# ---------------------------------------------------------------------------
# 3. Value sets
# ---------------------------------------------------------------------------


def test_value_sets_are_owned_labelled_and_consistent():
    document = json.loads((ROOT / "registry" / "whole-person-value-sets.json").read_text(encoding="utf-8"))
    assert document["owner"].startswith("OpenBody")
    assert document["review_status"] == "unreviewed"
    value_sets = load_value_sets()
    for item in value_sets.values():
        seen = [v for values in item["dimensions"].values() for v in values]
        assert len(seen) == len(set(seen))
    symptom_codes = [k for k, v in value_sets.items() if v["domain"] == "symptom"]
    assert symptom_codes
    for key in symptom_codes:
        assert set(value_sets[key]["dimensions"]) == {"presence", "severity"}


def test_overlapping_dimensions_are_rejected(tmp_path):
    document = json.loads((ROOT / "registry" / "whole-person-value-sets.json").read_text(encoding="utf-8"))
    document["codes"][0]["dimensions"]["severity"].append("present")
    path = tmp_path / "value-sets.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(WholePersonStateError) as refused:
        load_value_sets(path)
    assert refused.value.code == "value_sets_invalid"


def test_every_categorical_value_in_the_corpora_has_a_value_set():
    value_sets = load_value_sets()
    envelopes = list(INPUTS["envelopes"])
    for consumer in MAPPING["consumers"]:
        envelopes += [item["expect"]["envelope"] for item in consumer["records"] if "envelope" in item["expect"]]
    categorical = [e for e in envelopes if e["measurement"]["value_type"] == "categorical"]
    assert categorical
    for item in categorical:
        measurement = item["measurement"]
        value_set = value_sets[(measurement["code"]["system"], measurement["code"]["code"])]
        assert any(measurement["value"] in values for values in value_set["dimensions"].values())


def test_snapshot_pins_the_value_sets():
    assert GOLDEN["contract"]["value_sets_version"] == "openbody.whole-person-value-sets/1.0"
    assert GOLDEN["contract"]["value_sets_digest"] == whole_person.value_sets_digest()


# ---------------------------------------------------------------------------
# 8. Time and revocation
# ---------------------------------------------------------------------------


def test_validation_after_as_of_is_excluded_and_rejected_in_state():
    lab = envelope("wp-lab-glucose-001")
    lab["validation"]["validated_at"] = "2026-09-20T08:00:01Z"
    snapshot = assemble([lab])
    assert snapshot["exclusions"][0]["code"] == "validation_after_as_of"
    tampered = copy.deepcopy(GOLDEN)
    for entry in tampered["entries"]:
        for candidate in entry["candidates"]:
            if candidate["validation"]:
                candidate["validation"]["validated_at"] = "2026-09-20T08:00:01Z"
    tampered.pop("snapshot_digest")
    tampered["snapshot_digest"] = whole_person.canonical_digest(tampered)
    with pytest.raises(WholePersonStateError) as refused:
        validate_state(tampered)
    assert refused.value.code == "validation_after_as_of"


def test_present_use_applies_current_revocations_to_a_historical_snapshot():
    historical = assemble(INPUTS["envelopes"])
    assert present_use(historical, INPUTS["envelopes"], [])["usable"] is True
    report = present_use(historical, INPUTS["envelopes"], ["urn:invivo:record:ring-a:hrv-2026-09-19"])
    assert report["affected"] == {"wp-hrv-001": "source_revoked", "wp-hrv-baseline-001": "derivation_parent_revoked"}
    assert {k["code"] for k in report["basis_affected"]} == {"80404-7", "hrv-sdnn-nocturnal-baseline"}
    with pytest.raises(WholePersonStateError) as refused:
        require_present_use(historical, INPUTS["envelopes"], ["urn:invivo:record:ring-a:hrv-2026-09-19"])
    assert refused.value.code == "revoked_since_snapshot"
    # The historical snapshot itself is unchanged: present use does not re-date it.
    assert historical == assemble(INPUTS["envelopes"])


def test_present_use_does_not_redate_time_or_purpose():
    # A consent that has expired by now is not a revocation. Present use applies
    # only the revocation set; consent windows were judged at as_of.
    historical = assemble(INPUTS["envelopes"])
    assert present_use(historical, INPUTS["envelopes"], ["urn:unrelated:ref"])["usable"] is True


# ---------------------------------------------------------------------------
# 10. Placement against the source envelope
# ---------------------------------------------------------------------------


def test_golden_and_cross_consumer_snapshots_verify_against_their_envelopes():
    verify_state_against_inputs(GOLDEN, INPUTS["envelopes"])
    mapped, envelopes = {}, []
    for consumer in MAPPING["consumers"]:
        for item in consumer["records"]:
            try:
                result = map_record(item, mapped)
            except MappingRefused:
                continue
            mapped[item["name"]] = result
            envelopes.append(result)
    assembly = MAPPING["assembly"]
    snapshot = assemble_state(
        envelopes, subject=MAPPING["subject"], as_of=assembly["as_of"], purpose=assembly["purpose"], revoked=assembly["revoked"]
    )
    verify_state_against_inputs(snapshot, envelopes)


def test_swapped_candidates_between_entries_are_misplaced():
    # Swap the single candidates of two single-source quantity entries whose
    # values and freshness policies make the swap internally consistent.
    tampered = copy.deepcopy(GOLDEN)
    keys = {entry["key"]["code"]: entry for entry in tampered["entries"]}
    sleep, hrv = keys["93832-4"], keys["80404-7"]
    sleep["key"], hrv["key"] = hrv["key"], sleep["key"]
    tampered.pop("snapshot_digest")
    tampered["snapshot_digest"] = whole_person.canonical_digest(tampered)
    validate_state(tampered)  # a snapshot alone cannot tell
    with pytest.raises(WholePersonStateError) as refused:
        verify_state_against_inputs(tampered, INPUTS["envelopes"])
    assert refused.value.code == "candidate_misplaced"


# ---------------------------------------------------------------------------
# 11. Source identity and independence
# ---------------------------------------------------------------------------


def _providehr_item(name="ambient-symptom-present"):
    consumer = next(c for c in MAPPING["consumers"] if c["consumer"] == "providehr")
    return copy.deepcopy(next(item for item in consumer["records"] if item["name"] == name))


def test_same_local_ids_in_two_tenants_are_distinct_records_and_sources():
    first = _providehr_item()
    second = _providehr_item()
    second["record"]["tenant_id"] = "tenant-2"
    second["record"]["fact_id"] = "fact-t2-0001"
    second["record"]["source_sha256"] = "5" * 64
    a, b = map_record(first, {}), map_record(second, {})
    assert a["source"]["source_id"] != b["source"]["source_id"]
    assert a["source"]["record_ref"] != b["source"]["record_ref"]
    snapshot = assemble_state([a, b], subject=MAPPING["subject"], as_of="2026-09-20T08:00:00Z", purpose="encounter_context")
    entry = next(e for e in snapshot["entries"] if e["key"]["code"] == "404640003")
    assert entry["resolution"] == "concordant"


def test_same_record_through_another_connection_is_not_a_second_source():
    first = _providehr_item()
    second = _providehr_item()
    second["record"]["source"]["connection_id"] = "conn-2"
    second["record"]["fact_id"] = "fact-conn2-0001"
    a, b = map_record(first, {}), map_record(second, {})
    assert a["source"]["record_ref"] == b["source"]["record_ref"]
    assert a["source"]["source_id"] != b["source"]["source_id"]
    with pytest.raises(WholePersonStateError) as refused:
        assemble_state([a, b], subject=MAPPING["subject"], as_of="2026-09-20T08:00:00Z", purpose="encounter_context")
    assert refused.value.code == "source_identity_conflict"


def test_same_source_bytes_under_another_record_ref_do_not_corroborate():
    first = _providehr_item()
    second = _providehr_item()
    second["record"]["source"]["adapter_id"] = "legacy-journal"
    second["record"]["source_record_type"] = "DocumentReference"
    second["record"]["fact_id"] = "fact-legacy-0001"
    a, b = map_record(first, {}), map_record(second, {})
    assert a["source"]["record_digest"] == b["source"]["record_digest"]
    snapshot = assemble_state([a, b], subject=MAPPING["subject"], as_of="2026-09-20T08:00:00Z", purpose="encounter_context")
    entry = next(e for e in snapshot["entries"] if e["key"]["code"] == "404640003")
    assert entry["resolution"] == "single_source"
    assert len(entry["basis"]) == 2


def test_scope_components_cannot_collide_through_separators():
    base = {"clinical_system": "s", "adapter_id": "a", "connection_id": "c"}
    left = providehr_source_id(dict(base, tenant_id="t:x", data_controller="y"))
    right = providehr_source_id(dict(base, tenant_id="t", data_controller="x:y"))
    assert left != right
    contribution = _providehr_item()["record"]
    assert providehr_record_ref(contribution).startswith("urn:providehr:record:tenant-1:region-x:")


# ---------------------------------------------------------------------------
# 12. Terminology labels
# ---------------------------------------------------------------------------


def test_every_producer_terminology_table_is_labelled_synthetic():
    assert terminology_label_failures(MAPPING) == []
    assert {t["status"] for t in MAPPING["terminology"]["tables"]} == {"synthetic_unreviewed"}


def test_an_unlabelled_or_unevidenced_table_fails():
    corpus = copy.deepcopy(MAPPING)
    corpus["terminology"]["tables"] = [t for t in corpus["terminology"]["tables"] if t["table"] != "concept_codes"]
    assert terminology_label_failures(corpus) == ["providehr.concept_codes has no terminology label"]
    corpus = copy.deepcopy(MAPPING)
    corpus["terminology"]["tables"][0]["status"] = "reviewed"
    assert terminology_label_failures(corpus) == ["metabolog.concepts is marked reviewed without a review_ref"]


# ---------------------------------------------------------------------------
# Frozen v1 baseline
# ---------------------------------------------------------------------------


def test_frozen_manifest_pins_the_corrected_v1_baseline():
    assert whole_person.frozen_manifest_failures() == []
    manifest = json.loads((CORPUS_DIR / "frozen-manifest.json").read_text(encoding="utf-8"))
    pinned = {item["path"] for item in manifest["files"]}
    for required in (
        "schemas/whole-person-observation.schema.json",
        "schemas/whole-person-state.schema.json",
        "registry/whole-person-value-sets.json",
        "docs/CANONICAL_DIGEST_V1.md",
        "fixtures/whole-person-state/v1/canonical-digest-vectors.json",
        "fixtures/whole-person-state/v1/native-validation.json",
        "fixtures/whole-person-state/v1/snapshot.golden.json",
        "fixtures/whole-person-state/v1/vectors.json",
    ):
        assert required in pinned
    assert manifest["golden_snapshot_digest"] == GOLDEN["snapshot_digest"]


def test_frozen_manifest_detects_a_changed_artifact(tmp_path):
    manifest = json.loads((CORPUS_DIR / "frozen-manifest.json").read_text(encoding="utf-8"))
    manifest["files"][0]["sha256"] = "0" * 64
    path = tmp_path / "frozen-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    failures = whole_person.frozen_manifest_failures(path)
    assert len(failures) == 1 and "changed after the v1 freeze" in failures[0]
