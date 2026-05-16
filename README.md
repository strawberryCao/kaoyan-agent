# Kaoyan Problem Discovery Agent

This project is a problem-discovery and adaptive-intervention agent for
Chinese postgraduate entrance exam preparation. V0.1 only implements the
minimum chat and conversation logging loop.

## Current Scope

- Streamlit chat UI
- OpenAI-compatible LLM client
- SQLite database initialization
- Conversation logging for user and assistant messages
- `.env` based local LLM configuration

Nightly memory update, Problem Board, long-term memory, file handling, and
MetaController orchestration are planned for later versions.

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
`files/`, `prompts/`, and `tools/` without changing the V0.1 database layer.

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
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
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

## Verify

1. Open the Streamlit page.
2. Send a chat message.
3. Confirm the assistant responds.
4. Check that both messages were saved:

```bash
python -c "import sqlite3; c=sqlite3.connect('data/app.db'); print(c.execute('select role, content, created_at from conversations order by id desc limit 5').fetchall())"
```

## Roadmap

Follow `docs/ROADMAP.md`.

- V0.1: Basic chat and conversation logging
- V0.2: Nightly Memory Update MVP
- V0.3: Problem Board UI
- V0.4: Clarification Agent
- V0.5: Plan Agent
- V0.6: File Management
- V0.7: Web Search
- V0.8: Skills and self-evolution
