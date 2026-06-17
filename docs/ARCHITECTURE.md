# Architecture

This project uses a Streamlit + SQLite + LangChain Agentic Workflow architecture. UI code handles interaction, workflows orchestrate the application flow, agents call LLMs and read-only tools through LangChain, repositories own SQLite CRUD, and schemas constrain structured LLM output.

## Product Information Architecture

The current MVP is one kaoyan preparation workspace:

```text
Kaoyan Agent
-> global chat sessions
-> common study functions
-> agent diagnostics
-> settings
```

Sidebar order:

1. New chat
2. Common functions: Today Task / Study Plan, Supervision Mode, Mistake Review, Score Trend
3. Recent chats
4. Agent diagnostics: Nightly Review, Problem Board
5. Light encouragement: Fortune Card
6. Settings

Memory is a lower-level capability. The settings page provides the current memory viewer.

## Package Layout

```text
src/kaoyan_agent/
  agents/        Agent capability wrappers; no SQL writes
  core/          settings, paths, JSON parser, container
  db/            schema, connection, initialization, migrations
  repositories/  SQLite CRUD boundary; no LLM calls
  schemas/       dataclass contracts and Pydantic structured outputs
  services/      LLM / LangChain-ready client
  prompts/       prompt registry
  workflows/     application orchestration
  ui/            Streamlit pages and components
  memory/        memory-domain logic
```

Root business packages such as `agents/`, `db/`, `services/`, and `ui/` should not be restored. Use `from kaoyan_agent...` imports.

## Layer Rules

- `app.py`: Streamlit setup, `init_db()`, sidebar navigation, page dispatch.
- `ui/`: render and collect interactions only.
- `workflows/`: orchestrate repositories, agents, services, and schemas.
- `agents/`: encapsulate reasoning; do not write the database.
- `repositories/`: CRUD only; do not call LLMs or build prompts.
- `db/`: connection, schema initialization, migrations, and helpers.
- `schemas/`: structured-output contracts.
- `memory/`: retrieval, gating, merging, and scoring logic.

## Core Chains

Online chat:

```text
app.py
-> chat_page
-> OnlineSessionWorkflow
-> ChatRepository / RawEventRepository / AgentRunRepository
-> QueryRewriter + Router + MemoryRetriever + ContextBuilder
-> ChatAgent
-> LangChain create_agent with read-only tools
-> LLMClient.chat fallback
```

Nightly review:

```text
nightly_review_page
-> nightly_review_panel
-> NightlyMemoryWorkflow
-> NightlyMemoryAgent
-> LangChain create_agent(response_format=NightlyMemoryUpdateOutput)
-> response["structured_response"]
-> model_dump()
-> nightly_review_repository
-> daily_memory_graphs
-> Memory Gate / Problem Gate / Skill Gate
-> memory_repository / problem_repository / skill_memory_repository
-> global_memory_nodes / global_memory_edges
-> agent_runs
-> SQLite
```

Practice review:

```text
mistake_review_panel
-> PlanningWorkflow.generate_and_save_practice_card()
-> PracticeReviewAgent
-> LangChain create_agent(response_format=PracticeReviewCard)
-> normalize_card()
-> PracticeReviewRepository.create_card()
-> SQLite
```

## LangChain Boundary

- `services/llm_client.py` exposes `create_langchain_model()`, preferring `ChatDeepSeek` and falling back to `ChatOpenAI`.
- `NightlyMemoryAgent` and `PracticeReviewAgent` use Pydantic `response_format` and read `response["structured_response"]`.
- `ChatAgent` uses only read-only tools: `list_open_problems_tool`, `list_today_tasks_tool`, and `search_memory_tool`.
- Agents do not write SQLite. Database writes remain in workflows through repositories.
- This version does not implement LangGraph. A future version can consider mapping `OnlineSessionWorkflow` to LangGraph StateGraph only if more complex state-graph orchestration is needed.

## Embedding Boundary

Embeddings are accessed through `kaoyan_agent.memory.embeddings.EmbeddingClient`.
The default provider is SiliconFlow with model `BAAI/bge-m3` and an
OpenAI-compatible `/embeddings` endpoint. Configure it with:

```text
EMBEDDING_PROVIDER=siliconflow
EMBEDDING_API_KEY=...
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_MODEL=BAAI/bge-m3
```

The system does not require embeddings to succeed. Missing keys, HTTP errors,
or malformed responses return empty vectors, and memory gates/retrieval fall
back to lexical scoring. Gate results preserve `embedding_status` and
`embedding_error` for diagnostics.

## Database Compatibility

The SQLite database may still contain `projects` and `project_id` from earlier iterations. Keep them as compatibility fields for now. The current UI and docs do not treat them as product architecture.

Do not delete `data/app.db`, do not rebuild it, and do not drop compatibility columns in this task.

## Pydantic Structured Output

`src/kaoyan_agent/schemas/nightly_memory.py` defines the structured output for Nightly Memory Update. Any LLM output that can affect `problem_board`, `memories`, or later workflow control must pass Pydantic validation first.

Failure behavior:

- save raw response
- save `parse_status="failed"`
- save `error_message`
- do not write `problem_board`
- do not write `memories`
- do not write `skill_memories`
- do not write `daily_memory_graphs`
