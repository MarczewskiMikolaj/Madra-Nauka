# Mądra Nauka - Dokumentacja Projektu

## Przegląd

**Mądra Nauka** to polska platforma edukacyjna do nauki z fiszkami (flashcards), zbudowana jako Progressive Web App (PWA). Umożliwia tworzenie zestawów fiszek, naukę z inteligentnym systemem powtórek (SM-2 light), testy wielokrotnego wyboru, śledzenie postępów oraz powiadomienia push z przypomnieniami o powtórkach.

- **URL produkcyjny:** http://madranauka.online/
- **Język interfejsu:** polski

---

## Stack technologiczny

| Warstwa         | Technologia                                                        |
|-----------------|--------------------------------------------------------------------|
| Backend         | Python 3.12, Flask 3.0.3, Gunicorn 22.0.0                        |
| Szyfrowanie     | cryptography (Fernet) — szyfrowanie pliku users.json              |
| Storage         | Google Cloud Storage (produkcja) / pliki lokalne (dev)            |
| Push            | pywebpush ≥2.0.0, VAPID keys, Web Push API                       |
| Scheduler       | Google Cloud Scheduler (HTTP trigger co godzinę)                  |
| Frontend        | Vanilla JS, HTML5 (Jinja2), CSS3                                  |
| PWA             | Service Worker (v6), Web App Manifest                             |
| Deploy          | Docker, Google Cloud Run (europe-west4)                           |

### Zależności (`requirements.txt`)

```
Flask==3.0.3
Werkzeug==3.0.4
cryptography==43.0.3
gunicorn==22.0.0
google-cloud-storage==2.18.2
pywebpush>=2.0.0
```

---

## Struktura projektu

```
.
├── app.py                    # Entry point (~30 linii): tworzy app, rejestruje blueprinty
├── config.py                 # Stałe: SECRET_KEY, ENCRYPTION_KEY, VAPID keys, SCHEDULER_SECRET
├── storage.py                # Singleton DataStore + load/save dla users.json i sets.json
├── helpers.py                # Utylitki: login_required, find_user_set, compute_streak, itp.
├── requirements.txt
├── Dockerfile
├── blueprints/
│   ├── auth.py               # login, register, logout
│   ├── dashboard.py          # index (landing), dashboard (panel główny)
│   ├── sets.py               # CRUD zestawów (url_prefix=/zestawy)
│   ├── learn.py              # Tryb nauki: learn_set, learn_card, learn_submit, learn_summary
│   ├── test.py               # Tryb testu: test_set, test_question, test_summary_route
│   ├── profile.py            # Profil: statystyki, zmiana hasła, nawigacja kalendarza
│   ├── notifications.py      # Web Push: subscribe/unsubscribe, trigger-daily, send logic
│   └── pwa.py                # manifest, service-worker, favicon, icons, offline
├── static/
│   ├── css/
│   │   ├── style.css         # Globalne style
│   │   ├── auth.css          # Logowanie/rejestracja
│   │   ├── dashboard.css     # Dashboard
│   │   ├── sets.css          # Zestawy
│   │   └── learn.css         # Tryb nauki
│   ├── icons/                # Ikony PWA (16×16 do 512×512, niektóre maskable)
│   ├── favicon.ico
│   └── service-worker.js     # SW v6 — cache-first dla statycznych, network-first dla stron
└── templates/
    ├── index.html            # Landing page
    ├── login.html / register.html
    ├── dashboard.html        # Dashboard z listą zestawów i strefą powtórek
    ├── profile.html          # Profil (dwa taby: statystyki / konto)
    ├── create_set.html / edit_set.html / view_set.html
    ├── learn_set.html        # Tryb nauki (fiszki)
    ├── learn_summary.html    # Podsumowanie nauki
    ├── test_set.html         # Pytanie testowe (wielokrotny wybór)
    ├── test_summary.html     # Podsumowanie testu
    └── offline.html          # Strona offline (cachowana przez SW)
```

