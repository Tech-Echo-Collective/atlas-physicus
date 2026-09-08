import sys,gzip,json,sqlite3,hashlib,math,re,datetime,unicodedata
from pathlib import Path
from collections import defaultdict,Counter
from types import SimpleNamespace
import pycountry
from physics_atlas_api.metrics.normalization import robust_log_winsorized_cohort,robust_mncs_cohort,robust_centered_change_cohort
from physics_atlas_api.metrics.ui_shards import UIShardBuilder,_encode
import argparse
parser=argparse.ArgumentParser(description='Publish verified paper-time affiliation shares and normalized category metrics.')
parser.add_argument('--work-dir',type=Path,required=True);parser.add_argument('--output-dir',type=Path,required=True)
args=parser.parse_args(); ROOT=args.work_dir;OUT=args.output_dir;OUT.mkdir(parents=True,exist_ok=True)
DB=sqlite3.connect(ROOT/'source.sqlite'); CATS=json.loads(Path(__file__).with_name('categories.json').read_text()); cmap={c['category']:c['id'] for c in CATS}; VERSION='arxiv-attributed-20260908-v1';AT=datetime.datetime.now(datetime.timezone.utc).isoformat()
def provenance(source='INSPIRE literature and institution authority records',status='verified',kind='external-api',record=None):
 d={'source':source,'sourceType':kind,'version':VERSION,'status':status,'retrievedAt':AT}
 if record:d['sourceRecordId']=str(record)
 return d
P=provenance(); D=provenance('Derived from retrieved INSPIRE arXiv papers; confirmed paper-time institution links','unverified','derived')
def norm(s):return re.sub(r'[^\w]+',' ',unicodedata.normalize('NFKC',s).casefold()).strip()
institutions={}; source_map={}; authority_parents=defaultdict(set);names=defaultdict(set);country_map={}; inst_fields=defaultdict(set)
for (blob,) in DB.execute('select payload from authorities'):
 receipt=json.loads(gzip.decompress(blob));m=receipt['metadata'];sid=str(m['control_number']);addrs=m.get('addresses',[])
 codes={a.get('country_code') for a in addrs if a.get('country_code')};codes.discard('')
 if len(codes)!=1:continue
 code=next(iter(codes));country=pycountry.countries.get(alpha_2=code)
 if not country:continue
 addr=next(a for a in addrs if a.get('country_code')==code);ror=next((x['value'].strip().rstrip('/').rsplit('/',1)[-1] for x in m.get('external_system_identifiers',[]) if x.get('schema')=='ROR'),None)
 iid='institution-ror-'+ror if ror else 'institution-inspire-'+sid;cid='country-'+code.lower()
 variants=[x.get('value') for x in m.get('name_variants',[]) if x.get('value')];hier=[x.get('name') for x in m.get('institution_hierarchy',[]) if x.get('name')];icn=m.get('ICN',[]);icn=[icn] if isinstance(icn,str) else icn
 label=(variants or hier or icn or ['INSPIRE institution '+sid])[0]
 if label.lower()=='obsolete':continue
 country_map[cid]={'id':cid,'isoAlpha3':country.alpha_3,'isoNumeric':country.numeric,'name':country.name,'region':'World','provenance':P}
 if iid not in institutions:
  institutions[iid]={'id':iid,'name':label,'canonicalName':label,'aliases':sorted(set(variants+hier+icn)-{label}),'externalIds':[],'countryId':cid,'city':next(iter(addr.get('cities',[])),'Not supplied'),'fieldIds':[],'identityConfidence':1,'provenance':provenance('INSPIRE institution authority','verified',record=sid)}
  if isinstance(addr.get('latitude'),(int,float)) and isinstance(addr.get('longitude'),(int,float)):institutions[iid]['location']={'latitude':addr['latitude'],'longitude':addr['longitude']}
  if ror:institutions[iid]['externalIds'].append({'scheme':'ROR','value':'https://ror.org/'+ror})
 if institutions[iid]['countryId']!=cid:continue
 institutions[iid]['externalIds'].append({'scheme':'INSPIRE','value':sid});source_map[sid]=iid
 if ror and hier:authority_parents[iid].add(hier[-1])
 for name in [label]+variants+hier+icn:
  n=norm(name)
  if len(n)>=12 and len(n.split())>=2:names[n].add(iid)
