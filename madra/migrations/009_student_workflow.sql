BEGIN IMMEDIATE;
CREATE TABLE study_drafts (
 item_id TEXT PRIMARY KEY REFERENCES session_items(id) ON DELETE CASCADE,
 response TEXT NOT NULL DEFAULT '', response_mode TEXT NOT NULL DEFAULT 'text',
 used_help INTEGER NOT NULL DEFAULT 0, flagged INTEGER NOT NULL DEFAULT 0,
 revision INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
);
CREATE TABLE form_drafts (
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 draft_key TEXT NOT NULL, payload_json TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
 updated_at TEXT NOT NULL, PRIMARY KEY(user_id,draft_key)
);
CREATE TABLE daily_preferences (
 user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 budget INTEGER NOT NULL DEFAULT 20 CHECK(budget BETWEEN 5 AND 180)
);
CREATE TABLE content_states (
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 kind TEXT NOT NULL CHECK(kind IN ('workspace','topic','material','upload')),
 content_id TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('archived','trashed')),
 updated_at TEXT NOT NULL, PRIMARY KEY(kind,content_id)
);
CREATE INDEX content_states_owner ON content_states(user_id,status);
CREATE TABLE reading_progress (
 material_id TEXT NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 chapter INTEGER NOT NULL, recalled TEXT NOT NULL DEFAULT '', completed INTEGER NOT NULL DEFAULT 0,
 updated_at TEXT NOT NULL, PRIMARY KEY(material_id,user_id,chapter)
);
CREATE TABLE goal_requirements (
 id TEXT PRIMARY KEY, goal_id TEXT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
 title TEXT NOT NULL, topic_id TEXT REFERENCES topics(id) ON DELETE SET NULL,
 checked INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE image_assets (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 png BLOB NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE activity_images (
 activity_id TEXT PRIMARY KEY REFERENCES activities(id) ON DELETE CASCADE,
 asset_id TEXT NOT NULL REFERENCES image_assets(id)
);
CREATE TABLE exam_options (
 session_id TEXT PRIMARY KEY REFERENCES study_sessions(id) ON DELETE CASCADE,
 manual_finish INTEGER NOT NULL DEFAULT 1, timer_minutes INTEGER NOT NULL DEFAULT 0,
 selection_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE topic_packages (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 payload_json TEXT NOT NULL, workspace_id TEXT REFERENCES workspaces(id),
 imported_topic_id TEXT REFERENCES topics(id), created_at TEXT NOT NULL
);
PRAGMA user_version=9;
COMMIT;
