"""Catalogue completeness and rejection of unverified vehicle imagery."""
import asyncio
from src.car_database import vehicle_api as v


def test_model_grid_can_request_beyond_twelve(auth_client, monkeypatch):
    v._cache.clear()
    v._locks.clear()
    async def upstream(url, *args, **kwargs):
        return {'Results': [{'Model_Name': f'Model {i:02d}'} for i in range(30)] + [{'Model_Name':'M4'}]}
    monkeypatch.setattr(v, '_get_json', upstream)
    result = auth_client.get('/api/vehicles/models?make=BMW&limit=1000').json()['items']
    assert len(result) > 30
    assert {'M4','Model 29','3 Series'} <= {r['value'] for r in result}
    assert all(r['image'] is None for r in result)
    assert len(auth_client.get('/api/vehicles/models?make=BMW').json()['items']) == 12


def test_offline_models_and_deduplication(monkeypatch):
    v._cache.clear()
    v._locks.clear()
    async def offline(*args, **kwargs):
        raise OSError('offline')
    monkeypatch.setattr(v, '_get_json', offline)
    result = asyncio.run(v.models('Skoda', limit=1000))
    values = [r['value'] for r in result]
    assert 'Octavia' in values and 'Enyaq' in values
    assert len(values) == len(set(values))


def test_mislabeled_local_photos_never_escape():
    for model in ['Accord', 'Civic', 'CR-V']:
        assert v.local_image('Honda', model) == ''


def test_photo_rejects_wrong_model_redirect_and_year(monkeypatch):
    v._cache.clear()
    v._locks.clear()
    async def wrong_model(*args, **kwargs):
        return {'query': {'pages': {'1': {'title':'BMW M3', 'thumbnail':{'source':'https://example.com/m3.jpg'}}}}}
    monkeypatch.setattr(v, '_get_json', wrong_model)
    assert asyncio.run(v.photo_url('BMW', 'M4')) == ''
    async def generic_year(*args, **kwargs):
        return {'query': {'pages': {'1': {'title':'Honda Accord', 'thumbnail':{'source':'https://example.com/newest-accord.jpg'}}}}}
    monkeypatch.setattr(v, '_get_json', generic_year)
    assert asyncio.run(v.photo_url('Honda', 'Accord', '2013')) == ''


def test_exact_model_photo_and_no_broad_search(monkeypatch):
    v._cache.clear()
    v._locks.clear()
    calls = []
    async def exact(url, params, **kwargs):
        calls.append(params)
        return {'query': {'pages': {'1': {'title':'Honda CR-V', 'thumbnail':{'source':'https://example.com/crv.jpg'}}}}}
    monkeypatch.setattr(v, '_get_json', exact)
    assert asyncio.run(v.photo_url('Honda', 'CR-V')) == 'https://example.com/crv.jpg'
    assert all('generator' not in params for params in calls)
