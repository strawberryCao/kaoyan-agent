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
- `memories`: long-term memory with status, valid time, evidence references, and effectiveness score.
- `problem_board`: open/watching/resolved/ignored/archived problems with evidence and merge metadata.
- `memory_operations` and `problem_operations`: gate decisions.
- `global_memory_nodes` and `global_memory_edges`: cross-day graph.
- `skill_memories`: reusable validated intervention workflows.

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
