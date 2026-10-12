BEGIN IMMEDIATE;
ALTER TABLE ai_jobs ADD COLUMN progress_json TEXT NOT NULL DEFAULT '{"stage":"queued","output_chars":0}';
PRAGMA user_version=5;
COMMIT;
