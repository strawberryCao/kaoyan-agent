# Database Design

## Current Product Scope

The MVP has one kaoyan preparation workspace. Database compatibility fields from earlier iterations may remain, but the UI should not expose them as product concepts.

Do not delete or rebuild `data/app.db`.

## Evidence Tables

- `raw_events`: canonical evidence source for user input, assistant replies, file summaries, task feedback, scores, and supervision events.
- `conversations`: chat messages.
- `chat_sessions`: global chat sessions.
- `agent_runs`: request/response audit log for agent calls.
- `tool_runs`: request/result audit log for tool calls.
- `evidence_links`: links memories, problems, tasks, reports, and reviews back to raw evidence.

## Memory And Problem Tables

- `nightly_reviews`: full nightly review result, raw model output, `parse_status`, and `error_message`.
- `daily_memory_graphs`: per-day graph before long-term merge.
- `memories`: long-term memory with status, valid time, evidence references, effectiveness score, and optional `embedding_json`.
- `problem_board`: open/watching/resolved/ignored/archived problems with evidence, merge metadata, and optional `embedding_json`.
- `memory_operations` and `problem_operations`: gate decisions.
- `global_memory_nodes` and `global_memory_edges`: cross-day graph. Nodes may store `embedding_json` for small-scale SQLite cosine retrieval.
- `skill_memories`: reusable validated intervention workflows with trigger/procedure JSON, confidence, effectiveness, evidence references, and optional embeddings.
- `skill_operations`: Skill Gate decisions for insert/update/merge/skip.

## Study Tables

- `study_tasks`: today or dated task cards.
- `practice_reviews`: generated or evidence-grounded review questions and outcomes.
- `mistake_cards`: mistake-review cards.
- `motivation_items`: daily signs, random tasks, and soothing actions.
- `score_records`: score entries.
- `score_analysis_reports`: trend/risk analysis.

## Supervision Tables

- `focus_sessions`: supervision session lifecycle.
- `focus_timeline_events`: start/pause/resume/finish timeline.
- `focus_state_events`: state labels only.
- `focus_reports`: AI supervision report and problem signals.

## Compatibility Fields

Tables may still include `project_id`, and the database may still include `projects`. These are retained only to avoid damaging historical data. New UI work should treat the product as a single workspace.

If a repository needs a compatibility value, keep that logic inside the repository or database layer. Do not push it into Streamlit state.

## Structured Output Rule

Pydantic schema and SQLite schema are different contracts. `src/kaoyan_agent/schemas/nightly_memory.py` validates whether LLM output is acceptable; `src/kaoyan_agent/db/schema.sql` defines how accepted data is stored.

Never write unvalidated LLM JSON directly into `problem_board` or `memories`.

The current offline memory loop writes long-term tables only after structured
validation succeeds:

```text
raw_events
-> NightlyMemoryAgent structured candidates
-> nightly_reviews
-> episodic/semantic memories
-> daily_memory_graphs + daily_graph_nodes + daily_graph_edges
-> Chroma / Neo4j index sync
-> global_graph_nodes / global_graph_edges
-> graph-context ProblemDiscoveryAgent
-> Memory Gate / Problem Gate / Skill Gate
-> memories / problem_board / skill_memories
```

Only `parse_status="success"` may write long-term tables. `failed` and
`partial_success` persist `nightly_reviews.raw_response`, diagnostics, and
`error_message`, but do not write `problem_board`, `memories`, `skill_memories`,
or `daily_memory_graphs`.

SQLite remains the source of truth. Chroma stores memory/problem vector indexes,
and Neo4j stores relationship indexes. Index sync failure is isolated from the
SQLite transaction and recorded in `nightly_reviews.index_sync_status_json`.

Embeddings are provided through a low-cost API configuration rather than a local
model. The default is SiliconFlow `BAAI/bge-m3` through an OpenAI-compatible
`/embeddings` endpoint. If the embedding API key is missing or the request
fails, gates and retrieval fall back to lexical scoring and record the embedding
status in gate results.
