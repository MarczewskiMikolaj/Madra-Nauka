# Mądra Nauka 2.0.0

Osobiste centrum nauki po polsku: przedmioty, tematy, notatki, linki i różne metody ćwiczenia. Plan dnia łączy pytania otwarte, zadania, quizy, luki i fiszki w jedną sesję.

Nawigacja została uproszczona do **Nauka** i **Materiały**. Cele i historia rozwijają się na ekranie nauki, a tematy otwierasz bezpośrednio z materiałów. [Opis uproszczenia](docs/SIMPLIFIED_NAVIGATION.md).

Aktualny przebieg studenta: [plan wdrożenia](docs/STUDENT_UX_IMPLEMENTATION_PLAN.md) i [wyniki weryfikacji](docs/STUDENT_UX_VERIFICATION.md). Aktualizacja z 15 października 2026 rozszerza opisane niżej pierwsze MVP. Przebudowę list, podglądu AI i rozwiązywania opisuje [wdrożenie sekcji ćwiczeń](docs/EXERCISES_UX_IMPLEMENTATION.md).

Plan pierwszego stabilnego wydania i audyt braków: [docs/RELEASE_PLAN.md](docs/RELEASE_PLAN.md). Instrukcja publikacji i kopii: [docs/RELEASE.md](docs/RELEASE.md).

Pełna wizja produktu, zakres MVP, model danych, migracja i dalsze etapy: [docs/PLAN.md](docs/PLAN.md).

## Uruchomienie

Python 3.12 lub nowszy. Nowa aplikacja nie wymaga Google Cloud ani klucza szyfrowania do lokalnego uruchomienia.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Otwórz http://127.0.0.1:8080. Załóż konto albo wybierz **Wypróbuj na przykładzie**. Każde demo tworzy osobne konto z materiałami z biologii, Pythona i angielskiego. Konto demo jest dostępne przez bieżącą sesję przeglądarki; po wylogowaniu nie można się do niego ponownie zalogować. Do własnej pracy załóż zwykłe konto.

Przy pierwszym uruchomieniu aplikacja tworzy bazę `instance/madra.sqlite3` i lokalny losowy klucz sesji `instance/secret.key`. Zachowaj ten katalog, aby zachować dane i sesje. Pliki są ignorowane przez Git. Alternatywny port: `PORT=8081 python app.py`.

## Działające MVP

- rejestracja z e-mailem, logowanie adresem lub nazwą, wylogowanie i oddzielne dane użytkowników;
- ustawienia konta: zmiana nazwy do logowania, zmiana hasła z potwierdzeniem obecnego i wylogowaniem pozostałych sesji, wgrywanie oraz usuwanie awatara;
- biblioteka przedmiotów i tematów; wyszukiwanie także tematów, notatek, linków i ćwiczeń;
- notatki tekstowe i linki HTTP/HTTPS;
- pięć typów ćwiczeń, edycja z zachowaniem ID i historii, archiwum z przywracaniem;
- mieszane sesje z czasem 1–180 minut, plan dnia dla kilku celów lub nauka konkretnego przedmiotu/tematu;
- quiz oceniany na serwerze; odpowiedzi otwarte, zadania i luki z porównaniem i samooceną;
- wynik zapisany od razu, bez duplikatów przy ponowieniu; cofnięcie ostatniej oceny;
- wznowienie sesji z niezmienną kolejnością i migawką treści;
- proste terminy powtórek, edycja i usuwanie celów z datą i dziennym czasem, tygodniowa rozpiska pierwszego przejścia materiału;
- statystyki trzech wymiarów nauki, aktywność tygodniowa i historia sesji;
- eksport JSON oraz ZIP z oryginalnymi plikami, usuwanie własnego konta i danych, administracyjne kopie bazy, jawny import danych poprzedniej wersji;
- responsywny interfejs, CSRF, escaping treści i ograniczenie prób logowania.

Statystyki są wskaźnikiem zarejestrowanych ocen, a nie pomiarem gotowości do egzaminu. Plan wybiera powtórki, nowe ćwiczenia, a gdy nie ma zaległości — dodatkowe utrwalenie. Czas jest szacunkowy; pojedyncze zadanie może być dłuższe od wybranego krótkiego budżetu. Harmonogram jest prostą regułą, nie FSRS.

