# Task Assignment

All members work inside `src/kaoyan_agent/` unless editing `app.py`, docs, tests, or local config.

## Member 1: Navigation, Chat Entry, Database Compatibility

Primary files:

- `app.py`
- `src/kaoyan_agent/ui/chat_page.py`
- `src/kaoyan_agent/workflows/chat_workflow.py`
- `src/kaoyan_agent/repositories/conversation_repository.py`
- `src/kaoyan_agent/repositories/raw_events.py`
- `src/kaoyan_agent/db/`

Boundary: New Chat creates a global chat session. Chat is evidence input, not the product center.

## Member 2: Nightly Review, Problem Board, Memory

Primary files:

- `src/kaoyan_agent/ui/nightly_review_page.py`
- `src/kaoyan_agent/ui/components/nightly_review_panel.py`
- `src/kaoyan_agent/ui/problem_board_page.py`
- `src/kaoyan_agent/ui/components/problem_board_panel.py`
- `src/kaoyan_agent/ui/components/memory_panel.py`
- `src/kaoyan_agent/workflows/nightly_memory_workflow.py`
- `src/kaoyan_agent/agents/nightly_memory_agent.py`
- `src/kaoyan_agent/schemas/nightly_memory.py`
- `src/kaoyan_agent/repositories/nightly_review_repository.py`
- `src/kaoyan_agent/repositories/problem_repository.py`
- `src/kaoyan_agent/repositories/memory_repository.py`

Boundary: Long-term writes must pass Pydantic validation. Failed structured parsing must not write `problem_board` or `memories`.

## Member 3: Common Study Functions

Primary files:

- `src/kaoyan_agent/ui/task_page.py`
- `src/kaoyan_agent/ui/mistake_review_page.py`
- `src/kaoyan_agent/ui/score_trend_page.py`
- `src/kaoyan_agent/ui/components/task_panel.py`
- `src/kaoyan_agent/ui/components/mistake_review_panel.py`
- `src/kaoyan_agent/ui/components/score_trend_panel.py`
- `src/kaoyan_agent/workflows/workspace_workflow.py`
- `src/kaoyan_agent/workflows/planning.py`
- `src/kaoyan_agent/repositories/study_task_repository.py`
- `src/kaoyan_agent/repositories/mistake_review_repository.py`
- `src/kaoyan_agent/repositories/score_repository.py`

Boundary: Today Task / Study Plan, Supervision Mode, Mistake Review, and Score Trend are high-frequency entries and should stay near the top of the sidebar.

## Member 4: Supervision Mode And Fortune Card

Primary files:

- `src/kaoyan_agent/ui/supervision_page.py`
- `src/kaoyan_agent/ui/fortune_page.py`
- `src/kaoyan_agent/ui/components/pomodoro_supervision_panel.py`
- `src/kaoyan_agent/ui/components/fortune_card.py`
- `src/kaoyan_agent/workflows/focus.py`
- `src/kaoyan_agent/workflows/planning.py`
- `src/kaoyan_agent/repositories/supervision_repository.py`
- `src/kaoyan_agent/repositories/fortune_repository.py`

Boundary: Supervision Mode is an independent page. Task E extends the existing
pomodoro flow with camera snapshot recognition, state-event persistence, and a
focus report. UI must not save raw camera images; only recognition results and
report signals should enter SQLite.

## Member 5: Settings And Runtime Info

Primary files:

- `src/kaoyan_agent/ui/settings_page.py`
- `src/kaoyan_agent/workflows/settings_workflow.py`
- `src/kaoyan_agent/ui/components/memory_panel.py`

Boundary: Settings stays minimal: memory viewer, model info, and database path.

## Shared Files

Coordinate before changing:

- `src/kaoyan_agent/db/schema.sql`
- `src/kaoyan_agent/db/database.py`
- `src/kaoyan_agent/schemas/nightly_memory.py`
- `src/kaoyan_agent/schemas/contracts.py`
- `src/kaoyan_agent/services/llm_client.py`
- `src/kaoyan_agent/prompts/nightly_memory_update_prompt.txt`
- public workflow method signatures