---

## Architektura aplikacji

### Blueprinty i URL-e

Trzy blueprinty dzielą prefiks `/zestawy`: `sets`, `learn`, `test`. Szablony używają pełnych nazw endpointów: `url_for('sets.view_set', set_id=...)`, `url_for('auth.login')` itp.

### Warstwa danych (DataStore)

Aplikacja **nie używa bazy danych** — dane w plikach JSON:

- **`users.json`** — szyfrowany (Fernet), lista użytkowników
- **`sets.json`** — nieszyfrowany, lista zestawów fiszek

`storage.store` to singleton `DataStore`. Każda trasa wywołuje:
- `store.reload_sets()` / `store.reload_users()` — przeładowanie z GCS (tryb cloud)
- `store.sets` / `store.users` — bezpośredni dostęp do danych w pamięci
- `store.save_and_reload_sets()` / `store.save_and_reload_users()` — zapis + re-sync

Dwa tryby storage (przełączane `USE_CLOUD_STORAGE`):
- **Lokalny (dev):** odczyt/zapis plików z dysku
- **Cloud (prod):** GCS bucket z **optimistic locking** (generacje blobów + exponential backoff retry)

### Konfiguracja (`config.py`)

Przechowuje wszystkie stałe konfiguracyjne:
- `SECRET_KEY` — klucz sesji Flask
- `ENCRYPTION_KEY` — klucz Fernet do szyfrowania users.json
- `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_CLAIMS` — klucze Web Push
- `SCHEDULER_SECRET` — sekret Bearer do autoryzacji Cloud Scheduler (`os.environ.get('SCHEDULER_SECRET', 'change-me-in-production')`)
- `USE_CLOUD_STORAGE`, `USERS_BUCKET_NAME` — konfiguracja storage

---

## Funkcjonalności

### 1. Autentykacja

- **Rejestracja** (`/register`) — walidacja: unikalna nazwa, hasło min. 6 znaków, potwierdzenie hasła; username stripowany z białych znaków
- **Logowanie** (`/login`) — weryfikacja hashem (Werkzeug); username stripowany
- **Wylogowanie** (`/logout`) — czyszczenie sesji
- Hasła hashowane: `werkzeug.security.generate_password_hash`

### 2. Zarządzanie zestawami fiszek

- **Dashboard** (`/dashboard`) — lista zestawów posortowana: najpierw "do powtórki dzisiaj" (wg `next_review_date`), potem pozostałe alfabetycznie; streak dzienny; mini-kalendarz aktywności (30 dni)
- **Tworzenie** (`/zestawy/nowy`) — ręczne dodawanie kart lub import CSV; karta wymaga **zarówno tekstu, jak i odpowiedzi** (puste pola ignorowane)
- **Edycja** (`/zestawy/<id>/edytuj`) — zachowuje istniejące statystyki kart; te same reguły walidacji co tworzenie
- **Usuwanie** (`/zestawy/<id>/usun`) — POST, tylko autor
- **Podgląd** (`/zestawy/<id>`) — szczegóły zestawu + Top 6 najtrudniejszych fiszek (najniższy procent sukcesu)

### 3. Tryb nauki (fiszki)

- **Start nauki** (`/zestawy/<id>/ucz-sie`) — wybiera karty do sesji wg SM-2 light; opcje: `?random=1` (losowa kolejność), `?review=1` (tylko trudne)
- **Tryb powtórki:** karty z niskim procentem sukcesu, nieopanowane, lub z przekroczonym `next_due`
- **Submit wyników** (`POST /zestawy/<id>/ucz-sie/submit`) — bulk JSON; zwraca JSON z URL podsumowania
- **Podsumowanie** (`/zestawy/<id>/podsumowanie`) — statystyki sesji, aktualizacja SM-2, zapis historii nauki
- Loading state na przycisku submit (disabled + "Wysyłanie...") podczas żądania

