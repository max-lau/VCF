"""
discovery_agent_guard.py
========================
ParaIQ — Resource-Safe Discovery Agent (WIRED — VPS edition)
Module: backend.demo1.discovery_agent_guard

Real module names matched to actual VPS layout:
  bates.py        → stamp_document
  risk_scorer.py  → score_document
  intelligence.py → enrich_document
  ocr_intake.py   → via internal httpx (existing pattern)
  privilege       → _screen_privilege() called directly (existing background task)

The runner accepts file_ids (already uploaded via /discovery/intake),
resolves paths from discovery_files, then runs all 7 stages with hard guards.
"""

import asyncio
import time
import logging
import os
import httpx
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from pathlib import Path

from backend.demo1.pg import get_conn

logger = logging.getLogger("paraiq.discovery_agent")

UPLOAD_DIR = Path(os.environ.get("DISCOVERY_UPLOAD_DIR", str(Path(__file__).parent.parent.parent / "uploads" / "discovery")))
API_KEY    = os.environ.get("PARAIQ_API_KEY", "")
BASE_URL   = "http://localhost:5003"

# ── Real VPS module imports ──────────────────────────────────────────────────
try:
    from backend.demo1.bates import stamp_pdf as _stamp_bates   # bates.py
    from backend.demo1.risk_scorer import score_text as _score_doc  # risk_scorer.py
    from backend.demo1.intelligence import generate_case_brief as _enrich_doc  # intelligence.py
    _IMPORTS_OK = True
except ImportError as e:
    logger.warning(f"ParaIQ module import — stub mode: {e}")
    _IMPORTS_OK = False

# Privilege screening — import the existing function directly so we
# don't duplicate the enclave routing logic already in discovery_intake.py
try:
    from backend.demo1.discovery_intake import _screen_privilege, _get_doc_text
    _PRIV_OK = True
except ImportError:
    _PRIV_OK = False


# ─────────────────────────────────────────────
# HARD LIMITS
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class AgentLimits:
    max_llm_calls_per_run:           int   = 8
    max_tokens_per_call:             int   = 2048
    max_total_tokens_per_run:        int   = 12000
    max_pipeline_rounds:             int   = 5
    max_ocr_pages_per_run:           int   = 150
    max_docs_per_run:                int   = 30
    timeout_seconds_per_stage:       int   = 90
    timeout_seconds_total:           int   = 600
    max_estimated_cost_usd:          float = 0.25
    circuit_breaker_error_threshold: int   = 3


# ─────────────────────────────────────────────
# RUN STATE
# ─────────────────────────────────────────────

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN   = "open"
    HALF   = "half"


@dataclass
class AgentRunState:
    case_id:  str
    firm_id:  str
    limits:   AgentLimits = field(default_factory=AgentLimits)

    llm_calls:           int = 0
    total_input_tokens:  int = 0
    total_output_tokens: int = 0
    pipeline_rounds:     int = 0
    ocr_pages_processed: int = 0
    docs_processed:      int = 0
    consecutive_errors:  int = 0

    run_start_time: float = field(default_factory=time.time)
    circuit: CircuitState = CircuitState.CLOSED
    aborted:      bool = False
    abort_reason: str  = ""

    privilege_log_rows: list = field(default_factory=list)
    bates_manifest:     list = field(default_factory=list)
    flagged_docs:       list = field(default_factory=list)
    zip_path:           str  = ""

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.run_start_time

    @property
    def estimated_cost_usd(self) -> float:
        return round(
            (self.total_input_tokens  / 1_000_000) * 3.0 +
            (self.total_output_tokens / 1_000_000) * 15.0, 6
        )

    def to_summary(self) -> dict:
        return {
            "case_id":             self.case_id,
            "firm_id":             self.firm_id,
            "llm_calls":           self.llm_calls,
            "total_input_tokens":  self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "pipeline_rounds":     self.pipeline_rounds,
            "ocr_pages":           self.ocr_pages_processed,
            "docs_processed":      self.docs_processed,
            "flagged_docs":        len(self.flagged_docs),
            "privilege_log_rows":  len(self.privilege_log_rows),
            "zip_path":            self.zip_path,
            "elapsed_seconds":     round(self.elapsed_seconds, 2),
            "estimated_cost_usd":  self.estimated_cost_usd,
            "circuit":             self.circuit.value,
            "aborted":             self.aborted,
            "abort_reason":        self.abort_reason,
        }


