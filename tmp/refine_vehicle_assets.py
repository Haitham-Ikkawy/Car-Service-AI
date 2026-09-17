"""Recover model aliases and exact named photos from shared vehicle articles."""
import concurrent.futures
import re
from complete_vehicle_assets import ROOT, CLIENT, WIKI, COMMONS, META, get, key, read, write, pages_for, image_for, title

catalogue=read('tmp/vehicle-catalogue-completed.json')
manifest=read('vehicle-images-manifest.json')
pages=read('tmp/vehicle-wiki-pages.json')
rejected=read('tmp/vehicle-candidates-unresolved.json')
META.update(read('tmp/vehicle-photo-metadata.json'))

# Published article naming conventions, not substitutions for a different car.
overrides={
 ('Li Auto','L6'):'Li L6',('NIO','EC7'):'Nio EC7',('JAC','S3'):'JAC Refine S3',
 ('GAC','GN6'):'Trumpchi M6',('GAC','GN8'):'Trumpchi M8',('BAIC','X35'):'Senova X35',
 ('Geely','Geometry C'):'Geometry C',('Great Wall','Poer'):'Great Wall Pao',
 ('Bentley','Flying Spur'):'Bentley Flying Spur (2005)',('Bentley','Mulsanne'):'Bentley Mulsanne (2010)',
 ('Alfa Romeo','Junior'):'Alfa Romeo Junior (2023)',('Fiat','Tipo'):'Fiat Tipo (2015)',
 ('Fiat','Topolino'):'Fiat Topolino (2023)',('Ford','Fusion'):'Ford Fusion (Americas)',
 ('Jeep','Gladiator'):'Jeep Gladiator (JT)',('Jeep','Grand Wagoneer'):'Jeep Wagoneer (WS)',
 ('Tesla','Roadster'):'Tesla Roadster (first generation)',('Mini','Clubman'):'Mini Clubman (2007)',
 ('Buick','Verano'):'Buick Verano (second generation)',('Infiniti','Q60'):'Infiniti Q60 (CV37)',
 ('DS','DS 7'):'DS 7 Crossback',('MG','4'):'MG4 EV',
 ('Ferrari','812'):'Ferrari 812 Superfast',('Jaguar','E-PACE'):'Jaguar E-Pace',
 ('Land Rover','Range Rover'):'Range Rover',('Land Rover','Evoque'):'Range Rover Evoque',
 ('Nissan','Z'):'Nissan Z (RZ34)',('BMW','Z4'):'BMW Z4 (G29)',
 ('Abarth','500e'):'Abarth 500e',('Abarth','695'):'Abarth 695',
}
extra=pages_for(list(dict.fromkeys(overrides.values())))
write('tmp/vehicle-refined-pages.json',extra)
for record in rejected:
    b,m=record['brand'],record['model']
    page=extra.get(overrides.get((b,m),'')) or pages.get(title(b,m))
    if page and m not in catalogue[b]:
        catalogue[b].append(m)
        manifest['brands'][b]['models'][m]={'status':'missing','reason':'Shared article; exact photograph still required',
            'modelSource':'https://en.wikipedia.org/wiki/'+page['title'].replace(' ','_')}

def words(s):
    return re.sub(r'[^a-z0-9]+',' ',s.casefold()).strip()

def filename_matches(b,m,filename):
    # Require the name on the file itself; never accept an article's unrelated lead photo.
    names=[f'{b} {m}']
    if b=='Li Auto': names.append('Li '+m)
    if b=='Land Rover': names.append(m if m.startswith('Range Rover') else 'Range Rover '+m)
    if b=='DS': names.append(m)
    if b=='GAC': names.append('Trumpchi '+m)
    if b=='JAC' and m in ['T6','T8']:names.append('JAC Shuailing '+m)
    if b=='FAW':names.append(m.replace('Besturn','Bestune'))
    if b=='Ferrari' and m=='812':names.append('Ferrari 812 Superfast')
    if b=='MG' and m=='4':names.append('MG4')
    text=words(filename.removeprefix('File:'))
    return any(re.search(r'\b'+re.escape(words(n))+r'\b',text) for n in names)

