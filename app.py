from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet
from datetime import datetime, timezone
from uuid import uuid4
from google.cloud import storage
import os
import json
import random


app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'


# Encryption key - in production, store this securely (environment variable, key management service)
ENCRYPTION_KEY = b'8LQQvN7xVJ9xKvJZLWj0zQYzQYJtZGN7xVJ9xKvJZLW=' # Example key - change in production
cipher = Fernet(ENCRYPTION_KEY)

USERS_FILE = 'users.json'
SETS_FILE = 'sets.json'

BUCKET_NAME = os.environ.get("USERS_BUCKET_NAME", "python-fiszki-users")
USERS_FILE_NAME = "users.json"
SETS_FILE_NAME = "sets.json"

# Sprawdź czy używać Cloud Storage (produkcja) czy lokalnych plików (development)
USE_CLOUD_STORAGE = os.environ.get("USE_CLOUD_STORAGE", "false").lower() == "true"


def get_storage_client():
    return storage.Client()

def load_users():
    """Wczytaj użytkowników - z GCS (produkcja) lub lokalnie (development)."""
    if not USE_CLOUD_STORAGE:
        # Wersja lokalna - pliki na dysku
        if not os.path.exists(USERS_FILE):
            return []
        try:
            with open(USERS_FILE, 'rb') as f:
                encrypted_data = f.read()
                if not encrypted_data:
                    return []
                decrypted_data = cipher.decrypt(encrypted_data)
                data = json.loads(decrypted_data.decode('utf-8'))
                
                if isinstance(data, dict) and 'users' in data and isinstance(data['users'], list):
                    return data['users']
                if isinstance(data, dict):
                    migrated = []
                    for login, info in data.items():
                        item = {
                            'login': login,
                            'haslo': info.get('haslo') or info.get('password'),
                            'data_utworzenia': info.get('data_utworzenia')
                        }
                        migrated.append(item)
                    return migrated
                if isinstance(data, list):
                    return data
                return []
        except Exception as e:
            print(f"Błąd podczas wczytywania użytkowników (lokalnie): {e}")
            return []
    
    # Wersja cloud - Google Cloud Storage
    try:
        client = get_storage_client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(USERS_FILE_NAME)
        
        if not blob.exists():
            return []
        
        encrypted_data = blob.download_as_bytes()
        if not encrypted_data:
            return []
        
        decrypted_data = cipher.decrypt(encrypted_data)
        data = json.loads(decrypted_data.decode('utf-8'))
        
        # Obsługa formatu: {"users": [...]} 
        if isinstance(data, dict) and 'users' in data and isinstance(data['users'], list):
            return data['users']
        
        # Obsługa starego formatu: {"login": {"haslo": ..., "data_utworzenia": ...}, ...}
        if isinstance(data, dict):
            migrated = []
            for login, info in data.items():
                item = {
                    'login': login,
                    'haslo': info.get('haslo') or info.get('password'),
                    'data_utworzenia': info.get('data_utworzenia')
                }
                migrated.append(item)
            return migrated
        
        # Jeśli już lista
        if isinstance(data, list):
            return data
        
        return []
    except Exception as e:
        print(f"Błąd podczas wczytywania użytkowników (cloud): {e}")
        return []

def save_users(users_data):
    """Zapisz użytkowników - do GCS (produkcja) lub lokalnie (development)."""
    if not USE_CLOUD_STORAGE:
        # Wersja lokalna - pliki na dysku
        try:
            wrapper = {'users': users_data}
            json_data = json.dumps(wrapper, indent=2, ensure_ascii=False).encode('utf-8')
            encrypted_data = cipher.encrypt(json_data)
            with open(USERS_FILE, 'wb') as f:
                f.write(encrypted_data)
        except Exception as e:
            print(f"Błąd podczas zapisywania użytkowników (lokalnie): {e}")
        return
    
    # Wersja cloud - Google Cloud Storage
    try:
        wrapper = {'users': users_data}
        json_data = json.dumps(wrapper, indent=2, ensure_ascii=False).encode('utf-8')
        encrypted_data = cipher.encrypt(json_data)
        
        client = get_storage_client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(USERS_FILE_NAME)
        blob.upload_from_string(encrypted_data, content_type='application/octet-stream')
    except Exception as e:
        print(f"Błąd podczas zapisywania użytkowników (cloud): {e}")

