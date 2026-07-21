# VCFClaimsIQ — Victim Compensation Fund Claims Platform

Single-tenant claims-processing platform built for the CT law firm handling 9/11 Victim Compensation Fund (VCF) claims. Reuses the architecture of ParaIQ but is dedicated to high-volume administrative claims intake, classification, deadline tracking, and disbursement coordination.

---

## Purpose

VCFClaimsIQ is designed for a single-tenant law firm processing:

- **10,000+ existing VCF claims**
- **~5 new claims per day**
- **100+ daily communications** across clients, labs, doctor offices, Medicare/Medicaid, banks, the VCF, and the law office

It replaces litigation-oriented workflows with administrative-claims operations:

| ParaIQ (Litigation) | VCFClaimsIQ (Administrative Claims) |
|---|---|
| Matters / cases | **Claims** |
| Discovery & privilege review | **OCR intake & document classification** |
| Court deadlines & docketing | **VCF deadlines & response tracking** |
| Depositions & interrogatories | **Client statements & medical records** |
| Trial prep | **VCF submission & disbursement** |

---

## Core Modules

| Module | Description |
|---|---|
| **Dashboard** | Claims-by-stage KPIs, overdue deadlines, intake volume |
| **Claims** | Claim creation, VCF-specific fields, lifecycle stage tracking |
| **Documents** | Claim-linked document repository |
| **OCR Intake** | Claude Vision + Tesseract extraction of handwritten/mixed-language forms |
| **Batch Intake** | Queue-based bulk upload for high-volume intake |
| **Correspondence** | Unified communications log (email, phone, fax, mail) |
| **VCF Workflow** | Account prep, deadline tracking, disbursement calculation |
| **Calendar** | Firm calendar with VCF deadline integration |
| **Contacts** | Clients, providers, agencies, VCF contacts |
| **Reports** | Claims volume, deadlines, disbursements |
| **Client Portal** | Secure claimant document upload & status view |
| **Admin** | Users, roles, audit log, AI config |

---

## Tech Stack

- **Backend:** Python 3.12, FastAPI, Uvicorn (port 5003)
- **Database:** Postgres (Supabase) with Row-Level Security; single-tenant via `firm_id = 'waw_vcf'`
- **NLP / AI:** Anthropic Claude API (Vision OCR + structured extraction)
- **Vector Store:** ChromaDB / Pinecone (optional, for semantic search)
- **Auth:** JWT (PyJWT) + bcrypt; token blocklist in Postgres
- **Frontend:** Vue 3 + Vite + Vue Router + Pinia
- **OCR:** Claude Vision primary; Tesseract fallback for printed text
- **Chrome Extension:** Side-panel helper for `claims.vcf.gov` registration

---

## Project Structure

```
C:/vcf/
├── backend/demo1/           # FastAPI app
│   ├── main.py              # Router mounts, middleware, startup
│   ├── case_management.py   # Claim CRUD
│   ├── ocr_intake.py        # OCR intake pipeline
│   ├── vcf_account.py       # VCF.gov account prep sheets
│   ├── vcf_deadlines.py     # VCF deadline tracking
│   ├── vcf_disbursements.py # Award / lien / net-to-claimant calc
│   ├── communications.py    # Unified communications log
│   └── routers/             # Additional module routers
├── frontend/paraiq-vue/     # Vue 3 SPA
│   ├── src/views/vcf/       # VCF-specific views
│   └── src/components/layout/ # Sidebar, AppShell
├── migrations/              # Postgres schema migrations (001–011+)
├── tests/                   # pytest suite
├── chrome_extension_vcf/    # VCF.gov registration helper
└── docs/                    # Runbooks and findings
```

---

## Quick Start

### 1. Clone and set up environment

```bash
git clone https://github.com/max-lau/VCF.git
cd VCF
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Required:
# ANTHROPIC_API_KEY=...
# DATABASE_URL=postgresql://...
# JWT_SECRET_KEY=...
# VCF_PREP_ENC_KEY=...   # Fernet key; generate with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3. Apply database migrations

Migrations are in `migrations/`. Apply them in order against your Postgres database.

### 4. Run the API

```bash
uvicorn backend.demo1.main:app --host 0.0.0.0 --port 5003
```

### 5. Run the frontend

```bash
cd frontend/paraiq-vue
npm install
npm run dev
```

---

## Security & Compliance Notes

- **Single-tenant:** `FIRM_ID = 'waw_vcf'` is enforced in middleware.
- **RLS:** All tenant tables use Postgres Row-Level Security.
- **PII:** SSN/DOB are limited to last-4 and date fields; consider encrypting `prep_blob` at rest with `VCF_PREP_ENC_KEY`.
- **Audit:** All API activity is logged to the immutable `audit_trail` table.

---

## VCF Workflow

1. **Intake** — scan/paper forms → OCR → structured claim data
2. **Eligibility Review** — verify presence, certified condition, and financial docs
3. **VCF Account Prep** — generate copy-paste credentials for `claims.vcf.gov`
4. **Claim Submission** — track submission status and VCF correspondence
5. **Award Determination** — record gross award and liens
6. **Disbursement** — calculate attorney fee, Medicare/Medicaid liens, net to claimant

---

## Author

Maxwell L. — [GitHub](https://github.com/max-lau)
