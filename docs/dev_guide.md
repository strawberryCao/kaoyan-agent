# Developer Guide

## Basic Rule

All business code lives under:

```text
src/kaoyan_agent/
```

Do not restore root-level business packages such as `agents/`, `db/`, `ui/`, `services/`, `repositories/`, or `workflows/`.

Use:

```python
from kaoyan_agent...
```

## Product Rule

The MVP is one kaoyan preparation workspace. The UI should expose global chats, common study functions, agent diagnostics, light encouragement, and settings.

Do not expose multi-workspace management in the product UI. Historical `project_id` fields can remain in repositories and the database for compatibility, but UI code should only keep chat and page navigation state.

## Page Locations

- Chat: `src/kaoyan_agent/ui/chat_page.py`
- Today Task / Study Plan: `src/kaoyan_agent/ui/task_page.py`
- Supervision Mode: `src/kaoyan_agent/ui/supervision_page.py`
- Mistake Review: `src/kaoyan_agent/ui/mistake_review_page.py`
- Score Trend: `src/kaoyan_agent/ui/score_trend_page.py`
- Nightly Review: `src/kaoyan_agent/ui/nightly_review_page.py`
- Problem Board: `src/kaoyan_agent/ui/problem_board_page.py`
- Fortune Card: `src/kaoyan_agent/ui/fortune_page.py`
- Settings: `src/kaoyan_agent/ui/settings_page.py`

## Layering

UI should call workflow functions or render reusable components. UI should not write SQL and should not call LLMs directly.

```text
ui/page
-> ui/component
-> workflow
-> repository / agent / service / schema
```

Repository code must not call LLMs or build prompts. Agent code must not write SQL.

## Common Work Areas

- Sidebar and page dispatch: `app.py`
- Common study data aggregation: `workflows/workspace_workflow.py`
- Settings data aggregation: `workflows/settings_workflow.py`
- Task creation and score writes: `workflows/planning.py`
- Nightly structured output: `workflows/nightly_memory_workflow.py`
- Memory display: `ui/components/memory_panel.py`

Internal files such as `focus.py`, `motivation.py`, and `practice_review.py` remain as compatibility wrappers or domain modules. User-visible pages should use the approved Chinese labels.

## Database Changes

1. Update `docs/database_design.md`.
2. Update `src/kaoyan_agent/db/schema.sql`.
3. Add forward-compatible migration helpers in `src/kaoyan_agent/db/database.py`.
4. Add repository methods.
5. Call repositories from workflows.
6. Call workflows from UI.

Never delete or rebuild `data/app.db` during normal development.

## Nightly Memory Development

The preferred path is LangChain structured output:

```text
NightlyMemoryAgent
-> create_langchain_model()
-> create_agent(response_format=NightlyMemoryUpdateOutput)
-> response["structured_response"]
-> NightlyMemoryUpdateOutput.model_validate()
-> workflow model_dump()
-> repositories
-> SQLite
```

The raw JSON fallback remains:

```text
LLM raw response
-> NightlyMemoryUpdateOutput.model_validate_json()
-> typed object
-> model_dump()
-> repositories
-> SQLite
```

If validation fails, save raw output and error diagnostics in `nightly_reviews`; do not write `problem_board` or `memories`.

## LangChain Development

- Use `create_langchain_model()` from `services/llm_client.py` instead of instantiating provider models inside UI or workflows.
- `create_langchain_model()` tries `langchain_deepseek.ChatDeepSeek` first, then `langchain_openai.ChatOpenAI`.
- Use `create_agent(..., response_format=PydanticModel)` when an agent output controls persistence or workflow decisions.
- Read structured output from `response["structured_response"]`.
- ChatAgent tools must be read-only. Current tools are `list_open_problems_tool`, `list_today_tasks_tool`, and `search_memory_tool`.
- Do not put database writes in tools or agents. Writes belong in workflows calling repositories.
- Do not add LangGraph in this version. A future version can consider mapping `OnlineSessionWorkflow` to LangGraph StateGraph only if state-graph orchestration becomes necessary.

## Checks

```powershell
.\.venv\Scripts\python.exe -m compileall app.py src tests
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -c "from kaoyan_agent.db import init_db; init_db(); print('ok')"
```
