BEGIN IMMEDIATE;
CREATE TABLE uploads (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 workspace_id TEXT REFERENCES workspaces(id), topic_id TEXT REFERENCES topics(id),
 filename TEXT NOT NULL, file_blob BLOB NOT NULL, text_content TEXT NOT NULL,
 draft_json TEXT NOT NULL, created_at TEXT NOT NULL, imported_at TEXT
);
CREATE INDEX upload_owner ON uploads(user_id);
CREATE TABLE upload_materials (
 upload_id TEXT NOT NULL REFERENCES uploads(id), material_id TEXT NOT NULL REFERENCES materials(id),
 PRIMARY KEY(upload_id, material_id)
);
CREATE TABLE upload_activities (
 upload_id TEXT NOT NULL REFERENCES uploads(id), activity_id TEXT NOT NULL REFERENCES activities(id),
 source_label TEXT NOT NULL, PRIMARY KEY(upload_id, activity_id)
);
PRAGMA user_version=2;
COMMIT;
