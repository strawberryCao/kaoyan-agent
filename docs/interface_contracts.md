# Interface Contracts

## AgentRequest

`AgentRequest(request_id, user_id, session_id, input_text, context, retrieved_items, tool_results, metadata)`

Used by workflows when invoking an agent.

## AgentResponse

`AgentResponse(text, structured_data, confidence, evidence_refs, next_actions, raw_response, parse_status, errors)`

All LLM control-flow failures must set a non-success `parse_status` and keep raw output when available.

## ToolRequest

`ToolRequest(tool_name, arguments, user_id, session_id, trace_id)`

Tools should not read Streamlit state or create database connections outside repositories.

## ToolResult

`ToolResult(tool_name, status, data, summary, evidence_refs, error)`

`status` is `ok` or `error`.

## Workflow DTOs

Current workflow outputs:

- `OnlineSessionResult`
- `NightlyWorkflowResult`

UI pages should render these DTOs and avoid calling agents directly.

## Structured Output

Nightly Memory output must be validated through `NightlyMemoryUpdateOutput.model_validate_json()` before it can affect `problem_board`, `memories`, or workflow control flow.

The generic `kaoyan_agent.core.json_parser` helpers are still allowed for low-risk fallback extraction in non-persistence features, but they are not enough for nightly memory writes. If Pydantic validation fails, save `raw_response`, `parse_status="failed"`, and `error_message`, then skip writes to `problem_board` and `memories`.

Current Nightly Memory output includes:

- `daily_summary`
- `key_events`
- `episodic_memories`
- `semantic_memories`
- `daily_graph_nodes`
- `daily_graph_edges`
- `daily_memory_graph`
- `candidate_problems` / `discovered_problems`
- `evidence_links`
- `memory_updates`
- `skill_observations` / `skill_updates`
- `next_actions`

`candidate_problems`, `memory_updates`, and `skill_updates` may suggest
`operation`, `merge_key`, and `target_*_id`. The workflow gate makes the final
insert/update/merge/skip decision for problem board, legacy memory updates, and
skills. Formal `episodic_memories` and `semantic_memories` are Pydantic-validated
and written with stable merge keys.

`NightlyWorkflowResult` now includes `inserted_skill_ids`, `daily_memory_graph_id`,
and `gate_results` in addition to problem and memory IDs.

`nightly_reviews.inserted_counts_json` records inserted counts for the formal
chain. `nightly_reviews.index_sync_status_json` records Chroma and Neo4j sync
status; index failures must not roll back the SQLite write.