Audio, push, pełna synchronizacja offline, wspólna edycja i reset hasła e-mailem należą do kolejnych etapów. Wymianę tematów, pobraną notatkę offline i wspólny plan kilku celów opisuje aktualizacja poniżej. Opracowanie wgranych materiałów wymaga połączenia ChatGPT; ręczne materiały i nauka działają lokalnie. Poprzedni service worker jest wyrejestrowywany, a stare cache HTML czyszczone — nowa aplikacja wymaga połączenia z serwerem.

## Struktura

```text
app.py                 punkt uruchomienia
madra/                 aktywna aplikacja
  auth.py              konta i CSRF
  library.py           materiały i ćwiczenia
  study.py             sesje i transakcyjny zapis
  planning.py          plan dnia, cele, statystyki, eksport
  db.py                połączenia i migracje SQLite
  services/            harmonogram, demo i import
  migrations/          wersjonowany schemat
  templates/           wspólny layout i ekrany
  static/              CSS i mały moduł JS
tests/                 testy na sztucznych danych
docs/PLAN.md           plan rozwoju
legacy/                kod poprzedniej wersji do porównania
```

## Testy

```bash
python -m unittest discover -s tests -v
```

Testy używają tymczasowych baz i syntetycznych materiałów. Weryfikują pełny przebieg, izolację kont, CSRF, edycję w czasie sesji, zapis równoczesnych odpowiedzi, rollback po błędzie, cofnięcie oceny, harmonogram, eksport i import. Nie czytają lokalnych plików danych ani produkcji.

## Import poprzedniej wersji

Źródłowe `sets.json` i `users.json` pozostają bez zmian. Najpierw wykonaj kopię danych. Import jest domyślnie podglądem:

```bash
flask --app app import-legacy --sets sets.json --users users.json
```

Jeśli użytkownicy są zaszyfrowani, ustaw `LEGACY_ENCRYPTION_KEY` na stary klucz Fernet w środowisku. Nie zapisuj klucza w repo. Dopiero po sprawdzeniu podglądu:

```bash
flask --app app import-legacy --sets sets.json --users users.json --apply
```

Możesz także przypisać zestawy do wcześniej założonego konta:

```bash
flask --app app import-legacy --sets sets.json --owner "Moja nazwa"
flask --app app import-legacy --sets sets.json --owner "Moja nazwa" --apply
```

Każdy stary zestaw staje się przedmiotem z tematem i fiszkami. Hash hasła jest przenoszony bez znajomości hasła. Dawne statystyki i pełna historia zestawu są zachowane jako metadane źródłowe w eksporcie; nowy dziennik odpowiedzi zaczyna się od nowych sesji. Import nie fabrykuje zdarzeń ze starych agregatów. Powtórny import tego samego zestawu nie tworzy duplikatu. Konflikt kont lub brak właściciela zatrzymuje import.

## Konfiguracja i wdrożenie

| Zmienna | Znaczenie |
|---|---|
| `PORT` | Port lokalnego serwera, domyślnie 8080 |
| `MADRA_DATABASE_PATH` | Pełna ścieżka do bazy SQLite |
| `SECRET_KEY` | Stały, losowy sekret sesji; wymagany w produkcji |
| `MADRA_ENV=production` | Wymaga sekretu, włącza secure cookies i wyłącza publiczne demo |
| `LEGACY_ENCRYPTION_KEY` | Klucz do jawnego importu dawnych użytkowników |

Lokalnie SQLite wymaga trwałego dysku. Na Cloud Run ustaw `MADRA_STATE_BUCKET`: aplikacja pracuje na niezależnych bazach w pamięci i po każdej transakcji atomowo zapisuje kompletny stan w Cloud Storage. Warunek generacji GCS odrzuca zapis ze starej wersji zamiast nadpisywać nowsze dane. Nowe żądania pobierają aktualny stan. Nie montujemy SQLite przez GCS FUSE. To prosty wariant dla małego MVP; koszt i czas przesyłania rosną wraz z bazą i liczbą plików. Dla większej aplikacji docelowo PostgreSQL i osobne obiekty plików.

Dockerfile uruchamia Gunicorn jako użytkownik bez uprawnień administratora. Podłącz trwały wolumen do `/data`, przekaż `SECRET_KEY` przez konfigurację środowiska i zapewnij HTTPS przez reverse proxy. Obraz kopiuje wyłącznie aktywną aplikację i zależności; lokalne JSON-y i baza nie są do niego dołączane.

