from functools import wraps
from datetime import datetime, timezone, timedelta
from flask import session, redirect, url_for, flash


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POLISH_MONTHS = [
    'Styczeń', 'Luty', 'Marzec', 'Kwiecień', 'Maj', 'Czerwiec',
    'Lipiec', 'Sierpień', 'Wrzesień', 'Październik', 'Listopad', 'Grudzień'
]


# ---------------------------------------------------------------------------
# 1. login_required decorator
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# 2. find_user_set – find set by ID and verify ownership
# ---------------------------------------------------------------------------

def find_user_set(store, set_id):
    """Return (zestaw, None) on success or (None, redirect_response) on failure."""
    zestaw = next((s for s in store.sets if s.get('id') == set_id), None)
    if not zestaw:
        flash('Zestaw nie został znaleziony.', 'error')
        return None, redirect(url_for('dashboard.dashboard'))
    if zestaw.get('autor') != session['username']:
        flash('Nie masz dostępu do tego zestawu.', 'error')
        return None, redirect(url_for('dashboard.dashboard'))
    return zestaw, None


# ---------------------------------------------------------------------------
# 3. make_default_stats – 13-key default card statistics dict
# ---------------------------------------------------------------------------

def make_default_stats():
    return {
        'pokazane': 0,
        'rozumiem': 0,
        'nie_rozumiem': 0,
        'procent_sukcesu': 0,
        'streak_rozumiem': 0,
        'streak_nie_rozumiem': 0,
        'opanowana': False,
        'sessions_ok_streak': 0,
        'fail_streak_sessions': 0,
        'last_seen_date': None,
        'total_sessions_ok': 0,
        'next_due': None,
        'leech': False
    }


# ---------------------------------------------------------------------------
# 4. ensure_card_stats – fill missing stats keys with defaults
# ---------------------------------------------------------------------------

def ensure_card_stats(karta):
    stats = karta.setdefault('statystyki', {})
    for key, default in make_default_stats().items():
        stats.setdefault(key, default)
    return stats


# ---------------------------------------------------------------------------
# 5. compute_next_review_date – review date scheduling
# ---------------------------------------------------------------------------

def compute_next_review_date(completed_count, base_date):
    """Return an ISO-format date string for the next set-level review.

    Schedule:
      - first 5 completions  -> +1 day
      - completions 5-7      -> +3 days
      - 8+                   -> +7 days
    """
    if completed_count < 5:
        return (base_date + timedelta(days=1)).isoformat()
    elif completed_count < 8:
        return (base_date + timedelta(days=3)).isoformat()
    else:
        return (base_date + timedelta(days=7)).isoformat()


# ---------------------------------------------------------------------------
# 6. compute_streak – consecutive-day activity streak
# ---------------------------------------------------------------------------

def compute_streak(activity_dates):
    """Return (streak_count, streak_dates_set) from a set of ISO date strings."""
    today = datetime.now(timezone.utc).date()
    day = today if today.isoformat() in activity_dates else today - timedelta(days=1)
    streak = 0
    streak_dates = set()
    while day.isoformat() in activity_dates:
        streak += 1
        streak_dates.add(day.isoformat())
        day -= timedelta(days=1)
    return streak, streak_dates


# ---------------------------------------------------------------------------
# 7. collect_activity_dates – unique activity dates across all user sets
# ---------------------------------------------------------------------------

def collect_activity_dates(user_sets):
    """Gather unique ISO date strings from all sets' learning and test history."""
    activity_dates = set()
    for zestaw in user_sets:
        for wpis in zestaw.get('historia_nauki', []) or []:
            data = wpis.get('data')
            if data:
                activity_dates.add(data)
        for wpis in zestaw.get('historia_testow', []) or []:
            data = wpis.get('data')
            if data:
                activity_dates.add(data)
    return activity_dates


# ---------------------------------------------------------------------------
# 8. build_month_grid – calendar grid for the current month
# ---------------------------------------------------------------------------

def build_month_grid(activity_dates, streak_dates):
    """Build a month calendar grid for the current month.

    Returns (month_rows, month_name_pl, year) where *month_rows* is a list of
    7-element rows suitable for rendering, *month_name_pl* is the Polish name
    of the current month, and *year* is the numeric year.
    """
    import calendar as _calendar

    today_date = datetime.now(timezone.utc).date()
    year, month = today_date.year, today_date.month
    start_weekday, days_in_month = _calendar.monthrange(year, month)  # Monday=0

    # Build the flat grid with leading None padding
    month_grid = []
    for _ in range(start_weekday):
        month_grid.append(None)
    for d in range(1, days_in_month + 1):
        date_obj = today_date.replace(day=d)
        date_str = date_obj.isoformat()
        month_grid.append({
            'day': d,
            'date': date_str,
            'active': date_str in activity_dates,
            'streak': date_str in streak_dates
        })
    # Trailing None padding to fill the last week row
    while len(month_grid) % 7 != 0:
        month_grid.append(None)

    month_rows = [month_grid[i:i + 7] for i in range(0, len(month_grid), 7)]
    month_name_pl = POLISH_MONTHS[month - 1]
    return month_rows, month_name_pl, year


# ---------------------------------------------------------------------------
# 10. get_valid_cards – cards with non-empty tekst and odpowiedz
# ---------------------------------------------------------------------------

def get_valid_cards(zestaw):
    return [
        k for k in zestaw.get('karty', [])
        if k.get('tekst', '').strip() and k.get('odpowiedz', '').strip()
    ]
