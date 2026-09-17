"""Real Chromium tests against the running app.

Speech transcripts and the external vision provider are controlled fixtures;
navigation, rendering, uploads, validation and session persistence run normally.
Run: python -m pytest tests/test_diagnose_browser.py -q
Requires playwright and a locally installed Chrome or Edge browser.
"""
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn

playwright = pytest.importorskip('playwright.sync_api')


@pytest.fixture
def browser_page(auth_client, monkeypatch):
    from src.app import app
    from src.car_database import twin

    def identify(content, mime, user):
        assert content and mime.startswith('image/')
        time.sleep(0.4)  # Verify that the preview is visible while waiting.
        return {'manufacturer': 'Honda', 'model': 'Accord', 'year': 2023,
                'confidence': 0.98}

    monkeypatch.setattr(twin, 'identify_vehicle_image', identify)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome', headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(10000)
        # Keep catalogue/network enrichment deterministic, using the real local catalogue.
        page.route('**/api/vehicles/makes*', lambda r: r.fulfill(json={'items': []}))
        page.route('**/api/vehicles/models*', lambda r: r.fulfill(json={'items': []}))
        page.route('**/api/vehicles/engines*', lambda r: r.fulfill(json={'items': []}))
        page.route('**/api/vehicles/image*', lambda r: r.abort())
        errors = []
        page.on('pageerror', lambda error: errors.append(error.stack))
        yield page, f'http://127.0.0.1:{port}'
        browser.close()
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
        assert not errors, errors


def test_history(browser_page):
    page, base = browser_page
    for previous in ['/my-diagnoses', '/chat']:
        for browser_back in [False, True]:
            page.goto(base + previous)
            page.locator('a[href="/diagnose"]').first.click()
            page.wait_for_selector('#dz-back-vehicle')
            count = page.evaluate('history.length')
            page.reload()
            assert page.evaluate('history.length') == count
            if browser_back:
                page.go_back()  # Same history operation as browser mouse Back.
            else:
                page.locator('#dz-back-vehicle').click()
            page.wait_for_url(base + previous)
    page.locator('a[href="/diagnose"]').first.click()
    history_count = page.evaluate('history.length')
    page.locator('#dz-vehicle-search').fill('Honda Accord 2023 US')
    playwright.expect(page.locator('#dz-car-selected-brand')).to_have_text('Honda')
    page.locator('#dz-continue-vehicle').click()
    page.locator('#dz-back-describe').click()
    page.locator('#dz-continue-vehicle').click()
    assert page.evaluate('history.length') == history_count
    page.go_back()
    page.wait_for_url(base + '/chat')
    direct = page.context.new_page()
    direct.goto(base + '/diagnose')
    direct.locator('#dz-back-vehicle').click()
    direct.wait_for_url(base + '/my-diagnoses')
    direct.close()


