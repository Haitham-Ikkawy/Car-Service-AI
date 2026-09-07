"""Vehicle API pure helpers: VIN validation, slug/title, image fallbacks."""
from __future__ import annotations

from src.car_database import vehicle_api as v


def test_valid_vin():
    assert v._valid_vin("1HGCM82633A004352") is True   # 17 chars, valid set
    assert v._valid_vin("bad") is False                 # too short
    assert v._valid_vin("1HGCM82633A00435I") is False   # contains I (not allowed)
    assert v._valid_vin("1hgcm82633a004352") is True    # lowercased is normalised


def test_slug():
    assert v._slug("Mercedes-Benz") == "mercedes-benz"
    assert v._slug("Land Rover") == "land-rover"


def test_title_canonicalises_uppercase():
    assert v._title("BMW") == "BMW"
    assert v._title("MERCEDES-BENZ") == "Mercedes-Benz"
    assert v._title("toyota") == "toyota" or v._title("TOYOTA") == "Toyota"


def test_local_image_missing_returns_empty():
    assert v.local_image("NotARealMake", "NotARealModel") == ""


def test_imagin_off_by_default(monkeypatch):
    """With no licensed key, the CGI-render fallback is disabled."""
    monkeypatch.setattr(v, "_IMAGIN_CUSTOMER", "")
    assert v._imagin_url("Toyota", "Camry", "2021") == ""


def test_imagin_url_built_when_key_present(monkeypatch):
    monkeypatch.setattr(v, "_IMAGIN_CUSTOMER", "somekey")
    url = v._imagin_url("Toyota", "Camry", "2021")
    assert url.startswith("https://cdn.imagin.studio/getimage?")
    assert "make=toyota" in url and "customer=somekey" in url
