from flask import Blueprint, render_template, redirect, url_for, session
from datetime import datetime, timezone, timedelta

from helpers import (
    login_required,
    compute_streak,
    collect_activity_dates,
    build_month_grid,
    compute_next_review_date,
    POLISH_MONTHS,
)
from storage import store

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
def index():
    return render_template('index.html')


@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    # Przeładuj dane z Cloud Storage, aby mieć świeże dane
    store.reload_sets()

    # Pokaż zestawy użytkownika na stronie głównej
    user_sets = [s for s in store.sets if s.get('autor') == session['username']]

    # Wzbogacenie: oblicz procent opanowania (ostrzejsze kryteria)
    enriched_sets = []
    for s in user_sets:
        karty = s.get('karty', []) or []
        total_cards = len(karty)
        mastered = 0

        # Wyczyść błędną datę powtórki dla nowych zestawów bez aktywności
        try:
            if s.get('next_review_date'):
                if not (s.get('days_completed') or []) and not (s.get('historia_nauki') or []):
                    s['next_review_date'] = None
        except Exception as e:
            print(f'Warning: could not clear next_review_date for set {s.get("id", "?")}: {e}')

        if total_cards > 0:
            for karta in karty:
                stats = karta.get('statystyki') or {}
                stats.setdefault('opanowana', False)
                pokazane = stats.get('pokazane', 0)
                procent = stats.get('procent_sukcesu', 0)
                if stats.get('opanowana'):
                    mastered += 1
                elif pokazane >= 5 and procent >= 85:
                    mastered += 1

        # Fallback: wyznacz next_review_date jeśli brak, na podstawie ukończonych dni
        try:
            if not s.get('next_review_date'):
                completed_days = set(s.get('days_completed') or [])
                completed_count = len(completed_days)
                if completed_count > 0:
                    now_date = datetime.now(timezone.utc).date()
                    s['next_review_date'] = compute_next_review_date(
                        completed_count, now_date
                    )
        except Exception as e:
            print(f'Warning: could not compute next_review_date for set {s.get("id", "?")}: {e}')

        mastery_percent = round((mastered / total_cards) * 100) if total_cards > 0 else 0

        if mastery_percent <= 40:
            mastery_class = 'low'
        elif mastery_percent <= 75:
            mastery_class = 'mid'
        else:
            mastery_class = 'high'

        enriched_sets.append({
            **s,
            'mastery_percent': mastery_percent,
            'mastered_count': mastered,
            'total_cards': total_cards,
            'mastery_class': mastery_class,
        })

    # Oblicz codzienny streak (kolejne dni z aktywnością, licząc od dziś)
    activity_dates = collect_activity_dates(user_sets)
    streak, streak_dates = compute_streak(activity_dates)

    # Przygotuj kalendarz bieżącego miesiąca do podglądu (popover)
    month_rows, month_name_pl, year = build_month_grid(activity_dates, streak_dates)

    # Wyznacz zestawy do powtórki dzisiaj
    today_str = datetime.now(timezone.utc).date().isoformat()
    due_today_sets = []
    for s in enriched_sets:
        next_date = s.get('next_review_date')
        is_new = not (s.get('days_completed') or []) and not (s.get('historia_nauki') or [])
        # Dodaj zestawy z datą <= dzisiaj (również przeterminowane) lub nowe zestawy
        if (next_date and next_date <= today_str) or is_new:
            due_today_sets.append(s)

    # Dodaj dzisiejszą datę do wszystkich zestawów dla porównania w szablonie
    for s in enriched_sets:
        s['today_date'] = today_str
    for s in due_today_sets:
        s['today_date'] = today_str

    return render_template(
        'dashboard.html',
        username=session['username'],
        zestawy=enriched_sets,
        due_today_sets=due_today_sets,
        daily_streak=streak,
        month_rows=month_rows,
        month_name=month_name_pl,
        year=year,
    )
