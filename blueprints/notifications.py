import json
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, session
from pywebpush import webpush, WebPushException
from config import VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_CLAIMS, SCHEDULER_SECRET
from helpers import login_required
from storage import store

notifications = Blueprint('notifications', __name__)


@notifications.route('/push/vapid-public-key')
def vapid_public_key():
    return jsonify({'key': VAPID_PUBLIC_KEY})


@notifications.route('/push/subscribe', methods=['POST'])
@login_required
def subscribe():
    store.reload_users()
    data = request.get_json()
    if not data or not data.get('endpoint'):
        return jsonify({'error': 'invalid'}), 400

    username = session['username']
    user = next((u for u in store.users if u.get('login') == username), None)
    if not user:
        return jsonify({'error': 'user not found'}), 404

    subscription = {
        'endpoint': data['endpoint'],
        'keys': data.get('keys') or {},
        'utc_offset': data.get('utc_offset', 0),  # from JS getTimezoneOffset()
        'last_sent_date': None,
    }

    # Replace existing subscription for same endpoint, or append
    subs = user.setdefault('push_subscriptions', [])
    subs = [s for s in subs if s.get('endpoint') != data['endpoint']]
    subs.append(subscription)
    user['push_subscriptions'] = subs
    store.save_and_reload_users()
    return jsonify({'ok': True})


@notifications.route('/push/unsubscribe', methods=['POST'])
@login_required
def unsubscribe():
    store.reload_users()
    data = request.get_json()
    endpoint = data.get('endpoint') if data else None
    username = session['username']
    user = next((u for u in store.users if u.get('login') == username), None)
    if not user or not endpoint:
        return jsonify({'ok': False})
    user['push_subscriptions'] = [
        s for s in user.get('push_subscriptions', [])
        if s.get('endpoint') != endpoint
    ]
    store.save_and_reload_users()
    return jsonify({'ok': True})


def _count_due_sets(username):
    """Count sets due for review today for a given user."""
    today_str = datetime.now(timezone.utc).date().isoformat()
    user_sets = [s for s in store.sets if s.get('autor') == username]
    count = 0
    for s in user_sets:
        next_date = s.get('next_review_date')
        is_new = not (s.get('days_completed') or []) and not (s.get('historia_nauki') or [])
        if (next_date and next_date <= today_str) or is_new:
            count += 1
    return count


@notifications.route('/push/trigger-daily', methods=['POST'])
def trigger_daily():
    """Called by Cloud Scheduler every hour via HTTP POST.
    Secured by a shared secret in the Authorization header.
    Optional query param ?force=1 bypasses hour check (for manual testing)."""
    auth = request.headers.get('Authorization', '')
    if auth != f'Bearer {SCHEDULER_SECRET}':
        return jsonify({'error': 'unauthorized'}), 401
    force = request.args.get('force') == '1'
    result = send_daily_notifications(force=force)
    return jsonify(result)


def send_daily_notifications(force=False):
    """Called every hour (via Cloud Scheduler). Sends push to users whose 8am local just passed.
    If force=True, bypasses hour check (for manual testing)."""
    result = {'ok': True, 'sent': 0, 'skipped_hour': 0, 'skipped_already_sent': 0, 'errors': 0, 'expired': 0}
    try:
        store.reload_sets()
        store.reload_users()
        now_utc = datetime.now(timezone.utc)
        current_utc_hour = now_utc.hour
        today_str = now_utc.date().isoformat()

        changed = False
        for user in store.users:
            subs = user.get('push_subscriptions', [])
            if not subs:
                continue
            username = user.get('login', '')
            for sub in subs:
                # utc_offset from JS getTimezoneOffset(): (UTC - local) in minutes
                # 8am local = 8am - (-utc_offset/60)h UTC = (8*60 + utc_offset) / 60 UTC
                utc_offset = sub.get('utc_offset', 0)
                target_utc_hour = (8 * 60 + utc_offset) // 60 % 24
                if not force and current_utc_hour != target_utc_hour:
                    result['skipped_hour'] += 1
                    continue
                if sub.get('last_sent_date') == today_str:
                    result['skipped_already_sent'] += 1
                    continue

                due_count = _count_due_sets(username)
                if due_count == 0:
                    body = 'Dzisiaj nie masz zestawów do powtórki. Dobra robota! 🎉'
                elif due_count == 1:
                    body = 'Masz 1 zestaw do powtórki dzisiaj!'
                elif due_count < 5:
                    body = f'Masz {due_count} zestawy do powtórki dzisiaj!'
                else:
                    body = f'Masz {due_count} zestawów do powtórki dzisiaj!'

                try:
                    webpush(
                        subscription_info={
                            'endpoint': sub['endpoint'],
                            'keys': sub.get('keys') or {},
                        },
                        data=json.dumps({'title': 'Mądra Nauka 📚', 'body': body}),
                        vapid_private_key=VAPID_PRIVATE_KEY,
                        vapid_claims=VAPID_CLAIMS,
                    )
                    sub['last_sent_date'] = today_str
                    changed = True
                    result['sent'] += 1
                    print(f'Push sent to {username}: {body}')
                except WebPushException as e:
                    result['errors'] += 1
                    if e.response and e.response.status_code in (404, 410):
                        sub['_expired'] = True
                        result['expired'] += 1
                    elif e.response and e.response.status_code == 429:
                        print(f'Push rate-limited for {username}, skipping: {e}')
                        continue
                    print(f'Push error for {username}: {e}')

        # Remove expired subscriptions
        for user in store.users:
            subs_before = user.get('push_subscriptions', [])
            cleaned = [s for s in subs_before if not s.get('_expired')]
            if len(cleaned) != len(subs_before):
                user['push_subscriptions'] = cleaned
                changed = True

        if changed:
            store.save_and_reload_users()
    except Exception as e:
        print(f'send_daily_notifications error: {e}')
        result['ok'] = False
        result['error'] = str(e)
    return result
