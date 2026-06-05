# Kaoyan Problem Discovery Agent

This project is a problem-discovery and adaptive-intervention agent for
Chinese postgraduate entrance exam preparation.

The current implementation is V0.4: V0.3 chat/session and Nightly Memory
Update behavior is kept stable, with four additional Streamlit demo modules
for exam-preparation workflows.

## Current Scope

- Streamlit chat UI
- OpenAI-compatible LLM client
- SQLite database initialization
- Multiple chat sessions
- Sidebar session creation and history switching
- Conversation logging for user and assistant messages
- ChatAgent context limited to the current session's latest messages
- Main chat page with a manual `生成夜间回顾` button
- Separate internal Nightly Review page with a manual `生成今晚记忆更新` button
- Separate internal Problem Board page for open problems
- Separate internal Memories page for long-term memory records
- NightlyMemoryAgent JSON parsing and fallback
- `nightly_reviews`, `problem_board`, and `memories` persistence
- Today dashboard with SQLite-backed study task cards
- Mistake review pool with generated mistake cards and reason statistics
- Chapter checkpoint page with generated questions and fallback scoring
- Daily sign, random task, and low-energy task demo page
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
|   |-- checkpoint_agent.py
|   |-- intervention_agent.py
|   |-- mistake_review_agent.py
|   `-- nightly_memory_agent.py
|-- db/
|   |-- database.py
|   `-- schema.sql
|-- pages/
|   |-- 1_Nightly_Review.py
|   |-- 2_Problem_Board.py
|   `-- 3_Memories.py
|-- prompts/
|   `-- nightly_memory_update_prompt.txt
|-- services/
|   `-- llm_client.py
|-- ui/
|   |-- demo_pages.py
|   `-- nightly_review.py
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
study_tasks
mistake_cards
checkpoint_records
daily_signs
```

Each message belongs to exactly one `chat_session`. Normal chat only uses the
current session's recent messages; it does not yet retrieve `memories` or
`problem_board`.

Problem Board and Memories are internal dashboard pages. The latest nightly
review result is also displayed on the main chat page after pressing
`生成夜间回顾`.

The V0.4 demo tables are initialized automatically by `init_db()`:

- `study_tasks`: today's task cards, subject, estimated minutes, source, and
  `todo/doing/done/skipped` status.
- `mistake_cards`: saved mistake cards, reason label, knowledge points, review
  priority, and `unmastered/reviewing/mastered` status.
- `checkpoint_records`: chapter checkpoint answers, score, pass flag, feedback,
  and weak points.
- `daily_signs`: saved daily sign level, sign text, and advice.

## Demo Pages

The main `app.py` sidebar has these pages:

1. `聊天`: keeps the original chat and manual Nightly Memory Update flow.
2. `今日作战台`: add tasks, generate default examples, and update task status
   with `开始` / `完成` / `放弃`.
3. `错题复刷池`: enter a mistake question, generate a mistake card, save it, view
   reason statistics, and update mastery status.
4. `章节闯关验收`: generate 3 checkpoint questions plus 1 retelling question,
   submit an answer, save a score, and create a review task when not passed.
5. `上岸签 / 随机任务`: generate a daily sign, generate a random low-pressure
   task, or convert a low-energy state into a 3-5 minute task.

## Fallback Demo Logic

The demo does not require an API key to be usable.

- `safe_generate_with_llm()` first tries the configured OpenAI-compatible
  client, then returns a fallback string on any error.
- Mistake cards fall back to rule-based reason inference and a template
  analysis.
- Checkpoint questions fall back to chapter templates; checkpoint scoring falls
  back to answer-length bands: under 30 chars = 50, 30-100 chars = 70, over
  100 chars = 80.
- Daily signs, random tasks, and low-energy tasks fall back to local templates.

To improve the real LLM behavior later, update these modules:

- `agents/mistake_review_agent.py`
- `agents/checkpoint_agent.py`
- `agents/intervention_agent.py`
- `services/llm_client.py`

## Verify Chat Behavior

1. Open the Streamlit app.
2. Confirm the main page only shows chat, new-session controls, and chat history.
3. Send a message in the default session.
4. Click `新建对话` in the sidebar.
5. Send a different message.
6. Click the old session in the sidebar and confirm only that session's
   messages are shown.
7. In one session, send `我叫小李，正在复习 408。`
8. Then send `我刚才说我在复习什么？`
9. Confirm the assistant answers from the same session context.
10. Switch to a new session and ask the same question again; it should not know
    the previous session's content.

Check saved sessions and messages:

```bash
python -c "import sqlite3; c=sqlite3.connect('data/app.db'); print(c.execute('select id, title, updated_at from chat_sessions order by updated_at desc').fetchall()); print(c.execute('select session_id, role, content from conversations order by id').fetchall())"
```

## Verify Nightly Memory Update

1. Create a few conversations and send study review messages.
2. Click `生成夜间回顾` on the main chat page.
3. Alternatively, open the `Nightly Review` page from the Streamlit sidebar and
   click `生成今晚记忆更新`.
4. Confirm the page shows `今晚记忆更新结果` and a `daily_summary`.
5. Open the `Problem Board` page and confirm open problems are shown there, or
   that the empty state is clear.
6. Open the `Memories` page and confirm memory records are shown there, or that
   the empty state is clear.
7. Confirm the chat page still does not display Problem Board or Memories.
8. Confirm SQLite has a `nightly_reviews` record.

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
- V0.2: Chat/session stabilization
- V0.3: Nightly Memory Update and Problem Discovery MVP
- V0.4: Streamlit business demo modules
- V0.5: Clarification Agent
- V0.6: Plan Agent
- V0.7: File Management
- V0.8: Web Search
- V0.9: Skills and self-evolution
