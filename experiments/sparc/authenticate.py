"""Authenticate release bytes before bounded extraction; no upstream code execution."""
import argparse
import datetime
import json
import platform
import shutil
import stat
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from .adapter import IntegrityError, sha256
from .evidence_tools import external_directory


def metadata_check(lock, release):
    for key, expected in (("tag_name", lock["tag"]), ("prerelease", lock["release_status"] == "prerelease"), ("published_at", lock["published_at"])):
        if release.get(key) != expected:
            raise IntegrityError(f"release metadata mismatch: {key}")
    assets = []
    for prefix in ("", "graph_"):
        found = [a for a in release["assets"] if a["name"] == lock[prefix + "artifact"]]
        if len(found) != 1:
            raise IntegrityError("missing or duplicate asset")
        a = found[0]
        if a["size"] != lock[prefix + "size_bytes"] or a.get("digest") != "sha256:" + lock[prefix + "sha256"]:
            raise IntegrityError("upstream asset digest/size mismatch")
        assets.append(a)
    return assets


def verify(path, digest, size):
    observed = sha256(path)
    if path.stat().st_size != size or observed != digest:
        raise IntegrityError("local artifact digest/size mismatch")
    return observed


def safe_extract(path, target, *, max_bytes=8 * 1024**3, max_files=100000):
    """Preflight all entries; extract into a newly created private directory only."""
    target = Path(target)
    if target.exists():
        raise ValueError("extraction target must not exist")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > max_files or sum(i.file_size for i in infos) > max_bytes:
            raise ValueError("extraction budget exceeded")
        seen = set()
        for i in infos:
            p = PurePosixPath(i.filename)
            mode = i.external_attr >> 16
            if p.is_absolute() or '..' in p.parts or '\\' in i.filename or ':' in i.filename or not p.parts:
                raise ValueError("unsafe archive path")
            if p in seen or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError("duplicate or special archive entry")
            seen.add(p)
            if i.file_size > max_bytes or i.file_size > max(1, i.compress_size) * 1000:
                raise ValueError("unreasonable compression ratio")
        target.mkdir(mode=0o700)
        try:
            for i in infos:
                dest = target / i.filename
                if i.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(i) as src, dest.open('xb') as out:
                    remaining = i.file_size
                    while block := src.read(min(1 << 20, remaining + 1)):
                        remaining -= len(block)
                        if remaining < 0:
                            raise ValueError("entry exceeded declared size")
                        out.write(block)
                    if remaining:
                        raise ValueError("truncated entry")
        except Exception:
            shutil.rmtree(target)
            raise
    return {"files": len(infos), "uncompressed_bytes": sum(i.file_size for i in infos)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--evidence', type=Path, required=True)
    args = p.parse_args()
    args.cache = external_directory(args.cache)
    args.evidence = external_directory(args.evidence)
    (args.evidence/'manifests').mkdir(exist_ok=True)
    (args.evidence/'receipts').mkdir(exist_ok=True)
    lock = json.loads(Path(__file__).with_name('upstream-lock.json').read_text())['sckan']
    url = f"https://api.github.com/repos/{lock['repository']}/releases/tags/{lock['tag']}"
    raw = urllib.request.urlopen(url, timeout=60).read()
    release = json.loads(raw)
    assets = metadata_check(lock, release)
    args.cache.mkdir(parents=True, exist_ok=True)
    (args.evidence / 'manifests/sckan-release.json').write_bytes(raw)
    receipts = []
    for a in assets:
        path = args.cache / a['name']
        if not path.exists():
            tmp = path.with_suffix('.partial')
            with urllib.request.urlopen(a['browser_download_url'], timeout=120) as src, tmp.open('wb') as out:
                total = 0
                while block := src.read(1 << 20):
                    total += len(block)
                    if total > a['size']:
                        raise IntegrityError('download exceeds pinned size')
                    out.write(block)
            verify(tmp, a['digest'][7:], a['size'])
            tmp.rename(path)
        observed = verify(path, a['digest'][7:], a['size'])
        receipt = dict(repository=lock['repository'], release_url=release['html_url'], tag=release['tag_name'],
                       release_status='prerelease', published_at=release['published_at'], asset=a['name'],
                       expected_sha256=a['digest'][7:], observed_sha256=observed, byte_count=path.stat().st_size,
                       verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       runtime=platform.python_version(), tool='experiments.sparc.authenticate',
                       host_architecture=platform.machine(), verification_result='VERIFIED')
        receipt['retrieval_recorded_at'] = receipt['verified_at']
        receipt['retrieval_note'] = 'Timestamp recorded after retrieval and digest check; cache reuse may precede this invocation.'
        receipts.append(receipt)
        (args.evidence / 'receipts/sckan-artifacts.json').write_text(json.dumps(receipts, indent=2) + '\n')
        print(json.dumps(receipt), flush=True)

if __name__ == '__main__':
    main()
