import csv
import io
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime, timezone
from uuid import uuid4
from storage import store
from helpers import login_required, find_user_set, make_default_stats, ensure_card_stats, compute_next_review_date

sets = Blueprint('sets', __name__)


@sets.route('/')
def zestawy():
    # Utrzymujemy jedno źródło prawdy dla listy zestawów – przekierowujemy do dashboardu,
    # który oblicza opanowanie i pozostałe dane widoku.
    return redirect(url_for('dashboard.dashboard'))


@sets.route('/nowy', methods=['GET', 'POST'])
@login_required
def create_set():
    if request.method == 'POST':
        nazwa = request.form.get('nazwa', '').strip()

        # Sprawdź czy jest plik CSV
        csv_file = request.files.get('csv_file')
        karty = []

        if csv_file and csv_file.filename.endswith('.csv'):
            # Import z CSV
            try:
                # Odczytaj plik CSV
                stream = io.StringIO(csv_file.stream.read().decode("UTF-8"), newline=None)
                csv_reader = csv.reader(stream)

                for row in csv_reader:
                    if len(row) >= 2:
                        pytanie = row[0].strip()
                        odpowiedz = row[1].strip()
                        if pytanie or odpowiedz:
                            karty.append({
                                'tekst': pytanie,
                                'odpowiedz': odpowiedz,
                                'statystyki': make_default_stats()
                            })

                if not karty:
                    flash('Plik CSV jest pusty lub nieprawidłowy.', 'error')
                    return render_template('create_set.html', username=session['username'])

            except Exception as e:
                flash(f'Błąd podczas importu CSV: {str(e)}', 'error')
                return render_template('create_set.html', username=session['username'])
        else:
            # Standardowe dodawanie
            teksty = request.form.getlist('tekst[]')
            odpowiedzi = request.form.getlist('odpowiedz[]')

            # Zbuduj listę kart, ignorując puste pary
            for i in range(max(len(teksty), len(odpowiedzi))):
                t = (teksty[i].strip() if i < len(teksty) and teksty[i] is not None else '')
                o = (odpowiedzi[i].strip() if i < len(odpowiedzi) and odpowiedzi[i] is not None else '')
                if t and o:
                    karty.append({
                        'tekst': t,
                        'odpowiedz': o,
                        'statystyki': make_default_stats()
                    })

        if not nazwa:
            flash('Podaj nazwę zestawu.', 'error')
            return render_template('create_set.html', username=session['username'])

        if not karty:
            flash('Dodaj przynajmniej jedną fiszkę (tekst i odpowiedź) lub zaimportuj plik CSV.', 'error')
            return render_template('create_set.html', username=session['username'])

        new_set = {
            'id': uuid4().hex,
            'autor': session['username'],
            'nazwa': nazwa,
            'data_utworzenia': datetime.now(timezone.utc).isoformat(),
            'karty': karty
        }

        store.sets.append(new_set)
        store.save_and_reload_sets()
        flash('Zestaw został utworzony!', 'success')
        return redirect(url_for('sets.zestawy'))

    return render_template('create_set.html', username=session['username'])


@sets.route('/<set_id>')
@login_required
def view_set(set_id):
    # Przeładuj dane z Cloud Storage
    store.reload_sets()

    # Znajdź zestaw i zweryfikuj dostęp
    zestaw, err = find_user_set(store, set_id)
    if err:
        return err

    # Wyczyść błędną datę powtórki dla nowych zestawów bez aktywności
    try:
        if zestaw.get('next_review_date'):
            if not (zestaw.get('days_completed') or []) and not (zestaw.get('historia_nauki') or []):
                zestaw['next_review_date'] = None
    except Exception:
        pass

    # Fallback: wyznacz next_review_date jeśli brak, na podstawie ukończonych dni (days_completed)
    try:
        if not zestaw.get('next_review_date'):
            completed_days = set(zestaw.get('days_completed') or [])
            completed_count = len(completed_days)
            if completed_count > 0:
                now_date = datetime.now(timezone.utc).date()
                zestaw['next_review_date'] = compute_next_review_date(completed_count, now_date)
    except Exception:
        pass

    # Uzupełnij brakujące statystyki i Top 5 najtrudniejszych fiszek (najniższy procent sukcesu, tylko karty z historią)
    for karta in zestaw.get('karty', []) or []:
        ensure_card_stats(karta)

    top_difficult_cards = []
    for idx, karta in enumerate(zestaw.get('karty', []), start=1):
        stats = karta.get('statystyki') or {}
        shown = stats.get('pokazane', 0)
        success = stats.get('procent_sukcesu', 0)
        opanowana = stats.get('opanowana', False)

        # Pokazuj tylko fiszki, które:
        # - były pokazane co najmniej 3 razy
        # - mają sukces < 40% (trudne)
        # - NIE są opanowane
        if shown >= 3 and success < 40 and not opanowana:
            top_difficult_cards.append({
                'index': idx,
                'tekst': karta.get('tekst', ''),
                'odpowiedz': karta.get('odpowiedz', ''),
                'pokazane': shown,
                'procent_sukcesu': success
            })

    # Sortuj: najpierw najniższy procent, potem najwięcej pokazanych (najbardziej problematyczne)
    top_difficult_cards = sorted(top_difficult_cards, key=lambda c: (c['procent_sukcesu'], -c['pokazane']))[:6]

    return render_template(
        'view_set.html',
        username=session['username'],
        zestaw=zestaw,
        top_difficult_cards=top_difficult_cards
    )