@pytest.mark.parametrize('text,brand,model,year,market', [
    ('معي هوندا أكورد 2023 أمريكية', 'Honda', 'Accord', '2023', 'US'),
    ('عندي هوندا أكورد موديل 2023 أمريكي', 'Honda', 'Accord', '2023', 'US'),
    ('معي تويوتا كامري 2022 خليجي', 'Toyota', 'Camry', '2022', 'GCC'),
    ('Honda Accord 2023 أمريكية', 'Honda', 'Accord', '2023', 'US'),
    ('Honda Accord 2023 American', 'Honda', 'Accord', '2023', 'US'),
    ('بدي اختار هوندا أكورد ٢٠٢٣ يابانية', 'Honda', 'Accord', '2023', 'JP'),
    ('عندي فولكس فاجن جولف 2020 أوروبية', 'Volkswagen', 'Golf', '2020', 'EU'),
    ('معي داسيا سانديرو 2022 خليجي', 'Dacia', 'Sandero', '2022', 'GCC'),
])
def test_vehicle_text(browser_page, text, brand, model, year, market):
    page, base = browser_page
    page.goto(base + '/diagnose')
    page.locator('#dz-vehicle-search').fill(text)
    playwright.expect(page.locator('#dz-car-selected-brand')).to_have_text(brand)
    playwright.expect(page.locator('#dz-car-selected-model')).to_contain_text(model)
    playwright.expect(page.locator('#dz-year-select')).to_have_value(year)
    playwright.expect(page.locator('#dz-market-select')).to_have_value(market)
    with page.expect_response(lambda response: '/api/diag-sessions/' in response.url
                              and response.url.endswith('/update') and response.status == 200):
        page.locator('#dz-continue-vehicle').click()
        playwright.expect(page.locator('#dz-vehicle-badge-text')).to_contain_text(f'{brand} {model} {year} {market}')
    # Inspect persisted identity after the server acknowledges the autosave.
    from src.shared.store import store
    vehicles = [s['vehicle'] for s in store.diag_sessions('tester@example.com')]
    assert any(v.get('brand') == brand and v.get('model') == model and
               v.get('year') == int(year) and v.get('market') == market for v in vehicles)


def test_manual_market_and_restore(browser_page):
    page, base = browser_page
    page.goto(base + '/diagnose')
    page.locator('#dz-vehicle-search').fill('Honda')
    page.locator('#dz-car-suggestions [data-brand="Honda"]').first.click()
    page.locator('[data-model="Accord"]').first.click()
    page.locator('#dz-year-select').select_option('2023')
    page.locator('#dz-market-select').select_option('US')
    playwright.expect(page.locator('#dz-car-selected-model')).to_have_text('Accord — 2023 — American (US)')
    page.locator('#dz-continue-vehicle').click()
    page.wait_for_timeout(1200)
    from src.shared.store import store
    session = store.diag_sessions('tester@example.com')[0]
    assert session['vehicle']['market'] == 'US'
    page.goto(base + '/diagnose?session_id=' + session['id'])
    page.wait_for_timeout(700)
    assert page.locator('#dz-market-select').input_value() == 'US'
    assert page.locator('#dz-year-select').input_value() == '2023'
    assert 'Accord' in page.locator('#dz-car-selected-model').text_content()


def test_voice_transcription(browser_page):
    page, base = browser_page
    page.add_init_script('''window.SpeechRecognition = class {
      start() {
        window.testSpeechLanguage = this.lang;
        this.onstart();
        this.onresult({results: [[{transcript: 'معي هوندا أكورد 2023 أميركية'}]]});
        this.onend();
      }
      stop() { this.onend(); }
    };''')
    page.goto(base + '/diagnose')
    assert page.locator('#dz-voice-language').count() == 0
    assert page.get_by_text('Voice language', exact=False).count() == 0
    page.evaluate("document.documentElement.lang = 'ar'")
    page.locator('#dz-car-voice-btn').click()
    playwright.expect(page.locator('#dz-car-selected-brand')).to_have_text('Honda')
    playwright.expect(page.locator('#dz-car-selected-model')).to_have_text('Accord — 2023 — American (US)')
    assert page.evaluate('window.testSpeechLanguage') == 'ar-LB'


def test_full_model_grid_and_live_search_index(browser_page):
    page, base = browser_page
    requested = []
    def models(route):
        requested.append(route.request.url)
        route.fulfill(json={'items': [{'value': f'Model {i:02d}', 'image': None} for i in range(30)] + [{'value':'M4', 'image':None}]})
    page.unroute('**/api/vehicles/models*')
    page.route('**/api/vehicles/models*', models)
    page.goto(base + '/diagnose')
    page.locator('#dz-brands-grid [data-brand="BMW"]').click()
    playwright.expect(page.locator('#dz-car-models-grid [data-model="Model 29"]')).to_be_visible()
    playwright.expect(page.locator('#dz-car-models-grid [data-model="M4"]')).to_be_visible()
    assert 'limit=1000' in requested[-1]
    page.locator('#dz-change-vehicle').click()
    page.locator('#dz-vehicle-search').fill('M4')
    playwright.expect(page.locator('#dz-car-selected-brand')).to_have_text('BMW')
    playwright.expect(page.locator('#dz-car-selected-model')).to_contain_text('M4')


