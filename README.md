# Kaoyan Problem Discovery Agent

This project is a problem-discovery and adaptive-intervention agent for
Chinese postgraduate entrance exam preparation.

The current implementation is V0.2-precheck: V0.1.5 chat/session behavior is
kept stable, and the manual Nightly Memory Update entrypoint is wired to the
V0.2 database tables.

## Current Scope

- Streamlit chat UI
- OpenAI-compatible LLM client
- SQLite database initialization
- Multiple chat sessions
- Sidebar session creation and history switching
- Conversation logging for user and assistant messages
- ChatAgent context limited to the current session's latest messages
- Manual `生成今晚记忆更新` button
- NightlyMemoryAgent JSON parsing and fallback
- `nightly_reviews`, `problem_board`, and `memories` persistence
- Basic display for nightly review result, open problems, and memories
- `.env` based local LLM configuration

Not implemented in this version:

- File upload
- Web search
- Automatic scheduled jobs
- Vector database
- Retrieval from long-term memory during normal chat
- Plan generation

## Project Structure

```text
.
|-- app.py
|-- config.py
|-- agents/
|   |-- chat_agent.py
|   `-- nightly_memory_agent.py
|-- db/
|   |-- database.py
|   `-- schema.sql
|-- prompts/
|   `-- nightly_memory_update_prompt.txt
|-- services/
|   `-- llm_client.py
|-- docs/
|-- data/
|   `-- app.db
|-- .env.example
|-- requirements.txt
`-- README.md
```

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

The app initializes SQLite automatically. The default database path is:

```text
data/app.db
```

During early development, if an old local database conflicts with the current
schema, it is acceptable to delete `data/app.db` and let the app recreate it:

```bash
del data\app.db
streamlit run app.py
```

## Database

Core tables:

```text
chat_sessions
conversations
memories
problem_board
nightly_reviews
```

Each message belongs to exactly one `chat_session`. Normal chat only uses the
current session's recent messages; it does not yet retrieve `memories` or
`problem_board`.

## Verify V0.1.5 Behavior

1. Open the Streamlit page.
2. Send a message in the default session.
3. Click `新建对话` in the sidebar.
4. Send a different message.
5. Click the old session in the sidebar and confirm only that session's
   messages are shown.
6. In one session, send `我叫小李，正在复习 408。`
7. Then send `我刚才说我在复习什么？`
8. Confirm the assistant answers from the same session context.
9. Switch to a new session and ask the same question again; it should not know
   the previous session's content.

Check saved sessions and messages:

```bash
python -c "import sqlite3; c=sqlite3.connect('data/app.db'); print(c.execute('select id, title, updated_at from chat_sessions order by updated_at desc').fetchall()); print(c.execute('select session_id, role, content from conversations order by id').fetchall())"
```

## Verify V0.2 Nightly Memory Update

1. Create a few conversations and send study review messages.
2. Click `生成今晚记忆更新` in the sidebar.
3. Confirm the page shows `今晚记忆更新结果` and a `daily_summary`.
4. Confirm `Problem Board` and `Memories` either show rows or clearly say they
   are empty.
5. Confirm SQLite has a `nightly_reviews` record.

Check saved nightly data:

```bash
python -c "import sqlite3; c=sqlite3.connect('data/app.db'); print('reviews', c.execute('select id, review_date, parse_status, daily_summary from nightly_reviews order by id desc limit 3').fetchall()); print('problems', c.execute('select id, problem_type, subject, status, review_id from problem_board order by id desc limit 5').fetchall()); print('memories', c.execute('select id, memory_type, content, review_id from memories order by id desc limit 5').fetchall())"
```

If the prompt file is missing, the LLM is unavailable, or the model does not
return valid JSON, the app saves a fallback `nightly_reviews` record with a
non-`ok` `parse_status` instead of crashing.

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