# Only unique whole affiliation segments match an authority alias. No fuzzy identity guesses.
aliases={n:next(iter(v)) for n,v in names.items() if len(v)==1};resolve_cache={}
def resolve(author):
 ids={source_map[a['id']] for a in author['affiliations'] if a['id'] in source_map};method='source-institution-link'
 if ids:return ids,method
 for raw in author['raw']+[a['name'] for a in author['affiliations']]:
  if raw not in resolve_cache:
   parts=re.split(r'[,;\n]',raw);candidate=set()
   for part in parts:
    if norm(part) in aliases:candidate.add(aliases[norm(part)])
   resolve_cache[raw]=candidate if len(candidate)==1 else set()
  ids.update(resolve_cache[raw])
 return ids,'unique-authority-name-segment'
# Compact per-paper calculations; every source author remains in the fractional denominator.
works=[]; seen_arxiv=set(); counts=Counter(); coverage=defaultdict(Counter); citation_means=defaultdict(lambda:[0.,0])
for (blob,) in DB.execute('select payload from works order by id'):
 w=json.loads(gzip.decompress(blob));counts['retrieved']+=1;date=w.get('date') or '';year=int(date[:4]) if re.match(r'^\d{4}',date) else 0
 fields=sorted({cmap[c] for a in w['arxiv'] for c in a.get('categories',[]) if c in cmap});arxivs=sorted({a['value'] for a in w['arxiv'] if a.get('value')})
 if not fields or not 2018<=year<=2026:counts['outside-dated-scope']+=1;continue
 if any(a in seen_arxiv for a in arxivs):counts['duplicate-arxiv']+=1;continue
 seen_arxiv.update(arxivs);authors=w['authors'];iw=defaultdict(float);resolved=[];unresolved=0
 for a in authors:
  ids,method=resolve(a);resolved.append((ids,method))
  if not ids:unresolved+=1;continue
  for iid in ids:iw[iid]+=1/len(authors)/len(ids)
 cw=defaultdict(float)
 for ids,method in resolved:
  countries={institutions[iid]['countryId'] for iid in ids}
  for cid in countries:cw[cid]+=1/len(authors)/len(countries)
 mass=sum(iw.values());assert mass<=1+1e-8
 for f in fields:coverage[(f,year)].update(papers=1,sourceAuthors=len(authors),verifiedAuthors=len(authors)-unresolved,attributedPapers=int(bool(iw)))
 counts['sourceAuthors']+=len(authors);counts['verifiedAuthors']+=len(authors)-unresolved
 if not iw:counts['withoutVerifiedInstitution']+=1;continue
 w.update(year=year,fieldIds=fields,arxivId=arxivs[0],iw=dict(iw),cw=dict(cw),resolved=resolved,complete=unresolved==0)
 works.append(w);counts['attributed']+=1;counts['attributedFractionalMass']+=mass
 cit=w.get('citations')
 if isinstance(cit,(int,float)) and cit>=0:
  for f in fields:citation_means[(f,year)][0]+=cit;citation_means[(f,year)][1]+=1
print('attribution',dict(counts),'authorities',len(institutions),flush=True)
# Annual fractional masses and indicators. Field shares sum to one within each paper.
activity=defaultdict(lambda:defaultdict(float));impact_num=defaultdict(lambda:defaultdict(float));impact_den=defaultdict(lambda:defaultdict(float));collab_num=defaultdict(lambda:defaultdict(float));collab_den=defaultdict(lambda:defaultdict(float));inputs=defaultdict(Counter);mix=defaultdict(lambda:defaultdict(Counter))
for w in works:
 y=w['year'];fs=w['fieldIds'];cit=w.get('citations')
 for typ,weights in [('country',w['cw']),('institution',w['iw'])]:
  international=len(w['cw'])>1 if typ=='country' else len(w['iw'])>1
  known_collaboration=w['complete'] or international
  for f in fs:
   key=(typ,f,y)
   for eid,share in weights.items():
    v=share/len(fs);activity[key][eid]+=v;inputs[key][eid]+=1
    if known_collaboration:collab_den[key][eid]+=v;collab_num[key][eid]+=v*international
    if isinstance(cit,(int,float)) and cit>=0:
     total,n=citation_means[(f,y)];mean=total/n if n else 0
     if mean>0:impact_num[key][eid]+=v*cit/mean;impact_den[key][eid]+=v
    for sub in fs:mix[key][eid][sub]+=v/len(fs)
