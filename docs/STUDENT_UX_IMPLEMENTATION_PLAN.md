# Plan wdrożenia audytu studenta

15 października 2026. Podstawa: `STUDENT_UX_AUDIT_2026-10-15.md`.

## Zakres wydania

Wdrożyć pełny codzienny przebieg osobistej nauki: szybkie dodanie materiału, zachowanie pracy, plan kilku egzaminów, ćwiczenie i sprawdzian, porządkowanie oraz przenoszenie zestawów. Zachować historię i migawki sesji, własność danych, CSRF oraz jawne uruchamianie AI. Migracje uruchamiać i testować na sztucznych bazach; publikacja na produkcji nie jest częścią zmiany kodu.

| Etap | Zmiana | Kryteria ukończenia |
|---|---|---|
| 1. Zachowanie pracy | Serwerowe szkice odpowiedzi i formularzy notatek, automatyczny zapis, jawny zapis przy przerwie, wykrywanie konfliktu | Odświeżenie, przerwa i inne urządzenie przywracają szkic. Szkic nie odsłania wzorca i nie nalicza oceny. Cudzy szkic niedostępny. |
| 2. Jeden plan dnia | Wspólny budżet 5–180 min, aktywne cele według terminu i dni, podział czasu, przeterminowane cele poza domyślnym planem | Kilka egzaminów dostaje porcję w ramach jednego limitu; podgląd i start wybierają te same pytania. Licznik trudności ma globalną akcję. |
| 3. Pierwszy materiał | Wklejenie notatki bez ręcznego tworzenia struktury, krótkie czytanie–odtwarzanie–porównanie, pamięć rozdziału i postępu, pytanie ze źródłem | Można rozpocząć naukę z samej notatki bez AI. Próby z notatki nie udają ocen obiektywnych. |
| 4. Porządek | Archiwum przedmiotu i tematu, kosz notatek/plików, przywracanie, przenoszenie treści i tematów, filtr plików | Zarchiwizowane treści nie trafiają do nowych planów; historyczne sesje nadal działają. Przeniesienie nie zostawia źródeł innego tematu. |
| 5. Wygodne ćwiczenia | Odpowiedź na kartce/ustnie, bezpieczne obrazki pytań, wybór rozdziału po tytule, wybór poprawnej opcji quizu, rozwijane adnotacje | Obrazki dostępne tylko właścicielowi, zachowane w migawce i eksporcie. Pomoc jest oznaczana automatycznie. |
| 6. Sprawdzian | Nawigacja, pomijanie, oznaczenie do powrotu, poprawianie odpowiedzi, wybór liczby pytań z równoważeniem tematów, opcjonalny zegar | Żaden wzorzec ani wynik nie ujawnia się przed zakończeniem. Sam zapis ostatniej odpowiedzi w nowym trybie nie kończy egzaminu bez decyzji. |
| 7. Zakres i wyniki | Lista wymagań celu z przypisaniem do tematów, odrębna deklaracja sprawdzenia, brak danych zamiast 0%, liczby prób samodzielnych/z pomocą | Jedno pytanie nie oznacza pokrycia całego tematu. Interfejs nie obiecuje zdania egzaminu. |
| 8. Materiały i AI | Wiele plików, zdjęcia PNG/JPG/WebP, jasne limity i konwersja prezentacji do PDF, trzy cele opracowania, anulowanie i powrót do pliku po logowaniu | Błędny plik nie daje częściowego zapisu grupy. Anulowany worker nie nadpisuje wyniku. Brak zmiany modelu i zasad autoryzacji dostawcy. |
| 9. Regularność i wymiana | Plan tygodnia w łącznym budżecie, ponowna praktyka po błędach, przenośny eksport/import tematu, samodzielny plik notatki do czytania offline, przypomnienie kalendarzowe | Eksport tematu nie zawiera historii ani danych konta. Import tworzy własną kopię z podglądem. Notatkę można czytać bez aplikacji i sieci. |
| 10. Uproszczenie i weryfikacja | Jeden start nauki i konfigurator, AI w koncie, krótsze Dzisiaj, jeden formularz celu, czytelne nazwy i import | Pełne testy regresji i migracji, testy nowych scenariuszy oraz przeglądarka desktop i telefon. |

## Decyzje dotyczące zakresu

- Pełna synchronizacja odpowiedzi offline, Web Push, wspólna edycja i odzyskiwanie hasła pozostają osobnymi projektami: wymagają protokołu synchronizacji, usługi powiadomień, uprawnień współpracy lub dostawcy poczty. W tym wydaniu ich praktyczną część realizują szkice na serwerze, plik notatki offline, przypomnienie `.ics` i wymiana pojedynczego tematu. Nie dodajemy nieaktywnych przycisków ani pozornego offline.
- Import slajdów z ilustracjami odbywa się przez PDF wyeksportowany z PowerPointa. Obsługa PPTX bez utraty układu wymaga silnika konwersji, którego obecne środowisko aplikacji nie ma. UI opisuje ten krok przed wyborem pliku. Zdjęcia są obsługiwane bez konwersji po stronie użytkownika.
- Logowanie ChatGPT na domenie zachowuje istniejący, dostępny dla projektu flow. Automatyczny callback zależy od uprawnień OpenAI; aplikacja nie może samodzielnie ich nadać. Usprawniamy powrót do pliku i wyjaśnienie stanu.
- Obecna paleta `#f4f6f9`, `#ffffff`, `#1c2944`, `#667287`, `#304bdb` i Avenir Next pozostają. Główną treścią Dzisiaj jest konkretny plan. Wyrównanie do lewej, krótkie formularze, szczegóły rozwijane; bez nowej dekoracyjnej warstwy.
- Nie dodajemy rankingów, punktów, marketplace, pełnego planu zajęć, nowego algorytmu pamięci ani automatycznej oceny wszystkich odpowiedzi przez AI.

## Weryfikacja i publikacja

Każdy etap ma testy zachowania: własność, CSRF, walidacja, powtórzenie zapisu, migracja, zachowanie historii. Ostatni przebieg obejmuje kilka celów, utratę połączenia podczas szkicu, przerwę, sprawdzian, przenoszenie i przywracanie, eksport/import oraz mały ekran. Zmiany nie czytają prywatnych `users.json`, `sets.json` ani produkcji. Rzeczywiste AI i badanie z 5–8 studentami są walidacją zewnętrzną, której testy syntetyczne nie zastąpią.

Status: etapy 1–10 wdrożone w kodzie. Weryfikacja i ograniczenia: [STUDENT_UX_VERIFICATION.md](STUDENT_UX_VERIFICATION.md). Publikacja na produkcji pozostaje odrębnym krokiem.