# Wczytaj użytkowników przy starcie aplikacji
users = load_users()

def load_sets():
    """Wczytaj zestawy fiszek - z GCS (produkcja) lub lokalnie (development)."""
    if not USE_CLOUD_STORAGE:
        # Wersja lokalna - pliki na dysku
        if not os.path.exists(SETS_FILE):
            return []
        try:
            with open(SETS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict) and 'sets' in data and isinstance(data['sets'], list):
                    return data['sets']
                if isinstance(data, list):
                    return data
                return []
        except Exception as e:
            print(f"Błąd podczas wczytywania zestawów (lokalnie): {e}")
            return []
    
    # Wersja cloud - Google Cloud Storage
    try:
        client = get_storage_client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(SETS_FILE_NAME)
        
        if not blob.exists():
            return []
        
        data_str = blob.download_as_text()
        if not data_str.strip():
            return []
        
        data = json.loads(data_str)
        if isinstance(data, dict) and 'sets' in data and isinstance(data['sets'], list):
            return data['sets']
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        print(f"Błąd podczas wczytywania zestawów (cloud): {e}")
        return []

def save_sets(sets_data):
    """Zapisz zestawy fiszek - do GCS (produkcja) lub lokalnie (development)."""
    if not USE_CLOUD_STORAGE:
        # Wersja lokalna - pliki na dysku
        try:
            wrapper = {'sets': sets_data}
            with open(SETS_FILE, 'w', encoding='utf-8') as f:
                json.dump(wrapper, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Błąd podczas zapisywania zestawów (lokalnie): {e}")
        return
    
    # Wersja cloud - Google Cloud Storage
    try:
        wrapper = {'sets': sets_data}
        client = get_storage_client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(SETS_FILE_NAME)
        blob.upload_from_string(
            json.dumps(wrapper, ensure_ascii=False, indent=2),
            content_type='application/json'
        )
    except Exception as e:
        print(f"Błąd podczas zapisywania zestawów (cloud): {e}")

# Wczytaj zestawy przy starcie aplikacji
sets = load_sets()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Znajdź użytkownika po loginie w liście
        user = next((u for u in users if u.get('login') == username), None)
        if user and check_password_hash(user['haslo'], password):
            session['username'] = username
            flash('Logowanie pomyślne!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Nieprawidłowa nazwa użytkownika lub hasło', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Sprawdź, czy login już istnieje
        if any(u.get('login') == username for u in users):
            flash('Nazwa użytkownika już istnieje', 'error')
        elif password != confirm_password:
            flash('Hasła nie pasują do siebie', 'error')
        elif len(password) < 6:
            flash('Hasło musi mieć co najmniej 6 znaków', 'error')
        else:
            new_user = {
                'login': username,
                'haslo': generate_password_hash(password),
                'data_utworzenia': datetime.now(timezone.utc).isoformat()
            }
            users.append(new_user)
            save_users(users)
            flash('Rejestracja zakończona sukcesem! Zaloguj się.', 'success')
            return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    # Pokaż zestawy użytkownika na stronie głównej
    user_sets = [s for s in sets if s.get('autor') == session['username']]

    # Oblicz codzienny streak (kolejne dni z aktywnością, licząc od dziś)
    from datetime import timedelta
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

    streak = 0
    day = datetime.now(timezone.utc).date()
    while day.isoformat() in activity_dates:
        streak += 1
        day = day - timedelta(days=1)

    # Zbierz daty należące do aktualnego streaka
    streak_dates = set()
    day_iter = datetime.now(timezone.utc).date()
    while day_iter.isoformat() in activity_dates:
        streak_dates.add(day_iter.isoformat())
        day_iter = day_iter - timedelta(days=1)

    # Przygotuj kalendarz bieżącego miesiąca do podglądu (popover)
    import calendar as _calendar
    today_date = datetime.now(timezone.utc).date()
    year, month = today_date.year, today_date.month
    start_weekday, days_in_month = _calendar.monthrange(year, month)  # Monday=0
    # Zbuduj siatkę miesiąca z wypełnieniem luk
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
    while len(month_grid) % 7 != 0:
        month_grid.append(None)
    month_rows = [month_grid[i:i+7] for i in range(0, len(month_grid), 7)]
    polish_months = ['Styczeń', 'Luty', 'Marzec', 'Kwiecień', 'Maj', 'Czerwiec', 'Lipiec', 'Sierpień', 'Wrzesień', 'Październik', 'Listopad', 'Grudzień']
    month_name_pl = polish_months[month - 1]

    return render_template('dashboard.html', username=session['username'], zestawy=user_sets, daily_streak=streak, month_rows=month_rows, month_name=month_name_pl, year=year)

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('Zostałeś wylogowany', 'success')
    return redirect(url_for('index'))

@app.route('/profil')
def profile():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    user_sets = [s for s in sets if s.get('autor') == username]
    
    # Oblicz statystyki
    total_sets = len(user_sets)
    
    # Zestawy rozwiązane dzisiaj
    today = datetime.now(timezone.utc).date().isoformat()
    sets_solved_today = 0
    
    # Statystyki tygodniowe (ostatnie 7 dni)
    from collections import defaultdict
    weekly_stats = defaultdict(int)
    set_solve_counts = defaultdict(int)
    
    for zestaw in user_sets:
        historia = zestaw.get('historia_nauki', [])
        for wpis in historia:
            data = wpis.get('data')
            if data:
                # Sprawdź czy dzisiaj
                if data == today:
                    sets_solved_today += 1
                
                # Dodaj do statystyk tygodniowych
                weekly_stats[data] += 1
                
                # Zlicz ile razy każdy zestaw był rozwiązywany
                set_solve_counts[zestaw['id']] += 1
    
    # Przygotuj dane dla wykresu tygodniowego (ostatnie 7 dni)
    from datetime import timedelta
    chart_data = []
    polish_days = ['Pon', 'Wt', 'Śr', 'Czw', 'Pt', 'Sob', 'Niedz']
    for i in range(6, -1, -1):
        day = (datetime.now(timezone.utc).date() - timedelta(days=i)).isoformat()
        count = weekly_stats.get(day, 0)
        day_weekday = (datetime.now(timezone.utc).date() - timedelta(days=i)).weekday()
        day_name = polish_days[day_weekday]
        chart_data.append({'day': day_name, 'count': count, 'date': day})
    
    # Znajdź najczęściej rozwiązywany zestaw
    most_solved_set = None
    max_count = 0
    if set_solve_counts:
        most_solved_id = max(set_solve_counts, key=set_solve_counts.get)
        most_solved_set = next((s for s in user_sets if s['id'] == most_solved_id), None)
        max_count = set_solve_counts[most_solved_id]

    # Oblicz streak (ciąg kolejnych dni z aktywnością: nauka lub test)
    from datetime import timedelta as _timedelta
    activity_dates = set()
    from collections import defaultdict
    learn_counts_by_date = defaultdict(int)  # data -> łączna liczba rozwiązań (sesji nauki) tego dnia
    for zestaw in user_sets:
        for wpis in zestaw.get('historia_nauki', []) or []:
            data = wpis.get('data')
            if data:
                activity_dates.add(data)
                learn_counts_by_date[data] += 1
        for wpis in zestaw.get('historia_testow', []) or []:
            data = wpis.get('data')
            if data:
                activity_dates.add(data)
                # Testy nie są wliczane do licznika kalendarza, aby dopasować pole "Rozwiązanych dzisiaj"
    daily_streak = 0
    _day = datetime.now(timezone.utc).date()
    while _day.isoformat() in activity_dates:
        daily_streak += 1
        _day = _day - _timedelta(days=1)
    
    # Przygotuj pełny kalendarz aktywności na bieżący miesiąc (siatka tygodni)
    import calendar as _calendar
    today_date = datetime.now(timezone.utc).date()
    year, month = today_date.year, today_date.month
    start_weekday, days_in_month = _calendar.monthrange(year, month)  # Monday=0
    month_grid = []
    for _ in range(start_weekday):
        month_grid.append(None)
    # Zbierz daty należące do aktualnego streaka
    streak_dates = set()
    _iter = datetime.now(timezone.utc).date()
    from datetime import timedelta as _td
    while _iter.isoformat() in activity_dates:
        streak_dates.add(_iter.isoformat())
        _iter = _iter - _td(days=1)
    for d in range(1, days_in_month + 1):
        date_obj = today_date.replace(day=d)
        date_str = date_obj.isoformat()
        month_grid.append({
            'day': d,
            'date': date_str,
            'active': date_str in activity_dates,
            'streak': date_str in streak_dates,
            'count': int(learn_counts_by_date.get(date_str, 0))
        })
    while len(month_grid) % 7 != 0:
        month_grid.append(None)
    month_rows = [month_grid[i:i+7] for i in range(0, len(month_grid), 7)]
    polish_months = ['Styczeń', 'Luty', 'Marzec', 'Kwiecień', 'Maj', 'Czerwiec', 'Lipiec', 'Sierpień', 'Wrzesień', 'Październik', 'Listopad', 'Grudzień']
    month_name_pl = polish_months[month - 1]
    
    return render_template('profile.html',
                         username=username,
                         total_sets=total_sets,
                         sets_solved_today=sets_solved_today,
                         chart_data=chart_data,
                         most_solved_set=most_solved_set,
                         most_solved_count=max_count,
                         daily_streak=daily_streak,
                         month_rows=month_rows,
                         month_name=month_name_pl,
                         year=year)

# Widok listy zestawów fiszek (placeholder)
@app.route('/zestawy')
def zestawy():
    if 'username' not in session:
        return redirect(url_for('login'))
    # Pokaż tylko zestawy należące do aktualnego użytkownika
    user_sets = [s for s in sets if s.get('autor') == session['username']]
    return render_template('dashboard.html', username=session['username'], zestawy=user_sets)

@app.route('/zestawy/nowy', methods=['GET', 'POST'])
def create_set():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        nazwa = request.form.get('nazwa', '').strip()
        
        # Sprawdź czy jest plik CSV
        csv_file = request.files.get('csv_file')
        karty = []
        
        if csv_file and csv_file.filename.endswith('.csv'):
            # Import z CSV
            import csv
            import io
            
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
                                'statystyki': {
                                    'pokazane': 0,
                                    'rozumiem': 0,
                                    'nie_rozumiem': 0,
                                    'procent_sukcesu': 0
                                }
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
                if t or o:
                    karty.append({
                        'tekst': t,
                        'odpowiedz': o,
                        'statystyki': {
                            'pokazane': 0,
                            'rozumiem': 0,
                            'nie_rozumiem': 0,
                            'procent_sukcesu': 0
                        }
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

        sets.append(new_set)
        save_sets(sets)
        flash('Zestaw został utworzony!', 'success')
        return redirect(url_for('zestawy'))

    return render_template('create_set.html', username=session['username'])

@app.route('/zestawy/<set_id>')
def view_set(set_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    # Znajdź zestaw
    zestaw = next((s for s in sets if s.get('id') == set_id), None)
    if not zestaw:
        flash('Zestaw nie został znaleziony.', 'error')
        return redirect(url_for('zestawy'))
    
    # Sprawdź czy użytkownik jest autorem
    if zestaw.get('autor') != session['username']:
        flash('Nie masz dostępu do tego zestawu.', 'error')
        return redirect(url_for('zestawy'))
    
    return render_template('view_set.html', username=session['username'], zestaw=zestaw)

@app.route('/zestawy/<set_id>/edytuj', methods=['GET', 'POST'])
def edit_set(set_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    # Znajdź zestaw
    zestaw = next((s for s in sets if s.get('id') == set_id), None)
    if not zestaw:
        flash('Zestaw nie został znaleziony.', 'error')
        return redirect(url_for('zestawy'))
    
    # Sprawdź czy użytkownik jest autorem
    if zestaw.get('autor') != session['username']:
        flash('Nie masz dostępu do tego zestawu.', 'error')
        return redirect(url_for('zestawy'))
    
    if request.method == 'POST':
        nazwa = request.form.get('nazwa', '').strip()
        teksty = request.form.getlist('tekst[]')
        odpowiedzi = request.form.getlist('odpowiedz[]')

        # Zbuduj listę kart - zachowaj istniejące statystyki jeśli są
        karty = []
        stare_karty = zestaw.get('karty', [])
        for i in range(max(len(teksty), len(odpowiedzi))):
            t = (teksty[i].strip() if i < len(teksty) and teksty[i] is not None else '')
            o = (odpowiedzi[i].strip() if i < len(odpowiedzi) and odpowiedzi[i] is not None else '')
            if t or o:
                # Zachowaj statystyki jeśli karta już istniała w tym samym miejscu
                stare_stats = None
                if i < len(stare_karty) and stare_karty[i].get('tekst') == t:
                    stare_stats = stare_karty[i].get('statystyki')
                
                karty.append({
                    'tekst': t,
                    'odpowiedz': o,
                    'statystyki': stare_stats if stare_stats else {
                        'pokazane': 0,
                        'rozumiem': 0,
                        'nie_rozumiem': 0,
                        'procent_sukcesu': 0
                    }
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
        save_sets(sets)
        flash('Zestaw został zaktualizowany!', 'success')
        return redirect(url_for('view_set', set_id=set_id))
    
    return render_template('edit_set.html', username=session['username'], zestaw=zestaw)

@app.route('/zestawy/<set_id>/usun', methods=['POST'])
def delete_set(set_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    # Znajdź zestaw
    zestaw = next((s for s in sets if s.get('id') == set_id), None)
    if not zestaw:
        flash('Zestaw nie został znaleziony.', 'error')
        return redirect(url_for('dashboard'))
    
    # Sprawdź czy użytkownik jest autorem
    if zestaw.get('autor') != session['username']:
        flash('Nie masz dostępu do tego zestawu.', 'error')
        return redirect(url_for('dashboard'))
    
    # Usuń zestaw z listy
    sets.remove(zestaw)
    save_sets(sets)
    
    flash(f'Zestaw "{zestaw["nazwa"]}" został usunięty.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/zestawy/<set_id>/ucz-sie')
def learn_set(set_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    # Znajdź zestaw
    zestaw = next((s for s in sets if s.get('id') == set_id), None)
    if not zestaw:
        flash('Zestaw nie został znaleziony.', 'error')
        return redirect(url_for('zestawy'))
    
    # Sprawdź czy użytkownik jest autorem
    if zestaw.get('autor') != session['username']:
        flash('Nie masz dostępu do tego zestawu.', 'error')
        return redirect(url_for('zestawy'))
    
    if not zestaw.get('karty') or len(zestaw['karty']) == 0:
        flash('Ten zestaw nie zawiera żadnych fiszek.', 'error')
        return redirect(url_for('view_set', set_id=set_id))
    
    # Pobierz opcje nauki
    random_order = request.args.get('random') == '1'
    review_mode = request.args.get('review') == '1'
    
    # Przygotuj kolejność indeksów kart do nauki (przechowujemy tylko indeksy, nie całe karty)
    total_cards = len(zestaw.get('karty', []))
    order = list(range(total_cards))
    
    # Tryb powtórki - tylko fiszki oznaczone jako trudne na podstawie statystyk
    if review_mode:
        # Znajdź karty z < 70% sukcesu LUB karty które nie mają jeszcze statystyk/były pokazane < 3 razy
        difficult_indices = []
        for i, karta in enumerate(zestaw['karty']):
            stats = karta.get('statystyki', {})
            pokazane = stats.get('pokazane', 0)
            procent = stats.get('procent_sukcesu', 0)
            
            # Karta jest trudna jeśli: ma < 70% sukcesu LUB była pokazana < 3 razy (niedostatecznie poznana)
            if pokazane < 3 or procent < 70:
                difficult_indices.append(i)
        
        if difficult_indices:
            order = difficult_indices
        else:
            flash('Brak trudnych fiszek do powtórki! Wszystkie fiszki mają ≥70% sukcesu. 🎉', 'success')
            return redirect(url_for('view_set', set_id=set_id))
    
    # Losowa kolejność
    if random_order:
        import random
        random.shuffle(order)
    
    # Zapisz przygotowaną kolejność i resetuj stan sesji nauki
    session[f'learn_{set_id}_order'] = order
    session[f'learn_{set_id}_results'] = []
    session[f'learn_{set_id}_current'] = 0
    session[f'learn_{set_id}_mode'] = {'random': random_order, 'review': review_mode}
    session.modified = True
    
    # Stwórz tymczasowy zestaw z kartami w odpowiedniej kolejności
    zestaw_temp = zestaw.copy()
    zestaw_temp['karty'] = [zestaw['karty'][i] for i in order]
    
    return render_template('learn_set.html', username=session['username'], zestaw=zestaw_temp, current_index=0)

@app.route('/zestawy/<set_id>/ucz-sie/<int:card_index>', methods=['GET', 'POST'])
def learn_card(set_id, card_index):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    # Znajdź zestaw
    zestaw = next((s for s in sets if s.get('id') == set_id), None)
    if not zestaw:
        flash('Zestaw nie został znaleziony.', 'error')
        return redirect(url_for('zestawy'))
    
    # Sprawdź czy użytkownik jest autorem
    if zestaw.get('autor') != session['username']:
        flash('Nie masz dostępu do tego zestawu.', 'error')
        return redirect(url_for('zestawy'))
    
    # Pobierz kolejność indeksów kart z sesji i zbuduj listę kart w tej kolejności
    order = session.get(f'learn_{set_id}_order')
    if order is None:
        order = list(range(len(zestaw.get('karty', []))))
    ordered_cards = [zestaw['karty'][i] for i in order] if zestaw.get('karty') else []
    
    if request.method == 'POST':
        # Zapisz wynik (czy rozumie czy nie)
        understood = request.form.get('understood') == 'true'
        results_key = f'learn_{set_id}_results'
        
        if results_key not in session:
            session[results_key] = []
        
        session[results_key].append(understood)
        
        # Zaktualizuj statystyki tej konkretnej karty
        order = session.get(f'learn_{set_id}_order') or list(range(len(zestaw.get('karty', []))))
        original_index = order[card_index] if card_index < len(order) else card_index
        
        if original_index < len(zestaw['karty']):
            karta = zestaw['karty'][original_index]
            
            # Upewnij się, że karta ma strukturę statystyk
            if 'statystyki' not in karta:
                karta['statystyki'] = {
                    'pokazane': 0,
                    'rozumiem': 0,
                    'nie_rozumiem': 0,
                    'procent_sukcesu': 0
                }
            
            # Aktualizuj statystyki
            karta['statystyki']['pokazane'] += 1
            if understood:
                karta['statystyki']['rozumiem'] += 1
            else:
                karta['statystyki']['nie_rozumiem'] += 1
            
            # Przelicz procent sukcesu
            total = karta['statystyki']['pokazane']
            if total > 0:
                karta['statystyki']['procent_sukcesu'] = round((karta['statystyki']['rozumiem'] / total) * 100, 1)
            
            # Zapisz zmiany do pliku
            save_sets(sets)
        
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
            return redirect(url_for('learn_summary', set_id=set_id))
        else:
            # Następna fiszka
            return redirect(url_for('learn_card', set_id=set_id, card_index=card_index + 1))
    
    # GET - pokaż fiszkę
    if card_index >= len(ordered_cards):
        return redirect(url_for('learn_summary', set_id=set_id))
    
    # Stwórz tymczasowy zestaw z kartami w kolejności ustalonej w sesji
    zestaw_temp = zestaw.copy()
    zestaw_temp['karty'] = ordered_cards
    
    return render_template('learn_set.html', 
                         username=session['username'], 
                         zestaw=zestaw_temp, 
                         current_index=card_index)

@app.route('/zestawy/<set_id>/podsumowanie')
def learn_summary(set_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    # Znajdź zestaw
    zestaw = next((s for s in sets if s.get('id') == set_id), None)
    if not zestaw:
        flash('Zestaw nie został znaleziony.', 'error')
        return redirect(url_for('dashboard'))
    
    # Pobierz wyniki
    results_key = f'learn_{set_id}_results'
    results = session.get(results_key, [])
    
    understood_count = sum(1 for r in results if r)
    not_understood_count = sum(1 for r in results if not r)
    solved_total = len(results)
    total_cards = len(zestaw.get('karty', []))
    unsolved_count = total_cards - solved_total
    
    # Zapisz wyniki do zestawu przed wyczyszczeniem sesji
    if results:
        # Uzupełnij wyniki o None dla nierozwiązanych fiszek
        full_results = results + [None] * (total_cards - len(results))
        zestaw['ostatnie_wyniki'] = full_results
        zestaw['data_ostatniej_nauki'] = datetime.now(timezone.utc).isoformat()
        
        # Dodaj wpis do historii nauki
        if 'historia_nauki' not in zestaw:
            zestaw['historia_nauki'] = []
        
        today = datetime.now(timezone.utc).date().isoformat()
        zestaw['historia_nauki'].append({
            'data': today,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'zrozumiane': understood_count,
            'niezrozumiane': not_understood_count
        })
        
        save_sets(sets)
    
    # Wyczyść sesję
    if results_key in session:
        del session[results_key]
    if f'learn_{set_id}_current' in session:
        del session[f'learn_{set_id}_current']
    if f'learn_{set_id}_order' in session:
        del session[f'learn_{set_id}_order']
    session.modified = True
    
    return render_template('learn_summary.html',
                         username=session['username'],
                         zestaw=zestaw,
                         understood=understood_count,
                         not_understood=not_understood_count,
                         unsolved=unsolved_count,
                         total=total_cards)

@app.route('/zestawy/<set_id>/test')
def test_set(set_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    # Znajdź zestaw
    zestaw = next((s for s in sets if s.get('id') == set_id), None)
    if not zestaw:
        flash('Zestaw nie został znaleziony.', 'error')
        return redirect(url_for('dashboard'))
    
    # Sprawdź czy zestaw ma karty
    if not zestaw.get('karty') or len(zestaw['karty']) == 0:
        flash('Ten zestaw nie zawiera żadnych fiszek.', 'error')
        return redirect(url_for('view_set', set_id=set_id))
    
    # Jeśli jest tylko jedna fiszka, test będzie z jedną opcją poprawną i powtarzającymi się błędnymi
    # (pozwalamy na test dla minimalnych zestawów)
    
    # Pobierz liczbę pytań
    count = int(request.args.get('count', 5))
    karty = list(zestaw['karty'])
    
    # Używaj tylko kart z niepustym pytaniem i odpowiedzią
    valid_cards = [
        c for c in karty
        if isinstance(c.get('tekst'), str) and c.get('tekst').strip()
        and isinstance(c.get('odpowiedz'), str) and c.get('odpowiedz').strip()
    ]
    if not valid_cards:
        flash('Brak odpowiednich fiszek do tworzenia testu (puste pytania lub odpowiedzi).', 'error')
        return redirect(url_for('view_set', set_id=set_id))
    
    # Jeśli -1, użyj wszystkich
    if count == -1:
        count = len(valid_cards)
    else:
        count = min(count, len(valid_cards))
    
    # Losuj pytania
    test_cards = valid_cards if count == len(valid_cards) else random.sample(valid_cards, count)
    
    # Dla każdej karty generuj pytanie z wielokrotnym wyborem
    questions = []
    for i, card in enumerate(test_cards):
        # Poprawna odpowiedź
        correct_answer = str(card['odpowiedz'])
        
        # Wygeneruj 3 losowe niepoprawne odpowiedzi z innych kart
        # Zbierz unikalną pulę odpowiedzi (bez poprawnej)
        answers_pool = list({
            str(c['odpowiedz']) for c in valid_cards
            if str(c['odpowiedz']) != correct_answer
        })
        # Uzupełnij do 3 błędnych odpowiedzi
        wrong_answers = []
        if len(answers_pool) >= 3:
            wrong_answers = random.sample(answers_pool, 3)
        else:
            wrong_answers = answers_pool.copy()
            # Jeśli za mało unikalnych, dopełnij powtarzającymi się wpisami
            while len(wrong_answers) < 3:
                wrong_answers.append('—')
        
        # Wszystkie opcje (poprawna + niepoprawne) i tasowanie
        # Zadbaj, by wszystkie opcje były stringami
        all_answers = [correct_answer] + [str(w) for w in wrong_answers[:3]]
        random.shuffle(all_answers)
        
        questions.append({
            'number': i + 1,
            'question': card['tekst'],
            'correct_answer': correct_answer,
            'options': all_answers,
            'card_index': valid_cards.index(card)
        })
    
    # Zapisz pytania w sesji
    session[f'test_{set_id}_questions'] = questions
    session[f'test_{set_id}_current'] = 0
    session[f'test_{set_id}_results'] = []
    session.modified = True
    
    print(f"DEBUG: Test created with {len(questions)} questions for set {set_id}")
    print(f"DEBUG: Redirecting to test_question with question_index=0")
    
    # Przekieruj do pierwszego pytania
    return redirect(url_for('test_question', set_id=set_id, question_index=0))

@app.route('/zestawy/<set_id>/test/<int:question_index>', methods=['GET', 'POST'])
def test_question(set_id, question_index):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    # Znajdź zestaw
    zestaw = next((s for s in sets if s.get('id') == set_id), None)
    if not zestaw:
        flash('Zestaw nie został znaleziony.', 'error')
        return redirect(url_for('dashboard'))
    
    # Pobierz pytania z sesji
    questions = session.get(f'test_{set_id}_questions', [])
    print(f"DEBUG test_question: Found {len(questions)} questions in session for set {set_id}")
    print(f"DEBUG test_question: question_index={question_index}")
    
    if not questions or question_index >= len(questions):
        print(f"DEBUG test_question: No questions or index out of range, redirecting to summary")
        return redirect(url_for('test_summary_route', set_id=set_id))
    
    current_question = questions[question_index]
    
    if request.method == 'POST':
        # Zapisz odpowiedź
        user_answer = request.form.get('answer')
        is_correct = (user_answer == current_question['correct_answer'])
        
        results_key = f'test_{set_id}_results'
        if results_key not in session:
            session[results_key] = []
        
        session[results_key].append({
            'question': current_question['question'],
            'correct_answer': current_question['correct_answer'],
            'user_answer': user_answer,
            'is_correct': is_correct
        })
        session.modified = True
        
        # Sprawdź czy to ostatnie pytanie
        if question_index >= len(questions) - 1:
            # Ostatnie pytanie – pokaż podsumowanie testu
            return redirect(url_for('test_summary_route', set_id=set_id))
        else:
            # Następne pytanie
            return redirect(url_for('test_question', set_id=set_id, question_index=question_index + 1))
    
    # GET - pokaż pytanie
    return render_template('test_set.html',
                         username=session['username'],
                         zestaw=zestaw,
                         question=current_question,
                         question_index=question_index,
                         total_questions=len(questions))

@app.route('/zestawy/<set_id>/test/summary')
def test_summary_route(set_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    # Znajdź zestaw
    zestaw = next((s for s in sets if s.get('id') == set_id), None)
    if not zestaw:
        flash('Zestaw nie został znaleziony.', 'error')
        return redirect(url_for('dashboard'))
    
    # Pobierz wyniki z sesji
    results = session.get(f'test_{set_id}_results', [])
    
    if not results:
        flash('Brak wyników testu.', 'error')
        return redirect(url_for('view_set', set_id=set_id))
    
    # Oblicz wynik
    correct_count = sum(1 for r in results if r['is_correct'])
    total = len(results)
    percentage = (correct_count / total * 100) if total > 0 else 0
    
    # Zapisz wynik do historii
    if 'historia_testow' not in zestaw:
        zestaw['historia_testow'] = []
    
    today = datetime.now(timezone.utc).date().isoformat()
    zestaw['historia_testow'].append({
        'data': today,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'poprawne': correct_count,
        'lacznie': total,
        'procent': round(percentage, 1)
    })
    
    save_sets(sets)
    
    # Wyczyść sesję testu
    for key in [f'test_{set_id}_questions', f'test_{set_id}_current', f'test_{set_id}_results']:
        if key in session:
            del session[key]
    session.modified = True
    
    return render_template('test_summary.html',
                         username=session['username'],
                         zestaw=zestaw,
                         results=results,
                         correct=correct_count,
                         total=total,
                         percentage=round(percentage, 1))


import os
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)

