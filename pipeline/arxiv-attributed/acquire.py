import concurrent.futures as futures
import datetime as dt
import gzip, hashlib, json, re, sqlite3, time, urllib.parse, urllib.request
from pathlib import Path

import argparse
parser=argparse.ArgumentParser(description='Fetch native arXiv category records and linked institution authorities from INSPIRE.')
parser.add_argument('--work-dir', type=Path, required=True)
args=parser.parse_args()
ROOT=args.work_dir; ROOT.mkdir(parents=True,exist_ok=True)
DB=sqlite3.connect(ROOT/'source.sqlite')
DB.executescript('CREATE TABLE IF NOT EXISTS works(id TEXT PRIMARY KEY, payload BLOB); CREATE TABLE IF NOT EXISTS captures(category TEXT, year INTEGER, total INTEGER, received INTEGER, url TEXT, sha TEXT, at TEXT, error TEXT, PRIMARY KEY(category,year)); CREATE TABLE IF NOT EXISTS authorities(id TEXT PRIMARY KEY, payload BLOB);')
CATS=json.loads(Path(__file__).with_name('categories.json').read_text())
SIZE=250
def fetch(url):
    for attempt in range(3):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'AtlasPhysicus/1.0 (public research atlas; https://atlas.techecho.org)'})
            with urllib.request.urlopen(req,timeout=30) as r: data=r.read(60_000_001)
            if len(data)>60_000_000:raise ValueError('response exceeds bounded processing size')
            return json.loads(data),hashlib.sha256(data).hexdigest(),dt.datetime.now(dt.timezone.utc).isoformat()
        except Exception:
            if attempt==2:raise
            time.sleep(2*(attempt+1))
def capture(task):
    cat,year=task
    query=f'arxiv_eprints.categories:{cat} and date >= {year} and date < {year+1}'
    url='https://inspirehep.net/api/literature?'+urllib.parse.urlencode({'q':query,'size':SIZE,'sort':'mostrecent','fields':'control_number,titles,preprint_date,arxiv_eprints,authors,dois,citation_count,citation_count_without_self_citations'})
    try:
        body,sha,at=fetch(url)
        rows=[]
        for hit in body['hits']['hits']:
            m=hit['metadata']; arxiv=m.get('arxiv_eprints',[])
            if not arxiv:continue
            authors=[]
            for a in m.get('authors',[]):
                authors.append({'name':a.get('full_name','Unknown author'),'id':str(a.get('recid') or (a.get('record') or {}).get('$ref','')).rsplit('/',1)[-1],
                                'affiliations':[{'id':str((v.get('record') or {}).get('$ref','')).rsplit('/',1)[-1],'name':v.get('value','')} for v in a.get('affiliations',[])],
                                'raw':[v.get('value','') for v in a.get('raw_affiliations',[]) if v.get('value')]})
            work={'id':str(m['control_number']),'title':m.get('titles',[{}])[0].get('title','Untitled'), 'date':m.get('preprint_date'),
                  'arxiv':arxiv,'authors':authors,'dois':m.get('dois',[]),'citations':m.get('citation_count_without_self_citations'),
                  'allCitations':m.get('citation_count'),'retrievedAt':at,'checksum':hashlib.sha256(json.dumps(m,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
            rows.append(work)
        total=body['hits']['total'];total=total.get('value',0) if isinstance(total,dict) else total
        return task,rows,(cat,year,total,len(body['hits']['hits']),url,sha,at,None)
    except Exception as e:return task,[],(cat,year,0,0,url,'',dt.datetime.now(dt.timezone.utc).isoformat(),str(e))

done={(r[0],r[1]) for r in DB.execute('SELECT category,year FROM captures WHERE error IS NULL')}
tasks=[(c['category'],y) for y in range(2018,2027) for c in CATS if (c['category'],y) not in done]
print(json.dumps({'stage':'acquisition-start','partitions':len(tasks),'categories':len(CATS),'perPartition':SIZE}),flush=True)
with futures.ThreadPoolExecutor(max_workers=5) as pool:
    pending={pool.submit(capture,t):t for t in tasks}
    for index,completed in enumerate(futures.as_completed(pending),1):
        task,rows,receipt=completed.result()
        for work in rows:DB.execute('INSERT OR IGNORE INTO works VALUES (?,?)',(work['id'],gzip.compress(json.dumps(work,separators=(',',':')).encode(),compresslevel=1)))
        DB.execute('INSERT OR REPLACE INTO captures VALUES (?,?,?,?,?,?,?,?)',receipt)
        DB.commit()
        if index%15==0 or receipt[-1]:print(json.dumps({'stage':'papers','done':index,'total':len(tasks),'partition':task,'records':DB.execute('SELECT COUNT(*) FROM works').fetchone()[0],'error':receipt[-1]}),flush=True)

# Exact source-issued institution IDs are resolved in bounded batches.
ids=set()
for (blob,) in DB.execute('SELECT payload FROM works'):
    work=json.loads(gzip.decompress(blob))
    for author in work['authors']:
        ids.update(v['id'] for v in author['affiliations'] if v['id'].isdigit())
known={r[0] for r in DB.execute('SELECT id FROM authorities')}
missing=sorted(ids-known)
def authority_batch(values):
    url='https://inspirehep.net/api/institutions?'+urllib.parse.urlencode({'q':' OR '.join('control_number:'+v for v in values),'size':len(values)})
    try:
        body,sha,at=fetch(url)
        return [{'metadata':h['metadata'],'sha':sha,'retrievedAt':at,'url':url} for h in body['hits']['hits']]
    except Exception as e:
        print(json.dumps({'stage':'authority-error','error':str(e)}),flush=True);return []
print(json.dumps({'stage':'institutions','uniqueIds':len(ids),'fetching':len(missing)}),flush=True)
with futures.ThreadPoolExecutor(max_workers=5) as pool:
    for rows in pool.map(authority_batch,[missing[i:i+40] for i in range(0,len(missing),40)]):
        for item in rows:DB.execute('INSERT OR REPLACE INTO authorities VALUES (?,?)',(str(item['metadata']['control_number']),gzip.compress(json.dumps(item,separators=(',',':')).encode())))
        DB.commit()
print(json.dumps({'stage':'complete','works':DB.execute('SELECT COUNT(*) FROM works').fetchone()[0],'authorities':DB.execute('SELECT COUNT(*) FROM authorities').fetchone()[0],'failedPartitions':DB.execute('SELECT COUNT(*) FROM captures WHERE error IS NOT NULL').fetchone()[0]}),flush=True)
