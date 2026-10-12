BEGIN IMMEDIATE;
ALTER TABLE uploads DROP COLUMN text_content;
UPDATE uploads SET draft_json='{"guide":"","activities":[],"generator":"pending"}'
WHERE imported_at IS NULL AND COALESCE(json_extract(draft_json,'$.generator'),'') != 'ai';
PRAGMA user_version=4;
COMMIT;
