# Uproszczenie nawigacji — 17 października 2026

Aplikacja ma dwa główne miejsca: **Nauka** i **Materiały**.

- Nauka: wybór czasu i bezpośredni start albo wznowienie sesji. Podgląd proponowanego zestawu i dodatkowe tryby są rozwijane. Cele, plan tygodnia oraz historia z paginacją mieszczą się na tej samej stronie.
- Materiały: tematy pogrupowane według przedmiotów. Kliknięcie otwiera temat, bez pośredniej strony przedmiotu. Dodawanie, edycja, nauka całego przedmiotu i archiwizacja pozostają dostępne przy danym przedmiocie. Pliki i stan opracowań AI są w rozwijanej sekcji.
- Czytanie notatki, sesja, podgląd importu i formularze pozostają osobnymi ekranami roboczymi, ponieważ wymagają skupienia lub zatwierdzenia danych.

Usunięto samodzielne szablony celów, postępów i przedmiotu. Stare adresy `/cele`, `/postepy` i `/przedmioty/<id>` prowadzą do nowego miejsca. Formularze celów wracają bezpośrednio do rozwiniętej sekcji. Dostęp do przedmiotu nadal sprawdza właściciela.

Zachowano istniejącą identyfikację: Avenir Next / systemowy sans-serif, tło `#f4f6f9`, powierzchnie `#ffffff`, tekst `#1c2944`, akcje `#304bdb`, tekst pomocniczy `#667287`. Listy tematów zastępują karty wymagające przechodzenia do kolejnych ekranów. Jedna główna akcja na pulpicie, tekst wyrównany do lewej, dwie pozycje nawigacji także na telefonie.

Weryfikacja: 185 testów na tymczasowych bazach, w tym przekierowania, zachowanie paginacji, bezpośrednie linki do tematów, ukrywanie archiwalnych tematów i start sesji z wybranym czasem. Kontrola przeglądarkowa na danych demo: ekran nauki, rozwijanie celów, lista materiałów, rozpoczęcie pięciominutowej sesji oraz układ mobilny i desktopowy. Bez zmian schematu bazy i bez wdrożenia na produkcję.