# Publish genuine observed metric dimensions independently. Small cohorts are disclosed, not blocked by joint certification.
observations=[]; overview=defaultdict(list); series=defaultdict(list)
for (typ,f,y),values in activity.items():series[(typ,f)].append(y)
def summed(data,typ,f,ys):
 out=defaultdict(float)
 for y in ys:
  for eid,v in data.get((typ,f,y),{}).items():out[eid]+=v
 return dict(out)
def add(typ,f,t,metric,raw,scores,method,params,unit):
 for eid,score in scores.items():
  if not math.isfinite(score):continue
  row={'id':f'obs-{len(observations)}','entityType':typ,'entityId':eid,'scienceDomainId':'physics','fieldId':f,'metricId':metric,'period':str(t),'value':round(max(0,min(100,score)),6),'rawValue':round(raw[eid],8),'rawUnit':unit,'normalizationMethod':method,'normalizationParameters':params,'inputCount':sum(inputs.get((typ,f,y),{}).get(eid,0) for y in range(max(2018,t-2),t+1)),'qualityFlags':['retrieved-corpus-not-census','partial-attribution']+(['current-year-partial'] if t==2026 else []),'source':'INSPIRE native arXiv categories and verified paper-time institution links','algorithmVersion':'arxiv-observed-metrics-v1','calculationVersion':VERSION,'provenance':D}
  observations.append(row);overview[(typ,eid,t,metric)].append(row['value'])
for typ,f in sorted(series):
 for t in range(2018,2027):
  ys=list(range(max(2018,t-2),t+1));raw=summed(activity,typ,f,ys)
  if not raw:continue
  fitted=robust_log_winsorized_cohort(raw,minimum_cohort=2)
  add(typ,f,t,'research_activity_score',raw,fitted.scores,fitted.method_version,{**fitted.parameters,'windowStart':min(ys),'windowEnd':t,'cohortField':f,'cohortEntityType':typ},'fractional papers')
  mature=list(range(max(2018,t-4),t-1));num=summed(impact_num,typ,f,mature);den=summed(impact_den,typ,f,mature);iraw={e:num.get(e,0)/d for e,d in den.items() if d>0}
  fitted=robust_mncs_cohort(iraw,minimum_cohort=2)
  add(typ,f,t,'research_impact',iraw,fitted.scores,fitted.method_version,{**fitted.parameters,'citationObservedAt':AT,'publicationYears':mature,'cohortField':f,'cohortEntityType':typ},'mean normalized non-self citation score')
  num=summed(collab_num,typ,f,ys);den=summed(collab_den,typ,f,ys);craw={e:num.get(e,0)/d for e,d in den.items() if d>0}
  add(typ,f,t,'collaboration',craw,{e:v*100 for e,v in craw.items()},'fractional-confirmed-collaboration-share-v1',{'outputMin':0,'outputMax':100,'unknownRelationships':'excluded'},'fraction of confirmed collaborative output')
  mixes=defaultdict(Counter)
  for y in ys:
   for e,c in mix.get((typ,f,y),{}).items():mixes[e].update(c)
  draw={}
  for e,c in mixes.items():
   total=sum(c.values());draw[e]=-sum(v/total*math.log(v/total) for v in c.values() if v>0)/math.log(len(CATS))
  add(typ,f,t,'research_diversity',draw,{e:v*100 for e,v in draw.items()},'normalized-arxiv-category-shannon-entropy-v1',{'categoryCount':len(CATS),'outputMin':0,'outputMax':100},'normalized category entropy')
  if 2023<=t<=2025:
   base=summed(activity,typ,f,range(t-5,t-2));mraw={e:math.log(v/base[e]) for e,v in raw.items() if base.get(e,0)>0 and v>0}
   fitted=robust_centered_change_cohort(mraw,minimum_cohort=2)
   add(typ,f,t,'momentum',mraw,fitted.scores,fitted.method_version,{**fitted.parameters,'baselineStart':t-5,'baselineEnd':t-3,'recentStart':t-2,'recentEnd':t},'log fractional-output ratio')
