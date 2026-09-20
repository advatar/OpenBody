"""Read-only provenance investigation; no simulator, guessed values or execution contract."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
import urllib.error
from .authenticate_ascent import fetch, retrieve_dataset, object_url, external_directory

DOC_COMMIT = '20faf73c7e3e743909ad98db4438a01dd5743389'
ASCENT_COMMIT = '1360b77920c5759a66815b6b3db29efa7f78f950'


def measure_manifest(raw):
    parsed = json.loads(raw)
    declarations = [f['size'] for f in parsed.get('files', []) if f.get('path')=='manifest.json']
    return dict(byte_count=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                utf8_bom=raw.startswith(b'\xef\xbb\xbf'), unicode_characters=len(raw.decode('utf-8')),
                crlf_count=raw.count(b'\r\n'), lf_count=raw.count(b'\n'),
                lf_normalized_bytes=len(raw.replace(b'\r\n',b'\n')),
                crlf_normalized_bytes=len(raw.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')),
                compact_json_bytes=len(json.dumps(parsed,ensure_ascii=False,separators=(',',':')).encode()),
                gzip_bytes=len(gzip.compress(raw,mtime=0)), self_declared_sizes=declarations)


def classify_manifest(entry, observations):
    """Diagnose only a stable same-version raw-object/API contradiction; never waive it."""
    if len(observations)<2: return 'UNRESOLVED'
    expected = __import__('base64').b64decode(entry['sha256']).hex()
    for item in observations:
        headers = item['headers']
        if headers.get('x-amz-version-id') != entry['s3Version']:
            return 'VERSION_MISMATCH'
        if headers.get('content-encoding') not in (None,'identity'):
            return 'UNRESOLVED'  # decoding needs separate evidence
        if item['sha256'] != expected or int(headers.get('content-length',-1)) != item['byte_count']:
            return 'UNRESOLVED'
    if len({(o['sha256'],o['byte_count']) for o in observations}) != 1:
        return 'UNRESOLVED'
    if observations[0]['byte_count']==entry['size']: return 'RESOLVED'
    if all(o['measurements']['self_declared_sizes']==[o['byte_count']] for o in observations):
        return 'UPSTREAM_METADATA_DEFECT'
    return 'UNRESOLVED'


def xlsx_cells(path):
    """Read values only (never formulas/macros); no ZIP extraction or workbook execution."""
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    cells={}
    with zipfile.ZipFile(path) as archive:
        if sum(i.file_size for i in archive.infolist()) > 10*1024*1024:
            raise ValueError('workbook XML budget exceeded')
        strings=[]
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings=[''.join(x.itertext()) for x in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('s:si',ns)]
        for name in archive.namelist():
            if name.startswith('xl/worksheets/sheet') and name.endswith('.xml'):
                for cell in ET.fromstring(archive.read(name)).findall('.//s:c',ns):
                    value=cell.find('s:v',ns)
                    if value is not None and value.text:
                        text=strings[int(value.text)] if cell.get('t')=='s' else value.text
                    else:text=''.join(t.text or '' for t in cell.findall('.//s:t',ns))
                    if text:cells[name+'#'+cell.attrib['r']]=text
    return cells


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    out=external_directory(args.output)
    primary={}
    for dataset in (364,365):
        primary[str(dataset)]=retrieve_dataset(dataset,out/str(dataset))
    files=json.loads((out/'364/file-list.json').read_text())
    entry=next(f for f in files if f['path']=='manifest.json')
    observations=[]
    versioned=object_url(364,entry)
    # Separate requests to the version-addressed S3 object and the current object.
    for index,url in enumerate((versioned,versioned,versioned.split('?')[0])):
        raw,receipt=fetch(url);receipt['measurements']=measure_manifest(raw)
        (out/f'manifest-retrieval-{index}.bin').write_bytes(raw);observations.append(receipt)
    manifest=dict(classification=classify_manifest(entry,observations),
                  file_verification_status='FAILED',declared_entry=entry,observations=observations,
                  explanation='Same object version/digest: file-list size conflicts with raw bytes, HTTP Content-Length and manifest self-entry. Internal publisher cause is not established.')
    sources={
      'doi':'https://api.datacite.org/dois/10.26275/0JZ3-ZRLO',
      'versions':'https://api.pennsieve.io/discover/datasets/364/versions',
      'ascent_documentation':f'https://raw.githubusercontent.com/wmglab-duke/ascent/{DOC_COMMIT}/docs/source/Running_ASCENT/osparc.md',
      'citation_guide':'https://docs.sparc.science/docs/instructions-for-sparc-investigators-to-cite-their-datasets-in-manuscripts-1',
      'portal_tutorial':'https://docs.sparc.science/v1.0/docs/tutorial-running-ascent-on-o2s2parc-from-the-sparc-portal',
    }
    for name in ('config/templates/osparc/osparc_sim.json','config/templates/osparc/osparc_centroid_sim.json',
                 'config/templates/osparc/osparc_run.json','src/neuron/HOC_Files/FindThresh.hoc',
                 'src/neuron/HOC_Files/Saving_Thresh.hoc','requirements.txt','docs/source/Getting_Started.md'):
        sources[name]=f'https://raw.githubusercontent.com/wmglab-duke/ascent/{ASCENT_COMMIT}/{name}'
    receipts={}
    for name,url in sources.items():
        try:
            raw,receipt=fetch(url);receipts[name]=receipt
            (out/(name.replace('/','_')+'.raw')).write_bytes(raw)
        except urllib.error.HTTPError as exc:
            receipts[name]={'url':url,'retrieval_status':'BLOCKED','http_status':exc.code}
    # Selected factual cells only; examples/help-text columns are not study settings.
    sheets={}
    for name in ('dataset_description.xlsx','manifest.xlsx','submission.xlsx'):
        cells=xlsx_cells(out/'364/files'/name)
        sheets[name]={'nonempty_cells':len(cells),'selected_cells':{k:v for k,v in cells.items() if ('osparc.io/study/' in v or 'v.1.2.1' in v or v=='template.json')}}
    result=dict(primary=primary,manifest_investigation=manifest,sources=receipts,workbook_inspection=sheets)
    (out/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'classification':manifest['classification'],'retrieved_files':{k:len(v['files']) for k,v in primary.items()},'candidate_executed':False}))

if __name__=='__main__':main()
