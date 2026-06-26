# C/D/E Feature Integration

This project now treats `src/kaoyan_agent/` as the only runtime business package.
The original task C/D/E feature packages are archived under
`archive_feature_packages/` and are not imported by `app.py`, `src/`, or `tests/`.

## Runtime Mapping

- Task C task, score, practice, fortune, and problem-board behavior is mapped to
  `StudyTaskRepository`, `ScoreRepository`, `PracticeReviewRepository`,
  `MotivationRepository`, and `ProblemRepository`.
- Task D focus timer behavior is integrated into `FocusWorkflow` and
  `FocusRepository`; camera recognition, `raw_events`, and focus reports remain
  part of the same workflow.
- Task E remains the main formal package structure for router, memory,
  problem board, schemas, prompt registry, and validation.

## Persistence Rules

- No duplicate `daily_tasks` or `daily_plans` runtime tables are introduced.
  D-style statuses are mapped centrally in `StudyTaskRepository`.
- `motivation_items` is the formal persistence table for daily sign and
  micro-action output.
- `focus_sessions` is extended additively for timer compatibility. Existing
  database rows are preserved by migration.
- `ProblemDiscoveryAgent` only returns validated discovery results. It does not
  write to `problem_board`; writes remain in workflow/gate/repository layers.

## Final P0 Productization Pass

- Online chat now grades action intent before dispatch. Ambiguous mistake
  questions are answered first and create a persistent pending action; only an
  explicit save command or user confirmation writes `mistake_cards`.
- Online chat writes `conversations`, `raw_events`, business operation tables,
  `online_action_runs`, `pending_actions`, and execution trace records. It does
  not write `memories`, `problem_board`, or graph tables directly.
- Each online turn records engineering trace steps in `agent_trace_steps`.
  These traces are visible in the chat page and the Agent Diagnostics page, but
  they do not expose hidden chain-of-thought, full prompts, API keys, or raw
  tracebacks.
- Supervision mode uses a DB-backed timer state and a first-screen local YOLO
  supervision panel. Missing YOLO weights or dependencies degrade to manual
  state recording without breaking the timer.
- Memory diagnostics are audit-only. When no independent vector or graph
  backend is detected, the UI says so explicitly and shows the current
  lightweight retrieval formula instead of claiming FAISS, Chroma, Qdrant, or
  Neo4j is enabled.

## Reliable visual supervision v2

- Study behavior and person presence use separate local YOLO models. A missing
  behavior box is `unknown`, never an automatic `away` result.
- `away` requires 10 continuous seconds without a person detection. Behavior
  states use a 3-second temporal window and phone use takes priority.
- Stable state segments persist duration and detector version. Reports calculate
  numeric metrics deterministically and require at least 80% session and
  classified coverage before making whole-session claims.
- Legacy local-YOLO evidence remains in SQLite as `legacy_unverified` but is
  excluded from new nightly memory and problem-discovery inputs.
- Camera frames and bounding boxes are not persisted.

## Zero-label visual supervision v3

- The SCB pilot behavior detector is no longer a default decision source. It is
  kept only in diagnostics because the classroom dataset does not match the
  local dorm/webcam view well enough.
- The default runtime uses the fixed COCO YOLO weight for `person` and
  `cell phone`. Phone evidence has priority over focused evidence.
- Local face/pose evidence is optional: MediaPipe is used when available, and
  OpenCV face detection is used as a lightweight fallback. No camera frames are
  persisted.
- If face/pose evidence is unavailable or fails on a frame, a high-confidence
  `person` detection with no phone can produce a low-confidence visual-evidence
  `focused` result after temporal smoothing. UI text treats this as evidence
  based "suspected focus", not a claim about mental attention.
- Grounding DINO is not part of the default realtime path because it is too
  heavy for the current supervision loop. It remains a future optional enhancer
  for objects such as book, pen, paper, and phone.
