"""One-off catalogue audit/import. All sources and unresolved assets go in the manifest."""
import concurrent.futures
import hashlib
import html
import io
import json
import re
import sys
import time
import threading
import unicodedata
from pathlib import Path
from urllib.parse import quote

import httpx
from PIL import Image

sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
HEADERS = {'User-Agent': 'CarServiceAIAssetAudit/1.0 (vehicle catalogue asset verification)'}
CLIENT = httpx.Client(headers=HEADERS, timeout=25, follow_redirects=True)
WIKI = 'https://en.wikipedia.org/w/api.php'
COMMONS = 'https://commons.wikimedia.org/w/api.php'
META = {}
GATE = threading.Lock()
NEXT_REQUEST = 0.0

def get(url, **kwargs):
    global NEXT_REQUEST
    for attempt in range(5):
        with GATE:
            delay = NEXT_REQUEST - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            NEXT_REQUEST = time.monotonic() + 0.4
        response = CLIENT.get(url, **kwargs)
        if response.status_code != 429:
            return response
        pause = max(1, int(response.headers.get('retry-after', '60')))
        print('Respecting upstream rate limit; retry in', pause, 'seconds', flush=True)
        with GATE:
            NEXT_REQUEST = max(NEXT_REQUEST, time.monotonic() + pause)
    return response

def key(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s).casefold() if c.isalnum())

def slug(s):
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    return s.lower().replace(' ', '-').replace('/', '-').replace('#', '')

def clean(s):
    return html.unescape(re.sub('<[^>]+>', '', str(s or ''))).strip()

def read(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))

