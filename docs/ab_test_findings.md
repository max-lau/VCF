# A/B Test Findings: case_brief_prompt_v1

## Experiment
Three prompt strategies for `generate_case_brief()` in ParaIQ, tested across 4 real cases.
Variant assignment is deterministic via MD5 hash of `case_id:experiment_id` —
same case always receives same prompt version, making results reproducible.

## Variants
- **Control**: Original prompt — "senior litigation paralegal" role, full 7-section schema
- **Variant A**: Chain-of-thought framing — asks model to reason through legal theory,
  strongest evidence, and biggest risk before producing JSON
- **Variant B**: Minimal framing — brief role statement, lets schema drive structure

## Results (n=4, early data)

| Metric            | Control | Variant A | Variant B |
|-------------------|--------:|----------:|----------:|
| Sample size       | 1       | 1         | 2         |
| Avg latency (ms)  | 31,802  | 25,903    | 32,039    |
| Avg input tokens  | 490     | 504       | 674       |
| Avg output tokens | 1,518   | 1,192     | 1,587     |
| Avg output length | 6,975   | 5,324     | 6,639     |
| Total cost ($)    | 0.0242  | 0.0194    | 0.0517    |

## Early Observations
- **Variant A is fastest and cheapest**: 19% lower latency than control, 20% fewer output tokens.
  The chain-of-thought instruction may focus the model, reducing verbose padding.
- **Variant B is most expensive**: Higher input tokens (longer preamble) and highest output.
  Minimal framing appears to cause the model to be more expansive, not less.
- **All variants produce valid JSON** with all 7 required sections — no schema failures.

## Conclusion (provisional)
Variant A shows the best efficiency profile at this sample size.
Recommendation: continue collecting data (target n=20 per variant) before declaring a winner.
Quality scoring (human review of section content) is the next measurement to add.

## Infrastructure
- Log: `logs/ab_test_log.jsonl` (JSONL, one record per brief generation)
- Report: `python3 scripts/ab_test_report.py [--experiment case_brief_prompt_v1]`
- Each record includes: variant, tokens in/out, latency_ms, output_length, trace_id
- Langfuse traces tagged with variant name for cross-referencing in dashboard
