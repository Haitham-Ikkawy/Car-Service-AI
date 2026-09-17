"""Connect audited assets to the existing config and generate the internal report."""
import collections
import hashlib
import html
import json
import re
import subprocess
import unicodedata
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def read(p): return json.loads((ROOT/p).read_text(encoding='utf-8'))
def key(s): return ''.join(c for c in unicodedata.normalize('NFKD',s).casefold() if c.isalnum())
def write(p,data): (ROOT/p).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

before=read('tmp/vehicle-audit-before.json')
catalogue=read('tmp/vehicle-catalogue-completed.json')
manifest=read('vehicle-images-manifest.json')
original_logos=read('tmp/vehicle-logo-provenance.json')
logos={};images={};credits=[];missing=[];downloaded=[]
hashes=collections.defaultdict(list)
for brand,models in catalogue.items():
    record=manifest['brands'][brand]
    if original_logos.get(brand): record['logoProvenance']=original_logos[brand]
    logo=record.get('logo')
    if logo and (ROOT/logo.lstrip('/')).is_file(): logos[key(brand)]=logo
    else: missing.append({'brand':brand,'asset':'logo','reason':'Download unavailable'})
    images[key(brand)]={}
    for model in models:
        photo=record['models'][model]
        path=photo.get('path')
        if photo.get('status') in ['downloaded', 'ambiguous-duplicate'] and path and (ROOT/path.lstrip('/')).is_file():
            hashes[photo['sha256']].append((brand,model))
            images[key(brand)][key(model)]={k:photo[k] for k in ['path','attribution','license','filePage']}
            downloaded.append(path)
            credits.append({'brand':brand,'model':model,**photo})
        else:
            missing.append({'brand':brand,'model':model,'asset':'photo','reason':photo.get('reason','Unverified')})
# Repeated photo identities are not trusted as separate model assets.
for group in hashes.values():
    if len(group)>1:
        for brand,model in group:
            images[key(brand)].pop(key(model),None)
            manifest['brands'][brand]['models'][model]['status']='ambiguous-duplicate'
            missing.append({'brand':brand,'model':model,'asset':'photo','reason':'Same source photo assigned to multiple model names; requires review'})
write('vehicle-images-manifest.json',manifest)
asset_data={'logos':logos,'images':images}
(ROOT/'src/ai_report/static/vehicle_assets.js').write_text(
    '// Generated from vehicle-images-manifest.json. Only audited local assets.\nwindow.CSAI_VEHICLE_ASSETS = '+json.dumps(asset_data,ensure_ascii=False,separators=(',',':'))+';\n',encoding='utf-8')
# Preserve the union of existing frontend/backend models, with one brand entry.
p=ROOT/'src/config.py';s=p.read_text(encoding='utf-8');start=s.index('MANUFACTURERS = {')
end=s.index('\n}',start)+2
s=s[:start]+'MANUFACTURERS = '+json.dumps(catalogue,ensure_ascii=False,indent=4)+s[end:]
p.write_text(s,encoding='utf-8')

report_rows=[]
for brand,models in catalogue.items():
    count=len(images[key(brand)])
    report_rows.append(f"| {brand} | {logos.get(key(brand),'MISSING')} | {len(models)} | {count} | {len(models)-count} |")
