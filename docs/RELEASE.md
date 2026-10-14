# Mądra Nauka 2.0.0 — instrukcja wydania

## Zmiany

Pierwsze stabilne wydanie nowej aplikacji uzupełnia MVP o rejestrację e-mailem z natychmiastową aktywacją konta, wyszukiwanie całej biblioteki, przywracanie ćwiczeń, edycję celów i tygodniową rozpiskę czasu. Dodaje ZIP z oryginałami, usuwanie własnych danych oraz narzędzia kopii SQLite.

Poprawia atomowość ogranicznika logowania, sprawdzanie ważności sesji w transakcji i podczas oczekiwania na połączenie AI, oraz cofnięcie oceny przy jednakowych timestampach i ponownym wysłaniu formularza. Eksporty odczytują spójny stan bez ponownego zapisu obiektu GCS. `/health` zwraca `2.0.0`; błąd 500 otrzymuje polski ekran.

## Kopia i próba odtworzenia

Kopia zawiera dane wszystkich użytkowników, w tym hashe haseł i oryginalne pliki. Polecenie używa SQLite Backup API, nie kopiuje samego pliku obok aktywnego WAL. Cel musi być nowym plikiem; uprawnienia to 0600. Nie nadpisuje istniejącej kopii.

```bash
flask --app app backup-db /bezpieczny/katalog/przed-wydaniem.sqlite3
flask --app app verify-backup /bezpieczny/katalog/przed-wydaniem.sqlite3
```

Kopia w trybie chmurowym pobiera aktualną migawkę GCS. Te polecenia nie obejmują `SECRET_KEY` ani zaszyfrowanych plików/obiektów `chatgpt/` / `auth/`; zabezpiecz je osobno, jeśli po odtworzeniu połączenia AI mają pozostać dostępne. Bez nich można ponownie połączyć AI. Dostęp do kopii i retencję ogranicza administrator.

Próbę odtworzenia wykonaj w osobnym katalogu i z osobną bazą:

1. Skopiuj kopię do nowej ścieżki, bez plików `-wal` i `-shm` poprzedniej bazy.
2. Uruchom z `MADRA_DATABASE_PATH` wskazującym tę kopię, bez `MADRA_STATE_BUCKET`.
3. Sprawdź logowanie testowego konta, liczbę materiałów i plików oraz historię sesji.
4. Dla rzeczywistego odtworzenia lokalnego zatrzymaj serwer, zachowaj uszkodzony katalog osobno i dopiero podmień bazę. Nie podmieniaj bazy działającego procesu.

Przy odtworzeniu produkcji chmurowej zatrzymaj zapisy wszystkich rewizji. Zachowaj obecny obiekt, zweryfikuj kopię i opublikuj ją pod właściwym prefiksem warunkowo względem znanej generacji. Po wznowieniu sprawdź konta i pliki. Tego kroku nie automatyzujemy poleceniem nadpisującym produkcję.

## Publikacja

1. Uruchom cały zestaw testów, Ruff, Black i sprawdzenie składni JS.
2. Wykonaj kopię produkcji przed pierwszym uruchomieniem nowej rewizji: fabryka aplikacji uruchamia migracje od razu. Migracje 007 i 008 są addytywne i pozostawia istniejące konta.
3. Staging powinien używać osobnego prefiksu GCS. Sam tag `--no-traffic` nie izoluje danych — skrypt obecnie używa tego samego `madra-v2` co produkcja. Nie testuj usuwania kont na produkcyjnych danych.
4. Zbuduj i sprawdź obraz Docker, `/health`, rejestrację, upload, naukę, archiwum ZIP i cofanie oceny.
5. Zweryfikuj rzeczywiste połączenie ChatGPT i generowanie; testy automatyczne używają syntetycznych odpowiedzi OpenAI.
6. Przełącz ruch na konkretną sprawdzoną rewizję. Zachowaj pojedynczą instancję i pojedynczy worker.

Powrót do poprzedniego obrazu nie wymaga usuwania tabeli e-maili ani tabel migracji 008. Starszy obraz nie obsługuje nowych trybów sesji, więc nie należy rozwiązywać rozpoczętych sprawdzianów podczas rollbacku. Poprzedni obraz nie pozwala logować się e-mailem — uwzględnij to przy rollbacku. Odtworzenie starszej kopii danych usuwa zapisy dokonane po jej wykonaniu, więc wymaga osobnej decyzji operacyjnej.

## Ograniczenia

Brak odzyskiwania konta, automatycznego importu ZIP, offline, współdzielenia i trwałej kolejki AI. Plan tygodnia uwzględnia zakres, trudności i najbliższe powtórki; nie symuluje gotowości do egzaminu. Całe migawki GCS i skanowanie treści w wyszukiwaniu są rozwiązaniem dla małej aplikacji. Skalowanie wymaga PostgreSQL, osobnego magazynu plików oraz kolejki zadań.

## Rozbudowa studencka

Przegląd błędów, tryb trudności, stopniowane podpowiedzi, źródła, zakres i ważność tematów, dni nauki, próbne sprawdziany, importy oraz Markdown i wzory opisuje [README](../README.md#pełny-przebieg-nauki-studenta). Przed publikacją sprawdź również brak wzorców w HTML trwającego/paused sprawdzianu i pełny eksport oraz usunięcie nowych danych.
