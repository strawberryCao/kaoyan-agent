# Kaoyan Problem Discovery Agent

This project is a problem-discovery and adaptive-intervention agent for
Chinese postgraduate entrance exam preparation.

The current implementation is V0.1.5: basic chat, DeepSeek/OpenAI-compatible
LLM calls, SQLite conversation logging, chat session management, and scoped
multi-turn context.

## Current Scope

- Streamlit chat UI
- OpenAI-compatible LLM client
- SQLite database initialization
- Multiple chat sessions
- Sidebar session creation and history switching
- Conversation logging for user and assistant messages
- LLM context limited to the current session's latest messages
- `.env` based local LLM configuration

Nightly memory update, Problem Board, long-term memory, file handling, and
web search are planned for later versions and are not implemented in V0.1.5.

## Project Structure

```text
.
|-- app.py
|-- config.py
|-- db/
|   |-- database.py
|   `-- schema.sql
|-- services/
|   `-- llm_client.py
|-- docs/
|-- data/
|   `-- app.db
|-- .env.example
|-- requirements.txt
`-- README.md
```

Future versions can add explicit modules such as `agents/`, `memory/`,
`files/`, `prompts/`, and `tools/` without changing the V0.1.5 session layer.

## Setup

Create and activate a virtual environment, then install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create a local `.env` file from `.env.example`:

```text
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-v4-flash
```

Do not commit real API keys.

## Run

```bash
streamlit run app.py
```

The app initializes SQLite automatically. The database file is created at:

```text
data/app.db
```

## Database

V0.1.5 uses two tables:

```text
chat_sessions
- id
- title
- summary
- created_at
- updated_at

conversations
- id
- session_id
- role
- content
- created_at
```

Each message belongs to exactly one `chat_session`. The UI only displays the
current session, and the LLM request only uses the current session's latest 20
messages.

## Verify Session Management

1. Open the Streamlit page.
2. Send a message in the default session.
3. Click `新建对话` in the sidebar.
4. Send a different message.
5. Click the old session in the sidebar and confirm only its own messages show.

Check the saved sessions and messages:

```bash
python -c "import sqlite3; c=sqlite3.connect('data/app.db'); print(c.execute('select id, title, updated_at from chat_sessions order by updated_at desc').fetchall()); print(c.execute('select session_id, role, content from conversations order by id').fetchall())"
```

## Verify Multi-Turn Context

In one session, send:

```text
我叫小李，正在复习 408。
```

Then send:

```text
我刚才说我在复习什么？
```

The assistant should answer based on the same session context. Create a new
session and ask the second question again; it should not know the previous
session's content.

## Existing Database Compatibility

If `data/app.db` was created by V0.1 and only has the old `conversations`
table, V0.1.5 runs a simple migration during startup:

- creates `chat_sessions`
- adds nullable `session_id` to the existing `conversations` table
- creates one `历史对话` session
- attaches old conversation rows to that session

For early development, it is also acceptable to delete `data/app.db` and let
the app recreate a fresh database:

```bash
del data\app.db
streamlit run app.py
```

## Roadmap

Follow `docs/ROADMAP.md`.

- V0.1: Basic chat and conversation logging
- V0.1.5: Session management and scoped multi-turn context
- V0.2: Nightly Memory Update MVP
- V0.3: Problem Board UI
- V0.4: Clarification Agent
- V0.5: Plan Agent
- V0.6: File Management
- V0.7: Web Search
- V0.8: Skills and self-evolution
