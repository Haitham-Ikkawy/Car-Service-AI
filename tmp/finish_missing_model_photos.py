"""Import only remaining missing photos, using reviewed article/category identities."""
from complete_vehicle_assets import get,COMMONS,META,key,read,write,image_for

# Article aliases were checked in tmp/missing-model-evidence.json. Specific
# filenames were reviewed from article images and named Commons categories.
selected = [
 ('Acura','NSX','Honda NSX (second generation)','2022 Acura NSX Type S, front 5.4.25.jpg'),
 ('Alfa Romeo','Junior','Alfa Romeo Junior (2024)','Alfa Romeo Junior Ibrida DSC 7219.jpg'),
 ('Buick','Verano','Buick Verano (North America)','2012 Buick Verano -- 04-30-2012.JPG'),
 ('Ram','2500','Ram 2500 (DT)','2025 RAM 2500 Laramie Sport Crew Cab 4x4, front NYIAS 2025.jpg'),
 ('Smart','#1','Smart 1','Smart ♯1 Pro – f 11102025.jpg'),
 ('Smart','#3','Smart 3','Smart Hashtag 3 DSC 7992.jpg'),
 ('Smart','#5','Smart 5','Smart Hashtag 5 Premium autoMOBIL Tübingen 2025 DSC 2755 (cropped).jpg'),
 ('Volvo','EX40','Volvo EX40','Volvo EX40 Ultra Twin Motor (ZAA-XE400AXCE2) front.jpg'),
 ('Volvo','EC40','Volvo C40','2024 Volvo EC40 Ultra Twin Motor Black Edition.jpg'),
 ('Geely','Atlas','Geely Boyue','2019 Geely Boyue (facelift), front 8.3.23.jpg'),
 ('Geely','Okavango','Geely Haoyue','2022 Geely Haoyue.jpg'),
 ('Geely','Tugella','Geely Xingyue S','2019 Geely Xingyue (front).jpg'),
 ('Geely','Geometry C','Geometry C','Geometry C 012.jpg'),
 ('Chery','Arrizo 6','Chery Arrizo 5 Plus','Chery Arrizo GX 008.jpg'),
 ('Great Wall','Poer','GWM Cannon','2023 Great-Wall Pao Passenger Edition (facelift), front 8.18.23.jpg'),
 ('Li Auto','One','Li One','2020 Lixiang ONE (front).jpg'),
 ('GAC','GN6','Trumpchi M6','Trumpchi GM6 IMG001.jpg'),
 ('JAC','J7','JAC Binyue','JAC Binyue facelift -- Auto Chongqing -- 2012-06-07.jpg'),
 ('JAC','T8','JAC Shuailing T8','JAC Frison.jpg'),
 ('JAC','T9','JAC T9 Ute','JAC Hunter facelift 001.jpg'),
 ('BAIC','X35','Beijing X3','2018 BAIC Senova X35, front 8.11.18.jpg'),
 ('FAW','Besturn B50','Bestune B50','Besturn B50 II 03.jpg'),
 ('Mahindra','XUV400','Mahindra XUV300','2023 Mahindra XUV 400 EL EV , Ashiana Brahmananda, Jamshedpur, Jharkhand, India ( Ank Kumar, Infosys Limited ) 01.jpg'),
 ('Abarth','695','Fiat 500 (2007)','Abarth695TributoFerraridc.jpg'),
]
manifest=read('vehicle-images-manifest.json')
jobs=[(b,m,t,f) for b,m,t,f in selected if manifest['brands'][b]['models'][m].get('status')!='downloaded']
response=get(COMMONS,params={'action':'query','format':'json','prop':'imageinfo','iiprop':'url|extmetadata',
                            'iiurlwidth':800,'titles':'|'.join('File:'+f for _,_,_,f in jobs)})
response.raise_for_status()
pages={key(p['title'].removeprefix('File:')):p for p in response.json().get('query',{}).get('pages',{}).values()}
for brand,model,title,filename in jobs:
    info=pages.get(key(filename),{}).get('imageinfo',[{}])[0]
    if not info.get('thumburl'):
        print(brand,model,'no thumbnail',flush=True)
        continue
    META[key(filename)]=info.get('extmetadata',{})
    _,_,photo=image_for((brand,model,{'title':title,'pageimage':filename,'thumbnail':{'source':info['thumburl']}}))
    if photo['status']=='downloaded':
        photo['verification']='Reviewed model article / Commons category and named photograph. Regional name or model-name alias retained where documented; no claim of exact year or market.'
        manifest['brands'][brand]['models'][model]=photo
    print(brand,model,photo['status'],photo.get('reason',''),flush=True)
write('vehicle-images-manifest.json',manifest)
