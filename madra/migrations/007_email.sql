BEGIN IMMEDIATE;
CREATE TABLE user_emails (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE
);
CREATE INDEX topics_workspace ON topics(workspace_id);
CREATE INDEX activities_topic ON activities(topic_id,archived);
CREATE INDEX materials_topic ON materials(topic_id);
CREATE INDEX sessions_owner ON study_sessions(user_id,status,created_at);
PRAGMA user_version=7;
COMMIT;
