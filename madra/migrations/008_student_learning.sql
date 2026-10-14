BEGIN IMMEDIATE;
CREATE TABLE activity_support (
 activity_id TEXT PRIMARY KEY REFERENCES activities(id) ON DELETE CASCADE,
 hints_json TEXT NOT NULL DEFAULT '[]', explanation TEXT NOT NULL DEFAULT '',
 rubric TEXT NOT NULL DEFAULT '', material_id TEXT REFERENCES materials(id),
 source_chapter INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE session_settings (
 session_id TEXT PRIMARY KEY REFERENCES study_sessions(id) ON DELETE CASCADE,
 mode TEXT NOT NULL DEFAULT 'regular' CHECK(mode IN ('regular','difficult','exam')),
 scope_json TEXT NOT NULL DEFAULT '{}', paused INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE exam_answers (
 item_id TEXT PRIMARY KEY REFERENCES session_items(id) ON DELETE CASCADE,
 response TEXT NOT NULL, objective_correct INTEGER, submitted_at TEXT NOT NULL
);
CREATE TABLE review_notes (
 review_id TEXT PRIMARY KEY REFERENCES reviews(id) ON DELETE CASCADE,
 used_help INTEGER NOT NULL DEFAULT 0, reason TEXT NOT NULL DEFAULT ''
);
CREATE TABLE goal_settings (
 goal_id TEXT PRIMARY KEY REFERENCES goals(id) ON DELETE CASCADE,
 weekdays_json TEXT NOT NULL DEFAULT '[0,1,2,3,4,5,6]', all_topics INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE goal_topics (
 goal_id TEXT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
 topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
 priority INTEGER NOT NULL DEFAULT 1 CHECK(priority BETWEEN 1 AND 3),
 PRIMARY KEY(goal_id,topic_id)
);
CREATE TABLE activity_imports (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 topic_id TEXT NOT NULL REFERENCES topics(id), payload_json TEXT NOT NULL,
 created_at TEXT NOT NULL, imported_at TEXT
);
PRAGMA user_version=8;
COMMIT;
