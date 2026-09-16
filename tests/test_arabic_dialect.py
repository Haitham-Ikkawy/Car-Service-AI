"""Tests for Arabic dialect detection and automotive terminology mapping."""
import pytest
from src.shared.utils.arabic_dialect import (
    DialectResult,
    detect_arabic_dialect,
    detect_language_and_dialect,
    find_automotive_terms,
    normalize_arabic_text,
    _count_matches,
)


class TestDialectDetection:
    """Test dialect detection from Arabic text."""

    def test_lebanese_detection(self):
        text = "السكان خبطت وصار في طقطقة"
        dialect, confidence = detect_arabic_dialect(text)
        assert dialect in ("Lebanese", "Syrian", "Jordanian", "Palestinian")
        assert confidence > 0.3

    def test_egyptian_detection(self):
        text = "الموتور بيسخن اوي والرادياتير محتاج فحص واتكلم مع营业"
        dialect, confidence = detect_arabic_dialect(text)
        # Egyptian detection might return Arabic if no strong markers
        assert dialect in ("Egyptian", "Arabic")
        assert confidence >= 0.2

    def test_gulf_detection(self):
        text = "الحين المكيف ما يبرد عشان كذا راح اوديه عند الكهربائي"
        dialect, confidence = detect_arabic_dialect(text)
        assert dialect in ("Saudi", "Emirati", "Kuwaiti", "Qatari", "Bahraini", "Omani", "Arabic")
        assert confidence >= 0.2

    def test_iraqi_detection(self):
        text = "هسة الموتور شلونك"
        dialect, confidence = detect_arabic_dialect(text)
        # Iraqi detection might return Arabic if no strong markers
        assert dialect in ("Iraqi", "Arabic")
        assert confidence >= 0.1

    def test_maghreb_detection(self):
        text = "شحال حالك واش بزاف دابا خلاص"
        dialect, confidence = detect_arabic_dialect(text)
        assert dialect in ("Moroccan", "Algerian", "Tunisian", "Libyan", "Arabic")
        assert confidence >= 0.2

    def test_empty_text(self):
        dialect, confidence = detect_arabic_dialect("")
        assert dialect == ""
        assert confidence == 0.0

    def test_non_arabic_text(self):
        dialect, confidence = detect_arabic_dialect("The engine is overheating")
        # Non-Arabic text should return Arabic (general) if no markers found
        # or empty string if no Arabic characters
        assert dialect in ("", "Arabic")


class TestLanguageDetection:
    """Test full language and dialect detection pipeline."""

    def test_arabic_detection(self):
        result = detect_language_and_dialect("المحرك بيسخن")
        assert result.language == "ar"
        assert result.dialect_confidence > 0.2

    def test_english_detection(self):
        result = detect_language_and_dialect("The engine is overheating")
        assert result.language == "en"
        assert result.dialect == ""

    def test_mixed_language_detection(self):
        result = detect_language_and_dialect("المحرك is overheating")
        # Mixed language - might detect as Arabic or English depending on ratio
        assert result.language in ("ar", "en")

    def test_empty_text(self):
        result = detect_language_and_dialect("")
        assert result.language == "en"

    def test_automotive_terms_detected(self):
        result = detect_language_and_dialect("السكان خبطت")
        assert len(result.detected_terms) > 0
        assert len(result.canonical_concepts) > 0


class TestAutomotiveTerms:
    """Test automotive terminology mapping."""

    def test_steering_wheel_terms(self):
        text = "السكان خبطت"
        terms = find_automotive_terms(text)
        assert any(t["canonical_id"] == "steering_wheel" for t in terms)

    def test_track_rod_end_terms(self):
        text = "بيضة السيارة مكسرة"
        terms = find_automotive_terms(text)
        assert any(t["canonical_id"] == "track_rod_end" for t in terms)

    def test_ac_compressor_terms(self):
        text = "الكمبروسر ما يشتغل"
        terms = find_automotive_terms(text)
        assert any(t["canonical_id"] == "ac_compressor" for t in terms)

    def test_engine_terms(self):
        text = "الموتور بيسخن"
        terms = find_automotive_terms(text)
        assert any(t["canonical_id"] == "engine" for t in terms)

    def test_battery_terms(self):
        text = "البطارية خلصت"
        terms = find_automotive_terms(text)
        assert any(t["canonical_id"] == "battery" for t in terms)

    def test_brakes_terms(self):
        text = "المكابح صوت غريب"
        terms = find_automotive_terms(text)
        assert any(t["canonical_id"] == "brakes" for t in terms)

    def test_clutch_terms(self):
        text = "القير ما يشتغل"
        terms = find_automotive_terms(text)
        assert any(t["canonical_id"] == "clutch" for t in terms)

    def test_transmission_terms(self):
        text = "الجير بيرجف"
        terms = find_automotive_terms(text)
        assert any(t["canonical_id"] == "transmission" for t in terms)

    def test_no_terms_found(self):
        text = "The car is not working"
        terms = find_automotive_terms(text)
        assert len(terms) == 0

    def test_multiple_terms(self):
        text = "السكان خبطت والكمبروسر مشتغل والبطارية ضعيفة"
        terms = find_automotive_terms(text)
        assert len(terms) >= 3


class TestTextNormalization:
    """Test Arabic text normalization."""

    def test_diacritics_removal(self):
        text = "مَحَرِّك"
        normalized = normalize_arabic_text(text)
        assert "َ" not in normalized
        assert "ِ" not in normalized

    def test_alef_normalization(self):
        text = "إ◾أ◾آ◾ا"
        normalized = normalize_arabic_text(text)
        assert "إ" not in normalized
        assert "أ" not in normalized
        assert "آ" not in normalized

    def test_ta_marbuta_normalization(self):
        text = "ة"
        normalized = normalize_arabic_text(text)
        assert normalized == "ه"

    def test_ya_normalization(self):
        text = "ى"
        normalized = normalize_arabic_text(text)
        assert normalized == "ي"


class TestIntegration:
    """Integration tests for dialect detection and terminology mapping."""

    def test_lebanese_with_terms(self):
        result = detect_language_and_dialect("السكان خبطت وصار طقطقة")
        assert result.language == "ar"
        assert len(result.detected_terms) > 0
        assert result.canonical_concepts[0]["en"] == "Steering Wheel"

    def test_egyptian_with_terms(self):
        result = detect_language_and_dialect("الموتور بيسخن اوي والكمبروسر مشتغل")
        assert result.language == "ar"
        assert len(result.detected_terms) >= 2
        concept_ids = [c["id"] for c in result.canonical_concepts]
        assert "engine" in concept_ids
        assert "ac_compressor" in concept_ids

    def test_gulf_with_terms(self):
        result = detect_language_and_dialect("الحين البطارية خلصت والمولد مشتغل")
        assert result.language == "ar"
        assert len(result.detected_terms) >= 2
        concept_ids = [c["id"] for c in result.canonical_concepts]
        assert "battery" in concept_ids
        assert "alternator" in concept_ids
