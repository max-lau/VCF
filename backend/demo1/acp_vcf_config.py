# backend/demo1/acp_vcf_config.py
"""
ACP-VCF Configuration
Specialized for WAW Law Firm - 9/11 Victim Compensation Fund (VCF) Claims
"""

APP_NAME = "ACP-VCF"
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

print(f"✅ {APP_NAME} configuration loaded for {FIRM_NAME}")