from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime, timezone
from storage import store
from helpers import login_required, find_user_set, get_valid_cards
import random

test = Blueprint('test', __name__, url_prefix='/zestawy')


@test.route('/<set_id>/test')
@login_required
def test_set(set_id):
    store.reload_sets()

    zestaw, err = find_user_set(store, set_id)
    if err:
        return err

    # Sprawdź czy zestaw ma karty
    if not zestaw.get('karty') or len(zestaw['karty']) == 0:
        flash('Ten zestaw nie zawiera żadnych fiszek.', 'error')
        return redirect(url_for('sets.view_set', set_id=set_id))

    # Jeśli jest tylko jedna fiszka, test będzie z jedną opcją poprawną i powtarzającymi się błędnymi
    # (pozwalamy na test dla minimalnych zestawów)

    # Pobierz liczbę pytań
    try:
        count = int(request.args.get('count', 5))
    except ValueError:
        count = 5
    karty = list(zestaw['karty'])

    # Używaj tylko kart z niepustym pytaniem i odpowiedzią
    valid_cards = get_valid_cards(zestaw)
    if not valid_cards:
        flash('Brak odpowiednich fiszek do tworzenia testu (puste pytania lub odpowiedzi).', 'error')
        return redirect(url_for('sets.view_set', set_id=set_id))

    # Jeśli -1, użyj wszystkich; odrzuć inne wartości < 1
    if count == -1:
        count = len(valid_cards)
    elif count < 1:
        count = 5
    count = min(count, len(valid_cards))

    # Losuj pytania (indeksy w valid_cards)
    valid_indices = list(range(len(valid_cards)))
    test_card_indices = valid_indices if count == len(valid_cards) else random.sample(valid_indices, count)

    # Dla każdej karty generuj pytanie z wielokrotnym wyborem
    # Zapisuj tylko indeksy, aby zmniejszyć payload sesji
    questions = []
    for i, card_index in enumerate(test_card_indices):
        # Poprawna odpowiedź
        correct_index = card_index

        # Wygeneruj 3 losowe niepoprawne odpowiedzi z innych kart (indeksy)
        wrong_pool = [idx for idx in valid_indices if idx != correct_index]
        if len(wrong_pool) >= 3:
            wrong_indices = random.sample(wrong_pool, 3)
        else:
            wrong_indices = wrong_pool.copy()

        # Uzupełnij do 3 błędnych odpowiedzi placeholderami
        while len(wrong_indices) < 3:
            wrong_indices.append(None)

        # Wszystkie opcje (poprawna + niepoprawne) i tasowanie
        options_indices = [correct_index] + wrong_indices[:3]
        random.shuffle(options_indices)
        correct_option = options_indices.index(correct_index)

        questions.append({
            'number': i + 1,
            'card_index': card_index,
            'options': options_indices,
            'correct_option': correct_option
        })

    # Zapisz pytania w sesji
    session[f'test_{set_id}_questions'] = questions
    session[f'test_{set_id}_current'] = 0
    session[f'test_{set_id}_results'] = []
    session.modified = True

    # Przekieruj do pierwszego pytania
    return redirect(url_for('test.test_question', set_id=set_id, question_index=0))


@test.route('/<set_id>/test/<int:question_index>', methods=['GET', 'POST'])
@login_required
def test_question(set_id, question_index):
    store.reload_sets()

    # Znajdź zestaw
    zestaw = next((s for s in store.sets if s.get('id') == set_id), None)
    if not zestaw:
        flash('Zestaw nie został znaleziony.', 'error')
        return redirect(url_for('dashboard.dashboard'))

    if zestaw.get('autor') != session['username']:
        flash('Nie masz dostępu do tego zestawu.', 'error')
        return redirect(url_for('dashboard.dashboard'))

    # Pobierz pytania z sesji
    questions = session.get(f'test_{set_id}_questions', [])

    if not questions or question_index < 0 or question_index >= len(questions):
        return redirect(url_for('test.test_summary_route', set_id=set_id))

    # Odbuduj listę poprawnych kart, aby odczytać treść i odpowiedzi
    valid_cards = get_valid_cards(zestaw)

    current_question = questions[question_index]
    card_index = current_question.get('card_index')
    options_indices = current_question.get('options', [])
    correct_option = current_question.get('correct_option')

    if card_index is None or card_index >= len(valid_cards):
        flash('Nieprawidłowe dane testu. Spróbuj uruchomić test ponownie.', 'error')
        return redirect(url_for('sets.view_set', set_id=set_id))

    card = valid_cards[card_index]
    rendered_options = []
    for idx, option_index in enumerate(options_indices):
        if option_index is None or option_index >= len(valid_cards):
            option_text = '—'
        else:
            option_text = str(valid_cards[option_index].get('odpowiedz', '—'))
        rendered_options.append({
            'value': str(idx),
            'text': option_text
        })

    question_payload = {
        'number': current_question.get('number', question_index + 1),
        'question': card.get('tekst', ''),
        'options': rendered_options,
        'correct_option': correct_option
    }

    if request.method == 'POST':
        # Zapisz odpowiedź
        user_answer = request.form.get('answer')
        try:
            selected_option = int(user_answer) if user_answer is not None else None
        except ValueError:
            selected_option = None

        is_correct = (selected_option is not None and selected_option == question_payload['correct_option'])

        results_key = f'test_{set_id}_results'
        if results_key not in session:
            session[results_key] = []

        session[results_key].append({
            'card_index': card_index,
            'selected_option': selected_option,
            'correct_option': question_payload['correct_option'],
            'options': options_indices,
            'is_correct': is_correct
        })
        session.modified = True

        # Sprawdź czy to ostatnie pytanie
        if question_index >= len(questions) - 1:
            # Ostatnie pytanie – pokaż podsumowanie testu
            return redirect(url_for('test.test_summary_route', set_id=set_id))
        else:
            # Następne pytanie
            return redirect(url_for('test.test_question', set_id=set_id, question_index=question_index + 1))

    # GET - pokaż pytanie
    return render_template('test_set.html',
                         username=session['username'],
                         zestaw=zestaw,
                         question=question_payload,
                         question_index=question_index,
                         total_questions=len(questions))


