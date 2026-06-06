# Prompt Registry

## Purpose

Prompts are managed by name and version instead of being embedded in workflow code.

Current registry:

- `chat.default`
- `query_rewriter.default`
- `nightly_memory_update` from `src/kaoyan_agent/prompts/nightly_memory_update_prompt.txt`

## Naming

Use `<agent_or_workflow>.<purpose>`:

- `chat.default`
- `router.classify`
- `event_extractor.daily`
- `memory_gate.decide`
- `problem_gate.decide`
- `score_analysis.trend`
- `focus_report.generate`

## Output Schemas

Every prompt that affects control flow must point to a schema in `docs/interface_contracts.md` or `docs/SCHEMAS.md`.

## Fallback

Every prompt caller must define:

- expected JSON keys
- parse fallback
- allowed value ranges
- whether failed output is allowed to write into long-term memory



