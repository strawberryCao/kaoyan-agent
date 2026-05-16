# Architecture

## Center of the Architecture

The center of this project is not ChatAgent.

The center is ProblemDiscoveryAgent.

ChatAgent is only the front-stage interaction layer.

## System Overview

User Interaction
→ Conversation Logging
→ Nightly Memory Update
→ Problem Discovery
→ Problem Board
→ Memory Update
→ Next-Day Intervention

## Online Loop

The online loop handles real-time user interaction.

User input
→ Context building
→ Optional clarification
→ ChatAgent response
→ Conversation saved

In the first MVP, the online loop can stay simple.

## Offline Loop

The offline loop is the core.

Daily conversations
→ NightlyMemoryAgent
→ key event extraction
→ valuable problem discovery
→ memory update
→ problem board update
→ next action generation

## Core Components

### ChatAgent

Handles normal user-facing answers.

### ClarificationAgent

Asks necessary clarification questions when the user’s request is vague.

Rules:

- Ask only when the missing information significantly affects answer quality.
- Ask at most two questions.
- Avoid unnecessary questioning.
- If a reasonable assumption is enough, answer with the assumption.

### NightlyMemoryAgent

Runs at night or through a manual button in the MVP.

Responsibilities:

- read today’s conversations
- read existing memories
- read open problems
- summarize daily events
- discover valuable problems
- generate memory updates
- generate next actions

### ProblemDiscoveryAgent

Discovers valuable problems.

Each problem should include:

- problem_type
- subject
- description
- evidence
- root_cause
- severity
- confidence
- value_score
- suggested_action
- status

### MemoryAgent

Controls long-term memory.

It should not blindly store all conversations.

Memory should be inserted, updated, merged, or skipped.

### PlanAgent

Generates next-day plans based on problems, memory, and unfinished tasks.

### FileAgent

Handles uploaded files.

Responsibilities:

- upload
- save
- parse
- summarize
- index
- retrieve

### SearchAgent

Handles web search when current or external information is needed.

Search should be used for:

- current exam policy
- admission information
- latest materials
- official documents
- external verification

## Problem Board

A blackboard-style shared table for all discovered problems.

The Problem Board is used by:

- NightlyMemoryAgent
- MemoryAgent
- PlanAgent
- future ChatAgent context retrieval

## Data Stores

### SQLite

Used for:

- conversations
- files
- file_chunks
- memories
- problem_board
- daily_reviews
- nightly_reviews
- daily_plans
- tasks

### File Storage

Original files go to:

```text
data/uploads/
```

Parsed text goes to:

```text
data/parsed/
```

## First MVP Architecture

The first MVP should include:

- Streamlit app
- LLM client
- SQLite database
- conversations table
- memories table
- problem_board table
- nightly_reviews table
- Nightly Memory Update button

## Future Architecture Extensions

Later versions can add:

- MetaController
- ClarificationAgent
- FileAgent
- SearchAgent
- Skills registry
- lightweight self-evolution of prompts and strategies
