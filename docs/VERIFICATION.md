# Weryfikacja MVP

Ostatnia weryfikacja: 14 października 2026. Starsze sekcje poniżej są zapisem poprzednich etapów i opisują ich ówczesne ograniczenia.

## Czytnik rozdziałów i kolejność nauki — 14 października 2026

- Aktualny widok: osobne zakładki notatek/źródeł i ćwiczeń w temacie oraz podglądzie importu; stały plan nad czytnikiem z linkami do rozdziałów. Jednocześnie widoczny jest jeden, zawsze rozwinięty rozdział. Plan nie jest numerowany jako rozdział. 129 testów przechodzi; w przeglądarce sprawdzono przełączanie zakładek/rozdziałów, bezpośrednie hashe oraz szerokość 390 px bez poziomego przewijania.
- Naprawiono puste karty powodowane przez śródtytuły zapisane na tym samym poziomie Markdown co tytuły rozdziałów. Nowy zapis rozdziela te poziomy; czytnik uwzględnia hierarchię nagłówków, CRLF i bloki kodu oraz scala starsze puste nagłówki nadrzędne z ich treścią.
- Nowe generowanie przyjmuje `learning_order` jako permutację indeksów rozdziałów. Aplikacja układa według niej notatkę i sama tworzy zgodny plan. Gdy model pomija pole, plan powstaje z faktycznej kolejności rozdziałów.
- Sprawdzono render zapisanej notatki Oracle: 8 kart z treścią, bez pustych kart nadrzędnych. Dane w bazie i historyczna tekstowa propozycja kolejności nauki pozostają zachowane; dla starego płaskiego zapisu granice końcowych sekcji nie zawsze dają się jednoznacznie odzyskać.
- Testy obejmują zagnieżdżone śródtytuły, przykłady Markdown w kodzie, starszy płaski format, poprawność permutacji i generowanie planu z ukończonej odpowiedzi AI. Odpowiedzi AI w testach są syntetyczne.

## Rozbudowa z perspektywy studenta — 13 października 2026