### 4. System inteligentnych powtórek (SM-2 light)

Per-karta:
- `streak_rozumiem`, `sessions_ok_streak`, `fail_streak_sessions`, `next_due` (1/6/16 dni)
- **Opanowanie:** 3 kolejne poprawne LUB 5+ pokazań z ≥85% sukcesem
- **Degradacja:** utrata opanowania po 2 kolejnych błędnych sesjach (tolerancja)
- **Leech detection:** ≥6 błędów i <60% sukcesu

Per-zestaw:
- `next_review_date`: codziennie (5 dni) → co 3 dni (3 razy) → co tydzień
- `days_completed`: lista dni, w których wszystkie karty zestawu zostały przerobione

### 5. Testy wielokrotnego wyboru

- **Start testu** (`/zestawy/<id>/test`) — generuje pytania z 4 opcjami (1 poprawna + do 3 losowych z innych kart)
- Parametr `?count=N` (domyślnie 5; `-1` = wszystkie karty)
- Pytania i wyniki przechowywane w Flask session podczas testu
- **Podsumowanie** (`/zestawy/<id>/test/summary`) — wynik procentowy, szczegóły per-pytanie, zapis do `historia_testow`
- Zabezpieczenie autoryzacji: ownership check (autor == zalogowany użytkownik) w każdej trasie testu

### 6. Profil i statystyki

**Dwa taby** (`?tab=statystyki` / `?tab=konto`):

**Tab statystyki:**
- 6 kart statystyk: łączna liczba zestawów, fiszek, opanowanych, leech, sesji nauki, sesji dziś
- **Wykres tygodniowy** — liczba sesji nauki dla każdego z ostatnich 7 dni (canvas bar chart)
- **Top 3 zestawy** — najczęściej rozwiązywane
- **Tabela postępów per-zestaw** — procent opanowania, liczba leech, ostatnia sesja
- **Kalendarz aktywności** — siatka bieżącego miesiąca z nawigacją (AJAX, bez przeładowania); dni ze streakiem wyróżnione; tooltip z nazwami zestawów
- **Heatmapa roczna** — GitHub-style grid aktywności z przełącznikiem Miesiąc/Rok (stan w localStorage); formatowanie dat przez lokalny czas (nie `toISOString()`) dla uniknięcia błędów strefy UTC

**Tab konto:**
- Formularz zmiany hasła (walidacja JS po stronie klienta + Python po stronie serwera)
- Przełącznik powiadomień push (toggle)

### 7. Powiadomienia push (Web Push)

**Architektura:**
- Browser rejestruje service worker i subskrybuje push przez `PushManager.subscribe()`
- Klucz publiczny VAPID pobierany z `/push/vapid-public-key`
- Subskrypcja (endpoint + keys + utc_offset) zapisywana w `user['push_subscriptions']` przez `POST /push/subscribe`
- `utc_offset` z JS `new Date().getTimezoneOffset()` (UTC − lokalny czas w minutach; ujemny dla UTC+)

**Wysyłanie notyfikacji:**
- **Google Cloud Scheduler** wysyła `POST /push/trigger-daily` co godzinę (6:00 UTC, region europe-west1)
- Endpoint zabezpieczony Bearer tokenem (`Authorization: Bearer <SCHEDULER_SECRET>`)
- `send_daily_notifications()` oblicza godzinę 8:00 lokalną każdego subskrybenta: `target_utc_hour = (8 * 60 + utc_offset) // 60 % 24`
- Subskrypcje z ostatnio wysłaną datą (`last_sent_date == today`) pomijane — brak duplikatów
- Treść notyfikacji: liczba zestawów do powtórki (odmiana polska: 1/2-4/5+)
- Wygasłe subskrypcje (HTTP 404/410 z push service) automatycznie usuwane