# ─────────────────────────────────────────────
# GUARD
# ─────────────────────────────────────────────

class DiscoveryAgentGuard:

    def __init__(self, state: AgentRunState):
        self.state = state

    def _trip_circuit(self, reason: str):
        self.state.circuit      = CircuitState.OPEN
        self.state.aborted      = True
        self.state.abort_reason = f"CIRCUIT OPEN: {reason}"
        logger.error(f"[{self.state.case_id}] Circuit tripped — {reason}")

    def _abort(self, reason: str):
        self.state.aborted      = True
        self.state.abort_reason = reason
        logger.error(f"[{self.state.case_id}] ABORTED — {reason}")

    def record_error(self):
        self.state.consecutive_errors += 1
        if self.state.consecutive_errors >= self.state.limits.circuit_breaker_error_threshold:
            self._trip_circuit(f"{self.state.consecutive_errors} consecutive errors")

    def record_success(self):
        self.state.consecutive_errors = 0
        if self.state.circuit == CircuitState.HALF:
            self.state.circuit = CircuitState.CLOSED

    def check_circuit(self) -> bool:
        if self.state.circuit == CircuitState.OPEN:
            return False
        return True

    def check_llm_call(self, estimated_input_tokens: int = 500) -> bool:
        s, L = self.state, self.state.limits
        if not self.check_circuit() or s.aborted:
            return False
        if s.llm_calls >= L.max_llm_calls_per_run:
            self._abort(f"LLM call cap ({s.llm_calls}/{L.max_llm_calls_per_run})")
            return False
        projected = s.total_input_tokens + estimated_input_tokens
        if projected > L.max_total_tokens_per_run:
            self._abort(f"Token budget ({projected} > {L.max_total_tokens_per_run})")
            return False
        cost = (projected / 1_000_000) * 3.0 + (s.total_output_tokens / 1_000_000) * 15.0
        if cost > L.max_estimated_cost_usd:
            self._abort(f"Cost ceiling (${cost:.4f} > ${L.max_estimated_cost_usd})")
            return False
        if s.elapsed_seconds > L.timeout_seconds_total:
            self._abort(f"Total timeout ({s.elapsed_seconds:.0f}s)")
            return False
        return True

    def check_ocr(self, page_count: int) -> bool:
        s, L = self.state, self.state.limits
        if s.ocr_pages_processed + page_count > L.max_ocr_pages_per_run:
            self._abort(f"OCR page cap ({s.ocr_pages_processed + page_count} > {L.max_ocr_pages_per_run})")
            return False
        return True

    def check_doc_count(self, new_docs: int = 1) -> bool:
        s, L = self.state, self.state.limits
        if s.docs_processed + new_docs > L.max_docs_per_run:
            self._abort(f"Doc cap ({s.docs_processed + new_docs} > {L.max_docs_per_run})")
            return False
        return True

    def check_rounds(self) -> bool:
        if self.state.pipeline_rounds >= self.state.limits.max_pipeline_rounds:
            self._abort(f"Max rounds ({self.state.pipeline_rounds})")
            return False
        return True

    def record_llm_call(self, input_tokens: int, output_tokens: int):
        self.state.llm_calls           += 1
        self.state.total_input_tokens  += input_tokens
        self.state.total_output_tokens += output_tokens
        logger.debug(
            f"[{self.state.case_id}] LLM #{self.state.llm_calls} "
            f"in:{input_tokens} out:{output_tokens} "
            f"cost:${self.state.estimated_cost_usd:.5f}"
        )

    def record_ocr(self, pages: int): self.state.ocr_pages_processed += pages
    def record_doc(self):             self.state.docs_processed += 1
    def record_round(self):           self.state.pipeline_rounds += 1


