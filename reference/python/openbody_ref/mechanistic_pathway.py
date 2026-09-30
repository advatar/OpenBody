from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from jsonschema import Draft202012Validator, FormatChecker

ROOT=Path(__file__).resolve().parents[3]
SCHEMA=json.loads((ROOT/"schemas"/"mechanistic-pathway.v1.schema.json").read_text())
VALIDATOR=Draft202012Validator(SCHEMA,format_checker=FormatChecker())
RANK={"synthetic":0,"in_vitro_ex_vivo":1,"animal_in_vivo":2,"observational_human":3,"interventional_human":4,"replicated_human":5,"clinically_validated":6}

def validate_pathway(value:Any)->None:
    errors=sorted(VALIDATOR.iter_errors(value),key=lambda e:list(e.absolute_path))
    if errors: raise ValueError(errors[0].message)
    ids=[n["id"] for n in value["nodes"]]
    if len(ids)!=len(set(ids)): raise ValueError("node ids must be unique")
    edge_ids=[e["id"] for e in value["edges"]]
    if len(edge_ids)!=len(set(edge_ids)): raise ValueError("edge ids must be unique")
    known=set(ids)
    if any(e["source"] not in known or e["target"] not in known for e in value["edges"]):
        raise ValueError("edge references unknown node")

def pathway_evidence_summary(value:dict)->dict:
    validate_pathway(value)
    limiting=min(value["edges"],key=lambda e:RANK[e["evidence"]["maturity"]])
    species=sorted({e["context"]["species"] for e in value["edges"]})
    return {
      "limiting_edge":limiting["id"],
      "limiting_maturity":limiting["evidence"]["maturity"],
      "mixed_species":len(species)>1,
      "species":species,
      "clinically_validated":all(e["evidence"]["maturity"]=="clinically_validated" for e in value["edges"]),
    }
