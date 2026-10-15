# Weryfikacja usprawnień dla studenta

15 października 2026. Plan: [STUDENT_UX_IMPLEMENTATION_PLAN.md](STUDENT_UX_IMPLEMENTATION_PLAN.md).

## Zrealizowany zakres

Wdrożono etapy 1–10 planu w kodzie aplikacji. Migracja 009 dodaje szkice, ustawienie dziennego czasu, stany archiwum/kosza, postęp czytania, wymagania egzaminu, obrazy, ustawienia sprawdzianu i robocze pakiety tematów. Treści i dawne migawki pozostają zachowane.

Wspólny plan działa zarówno na Dzisiaj, jak i w Celach. Terminy przeterminowanych celów, dostępność dni, limity poszczególnych celów i powtórki w przyszłości mają testy regresji. Zmiana z planu dnia na wszystkie przedmioty jest jawną zmianą zakresu.

Zapis szkiców jest oddzielony od ocen, chroniony własnością, CSRF i numerem rewizji. Automatyczne zapisy i finalny formularz są wykonywane kolejno. Szkic nie odsłania wzorca, nie tworzy oceny i nie kończy sprawdzianu.

Archiwum/kosz wyłączają treści z planów i wyników wyszukiwania, a przywracanie odzyskuje je bez odtwarzania historii. Przenoszenie usuwa niepasujące powiązania. Obrazy mają osobne zasoby; edycja nie zmienia starszych migawek.

Sprawdzian ma nawigację, flagi, zmianę odpowiedzi, opcjonalny zegar i ekran zakończenia z liczbą zapisanych odpowiedzi. Wyniki i wzorce pojawiają się po zakończeniu. Puste lub niewysłane szkice pozostają bez wyniku.

## Testy

Pełny zestaw: python -m unittest discover -s tests -q.

Zestaw zawiera testy istniejącej funkcjonalności oraz scenariusze w tests/test_student_workflow.py:

- wznowienie szkicu, odświeżenie i restart;
- konflikt dwóch kart i odrzucenie nieaktualnej odpowiedzi;
- szkic quizu, kartka/odpowiedź ustna i automatyczne oznaczenie pomocy;
- szkice notatek i samodzielnego odtwarzania rozdziału;
- wspólny czas, nakładające się cele, identyczne nazwy, dostępność dni, wygasłe terminy, krótka pozostała porcja i limit liczby pytań;
- globalne trudności i filtrowanie metod przed ograniczeniem liczby pytań;
- migracja ze schematu 8 z zachowaniem ocen;
- archiwum, kosz, przenoszenie i odłączenie źródeł/wymagań;
- prywatność i migawki obrazów;
- nawigacja sprawdzianu i brak wzorców przed końcem;
- anulowanie AI, niepublikowanie wyniku po anulowaniu i wejście obrazowe;
- atomowy upload kilku plików;
- zapis samych pytań i przywrócenie opracowania z kosza;
- eksport/import tematu z obrazem, podgląd i powtórzenie zapisu;
- usunięcie nowych danych z kontem oraz eksport bez danych uwierzytelniających;
- błąd zapisu chmurowego i bezpieczne ponowienie szkicu bez ocen;
- cofnięcie błędnej oceny usuwa zaplanowaną dodatkową próbę;
- rozpiska nie przesuwa poprawnie wykonanych powtórek przed ich termin.

Dodatkowe kontrole: Ruff, Black, składnia JavaScript (node --check) i git diff --check.

## Przeglądarka

Uruchomiono lokalną aplikację z niezależną bazą /private/tmp/madra-student-workflow-preview/app.sqlite3, bez danych użytkownika i prawdziwego połączenia AI.

Wykonano:

1. Demo → mieszana sesja → błędny quiz → fiszka → odpowiedź otwarta.
2. Wpisanie odpowiedzi i natychmiastowy zapis przerwy → wznowienie → tekst zachowany również po restarcie serwera.
3. Wklejenie notatki z matematyką → utworzenie struktury → czytanie → odtworzenie z pamięci → porównanie bez automatycznej oceny.
4. Sprawdzian z trzema pytaniami i zegarem → pominięcie z flagą → wysłanie kolejnych odpowiedzi → powrót do wcześniejszej.
5. Nowy przebieg zakończenia sprawdzianu przez ekran aplikacji, bez natywnego okna potwierdzenia.
6. Formularz drugiego egzaminu i kontrola planu kilku przedmiotów.
7. Oględziny ekranów przy 390 px i w widoku desktopowym.

W toku sprawdzenia poprawiono obsługę requestSubmit przy formularzu bez zmian oraz zastąpiono natywne potwierdzenie zakończenia sprawdzianu ekranem pokazującym konsekwencje. Zrzuty znajdują się w output/student-workflow/.

## Granice tej weryfikacji

Nie używano materiałów prawdziwego użytkownika, prywatnych JSON-ów ani produkcji. Nie przełączano ruchu, nie uruchamiano wdrożenia chmurowego i nie wysyłano plików do prawdziwego AI.

Generowanie w testach korzysta z syntetycznych odpowiedzi. Realne logowanie, granty, limity i jakość opracowań wymagają oddzielnego sprawdzenia na koncie użytkownika. Anulowanie nie cofa przetwarzania już rozpoczętego przez dostawcę.

Pełna synchronizacja odpowiedzi offline, push, odzyskiwanie hasła i wspólna edycja są poza zakresem opisanym w planie. W tym wydaniu działają pobrana notatka offline, import/eksport tematu i przypomnienie kalendarzowe. Bez sieci otwarty formularz zachowuje tekst w pamięci i ostrzega przed opuszczeniem strony; zamknięcie aplikacji przed zapisem nadal może utracić te zmiany.

Pozostają wcześniejsze ostrzeżenia ResourceWarning z zasobów testowych. Ta kontrola nie jest badaniem użyteczności z rzeczywistymi studentami ani pełnym audytem dostępności.

## Wynik końcowy

- Pełny zestaw: **174 testy, wszystkie zakończone poprawnie** (w audycie przed zmianą: 129).
- Ruff, Black, składnia JavaScript i kontrola białych znaków diffu: bez błędów.
- Ostateczny widok Dzisiaj oraz Cele sprawdzono przy szerokości 390 px; Dzisiaj także przy 1440 px. Szerokość dokumentu odpowiadała szerokości okna, bez poziomego przewijania.
- Dwa cele otrzymały w obu widokach tę samą porcję: Python 7 min i biologia 10 min. Razem 17 min pozostałych ze wspólnego budżetu 20 min po wcześniejszych 3 min praktyki.
- W końcowej karcie przeglądarki nie odnotowano ostrzeżeń ani błędów konsoli.
- Zrzuty: output/student-workflow/today-desktop.png, today-mobile.png, goals-mobile.png, restored-draft-mobile.png, recall-mobile.png i exam-mobile.png. Wszystkie zawierają dane syntetyczne.

Kod i migracja są gotowe w lokalnym projekcie. Testy i podgląd korzystały wyłącznie z osobnych baz; nie wykonano migracji ani publikacji na produkcji.
