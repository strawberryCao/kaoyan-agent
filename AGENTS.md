# AGENTS.md

## Repository Name

Kaoyan Problem Discovery Agent

## Goal

This repository implements a problem-discovery and adaptive-intervention agent for Chinese postgraduate entrance exam preparation. It is not a plain Q&A chatbot and not a multi-workspace management product.

Core loop:

```text
daily interaction
-> raw evidence
-> nightly memory update
-> Pydantic structured validation
-> valuable problem discovery
-> Problem Board
-> long-term memory
-> next intervention / task
-> intervention tracking
```

## Product Structure

The MVP has one kaoyan preparation workspace:

```text
Kaoyan Agent
-> global chats
-> common study functions
-> agent diagnostics
-> settings
```

The sidebar should expose New Chat, common study functions, recent chats, Nightly Review, Problem Board, Fortune Card, and Settings. Memory is viewed inside Settings.

## Engineering Rules

- Use `src/kaoyan_agent/` as the only formal business package.
- Use `from kaoyan_agent...` imports.
- `app.py` is the only Streamlit entrypoint.
- `ui/` renders pages and collects user actions only.
- `workflows/` orchestrates repositories, agents, services, and schemas.
- `agents/` does not write SQL.
- `repositories/` only performs CRUD; it does not call LLMs or build prompts.
- `db/` owns connection, schema initialization, migrations, and helpers.
- `schemas/` owns Pydantic structured-output validation.
- `memory/` owns memory-domain logic, not Streamlit pages.

## Data Rules

Historical database compatibility fields such as `project_id` may remain. They are not product concepts in the current UI. Do not delete or rebuild `data/app.db`.

LLM outputs that affect `problem_board`, `memories`, or later workflow control must pass Pydantic validation before persistence.

Failure path:

```text
ValidationError
-> nightly_reviews.raw_response
-> parse_status="failed"
-> error_message
-> no problem_board write
-> no memories write
```

## Definition Of Done

1. Code is implemented in the correct layer.
2. Existing real database is not deleted or reset.
3. UI uses the approved user-visible names.
4. Tests or compile checks run.
5. Docs are updated when behavior or boundaries change.
