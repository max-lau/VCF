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
| Matters / cases | **Claims / claimants** |
| Discovery & privilege review | **OCR intake & document classification** |
| Court deadlines & docketing | **VCF deadlines & response tracking** |
| Depositions & interrogatories | **Client statements & medical records** |
| Trial prep | **VCF submission & disbursement** |
| Legal research / legal-bert | **Medical NLP (BioClinicalBERT / scispaCy)** |
| Correspondence | **Communications** |

---

## Core Modules

| Module | Description |
|---|---|
| **Dashboard** | Claims-by-stage KPIs, overdue deadlines, intake volume |
| **Claims** | Claim creation, VCF-specific fields, lifecycle stage tracking |
| **Documents** | Claim-linked document repository |
| **OCR Intake** | Claude Vision + Tesseract extraction of handwritten/mixed-language forms; auto-links to existing cases by name/DOB/phone |
| **Batch Intake** | Queue-based bulk upload for high-volume intake |
| **Email Inbox** | Gmail/Outlook-connected intake; attachments auto-classified and linked to claims |
| **Communications** | Unified log of emails, phone calls, faxes, and mail per claim |
| **Document Inbox** | Queue for unmatched email/OCR attachments waiting to be linked to a claim |
| **VCF Account Prep** | Generate copy-paste credentials for `claims.vcf.gov`; auto-assigns a dedicated law-firm VCF email per claimant |
| **VCF Workflow / Kanban** | Visual claim-stage board (Intake → Eligibility → Account Created → Submitted → Award → Disbursed) |
| **Deadlines** | VCF response windows and firm deadlines with notifications |
| **Disbursements** | Award, lien, attorney fee, and net-to-claimant calculation |
| **Medical NLP** | Clinical entity extraction and claim-relevance scoring using medical models |
| **Redaction** | Vault-only PII redaction: original PDF left, redacted PDF right, inline preview |
| **Calendar** | Firm calendar with VCF deadline integration |
| **Contacts** | Clients, providers, agencies, VCF contacts |
| **Reports** | Claims volume, deadlines, disbursements |
| **Client Portal** | Secure claimant document upload & status view |
| **Admin** | Users, roles, audit log, AI config |

---

## Tech Stack

- **Backend:** Python 3.14, FastAPI, Uvicorn (port 5003)
- **Database:** PostgreSQL (Supabase) with Row-Level Security; single-tenant via `firm_id = 'waw_vcf'`
- **AI / NLP:**
  - Anthropic Claude API for Vision OCR, structured extraction, and reasoning
  - BioClinicalBERT / scispaCy for medical entity extraction (replaces legal-bert)
  - Presidio Analyzer + Anonymizer (optional) for PII redaction; Claude-only fallback
- **Vector Store:** ChromaDB / Pinecone (optional, for semantic search)
- **Auth:** JWT (PyJWT) + bcrypt; token blocklist in Postgres
- **Frontend:** Vue 3 + Vite + Vue Router + Pinia
- **OCR:** Claude Vision primary; Tesseract fallback for printed text
- **Chrome Extension:** Side-panel helper for `claims.vcf.gov` registration and copy-paste fields
- **Email:** Gmail OAuth2 + IMAP; Outlook OAuth2 + Microsoft Graph polling

---

## Architecture

### Backend (`backend/demo1/`)

| File | Responsibility |
|---|---|
| `main.py` | App factory: middleware, router mounts, startup init |
| `case_management.py` | Claim CRUD, case binders, document linking |
| `ocr_intake.py` | OCR intake pipeline, scan storage, auto-matching |
| `vcf_account.py` | VCF.gov account prep sheet generation |
| `vcf_deadlines.py` | Deadline creation, tracking, notifications |
| `vcf_disbursements.py` | Award / lien / net-to-claimant calc |
| `communications.py` | Unified communications log |
| `email_intake.py` | Gmail/Outlook account linking and polling |
| `medical_nlp.py` | Medical entity analysis and claim relevance |
| `redaction.py` | Vault-only PDF/text redaction with inline preview |
| `security_headers.py` | OWASP security headers; CSP frame-ancestors exemptions for redaction previews |
| `pg.py` | Postgres connection / transaction helper |

### Frontend (`frontend/paraiq-vue/`)

| Path | Responsibility |
|---|---|
| `src/views/vcf/` | VCF-specific views: Account Prep, Workflow/Kanban, Reports |
| `src/views/redaction/RedactionView.vue` | 1:2:2 vault/original/redacted PDF workspace |
| `src/views/intake/IntakeView.vue` | OCR scan upload and review |
| `src/views/email/EmailInboxView.vue` | Email intake triage |
| `src/components/layout/` | AppShell, sidebar navigation |

### Security

- **Single-tenant:** `FIRM_ID = 'waw_vcf'` is enforced in JWT middleware.
- **RLS:** All tenant tables use Postgres Row-Level Security.
- **PII:** SSN/DOB are limited to last-4 and date fields; `prep_blob` is encrypted at rest with `VCF_PREP_ENC_KEY`.
- **CSP:** Strict Content-Security-Policy with same-origin framing exemptions for redaction PDF previews.
- **Audit:** All API activity is logged to the immutable `audit_trail` table.

---

## Recent Modifications

### Redaction module rework
- PDF redaction now pulls **only from the document vault** (`case_documents`) — no local uploads.
- Added `/redact/{id}/preview` endpoint for inline iframe display; `/redact/{id}/download` remains for downloads.
- Workspace layout set to **1:2:2** (vault picker : original PDF : redacted PDF).
- CSP updated to allow same-origin framing for redaction file endpoints.

### Medical NLP
- Replaced litigation-focused `legal-bert` with **BioClinicalBERT / scispaCy** for clinical entity recognition.
- Added `/medical-nlp/analyze` endpoint for conditions, medications, procedures, and claim-relevance scoring.

### Name-order handling
- Added surname-first detection for Chinese, Vietnamese, Korean, Japanese, Mongolian, Khmer, and Lao claimants.
- Manual `Name order` selector in intake/prep forms; auto-selected by `preferred_language`.

### Email intake
- Added Gmail OAuth2 + Outlook OAuth2 account linking.
- Attachments are classified and either auto-linked to a case or queued in the Document Inbox.
- Backend poller fetches new messages automatically.

### VCF dedicated emails
- Law-firm-provided VCF emails (`wawvcf.com`) are auto-assigned per claimant on case creation.
- Distinct from the claimant's personal email; all VCF correspondence routes through the firm.

### Litigation cleanup
- Removed/hidden litigation-only views: Correspondence, Legal Research, Motions, Depositions, Contracts, Trial prep, etc.
- Kept and repurposed: Communications, Timeline, Workflow/Kanban, Insights/Medical NLP.

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
# GMAIL_CLIENT_ID=...
# GMAIL_CLIENT_SECRET=...
```

### 3. Apply database migrations

Migrations are in `migrations/`. Apply them in order against your Postgres database.

### 4. Run the API

```bash
python -m uvicorn backend.demo1.main:app --host 0.0.0.0 --port 5003
```

### 5. Run the frontend

```bash
cd frontend/paraiq-vue
npm install
npm run dev
```

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