def test_downloaded_vehicle_assets_desktop_and_mobile(browser_page):
    page, base = browser_page
    for width in [1280, 390]:
        page.set_viewport_size({'width': width, 'height': 900})
        for brand, models in [('Honda', ['Accord', 'Civic', 'CR-V']),
                              ('Toyota', ['Camry', 'Corolla']),
                              ('BYD', ['Seal']), ('BMW', ['M4'])]:
            page.goto(base + '/diagnose', wait_until='domcontentloaded')
            page.locator('#dz-brands-view-all').click()
            card = page.locator(f'#dz-brands-grid [data-brand="{brand}"]')
            playwright.expect(card).to_be_visible()
            logo = card.locator('img')
            playwright.expect(logo).to_be_visible()
            page.wait_for_function('(img) => img.complete && img.naturalWidth > 0', arg=logo.element_handle())
            card.click()
            urls = []
            for model in models:
                photo = page.locator(f'#dz-car-models-grid [data-model="{model}"] img.dz-model-img')
                photo.scroll_into_view_if_needed()
                playwright.expect(photo).to_be_visible()
                page.wait_for_function('(img) => img.complete && img.naturalWidth > 0', arg=photo.element_handle())
                assert '/image/vehicles/' in photo.get_attribute('src')
                assert photo.get_attribute('title')
                urls.append(photo.get_attribute('src'))
            assert len(urls) == len(set(urls))
        page.screenshot(path=str(Path(f'tmp/vehicle-selector-{width}.png')), full_page=True)


def test_partial_arabic_and_confirmation(browser_page):
    page, base = browser_page
    page.goto(base + '/diagnose')
    page.locator('#dz-vehicle-search').fill('معي هوندا اكورد')
    playwright.expect(page.locator('#dz-car-suggestions button')).to_have_text('Honda — Accord')
    page.locator('#dz-vehicle-search').press('Enter')
    playwright.expect(page.locator('#dz-car-selected-model')).to_have_text('Accord')
    page.locator('#dz-change-vehicle').click()
    # Ambiguous identities require a choice, never silently pick the first brand.
    page.locator('#dz-vehicle-search').fill('Honda Accord Toyota Camry 2023 US')
    page.locator('#dz-vehicle-search').press('Enter')
    playwright.expect(page.locator('#dz-car-suggestions')).to_contain_text('Confirm your vehicle')
    playwright.expect(page.locator('#dz-car-selected')).to_be_hidden()
    page.locator('#dz-car-suggestions button').filter(has_text='Toyota').click()
    playwright.expect(page.locator('#dz-car-selected-brand')).to_have_text('Toyota')


def test_image_upload(browser_page):
    page, base = browser_page
    page.goto(base + '/diagnose')
    zone = page.locator('#dz-photo-detect-zone')
    playwright.expect(zone).to_be_visible()
    playwright.expect(page.locator('#dz-photo-detect-title')).to_have_text('Upload Car Image')
    with page.expect_file_chooser() as chooser:
        zone.click()
    chooser.value.set_files(str(Path('image/ai-mechanic-car.png').resolve()))
    playwright.expect(page.locator('#dz-photo-detect-preview')).to_be_visible()
    playwright.expect(page.locator('#dz-photo-detect-title')).to_have_text('Upload Car Image')
    playwright.expect(page.locator('#dz-car-selected-brand')).to_have_text('Honda')
    playwright.expect(page.locator('#dz-year-select')).to_have_value('2023')
    page.locator('#dz-continue-vehicle').click()
    playwright.expect(page.locator('#dz-problem')).to_be_visible()
