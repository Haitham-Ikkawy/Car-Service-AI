"""Validate the shipped catalogue/assets without depending on external APIs."""
import hashlib
import json
import unicodedata
from pathlib import Path

from src.config import MANUFACTURERS

ROOT = Path(__file__).resolve().parents[1]


def key(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value).casefold() if c.isalnum())


def test_catalogue_logos_and_connected_photos():
    source = (ROOT / 'src/ai_report/static/vehicle_assets.js').read_text(encoding='utf-8')
    assets = json.loads(source.split(' = ', 1)[1].rstrip(';\n'))
    manifest = json.loads((ROOT / 'vehicle-images-manifest.json').read_text(encoding='utf-8'))
    assert len({key(b) for b in MANUFACTURERS}) == len(MANUFACTURERS)
    for brand, models in MANUFACTURERS.items():
        assert models, f'{brand} has no configured models'
        assert len({key(m) for m in models}) == len(models)
        assert (ROOT / assets['logos'][key(brand)].lstrip('/')).is_file()
    seen = set()
    for brand, models in assets['images'].items():
        for model, photo in models.items():
            path = ROOT / photo['path'].lstrip('/')
            assert path.is_file()
            assert 0 < path.stat().st_size < 250_000
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest not in seen, f'Duplicate connected image: {brand} {model}'
            seen.add(digest)
            assert photo['attribution'] and photo['license'] and photo['filePage']
            record = next(r for b, data in manifest['brands'].items() if key(b) == brand
                          for m, r in data['models'].items() if key(m) == model)
            assert record['sha256'] == digest
            assert record['verifiedModel'] and record['market'] == 'unknown'
    assert len(seen) > 200
