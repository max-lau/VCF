# ParaIQ — Guarded Discovery Pipeline: Best Practices

**Date:** May 2026  
**Author:** Maxwell / ParaIQ  
**VPS:** `root@5.161.83.6` (`ubuntu-2gb-ash-1`)  
**Key file:** `/root/nlp-portfolio/discovery_agent_guard.py`  
**Endpoint:** `POST /discovery/run-guarded`

---

## 1. The Core Problem This Solves

Agentic AI pipelines have no natural cost ceiling. Without guards:
- A 30-doc discovery batch calling `generate_case_brief()` per doc = **$0.315** — exceeds cap, aborts mid-run
- A runaway loop or hung OCR stage can burn tokens indefinitely
- No visibility into what failed, when, or why

The `DiscoveryAgentGuard` pattern solves all three.

---

## 2. The `AgentLimits` Pattern — Frozen, Single Source of Truth

```python
@dataclass(frozen=True)
class AgentLimits:
    max_llm_calls_per_run:     int   = 8
    max_total_tokens_per_run:  int   = 12000
    max_estimated_cost_usd:    float = 0.25
    max_docs_per_run:          int   = 30
    max_ocr_pages_per_run:     int   = 150
    timeout_seconds_per_stage: int   = 90
    timeout_seconds_total:     int   = 600
    circuit_breaker_error_threshold: int = 3
```

**Why `frozen=True`:**  
A mutable limits object can be widened by agent logic at runtime. `frozen=True` makes it immutable — no stage can relax its own constraints.

**Why caller-overridable:**  
The FastAPI endpoint exposes every limit as an optional body param. A bulk run can request `max_docs=50`; a tight demo can cap at `max_cost_usd=0.01`. Defaults are always safe.

---

## 3. The Guard Pattern — O(1) Pre-flight Checks

Every expensive operation is preceded by a guard check:

```python
# Before any LLM call:
if not guard.check_llm_call(estimated_input_tokens=250):
    return  # abort this stage, not the whole run

# Before OCR:
if not guard.check_ocr(page_count):
    return

# Before processing docs:
if not guard.check_doc_count(len(file_ids)):
    return self._result("blocked_doc_gate")
```

**Key principle:** Guard checks are synchronous and O(1). Zero performance overhead. Call them freely.

