# Vehicle asset sources

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
