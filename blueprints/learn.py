import random
import time
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime, timezone, timedelta
from storage import store
from helpers import login_required, find_user_set, compute_next_review_date

learn = Blueprint('learn', __name__, url_prefix='/zestawy')


@learn.route('/<set_id>/ucz-sie')
@login_required
def learn_set(set_id):
    store.reload_sets()

    zestaw, err = find_user_set(store, set_id)
    if err:
        return err

    if not zestaw.get('karty') or len(zestaw['karty']) == 0:
        flash('Ten zestaw nie zawiera żadnych fiszek.', 'error')
        return redirect(url_for('sets.view_set', set_id=set_id))

    # Pobierz opcje nauki (domyślnie losowa kolejność; random=0 wyłącza)
    random_param = request.args.get('random')
    random_order = False if random_param is None else random_param == '1'
    review_mode = request.args.get('review') == '1'

    # Przygotuj kolejność indeksów kart do nauki (przechowujemy tylko indeksy, nie całe karty)
    total_cards = len(zestaw.get('karty', []))
    order = list(range(total_cards))

    # Tryb powtórki - tylko fiszki oznaczone jako trudne na podstawie statystyk i terminowości
    if review_mode:
        # Znajdź karty:
        # - Nieopanowane i (procent < 70 lub pokazane < 3)
        # - Opanowane, ale termin powtórki (next_due <= dziś) lub długa nieaktywność (>14 dni)
        difficult_indices = []
        for i, karta in enumerate(zestaw['karty']):
            stats = karta.get('statystyki', {})
            pokazane = stats.get('pokazane', 0)
            procent = stats.get('procent_sukcesu', 0)
            opanowana = stats.get('opanowana', False)
            next_due = stats.get('next_due')
            last_seen = stats.get('last_seen_date')
            due = False
            inactive = False
            try:
                if next_due:
                    due = datetime.fromisoformat(next_due).date() <= datetime.now(timezone.utc).date()
                if last_seen:
                    inactive = (datetime.now(timezone.utc).date() - datetime.fromisoformat(last_seen).date()).days > 14
            except Exception:
                pass

            if (not opanowana and (pokazane < 3 or procent < 70)) or (opanowana and (due or inactive)):
                difficult_indices.append(i)

        if difficult_indices:
            order = difficult_indices
        else:
            flash('Brak trudnych fiszek do powtórki! Wszystkie fiszki mają ≥70% sukcesu lub są opanowane (3× z rzędu). 🎉', 'success')
            return redirect(url_for('sets.view_set', set_id=set_id))

    # Losowa kolejność
    if random_order:
        rng = random.Random(time.time_ns())  # świeże losowanie przy każdym uruchomieniu
        rng.shuffle(order)

    # Nie zapisujemy wyników per karta w sesji (obsługa po stronie klienta)

    # Stwórz tymczasowy zestaw z kartami w odpowiedniej kolejności
    zestaw_temp = zestaw.copy()
    zestaw_temp['karty'] = [zestaw['karty'][i] for i in order]

    return render_template(
        'learn_set.html',
        username=session['username'],
        zestaw=zestaw_temp,
        current_index=0,
        order=order,
        random_order=random_order,
        review_mode=review_mode
    )


@learn.route('/<set_id>/ucz-sie/submit', methods=['POST'])
@login_required
def learn_submit(set_id):
    store.reload_sets()

    # Znajdź zestaw
    zestaw = next((s for s in store.sets if s.get('id') == set_id), None)
    if not zestaw:
        return jsonify({'error': 'set_not_found'}), 404
    if zestaw.get('autor') != session['username']:
        return jsonify({'error': 'forbidden'}), 403

    data = request.get_json(silent=True) or {}
    results = data.get('results') or []
    order = data.get('order') or []
    mode = data.get('mode') or {'random': False, 'review': False}

    if not isinstance(results, list) or not isinstance(order, list):
        return jsonify({'error': 'invalid_payload'}), 400

    # Walidacja order: musi być listą unikalnych intów w zakresie 0..len(karty)-1
    karty = zestaw.get('karty') or []
    num_cards = len(karty)
    if order:
        if (not all(isinstance(x, int) for x in order)
                or not all(0 <= x < num_cards for x in order)
                or len(set(order)) != len(order)):
            return jsonify({'error': 'invalid_order'}), 400

    # Upewnij się, że długości wyników i kolejności są spójne
    if len(order) == 0:
        order = list(range(len(zestaw.get('karty', []) or [])))
    if len(results) != len(order):
        normalized = [None] * len(order)
        for i, value in enumerate(results[:len(order)]):
            normalized[i] = value
        results = normalized

    # Zapisz wyniki do sesji, aby użyć istniejącego podsumowania
    session[f'learn_{set_id}_results'] = results
    session[f'learn_{set_id}_order'] = order
    session[f'learn_{set_id}_mode'] = mode
    session.modified = True

    return jsonify({'redirect': url_for('learn.learn_summary', set_id=set_id)})