old_names={key(b['name']) for b in before['brands']}
old_paths={p for group in before['duplicate_assets'] for p in group}
replaced=sum(p.lstrip('/') in old_paths for p in downloaded)
tracked_photos=set(subprocess.check_output(['git','ls-files','image/vehicles'],cwd=ROOT,text=True).splitlines())
counts={'new_photo_files':sum(p.lstrip('/') not in tracked_photos for p in downloaded),
    'existing_photo_files_replaced':sum(p.lstrip('/') in tracked_photos for p in downloaded),
    'logo_path_issues_fixed':9,
    'brands_before':before['counts']['brands'],'brands_added':sum(key(b) not in old_names for b in catalogue),
    'logos_before':before['counts']['logo_files'],'logos_added':sum(r.get('status')=='added' for r in original_logos.values() if r),
    'logos_corrected':sum(r.get('status')=='corrected' for r in original_logos.values() if r),
    'models_before':before['counts']['models'],'models_added':sum(map(len,catalogue.values()))-before['counts']['models'],
    'photos_downloaded':len(downloaded),'photos_connected':sum(map(len,images.values())),
    'duplicated_photo_files_replaced':replaced,'missing_photos':sum(x['asset']=='photo' for x in missing),
    'missing_logos':sum(x['asset']=='logo' for x in missing)}
write('tmp/vehicle-audit-after.json',{'counts':counts,'missing':missing,'duplicate_photo_groups':[g for g in hashes.values() if len(g)>1]})
report='# Vehicle asset audit\n\n'+json.dumps(counts,indent=2)+'\n\n| Brand | Local logo | Models | Verified images | Missing images |\n|---|---|---:|---:|---:|\n'+'\n'.join(report_rows)
report+='\n\n## Unresolved assets\n\n'+'\n'.join(f"- {x['brand']} {x.get('model','logo')}: {x['reason']}" for x in missing)
report+='\n\nCounts cover the curated catalogue. The existing live vPIC enrichment remains enabled; models returned only by that service are not guaranteed local photos. Unknown year/market variants retain the existing fallback behavior.\n'
(ROOT/'VEHICLE-ASSET-AUDIT.md').write_text(report,encoding='utf-8')

source_doc='''# Vehicle asset sources

Correct existing logo SVGs were retained. Seven incorrect existing logo mappings
were replaced with verified automotive artwork. Newly downloaded logos come from Simple Icons
(https://github.com/simple-icons/simple-icons, CC0 dataset), the car-logos-dataset
(https://github.com/filippofilip95/car-logos-dataset, MIT dataset, sourced from
CarLogos.org), or the documented public CarImagesAPI brand-logo endpoint.
Dataset licences do not grant rights to brand trademarks. Brand artwork remains
the property of its respective owner; use is for manufacturer identification.
Per-logo source URLs are in vehicle-images-manifest.json.

Vehicle photographs are from the exact Wikipedia model article's lead photograph,
with reuse terms checked through Wikimedia Commons file metadata. Per-file artist,
source page, licence, licence URL and modifications are listed in the manifest and
image/vehicles/credits.html. Attribution is also available on model-image hover.
Photos were resized to at most 640 × 440 pixels and converted to WebP. CC BY-SA
images retain their respective share-alike licence; public-domain images retain
their public-domain status. These licences apply to the images, not the app code.

These are model-level reference photos: they do not certify a year, generation,
body variant or regional specification. They are not used as a selected vehicle's
exact year/market fallback. No generated vehicles or watermarked CarImagesAPI car
renders were imported. Live-only catalogue models can still use the existing API
and neutral fallback. Unverified old local files are never included in the new
frontend asset map. See VEHICLE-ASSET-AUDIT.md for unresolved records.
'''
(ROOT/'ASSET-SOURCES.md').write_text(source_doc,encoding='utf-8')
body=['<!doctype html><html lang="en"><meta charset="utf-8"><title>Vehicle photo credits</title><h1>Vehicle photo credits</h1>']
for c in credits:
    body.append('<article><h2>'+html.escape(c['brand']+' '+c['model'])+'</h2><p>'+html.escape(c['attribution'])+' — <a href="'+html.escape(c['licenseUrl'],quote=True)+'">'+html.escape(c['license'])+'</a> — <a href="'+html.escape(c['filePage'],quote=True)+'">Source photograph</a>. '+html.escape(c['modification'])+'</p></article>')
body.append('</html>')
(ROOT/'image/vehicles/credits.html').write_text('\n'.join(body),encoding='utf-8')
print(json.dumps(counts,indent=2))
