"""Retrieve public dataset v1 objects; record mismatches without accepting them."""
import argparse,json,urllib.request,urllib.parse,base64,hashlib,datetime,pathlib
p=argparse.ArgumentParser()
p.add_argument('--cache',type=pathlib.Path,required=True)
args=p.parse_args()
root=pathlib.Path(__file__).parent/'evidence'
cache=args.cache/'ascent';cache.mkdir(parents=True,exist_ok=True)
base='https://api.pennsieve.io/discover/datasets/364/versions/1'
files=[]
def walk(path=''):
 u=base+'/files/browse?limit=100&path='+urllib.parse.quote(path)
 x=json.load(urllib.request.urlopen(u,timeout=60))
 assert x['totalCount']<=100
 for f in x['files']:
  if f['type']=='Directory':walk(f['path'])
  else:files.append(f)
walk()
receipts=[]
for f in files:
 u=f['uri'].replace('s3://sparc-prod-aod-discover-publish50-use1/','https://sparc-prod-aod-discover-publish50-use1.s3.amazonaws.com/')+'?versionId='+urllib.parse.quote(f['s3Version'])
 b=urllib.request.urlopen(u,timeout=60).read(); h=hashlib.sha256(b).hexdigest(); expected=base64.b64decode(f['sha256']).hex()
 result = 'VERIFIED' if h==expected and len(b)==f['size'] else 'FAILED'
 dest=cache/f['path']
 assert dest.resolve().is_relative_to(cache.resolve()), 'unsafe upstream path'
 dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b)
 receipts.append(dict(path=f['path'],size=len(b),expected_sha256=expected,observed_sha256=h,object_version=f['s3Version'],retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),status=result,expected_size=f['size']))
(root/'manifests/ascent-files.json').write_text(json.dumps(files,indent=2)+'\n')
(root/'receipts/ascent-artifacts.json').write_text(json.dumps(receipts,indent=2)+'\n')
for name,url in [('ascent-datacite.json','https://api.datacite.org/dois/10.26275/0JZ3-ZRLO'),('ascent-dataset.json',base)]:
 (root/'manifests'/name).write_bytes(urllib.request.urlopen(url,timeout=60).read())
print(json.dumps(receipts,indent=2))
if any(r['status']!='VERIFIED' for r in receipts):raise SystemExit(1)
