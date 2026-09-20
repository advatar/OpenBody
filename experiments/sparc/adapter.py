"""Fail-closed, research-only reader for pinned SCKAN exports."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

class IntegrityError(ValueError): pass

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1<<20), b""): h.update(b)
    return h.hexdigest()

def load_export(path: Path, expected_sha256: str|None=None) -> dict:
    if expected_sha256 and sha256(path)!=expected_sha256:
        raise IntegrityError("SCKAN export digest mismatch")
    data=json.loads(path.read_text())
    if not isinstance(data,dict) or not isinstance(data.get("edges"),list):
        raise ValueError("export must contain an edges array")
    for i,e in enumerate(data["edges"]):
        if not isinstance(e,dict) or not all(k in e for k in ("subject","predicate","object")):
            raise ValueError(f"edge {i} lacks subject/predicate/object")
    return data

def query(data: dict, *, subject=None, predicate=None, object_=None, species=None) -> list[dict]:
    out=[]
    for e in data["edges"]:
        if subject is not None and e["subject"]!=subject: continue
        if predicate is not None and e["predicate"]!=predicate: continue
        if object_ is not None and e["object"]!=object_: continue
        if species is not None and e.get("species")!=species: continue
        out.append(e)
    return out

def envelope(path: Path, *, expected_sha256=None, **filters) -> dict:
    data=load_export(path, expected_sha256)
    matches=query(data, **filters)
    return {
      "status":"ok" if matches else "unknown",
      "research_only":True,
      "source":{"path":str(path),"sha256":sha256(path),
                "upstream_version":data.get("upstream_version"),
                "upstream_authentication":data.get("upstream_authentication","unverified")},
      "query":filters, "matches":matches,
      "limitations":[
        "No inverse, transitive, anatomical, species, or signal-flow relation is inferred.",
        "Absence of a match is unknown coverage, not evidence that a connection is absent.",
        "A local digest establishes file integrity, not upstream authenticity."
      ]
    }

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("export",type=Path); p.add_argument("--sha256")
    p.add_argument("--subject"); p.add_argument("--predicate"); p.add_argument("--object",dest="object_")
    p.add_argument("--species")
    a=p.parse_args(argv)
    print(json.dumps(envelope(a.export,expected_sha256=a.sha256,subject=a.subject,
      predicate=a.predicate,object_=a.object_,species=a.species),sort_keys=True,indent=2))
if __name__=="__main__": main()


def sparql_envelope(data: dict) -> dict:
    """Keep typed native SPARQL bindings; never flatten OWL restrictions into edges.

    Blank-node labels are execution-local, so this bounded canonicalizer refuses
    them rather than pretending that arbitrary labels identify stable anatomy.
    """
    if not isinstance(data, dict) or not isinstance(data.get('head'), dict):
        raise ValueError('invalid SPARQL result head')
    variables = data['head'].get('vars')
    rows = data.get('results', {}).get('bindings')
    if not isinstance(variables, list) or not all(isinstance(v, str) for v in variables) or len(set(variables)) != len(variables) or not isinstance(rows, list):
        raise ValueError('invalid SPARQL SELECT result')
    for row in rows:
        if not isinstance(row, dict) or set(row) - set(variables):
            raise ValueError('invalid binding variables')
        for term in row.values():
            if not isinstance(term, dict) or term.get('type') not in ('uri', 'literal', 'typed-literal') or not isinstance(term.get('value'), str):
                raise ValueError('unsupported or malformed RDF term (including blank node)')
    encode = lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    canonical = {'head': {'vars': sorted(variables)}, 'results': {'bindings': sorted(rows, key=encode)}}
    raw = encode(canonical).encode('utf-8')
    return {'status': 'ok' if rows else 'unknown', 'research_only': True,
            'raw_row_count': len(rows), 'canonical_result': canonical,
            'result_sha256': hashlib.sha256(raw).hexdigest(),
            'limitations': ['Bindings are query results, not asserted direct connectivity edges.',
                           'OWL filler restrictions retain their native predicates; unsupported nested expressions require source inspection.',
                           'No inverse, transitive connectivity, signal direction, or clinical effect is inferred.']}
