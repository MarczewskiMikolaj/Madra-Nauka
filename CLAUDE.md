# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run locally (development)
python app.py

# Run with gunicorn (production-like)
gunicorn --bind 0.0.0.0:8080 app:app

# Install dependencies
pip install -r requirements.txt
```

There are no tests in this project.

## Architecture

**Mądra Nauka** is a Polish-language flashcard learning platform (PWA). No database — data stored in JSON files.

### Module structure

```
app.py              # Entry point (~30 lines): creates Flask app, registers blueprints
config.py           # Constants: SECRET_KEY, ENCRYPTION_KEY, VAPID keys, SCHEDULER_SECRET, bucket config
storage.py          # DataStore singleton + load/save for users.json and sets.json
helpers.py          # Shared utilities: login_required, find_user_set, get_valid_cards, compute_streak, etc.
blueprints/
  auth.py           # login, register, logout
  dashboard.py      # index (landing), dashboard (main panel with sets list)
  sets.py           # CRUD: create_set, view_set, edit_set, delete_set (url_prefix=/zestawy)
  learn.py          # Learning mode: learn_set, learn_card, learn_submit, learn_summary (url_prefix=/zestawy)
  test.py           # Test mode: test_set, test_question, test_summary_route (url_prefix=/zestawy)
  profile.py        # User profile with stats, change_password, calendar nav
  notifications.py  # Web Push: vapid-public-key, subscribe, unsubscribe, trigger-daily, send logic
  pwa.py            # manifest, service-worker, favicon, icons, offline
```

### Data access pattern

All data access goes through `storage.store` (a `DataStore` singleton). Routes call:
- `store.reload_sets()` / `store.reload_users()` — reloads from GCS if in cloud mode
- `store.sets` / `store.users` — direct access to in-memory data
- `store.save_and_reload_sets()` / `store.save_and_reload_users()` — persist + re-sync

### Blueprint URL conventions

Templates use fully-qualified endpoint names: `url_for('sets.view_set', set_id=...)`, `url_for('auth.login')`, etc. Three blueprints share the `/zestawy` prefix: `sets`, `learn`, `test`.

### Storage layer

Two modes controlled by `USE_CLOUD_STORAGE` env var:
- **Local (dev, default):** reads/writes `users.json` (Fernet-encrypted) and `sets.json` (plaintext) from disk
- **Cloud (prod):** same files in GCS bucket with optimistic locking (blob generations + exponential backoff retry)

### Key data flows

- **Learning flow:** `learn_set` → `learn_card` or `learn_submit` (bulk JSON) → `learn_summary` (SM-2 stats update)
- **Test flow:** `test_set` → `test_question` → `test_summary_route`
- **Push notifications flow:** browser subscribes via `/push/subscribe` (stores endpoint + VAPID keys + UTC offset in `user['push_subscriptions']`); Google Cloud Scheduler fires `POST /push/trigger-daily` every hour (secured by Bearer token); `send_daily_notifications()` computes 8am local per subscriber using stored `utc_offset`, sends via `pywebpush`

### Card validation

Both `create_set` and `edit_set` require a card to have **both** `tekst` (question) **and** `odpowiedz` (answer) — cards with either field empty are ignored.

### SM-2 light algorithm

Per-card tracking: `streak_rozumiem`, `sessions_ok_streak`, `fail_streak_sessions`, `next_due` (1/6/16 day intervals). A card is "opanowana" (mastered) after 3 consecutive correct sessions OR 5+ exposures at 85%+ success. Mastery is lost only after 2 consecutive failing sessions (tolerance). Cards with 6+ errors and <60% success are flagged as "leech".

Per-set: `next_review_date` schedule — daily (5 days) → every 3 days (3×) → weekly. `days_completed` tracks days when all cards in the set were reviewed.

### Profile page

Two tabs (`?tab=statystyki` / `?tab=konto`):
- **Statystyki:** 6 stat cards, activity calendar with AJAX month navigation (no page reload), yearly GitHub-style heatmap (toggle Miesiąc/Rok, state in localStorage), weekly bar chart, top 3 sets, per-set progress table
- **Konto:** password change form (client-side + server-side validation), push notification toggle

Heatmap uses local date formatting (not `toISOString()`) to avoid UTC timezone offset bugs. Tooltip is a custom div (not `title` attribute) to show immediately on hover.

### Web Push notifications

VAPID keys are hardcoded in `config.py`. Each user's `push_subscriptions` list stores `{endpoint, keys, utc_offset, last_sent_date}`. `utc_offset` from JS `new Date().getTimezoneOffset()` (UTC − local in minutes; negative for UTC+ zones). Target UTC hour = `(8 * 60 + utc_offset) // 60 % 24`. Deduplication: `last_sent_date` checked per subscription before sending. Expired subscriptions (HTTP 404/410 from push service) are removed automatically after each run.

`/push/trigger-daily` is secured by `Authorization: Bearer <SCHEDULER_SECRET>` where `SCHEDULER_SECRET = os.environ.get('SCHEDULER_SECRET', 'change-me-in-production')`.

**No APScheduler** — replaced with Google Cloud Scheduler (job in region `europe-west1`, schedule `0 * * * *`). Cloud Run runs in `europe-west4`.

### Service worker

Cache version is `fiszki-v6`. Bump the version string in `static/service-worker.js` whenever external CSS files change (to bust SW cache). Critical styles that change frequently are kept as inline `<style>` blocks in templates to bypass SW cache.

`self.skipWaiting()` is called unconditionally at the start of the `install` event — not inside the `cache.addAll` promise chain — so the SW always activates even if caching partially fails. `PAGES_TO_CACHE` contains only `/offline`; authenticated pages must not be pre-cached (redirects would cause `cache.addAll` to fail).

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `USE_CLOUD_STORAGE` | `false` | `true` = GCS, `false` = local files |
| `USERS_BUCKET_NAME` | `python-fiszki-users` | GCS bucket name |
| `PORT` | `8080` | Server port |
| `SCHEDULER_SECRET` | `change-me-in-production` | Bearer token for Cloud Scheduler endpoint |

### Known limitations

- `SECRET_KEY`, `ENCRYPTION_KEY`, and VAPID keys are hardcoded in `config.py`
- `DataStore` singleton — each Gunicorn worker has its own in-memory copy; race conditions mitigated by GCS optimistic locking and `last_sent_date` per subscription
- No CSRF protection on forms
- No test suite