for (typ,eid,t,metric),values in overview.items():
 observations.append({'id':f'obs-{len(observations)}','entityType':typ,'entityId':eid,'scienceDomainId':'physics','metricId':metric,'period':str(t),'value':round(sum(values)/len(values),6),'rawValue':sum(values)/len(values),'rawUnit':'equal-weight mean of available field scores','normalizationMethod':'equal-field-normalized-mean-v1','normalizationParameters':{'availableFields':len(values),'totalFields':len(CATS),'missingFields':'omitted'},'qualityFlags':['retrieved-corpus-not-census','partial-attribution'],'source':D['source'],'algorithmVersion':'arxiv-observed-metrics-v1','calculationVersion':VERSION,'provenance':D})
print('metrics',len(observations),flush=True)
# Relationships reuse the original on-demand UI transport, without loading millions of rows on entry.
sink=UIShardBuilder(VERSION)
def emit(kind,row):
 encoded=_encode(row);overhead=len(sink._prefix(kind))+len(sink._suffix())
 if sink.buffers[kind] and overhead+sink.sizes[kind]+1+len(encoded)>4*1024*1024:sink._flush(kind)
 sink.index.add(kind,row,sink._id(kind));sink.sizes[kind]+=len(encoded)+bool(sink.buffers[kind]);sink.buffers[kind].append(encoded)
papers=[];researchers={};researcher_fields=defaultdict(set);verified_inst=set()
for i,w in enumerate(works):
 pid='paper-inspire-'+w['id'];p={'id':pid,'title':w['title'],'summary':'','year':w['year'],'fieldIds':w['fieldIds'],'arxivId':w['arxivId'],'externalIdentifiers':[{'scheme':'INSPIRE','value':w['id']}],'provenance':provenance(record=w['id'])}
 if re.match(r'^\d{4}(?:-\d{2})?(?:-\d{2})?$',w['date']):p['publicationDate']=w['date']
 doi=next((d['value'] for d in w['dois'] if re.match(r'^10\.\d{4,9}/\S+$',d.get('value',''))),None)
 if doi:p['doi']=doi
 papers.append(p);verified_inst.update(w['iw']);seen_authors=set()
 for n,(a,(ids,method)) in enumerate(zip(w['authors'],w['resolved']),1):
  # Known source author identities are retained; otherwise identity stays local to this paper.
  if not ids:continue
  rid='inspire-author:'+a['id'] if a['id'].isdigit() else f'paper-author-{w["id"]}-{n}'
  researcher_fields[rid].update(w['fieldIds'])
  if rid not in researchers:researchers[rid]={'id':rid,'name':a['name'] or 'Unnamed source author','fieldIds':[],'externalIds':([{'scheme':'INSPIRE','value':a['id']}] if a['id'].isdigit() else []),'provenance':provenance(record=a['id'] or f'{w["id"]}:author:{n}')}
  if rid not in seen_authors:emit('authorships',{'id':f'auth-{w["id"]}-{n}','paperId':pid,'researcherId':rid,'authorPosition':n,'provenance':P})
  seen_authors.add(rid)
  for iid in sorted(ids):
   verified_inst.add(iid);inst_fields[iid].update(w['fieldIds'])
   emit('affiliations',{'id':f'aff-{w["id"]}-{n}-{iid}','paperId':pid,'researcherId':rid,'institutionId':iid,'startYear':w['year'],'endYear':w['year'],'source':method,'confidence':1,'provenance':provenance('Paper-time attribution: '+method,record=w['id'])})
 emit('externalResources',{'id':'source-'+pid,'entityType':'paper','entityId':pid,'resourceType':'arxiv','label':'Original arXiv paper','url':'https://arxiv.org/abs/'+w['arxivId'],'isPrimary':True,'provenance':P})
 if i%10000==0:print('relationships',i,sink.record_counts,flush=True)
