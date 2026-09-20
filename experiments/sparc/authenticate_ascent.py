"""Retrieve public ASCENT metadata and bytes without executing a study.

Raw/reconstructable data is written only to an explicit external directory.
A failed size or digest check remains FAILED, even if later diagnosed upstream.
"""
import argparse
import base64
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import urllib.parse
import urllib.request
from .evidence_tools import external_directory

BASE = 'https://api.pennsieve.io/discover/datasets'
BUCKET = 'sparc-prod-aod-discover-publish50-use1'
MAX_BYTES = 10 * 1024 * 1024


def fetch(url):
    req = urllib.request.Request(url, headers={'Accept-Encoding': 'identity'})
    with urllib.request.urlopen(req, timeout=45) as response:
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('metadata retrieval exceeds bounded budget')
        headers = {k.lower(): v for k, v in response.headers.items() if k.lower() in (
            'content-length', 'content-type', 'content-encoding', 'etag', 'last-modified', 'x-amz-version-id')}
    return data, dict(url=url, retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      byte_count=len(data), sha256=hashlib.sha256(data).hexdigest(), headers=headers)


def object_url(dataset, entry):
    path = PurePosixPath(entry['path'])
    if path.is_absolute() or '..' in path.parts or not path.parts or '\\' in entry['path']:
        raise ValueError('unsafe upstream path')
    expected = f's3://{BUCKET}/{dataset}/{entry["path"]}'
    if entry['uri'] != expected:
        raise ValueError('unexpected upstream object location')
    return f'https://{BUCKET}.s3.amazonaws.com/{dataset}/{urllib.parse.quote(entry["path"])}?versionId={urllib.parse.quote(entry["s3Version"])}'


def file_check(entry, raw):
    expected = base64.b64decode(entry['sha256'], validate=True).hex()
    if len(expected) != 64:
        raise ValueError('invalid SHA-256 declaration')
    observed = hashlib.sha256(raw).hexdigest()
    return dict(path=entry['path'], expected_size=entry['size'], size=len(raw),
                expected_sha256=expected, observed_sha256=observed, object_version=entry['s3Version'],
                status='VERIFIED' if len(raw)==entry['size'] and observed==expected else 'FAILED')


def retrieve_dataset(dataset, output):
    output = external_directory(output)
    base = f'{BASE}/{dataset}/versions/1'
    raw, receipt = fetch(base)
    metadata = json.loads(raw)
    if metadata.get('id') != dataset or metadata.get('version') != 1:
        raise ValueError('dataset/version mismatch')
    (output/'dataset.json').write_bytes(raw)
    files, pages, seen = [], [], set()
    def walk(path=''):
        if path in seen or len(seen) >= 100:
            raise ValueError('repeated directory or directory budget exceeded')
        seen.add(path)
        data, page = fetch(base+'/files/browse?limit=100&path='+urllib.parse.quote(path))
        page_data = json.loads(data)
        if page_data['totalCount'] != len(page_data['files']) or page_data['totalCount'] > 100:
            raise ValueError('incomplete listing; pagination required')
        pages.append(page)
        for entry in page_data['files']:
            if entry['type']=='Directory': walk(entry['path'])
            else: files.append(entry)
    walk()
    if len(files) != metadata['fileCount']:
        raise ValueError('recursive listing differs from dataset fileCount')
    receipts = []
    for entry in files:
        data, retrieval = fetch(object_url(dataset, entry))
        checked = file_check(entry, data)
        target = output/entry['path']
        if not target.resolve().is_relative_to(output):
            raise ValueError('unsafe output path')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        receipts.append(dict(**checked, retrieval=retrieval))
    result = dict(dataset=dataset, version=1, doi=metadata['doi'], title=metadata['name'],
                  license=metadata['license'], version_published_at=metadata['versionPublishedAt'],
                  metadata_retrieval=receipt, listing_retrievals=pages, files=receipts)
    (output/'retrieval.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'file-list.json').write_text(json.dumps(files,indent=2)+'\n')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = retrieve_dataset(364, args.output)
    print(json.dumps(result,indent=2))
    if any(f['status']!='VERIFIED' for f in result['files']):
        raise SystemExit(1)

if __name__ == '__main__': main()
