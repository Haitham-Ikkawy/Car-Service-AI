/* One catalogue-backed resolver for search and speech transcripts. */
(function (root) {
  const normalize = value => String(value || '').normalize('NFKC').toLowerCase()
    .replace(/[\u064b-\u065f\u0670\u0640]/g, '').replace(/[أإآٱ]/g, 'ا')
    .replace(/ى/g, 'ي').replace(/ة/g, 'ه')
    .replace(/[٠-٩]/g, c => String(c.charCodeAt(0) - 1632))
    .replace(/[۰-۹]/g, c => String(c.charCodeAt(0) - 1776))
    .replace(/[^a-z0-9\u0621-\u064a]+/g, ' ').trim();
  const aliases = {};
  // Pronunciations supplement the catalogue; they never introduce new vehicles.
  const rows = `Acura|اكورا
Alfa Romeo|الفا روميو
Aston Martin|استون مارتن
Audi|اودي
Bentley|بنتلي
BMW|بي ام دبليو|بي إم دبليو|بي ام
Buick|بويك
Cadillac|كاديلاك
Chevrolet|شيفروليه|شفروليه|شفروليت
Chrysler|كرايسلر
Citroen|ستروين|سيتروين
Dodge|دودج
Ferrari|فيراري
Fiat|فيات
Ford|فورد
Genesis|جينيسيس|جنسس
GMC|جي ام سي
Honda|هوندا
Hyundai|هيونداي|هونداي
Infiniti|انفينيتي
Jaguar|جاغوار|جاكوار
Jeep|جيب
Kia|كيا
Lamborghini|لامبورغيني
Land Rover|لاند روفر|لاندروفر
Lexus|لكزس|ليكزس
Lincoln|لينكولن
Maserati|مازيراتي
Mazda|مازدا
McLaren|مكلارين|ماكلارين
Mercedes-Benz|مرسيدس|مرسيدس بنز
Mitsubishi|ميتسوبيشي|متسوبيشي
Nissan|نيسان
Opel|اوبل
Peugeot|بيجو
Porsche|بورش|بورشه
Ram|رام
Renault|رينو
Rolls-Royce|رولز رويس
Seat|سيات
Skoda|سكودا
Smart|سمارت
Subaru|سوبارو
Suzuki|سوزوكي
Tesla|تسلا|تيسلا
Toyota|تويوتا
Volkswagen|فولكس فاجن|فولكسواجن|فولكس واجن
Volvo|فولفو
Dacia|داسيا|داتشيا
Mini|ميني
Sandero|سانديرو
Logan|لوجان|لوغان
Jogger|جوغر|جوجر
Cooper|كوبر
Clubman|كلوبمان
Countryman|كانتريمان
Enyaq|انياك
Accord|اكورد
Civic|سيفيك
CR-V|سي ار في
HR-V|اتش ار في
RAV4|راف فور|راف 4
Camry|كامري
Corolla|كورولا
Land Cruiser|لاند كروزر|لاندكروزر
Yaris|يارس|ياريس
Prius|بريوس
Hilux|هايلوكس|هايلكس
City|سيتي
Fit|فيت
Giulia|جوليا
Stelvio|ستلفيو
Tonale|تونالي
Vantage|فانتاج
Continental GT|كونتيننتال جي تي
Flying Spur|فلاينج سبير
Bentayga|بنتايجا
Encore|انكور
Envision|انفيجن
LaCrosse|لاكروس
Escalade|اسكاليد
Spark|سبارك
Cruze|كروز
Malibu|ماليبو
Trailblazer|تريل بليزر|تريل بليزر
Equinox|اكوينوكس
Pacifica|باسيفيكا
Berlingo|بيرلينجو
Challenger|تشالنجر|شالنجر
Charger|تشارجر|شارجر
Durango|دورانجو
Roma|روما
Panda|باندا
Punto|بونتو
Tipo|تيبو
Fiesta|فييستا|فيستا
Focus|فوكس|فوكاس
Mustang|موستانج|مستنج
Ranger|رينجر|رانجر
Escape|اسكيب
Explorer|اكسبلورر
Terrain|تيرين
Acadia|اكاديا
Yukon|يوكن|يوكون
Sierra|سييرا
Tucson|توسان|توسون
Santa Fe|سانتا في
Elantra|النترا|الانترا
Kona|كونا
Renegade|رينيجيد
Compass|كومباس
Cherokee|شيروكي
Grand Cherokee|جراند شيروكي|غراند شيروكي
Wrangler|رانجلر|ورانجلر
Rio|ريو
Ceed|سيد
Sportage|سبورتاج
Sorento|سورينتو|سورنتو
Picanto|بيكانتو|بيكانطو
Huracan|هوراكان
Urus|اوروس
Revuelto|ريفويلتو
Range Rover|رينج روفر|رنج روفر
Discovery|ديسكفري|ديسكوفري
Defender|ديفندر
Evoque|ايفوك
Corsair|كورسير
Aviator|افياتور
Navigator|نافيجيتور|نافيجاتور
Ghibli|جيبلي|غيبلي
Levante|ليفانتي
Grecale|جريكالي
GranTurismo|جران توريزمو
Artura|ارتورا
Lancer|لانسر
Outlander|اوتلاندر
Pajero|باجيرو
Micra|ميكرا
Qashqai|قشقاي|كاشكاي
X-Trail|اكس تريل
Leaf|ليف
Altima|التيما|التيما
Corsa|كورسا
Astra|استرا
Insignia|انسيجنيا
Mokka|موكا
Grandland|جراند لاند
Cayenne|كايين|كايان
Macan|ماكان
Taycan|تايكان
Panamera|باناميرا
Clio|كليو
Megane|ميجان
Captur|كابتشر|كابتور
Duster|داستر
Arkana|اركانا
Ghost|جوست|غوست
Phantom|فانتوم
Cullinan|كولينان
Spectre|سبيكتر
Ibiza|ابيزا
Leon|ليون
Arona|ارونا
Ateca|اتيكا
Tarraco|تاراكو
Fabia|فابيا
Octavia|اوكتافيا
Superb|سوبيرب|سوبرب
Karoq|كاروك
Kodiaq|كودياك
ForTwo|فور تو
ForFour|فور فور
Impreza|امبريزا
Forester|فورستر
Outback|اوتباك
Swift|سويفت
Baleno|بالينو
Vitara|فيتارا
Jimny|جيمني|جمني
Ertiga|ارتيجا
Golf|جولف|غولف
Passat|باسات
Tiguan|تيجوان|تيغوان
Polo|بولو
Touareg|طوارق|توارج
Arteon|ارتيون`;
  rows.split('\n').forEach(row => { const [name, ...values] = row.split('|'); aliases[name] = values; });
  const letters = ['اي','بي','سي','دي','اي','اف','جي','اتش','اي','جي','كي','ال','ام','ان','او','بي','كيو','ار','اس','تي','يو','في','دبليو','اكس','واي','زد'];
  function names(name) {
    const spelled = name.toLowerCase().replace(/[a-z]/g, c => ' ' + letters[c.charCodeAt(0)-97] + ' ');
    const variants = [name, spelled, ...(aliases[name] || [])];
    // Catalogue codes and families (A-Class, 3 Series, Model Y, etc.).
    variants.push(name.replace(/Class/gi, 'كلاس').replace(/Series/gi, 'سيريز').replace(/Model/gi, 'موديل')
      .replace(/[a-z]/gi, c => ' ' + letters[c.toLowerCase().charCodeAt(0)-97] + ' '));
    return [...new Set(variants.map(normalize))];
  }
  function match(text, name) {
    return names(name).some(alias => (' ' + text + ' ').includes(' ' + alias + ' ') ||
      (alias.replace(/ /g,'').length > 2 && text.split(' ').some(word => word === alias.replace(/ /g,''))));
  }
  const markets = {US:['us','usa','american','امريكي','امريكية','اميركي','اميركية'], JP:['jp','japan','japanese','jdm','ياباني','يابانية'], EU:['eu','european','europe','اوروبي','اوروبية'], GCC:['gcc','gulf','خليجي','خليجية','خليج'], Other:['other','اخرى','اخر']};
  function resolve(text, catalogue) {
    text = normalize(text);
    const yearMatch = text.match(/\b(?:19|20)\d{2}\b/);
    const year = yearMatch ? Number(yearMatch[0]) : '';
    const foundMarkets = Object.entries(markets).filter(([, list]) => list.some(alias => match(text, alias)));
    const market = foundMarkets.length === 1 ? foundMarkets[0][0] : '';
    const brands = catalogue.filter(b => match(text, b.name));
    const candidates = [];
    for (const brand of brands.length ? brands : catalogue) {
      const models = brand.models.filter(m => match(text, m) && !(normalize(m) === String(year)));
      // A longer named model wins over its contained short name (Grand Cherokee).
      const exact = models.filter(m => !models.some(other => other !== m && normalize(other).includes(normalize(m))));
      exact.forEach(model => candidates.push({brand:brand.name, model, year, market}));
    }
    return {vehicle:candidates.length === 1 ? candidates[0] : null, candidates,
      brand:brands.length === 1 ? brands[0].name : '', year, market,
      confident:candidates.length === 1 && foundMarkets.length <= 1 && (brands.length === 1 || normalize(candidates[0].model).length > 3)};
  }
  root.DiagnosisVehicleResolver = {resolve, normalize, names};
})(typeof window !== 'undefined' ? window : globalThis);
