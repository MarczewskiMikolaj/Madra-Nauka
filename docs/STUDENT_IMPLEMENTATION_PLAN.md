# Rozbudowa przebiegu nauki — plan wdrożenia

13 października 2026. Zakres: wszystkie elementy wskazane w audycie studenta, bez poczty i odzyskiwania kont.

1. Addytywna migracja 008: pomoc do ćwiczeń, ustawienia sesji, odpowiedzi sprawdzianów, adnotacje ocen, zakres i dni celu, robocze importy. Dotychczasowe treści i migawki pozostają zachowane.
2. Sesje: pełny przegląd odpowiedzi, tryb trudności, jawny konflikt aktywnej sesji i zapisana przerwa. Dodatkowe ćwiczenie zapisuje nową próbę i aktualizuje prosty harmonogram; nie usuwa dawnych błędów.
3. Pomoc: trzy stopnie podpowiedzi, uzasadnienie, kryteria samooceny, informacja o użyciu pomocy i przyczynie błędu, powrót do notatki lub źródłowego PDF. Sprawdzian nie ujawnia pomocy ani wzorca przed końcem.
4. Cele i plan: wybrane tematy, ważność i dni dostępne na naukę; osobno nowy materiał, trudności, powtórki i tematy bez ćwiczeń. Te dane wpływają na dobór sesji. Plan po przerwie ogranicza porcję do wybranego czasu.
5. Próbny sprawdzian: utrwalona kolejność, zapis odpowiedzi bez feedbacku do końca, automatyczne quizy i osobna samoocena reszty. Wyniki według tematów, historia i rozróżnienie danych nieocenionych.
6. Bank pytań: import JSON/CSV/TSV oraz dwukolumnowych fiszek z podglądem, walidacją, ograniczeniem wielkości i idempotentnym zapisem. Dodatkowe opracowanie rozdziału zachowuje poprzednie materiały i używa istniejącego oryginału.
7. Czytelne treści: Markdown, tabele, kod i lokalne renderowanie wzorów. Surowy HTML oraz niebezpieczne odnośniki nie są wykonywane. Tekst źródłowy w bazie pozostaje niezmieniony.
8. Weryfikacja: stare i nowe testy, migracja ze schematu 7, izolacja kont, CSRF, ponowienia i cofanie ocen, brak wycieku odpowiedzi sprawdzianu, bezpieczne formatowanie, pełny przebieg i ekran mobilny w przeglądarce. Eksport i usuwanie kont obejmują nowe tabele.

Kryterium zakończenia: scenariusz z audytu nie pokazuje pustego planu po błędzie. Student może przejrzeć błędną odpowiedź, poćwiczyć trudności, przełączyć temat i wykonać sprawdzian bez odsłonięcia wzorca w czasie rozwiązywania. Nowe funkcje ręcznej nauki nie wymagają AI. Generowanie z pliku nadal wymaga istniejącego połączenia ChatGPT i pozostaje jawną akcją użytkownika.

Pełne offline z zapisem wyników nie było częścią ostatniej listy wdrożenia i wymaga osobnego protokołu synchronizacji. Ta rozbudowa nie tworzy pozornego trybu offline ani predykcji zdania egzaminu. Publikacja na produkcji jest odrębnym krokiem po sprawdzeniu obrazu i rzeczywistego AI.

## Realizacja i weryfikacja

Wdrożono punkty 1–8. Migracja 008 zachowuje dotychczasowe treści i strukturę podstawowych tabel. Dodatkowe dane są objęte eksportem i usuwaniem konta.

118 testów przechodzi: stary zestaw oraz scenariusze błędów, trudności, zakresu celu, dostępności, ważności tematów, zmiany/wznowienia sesji, sprawdzianu bez ujawniania odpowiedzi, importów, formatowania, migracji ze schematu 7, trwałości po restarcie i ponowień po awarii GCS. Opracowanie rozdziału zachowuje relację z oryginałem również po zakończeniu zadania AI.

W Chromium sprawdzono notatkę z matematyką, tabelą i kodem, mobilny plan, błędny quiz z uzasadnieniem, odpowiedź otwartą z kryteriami, przegląd odpowiedzi, pełny sprawdzian z osobną samooceną i import TSV z podglądem. Sprawdzone widoki mają przy 390 px szerokość dokumentu 390 px. Konsola bez błędów i ostrzeżeń. Zrzuty: `output/playwright/student/`.

Ruff, Black i kontrola składni JavaScript przechodzą. W zestawie pozostają wcześniejsze ResourceWarning dotyczące zasobów testowych w Pythonie 3.14. Nie korzystano z prawdziwych materiałów ani danych produkcji. Odpowiedzi AI są syntetyczne; dostarczane przez prawdziwe połączenie opracowania wymagają sprawdzenia jakości na materiałach użytkownika. Nie zbudowano obrazu Docker ani nie przełączono ruchu produkcyjnego.

Wzory korzystają z lokalnego KaTeX 0.16.22 z licencją i zweryfikowanym SHA-512 dystrybucji npm. Renderer ma `trust: false`, limit rozwijania makr i rozmiaru. [Dokumentacja bezpieczeństwa KaTeX](https://katex.org/docs/security). Formatowanie Markdown korzysta z wyłączonego HTML i wyłączonych obrazków. Tekst źródłowy pozostaje w bazie.
