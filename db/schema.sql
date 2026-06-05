CREATE TABLE IF NOT EXISTS chat_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT '新对话',
    summary TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS nightly_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_date TEXT NOT NULL,
    daily_summary TEXT NOT NULL DEFAULT '',
    key_events_json TEXT NOT NULL DEFAULT '[]',
    discovered_problems_json TEXT NOT NULL DEFAULT '[]',
    memory_updates_json TEXT NOT NULL DEFAULT '[]',
    next_actions_json TEXT NOT NULL DEFAULT '[]',
    raw_result_json TEXT NOT NULL DEFAULT '{}',
    raw_response TEXT NOT NULL DEFAULT '',
    parse_status TEXT NOT NULL DEFAULT 'ok',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS problem_board (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (review_id) REFERENCES nightly_reviews(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id INTEGER,
    operation TEXT NOT NULL DEFAULT 'insert',
    memory_type TEXT NOT NULL DEFAULT 'strategy',
    content TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 1,
    confidence REAL NOT NULL DEFAULT 0.0,
    merge_key TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (review_id) REFERENCES nightly_reviews(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS study_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    estimated_minutes INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'todo'
        CHECK (status IN ('todo', 'doing', 'done', 'skipped')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mistake_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    updated_at TEXT NOT NULL
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

CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated_at
ON chat_sessions (updated_at);

CREATE INDEX IF NOT EXISTS idx_conversations_created_at
ON conversations (created_at);

CREATE INDEX IF NOT EXISTS idx_conversations_session_id_created_at
ON conversations (session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_problem_board_status
ON problem_board (status);

CREATE INDEX IF NOT EXISTS idx_memories_memory_type
ON memories (memory_type);

CREATE INDEX IF NOT EXISTS idx_nightly_reviews_review_date
ON nightly_reviews (review_date);

CREATE INDEX IF NOT EXISTS idx_study_tasks_created_at
ON study_tasks (created_at);

CREATE INDEX IF NOT EXISTS idx_study_tasks_status
ON study_tasks (status);

CREATE INDEX IF NOT EXISTS idx_mistake_cards_reason
ON mistake_cards (mistake_reason);

CREATE INDEX IF NOT EXISTS idx_mistake_cards_mastery_status
ON mistake_cards (mastery_status);

CREATE INDEX IF NOT EXISTS idx_checkpoint_records_created_at
ON checkpoint_records (created_at);

CREATE INDEX IF NOT EXISTS idx_daily_signs_created_at
ON daily_signs (created_at);
