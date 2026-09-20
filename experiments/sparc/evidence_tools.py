"""Compact provenance and full-output verification without vendoring result dumps."""
import argparse
import hashlib
import json
from pathlib import Path
from .adapter import sparql_envelope


def external_directory(path):
    path = Path(path).resolve()
    repository = Path(__file__).resolve().parents[2]
    if path.is_relative_to(repository):
        raise ValueError('raw evidence output must be outside this repository')
    path.mkdir(parents=True, exist_ok=True)
    return path


def compact_result(record):
    """Retain exact identities/counts/digests and at most two typed regression rows."""
    result=sparql_envelope(record['canonical_result'])
    for key in ('result_sha256','raw_row_count','status'):
        if result[key] != record[key]:raise ValueError('inconsistent full result receipt')
    compact={k:v for k,v in record.items() if k not in ('canonical_result','query_text')}
    rows=result['canonical_result']['results']['bindings']
    compact['query_file']='queries/'+record['query_id']+'.rq'
    compact['variables']=result['canonical_result']['head']['vars']
    compact['selected_bindings']=rows[:2]
    compact['observed_species']=sorted({r['species']['value'] for r in rows if 'species' in r})
    compact['metadata_predicates']=sorted({r['metadata_predicate']['value'] for r in rows if 'metadata_predicate' in r})
    compact['selection_note']='First two canonical rows only; digest/count cover the complete external result, not these selected facts.'
    return compact


def verify_results(full, compact, query_dir):
    """Replaces bulk-fixture checks; run on external output, never on summary alone."""
    expected={r['query_id']:r for r in compact}
    observed={r['query_id']:r for r in full}
    if len(observed)!=len(full) or len(expected)!=len(compact) or observed.keys()!=expected.keys():
        raise ValueError('query set mismatch')
    for name,r in observed.items():
        baseline=expected[name]
        text=(query_dir/(name+'.rq')).read_bytes()
        if r['query_text'] != text.decode() or hashlib.sha256(text).hexdigest()!=r['query_sha256']:
            raise ValueError('query source mismatch')
        projected=compact_result(r)
        for key in ('query_sha256','result_sha256','raw_row_count','status','selected_bindings','variables','observed_species','metadata_predicates',
                    'source_artifact_sha256','journal_sha256','release','release_status','engine','engine_commit','engine_image','execution_status'):
            if projected[key]!=baseline[key]:raise ValueError(f'reproduction mismatch: {name}/{key}')
    return len(full)


def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);args=p.parse_args()
    root=Path(__file__).parent
    count=verify_results(json.loads(args.results.read_text()),json.loads((root/'evidence/receipts/sckan-queries.json').read_text()),root/'queries')
    print(f'PASS: all {count} external query results match the frozen receipts')

if __name__=='__main__':main()
