"""
test_email_filter.py
====================
Unit tests for the VCF-specific email filter engine.
No live server or database required.
"""
from datetime import datetime, timezone

import pytest

from backend.demo1.email_filter import EmailFilterEngine, EmailMessage


def _make_msg(subject: str, body: str, from_address: str = "lab@example.com") -> EmailMessage:
    return EmailMessage(
        provider_message_id="msg-1",
        provider="gmail",
        attorney_id="1",
        account_id="1",
        firm_id="waw_vcf",
        from_address=from_address,
        to_addresses=["intake@wawvcf.com"],
        cc_addresses=[],
        subject=subject,
        body_text=body,
        body_html="",
        received_at=datetime.now(timezone.utc),
        headers={},
        attachment_names=["records.pdf"],
    )


def _engine_with_case() -> EmailFilterEngine:
    engine = EmailFilterEngine("waw_vcf")
    engine._case_registry = {
        "7": {
            "title": "vcf-2026-chen-wm",
            "client": "chen weiming",
            "docket": "",
        }
    }
    return engine


class TestVCFFilterRouting:
    def test_vcf_gov_email_routes_to_intake(self):
        engine = _engine_with_case()
        msg = _make_msg(
            subject="VCF claim update required",
            body="Please submit updated medical records for your VCF claim.",
            from_address="noreply@claims.vcf.gov",
        )
        result = engine.process(msg)
        assert result.routing_decision == "intake"
        assert "vcf" in result.extracted_entities["vcf_keywords"]

    def test_lab_email_with_patient_name_routes_to_intake(self):
        engine = _engine_with_case()
        msg = _make_msg(
            subject="Lab results for Chen Weiming",
            body="Attached are the pathology and radiology reports for Chen Weiming, DOB 03/12/1958.",
            from_address="results@riversidecancer.org",
        )
        result = engine.process(msg)
        assert result.routing_decision == "intake"
        assert result.case_id_matched == 7
        assert "pathology" in result.extracted_entities["vcf_keywords"]

    def test_medical_records_no_case_match_routes_to_review(self):
        engine = _engine_with_case()
        msg = _make_msg(
            subject="Medical records",
            body="Please find enclosed medical records for the requested patient.",
            from_address="records@downtownmedical.org",
        )
        result = engine.process(msg)
        # VCF/medical keywords push it into review even without a case match
        assert result.routing_decision in ("intake", "review")
        assert "medical records" in result.extracted_entities["vcf_keywords"]

    def test_spam_promo_is_discarded(self):
        engine = _engine_with_case()
        msg = _make_msg(
            subject="Limited time offer - 50% off!",
            body="Click here now for a free trial and unsubscribe anytime.",
            from_address="deals@marketing.example.com",
        )
        result = engine.process(msg)
        assert result.routing_decision == "discard"

    def test_system_domain_is_discarded(self):
        engine = _engine_with_case()
        msg = _make_msg(
            subject="Security alert",
            body="Unusual sign-in activity detected.",
            from_address="security@accountprotection.microsoft.com",
        )
        result = engine.process(msg)
        assert result.routing_decision == "discard"
