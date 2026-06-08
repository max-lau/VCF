# ─────────────────────────────────────────────────────────────────────────────
# PASTE THIS AT THE BOTTOM OF discovery_intake.py
# ─────────────────────────────────────────────────────────────────────────────

from discovery_agent_guard import GuardedDiscoveryRunner, AgentLimits

@router.post("/run-guarded")
async def run_guarded_discovery(body: dict):
    """
    Guarded batch discovery run.
    Accepts file_ids already uploaded via /discovery/intake.
    Runs all 7 pipeline stages with hard compute guards.

    Body:
        file_ids     list[int]  — required; IDs from discovery_files
        case_number  str        — required; ties to cases table
        firm_id      str        — optional; for enclave routing (default: "default")
        bates_prefix str        — optional; e.g. "PROD", "DEF", "CONF" (default: "PROD")
        bates_start  int        — optional; starting Bates number (default: 1)
        output_dir   str        — optional; where to write the ZIP (default: /tmp)

        # Override any limit (all optional):
        max_llm_calls        int
        max_total_tokens     int
        max_docs             int
        max_ocr_pages        int
        max_cost_usd         float
        timeout_per_stage    int
        timeout_total        int

    Returns:
        { status: "completed"|"aborted"|"blocked_doc_gate"|"no_files",
          summary: { llm_calls, estimated_cost_usd, flagged_docs, zip_path, ... } }
    """
    file_ids     = body.get("file_ids", [])
    case_number  = body.get("case_number", "").strip()
    firm_id      = body.get("firm_id", "default")
    bates_prefix = body.get("bates_prefix", "PROD")
    bates_start  = int(body.get("bates_start", 1))
    output_dir   = body.get("output_dir", "/tmp")

    if not file_ids:
        raise HTTPException(400, "file_ids is required")
    if not case_number:
        raise HTTPException(400, "case_number is required")

    # Build limits — caller can override any individual limit
    limits = AgentLimits(
        max_llm_calls_per_run     = int(body.get("max_llm_calls",     8)),
        max_total_tokens_per_run  = int(body.get("max_total_tokens",  12000)),
        max_docs_per_run          = int(body.get("max_docs",          30)),
        max_ocr_pages_per_run     = int(body.get("max_ocr_pages",     150)),
        max_estimated_cost_usd    = float(body.get("max_cost_usd",    0.25)),
        timeout_seconds_per_stage = int(body.get("timeout_per_stage", 90)),
        timeout_seconds_total     = int(body.get("timeout_total",     600)),
    )

    runner = GuardedDiscoveryRunner(
        case_id      = case_number,
        firm_id      = firm_id,
        limits       = limits,
        bates_prefix = bates_prefix,
        bates_start  = bates_start,
    )

    result = await runner.run_from_ids(file_ids=file_ids, output_dir=output_dir)
    return result
