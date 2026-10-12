# Mądra Nauka 2.0

Read docs/PLAN.md for product scope and future roadmap. Active application lives in madra/; app.py creates the Flask application. Code in legacy/ is archival reference, not an active route or storage layer.

Commands:
- `python app.py`: localhost:8080
- `python -m unittest discover -s tests -v`: isolated behavioral tests
- `flask --app app import-legacy --sets PATH --users PATH`: dry-run migration

Use the create_app factory and a temporary DATABASE for tests. Never operate on users.json or sets.json during tests. SQLite connections use explicit transactions. All mutations require CSRF; all entity routes verify ownership. Reviews persist in POST and duplicate item IDs must not duplicate history. Study sessions freeze exercise content and order. User dates use Europe/Warsaw.

Production SQLite requires a persistent volume and one application instance. Multi-instance deployment is a separate PostgreSQL migration. Do not silently deploy to the old Cloud Run configuration.