# ─────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────

class GuardedDiscoveryRunner:
    """
    Accepts file_ids already uploaded via /discovery/intake.
    Resolves file metadata from discovery_files, then runs 7 guarded stages.

    Called from the new /discovery/run-guarded endpoint in discovery_intake.py.
    """

    def __init__(
        self,
        case_id:      str,
        firm_id:      str,
        limits:       Optional[AgentLimits] = None,
        bates_prefix: str = "PROD",
        bates_start:  int = 1,
    ):
        self.state        = AgentRunState(case_id=case_id, firm_id=firm_id, limits=limits or AgentLimits())
        self.guard        = DiscoveryAgentGuard(self.state)
        self.bates_prefix = bates_prefix
        self.bates_counter= bates_start

    # ── Entry point ──────────────────────────

    async def run_from_ids(self, file_ids: list, output_dir: str = "/tmp") -> dict:
        """
        Primary entry point. Resolves file metadata from discovery_files DB,
        then runs the guarded pipeline for each file.
        """
        # Resolve file rows from DB
        if not file_ids:
            return self._result("no_files")
        # Resolve file rows from DB
        with get_conn(self.state.firm_id) as conn:
            rows = conn.execute(
                "SELECT * FROM discovery_files WHERE id = ANY(%s)",
                (file_ids,),
            ).fetchall()

        file_records = [dict(r) for r in rows]

        logger.info(
            f"[{self.state.case_id}] Guarded run START "
            f"firm={self.state.firm_id} files={len(file_records)} "
            f"limits: {self.state.limits.max_llm_calls_per_run} LLM calls "
            f"${self.state.limits.max_estimated_cost_usd} cap"
        )

        if not self.guard.check_doc_count(len(file_records)):
            return self._result("blocked_doc_gate")

        for rec in file_records:
            if self.state.aborted:
                break
            self.guard.record_round()
            if not self.guard.check_rounds():
                break
            await self._process_file(rec)

        # Stage 7: ZIP
        if not self.state.aborted and self.state.docs_processed > 0:
            await self._build_zip(output_dir)

        self._persist_run_summary()

        logger.info(f"[{self.state.case_id}] Guarded run END — {self.state.to_summary()}")
        return self._result("completed" if not self.state.aborted else "aborted")

    # ── Per-file pipeline ────────────────────

    async def _process_file(self, rec: dict):
        state = self.state
        guard = self.guard

        if state.aborted:
            return

        file_id   = rec["id"]
        filename  = rec["filename"]
        orig_name = rec["original_name"]
        route     = rec.get("route", "digital")
        file_path = UPLOAD_DIR / filename

        async def _inner():

            # ── Stage 1: OCR / Text Extraction ───────────────────────────
            logger.info(f"[{state.case_id}] OCR/EXTRACT  file_id={file_id} route={route}")
            ocr_text   = ""
            page_count = 1

            try:
                if route == "ocr":
                    # Call existing OCR endpoint (httpx — same pattern as discovery_intake.py)
                    if not guard.check_ocr(10):  # pre-check with estimate
                        return
                    async with httpx.AsyncClient(timeout=60) as hx:
                        resp = await hx.post(
                            f"{BASE_URL}/discovery/process/ocr/{file_id}",
                            headers={"X-API-Key": API_KEY},
                        )
                    data       = resp.json()
                    ocr_text   = data.get("text", "")
                    page_count = max(1, data.get("word_count", 500) // 250)  # rough estimate

                elif route in ("digital", "unknown"):
                    # pdfminer — same as extract_text_to_case in discovery_intake.py
                    try:
                        from pdfminer.high_level import extract_text as pdf_extract
                        raw        = pdf_extract(str(file_path))
                        ocr_text   = " ".join(raw.split())[:10000]
                        page_count = max(1, len(ocr_text) // 2000)
                    except (OSError, ValueError, TypeError, ImportError) as e:
                        logger.warning(f"[DiscoveryAgent] PDF text extraction failed for {orig_name}: {e}")
                        ocr_text   = _get_doc_text(orig_name) if _PRIV_OK else ""
                        page_count = 1

                else:
                    # Audio etc. — pull from case_documents if already transcribed
                    ocr_text   = _get_doc_text(orig_name) if _PRIV_OK else ""
                    page_count = 1

                if not guard.check_ocr(page_count):
                    return

                guard.record_ocr(page_count)
                guard.record_success()

            except Exception as e:
                logger.error(f"[{state.case_id}] OCR failed file_id={file_id}: {e}")
                guard.record_error()
                return

            # ── Stage 2: Bates Stamping ───────────────────────────────────
            logger.info(f"[{state.case_id}] BATES  file_id={file_id}")
            bates_number = f"{self.bates_prefix}{str(self.bates_counter).zfill(6)}"
            stamped_path = str(file_path)  # default: same file

            try:
                if _IMPORTS_OK:
                    dest = UPLOAD_DIR / f"bates_{bates_number}_{filename}"
                    labels = [bates_number] * max(page_count, 1)
                    _stamp_bates(file_path, dest, labels)
                    stamped_path = str(dest)
                self.bates_counter += 1
                state.bates_manifest.append({
                    "bates":        bates_number,
                    "file_id":      file_id,
                    "original":     orig_name,
                    "stamped_path": stamped_path,
                })
                guard.record_success()

            except Exception as e:
                logger.error(f"[{state.case_id}] Bates failed file_id={file_id}: {e}")
                # Non-fatal
                self.bates_counter += 1

            # ── Stage 3: Privilege Detection ──────────────────────────────
            # Reuses _screen_privilege() from discovery_intake.py directly —
            # enclave routing + keyword fallback already handled there.
            # _hard_flag keyword check fires first inside _screen_privilege.
            logger.info(f"[{state.case_id}] PRIV   file_id={file_id}")
            privilege_result = {
                "is_privileged": False, "privilege_type": None,
                "confidence": 0.0, "requires_review": False,
            }

            try:
                if _PRIV_OK and ocr_text:
                    # Run synchronously (it writes directly to DB via UPDATE)
                    await _screen_privilege(
                        file_id=file_id,
                        text=ocr_text[:5000],
                        filename=orig_name,
                        firm_id=state.firm_id,
                    )
                    # Read verdict back from DB
                    with get_conn(state.firm_id) as conn:
                        row = conn.execute(
                            "SELECT privilege_flag, privilege_type, privilege_confidence, requires_review "
                            "FROM discovery_files WHERE id=%s", (file_id,)
                        ).fetchone()
                    if row:
                        privilege_result = {
                            "is_privileged":  bool(row["privilege_flag"]),
                            "privilege_type": row["privilege_type"],
                            "confidence":     row["privilege_confidence"] or 0.0,
                            "requires_review":bool(row["requires_review"]),
                        }
                    # Note: enclave calls ARE LLM calls — record approximate tokens
                    if privilege_result["is_privileged"]:
                        guard.record_llm_call(input_tokens=500, output_tokens=150)
                else:
                    # No privilege module — mark as stub
                    privilege_result["confidence"] = 0.0

                guard.record_success()

                if privilege_result["is_privileged"]:
                    state.flagged_docs.append({
                        "file_id":        file_id,
                        "bates":          bates_number,
                        "original_name":  orig_name,
                        "privilege_type": privilege_result["privilege_type"],
                        "confidence":     privilege_result["confidence"],
                        "requires_review":privilege_result["requires_review"],
                    })

            except Exception as e:
                logger.error(f"[{state.case_id}] Privilege failed file_id={file_id}: {e}")
                guard.record_error()
                return

            # ── Stage 4: Risk Scoring (heuristic — no LLM cost) ──────────
            logger.info(f"[{state.case_id}] RISK   file_id={file_id}")
            risk_result = {"score": -1, "level": "UNKNOWN"}
            try:
                if _IMPORTS_OK and ocr_text:
                    risk_result = _score_doc(ocr_text, privilege_result)
                else:
                    risk_result = {"score": 0, "level": "UNSCORED"}
                guard.record_success()

            except Exception as e:
                logger.error(f"[{state.case_id}] Risk score failed file_id={file_id}: {e}")
                guard.record_error()

            # ── Stage 5: Case Intelligence / AI Enrichment ────────────────
            # Skipped for hard-privileged docs; attorney reviews those directly.
            # Also skipped if LLM budget is exhausted — doc still completes.
            ai_enrichment = None
            if not privilege_result["is_privileged"]:
                logger.info(f"[{state.case_id}] ENRICH file_id={file_id}")
                try:
                    # Lightweight inline summary — ~250 input tokens, ~120 output
                    # Much cheaper than generate_case_brief (~1100/480 tokens)
                    if not guard.check_llm_call(estimated_input_tokens=250):
                        logger.warning(f"[{state.case_id}] Enrichment skipped — LLM budget exhausted")
                    elif ocr_text:
                        from backend.demo1.main import client, claude_with_retry
                        _resp = claude_with_retry(
                            client.messages.create,
                            model="claude-haiku-4-5-20251001",
                            max_tokens=120,
                            firm_id=state.firm_id,
                            messages=[{
                                "role": "user",
                                "content": (
                                    "Summarize this legal document in 2 sentences. "
                                    "List up to 3 key dates (YYYY-MM-DD) and 3 key parties. "
                                    "Reply in JSON only: "
                                    '{"summary":"...","key_dates":[],"entities":[]}'
                                    f"\n\nDOCUMENT:\n{ocr_text[:1500]}"
                                )
                            }]
                        )
                        import json as _json
                        raw = _resp.content[0].text.strip()
                        try:
                            ai_enrichment = _json.loads(raw)
                        except (_json.JSONDecodeError, ValueError, TypeError) as e:
                            logger.warning(f"[DiscoveryAgent] Enrichment JSON parse failed: {e}")
                            ai_enrichment = {"summary": raw[:200], "key_dates": [], "entities": []}
                        ai_enrichment["input_tokens"]  = _resp.usage.input_tokens
                        ai_enrichment["output_tokens"] = _resp.usage.output_tokens
                        guard.record_llm_call(
                            input_tokens  = _resp.usage.input_tokens,
                            output_tokens = _resp.usage.output_tokens,
                        )
                        guard.record_success()
                    else:
                        ai_enrichment = {"summary": "", "key_dates": [], "entities": []}

                except Exception as e:
                    logger.error(f"[{state.case_id}] Enrichment failed file_id={file_id}: {e}")
                    guard.record_error()

            # ── Stage 6: Privilege Log + Chain of Custody row ─────────────
            logger.info(f"[{state.case_id}] LOG    file_id={file_id}")
            try:
                log_row = {
                    "case_id":        state.case_id,
                    "file_id":        file_id,
                    "bates":          bates_number,
                    "original_name":  orig_name,
                    "stamped_path":   stamped_path,
                    "is_privileged":  privilege_result["is_privileged"],
                    "privilege_type": privilege_result.get("privilege_type"),
                    "confidence":     privilege_result.get("confidence"),
                    "requires_review":privilege_result.get("requires_review"),
                    "risk_score":     risk_result["score"],
                    "risk_label":     risk_result["level"],
                    "ai_summary":     (ai_enrichment or {}).get("summary", ""),
                    "ocr_pages":      page_count,
                }

                # Write to privilege_log table (existing privilege_log.py pattern)
                with get_conn(state.firm_id) as conn:
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS privilege_log (
                            id              SERIAL PRIMARY KEY,
                            case_id         TEXT,
                            file_id         INTEGER,
                            bates           TEXT,
                            original_name   TEXT,
                            is_privileged   INTEGER,
                            privilege_type  TEXT,
                            confidence      REAL,
                            requires_review INTEGER,
                            risk_score      REAL,
                            risk_label      TEXT,
                            ai_summary      TEXT,
                            created_at      TIMESTAMPTZ DEFAULT NOW()
                        )
                    """)
                    conn.execute("""
                        INSERT INTO privilege_log
                        (case_number, filename, privilege_type, basis, file_id, bates,
                         is_privileged, confidence, requires_review, risk_score, risk_label, ai_summary)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        log_row["case_id"], log_row["original_name"],
                        log_row["privilege_type"] or "none", "none",
                        log_row["file_id"], log_row["bates"],
                        int(log_row["is_privileged"]),
                        log_row["confidence"],
                        int(log_row["requires_review"] or 0),
                        log_row["risk_score"], log_row["risk_label"], log_row["ai_summary"],
                    ))
                    # Update discovery_files status
                    conn.execute(
                        "UPDATE discovery_files SET status='processed' WHERE id=%s", (file_id,)
                    )

                state.privilege_log_rows.append(log_row)
                guard.record_doc()
                guard.record_success()

            except Exception as e:
                logger.error(f"[{state.case_id}] Log/CoC failed file_id={file_id}: {e}")
                guard.record_error()

        # Per-stage timeout
        try:
            await asyncio.wait_for(_inner(), timeout=state.limits.timeout_seconds_per_stage)
        except asyncio.TimeoutError:
            state.aborted      = True
            state.abort_reason = f"Stage timeout ({state.limits.timeout_seconds_per_stage}s) file_id={file_id}"
            logger.error(f"[{state.case_id}] {state.abort_reason}")

    # ── Stage 7: ZIP ─────────────────────────

    async def _build_zip(self, output_dir: str):
        import zipfile
        state = self.state
        logger.info(f"[{state.case_id}] ZIP  building discovery package")
        try:
            zip_path = Path(output_dir) / f"{state.case_id}_discovery_guarded.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for entry in state.bates_manifest:
                    sp = Path(entry["stamped_path"])
                    if sp.exists():
                        zf.write(sp, arcname=f"{entry['bates']}_{entry['original']}")
            state.zip_path = str(zip_path)
            logger.info(f"[{state.case_id}] ZIP  → {zip_path}")
        except Exception as e:
            logger.error(f"[{state.case_id}] ZIP failed: {e}")
            self.guard.record_error()

    # ── Persist run summary ──────────────────

    def _persist_run_summary(self):
        try:
            s = self.state.to_summary()
            with get_conn(self.state.firm_id) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS discovery_runs (
                        id              SERIAL PRIMARY KEY,
                        case_id         TEXT,
                        firm_id         TEXT,
                        status          TEXT,
                        docs_processed  INTEGER,
                        flagged_docs    INTEGER,
                        llm_calls       INTEGER,
                        estimated_cost  REAL,
                        elapsed_seconds REAL,
                        zip_path        TEXT,
                        aborted         INTEGER,
                        abort_reason    TEXT,
                        created_at      TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                conn.execute("""
                    INSERT INTO discovery_runs
                    (case_id, firm_id, status, docs_processed, flagged_docs,
                     llm_calls, estimated_cost, elapsed_seconds, zip_path, aborted, abort_reason)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    s["case_id"], s["firm_id"],
                    "aborted" if s["aborted"] else "completed",
                    s["docs_processed"], s["flagged_docs"],
                    s["llm_calls"], s["estimated_cost_usd"],
                    s["elapsed_seconds"], s["zip_path"],
                    int(s["aborted"]), s["abort_reason"],
                ))
        except Exception as e:
            logger.warning(f"[{self.state.case_id}] Persist summary failed: {e}")

    def _result(self, status: str) -> dict:
        return {"status": status, "summary": self.state.to_summary()}
