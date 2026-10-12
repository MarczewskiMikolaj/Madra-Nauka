# Mądra Nauka 2.0

Read docs/PLAN.md for product scope and future roadmap. Active application lives in madra/; app.py creates the Flask application. Code in legacy/ is archival reference, not an active route or storage layer.

Commands:
- `python app.py`: localhost:8080
- `python -m unittest discover -s tests -v`: isolated behavioral tests
- `flask --app app import-legacy --sets PATH --users PATH`: dry-run migration

Use the create_app factory and a temporary DATABASE for tests. Never operate on users.json or sets.json during tests. SQLite connections use explicit transactions. All mutations require CSRF; all entity routes verify ownership. Reviews persist in POST and duplicate item IDs must not duplicate history. Study sessions freeze exercise content and order. User dates use Europe/Warsaw.

Local SQLite uses a persistent disk. Cloud Run uses MADRA_STATE_BUCKET: independent in-memory SQLite snapshots with GCS generation preconditions; never mount SQLite through GCS FUSE. Deploy one worker and one instance. Existing ENCRYPTION_KEY may supply a stable session/encryption secret in cloud mode. Cloud OAuth uses the loopback helper and a fragment-to-CSRF-protected-POST relay. No API key. Old data objects are not migrated or overwritten. PostgreSQL is the upgrade path for larger workloads.
