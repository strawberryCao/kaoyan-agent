# AGENTS.md

## Project Name

Kaoyan Problem Discovery Agent

## Project Goal

This project is not a normal postgraduate exam chatbot.

It is a problem-discovery and adaptive-intervention agent for Chinese postgraduate entrance exam preparation.

The core idea is:

Daily user interaction → nightly review → valuable problem discovery → root cause analysis → memory update → next-day intervention.

The most important component is the Problem Discovery Agent.

If the agent can discover a valuable problem, that itself is already the beginning of solving the problem.

## Product Positioning

The first implementation focuses on postgraduate exam preparation, but the underlying design is a general problem-discovery agent framework.

The original broader idea was:

- The agent discovers that a plant has not been watered for days and treats it as a problem.
- The agent notices repeated complaints about a campus shuttle bus and identifies the need for a reservation system.
- The agent notices that a user often says they are anxious but remains inactive, then tries to discover the deeper cause.

Because this general problem space is too broad for a course project, the project is narrowed to the exam-preparation scenario.

## Core Loop

The system should follow this loop:

1. Record user conversations, uploaded files, plans, and completion feedback.
2. Run a nightly memory update.
3. Discover valuable problems from today’s events.
4. Analyze root causes.
5. Decide which problems should enter the Problem Board.
6. Decide which information should become long-term memory.
7. Generate next-day interventions or study tasks.
8. Track whether interventions work.

## Key Principle

Do not implement this as a simple Q&A chatbot.

Chat is only the input channel.

The center of the system is:

- Problem Discovery Agent
- Nightly Memory Update
- Problem Board
- Long-term Memory
- Plan / Intervention Generation

## First MVP Priority

The first MVP should implement:

1. Streamlit chat UI.
2. LLM client.
3. SQLite conversation logging.
4. Nightly Memory Update button.
5. Problem Board table.
6. Memory table.
7. Nightly review result display.

Do not implement everything at once.

## Agent Modules

Recommended modules:

- ChatAgent: handles normal user interaction.
- ProblemDiscoveryAgent: discovers valuable problems.
- NightlyMemoryAgent: performs nightly reflection and memory update.
- MemoryAgent: stores, merges, and retrieves memories.
- PlanAgent: converts problems into next-day tasks.
- ClarificationAgent: asks follow-up questions when user needs are vague.
- FileAgent: handles uploaded files.
- SearchAgent: searches web when current external information is required.

## Most Important Current Feature

The current priority is Nightly Memory Update.

It should:

1. Read today’s conversations.
2. Read existing memories.
3. Read open problems from the Problem Board.
4. Summarize key daily events.
5. Discover 1 to 3 valuable problems.
6. Generate memory updates.
7. Save discovered problems into the Problem Board.
8. Save memory updates into the memories table.
9. Save the full result into nightly_reviews.

## Problem Value Criteria

A problem is valuable if it satisfies one or more:

- It appears repeatedly.
- It affects future learning or project progress.
- It can be intervened by the agent.
- It reveals a root cause rather than a surface issue.
- It requires follow-up tracking.
- It has high impact on exam preparation or project implementation.

## Memory Rule

Do not save every message as long-term memory.

Memory pipeline:

Raw conversation → daily summary → candidate problems → candidate memories → memory gate → merge or store.

Only store information that will affect future answers, plans, problem discovery, or intervention strategy.

## Engineering Rules

- Use Python.
- Use Streamlit for the first demo.
- Use SQLite for persistence.
- Use an OpenAI-compatible LLM client.
- Use `.env` for local secrets.
- Do not commit real API keys.
- Keep modules explicit and small.
- Use structured JSON outputs for LLM control-flow decisions.
- Add fallback when JSON parsing fails.
- Do not introduce LangChain, LangGraph, Neo4j, or vector database in the first MVP unless explicitly requested.
- Prioritize a working MVP over architectural completeness.

## Definition of Done

A task is done only when:

1. Code is implemented.
2. The app can run.
3. The feature can be manually tested.
4. SQLite tables are initialized automatically.
5. No real API key is committed.
6. README or docs are updated if behavior changes.


