"""Search Commons for remaining exact named models; no generic vehicle fallback."""
import concurrent.futures
import re
from complete_vehicle_assets import ROOT, COMMONS, META, get, key, read, write, image_for, clean

manifest=read('vehicle-images-manifest.json')
missing=read('tmp/vehicle-audit-after.json')['missing']

def words(s):return re.sub(r'[^a-z0-9]+',' ',s.casefold()).strip()
def recover(item):
    b,m=item['brand'],item['model']
    name=f'{b} {m}'
    if b=='Li Auto':name='Li '+m
    if b=='FAW':name=m.replace('Besturn','Bestune')
    if b=='Great Wall' and m=='Poer':name='Great Wall Poer'
    try:
        r=get(COMMONS,params={'action':'query','format':'json','generator':'search','gsrnamespace':6,
            'gsrsearch':'"'+name+'"','gsrlimit':12,'prop':'imageinfo','iiprop':'url|extmetadata','iiurlwidth':640})
        r.raise_for_status()
        pages=list(r.json().get('query',{}).get('pages',{}).values())
        pages.sort(key=lambda p:(not bool(re.search(r'front|3.4',p['title'],re.I)),len(p['title'])))
        for p in pages:
            filename=p['title'].removeprefix('File:')
            info=p.get('imageinfo',[{}])[0]
            meta=info.get('extmetadata',{})
            description=clean(meta.get('ImageDescription',{}).get('value',''))
            if not filename.lower().endswith(('.jpg','.jpeg','.png','.webp')) or not info.get('thumburl'):continue
            if re.search(r'interior|engine|logo|badge|dashboard|steering|rear|tail|trunk',filename,re.I):continue
            if not any(re.search(r'\b'+re.escape(words(name))+r'\b',words(value)) for value in [filename,description]):continue
            META[key(filename)]=meta
            page={'title':name,'pageimage':filename,'thumbnail':{'source':info['thumburl']}}
            _,_,photo=image_for((b,m,page))
            if photo['status']=='downloaded':
                photo.pop('sourcePage',None)
                photo['verification']='Exact brand/model name in Commons file title or description; reusable licence verified'
                return b,m,photo
    except Exception as exc:print(b,m,type(exc).__name__,flush=True)
    return b,m,None

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    for b,m,photo in pool.map(recover,[i for i in missing if i['asset']=='photo']):
        if photo:manifest['brands'][b]['models'][m]=photo
        print(b,m,'downloaded' if photo else 'unresolved',flush=True)
write('vehicle-images-manifest.json',manifest)
