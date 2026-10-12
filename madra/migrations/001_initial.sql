BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY, username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT 'blue',
    created_at TEXT NOT NULL, legacy_key TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS workspace_owner ON workspaces(user_id);
CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY, topic_id TEXT NOT NULL REFERENCES topics(id),
    kind TEXT NOT NULL CHECK(kind IN ('note','link')), title TEXT NOT NULL,
    content TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activities (
    id TEXT PRIMARY KEY, topic_id TEXT NOT NULL REFERENCES topics(id),
    kind TEXT NOT NULL CHECK(kind IN ('flashcard','open','quiz','exercise','cloze')),
    dimension TEXT NOT NULL CHECK(dimension IN ('memory','understanding','application')),
    prompt TEXT NOT NULL, answer TEXT NOT NULL, options_json TEXT NOT NULL DEFAULT '[]',
    minutes INTEGER NOT NULL CHECK(minutes BETWEEN 1 AND 15), archived INTEGER NOT NULL DEFAULT 0,
    legacy_stats_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS progress (
    user_id TEXT NOT NULL REFERENCES users(id), activity_id TEXT NOT NULL REFERENCES activities(id),
    reviews INTEGER NOT NULL DEFAULT 0, successes INTEGER NOT NULL DEFAULT 0, last_grade INTEGER,
    interval_days INTEGER NOT NULL DEFAULT 0, due_date TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY(user_id,activity_id)
);
CREATE TABLE IF NOT EXISTS study_sessions (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), title TEXT NOT NULL,
    budget_minutes INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'active'
    CHECK(status IN ('active','completed','ended')), created_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS session_items (
    id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES study_sessions(id),
    activity_id TEXT NOT NULL REFERENCES activities(id), position INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL, response TEXT, revealed INTEGER NOT NULL DEFAULT 0,
    objective_correct INTEGER, UNIQUE(session_id,position)
);
CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY, item_id TEXT NOT NULL UNIQUE REFERENCES session_items(id),
    user_id TEXT NOT NULL REFERENCES users(id), activity_id TEXT NOT NULL REFERENCES activities(id),
    grade INTEGER NOT NULL CHECK(grade BETWEEN 0 AND 3), response TEXT NOT NULL DEFAULT '',
    objective_correct INTEGER, previous_progress_json TEXT, created_at TEXT NOT NULL, corrected_at TEXT
);
CREATE INDEX IF NOT EXISTS review_history ON reviews(user_id,created_at);
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id), title TEXT NOT NULL, target_date TEXT NOT NULL,
    daily_minutes INTEGER NOT NULL CHECK(daily_minutes BETWEEN 5 AND 180),
    completed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS login_attempts (
    key TEXT PRIMARY KEY, count INTEGER NOT NULL, first_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS legacy_payloads (
    workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id), payload_json TEXT NOT NULL, imported_at TEXT NOT NULL
);
PRAGMA user_version=1;
COMMIT;