@test.route('/<set_id>/test/summary')
@login_required
def test_summary_route(set_id):
    store.reload_sets()

    def cleanup_test_session():
        for key in [f'test_{set_id}_questions', f'test_{set_id}_current', f'test_{set_id}_results']:
            session.pop(key, None)

    # Znajdź zestaw
    zestaw = next((s for s in store.sets if s.get('id') == set_id), None)
    if not zestaw:
        cleanup_test_session()
        flash('Zestaw nie został znaleziony.', 'error')
        return redirect(url_for('dashboard.dashboard'))

    if zestaw.get('autor') != session['username']:
        cleanup_test_session()
        flash('Nie masz dostępu do tego zestawu.', 'error')
        return redirect(url_for('dashboard.dashboard'))

    # Pobierz wyniki z sesji
    results = session.get(f'test_{set_id}_results', [])

    if not results:
        cleanup_test_session()
        flash('Brak wyników testu.', 'error')
        return redirect(url_for('sets.view_set', set_id=set_id))

    # Odbuduj listę poprawnych kart, aby odczytać treść i odpowiedzi
    valid_cards = get_valid_cards(zestaw)

    # Zbuduj wyniki do wyświetlenia
    display_results = []
    for r in results:
        card_index = r.get('card_index')
        selected_option = r.get('selected_option')
        correct_option = r.get('correct_option')
        options_indices = r.get('options', [])
        if card_index is None or card_index >= len(valid_cards):
            continue
        card = valid_cards[card_index]
        question_text = card.get('tekst', '')
        correct_answer = '—'
        user_answer = None

        if isinstance(options_indices, list) and 0 <= correct_option < len(options_indices):
            correct_idx = options_indices[correct_option]
            if correct_idx is not None and correct_idx < len(valid_cards):
                correct_answer = str(valid_cards[correct_idx].get('odpowiedz', '—'))

        if isinstance(options_indices, list) and selected_option is not None and 0 <= selected_option < len(options_indices):
            selected_idx = options_indices[selected_option]
            if selected_idx is not None and selected_idx < len(valid_cards):
                user_answer = str(valid_cards[selected_idx].get('odpowiedz', '—'))

        display_results.append({
            'question': question_text,
            'correct_answer': correct_answer,
            'user_answer': user_answer,
            'is_correct': r.get('is_correct', False)
        })

    # Oblicz wynik
    correct_count = sum(1 for r in display_results if r['is_correct'])
    total = len(display_results)
    percentage = (correct_count / total * 100) if total > 0 else 0

    # Zapisz wynik do historii
    if not isinstance(zestaw.get('historia_testow'), list):
        zestaw['historia_testow'] = []

    today = datetime.now(timezone.utc).date().isoformat()
    zestaw['historia_testow'].append({
        'data': today,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'poprawne': correct_count,
        'lacznie': total,
        'procent': round(percentage, 1)
    })

    store.save_and_reload_sets()

    # Wyczyść sesję testu
    for key in [f'test_{set_id}_questions', f'test_{set_id}_current', f'test_{set_id}_results']:
        if key in session:
            del session[key]
    session.modified = True

    return render_template('test_summary.html',
                         username=session['username'],
                         zestaw=zestaw,
                         results=display_results,
                         correct=correct_count,
                         total=total,
                         percentage=round(percentage, 1))
