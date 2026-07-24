"""
test_intake_identity_matching.py
================================
Unit tests for the VCF intake case-linking helpers.
These tests are pure logic — no live server or external API required.
"""
import pytest
from backend.demo1.ocr_intake import _normalize_name, _extract_identity_signals, _content_hash


class TestNormalizeName:
    def test_removes_punctuation_and_extra_spaces(self):
        assert _normalize_name("Chen, Weiming") == "Chen Weiming"
        assert _normalize_name("  Chen   Weiming  ") == "Chen Weiming"
        assert _normalize_name("O'Connor,  Sarah") == "OConnor Sarah"

    def test_handles_none_and_empty(self):
        assert _normalize_name(None) == ""
        assert _normalize_name("") == ""


class TestExtractIdentitySignals:
    def test_extracts_all_expected_fields(self):
        fields = {
            "client_name": "Chen Weiming",
            "date_of_birth": "1958-03-12",
            "ssn_last4": "1234",
            "phone": "917-555-0138",
            "email": "chen@example.com",
            "address": "96 Henry St",
            "employer": "Golden Dragon Restaurant",
            "provider_name": "Downtown Medical Center",
            "medical_conditions": ["thyroid cancer", "lung cancer"],
            "doc_type": "medical_record",
        }
        signals = _extract_identity_signals(fields)
        assert signals["name"] == "Chen Weiming"
        assert signals["dob"] == "1958-03-12"
        assert signals["ssn_last4"] == "1234"
        assert signals["phone"] == "917-555-0138"
        assert signals["email"] == "chen@example.com"
        assert signals["address"] == "96 Henry St"
        assert signals["employer"] == "Golden Dragon Restaurant"
        assert signals["provider_name"] == "Downtown Medical Center"
        assert signals["medical_conditions"] == ["thyroid cancer", "lung cancer"]
        assert signals["doc_type"] == "medical_record"

    def test_normalizes_client_name(self):
        signals = _extract_identity_signals({"client_name": "Chen, Weiming"})
        assert signals["name"] == "Chen Weiming"

    def test_defaults_missing_fields_to_none_or_empty(self):
        signals = _extract_identity_signals({})
        assert signals["name"] == ""
        assert signals["dob"] is None
        assert signals["ssn_last4"] is None
        assert signals["medical_conditions"] == []
        assert signals["doc_type"] == "other"


class TestContentHash:
    def test_same_bytes_produce_same_hash(self):
        data = b"same file contents"
        assert _content_hash(data) == _content_hash(data)

    def test_different_bytes_produce_different_hash(self):
        assert _content_hash(b"file a") != _content_hash(b"file b")

    def test_sha256_hex_length(self):
        assert len(_content_hash(b"test")) == 64
