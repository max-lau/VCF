# ParaIQ: Production-Grade Legal AI Infrastructure

**A solo-built, multi-tenant legal AI platform — engineered by a practicing legal mind, not just a developer.**
Live at [app.para-iq.com](https://app.para-iq.com) · [github.com/max-lau/nlp-portfolio](https://github.com/max-lau/nlp-portfolio)

Most legal-tech platforms today are case-management systems with an LLM bolted on. ParaIQ inverts that: it's an AI-native reasoning layer — agentic research, drafting, review, and risk analysis — built on top of the workflow plumbing the industry already solved. The system is built and operated by one person who is both the legal domain expert and the full-stack engineer, which shows up directly in how the AI is scoped, guarded, and evaluated.

## AI Capabilities (shipped in the last six months)

| Capability | What it does | Why it matters |
|---|---|---|
| **Autonomous AI agents** | Firm-wide agents plan and execute multi-step tasks (research → draft → file-to-matter) with structured plans, not free-form chat | Agent output passes through a validation gate before anything touches firm data |
| **AI legal research** | Voice- or text-triggered research memos per matter, favorability-scored, delivered to a per-firm dashboard | Attorneys get cited memos, not chat transcripts |
| **AI document review & risk** | Per-document risk scoring, entity extraction, contradiction detection across a case file | Surfaces the cross-document inconsistencies humans miss at volume |
| **Passive time capture** | Reconstructs billable activity from system events; attorney reviews, never auto-bills | Solves the #1 revenue leak in small firms without trust-destroying auto-billing |
| **Client communication drafting** | Drafts status updates and letters in firm voice, gated behind attorney review | Review gate is structural (watermark shield + audit log), not a checkbox |
| **RAG pipeline, measured** | ChromaDB + MiniLM embeddings, Claude generation, RAGAS-scored | Four documented eval runs with real deltas — including a regression (below) |
| **Cost-aware model routing** | Haiku for parsing/intent, Sonnet for generation, per-firm usage governance | AI spend is a governed budget line, not a surprise |
| **Voice command layer** | 31 commands across Telegram bot, dashboard mic, and API — Whisper STT → intent parse → execution | Same auth and tenant scoping as every other channel |

## Evaluation Discipline: The RAG Trail

Four RAGAS-scored eval runs, each documented with hypothesis → change → measured result — including the run that went backwards:

| Metric | Run 1 | Run 2 | Run 3 | Run 4 |
|---|---|---|---|---|
| Faithfulness | 0.883 | 0.931 | 0.879 | 0.893 |
| Answer Relevancy | 0.814 | 0.761 | 0.762 | 0.852 |
| Context Precision | 0.961 | 0.958 | 0.973 | 0.973 |

Run 3 stored full document text in retrieval metadata expecting a faithfulness gain — it *regressed* (-0.052), because more context gave the model more surface to stray from. Run 4 recovered it with a tightened generation contract (strict quoting prompt, reduced max_tokens). The point isn't the scores; it's that changes to the AI pipeline are hypothesis-tested, and negative results are kept in the record.

## Security Architecture: Verified, Not Just Configured

Legal data demands isolation guarantees, and configuration is not a guarantee. The defining incident of this project's security work:

**The RLS That Wasn't.** ParaIQ's tenant isolation is Postgres row-level security — policies on every tenant-scoped table, keyed on a per-connection firm context, with `FORCE ROW LEVEL SECURITY` applied specifically to close the table-owner bypass. Every configuration-level check passed: policies present and correct, FORCE set on 67 tables, the context function returning the right value. Then a routine adversarial test — firm B requesting firm A's case brief over HTTP — returned the data.

Root cause, two layers deep: the app's database role carried `BYPASSRLS`, a role *attribute* that ignores RLS entirely, FORCE included — every policy had been decorative for application traffic since the Postgres migration. And the connection string pointed at a transaction-mode pooler, where per-connection tenant context is unsafe by design (contexts can bleed across multiplexed connections).

The fix ([incident write-up](docs/incident-2026-07-06-bypassrls.md), commit `7e08574`): a dedicated least-privilege application role (`NOBYPASSRLS`), session-mode pooling, and table ownership transferred to the app role — safe precisely *because* FORCE subjects owners to policies. Isolation claims are now gated on a six-case cross-tenant test matrix (cross-tenant reads 404, same-tenant 200, strict firm scoping even for the superuser role), not on configuration inspection. The hole was found and closed before any real client data existed — which is what the staged rollout was designed for.

The rest of the security posture, in the same spirit:

- **Fail-closed tenant context** — a JWT/firm-context mismatch once caused a silent fallback to the default tenant; it is now a startup assertion that refuses to boot rather than a runtime default
- **Prompt injection defense + output validation** — all AI output passes a validation layer (PII redaction, harmful-content scan, schema checks), audit-logged
- **JWT-only browser auth** — static API keys are restricted to three localhost machine-to-machine paths, rejected if proxy headers are present
- **Attorney review gates** — AI drafts carry a watermark shield until a named attorney confirms review; the confirmation is an audit-trail event
- **Immutable audit logging** — every AI action, agent step, and privileged operation is logged per firm

## What's Deliberately Deferred

Billing and financial infrastructure are intentionally absent. Those layers are commoditized by incumbents and add no differentiation; the engineering bet is entirely on the AI reasoning layer and the trust infrastructure around it.

## The Differentiator

Every guardrail above sits where it does because the builder has been the end user: knowing *which* AI outputs a malpractice carrier would ask about, *which* documents are privileged before a classifier says so, and *why* an attorney will never trust auto-billed time. ParaIQ exists because both skill sets sat in one person — which shows up not in any single feature, but in *where the guardrails are placed*.
