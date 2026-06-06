# Roadmap

## V0.1 Basic Chat and Conversation Logging

Goal:

Build the minimum working chat system.

Tasks:

- Streamlit chat UI
- LLM client
- SQLite database initialization
- conversations table
- save user and assistant messages

Done when:

- `streamlit run app.py` works
- user can chat
- messages are saved into SQLite

## V0.2 Nightly Memory Update MVP

Goal:

Build the core offline evolution loop.

Tasks:

- create NightlyMemoryAgent
- add nightly memory update prompt
- create memories table
- create problem_board table
- create nightly_reviews table
- add button: Generate Nightly Memory Update
- read today’s conversations
- call LLM to generate structured JSON
- save discovered problems
- save memory updates
- display result in UI

Done when:

- clicking the button generates a daily summary
- valuable problems are inserted into problem_board
- memory updates are inserted into memories
- full review result is saved into nightly_reviews

## V0.3 Problem Board UI

Goal:

Make discovered problems visible.

Tasks:

- show open problems in Streamlit
- show severity, confidence, and value_score
- allow marking problem as resolved or ignored

Done when:

- open problems are visible in the UI
- problem status can be updated without deleting history

## V0.4 Clarification Agent

Goal:

Add active questioning.

Tasks:

- detect vague user requests
- ask at most two clarification questions
- avoid unnecessary questioning
- answer with assumptions when reasonable

Done when:

- vague requests trigger clarification
- clear requests are answered directly

## V0.5 Plan Agent

Goal:

Convert discovered problems into next-day actions.

Tasks:

- read open problems
- read memory
- generate next-day plan
- save daily plan
- track task status

Done when:

- the system can generate a plan based on problem_board and memories

## V0.6 File Management

Goal:

Support user-uploaded files.

Tasks:

- upload TXT/PDF
- save original file
- parse text
- summarize file
- save file metadata
- associate file with memory or problem

Done when:

- uploaded files are saved
- parsed text is available
- file summaries are stored

## V0.7 Web Search

Goal:

Add search capability.

Tasks:

- search when current information is needed
- prefer official sources
- store source metadata
- generate source-grounded answers

Done when:

- current-information questions can trigger search
- answer includes source records or citations

## V0.8 Skills and Self-Evolution

Goal:

Package repeatable workflows.

Tasks:

- wrong-question analysis skill
- English word note skill
- daily review skill
- search-with-citation skill
- track skill effectiveness
- update strategy prompts based on feedback

Done when:

- skills can be selected by trigger
- strategy updates are stored and reused


