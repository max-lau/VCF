# VCF Email Intake Routing — End-to-End Test Summary

**Date:** 2026-08-08  
**Branch:** `acp-vcf-v1`

## Goal
Validate that `.docx` email attachments are processed by a local extractor instead of Claude Vision, reducing token cost and latency for VCFClaimsIQ administrative-claim intake.

## Outcome ✅
A `.docx` attachment sent to `henidt@gmail.com` was successfully received via Gmail, routed through the vault pipeline, and extracted locally by **mammoth**. No Claude Vision call was made.

Confirmed extracted text in `case_documents`:

```text
VCF Medical Record

Patient: Chen Weiming
Diagnosis: Stage IIIA lung adenocarcinoma
WTC Health Program registered: 2018
```

## Key code changes
- `backend/demo1/intake_router.py` — added `mammoth` + `python-docx` extractors for `.docx`, direct text handling for `.txt`/`.csv`, and visible `WARNING`-level logs for local routes.
- `backend/demo1/attachment_handler.py` — auto-create `quarantine`/`cleared` directories on import.
- `backend/demo1/email_poller.py` — made Gmail fetch limit configurable via `EMAIL_POLL_MAX_RESULTS`.
- `requirements.txt` — removed conflicting `langchain`/`instructor` pins; added `email-validator`, `mammoth`, `python-docx`.
- `scripts/start_vcf_backend.sh` — reliable one-line backend starter for the VPS.
- `scripts/test_email_docx_route.py` — offline MIME + `.docx` routing simulation.
- `scripts/check_email_intake.py` — DB diagnostic for email intake and `case_documents`.

## VPS deployment notes
- Backend runs on `http://5.161.83.6:5004`.
- Gmail OAuth used a temporary Cloudflare Tunnel (`*.trycloudflare.com`).
- `supabase` Python package still needs installation for storage uploads to work end-to-end.
- ParaIQ API is paused via PM2 and scheduled to restart ~16 hours after stop.

## Next steps (optional)
1. Install `supabase` on the VPS so attachments upload to Supabase storage.
2. Set up a permanent subdomain (e.g. `vcf.para-iq.com`) for stable Gmail OAuth.
3. Extend `intake_router.py` to PDF and image routes per `intake-routing-spec.md`.