Cloud Run: projekt `python-fiszki`, region `europe-west4`, usługa `python-fiszki`, bucket `python-fiszki-users`. Obiekty nowej wersji trafiają pod `madra-v2/`; stare dane nie są importowane ani nadpisywane. Przy tej konfiguracji dotychczasowy `ENCRYPTION_KEY` może pełnić rolę stałego sekretu, jeżeli nie ustawiono `SECRET_KEY`. Zmiana sekretu uniemożliwi odczyt zapisanych połączeń.

`scripts/deploy-cloud.sh` buduje obraz i wdraża go z tagiem bez przełączania ruchu. Konfiguracja: jedna instancja, jeden worker Gunicorn, 1 GiB RAM, stale przydzielany CPU i minimalnie jedna instancja dla zadań AI w tle. Powoduje to opłaty za działającą instancję także poza żądaniami; nie tworzymy Cloud SQL. Restart platformy może przerwać generowanie; heartbeat pozwala wykryć przerwany worker bez limitowania całkowitego czasu AI. Po sprawdzeniu tagowanej wersji przełącz ruch na jej konkretną rewizję. Trigger GitHuba aktualizuje potem obraz po pushu na `main`, zachowując konfigurację usługi.

## Materiały z plików

W Bibliotece wybierz **Wgraj plik** albo użyj przycisku w istniejącym temacie. Obsługiwane są PDF (także skany), DOCX, TXT, Markdown i zdjęcia PNG/JPG/WebP, do 5 plików naraz. Limit to 10 MB na plik, 100 stron PDF i 16 megapikseli na zdjęcie; TXT/MD wymagają UTF-8. Zaktualizuj zależności: `pip install -r requirements.txt`.

Aplikacja sprawdza format i przechowuje oryginał. Nie wyciąga tekstu, nie tworzy transkrypcji ani lokalnych pytań z fragmentów. Dopiero po uruchomieniu AI powstają notatka i ćwiczenia. Podgląd pozwala poprawić wynik i wybrać ćwiczenia przed zapisem. Zapis tworzy jedną notatkę AI i wybrane ćwiczenia; ponowienie zapisu nie tworzy duplikatów.

Oryginały są przechowywane w SQLite jako BLOB i dostępne wyłącznie właścicielowi. Eksport JSON zawiera opracowania i połączenia źródłowe, bez binarnego oryginału (pobierz go osobno). Walidator działa w osobnym procesie z limitem czasu i CPU; Linux dodatkowo ogranicza pamięć. Zaszyfrowany PDF lub uszkodzony dokument są odrzucane. Migracja 004 usuwa dawną kolumnę z wyciągniętym tekstem i niezapisane lokalne propozycje, zachowując pliki i opracowania AI.

## Opracowanie AI z planu ChatGPT

Aplikacja obsługuje oficjalny flow **Sign in with ChatGPT** dla aplikacji open source. Uprawnione konta Plus i Pro mogą zatwierdzić używanie swojego planu; dostępność i limity określa OpenAI. Samo logowanie nie wystarcza — potrzebny jest grant `chatgpt.tokens.use.direct`. Nie jest używany płatny klucz API ani automatyczny fallback do rozliczenia API.

1. Wybierz **Połącz ChatGPT** w menu konta lub podglądzie pliku.
2. Zaloguj się na stronie OpenAI i zatwierdź użycie planu. Callback lokalny to `http://127.0.0.1:<PORT>/auth/callback`. Używaj `127.0.0.1`, nie `localhost`.
3. Wróć do wgranego pliku. Model jest ustawiony na GPT-5.6 Terra; wpisz cel i wybierz **Przygotuj materiały z AI**.
4. Opracowanie w tle zastępuje propozycje po ukończeniu i walidacji: objaśnienia, przykłady, wskazówki i do 20 ćwiczeń (pięć dostępnych typów). Ćwiczenia zawierają wskazania stron/sekcji oraz cytaty lub opisy tabel i ilustracji podane przez AI. Aplikacja sprawdza strukturę odpowiedzi, a nie prawdziwość tych wskazań — przejrzyj je w oryginalnym pliku.

