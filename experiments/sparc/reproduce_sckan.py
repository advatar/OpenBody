"""Execute the bounded research query set against an authenticated local journal."""
import argparse
import datetime
import hashlib
import json
import platform
import subprocess
import zipfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from .adapter import sparql_envelope, sha256
from .authenticate import verify

IMAGE = 'tgbugs/musl@sha256:0eca49ed3b0e0cb93145710ad7d587dc49868df16f63747559abaac5bda20897'

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--endpoint', default='http://127.0.0.1:19999/blazegraph/sparql')
    args = p.parse_args()
    if urllib.parse.urlparse(args.endpoint).hostname not in ('127.0.0.1', 'localhost'):
        raise ValueError('only local execution is supported')
    if args.endpoint != 'http://127.0.0.1:19999/blazegraph/sparql':
        raise ValueError('endpoint must match the inspected container port')
    root = Path(__file__).parent
    lock = json.loads((root/'upstream-lock.json').read_text())['sckan']
    verify(args.cache/lock['artifact'], lock['sha256'], lock['size_bytes'])
    journal = args.cache/'release'/lock['artifact'][:-4]/'data/blazegraph.jnl'
    with zipfile.ZipFile(args.cache/lock['artifact']) as archive:
        h = hashlib.sha256()
        with archive.open(lock['artifact'][:-4]+'/data/blazegraph.jnl') as stream:
            while block := stream.read(1 << 20): h.update(block)
    journal_digest = h.hexdigest()
    verify(journal, journal_digest, journal.stat().st_size)
    inspect = json.loads(subprocess.check_output(['docker','inspect','openbody-sparc-reproduction']))[0]
    if inspect['Config']['Image'] != IMAGE:
        raise ValueError('running engine image mismatch')
    ports = inspect['NetworkSettings']['Ports'].get('9999/tcp', [])
    if not any(p['HostIp']=='127.0.0.1' and p['HostPort']=='19999' for p in ports):
        raise ValueError('container endpoint port mismatch')
    mount = next(m for m in inspect['Mounts'] if m['Destination']=='/var/lib/blazegraph')
    mounted = Path(mount['Source'])/'blazegraph.jnl'
    verify(mounted, journal_digest, journal.stat().st_size)
    status = urllib.request.urlopen(args.endpoint.rsplit('/',1)[0]+'/status',timeout=30).read().decode()
    if '2.1.6-SNAPSHOT' not in status or '6b0c935523f5064b80279b30a5175a858cddd2a1' not in status:
        raise ValueError('engine version mismatch')
    receipts = []
    for path in sorted((root/'queries').glob('*.rq')):
        query = path.read_text()
        start = time.monotonic()
        receipt = dict(query_id=path.stem, query_text=query, query_language='SPARQL 1.1',
                       query_sha256=sha256(path), release=lock['tag'], release_status='prerelease',
                       source_artifact_sha256=lock['sha256'], journal_sha256=journal_digest,
                       engine='Blazegraph 2.1.6-SNAPSHOT', engine_commit='6b0c935523f5064b80279b30a5175a858cddd2a1',
                       engine_image=IMAGE, host_architecture=platform.machine(), execution_architecture='linux/amd64 (emulated)',
                       executed_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        try:
            req = urllib.request.Request(args.endpoint, urllib.parse.urlencode({'query':query}).encode(), headers={'Accept':'application/sparql-results+json'})
            raw = urllib.request.urlopen(req, timeout=120).read()
            envelope = sparql_envelope(json.loads(raw))
            receipt.update(envelope)
            receipt['execution_status'] = 'REPRODUCED' if envelope['raw_row_count'] else 'VERIFIED'
            receipt['interpretation'] = 'Executed pinned-release query; not agreement with a historical release result or biological validation.'
        except Exception as exc:
            receipt.update(execution_status='FAILED', error_type=type(exc).__name__)
        receipt['duration_seconds'] = round(time.monotonic()-start, 6)
        receipts.append(receipt)
        (root/'evidence/receipts/sckan-queries.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2)+'\n')
        print(path.stem,receipt['execution_status'],receipt.get('raw_row_count'),receipt.get('result_sha256'),flush=True)
    verify(mounted, journal_digest, journal.stat().st_size)
    if any(r['execution_status']=='FAILED' for r in receipts):
        raise SystemExit(1)

if __name__ == '__main__': main()
