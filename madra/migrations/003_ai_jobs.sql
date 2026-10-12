BEGIN IMMEDIATE;
CREATE TABLE ai_jobs (
 id TEXT PRIMARY KEY, upload_id TEXT NOT NULL REFERENCES uploads(id),
 user_id TEXT NOT NULL REFERENCES users(id), state TEXT NOT NULL,
 model TEXT NOT NULL, goal TEXT NOT NULL, error TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, finished_at TEXT
);
CREATE UNIQUE INDEX one_generation_per_file ON ai_jobs(upload_id) WHERE state='running';
PRAGMA user_version=3;
COMMIT;
