import json
import copy
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


@notifications.route('/push/debug-subs', methods=['POST'])
def debug_subs():
    """Show stored subscriptions (endpoint prefix + keys presence). Secured by Bearer token."""
    auth = request.headers.get('Authorization', '')
    if auth != f'Bearer {SCHEDULER_SECRET}':
        return jsonify({'error': 'unauthorized'}), 401
    store.reload_users()
    info = []
    for user in store.users:
        subs = user.get('push_subscriptions', [])
        if not subs:
            continue
        username = user.get('login', '')
        for sub in subs:
            keys = sub.get('keys') or {}
            info.append({
                'user': username,
                'endpoint_prefix': sub.get('endpoint', '')[:80],
                'has_p256dh': bool(keys.get('p256dh')),
                'has_auth': bool(keys.get('auth')),
                'last_sent_date': sub.get('last_sent_date'),
            })
    return jsonify({'subscriptions': info, 'count': len(info)})


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
    """Called once daily by Cloud Scheduler. Sends push to all subscribers.
    Deduplication via last_sent_date prevents double sends.
    If force=True, bypasses last_sent_date check."""
    result = {'ok': True, 'sent': 0, 'skipped_already_sent': 0, 'errors': 0, 'expired': 0}
    try:
        store.reload_sets()
        store.reload_users()
        today_str = datetime.now(timezone.utc).date().isoformat()

        changed = False
        for user in store.users:
            subs = user.get('push_subscriptions', [])
            if not subs:
                continue
            username = user.get('login', '')
            for sub in subs:
                if not force and sub.get('last_sent_date') == today_str:
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
                    endpoint = sub['endpoint']
                    keys = sub.get('keys') or {}
                    if not keys.get('p256dh') or not keys.get('auth'):
                        print(f'Push skip {username}: missing keys p256dh/auth, endpoint={endpoint[:80]}')
                        sub['_expired'] = True
                        result['errors'] += 1
                        result['expired'] += 1
                        continue

                    # Deep copy claims so pywebpush doesn't mutate the shared dict
                    claims = copy.deepcopy(VAPID_CLAIMS)

                    webpush(
                        subscription_info={
                            'endpoint': endpoint,
                            'keys': keys,
                        },
                        data=json.dumps({'title': 'Czas na powtórkę! 📚', 'body': body}),
                        vapid_private_key=VAPID_PRIVATE_KEY,
                        vapid_claims=claims,
                        content_encoding='aes128gcm',
                    )
                    sub['last_sent_date'] = today_str
                    changed = True
                    result['sent'] += 1
                    print(f'Push sent to {username} endpoint={endpoint[:80]}')
                except WebPushException as e:
                    result['errors'] += 1
                    status_code = e.response.status_code if e.response else None
                    resp_body = ''
                    try:
                        resp_body = e.response.text[:500] if e.response else ''
                    except Exception:
                        pass
                    print(f'Push error for {username}: status={status_code} body={resp_body} endpoint={sub.get("endpoint", "")[:80]}')
                    if status_code in (400, 401, 403, 404, 410):
                        sub['_expired'] = True
                        result['expired'] += 1
                    elif status_code == 429:
                        print(f'Push rate-limited for {username}, skipping')
                        continue

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