@learn.route('/<set_id>/ucz-sie/<int:card_index>', methods=['GET', 'POST'])
@login_required
def learn_card(set_id, card_index):
    store.reload_sets()

    zestaw, err = find_user_set(store, set_id)
    if err:
        return err

    # Pobierz kolejność indeksów kart z sesji i zbuduj listę kart w tej kolejności
    order = session.get(f'learn_{set_id}_order')
    if order is None:
        order = list(range(len(zestaw.get('karty', []))))
    ordered_cards = [zestaw['karty'][i] for i in order] if zestaw.get('karty') else []

    # Walidacja card_index
    if card_index < 0 or card_index >= len(ordered_cards):
        flash('Nieprawidłowy indeks fiszki.', 'error')
        return redirect(url_for('sets.view_set', set_id=set_id))

    if request.method == 'POST':
        # Zapisz wynik (czy rozumie czy nie)
        understood = request.form.get('understood') == 'true'
        results_key = f'learn_{set_id}_results'

        if results_key not in session:
            session[results_key] = []

        session[results_key].append(understood)

        order = session.get(f'learn_{set_id}_order') or list(range(len(zestaw.get('karty', []))))
        original_index = order[card_index] if card_index < len(order) else card_index

        # Jeśli nie rozumie, dodaj do listy trudnych fiszek w sesji (dla starych użytkowników)
        if not understood:
            difficult_key = f'learn_{set_id}_difficult'
            if difficult_key not in session:
                session[difficult_key] = []
            if original_index not in session[difficult_key]:
                session[difficult_key].append(original_index)

        session.modified = True

        # Sprawdź czy to była ostatnia fiszka
        if card_index >= len(ordered_cards) - 1:
            # Przekieruj do podsumowania
            return redirect(url_for('learn.learn_summary', set_id=set_id))
        else:
            # Następna fiszka
            return redirect(url_for('learn.learn_card', set_id=set_id, card_index=card_index + 1))

    # GET - pokaż fiszkę
    if card_index >= len(ordered_cards):
        return redirect(url_for('learn.learn_summary', set_id=set_id))

    # Stwórz tymczasowy zestaw z kartami w kolejności ustalonej w sesji
    zestaw_temp = zestaw.copy()
    zestaw_temp['karty'] = ordered_cards

    return render_template('learn_set.html',
                         username=session['username'],
                         zestaw=zestaw_temp,
                         current_index=card_index,
                         order=order)


