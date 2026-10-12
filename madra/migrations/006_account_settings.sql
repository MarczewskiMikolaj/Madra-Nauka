BEGIN IMMEDIATE;
CREATE TABLE user_profiles (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    avatar_png BLOB,
    session_version INTEGER NOT NULL DEFAULT 0
);
PRAGMA user_version=6;
COMMIT;
