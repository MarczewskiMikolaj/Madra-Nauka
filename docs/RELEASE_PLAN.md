# Pierwsze stabilne wydanie — Mądra Nauka 2.0.0

Plan i audyt: 13 października 2026. Pierwsze wydanie nowej aplikacji zachowuje numerację 2.0, odróżniając ją od archiwalnej aplikacji fiszek.

## Stan początkowy

81 testów przechodzi. Główny przebieg nauki jest gotowy, ale nie wystarcza to do wydania. Audyt kodu wykrył:

- Archiwizacja ćwiczeń jest jednostronna: brak widoku archiwum i przywracania.
- Biblioteka szuka tylko po nazwie i opisie przedmiotu.
- Cel można dodać i zakończyć, ale nie poprawić terminu, budżetu ani usunąć.
- Rejestracja wyłącznie nazwą, bez e-maila; brak usuwania własnych danych.
- Eksport JSON pomija oryginały plików; brak pełnego archiwum do pobrania.
- Ogranicznik logowania sprawdza stan poza transakcją i łączy IP z nazwą: równoległe żądania i zmiana nazw osłabiają limit.
- Po unieważnieniu sesji równoległy zapis może korzystać z wcześniej załadowanego użytkownika.
- Cofnięcie oceny używa czasu jako kolejności; identyczne timestampy mogą wskazać inne zdarzenie. Ponowienie formularza cofnięcia mogło usunąć poprzednią ocenę.
- Brak przyjaznej strony błędu 500 i oznaczenia wersji wydania.
- Dokument weryfikacji opisuje nieaktualny stan starszych etapów.

## Realizacja w tym wydaniu

1. Fundament: poprawić limitowanie logowania oraz weryfikację sesji przy zapisie, ustabilizować cofanie ocen, dodać wersję i obsługę błędu 500.
2. Biblioteka: wyszukiwanie tematów, notatek, linków i ćwiczeń oraz przywracanie archiwum z zachowaniem historii.
3. Cele: edycja i usuwanie, tygodniowa rozpiska czasu do pierwszego przejścia zakresu, osobno od powtórek.
4. Konto: rejestracja i logowanie e-mailem z natychmiastową aktywacją; usuwanie danych po potwierdzeniu hasła i nazwy. Blokada usuwania podczas aktywnego AI.
5. Dane: archiwum ZIP z JSON-em i oryginałami plików; administracyjna kopia SQLite i kontrola integralności do odtworzenia.
6. Weryfikacja: testy regresji, cały zestaw, przeglądarka desktop/mobile na sztucznych danych, dokumentacja i instrukcja wydania.

Status realizacji: punkty 1–6 wdrożone w kodzie i lokalnie zweryfikowane. Publikacja na produkcji pozostaje osobnym krokiem operacyjnym; szczegóły w [RELEASE.md](RELEASE.md), wyniki w [VERIFICATION.md](VERIFICATION.md).

## Warunki wydania

- Wszystkie testy przechodzą, w tym izolacja kont, rejestracja e-mailem, CSRF, usuwanie i oryginalne pliki.
- Migracja z wersji schematu 6 zachowuje istniejące dane.
- Nowe formularze działają w przeglądarce także przy 390 px.
- Dane rzeczywistych użytkowników i pliki starej wersji pozostają nietknięte.
- Przed przełączeniem ruchu: kopia produkcji, test odtworzenia, sprawdzenie wersji tagowanej oraz rzeczywistego logowania/generowania AI. Publikacja wymaga wskazania konkretnego środowiska i końcowego zatwierdzenia sprawdzonych zmian.

## Następne etapy

Po walidacji z użytkownikami: trwała kolejka AI i PostgreSQL przed skalowaniem, automatyczne kopie i monitoring produkcji, import własnego archiwum, tagi, pełny plan egzaminu, FSRS, offline i powiadomienia, współdzielenie. Nie są warunkami osobistego wydania na pojedynczej instancji. Odzyskiwanie konta wyłączono z zakresu na prośbę użytkownika. Weryfikacja adresu i obsługa poczty zostały wyłączone z zakresu na prośbę użytkownika.
