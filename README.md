# Mądra Nauka 2.0

Osobiste centrum nauki po polsku: przedmioty, tematy, notatki, linki i różne metody ćwiczenia. Plan dnia łączy pytania otwarte, zadania, quizy, luki i fiszki w jedną sesję.

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

- konta, logowanie, wylogowanie, oddzielne dane użytkowników;
- biblioteka przedmiotów i tematów; wyszukiwanie przedmiotów;
- notatki tekstowe i linki HTTP/HTTPS;
- pięć typów ćwiczeń, edycja z zachowaniem ID i historii, archiwizacja;
- mieszane sesje 5/10/20 minut, globalne lub dla konkretnego przedmiotu/tematu;
- quiz oceniany na serwerze; odpowiedzi otwarte, zadania i luki z porównaniem i samooceną;
- wynik zapisany od razu, bez duplikatów przy ponowieniu; cofnięcie ostatniej oceny;
- wznowienie sesji z niezmienną kolejnością i migawką treści;
- proste terminy powtórek, cele z datą i dziennym czasem;
- statystyki trzech wymiarów nauki, aktywność tygodniowa i historia sesji;
- eksport JSON i jawny import danych poprzedniej wersji;
- responsywny interfejs, CSRF, escaping treści i ograniczenie prób logowania.

Statystyki są wskaźnikiem zarejestrowanych ocen, a nie pomiarem gotowości do egzaminu. Plan wybiera powtórki, nowe ćwiczenia, a gdy nie ma zaległości — dodatkowe utrwalenie. Czas jest szacunkowy; pojedyncze zadanie może być dłuższe od wybranego krótkiego budżetu. Harmonogram jest prostą regułą, nie FSRS.

Audio, push, pełne offline, współdzielenie, reset hasła e-mailem i zaawansowany plan egzaminu należą do kolejnych etapów. Opracowanie wgranych materiałów wymaga połączenia ChatGPT; ręczne materiały i nauka działają lokalnie. Poprzedni service worker jest wyrejestrowywany, a stare cache HTML czyszczone — nowa aplikacja wymaga połączenia z serwerem.

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

W Bibliotece wybierz **Wgraj plik** albo użyj przycisku w istniejącym temacie. Obsługiwane są PDF (także skany), DOCX, TXT i Markdown. Limit to 10 MB i 100 stron PDF; TXT/MD wymagają UTF-8. Zaktualizuj zależności: `pip install -r requirements.txt`.

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

Przed połączeniem wymagana jest niezaznaczona domyślnie zgoda na korzystanie ze wspólnej puli Codex / ChatGPT Work i dostępnych kredytów ChatGPT / Codex. Dotychczasowe połączenia również wymagają zgody przed kolejnym generowaniem. Zgodę można wycofać w Połączeniu AI; blokuje to nowe generowanie, ale nie anuluje już wysłanych zadań. OpenAI decyduje o rozliczeniu użycia — brak osobnego przełącznika kredytów w tym flow. Kredyty API są oddzielne.

Wynik AI i zapisany temat mają menu rodzajów materiałów z licznikami oraz osobne sekcje pytań otwartych, quizów, zadań, fiszek i luk. Podgląd umożliwia zaznaczanie całych grup, a notatkę pokazuje do czytania z osobno rozwijaną edycją. Nowe generowanie domyślnie prosi o obszerną notatkę (zwykle 12–30 tys. znaków dla wielostronicowego źródła, maksymalnie 45 tys.), z tematami, objaśnieniami, rozwiązanymi przykładami i podsumowaniem; długość zależy od zakresu źródła. Dotychczasowe opracowania nie są automatycznie generowane ponownie.

Nowe opracowania AI zwracają rozdziały z tytułami i treścią, zapisane w edytowalnej notatce. Czytnik pokazuje spis treści oraz rozwijane rozdziały. Dostępny jest przed zapisem, po zapisie na ekranie pliku oraz jako osobna strona notatki z biblioteki. Starsze notatki z nagłówkami korzystają z nich, a długie notatki bez nagłówków są grupowane według akapitów do prezentacji; treść w bazie pozostaje bez zmian.

Generowanie zawsze używa `gpt-5.6-terra`. Model z formularza jest ignorowany przez backend. Brak Terra w katalogu konta blokuje generowanie z czytelnym komunikatem, bez przełączania na inny model.

### Logowanie ChatGPT na domenie

`MADRA_PUBLIC_URL=https://madranauka.online` włącza połączenie chmurowe. Callback OpenAI pozostaje `http://127.0.0.1:8085/auth/callback`, zgodnie z flow OSS. W Połączeniu AI pobierz `madra-login.py`, uruchom `python3 madra-login.py`, następnie kliknij Kontynuuj z ChatGPT. Pomocnik nasłuchuje wyłącznie na loopback, nie zapisuje tokenów ani logów URL; po odebraniu kodu zamyka się i wraca na domenę. Kod trafia we fragmencie URL, a przeglądarka usuwa fragment i przekazuje go POST-em z CSRF. Aplikacja nadal weryfikuje state, PKCE, nonce, podpis i tożsamość. Zaszyfrowane połączenia przechowuje w prywatnych obiektach GCS; między rewizjami odświeżanie tokenów chroni blokada i warunek generacji. Klucz OpenAI API nie jest potrzebny. Logowanie wymaga komputera z Pythonem 3; samo otwarcie strony na telefonie nie uruchomi lokalnego listenera. Limity planu/kredytów nadal wyznacza OpenAI.