**Endpointy push:**
| Metoda | Ścieżka | Opis |
|--------|---------|------|
| GET | `/push/vapid-public-key` | Zwraca klucz publiczny VAPID |
| POST | `/push/subscribe` | Zapisuje subskrypcję push użytkownika |
| POST | `/push/unsubscribe` | Usuwa subskrypcję push |
| POST | `/push/trigger-daily` | Trigger dla Cloud Scheduler (Bearer auth) |

### 8. PWA i Service Worker

- **Manifest:** standalone, portrait, kategorie: education/productivity; skróty: "Moje Zestawy" → `/dashboard`
- **Service Worker (v6):**
  - **Cache-first** dla zasobów statycznych (`/static/`, `/icons/`, `favicon.ico`)
  - **Network-first** dla stron — fallback z cache, a przy braku: strona `/offline`
  - `self.skipWaiting()` wywoływane bezwarunkowo na początku `install` (nie zależy od wyniku `cache.addAll`)
  - `PAGES_TO_CACHE` zawiera wyłącznie `/offline` — uwierzytelnione strony wykluczone (powodowałyby błąd `cache.addAll` przez przekierowanie)
  - Obsługa push events i `notificationclick` (otwiera/focusuje `/dashboard`)
  - Wersję cache (`fiszki-vN`) należy podbić przy każdej zmianie zewnętrznych plików CSS

---

## Model danych

### Użytkownik

```json
{
  "login": "string",
  "haslo": "werkzeug_hashed_password",
  "data_utworzenia": "ISO 8601 datetime",
  "push_subscriptions": [
    {
      "endpoint": "https://...",
      "keys": { "p256dh": "...", "auth": "..." },
      "utc_offset": -60,
      "last_sent_date": "YYYY-MM-DD"
    }
  ]
}
```

### Zestaw fiszek

```json
{
  "id": "uuid hex",
  "autor": "login",
  "nazwa": "string",
  "data_utworzenia": "ISO 8601",
  "karty": [Karta],
  "historia_nauki": [
    { "data": "YYYY-MM-DD", "timestamp": "ISO 8601", "zrozumiane": 0, "niezrozumiane": 0 }
  ],
  "historia_testow": [
    { "data": "YYYY-MM-DD", "timestamp": "ISO 8601", "poprawne": 0, "lacznie": 0, "procent": 0.0 }
  ],
  "ostatnie_wyniki": [true, false, null],
  "data_ostatniej_nauki": "ISO 8601",
  "days_completed": ["YYYY-MM-DD"],
  "next_review_date": "YYYY-MM-DD"
}
```

### Karta (fiszka)

```json
{
  "tekst": "pytanie (wymagane)",
  "odpowiedz": "odpowiedź (wymagana)",
  "statystyki": {
    "pokazane": 0,
    "rozumiem": 0,
    "nie_rozumiem": 0,
    "procent_sukcesu": 0,
    "streak_rozumiem": 0,
    "streak_nie_rozumiem": 0,
    "opanowana": false,
    "sessions_ok_streak": 0,
    "fail_streak_sessions": 0,
    "last_seen_date": null,
    "total_sessions_ok": 0,
    "next_due": null,
    "leech": false
  }
}
```

---

## Endpointy (pełna lista)

