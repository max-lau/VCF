# Intake Routing Spec — OCR Intake & Email Intake

## Goal
Reduce Claude Vision token spend and latency by parsing documents locally first.
Claude Vision is the **exception handler**, not the default path.

## Tools (open source, Rust, MIT, local — no API key)
- **AnyDoc** (github.com/firecrawl/anydoc) — docx, doc, docm, xlsx, xls, xlsm, pptx, ppt,
  rtf, odt, ods, odp, epub, csv → clean Markdown. ~5 ms/doc. Node & Python bindings.
- **pdf-inspector** (github.com/firecrawl/pdf-inspector) — per-page PDF classification
  (text_based / scanned / image_based / mixed) without rendering; extracts embedded text;
  returns `pages_needing_ocr`. Use `--compact` output to save tokens downstream.

## Routing logic
1. **Hash & dedupe first**: SHA-256 the file; if seen before, return stored extraction.
2. **Email Intake**: walk MIME parts. Plain/HTML body → convert directly (no model).
   Attachments → same gate as below.
3. **Office/OpenDocument/CSV/EPUB files** → AnyDoc → Markdown. Done.
4. **PDF** → pdf-inspector:
   - text_based → take extracted Markdown. Done.
   - mixed → extract text pages locally; send ONLY `pages_needing_ocr` onward.
   - scanned / image_based → step 5.
5. **Image files & scanned pages**:
   - Printed text → cheap local OCR (Tesseract/PaddleOCR) with confidence scores.
   - Mean confidence < 0.7, or handwriting heuristic fires → **Claude Vision**.
   - Handwriting, signatures, stamps, complex forms → **Claude Vision** (this is the
     intended exception — Vision genuinely outperforms classical OCR here).
6. **Fallback safety**: the existing Vision path stays in place as the final fallback
   at every stage. Quality must never regress during migration.

## Token hygiene downstream
- Feed the LLM the clean Markdown (not HTML, not raw dumps).
- Use pdf-inspector `--compact` to collapse dot leaders/padding.

## Observability
Log per file: `{route_taken, pages_total, pages_to_vision, tokens_used, latency_ms}`.
Review distribution after one week to confirm savings and tune thresholds.

## Rollout order
1. Email Intake (MIME body parsing + AnyDoc for attachments) — lowest risk.
2. OCR Intake (pdf-inspector routing, then local-OCR-with-Vision-fallback for images).
3. Keep Vision fallback unchanged throughout.

## Acceptance criteria
- Born-digital PDFs and Office docs: $0 vision cost, < 1 s latency.
- Mixed PDFs: vision calls only for flagged pages.
- Handwriting samples: extraction quality equal to or better than current pipeline.
- No file type that worked before is silently degraded (regression test set required).

## Caveat
AnyDoc's own benchmark shows mammoth slightly higher on docx *completeness* — spot-check
the most important docx templates after switching.