def choose_photo(item):
    b,m,record=item
    query_title=overrides.get((b,m),title(b,m))
    page=extra.get(query_title) or pages.get(query_title) or pages.get(title(b,m))
    if not page:return b,m,None
    try:
        files=list(ARTICLE_FILES.get(page['title'], []))
        files=[f for f in files if f.lower().endswith(('.jpg','.jpeg','.png','.webp')) and filename_matches(b,m,f)
               and not re.search(r'interior|engine|logo|badge|dashboard|steering|wheel|rear|tail|trunk',f,re.I)]
        files.sort(key=lambda f:(not bool(re.search(r'front|3.4',f,re.I)),len(f)))
        if not files:return b,m,None
        candidates=FILE_INFO
        for filename in files[:4]:
            info=candidates.get(filename,{}).get('imageinfo',[{}])[0]
            if not info.get('thumburl'):continue
            META[key(filename.removeprefix('File:'))]=info.get('extmetadata',{})
            chosen={'title':page['title'],'pageimage':filename.removeprefix('File:'),'thumbnail':{'source':info['thumburl']}}
            _,_,photo=image_for((b,m,chosen))
            if photo['status']=='downloaded':
                photo['verification']='Exact brand/model in article image filename; shared-article lead image not used'
                return b,m,photo
    except Exception as exc:
        print('Photo recovery:',b,m,type(exc).__name__,flush=True)
    return b,m,None

jobs=[(b,m,manifest['brands'][b]['models'][m]) for b,models in catalogue.items() for m in models
      if manifest['brands'][b]['models'][m].get('status')!='downloaded']
ARTICLE_FILES={}
FILE_INFO={}
article_names=[]
for b,m,_ in jobs:
    query_title=overrides.get((b,m),title(b,m))
    page=extra.get(query_title) or pages.get(query_title) or pages.get(title(b,m))
    if page and page['title'] not in article_names:article_names.append(page['title'])
for offset in range(0,len(article_names),8):
    params={'action':'query','format':'json','prop':'images','imlimit':'max','titles':'|'.join(article_names[offset:offset+8])}
    for _ in range(20):
        r=get(WIKI,params=params);r.raise_for_status();data=r.json()
        for p in data.get('query',{}).get('pages',{}).values():
            ARTICLE_FILES.setdefault(p['title'],[]).extend(f['title'] for f in p.get('images',[]))
        if 'continue' not in data:break
        params.update(data['continue'])
    print('Shared article files read',min(offset+8,len(article_names)),'/',len(article_names),flush=True)
files=[]
for b,m,_ in jobs:
    query_title=overrides.get((b,m),title(b,m))
    page=extra.get(query_title) or pages.get(query_title) or pages.get(title(b,m))
    if not page:continue
    matches=[f for f in ARTICLE_FILES.get(page['title'],[]) if f.lower().endswith(('.jpg','.jpeg','.png','.webp'))
             and filename_matches(b,m,f) and not re.search(r'interior|engine|logo|badge|dashboard|steering|wheel|rear|tail|trunk',f,re.I)]
    matches.sort(key=lambda f:(not bool(re.search(r'front|3.4',f,re.I)),len(f)))
    files.extend(matches[:4])
files=list(dict.fromkeys(files))
for offset in range(0,len(files),35):
    r=get(COMMONS,params={'action':'query','format':'json','prop':'imageinfo','iiprop':'url|extmetadata',
        'iiurlwidth':640,'titles':'|'.join(files[offset:offset+35])})
    r.raise_for_status()
    FILE_INFO.update({p['title']:p for p in r.json().get('query',{}).get('pages',{}).values()})
    print('Recovery photo metadata',min(offset+35,len(files)),'/',len(files),flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    for i,(b,m,photo) in enumerate(pool.map(choose_photo,jobs),1):
        if photo:manifest['brands'][b]['models'][m]=photo
        if i%10==0:print('Shared-article photos checked',i,'/',len(jobs),flush=True)
write('vehicle-images-manifest.json',manifest)
write('tmp/vehicle-catalogue-completed.json',catalogue)
write('tmp/vehicle-photo-metadata.json',META)
print('Refinement complete',flush=True)