def write(name, data):
    (ROOT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def title(brand, model):
    aliases = {'DS': '', 'GAC': 'Trumpchi', 'FAW': '', 'Dongfeng': '', 'BAIC': 'Beijing',
               'Great Wall':'Great Wall', 'Mini':'Mini', 'Citroen':'Citroën', 'Skoda':'Škoda', 'Seat':'SEAT'}
    name = f'{aliases.get(brand, brand)} {model}'.strip()
    return {'Honda NSX':'Honda NSX', 'Chevrolet Bolt':'Chevrolet Bolt',
            'Porsche 718 Boxster':'Porsche 718 Boxster', 'Porsche 718 Cayman':'Porsche 718 Cayman'}.get(name, name)

def pages_for(titles):
    out = {}
    for offset in range(0, len(titles), 35):
        batch = titles[offset:offset+35]
        try:
            r = get(WIKI, params={'action':'query','format':'json','redirects':1,
                'prop':'pageimages','piprop':'thumbnail|name','pithumbsize':640,'titles':'|'.join(batch)})
            r.raise_for_status()
            query = r.json().get('query', {})
            pages = {p['title']:p for p in query.get('pages',{}).values() if 'missing' not in p}
            aliases = {x['from']:x['to'] for field in ['normalized','redirects'] for x in query.get(field,[])}
            for wanted in batch:
                actual = wanted
                for _ in range(6):
                    actual = aliases.get(actual, actual)
                if actual in pages:
                    out[wanted] = pages[actual]
        except Exception as exc:
            print('Page batch failed:', type(exc).__name__, flush=True)
        print('Verified model pages', min(offset+35,len(titles)), '/', len(titles), flush=True)
    return out

def same_model(wanted, actual):
    # Never follow a model redirect into a different vehicle. Parenthetical
    # disambiguation is acceptable; generation/model-name substitution is not.
    return key(wanted) == key(re.sub(r'\s*\((?:car|automobile|first generation|second generation)\)$','',actual,flags=re.I))

def image_for(item):
    brand, model, page = item
    result = {'sourcePage':'https://en.wikipedia.org/wiki/'+quote(page['title'].replace(' ','_')),
              'verifiedModel':True, 'scope':'model', 'year':None, 'market':'unknown'}
    filename = page.get('pageimage','')
    url = page.get('thumbnail',{}).get('source','')
    if not url or not filename or not filename.lower().endswith(('.jpg','.jpeg','.png','.webp')):
        return brand, model, dict(result, status='missing', reason='No raster vehicle photograph on verified model page')
    try:
        metadata = META.get(key(filename), {})
        fields = {k:clean(v.get('value','')) for k,v in metadata.items()}
        license_name = fields.get('LicenseShortName','')
        if not (license_name.startswith(('CC BY','CC0','Public domain')) or license_name == 'PDM'):
            return brand, model, dict(result,status='missing',reason='Reusable photo license not verified',license=license_name)
        r = get(url)
        r.raise_for_status()
        if len(r.content)>8_000_000:
            raise ValueError('Oversized source')
        img=Image.open(io.BytesIO(r.content))
        if img.width<180 or img.height<90:
            raise ValueError('Photo too small')
        img.thumbnail((640,440))
        path=Path('image/vehicles')/slug(brand)/(slug(model)+'.webp')
        (ROOT/path).parent.mkdir(parents=True,exist_ok=True)
        img.convert('RGB').save(ROOT/path,'WEBP',quality=80,method=6)
        result.update(status='downloaded',path='/'+path.as_posix(),sourceUrl=url,
            sourceType='wikimedia_commons',imageSource='Wikimedia Commons',
            attribution=fields.get('Artist',''),license=license_name,licenseUrl=fields.get('LicenseUrl',''),
            description=fields.get('ImageDescription',''),
            filePage='https://commons.wikimedia.org/wiki/File:'+quote(filename.replace(' ','_')),
            modification='Resized to at most 640×440 and converted to WebP',
            sha256=hashlib.sha256((ROOT/path).read_bytes()).hexdigest())
        return brand,model,result
    except Exception as exc:
        return brand,model,dict(result,status='missing',reason=type(exc).__name__+' downloading licensed photo')

def logo_for(brand, existing, dataset):
    if existing and (ROOT/existing.lstrip('/')).is_file():
        return brand, {'path':existing,'status':'existing'}
    for ext in ['svg','png','webp']:
        path=Path('image/car_logos')/(slug(brand)+'.'+ext)
        if (ROOT/path).is_file():
            return brand, {'path':'/'+path.as_posix(),'status':'connected-existing'}
    entry=next((d for d in dataset if key(d['name'])==key(brand) or key(d['slug'])==key(brand)),None)
    candidates=[('svg','https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/'+key(brand)+'.svg')]
    if entry:
        candidates.append(('png',entry['image']['thumb']))
    candidates.append(('png','https://carimagesapi.com/brand-logo?make='+quote(brand)))
    for ext,url in candidates:
        try:
            r=CLIENT.get(url)
            r.raise_for_status()
            path=Path('image/car_logos')/(slug(brand)+'.'+ext)
            if ext=='svg':
                if '<svg' not in r.text or '<script' in r.text or '<!ENTITY' in r.text:
                    continue
                (ROOT/path).write_bytes(r.content)
            else:
                img=Image.open(io.BytesIO(r.content)).convert('RGBA')
                img.thumbnail((256,256))
                img.save(ROOT/path,'PNG',optimize=True)
            return brand, {'path':'/'+path.as_posix(),'status':'added','sourceUrl':url,
                'license':'Brand trademark; artwork rights remain with respective owners. See ASSET-SOURCES.md.'}
        except Exception:
            continue
    return brand, {'status':'missing','reason':'No verified downloadable logo available'}

def main():
    before=read('tmp/vehicle-audit-before.json')
    additions=read('tmp/vehicle-additions.json')
    catalogue={b['name']:list(b['models']) for b in before['brands']}
    proposed={}
    # Regional names for the same model must not create duplicate cards.
    duplicate_aliases={('Honda','Jazz'),('Kia','Optima'),('Kia','Cerato'),('BYD','Yuan Plus'),('Mitsubishi','L200')}
    for brand, names in additions.items():
        old=catalogue.setdefault(brand,[])
        proposed[brand]=[m for m in names.split('|') if key(m) not in {key(v) for v in old} and (brand,m) not in duplicate_aliases]
    titles=list(dict.fromkeys(title(b,m) for b in catalogue for m in catalogue[b]+proposed.get(b,[])))
    cache=ROOT/'tmp/vehicle-wiki-pages.json'
    pages=read('tmp/vehicle-wiki-pages.json') if cache.exists() else {}
    pages.update(pages_for([t for t in titles if t not in pages]))
    write('tmp/vehicle-wiki-pages.json',pages)
    rejected=[]
    for brand,models in proposed.items():
        for model in models:
            wanted=title(brand,model);page=pages.get(wanted)
            if page and same_model(wanted,page['title']):
                catalogue[brand].append(model)
            else:
                rejected.append({'brand':brand,'model':model,'reason':'Exact model page not verified','resolved':page['title'] if page else None})
    dataset=CLIENT.get('https://raw.githubusercontent.com/filippofilip95/car-logos-dataset/master/logos/data.json').json()
    old_logos={b['name']:b['logo'] for b in before['brands']}
    logos={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for brand,record in pool.map(lambda b:logo_for(b,old_logos.get(b),dataset),catalogue):
            logos[brand]=record
    manifest=read('vehicle-images-manifest.json')
    manifest['_comment']='Verified local model photographs and logo provenance. Model photos do not establish year, body variant or market.'
    jobs=[]
    for brand,models in catalogue.items():
        record=manifest['brands'].setdefault(brand,{'models':{}})
        record['logo']=logos[brand].get('path')
        record['logoProvenance']=logos[brand]
        for model in models:
            wanted=title(brand,model);page=pages.get(wanted)
            if page and same_model(wanted,page['title']):
                jobs.append((brand,model,page))
            else:
                record['models'][model]={'status':'missing','reason':'Exact model page not verified'}
    metadata_cache=ROOT/'tmp/vehicle-photo-metadata.json'
    if metadata_cache.exists():
        META.update(read('tmp/vehicle-photo-metadata.json'))
    filenames=list(dict.fromkeys(p['pageimage'] for _,_,p in jobs if p.get('pageimage') and key(p['pageimage']) not in META))
    for offset in range(0,len(filenames),35):
        batch=filenames[offset:offset+35]
        try:
            r=get(COMMONS,params={'action':'query','format':'json','prop':'imageinfo','iiprop':'extmetadata',
                'titles':'|'.join('File:'+f for f in batch)})
            r.raise_for_status()
            for page in r.json().get('query',{}).get('pages',{}).values():
                if page.get('imageinfo'):
                    META[key(page['title'].removeprefix('File:'))]=page['imageinfo'][0].get('extmetadata',{})
        except Exception as exc:
            print('Metadata batch failed:',type(exc).__name__,flush=True)
        write('tmp/vehicle-photo-metadata.json',META)
        print('Photo licences checked',min(offset+35,len(filenames)),'/',len(filenames),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for i,(brand,model,record) in enumerate(pool.map(image_for,jobs),1):
            manifest['brands'][brand]['models'][model]=record
            if i%20==0:print('Images processed',i,'/',len(jobs),flush=True)
    write('vehicle-images-manifest.json',manifest)
    write('tmp/vehicle-catalogue-completed.json',catalogue)
    write('tmp/vehicle-candidates-unresolved.json',rejected)
    write('tmp/vehicle-logos-results.json',logos)
    print('DONE',len(catalogue),'brands',sum(map(len,catalogue.values())),'models',flush=True)

if __name__=='__main__':
    main()