| Metoda   | Ścieżka                               | Blueprint          | Opis                            |
|----------|---------------------------------------|--------------------|---------------------------------|
| GET      | `/`                                   | dashboard          | Landing page                    |
| GET/POST | `/login`                              | auth               | Logowanie                       |
| GET/POST | `/register`                           | auth               | Rejestracja                     |
| GET      | `/logout`                             | auth               | Wylogowanie                     |
| GET      | `/dashboard`                          | dashboard          | Panel główny użytkownika        |
| GET      | `/profil`                             | profile            | Profil ze statystykami          |
| POST     | `/profil/zmien-haslo`                 | profile            | Zmiana hasła                    |
| GET/POST | `/zestawy/nowy`                       | sets               | Tworzenie zestawu               |
| GET      | `/zestawy/<id>`                       | sets               | Podgląd zestawu                 |
| GET/POST | `/zestawy/<id>/edytuj`                | sets               | Edycja zestawu                  |
| POST     | `/zestawy/<id>/usun`                  | sets               | Usunięcie zestawu               |
| GET      | `/zestawy/<id>/ucz-sie`               | learn              | Start sesji nauki               |
| POST     | `/zestawy/<id>/ucz-sie/submit`        | learn              | Submit wyników nauki (JSON)     |
| GET/POST | `/zestawy/<id>/ucz-sie/<card_index>`  | learn              | Nauka — konkretna karta         |
| GET      | `/zestawy/<id>/podsumowanie`          | learn              | Podsumowanie sesji nauki        |
| GET      | `/zestawy/<id>/test`                  | test               | Start testu                     |
| GET/POST | `/zestawy/<id>/test/<q_index>`        | test               | Pytanie testowe                 |
| GET      | `/zestawy/<id>/test/summary`          | test               | Podsumowanie testu              |
| GET      | `/push/vapid-public-key`              | notifications      | Klucz VAPID (publiczny)         |
| POST     | `/push/subscribe`                     | notifications      | Zapis subskrypcji push          |
| POST     | `/push/unsubscribe`                   | notifications      | Usunięcie subskrypcji push      |
| POST     | `/push/trigger-daily`                 | notifications      | Trigger Cloud Scheduler         |
| GET      | `/manifest.json`                      | pwa                | PWA manifest                    |
| GET      | `/service-worker.js`                  | pwa                | Service Worker                  |
| GET      | `/favicon.ico`                        | pwa                | Favicon                         |
| GET      | `/icons/<filename>`                   | pwa                | Ikony PWA                       |
| GET      | `/offline`                            | pwa                | Strona offline (cachowana)      |

---

## Deployment

### Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /usr/src/app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8080
ENV PORT=8080
ENV USE_CLOUD_STORAGE=true
ENV USERS_BUCKET_NAME=python-fiszki-users
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
```

### Zmienne środowiskowe

| Zmienna             | Domyślna              | Opis                                               |
|---------------------|-----------------------|----------------------------------------------------|
| `PORT`              | `8080`                | Port serwera                                       |
| `USE_CLOUD_STORAGE` | `false`               | `true` = GCS, `false` = pliki lokalne              |
| `USERS_BUCKET_NAME` | `python-fiszki-users` | Nazwa bucketu GCS                                  |
| `SCHEDULER_SECRET`  | `change-me-in-production` | Bearer token do autoryzacji Cloud Scheduler    |

### Google Cloud Scheduler

Job skonfigurowany w regionie `europe-west1` (Cloud Scheduler nie obsługuje `europe-west4`):
- Harmonogram: `0 * * * *` (co godzinę)
- Target: `POST https://<cloud-run-url>/push/trigger-daily`
- Header: `Authorization: Bearer <SCHEDULER_SECRET>`

Cloud Run działa w regionie `europe-west4`.

### Uruchomienie lokalne

```bash
python app.py
# lub
gunicorn --bind 0.0.0.0:8080 app:app
```

---

## Znane ograniczenia

1. **Brak bazy danych** — dane w plikach JSON; każdy worker Gunicorn ma własną kopię w pamięci (race conditions mitigowane przez GCS optimistic locking i `last_sent_date` per subskrypcja)
2. **Hardcoded secrets** — `SECRET_KEY`, `ENCRYPTION_KEY` i klucze VAPID w `config.py`; `SCHEDULER_SECRET` z env var
3. **Brak CSRF protection** — formularze bez tokenów CSRF
4. **Brak testów** — projekt nie zawiera testów jednostkowych ani integracyjnych
5. **Izolacja danych** — każdy użytkownik widzi tylko swoje zestawy (filtrowanie po `autor == session['username']`), brak ról ani grup
