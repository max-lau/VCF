# WaW LLP Demo Tenant — Deployment & Demo Guide

Synthetic dataset for pitching ParaIQ to WaW, a boutique firm serving 9/11 Victim
Compensation Fund (VCF) claimants. Everything here is fictional; all documents carry
a discreet "synthetic record" footer (strip it from the generator scripts if you'd
rather not show it on screen — but keeping it is the safer default for anything that
looks like PHI).

## Package contents

| File | Purpose |
|---|---|
| `waw_seed_data.json` | Firm, user, 8 clients, cases, Kanban stages, ~90 timeline events, document registry |
| `seed_waw.py` | Idempotent seeder (reads the JSON; `--reset`, `--dry-run` flags) |
| `chen_weiming_intake_questionnaire_zh.png` | Typed Chinese form, handwritten Simplified Chinese answers — Claude Vision demo #1 |
| `krystyna_nowak_intake_questionnaire_en.png` | Typed English form, handwritten broken-English answers — Claude Vision demo #2 |
| `chen_weiming_medrec_set{1,2,3}_*.pdf` | Thyroid pathology (2019), lung CT + biopsy w/ EGFR panel (2025), oncology treatment summary (2026) |
| `krystyna_nowak_medrec_set{1,2,3}_*.pdf` | Breast pathology (2023), oncology/survivorship summary (2024), WTC-HP pulmonary/GI/lymphedema records (2026) |

## The roster (spec compliance)

| Client | Age | Demo | Condition(s) | Kanban stage |
|---|---|---|---|---|
| Weiming Chen 陈伟明 (M, Chinese) | 68 | **Deep dive #1** | Lung adenocarcinoma + papillary thyroid carcinoma (2 cancers) | Under Review |
| Krystyna Nowak (F, White/Polish-born) | 64 | **Deep dive #2** | Breast cancer + lymphedema, asthma, GERD | Award / Decision |
| James Callahan (M, White) | 58 | | Lung cancer (squamous) + COPD — NYPD responder | Closed |
| Sarah Bennett (F, White) | 26 | | Chronic rhinosinusitis / allergies (mild) — BPC child resident | Intake |
| Denise Washington (F, Black) | 52 | | Multiple myeloma — FDNY EMT | Claim Filed |
| Miguel Herrera (M, Hispanic) | 85 | | Prostate cancer — debris removal worker | Disbursement |
| Rosa Alvarez (F, Hispanic) | 47 | | Sarcoidosis + severe asthma (serious breathing, non-cancer) | WTC-HP Certification |
| Lily Zhang 张丽 (F, Chinese) | 45 | | Non-Hodgkin lymphoma — defunct-employer proof challenge | Documentation |

Counts: 2 lung cancers, 4 other cancers (breast, myeloma, prostate, NHL), 2 non-cancer
(mild allergies → serious breathing). 3 White (1M/2F), 1 Black F, 2 Hispanic (1M/1F),
2 Chinese (1M/1F). Ages 26–85. Every Kanban column is occupied, so the board demos full.

## Schema mapping (confirmed, not guessed)

Aligned against `seed_guest.py` and prior session output. There is **no `clients`
table** — each VCF claimant is one row in `cases`, with `client_name` holding the
name. Mapping used by `seed_waw.py`:

| Concept | Real table.column |
|---|---|
| Tenant | `firms.id` = `'waw'` (not a separate `firm_id` column) |
| Login | `public.users` — **schema-qualify**, there's also a Supabase `auth.users` with overlapping column names |
| Kanban stage | `cases.status` — direct 1:1, no separate board table |
| Client demographics / exposure / WTC-HP detail | one **pinned** `case_notes` row per case ("CLIENT INTAKE SUMMARY") |
| Timeline (87 events) | one `case_notes` row per event; `pinned=TRUE` for milestones (award letter, claim filed, certification, etc.) |
| Intake images / medical PDFs | one `case_documents` row each; `doc_text` for the two Vision-demo images is pre-filled with the structured extraction so the case looks complete even before you run Vision live |

Two things I could **not** confirm and flagged inline in the script — check against
`auth.py` before running:
1. The value for `users.role` (script uses `'firm_admin'` as a placeholder).
2. Whether `username`/`email` carry a UNIQUE constraint (affects what `ON CONFLICT
   DO NOTHING` silently no-ops on if you rerun after a mistake — use `--reset` instead).

## Deploy to the VPS

1. **Transfer** (base64 pattern — no heredocs):
   ```bash
   # local
   tar czf waw_demo.tgz waw_seed_data.json seed_waw.py *.png *.pdf
   base64 -w0 waw_demo.tgz > waw_demo.b64
   # paste/scp waw_demo.b64, then on VPS:
   mkdir -p /root/nlp-portfolio/demo_docs/waw && cd /root/nlp-portfolio/demo_docs/waw
   base64 -d waw_demo.b64 > waw_demo.tgz && tar xzf waw_demo.tgz
   ```
   (Or plain `scp waw_demo.tgz root@5.161.83.6:...` since it's binary-safe anyway.)

2. **Spot-check the two flagged assumptions above** against `auth.py` (one grep for
   `role` and one for the `users` table's constraints is enough).

3. **Dry run, then seed:**
   ```bash
   cd /root/nlp-portfolio && source .venv/bin/activate
   export DATABASE_URL="$(grep '^DATABASE_URL' .env | cut -d= -f2-)"
   python3 demo_docs/waw/seed_waw.py --dry-run
   python3 demo_docs/waw/seed_waw.py
   ```

4. **Verify tenant isolation (your standing rule):** log in as `WaW / 11Bway` → exactly
   8 cases; log in as `maxwell` (firm `default`) → zero WaW rows visible. Add firm
   `waw` to the cross-tenant CI matrix while you're at it — a third tenant makes that
   gate meaningfully stronger.

## Running the demo

- **Vision intake (the wow moment):** upload `chen_weiming_intake_questionnaire_zh.png`
  through the ParaIQ UI *live* rather than pre-loading it — Claude Vision reading
  handwritten Chinese into a structured English intake record is the single most
  impressive 30 seconds you have. Follow with Krystyna's broken-English form to show
  it normalizes messy language, not just translates.
- **Timeline:** open Chen's case — 18 events from referral through deficiency cure to
  upcoming re-staging scan. Two future-dated events per deep-dive case make the
  calendar/reminder story land.
- **Kanban:** all 8 columns populated; Callahan (Closed) shows the full lifecycle,
  Nowak sits at the appeal-vs-accept decision with a real deadline (07/18/2026).
- **Multilingual angle:** Chen (Mandarin), Herrera (Spanish), Nowak (Polish/broken
  English) — three language contexts in one 8-client book of business mirrors the real
  VCF claimant population and is exactly WaW's pain point.

## Caution flags

- These intake images and PDFs *look* like PHI. Keep them inside the demo tenant and
  the private repo; don't publish them in the public case study without the synthetic
  footer visible.
- The two uploaded-document demos are also your **indirect prompt-injection surface**
  (already on your risk list) — worth a slide in the pitch, actually: "ParaIQ treats
  uploaded documents as untrusted data."
- `11Bway` is a weak password on an internet-facing app; fine for a demo window, but
  consider rotating it after the WaW meeting or gating the tenant behind the
  Cloudflare Access policy.