Cały oryginalny plik (inline `input_file.file_data`, bez Files upload API) i cel są wysyłane do OpenAI dopiero po uruchomieniu generowania. PDF jest analizowany jako tekst i obrazy stron z `detail=high`. DOCX/TXT/MD są odczytywane tekstowo przez OpenAI; dokumenty z istotnymi ilustracjami należy dostarczyć jako PDF. Nie ma automatycznego powrotu do analizy transkrypcji przy błędzie. Lokalna kopia oryginału pozostaje w bazie. Tokeny nie trafiają do cookies, JSON eksportu ani logów: chronione są szyfrowaniem opartym na `SECRET_KEY` oraz plikami 0600 w katalogu `chatgpt/` obok bazy. Zachowaj klucz przy restarcie; jego zmiana unieważnia możliwość odczytu połączeń. Katalog i kopie zapasowe zawierają poufne dane. Odłączenie usuwa tokeny lokalnie i próbuje odwołać sesję po stronie OpenAI.

Generowanie korzysta z Responses API: `store=false`, `stream=true`, bez nieobsługiwanych parametrów. Sukces wymaga zdarzenia `response.completed`; limit abonamentu, przerwanie i niepoprawny JSON pozostawiają poprzednie propozycje. Zlecenia działają w wątkach jednej instancji; restart oznacza błąd i możliwość ponowienia. Przed wdrożeniem wieloinstancyjnym przenieś je do trwałej kolejki. Dynamiczny flow loopback jest domyślnie wyłączony w `MADRA_ENV=production` — nie stanowi gotowej integracji publicznego serwisu.