118 testów przechodzi po migracji 008 i wdrożeniu pełnego przebiegu: historia odpowiedzi, trudności, pomoc i źródła, zakres/dni/ważność celu, sprawdzian, importy i formatowanie treści. Szczegóły zakresu, testów, sprawdzonych widoków i ograniczeń: [STUDENT_IMPLEMENTATION_PLAN.md](STUDENT_IMPLEMENTATION_PLAN.md#realizacja-i-weryfikacja). Poprzednie liczby testów poniżej opisują wcześniejsze etapy.

## Pierwsze stabilne wydanie — 2.0.0

- 98 testów przechodzi w lokalnym Pythonie 3.14; przed zmianami przechodziło 81. CI obejmuje Python 3.12 i 3.14, ale nie uruchamiano go zdalnie w tej sesji.
- Nowe testy sprawdzają rejestrację i logowanie e-mailem, walidację i unikalność adresów oraz natychmiastową aktywację konta. Obsługa poczty i weryfikacja adresu są całkowicie usunięte z kodu zgodnie z życzeniem użytkownika.
- Biblioteka: wyszukiwanie treści z polskimi literami i escapingiem, izolacja kont, archiwum i przywrócenie bez utraty historii.
- Cele: edycja, walidacja, tygodniowa rozpiska i usuwanie bez naruszenia materiałów.
- Dane: ZIP zachowuje bajty oryginałów i pomija dane uwierzytelniające; kopia SQLite ma prawa 0600, przechodzi kontrolę integralności i daje się ponownie otworzyć. Próba nadpisania istniejącej kopii jest odrzucana. To próba na syntetycznej bazie, nie odtworzenie produkcji.
- Konto: usuwanie po potwierdzeniu hasła i nazwy, brak dostępu po usunięciu, zachowanie innych kont, brak sierot relacyjnych, blokada podczas AI i przy podłączonym ChatGPT. Nowe dane i usuwanie sprawdzono również na syntetycznym GCS, w tym błąd zapisu.
- Błędy: limit prób jest atomowy dla równoległych żądań i działa również przy zmienianiu nazw. Zapis ze starej sesji jest odrzucany. Cofnięcie oceny przy jednakowych timestampach wskazuje ostatnie zdarzenie; ponowienie nie usuwa poprzedniej odpowiedzi.
- Ruff, Black, `node --check madra/static/app.js` i `git diff --check` przechodzą. Testy w Pythonie 3.14 emitują również ResourceWarning dotyczące zamykania zasobów testowych; nie są błędami wyniku zestawu.
- Migracja 007 została sprawdzona od istniejącego schematu 6; dawne konto i logowanie nazwą pozostają zachowane.
- Przeglądarka Chromium: rejestracja, edycja celu, przywracanie ćwiczenia, wyszukiwanie i ustawienia konta. Cele obejrzano na desktopie 1440 px i telefonie 390 px. Sprawdzone mobilne widoki tematu i konta mają `scrollWidth == innerWidth == 390`; konsola bez błędów i ostrzeżeń.
- Zrzuty obejrzane lokalnie: `output/playwright/release/goals-desktop.png`, `goals-mobile.png`, `account-mobile.png`; dodatkowo zapisano archiwum i wyniki wyszukiwania.
- Graf struktury aktywnej aplikacji wygenerowano przez graphify w `output/graphify-release/`. Dawny graf w katalogu głównym opisuje starszy kod i pozostał nietknięty.
- Nie zmieniano `sets.json`, `users.json` ani danych produkcji. Przeglądarka używa osobnej bazy w `/private/tmp/`.

Rzeczywiste OpenAI nie było używane w nowych testach. Brak Dockera w środowisku uniemożliwił sprawdzenie obrazu. Nie wykonano publikacji ani przełączenia ruchu. Instrukcja tych kroków i warunków znajduje się w [RELEASE.md](RELEASE.md).

Data wcześniejszego MVP: 11 października 2026.

## Wynik

MVP opisane w [PLAN.md](PLAN.md) zostało zaimplementowane. Przebudowa korzysta z Flask, modułów domenowych i transakcyjnej bazy SQLite. Oryginalna implementacja znajduje się w `legacy/`; pliki źródłowe `sets.json` i `users.json` pozostały bez zmian.

## Kontrole automatyczne

- 28 testów integracyjnych zakończonych sukcesem: `python -m unittest discover -s tests -v`.
- Testy wykonane w osobnym środowisku Python 3.13 po instalacji aktualnego `requirements.txt`.
- Pokryte zachowania: pełny przebieg nauki i trwałość danych, izolacja kont, CSRF, logowanie i ograniczenie prób, sesje mieszane, limit kolejki, migawki treści, ocena quizu na serwerze, ponowienia i równoległe wysłanie oceny, cofnięcie oceny, transakcje i awaria zapisu, archiwizacja, eksport, import dawnych kont i zestawów, strefa czasowa Warszawy oraz konfiguracja produkcyjna.
- Black, Ruff i sprawdzenie składni JavaScript zakończone sukcesem.
- Konfiguracja Gunicorn sprawdzona przez `--check-config`.
- `git diff --exit-code -- sets.json users.json` potwierdził brak modyfikacji dawnych danych.

Testy używają syntetycznych danych i tymczasowych baz, bez odczytywania danych prawdziwych użytkowników.

## Przeglądarka

W lokalnym Chromium zweryfikowano:

1. Wejście do izolowanego demo, widoki biblioteki, sesji i postępów.
2. Ukończenie sesji z pięcioma typami ćwiczeń: quizem, pytaniem otwartym, zadaniem, fiszką i luką.
3. Rejestrację własnego konta, dodanie przedmiotu, tematu, notatki, zadania i celu; wykonanie sesji oraz odczyt zapisanej historii w postępach.
4. Wygląd na desktopie 1440 px i telefonie 390 px. Na sprawdzonym ekranie mobilnym szerokość dokumentu odpowiadała szerokości okna; bez przewijania w poziomie.

Zrzuty zapisano lokalnie w ignorowanym przez Git `output/playwright/`, m.in. `today-desktop.png`, `study-mobile.png`, `summary-mobile.png`, `own-topic-mobile.png`, `own-progress-mobile.png`. Zostały obejrzane podczas weryfikacji.

Przebieg tworzenia ćwiczenia wykrył nieprawidłową wartość domyślną pola liczbowego po formatowaniu szablonu. Poprawiono białe znaki makra i dodano test regresji. Pełny przebieg powtórzony na poprawionej wersji zakończył się sukcesem.

## Granice weryfikacji i dalsze kroki

- Nie zbudowano obrazu Docker: środowisko nie ma dostępnego Dockera. Sprawdzono konfigurację Gunicorn, ale potrzebny jest osobny test obrazu i trwałego wolumenu przed wdrożeniem.
- Nie przeprowadzono testów obciążeniowych, audytu dostępności ani migracji prawdziwych danych. Import pozostaje jawną operacją z domyślnym podglądem.
- Nie wdrożono aplikacji ani nie wypchnięto zmian na GitHub. Workflow CI jest przygotowany, ale nie został uruchomiony zdalnie.
- SQLite wymaga trwałego dysku i pojedynczej instancji. Dotychczasowy efemeryczny hosting Cloud Run wymaga zmiany sposobu przechowywania danych przed wdrożeniem.
- Interpretacja AI, OCR skanów, audio, współdzielenie, pełne offline, powiadomienia oraz odzyskiwanie hasła są kolejnymi etapami planu.

## Rozszerzenie: pliki i generowanie materiałów

- 36 testów integracyjnych zakończonych sukcesem po dodaniu uploadów. Nowe testy obejmują TXT/MD, DOCX, PDF z tekstem, zaszyfrowane i puste PDF, błędne formaty, limity, timeout parsera, CSRF, izolację właściciela, pobieranie oryginału, usuwanie propozycji, zapis do nowego przedmiotu i brak duplikatów po ponowieniu zapisu.
- W przeglądarce wgrano syntetyczny Markdown, zmieniono nazwę i pytanie, odznaczono jedno ćwiczenie i zapisano materiały w nowym temacie. Podgląd i zapis obejrzano na telefonie; brak przewijania w poziomie.
- Zrzuty: `output/playwright/upload-preview-mobile.png`, `output/playwright/upload-saved-mobile.png`.
- Ograniczenie: propozycje powstają z fragmentów tekstu, bez AI i OCR. Ekstrakcja nie odtwarza układu stron ani grafik.

## Rozszerzenie: ChatGPT i opracowanie AI

50 testów przeszło po integracji. Nowe testy sprawdzają PKCE, wspólny identyfikator hosta, szyfrowanie i prawa plików z tokenami, walidację podpisu JWT/issuer/audience/nonce/expiry, odrzucenie nieprawidłowego state i replay, osobną zgodę na użycie planu, rotację tokenów, cytaty ze źródła, strukturę quizów, pełne ukończenie streamu, zachowanie poprzednich propozycji po awarii, zapis quizu AI, izolację kont i CSRF. Dynamiczne logowanie loopback jest wyłączone w konfiguracji produkcyjnej.

Testy integracji z OpenAI używają syntetycznych tokenów i odpowiedzi. Nie wykonano rzeczywistego generowania z abonamentu: wymagane jest logowanie i zgoda właściciela konta. Jakość wyników wymaga sprawdzenia na jego materiałach po połączeniu. Generowanie nie tworzy jeszcze kalendarza nauki z terminem egzaminu.

Przeglądarka: ekran połączenia został obejrzany. Wykryto blokadę przekierowania OAuth przez CSP i dodano wyłącznie oficjalną domenę `auth.openai.com` do `form-action` oraz test regresji. Przekierowanie do tej domeny działa; automatyczna przeglądarka zatrzymała się na ochronie dostępu OpenAI (HTTP 403 „Just a moment”). Nie próbowano jej obchodzić. Logowanie wymaga interaktywnej przeglądarki użytkownika i nadal nie zostało zweryfikowane do końca.

## Analiza oryginalnych plików — 11 października 2026

55 testów przeszło. Żądanie AI zawiera pełny oryginał w `input_file.file_data`, a PDF ma `detail=high`; nie ma lokalnej transkrypcji ani heurystycznego generatora. Test dwustronicowego PDF sprawdza niezmienione bajty załącznika i wskazanie diagramu na drugiej stronie. Testy obejmują skany PDF, brak notatek/ćwiczeń przed analizą AI, zapis jednej notatki, izolację kont i zachowanie poprzedniego wyniku po awarii. Migracja 004 usuwa kolumnę wyciągniętego tekstu i niezapisane lokalne propozycje, zachowując oryginały i opracowania AI.

Odpowiedzi OpenAI w testach są syntetyczne. Testy potwierdzają sposób wysyłania plików i obsługę wyników, a nie jakość rzeczywistych opracowań. Cytaty/opisy ilustracji są wskazaniami modelu; aplikacja nie przedstawia ich jako niezależnie zweryfikowanych.

## Postęp AI bez limitu czasu

57 testów przeszło. Test streamu potwierdza brak timeoutu i etapy na podstawie `response.created`, `response.output_text.delta` oraz walidacji po ukończeniu. Test widoku postępu potwierdza odczyt zapisanego etapu i liczby znaków; test awarii sprawdza trwały komunikat w podglądzie pliku i bibliotece. Migracja 005 dodaje postęp do zadania.

## Rzeczywista diagnostyka limitu planu

Ponowienie ostatniego zadania przez połączone konto wykazało zdarzenie `error` z kodem `subscription_sharing_usage_limit_exceeded`, przed otrzymaniem tekstu odpowiedzi. Pierwotna obsługa czytała tylko `response.error.code`, przez co gubiła kod z wydarzenia najwyższego poziomu. Poprawka rozpoznaje obie struktury, zagnieżdżone `error` i `incomplete_details.reason`; pokazuje konkretny komunikat oraz link do ustawień Usage. Nie zakłada wyczerpania całego abonamentu ani czasu resetu. 58 testów przeszło. Rzeczywiste generowanie pozostaje zablokowane przez limit zgłoszony przez dostawcę.
