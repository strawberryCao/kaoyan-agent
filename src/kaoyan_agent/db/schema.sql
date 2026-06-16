-- 会话输入层：chat 是输入渠道，后续 nightly review 会从这些记录提取证据。
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    exam_year TEXT NOT NULL DEFAULT '',
    target_school TEXT NOT NULL DEFAULT '',
    target_major TEXT NOT NULL DEFAULT '',
    subjects_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    title TEXT NOT NULL DEFAULT '新对话',
    summary TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    session_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);

-- 原始事件层：统一保存聊天、上传、反馈等证据，Problem Discovery 主要读这里。
CREATE TABLE IF NOT EXISTS raw_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    session_id INTEGER,
    subject TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'chat_message',
    source_id INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE SET NULL
);

-- 运行审计层：记录 agent/tool 的输入输出和失败状态，便于复盘模型行为。
CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    session_id INTEGER,
    user_message_id INTEGER,
    user_event_id INTEGER,
    assistant_message_id INTEGER,
    agent_name TEXT NOT NULL,
    workflow_name TEXT NOT NULL DEFAULT '',
    request_json TEXT NOT NULL DEFAULT '{}',
    response_json TEXT NOT NULL DEFAULT '{}',
    raw_response TEXT NOT NULL DEFAULT '',
    parse_status TEXT NOT NULL DEFAULT 'ok',
    error_message TEXT NOT NULL DEFAULT '',
    duration_ms INTEGER NOT NULL DEFAULT 0,
    validation_errors_json TEXT NOT NULL DEFAULT '[]',
    normalization_diagnostics_json TEXT NOT NULL DEFAULT '[]',
    candidate_results_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE SET NULL,
    FOREIGN KEY (user_message_id) REFERENCES conversations(id) ON DELETE SET NULL,
    FOREIGN KEY (user_event_id) REFERENCES raw_events(id) ON DELETE SET NULL,
    FOREIGN KEY (assistant_message_id) REFERENCES conversations(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS agent_trace_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_run_id INTEGER NOT NULL,
    session_id INTEGER,
    user_message_id INTEGER,
    user_event_id INTEGER,
    assistant_message_id INTEGER,
    step_order INTEGER NOT NULL DEFAULT 0,
    step_name TEXT NOT NULL DEFAULT '',
    step_type TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ok',
    input_summary TEXT NOT NULL DEFAULT '',
    output_summary TEXT NOT NULL DEFAULT '',
    decision_summary TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    error_message TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL DEFAULT '',
    duration_ms INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (agent_run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE SET NULL,
    FOREIGN KEY (user_message_id) REFERENCES conversations(id) ON DELETE SET NULL,
    FOREIGN KEY (user_event_id) REFERENCES raw_events(id) ON DELETE SET NULL,
    FOREIGN KEY (assistant_message_id) REFERENCES conversations(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS tool_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT NOT NULL,
    workflow_name TEXT NOT NULL DEFAULT '',
    request_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'ok',
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS online_action_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    session_id INTEGER,
    user_event_id INTEGER,
    action_key TEXT NOT NULL UNIQUE,
    route TEXT NOT NULL DEFAULT '',
    action_type TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    result_json TEXT NOT NULL DEFAULT '{}',
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE SET NULL,
    FOREIGN KEY (user_event_id) REFERENCES raw_events(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS pending_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    session_id INTEGER,
    user_event_id INTEGER,
    assistant_message_id INTEGER,
    pending_key TEXT NOT NULL UNIQUE,
    action_type TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending_confirmation'
        CHECK (status IN ('pending_confirmation', 'confirmed', 'dismissed', 'completed')),
    payload_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    created_target_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE SET NULL,
    FOREIGN KEY (user_event_id) REFERENCES raw_events(id) ON DELETE SET NULL,
    FOREIGN KEY (assistant_message_id) REFERENCES conversations(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS evidence_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    evidence_type TEXT NOT NULL,
    evidence_id INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

-- 夜间复盘层：保存 nightly memory update 的结构化结果和原始模型输出。
CREATE TABLE IF NOT EXISTS nightly_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    review_date TEXT NOT NULL,
    daily_summary TEXT NOT NULL DEFAULT '',
    key_events_json TEXT NOT NULL DEFAULT '[]',
    discovered_problems_json TEXT NOT NULL DEFAULT '[]',
    memory_updates_json TEXT NOT NULL DEFAULT '[]',
    skill_updates_json TEXT NOT NULL DEFAULT '[]',
    next_actions_json TEXT NOT NULL DEFAULT '[]',
    gate_results_json TEXT NOT NULL DEFAULT '[]',
    index_sync_status_json TEXT NOT NULL DEFAULT '{}',
    inserted_counts_json TEXT NOT NULL DEFAULT '{}',
    raw_result_json TEXT NOT NULL DEFAULT '{}',
    raw_response TEXT NOT NULL DEFAULT '',
    parse_status TEXT NOT NULL DEFAULT 'ok',
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);

-- 问题与长期记忆层：Problem Board 追踪可干预问题，memories 保存会影响未来回答的信息。
CREATE TABLE IF NOT EXISTS problem_board (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    review_id INTEGER,
    problem_type TEXT NOT NULL DEFAULT 'other',
    subject TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    root_cause TEXT NOT NULL DEFAULT '',
    severity INTEGER NOT NULL DEFAULT 1,
    confidence REAL NOT NULL DEFAULT 0.0,
    value_score INTEGER NOT NULL DEFAULT 1,
    suggested_action TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    merge_key TEXT NOT NULL DEFAULT '',
    merged_into_problem_id INTEGER,
    embedding_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (review_id) REFERENCES nightly_reviews(id) ON DELETE SET NULL,
    FOREIGN KEY (merged_into_problem_id) REFERENCES problem_board(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    review_id INTEGER,
    operation TEXT NOT NULL DEFAULT 'insert',
    memory_type TEXT NOT NULL DEFAULT 'strategy',
    content TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 1,
    confidence REAL NOT NULL DEFAULT 0.0,
    merge_key TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    valid_from TEXT,
    last_used_at TEXT,
    effectiveness_score REAL NOT NULL DEFAULT 0.0,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    embedding_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (review_id) REFERENCES nightly_reviews(id) ON DELETE SET NULL
);

-- 记忆图和操作记录：保留候选问题/记忆与原始证据之间的追踪关系。
CREATE TABLE IF NOT EXISTS daily_memory_graphs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id INTEGER,
    graph_date TEXT NOT NULL,
    nodes_json TEXT NOT NULL DEFAULT '[]',
    edges_json TEXT NOT NULL DEFAULT '[]',
    summary TEXT NOT NULL DEFAULT '',
    source_event_ids_json TEXT NOT NULL DEFAULT '[]',
    node_count INTEGER NOT NULL DEFAULT 0,
    edge_count INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (review_id) REFERENCES nightly_reviews(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS daily_graph_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daily_graph_id INTEGER NOT NULL,
    node_key TEXT NOT NULL,
    node_type TEXT NOT NULL DEFAULT '',
    ref_type TEXT NOT NULL DEFAULT '',
    ref_id INTEGER,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (daily_graph_id) REFERENCES daily_memory_graphs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS daily_graph_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daily_graph_id INTEGER NOT NULL,
    source_node_key TEXT NOT NULL,
    target_node_key TEXT NOT NULL,
    relation_type TEXT NOT NULL DEFAULT '',
    weight REAL NOT NULL DEFAULT 1.0,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (daily_graph_id) REFERENCES daily_memory_graphs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id INTEGER,
    memory_id INTEGER,
    operation TEXT NOT NULL,
    candidate_json TEXT NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (review_id) REFERENCES nightly_reviews(id) ON DELETE SET NULL,
    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS problem_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id INTEGER,
    problem_id INTEGER,
    operation TEXT NOT NULL,
    candidate_json TEXT NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (review_id) REFERENCES nightly_reviews(id) ON DELETE SET NULL,
    FOREIGN KEY (problem_id) REFERENCES problem_board(id) ON DELETE SET NULL
);

-- 全局/技能记忆预留层：用于后续把长期记忆组织成更通用的节点与技能经验。
CREATE TABLE IF NOT EXISTS global_memory_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_type TEXT NOT NULL,
    ref_type TEXT NOT NULL DEFAULT '',
    ref_id INTEGER,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    embedding_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS global_memory_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_node_id INTEGER NOT NULL,
    target_node_id INTEGER NOT NULL,
    relation_type TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_node_id) REFERENCES global_memory_nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (target_node_id) REFERENCES global_memory_nodes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS global_graph_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_key TEXT NOT NULL UNIQUE,
    node_type TEXT NOT NULL DEFAULT '',
    ref_type TEXT NOT NULL DEFAULT '',
    ref_id INTEGER,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    confidence REAL NOT NULL DEFAULT 0.0,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS global_graph_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    edge_key TEXT NOT NULL UNIQUE,
    source_node_key TEXT NOT NULL,
    target_node_key TEXT NOT NULL,
    relation_type TEXT NOT NULL DEFAULT '',
    weight REAL NOT NULL DEFAULT 1.0,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS graph_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_key TEXT NOT NULL UNIQUE,
    node_type TEXT NOT NULL DEFAULT '',
    ref_type TEXT NOT NULL DEFAULT '',
    ref_id INTEGER,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    embedding_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    edge_key TEXT NOT NULL UNIQUE,
    source_node_key TEXT NOT NULL,
    target_node_key TEXT NOT NULL,
    relation_type TEXT NOT NULL DEFAULT '',
    weight REAL NOT NULL DEFAULT 1.0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id INTEGER,
    skill_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    trigger_json TEXT NOT NULL DEFAULT '{}',
    procedure_json TEXT NOT NULL DEFAULT '{}',
    merge_key TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.0,
    effectiveness_score REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'active',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    embedding_json TEXT NOT NULL DEFAULT '[]',
    last_used_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (review_id) REFERENCES nightly_reviews(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS skill_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id INTEGER,
    skill_id INTEGER,
    operation TEXT NOT NULL,
    candidate_json TEXT NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (review_id) REFERENCES nightly_reviews(id) ON DELETE SET NULL,
    FOREIGN KEY (skill_id) REFERENCES skill_memories(id) ON DELETE SET NULL
);

-- 学习干预层：保存由问题转化出的任务、错题复盘、检查点和动力微行动。
CREATE TABLE IF NOT EXISTS study_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    title TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    estimated_minutes INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    related_problem_id INTEGER,
    scheduled_date TEXT,
    status TEXT NOT NULL DEFAULT 'todo'
        CHECK (status IN ('todo', 'doing', 'done', 'skipped', 'delayed')),
    finished_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (related_problem_id) REFERENCES problem_board(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS practice_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    related_problem_id INTEGER,
    subject TEXT NOT NULL DEFAULT '',
    topic TEXT NOT NULL DEFAULT '',
    question_text TEXT NOT NULL DEFAULT '',
    user_answer TEXT NOT NULL DEFAULT '',
    ai_feedback TEXT NOT NULL DEFAULT '',
    score REAL NOT NULL DEFAULT 0.0,
    is_correct INTEGER NOT NULL DEFAULT 0,
    improved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (related_problem_id) REFERENCES problem_board(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS mistake_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    subject TEXT NOT NULL DEFAULT '',
    chapter TEXT NOT NULL DEFAULT '',
    question TEXT NOT NULL DEFAULT '',
    analysis TEXT NOT NULL DEFAULT '',
    mistake_reason TEXT NOT NULL DEFAULT 'unknown',
    knowledge_points TEXT NOT NULL DEFAULT '',
    review_priority INTEGER NOT NULL DEFAULT 1,
    mastery_status TEXT NOT NULL DEFAULT 'unmastered'
        CHECK (mastery_status IN ('unmastered', 'reviewing', 'mastered')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS checkpoint_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL DEFAULT '',
    chapter TEXT NOT NULL DEFAULT '',
    user_answer TEXT NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0,
    passed INTEGER NOT NULL DEFAULT 0,
    feedback TEXT NOT NULL DEFAULT '',
    weak_points TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_signs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sign_level TEXT NOT NULL DEFAULT '',
    sign_text TEXT NOT NULL DEFAULT '',
    today_advice TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS motivation_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    sign_type TEXT NOT NULL DEFAULT '',
    sign_level TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    suggested_action TEXT NOT NULL DEFAULT '',
    estimated_minutes INTEGER NOT NULL DEFAULT 0,
    can_add_to_task_board INTEGER NOT NULL DEFAULT 1,
    created_task_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (created_task_id) REFERENCES study_tasks(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS score_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    subject TEXT NOT NULL DEFAULT '',
    score REAL NOT NULL DEFAULT 0.0,
    full_score REAL NOT NULL DEFAULT 100.0,
    exam_type TEXT NOT NULL DEFAULT '',
    exam_date TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS score_analysis_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    subject TEXT NOT NULL DEFAULT '',
    report_date TEXT NOT NULL,
    latest_score REAL,
    score_delta REAL,
    risk_level TEXT NOT NULL DEFAULT '',
    ai_suggestion TEXT NOT NULL DEFAULT '',
    raw_result_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);

-- 专注跟踪层：记录番茄钟/督学过程，用于发现拖延、分心和卡住等问题信号。
CREATE TABLE IF NOT EXISTS focus_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    task_id INTEGER,
    task_title TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    planned_minutes INTEGER NOT NULL DEFAULT 0,
    timer_status TEXT NOT NULL DEFAULT 'ended',
    segment_started_at TEXT NOT NULL DEFAULT '',
    accumulated_seconds INTEGER NOT NULL DEFAULT 0,
    actual_seconds INTEGER NOT NULL DEFAULT 0,
    actual_minutes INTEGER NOT NULL DEFAULT 0,
    pause_count INTEGER NOT NULL DEFAULT 0,
    completion_status TEXT NOT NULL DEFAULT 'unknown',
    reflection TEXT NOT NULL DEFAULT '',
    started_at TEXT,
    ended_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (task_id) REFERENCES study_tasks(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS focus_timeline_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    focus_session_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (focus_session_id) REFERENCES focus_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS focus_state_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    focus_session_id INTEGER NOT NULL,
    state_type TEXT NOT NULL CHECK (state_type IN ('focused', 'away', 'distracted', 'blocked', 'unknown')),
    confidence REAL NOT NULL DEFAULT 0.0,
    explanation TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (focus_session_id) REFERENCES focus_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS focus_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    focus_session_id INTEGER NOT NULL,
    effective_focus_minutes INTEGER NOT NULL DEFAULT 0,
    away_count INTEGER NOT NULL DEFAULT 0,
    distracted_count INTEGER NOT NULL DEFAULT 0,
    blocked_count INTEGER NOT NULL DEFAULT 0,
    longest_focus_minutes INTEGER NOT NULL DEFAULT 0,
    focus_quality TEXT NOT NULL DEFAULT '',
    ai_summary TEXT NOT NULL DEFAULT '',
    possible_problem_signal TEXT NOT NULL DEFAULT '',
    suggested_action TEXT NOT NULL DEFAULT '',
    raw_result_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (focus_session_id) REFERENCES focus_sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated_at
ON chat_sessions (updated_at);

CREATE INDEX IF NOT EXISTS idx_projects_status_updated_at
ON projects (status, updated_at);

CREATE INDEX IF NOT EXISTS idx_conversations_created_at
ON conversations (created_at);

CREATE INDEX IF NOT EXISTS idx_conversations_session_id_created_at
ON conversations (session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_raw_events_created_at
ON raw_events (created_at);

CREATE INDEX IF NOT EXISTS idx_raw_events_session_created_at
ON raw_events (session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_raw_events_source
ON raw_events (source_type, source_id);

CREATE INDEX IF NOT EXISTS idx_agent_runs_agent_created_at
ON agent_runs (agent_name, created_at);

CREATE INDEX IF NOT EXISTS idx_tool_runs_tool_created_at
ON tool_runs (tool_name, created_at);

CREATE INDEX IF NOT EXISTS idx_online_action_runs_key
ON online_action_runs (action_key);

CREATE INDEX IF NOT EXISTS idx_online_action_runs_session
ON online_action_runs (session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_evidence_links_target
ON evidence_links (target_type, target_id);

CREATE INDEX IF NOT EXISTS idx_evidence_links_evidence
ON evidence_links (evidence_type, evidence_id);

CREATE INDEX IF NOT EXISTS idx_problem_board_status
ON problem_board (status);

CREATE INDEX IF NOT EXISTS idx_problem_board_review_id
ON problem_board (review_id);

CREATE INDEX IF NOT EXISTS idx_memories_memory_type
ON memories (memory_type);

CREATE INDEX IF NOT EXISTS idx_memories_review_id
ON memories (review_id);

CREATE INDEX IF NOT EXISTS idx_nightly_reviews_review_date
ON nightly_reviews (review_date);

CREATE INDEX IF NOT EXISTS idx_daily_memory_graphs_date
ON daily_memory_graphs (graph_date);

CREATE INDEX IF NOT EXISTS idx_daily_graph_nodes_graph
ON daily_graph_nodes (daily_graph_id, node_type);

CREATE INDEX IF NOT EXISTS idx_daily_graph_nodes_key
ON daily_graph_nodes (node_key);

CREATE INDEX IF NOT EXISTS idx_daily_graph_edges_graph
ON daily_graph_edges (daily_graph_id, relation_type);

CREATE INDEX IF NOT EXISTS idx_daily_graph_edges_source
ON daily_graph_edges (source_node_key);

CREATE INDEX IF NOT EXISTS idx_daily_graph_edges_target
ON daily_graph_edges (target_node_key);

CREATE INDEX IF NOT EXISTS idx_global_memory_nodes_type
ON global_memory_nodes (node_type, status);

CREATE INDEX IF NOT EXISTS idx_global_graph_nodes_key
ON global_graph_nodes (node_key);

CREATE INDEX IF NOT EXISTS idx_global_graph_nodes_type_status
ON global_graph_nodes (node_type, status);

CREATE INDEX IF NOT EXISTS idx_global_graph_edges_source
ON global_graph_edges (source_node_key, relation_type);

CREATE INDEX IF NOT EXISTS idx_global_graph_edges_target
ON global_graph_edges (target_node_key, relation_type);

CREATE INDEX IF NOT EXISTS idx_skill_memories_status
ON skill_memories (status, updated_at);

CREATE INDEX IF NOT EXISTS idx_skill_operations_review_id
ON skill_operations (review_id);

CREATE INDEX IF NOT EXISTS idx_study_tasks_created_at
ON study_tasks (created_at);

CREATE INDEX IF NOT EXISTS idx_study_tasks_status
ON study_tasks (status);

CREATE INDEX IF NOT EXISTS idx_practice_reviews_problem
ON practice_reviews (related_problem_id);

CREATE INDEX IF NOT EXISTS idx_mistake_cards_reason
ON mistake_cards (mistake_reason);

CREATE INDEX IF NOT EXISTS idx_mistake_cards_mastery_status
ON mistake_cards (mastery_status);

CREATE INDEX IF NOT EXISTS idx_checkpoint_records_created_at
ON checkpoint_records (created_at);

CREATE INDEX IF NOT EXISTS idx_daily_signs_created_at
ON daily_signs (created_at);

CREATE INDEX IF NOT EXISTS idx_motivation_items_created_at
ON motivation_items (created_at);

CREATE INDEX IF NOT EXISTS idx_score_records_subject_date
ON score_records (subject, exam_date);

CREATE INDEX IF NOT EXISTS idx_focus_sessions_task
ON focus_sessions (task_id);

CREATE INDEX IF NOT EXISTS idx_focus_sessions_started_at
ON focus_sessions (started_at);


CREATE INDEX IF NOT EXISTS idx_focus_state_events_session
ON focus_state_events (focus_session_id, created_at);