**Key principle:** A failed check aborts the *stage*, not the *run* (unless it's a hard gate like doc count). The doc still completes with whatever stages succeeded.

---

## 4. Circuit Breaker — Stops Cascading Failures

```python
def record_error(self):
    self.state.consecutive_errors += 1
    if self.state.consecutive_errors >= self.state.limits.circuit_breaker_error_threshold:
        self._trip_circuit(f"{self.state.consecutive_errors} consecutive errors")

def record_success(self):
    self.state.consecutive_errors = 0  # reset on any success
```

**Why this matters:** If the privilege enclave goes down mid-batch, without a circuit breaker every subsequent doc will hang for 30s waiting for a timeout. With 3 consecutive errors, the circuit opens and the remaining docs skip straight to logging with a clean abort reason.

---

## 5. Token Accounting — Real Cost Visibility

```python
def record_llm_call(self, input_tokens: int, output_tokens: int):
    self.state.llm_calls           += 1
    self.state.total_input_tokens  += input_tokens
    self.state.total_output_tokens += output_tokens
```

**Always use actual token counts from the API response**, not estimates:

```python
guard.record_llm_call(
    input_tokens  = _resp.usage.input_tokens,   # from Anthropic response
    output_tokens = _resp.usage.output_tokens,
)
```

Estimates are only used for the *pre-flight* `check_llm_call()` projection. Actuals are recorded after the call returns.

---

## 6. Model Selection — Match Model to Task

| Task | Model | Avg Cost/Doc | When to Use |
|---|---|---|---|
| Full case brief | `claude-sonnet` via `generate_case_brief()` | $0.0105 | Attorney-requested, single case |
| Lightweight doc summary | `claude-haiku-4-5` inline | $0.003 | Bulk discovery runs |
| Privilege detection | Legal-BERT INT8 (enclave) | ~$0 | Every doc, always |
| Risk scoring | `score_text()` heuristic | $0 | Every doc, always |

**Rule:** Default to Haiku for bulk pipeline enrichment. Reserve Sonnet/Opus for attorney-facing outputs (briefs, timelines, contradiction reports).

**The specific swap that saved 3.5x:**

```python
# Before — $0.0105/doc, 15s
generate_case_brief(case_id_int)  # full 2-page Claude Sonnet memo

# After — $0.003/doc, 2s
claude-haiku-4-5, max_tokens=120, text[:1500]  # key facts only
```

---

## 7. Per-Stage Timeout Wrapping

Every per-doc pipeline runs inside `asyncio.wait_for()`:

```python
try:
    await asyncio.wait_for(_inner(), timeout=state.limits.timeout_seconds_per_stage)
except asyncio.TimeoutError:
    state.aborted      = True
    state.abort_reason = f"Stage timeout ({state.limits.timeout_seconds_per_stage}s)"
```

**Why:** OCR on a large scanned PDF can hang. A privilege enclave call can stall. Without a timeout, one bad doc blocks the entire batch indefinitely.

---

## 8. `_hard_flag()` — Zero-Cost Privilege Detection

Before any LLM privilege call, run the keyword override:

```python
hard_flagged = _hard_flag(ocr_text)  # synchronous, zero tokens

if hard_flagged:
    privilege_result = {
        "is_privileged":  True,
        "privilege_type": "Attorney-Client (hard flag)",
        "confidence":     1.0,
        "hard_flagged":   True,
        "input_tokens":   0,   # ← no LLM cost
        "output_tokens":  0,
    }
else:
    # Only now spend tokens on LLM privilege analysis
    await check_privilege(ocr_text, case_id=state.case_id)
```

**Why:** Docs with explicit keywords (`"attorney-client"`, `"privileged and confidential"`, etc.) don't need LLM inference. Hard flags are deterministic, instantaneous, and free.

---

## 9. Non-Fatal Stage Design

Stages are designed so one failure doesn't kill the doc:

- **Bates fails on PNG** → logged as error, pipeline continues with `stamped_path = original_path`
- **Enrichment budget exhausted** → logged as warning, doc completes without summary
- **Privilege enclave down** → falls back to keyword scan
- **Risk scorer exception** → defaults to `{"score": -1, "level": "UNKNOWN"}`

Only truly unrecoverable errors (OCR timeout, DB connection lost) abort the run.

---

## 10. Run Persistence — Every Run Auditable

Every run writes a summary row to `discovery_runs`:

```sql
SELECT case_id, status, docs_processed, flagged_docs,
       llm_calls, estimated_cost, elapsed_seconds, abort_reason
FROM discovery_runs
ORDER BY created_at DESC;
```

This feeds into the Vue dashboard's run history view and gives attorneys visibility into what the agent did, what it cost, and why it stopped.

---

## 11. Benchmark Results (May 2026)

| Metric | Before (unguarded) | After (guarded) |
|---|---|---|
| Cost per doc | $0.0105 | $0.003 |
| Time per doc | ~15s | ~2s |
| Docs per $0.25 cap | 23 | **83** |
| Runaway loop protection | ❌ | ✅ |
| Cost visibility | ❌ | ✅ real-time |
| Circuit breaker | ❌ | ✅ |
| Audit trail | ❌ | ✅ SQLite |

---

## 12. Deployment Checklist

```bash
# 1. Guard file must be at project root (not demo1/) — Python path issue
cp backend/demo1/discovery_agent_guard.py /root/nlp-portfolio/discovery_agent_guard.py

# 2. Always run with venv Python
/root/nlp-portfolio/.venv/bin/python3 discovery_agent_guard.py

# 3. After any patch, copy to both locations
cp discovery_agent_guard.py backend/demo1/discovery_agent_guard.py

# 4. Restart API after changes
pm2 restart paraiq-api

# 5. Verify privilege_log schema has all columns
sqlite3 backend/demo1/analyses.db "PRAGMA table_info(privilege_log);"
```

---

## 13. Next Steps

- [ ] Wire Vue frontend `DiscoveryUpload.vue` to call `/discovery/run-guarded` (one button, full batch)
- [ ] Add `discovery_runs` tab to ParaIQ dashboard showing cost + status history
- [ ] Expand `_hard_flag()` keyword list as new privilege patterns emerge
- [ ] Consider per-firm `AgentLimits` stored in `db_enclaves` — different caps for different firm tiers
- [ ] MCP tunnel: expose `/discovery/run-guarded` as an MCP tool for Claude Code agent access

---

## 14. Engineering Discipline

This project follows the global **CLAUDE.md** engineering standards — see `CLAUDE.md` for the full specification.

**ParaIQ-specific reminders:**
- Guard file lives at `/root/nlp-portfolio/` AND `/root/nlp-portfolio/backend/demo1/` — always sync both after any patch
- Always use `/root/nlp-portfolio/.venv/bin/python3` — never bare `python3`
- Pre-flight grep before any new import: `grep "^def " backend/demo1/*.py`
- Tests: `/root/nlp-portfolio/.venv/bin/python3 -m pytest tests/test_discovery_agent_guard.py -v`
- Commit debt from May 21 session: 4 commits outstanding (see CLAUDE.md §3.1)
