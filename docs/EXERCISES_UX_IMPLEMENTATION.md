# Wdrożenie czytelnej sekcji ćwiczeń

15 października 2026. Podstawa: [propozycja UX](EXERCISES_UX_PROPOSAL.md).

## Rezultat

- Biblioteka ma jedną rozwijaną listę, wyszukiwanie oraz prawdziwe filtry rodzaju i statusu. Pełne polecenie, ilustracja i warianty quizu są dostępne po otwarciu pytania. Edycja i archiwizacja są w dodatkowych działaniach.
- „Rozpocznij ćwiczenia” uruchamia praktykę tematu. „Rozwiąż to pytanie” tworzy zakres obejmujący dokładnie wybrany element, z kontrolą własności i archiwizacji. Rozpoczęta wcześniej sesja zachowuje dotychczasową ochronę przed przypadkowym zastąpieniem.
- Propozycje AI są jedną listą w oryginalnej kolejności. Checkbox „Zachowaj”, licznik wybranych i zaznaczanie widocznych pytań wyjaśniają zakres zapisu. Filtr nie usuwa wyboru ukrytych pytań.
- Podgląd odpowiedzi nie wymaga otwierania edycji. Wzory, kod, listy i tabele korzystają z tego samego bezpiecznego renderera co sesja. Po edycji można odświeżyć podgląd; zamknięcie edytora również go aktualizuje. Żądanie podglądu nie modyfikuje szkicu AI ani nie kontaktuje się z dostawcą.
- Pasek zapisu pokazuje liczbę ćwiczeń i dostępny w obu zakładkach wybór notatki. Brak jakiegokolwiek wyboru wyłącza zapis. Na telefonie pasek uwzględnia dolną nawigację.
- Sesja eksponuje polecenie, odpowiedź i główne działanie. Metadane i pomoc są drugorzędne. Odpowiedź na kartce lub ustnie ukrywa zbędny tekst; luka ma krótkie pole bez wyboru sposobu odpowiedzi.
- Sprawdzenie quizu atomowo zapisuje ujawnienie, wynik, postęp i ewentualną ponowną próbę. Strona wyniku zachowuje warianty, oznacza wybrany i poprawny, pokazuje tekstowy werdykt oraz „Następne pytanie”. Ostatni quiz kieruje do podsumowania. Ponowienie, odświeżenie i równoczesne sprawdzenie nie mnożą ocen.
- Zachowano cofnięcie i zamrożoną odpowiedź po ujawnieniu. Dawne, ujawnione quizy bez oceny nadal można zatwierdzić. Sprawdzian zachowuje odroczone ujawnianie wyników.
- „Nie wiem — pokaż rozwiązanie” nie wymaga pozornego tekstu. Próba jest oznaczona jako niesamodzielna i zapisywana do powtórki; nie można zamienić jej na sukces przez przesłanie wyższej oceny.
- Zachowano wartości czterech ocen i odstępy powtórek. Czytelniejsze nazwy to „Jeszcze nie”, „Częściowo”, „Samodzielnie”, „Bez trudu”; nazwy ujednolicono w podsumowaniu i postępach.

## Weryfikacja

Pełny zestaw: **182 testy, wszystkie przechodzą**. Osiem dodatkowych scenariuszy w tests/test_exercise_workspace.py obejmuje atomowy zapis quizu, równoczesne żądania, rollback całej operacji, cofnięcie, zakres jednego pytania, przełączanie sesji, niesamodzielną próbę oraz prywatny i bezpieczny podgląd. Dotychczasowe testy importu dostosowano do jednej listy, zachowując kontrolę indeksów i zapisywanej treści.

Ruff, Black, składnia JavaScript i git diff --check: bez błędów.

W przeglądarce na oddzielnej bazie syntetycznej sprawdzono:

- filtrowanie propozycji i odznaczenie wyłącznie widocznego quizu;
- edycję polecenia z matematyką i odświeżenie podglądu;
- zapis edytowanego zestawu oraz pojedynczego pytania bez notatki;
- wyłączenie zapisu przy pustym wyborze;
- listę biblioteki, warianty quizu i przełączenie rozpoczętej sesji na jedno pytanie;
- błędny quiz z zapisem wyniku i przejściem do podsumowania;
- odpowiedź na kartce, porównanie i samoocenę;
- tekstową lukę oraz odsłonięcie odpowiedzi fiszki bez wpisywania tekstu;
- widok 390 px bez poziomego przewijania i standardowy widok komputera.

Zrzuty w output/student-workflow/: exercises-after-list.png, exercises-after-feedback.png, exercises-after-feedback-mobile.png, exercises-after-self-grade-mobile.png i exercises-after-ai-mobile.png.

## Granice

Kontrole używały lokalnej bazy demonstracyjnej, bez materiałów użytkownika, produkcji i prawdziwych wywołań AI. Testy nie zastępują badania z rzeczywistymi studentami ani pełnego audytu dostępności. Nie zmieniono w tym zadaniu promptów generowania, algorytmu powtórek ani liczby stopni samooceny. Kontekstowe „Wyjaśnij prościej” i „Pokaż przykład” pozostają dalszym etapem opisanym w propozycji; obecna podpowiedź i źródła nadal działają.
