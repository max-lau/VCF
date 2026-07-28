# backend/demo1/acp_vcf_config.py
"""
ACP-VCF Configuration
Specialized for WAW Law Firm - 9/11 Victim Compensation Fund (VCF) Claims
"""

APP_NAME = "VCFClaimsIQ"
FIRM_NAME = "WAW Law Firm - 9/11 VCF Claims"
FIRM_ID = "waw_vcf"                    # Fixed single-tenant ID

# VCF-specific deadlines (days)
VCF_DEADLINES = {
    "missing_info": 60,      # VCF preliminary review response
    "substantive": 30,       # Substantive eligibility response
    "award_calc": 90,        # Typical award processing window
}

# Default intake categories for VCF
VCF_CATEGORIES = [
    "Presence Proof",
    "Medical Records / Certified Condition",
    "Financial / Lost Earnings",
    "Personal Statement / Affidavit",
    "Banking / Payment Info",
    "Other Correspondence"
]

import os

_VCF_EMAIL_DOMAIN = os.getenv("VCF_DEDICATED_EMAIL_DOMAIN", "").strip()
_VCF_EMAIL_PREFIX = os.getenv("VCF_DEDICATED_EMAIL_PREFIX", "vcfclaim").strip()

print(f"[ACP-VCF] {APP_NAME} configuration loaded for {FIRM_NAME}")
if not _VCF_EMAIL_DOMAIN:
    print("[ACP-VCF] WARNING: VCF_DEDICATED_EMAIL_DOMAIN is not set. New cases will not be assigned a law-firm VCF email.")
else:
    print(f"[ACP-VCF] VCF dedicated email domain: {_VCF_EMAIL_PREFIX}@{_VCF_EMAIL_DOMAIN}")