institutions={k:v for k,v in institutions.items() if k in verified_inst}
for iid,v in institutions.items():
 v['fieldIds']=sorted(inst_fields[iid]);sid=next(x['value'] for x in v['externalIds'] if x['scheme']=='INSPIRE')
 emit('externalResources',{'id':'source-'+iid,'entityType':'institution','entityId':iid,'resourceType':'inspire','label':'Institution authority record','url':'https://inspirehep.net/institutions/'+sid,'isPrimary':True,'provenance':P})
for rid,r in researchers.items():r['fieldIds']=sorted(researcher_fields[rid])
fields=[{'id':c['id'],'label':c['label'],'description':'arXiv category '+c['category'],'aliases':[c['category']],'ontologyVersion':'arxiv-category-taxonomy-2026-09-08','nodeKind':'field','isExplorable':True,'displayOrder':i,'provenance':provenance('https://arxiv.org/category_taxonomy')} for i,c in enumerate(CATS)]
defs=[]
for mid,name,description in [('research_activity_score','Research Activity','Fractional paper output in the trailing three years, normalized within the same arXiv category, entity type and year.'),('research_impact','Research Impact','Mean non-self citation counts normalized by arXiv category and publication year; mature papers; citations observed at the current capture date.'),('collaboration','Collaboration','Fractional share of confirmed international (country) or inter-institutional (institution) papers. Unknown collaboration relationships are excluded.'),('research_diversity','Research Diversity','Shannon entropy of native arXiv category shares, normalized by the 51-category taxonomy.'),('momentum','Momentum','Log change between adjacent three-year observed-output windows, centered and scaled within the category cohort. Only 2023–2025 have complete acquired windows.')]:
 defs.append({'id':mid,'name':name,'category':'Research metrics','description':description,'interpretation':description+' Calculated on the retrieved corpus; source coverage differs across categories and years.','unit':'score (0–100)','version':'arxiv-observed-metrics-v1','requiredData':['native arXiv categories','verified paper-time institution links'],'implementationStatus':'live-calculated','provenance':D})
geo=[]
for cid,c in country_map.items():
 if cid=='country-tw' and 'country-cn' in country_map:continue
 geo.append({'id':'view-'+cid,'countryId':cid,'geometryIsoNumerics':[c['isoNumeric']]+(['158'] if cid=='country-cn' and 'country-tw' in country_map else []),'locationCountryIds':[cid]+(['country-tw'] if cid=='country-cn' and 'country-tw' in country_map else []),'provenance':P})
core={'metadata':{'schemaVersion':'1.0.0','datasetKind':'live-api','deliveryMode':'attributed-dataset','period':'2025','generatedAt':AT,'disclaimer':f'{len(works):,} attributed papers · 51 arXiv physics categories · 2018–2026. Up to 250 INSPIRE records per category/year; this is a retrieved corpus, not a complete census. Only verified paper-time affiliation shares contribute; unknown shares remain unallocated. 2026 is partial. Historical citation scores use citations observed on 8 September 2026.','provenance':D},'scienceDomains':[{'id':'physics','label':'Physics','description':'Research classified by the official arXiv physics taxonomy','fieldIds':[c['id'] for c in CATS],'provenance':P}],'fields':fields,'countries':list(country_map.values()),'geographicViews':geo,'institutions':list(institutions.values()),'researchers':list(researchers.values()),'papers':papers,'researchGroups':[],'affiliations':[],'authorships':[],'externalResources':[],'metricDefinitions':defs,'metricObservations':observations}
ns=SimpleNamespace(papers=[SimpleNamespace(id=p['id']) for p in papers],researchers=[SimpleNamespace(id=p['id']) for p in researchers.values()],institutions=[SimpleNamespace(id=p['id']) for p in institutions.values()],research_groups=[],authorships=[],affiliations=[],external_resources=[])
# Keep the exact compact index bounded; physics-wide catalogs need more than the pilot's 8 MiB.
import physics_atlas_api.metrics.ui_shards as transport
transport.MAX_UI_INDEX_BYTES=32*1024*1024
export=sink.finish(ns)
for kind,path,data in export.assets:(OUT/path).write_bytes(data)
(OUT/'relationships.json').write_text(json.dumps(export.metadata,separators=(',',':')))
# A shared ROR names the authority parent, rather than whichever department was seen first.
canonical_names={iid:next(iter(values)) for iid,values in authority_parents.items() if iid in institutions and len(values)==1 and next(iter(values)) in institutions[iid]['aliases']}
(OUT/'canonical-names.json').write_text(json.dumps(canonical_names,separators=(',',':'),ensure_ascii=False))
# Repeated provenance/normalization definitions are interned for transport and restored before schema parsing.
provs=[];prov_ids={};parameters=[];parameter_ids={}
def intern(value,arr,lookup):
 key=json.dumps(value,sort_keys=True,separators=(',',':'))
 if key not in lookup:lookup[key]=len(arr);arr.append(value)
 return lookup[key]