@learn.route('/<set_id>/podsumowanie')
@login_required
def learn_summary(set_id):
    store.reload_sets()

    # Znajdź zestaw
    zestaw = next((s for s in store.sets if s.get('id') == set_id), None)
    if not zestaw:
        flash('Zestaw nie został znaleziony.', 'error')
        return redirect(url_for('dashboard.dashboard'))

    # Pobierz wyniki
    results_key = f'learn_{set_id}_results'
    results = session.get(results_key, [])
    order = session.get(f'learn_{set_id}_order') or list(range(len(zestaw.get('karty', []))))
    last_mode = session.get(f'learn_{set_id}_mode', {'random': False, 'review': False})

    answered_results = [r for r in results if r is True or r is False]
    understood_count = sum(1 for r in answered_results if r)
    not_understood_count = sum(1 for r in answered_results if not r)
    solved_total = len(answered_results)
    total_cards = len(zestaw.get('karty', []))
    unsolved_count = max(0, total_cards - solved_total)

    # Zapisz wyniki do zestawu przed wyczyszczeniem sesji i zaktualizuj sesyjne statystyki
    if results:
        # Odwzoruj wyniki na oryginalne indeksy kart (ważne przy losowej kolejności)
        full_results = [None] * total_cards
        for idx, res in enumerate(results):
            orig_idx = order[idx] if idx < len(order) else idx
            if 0 <= orig_idx < total_cards:
                full_results[orig_idx] = res
        zestaw['ostatnie_wyniki'] = full_results
        unsolved_count = sum(1 for r in full_results if r is None)
        now_ts = datetime.now(timezone.utc)
        today = now_ts.date().isoformat()
        zestaw['data_ostatniej_nauki'] = now_ts.isoformat()

        # Aktualizacja per-karta: sesje, degradacja tolerancyjna, due scheduling
        for i in range(total_cards):
            session_res = full_results[i]
            karta = zestaw['karty'][i]
            stats = karta.setdefault('statystyki', {})
            # Uzupełnij brakujące klucze
            stats.setdefault('pokazane', 0)
            stats.setdefault('rozumiem', 0)
            stats.setdefault('nie_rozumiem', 0)
            stats.setdefault('procent_sukcesu', 0)
            stats.setdefault('sessions_ok_streak', 0)
            stats.setdefault('fail_streak_sessions', 0)
            stats.setdefault('last_seen_date', None)
            stats.setdefault('total_sessions_ok', 0)
            stats.setdefault('next_due', None)
            stats.setdefault('leech', False)
            stats.setdefault('opanowana', False)

            if session_res is not None:
                stats['pokazane'] = stats.get('pokazane', 0) + 1
                stats['last_seen_date'] = today
                if session_res is True:
                    stats['rozumiem'] = stats.get('rozumiem', 0) + 1
                    stats['sessions_ok_streak'] = stats.get('sessions_ok_streak', 0) + 1
                    stats['fail_streak_sessions'] = 0
                    stats['total_sessions_ok'] = stats.get('total_sessions_ok', 0) + 1
                    # Proste odstępy powtórek (SM-2 light) zależne od streak sesji
                    streak = stats['sessions_ok_streak']
                    if streak >= 3:
                        interval_days = 16
                    elif streak == 2:
                        interval_days = 6
                    else:
                        interval_days = 1
                    stats['next_due'] = (now_ts.date() + timedelta(days=interval_days)).isoformat()
                else:
                    stats['nie_rozumiem'] = stats.get('nie_rozumiem', 0) + 1
                    stats['fail_streak_sessions'] = stats.get('fail_streak_sessions', 0) + 1
                    stats['sessions_ok_streak'] = 0
                    # Tolerancja błędu: degraduj dopiero po 2 kolejnych sesjach z błędem
                    if stats.get('opanowana') and stats['fail_streak_sessions'] >= 2:
                        stats['opanowana'] = False

                # Przelicz procent sukcesu po aktualizacji liczników
                pokazane = stats.get('pokazane', 0)
                rozumiem = stats.get('rozumiem', 0)
                if pokazane > 0:
                    stats['procent_sukcesu'] = round((rozumiem / pokazane) * 100, 1)
                else:
                    stats['procent_sukcesu'] = 0

                # Nadanie opanowania wg sesji lub prób + skuteczność
                procent = stats.get('procent_sukcesu', 0)
                if not stats.get('opanowana') and (
                    stats.get('sessions_ok_streak', 0) >= 3 or (pokazane >= 5 and procent >= 85)
                ):
                    stats['opanowana'] = True

                # Wykrywanie szczególnie trudnych fiszek
                if stats.get('nie_rozumiem', 0) >= 6 and procent < 60:
                    stats['leech'] = True
                elif procent >= 70:
                    stats['leech'] = False

        # Dodaj wpis do historii nauki
        if 'historia_nauki' not in zestaw:
            zestaw['historia_nauki'] = []
        zestaw['historia_nauki'].append({
            'data': today,
            'timestamp': now_ts.isoformat(),
            'zrozumiane': understood_count,
            'niezrozumiane': not_understood_count
        })

        # Oznacz zestaw jako ukończony dziś, jeśli wszystkie fiszki były dziś przerobione
        all_seen_today = False
        try:
            zestaw.setdefault('days_completed', [])
            all_seen_today = True
            for karta in zestaw.get('karty', []) or []:
                stats = karta.get('statystyki') or {}
                if stats.get('last_seen_date') != today:
                    all_seen_today = False
                    break
            if all_seen_today and today not in zestaw['days_completed']:
                zestaw['days_completed'].append(today)
        except Exception:
            pass

        # Ustal termin kolejnej powtórki zestawu wg harmonogramu, tylko jeśli ukończony dziś:
        # - pierwsze 5 dni ukończeń: codziennie
        # - potem 3 ukończenia co 3 dni
        # - potem co tydzień
        try:
            if all_seen_today:
                completed_days = set(zestaw.get('days_completed') or [])
                completed_count = len(completed_days)
                zestaw['next_review_date'] = compute_next_review_date(completed_count, now_ts.date())
        except Exception:
            pass

        store.save_and_reload_sets()

    # Wyczyść sesję
    if results_key in session:
        del session[results_key]
    if f'learn_{set_id}_current' in session:
        del session[f'learn_{set_id}_current']
    if f'learn_{set_id}_order' in session:
        del session[f'learn_{set_id}_order']
    if f'learn_{set_id}_mode' in session:
        del session[f'learn_{set_id}_mode']
    if f'learn_{set_id}_difficult' in session:
        del session[f'learn_{set_id}_difficult']
    session.modified = True

    return render_template('learn_summary.html',
                         username=session['username'],
                         zestaw=zestaw,
                         understood=understood_count,
                         not_understood=not_understood_count,
                         unsolved=unsolved_count,
                         total=total_cards,
                         last_mode=last_mode)
