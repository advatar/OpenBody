"""Reference consumer mappings into the whole-person observation envelope (issue #30).

Each function maps one representative record shape from a downstream consumer
into an ``openbody.whole-person-observation/1.0`` envelope, or refuses it with a
stable :class:`MappingRefused` code. The functions are executable statements of
the mapping rules in ``docs/WHOLE_PERSON_STATE.md`` ("Consumer mapping"); the
consumers implement the same rules natively (Swift, Kotlin, Rust) and use
``fixtures/whole-person-state/v1/consumer-mapping.json`` as their shared vectors.

Consumers and the record shapes they are mapped from:

* Metabolog / InVivo (advatar/Metabolog #1129, #1144; merged #1131, #1145):
  ``HealthTimelineEntryRecord`` (SwiftData timeline), ``OpenBodyAdmittedObservation``
  (the admitted-observation.v1 document it validates), ``OpenBodyStateRecord``
  (M0 temporal state graph) and the M0 epistemic classes.
* ProvidEHR ambient evidence (advatar/ProvidEHR #600, PR #689): the
  ``longitudinal::Contribution`` of a reviewed clinical fact, with its
  ``SourceKey`` and ``CaptureConsent``.
* TwinSuite conversational adapter (advatar/TwinSuite #144): a conversation
  candidate (said / inferred / confirmed) whose raw custody stays in InVivo.

Rules shared by every mapper:

* Host context is supplied, never inferred: subject, verified binding, consent
  and authority references, ingestion time and clock status come from the
  custodian. A consumer's patient identifier is never used as the subject.
* ``record_ref`` is version-specific, so a correction revokes exactly the
  superseded version; ``source_id`` is the consumer's own conflict unit.
* Confidence, hedging, confirmation and review never become measurement
  uncertainty, measurement status or clinician validation.
* Anything the 1.0 envelope cannot represent without loss is refused, not
  approximated.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .whole_person import (
    CORPUS_DIR,
    OBSERVATION_VERSION,
    ConformanceResult,
    WholePersonStateError,
    assemble_state,
    canonical_digest,
    validate_observation,
    validate_state,
)

MAPPING_VERSION = "openbody.whole-person-consumer-mapping/1.0"
CONSUMER_MAPPING_NAME = "consumer-mapping.json"


class MappingRefused(ValueError):
    """A consumer record that the 1.0 envelope cannot carry without loss."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _refuse(code: str, message: str) -> None:
    raise MappingRefused(code, message)


def _base(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": OBSERVATION_VERSION,
        "subject": context["subject"],
        "subject_binding": copy.deepcopy(context["subject_binding"]),
    }


def _finish(envelope: dict[str, Any]) -> dict[str, Any]:
    validate_observation(envelope)
    return envelope


# ---------------------------------------------------------------------------
# Metabolog / InVivo
# ---------------------------------------------------------------------------

# InVivo M0 epistemic class -> (origin constraint, contract epistemic_status).
# ``observed`` in M0 covers both measurement and report; the origin decides.
METABOLOG_EPISTEMIC = {
    "observed": "observed_or_reported",
    "derived": "derived",
    "statistical_inference": "inferred",
    # Mechanistic inference is simulation/counterfactual output. It belongs to
    # the model-family contract (OpenBody #18/#19), not to observed state.
    "mechanistic_inference": None,
}

# Cymbathera evidence quality -> envelope quality. InVivo's derived
# ``confidence`` (1 / 0.5 / nil) is never carried as uncertainty.
METABOLOG_QUALITY = {"qualified": "acceptable", "limited": "degraded", "unknown": "unknown"}


def map_metabolog_epistemic_class(epistemic_class: str, origin: str) -> str:
    """Map an InVivo M0 epistemic class onto the contract's epistemic_status."""

    if epistemic_class not in METABOLOG_EPISTEMIC:
        _refuse("epistemic_class_unmapped", f"Unknown InVivo epistemic class {epistemic_class}")
    status = METABOLOG_EPISTEMIC[epistemic_class]
    if status is None:
        _refuse(
            "model_family_contract_required",
            "Mechanistic inference is a model output governed by the model-family contract",
        )
    if status == "observed_or_reported":
        return "reported" if origin in {"self_report", "conversation"} else "observed"
    return status