for key,rows in core.items():
 if not isinstance(rows,list):continue
 for row in rows:
  if 'provenance' in row:row['provenance']=intern(row['provenance'],provs,prov_ids)
  if 'normalizationParameters' in row:row['normalizationParameters']=intern(row['normalizationParameters'],parameters,parameter_ids)
metric_rows=core.pop('metricObservations'); metric_files={}
for year in range(2018,2027):
 rows=[r for r in metric_rows if r['period']==str(year)]; columns=list(dict.fromkeys(k for r in rows for k in r)); payload={'columns':columns,'rows':[[r.get(k) for k in columns] for r in rows]}
 encoded=json.dumps(payload,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode(); zipped=gzip.compress(encoded,compresslevel=6,mtime=0); filename=f'metrics-{year}.json.gz';(OUT/filename).write_bytes(zipped);metric_files[str(year)]={'path':filename,'bytes':len(zipped),'decodedBytes':len(encoded),'sha256':hashlib.sha256(zipped).hexdigest(),'records':len(rows),'decodedSha256':hashlib.sha256(encoded).hexdigest()}
core['metricObservations']=[]
packed={'version':'arxiv-atlas-packed-v1','provenance':provs,'normalizationParameters':parameters,'dataset':core};raw=json.dumps(packed,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode();compressed=gzip.compress(raw,compresslevel=6,mtime=0);(OUT/'atlas.json.gz').write_bytes(compressed)
receipts=[dict(zip(['category','year','total','received','url','sha256','retrievedAt','error'],r)) for r in DB.execute('select * from captures order by category,year')]
report={'version':VERSION,'generatedAt':AT,'source':'INSPIRE REST API','taxonomy':'https://arxiv.org/category_taxonomy','counts':dict(counts),'countries':len(country_map),'institutions':len(institutions),'researchers':len(researchers),'papers':len(papers),'metrics':len(observations),'partitions':receipts,'attributionByFieldYear':[{'fieldId':f,'year':y,**dict(c)} for (f,y),c in sorted(coverage.items())],'relationships':sink.record_counts,'indexDecodedBytes':export.metadata['index']['decodedBytes'],'coreBytes':len(compressed),'coreDecodedBytes':len(raw),'coreSha256':hashlib.sha256(compressed).hexdigest(),'coreDecodedSha256':hashlib.sha256(raw).hexdigest(),'metricFiles':metric_files,'methods':{'attribution':'Exact source institution identity links or a unique exact authority-name affiliation segment; no fuzzy matching. Unknown author shares remain unallocated.','normalization':'Within category/year/entity-type robust log 5–95% winsorization; normalized citation cohorts; bounded collaboration share; Shannon diversity; robust centered momentum. Minimum display cohort 2, not old certification threshold 30.','overview':'Equal mean of available normalized category scores, without filling absent categories.','coverage':'Most recent up to 250 source records per category/year. Different completeness across partitions; not census or probability sample.'}}
(OUT/'coverage.json').write_text(json.dumps(report,separators=(',',':'),ensure_ascii=False));(ROOT/'result.json').write_text(json.dumps({k:v for k,v in report.items() if k not in ['partitions','attributionByFieldYear']},indent=2));print((ROOT/'result.json').read_text(),flush=True)
