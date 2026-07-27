# VCFClaimsIQ Backend (`backend/demo1/`)

FastAPI backend for the VCFClaimsIQ administrative claims platform.

---

## Run locally

```powershell
# From repository root
cd C:\vcf
. venv/Scripts/activate
python -m uvicorn backend.demo1.main:app --host 0.0.0.0 --port 5003
```

The API will be available at `http://localhost:5003`.

---

## Module map

| Module | File | Purpose |
|---|---|---|
| App factory | `main.py` | Middleware, router mounts, startup table init |
| Claims | `case_management.py` | Claim CRUD, case binder, document linking |
| OCR Intake | `ocr_intake.py` | Scan upload, Claude Vision OCR, auto case-matching |
| Email Intake | `email_intake.py` | Gmail/Outlook OAuth, polling, attachment ingestion |
| VCF Account Prep | `vcf_account.py` | Prep-sheet generation, security answers, dedicated VCF emails |
| VCF Deadlines | `vcf_deadlines.py` | Deadline tracking and notifications |
| VCF Disbursements | `vcf_disbursements.py` | Award, lien, fee, net-to-claimant calc |
| Communications | `communications.py` | Unified comms log per claim |
| Medical NLP | `medical_nlp.py` | BioClinicalBERT / scispaCy clinical analysis |
| Redaction | `redaction.py` | Vault-only PII redaction with inline preview |
| Security headers | `security_headers.py` | OWASP headers, CSP frame exemptions |
| Auth | `auth.py` | JWT issue/validate, password hashing, token blocklist |
| Database | `pg.py` | Postgres connection helper |

---

## Key API patterns

- All routes (except public login/register/health) require a JWT in the `Authorization: Bearer <token>` header or a `?token=<jwt>` query parameter for capability URLs.
- `firm_id` is extracted from the JWT and applied to every tenant query.
- File storage uses Supabase Storage (`vcf-documents` bucket) with local-disk fallback.

---

## Environment variables

See `.env.example` for the full list. Key variables:

```bash
DATABASE_URL=postgresql://...
ANTHROPIC_API_KEY=...
JWT_SECRET_KEY=...
VCF_PREP_ENC_KEY=...
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...
VCF_DEDICATED_EMAIL_DOMAIN=wawvcf.com
VCF_DEDICATED_EMAIL_PREFIX=vcfclaim
```