def map_metabolog_timeline_entry(record: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Map a ``HealthTimelineEntryRecord`` revision into an envelope.

    The SwiftData record is mutable (``updatedAt``), so the envelope names the
    revision: ``observation_id`` and ``record_ref`` carry ``updatedAt`` and
    ``record_digest`` is the canonical digest of the record as exported. The
    timeline's ``source`` string is an intake channel, not a device; the
    custodian supplies the real source identity in ``context['source']``.
    A value the person typed in (``manualReading``) is ``reported``, even for
    a glucose meter value; only device-provenanced samples are ``observed``.
    """

    concept = context["concepts"].get(record["kind"])
    if concept is None:
        _refuse("domain_unsupported", f"Timeline kind {record['kind']} has no 1.0 domain")
    revision = record["updatedAt"]
    record_ref = f"urn:invivo:timeline:{record['id']}:rev:{revision}"
    manual = context["entry_method"] == "manual"
    if record["kind"] == "symptom":
        symptom = record["payload"]["symptom"]
        code = context["symptom_codes"].get(symptom["kind"])
        if code is None:
            _refuse("concept_unmapped", f"Symptom {symptom['kind']} has no agreed code")
        measurement = {
            "domain": "symptom",
            "code": code,
            "value_type": "categorical",
            "value": context["severity_values"][str(symptom["severity"])],
            "unit": None,
        }
        origin = "self_report"
    else:
        if record.get("value") is None or record.get("unit") is None:
            _refuse("value_missing", "A quantity timeline entry needs value and unit")
        measurement = {
            "domain": concept["domain"],
            "code": concept["code"],
            "value_type": "quantity",
            "value": record["value"],
            "unit": record["unit"],
        }
        origin = "self_report" if manual else "device_sensor"
    envelope = _base(context)
    envelope.update(
        {
            "observation_id": f"invivo:timeline:{record['id']}:rev:{revision}",
            "scope": list(concept["scope"]),
            "source": {**copy.deepcopy(context["source"]), "record_ref": record_ref, "record_digest": canonical_digest(record)},
            "origin": origin,
            "epistemic_status": "reported" if origin == "self_report" else "observed",
            "context_level": "individual",
            "time": {
                "effective_start": record["timestamp"],
                "effective_end": None,
                "ingested_at": record["createdAt"],
                "clock": {"status": context["clock_status"]},
            },
            "measurement": measurement,
            "missingness": {"status": "present"},
            # The timeline carries no uncertainty; it stays unknown.
            "uncertainty": {"status": "unknown"},
            "quality": {"status": "unknown", "flags": []},
            "consent": copy.deepcopy(context["consent"]),
        }
    )
    return _finish(envelope)


def map_metabolog_admitted_observation(
    admitted: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    """Map the admitted-observation.v1 document InVivo holds into a linked envelope.

    The envelope references the admitted record (never copies its authority):
    ``clinical_link.admitted_observation_id`` and ``clinical_version_ref`` are
    the admitted ``id`` (already the immutable ``urn:openbody:observation:<version_uid>``),
    and ``content_digest`` is the canonical digest of the admitted document.
    The admitted uncertainty model (epistemic/aleatoric/coverage in [0, 1]) has
    no 1.0 envelope equivalent: all-null maps to ``unknown``; any number is
    refused rather than dropped.
    """

    if admitted.get("profile") != "openbody.admitted-observation.v1":
        _refuse("profile_unsupported", "Only openbody.admitted-observation.v1 can be linked")
    uncertainty = admitted["uncertainty"]
    if any(uncertainty[field] is not None for field in ("epistemic", "aleatoric", "coverage")):
        _refuse(
            "uncertainty_not_representable",
            "Admitted numeric uncertainty has no 1.0 envelope equivalent",
        )
    code = admitted["code"]
    concept = context["loinc_domains"].get(code["code"])
    if concept is None:
        _refuse("domain_unsupported", f"Admitted code {code['code']} has no agreed 1.0 domain")
    if admitted["effective_time"] is None:
        _refuse("time_missing", "An admitted observation without effective_time has no envelope time")
    source = admitted["source"]
    pack = admitted["normalization"]["rule_pack"]
    envelope = _base(context)
    envelope.update(
        {
            "observation_id": f"invivo:admitted:{admitted['id']}",
            "scope": list(concept["scope"]),
            "source": {
                "source_id": f"urn:providehr:source:{source['system']}:{source['clinical_version']['tenant_id']}",
                "source_kind": "ehr",
                "source_version": f"{pack['pack_id']}/{pack['version']}",
                "record_ref": admitted["id"],
                "record_digest": source["resource_digest"],
            },
            "origin": "clinical_record",
            "epistemic_status": "imported",
            "context_level": "individual",
            "time": {
                "effective_start": admitted["effective_time"],
                "effective_end": None,
                "ingested_at": context["ingested_at"],
                "clock": {"status": context["clock_status"]},
            },
            "measurement": {
                "domain": concept["domain"],
                "code": {"system": code["system"], "code": code["code"], "display": code["display"]},
                "value_type": "quantity",
                "value": admitted["quantity"]["value"],
                "unit": admitted["quantity"]["code"],
            },
            "missingness": {"status": "present"},
            "uncertainty": {"status": "unknown"},
            "quality": {"status": "acceptable" if not admitted["normalization"]["review_reasons"] else "degraded", "flags": []},
            "consent": copy.deepcopy(context["consent"]),
            "clinical_link": {
                "profile": "openbody.admitted-observation.v1",
                "admitted_observation_id": admitted["id"],
                "clinical_version_ref": admitted["id"],
                "content_digest": canonical_digest(admitted),
            },
        }
    )
    return _finish(envelope)


def map_metabolog_state_record(record: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """An M0 ``OpenBodyStateRecord`` is model state, not an observation.

    It names a model id/version and latent body-system domains, its evidence
    references carry no envelope digests, and ``confidence``/``uncertainty`` are
    unitless doubles. It is carried by the model-family contract (#18/#19);
    only its evidence observations become envelopes.
    """

    _refuse(
        "model_family_contract_required",
        f"PhysiologicalState {record['id']} ({record['modelID']}@{record['modelVersion']}) is model output",
    )
    return {}  # pragma: no cover


# ---------------------------------------------------------------------------
# ProvidEHR ambient evidence (#600 / PR #689)
# ---------------------------------------------------------------------------

PROVIDEHR_SUPPORTED_KINDS = {"symptom"}
PROVIDEHR_SCOPE_FIELDS = ("tenant_id", "data_controller")


def _urn_part(value: Any) -> str:
    """Percent-encode one URN component so that ':' inside it cannot merge two identities."""

    return quote(str(value), safe="-._~")


def _providehr_scope(source: dict[str, Any]) -> tuple[str, str]:
    missing = [field for field in PROVIDEHR_SCOPE_FIELDS if not source.get(field)]
    if missing:
        _refuse(
            "source_scope_missing",
            f"A ProvidEHR SourceKey needs explicit {' and '.join(missing)} scoping (decision 11)",
        )
    return str(source["tenant_id"]), str(source["data_controller"])


def providehr_source_id(source: dict[str, Any]) -> str:
    """Map a tenant- and controller-scoped ProvidEHR ``SourceKey`` to ``source_id``.

    ``source`` is the ``SourceKey`` (``clinical_system``, ``adapter_id``,
    ``connection_id``) together with the ``tenant_id`` and ``data_controller``
    that scope it. Without both scope fields the key is refused
    (``source_scope_missing``): the same key under two tenants or controllers is
    two different sources. Each component is percent-encoded.

    ``source_id`` is the conflict unit, but it is not the independence unit.
    Another adapter or connection that reaches the same underlying record still
    produces the same ``record_ref`` (see :func:`providehr_record_ref`) and the
    same source digest, so it never counts as independent corroboration
    (decision 11).
    """

    tenant, controller = _providehr_scope(source)
    return "urn:providehr:source:" + ":".join(
        _urn_part(part)
        for part in (tenant, controller, source["clinical_system"], source["adapter_id"], source["connection_id"])
    )


def providehr_record_ref(contribution: dict[str, Any]) -> str:
    """The underlying clinical record version, independent of adapter and connection.

    The reference is scoped by tenant, data controller and clinical system, and
    names the controller's own record identity (``source_record_type``,
    ``source_record_id``, ``source_version``). It never names the adapter or the
    connection that fetched the record, so every path to the same record yields
    the same ``record_ref``.
    """

    tenant, controller = _providehr_scope(contribution)
    return "urn:providehr:record:" + ":".join(
        _urn_part(part)
        for part in (
            tenant,
            controller,
            contribution["source"]["clinical_system"],
            contribution["source_record_type"],
            contribution["source_record_id"],
            contribution["source_version"],
        )
    )


def map_providehr_contribution(
    contribution: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    """Map one reviewed ``Contribution`` from the patient's own state.

    Family-history and unknown-subject facts (``family_history`` / ``unowned``)
    never become the subject's envelope. Only current symptoms map in 1.0;
    problems, medications, plans and the composite blood-pressure observation
    have no 1.0 domain. A patient's or clinician's spoken statement is
    ``reported`` from ``conversation`` even after clinician review: review
    attests what was said and admitted, not a measurement, and 1.0 only allows
    a validation receipt on ``clinician_validated``. Negation is the value
    (``absent``), hedging is a quality flag, never uncertainty.
    """

    if context["subject_role"] != "patient":
        _refuse("subject_not_patient", "Family-history or unknown-subject facts are not the subject's state")
    if contribution["kind"] not in PROVIDEHR_SUPPORTED_KINDS:
        _refuse("domain_unsupported", f"Claim kind {contribution['kind']} has no 1.0 domain")
    if contribution["temporality"] != "current":
        _refuse("temporality_unsupported", "Historical or planned statements have no 1.0 effective-time meaning")
    code = context["concept_codes"].get(contribution["concept"])
    if code is None:
        _refuse("concept_unmapped", f"Local concept {contribution['concept']} has no agreed code")
    purpose = context["purpose_map"].get(context["capture_consent"]["purpose"])
    if purpose is None:
        _refuse("purpose_unmapped", "Capture consent purpose has no whole-person purpose")
    scoped_source = {
        **contribution["source"],
        **{field: contribution.get(field) for field in PROVIDEHR_SCOPE_FIELDS},
    }
    source_id = providehr_source_id(scoped_source)
    record_ref = providehr_record_ref(contribution)
    envelope = _base(context)
    envelope.update(
        {
            "observation_id": f"providehr:fact:{contribution['fact_id']}",
            "scope": ["ob://human/whole_body"],
            "source": {
                "source_id": source_id,
                "source_kind": "ehr",
                "source_version": f"{contribution['vendor']}/{context['clinical_source_version']}",
                "record_ref": record_ref,
                "record_digest": f"sha256:{contribution['source_sha256']}",
            },
            "origin": "conversation",
            "epistemic_status": "reported",
            "context_level": "individual",
            "time": {
                "effective_start": contribution["clinical_time"],
                "effective_end": None,
                "ingested_at": contribution["recorded_at"],
                "clock": {"status": context["clock_status"]},
            },
            "measurement": {
                "domain": "symptom",
                "code": code,
                "value_type": "categorical",
                "value": "absent" if contribution["assertion"] == "negated" else "present",
                "unit": None,
            },
            "missingness": {"status": "present"},
            "uncertainty": {"status": "unknown"},
            "quality": {
                "status": "unknown",
                "flags": ["speaker_hedged"] if contribution["uncertain"] else [],
            },
            "consent": {
                "consent_ref": context["capture_consent"]["consent_ref"],
                "authority_ref": context["authority_ref"],
                "purposes": [purpose],
                "granted_at": context["capture_consent"]["captured_at"],
                "expires_at": None,
            },
        }
    )
    return _finish(envelope)


def providehr_revocations(sources: list[dict[str, Any]], consents: list[dict[str, Any]]) -> list[str]:
    """Host-resolved revocations from ProvidEHR source availability and consent.

    ``Revoked`` sources revoke their source_id; withdrawn capture consent
    revokes its consent_ref. Each source ``key`` carries its tenant and data
    controller scope, as :func:`providehr_source_id` requires. ``Unavailable``/``Withheld`` sources produce no
    envelopes; ``Stale`` sources still map and the assembler judges freshness.
    """

    revoked = {providehr_source_id(s["key"]) for s in sources if s["availability"]["availability"] == "revoked"}
    revoked |= {c["consent_ref"] for c in consents if c["withdrawn"]}
    return sorted(revoked)


# ---------------------------------------------------------------------------
# TwinSuite conversational adapter (#144)
# ---------------------------------------------------------------------------


def map_twinsuite_candidate(
    candidate: dict[str, Any],
    context: dict[str, Any],
    parent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map a TwinSuite conversation candidate held in InVivo custody.

    * ``said`` by the subject -> ``conversation`` / ``reported``;
    * ``confirmed`` by the subject -> still ``reported`` with the
      ``user_confirmed`` quality flag: confirmation is neither measurement nor
      clinician validation;
    * ``inferred`` (extractor output, e.g. a meal from free text) ->
      ``model_transform`` / ``inferred`` with the said envelope as a
      digest-bound derivation parent;
    * another or ambiguous speaker -> refused; the statement stays in custody;
    * a transcript correction is a new utterance revision with its own
      ``record_ref``; the host revokes the superseded revision.
    """

    if candidate["speaker"] != "subject":
        _refuse("speaker_not_subject", "Only the subject's own statements map to the subject's envelope")
    concept = context["concepts"].get(candidate["kind"])
    if concept is None:
        _refuse("domain_unsupported", f"Candidate kind {candidate['kind']} has no 1.0 domain")
    record_ref = f"urn:invivo:conversation:{candidate['utterance_id']}:rev:{candidate['utterance_revision']}"
    envelope = _base(context)
    envelope.update(
        {
            "observation_id": f"twinsuite:{candidate['utterance_id']}:rev:{candidate['utterance_revision']}:{candidate['assertion']}",
            "scope": list(concept["scope"]),
            "context_level": "individual",
            "time": {
                "effective_start": candidate["spoken_at"],
                "effective_end": None,
                "ingested_at": candidate["captured_at"],
                "clock": {"status": context["clock_status"]},
            },
            "measurement": {
                "domain": concept["domain"],
                "code": concept["code"],
                "value_type": "text",
                "value": candidate["text"],
                "unit": None,
            },
            "missingness": {"status": "present"},
            "uncertainty": {"status": "unknown"},
            "consent": copy.deepcopy(context["consent"]),
        }
    )
    if candidate["assertion"] in {"said", "confirmed"}:
        envelope.update(
            {
                "source": {
                    **copy.deepcopy(context["source"]),
                    "record_ref": record_ref,
                    "record_digest": canonical_digest(candidate["utterance"]),
                },
                "origin": "conversation",
                "epistemic_status": "reported",
                "quality": {
                    "status": "unknown",
                    "flags": ["user_confirmed"] if candidate["assertion"] == "confirmed" else [],
                },
            }
        )
    elif candidate["assertion"] == "inferred":
        if parent is None:
            _refuse("derivation_parent_missing", "An inferred candidate needs the said envelope as parent")
        extractor = candidate["extractor"]
        envelope.update(
            {
                "source": {
                    **copy.deepcopy(context["extractor_source"]),
                    "record_ref": f"urn:twinsuite:extraction:{candidate['utterance_id']}:rev:{candidate['utterance_revision']}",
                    "record_digest": canonical_digest(candidate),
                },
                "origin": "model_transform",
                "epistemic_status": "inferred",
                "quality": {"status": "unknown", "flags": []},
                "derivation": {
                    "transform_id": extractor["id"],
                    "transform_version": extractor["version"],
                    "parents": [
                        {"observation_id": parent["observation_id"], "envelope_digest": canonical_digest(parent)}
                    ],
                },
            }
        )
        envelope["measurement"] = copy.deepcopy(candidate["inferred_measurement"])
    else:
        _refuse("assertion_unsupported", f"Unknown candidate assertion {candidate['assertion']}")
    return _finish(envelope)


MAPPERS = {
    "metabolog.timeline_entry": map_metabolog_timeline_entry,
    "metabolog.admitted_observation": map_metabolog_admitted_observation,
    "metabolog.state_record": map_metabolog_state_record,
    "providehr.contribution": map_providehr_contribution,
    "twinsuite.candidate": map_twinsuite_candidate,
}


# ---------------------------------------------------------------------------
# Shared consumer-mapping corpus (fixtures/whole-person-state/v1)
# ---------------------------------------------------------------------------


def map_record(item: dict[str, Any], mapped: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Map one corpus record, resolving a named parent from earlier records."""

    mapper = MAPPERS[item["mapper"]]
    if item["mapper"] == "twinsuite.candidate":
        return mapper(item["record"], item["context"], mapped.get(item.get("parent", "")))
    return mapper(item["record"], item["context"])


def evaluate_consumer_mapping(corpus_dir: Path = CORPUS_DIR) -> list[ConformanceResult]:
    """Re-map every consumer record and re-assemble the cross-consumer snapshot."""

    corpus = json.loads((corpus_dir / CONSUMER_MAPPING_NAME).read_text(encoding="utf-8"))
    results: list[ConformanceResult] = []
    mapped: dict[str, dict[str, Any]] = {}
    envelopes: list[dict[str, Any]] = []
    for consumer in corpus["consumers"]:
        for item in consumer["records"]:
            name = f"{consumer['consumer']}/{item['name']}"
            expect = item["expect"]
            failures: list[str] = []
            try:
                envelope = map_record(item, mapped)
            except MappingRefused as refusal:
                detail = f"refused ({refusal.code})"
                if expect.get("refused") != refusal.code:
                    failures.append(f"expected {expect}, got {detail}")
            except WholePersonStateError as error:
                detail = f"invalid envelope ({error.code})"
                failures.append(f"mapper produced an invalid envelope: {error}")
            else:
                detail = f"{envelope['origin']}/{envelope['epistemic_status']}"
                mapped[item["name"]] = envelope
                envelopes.append(envelope)
                if expect.get("envelope") != envelope:
                    failures.append(f"mapped envelope differs from the fixture (expected {expect})")
            results.append(ConformanceResult(f"consumer-mapping {name}", failures, detail))

    assembly = corpus["assembly"]
    failures = []
    detail = ""
    try:
        snapshot = assemble_state(
            envelopes,
            subject=corpus["subject"],
            as_of=assembly["as_of"],
            purpose=assembly["purpose"],
            revoked=assembly["revoked"],
        )
        validate_state(snapshot)
    except WholePersonStateError as error:
        failures.append(f"cross-consumer assembly rejected: {error.code}: {error}")
    else:
        detail = snapshot["snapshot_digest"]
        expect = assembly["expect"]
        exclusions = {item["observation_id"]: item["code"] for item in snapshot["exclusions"]}
        if exclusions != expect["exclusions"]:
            failures.append(f"exclusions expected {expect['exclusions']}, got {exclusions}")
        entries = [
            {
                "domain": entry["key"]["domain"],
                "code": entry["key"]["code"],
                **({"dimension": entry["key"]["dimension"]} if "dimension" in entry["key"] else {}),
                "resolution": entry["resolution"],
                "basis": entry["basis"],
                "blockers": entry["clinical_use"]["blockers"],
            }
            for entry in snapshot["entries"]
        ]
        if entries != expect["entries"]:
            failures.append("cross-consumer entries differ from the fixture")
        if snapshot["snapshot_digest"] != expect["snapshot_digest"]:
            failures.append("cross-consumer snapshot digest differs from the fixture")
    results.append(ConformanceResult("consumer-mapping cross-consumer-assembly", failures, detail))
    failures = terminology_label_failures(corpus)
    results.append(
        ConformanceResult(
            "consumer-mapping terminology-labels",
            failures,
            f"{len(corpus.get('terminology', {}).get('tables', []))} tables labelled",
        )
    )
    return results


# Context keys that are source-to-contract terminology tables (decision 12).
TERMINOLOGY_TABLES = {"concepts", "symptom_codes", "severity_values", "loinc_domains", "concept_codes", "purpose_map"}
TERMINOLOGY_STATUSES = {"synthetic_unreviewed", "reviewed"}


def terminology_label_failures(corpus: dict[str, Any]) -> list[str]:
    """Every producer terminology table in the corpus carries an owner and a review label.

    A table stays ``synthetic_unreviewed`` until its owner reviews it. ``reviewed``
    needs a ``review_ref``. An unlabelled table fails the check, so a synthetic
    table cannot silently pass as reviewed terminology.
    """

    labels = {
        (label["consumer"], label["table"]): label
        for label in corpus.get("terminology", {}).get("tables", [])
    }
    failures: list[str] = []
    for consumer in corpus["consumers"]:
        used = sorted({key for item in consumer["records"] for key in item["context"] if key in TERMINOLOGY_TABLES})
        for table in used:
            label = labels.get((consumer["consumer"], table))
            if label is None:
                failures.append(f"{consumer['consumer']}.{table} has no terminology label")
            elif label.get("status") not in TERMINOLOGY_STATUSES or not label.get("owner"):
                failures.append(f"{consumer['consumer']}.{table} label needs an owner and a known status")
            elif label["status"] == "reviewed" and not label.get("review_ref"):
                failures.append(f"{consumer['consumer']}.{table} is marked reviewed without a review_ref")
    return failures