@sets.route('/<set_id>/edytuj', methods=['GET', 'POST'])
@login_required
def edit_set(set_id):
    # Przeładuj dane z Cloud Storage
    store.reload_sets()

    # Znajdź zestaw i zweryfikuj dostęp
    zestaw, err = find_user_set(store, set_id)
    if err:
        return err

    if request.method == 'POST':
        nazwa = request.form.get('nazwa', '').strip()
        teksty = request.form.getlist('tekst[]')
        odpowiedzi = request.form.getlist('odpowiedz[]')

        # Zbuduj listę kart - zachowaj istniejące statystyki jeśli są
        karty = []
        stare_karty = zestaw.get('karty', [])

        # Buduj lookup po treści karty (tekst, odpowiedz) -> statystyki
        stare_stats_lookup = {}
        for karta in stare_karty:
            key = (karta.get('tekst', ''), karta.get('odpowiedz', ''))
            if key not in stare_stats_lookup:  # first occurrence wins
                stare_stats_lookup[key] = karta.get('statystyki')

        for i in range(max(len(teksty), len(odpowiedzi))):
            t = (teksty[i].strip() if i < len(teksty) and teksty[i] is not None else '')
            o = (odpowiedzi[i].strip() if i < len(odpowiedzi) and odpowiedzi[i] is not None else '')
            if t and o:
                # Zachowaj statystyki jeśli karta istniała (niezależnie od pozycji)
                key = (t, o)
                old_stats = stare_stats_lookup.get(key)

                # Uzupełnij brakujące pola w starych statystykach
                if not old_stats:
                    old_stats = make_default_stats()
                else:
                    old_stats.setdefault('streak_rozumiem', 0)
                    old_stats.setdefault('streak_nie_rozumiem', 0)
                    old_stats.setdefault('opanowana', False)
                    old_stats.setdefault('sessions_ok_streak', 0)
                    old_stats.setdefault('fail_streak_sessions', 0)
                    old_stats.setdefault('last_seen_date', None)
                    old_stats.setdefault('total_sessions_ok', 0)
                    old_stats.setdefault('next_due', None)
                    old_stats.setdefault('leech', False)
                karty.append({
                    'tekst': t,
                    'odpowiedz': o,
                    'statystyki': old_stats
                })

        if not nazwa:
            flash('Podaj nazwę zestawu.', 'error')
            return render_template('edit_set.html', username=session['username'], zestaw=zestaw)

        if not karty:
            flash('Dodaj przynajmniej jedną fiszkę.', 'error')
            return render_template('edit_set.html', username=session['username'], zestaw=zestaw)

        # Aktualizuj zestaw
        zestaw['nazwa'] = nazwa
        zestaw['karty'] = karty
        store.save_and_reload_sets()
        flash('Zestaw został zaktualizowany!', 'success')
        return redirect(url_for('sets.view_set', set_id=set_id))

    return render_template('edit_set.html', username=session['username'], zestaw=zestaw)


@sets.route('/<set_id>/usun', methods=['POST'])
@login_required
def delete_set(set_id):
    # Przeładuj dane z Cloud Storage
    store.reload_sets()

    # Znajdź zestaw
    zestaw = next((s for s in store.sets if s.get('id') == set_id), None)
    if not zestaw:
        flash('Zestaw nie został znaleziony.', 'error')
        return redirect(url_for('dashboard.dashboard'))

    # Sprawdź czy użytkownik jest autorem
    if zestaw.get('autor') != session['username']:
        flash('Nie masz dostępu do tego zestawu.', 'error')
        return redirect(url_for('dashboard.dashboard'))

    # Usuń zestaw z listy
    store.sets.remove(zestaw)
    store.save_and_reload_sets()

    flash(f'Zestaw "{zestaw["nazwa"]}" został usunięty.', 'success')
    return redirect(url_for('dashboard.dashboard'))