Źródła integracji: [quickstart](https://developers.openai.com/siwc/quickstart), [rejestracja i autoryzacja](https://developers.openai.com/siwc/token-sharing-open-source/sign-in), [modele i generowanie](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference), [ograniczenia preview](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations).

Generowanie nie ma limitu całkowitego czasu ani timeoutu połączenia. Oczekujemy na ukończenie streamu lub błąd dostawcy. Ekran postępu aktualizuje się co 3 sekundy: wysyłanie pliku, przetwarzanie przez OpenAI, tworzenie odpowiedzi, walidacja. Pokazuje czas oczekiwania i liczbę znaków odpowiedzi. To etapy wynikające ze zdarzeń streamu, bez fikcyjnego procentu i postępu stron. Można opuścić ekran; zadanie działa w tle. Restart serwera nadal przerywa jego wątki. Biblioteka i podgląd pliku pokazują ostatni błąd oraz możliwość ponowienia. Logi zawierają identyfikator zadania, etap, czas, liczbę znaków i status HTTP błędu, bez pliku, celu i tokenów.


Wynik AI i zapisany temat mają menu rodzajów materiałów z licznikami oraz osobne sekcje pytań otwartych, quizów, zadań, fiszek i luk. Podgląd umożliwia zaznaczanie całych grup, a notatkę pokazuje do czytania z osobno rozwijaną edycją. Nowe generowanie domyślnie prosi o obszerną notatkę (zwykle 12–30 tys. znaków dla wielostronicowego źródła, maksymalnie 45 tys.), z tematami, objaśnieniami, rozwiązanymi przykładami i podsumowaniem; długość zależy od zakresu źródła. Dotychczasowe opracowania nie są automatycznie generowane ponownie.

Nowe opracowania AI zwracają rozdziały z tytułami i treścią, zapisane w edytowalnej notatce. Czytnik pokazuje spis treści oraz rozwijane rozdziały. Dostępny jest przed zapisem, po zapisie na ekranie pliku oraz jako osobna strona notatki z biblioteki. Starsze notatki z nagłówkami korzystają z nich, a długie notatki bez nagłówków są grupowane według akapitów do prezentacji; treść w bazie pozostaje bez zmian.

Generowanie zawsze używa `gpt-5.6-terra`. Model z formularza jest ignorowany przez backend. Brak Terra w katalogu konta blokuje generowanie z czytelnym komunikatem, bez przełączania na inny model.

### Logowanie ChatGPT na domenie

`MADRA_PUBLIC_URL=https://madranauka.online` włącza połączenie chmurowe. Callback OpenAI pozostaje `http://127.0.0.1:8085/auth/callback`, zgodnie z flow OSS. Logowanie otwiera się w nowej karcie. Po zatwierdzeniu w OpenAI, jeśli przeglądarka pokazuje niedostępny adres loopback, użytkownik może wrócić do Połączenia AI i wkleić pełny adres w sekcji „Dokończ połączenie”. Adres jest przekazywany POST-em z CSRF, a serwer weryfikuje dokładny origin i ścieżkę, state, PKCE, nonce, podpis oraz tożsamość. Nie pobiera wklejonego URL. Kod nie trafia do logów URL. To ręczne dokończenie, nie automatyczny callback na domenę; internetowy wariant integracji wymaga odpowiedniego dostępu OpenAI.

Tutorial Pythona, przycisk pobierania pomocnika i dodatkowa lokalna zgoda zostały usunięte z UI. Istniejący endpoint pomocnika i relay obsługują wcześniej pobrane pomocniki. Zgoda na użycie planu jest sprawdzana na podstawie scope przyznanego przez OpenAI. Nie używamy klucza API ani automatycznego fallbacku płatności. Zaszyfrowane połączenia przechowywane są w prywatnych obiektach GCS.

## Rejestracja e-mailem

Nowe konta wymagają nazwy, adresu e-mail i hasła. Logowanie przyjmuje adres lub nazwę. Istniejące konta nie muszą podawać adresu i nadal logują się nazwą. Adres jest unikalny bez rozróżniania wielkości liter. Odzyskiwanie konta nie należy do tego wydania.

Rejestracja od razu aktywuje konto i loguje użytkownika. Adres służy do logowania; aplikacja nie wysyła wiadomości ani nie weryfikuje własności skrzynki. Nie wymaga konfiguracji poczty.

## Archiwum i usuwanie danych

W ustawieniach konta **Pobierz archiwum z oryginalnymi plikami** zapisuje ZIP: `data.json`, oryginały w `originals/` z zachowaniem nazw i opcjonalny awatar. JSON zawiera mapowanie źródeł do plików. Eksport pomija hasła, tokeny ChatGPT i tokeny potwierdzenia. ZIP służy do pobrania danych; automatyczny import tego archiwum nie jest zaimplementowany. Dotychczasowy eksport JSON pozostaje dostępny.

Usunięcie konta wymaga obecnego hasła oraz wpisania nazwy. Usuwa bieżące dane konta, w tym pliki i historię. Aktywne zadanie AI blokuje operację; połączenie ChatGPT trzeba wcześniej odłączyć. Kopie administratora mają osobną retencję. Konto demonstracyjne kończysz przez wylogowanie.

## Pełny przebieg nauki studenta

Plan i wyniki rozbudowy: [docs/STUDENT_IMPLEMENTATION_PLAN.md](docs/STUDENT_IMPLEMENTATION_PLAN.md). Audyt wyjściowy: [docs/STUDENT_AUDIT.md](docs/STUDENT_AUDIT.md).

- **Tryby nauki / sprawdzian** w temacie i przedmiocie pozwalają wybrać naukę, trudności albo próbny sprawdzian, 5/10/20/30/60 minut oraz rodzaje pytań. Trudności wybierają ostatnie oceny 0–1 także przed terminem powtórki. Każda oceniona próba zapisuje nową historię i aktualizuje prosty harmonogram. „Trudno” skraca poprzedni odstęp; „jeszcze raz” ustawia jutro.
- Podsumowanie zawiera pełne pytania, własne odpowiedzi, wzorce, wyjaśnienia, źródła oraz wyniki według tematów. Historia w Postępach ma strony, więc można wrócić również do starszych sesji.
- Edycja ćwiczenia ma do trzech podpowiedzi, uzasadnienie, kryteria samooceny i odnośnik do własnego materiału/rozdziału. Pomoc i adnotacja przyczyny trudności są opcjonalne. Migawka sesji zachowuje ówczesne treści. Źródła są odnośnikami do bieżących materiałów; wskazania stron AI wymagają sprawdzenia.
- Zmiana zakresu przy aktywnej sesji pokazuje wybór: kontynuować ją albo zapisać przerwę i przejść do nowej. Zapisane przerwy można wznowić z Dzisiaj i historii.
- **Próbny sprawdzian** zapisuje odpowiedzi bez wzorców i podpowiedzi do końca. Quizy są wtedy oceniane automatycznie, reszta wymaga osobnej samooceny. Wcześniejsze zakończenie pokazuje liczbę nierozwiązanych pytań. Przerwa nie ujawnia wzorców. Ocenione odpowiedzi aktualizują harmonogram; nieocenione odpowiedzi otwarte nie zmieniają postępu.
- Edycja celu pozwala wybrać tematy, ważność 1–3 i dni nauki. Domyślny plan Dzisiaj i globalna sesja korzystają z najbliższego niezakończonego celu; można jawnie wybrać wszystkie przedmioty. Szacunek obejmuje nowe pytania, trudności i najbliższe zaplanowane powtórki. Tematy bez ćwiczeń są pokazane jako niesprawdzone. To plan najbliższych prób, nie predykcja zdania egzaminu.
- **Dodaj wiele ćwiczeń** obsługuje JSON/CSV/TSV oraz dwukolumnowe fiszki (także tekstowy eksport Anki; nie plik `.apkg`). Limit: 1 MB i 200 pytań. Podgląd poprzedza zapis; ponowienie zapisu nie tworzy duplikatu. JSON zawiera tablicę obiektów `kind`, `prompt`, `answer`, opcjonalnie `options`, `minutes`, `hints`, `explanation`, `rubric`. CSV z nagłówkami używa tych samych pól; opcje i podpowiedzi rozdziela `|`. Bez nagłówków potrzebne są dokładnie dwie kolumny: pytanie i odpowiedź.
- Na zapisanym opracowaniu pliku wybierz rozdział, aby przygotować kolejną analizę bez ponownego uploadu. Aplikacja tworzy osobne opracowanie z kopią oryginału i zachowuje poprzednie materiały. Dopiero przycisk generowania wysyła pełny plik oraz cel do istniejącego połączenia ChatGPT. Powielone kliknięcie przygotowania tego samego niezapisanego rozdziału wznawia jego szkic. Każde opracowanie nadal ma limit 20 ćwiczeń, ale temat może zawierać wiele opracowań i pytań ręcznych.

Notatki i treści ćwiczeń obsługują Markdown, tabele, bloki kodu oraz wzory `$...$` i `$$...$$`. KaTeX, CSS i fonty są dołączone lokalnie (`madra/static/vendor/katex/`); nie korzystają z zewnętrznego CDN. Surowy HTML i obrazki Markdown nie są wykonywane. Kod jest wyświetlany, nie uruchamiany. Zaktualizuj zależności przez `pip install -r requirements.txt`. Migracja 008 tworzy tabele pomocnicze bez zmiany istniejących treści i migawkowanych sesji. Eksport i usuwanie konta obejmują nowe dane.

## Usprawnienia dla studenta — 15 października 2026

- **Szkice bez utraty pracy.** Odpowiedzi, wybór quizu i edycja notatek zapisują się na serwerze podczas pisania. „Zapisz przerwę” zachowuje bieżący szkic również bez JavaScript. Szkic nie odsłania odpowiedzi ani nie nalicza próby. Inna karta z nieaktualnym szkicem dostaje konflikt; tekst trzeba zachować przed odświeżeniem. Bez sieci otwarta strona zachowuje tekst w pamięci i ostrzega przed wyjściem, ale nie obiecuje zapisu offline.
- **Jeden budżet dnia.** Na Dzisiaj ustalasz łącznie 5–180 minut dla aktywnych celów. Plan przeplata cele według terminów i dostępnych dni, pilnuje ich limitów oraz usuwa duplikaty. Ocenione próby pomniejszają dzisiejszą porcję o czas szacowany w pytaniu; pozostałą porcję 1–4 min także można uruchomić. Podgląd czasu pozwala świadomie wybrać dodatkową pracę. To szacunki, nie pomiar rzeczywistego czasu.
- **Wspólna rozpiska tygodnia.** Dzisiaj i Cele używają tej samej reguły. Plan obejmuje jedną najbliższą próbę każdego ćwiczenia i nie przyspiesza poprawnie wykonanych powtórek przed ich terminem. Przeterminowany lub zarchiwizowany cel nie przejmuje planu. Trudności można ćwiczyć jawnie we wszystkich przedmiotach.
- **Nauka z opracowanych materiałów.** Główna ścieżka to wgranie plików → opracowanie AI → sprawdzenie i zapis → nauka. Dzisiaj, biblioteka i ekran dodawania prowadzą do tego samego procesu. Z rozdziału notatki można przejść przez czytanie, odtworzenie z pamięci i porównanie. Próba nie jest automatycznie oceniana. Czytnik pamięta ostatni rozdział, oznacza rozdziały z wykonaną próbą i przenosi źródło do formularza pytania.
- **Porządkowanie.** Przedmioty i tematy mają archiwum; notatki i opracowania plików — kosz z przywracaniem. Kosz opracowania obejmuje jego notatkę i ćwiczenia. Przenoszenie tematów i treści zachowuje historię oraz odłącza niepasujące źródła i wymagania dawnego przedmiotu. Wcześniejsze migawki sesji pozostają czytelne.
- **Zadania na kartce i obrazy.** Można odpowiedzieć ustnie lub na kartce, bez wymuszonego przepisywania rozwiązania. Pytanie może mieć ilustrację PNG/JPG/WebP do 5 MB i 16 megapikseli. Obraz jest czyszczony z metadanych i dostępny tylko właścicielowi. Edycja obrazu nie zmienia go w już rozpoczętej sesji; eksport i usuwanie konta obejmują obrazy.
- **Sprawdzian.** Wybór 1–30 pytań równoważy tematy i uwzględnia długie zadania niezależnie od szacunkowego budżetu. Można pomijać, oznaczać do powrotu i poprawiać odpowiedzi. Ekran zakończenia pokazuje liczbę wysłanych odpowiedzi. Sam szkic nie jest wynikiem. Opcjonalny zegar tylko przypomina o czasie i biegnie również podczas przerwy.
- **Zakres egzaminu.** W celu można wkleić wymagania po jednym w wierszu, przypisać je do tematu i oznaczyć po własnej próbie. To deklaracja studenta, oddzielona od procentu podjętych pytań. Puste kategorie wyników pokazują „Brak danych”.
- **Materiały i AI.** Można wgrać do 5 plików naraz: PDF, DOCX, TXT, MD oraz PNG/JPG/WebP. Cały wybór jest walidowany przed zapisem. Limit: 10 MB na plik, 100 stron PDF i 16 megapikseli na zdjęcie. Prezentacje PPTX trzeba wcześniej wyeksportować do PDF. Opracowanie ma tryby „Wyjaśnij od podstaw”, „Szybka powtórka” i „Przygotuj zadania”; przy zapisie można zachować same pytania. Anulowanie blokuje publikację wyniku i zatrzymuje odczyt przy kolejnym zdarzeniu streamu; rozpoczęte przetwarzanie dostawcy może jeszcze trwać. Logowanie AI wraca do wybranego pliku. Model i uprawnienia pozostają zgodne z dotychczasowym połączeniem.
- **Wymiana zestawu.** Menu tematu pozwala pobrać JSON z notatkami, ćwiczeniami i obrazami, bez historii i danych konta. „Dodaj gotowy zestaw” pokazuje podgląd i tworzy własną kopię. Limity: 20 MB, 200 ćwiczeń i 50 notatek. Tekstowe importy pytań rozpoznają JSON lub dwie kolumny automatycznie; nadal nie obsługują .apkg.
- **Powroty.** W zwykłej nauce można włączyć jedną ponowną próbę błędu po innych pytaniach; potrzebne są co najmniej dwa pozostałe pytania. Pobrana notatka HTML działa bez sieci (wzory pozostają w notacji TeX). Można pobrać plik kalendarza z siedmioma przypomnieniami od jutra o 18:00 czasu polskiego; dodanie do kalendarza jest osobnym działaniem użytkownika.
- **Prostsze ekrany.** Dzisiaj zaczyna się od konkretnego planu lub wznowienia. Nawigacja ma cztery codzienne obszary; AI i eksport są w koncie. Adnotacje oraz zaawansowane opcje są rozwijane, rozdziały wybiera się po tytule, a poprawny wariant quizu zaznacza przy opcji.

Migracja 009 dodaje osobne tabele, bez przepisywania ćwiczeń i historii. Nowe dane należą do eksportu konta i są usuwane razem z kontem. Archiwum ZIP całego konta nadal służy pobraniu danych; import zestawu tematu nie jest odtwarzaniem całego konta.

Wejście zdjęć jest zgodne z [dokumentacją obrazów w Responses](https://developers.openai.com/api/docs/guides/images-vision). Testy używają syntetycznych streamów i nie potwierdzają rzeczywistej dostępności modelu, grantów ani jakości analizy obrazów.

Pełna synchronizacja odpowiedzi offline, Web Push, wspólna edycja i odzyskiwanie hasła pozostają poza tym wydaniem, zgodnie z zakresem planu.
