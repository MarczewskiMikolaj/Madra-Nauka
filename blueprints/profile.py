import calendar as _calendar
from flask import Blueprint, render_template, redirect, url_for, session, request, flash
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import (
    login_required,
    compute_streak,
    POLISH_MONTHS,
)
from storage import store

profile_bp = Blueprint('profile', __name__)


@profile_bp.route('/profil')
@login_required
def profile():
    # Przeładuj dane z Cloud Storage
    store.reload_sets()

    username = session['username']
    user_sets = [s for s in store.sets if s.get('autor') == username]

    tab = request.args.get('tab', 'statystyki')

    # Oblicz statystyki
    total_sets = len(user_sets)

    # Oblicz wszystkie statystyki w jednej pętli
    today = datetime.now(timezone.utc).date().isoformat()
    total_cards = 0
    mastered_cards = 0
    leech_cards = 0
    lifetime_sessions = 0
    sets_solved_today = 0
    weekly_stats = defaultdict(int)
    set_solve_counts = defaultdict(int)
    activity_dates = set()
    learn_counts_by_date = defaultdict(int)
    daily_set_counts = defaultdict(lambda: defaultdict(int))
    set_stats = []

    for s in user_sets:
        sid = s['id']
        nazwa = s.get('nazwa', '')
        karty = s.get('karty', [])
        historia_nauki = s.get('historia_nauki', []) or []

        # Karty
        total_c = 0
        mastered_c = 0
        leech_c = 0
        for k in karty:
            total_c += 1
            stats_k = k.get('statystyki', {})
            if stats_k.get('opanowana') == True:
                mastered_c += 1
            if stats_k.get('leech') == True:
                leech_c += 1
        total_cards += total_c
        mastered_cards += mastered_c
        leech_cards += leech_c

        # Historia nauki
        total_sess = len(historia_nauki)
        lifetime_sessions += total_sess
        last_sess = None
        for wpis in historia_nauki:
            data = wpis.get('data')
            if data:
                if data == today:
                    sets_solved_today += 1
                weekly_stats[data] += 1
                set_solve_counts[sid] += 1
                activity_dates.add(data)
                learn_counts_by_date[data] += 1
                daily_set_counts[data][nazwa] += 1
                if last_sess is None or data > last_sess:
                    last_sess = data

        # Historia testów (tylko dla activity_dates)
        for wpis in s.get('historia_testow', []) or []:
            data = wpis.get('data')
            if data:
                activity_dates.add(data)

        mastered_pct = round(mastered_c * 100 / total_c) if total_c > 0 else 0
        set_stats.append({
            'id': sid,
            'nazwa': nazwa,
            'total_cards': total_c,
            'mastered_cards': mastered_c,
            'mastered_pct': mastered_pct,
            'leech_cards': leech_c,
            'total_sessions': total_sess,
            'last_session': last_sess,
        })

    set_stats.sort(key=lambda x: x['last_session'] or '', reverse=True)

    yearly_activity = dict(learn_counts_by_date)
    yearly_activity_sets = {
        date: sorted(sets.items(), key=lambda x: -x[1])
        for date, sets in daily_set_counts.items()
    }

    # Przygotuj dane dla wykresu tygodniowego (ostatnie 7 dni) - liczba sesji nauki
    chart_data = []
    polish_days = ['Pon', 'Wt', 'Śr', 'Czw', 'Pt', 'Sob', 'Niedz']
    for i in range(6, -1, -1):
        day_date = datetime.now(timezone.utc).date() - timedelta(days=i)
        day = day_date.isoformat()
        count = weekly_stats.get(day, 0)
        day_weekday = day_date.weekday()
        day_name = polish_days[day_weekday]
        chart_data.append({'day': day_name, 'count': count, 'date': day})

    # Top 3 najczęściej rozwiązywanych zestawów
    sorted_sets = sorted(set_solve_counts.items(), key=lambda x: x[1], reverse=True)
    top_sets = []
    for set_id, count in sorted_sets[:3]:
        zestaw = next((s for s in user_sets if s['id'] == set_id), None)
        if zestaw is not None:
            top_sets.append({'zestaw': zestaw, 'count': count})

    # Oblicz streak (ciąg kolejnych dni z aktywnością: nauka lub test)
    daily_streak, streak_dates = compute_streak(activity_dates)

    # Nawigacja po miesiącach kalendarza
    today_date = datetime.now(timezone.utc).date()
    current_year, current_month = today_date.year, today_date.month

    raw_month = request.args.get('month', '')
    view_year, view_month = current_year, current_month
    if raw_month:
        try:
            parsed = datetime.strptime(raw_month, '%Y-%m')
            view_year, view_month = parsed.year, parsed.month
        except ValueError:
            pass
    # Ogranicz do bieżącego miesiąca (nie można przeglądać przyszłości)
    if (view_year, view_month) > (current_year, current_month):
        view_year, view_month = current_year, current_month

    viewing_current_month = (view_year == current_year and view_month == current_month)

    # prev_month
    prev_year, prev_month_num = (view_year, view_month - 1) if view_month > 1 else (view_year - 1, 12)
    prev_month = {
        'year': prev_year,
        'month': prev_month_num,
        'label': POLISH_MONTHS[prev_month_num - 1],
    }

    # next_month — None jeśli jesteśmy na bieżącym miesiącu
    if viewing_current_month:
        next_month = None
    else:
        next_year, next_month_num = (view_year, view_month + 1) if view_month < 12 else (view_year + 1, 1)
        next_month = {
            'year': next_year,
            'month': next_month_num,
            'label': POLISH_MONTHS[next_month_num - 1],
        }

    # Przygotuj pełny kalendarz aktywności dla wybranego miesiąca (siatka tygodni)
    start_weekday, days_in_month = _calendar.monthrange(view_year, view_month)  # Monday=0

    month_grid = []
    for _ in range(start_weekday):
        month_grid.append(None)
    for d in range(1, days_in_month + 1):
        date_obj = today_date.replace(year=view_year, month=view_month, day=d)
        date_str = date_obj.isoformat()
        month_grid.append({
            'day': d,
            'date': date_str,
            'active': date_str in activity_dates,
            'streak': date_str in streak_dates,
            'count': int(learn_counts_by_date.get(date_str, 0)),
        })
    while len(month_grid) % 7 != 0:
        month_grid.append(None)

    month_rows = [month_grid[i:i + 7] for i in range(0, len(month_grid), 7)]
    month_name_pl = POLISH_MONTHS[view_month - 1]

    return render_template(
        'profile.html',
        username=username,
        total_sets=total_sets,
        total_cards=total_cards,
        mastered_cards=mastered_cards,
        leech_cards=leech_cards,
        lifetime_sessions=lifetime_sessions,
        sets_solved_today=sets_solved_today,
        chart_data=chart_data,
        top_sets=top_sets,
        set_stats=set_stats,
        yearly_activity=yearly_activity,
        yearly_activity_sets=yearly_activity_sets,
        daily_streak=daily_streak,
        month_rows=month_rows,
        month_name=month_name_pl,
        year=view_year,
        prev_month=prev_month,
        next_month=next_month,
        viewing_current_month=viewing_current_month,
        tab=tab,
    )


@profile_bp.route('/profil/zmien-haslo', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    store.reload_users()
    user = next((u for u in store.users if u.get('login') == session['username']), None)

    if user is None:
        flash('Nie znaleziono użytkownika.', 'error')
        return redirect(url_for('profile.profile', tab='konto'))

    if not check_password_hash(user.get('haslo', ''), current_password):
        flash('Aktualne hasło jest nieprawidłowe.', 'error')
        return redirect(url_for('profile.profile', tab='konto'))

    if new_password != confirm_password:
        flash('Nowe hasła nie są zgodne.', 'error')
        return redirect(url_for('profile.profile', tab='konto'))

    if len(new_password) < 6:
        flash('Nowe hasło musi mieć co najmniej 6 znaków.', 'error')
        return redirect(url_for('profile.profile', tab='konto'))

    user['haslo'] = generate_password_hash(new_password)
    store.save_and_reload_users()
    flash('Hasło zostało zmienione.', 'success')
    return redirect(url_for('profile.profile', tab='konto'))
