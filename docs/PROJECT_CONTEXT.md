# Project Context

## What This Project Really Is

This project is a problem-discovery agent.

The exam-preparation scenario is only the first vertical implementation.

The core hypothesis is:

If an agent can discover valuable problems from daily user behavior, then solving those problems becomes much easier.

## Why Exam Preparation

The original target was a general autonomous problem-discovery agent.

However, a general agent would require:

- open-ended environment perception
- physical or external execution
- complex permissions
- long-term goal management
- safety boundaries
- uncertain feedback loops

This is too difficult for a course project.

Therefore, the project chooses postgraduate exam preparation as the vertical scenario.

## Current Scenario

The system focuses on:

- Math I
- English I
- 408 Computer Science
- wrong-question analysis
- learning planning
- weak-point discovery
- execution difficulty
- anxiety / study state
- daily review
- next-day planning

## Core System Idea

The agent should not only answer what the user asks.

It should discover what the user has not clearly realized.

Examples:

- The user says “I understand the answer but cannot solve it myself.”
  The agent should discover a method-transfer problem.

- The user repeatedly fails daily plans.
  The agent should discover a planning or execution problem.

- The user repeatedly asks similar knowledge points.
  The agent should discover a weak knowledge cluster.

- The user expresses anxiety but remains inactive.
  The agent should discover that anxiety may be connected to task ambiguity or lack of execution feedback.

## Core Daily Loop

1. User chats with the agent.
2. The system records the conversation.
3. At night, the agent summarizes the day.
4. The Problem Discovery Agent finds valuable problems.
5. The Memory Agent updates long-term memory.
6. The Plan Agent creates next-day interventions.
7. Future interactions use these memories and problems.

## Key Design Claim

The project should be described as:

A problem-discovery and adaptive-intervention agent for exam preparation.

It should not be described as:

A simple chatbot for postgraduate exam Q&A.
