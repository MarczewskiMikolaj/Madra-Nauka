# Mądra Nauka 📚

Polska platforma do nauki z fiszkami z inteligentnym systemem powtórek (SM-2), testami wielokrotnego wyboru i powiadomieniami push. Działa jako Progressive Web App — offline na iOS, Android i Desktop.

**→ [madranauka.online](http://madranauka.online/)**

---

## Funkcje

- **Inteligentne powtórki** — algorytm SM-2 light dobiera częstotliwość powtórek per-karta (1/6/16 dni); wykrywa opanowane karty i "leeche"
- **Tryb nauki** — przeglądanie fiszek z oceną "rozumiem / nie rozumiem"; opcja losowej kolejności i tryb powtórki trudnych
- **Testy wielokrotnego wyboru** — automatyczne generowanie pytań z 4 opcjami; historia wyników
- **Powiadomienia push** — codzienna przypominajka o 8:00 (czas lokalny) z liczbą zestawów do powtórki
- **Import CSV** — szybkie dodawanie dużych zestawów
- **Statystyki i streaki** — kalendarz aktywności, heatmapa roczna, wykres tygodniowy, Top 3 zestawy
- **PWA** — instalacja jako natywna aplikacja; działa offline dzięki Service Worker

---

## Stack

| Warstwa | Technologia |
|---------|-------------|
| Backend | Python 3.12, Flask 3.0.3, Gunicorn |
| Storage | Google Cloud Storage (prod) |
| Szyfrowanie | Fernet (dane użytkowników) |
| Push | Web Push API, VAPID, pywebpush |
| Scheduler | Google Cloud Scheduler |
| Deploy | Docker, Google Cloud Run |
| Frontend | Vanilla JS, HTML5/CSS3, Jinja2 |

---

## Uruchomienie lokalne

```bash
git clone <repo>
cd fiszki
pip install -r requirements.txt
python app.py
```

Aplikacja uruchomi się na `http://localhost:8080`.
Domyślnie używa lokalnych plików JSON (`sets.json`, `users.json`).

---

## Zmienne środowiskowe

| Zmienna | Opis |
|---------|------|
| `USE_CLOUD_STORAGE` | `true` = Google Cloud Storage, `false` = lokalne pliki (domyślnie) |
| `USERS_BUCKET_NAME` | Nazwa bucketu GCS (domyślnie `python-fiszki-users`) |
| `SCHEDULER_SECRET` | Bearer token dla endpointu Cloud Scheduler |
| `PORT` | Port serwera (domyślnie `8080`) |

---

## LEARN SMART, DREAM BIG
